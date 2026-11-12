# ruff: noqa: I001
from sqlalchemy import BigInteger, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DiagnosticReport(Base):
    __tablename__ = "diagnostic_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "report_key", name="uq_diagnostic_report_user_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    report_key: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
