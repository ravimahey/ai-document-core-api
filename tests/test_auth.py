from fastapi.testclient import TestClient


def test_login_and_access_protected_routes(client: TestClient) -> None:
    # 1. Register a user
    register_payload = {
        "username": "authuser",
        "email": "auth@example.com",
        "password": "Password123!",
        "full_name": "Auth User",
        "is_superuser": False,
        "role": "user",
    }
    reg_response = client.post("/api/v1/register", json=register_payload)
    assert reg_response.status_code == 200

    # 2. Login with email
    login_data = {
        "username": "auth@example.com",
        "password": "Password123!",
    }
    login_response = client.post("/api/v1/token", data=login_data)
    assert login_response.status_code == 200
    token_info = login_response.json()
    assert "access_token" in token_info
    assert token_info["token_type"] == "bearer"
    access_token = token_info["access_token"]

    # 3. Access /api/v1/me with token
    headers = {"Authorization": f"Bearer {access_token}"}
    me_response = client.get("/api/v1/me", headers=headers)
    assert me_response.status_code == 200
    user_data = me_response.json()
    assert user_data["username"] == "authuser"
    assert user_data["email"] == "auth@example.com"

    # 4. Access /api/v1/user list with token
    users_response = client.get("/api/v1/user", headers=headers)
    assert users_response.status_code == 200
    users_list = users_response.json()
    assert len(users_list) == 1
    assert users_list[0]["username"] == "authuser"


def test_login_with_username_success(client: TestClient) -> None:
    register_payload = {
        "username": "uname_user",
        "email": "uname@example.com",
        "password": "SecretPassword1",
        "full_name": "Uname User",
        "is_superuser": False,
        "role": "user",
    }
    reg_response = client.post("/api/v1/register", json=register_payload)
    assert reg_response.status_code == 200

    # Login using username instead of email
    login_data = {
        "username": "uname_user",
        "password": "SecretPassword1",
    }
    login_response = client.post("/api/v1/token", data=login_data)
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()


def test_login_wrong_password_fails(client: TestClient) -> None:
    register_payload = {
        "username": "failedlogin",
        "email": "failed@example.com",
        "password": "CorrectPassword",
        "full_name": "Failed Login User",
        "is_superuser": False,
        "role": "user",
    }
    client.post("/api/v1/register", json=register_payload)

    login_data = {
        "username": "failed@example.com",
        "password": "WrongPassword",
    }
    response = client.post("/api/v1/token", data=login_data)
    assert response.status_code == 401
    assert "invalid username or password" in response.json()["detail"].lower()


def test_login_nonexistent_user_fails(client: TestClient) -> None:
    login_data = {
        "username": "nonexistent@example.com",
        "password": "SomePassword",
    }
    response = client.post("/api/v1/token", data=login_data)
    assert response.status_code == 401
