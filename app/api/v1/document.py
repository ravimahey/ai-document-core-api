from fastapi import APIRouter, File, Query, UploadFile, status

from app.api.deps import CurrentActiveUserDep, DocumentServiceDep
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentRetryResponse,
    DocumentUploadResponse,
)

document_router = APIRouter(prefix="/documents", tags=["Document APIs"])


@document_router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a new document",
    description="Accepts a multipart file (.pdf, .docx, .txt, .md), uploads it to object storage, and enqueues background processing.",
)
async def upload_document(
    file: UploadFile = File(..., description="The document file to upload"),
    document_service: DocumentServiceDep = None,  # type: ignore[assignment]
    current_user: CurrentActiveUserDep = None,  # type: ignore[assignment]
) -> DocumentUploadResponse:
    doc = await document_service.upload_document(
        user_id=current_user.id,
        file=file,
    )
    return DocumentUploadResponse.model_validate(doc)


@document_router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List uploaded documents",
    description="Retrieve a paginated list of documents owned by the current user with optional status filtering.",
)
def list_documents(
    status_filter: str | None = Query(
        None,
        alias="status",
        description="Optional filter by status (e.g. queued, processing, completed, failed)",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    document_service: DocumentServiceDep = None,  # type: ignore[assignment]
    current_user: CurrentActiveUserDep = None,  # type: ignore[assignment]
) -> DocumentListResponse:
    docs, total, has_more = document_service.list_documents(
        user_id=current_user.id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@document_router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document details",
    description="Retrieve metadata, chunk count, and processing status for a single document owned by the user.",
)
def get_document(
    document_id: int,
    document_service: DocumentServiceDep = None,  # type: ignore[assignment]
    current_user: CurrentActiveUserDep = None,  # type: ignore[assignment]
) -> DocumentResponse:
    doc = document_service.get_document(
        user_id=current_user.id,
        document_id=document_id,
    )
    return DocumentResponse.model_validate(doc)


@document_router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description="Deletes the document record, deletes the file from object storage, and purges its vector embeddings from FAISS.",
)
def delete_document(
    document_id: int,
    document_service: DocumentServiceDep = None,  # type: ignore[assignment]
    current_user: CurrentActiveUserDep = None,  # type: ignore[assignment]
) -> None:
    document_service.delete_document(
        user_id=current_user.id,
        document_id=document_id,
    )


@document_router.post(
    "/{document_id}/retry",
    response_model=DocumentRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry failed document processing",
    description="Re-enqueues a document for background processing if it is currently in 'failed' status.",
)
def retry_document(
    document_id: int,
    document_service: DocumentServiceDep = None,  # type: ignore[assignment]
    current_user: CurrentActiveUserDep = None,  # type: ignore[assignment]
) -> DocumentRetryResponse:
    doc = document_service.retry_processing(
        user_id=current_user.id,
        document_id=document_id,
    )
    return DocumentRetryResponse(
        id=doc.id,
        status=doc.status,
        message="Document processing task has been re-enqueued.",
    )
