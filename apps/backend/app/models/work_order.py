from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.leather_type import LeatherType


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        UniqueConstraint("order_number", name="uq_work_orders_order_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(64), nullable=False)
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
    total_spent_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
    product = relationship("Product", lazy="joined")
    leather_type = relationship(LeatherType, lazy="joined")


class WorkOrderAssignment(Base):
    __tablename__ = "work_order_assignments"
    __table_args__ = (
        UniqueConstraint(
            "work_order_id",
            "operation_id",
            name="uq_work_order_assignments_work_order_operation",
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
