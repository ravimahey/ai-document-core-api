from dataclasses import dataclass
import logging
from typing import Any

from langchain_core.documents import Document as LCDocument
from langchain_core.embeddings import Embeddings
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import EmbeddingModelMismatchError
from app.models.document import Document
from app.services.vector_store import FAISSService, get_embeddings

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    document_id: int
    filename: str
    page: int | None
    chunk_index: int | None
    content: str
    score: float | None


class RetrievalService:
    """Service to search user-isolated FAISS indexes for relevant document chunks."""

    def __init__(
        self,
        db: Session,
        faiss_service: FAISSService,
        settings: Settings | None = None,
        embeddings: Embeddings | None = None,
    ):
        self._db = db
        self._faiss = faiss_service
        self._settings = settings or get_settings()
        self._embeddings = embeddings or get_embeddings(self._settings)

    def retrieve(
        self,
        user_id: int,
        query: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Search eligible completed documents owned by user_id and return relevant chunks."""
        clean_query = query.strip() if query else ""
        if not clean_query:
            return []

        # 1. Fetch eligible documents for user_id with status == 'completed'
        stmt = (
            select(Document)
            .where(
                Document.user_id == user_id,
                Document.status == "completed",
            )
        )
        completed_docs = list(self._db.scalars(stmt).all())
        if not completed_docs:
            logger.debug(
                "User %s has no completed documents; skipping FAISS retrieval.",
                user_id,
            )
            return []

        # 2. Check for embedding model mismatch
        target_model = self._settings.embedding_model
        for doc in completed_docs:
            if doc.embedding_model and doc.embedding_model != target_model:
                raise EmbeddingModelMismatchError(
                    f"Document '{doc.original_filename}' was embedded with "
                    f"'{doc.embedding_model}' which does not match current configured model '{target_model}'."
                )

        allowed_doc_ids = {doc.id for doc in completed_docs}
        doc_filename_map = {
            doc.id: doc.original_filename for doc in completed_docs
        }

        # 3. Perform similarity search on the user's isolated FAISS index
        k = top_k or self._settings.rag_top_k
        raw_results = self._faiss.search_user_index(
            user_id=user_id,
            query=clean_query,
            embeddings=self._embeddings,
            top_k=k,
            allowed_document_ids=allowed_doc_ids,
        )

        # 4. Filter by similarity threshold if configured
        threshold = self._settings.rag_similarity_threshold
        filtered_results: list[tuple[LCDocument, float]] = []
        for doc_chunk, score in raw_results:
            if threshold is not None and score > threshold:
                continue
            filtered_results.append((doc_chunk, score))

        # 5. Deduplicate and enforce max context characters
        chunks: list[RetrievedChunk] = []
        seen_contents: set[str] = set()
        total_chars = 0
        max_chars = self._settings.rag_max_context_characters

        for doc_chunk, score in filtered_results:
            content = doc_chunk.page_content.strip()
            if not content or content in seen_contents:
                continue

            metadata = doc_chunk.metadata or {}
            chunk_doc_id = metadata.get("document_id")

            # Double-check isolation: document must belong to allowed completed docs
            if chunk_doc_id not in allowed_doc_ids:
                continue

            if total_chars + len(content) > max_chars and chunks:
                break

            seen_contents.add(content)
            total_chars += len(content)

            filename = metadata.get("filename") or doc_filename_map.get(
                chunk_doc_id, "unknown"
            )
            page = metadata.get("page")
            chunk_index = metadata.get("chunk_index")

            chunks.append(
                RetrievedChunk(
                    document_id=int(chunk_doc_id),
                    filename=str(filename),
                    page=int(page) if page is not None else None,
                    chunk_index=int(chunk_index) if chunk_index is not None else None,
                    content=content,
                    score=float(score) if score is not None else None,
                )
            )

        return chunks
