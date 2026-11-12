from collections.abc import Iterator
from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.operation import Operation
from app.models.operation_catalog import OperationCatalogEntry
from app.models.product import Product
from app.models.timer_session import TimerSession
from app.models.user import User
from app.models.work_order import WorkOrder
from app.models.work_shift import WorkShift
from app.services.operation_worker_report_service import OperationWorkerReportService


@pytest.fixture()
def report_session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            OperationCatalogEntry(id=1, name="Пошив", created_at=1, updated_at=1)
        )
        for user_id in (1, 2):
            session.add(
                User(
                    id=user_id,
                    name="Тёзка",
                    phone=str(user_id),
                    roles=["worker"],
                    created_at=1,
                    updated_at=1,
                )
            )
            session.add(
                WorkShift(
                    id=user_id,
                    user_id=user_id,
                    started_at=1,
                    business_date="1970-01-01",
                    created_at=1,
                )
            )
        for index in (1, 2, 3):
            session.add(
                Product(
                    id=index,
                    name=f"Изделие {index}",
                    version="1",
                    author="Admin",
                    created_at=1,
                )
            )
            session.add(
                Operation(
                    id=index,
                    product_id=index,
                    operation_catalog_entry_id=1,
                    name="Пошив",
                )
            )
            session.add(
                WorkOrder(
                    id=index,
                    order_number=str(index),
                    product_id=index,
                    quantity=10,
                    defect_quantity=10 if index == 3 else 2,
                    created_at=1,
                    updated_at=1,
                    completed_at=index * 100000,
                )
            )
        session.flush()
        for index, user_id, elapsed in ((1, 1, 80000), (2, 1, 160000), (3, 2, 90000)):
            session.add(
                TimerSession(
                    shift_id=user_id,
                    user_id=user_id,
                    timer_type_code=2,
                    order_id=index,
                    operation_id=index,
                    started_at=1,
                    ended_at=1 + elapsed,
                    created_at=1,
                )
            )
        session.commit()
        yield session
    engine.dispose()


def test_catalog_operations_group_across_products_without_merging_workers(
    report_session: Session,
) -> None:
    """
    Проверяем среднее время по партиям:
    - операции изделий имеют общий справочник, имена исполнителей совпадают
    - время делится на количество без брака, нулевое количество безопасно
    - отсутствующие значения отличаются от нулевого среднего
    """
    report = OperationWorkerReportService(report_session).get_report(
        date(1970, 1, 1), date(1970, 1, 2)
    )
    assert [batch.order_number for batch in report.batches] == ["3", "2", "1"]
    assert len(report.rows) == 2
    assert report.rows[0].average_ms == [None, 20000, 10000]
    assert report.rows[1].average_ms == [0, None, None]


def test_filters_pagination_and_export_keep_all_matching_batches(
    report_session: Session,
) -> None:
    """
    Проверяем фильтры и выгрузку отчёта:
    - отобрать исполнителя и операцию, показать одну партию на странице
    - выгрузить все подходящие партии на отдельных листах изделий
    """
    service = OperationWorkerReportService(report_session)
    period = (date(1970, 1, 1), date(1970, 1, 2))
    report = service.get_report(
        *period,
        worker_user_ids=[1],
        operation_catalog_entry_ids=[1],
        page=2,
        page_size=1,
    )
    assert report.total == 2
    assert report.pages == 2
    assert [batch.order_number for batch in report.batches] == ["1"]
    assert report.rows[0].average_ms == [10000]
    assert service.get_report(*period, product_ids=[3]).rows[0].average_ms == [0]
    assert service.get_report(*period, order_number="missing").rows == []
    content, filename = service.export_xlsx(*period, worker_user_ids=[1])
    assert filename.endswith(".xlsx")
    with ZipFile(BytesIO(content)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
        second_sheet = archive.read("xl/worksheets/sheet2.xml").decode()
        assert "1 / 8" in sheet and "2 / 8" not in sheet
        assert "2 / 8" in second_sheet and "1 / 8" not in second_sheet
        assert "Изделие 1" in sheet and "Изделие 2" in second_sheet
        assert "3 / 0" not in sheet + second_sheet
        assert 'r="C2"' in sheet and 'r="C2"' in second_sheet


def test_product_tables_keep_batches_and_values_together(
    report_session: Session,
) -> None:
    """
    Проверяем разделение таблиц по изделиям и версиям:
    - партии одного изделия перемежаются с партиями другого
    - одинаковые названия разных версий не объединяются
    - строки содержат только значения и исполнителей своего изделия
    """
    first = report_session.get(Product, 1)
    second = report_session.get(Product, 2)
    third_order = report_session.get(WorkOrder, 3)
    assert first is not None and second is not None and third_order is not None
    first.name = second.name = "Одинаковое название"
    second.version = "2"
    third_order.product_id = 1
    report_session.commit()
    report = OperationWorkerReportService(report_session).get_report(
        date(1970, 1, 1), date(1970, 1, 2)
    )
    assert [
        (product.product_id, product.product_version) for product in report.products
    ] == [(1, "1"), (2, "2")]
    first_table, second_table = report.products
    assert [batch.order_number for batch in first_table.batches] == ["3", "1"]
    assert [row.average_ms for row in first_table.rows] == [[None, 10000], [0, None]]
    assert [batch.order_number for batch in second_table.batches] == ["2"]
    assert [row.average_ms for row in second_table.rows] == [[20000]]
