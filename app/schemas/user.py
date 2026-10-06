from pydantic import BaseModel, EmailStr


class CreateUser(BaseModel):
    username: str
    email: str
    hashed_password: str
    full_name: str
    is_serperuser: bool


class UserResponse(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    is_active: bool
    is_superuser: bool
