from fastapi.testclient import TestClient


def create_author_user(client: TestClient, name: str = "Марина Волкова") -> dict:
    phone_suffix = sum(ord(char) for char in name) % 10_000
    response = client.post(
        "/api/users",
        json={
            "name": name,
            "phone": f"+7999111{phone_suffix:04d}",
            "roles": ["constructor"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_and_get_product(client: TestClient) -> None:
    author_user = create_author_user(client)
    payload = {
        "name": "Кошелек Daily Fold",
        "version": "1.0",
        "author_user_id": author_user["id"],
        "operations": [
            {
                "name": "Крой",
                "children": [
                    {"name": "Фасад", "children": []},
                    {"name": "Подклад", "children": []},
                ],
            },
            {"name": "Пошив", "children": []},
        ],
    }

    create_response = client.post("/api/products", json=payload)

    assert create_response.status_code == 201
    created_product = create_response.json()
    assert created_product["name"] == payload["name"]
    assert created_product["version"] == payload["version"]
    assert created_product["author"] == author_user["name"]
    assert len(created_product["operations"]) == 2
    assert created_product["operations"][0]["children"][0]["name"] == "Фасад"

    product_id = created_product["id"]

    get_response = client.get(f"/api/products/{product_id}")

    assert get_response.status_code == 200
    fetched_product = get_response.json()
    assert fetched_product == created_product


def test_list_products_returns_operations_count(client: TestClient) -> None:
    author_user = create_author_user(client)
    create_response = client.post(
        "/api/products",
        json={
            "name": "Сумка Saddle Mini",
            "version": "2.0",
            "author_user_id": author_user["id"],
            "operations": [
                {"name": "Подготовка деталей", "children": []},
                {
                    "name": "Сборка",
                    "children": [
                        {"name": "Пошив корпуса", "children": []},
                    ],
                },
            ],
        },
    )
    assert create_response.status_code == 201

    list_response = client.get("/api/products")

    assert list_response.status_code == 200
    products = list_response.json()
    assert len(products) == 1
    assert products[0]["name"] == "Сумка Saddle Mini"
    assert products[0]["author"] == author_user["name"]
    assert products[0]["operations_count"] == 3


def test_create_product_rejects_duplicate_sibling_operations(client: TestClient) -> None:
    author_user = create_author_user(client)
    response = client.post(
        "/api/products",
        json={
            "name": "Ремень Craft Line",
            "version": "1.2",
            "author_user_id": author_user["id"],
            "operations": [
                {"name": "Крой", "children": []},
                {"name": "крой", "children": []},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Operation names must be unique among siblings."


def test_create_product_rejects_duplicate_name_and_version(client: TestClient) -> None:
    author_user = create_author_user(client)
    payload = {
        "name": "Кошелек Daily Fold",
        "version": "1.0",
        "author_user_id": author_user["id"],
        "operations": [{"name": "Крой", "children": []}],
    }

    first_response = client.post("/api/products", json=payload)
    assert first_response.status_code == 201

    second_response = client.post("/api/products", json=payload)

    assert second_response.status_code == 422
    assert second_response.json()["detail"] == "Product with this name and version already exists."


def test_create_product_rejects_empty_operation_name(client: TestClient) -> None:
    author_user = create_author_user(client)
    response = client.post(
        "/api/products",
        json={
            "name": "Рюкзак Field Pack",
            "version": "0.9",
            "author_user_id": author_user["id"],
            "operations": [
                {"name": " ", "children": []},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Value error, Operation name must not be empty."


def test_delete_product_removes_it(client: TestClient) -> None:
    author_user = create_author_user(client)
    create_response = client.post(
        "/api/products",
        json={
            "name": "Портмоне Classic",
            "version": "1.1",
            "author_user_id": author_user["id"],
            "operations": [{"name": "Сборка", "children": []}],
        },
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/products/{product_id}")

    assert delete_response.status_code == 204

    get_response = client.get(f"/api/products/{product_id}")

    assert get_response.status_code == 404
    assert get_response.json()["detail"] == f"Product {product_id} not found."


def test_update_product_status(client: TestClient) -> None:
    author_user = create_author_user(client)
    create_response = client.post(
        "/api/products",
        json={
            "name": "Портфель Office Line",
            "version": "1.0",
            "author_user_id": author_user["id"],
            "operations": [{"name": "Сборка", "children": []}],
        },
    )
    assert create_response.status_code == 201
    product_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/products/{product_id}/status",
        json={"is_active": False},
    )

    assert patch_response.status_code == 200
    updated_product = patch_response.json()
    assert updated_product["is_active"] is False

    list_response = client.get("/api/products")
    assert list_response.status_code == 200
    assert list_response.json()[0]["is_active"] is False


def test_get_unknown_product_returns_404(client: TestClient) -> None:
    response = client.get("/api/products/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Product 999 not found."


def test_create_product_without_author_uses_default_author(client: TestClient) -> None:
    response = client.post(
        "/api/products",
        json={
            "name": "Обложка Heritage",
            "version": "1.0",
            "operations": [{"name": "Крой", "children": []}],
        },
    )

    assert response.status_code == 201
    assert response.json()["author"]
