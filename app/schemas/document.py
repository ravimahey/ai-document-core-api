from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    id: int
    original_filename: str
    file_extension: str
    mime_type: str
    file_size_bytes: int
    status: str
    chunk_count: int
    embedding_model: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResponse(BaseModel):
    id: int
    original_filename: str
    status: str
    file_size_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class DocumentRetryResponse(BaseModel):
    id: int
    status: str
    message: str
