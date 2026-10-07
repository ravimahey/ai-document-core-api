from starlette import status
class AppException(Exception):
    status_code: int = 500

    def __init__(self, message: str | None = None):
        self.message = message or self.message
        super().__init__(message)


class UserAlreadyExistsError(AppException):
    status_code = status.HTTP_409_CONFLICT
    message = "User Already Registered"


class UserNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND


class InvalidCredentialsError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED


from fastapi import Request
from fastapi.responses import JSONResponse


async def app_exception_handler(
    request: Request,
    exc: AppException,
):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )
