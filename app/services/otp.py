import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    EmailDeliveryError,
    OTPCooldownError,
    OTPExpiredError,
    OTPInvalidError,
    OTPMaxAttemptsExceededError,
    OTPRateLimitExceededError,
    UserAlreadyExistsError,
    UserInactiveError,
    UserNotFoundError,
)
from app.core.security import generate_otp, get_password_hash, hash_otp, verify_otp_hash
from app.models.otp import OTPChallenge
from app.models.user import User
from app.repositories.otp import OTPRepository
from app.repositories.user import UserRepository
from app.schemas.auth import Token
from app.schemas.otp import (
    LoginOTPRequest,
    LoginOTPVerify,
    OTPStatusResponse,
    RegistrationOTPRequest,
    RegistrationOTPVerify,
)
from app.services.auth import AuthService
from app.services.email import BaseEmailService

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class OTPService:
    def __init__(
        self,
        db: Session,
        otp_repository: OTPRepository,
        user_repository: UserRepository,
        auth_service: AuthService,
        email_service: BaseEmailService,
        settings: Settings | None = None,
    ):
        self._db = db
        self._otp_repo = otp_repository
        self._user_repo = user_repository
        self._auth_service = auth_service
        self._email_service = email_service
        self._settings = settings or get_settings()

    def request_registration_otp(
        self,
        request_data: RegistrationOTPRequest,
        ip_address: str | None = None,
    ) -> OTPStatusResponse:
        """Validate registration input and issue a registration OTP."""
        email_str = str(request_data.email).lower()

        # 1. Validate uniqueness
        if self._user_repo.get_by_email(email_str) is not None:
            raise UserAlreadyExistsError(
                "A user with this email is already registered."
            )
        if self._user_repo.get_by_username(request_data.username) is not None:
            raise UserAlreadyExistsError(
                "A user with this username is already registered."
            )

        now = datetime.now(UTC)

        # 2. Rate limiting check (requests per hour)
        recent_count = self._otp_repo.count_recent_requests(
            email=email_str,
            since=now - timedelta(hours=1),
        )
        if recent_count >= self._settings.otp_max_requests_per_hour:
            raise OTPRateLimitExceededError()

        # 3. Resend cooldown check
        latest_challenge = self._otp_repo.get_latest_challenge(
            email=email_str,
            purpose="registration",
        )
        if latest_challenge is not None:
            elapsed = (now - _ensure_utc(latest_challenge.last_sent_at)).total_seconds()
            if elapsed < self._settings.otp_resend_cooldown_seconds:
                remaining = int(self._settings.otp_resend_cooldown_seconds - elapsed)
                raise OTPCooldownError(
                    f"Please wait {remaining} seconds before requesting a new OTP."
                )

        # 4. Invalidate previous registration challenges for this email
        self._otp_repo.invalidate_existing_challenges(
            email=email_str,
            purpose="registration",
        )

        # 5. Generate secure OTP and hash it
        otp_plain = generate_otp(length=self._settings.otp_length)
        hashed_otp = hash_otp(
            otp=otp_plain,
            secret_key=self._settings.otp_secret_key,
        )

        # 6. Securely prepare pending registration payload (hash password immediately)
        payload = {
            "username": request_data.username,
            "email": email_str,
            "hashed_password": get_password_hash(request_data.password),
            "full_name": request_data.full_name,
            "is_superuser": request_data.is_superuser,
            "role": request_data.role,
        }

        challenge = OTPChallenge(
            email=email_str,
            purpose="registration",
            hashed_otp=hashed_otp,
            payload=json.dumps(payload),
            user_id=None,
            attempts=0,
            max_attempts=self._settings.otp_max_attempts,
            is_used=False,
            expires_at=now + timedelta(minutes=self._settings.otp_expire_minutes),
            created_at=now,
            last_sent_at=now,
            ip_address=ip_address,
        )

        # 7. Deliver OTP email BEFORE committing
        try:
            self._email_service.send_otp_email(
                to_email=email_str,
                otp=otp_plain,
                purpose="registration",
            )
        except EmailDeliveryError:
            self._db.rollback()
            raise

        self._otp_repo.add(challenge)
        self._db.commit()

        return OTPStatusResponse(
            message="Verification code sent to your email.",
            email=email_str,
        )

    def verify_registration_otp(
        self,
        verify_data: RegistrationOTPVerify,
    ) -> User:
        """Verify registration OTP and activate user account."""
        email_str = str(verify_data.email).lower()
        now = datetime.now(UTC)

        challenge = self._otp_repo.get_active_challenge(
            email=email_str,
            purpose="registration",
        )
        if challenge is None:
            raise OTPInvalidError(
                "No active registration challenge found for this email."
            )

        # Check expiration
        if _ensure_utc(challenge.expires_at) < now:
            challenge.is_used = True
            self._db.commit()
            raise OTPExpiredError()

        # Check attempt limits
        if challenge.attempts >= challenge.max_attempts:
            challenge.is_used = True
            self._db.commit()
            raise OTPMaxAttemptsExceededError()

        # Verify OTP code
        if not verify_otp_hash(
            otp=verify_data.otp,
            hashed_otp=challenge.hashed_otp,
            secret_key=self._settings.otp_secret_key,
        ):
            challenge.attempts += 1
            if challenge.attempts >= challenge.max_attempts:
                challenge.is_used = True
            self._db.commit()
            raise OTPInvalidError(
                f"Invalid OTP. {challenge.max_attempts - challenge.attempts} attempt(s) remaining."
            )

        # Invalidate OTP immediately to prevent reuse / race conditions
        challenge.is_used = True

        if not challenge.payload:
            self._db.commit()
            raise OTPInvalidError("Registration details missing from challenge.")

        user_info = json.loads(challenge.payload)

        # Final concurrency safeguard: re-check uniqueness before inserting
        if self._user_repo.get_by_email(user_info["email"]) is not None:
            self._db.commit()
            raise UserAlreadyExistsError(
                "A user with this email is already registered."
            )
        if self._user_repo.get_by_username(user_info["username"]) is not None:
            self._db.commit()
            raise UserAlreadyExistsError(
                "A user with this username is already registered."
            )

        new_user = User(
            username=user_info["username"],
            email=user_info["email"],
            hashed_password=user_info["hashed_password"],
            full_name=user_info.get("full_name"),
            is_active=True,
            is_superuser=user_info.get("is_superuser", False),
            role=user_info.get("role", "user"),
        )

        self._user_repo.add(new_user)
        self._db.commit()
        self._db.refresh(new_user)
        return new_user

    def request_login_otp(
        self,
        request_data: LoginOTPRequest,
        ip_address: str | None = None,
    ) -> OTPStatusResponse:
        """Request a passwordless login OTP with anti-enumeration protection."""
        email_str = str(request_data.email).lower()
        now = datetime.now(UTC)

        # Anti-enumeration response
        generic_message = "If an account with that email exists and is active, a login code has been sent."

        # 1. Rate limiting check
        recent_count = self._otp_repo.count_recent_requests(
            email=email_str,
            since=now - timedelta(hours=1),
        )
        if recent_count >= self._settings.otp_max_requests_per_hour:
            raise OTPRateLimitExceededError()

        # 2. Resend cooldown check
        latest_challenge = self._otp_repo.get_latest_challenge(
            email=email_str,
            purpose="login",
        )
        if latest_challenge is not None:
            elapsed = (now - _ensure_utc(latest_challenge.last_sent_at)).total_seconds()
            if elapsed < self._settings.otp_resend_cooldown_seconds:
                remaining = int(self._settings.otp_resend_cooldown_seconds - elapsed)
                raise OTPCooldownError(
                    f"Please wait {remaining} seconds before requesting a new OTP."
                )

        # 3. Lookup user
        user = self._user_repo.get_by_email(email_str)
        if user is None or not user.is_active:
            # Return generic success without sending email to prevent user enumeration
            return OTPStatusResponse(
                message=generic_message,
                email=email_str,
            )

        # 4. Invalidate prior active login challenges
        self._otp_repo.invalidate_existing_challenges(
            email=email_str,
            purpose="login",
        )

        # 5. Generate and hash OTP
        otp_plain = generate_otp(length=self._settings.otp_length)
        hashed_otp = hash_otp(
            otp=otp_plain,
            secret_key=self._settings.otp_secret_key,
        )

        challenge = OTPChallenge(
            email=email_str,
            purpose="login",
            hashed_otp=hashed_otp,
            payload=None,
            user_id=user.id,
            attempts=0,
            max_attempts=self._settings.otp_max_attempts,
            is_used=False,
            expires_at=now + timedelta(minutes=self._settings.otp_expire_minutes),
            created_at=now,
            last_sent_at=now,
            ip_address=ip_address,
        )

        # 6. Deliver email before committing
        try:
            self._email_service.send_otp_email(
                to_email=email_str,
                otp=otp_plain,
                purpose="login",
            )
        except EmailDeliveryError:
            self._db.rollback()
            raise

        self._otp_repo.add(challenge)
        self._db.commit()

        return OTPStatusResponse(
            message=generic_message,
            email=email_str,
        )

    def verify_login_otp(
        self,
        verify_data: LoginOTPVerify,
    ) -> Token:
        """Verify login OTP and issue JWT access token."""
        email_str = str(verify_data.email).lower()
        now = datetime.now(UTC)

        challenge = self._otp_repo.get_active_challenge(
            email=email_str,
            purpose="login",
        )
        if challenge is None:
            raise OTPInvalidError("No active login challenge found for this email.")

        # Check expiration
        if _ensure_utc(challenge.expires_at) < now:
            challenge.is_used = True
            self._db.commit()
            raise OTPExpiredError()

        # Check attempt limits
        if challenge.attempts >= challenge.max_attempts:
            challenge.is_used = True
            self._db.commit()
            raise OTPMaxAttemptsExceededError()

        # Verify OTP code
        if not verify_otp_hash(
            otp=verify_data.otp,
            hashed_otp=challenge.hashed_otp,
            secret_key=self._settings.otp_secret_key,
        ):
            challenge.attempts += 1
            if challenge.attempts >= challenge.max_attempts:
                challenge.is_used = True
            self._db.commit()
            raise OTPInvalidError(
                f"Invalid OTP. {challenge.max_attempts - challenge.attempts} attempt(s) remaining."
            )

        # Invalidate OTP immediately to prevent reuse
        challenge.is_used = True
        self._db.commit()

        # Fetch and validate user
        user = self._user_repo.get_by_email(email_str)
        if user is None:
            raise UserNotFoundError()
        if not user.is_active:
            raise UserInactiveError()

        payload = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
        }
        access_token = self._auth_service.create_token(payload)
        return Token(access_token=access_token, token_type="bearer")
