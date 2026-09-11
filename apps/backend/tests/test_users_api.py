from fastapi.testclient import TestClient


def user_payload(
    name: str,
    phone: str,
    *,
    roles: list[str],
    is_active: bool = True,
    author_user_id: int | None = None,
) -> dict:
    payload = {
        "name": name,
        "phone": phone,
        "roles": roles,
        "is_active": is_active,
    }
    if author_user_id is not None:
        payload["author_user_id"] = author_user_id
    return payload


def test_create_and_list_user(client: TestClient) -> None:
    payload = user_payload(
        "Анна Петрова",
        "+79990000010",
        roles=["worker", "constructor", "reports"],
    )

    create_response = client.post("/api/users", json=payload)

    assert create_response.status_code == 201
    created_user = create_response.json()
    assert created_user["name"] == payload["name"]
    assert created_user["phone"] == payload["phone"]
    assert created_user["roles"] == payload["roles"]
    assert created_user["is_active"] is True
    assert created_user["deleted_at"] is None
    assert created_user["author_user_id"] == created_user["id"]
    assert created_user["author"] == created_user["name"]

    list_response = client.get("/api/users")

    assert list_response.status_code == 200
    users = list_response.json()
    assert any(user["id"] == created_user["id"] for user in users)


def test_update_user(client: TestClient) -> None:
    author_response = client.post(
        "/api/users",
        json=user_payload("Главный администратор", "+79990000011", roles=["admin"]),
    )
    assert author_response.status_code == 201
    author_id = author_response.json()["id"]

    create_response = client.post(
        "/api/users",
        json=user_payload(
            "Илья Сергеев",
            "+79990000012",
            roles=["brigadier"],
            author_user_id=author_id,
        ),
    )
    user_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/users/{user_id}",
        json=user_payload(
            "Илья Сергеев Обновленный",
            "+79990000013",
            roles=["brigadier", "admin"],
            is_active=False,
        ),
    )

    assert update_response.status_code == 200
    updated_user = update_response.json()
    assert updated_user["name"] == "Илья Сергеев Обновленный"
    assert updated_user["phone"] == "+79990000013"
    assert updated_user["author_user_id"] == author_id
    assert updated_user["author"] == "Главный администратор"
    assert updated_user["roles"] == ["brigadier", "admin"]
    assert updated_user["is_active"] is False
    assert updated_user["updated_at"] >= updated_user["created_at"]


def test_update_user_status(client: TestClient) -> None:
    create_response = client.post(
        "/api/users",
        json=user_payload("Марина Волкова", "+79990000014", roles=["constructor"]),
    )
    user_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/users/{user_id}/status",
        json={"is_active": False},
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["is_active"] is False


def test_delete_user_hides_it_from_regular_list_but_returns_in_deleted_and_get_by_id(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/users",
        json=user_payload("Олег Козлов", "+79990000015", roles=["admin"]),
    )
    user_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/users/{user_id}")
    assert delete_response.status_code == 204

    list_response = client.get("/api/users")
    assert list_response.status_code == 200
    assert all(user["id"] != user_id for user in list_response.json())

    deleted_response = client.get("/api/users/deleted")
    assert deleted_response.status_code == 200
    deleted_users = deleted_response.json()
    assert len(deleted_users) == 1
    assert deleted_users[0]["id"] == user_id
    assert deleted_users[0]["deleted_at"] is not None

    get_response = client.get(f"/api/users/{user_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == user_id
    assert get_response.json()["deleted_at"] is not None


def test_get_unknown_user_returns_404(client: TestClient) -> None:
    response = client.get("/api/users/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "User 999 not found."


def test_deleted_user_cannot_be_updated_or_deleted_again(client: TestClient) -> None:
    create_response = client.post(
        "/api/users",
        json=user_payload("Светлана Миронова", "+79990000016", roles=["worker"]),
    )
    user_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/users/{user_id}")
    assert delete_response.status_code == 204

    update_response = client.put(
        f"/api/users/{user_id}",
        json=user_payload(
            "Светлана Миронова 2",
            "+79990000017",
            roles=["worker", "brigadier"],
        ),
    )
    assert update_response.status_code == 404

    second_delete_response = client.delete(f"/api/users/{user_id}")
    assert second_delete_response.status_code == 404


def test_cannot_remove_last_active_admin_role(client: TestClient) -> None:
    update_response = client.put(
        "/api/users/1",
        json=user_payload(
            "Test Admin",
            "+79990000001",
            roles=["worker"],
        ),
    )

    assert update_response.status_code == 422
    assert update_response.json()["detail"] == "Нельзя убрать последнего активного администратора."


def test_cannot_deactivate_last_active_admin(client: TestClient) -> None:
    patch_response = client.patch(
        "/api/users/1/status",
        json={"is_active": False},
    )

    assert patch_response.status_code == 422
    assert patch_response.json()["detail"] == "Нельзя убрать последнего активного администратора."


def test_cannot_delete_last_active_admin(client: TestClient) -> None:
    delete_response = client.delete("/api/users/1")

    assert delete_response.status_code == 422
    assert delete_response.json()["detail"] == "Нельзя убрать последнего активного администратора."


def test_can_change_admin_when_another_active_admin_exists(client: TestClient) -> None:
    second_admin_response = client.post(
        "/api/users",
        json=user_payload("Второй Администратор", "+79990000018", roles=["admin"]),
    )
    assert second_admin_response.status_code == 201

    update_response = client.put(
        "/api/users/1",
        json=user_payload(
            "Test Admin",
            "+79990000001",
            roles=["worker"],
        ),
    )

    assert update_response.status_code == 200
    assert update_response.json()["roles"] == ["worker"]
