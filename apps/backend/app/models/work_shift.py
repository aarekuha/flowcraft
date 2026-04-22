from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WorkShift(Base):
    __tablename__ = "work_shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ended_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    business_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    user = relationship("User", lazy="joined")
    timer_sessions = relationship(
        "TimerSession",
        back_populates="shift",
        cascade="all, delete-orphan",
        order_by="TimerSession.started_at",
    )
