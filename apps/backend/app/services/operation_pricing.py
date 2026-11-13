from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.models.planning import OperationTimeEstimate, PlanningSettings

COEFFICIENT_SCALE = 10000
DEFAULT_BASE_RATE_CENTS = 35000


def operation_price(
    base_rate_cents: int, coefficient_units: int, seconds: int | None
) -> int:
    numerator = base_rate_cents * coefficient_units * (seconds or 0)
    denominator = 3600 * COEFFICIENT_SCALE
    return (numerator + denominator - 1) // denominator


def get_base_rate(session: Session) -> int:
    rate = session.scalar(
        select(PlanningSettings.base_rate_cents).where(PlanningSettings.id == 1)
    )
    return DEFAULT_BASE_RATE_CENTS if rate is None else rate


def recalculate_prices(session: Session, operation_ids: set[int] | None = None) -> None:
    session.flush()
    rate = get_base_rate(session)
    parents = set(
        session.scalars(
            select(Operation.parent_id).where(Operation.parent_id.is_not(None))
        )
    )
    query = select(Operation, OperationTimeEstimate.seconds_per_item).outerjoin(
        OperationTimeEstimate, OperationTimeEstimate.operation_id == Operation.id
    )
    if operation_ids is not None:
        query = query.where(Operation.id.in_(operation_ids))
    for operation, seconds in session.execute(query):
        if operation.standard_time_seconds is not None:
            seconds = operation.standard_time_seconds
        operation.price_cents = (
            None
            if operation.id in parents
            else operation_price(rate, operation.coefficient_units, seconds)
        )
