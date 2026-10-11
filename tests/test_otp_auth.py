from datetime import datetime, timedelta, timezone
import re
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.otp import OTPChallenge
from app.models.user import User
from app.services.email import MockEmailService


def extract_otp_from_email(email_body: str) -> str:
    match = re.search(r"\b(\d{6})\b", email_body)
    assert match is not None, f"Could not find 6-digit OTP in body: {email_body}"
    return match.group(1)


def test_registration_otp_success_flow(
    client: TestClient, mock_email: MockEmailService, db_session: Session
) -> None:
    # 1. Request registration OTP
    reg_payload = {
        "username": "otpuser",
        "email": "otpuser@example.com",
        "password": "Password123!",
        "full_name": "OTP User",
        "is_superuser": False,
        "role": "user",
    }
    resp = client.post("/api/v1/auth/register/request-otp", json=reg_payload)
    assert resp.status_code == 200
    assert "sent" in resp.json()["message"].lower()

    # 2. Email was received
    assert len(mock_email.sent_emails) == 1
    sent_msg = mock_email.sent_emails[0]
    assert sent_msg["to_email"] == "otpuser@example.com"
    otp_code = extract_otp_from_email(sent_msg["body"])

    # Account is not yet created before verification
    assert db_session.query(User).filter_by(email="otpuser@example.com").first() is None

    # 3. Verify OTP
    verify_payload = {
        "email": "otpuser@example.com",
        "otp": otp_code,
    }
    verify_resp = client.post("/api/v1/auth/register/verify-otp", json=verify_payload)
    assert verify_resp.status_code == 201
    created_user = verify_resp.json()
    assert created_user["username"] == "otpuser"
    assert created_user["email"] == "otpuser@example.com"
    assert created_user["is_active"] is True

    # Account exists in DB
    user_in_db = db_session.query(User).filter_by(email="otpuser@example.com").first()
    assert user_in_db is not None
    assert user_in_db.is_active is True

    # 4. User can also log in with their password
    login_resp = client.post(
        "/api/v1/token",
        data={"username": "otpuser@example.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


def test_registration_otp_invalid_code(
    client: TestClient, mock_email: MockEmailService
) -> None:
    reg_payload = {
        "username": "invalid_otp_user",
        "email": "invalid_otp@example.com",
        "password": "Password123!",
        "full_name": "Invalid OTP User",
    }
    client.post("/api/v1/auth/register/request-otp", json=reg_payload)
    assert len(mock_email.sent_emails) == 1

    # Verify with incorrect OTP
    verify_resp = client.post(
        "/api/v1/auth/register/verify-otp",
        json={"email": "invalid_otp@example.com", "otp": "000000"},
    )
    assert verify_resp.status_code == 400
    assert "invalid otp" in verify_resp.json()["detail"].lower()


def test_registration_otp_exceeded_attempts(
    client: TestClient, mock_email: MockEmailService
) -> None:
    reg_payload = {
        "username": "max_attempts_user",
        "email": "max_attempts@example.com",
        "password": "Password123!",
    }
    client.post("/api/v1/auth/register/request-otp", json=reg_payload)

    # Fail 5 times (default max attempts)
    for _ in range(5):
        client.post(
            "/api/v1/auth/register/verify-otp",
            json={"email": "max_attempts@example.com", "otp": "111111"},
        )

    # 6th attempt fails with max attempts exceeded
    resp = client.post(
        "/api/v1/auth/register/verify-otp",
        json={"email": "max_attempts@example.com", "otp": "111111"},
    )
    assert resp.status_code == 400
    assert (
        "exceeded" in resp.json()["detail"].lower()
        or "invalid" in resp.json()["detail"].lower()
    )


def test_registration_otp_expired(
    client: TestClient, mock_email: MockEmailService, db_session: Session
) -> None:
    reg_payload = {
        "username": "expired_user",
        "email": "expired@example.com",
        "password": "Password123!",
    }
    client.post("/api/v1/auth/register/request-otp", json=reg_payload)
    otp_code = extract_otp_from_email(mock_email.sent_emails[0]["body"])

    # Force expiration in database
    challenge = (
        db_session.query(OTPChallenge)
        .filter_by(email="expired@example.com", purpose="registration")
        .first()
    )
    assert challenge is not None
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()

    resp = client.post(
        "/api/v1/auth/register/verify-otp",
        json={"email": "expired@example.com", "otp": otp_code},
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


def test_registration_otp_single_use(
    client: TestClient, mock_email: MockEmailService
) -> None:
    reg_payload = {
        "username": "single_use_user",
        "email": "single_use@example.com",
        "password": "Password123!",
    }
    client.post("/api/v1/auth/register/request-otp", json=reg_payload)
    otp_code = extract_otp_from_email(mock_email.sent_emails[0]["body"])

    # First verification succeeds
    first = client.post(
        "/api/v1/auth/register/verify-otp",
        json={"email": "single_use@example.com", "otp": otp_code},
    )
    assert first.status_code == 201

    # Second verification fails (single-use)
    second = client.post(
        "/api/v1/auth/register/verify-otp",
        json={"email": "single_use@example.com", "otp": otp_code},
    )
    assert second.status_code == 400


def test_registration_duplicate_checks(
    client: TestClient, mock_email: MockEmailService
) -> None:
    reg_payload = {
        "username": "dup_user",
        "email": "dup@example.com",
        "password": "Password123!",
    }
    # Direct register
    client.post("/api/v1/register", json=reg_payload)

    # Requesting registration OTP for existing email fails
    resp = client.post(
        "/api/v1/auth/register/request-otp",
        json={
            "username": "different_name",
            "email": "dup@example.com",
            "password": "Password123!",
        },
    )
    assert resp.status_code == 409

    # Requesting registration OTP for existing username fails
    resp2 = client.post(
        "/api/v1/auth/register/request-otp",
        json={
            "username": "dup_user",
            "email": "different@example.com",
            "password": "Password123!",
        },
    )
    assert resp2.status_code == 409


def test_registration_resend_cooldown(
    client: TestClient, mock_email: MockEmailService
) -> None:
    reg_payload = {
        "username": "cooldown_user",
        "email": "cooldown@example.com",
        "password": "Password123!",
    }
    resp1 = client.post("/api/v1/auth/register/request-otp", json=reg_payload)
    assert resp1.status_code == 200

    # Immediate second request fails with 429 Cooldown
    resp2 = client.post("/api/v1/auth/register/request-otp", json=reg_payload)
    assert resp2.status_code == 429
    assert "wait" in resp2.json()["detail"].lower()


def test_email_delivery_failure_rolls_back(
    client: TestClient, mock_email: MockEmailService, db_session: Session
) -> None:
    mock_email.should_fail = True
    reg_payload = {
        "username": "email_fail_user",
        "email": "fail_email@example.com",
        "password": "Password123!",
    }
    resp = client.post("/api/v1/auth/register/request-otp", json=reg_payload)
    assert resp.status_code == 502

    # Verify no challenge was persisted
    assert (
        db_session.query(OTPChallenge).filter_by(email="fail_email@example.com").first()
        is None
    )


def test_login_otp_success_flow(
    client: TestClient, mock_email: MockEmailService
) -> None:
    # 1. Register a user
    client.post(
        "/api/v1/register",
        json={
            "username": "loginotp_user",
            "email": "loginotp@example.com",
            "password": "Password123!",
            "full_name": "Login OTP User",
        },
    )
    mock_email.clear()

    # 2. Request Login OTP
    req_resp = client.post(
        "/api/v1/auth/login/request-otp",
        json={"email": "loginotp@example.com"},
    )
    assert req_resp.status_code == 200
    assert "login code has been sent" in req_resp.json()["message"].lower()

    # 3. Check email
    assert len(mock_email.sent_emails) == 1
    otp_code = extract_otp_from_email(mock_email.sent_emails[0]["body"])

    # 4. Verify Login OTP
    verify_resp = client.post(
        "/api/v1/auth/login/verify-otp",
        json={"email": "loginotp@example.com", "otp": otp_code},
    )
    assert verify_resp.status_code == 200
    token_data = verify_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 5. Access protected endpoint with token
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_resp = client.get("/api/v1/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "loginotp@example.com"


def test_login_otp_nonexistent_user_anti_enumeration(
    client: TestClient, mock_email: MockEmailService
) -> None:
    resp = client.post(
        "/api/v1/auth/login/request-otp",
        json={"email": "ghost@example.com"},
    )
    # Generic success response returned to avoid user enumeration
    assert resp.status_code == 200
    assert "if an account" in resp.json()["message"].lower()
    # BUT no email sent!
    assert len(mock_email.sent_emails) == 0


def test_login_otp_inactive_user(
    client: TestClient, mock_email: MockEmailService, db_session: Session
) -> None:
    client.post(
        "/api/v1/register",
        json={
            "username": "inactive_otp_user",
            "email": "inactive_otp@example.com",
            "password": "Password123!",
        },
    )
    user = db_session.query(User).filter_by(email="inactive_otp@example.com").first()
    assert user is not None
    user.is_active = False
    db_session.commit()
    mock_email.clear()

    # Inactive user requests login OTP -> generic response, no email sent
    resp = client.post(
        "/api/v1/auth/login/request-otp",
        json={"email": "inactive_otp@example.com"},
    )
    assert resp.status_code == 200
    assert len(mock_email.sent_emails) == 0


def test_cross_purpose_otp_rejection(
    client: TestClient, mock_email: MockEmailService
) -> None:
    # 1. Register a user for login testing
    client.post(
        "/api/v1/register",
        json={
            "username": "crosspurpose",
            "email": "cross@example.com",
            "password": "Password123!",
        },
    )

    # 2. Request registration OTP for a new user
    mock_email.clear()
    client.post(
        "/api/v1/auth/register/request-otp",
        json={
            "username": "cross_new",
            "email": "cross_new@example.com",
            "password": "Password123!",
        },
    )
    reg_otp = extract_otp_from_email(mock_email.sent_emails[0]["body"])

    # Attempt to verify registration OTP on login endpoint -> rejected
    login_verify_resp = client.post(
        "/api/v1/auth/login/verify-otp",
        json={"email": "cross_new@example.com", "otp": reg_otp},
    )
    assert login_verify_resp.status_code == 400


def test_login_otp_invalid_code(
    client: TestClient, mock_email: MockEmailService
) -> None:
    client.post(
        "/api/v1/register",
        json={
            "username": "wrongcode_user",
            "email": "wrongcode@example.com",
            "password": "Password123!",
        },
    )
    client.post(
        "/api/v1/auth/login/request-otp",
        json={"email": "wrongcode@example.com"},
    )

    resp = client.post(
        "/api/v1/auth/login/verify-otp",
        json={"email": "wrongcode@example.com", "otp": "999999"},
    )
    assert resp.status_code == 400
    assert "invalid otp" in resp.json()["detail"].lower()


def test_login_otp_single_use(client: TestClient, mock_email: MockEmailService) -> None:
    client.post(
        "/api/v1/register",
        json={
            "username": "reuse_login_user",
            "email": "reuse_login@example.com",
            "password": "Password123!",
        },
    )
    mock_email.clear()
    client.post(
        "/api/v1/auth/login/request-otp",
        json={"email": "reuse_login@example.com"},
    )
    otp_code = extract_otp_from_email(mock_email.sent_emails[0]["body"])

    # First verify succeeds
    resp1 = client.post(
        "/api/v1/auth/login/verify-otp",
        json={"email": "reuse_login@example.com", "otp": otp_code},
    )
    assert resp1.status_code == 200

    # Second verify fails
    resp2 = client.post(
        "/api/v1/auth/login/verify-otp",
        json={"email": "reuse_login@example.com", "otp": otp_code},
    )
    assert resp2.status_code == 400
