from fastapi import APIRouter, Query, status

from app.api.deps import ChatServiceDep, CurrentActiveUserDep
from app.schemas.chat import (
    ChatExchangeResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageResponse,
    SendMessageRequest,
)

chat_router = APIRouter(prefix="/chat", tags=["Chat APIs"])


@chat_router.post(
    "/conversations",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreate,
    chat_service: ChatServiceDep,
    current_user: CurrentActiveUserDep,
) -> ConversationDetailResponse:
    """Create a new conversation thread, optionally sending an initial message."""
    conversation, user_msg, assistant_msg = chat_service.create_conversation(
        user_id=current_user.id,
        title=payload.title,
        initial_message=payload.initial_message,
    )

    messages_list: list[MessageResponse] = []
    if user_msg:
        messages_list.append(MessageResponse.model_validate(user_msg))
    if assistant_msg:
        messages_list.append(MessageResponse.model_validate(assistant_msg))

    return ConversationDetailResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages_list,
    )


@chat_router.get(
    "/conversations",
    response_model=ConversationListResponse,
    status_code=status.HTTP_200_OK,
)
def list_conversations(
    chat_service: ChatServiceDep,
    current_user: CurrentActiveUserDep,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> ConversationListResponse:
    """List conversations belonging to the authenticated user with pagination."""
    conversations, total, has_more = chat_service.list_conversations(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )

    conversation_dtos = [
        ConversationResponse(
            id=c.id,
            user_id=c.user_id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=len(c.messages) if c.messages else 0,
        )
        for c in conversations
    ]

    return ConversationListResponse(
        conversations=conversation_dtos,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@chat_router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_200_OK,
)
def get_conversation(
    conversation_id: int,
    chat_service: ChatServiceDep,
    current_user: CurrentActiveUserDep,
) -> ConversationDetailResponse:
    """Retrieve an existing conversation and its chronological message history."""
    conversation, messages = chat_service.get_conversation_with_messages(
        user_id=current_user.id,
        conversation_id=conversation_id,
    )

    return ConversationDetailResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@chat_router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
)
def rename_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    chat_service: ChatServiceDep,
    current_user: CurrentActiveUserDep,
) -> ConversationResponse:
    """Rename an existing conversation title."""
    conversation = chat_service.rename_conversation(
        user_id=current_user.id,
        conversation_id=conversation_id,
        new_title=payload.title,
    )

    return ConversationResponse.model_validate(conversation)


@chat_router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: int,
    chat_service: ChatServiceDep,
    current_user: CurrentActiveUserDep,
) -> None:
    """Delete a conversation thread and all its messages."""
    chat_service.delete_conversation(
        user_id=current_user.id,
        conversation_id=conversation_id,
    )


@chat_router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatExchangeResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    conversation_id: int,
    payload: SendMessageRequest,
    chat_service: ChatServiceDep,
    current_user: CurrentActiveUserDep,
) -> ChatExchangeResponse:
    """Send a user message in an existing conversation and receive an AI assistant response."""
    user_msg, assistant_msg = chat_service.send_message(
        user_id=current_user.id,
        conversation_id=conversation_id,
        content=payload.content,
    )

    assistant_msg_response = MessageResponse.model_validate(assistant_msg)
    return ChatExchangeResponse(
        conversation_id=conversation_id,
        user_message=MessageResponse.model_validate(user_msg),
        assistant_message=assistant_msg_response,
        sources=assistant_msg_response.sources,
    )
