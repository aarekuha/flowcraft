import json
import logging
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from urllib.error import URLError
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.production_calendar import (
    CalendarDay,
    CalendarImport,
    CalendarMonth,
    CalendarYear,
)
from app.schemas.production_calendar import (
    CalendarDayRead,
    CalendarMonthDetail,
    CalendarMonthRead,
    CalendarStatusRead,
)

SOURCE = "https://calendar.kuzyak.in/api/calendar"
logger = logging.getLogger(__name__)


class SourceYears(BaseModel):
    status: Literal[200]
    years: list[int] = Field(min_length=1, max_length=200)


class SourceMonth(BaseModel):
    id: int = Field(ge=0, le=11, strict=True)
    workingDays: int = Field(ge=0, le=31, strict=True)
    notWorkingDays: int = Field(ge=0, le=31, strict=True)
    shortDays: int = Field(ge=0, le=31, strict=True)
    workingHours: int = Field(ge=0, le=248, strict=True)


class SourceYear(BaseModel):
    status: Literal[200]
    year: int
    months: list[SourceMonth] = Field(min_length=12, max_length=12)
    decree: dict


class SourceDay(BaseModel):
    date: datetime
    name: str = Field(min_length=1, max_length=500)
    from_date: datetime | None = Field(default=None, alias="from")


class SourceHolidays(BaseModel):
    status: Literal[200]
    year: int
    holidays: list[SourceDay]
    shortDays: list[SourceDay]
    transferredHolidays: list[SourceDay]
    workingWeekends: list[SourceDay]
    decree: dict


def fetch_calendar_json(suffix: str = "") -> dict:
    with urlopen(SOURCE + suffix, timeout=15) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("Calendar response is too large")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Expected a calendar object")
    return value


def parse_calendar_year(
    year: int,
    raw_year: dict,
    raw_holidays: dict,
) -> tuple[list[CalendarDay], list[CalendarMonth]]:
    annual = SourceYear.model_validate(raw_year)
    special = SourceHolidays.model_validate(raw_holidays)
    if annual.year != year or special.year != year:
        raise ValueError("Calendar year does not match the request")
    if annual.decree != special.decree:
        raise ValueError("Calendar documents differ between responses")
    if {month.id for month in annual.months} != set(range(12)):
        raise ValueError("Expected twelve distinct months")
    indexes: list[dict[date, SourceDay]] = []
    for items in (
        special.holidays,
        special.shortDays,
        special.transferredHolidays,
        special.workingWeekends,
    ):
        index: dict[date, SourceDay] = {}
        for item in items:
            day = item.date.date()
            if day.year != year or day in index:
                raise ValueError("Invalid or repeated calendar date")
            index[day] = item
        indexes.append(index)
    holidays, short, transfers, working_weekends = indexes
    if set(holidays) & (set(short) | set(transfers) | set(working_weekends)):
        raise ValueError("Holiday conflicts with another day type")
    if set(transfers) & (set(short) | set(working_weekends)):
        raise ValueError("Transferred day conflicts with a working day")
    if any(day.weekday() < 5 for day in working_weekends):
        raise ValueError("Working weekend must fall on a weekend")
    days: list[CalendarDay] = []
    day = date(year, 1, 1)
    while day.year == year:
        is_working = day.weekday() < 5 or day in working_weekends
        is_working = is_working and day not in holidays and day not in transfers
        if day in short and not is_working:
            raise ValueError("Shortened day must be a working day")
        kind = "work" if is_working else "weekend"
        event = None
        for index, label in (
            (working_weekends, "working_weekend"),
            (short, "shortened"),
            (transfers, "transferred"),
            (holidays, "holiday"),
        ):
            if day in index:
                event = index[day]
                kind = label
        days.append(
            CalendarDay(
                calendar_date=day,
                year=year,
                kind=kind,
                is_working=is_working,
                is_holiday=day in holidays,
                is_shortened=day in short,
                name=event.name if event else None,
                transferred_from=(
                    event.from_date.date() if event and event.from_date else None
                ),
            )
        )
        day += timedelta(days=1)
    months: list[CalendarMonth] = []
    for month in annual.months:
        number = month.id + 1
        selected = [day for day in days if day.calendar_date.month == number]
        working = sum(day.is_working for day in selected)
        shortened = sum(day.is_shortened for day in selected)
        if (
            working != month.workingDays
            or len(selected) - working != month.notWorkingDays
            or shortened != month.shortDays
            or working * 8 - shortened != month.workingHours
        ):
            raise ValueError("Monthly totals do not match calendar dates")
        months.append(
            CalendarMonth(
                year=year,
                month=number,
                calendar_days=len(selected),
                working_days=working,
                non_working_days=len(selected) - working,
                holiday_days=sum(day.is_holiday for day in selected),
                shortened_days=shortened,
                working_hours=month.workingHours,
            )
        )
    return days, months


class ProductionCalendarService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_status(self) -> CalendarStatusRead:
        latest = self.session.scalar(
            select(CalendarImport.imported_at)
            .order_by(CalendarImport.id.desc())
            .limit(1)
        )
        years = list(
            self.session.scalars(select(CalendarYear.year).order_by(CalendarYear.year))
        )
        return CalendarStatusRead(imported_at=latest, years=years)

    def get_month(self, year: int, month: int) -> CalendarMonthDetail | None:
        summary = self.session.get(CalendarMonth, (year, month))
        if summary is None:
            return None
        calendar_year = self.session.get(CalendarYear, year)
        if calendar_year is None:
            raise RuntimeError("Missing calendar year")
        imported = self.session.get(CalendarImport, calendar_year.import_id)
        if imported is None:
            raise RuntimeError("Missing calendar import")
        days = self.session.scalars(
            select(CalendarDay)
            .where(
                CalendarDay.calendar_date >= date(year, month, 1),
                CalendarDay.calendar_date
                <= date(year, month, monthrange(year, month)[1]),
            )
            .order_by(CalendarDay.calendar_date)
        ).all()
        return CalendarMonthDetail(
            imported_at=imported.imported_at,
            source=imported.source,
            week_days=imported.week_days,
            week_hours=imported.week_hours,
            summary=CalendarMonthRead.model_validate(summary),
            days=[CalendarDayRead.model_validate(day) for day in days],
        )

    def refresh(self, user_id: int) -> CalendarStatusRead:
        current_year = datetime.now(ZoneInfo("Europe/Moscow")).year
        payload: dict = {}
        prepared: dict[int, tuple[list[CalendarDay], list[CalendarMonth]]] = {}
        try:
            available = SourceYears.model_validate(fetch_calendar_json())
            years = sorted(set(available.years))
            if current_year not in years or any(y < 1900 or y > 9998 for y in years):
                raise ValueError("Current year is unavailable or year list is invalid")
            for year in years:
                if year < current_year:
                    continue
                annual = fetch_calendar_json(f"/{year}")
                holidays = fetch_calendar_json(f"/{year}/holidays")
                prepared[year] = parse_calendar_year(year, annual, holidays)
                payload[str(year)] = {"calendar": annual, "holidays": holidays}
        except (URLError, TimeoutError, OSError, ValueError, ValidationError):
            logger.exception("Production calendar download or validation failed")
            raise HTTPException(
                status_code=502,
                detail=(
                    "Не удалось загрузить календарь. Сохранённые данные не изменены."
                ),
            ) from None
        try:
            imported = CalendarImport(
                imported_at=int(datetime.now(UTC).timestamp() * 1000),
                imported_by_user_id=user_id,
                source=SOURCE,
                country="ru",
                week_days=5,
                week_hours=40,
                payload=payload,
            )
            self.session.add(imported)
            self.session.flush()
            for year, (days, months) in prepared.items():
                existing = self.session.get(CalendarYear, year)
                if existing is None:
                    self.session.add(CalendarYear(year=year, import_id=imported.id))
                else:
                    existing.import_id = imported.id
                self.session.flush()
                self.session.execute(
                    delete(CalendarDay).where(CalendarDay.year == year)
                )
                self.session.execute(
                    delete(CalendarMonth).where(CalendarMonth.year == year)
                )
                self.session.add_all([*days, *months])
            self.session.commit()
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Production calendar save failed")
            raise HTTPException(
                status_code=409,
                detail="Не удалось сохранить календарь. Повторить обновление.",
            ) from None
        return self.get_status()
