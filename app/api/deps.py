from collections.abc import Generator
from sqlalchemy.orm import Session
from fastapi import Depends
from typing import Annotated
from app.services.user import UserService, UserRepository
from app.services.auth import AuthService
from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """One session per request; always closed, rolled back on error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_user_service(db: DbSession, repository: UserRepositoryDep) -> UserService:
    return UserService(db=db, repository=repository)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_auth_service(db: DbSession, user_service: UserServiceDep) -> AuthService:
    return AuthService(db=db, user_service=user_service)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
