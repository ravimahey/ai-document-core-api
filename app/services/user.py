from sqlalchemy.orm import Session
import bcrypt
from app.models import User
from app.repositories.user import UserRepository
from app.schemas.user import CreateUser
from app.core.exceptions import UserAlreadyExistsError, UserNotFoundError


class UserService:
    def __init__(self, db: Session, repository: UserRepository):
        self._db = db
        self._repository = repository

    def _hash_password(self, password: str):
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password, salt)
        return hashed_password

    def _verify_password(self, password: str, hashed_password):
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password=hashed_password)

    def register_user(self, user: CreateUser) -> User:
        existing_user = self._repository.get_by_email(user.email)

        if existing_user is not None:
            raise UserAlreadyExistsError()

        new_user = User(
            username=user.username,
            email=user.email,
            hashed_password=self._hash_password(user.password.encode("utf-8")),
            full_name=user.full_name,
        )

        self._repository.add(new_user)

        self._db.commit()
        self._db.refresh(new_user)

        return new_user

    def get_all(self) -> list[User]:
        return self._repository.get_all()

    def get_user_by_email(self, email: str) -> User:
        user = self._repository.get_by_email(email=email)
        if user is None:
            raise UserNotFoundError()
        return user
