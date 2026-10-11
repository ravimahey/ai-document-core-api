from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.otp import OTPChallenge


class OTPRepository:
    def __init__(self, db: Session):
        self._db = db

    def add(self, challenge: OTPChallenge) -> None:
        self._db.add(challenge)
        self._db.flush()

    def get_active_challenge(self, email: str, purpose: str) -> OTPChallenge | None:
        """Fetch the most recent unused OTP challenge for an email and purpose."""
        query = (
            select(OTPChallenge)
            .where(
                OTPChallenge.email == email,
                OTPChallenge.purpose == purpose,
                OTPChallenge.is_used.is_(False),
            )
            .order_by(OTPChallenge.id.desc())
            .limit(1)
        )
        return self._db.scalar(query)

    def get_latest_challenge(self, email: str, purpose: str) -> OTPChallenge | None:
        """Fetch the latest challenge regardless of is_used status."""
        query = (
            select(OTPChallenge)
            .where(
                OTPChallenge.email == email,
                OTPChallenge.purpose == purpose,
            )
            .order_by(OTPChallenge.id.desc())
            .limit(1)
        )
        return self._db.scalar(query)

    def count_recent_requests(self, email: str, since: datetime) -> int:
        """Count challenges created for this email since a given datetime."""
        query = select(func.count(OTPChallenge.id)).where(
            OTPChallenge.email == email,
            OTPChallenge.created_at >= since,
        )
        result = self._db.scalar(query)
        return int(result or 0)

    def invalidate_existing_challenges(self, email: str, purpose: str) -> int:
        """Mark all active challenges for an email and purpose as used."""
        stmt = (
            update(OTPChallenge)
            .where(
                OTPChallenge.email == email,
                OTPChallenge.purpose == purpose,
                OTPChallenge.is_used.is_(False),
            )
            .values(is_used=True)
        )
        result = self._db.execute(stmt)
        self._db.flush()
        return int(result.rowcount or 0)

    def get_all_by_email(self, email: str) -> Sequence[OTPChallenge]:
        query = (
            select(OTPChallenge)
            .where(OTPChallenge.email == email)
            .order_by(OTPChallenge.id.desc())
        )
        return self._db.scalars(query).all()
