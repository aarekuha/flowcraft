from sqlalchemy import BigInteger, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TimerSession(Base):
    __tablename__ = "timer_sessions"
    __table_args__ = (
        Index(
            "ix_timer_sessions_user_time_window",
            "user_id",
            "deleted_at",
            "started_at",
            "ended_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(
        ForeignKey("work_shifts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    timer_type_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    operation_id: Mapped[int | None] = mapped_column(
        ForeignKey("operations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ended_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deleted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    shift = relationship("WorkShift", back_populates="timer_sessions")
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    deleted_by_user = relationship(
        "User",
        foreign_keys=[deleted_by_user_id],
        lazy="joined",
    )
    order = relationship("WorkOrder", lazy="joined")
    operation = relationship("Operation", lazy="joined")
    order_allocations = relationship(
        "WorkOrderTimeAllocation",
        back_populates="timer_session",
        cascade="all, delete-orphan",
    )
