from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.db.session import SessionLocal
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.auth import AuthService
from app.services.user import UserService

settings = get_settings()


def get_db() -> Generator[Session]:
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


def get_auth_service(user_service: UserServiceDep) -> AuthService:
    return AuthService(user_service=user_service)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/token")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    auth_service: AuthServiceDep,
    user_service: UserServiceDep,
) -> User:
    try:
        payload = auth_service.decode_token(token)
        email = payload.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = user_service.get_user_by_email(email)
        return user
    except AppException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return current_user


CurrentActiveUserDep = Annotated[User, Depends(get_current_active_user)]