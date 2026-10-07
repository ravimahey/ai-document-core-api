from collections.abc import Generator
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from typing import Annotated
from app.services.user import UserService, UserRepository
from app.services.auth import AuthService
from app.db.session import SessionLocal
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.schemas.auth  import User
from starlette import status

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


def get_auth_service(user_service: UserServiceDep) -> AuthService:
    return AuthService(user_service=user_service)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
# oauth2Dep = Annotated[OAuth2PasswordRequestForm, Depends()]

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    user = AuthServiceDep.decode_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


CurrentActiveUserDep = Annotated[User, Depends(get_current_active_user)]