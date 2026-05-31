from fastapi.testclient import TestClient


def test_create_and_list_leather_types(client: TestClient) -> None:
    first_response = client.post("/api/leather-types", json={"name": "Crazy Horse"})
    second_response = client.post("/api/leather-types", json={"name": "Наппа"})

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    list_response = client.get(
        "/api/leather-types?sort_direction=desc&page=1&page_size=1"
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["pages"] == 2
    assert payload["items"][0]["name"] == "Наппа"
    assert payload["items"][0]["is_active"] is True


def test_leather_types_search_is_case_insensitive_for_cyrillic(
    client: TestClient,
) -> None:
    response = client.post("/api/leather-types", json={"name": "Краст"})
    assert response.status_code == 201

    search_response = client.get("/api/leather-types?search=кРа")

    assert search_response.status_code == 200
    payload = search_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Краст"


def test_leather_type_status_hides_inactive_by_default(client: TestClient) -> None:
    create_response = client.post("/api/leather-types", json={"name": "Велюр"})
    assert create_response.status_code == 201
    leather_type_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/leather-types/{leather_type_id}/status",
        json={"is_active": False},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["is_active"] is False

    default_list_response = client.get("/api/leather-types")
    assert default_list_response.status_code == 200
    assert default_list_response.json()["total"] == 0

    full_list_response = client.get("/api/leather-types?include_inactive=true")
    assert full_list_response.status_code == 200
    assert full_list_response.json()["total"] == 1
    assert full_list_response.json()["items"][0]["is_active"] is False


def test_create_leather_type_rejects_duplicate_name(client: TestClient) -> None:
    first_response = client.post("/api/leather-types", json={"name": "Крейзи Хорс"})
    assert first_response.status_code == 201

    second_response = client.post("/api/leather-types", json={"name": "кРейзи хорс"})

    assert second_response.status_code == 422
    assert (
        second_response.json()["detail"]
        == "Leather type with this name already exists."
    )


def test_leather_type_write_requires_constructor_or_admin(client: TestClient) -> None:
    create_response = client.post("/api/leather-types", json={"name": "Спилок"})
    assert create_response.status_code == 201
    leather_type_id = create_response.json()["id"]

    user_response = client.post(
        "/api/users",
        json={
            "name": "Исполнитель справочников",
            "phone": "+79994445566",
            "roles": ["worker"],
            "is_active": True,
        },
    )
    assert user_response.status_code == 201

    setup_response = client.post(
        "/api/auth/setup-password",
        json={"phone": "+79994445566", "new_password": "password123"},
    )
    assert setup_response.status_code == 200

    forbidden_create_response = client.post(
        "/api/leather-types",
        json={"name": "Сафьян"},
    )
    assert forbidden_create_response.status_code == 403
    assert forbidden_create_response.json()["detail"] == "Недостаточно прав."

    forbidden_patch_response = client.patch(
        f"/api/leather-types/{leather_type_id}/status",
        json={"is_active": False},
    )
    assert forbidden_patch_response.status_code == 403
    assert forbidden_patch_response.json()["detail"] == "Недостаточно прав."

    list_response = client.get("/api/leather-types")
    assert list_response.status_code == 200
