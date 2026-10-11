from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.chat import Conversation, Message


class ChatRepository:
    def __init__(self, db: Session):
        self._db = db

    def create_conversation(
        self, user_id: int, title: str = "New conversation"
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            title=title,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._db.add(conversation)
        self._db.flush()
        return conversation

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        query = select(Conversation).where(Conversation.id == conversation_id)
        return self._db.scalar(query)

    def list_conversations(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> tuple[list[Conversation], int]:
        total_query = select(func.count(Conversation.id)).where(
            Conversation.user_id == user_id
        )
        total = int(self._db.scalar(total_query) or 0)

        query = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        conversations = list(self._db.scalars(query).all())
        return conversations, total

    def update_conversation_title(
        self, conversation: Conversation, title: str
    ) -> Conversation:
        conversation.title = title
        conversation.updated_at = datetime.now(timezone.utc)
        self._db.flush()
        return conversation

    def update_conversation_timestamp(self, conversation: Conversation) -> None:
        conversation.updated_at = datetime.now(timezone.utc)
        self._db.flush()

    def delete_conversation(self, conversation: Conversation) -> None:
        self._db.delete(conversation)
        self._db.flush()

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        model: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(message)
        self._db.flush()
        return message

    def get_messages(
        self, conversation_id: int, limit: int | None = None
    ) -> list[Message]:
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        if limit:
            query = query.limit(limit)
        return list(self._db.scalars(query).all())

    def get_recent_messages(self, conversation_id: int, limit: int) -> list[Message]:
        """Fetch the most recent N messages ordered chronologically."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        recent_desc = list(self._db.scalars(query).all())
        # Return in ascending chronological order for context reconstruction
        return list(reversed(recent_desc))

    def get_message_count(self, conversation_id: int) -> int:
        query = select(func.count(Message.id)).where(
            Message.conversation_id == conversation_id
        )
        return int(self._db.scalar(query) or 0)
