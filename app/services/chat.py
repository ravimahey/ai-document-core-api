from datetime import datetime
import logging

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConversationAccessDeniedError,
    ConversationNotFoundError,
    EmptyMessageError,
    MessageLengthExceededError,
)
from app.models.chat import Conversation, Message
from app.repositories.chat import ChatRepository
from app.services.llm import BaseLLMService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        db: Session,
        chat_repository: ChatRepository,
        llm_service: BaseLLMService,
        settings: Settings | None = None,
    ):
        self._db = db
        self._repo = chat_repository
        self._llm = llm_service
        self._settings = settings or get_settings()

    def create_conversation(
        self,
        user_id: int,
        title: str | None = None,
        initial_message: str | None = None,
    ) -> tuple[Conversation, Message | None, Message | None]:
        """Create a new conversation thread, optionally sending an initial message."""
        clean_title = title.strip() if title and title.strip() else "New conversation"
        conversation = self._repo.create_conversation(
            user_id=user_id,
            title=clean_title,
        )

        user_msg: Message | None = None
        assistant_msg: Message | None = None

        if initial_message and initial_message.strip():
            clean_msg = initial_message.strip()
            if len(clean_msg) > self._settings.chat_max_input_characters:
                raise MessageLengthExceededError(
                    f"Message exceeds maximum length of {self._settings.chat_max_input_characters} characters."
                )

            # Auto-title if user didn't supply a custom title
            if clean_title == "New conversation":
                auto_title = clean_msg[:45].strip()
                if len(clean_msg) > 45:
                    auto_title += "..."
                self._repo.update_conversation_title(conversation, auto_title)

            user_msg = self._repo.add_message(
                conversation_id=conversation.id,
                role="user",
                content=clean_msg,
            )
            self._db.flush()

            prompt_messages: list[BaseMessage] = [HumanMessage(content=clean_msg)]

            try:
                llm_result = self._llm.generate_chat_response(prompt_messages)
            except Exception:
                self._db.rollback()
                raise

            assistant_msg = self._repo.add_message(
                conversation_id=conversation.id,
                role="assistant",
                content=llm_result.content,
                model=llm_result.model,
                prompt_tokens=llm_result.prompt_tokens,
                completion_tokens=llm_result.completion_tokens,
                total_tokens=llm_result.total_tokens,
            )
            self._repo.update_conversation_timestamp(conversation)

        self._db.commit()
        self._db.refresh(conversation)
        if user_msg:
            self._db.refresh(user_msg)
        if assistant_msg:
            self._db.refresh(assistant_msg)

        return conversation, user_msg, assistant_msg

    def list_conversations(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Conversation], int, bool]:
        """List user conversations with pagination."""
        safe_page = max(1, page)
        safe_limit = min(max(1, page_size), 100)
        skip = (safe_page - 1) * safe_limit

        conversations, total = self._repo.list_conversations(
            user_id=user_id,
            skip=skip,
            limit=safe_limit,
        )
        has_more = (skip + len(conversations)) < total
        return conversations, total, has_more

    def get_conversation_with_messages(
        self,
        user_id: int,
        conversation_id: int,
    ) -> tuple[Conversation, list[Message]]:
        """Retrieve conversation and its full message history."""
        conversation = self._repo.get_conversation(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError()

        if conversation.user_id != user_id:
            raise ConversationAccessDeniedError()

        messages = self._repo.get_messages(conversation_id)
        return conversation, messages

    def rename_conversation(
        self,
        user_id: int,
        conversation_id: int,
        new_title: str,
    ) -> Conversation:
        """Rename an existing conversation."""
        conversation = self._repo.get_conversation(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError()

        if conversation.user_id != user_id:
            raise ConversationAccessDeniedError()

        clean_title = new_title.strip()
        if not clean_title:
            raise EmptyMessageError("Conversation title cannot be empty.")

        updated = self._repo.update_conversation_title(conversation, clean_title)
        self._db.commit()
        self._db.refresh(updated)
        return updated

    def delete_conversation(
        self,
        user_id: int,
        conversation_id: int,
    ) -> None:
        """Delete a conversation and its messages."""
        conversation = self._repo.get_conversation(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError()

        if conversation.user_id != user_id:
            raise ConversationAccessDeniedError()

        self._repo.delete_conversation(conversation)
        self._db.commit()

    def send_message(
        self,
        user_id: int,
        conversation_id: int,
        content: str,
    ) -> tuple[Message, Message]:
        """Send a user message in an existing conversation and generate an AI response."""
        conversation = self._repo.get_conversation(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError()

        if conversation.user_id != user_id:
            raise ConversationAccessDeniedError()

        clean_content = content.strip()
        if not clean_content:
            raise EmptyMessageError("Message content cannot be empty.")

        if len(clean_content) > self._settings.chat_max_input_characters:
            raise MessageLengthExceededError(
                f"Message exceeds maximum length of {self._settings.chat_max_input_characters} characters."
            )

        # Auto-update default title on first message exchange
        if conversation.title == "New conversation":
            auto_title = clean_content[:45].strip()
            if len(clean_content) > 45:
                auto_title += "..."
            self._repo.update_conversation_title(conversation, auto_title)

        # 1. Add user message
        user_msg = self._repo.add_message(
            conversation_id=conversation_id,
            role="user",
            content=clean_content,
        )
        self._db.flush()

        # 2. Retrieve recent history for context window
        recent_messages = self._repo.get_recent_messages(
            conversation_id=conversation_id,
            limit=self._settings.chat_history_message_limit,
        )

        # 3. Format into LangChain message types
        langchain_msgs: list[BaseMessage] = []
        for msg in recent_messages:
            if msg.role == "user":
                langchain_msgs.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                langchain_msgs.append(AIMessage(content=msg.content))
            elif msg.role == "system":
                langchain_msgs.append(SystemMessage(content=msg.content))

        # 4. Invoke LLM (rollback on error to maintain consistent DB state without orphan messages)
        try:
            llm_result = self._llm.generate_chat_response(langchain_msgs)
        except Exception:
            self._db.rollback()
            raise

        # 5. Persist assistant message
        assistant_msg = self._repo.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=llm_result.content,
            model=llm_result.model,
            prompt_tokens=llm_result.prompt_tokens,
            completion_tokens=llm_result.completion_tokens,
            total_tokens=llm_result.total_tokens,
        )

        self._repo.update_conversation_timestamp(conversation)
        self._db.commit()
        self._db.refresh(user_msg)
        self._db.refresh(assistant_msg)

        return user_msg, assistant_msg
