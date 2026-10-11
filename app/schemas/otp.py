from pydantic import BaseModel, EmailStr


class RegistrationOTPRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str | None = None
    is_superuser: bool = False
    role: str = "user"


class RegistrationOTPVerify(BaseModel):
    email: EmailStr
    otp: str


class LoginOTPRequest(BaseModel):
    email: EmailStr


class LoginOTPVerify(BaseModel):
    email: EmailStr
    otp: str


class OTPStatusResponse(BaseModel):
    message: str
    email: EmailStr | None = None
