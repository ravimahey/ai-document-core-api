from fastapi import APIRouter, HTTPException
from app.api.deps import UserServiceDep
from app.schemas.user import CreateUser
from starlette import status
from app.schemas.user import UserResponse


user_router = APIRouter()


@user_router.get("/user", response_model=list[UserResponse])
def get_users(user: UserServiceDep):
    try:
        get_users = user.get_all()
        return get_users
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Failed to retrieve users",
        ) from exc


@user_router.post("/register", response_model=UserResponse)
def register_user(user: UserServiceDep, new_user: CreateUser):
    return user.register_user(user=new_user)
