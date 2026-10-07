from pydantic import BaseModel, EmailStr, ConfigDict


class CreateUser(BaseModel):
    username: str
    email: str
    password: str
    full_name: str
    is_serperuser: bool


class UserResponse(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    is_active: bool
    is_superuser: bool
    model_config = ConfigDict(from_attributes=True)
