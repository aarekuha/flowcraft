from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MonthlyPiecework(Base):
    __tablename__ = "monthly_piecework"
    __table_args__ = (
        CheckConstraint("year BETWEEN 2000 AND 9998", name="ck_piecework_year"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_piecework_month"),
        CheckConstraint("amount_cents >= 0", name="ck_piecework_amount"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
