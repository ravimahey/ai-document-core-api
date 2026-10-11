from fastapi import APIRouter

from app.api.deps import CurrentActiveUserDep, UserServiceDep
from app.models.user import User
from app.schemas.user import CreateUser, UserResponse

user_router = APIRouter(tags=["User APIs"])


@user_router.get("/user", response_model=list[UserResponse])
def get_users(
    user_service: UserServiceDep,
    current_user: CurrentActiveUserDep,
) -> list[User]:
    return user_service.get_all()


@user_router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: CurrentActiveUserDep,
) -> User:
    return current_user
