from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.operation import Operation
from app.schemas.report import OperationWorkerReport, OperationWorkerRow
from app.services.report_service import ReportService
from app.services.xlsx_writer import CellValue, XlsxDuration, build_xlsx


class OperationWorkerReportService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_report(
        self,
        date_from: date,
        date_to: date,
        product_ids: list[int] | None = None,
        worker_user_ids: list[int] | None = None,
        operation_catalog_entry_ids: list[int] | None = None,
        order_number: str | None = None,
        page: int | None = 1,
        page_size: int | None = 20,
    ) -> OperationWorkerReport:
        report = ReportService(self.session).get_order_batch_report(
            date_from,
            date_to,
            product_ids,
            worker_user_ids,
            operation_catalog_entry_ids,
            order_number,
            page,
            page_size,
        )
        operation_ids = {
            detail.operation_id
            for batch in report.items
            for detail in batch.details
            if detail.operation_id is not None
        }
        catalog_ids: dict[int, int | None] = (
            {
                operation_id: catalog_id
                for operation_id, catalog_id in self.session.execute(
                    select(Operation.id, Operation.operation_catalog_entry_id).where(
                        Operation.id.in_(operation_ids)
                    )
                ).all()
            }
            if operation_ids
            else {}
        )
        rows: dict[str, OperationWorkerRow] = {}
        for index, batch in enumerate(report.items):
            elapsed: dict[str, int] = {}
            for detail in batch.details:
                catalog_id = (
                    catalog_ids.get(detail.operation_id)
                    if detail.operation_id is not None
                    else None
                )
                operation_key = (
                    f"catalog:{catalog_id}"
                    if catalog_id is not None
                    else f"operation:{detail.operation_id}"
                )
                key = f"{operation_key}:worker:{detail.worker_user_id}"
                rows.setdefault(
                    key,
                    OperationWorkerRow(
                        key=key,
                        operation_name=detail.operation_name,
                        worker_user_name=detail.worker_user_name,
                        average_ms=[None] * len(report.items),
                    ),
                )
                elapsed[key] = elapsed.get(key, 0) + detail.elapsed_ms
            for key, milliseconds in elapsed.items():
                rows[key].average_ms[index] = (
                    milliseconds // batch.submitted_quantity
                    if batch.submitted_quantity > 0
                    else 0
                )
        return OperationWorkerReport(
            batches=report.items,
            rows=sorted(
                rows.values(),
                key=lambda row: (
                    row.operation_name.casefold(),
                    row.worker_user_name.casefold(),
                    row.key,
                ),
            ),
            total=report.total,
            page=report.page,
            pages=report.pages,
        )

    def export_xlsx(
        self,
        date_from: date,
        date_to: date,
        product_ids: list[int] | None = None,
        worker_user_ids: list[int] | None = None,
        operation_catalog_entry_ids: list[int] | None = None,
        order_number: str | None = None,
    ) -> tuple[bytes, str]:
        report = self.get_report(
            date_from,
            date_to,
            product_ids,
            worker_user_ids,
            operation_catalog_entry_ids,
            order_number,
            None,
            None,
        )
        # Разбить широкую таблицу на листы в пределах лимита столбцов Excel
        sheets: list[tuple[str, list[list[CellValue]]]] = []
        for offset in range(0, max(len(report.batches), 1), 16382):
            batches = report.batches[offset : offset + 16382]
            rows: list[list[CellValue]] = [
                [
                    "Операция",
                    "Исполнитель",
                    *(
                        f"{batch.order_number} / {batch.submitted_quantity}"
                        for batch in batches
                    ),
                ]
            ]
            rows.extend(
                [
                    row.operation_name,
                    row.worker_user_name,
                    *(
                        XlsxDuration(value) if value is not None else None
                        for value in row.average_ms[offset : offset + 16382]
                    ),
                ]
                for row in report.rows
            )
            sheets.append((f"Операции и исполнители {len(sheets) + 1}", rows))
        return (
            build_xlsx(sheets, auto_width=True, freeze_header=True),
            f"flowcraft-operation-workers-{date_from}_{date_to}.xlsx",
        )
