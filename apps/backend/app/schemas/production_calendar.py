from datetime import date

from pydantic import BaseModel, ConfigDict


class CalendarStatusRead(BaseModel):
    imported_at: int | None
    years: list[int]


class CalendarDayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    calendar_date: date
    kind: str
    is_working: bool
    is_holiday: bool
    is_shortened: bool
    name: str | None
    transferred_from: date | None


class CalendarMonthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    calendar_days: int
    working_days: int
    non_working_days: int
    holiday_days: int
    shortened_days: int
    working_hours: int


class CalendarMonthDetail(BaseModel):
    imported_at: int
    source: str
    week_days: int
    week_hours: int
    summary: CalendarMonthRead
    days: list[CalendarDayRead]
