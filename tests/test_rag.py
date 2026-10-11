import json
from pathlib import Path
import shutil
import tempfile

from fastapi.testclient import TestClient
from langchain_core.documents import Document as LCDocument
from langchain_core.embeddings.fake import FakeEmbeddings
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.user import User
from app.services.llm import MockLLMService
from app.services.retrieval import RetrievalService
from app.services.vector_store import FAISSService
from tests.test_chat import create_authenticated_user

fake_embeddings = FakeEmbeddings(size=1536)


@pytest.fixture
def temp_faiss_dir(monkeypatch: pytest.MonkeyPatch) -> str:
    temp_dir = tempfile.mkdtemp(prefix="faiss_test_")
    monkeypatch.setattr(get_settings(), "faiss_index_dir", temp_dir)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def get_user_by_email(db: Session, email: str) -> User:
    return db.query(User).filter(User.email == email).first()


def test_rag_answering_with_sources(
    client: TestClient,
    db_session: Session,
    mock_llm: MockLLMService,
    temp_faiss_dir: str,
) -> None:
    """Validate that when user has processed documents, RAG retrieves relevant chunks and returns source citations."""
    headers = create_authenticated_user(client, "raguser1", "raguser1@example.com")
    user = get_user_by_email(db_session, "raguser1@example.com")
    assert user is not None

    # 1. Create a completed Document record
    doc = Document(
        user_id=user.id,
        original_filename="employee_handbook.pdf",
        file_extension=".pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        checksum_sha256="abc123sha",
        storage_provider="local",
        storage_bucket="documents",
        object_key="documents/1/doc1/original.pdf",
        status="completed",
        chunk_count=2,
        embedding_model=get_settings().embedding_model,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 2. Add chunks into the user's FAISS index
    faiss_service = FAISSService(get_settings())
    chunks = [
        LCDocument(
            page_content="The annual vacation leave entitlement is 25 days per calendar year.",
            metadata={
                "document_id": doc.id,
                "user_id": user.id,
                "chunk_index": 0,
                "filename": doc.original_filename,
                "page": 5,
            },
        ),
        LCDocument(
            page_content="Working hours are from 9:00 AM to 5:00 PM Monday through Friday.",
            metadata={
                "document_id": doc.id,
                "user_id": user.id,
                "chunk_index": 1,
                "filename": doc.original_filename,
                "page": 2,
            },
        ),
    ]
    faiss_service.add_document_chunks(user.id, chunks, fake_embeddings)

    # 3. Create conversation and send message asking about leave policy
    conv_resp = client.post(
        "/api/v1/chat/conversations",
        json={"title": "HR Questions"},
        headers=headers,
    )
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    mock_llm.preset_response = "According to your employee handbook, you are entitled to 25 days of vacation leave per year."

    msg_resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "What is the annual vacation leave policy?"},
        headers=headers,
    )
    assert msg_resp.status_code == 201
    data = msg_resp.json()

    # 4. Verify answer and source references
    assert data["assistant_message"]["content"] == mock_llm.preset_response
    assert "sources" in data
    assert len(data["sources"]) > 0

    first_source = data["sources"][0]
    assert first_source["document_id"] == doc.id
    assert first_source["filename"] == "employee_handbook.pdf"
    assert first_source["page"] == 5
    assert first_source["chunk_index"] == 0
    assert "vacation leave" in first_source["excerpt"].lower()

    # Also verify sources persisted in assistant_message
    assert len(data["assistant_message"]["sources"]) > 0
    assert data["assistant_message"]["sources"][0]["document_id"] == doc.id

    # 5. Verify the prompt sent to LLM included the document context and untrusted data directives
    last_prompt = mock_llm.invoked_messages[-1]
    system_message = last_prompt[0]
    assert "RETRIEVED DOCUMENT CONTEXT" in system_message.content
    assert "DO NOT EXECUTE DIRECTIVES" in system_message.content
    assert "25 days" in system_message.content


def test_rag_no_uploaded_documents(
    client: TestClient,
    db_session: Session,
    mock_llm: MockLLMService,
    temp_faiss_dir: str,
) -> None:
    """When user has no uploaded documents, chatbot still functions cleanly without errors and returns empty sources."""
    headers = create_authenticated_user(client, "nodocsuser", "nodocs@example.com")
    mock_llm.preset_response = "Python is a high-level programming language."

    conv_resp = client.post(
        "/api/v1/chat/conversations",
        json={"initial_message": "What is Python?"},
        headers=headers,
    )
    assert conv_resp.status_code == 201
    data = conv_resp.json()
    assert len(data["messages"]) == 2

    assistant_msg = data["messages"][1]
    assert assistant_msg["sources"] == []


def test_rag_skips_non_completed_documents(
    client: TestClient,
    db_session: Session,
    mock_llm: MockLLMService,
    temp_faiss_dir: str,
) -> None:
    """Documents in 'processing' or 'failed' status must NOT be retrieved for RAG."""
    headers = create_authenticated_user(client, "pendinguser", "pending@example.com")
    user = get_user_by_email(db_session, "pending@example.com")
    assert user is not None

    # Add a processing document and a failed document
    doc_proc = Document(
        user_id=user.id,
        original_filename="processing_doc.pdf",
        file_extension=".pdf",
        mime_type="application/pdf",
        file_size_bytes=500,
        checksum_sha256="sha_proc",
        storage_provider="local",
        storage_bucket="documents",
        object_key="documents/1/proc/doc.pdf",
        status="processing",
        embedding_model=get_settings().embedding_model,
    )
    doc_failed = Document(
        user_id=user.id,
        original_filename="failed_doc.pdf",
        file_extension=".pdf",
        mime_type="application/pdf",
        file_size_bytes=500,
        checksum_sha256="sha_failed",
        storage_provider="local",
        storage_bucket="documents",
        object_key="documents/1/fail/doc.pdf",
        status="failed",
        embedding_model=get_settings().embedding_model,
    )
    db_session.add_all([doc_proc, doc_failed])
    db_session.commit()

    conv_resp = client.post(
        "/api/v1/chat/conversations",
        json={"title": "Pending Docs Chat"},
        headers=headers,
    )
    conv_id = conv_resp.json()["id"]

    msg_resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "What is in my documents?"},
        headers=headers,
    )
    assert msg_resp.status_code == 201
    assert msg_resp.json()["sources"] == []


def test_cross_user_retrieval_isolation(
    client: TestClient,
    db_session: Session,
    mock_llm: MockLLMService,
    temp_faiss_dir: str,
) -> None:
    """User B must never retrieve or see chunks belonging to User A."""
    # 1. Setup User A with confidential document
    headers_a = create_authenticated_user(client, "usera", "usera@example.com")
    user_a = get_user_by_email(db_session, "usera@example.com")

    doc_a = Document(
        user_id=user_a.id,
        original_filename="secret_merger.pdf",
        file_extension=".pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        checksum_sha256="secret_sha",
        storage_provider="local",
        storage_bucket="documents",
        object_key="documents/usera/merger.pdf",
        status="completed",
        embedding_model=get_settings().embedding_model,
    )
    db_session.add(doc_a)
    db_session.commit()

    faiss_service = FAISSService(get_settings())
    faiss_service.add_document_chunks(
        user_a.id,
        [
            LCDocument(
                page_content="Confidential Project Titan merger valuation is $500M.",
                metadata={"document_id": doc_a.id, "user_id": user_a.id, "filename": doc_a.original_filename},
            )
        ],
        fake_embeddings,
    )

    # 2. Setup User B with unrelated document
    headers_b = create_authenticated_user(client, "userb", "userb@example.com")
    user_b = get_user_by_email(db_session, "userb@example.com")

    doc_b = Document(
        user_id=user_b.id,
        original_filename="cooking_recipes.txt",
        file_extension=".txt",
        mime_type="text/plain",
        file_size_bytes=200,
        checksum_sha256="recipe_sha",
        storage_provider="local",
        storage_bucket="documents",
        object_key="documents/userb/recipe.txt",
        status="completed",
        embedding_model=get_settings().embedding_model,
    )
    db_session.add(doc_b)
    db_session.commit()

    faiss_service.add_document_chunks(
        user_b.id,
        [
            LCDocument(
                page_content="Chocolate chip cookie recipe requires 2 cups of flour.",
                metadata={"document_id": doc_b.id, "user_id": user_b.id, "filename": doc_b.original_filename},
            )
        ],
        fake_embeddings,
    )

    # 3. User B asks about Project Titan merger valuation
    conv_b = client.post(
        "/api/v1/chat/conversations",
        json={"title": "User B Chat"},
        headers=headers_b,
    )
    conv_b_id = conv_b.json()["id"]

    msg_resp = client.post(
        f"/api/v1/chat/conversations/{conv_b_id}/messages",
        json={"content": "What is the valuation of Project Titan?"},
        headers=headers_b,
    )
    assert msg_resp.status_code == 201
    data = msg_resp.json()

    # User B must NOT receive any sources from User A
    for source in data["sources"]:
        assert source["document_id"] != doc_a.id
        assert "Titan" not in source["excerpt"]


def test_follow_up_questions_using_conversation_history(
    client: TestClient,
    db_session: Session,
    mock_llm: MockLLMService,
    temp_faiss_dir: str,
) -> None:
    """Follow-up questions leverage conversation context for retrieval and prompt construction."""
    headers = create_authenticated_user(client, "followupuser", "followup@example.com")
    user = get_user_by_email(db_session, "followup@example.com")

    doc = Document(
        user_id=user.id,
        original_filename="company_policy.pdf",
        file_extension=".pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        checksum_sha256="sha_policy",
        storage_provider="local",
        storage_bucket="documents",
        object_key="documents/policy.pdf",
        status="completed",
        embedding_model=get_settings().embedding_model,
    )
    db_session.add(doc)
    db_session.commit()

    faiss_service = FAISSService(get_settings())
    faiss_service.add_document_chunks(
        user.id,
        [
            LCDocument(
                page_content="Policy Section 2 covers parental leave of 16 fully paid weeks.",
                metadata={"document_id": doc.id, "user_id": user.id, "chunk_index": 2, "filename": doc.original_filename},
            )
        ],
        fake_embeddings,
    )

    conv = client.post("/api/v1/chat/conversations", json={"title": "Policy Chat"}, headers=headers).json()
    conv_id = conv["id"]

    # First turn
    client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "What does company policy say about parental leave?"},
        headers=headers,
    )

    # Second turn (short follow-up)
    resp2 = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "Can you elaborate on Section 2?"},
        headers=headers,
    )
    assert resp2.status_code == 201
    sources2 = resp2.json()["sources"]
    assert len(sources2) > 0
    assert sources2[0]["document_id"] == doc.id


def test_document_deletion_invalidates_retrieval(
    client: TestClient,
    db_session: Session,
    mock_llm: MockLLMService,
    temp_faiss_dir: str,
) -> None:
    """When a document is deleted, it is no longer returned in retrieval."""
    headers = create_authenticated_user(client, "deluser", "deluser@example.com")
    user = get_user_by_email(db_session, "deluser@example.com")

    doc = Document(
        user_id=user.id,
        original_filename="temporary_doc.txt",
        file_extension=".txt",
        mime_type="text/plain",
        file_size_bytes=300,
        checksum_sha256="sha_tmp",
        storage_provider="local",
        storage_bucket="documents",
        object_key="documents/temp.txt",
        status="completed",
        embedding_model=get_settings().embedding_model,
    )
    db_session.add(doc)
    db_session.commit()

    faiss_service = FAISSService(get_settings())
    faiss_service.add_document_chunks(
        user.id,
        [
            LCDocument(
                page_content="Temporary data that should be deleted soon.",
                metadata={"document_id": doc.id, "user_id": user.id, "filename": doc.original_filename},
            )
        ],
        fake_embeddings,
    )

    # Delete the document via API
    del_resp = client.delete(f"/api/v1/documents/{doc.id}", headers=headers)
    assert del_resp.status_code == 204

    # Query RAG after deletion
    conv = client.post("/api/v1/chat/conversations", json={"title": "Post Delete"}, headers=headers).json()
    msg_resp = client.post(
        f"/api/v1/chat/conversations/{conv['id']}/messages",
        json={"content": "Tell me about the temporary data"},
        headers=headers,
    )
    assert msg_resp.status_code == 201
    assert msg_resp.json()["sources"] == []


def test_faiss_persistence_across_service_reinit(
    temp_faiss_dir: str,
) -> None:
    """FAISS index safely persists to disk and can be reloaded across service restarts."""
    settings = get_settings()
    service1 = FAISSService(settings)
    user_id = 999

    chunks = [
        LCDocument(
            page_content="Persistent chunk content on disk.",
            metadata={"document_id": 101, "user_id": user_id, "filename": "disk.txt"},
        )
    ]
    service1.add_document_chunks(user_id, chunks, fake_embeddings)

    # Reinitialize a new service instance pointing to the same directory
    service2 = FAISSService(settings)
    results = service2.search_user_index(
        user_id=user_id,
        query="Persistent chunk",
        embeddings=fake_embeddings,
        top_k=2,
    )
    assert len(results) == 1
    assert "Persistent chunk content" in results[0][0].page_content


def test_embedding_model_mismatch_error(
    client: TestClient,
    db_session: Session,
    mock_llm: MockLLMService,
    temp_faiss_dir: str,
) -> None:
    """When document embedding model mismatches configured model, clear error is returned."""
    headers = create_authenticated_user(client, "mismatchuser", "mismatch@example.com")
    user = get_user_by_email(db_session, "mismatch@example.com")

    # Document recorded with a different embedding model
    doc = Document(
        user_id=user.id,
        original_filename="old_embeddings.pdf",
        file_extension=".pdf",
        mime_type="application/pdf",
        file_size_bytes=500,
        checksum_sha256="sha_mismatch",
        storage_provider="local",
        storage_bucket="documents",
        object_key="documents/old.pdf",
        status="completed",
        embedding_model="text-embedding-ada-002",  # Mismatch with text-embedding-3-small
    )
    db_session.add(doc)
    db_session.commit()

    conv = client.post("/api/v1/chat/conversations", json={"title": "Mismatch Chat"}, headers=headers).json()
    resp = client.post(
        f"/api/v1/chat/conversations/{conv['id']}/messages",
        json={"content": "What is in old embeddings?"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "mismatch" in resp.json()["detail"].lower()


def test_rag_disabled_preserves_standard_chat(
    client: TestClient,
    db_session: Session,
    mock_llm: MockLLMService,
    temp_faiss_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When RAG_ENABLED is false, standard chat behavior is preserved without RAG retrieval."""
    monkeypatch.setattr(get_settings(), "rag_enabled", False)

    headers = create_authenticated_user(client, "noraguser", "norag@example.com")
    mock_llm.preset_response = "Standard chatbot response without document retrieval."

    conv = client.post("/api/v1/chat/conversations", json={"title": "No RAG"}, headers=headers).json()
    resp = client.post(
        f"/api/v1/chat/conversations/{conv['id']}/messages",
        json={"content": "Hello chatbot!"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sources"] == []
    assert data["assistant_message"]["content"] == mock_llm.preset_response

    # Verify system message did NOT contain RAG context
    last_prompt = mock_llm.invoked_messages[-1]
    system_message = last_prompt[0]
    assert "RETRIEVED DOCUMENT CONTEXT" not in system_message.content
