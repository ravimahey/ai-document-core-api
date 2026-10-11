from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class SourceCitation(BaseModel):
    document_id: int
    filename: str
    page: int | None = None
    chunk_index: int | None = None
    excerpt: str | None = None
    score: float | None = None


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    sources: list[SourceCitation] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    title: str | None = Field(
        default=None, max_length=255, description="Optional custom title"
    )
    initial_message: str | None = Field(
        default=None, description="Optional first user message"
    )


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]

    model_config = ConfigDict(from_attributes=True)


class SendMessageRequest(BaseModel):
    content: str = Field(
        min_length=1,
        description="User message content",
    )


class ChatExchangeResponse(BaseModel):
    conversation_id: int
    user_message: MessageResponse
    assistant_message: MessageResponse
    sources: list[SourceCitation] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def message(self) -> MessageResponse:
        return self.assistant_message


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
