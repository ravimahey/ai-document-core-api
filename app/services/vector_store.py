from contextlib import contextmanager
import logging
from pathlib import Path
import shutil
from typing import Generator

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document as LCDocument
from langchain_core.embeddings import Embeddings

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@contextmanager
def file_lock(lock_path: Path) -> Generator[None]:
    """Simple cross-platform filesystem lock to synchronize user index modifications."""
    lock_file = lock_path.with_suffix(".lock")
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    # Simple spin-lock with bounded timeout
    import time

    start = time.time()
    acquired = False
    while time.time() - start < 15.0:
        try:
            # Atomic creation on OS level
            lock_fd = lock_file.open("x")
            lock_fd.close()
            acquired = True
            break
        except FileExistsError:
            time.sleep(0.05)

    try:
        yield
    finally:
        if acquired:
            try:
                lock_file.unlink(missing_ok=True)
            except Exception:
                pass


class FAISSService:
    """Manages persistent, user-isolated FAISS vector indexes."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_dir = Path(settings.faiss_index_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_index_dir(self, user_id: int) -> Path:
        user_dir = self._base_dir / f"user_{user_id}"
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def add_document_chunks(
        self,
        user_id: int,
        chunks: list[LCDocument],
        embeddings: Embeddings,
    ) -> int:
        """Add document chunks to the user's isolated FAISS index."""
        if not chunks:
            return 0

        user_dir = self._get_user_index_dir(user_id)
        index_file = user_dir / "index.faiss"

        with file_lock(user_dir):
            if index_file.exists():
                logger.info(
                    "Loading existing FAISS index for user %s from %s",
                    user_id,
                    user_dir,
                )
                vector_store = FAISS.load_local(
                    folder_path=str(user_dir),
                    embeddings=embeddings,
                    allow_dangerous_deserialization=True,  # Server-owned trusted path only
                )
                vector_store.add_documents(chunks)
            else:
                logger.info(
                    "Creating new FAISS index for user %s at %s",
                    user_id,
                    user_dir,
                )
                vector_store = FAISS.from_documents(chunks, embeddings)

            vector_store.save_local(str(user_dir))

        return len(chunks)

    def delete_document_chunks(
        self,
        user_id: int,
        document_id: int,
        embeddings: Embeddings,
    ) -> None:
        """Delete all vectors matching document_id from the user's FAISS index."""
        user_dir = self._get_user_index_dir(user_id)
        index_file = user_dir / "index.faiss"

        if not index_file.exists():
            return

        with file_lock(user_dir):
            if not index_file.exists():
                return

            try:
                vector_store = FAISS.load_local(
                    folder_path=str(user_dir),
                    embeddings=embeddings,
                    allow_dangerous_deserialization=True,
                )

                # Locate all vector IDs associated with this document ID
                ids_to_delete: list[str] = []
                for (
                    doc_id,
                    doc_obj,
                ) in vector_store.docstore._dict.items():  # type: ignore[attr-defined]
                    if doc_obj.metadata.get("document_id") == document_id:
                        ids_to_delete.append(doc_id)

                if ids_to_delete:
                    vector_store.delete(ids_to_delete)
                    if len(vector_store.docstore._dict) == 0:  # type: ignore[attr-defined]
                        # Remove directory if empty
                        shutil.rmtree(user_dir, ignore_errors=True)
                    else:
                        vector_store.save_local(str(user_dir))
                    logger.info(
                        "Deleted %s vectors for document %s from user %s index",
                        len(ids_to_delete),
                        document_id,
                        user_id,
                    )
            except Exception as exc:
                logger.error(
                    "Error deleting vectors for document %s (user %s): %s",
                    document_id,
                    user_id,
                    exc,
                )


def get_faiss_service(
    settings: Settings | None = None,
) -> FAISSService:
    settings = settings or get_settings()
    return FAISSService(settings)
