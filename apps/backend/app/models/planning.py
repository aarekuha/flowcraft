from datetime import date

from sqlalchemy import (
    JSON,
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


class PlanningSettings(Base):
    __tablename__ = "planning_settings"
    __table_args__ = (
        CheckConstraint(
            "display_offset_days >= 0",
            name="ck_planning_settings_display_offset",
        ),
        CheckConstraint(
            "preparation_seconds >= 0",
            name="ck_planning_settings_preparation",
        ),
        CheckConstraint(
            "horizon_months IN (1, 3, 6, 12)",
            name="ck_planning_settings_horizon",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    display_offset_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
    )
    preparation_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3600,
    )
    horizon_months: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class OperationTimeEstimate(Base):
    __tablename__ = "operation_time_estimates"
    __table_args__ = (
        CheckConstraint(
            "seconds_per_item IS NULL OR seconds_per_item >= 0",
            name="ck_operation_time_estimates_seconds",
        ),
        CheckConstraint(
            "completed_orders_count >= 0",
            name="ck_operation_time_estimates_orders_count",
        ),
        CheckConstraint(
            "items_count >= 0",
            name="ck_operation_time_estimates_items_count",
        ),
    )

    operation_id: Mapped[int] = mapped_column(
        ForeignKey("operations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seconds_per_item: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_orders_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calculated_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dirty_at: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )

    operation = relationship("Operation", back_populates="time_estimate")


class UserWorkScheduleDay(Base):
    __tablename__ = "user_work_schedule_days"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "work_date",
            name="uq_user_work_schedule_days_user_date",
        ),
        CheckConstraint(
            "available_seconds BETWEEN 3600 AND 57600",
            name="ck_user_work_schedule_days_available_seconds",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    available_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class PlanningQueueState(Base):
    __tablename__ = "planning_queue_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class PlanningRun(Base):
    __tablename__ = "planning_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'stale', 'failed')",
            name="ck_planning_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    input_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_details: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class ProductionPlanningState(Base):
    __tablename__ = "production_planning_state"
    __table_args__ = (
        CheckConstraint(
            "calculation_status IN ('idle', 'pending', 'running', 'error')",
            name="ck_production_planning_state_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    input_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    requested_revision: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    active_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("planning_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    calculation_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="idle",
    )
    running_revision: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    worker_heartbeat_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PlanningOrderResult(Base):
    __tablename__ = "planning_order_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "order_id",
            name="uq_planning_order_results_run_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("planning_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_finish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    calculated_finish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    issue_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class PlanningOperationResult(Base):
    __tablename__ = "planning_operation_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "order_id",
            "operation_id",
            name="uq_planning_operation_results_run_order_operation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("planning_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    standard_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    standard_time_source: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    stage_start: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stage_end: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    workload_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    remaining_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    preparation_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    first_planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    issue_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class PlanningWorkerDayAllocation(Base):
    __tablename__ = "planning_worker_day_allocations"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "user_id",
            "work_date",
            "order_id",
            "operation_id",
            name="uq_planning_worker_day_allocations_task",
        ),
        CheckConstraint(
            "work_seconds >= 0",
            name="ck_planning_worker_day_allocations_work",
        ),
        CheckConstraint(
            "preparation_seconds >= 0",
            name="ck_planning_worker_day_allocations_preparation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("planning_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    preparation_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
