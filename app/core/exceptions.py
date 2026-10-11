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
    status_code = status.HTTP_409_CONFLICT
    message = "User Already Registered"


class UserNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    message = "User Not Found"


class InvalidCredentialsError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "Invalid username or password"


class UserInactiveError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    message = "Account is inactive."


class OTPExpiredError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "OTP has expired. Please request a new one."


class OTPInvalidError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Invalid OTP code."


class OTPMaxAttemptsExceededError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Maximum verification attempts exceeded. Challenge invalidated."


class OTPCooldownError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    message = "Please wait before requesting another OTP."


class OTPRateLimitExceededError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    message = "Too many OTP requests. Please try again later."


class EmailDeliveryError(AppException):
    status_code = status.HTTP_502_BAD_GATEWAY
    message = "Failed to deliver verification email. Please try again."


# Chat & Conversation Exceptions
class ConversationNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    message = "Conversation not found."


class ConversationAccessDeniedError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    message = "You do not have permission to access this conversation."


class MessageLengthExceededError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Message exceeds maximum allowed character limit."


class EmptyMessageError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Message content cannot be empty."


class LLMProviderError(AppException):
    status_code = status.HTTP_502_BAD_GATEWAY
    message = "AI service temporarily unavailable. Please try again."


class LLMTimeoutError(AppException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    message = "AI service request timed out. Please try again."


class LLMAuthenticationError(AppException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    message = "AI service authentication failed. Check server configuration."


# Document & Storage Exceptions
class DocumentNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    message = "Document not found."


class DocumentAccessDeniedError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    message = "You do not have permission to access this document."


class InvalidFileTypeError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Unsupported file type. Supported formats: .pdf, .docx, .txt, .md."


class FileTooLargeError(AppException):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    message = "Uploaded file exceeds maximum allowed size."


class EmptyDocumentError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "The document contains no readable text."


class StorageError(AppException):
    status_code = status.HTTP_502_BAD_GATEWAY
    message = "Object storage operation failed."


class StorageNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    message = "Object not found in storage."


class DocumentProcessingBusyError(AppException):
    status_code = status.HTTP_409_CONFLICT
    message = "Document is currently being processed."


class DocumentNotEligibleForRetryError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Only documents in 'failed' status can be retried."


class EmbeddingModelMismatchError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Embedding model mismatch between configured model and document vector index."


async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )
