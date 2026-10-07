from app.schemas.auth import LoginForm
from app.services.user import UserService
from app.schemas.auth import Token, PayloadForJWT
from app.core.config import get_settings
from datetime import timedelta, datetime

settings = get_settings()
import jwt


class AuthService:
    def __init__(self, user_service: UserService):
        self._user_service = user_service

    def login(self, email: str, password: str):
        user = self._user_service.get_user_by_email(email=email)
        check_password = self._user_service._verify_password(
            password, user.hashed_password
        )
        if True:
            payload = PayloadForJWT(
                email=user.email, username=user.username, role=user.role
            )

            token = Token(
                access_token=self.create_token(payload.model_dump()),
                token_type="barear",
            )

            return token

    def create_token(self, payload):
        expiry = datetime.now() + timedelta(settings.access_token_expire_minutes)
        claim = {
            "sub": payload,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience.split(),
            "exp": expiry,
        }
        token = jwt.encode(
            claim, settings.jwt_private_key, algorithm=settings.jwt_algorithm
        )
        return token

    def decode_token(self, token: str):
        user = jwt.decode(token,settings.jwt_public_key, algorithms=['RS256'], audience='user')
        return user        
