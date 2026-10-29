from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.operation import Operation
from app.models.timer_session import TimerSession
from app.models.timer_session_audit import TimerSessionAuditLog
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderTimeAllocation
from app.models.work_shift import WorkShift
from app.schemas.admin_work_time import (
    AdminWorkTimeAllocationRead,
    AdminWorkTimeOperationRead,
    AdminWorkTimeOrderRead,
    AdminWorkTimeOverlapRead,
    AdminWorkTimeSessionCreate,
    AdminWorkTimeSessionRead,
    AdminWorkTimeSessionUpdate,
    AdminWorkTimeWorkerRead,
)
from app.schemas.operation_catalog import OperationCatalogEntryKind
from app.schemas.order import WorkOrderProductionStage
from app.schemas.timer import TimerType
from app.services.effective_order_time import (
    build_effective_operation_order_links_subquery,
)
from app.services.timer_service import CODE_TO_TIMER_TYPE, TIMER_TYPE_TO_CODE
from app.services.work_order_time_service import WorkOrderTimeService

MAX_RANGE_MS = 7 * 24 * 60 * 60 * 1000

TIMER_TYPE_LABELS = {
    TimerType.PREPARATION: "Подготовка",
    TimerType.OPERATION: "Операция",
    TimerType.BREAK: "Перерыв",
    TimerType.IDLE: "Брак/Ремонт",
}


class AdminWorkTimeService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_workers(self, *, include_inactive: bool) -> list[AdminWorkTimeWorkerRead]:
        historical_worker_ids = set(
            self.session.scalars(
                select(TimerSession.user_id)
                .where(TimerSession.deleted_at.is_(None))
                .distinct()
            ).all()
        )
        users = self.session.scalars(select(User)).all()
        result = [
            AdminWorkTimeWorkerRead(
                id=user.id,
                name=user.name,
                is_active=user.is_active,
                is_deleted=user.deleted_at is not None,
                can_add_time=self._worker_can_add_time(user),
            )
            for user in users
            if ("worker" in user.roles or user.id in historical_worker_ids)
            and (include_inactive or (user.is_active and user.deleted_at is None))
        ]
        result.sort(key=lambda item: (item.name.casefold(), item.id))
        return result

    def list_sessions(
        self,
        *,
        worker_user_id: int,
        period_start: int,
        period_end: int,
    ) -> list[AdminWorkTimeSessionRead]:
        self._validate_period(period_start, period_end)
        self._get_worker_or_404(worker_user_id)
        stmt: Select[tuple[TimerSession]] = (
            select(TimerSession)
            .options(
                selectinload(TimerSession.order_allocations).selectinload(
                    WorkOrderTimeAllocation.work_order
                )
            )
            .where(
                TimerSession.user_id == worker_user_id,
                TimerSession.deleted_at.is_(None),
                TimerSession.started_at < period_end,
                or_(
                    TimerSession.ended_at.is_(None),
                    TimerSession.ended_at > period_start,
                ),
            )
            .order_by(TimerSession.started_at.asc(), TimerSession.id.asc())
        )
        timer_sessions = self.session.scalars(stmt).unique().all()
        return [self._serialize_session(item) for item in timer_sessions]

    def list_cross_order_overlaps(
        self,
        *,
        worker_user_id: int,
        order_id: int,
        started_at: int,
        ended_at: int,
        exclude_session_id: int | None,
    ) -> list[AdminWorkTimeOverlapRead]:
        now = self._now_ts()
        self._validate_interval(started_at, ended_at, now)
        self._get_worker_or_404(worker_user_id)
        self._get_order_or_404(order_id)

        associated_orders = build_effective_operation_order_links_subquery()
        stmt = (
            select(WorkOrder.id, WorkOrder.order_number)
            .select_from(associated_orders)
            .join(
                TimerSession,
                TimerSession.id == associated_orders.c.timer_session_id,
            )
            .join(WorkOrder, WorkOrder.id == associated_orders.c.order_id)
            .where(
                TimerSession.user_id == worker_user_id,
                TimerSession.deleted_at.is_(None),
                TimerSession.timer_type_code
                == TIMER_TYPE_TO_CODE[TimerType.OPERATION],
                associated_orders.c.order_id != order_id,
                TimerSession.started_at < ended_at,
                or_(
                    TimerSession.ended_at.is_(None),
                    TimerSession.ended_at > started_at,
                ),
            )
            .distinct()
            .order_by(WorkOrder.order_number.asc(), WorkOrder.id.asc())
        )
        if exclude_session_id is not None:
            stmt = stmt.where(TimerSession.id != exclude_session_id)
        rows = self.session.execute(stmt).all()
        return [
            AdminWorkTimeOverlapRead(
                order_id=overlap_order_id,
                order_number=order_number,
            )
            for overlap_order_id, order_number in rows
        ]

    def search_orders(
        self,
        *,
        query: str,
        limit: int,
    ) -> list[AdminWorkTimeOrderRead]:
        normalized_query = query.strip().casefold()
        if not normalized_query:
            return []

        orders = self.session.scalars(
            select(WorkOrder)
            .where(
                func.lower(WorkOrder.order_number).contains(normalized_query),
            )
            .order_by(WorkOrder.order_number.asc(), WorkOrder.id.asc())
            .limit(limit)
        ).all()
        return [
            AdminWorkTimeOrderRead(
                id=order.id,
                order_number=order.order_number,
                product_name=order.product.name,
                product_version=order.product.version,
                is_deleted=order.deleted_at is not None,
            )
            for order in orders
        ]

    def list_order_operations(
        self,
        order_id: int,
    ) -> list[AdminWorkTimeOperationRead]:
        order = self._get_order_or_404(order_id)
        operations = self._get_leaf_operations(order.product_id)
        result = [
            AdminWorkTimeOperationRead(
                id=operation.id,
                name=self._operation_name(operation),
            )
            for operation in operations
        ]
        result.sort(key=lambda item: (item.name.casefold(), item.id))
        return result

    def create_session(
        self,
        *,
        admin_user_id: int,
        payload: AdminWorkTimeSessionCreate,
    ) -> AdminWorkTimeSessionRead:
        now = self._now_ts()
        self._validate_interval(payload.started_at, payload.ended_at, now)
        worker = self._get_worker_or_404(payload.worker_user_id)
        if not self._worker_can_add_time(worker):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Добавлять время можно только активному исполнителю.",
            )
        order = self._get_order_or_404(payload.order_id)
        operation = self._get_leaf_operation_or_422(
            order=order,
            operation_id=payload.operation_id,
        )
        shift = self._resolve_shift(
            worker_user_id=worker.id,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
            now=now,
        )
        self._ensure_no_order_collision(
            worker_user_id=worker.id,
            order_id=order.id,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
        )
        self._extend_shift(
            shift=shift,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
        )

        timer_session = TimerSession(
            shift_id=shift.id,
            user_id=worker.id,
            timer_type_code=TIMER_TYPE_TO_CODE[TimerType.OPERATION],
            order_id=order.id,
            operation_id=operation.id,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
            created_at=now,
            updated_at=now,
            deleted_at=None,
            deleted_by_user_id=None,
        )
        self.session.add(timer_session)
        self.session.flush()
        self._record_manual_sewing_start(
            order=order,
            operation=operation,
            started_at=payload.started_at,
        )
        self._write_audit(
            timer_session=timer_session,
            admin_user_id=admin_user_id,
            action="create",
            before_payload=None,
            after_payload=self._snapshot(timer_session, shift=shift),
            created_at=now,
        )
        WorkOrderTimeService(self.session).refresh_totals(
            {order.id},
            set_initial_taken_at=False,
            recalculate_taken_at=True,
            recalculate_cutting_started_at=True,
            updated_at=now,
        )
        self.session.commit()
        self.session.refresh(timer_session)
        return self._serialize_session(timer_session)

    def update_session(
        self,
        *,
        session_id: int,
        admin_user_id: int,
        payload: AdminWorkTimeSessionUpdate,
    ) -> AdminWorkTimeSessionRead:
        now = self._now_ts()
        self._validate_interval(payload.started_at, payload.ended_at, now)
        timer_session = self._get_session_or_404(session_id)
        self._validate_editable_session(timer_session)
        self._validate_expected_version(
            timer_session,
            payload.expected_updated_at,
        )
        before_payload = self._snapshot(timer_session)
        timer_type = CODE_TO_TIMER_TYPE[timer_session.timer_type_code]
        target_order: WorkOrder | None = None
        operation: Operation | None = None
        if timer_type == TimerType.OPERATION:
            target_order = self._get_operation_order_or_422(timer_session)
            if (
                payload.order_id is not None
                and payload.order_id != target_order.id
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Заказ существующей операции нельзя изменить.",
                )
            if payload.operation_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Необходимо выбрать производственную операцию.",
                )
            operation = self._get_leaf_operation_or_422(
                order=target_order,
                operation_id=payload.operation_id,
            )
        elif payload.order_id is not None or payload.operation_id is not None:
            if payload.order_id is None or payload.operation_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        "Для замены служебного интервала необходимо выбрать "
                        "заказ и операцию."
                    ),
                )
            target_order = self._get_order_or_404(payload.order_id)
            operation = self._get_leaf_operation_or_422(
                order=target_order,
                operation_id=payload.operation_id,
            )
        shift = self._resolve_shift(
            worker_user_id=timer_session.user_id,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
            now=now,
            preferred_shift=timer_session.shift,
        )
        if target_order is not None:
            self._ensure_no_order_collision(
                worker_user_id=timer_session.user_id,
                order_id=target_order.id,
                started_at=payload.started_at,
                ended_at=payload.ended_at,
                exclude_session_id=timer_session.id,
            )
        self._extend_shift(
            shift=shift,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
        )

        timer_session.shift_id = shift.id
        if target_order is not None and operation is not None:
            timer_session.timer_type_code = TIMER_TYPE_TO_CODE[TimerType.OPERATION]
            timer_session.order_id = target_order.id
            timer_session.operation_id = operation.id
        timer_session.started_at = payload.started_at
        timer_session.ended_at = payload.ended_at
        timer_session.updated_at = now
        if target_order is not None and operation is not None:
            self._record_manual_sewing_start(
                order=target_order,
                operation=operation,
                started_at=payload.started_at,
            )
        self.session.flush()
        self._write_audit(
            timer_session=timer_session,
            admin_user_id=admin_user_id,
            action="update",
            before_payload=before_payload,
            after_payload=self._snapshot(timer_session, shift=shift),
            created_at=now,
        )
        if target_order is not None:
            WorkOrderTimeService(self.session).refresh_totals(
                {target_order.id},
                set_initial_taken_at=False,
                recalculate_taken_at=True,
                recalculate_cutting_started_at=True,
                updated_at=now,
            )
        self.session.commit()
        self.session.refresh(timer_session)
        return self._serialize_session(timer_session)

    def delete_session(
        self,
        *,
        session_id: int,
        admin_user_id: int,
        expected_updated_at: int,
    ) -> None:
        now = self._now_ts()
        timer_session = self._get_session_or_404(session_id)
        self._validate_editable_session(timer_session)
        self._validate_expected_version(timer_session, expected_updated_at)
        timer_type = CODE_TO_TIMER_TYPE[timer_session.timer_type_code]
        operation_order = (
            self._get_operation_order_or_422(timer_session)
            if timer_type == TimerType.OPERATION
            else None
        )

        before_payload = self._snapshot(timer_session)
        timer_session.deleted_at = now
        timer_session.deleted_by_user_id = admin_user_id
        timer_session.updated_at = now
        self.session.flush()
        self._write_audit(
            timer_session=timer_session,
            admin_user_id=admin_user_id,
            action="delete",
            before_payload=before_payload,
            after_payload=self._snapshot(timer_session),
            created_at=now,
        )
        if operation_order is not None:
            WorkOrderTimeService(self.session).refresh_totals(
                {operation_order.id},
                set_initial_taken_at=False,
                recalculate_taken_at=True,
                recalculate_cutting_started_at=True,
                updated_at=now,
            )
        self.session.commit()

    def _validate_period(self, period_start: int, period_end: int) -> None:
        if period_end <= period_start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Окончание диапазона должно быть позже начала.",
            )
        if period_end - period_start > MAX_RANGE_MS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Диапазон не должен превышать 7 суток.",
            )

    def _validate_interval(self, started_at: int, ended_at: int, now: int) -> None:
        if ended_at <= started_at:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Окончание интервала должно быть позже начала.",
            )
        if ended_at > now:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Нельзя учитывать интервал из будущего.",
            )

    def _get_worker_or_404(self, worker_user_id: int) -> User:
        worker = self.session.get(User, worker_user_id)
        if worker is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Исполнитель не найден.",
            )
        return worker

    def _worker_can_add_time(self, worker: User) -> bool:
        return (
            worker.deleted_at is None
            and worker.is_active
            and "worker" in worker.roles
        )

    def _get_order_or_404(self, order_id: int) -> WorkOrder:
        order = self.session.get(WorkOrder, order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Заказ не найден.",
            )
        return order

    def _get_session_or_404(self, session_id: int) -> TimerSession:
        timer_session = self.session.scalar(
            select(TimerSession)
            .options(
                selectinload(TimerSession.order_allocations).selectinload(
                    WorkOrderTimeAllocation.work_order
                )
            )
            .where(
                TimerSession.id == session_id,
                TimerSession.deleted_at.is_(None),
            )
        )
        if timer_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Запись времени не найдена.",
            )
        return timer_session

    def _validate_editable_session(self, timer_session: TimerSession) -> None:
        timer_type = CODE_TO_TIMER_TYPE[timer_session.timer_type_code]
        if timer_type not in {
            TimerType.OPERATION,
            TimerType.PREPARATION,
            TimerType.BREAK,
            TimerType.IDLE,
        }:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Редактировать можно только производственные операции "
                    "и служебные интервалы."
                ),
            )
        if timer_session.ended_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Активный интервал необходимо сначала завершить.",
            )
        if timer_type == TimerType.OPERATION and timer_session.order_allocations:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Время распределено между частями заказа и недоступно "
                    "для редактирования."
                ),
            )
    def _validate_expected_version(
        self,
        timer_session: TimerSession,
        expected_updated_at: int,
    ) -> None:
        if timer_session.updated_at != expected_updated_at:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Запись времени уже изменена. Необходимо обновить данные.",
            )

    def _get_leaf_operations(self, product_id: int) -> list[Operation]:
        operations = self.session.scalars(
            select(Operation).where(Operation.product_id == product_id)
        ).all()
        parent_ids = {
            operation.parent_id
            for operation in operations
            if operation.parent_id is not None
        }
        return [operation for operation in operations if operation.id not in parent_ids]

    def _get_operation_order_or_422(
        self,
        timer_session: TimerSession,
    ) -> WorkOrder:
        order: WorkOrder | None = timer_session.order
        if order is None or timer_session.order_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Заказ операции недоступен.",
            )
        return order

    def _get_leaf_operation_or_422(
        self,
        *,
        order: WorkOrder,
        operation_id: int,
    ) -> Operation:
        operation = self.session.get(Operation, operation_id)
        if operation is None or operation.product_id != order.product_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Операция не относится к изделию заказа.",
            )
        child_exists = self.session.scalar(
            select(Operation.id).where(Operation.parent_id == operation.id).limit(1)
        )
        if child_exists is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Группа операций не может использоваться для учёта времени.",
            )
        return operation

    def _resolve_shift(
        self,
        *,
        worker_user_id: int,
        started_at: int,
        ended_at: int,
        now: int,
        preferred_shift: WorkShift | None = None,
    ) -> WorkShift:
        business_date = self._business_date(started_at)
        shifts = self.session.scalars(
            select(WorkShift)
            .where(
                WorkShift.user_id == worker_user_id,
                WorkShift.business_date == business_date,
            )
            .order_by(WorkShift.started_at.desc(), WorkShift.id.desc())
        ).all()
        if preferred_shift is not None and preferred_shift in shifts:
            return preferred_shift
        if shifts:
            return min(
                shifts,
                key=lambda shift: self._shift_distance(
                    shift=shift,
                    started_at=started_at,
                    ended_at=ended_at,
                    now=now,
                ),
            )
        shift = WorkShift(
            user_id=worker_user_id,
            started_at=started_at,
            ended_at=ended_at,
            business_date=business_date,
            created_at=now,
        )
        self.session.add(shift)
        self.session.flush()
        return shift

    def _extend_shift(
        self,
        *,
        shift: WorkShift,
        started_at: int,
        ended_at: int,
    ) -> None:
        shift.started_at = min(shift.started_at, started_at)
        if shift.ended_at is not None:
            shift.ended_at = max(shift.ended_at, ended_at)
        shift.business_date = self._business_date(shift.started_at)

    def _shift_distance(
        self,
        *,
        shift: WorkShift,
        started_at: int,
        ended_at: int,
        now: int,
    ) -> int:
        shift_end = shift.ended_at or now
        if ended_at < shift.started_at:
            return shift.started_at - ended_at
        if started_at > shift_end:
            return started_at - shift_end
        return 0

    def _ensure_no_order_collision(
        self,
        *,
        worker_user_id: int,
        order_id: int,
        started_at: int,
        ended_at: int,
        exclude_session_id: int | None = None,
    ) -> None:
        associated_orders = build_effective_operation_order_links_subquery()
        stmt = (
            select(TimerSession)
            .join(
                associated_orders,
                associated_orders.c.timer_session_id == TimerSession.id,
            )
            .where(
                associated_orders.c.order_id == order_id,
                TimerSession.user_id == worker_user_id,
                TimerSession.started_at < ended_at,
                or_(
                    TimerSession.ended_at.is_(None),
                    TimerSession.ended_at > started_at,
                ),
            )
        )
        if exclude_session_id is not None:
            stmt = stmt.where(TimerSession.id != exclude_session_id)
        collision = self.session.scalar(
            stmt.order_by(TimerSession.started_at.asc(), TimerSession.id.asc()).limit(1)
        )
        if collision is None:
            return

        collision_label = (
            self._operation_name(collision.operation)
            if collision.operation is not None
            else TIMER_TYPE_LABELS[TimerType.OPERATION]
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "same_order_time_overlap",
                "message": "В заказе уже есть пересекающийся интервал.",
                "collision": {
                    "session_id": collision.id,
                    "label": collision_label,
                    "started_at": collision.started_at,
                    "ended_at": collision.ended_at,
                },
            },
        )

    def _serialize_session(
        self,
        timer_session: TimerSession,
    ) -> AdminWorkTimeSessionRead:
        timer_type = CODE_TO_TIMER_TYPE[timer_session.timer_type_code]
        operation_name = (
            self._operation_name(timer_session.operation)
            if timer_session.operation is not None
            else None
        )
        positive_allocations = sorted(
            (
                allocation
                for allocation in timer_session.order_allocations
                if allocation.allocated_seconds > 0
            ),
            key=lambda allocation: (
                allocation.work_order.order_number,
                allocation.work_order_id,
            ),
        )
        has_allocations = bool(timer_session.order_allocations)
        blocked_reason: str | None = None
        if timer_type not in {
            TimerType.OPERATION,
            TimerType.PREPARATION,
            TimerType.BREAK,
            TimerType.IDLE,
        }:
            blocked_reason = "Служебный интервал доступен только для просмотра."
        elif timer_session.ended_at is None:
            blocked_reason = "Активный интервал необходимо сначала завершить."
        elif timer_type == TimerType.OPERATION and has_allocations:
            blocked_reason = "Время распределено между частями заказа."
        elif timer_type == TimerType.OPERATION and timer_session.order is None:
            blocked_reason = "Заказ операции недоступен."

        label = (
            operation_name
            if timer_type == TimerType.OPERATION and operation_name is not None
            else TIMER_TYPE_LABELS[timer_type]
        )
        return AdminWorkTimeSessionRead(
            id=timer_session.id,
            shift_id=timer_session.shift_id,
            worker_user_id=timer_session.user_id,
            timer_type=timer_type,
            label=label,
            order_id=timer_session.order_id,
            order_number=(
                timer_session.order.order_number
                if timer_session.order is not None
                else None
            ),
            operation_id=timer_session.operation_id,
            operation_name=operation_name,
            started_at=timer_session.started_at,
            ended_at=timer_session.ended_at,
            is_active=timer_session.ended_at is None,
            has_allocations=has_allocations,
            allocated_order_numbers=[
                allocation.work_order.order_number
                for allocation in positive_allocations
            ],
            allocations=[
                AdminWorkTimeAllocationRead(
                    order_id=allocation.work_order_id,
                    order_number=allocation.work_order.order_number,
                    allocated_seconds=allocation.allocated_seconds,
                )
                for allocation in positive_allocations
            ],
            editable=blocked_reason is None,
            blocked_reason=blocked_reason,
            updated_at=timer_session.updated_at,
        )

    def _write_audit(
        self,
        *,
        timer_session: TimerSession,
        admin_user_id: int,
        action: str,
        before_payload: dict[str, object] | None,
        after_payload: dict[str, object] | None,
        created_at: int,
    ) -> None:
        self.session.add(
            TimerSessionAuditLog(
                timer_session_id=timer_session.id,
                admin_user_id=admin_user_id,
                action=action,
                before_payload=before_payload,
                after_payload=after_payload,
                created_at=created_at,
            )
        )

    def _snapshot(
        self,
        timer_session: TimerSession,
        *,
        shift: WorkShift | None = None,
    ) -> dict[str, object]:
        snapshot_shift = shift or timer_session.shift
        return {
            "id": timer_session.id,
            "shift_id": timer_session.shift_id,
            "user_id": timer_session.user_id,
            "timer_type_code": timer_session.timer_type_code,
            "order_id": timer_session.order_id,
            "operation_id": timer_session.operation_id,
            "started_at": timer_session.started_at,
            "ended_at": timer_session.ended_at,
            "created_at": timer_session.created_at,
            "updated_at": timer_session.updated_at,
            "deleted_at": timer_session.deleted_at,
            "deleted_by_user_id": timer_session.deleted_by_user_id,
            "shift_started_at": snapshot_shift.started_at,
            "shift_ended_at": snapshot_shift.ended_at,
            "shift_business_date": snapshot_shift.business_date,
        }

    def _operation_name(self, operation: Operation) -> str:
        if operation.catalog_entry is not None:
            return str(operation.catalog_entry.name)
        return operation.name

    def _record_manual_sewing_start(
        self,
        *,
        order: WorkOrder,
        operation: Operation,
        started_at: int,
    ) -> None:
        operation_kind = (
            operation.catalog_entry.operation_kind
            if operation.catalog_entry is not None
            else OperationCatalogEntryKind.REGULAR.value
        )
        is_sewing_operation = (
            operation_kind == OperationCatalogEntryKind.REGULAR.value
            or (
                operation_kind == OperationCatalogEntryKind.ADJACENT.value
                and order.production_stage
                == WorkOrderProductionStage.IN_WORK.value
            )
        )
        if not is_sewing_operation:
            return
        if order.sewing_started_at is None:
            order.sewing_started_at = started_at
            return
        order.sewing_started_at = min(order.sewing_started_at, started_at)

    def _business_date(self, timestamp_ms: int) -> str:
        return datetime.fromtimestamp(timestamp_ms / 1000, UTC).date().isoformat()

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)
