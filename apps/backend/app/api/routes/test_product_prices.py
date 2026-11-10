# ruff: noqa: F811

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_authenticated_session
from app.api.routes.products import router
from app.api.routes.test_order_restrictions import order_api  # noqa: F401
from app.models.operation import Operation


@pytest.mark.parametrize("role", ["admin", "constructor", "brigadier", "worker"])
def test_only_admin_changes_existing_operation_price(
    order_api: tuple[TestClient, Session, FastAPI],
    role: str,
) -> None:
    """
    Проверяем права изменения существующей расценки:
    - отправить новую цену от администратора и остальных ролей
    - сохранить новую цену только для администратора
    - разрешить прежнюю правку нормы без изменения цены
    """
    client, session, app = order_api
    app.include_router(router, prefix="/products")
    app.dependency_overrides[get_authenticated_session] = lambda: SimpleNamespace(
        user_roles=[role]
    )
    response = client.patch(
        "/products/1/costs",
        json={
            "operations": [{"id": 1, "price_cents": 12345}],
        },
    )
    assert response.status_code == (200 if role == "admin" else 403)
    session.expire_all()
    operation = session.get(Operation, 1)
    assert operation is not None
    assert operation.price_cents == (12345 if role == "admin" else None)
    response = client.patch(
        "/products/1/costs",
        json={
            "operations": [{"id": 1, "standard_time_seconds": 90}],
        },
    )
    assert response.status_code == 200
    assert response.json()["operations"][0]["standard_time_seconds"] == 90
