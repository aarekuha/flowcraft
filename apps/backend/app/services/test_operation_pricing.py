# ruff: noqa: I001
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.operation import Operation
from app.models.product import Product
from app.models.planning import OperationTimeEstimate, PlanningSettings
from app.schemas.product import OperationCostUpdate, ProductCostsUpdate
from app.schemas.planning import PlanningSettingsUpdate
from app.services.operation_pricing import operation_price, recalculate_prices
from app.services.product_service import ProductService
from app.services.planning_service import PlanningService
from app.services.operation_time_estimate_service import OperationTimeEstimateService
from fastapi import HTTPException


@pytest.fixture()
def pricing_session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Product(id=1, name="Изделие", version="1", author="Автор", created_at=1)
        )
        session.add(PlanningSettings(id=1, base_rate_cents=35000, updated_at=1))
        session.flush()
        session.add(
            Operation(id=1, product_id=1, name="Пошив", coefficient_units=12500)
        )
        session.flush()
        session.add(
            OperationTimeEstimate(
                operation_id=1,
                seconds_per_item=61,
                algorithm_version="recent-30d-five-items-mean-v3",
            )
        )
        session.commit()
        yield session
    engine.dispose()


@pytest.mark.parametrize(
    "rate,coefficient,seconds,expected",
    [
        (35000, 10000, 3600, 35000),
        (35000, 12500, 61, 742),
        (35000, 10000, None, 0),
        (35000, 0, 60, 0),
        (0, 10000, 60, 0),
        (35000, 10001, 1, 10),
    ],
)
def test_price_exact_ceiling(
    rate: int, coefficient: int, seconds: int | None, expected: int
) -> None:
    """
    Проверяем точность цены:
    - использовать часовую ставку, коэффициент и секунды
    - округлить вверх до копейки и вернуть ноль при отсутствии времени
    """
    assert operation_price(rate, coefficient, seconds) == expected


def test_rate_coefficient_and_statistics_recalculate_stored_price(
    pricing_session: Session,
) -> None:
    """
    Проверяем обновление сохранённой цены:
    - изменить БС и коэффициент через сервисы
    - очистить статистическое время через пересчёт и получить ноль
    - запретить ручную замену цены и изменение коэффициента без прав
    """
    session = pricing_session
    recalculate_prices(session)
    session.commit()
    assert session.get(Operation, 1).price_cents == 742
    PlanningService(session).update_settings(
        PlanningSettingsUpdate(
            base_rate_cents=70000,
            display_offset_days=2,
            preparation_seconds=3600,
            horizon_months=3,
        ),
        1,
    )
    assert session.get(Operation, 1).price_cents == 1483
    payload = ProductCostsUpdate(
        operations=[OperationCostUpdate(id=1, coefficient_units=20000)]
    )
    with pytest.raises(HTTPException) as denied:
        ProductService(session).update_product_costs(1, payload)
    assert denied.value.status_code == 403
    ProductService(session).update_product_costs(1, payload, can_change_prices=True)
    assert session.get(Operation, 1).price_cents == 2373
    with pytest.raises(HTTPException):
        ProductService(session).update_product_costs(
            1,
            ProductCostsUpdate(operations=[OperationCostUpdate(id=1, price_cents=123)]),
            can_change_prices=True,
        )
    OperationTimeEstimateService(session).mark_operations_dirty({1})
    session.flush()
    OperationTimeEstimateService(session).recalculate_dirty()
    assert session.get(Operation, 1).price_cents == 0


def test_migration_preserves_old_prices_and_derives_coefficients(
    pricing_session: Session,
) -> None:
    """
    Проверяем перенос прежних цен на контролируемых данных:
    - рассчитать коэффициент с четырьмя знаками и сохранить прежнюю цену с отклонением
    - назначить коэффициент один и нулевую цену операции без времени
    """
    from sqlalchemy import text
    from scripts.migrate_operation_pricing import migrate

    session = pricing_session
    session.get(Operation, 1).price_cents = 1000
    session.add(Operation(id=2, product_id=1, name="Без времени", price_cents=500))
    session.flush()
    connection = session.connection()
    connection.execute(
        text(
            "CREATE TABLE operation_price_migration_report "
            "(operation_id INTEGER PRIMARY KEY, product_id INTEGER, "
            "operation_name TEXT, "
            "old_price_cents INTEGER, seconds_per_item INTEGER, "
            "coefficient_units INTEGER, new_price_cents INTEGER, delta_cents INTEGER)"
        )
    )
    migrate(connection)
    session.expire_all()
    assert session.get(Operation, 1).coefficient_units == 16862
    assert session.get(Operation, 1).price_cents == 1001
    assert session.get(Operation, 2).coefficient_units == 10000
    assert session.get(Operation, 2).price_cents == 0
    report = connection.execute(
        text(
            "SELECT old_price_cents, new_price_cents, delta_cents "
            "FROM operation_price_migration_report WHERE operation_id=1"
        )
    ).one()
    assert tuple(report) == (1000, 1001, 1)


def test_manual_time_immediately_reprices_and_clearing_restores_statistics(
    pricing_session: Session,
) -> None:
    """
    Проверяем приоритет ручного времени:
    - сохранить шесть минут и сразу получить стоимость 35 рублей
    - использовать явный ноль, а после удаления нормы вернуться к статистике
    """
    session = pricing_session
    service = ProductService(session)
    result = service.update_product_costs(
        1,
        ProductCostsUpdate(
            operations=[
                OperationCostUpdate(
                    id=1, coefficient_units=10000, standard_time_seconds=360
                )
            ]
        ),
        can_change_prices=True,
    )
    assert result.operations[0].price_cents == 3500
    assert session.get(Operation, 1).price_cents == 3500
    result = service.update_product_costs(
        1,
        ProductCostsUpdate(
            operations=[OperationCostUpdate(id=1, standard_time_seconds=0)]
        ),
        can_change_prices=True,
    )
    assert result.operations[0].price_cents == 0
    result = service.update_product_costs(
        1,
        ProductCostsUpdate(
            operations=[OperationCostUpdate(id=1, standard_time_seconds=None)]
        ),
        can_change_prices=True,
    )
    assert result.operations[0].price_cents == 594
