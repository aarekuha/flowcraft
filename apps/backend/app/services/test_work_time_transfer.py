# ruff: noqa: F811

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.work_order import WorkOrder
from app.schemas.admin_work_time import AdminWorkTimeSessionUpdate
from app.services.admin_work_time_service import AdminWorkTimeService
from app.services.test_completed_work import session  # noqa: F401
from app.services.work_order_time_service import WorkOrderTimeService


@pytest.mark.parametrize("valid_operation", [True, False])
def test_transfer_updates_both_orders_and_validates_operation(
    session: Session,
    valid_operation: bool,
) -> None:
    """
    Проверяем перенос завершённого интервала на другое изделие:
    - создать новый заказ с собственной операцией
    - отклонить операцию исходного изделия без переноса времени
    - перенести допустимую запись и пересчитать оба заказа
    """
    session.add(
        Product(id=2, name="Другое изделие", version="1", author="Admin", created_at=1)
    )
    session.flush()
    session.add(Operation(id=3, product_id=2, name="Покраска", price_cents=10))
    session.add(
        WorkOrder(
            id=5,
            order_number="200",
            product_id=2,
            quantity=10,
            created_at=1,
            updated_at=1,
        )
    )
    session.commit()
    WorkOrderTimeService(session).refresh_totals({1, 5}, set_initial_taken_at=False)
    session.commit()
    timer = session.get(TimerSession, 1)
    source = session.get(WorkOrder, 1)
    target = session.get(WorkOrder, 5)
    assert timer and source and target
    previous_total = source.total_spent_seconds
    assert timer.ended_at is not None
    payload = AdminWorkTimeSessionUpdate(
        order_id=5,
        operation_id=3 if valid_operation else 1,
        started_at=timer.started_at,
        ended_at=timer.ended_at,
        expected_updated_at=timer.updated_at,
    )
    service = AdminWorkTimeService(session)
    if not valid_operation:
        with pytest.raises(HTTPException) as error:
            service.update_session(session_id=1, admin_user_id=1, payload=payload)
        assert error.value.status_code == 422
        session.rollback()
        assert timer.order_id == 1
        assert source.total_spent_seconds == previous_total
        assert target.total_spent_seconds == 0
        return
    updated = service.update_session(session_id=1, admin_user_id=1, payload=payload)
    assert updated.order_id == 5 and updated.order_number == "200"
    assert updated.operation_id == 3
    session.expire_all()
    assert source.total_spent_seconds == previous_total - 1
    assert target.total_spent_seconds == 1
