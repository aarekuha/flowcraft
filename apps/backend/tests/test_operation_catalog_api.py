from fastapi.testclient import TestClient


def test_create_and_list_operation_catalog_entries(client: TestClient) -> None:
    first_response = client.post("/api/operation-catalog", json={"name": "Крой"})
    second_response = client.post("/api/operation-catalog", json={"name": "Пошив"})

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    list_response = client.get(
        "/api/operation-catalog?sort_direction=desc&page=1&page_size=1"
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["pages"] == 2
    assert payload["items"][0]["name"] == "Пошив"
    assert payload["items"][0]["is_active"] is True


def test_operation_catalog_search_is_case_insensitive_for_cyrillic(
    client: TestClient,
) -> None:
    response = client.post("/api/operation-catalog", json={"name": "Покраска уреза"})
    assert response.status_code == 201

    search_response = client.get("/api/operation-catalog?search=уРе")

    assert search_response.status_code == 200
    payload = search_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Покраска уреза"


def test_operation_catalog_status_hides_inactive_by_default(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/operation-catalog",
        json={"name": "Финишная полировка"},
    )
    assert create_response.status_code == 201
    entry_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/operation-catalog/{entry_id}/status",
        json={"is_active": False},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["is_active"] is False

    default_list_response = client.get("/api/operation-catalog")
    assert default_list_response.status_code == 200
    assert default_list_response.json()["total"] == 0

    full_list_response = client.get("/api/operation-catalog?include_inactive=true")
    assert full_list_response.status_code == 200
    assert full_list_response.json()["total"] == 1
    assert full_list_response.json()["items"][0]["is_active"] is False


def test_create_operation_catalog_entry_rejects_duplicate_name(
    client: TestClient,
) -> None:
    first_response = client.post("/api/operation-catalog", json={"name": "Сборка"})
    assert first_response.status_code == 201

    second_response = client.post("/api/operation-catalog", json={"name": "сБорка"})

    assert second_response.status_code == 422
    assert (
        second_response.json()["detail"]
        == "Operation with this name already exists."
    )


def test_operation_catalog_supports_adjacent_kind(client: TestClient) -> None:
    """
    Проверяем тип смежной операции в справочнике:
    - создать обычную операцию
    - изменить тип на смежный и вернуть его через API
    """
    create_response = client.post(
        "/api/operation-catalog",
        json={
            "name": "Подготовка фурнитуры",
            "operation_kind": "adjacent",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["operation_kind"] == "adjacent"

    regular_response = client.patch(
        f"/api/operation-catalog/{create_response.json()['id']}/kind",
        json={"operation_kind": "regular"},
    )
    assert regular_response.status_code == 200

    adjacent_response = client.patch(
        f"/api/operation-catalog/{create_response.json()['id']}/kind",
        json={"operation_kind": "adjacent"},
    )

    assert adjacent_response.status_code == 200
    assert adjacent_response.json()["operation_kind"] == "adjacent"

    list_response = client.get("/api/operation-catalog?search=фурнитуры")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["operation_kind"] == "adjacent"
