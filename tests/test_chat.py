from fastapi.testclient import TestClient

from app.services.llm import MockLLMService


def create_authenticated_user(
    client: TestClient, username: str, email: str, password: str = "Secret123!"
) -> dict[str, str]:
    """Helper to register and authenticate a user, returning auth headers."""
    client.post(
        "/api/v1/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "full_name": f"User {username}",
            "is_superuser": False,
            "role": "user",
        },
    )
    login_resp = client.post(
        "/api/v1/token",
        data={"username": email, "password": password},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_and_list_conversations(
    client: TestClient, mock_llm: MockLLMService
) -> None:
    headers = create_authenticated_user(client, "chatuser1", "chatuser1@example.com")

    # 1. Create empty conversation
    resp = client.post(
        "/api/v1/chat/conversations",
        json={"title": "My Research Chat"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "My Research Chat"
    assert len(data["messages"]) == 0
    conv_id = data["id"]

    # 2. List conversations
    list_resp = client.get("/api/v1/chat/conversations", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] == 1
    assert list_data["conversations"][0]["id"] == conv_id
    assert list_data["conversations"][0]["title"] == "My Research Chat"


def test_create_conversation_with_initial_message(
    client: TestClient, mock_llm: MockLLMService
) -> None:
    headers = create_authenticated_user(client, "chatuser2", "chatuser2@example.com")
    mock_llm.preset_response = "Hello! I can help you with that."

    resp = client.post(
        "/api/v1/chat/conversations",
        json={"initial_message": "Tell me a joke about programming"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["messages"]) == 2
    user_msg = data["messages"][0]
    ai_msg = data["messages"][1]

    assert user_msg["role"] == "user"
    assert user_msg["content"] == "Tell me a joke about programming"
    assert ai_msg["role"] == "assistant"
    assert ai_msg["content"] == "Hello! I can help you with that."


def test_send_message_and_continue_conversation(
    client: TestClient, mock_llm: MockLLMService
) -> None:
    headers = create_authenticated_user(client, "chatuser3", "chatuser3@example.com")
    mock_llm.preset_response = "AI response 1"

    # Start conversation
    create_resp = client.post(
        "/api/v1/chat/conversations",
        json={"initial_message": "Question 1"},
        headers=headers,
    )
    conv_id = create_resp.json()["id"]

    # Continue conversation
    mock_llm.preset_response = "AI response 2"
    send_resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "Question 2 with context"},
        headers=headers,
    )
    assert send_resp.status_code == 201
    exchange = send_resp.json()
    assert exchange["user_message"]["content"] == "Question 2 with context"
    assert exchange["assistant_message"]["content"] == "AI response 2"

    # Retrieve full conversation history
    get_resp = client.get(f"/api/v1/chat/conversations/{conv_id}", headers=headers)
    assert get_resp.status_code == 200
    messages = get_resp.json()["messages"]
    assert len(messages) == 4
    assert messages[0]["content"] == "Question 1"
    assert messages[1]["content"] == "AI response 1"
    assert messages[2]["content"] == "Question 2 with context"
    assert messages[3]["content"] == "AI response 2"

    # Verify LangChain mock received context
    last_call = mock_llm.invoked_messages[-1]
    # Should include previous user msg, previous AI msg, and current user msg
    msg_contents = [m.content for m in last_call]
    assert "Question 1" in msg_contents
    assert "AI response 1" in msg_contents
    assert "Question 2 with context" in msg_contents


def test_context_isolation_between_conversations(
    client: TestClient, mock_llm: MockLLMService
) -> None:
    headers = create_authenticated_user(client, "iso_user", "iso_user@example.com")

    # Thread A
    resp_a = client.post(
        "/api/v1/chat/conversations",
        json={"initial_message": "Topic A secret"},
        headers=headers,
    )
    conv_a = resp_a.json()["id"]

    # Thread B
    resp_b = client.post(
        "/api/v1/chat/conversations",
        json={"initial_message": "Topic B question"},
        headers=headers,
    )
    conv_b = resp_b.json()["id"]

    # Check Thread B LLM invocation
    call_for_b = mock_llm.invoked_messages[-1]
    b_contents = [m.content for m in call_for_b]
    assert "Topic B question" in b_contents
    assert "Topic A secret" not in b_contents


def test_rename_and_delete_conversation(
    client: TestClient, mock_llm: MockLLMService
) -> None:
    headers = create_authenticated_user(client, "rename_user", "rename@example.com")
    resp = client.post(
        "/api/v1/chat/conversations",
        json={"title": "Original Title"},
        headers=headers,
    )
    conv_id = resp.json()["id"]

    # Rename
    patch_resp = client.patch(
        f"/api/v1/chat/conversations/{conv_id}",
        json={"title": "Updated Title"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "Updated Title"

    # Delete
    del_resp = client.delete(f"/api/v1/chat/conversations/{conv_id}", headers=headers)
    assert del_resp.status_code == 204

    # Confirm deletion
    get_resp = client.get(f"/api/v1/chat/conversations/{conv_id}", headers=headers)
    assert get_resp.status_code == 404


def test_cross_user_isolation(client: TestClient, mock_llm: MockLLMService) -> None:
    user1_headers = create_authenticated_user(client, "user_alpha", "alpha@example.com")
    user2_headers = create_authenticated_user(client, "user_beta", "beta@example.com")

    # User 1 creates a conversation
    resp = client.post(
        "/api/v1/chat/conversations",
        json={"title": "Alpha Private Chat"},
        headers=user1_headers,
    )
    conv_id = resp.json()["id"]

    # User 2 tries to read it -> 403 Forbidden
    read_resp = client.get(
        f"/api/v1/chat/conversations/{conv_id}", headers=user2_headers
    )
    assert read_resp.status_code == 403

    # User 2 tries to send message -> 403 Forbidden
    msg_resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "Hacker msg"},
        headers=user2_headers,
    )
    assert msg_resp.status_code == 403

    # User 2 tries to rename -> 403 Forbidden
    rename_resp = client.patch(
        f"/api/v1/chat/conversations/{conv_id}",
        json={"title": "Hacked"},
        headers=user2_headers,
    )
    assert rename_resp.status_code == 403

    # User 2 tries to delete -> 403 Forbidden
    del_resp = client.delete(
        f"/api/v1/chat/conversations/{conv_id}", headers=user2_headers
    )
    assert del_resp.status_code == 403

    # User 2 listing conversations -> never sees Alpha's chat
    list_resp = client.get("/api/v1/chat/conversations", headers=user2_headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 0


def test_unauthenticated_requests_rejected(client: TestClient) -> None:
    assert client.post("/api/v1/chat/conversations", json={}).status_code == 401
    assert client.get("/api/v1/chat/conversations").status_code == 401
    assert client.get("/api/v1/chat/conversations/1").status_code == 401
    assert (
        client.post(
            "/api/v1/chat/conversations/1/messages", json={"content": "hi"}
        ).status_code
        == 401
    )


def test_validation_empty_or_too_long_message(
    client: TestClient, mock_llm: MockLLMService
) -> None:
    headers = create_authenticated_user(client, "val_user", "val_user@example.com")
    resp = client.post(
        "/api/v1/chat/conversations",
        json={"title": "Validation Chat"},
        headers=headers,
    )
    conv_id = resp.json()["id"]

    # Empty message
    empty_resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "   "},
        headers=headers,
    )
    assert empty_resp.status_code == 400
    assert "empty" in empty_resp.json()["detail"].lower()

    # Exceedingly long message (> 4000 characters)
    huge_text = "a" * 4500
    long_resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": huge_text},
        headers=headers,
    )
    assert long_resp.status_code == 400
    assert "maximum length" in long_resp.json()["detail"].lower()


def test_llm_failure_handling_and_no_orphans(
    client: TestClient, mock_llm: MockLLMService
) -> None:
    headers = create_authenticated_user(client, "fail_user", "fail_user@example.com")
    resp = client.post(
        "/api/v1/chat/conversations",
        json={"title": "Fail Test"},
        headers=headers,
    )
    conv_id = resp.json()["id"]

    # Simulate provider failure
    mock_llm.should_fail = True
    mock_llm.failure_type = "provider"

    send_resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "Will fail"},
        headers=headers,
    )
    assert send_resp.status_code == 502
    assert "ai service" in send_resp.json()["detail"].lower()

    # Verify database state has no orphaned user message
    get_resp = client.get(f"/api/v1/chat/conversations/{conv_id}", headers=headers)
    assert get_resp.status_code == 200
    assert len(get_resp.json()["messages"]) == 0

    # Retry when service recovers
    mock_llm.should_fail = False
    retry_resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "Will fail"},
        headers=headers,
    )
    assert retry_resp.status_code == 201


def test_llm_timeout_handling(client: TestClient, mock_llm: MockLLMService) -> None:
    headers = create_authenticated_user(client, "timeout_user", "timeout@example.com")
    resp = client.post(
        "/api/v1/chat/conversations",
        json={"title": "Timeout Test"},
        headers=headers,
    )
    conv_id = resp.json()["id"]

    mock_llm.should_fail = True
    mock_llm.failure_type = "timeout"

    send_resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"content": "Will timeout"},
        headers=headers,
    )
    assert send_resp.status_code == 504
    assert "timed out" in send_resp.json()["detail"].lower()


def test_chat_ui_endpoint_accessible(client: TestClient) -> None:
    resp = client.get("/chat")
    assert resp.status_code == 200
    assert "AI Document SaaS - Chatbot" in resp.text
