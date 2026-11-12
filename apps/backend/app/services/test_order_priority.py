from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.product import Product
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.order import (
    SortDirection,
    WorkOrderPage,
    WorkOrderSortField,
    WorkOrderStatusFilter,
)
from app.schemas.planning import PlanningQueueReorder
from app.services.order_service import OrderService
from app.services.planning_queue_service import PlanningQueueService


@pytest.fixture()
def priority_session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            User(
                id=1,
                name="Admin",
                phone="1",
                roles=["admin"],
                created_at=1,
                updated_at=1,
            )
        )
        session.add(
            Product(id=1, name="Изделие", version="1", author="Admin", created_at=1)
        )
        session.flush()
        for order_id, rank, stage in [
            (1, 30, "created"),
            (2, 10, "cutting"),
            (3, 10, "in_work"),
            (4, 1, "in_work"),
            (5, 2, "created"),
            (6, 3, "created"),
            (7, 20, "in_work"),
        ]:
            session.add(
                WorkOrder(
                    id=order_id,
                    order_number=f"TEST-{order_id}",
                    product_id=1,
                    quantity=10,
                    created_at=order_id,
                    updated_at=1,
                    planning_priority_rank=rank,
                    production_stage=stage,
                    completed_at=1 if order_id == 4 else None,
                    deleted_at=1 if order_id == 5 else None,
                    planning_excluded_at=1 if order_id == 6 else None,
                    quality_control_at=1 if order_id == 7 else None,
                )
            )
        session.commit()
        yield session
    engine.dispose()


def listed(
    session: Session,
    *,
    direction: SortDirection = SortDirection.ASC,
    page: int = 1,
    size: int = 20,
    status: WorkOrderStatusFilter = WorkOrderStatusFilter.ALL,
    search: str | None = None,
) -> WorkOrderPage:
    return OrderService(session).list_orders(
        search=search,
        include_completed=False,
        status_filter=status,
        sort_by=WorkOrderSortField.PRIORITY,
        sort_direction=direction,
        page=page,
        page_size=size,
    )


@pytest.mark.parametrize(
    "direction,expected",
    [
        (SortDirection.ASC, [2, 3, 7, 1, 4, 5, 6]),
        (SortDirection.DESC, [1, 7, 3, 2, 4, 5, 6]),
    ],
)
def test_priority_sort_orders_globally_before_pagination(
    priority_session: Session, direction: SortDirection, expected: list[int]
) -> None:
    """
    Проверяем сортировку всей очереди:
    - заказы имеют разные стадии и совпадающие ранги
    - обе сортировки применяются до разбиения на страницы
    - заказ вне очереди остаётся в конце
    """
    ids: list[int] = []
    for page in (1, 2, 3, 4):
        ids.extend(
            item.id
            for item in listed(
                priority_session, direction=direction, page=page, size=2
            ).items
        )
    assert ids == expected


@pytest.mark.parametrize(
    "status,order_id,position",
    [
        (WorkOrderStatusFilter.CREATED, 1, 4),
        (WorkOrderStatusFilter.CUTTING, 2, 1),
        (WorkOrderStatusFilter.IN_WORK, 3, 2),
        (WorkOrderStatusFilter.QUALITY_CONTROL, 7, 3),
    ],
)
def test_priority_keeps_global_position_under_stage_and_search_filters(
    priority_session: Session,
    status: WorkOrderStatusFilter,
    order_id: int,
    position: int,
) -> None:
    """
    Проверяем соответствие общей очереди:
    - отобрать отдельную стадию и номер заказа
    - позиция совпадает с приоритизацией, а не номером строки результата
    """
    queue = PlanningQueueService(priority_session).get_queue()
    report = listed(priority_session, status=status, search=f"TEST-{order_id}")
    assert len(report.items) == 1
    assert report.items[0].priority_position == position
    assert (
        next(item.position for item in queue.items if item.order_id == order_id)
        == position
    )


@pytest.mark.parametrize(
    "status", [WorkOrderStatusFilter.COMPLETED, WorkOrderStatusFilter.DELETED]
)
def test_archived_order_has_no_queue_position(
    priority_session: Session, status: WorkOrderStatusFilter
) -> None:
    """
    Проверяем архивные заказы:
    - выполненные и удалённые заказы доступны в своих списках
    - позиция очереди для них отсутствует
    """
    report = listed(priority_session, status=status)
    assert len(report.items) == 1
    assert report.items[0].priority_position is None


def test_reorder_is_visible_in_order_list_without_forecast_recalculation(
    priority_session: Session,
) -> None:
    """
    Проверяем обновление приоритета:
    - переместить заказ через сервис приоритизации
    - список сразу показывает новую позицию без пересчёта прогноза
    """
    service = PlanningQueueService(priority_session)
    queue = service.get_queue()
    service.reorder(
        PlanningQueueReorder(order_id=1, position=1, expected_revision=queue.revision),
        updated_by_user_id=1,
    )
    assert listed(priority_session).items[0].id == 1
    assert listed(priority_session, search="TEST-1").items[0].priority_position == 1
