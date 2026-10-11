from sqlalchemy.orm import Session

from app.core.exceptions import UserAlreadyExistsError, UserNotFoundError
from app.core.security import get_password_hash
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import CreateUser


class UserService:
    def __init__(self, db: Session, repository: UserRepository):
        self._db = db
        self._repository = repository

    def register_user(self, user: CreateUser) -> User:
        if self._repository.get_by_email(str(user.email)) is not None:
            raise UserAlreadyExistsError("A user with this email already exists.")

        if self._repository.get_by_username(user.username) is not None:
            raise UserAlreadyExistsError("A user with this username already exists.")

        new_user = User(
            username=user.username,
            email=str(user.email),
            hashed_password=get_password_hash(user.password),
            full_name=user.full_name,
            is_superuser=user.is_superuser,
            role=user.role,
        )

        self._repository.add(new_user)
        self._db.commit()
        self._db.refresh(new_user)

        return new_user

    def get_all(self) -> list[User]:
        return self._repository.get_all()

    def get_user_by_id(self, user_id: int) -> User:
        user = self._repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        return user

    def get_user_by_email(self, email: str) -> User:
        user = self._repository.get_by_email(email=email)
        if user is None:
            raise UserNotFoundError()
        return user

    def get_user_by_username(self, username: str) -> User:
        user = self._repository.get_by_username(username=username)
        if user is None:
            raise UserNotFoundError()
        return user

    def get_user_by_email_or_username(self, identifier: str) -> User:
        user = self._repository.get_by_email_or_username(identifier=identifier)
        if user is None:
            raise UserNotFoundError()
        return user
