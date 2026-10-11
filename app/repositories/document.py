from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session):
        self._db = db

    def add(self, document: Document) -> None:
        self._db.add(document)
        self._db.flush()

    def get_by_id(self, document_id: int) -> Document | None:
        query = select(Document).where(Document.id == document_id)
        return self._db.scalar(query)

    def get_by_id_and_user(
        self, document_id: int, user_id: int
    ) -> Document | None:
        query = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        return self._db.scalar(query)

    def list_user_documents(
        self,
        user_id: int,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Document], int]:
        total_query = select(func.count(Document.id)).where(
            Document.user_id == user_id
        )
        if status:
            total_query = total_query.where(Document.status == status)
        total = int(self._db.scalar(total_query) or 0)

        query = select(Document).where(Document.user_id == user_id)
        if status:
            query = query.where(Document.status == status)

        query = query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
        documents = list(self._db.scalars(query).all())
        return documents, total

    def delete(self, document: Document) -> None:
        self._db.delete(document)
        self._db.flush()

    def update_status(
        self,
        document: Document,
        status: str,
        error_message: str | None = None,
    ) -> None:
        document.status = status
        document.error_message = error_message
        document.updated_at = datetime.now(timezone.utc)
        self._db.flush()
