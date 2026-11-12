import gzip
import json
from collections.abc import Iterator
from time import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_session
from app.core.database import Base
from app.main import create_application
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.auth_service import SESSION_COOKIE_NAME


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    now = int(time() * 1000)
    with factory() as session:
        for identifier, role in ((1, "worker"), (2, "admin")):
            session.add(
                User(
                    id=identifier,
                    name=role,
                    phone=str(identifier),
                    roles=[role],
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            session.add(
                AuthSession(
                    token=role,
                    user_id=identifier,
                    user_name=role,
                    user_roles=[role],
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + 3600000,
                    idle_expires_at=now + 3600000,
                )
            )
        session.commit()
    app = create_application()
    app.state.session_factory = factory

    def db_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = db_session
    with TestClient(app) as instance:
        instance.cookies.set(SESSION_COOKIE_NAME, "worker")
        yield instance
    engine.dispose()


@pytest.fixture()
def payload() -> dict:
    now = int(time() * 1000)
    return {
        "owner_user_id": 1,
        "report_key": str(uuid4()),
        "captured_at": now,
        "window_start": now - 86400000,
        "build": "test",
        "viewport_width": 800,
        "viewport_height": 600,
        "events": [
            {"kind": "timer_click", "at": now, "order_id": 495, "operation_id": 517}
        ],
    }


def test_upload_retry_and_admin_access(client: TestClient, payload: dict) -> None:
    """
    Проверяем отправку через существующую авторизацию:
    - сохранить сжатый отчёт и повторить отправку без создания дубликата
    - разрешить просмотр администратору и запретить исполнителю
    """
    response = client.post(
        "/api/diagnostics/reports",
        content=gzip.compress(json.dumps(payload).encode()),
        headers={"Content-Encoding": "gzip"},
    )
    assert response.status_code == 200
    report_id = response.json()["id"]
    assert client.post("/api/diagnostics/reports", json=payload).json() == {
        "id": report_id
    }
    assert client.get(f"/api/diagnostics/reports/{report_id}").status_code == 403
    client.cookies.set(SESSION_COOKIE_NAME, "admin")
    assert len(client.get("/api/diagnostics/reports").json()) == 1
    report = client.get(f"/api/diagnostics/reports/{report_id}").json()
    assert report["user_id"] == 1
    assert report["report"]["events"][0]["operation_id"] == 517


def test_upload_rejects_changed_owner_and_anonymous(
    client: TestClient, payload: dict
) -> None:
    """
    Проверяем границы текущей сессии:
    - запретить отправку сохранённого отчёта другого пользователя
    - запретить отправку без авторизации
    """
    payload["owner_user_id"] = 2
    assert client.post("/api/diagnostics/reports", json=payload).status_code == 403
    client.cookies.clear()
    assert client.post("/api/diagnostics/reports", json=payload).status_code == 401


@pytest.mark.parametrize("invalid", ["old_event", "short_window", "secret", "gzip"])
def test_upload_rejects_invalid_report(
    client: TestClient, payload: dict, invalid: str
) -> None:
    """
    Проверяем проверку входящего отчёта:
    - отклонить события вне суток, лишние поля и повреждённое сжатие
    - не сохранить некорректный отчёт
    """
    if invalid == "old_event":
        payload["events"][0]["at"] = payload["window_start"] - 1
    elif invalid == "short_window":
        payload["window_start"] += 1
    elif invalid == "secret":
        payload["events"][0]["password"] = "must-not-store"
    if invalid == "gzip":
        response = client.post(
            "/api/diagnostics/reports",
            content=b"invalid",
            headers={"Content-Encoding": "gzip"},
        )
    else:
        response = client.post("/api/diagnostics/reports", json=payload)
    assert response.status_code == 422
    assert "must-not-store" not in response.text
    client.cookies.set(SESSION_COOKIE_NAME, "admin")
    assert client.get("/api/diagnostics/reports").json() == []
