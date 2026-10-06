from sqlalchemy.orm import Session

from app.models import User
from app.repositories.user import UserRepository
from app.schemas.user import CreateUser

class UserAlreadyExistsError(Exception):
    pass

class UserService:
    def __init__(self, db: Session, repository: UserRepository):
        self._db = db
        self._repository = repository

    def register_user(self, user: CreateUser) -> User:
        existing_user = self._repository.get_by_email(user.email)

        if existing_user is not None:
            raise UserAlreadyExistsError("User already registered")
        new_user = User(
            username=user.username,
            email=user.email,
            hashed_password=user.hashed_password,
            full_name=user.full_name,
        )

        self._repository.add(new_user)

        self._db.commit()
        self._db.refresh(new_user)

        return new_user

    def get_all(self) -> list[User]:
        return self._repository.get_all()
