from sqlalchemy import BigInteger, Boolean, CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OperationCatalogEntry(Base):
    __tablename__ = "operation_catalog_entries"
    __table_args__ = (
        UniqueConstraint("name", name="uq_operation_catalog_entries_name"),
        CheckConstraint(
            "operation_kind IN ('regular', 'cutting', 'adjacent')",
            name="ck_operation_catalog_entries_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    operation_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="regular",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
