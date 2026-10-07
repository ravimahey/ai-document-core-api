class AppException(Exception):
    status_code: int = 500

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class UserAlreadyExistsError(AppException):
    status_code = 409


class UserNotFoundError(AppException):
    status_code = 404


class InvalidCredentialsError(AppException):
    status_code = 401


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
