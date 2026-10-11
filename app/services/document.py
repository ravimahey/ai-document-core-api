import hashlib
import logging
from pathlib import Path
import tempfile
from typing import Any
import uuid

from fastapi import UploadFile
from langchain_core.embeddings import Embeddings
from langchain_core.embeddings.fake import FakeEmbeddings
from langchain_openai import OpenAIEmbeddings
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    DocumentAccessDeniedError,
    DocumentNotEligibleForRetryError,
    DocumentNotFoundError,
    EmptyDocumentError,
    FileTooLargeError,
    InvalidFileTypeError,
    StorageError,
)
from app.models.document import Document
from app.repositories.document import DocumentRepository
from app.services.storage import BaseStorageService
from app.services.vector_store import FAISSService
from app.tasks.document_tasks import process_document_task

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/octet-stream",
}


def _get_embeddings(settings: Settings) -> Embeddings:
    if settings.openai_api_key:
        return OpenAIEmbeddings(
            model=settings.embedding_model,
            openai_api_key=settings.openai_api_key,
        )
    return FakeEmbeddings(size=1536)


class DocumentService:
    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository,
        storage_service: BaseStorageService,
        faiss_service: FAISSService,
        settings: Settings | None = None,
    ):
        self._db = db
        self._repo = document_repository
        self._storage = storage_service
        self._faiss = faiss_service
        self._settings = settings or get_settings()

    async def upload_document(
        self,
        user_id: int,
        file: UploadFile,
    ) -> Document:
        """Stream, validate, store, and enqueue a document for processing."""
        # 1. Clean and validate filename & extension
        raw_filename = file.filename or "uploaded_file"
        safe_filename = Path(raw_filename).name
        extension = Path(safe_filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise InvalidFileTypeError(
                f"Unsupported file type '{extension}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
            )

        # 2. Stream file and compute SHA256 checksum while enforcing size limit
        hasher = hashlib.sha256()
        total_size = 0
        spool = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)

        try:
            while chunk := await file.read(64 * 1024):
                total_size += len(chunk)
                if total_size > self._settings.max_upload_size_bytes:
                    limit_mb = self._settings.max_upload_size_bytes / (
                        1024 * 1024
                    )
                    raise FileTooLargeError(
                        f"File size exceeds the {limit_mb:.1f} MB upload limit."
                    )
                hasher.update(chunk)
                spool.write(chunk)

            if total_size == 0:
                raise EmptyDocumentError("The uploaded file is empty (0 bytes).")

            checksum = hasher.hexdigest()

            # 3. Generate server-controlled unique object key
            doc_uuid = uuid.uuid4().hex
            safe_ext = extension.lstrip(".")
            object_key = (
                f"documents/{user_id}/{doc_uuid}/original.{safe_ext}"
            )

            # 4. Upload to MinIO / S3 storage
            spool.seek(0)
            content_type = file.content_type or "application/octet-stream"
            try:
                self._storage.upload_file(
                    file_obj=spool,
                    object_key=object_key,
                    content_type=content_type,
                    metadata={
                        "owner_id": str(user_id),
                        "checksum": checksum,
                        "original_filename": safe_filename,
                    },
                )
            except Exception as exc:
                logger.error("Failed uploading object to storage: %s", exc)
                raise StorageError(
                    "Failed to save document to storage service."
                ) from exc

        finally:
            spool.close()

        # 5. Save database record
        doc = Document(
            user_id=user_id,
            original_filename=safe_filename,
            file_extension=extension,
            mime_type=file.content_type or "application/octet-stream",
            file_size_bytes=total_size,
            checksum_sha256=checksum,
            storage_provider=self._storage.provider_name,
            storage_bucket=self._storage.bucket_name,
            object_key=object_key,
            status="queued",
            chunk_count=0,
        )

        try:
            self._repo.add(doc)
            self._db.commit()
            self._db.refresh(doc)
        except Exception as db_exc:
            logger.error("Failed creating document record: %s", db_exc)
            # Rollback storage: remove uploaded object to prevent orphaned blobs
            try:
                self._storage.delete_object(object_key)
            except Exception as clean_err:
                logger.error("Failed cleaning up orphaned object: %s", clean_err)
            raise db_exc

        # 6. Enqueue Celery background processing task
        try:
            task = process_document_task.delay(doc.id)
            doc.celery_task_id = str(task.id)
            self._db.commit()
        except Exception as celery_exc:
            logger.error("Failed enqueueing Celery task: %s", celery_exc)
            doc.status = "failed"
            doc.error_message = (
                "Document saved but background task dispatch failed."
            )
            self._db.commit()

        return doc

    def list_documents(
        self,
        user_id: int,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Document], int, bool]:
        """List documents owned by the user with pagination and optional status filter."""
        safe_page = max(1, page)
        safe_limit = min(max(1, page_size), 100)
        skip = (safe_page - 1) * safe_limit

        docs, total = self._repo.list_user_documents(
            user_id=user_id,
            status=status,
            skip=skip,
            limit=safe_limit,
        )
        has_more = (skip + len(docs)) < total
        return docs, total, has_more

    def get_document(self, user_id: int, document_id: int) -> Document:
        """Get document details ensuring owner isolation."""
        doc = self._repo.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError()

        if doc.user_id != user_id:
            raise DocumentAccessDeniedError()

        return doc

    def delete_document(self, user_id: int, document_id: int) -> None:
        """Delete document, object storage file, and FAISS vector embeddings."""
        doc = self._repo.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError()

        if doc.user_id != user_id:
            raise DocumentAccessDeniedError()

        # 1. Mark status as deleting so concurrent or running workers discard results
        doc.status = "deleting"
        self._db.commit()

        # 2. Remove file from object storage
        try:
            self._storage.delete_object(doc.object_key)
        except Exception as storage_err:
            logger.warning(
                "Error deleting object '%s' from storage: %s",
                doc.object_key,
                storage_err,
            )

        # 3. Remove document embeddings from FAISS
        try:
            embeddings = _get_embeddings(self._settings)
            self._faiss.delete_document_chunks(
                user_id=user_id,
                document_id=doc.id,
                embeddings=embeddings,
            )
        except Exception as faiss_err:
            logger.warning(
                "Error purging FAISS vectors for document %s: %s",
                document_id,
                faiss_err,
            )

        # 4. Remove database record
        self._repo.delete(doc)
        self._db.commit()

    def retry_processing(self, user_id: int, document_id: int) -> Document:
        """Retry a failed document processing task."""
        doc = self._repo.get_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError()

        if doc.user_id != user_id:
            raise DocumentAccessDeniedError()

        if doc.status != "failed":
            raise DocumentNotEligibleForRetryError(
                f"Cannot retry document with status '{doc.status}'. Only 'failed' documents are eligible."
            )

        # Reset document to queued
        doc.status = "queued"
        doc.error_message = None
        self._db.commit()

        # Enqueue Celery task
        try:
            task = process_document_task.delay(doc.id)
            doc.celery_task_id = str(task.id)
            self._db.commit()
        except Exception as celery_exc:
            logger.error("Failed to re-enqueue Celery task: %s", celery_exc)
            doc.status = "failed"
            doc.error_message = "Failed to dispatch retry task."
            self._db.commit()

        return doc
