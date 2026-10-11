from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidCredentialsError, UserNotFoundError
from app.core.security import verify_password
from app.schemas.auth import Token
from app.services.user import UserService   


class AuthService:
    def __init__(self, user_service: UserService, settings: Settings | None = None):
        self._user_service = user_service
        self._settings = settings or get_settings()

    def _get_audiences(self) -> list[str]:
        return [
            a.strip()
            for a in self._settings.jwt_audience.replace(",", " ").split()
            if a.strip()
        ]

    def login(self, email_or_username: str, password: str) -> Token:
        try:
            user = self._user_service.get_user_by_email_or_username(email_or_username)
        except UserNotFoundError:
            raise InvalidCredentialsError()

        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()

        payload = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
        }

        access_token = self.create_token(payload)
        return Token(access_token=access_token, token_type="bearer")

    def create_token(self, payload: dict[str, Any]) -> str:
        expiry = datetime.now(UTC) + timedelta(
            minutes=self._settings.access_token_expire_minutes
        )
        audiences = self._get_audiences()

        claim = {
            **payload,
            "iss": self._settings.jwt_issuer,
            "aud": audiences,
            "exp": expiry,
        }
        return jwt.encode(
            claim,
            self._settings.jwt_private_key,
            algorithm=self._settings.jwt_algorithm,
        )

    def decode_token(self, token: str) -> dict[str, Any]:
        audiences = self._get_audiences()
        try:
            decoded = jwt.decode(
                token,
                self._settings.jwt_public_key,
                algorithms=[self._settings.jwt_algorithm],
                audience=audiences if audiences else None,
                issuer=self._settings.jwt_issuer,
            )
            return decoded
        except jwt.PyJWTError as exc:
            raise InvalidCredentialsError("Could not validate credentials") from exc
