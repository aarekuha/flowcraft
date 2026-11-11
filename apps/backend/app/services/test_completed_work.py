from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_authenticated_session, get_session
from app.api.routes.completed_work import router
from app.core.database import Base
from app.models.bonus import Bonus, UserBonus
from app.models.operation import Operation
from app.models.planning import UserWorkScheduleDay
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderTimeAllocation
from app.models.work_shift import WorkShift
from app.services.completed_work_service import MOSCOW, CompletedWorkService
from app.services.work_summary_service import WorkSummaryService


def timestamp(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=MOSCOW).timestamp() * 1000)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                User(
                    id=i,
                    name=f"Сотрудник {i}",
                    phone=str(i),
                    roles=["worker"],
                    created_at=1,
                    updated_at=1,
                )
                for i in (1, 2)
            ]
        )
        db.add(Product(id=1, name="Изделие", version="2", author="Admin", created_at=1))
        db.flush()
        db.add_all(
            [
                Operation(id=1, product_id=1, name="Покраска", price_cents=1),
                Operation(id=2, product_id=1, name="Подготовка", price_cents=200),
            ]
        )
        db.add_all(
            [
                WorkShift(
                    id=i,
                    user_id=i,
                    business_date="2026-10-31",
                    started_at=1,
                    ended_at=100,
                    created_at=1,
                )
                for i in (1, 2)
            ]
        )
        for i, completed in enumerate(
            ["2026-11-01", "2026-11-30T23:59:59", "2026-12-01", "2026-10-31T23:59:59"],
            1,
        ):
            db.add(
                WorkOrder(
                    id=i,
                    order_number=f"962{i}",
                    product_id=1,
                    quantity=101 if i == 1 else 10,
                    defect_quantity=1 if i == 1 else 0,
                    completed_at=timestamp(completed),
                    created_at=1,
                    updated_at=1,
                )
            )
        db.flush()
        for i, order_id, op_id, user_id, duration in [
            (1, 1, 1, 1, 1000),
            (2, 1, 1, 2, 2000),
            (3, 1, 2, 1, 1000),
            (4, 2, 1, 1, 1000),
            (5, 3, 1, 1, 1000),
            (6, 4, 1, 1, 1000),
        ]:
            db.add(
                TimerSession(
                    id=i,
                    shift_id=user_id,
                    user_id=user_id,
                    order_id=order_id,
                    operation_id=op_id,
                    timer_type_code=2,
                    started_at=timestamp("2026-10-31") + i * 10000,
                    ended_at=timestamp("2026-10-31") + i * 10000 + duration,
                    created_at=1,
                )
            )
        for day, kind, seconds in [
            (1, "work", 28800),
            (2, "work", 14400),
            (3, "sick_leave", 0),
            (4, "vacation", 0),
            (5, "absence", 0),
        ]:
            db.add(
                UserWorkScheduleDay(
                    user_id=1,
                    work_date=date(2026, 11, day),
                    period_type=kind,
                    available_seconds=seconds,
                    updated_at=1,
                )
            )
        db.add(Bonus(id=1, name="Качество", amount_cents=12345))
        db.flush()
        db.add(UserBonus(user_id=1, bonus_id=1))
        db.commit()
        yield db
    engine.dispose()


@pytest.fixture()
def api(session: Session) -> Iterator[tuple[TestClient, FastAPI]]:
    app = FastAPI()
    app.include_router(router, prefix="/api/admin")
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_authenticated_session] = lambda: SimpleNamespace(
        user_roles=["admin"]
    )
    with TestClient(app) as client:
        yield client, app


def test_work_shares_rounding_schedule_and_month_boundaries(session: Session) -> None:
    """
    Проверяем расчёт изделий и выплаты за месяц:
    - учитывать брак, доли исполнителей и время до начала месяца
    - исключать заказы за границами месяца и суммировать максимумы по заказам
    - раздельно показывать рабочие дни, часы и отсутствия
    """
    report = CompletedWorkService(session).calculate(1, 2026, 11)
    assert [(row.order_number, row.operation_name) for row in report.items] == [
        ("9621", "Подготовка"),
        ("9621", "Покраска"),
        ("9622", "Покраска"),
    ]
    assert [row.quantity for row in report.items] == [
        Decimal("100.00"),
        Decimal("33.34"),
        Decimal("10.00"),
    ]
    assert [row.amount_cents for row in report.items] == [20000, 34, 10]
    assert report.total_quantity == Decimal("110.00")
    assert report.piecework_cents == 20044
    assert report.payout_cents == 32389
    assert (report.work_days, report.work_hours) == (2, Decimal(12))
    assert (report.sick_days, report.vacation_days, report.absence_days) == (1, 1, 1)


def test_order_allocations_replace_original_timer_link(session: Session) -> None:
    """
    Проверяем время после разделения заказа:
    - перенести долю таймера на другую часть заказа через распределение
    - исключить исходную связь из количества и начисления сотрудника
    """
    session.add(
        WorkOrderTimeAllocation(
            timer_session_id=1,
            work_order_id=2,
            allocated_seconds=1,
            created_at=1,
            updated_at=1,
        )
    )
    session.commit()
    report = CompletedWorkService(session).calculate(1, 2026, 11)
    assert [(row.order_number, row.operation_name) for row in report.items] == [
        ("9621", "Подготовка"),
        ("9622", "Покраска"),
    ]
    assert report.total_quantity == Decimal("110.00")
    assert report.piecework_cents == 20010


def test_current_prices_and_bonuses_are_recalculated(session: Session) -> None:
    """
    Проверяем пересчёт по актуальному справочнику:
    - изменить стоимость операции и размер назначенной премии
    - получить новые начисления при повторном открытии месяца
    """
    service = CompletedWorkService(session)
    previous = service.calculate(1, 2026, 11)
    operation = session.get(Operation, 2)
    bonus = session.get(Bonus, 1)
    assert operation and bonus
    operation.price_cents = 300
    bonus.amount_cents = 100
    session.commit()
    report = service.calculate(1, 2026, 11)
    assert previous.piecework_cents is not None
    assert report.piecework_cents == previous.piecework_cents + 10000
    assert report.bonuses_cents == 100
    assert report.payout_cents == 30144


def test_missing_price_keeps_partial_totals_and_exports(session: Session) -> None:
    """
    Проверяем итоги при отсутствии расценки:
    - сохранить количества и признак нерассчитанных строк
    - сложить рассчитанные позиции и премии, учитывая остальные как ноль
    - разрешить персональную и общую выгрузку XLSX
    """
    operation = session.get(Operation, 1)
    assert operation
    operation.price_cents = None
    session.commit()
    service = CompletedWorkService(session)
    report = service.calculate(1, 2026, 11)
    assert report.total_quantity == 110
    assert any(row.amount_cents is None for row in report.items)
    assert report.piecework_cents == 20000
    assert report.payout_cents == 32345
    summary = WorkSummaryService(session).calculate(2026, 11)
    assert all(row.incomplete for row in summary.items)
    assert [row.piecework_cents for row in summary.items] == [20000, 0]
    for data in [
        service.export(1, 2026, 11), WorkSummaryService(session).export(2026, 11)
    ]:
        with ZipFile(BytesIO(data)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            assert sheet.findall(".//s:f", ns)
    with ZipFile(BytesIO(service.export(1, 2026, 11))) as archive:
        assert "Не рассчитано" in archive.read("xl/worksheets/sheet1.xml").decode()


def test_xlsx_contains_literal_totals_and_linked_payout_formula(
    session: Session,
) -> None:
    """
    Проверяем редактируемую выгрузку:
    - премии и сделку сохранять числовыми значениями
    - выплату рассчитывать единственной формулой со ссылками на эти поля
    """
    data = CompletedWorkService(session).export(1, 2026, 11)
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(BytesIO(data)) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        cells = {cell.attrib["r"]: cell for cell in sheet.findall(".//s:c", namespace)}
        formulas = sheet.findall(".//s:f", namespace)
        assert len(formulas) == 1
        assert formulas[0].text is not None
        bonus_ref, work_ref = formulas[0].text.split("+")
        assert cells[bonus_ref].find("s:f", namespace) is None
        assert cells[work_ref].find("s:f", namespace) is None
        assert Decimal(
            cells[bonus_ref].findtext("s:v", default="", namespaces=namespace)
        ) == Decimal("123.45")
        assert Decimal(
            cells[work_ref].findtext("s:v", default="", namespaces=namespace)
        ) == Decimal("200.44")
        assert "Качество" in archive.read("xl/worksheets/sheet1.xml").decode()


def test_bonus_directory_assignment_validation_and_deletion(
    api: tuple[TestClient, FastAPI],
) -> None:
    """
    Проверяем управление премиями через API:
    - создать премию и назначить сотруднику без повторных начислений
    - отклонить неизвестные назначения без потери предыдущих
    - удалить премию вместе с назначениями
    """
    client, _ = api
    response = client.post(
        "/api/admin/bonuses", json={"name": " Премия ", "amount_cents": 123}
    )
    assert response.status_code == 201
    bonus_id = response.json()["id"]
    assert response.json()["name"] == "Премия"
    response = client.put(
        "/api/admin/users/1/bonuses", json={"bonus_ids": [bonus_id, bonus_id]}
    )
    assert response.status_code == 200 and len(response.json()) == 1
    assert (
        client.put("/api/admin/users/1/bonuses", json={"bonus_ids": [9999]}).status_code
        == 422
    )
    assert client.get("/api/admin/users/1/bonuses").json()[0]["id"] == bonus_id
    assert (
        client.put(
            f"/api/admin/bonuses/{bonus_id}",
            json={"name": "Новая", "amount_cents": 456},
        ).status_code
        == 200
    )
    assert (
        client.get("/api/admin/users/1/completed-work?year=2026&month=11").json()[
            "bonuses_cents"
        ]
        == 456
    )
    assert client.delete(f"/api/admin/bonuses/{bonus_id}").status_code == 204
    assert client.get("/api/admin/users/1/bonuses").json() == []
    assert (
        client.post(
            "/api/admin/bonuses", json={"name": " ", "amount_cents": 0}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/admin/bonuses", json={"name": "Премия", "amount_cents": -1}
        ).status_code
        == 422
    )
    assert (
        client.get("/api/admin/users/1/completed-work?year=2026&month=13").status_code
        == 422
    )
    assert (
        client.get("/api/admin/users/999/completed-work?year=2026&month=11").status_code
        == 404
    )


@pytest.mark.parametrize(
    "role", ["worker", "brigadier", "constructor", "quality_control", "reports"]
)
def test_non_admin_cannot_access_bonus_or_calculation(
    api: tuple[TestClient, FastAPI],
    role: str,
) -> None:
    """
    Проверяем ограничение доступа на сервере:
    - роль без администратора не получает премии, расчёт или XLSX
    - изменение справочника и назначений также запрещено
    """
    client, app = api
    app.dependency_overrides[get_authenticated_session] = lambda: SimpleNamespace(
        user_roles=[role]
    )
    requests: list[tuple[str, str, dict[str, Any] | None]] = [
        ("GET", "/bonuses", None),
        ("GET", "/completed-work-summary?year=2026&month=11", None),
        ("GET", "/completed-work-summary.xlsx?year=2026&month=11", None),
        ("POST", "/bonuses", {"name": "X", "amount_cents": 1}),
        ("PUT", "/bonuses/1", {"name": "X", "amount_cents": 1}),
        ("DELETE", "/bonuses/1", None),
        ("GET", "/users/1/bonuses", None),
        ("PUT", "/users/1/bonuses", {"bonus_ids": []}),
        (
            "PUT",
            "/users/1/completed-work/bonuses/1?year=2026&month=11",
            {"selected": False},
        ),
        (
            "PUT", "/users/1/completed-work/piecework?year=2026&month=11",
            {"amount_cents": 0},
        ),
        ("GET", "/users/1/completed-work?year=2026&month=11", None),
        ("GET", "/users/1/completed-work.xlsx?year=2026&month=11", None),
    ]
    for method, path, payload in requests:
        assert (
            client.request(method, f"/api/admin{path}", json=payload).status_code == 403
        )


def test_monthly_bonus_selection_is_persisted_and_scoped(
    api: tuple[TestClient, FastAPI],
    session: Session,
) -> None:
    """
    Проверяем сохранение отменённой премии на месяц:
    - по умолчанию учитывать все назначенные премии
    - исключать премию только для выбранного сотрудника, года и месяца
    - сохранять выбор при изменении размера и повторном сохранении назначений
    """
    client, _ = api
    path = "/api/admin/users/1/completed-work"
    selection = f"{path}/bonuses/1?year=2026&month=11"
    initial = client.get(f"{path}?year=2026&month=11").json()
    assert initial["bonuses"][0]["selected"] is True
    for _ in range(2):
        response = client.put(selection, json={"selected": False})
        assert response.status_code == 200
        assert response.json()["bonuses_cents"] == 0
        assert response.json()["payout_cents"] == initial["piecework_cents"]
    session.expire_all()
    reopened = client.get(f"{path}?year=2026&month=11").json()
    assert reopened["bonuses"][0]["selected"] is False
    for year, month in [(2026, 10), (2026, 12), (2027, 11)]:
        other = client.get(f"{path}?year={year}&month={month}").json()
        assert other["bonuses"][0]["selected"] is True
        assert other["bonuses_cents"] == 12345
    assert (
        client.put("/api/admin/users/2/bonuses", json={"bonus_ids": [1]}).status_code
        == 200
    )
    other_user = client.get(
        "/api/admin/users/2/completed-work?year=2026&month=11"
    ).json()
    assert other_user["bonuses"][0]["selected"] is True
    assert (
        client.put(
            "/api/admin/bonuses/1", json={"name": "Качество", "amount_cents": 500}
        ).status_code
        == 200
    )
    assert (
        client.put("/api/admin/users/1/bonuses", json={"bonus_ids": [1]}).status_code
        == 200
    )
    assert client.get(f"{path}?year=2026&month=11").json()["bonuses_cents"] == 0
    for _ in range(2):
        restored = client.put(selection, json={"selected": True})
        assert restored.status_code == 200
        assert restored.json()["bonuses_cents"] == 500
    assert (
        client.get(f"{path}?year=2026&month=11").json()["payout_cents"]
        == initial["piecework_cents"] + 500
    )


def test_new_bonus_is_selected_and_xlsx_excludes_cancelled_bonus(
    api: tuple[TestClient, FastAPI],
) -> None:
    """
    Проверяем печать только выбранных премий:
    - отменить существующую премию и назначить новую, выбранную по умолчанию
    - выгрузить только новую премию с правильной суммой и формулой выплаты
    - после отмены всех премий печатать нулевую сумму премий
    """
    client, _ = api
    base = "/api/admin/users/1/completed-work"
    assert (
        client.put(
            f"{base}/bonuses/1?year=2026&month=11", json={"selected": False}
        ).status_code
        == 200
    )
    bonus = client.post(
        "/api/admin/bonuses", json={"name": "Новая премия", "amount_cents": 321}
    ).json()
    assert (
        client.put(
            "/api/admin/users/1/bonuses", json={"bonus_ids": [1, bonus["id"]]}
        ).status_code
        == 200
    )
    report = client.get(f"{base}?year=2026&month=11").json()
    assert report["bonuses_cents"] == 321
    assert {item["id"]: item["selected"] for item in report["bonuses"]} == {
        1: False,
        bonus["id"]: True,
    }
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    for selected, expected in [(True, "3.21"), (False, "0")]:
        assert (
            client.put(
                f"{base}/bonuses/{bonus['id']}?year=2026&month=11",
                json={"selected": selected},
            ).status_code
            == 200
        )
        response = client.get(f"{base}.xlsx?year=2026&month=11")
        assert response.status_code == 200
        with ZipFile(BytesIO(response.content)) as archive:
            xml = archive.read("xl/worksheets/sheet1.xml")
            assert "Качество" not in xml.decode()
            assert ("Новая премия" in xml.decode()) == selected
            sheet = ET.fromstring(xml)
            cells = {
                cell.attrib["r"]: cell for cell in sheet.findall(".//s:c", namespace)
            }
            formula = sheet.find(".//s:f", namespace)
            assert formula is not None and formula.text is not None
            bonus_ref, _ = formula.text.split("+")
            assert Decimal(
                cells[bonus_ref].findtext("s:v", default="", namespaces=namespace)
            ) == Decimal(expected)


def test_monthly_selection_rejects_invalid_bonus_and_period_and_allows_deletion(
    api: tuple[TestClient, FastAPI],
) -> None:
    """
    Проверяем границы изменения выбора премий:
    - отклонить неназначенную премию и недопустимые значения месяца, года и выбора
    - после удаления отменённой премии сохранить работоспособность расчёта
    """
    client, _ = api
    base = "/api/admin/users/1/completed-work/bonuses"
    assert (
        client.put(
            f"{base}/999?year=2026&month=11", json={"selected": False}
        ).status_code
        == 404
    )
    for query in ["year=2026&month=0", "year=2026&month=13", "year=1999&month=11"]:
        assert (
            client.put(f"{base}/1?{query}", json={"selected": False}).status_code == 422
        )
    assert (
        client.put(
            f"{base}/1?year=2026&month=11", json={"selected": "false"}
        ).status_code
        == 422
    )
    assert (
        client.put(f"{base}/1?year=2026&month=11", json={"selected": False}).status_code
        == 200
    )
    assert client.delete("/api/admin/bonuses/1").status_code == 204
    report = client.get("/api/admin/users/1/completed-work?year=2026&month=11").json()
    assert report["bonuses"] == []
    assert report["bonuses_cents"] == 0


def test_summary_includes_current_users_and_selected_month_bonuses(
    api: tuple[TestClient, FastAPI],
    session: Session,
) -> None:
    """
    Проверяем общий расчёт для текущих сотрудников:
    - включить активного сотрудника без времени, исключить неактивного и удалённого
    - учитывать отмену премии только в выбранном месяце
    - получить те же суммы, что в индивидуальном расчёте
    """
    client, _ = api
    for user_id, active, deleted in [(3, True, None), (4, False, None), (5, True, 1)]:
        session.add(
            User(
                id=user_id,
                name=f"Сотрудник {user_id}",
                phone=str(user_id),
                roles=["admin"],
                is_active=active,
                deleted_at=deleted,
                created_at=1,
                updated_at=1,
            )
        )
    session.commit()
    CompletedWorkService(session).set_bonus_selection(1, 2026, 11, 1, selected=False)
    response = client.get("/api/admin/completed-work-summary?year=2026&month=11")
    assert response.status_code == 200
    rows = response.json()["items"]
    assert [row["user_id"] for row in rows] == [1, 2, 3]
    assert rows[0]["bonuses_cents"] == 0
    assert rows[2]["piecework_cents"] == 0
    for row in rows:
        personal = CompletedWorkService(session).calculate(row["user_id"], 2026, 11)
        assert row["piecework_cents"] == personal.piecework_cents
        assert row["bonuses_cents"] == personal.bonuses_cents
    previous = client.get("/api/admin/completed-work-summary?year=2026&month=10").json()
    assert previous["items"][0]["bonuses_cents"] == 12345


def test_summary_xlsx_blank_absences_and_gray_formula_totals(
    api: tuple[TestClient, FastAPI],
) -> None:
    """
    Проверяем формат общей выгрузки:
    - оставлять пустые ячейки при отсутствии больничных и отпуска
    - суммировать сделку и премии формулами по всем сотрудникам
    - окрашивать всю строку ИТОГО светло-серым фоном
    """
    client, _ = api
    response = client.get("/api/admin/completed-work-summary.xlsx?year=2026&month=11")
    assert response.status_code == 200
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(BytesIO(response.content)) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        cells = {cell.attrib["r"]: cell for cell in sheet.findall(".//s:c", ns)}
        assert cells["B2"].findtext("s:v", namespaces=ns) == "1"
        assert cells["C2"].findtext("s:v", namespaces=ns) == "1"
        assert cells["B3"].find("s:v", ns) is None
        assert cells["C3"].find("s:v", ns) is None
        assert cells["A4"].findtext("s:is/s:t", namespaces=ns) == "ИТОГО"
        assert cells["D4"].findtext("s:f", namespaces=ns) == "SUM(D2:D3)"
        assert cells["E4"].findtext("s:f", namespaces=ns) == "SUM(E2:E3)"
        assert Decimal(
            cells["D4"].findtext("s:v", default="", namespaces=ns)
        ) == Decimal("201.11")
        assert Decimal(
            cells["E4"].findtext("s:v", default="", namespaces=ns)
        ) == Decimal("123.45")
        formats = styles.findall("s:cellXfs/s:xf", ns)
        fills = styles.findall("s:fills/s:fill", ns)
        for column in "ABCDE":
            fmt = formats[int(cells[f"{column}4"].attrib["s"])]
            color = fills[int(fmt.attrib["fillId"])].find("s:patternFill/s:fgColor", ns)
            assert color is not None and color.attrib["rgb"] == "FFE5E7EB"


def test_empty_summary_exports_zero_formulas_without_self_reference(
    session: Session,
) -> None:
    """
    Проверяем выгрузку без текущих сотрудников:
    - исключить всех сотрудников из текущего состава
    - получить пустой отчёт и нулевые формулы без циклических ссылок
    """
    for user_id in (1, 2):
        user = session.get(User, user_id)
        assert user is not None
        user.is_active = False
    session.commit()
    service = WorkSummaryService(session)
    assert service.calculate(2026, 11).items == []
    with ZipFile(BytesIO(service.export(2026, 11))) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        assert [formula.text for formula in sheet.findall(".//s:f", ns)] == [
            "SUM(0)",
            "SUM(0)",
        ]


def test_manual_piecework_persistence_scope_reset_and_exports(
    api: tuple[TestClient, FastAPI], session: Session,
) -> None:
    """
    Проверяем ручную сделку сотрудника за месяц:
    - сохранить округлённую сумму независимо от системного расчёта и других месяцев
    - использовать её в выплате и обеих выгрузках, сохранив итог таблицы
    - сохранить ноль и вернуть актуальный системный расчёт после сброса
    """
    client, _ = api
    url = "/api/admin/users/1/completed-work/piecework?year=2026&month=11"
    response = client.put(url, json={"amount_cents": 21000})
    assert response.status_code == 200
    assert response.json()["piecework_cents"] == 20044
    assert response.json()["payable_piecework_cents"] == 21000
    assert response.json()["payout_cents"] == 33345
    service = CompletedWorkService(session)
    session.expire_all()
    assert service.calculate(1, 2026, 11).manual_piecework_cents == 21000
    assert service.calculate(1, 2026, 10).manual_piecework_cents is None
    assert service.calculate(2, 2026, 11).manual_piecework_cents is None
    operation = session.get(Operation, 2)
    assert operation is not None
    operation.price_cents = 300
    session.commit()
    report = service.calculate(1, 2026, 11)
    assert report.piecework_cents == 30044
    assert report.payable_piecework_cents == 21000
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    for data, expected in [
        (service.export(1, 2026, 11), 333.45),
        (WorkSummaryService(session).export(2026, 11), 210.67),
    ]:
        with ZipFile(BytesIO(data)) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            calculated = []
            for cell in sheet.findall(".//s:c", ns):
                if cell.find("s:f", ns) is not None:
                    value = cell.findtext("s:v", namespaces=ns)
                    assert value is not None
                    calculated.append(float(value))
            assert expected in calculated
    zero = client.put(url, json={"amount_cents": 0}).json()
    assert zero["manual_piecework_cents"] == 0
    assert zero["payable_piecework_cents"] == 0
    assert zero["payout_cents"] == 12345
    reset = client.put(url, json={"amount_cents": None}).json()
    assert reset["manual_piecework_cents"] is None
    assert reset["payable_piecework_cents"] == 30044
    assert reset["payout_cents"] == 42389


@pytest.mark.parametrize("amount", [-1, 1.5, True, "100"])
def test_manual_piecework_rejects_invalid_amount(
    api: tuple[TestClient, FastAPI], amount: Any,
) -> None:
    """
    Проверяем валидацию ручной суммы:
    - отклонить отрицательные и нецелые копейки, строки и логические значения
    - сохранить системный расчёт без ручного переопределения
    """
    client, _ = api
    response = client.put(
        "/api/admin/users/1/completed-work/piecework?year=2026&month=11",
        json={"amount_cents": amount},
    )
    assert response.status_code == 422
    report = client.get("/api/admin/users/1/completed-work?year=2026&month=11").json()
    assert report["manual_piecework_cents"] is None
