from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_authenticated_session, get_session
from app.api.routes.completed_work import router as admin_router
from app.api.routes.personal_work import router
from app.core.database import Base
from app.core.security import hash_password
from app.models.bonus import Bonus, UserBonus
from app.models.user import User
from app.services import personal_work_service
from app.services.auth_service import AuthenticatedSession


@pytest.fixture()
def personal_api() -> Iterator[tuple[TestClient, Session, AuthenticatedSession]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id=1,
                    name="Исполнитель 1",
                    phone="1",
                    roles=["worker"],
                    password_hash=hash_password("password-one"),
                    created_at=1,
                    updated_at=1,
                ),
                User(
                    id=2,
                    name="Исполнитель 2",
                    phone="2",
                    roles=["worker"],
                    password_hash=hash_password("password-two"),
                    created_at=1,
                    updated_at=1,
                ),
                Bonus(id=1, name="Скрытая премия", amount_cents=12345),
            ]
        )
        session.flush()
        session.add(UserBonus(user_id=1, bonus_id=1))
        session.commit()
        auth = AuthenticatedSession(
            session_id=1,
            token="test-session-one",
            user_id=1,
            user_name="Исполнитель 1",
            user_roles=["worker"],
            expires_at=9999999999999,
            idle_expires_at=9999999999999,
        )
        app = FastAPI()
        app.include_router(router, prefix="/api/worker")
        app.include_router(admin_router, prefix="/api/admin")
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_authenticated_session] = lambda: auth
        with TestClient(app) as client:
            yield client, session, auth
    engine.dispose()


def test_personal_report_requires_current_password_and_omits_bonuses(
    personal_api: tuple[TestClient, Session, AuthenticatedSession],
) -> None:
    """
    Проверяем персональный просмотр после ввода пароля:
    - отклонить запрос без подтверждения и с паролем другого пользователя
    - использовать сотрудника из сессии при попытке подставить чужой идентификатор
    - не передавать премии и выплату, не разрешать административную выгрузку
    """
    client, _, _ = personal_api
    path = "/api/worker/completed-work"
    assert client.get(f"{path}?year=2026&month=11").status_code == 403
    assert (
        client.post(f"{path}/unlock", json={"password": "password-two"}).status_code
        == 403
    )
    unlocked = client.post(f"{path}/unlock", json={"password": "password-one"})
    assert unlocked.status_code == 200
    assert unlocked.headers["cache-control"] == "no-store"
    headers = {"X-Work-Report-Token": unlocked.json()["token"]}
    for month in (10, 11):
        response = client.get(
            f"{path}?year=2026&month={month}&user_id=2", headers=headers
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        report = response.json()
        assert report["user_id"] == 1
        assert report["month"] == month
        assert report["piecework_cents"] == 0
        assert not {"bonuses", "bonuses_cents", "payout_cents"}.intersection(report)
        assert "Скрытая премия" not in response.text
    assert (
        client.get(
            "/api/admin/users/1/completed-work.xlsx?year=2026&month=11", headers=headers
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/admin/users/2/completed-work?year=2026&month=11", headers=headers
        ).status_code
        == 403
    )


def test_personal_access_cannot_be_reused_by_other_session_or_password(
    personal_api: tuple[TestClient, Session, AuthenticatedSession],
) -> None:
    """
    Проверяем привязку подтверждения к текущему пользователю и сессии:
    - отклонить изменённый токен и его использование другой сессией
    - после смены пароля отклонить старое подтверждение
    """
    client, session, auth = personal_api
    path = "/api/worker/completed-work"
    token = client.post(f"{path}/unlock", json={"password": "password-one"}).json()[
        "token"
    ]

    def response(token_value: str) -> int:
        return client.get(
            f"{path}?year=2026&month=11", headers={"X-Work-Report-Token": token_value}
        ).status_code

    assert response(token + "0") == 403
    assert response("invalid") == 403
    auth.session_id = 2
    assert response(token) == 403
    auth.session_id = 1
    auth.user_id = 2
    assert response(token) == 403
    auth.user_id = 1
    auth.token = "different-session-secret"
    assert response(token) == 403
    auth.token = "test-session-one"
    assert response(token) == 200
    user = session.get(User, 1)
    assert user is not None
    user.password_hash = hash_password("new-password")
    session.commit()
    assert response(token) == 403


def test_personal_access_expires_and_role_is_required(
    personal_api: tuple[TestClient, Session, AuthenticatedSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Проверяем ограничение срока и роли:
    - после истечения подтверждения снова требовать пароль
    - не разрешать открытие пользователю без роли исполнителя
    """
    client, _, auth = personal_api
    path = "/api/worker/completed-work"
    monkeypatch.setattr(personal_work_service.time, "time", lambda: 1000)
    access = client.post(f"{path}/unlock", json={"password": "password-one"}).json()
    monkeypatch.setattr(
        personal_work_service.time, "time", lambda: access["expires_at"] / 1000
    )
    assert (
        client.get(
            f"{path}?year=2026&month=11",
            headers={"X-Work-Report-Token": access["token"]},
        ).status_code
        == 403
    )
    auth.user_roles = ["brigadier"]
    assert (
        client.post(f"{path}/unlock", json={"password": "password-one"}).status_code
        == 403
    )


def test_personal_report_rejects_inactive_or_unset_password(
    personal_api: tuple[TestClient, Session, AuthenticatedSession],
) -> None:
    """
    Проверяем запрет просмотра при недоступной учётной записи:
    - без заданного пароля не выдавать подтверждение
    - не выдавать подтверждение неактивному сотруднику
    """
    client, session, _ = personal_api
    user = session.get(User, 1)
    assert user is not None
    user.password_hash = None
    session.commit()
    assert (
        client.post(
            "/api/worker/completed-work/unlock", json={"password": "password-one"}
        ).status_code
        == 403
    )
    user.password_hash = hash_password("password-one")
    user.is_active = False
    session.commit()
    assert (
        client.post(
            "/api/worker/completed-work/unlock", json={"password": "password-one"}
        ).status_code
        == 403
    )
