from datetime import datetime, timezone
import logging
from pathlib import Path
import tempfile
from typing import Any

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document as LCDocument
from langchain_core.embeddings import Embeddings
from langchain_core.embeddings.fake import FakeEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import openai

from app.core.config import get_settings
from app.core.exceptions import EmptyDocumentError, StorageError
from app.db.session import SessionLocal
from app.models.document import Document
from app.services.storage import get_storage_service
from app.services.vector_store import get_faiss_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_embeddings(settings: Any) -> Embeddings:
    if settings.openai_api_key:
        return OpenAIEmbeddings(
            model=settings.embedding_model,
            openai_api_key=settings.openai_api_key,
        )
    logger.warning(
        "OPENAI_API_KEY is not configured. Falling back to FakeEmbeddings for task."
    )
    return FakeEmbeddings(size=1536)


def _load_document_content(file_path: Path, extension: str) -> list[LCDocument]:
    ext = extension.lower()
    if ext == ".pdf":
        loader = PyPDFLoader(str(file_path))
    elif ext == ".docx":
        loader = Docx2txtLoader(str(file_path))
    elif ext in (".txt", ".md"):
        loader = TextLoader(str(file_path), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported file format: {extension}")

    docs = loader.load()
    if not docs or not any(d.page_content.strip() for d in docs):
        raise EmptyDocumentError("The document contains no readable text.")
    return docs


@celery_app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(
        StorageError,
        openai.RateLimitError,
        openai.APITimeoutError,
        openai.APIConnectionError,
    ),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_document_task(self, document_id: int) -> dict[str, Any]:
    """Asynchronously extracts text, chunks, embeds, and indexes an uploaded document."""
    settings = get_settings()
    storage = get_storage_service(settings)
    faiss_service = get_faiss_service(settings)

    db = SessionLocal()
    temp_file_path: Path | None = None

    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning(
                "Document %s not found in database. Aborting processing.",
                document_id,
            )
            return {"status": "skipped", "reason": "not_found"}

        if document.status == "deleting":
            logger.info(
                "Document %s is being deleted. Aborting processing.",
                document_id,
            )
            return {"status": "skipped", "reason": "deleting"}

        # 1. Update status to processing
        document.status = "processing"
        document.processing_started_at = datetime.now(timezone.utc)
        document.celery_task_id = self.request.id
        db.commit()

        # 2. Download from storage to secure temporary file
        with tempfile.NamedTemporaryFile(
            suffix=document.file_extension, delete=False
        ) as tmp:
            temp_file_path = Path(tmp.name)

        storage.download_file(document.object_key, str(temp_file_path))

        # 3. Extract text
        raw_documents = _load_document_content(
            temp_file_path, document.file_extension
        )

        # 4. Split text into chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        split_chunks = splitter.split_documents(raw_documents)

        # Filter out empty chunks and attach deterministic metadata
        final_chunks: list[LCDocument] = []
        for idx, chunk in enumerate(split_chunks):
            content = chunk.page_content.strip()
            if not content:
                continue
            metadata = {
                "document_id": document.id,
                "user_id": document.user_id,
                "chunk_index": idx,
                "filename": document.original_filename,
                **chunk.metadata,
            }
            final_chunks.append(
                LCDocument(page_content=content, metadata=metadata)
            )

        if not final_chunks:
            raise EmptyDocumentError("No valid text chunks could be produced.")

        # 5. Embed and persist to user's FAISS index
        embeddings = _get_embeddings(settings)
        faiss_service.add_document_chunks(
            user_id=document.user_id,
            chunks=final_chunks,
            embeddings=embeddings,
        )

        # 6. Re-check deletion state before final commit
        db.refresh(document)
        if document.status == "deleting":
            logger.info(
                "Document %s was marked for deletion during processing. Purging vectors.",
                document_id,
            )
            faiss_service.delete_document_chunks(
                document.user_id, document.id, embeddings
            )
            return {"status": "discarded", "reason": "deleted_during_task"}

        # 7. Mark completed
        document.status = "completed"
        document.chunk_count = len(final_chunks)
        document.embedding_model = settings.embedding_model
        document.processing_completed_at = datetime.now(timezone.utc)
        document.error_message = None
        db.commit()

        logger.info(
            "Document %s successfully processed (%s chunks indexed).",
            document.id,
            len(final_chunks),
        )
        return {
            "status": "completed",
            "document_id": document.id,
            "chunks": len(final_chunks),
        }

    except Exception as exc:
        logger.error(
            "Error processing document %s: %s", document_id, exc, exc_info=True
        )

        # Re-fetch document to safely record failure
        try:
            doc_record = db.get(Document, document_id)
            if doc_record and doc_record.status != "deleting":
                # Check if this task will be retried
                if self.request.retries < self.max_retries and isinstance(
                    exc,
                    (
                        StorageError,
                        openai.RateLimitError,
                        openai.APITimeoutError,
                        openai.APIConnectionError,
                    ),
                ):
                    doc_record.error_message = (
                        f"Transient error (retry {self.request.retries + 1}/{self.max_retries}): {exc}"[
                            :500
                        ]
                    )
                else:
                    doc_record.status = "failed"
                    doc_record.error_message = f"Processing failed: {exc}"[
                        :500
                    ]
                db.commit()
        except Exception as db_exc:
            logger.error(
                "Failed to update document status to failed: %s", db_exc
            )

        raise exc

    finally:
        db.close()
        if temp_file_path and temp_file_path.exists():
            try:
                temp_file_path.unlink(missing_ok=True)
            except Exception as clean_err:
                logger.warning(
                    "Failed to delete temporary file %s: %s",
                    temp_file_path,
                    clean_err,
                )
