from fastapi import Request
from fastapi.responses import JSONResponse
from starlette import status


class AppException(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    message: str = "An internal error occurred."

    def __init__(self, message: str | None = None):
        self.message = message if message is not None else self.message
        super().__init__(self.message)


class UserAlreadyExistsError(AppException):
    status_code: int = status.HTTP_409_CONFLICT
    message: str = "User Already Registered"


class UserNotFoundError(AppException):
    status_code: int = status.HTTP_404_NOT_FOUND
    message: str = "User Not Found"


class InvalidCredentialsError(AppException):
    status_code: int = status.HTTP_401_UNAUTHORIZED
    message: str = "Invalid username or password"


async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )
