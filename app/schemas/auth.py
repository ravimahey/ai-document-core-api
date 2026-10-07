from pydantic import BaseModel, EmailStr


class LoginForm(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
