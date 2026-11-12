import json
from collections.abc import Iterator
from time import time
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_session
from app.core.database import Base
from app.main import create_application
from app.models.auth_session import AuthSession
from app.models.operation import Operation
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderAssignment
from app.services.auth_service import SESSION_COOKIE_NAME
from app.services.timer_service import TimerService


@pytest.fixture()
def timer_client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    now = int(time() * 1000)
    with factory() as session:
        session.add(
            User(
                id=1,
                name="Исполнитель",
                phone="1",
                roles=["worker"],
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            Product(id=1, name="Изделие", version="1", author="Тест", created_at=now)
        )
        session.flush()
        session.add(
            WorkOrder(
                id=1,
                order_number="100",
                product_id=1,
                quantity=10,
                production_stage="in_work",
                created_at=now,
                updated_at=now,
            )
        )
        for operation_id in (1, 2):
            session.add(
                Operation(
                    id=operation_id, product_id=1, name=f"Операция {operation_id}"
                )
            )
            session.add(
                WorkOrderAssignment(
                    work_order_id=1, operation_id=operation_id, worker_user_id=1
                )
            )
        session.add(
            AuthSession(
                id=1,
                token="secret-cookie-do-not-log",
                user_id=1,
                user_name="Исполнитель",
                user_roles=["worker"],
                created_at=now,
                last_seen_at=now,
                expires_at=now + 3600000,
                idle_expires_at=now + 3600000,
            )
        )
        session.commit()
    app = create_application()
    app.state.session_factory = factory

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app, raise_server_exceptions=False) as client:
        client.cookies.set(SESSION_COOKIE_NAME, "secret-cookie-do-not-log")
        assert client.post("/api/timers/start-day").status_code == 200
        yield client
    engine.dispose()


def audit_records(caplog: pytest.LogCaptureFixture) -> list[dict]:
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "uvicorn.error.timer_audit"
    ]


def test_audit_records_switch_and_unchanged_without_secrets(
    timer_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Проверяем аудит успешных переключений:
    - сменить две операции и повторно выбрать уже активную
    - связать запрос, сохранение и ответ одним серверным идентификатором
    - сохранить цели и идентификаторы таймеров без cookie и лишних полей
    """
    for operation in (1, 2):
        caplog.clear()
        response = timer_client.post(
            "/api/timers/switch",
            json={
                "timer_type": "operation",
                "order_id": 1,
                "operation_id": operation,
                "user_id": 999,
                "token": "secret-body-do-not-log",
            },
            headers={"X-Timer-Request-Id": "untrusted-request-id"},
        )
        assert response.status_code == 200
        records = audit_records(caplog)
        assert [r["event"] for r in records] == [
            "timer_request_started",
            "timer_command_received",
            "timer_change_committed",
            "timer_request_finished",
        ]
        assert {r["request_id"] for r in records} == {
            response.headers["x-timer-request-id"]
        }
        assert response.headers["x-timer-request-id"] != "untrusted-request-id"
        result = records[-1]
        assert result["user_id"] == 1 and result["auth_session_id"] == 1
        assert result["requested"]["operation_id"] == operation
        assert result["committed_timer"]["operation_id"] == operation
        assert (
            result["previous_timer"]["timer_session_id"]
            != result["committed_timer"]["timer_session_id"]
        )
        assert result["committed"] and result["outcome"] == "success"
        assert result["duration_ms"] >= 0
        assert "secret-" not in json.dumps(records)
    caplog.clear()
    response = timer_client.post(
        "/api/timers/switch",
        json={"timer_type": "operation", "order_id": 1, "operation_id": 2},
    )
    assert response.status_code == 200
    result = audit_records(caplog)[-1]
    assert result["outcome"] == "unchanged"
    assert not result["committed"]
    assert result["previous_timer"]["operation_id"] == 2


@pytest.mark.parametrize("failure", ["assignment", "payload", "unauthorized"])
def test_rejected_requests_are_audited(
    timer_client: TestClient,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    """
    Проверяем отклонённые запросы:
    - запросить неназначенную операцию, неверный тип или запрос без авторизации
    - записать отказ даже до входа в обработчик переключения
    - не регистрировать успешное сохранение и не менять таймер
    """
    caplog.clear()
    payload = {"timer_type": "operation", "order_id": 1, "operation_id": 999}
    if failure == "payload":
        payload["timer_type"] = "secret-invalid-type"
    if failure == "unauthorized":
        timer_client.cookies.clear()
    response = timer_client.post("/api/timers/switch", json=payload)
    assert response.status_code == (401 if failure == "unauthorized" else 422)
    result = audit_records(caplog)[-1]
    assert result["outcome"] == "rejected"
    assert not result["committed"]
    assert result["user_id"] == (None if failure == "unauthorized" else 1)
    assert "secret-" not in json.dumps(audit_records(caplog))
    if failure == "assignment":
        assert result["requested"]["operation_id"] == 999
        assert result["previous_timer"]["timer_type_code"] == 1


@pytest.mark.parametrize("after_commit", [False, True])
def test_audit_distinguishes_failure_before_and_after_commit(
    timer_client: TestClient,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    after_commit: bool,
) -> None:
    """
    Проверяем диагностику искусственной серверной ошибки:
    - вызвать ошибку до сохранения или после commit при подготовке ответа
    - различить откат и фактически сохранённое переключение
    - не включать произвольный текст исключения в аудит
    """

    def fail(*args: object) -> None:
        raise RuntimeError("secret-exception-do-not-log")

    method = "_serialize_state" if after_commit else "_commit_timer_change"
    monkeypatch.setattr(TimerService, method, fail)
    caplog.clear()
    response = timer_client.post("/api/timers/switch", json={"timer_type": "break"})
    assert response.status_code == 500
    result = audit_records(caplog)[-1]
    assert result["outcome"] == "error"
    assert result["committed"] is after_commit
    assert result["exception_type"] == "RuntimeError"
    assert "secret-exception" not in json.dumps(audit_records(caplog))
    with cast(FastAPI, timer_client.app).state.session_factory() as session:
        active = session.scalar(
            select(TimerSession).where(TimerSession.ended_at.is_(None))
        )
        assert active is not None
        assert active.timer_type_code == (3 if after_commit else 1)


def test_day_end_audit_records_no_remaining_timer(
    timer_client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Проверяем аудит завершения дня:
    - завершить день с активной подготовкой
    - сохранить идентификатор закрытого таймера и отсутствие нового
    - повторное завершение отразить как отсутствие изменений
    """
    caplog.clear()
    assert timer_client.post("/api/timers/end-day").status_code == 200
    result = audit_records(caplog)[-1]
    assert result["previous_timer"]["timer_type_code"] == 1
    assert result["committed"] and result["committed_timer"] is None
    caplog.clear()
    assert timer_client.post("/api/timers/end-day").status_code == 200
    assert audit_records(caplog)[-1]["outcome"] == "unchanged"
