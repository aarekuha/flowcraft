from datetime import date

from sqlalchemy import JSON, BigInteger, Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CalendarImport(Base):
    __tablename__ = "production_calendar_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    imported_at: Mapped[int] = mapped_column(BigInteger)
    imported_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(2), default="ru")
    week_days: Mapped[int] = mapped_column(Integer, default=5)
    week_hours: Mapped[int] = mapped_column(Integer, default=40)
    payload: Mapped[dict] = mapped_column(JSON)


class CalendarYear(Base):
    __tablename__ = "production_calendar_years"

    year: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("production_calendar_imports.id"))


class CalendarDay(Base):
    __tablename__ = "production_calendar_days"

    calendar_date: Mapped[date] = mapped_column(Date, primary_key=True)
    year: Mapped[int] = mapped_column(
        ForeignKey("production_calendar_years.year", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    is_working: Mapped[bool] = mapped_column(Boolean)
    is_holiday: Mapped[bool] = mapped_column(Boolean)
    is_shortened: Mapped[bool] = mapped_column(Boolean)
    name: Mapped[str | None] = mapped_column(String(500))
    transferred_from: Mapped[date | None] = mapped_column(Date)


class CalendarMonth(Base):
    __tablename__ = "production_calendar_months"

    year: Mapped[int] = mapped_column(
        ForeignKey("production_calendar_years.year", ondelete="CASCADE"),
        primary_key=True,
    )
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_days: Mapped[int] = mapped_column(Integer)
    working_days: Mapped[int] = mapped_column(Integer)
    non_working_days: Mapped[int] = mapped_column(Integer)
    holiday_days: Mapped[int] = mapped_column(Integer)
    shortened_days: Mapped[int] = mapped_column(Integer)
    working_hours: Mapped[int] = mapped_column(Integer)
