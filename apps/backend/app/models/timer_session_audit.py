# ruff: noqa: I001

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TimerSessionAuditLog(Base):
    __tablename__ = "timer_session_audit_log"
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_timer_session_audit_log_action",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    timer_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("timer_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    admin_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    before_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    after_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    timer_session = relationship("TimerSession")
    admin_user = relationship("User")
