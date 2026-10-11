from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.db.session import SessionLocal
from app.models.user import User
from app.repositories.chat import ChatRepository
from app.repositories.document import DocumentRepository
from app.repositories.otp import OTPRepository
from app.repositories.user import UserRepository
from app.services.auth import AuthService
from app.services.chat import ChatService
from app.services.document import DocumentService
from app.services.email import BaseEmailService, get_email_service
from app.services.llm import BaseLLMService, get_llm_service
from app.services.otp import OTPService
from app.services.storage import BaseStorageService, get_storage_service
from app.services.user import UserService
from app.services.vector_store import FAISSService, get_faiss_service

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


def get_email_service_dep() -> BaseEmailService:
    return get_email_service()


EmailServiceDep = Annotated[BaseEmailService, Depends(get_email_service_dep)]


def get_otp_repository(db: DbSession) -> OTPRepository:
    return OTPRepository(db)


OTPRepositoryDep = Annotated[OTPRepository, Depends(get_otp_repository)]


def get_otp_service(
    db: DbSession,
    otp_repository: OTPRepositoryDep,
    user_repository: UserRepositoryDep,
    auth_service: AuthServiceDep,
    email_service: EmailServiceDep,
) -> OTPService:
    return OTPService(
        db=db,
        otp_repository=otp_repository,
        user_repository=user_repository,
        auth_service=auth_service,
        email_service=email_service,
    )


OTPServiceDep = Annotated[OTPService, Depends(get_otp_service)]


def get_llm_service_dep() -> BaseLLMService:
    return get_llm_service()


LLMServiceDep = Annotated[BaseLLMService, Depends(get_llm_service_dep)]


def get_chat_repository(db: DbSession) -> ChatRepository:
    return ChatRepository(db)


ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]


def get_chat_service(
    db: DbSession,
    chat_repository: ChatRepositoryDep,
    llm_service: LLMServiceDep,
) -> ChatService:
    return ChatService(
        db=db,
        chat_repository=chat_repository,
        llm_service=llm_service,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


def get_storage_service_dep() -> BaseStorageService:
    return get_storage_service()


StorageServiceDep = Annotated[BaseStorageService, Depends(get_storage_service_dep)]


def get_faiss_service_dep() -> FAISSService:
    return get_faiss_service()


FAISSServiceDep = Annotated[FAISSService, Depends(get_faiss_service_dep)]


def get_document_repository(db: DbSession) -> DocumentRepository:
    return DocumentRepository(db)


DocumentRepositoryDep = Annotated[DocumentRepository, Depends(get_document_repository)]


def get_document_service(
    db: DbSession,
    document_repository: DocumentRepositoryDep,
    storage_service: StorageServiceDep,
    faiss_service: FAISSServiceDep,
) -> DocumentService:
    return DocumentService(
        db=db,
        document_repository=document_repository,
        storage_service=storage_service,
        faiss_service=faiss_service,
    )


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]

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
