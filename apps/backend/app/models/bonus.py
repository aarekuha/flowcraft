from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Bonus(Base):
    __tablename__ = "bonuses"
    __table_args__ = (CheckConstraint("amount_cents >= 0", name="ck_bonus_amount"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)


class UserBonus(Base):
    __tablename__ = "user_bonuses"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    bonus_id: Mapped[int] = mapped_column(
        ForeignKey("bonuses.id", ondelete="CASCADE"), primary_key=True
    )


class MonthlyBonusExclusion(Base):
    __tablename__ = "monthly_bonus_exclusions"
    __table_args__ = (
        CheckConstraint("year BETWEEN 2000 AND 9998", name="ck_bonus_exclusion_year"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_bonus_exclusion_month"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    bonus_id: Mapped[int] = mapped_column(
        ForeignKey("bonuses.id", ondelete="CASCADE"), primary_key=True
    )
