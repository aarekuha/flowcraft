from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.planning import PlanningQueueState
from app.models.work_order import WorkOrder
from app.schemas.planning import (
    PlanningQueueItemRead,
    PlanningQueueRead,
    PlanningQueueReorder,
)
from app.services.planning_revision_service import PlanningRevisionService

PRIORITY_RANK_STEP = 1024
MAX_PRIORITY_RANK = 9_223_372_036_854_775_807
MIN_PRIORITY_RANK = -9_223_372_036_854_775_808


class PlanningQueueService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_queue(self) -> PlanningQueueRead:
        state = self._get_or_create_state()
        return self._serialize_queue(state.revision)

    def reorder(
        self,
        payload: PlanningQueueReorder,
        updated_by_user_id: int,
    ) -> PlanningQueueRead:
        state = self.session.scalar(
            select(PlanningQueueState)
            .where(PlanningQueueState.id == 1)
            .with_for_update()
        )
        if state is None:
            state = self._get_or_create_state()

        if state.revision != payload.expected_revision:
            self._raise_revision_conflict()

        orders = self._load_visible_orders()
        order_by_id = {order.id: order for order in orders}
        moving_order = order_by_id.get(payload.order_id)
        if moving_order is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Заказ отсутствует в текущей очереди планирования.",
            )

        remaining_orders = [order for order in orders if order.id != payload.order_id]
        insertion_index = self._resolve_insertion_index(payload, remaining_orders)
        reordered = list(remaining_orders)
        reordered.insert(insertion_index, moving_order)
        if [order.id for order in reordered] == [order.id for order in orders]:
            return self._serialize_queue(state.revision, orders)

        previous_order = reordered[insertion_index - 1] if insertion_index > 0 else None
        next_order = (
            reordered[insertion_index + 1]
            if insertion_index + 1 < len(reordered)
            else None
        )
        next_rank = self._calculate_rank(previous_order, next_order)
        if next_rank is None:
            self._renumber_plannable_orders()
            orders = self._load_visible_orders()
            order_by_id = {order.id: order for order in orders}
            moving_order = order_by_id[payload.order_id]
            reordered = [order_by_id[order.id] for order in reordered]
            previous_order = (
                reordered[insertion_index - 1] if insertion_index > 0 else None
            )
            next_order = (
                reordered[insertion_index + 1]
                if insertion_index + 1 < len(reordered)
                else None
            )
            next_rank = self._calculate_rank(previous_order, next_order)
            if next_rank is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Не удалось выделить позицию в очереди планирования.",
                )

        moving_order.planning_priority_rank = next_rank
        now = self._now_ts()
        state.revision += 1
        state.updated_at = now
        state.updated_by_user_id = updated_by_user_id
        PlanningRevisionService(self.session).invalidate_without_recalculation()
        self.session.commit()
        return self._serialize_queue(state.revision)

    def assign_lowest_priority(self, order: WorkOrder) -> None:
        current_max = self.session.scalar(
            select(func.max(WorkOrder.planning_priority_rank)).where(
                WorkOrder.planning_excluded_at.is_(None)
            )
        )
        order.planning_priority_rank = (current_max or 0) + PRIORITY_RANK_STEP

    def bump_revision(self, updated_by_user_id: int | None = None) -> None:
        now = self._now_ts()
        result = self.session.execute(
            update(PlanningQueueState)
            .where(PlanningQueueState.id == 1)
            .values(
                revision=PlanningQueueState.revision + 1,
                updated_at=now,
                updated_by_user_id=updated_by_user_id,
            )
            .returning(PlanningQueueState.id)
            .execution_options(synchronize_session=False)
        )
        if result.scalar_one_or_none() is None:
            self.session.add(
                PlanningQueueState(
                    id=1,
                    revision=1,
                    updated_at=now,
                    updated_by_user_id=updated_by_user_id,
                )
            )
        PlanningRevisionService(self.session).request_recalculation()

    def _resolve_insertion_index(
        self,
        payload: PlanningQueueReorder,
        remaining_orders: list[WorkOrder],
    ) -> int:
        if payload.position is not None:
            if payload.position > len(remaining_orders) + 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        "Позиция должна находиться в пределах текущей очереди."
                    ),
                )
            return payload.position - 1

        remaining_ids = [order.id for order in remaining_orders]
        before_index = self._neighbor_index(
            payload.before_order_id,
            remaining_ids,
            "Предыдущий заказ отсутствует в текущей очереди.",
        )
        after_index = self._neighbor_index(
            payload.after_order_id,
            remaining_ids,
            "Следующий заказ отсутствует в текущей очереди.",
        )
        if before_index is None:
            if after_index != 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Следующий заказ должен быть первым в очереди.",
                )
            return 0
        if after_index is None:
            if before_index != len(remaining_orders) - 1:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Предыдущий заказ должен быть последним в очереди.",
                )
            return len(remaining_orders)
        if after_index != before_index + 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Указанные заказы больше не являются соседними.",
            )
        return after_index

    def _neighbor_index(
        self,
        order_id: int | None,
        order_ids: list[int],
        error_detail: str,
    ) -> int | None:
        if order_id is None:
            return None
        try:
            return order_ids.index(order_id)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=error_detail,
            ) from error

    def _calculate_rank(
        self,
        previous_order: WorkOrder | None,
        next_order: WorkOrder | None,
    ) -> int | None:
        if previous_order is None and next_order is None:
            return PRIORITY_RANK_STEP
        if previous_order is None:
            if next_order is None:
                return PRIORITY_RANK_STEP
            candidate = next_order.planning_priority_rank - PRIORITY_RANK_STEP
            return candidate if candidate >= MIN_PRIORITY_RANK else None
        if next_order is None:
            candidate = previous_order.planning_priority_rank + PRIORITY_RANK_STEP
            return candidate if candidate <= MAX_PRIORITY_RANK else None
        gap = next_order.planning_priority_rank - previous_order.planning_priority_rank
        if gap <= 1:
            return None
        return previous_order.planning_priority_rank + gap // 2

    def _load_visible_orders(self) -> list[WorkOrder]:
        return list(
            self.session.scalars(
                select(WorkOrder)
                .where(
                    WorkOrder.planning_excluded_at.is_(None),
                    WorkOrder.completed_at.is_(None),
                    WorkOrder.deleted_at.is_(None),
                )
                .order_by(
                    WorkOrder.planning_priority_rank.asc(),
                    WorkOrder.id.asc(),
                )
            ).unique().all()
        )

    def _renumber_plannable_orders(self) -> None:
        orders = self.session.scalars(
            select(WorkOrder)
            .where(WorkOrder.planning_excluded_at.is_(None))
            .order_by(
                WorkOrder.planning_priority_rank.asc(),
                WorkOrder.id.asc(),
            )
        ).all()
        for index, order in enumerate(orders, start=1):
            order.planning_priority_rank = index * PRIORITY_RANK_STEP
        self.session.flush()

    def _serialize_queue(
        self,
        revision: int,
        orders: list[WorkOrder] | None = None,
    ) -> PlanningQueueRead:
        queue_orders = orders if orders is not None else self._load_visible_orders()
        return PlanningQueueRead(
            revision=revision,
            items=[
                PlanningQueueItemRead(
                    order_id=order.id,
                    position=index,
                    order_number=order.order_number,
                    product_name=order.product.name,
                    leather_type_name=(
                        order.leather_type.name
                        if order.leather_type is not None
                        else None
                    ),
                    quantity=order.quantity,
                    stage=(
                        "quality_control"
                        if order.quality_control_at is not None
                        else order.production_stage
                    ),
                )
                for index, order in enumerate(queue_orders, start=1)
            ],
        )

    def _get_or_create_state(self) -> PlanningQueueState:
        state = self.session.get(PlanningQueueState, 1)
        if state is not None:
            return state
        state = PlanningQueueState(
            id=1,
            revision=0,
            updated_at=self._now_ts(),
            updated_by_user_id=None,
        )
        self.session.add(state)
        self.session.flush()
        return state

    def _raise_revision_conflict(self) -> None:
        self.session.rollback()
        current_queue = self.get_queue()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "planning_queue_revision_conflict",
                "message": (
                    "Очередь уже изменена другим пользователем и была обновлена."
                ),
                "current": current_queue.model_dump(mode="json"),
            },
        )

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)
