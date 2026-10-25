from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.leather_type import LeatherType


class WorkOrderNumberCounter(Base):
    __tablename__ = "work_order_number_counters"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class WorkOrderFamily(Base):
    __tablename__ = "work_order_families"
    __table_args__ = (
        UniqueConstraint(
            "base_order_number",
            name="uq_work_order_families_base_order_number",
        ),
        CheckConstraint(
            "last_part_number >= 1",
            name="ck_work_order_families_last_part_number",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    base_order_number: Mapped[str] = mapped_column(String(64), nullable=False)
    last_part_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    orders = relationship("WorkOrder", back_populates="family")


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        UniqueConstraint("order_number", name="uq_work_orders_order_number"),
        UniqueConstraint(
            "family_id",
            "part_number",
            name="uq_work_orders_family_part_number",
        ),
        CheckConstraint(
            "part_number IS NULL OR part_number >= 1",
            name="ck_work_orders_part_number",
        ),
        CheckConstraint(
            "(family_id IS NULL AND part_number IS NULL) OR "
            "(family_id IS NOT NULL AND part_number IS NOT NULL)",
            name="ck_work_orders_family_part_consistency",
        ),
        CheckConstraint(
            "production_stage IN ('created', 'cutting', 'in_work')",
            name="ck_work_orders_production_stage",
        ),
        CheckConstraint(
            "cutting_spent_seconds >= 0",
            name="ck_work_orders_cutting_spent_seconds",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_order_families.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    part_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    leather_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("leather_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_spent_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cutting_spent_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    production_stage: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="created",
        index=True,
    )
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cutting_started_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    taken_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quality_control_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    defect_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    assignments = relationship(
        "WorkOrderAssignment",
        back_populates="work_order",
        cascade="all, delete-orphan",
        order_by="WorkOrderAssignment.id",
    )
    family = relationship("WorkOrderFamily", back_populates="orders")
    time_allocations = relationship(
        "WorkOrderTimeAllocation",
        back_populates="work_order",
        cascade="all, delete-orphan",
    )
    product = relationship("Product", lazy="joined")
    leather_type = relationship(LeatherType, lazy="joined")


class WorkOrderAssignment(Base):
    __tablename__ = "work_order_assignments"
    __table_args__ = (
        UniqueConstraint(
            "work_order_id",
            "operation_id",
            "worker_user_id",
            name="uq_work_order_assignments_order_operation_worker",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    worker_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    work_order = relationship("WorkOrder", back_populates="assignments")
    operation = relationship("Operation", lazy="joined")
    worker_user = relationship("User", lazy="joined")
    worker_states = relationship(
        "WorkOrderAssignmentWorkerState",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )


class WorkOrderAssignmentWorkerState(Base):
    __tablename__ = "work_order_assignment_worker_states"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "worker_user_id",
            name="uq_work_order_assignment_worker_states_assignment_worker",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("work_order_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    worker_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hidden_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    completed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    assignment = relationship(
        "WorkOrderAssignment",
        back_populates="worker_states",
    )
    worker_user = relationship("User", lazy="joined")


class WorkOrderTimeAllocation(Base):
    __tablename__ = "work_order_time_allocations"
    __table_args__ = (
        UniqueConstraint(
            "timer_session_id",
            "work_order_id",
            name="uq_work_order_time_allocations_session_order",
        ),
        CheckConstraint(
            "allocated_seconds >= 0",
            name="ck_work_order_time_allocations_seconds",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    timer_session_id: Mapped[int] = mapped_column(
        ForeignKey("timer_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    allocated_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    timer_session = relationship("TimerSession", back_populates="order_allocations")
    work_order = relationship("WorkOrder", back_populates="time_allocations")


class WorkOrderQrReference(Base):
    __tablename__ = "work_order_qr_references"

    legacy_order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_reference: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
