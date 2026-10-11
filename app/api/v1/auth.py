from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import AuthServiceDep, OTPServiceDep
from app.models.user import User
from app.schemas.auth import Token
from app.schemas.otp import (
    LoginOTPRequest,
    LoginOTPVerify,
    OTPStatusResponse,
    RegistrationOTPRequest,
    RegistrationOTPVerify,
)
from app.schemas.user import UserResponse

auth_router = APIRouter(tags=["Auth APIs"])


@auth_router.post("/token", response_model=Token)
def login(
    auth: AuthServiceDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """Password-based OAuth2 login returning access token."""
    return auth.login(form_data.username, form_data.password)


@auth_router.post(
    "/auth/register/request-otp",
    response_model=OTPStatusResponse,
    status_code=200,
)
@auth_router.post(
    "/register/request-otp",
    response_model=OTPStatusResponse,
    status_code=200,
    include_in_schema=False,
)
def request_registration_otp(
    otp_service: OTPServiceDep,
    request_data: RegistrationOTPRequest,
    request: Request,
) -> OTPStatusResponse:
    """Request a one-time password to verify email for new user registration."""
    client_ip = request.client.host if request.client else None
    return otp_service.request_registration_otp(
        request_data=request_data,
        ip_address=client_ip,
    )


@auth_router.post(
    "/auth/register/verify-otp",
    response_model=UserResponse,
    status_code=201,
)
@auth_router.post(
    "/register/verify-otp",
    response_model=UserResponse,
    status_code=201,
    include_in_schema=False,
)
def verify_registration_otp(
    otp_service: OTPServiceDep,
    verify_data: RegistrationOTPVerify,
) -> User:
    """Verify registration OTP and create an active user account."""
    return otp_service.verify_registration_otp(verify_data=verify_data)


@auth_router.post(
    "/auth/login/request-otp",
    response_model=OTPStatusResponse,
    status_code=200,
)
@auth_router.post(
    "/login/request-otp",
    response_model=OTPStatusResponse,
    status_code=200,
    include_in_schema=False,
)
def request_login_otp(
    otp_service: OTPServiceDep,
    request_data: LoginOTPRequest,
    request: Request,
) -> OTPStatusResponse:
    """Request a passwordless login OTP sent to the user's registered email."""
    client_ip = request.client.host if request.client else None
    return otp_service.request_login_otp(
        request_data=request_data,
        ip_address=client_ip,
    )


@auth_router.post(
    "/auth/login/verify-otp",
    response_model=Token,
    status_code=200,
)
@auth_router.post(
    "/login/verify-otp",
    response_model=Token,
    status_code=200,
    include_in_schema=False,
)
def verify_login_otp(
    otp_service: OTPServiceDep,
    verify_data: LoginOTPVerify,
) -> Token:
    """Verify login OTP and issue an access token."""
    return otp_service.verify_login_otp(verify_data=verify_data)
