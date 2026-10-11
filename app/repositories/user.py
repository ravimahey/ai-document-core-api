from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self._db = db

    def add(self, user: User) -> None:
        self._db.add(user)

    def get_by_id(self, user_id: int) -> User | None:
        return self._db.get(User, user_id)

    def get_all(self) -> list[User]:
        query = select(User)
        result = self._db.scalars(query)
        return list(result.all())

    def get_by_email(self, email: str) -> User | None:
        query = select(User).where(User.email == email)
        return self._db.scalar(query)

    def get_by_username(self, username: str) -> User | None:
        query = select(User).where(User.username == username)
        return self._db.scalar(query)

    def get_by_email_or_username(self, identifier: str) -> User | None:
        query = select(User).where(
            or_(User.email == identifier, User.username == identifier)
        )
        return self._db.scalar(query)
