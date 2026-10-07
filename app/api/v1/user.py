from fastapi import APIRouter, HTTPException
from app.api.deps import UserServiceDep, CurrentActiveUserDep
from app.schemas.user import CreateUser
from app.schemas.user import UserResponse

user_router = APIRouter(tags=["User APIs"])


@user_router.get("/user", response_model=list[UserResponse])
def get_users(user: UserServiceDep, current_user: CurrentActiveUserDep):
    get_users = user.get_all()


@user_router.post("/register", response_model=UserResponse)
def register_user(current_user: CurrentActiveUserDep, new_user: CreateUser):
    return current_user.register_user(user=new_user)
