from pydantic import BaseModel, EmailStr


class LoginForm(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str


class PayloadForJWT(BaseModel):
    sub: str
    username: str
    email: EmailStr
    role: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class User(BaseModel):
    id: int | None = None
    username: str
    email: EmailStr
    is_active: bool = True
    role: str | None = None
