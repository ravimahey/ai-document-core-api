import logging
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Any

from app.core.config import Settings, get_settings
from app.core.exceptions import EmailDeliveryError

logger = logging.getLogger(__name__)


class BaseEmailService(ABC):
    @abstractmethod
    def send_email(self, to_email: str, subject: str, body: str) -> None:
        """Send an email to a recipient."""

    def send_otp_email(self, to_email: str, otp: str, purpose: str) -> None:
        """Format and send an OTP verification email."""
        purpose_display = (
            "Registration Verification"
            if purpose == "registration"
            else "Login Verification"
        )
        subject = f"Your {purpose_display} Code"
        body = (
            f"Hello,\n\n"
            f"Your verification code for {purpose_display.lower()} is: {otp}\n\n"
            f"This code will expire in a few minutes. If you did not request this code, please ignore this email.\n\n"
            f"Thank you,\nAI Document SaaS Team"
        )
        self.send_email(to_email=to_email, subject=subject, body=body)


class ConsoleEmailService(BaseEmailService):
    def __init__(self, settings: Settings):
        self._settings = settings

    def send_email(self, to_email: str, subject: str, body: str) -> None:
        logger.info(
            "Delivering email via ConsoleEmailService to %s (Subject: %s)",
            to_email,
            subject,
        )


class SMTPEmailService(BaseEmailService):
    def __init__(self, settings: Settings):
        self._settings = settings

    def send_email(self, to_email: str, subject: str, body: str) -> None:
        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = subject
            msg["From"] = self._settings.smtp_from_email
            msg["To"] = to_email

            with smtplib.SMTP(
                self._settings.smtp_host, self._settings.smtp_port, timeout=10
            ) as server:
                if self._settings.smtp_use_tls:
                    server.starttls()
                if self._settings.smtp_username and self._settings.smtp_password:
                    server.login(
                        self._settings.smtp_username,
                        self._settings.smtp_password,
                    )
                server.send_message(msg)
        except Exception as exc:
            logger.error("Failed to send email to %s via SMTP: %s", to_email, exc)
            raise EmailDeliveryError("Failed to deliver email.") from exc


class MockEmailService(BaseEmailService):
    """In-memory mock email service for automated testing."""

    def __init__(self, should_fail: bool = False):
        self.sent_emails: list[dict[str, Any]] = []
        self.should_fail = should_fail

    def send_email(self, to_email: str, subject: str, body: str) -> None:
        if self.should_fail:
            raise EmailDeliveryError("Simulated email delivery failure.")
        self.sent_emails.append(
            {
                "to_email": to_email,
                "subject": subject,
                "body": body,
            }
        )

    def clear(self) -> None:
        self.sent_emails.clear()


def get_email_service(
    settings: Settings | None = None,
) -> BaseEmailService:
    settings = settings or get_settings()
    if settings.email_provider == "mock":
        return MockEmailService()
    if settings.email_provider == "smtp":
        return SMTPEmailService(settings)
    return ConsoleEmailService(settings)
