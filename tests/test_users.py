from fastapi.testclient import TestClient


def test_register_user_success(client: TestClient) -> None:
    payload = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "securepassword123",
        "full_name": "Test User",
        "is_superuser": False,
        "role": "user",
    }
    response = client.post("/api/v1/register", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"
    assert data["is_active"] is True
    assert "password" not in data


def test_register_duplicate_user_conflict(client: TestClient) -> None:
    payload = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "securepassword123",
        "full_name": "Test User",
        "is_superuser": False,
        "role": "user",
    }
    first = client.post("/api/v1/register", json=payload)
    assert first.status_code == 200

    second = client.post("/api/v1/register", json=payload)
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"].lower()


def test_get_users_unauthorized(client: TestClient) -> None:
    response = client.get("/api/v1/user")
    assert response.status_code == 401
