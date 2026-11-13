# ruff: noqa: I001
from collections.abc import Iterator
from pathlib import Path
from time import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_session
from app.core.config import settings
from app.core.database import Base
from app.main import create_application
from app.models.auth_session import AuthSession
from app.models.bitrix import BitrixConnection, BitrixMapping
from app.models.product import Product
from app.models.user import User
from app.services.auth_service import SESSION_COOKIE_NAME
from app.services.bitrix_client import BitrixClient, decrypt_webhook
from app.services.bitrix_service import begin_sync, now_ms, sync_catalog, LEASE_MS

WEBHOOK = "https://example.bitrix24.ru/rest/1/test-secret/"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "bitrix_key_path", tmp_path / "keys" / "bitrix.key")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

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
        for identifier in (1, 2, 3):
            session.add(
                Product(
                    id=identifier,
                    name=f"Изделие {identifier}",
                    version="2",
                    author="Тест",
                    created_at=now,
                    is_active=identifier != 3,
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
        instance.cookies.set(SESSION_COOKIE_NAME, "admin")
        yield instance
    engine.dispose()


@pytest.fixture()
def snapshot(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    items = [
        {
            "id": 179,
            "iblockId": 23,
            "name": "Ремень",
            "active": "Y",
            "type": 3,
            "property349": {"value": "Дополнение"},
            "_prices": [],
        },
        {
            "id": 655,
            "iblockId": 25,
            "name": "Ремень с двумя язычками",
            "active": "Y",
            "type": 4,
            "parentId": {"value": "179"},
            "_prices": [
                {
                    "id": 1,
                    "productId": 655,
                    "price": "3950.50",
                    "currency": "RUB",
                    "catalogGroupId": 1,
                }
            ],
        },
    ]
    monkeypatch.setattr(
        BitrixClient,
        "snapshot",
        lambda self: (items, {"23": {"fields": {"property349": {"name": "Описание"}}}}),
    )
    return items


def configure(client: TestClient) -> None:
    assert (
        client.put("/api/bitrix/settings", json={"webhook": WEBHOOK}).status_code == 200
    )


def test_secret_encrypted_and_not_returned(client: TestClient) -> None:
    """
    Проверяем одностороннюю передачу секрета:
    - сохранить вебхук в зашифрованном виде и расшифровать на сервере
    - не вернуть секрет при чтении настроек или ошибке валидации
    """
    configure(client)
    response = client.get("/api/bitrix/settings")
    assert response.json()["configured"] is True
    assert "test-secret" not in response.text
    with client.app.state.session_factory() as session:
        connection = session.get(BitrixConnection, 1)
        assert "test-secret" not in connection.encrypted_webhook
        assert decrypt_webhook(connection.encrypted_webhook) == WEBHOOK
    assert settings.bitrix_key_path.stat().st_mode & 0o777 == 0o600
    invalid = client.put(
        "/api/bitrix/settings", json={"webhook": "http://localhost/test-secret"}
    )
    assert invalid.status_code == 400
    assert "test-secret" not in invalid.text
    assert (
        client.put(
            "/api/bitrix/settings", content=b'{"webhook":"test-secret"'
        ).status_code
        == 400
    )
    assert (
        client.put(
            "/api/bitrix/settings",
            json={"webhook": WEBHOOK.replace("example.", "another.")},
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "settings", None),
        ("put", "settings", {"webhook": WEBHOOK}),
        ("get", "catalog", None),
        ("post", "check", None),
        ("post", "sync", None),
        ("put", "mappings/1", {"bitrix_ids": []}),
    ],
)
def test_all_endpoints_admin_only(
    client: TestClient, method: str, path: str, body
) -> None:
    """
    Проверяем доступ к интеграции:
    - запретить исполнителю читать каталог и менять настройки или связи
    - запретить запрос без текущей авторизации
    """
    client.cookies.set(SESSION_COOKIE_NAME, "worker")
    assert client.request(method, "/api/bitrix/" + path, json=body).status_code == 403
    client.cookies.clear()
    assert client.request(method, "/api/bitrix/" + path, json=body).status_code == 401


def test_sync_prices_mappings_and_removed_items(
    client: TestClient, snapshot: list[dict]
) -> None:
    """
    Проверяем сохранение каталога и сопоставлений:
    - загрузить свойства, вариации и точные цены с валютой
    - обновить название и цену без потери связи с изделием
    - сохранить исчезнувший товар с отметкой отсутствия
    """
    configure(client)
    assert client.post("/api/bitrix/sync").status_code == 202
    data = client.get("/api/bitrix/catalog").json()
    assert {product["id"] for product in data["products"]} == {1, 2}
    items = {item["id"]: item for item in data["items"]}
    assert items[655]["parent_id"] == 179
    assert items[655]["prices"][0]["price"] == "3950.50"
    assert items[179]["fields"]["property349"]["value"] == "Дополнение"
    assert (
        client.put(
            "/api/bitrix/mappings/1", json={"bitrix_ids": [179, 655]}
        ).status_code
        == 200
    )
    assert (
        client.put("/api/bitrix/mappings/2", json={"bitrix_ids": [655]}).status_code
        == 409
    )
    assert (
        client.put("/api/bitrix/mappings/3", json={"bitrix_ids": []}).status_code == 409
    )
    assert (
        client.put("/api/bitrix/mappings/1", json={"bitrix_ids": [999]}).status_code
        == 422
    )
    snapshot.pop(0)
    snapshot[0]["name"] = "Новое название"
    snapshot[0]["_prices"][0]["price"] = "4100.25"
    assert client.post("/api/bitrix/sync").status_code == 202
    data = client.get("/api/bitrix/catalog").json()
    items = {item["id"]: item for item in data["items"]}
    assert items[179]["present"] is False
    assert items[655]["name"] == "Новое название"
    assert items[655]["prices"][0]["price"] == "4100.25"
    assert items[655]["mapped_product_id"] == 1
    assert set(data["products"][0]["bitrix_ids"]) == {179, 655}
    assert (
        client.put("/api/bitrix/mappings/1", json={"bitrix_ids": [179]}).status_code
        == 200
    )
    assert (
        client.put("/api/bitrix/mappings/2", json={"bitrix_ids": [655]}).status_code
        == 200
    )


def test_failed_sync_keeps_previous_data(
    client: TestClient, snapshot: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Проверяем атомарность загрузки:
    - сохранить каталог и затем получить ошибку при следующей загрузке
    - оставить данные и дату успешной загрузки прежними
    """
    configure(client)
    client.post("/api/bitrix/sync")
    old_catalog = client.get("/api/bitrix/catalog").json()
    old_time = client.get("/api/bitrix/settings").json()["synced_at"]

    def broken(self):
        raise RuntimeError(WEBHOOK)

    monkeypatch.setattr(BitrixClient, "snapshot", broken)
    client.post("/api/bitrix/sync")
    assert client.get("/api/bitrix/catalog").json() == old_catalog
    status = client.get("/api/bitrix/settings").json()
    assert status["synced_at"] == old_time
    assert status["last_error"]
    assert "test-secret" not in str(status)
    assert status["syncing"] is False


def test_interrupted_sync_can_retry_without_stale_overwrite(
    client: TestClient, snapshot: list[dict]
) -> None:
    """
    Проверяем восстановление после прерванной загрузки:
    - запретить параллельную загрузку и замену настроек
    - разрешить повтор после истечения блокировки
    - не публиковать результат старой задачи поверх новой
    """
    configure(client)
    factory = client.app.state.session_factory
    with factory() as session:
        old_job = begin_sync(session)
    assert client.post("/api/bitrix/sync").status_code == 409
    assert (
        client.put("/api/bitrix/settings", json={"webhook": WEBHOOK}).status_code == 409
    )
    with factory() as session:
        session.get(BitrixConnection, 1).started_at = now_ms() - LEASE_MS - 1
        session.commit()
        new_job = begin_sync(session)
    sync_catalog(factory, old_job)
    assert client.get("/api/bitrix/catalog").json()["items"] == []
    sync_catalog(factory, new_job)
    assert len(client.get("/api/bitrix/catalog").json()["items"]) == 2


def test_inactive_product_keeps_mapping_and_deleted_product_releases_it(
    client: TestClient, snapshot: list[dict]
) -> None:
    """
    Проверяем жизненный цикл изделия:
    - скрыть неактивное изделие, сохранив сопоставление
    - удалить связь при физическом удалении изделия
    """
    configure(client)
    client.post("/api/bitrix/sync")
    client.put("/api/bitrix/mappings/1", json={"bitrix_ids": [655]})
    with client.app.state.session_factory() as session:
        session.get(Product, 1).is_active = False
        session.commit()
    data = client.get("/api/bitrix/catalog").json()
    assert [product["id"] for product in data["products"]] == [2]
    assert (
        next(item for item in data["items"] if item["id"] == 655)["mapped_product_id"]
        == 1
    )
    with client.app.state.session_factory() as session:
        session.delete(session.get(Product, 1))
        session.commit()
        assert session.get(BitrixMapping, 655) is None


def test_deals_lifecycle_and_atomic_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Проверяем жизненный цикл копии сделок:
    - сохранить все поля и товары, актуализировать закрытую сделку
    - сохранить отсутствующую сделку и предыдущие данные при ошибке
    - применить фильтры и запретить доступ исполнителю
    """
    configure(client)
    items = [
        {
            "fields": {
                "ID": "199719",
                "TITLE": "Муза",
                "CATEGORY_ID": "2",
                "STAGE_ID": "C2:NEW",
                "CLOSED": "N",
                "UF_MULTI": ["a", "b"],
            },
            "product_rows": [
                {
                    "ID": "10",
                    "PRODUCT_ID": 1487,
                    "QUANTITY": 2,
                    "PRICE": 100,
                    "TAX_RATE": 5,
                }
            ],
        }
    ]
    seen = []

    def snapshot(self, ids):
        seen.append(ids)
        return items, {"fields": {"UF_MULTI": {"formLabel": "Варианты"}}}

    monkeypatch.setattr(BitrixClient, "deals_snapshot", snapshot)
    assert client.post("/api/bitrix/deals/sync").status_code == 202
    detail = client.get("/api/bitrix/deals/199719").json()
    assert detail["fields"]["UF_MULTI"] == ["a", "b"]
    assert detail["product_rows"][0]["TAX_RATE"] == 5
    assert (
        client.get("/api/bitrix/deals?category_id=2&state=open&search=Муза").json()[
            "total"
        ]
        == 1
    )
    assert client.get("/api/bitrix/deals?category_id=3").json()["total"] == 0
    items[0]["fields"]["CLOSED"] = "Y"
    client.post("/api/bitrix/deals/sync")
    assert seen == [[], [199719]]
    assert client.get("/api/bitrix/deals?state=closed").json()["total"] == 1
    assert client.get("/api/bitrix/deals?state=open").json()["total"] == 0
    items.clear()
    client.post("/api/bitrix/deals/sync")
    assert (
        client.get("/api/bitrix/deals?state=missing").json()["items"][0]["id"] == 199719
    )
    before = client.get("/api/bitrix/deals/199719").json()
    stamp = client.get("/api/bitrix/deals/status").json()["synced_at"]

    def failure(self, ids):
        raise RuntimeError("secret must not escape")

    monkeypatch.setattr(BitrixClient, "deals_snapshot", failure)
    client.post("/api/bitrix/deals/sync")
    status = client.get("/api/bitrix/deals/status").json()
    assert status["synced_at"] == stamp
    assert status["last_error"] and "secret" not in status["last_error"]
    assert client.get("/api/bitrix/deals/199719").json() == before
    client.cookies.set(SESSION_COOKIE_NAME, "worker")
    for path in ("deals", "deals/status", "deals/199719"):
        assert client.get("/api/bitrix/" + path).status_code == 403
    assert client.post("/api/bitrix/deals/sync").status_code == 403


def test_deals_shared_lock_and_stale_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Проверяем блокировку обновления:
    - запретить параллельную загрузку каталога и замену настроек
    - не публиковать результаты устаревшего задания
    """
    from app.services.bitrix_deal_service import sync_deals

    configure(client)
    factory = client.app.state.session_factory
    with factory() as session:
        old = begin_sync(session, "deals")
    assert client.post("/api/bitrix/sync").status_code == 409
    assert client.post("/api/bitrix/deals/sync").status_code == 409
    assert (
        client.put("/api/bitrix/settings", json={"webhook": WEBHOOK}).status_code == 409
    )
    with factory() as session:
        session.get(BitrixConnection, 1).started_at = now_ms() - LEASE_MS - 1
        session.commit()
        new = begin_sync(session, "deals")
    monkeypatch.setattr(BitrixClient, "deals_snapshot", lambda self, ids: ([], {}))
    sync_deals(factory, old)
    assert client.get("/api/bitrix/deals/status").json()["synced_at"] is None
    sync_deals(factory, new)
    assert client.get("/api/bitrix/deals/status").json()["synced_at"] is not None


def test_sync_progress_visible_on_both_tabs_and_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """
    Проверяем наблюдаемость загрузки:
    - показать один этап и счётчики на обеих вкладках через API
    - записать прогресс в журнал без вебхука
    - отклонить обновление прогресса устаревшим заданием
    """
    from app.services.bitrix_progress import SyncProgress
    from app.services.bitrix_client import BitrixError

    configure(client)
    factory = client.app.state.session_factory
    with factory() as session:
        job = begin_sync(session, "deals")
    progress = SyncProgress(factory, job, "deals")
    progress.report("Загрузка карточек и товаров сделок", 25, 100)
    for path in ("settings", "deals/status"):
        status = client.get("/api/bitrix/" + path).json()
        assert status["syncing"] is True
        assert status["progress"]["completed"] == 25
        assert status["progress"]["total"] == 100
        assert status["progress"]["kind"] == "deals"
    assert "completed=25 total=100" in caplog.text
    assert "test-secret" not in caplog.text
    with factory() as session:
        session.get(BitrixConnection, 1).started_at = now_ms() - LEASE_MS - 1
        session.commit()
        begin_sync(session, "catalog")
    with pytest.raises(BitrixError):
        progress.report("Устаревшее обновление", 50, 100)
    assert client.get("/api/bitrix/settings").json()["progress"]["kind"] == "catalog"


def test_mapping_requirement_persists_and_excludes_existing_links(
    client: TestClient, snapshot: list[dict]
) -> None:
    """
    Проверяем статус изделия без сопоставления:
    - сохранить статус и сохранить его при обновлении каталога
    - запретить одновременное наличие статуса и сопоставлений
    - снять статус и разрешить назначение товара
    """
    configure(client)
    client.post("/api/bitrix/sync")
    path = "/api/bitrix/mappings/1/requirement"
    assert client.put(path, json={"not_required": True}).status_code == 200
    client.post("/api/bitrix/sync")
    product = next(
        item
        for item in client.get("/api/bitrix/catalog").json()["products"]
        if item["id"] == 1
    )
    assert product["mapping_not_required"] is True
    assert (
        client.put("/api/bitrix/mappings/1", json={"bitrix_ids": [655]}).status_code
        == 409
    )
    assert client.put(path, json={"not_required": False}).status_code == 200
    assert (
        client.put("/api/bitrix/mappings/1", json={"bitrix_ids": [655]}).status_code
        == 200
    )
    assert client.put(path, json={"not_required": True}).status_code == 409
    assert (
        client.put(
            "/api/bitrix/mappings/3/requirement", json={"not_required": True}
        ).status_code
        == 409
    )
    client.cookies.set(SESSION_COOKIE_NAME, "worker")
    assert client.put(path, json={"not_required": False}).status_code == 403


@pytest.mark.parametrize("kind", ["catalog", "deals"])
def test_cancel_preserves_snapshot_and_blocks_old_publication(
    client: TestClient, snapshot: list[dict], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """
    Проверяем ручное прерывание загрузки:
    - отменить задание и сохранить предыдущие данные
    - запретить отменённому заданию опубликовать результат или изменить новое задание
    - разрешить отмену только администратору
    """
    from app.services.bitrix_deal_service import sync_deals
    from app.services.bitrix_progress import SyncProgress, SyncCancelled

    configure(client)
    client.post("/api/bitrix/sync")
    before = client.get("/api/bitrix/catalog").json()
    factory = client.app.state.session_factory
    with factory() as session:
        job = begin_sync(session, kind)
    client.cookies.set(SESSION_COOKIE_NAME, "worker")
    assert (
        client.post("/api/bitrix/sync/cancel", json={"job_id": job}).status_code == 403
    )
    client.cookies.set(SESSION_COOKIE_NAME, "admin")
    assert (
        client.post("/api/bitrix/sync/cancel", json={"job_id": job}).status_code == 200
    )
    status_path = (
        "/api/bitrix/deals/status" if kind == "deals" else "/api/bitrix/settings"
    )
    status = client.get(status_path).json()
    assert status["syncing"] is False
    assert status["job_id"] is None
    assert "администратором" in status["last_error"]
    with pytest.raises(SyncCancelled):
        SyncProgress(factory, job, kind).heartbeat()
    with factory() as session:
        new_job = begin_sync(session, kind)
    assert (
        client.post("/api/bitrix/sync/cancel", json={"job_id": job}).status_code == 409
    )
    (sync_deals if kind == "deals" else sync_catalog)(factory, job)
    assert client.get(status_path).json()["job_id"] == new_job
    assert client.get("/api/bitrix/catalog").json() == before


def test_startup_releases_interrupted_job(client: TestClient) -> None:
    """
    Проверяем перезапуск backend:
    - оставить активное задание в БД перед запуском приложения
    - снять блокировку при запуске и сообщить причину прерывания
    - разрешить повторную загрузку сразу
    """
    configure(client)
    factory = client.app.state.session_factory
    with factory() as session:
        begin_sync(session, "deals")
    restarted = create_application()
    restarted.state.session_factory = factory
    with TestClient(restarted):
        status = client.get("/api/bitrix/deals/status").json()
        assert status["syncing"] is False
        assert status["progress"] is None
        assert "перезапуском" in status["last_error"]
        with factory() as session:
            assert begin_sync(session, "deals")


def test_cancel_during_download_does_not_publish_partial_result(
    client: TestClient, snapshot: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Проверяем отмену выполняющегося запроса:
    - отменить задание между получением данных и публикацией
    - сохранить предыдущий каталог и сообщение об отмене
    """
    from app.services.bitrix_service import stop_sync

    configure(client)
    client.post("/api/bitrix/sync")
    before = client.get("/api/bitrix/catalog").json()
    factory = client.app.state.session_factory
    with factory() as session:
        job = begin_sync(session)

    def downloaded(self):
        with factory() as session:
            stop_sync(session, job, "Отменено")
        return [], {}

    monkeypatch.setattr(BitrixClient, "snapshot", downloaded)
    sync_catalog(factory, job)
    assert client.get("/api/bitrix/catalog").json() == before
    assert client.get("/api/bitrix/settings").json()["last_error"] == "Отменено"
