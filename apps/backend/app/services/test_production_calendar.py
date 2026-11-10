from calendar import monthrange
from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.production_calendar import CalendarImport
from app.models.user import User
from app.services import production_calendar_service as calendar_service
from app.services.production_calendar_service import (
    ProductionCalendarService,
    parse_calendar_year,
)


@pytest.fixture()
def calendar_session() -> Iterator[Session]:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            User(
                id=1,
                name="Calendar fixture",
                phone="calendar-fixture",
                roles=["admin"],
                is_active=True,
                created_at=1,
                updated_at=1,
            )
        )
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture()
def calendar_source(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict]:
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "FixedDatetime":
            return cls(2026, 11, 10, 12, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(calendar_service, "datetime", FixedDatetime)
    payloads: dict[str, dict] = {"": {"status": 200, "years": [2025, 2026, 2027, 2028]}}
    for year in (2025, 2026, 2027, 2028):
        holidays = {date(year, 1, 1), date(year, 11, 4)}
        shortened = {date(year, 11, 3)} if date(year, 11, 3).weekday() < 5 else set()
        saturday = next(
            date(year, 2, day)
            for day in range(1, 8)
            if date(year, 2, day).weekday() == 5
        )
        monday = date(year, 2, saturday.day + 2)
        months = []
        for month in range(1, 13):
            dates = [
                date(year, month, day)
                for day in range(1, monthrange(year, month)[1] + 1)
            ]
            working = sum(
                (d.weekday() < 5 or d == saturday) and d not in holidays and d != monday
                for d in dates
            )
            short = sum(d in shortened for d in dates)
            months.append(
                {
                    "id": month - 1,
                    "workingDays": working,
                    "notWorkingDays": len(dates) - working,
                    "shortDays": short,
                    "workingHours": working * 8 - short,
                }
            )
        payloads[f"/{year}"] = {
            "status": 200,
            "year": year,
            "months": months,
            "decree": {"title": "Искусственные данные для теста"},
        }
        payloads[f"/{year}/holidays"] = {
            "status": 200,
            "year": year,
            "decree": {"title": "Искусственные данные для теста"},
            "holidays": [
                {"date": f"{d}T00:00:00.000Z", "name": "Праздник"}
                for d in sorted(holidays)
            ],
            "shortDays": [
                {"date": f"{d}T00:00:00.000Z", "name": "Сокращённый"}
                for d in sorted(shortened)
            ],
            "transferredHolidays": [
                {
                    "date": f"{monday}T00:00:00.000Z",
                    "name": "Перенос",
                    "from": f"{saturday}T00:00:00.000Z",
                }
            ],
            "workingWeekends": [
                {"date": f"{saturday}T00:00:00.000Z", "name": "Рабочая суббота"}
            ],
        }
    monkeypatch.setattr(
        calendar_service,
        "fetch_calendar_json",
        lambda suffix="": deepcopy(payloads[suffix]),
    )
    return payloads


def test_refresh_stores_years_and_monthly_totals(
    calendar_session: Session,
    calendar_source: dict[str, dict],
) -> None:
    """
    Проверяем загрузку календаря на искусственных данных:
    - сохранить текущий и будущие годы, пропустить прошлый год
    - вернуть месячные итоги и признаки праздника и сокращённого дня
    - сохранить режим недели и исходные ответы для будущих расчётов
    """
    service = ProductionCalendarService(calendar_session)
    assert service.get_status().imported_at is None
    assert service.get_month(2026, 11) is None
    result = service.refresh(1)
    assert result.years == [2026, 2027, 2028]
    assert result.imported_at is not None
    month = service.get_month(2026, 11)
    assert month is not None
    assert month.week_days == 5 and month.week_hours == 40
    assert month.summary.working_days == 20
    assert month.summary.working_hours == 159
    assert month.summary.shortened_days == 1
    assert month.summary.holiday_days == 1
    assert month.days[2].is_shortened and month.days[2].is_working
    assert month.days[3].is_holiday and not month.days[3].is_working
    leap = service.get_month(2028, 2)
    assert leap is not None and leap.summary.calendar_days == 29
    imported = calendar_session.scalar(select(CalendarImport))
    assert imported is not None
    assert imported.payload["2026"]["calendar"] == calendar_source["/2026"]


def test_refresh_preserves_other_years_and_history(
    calendar_session: Session,
    calendar_source: dict[str, dict],
) -> None:
    """
    Проверяем повторную актуализацию:
    - сохранить годы, исчезнувшие из списка источника
    - обновить название праздника без повторяющихся дат
    - сохранить предыдущий исходный снимок
    """
    service = ProductionCalendarService(calendar_session)
    service.refresh(1)
    calendar_source[""]["years"] = [2026, 2027]
    calendar_source["/2026/holidays"]["holidays"][0]["name"] = "Новое название"
    service.refresh(1)
    assert service.get_status().years == [2026, 2027, 2028]
    january = service.get_month(2026, 1)
    assert january is not None and len(january.days) == 31
    assert january.days[0].name == "Новое название"
    snapshots = calendar_session.scalars(
        select(CalendarImport).order_by(CalendarImport.id)
    ).all()
    assert len(snapshots) == 2
    assert snapshots[0].payload["2026"]["holidays"]["holidays"][0]["name"] == "Праздник"


@pytest.mark.parametrize(
    "problem", ["network", "totals", "missing_month", "wrong_year", "commit"]
)
def test_failed_refresh_preserves_saved_data(
    calendar_session: Session,
    calendar_source: dict[str, dict],
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    """
    Проверяем атомарность актуализации на искусственных данных:
    - испортить ответ будущего года, соединение или фиксацию транзакции
    - сохранить прежние даты, месячные показатели и время актуализации
    """
    service = ProductionCalendarService(calendar_session)
    before = service.refresh(1)
    previous = service.get_month(2026, 1)
    calendar_source["/2026/holidays"]["holidays"][0]["name"] = "Не сохранять"
    if problem == "network":

        def fail(suffix: str = "") -> dict:
            raise TimeoutError()

        monkeypatch.setattr(calendar_service, "fetch_calendar_json", fail)
    elif problem == "totals":
        calendar_source["/2027"]["months"][0]["workingDays"] += 1
    elif problem == "missing_month":
        calendar_source["/2027"]["months"].pop()
    elif problem == "commit":

        def fail_commit() -> None:
            raise SQLAlchemyError("Artificial commit failure")

        monkeypatch.setattr(calendar_session, "commit", fail_commit)
    else:
        calendar_source["/2027"]["year"] = 2026
    with pytest.raises(HTTPException) as error:
        service.refresh(1)
    assert error.value.status_code == (409 if problem == "commit" else 502)
    assert service.get_status() == before
    assert service.get_month(2026, 1) == previous
    assert len(calendar_session.scalars(select(CalendarImport)).all()) == 1


def test_transfers_and_working_weekends_keep_distinct_types(
    calendar_source: dict[str, dict],
) -> None:
    """
    Проверяем переносы на искусственном календаре:
    - сохранить рабочую субботу и нерабочий понедельник
    - сохранить исходную дату переноса отдельно от признака праздника
    """
    days, _ = parse_calendar_year(
        2026, calendar_source["/2026"], calendar_source["/2026/holidays"]
    )
    by_date = {day.calendar_date: day for day in days}
    saturday = by_date[date(2026, 2, 7)]
    monday = by_date[date(2026, 2, 9)]
    assert saturday.is_working and saturday.kind == "working_weekend"
    assert not monday.is_working and not monday.is_holiday
    assert monday.transferred_from == saturday.calendar_date
