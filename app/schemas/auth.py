from pydantic import BaseModel, EmailStr


class LoginForm(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str


class PayloadForJWT(BaseModel):
    username: str
    email: EmailStr
    role: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class User(BaseModel):
    username: str
    email: EmailStr
    role: str
