import hashlib
import hmac
import secrets

import bcrypt


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt and return as UTF-8 string."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically secure random numeric OTP string."""
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


def hash_otp(otp: str, secret_key: str) -> str:
    """Compute a secure HMAC-SHA256 digest of the OTP."""
    return hmac.new(
        secret_key.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_otp_hash(otp: str, hashed_otp: str, secret_key: str) -> bool:
    """Verify an OTP against an HMAC-SHA256 digest in constant time."""
    expected = hash_otp(otp, secret_key)
    return hmac.compare_digest(expected, hashed_otp)
