from pydantic import BaseModel, ConfigDict, EmailStr


class CreateUser(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str | None = None
    is_superuser: bool = False
    role: str = "user"


class UserResponse(BaseModel):
    id: int | None = None
    username: str
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    role: str | None = None

    model_config = ConfigDict(from_attributes=True)
