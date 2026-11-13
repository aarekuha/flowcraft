from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "operation_catalog_entry_id",
            name="uq_operations_product_catalog_entry",
        ),
        CheckConstraint("stage_start >= 1", name="ck_operations_stage_start"),
        CheckConstraint(
            "stage_end >= stage_start",
            name="ck_operations_stage_end",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    operation_catalog_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("operation_catalog_entries.id"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    coefficient_units: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10000
    )
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    standard_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_start: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stage_end: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    product = relationship("Product", back_populates="operations")
    catalog_entry = relationship("OperationCatalogEntry", lazy="joined")
    parent = relationship(
        "Operation",
        remote_side="Operation.id",
        back_populates="children",
    )
    children = relationship(
        "Operation",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="Operation.sort_order",
    )
    time_estimate = relationship(
        "OperationTimeEstimate",
        back_populates="operation",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="joined",
    )
