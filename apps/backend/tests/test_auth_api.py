from fastapi.testclient import TestClient


def test_current_session_and_logout(client: TestClient) -> None:
    me_response = client.get("/api/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["user_name"] == "Test Admin"
    assert "admin" in me_response.json()["user_roles"]

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    me_after_logout = client.get("/api/auth/me")
    assert me_after_logout.status_code == 401


def test_login_requests_password_setup_for_user_without_password(client: TestClient) -> None:
    create_response = client.post(
        "/api/users",
        json={
            "name": "Новый Пользователь",
            "phone": "+79990000090",
            "roles": ["worker"],
            "is_active": True,
        },
    )
    assert create_response.status_code == 201

    client.post("/api/auth/logout")

    login_response = client.post(
        "/api/auth/login",
        json={
            "phone": "+79990000090",
            "password": "temporary-password",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["status"] == "password_setup_required"

    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": "+79990000090",
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user_name"] == "Новый Пользователь"


def test_login_with_empty_password_opens_setup_flow_for_user_without_password(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/users",
        json={
            "name": "Пользователь Без Пароля",
            "phone": "+79990000091",
            "roles": ["worker"],
            "is_active": True,
        },
    )
    assert create_response.status_code == 201

    client.post("/api/auth/logout")

    login_response = client.post(
        "/api/auth/login",
        json={
            "phone": "+79990000091",
            "password": "",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["status"] == "password_setup_required"


def test_change_password_rotates_session(client: TestClient) -> None:
    response = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "password123",
            "new_password": "password456",
        },
    )

    assert response.status_code == 200

    client.post("/api/auth/logout")

    old_login = client.post(
        "/api/auth/login",
        json={
            "phone": "+79990000001",
            "password": "password123",
        },
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login",
        json={
            "phone": "+79990000001",
            "password": "password456",
        },
    )
    assert new_login.status_code == 200
    assert new_login.json()["status"] == "authenticated"


def test_login_accepts_phone_in_different_format(client: TestClient) -> None:
    client.post("/api/auth/logout")

    login_response = client.post(
        "/api/auth/login",
        json={
            "phone": "+7 999 000 00 01",
            "password": "password123",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["status"] == "authenticated"

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user_name"] == "Test Admin"


def test_setup_password_keeps_original_password_value(client: TestClient) -> None:
    create_response = client.post(
        "/api/users",
        json={
            "name": "Пользователь С Цифрами",
            "phone": "+7 999 000 00 92",
            "roles": ["worker"],
            "is_active": True,
        },
    )
    assert create_response.status_code == 201

    client.post("/api/auth/logout")

    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": "+79990000092",
            "new_password": "pass12345",
        },
    )
    assert setup_response.status_code == 200

    client.post("/api/auth/logout")

    login_response = client.post(
        "/api/auth/login",
        json={
            "phone": "+7 999 000 00 92",
            "password": "pass12345",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["status"] == "authenticated"
