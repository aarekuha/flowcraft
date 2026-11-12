# ruff: noqa: F811, I001

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models.work_order import WorkOrder
from app.schemas.order import SortDirection, WorkOrderSortField, WorkOrderStatusFilter
from app.services.order_service import OrderService
from app.services.test_order_priority import priority_session  # noqa: F401


@pytest.mark.parametrize(
    "status",
    [
        WorkOrderStatusFilter.ALL,
        WorkOrderStatusFilter.COMPLETED,
        WorkOrderStatusFilter.DELETED,
    ],
)
@pytest.mark.parametrize(
    "direction,expected",
    [
        (SortDirection.ASC, [2, 5, 4, 3, 1, 7, 6]),
        (SortDirection.DESC, [3, 1, 4, 5, 2, 7, 6]),
    ],
)
def test_forecast_sort_keeps_nulls_last_and_sorts_before_pagination(
    priority_session: Session,
    status: WorkOrderStatusFilter,
    direction: SortDirection,
    expected: list[int],
) -> None:
    """
    Проверяем сортировку по сохранённой расчётной дате:
    - задать разные, одинаковые и отсутствующие даты готовности
    - применить оба направления до разбиения на страницы, включая архивные списки
    - оставить пустые даты в конце и сохранить устойчивый порядок равных дат
    """
    days = {1: 20, 2: 10, 3: 20, 4: 12, 5: 11}
    for order_id in range(1, 8):
        order = priority_session.get(WorkOrder, order_id)
        assert order is not None
        order.calculated_finish_date = (
            date(2026, 11, days[order_id]) if order_id in days else None
        )
        if status == WorkOrderStatusFilter.COMPLETED:
            order.completed_at = 1
            order.deleted_at = None
        elif status == WorkOrderStatusFilter.DELETED:
            order.deleted_at = 1
    priority_session.commit()
    ids: list[int] = []
    for page in range(1, 5):
        result = OrderService(priority_session).list_orders(
            search=None,
            include_completed=True,
            status_filter=status,
            sort_by=WorkOrderSortField.CALCULATED_FINISH,
            sort_direction=direction,
            page=page,
            page_size=2,
        )
        ids.extend(item.id for item in result.items)
    assert ids == expected
