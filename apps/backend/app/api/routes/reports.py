from datetime import date
from typing import Annotated

# ruff: noqa: I001

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_any_role
from app.schemas.report import ProductQuantityReport, ProductTimeReport
from app.schemas.report import ReportFilterOptions
from app.schemas.report import OrderBatchReport
from app.services.report_service import ReportService

router = APIRouter()


@router.get(
    "/filter-options",
    response_model=ReportFilterOptions,
    summary="List report filter options",
)
def get_report_filter_options(
    _: object = Depends(require_any_role("reports")),
    session: Session = Depends(get_session),
) -> ReportFilterOptions:
    return ReportService(session).get_filter_options()


@router.get(
    "/products",
    response_model=ProductQuantityReport,
    summary="Completed product quantities by month and day",
)
def get_product_quantity_report(
    date_from: date,
    date_to: date,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    _: object = Depends(require_any_role("reports")),
    session: Session = Depends(get_session),
) -> ProductQuantityReport:
    return ReportService(session).get_product_quantity_report(
        date_from,
        date_to,
        product_id,
    )


@router.get("/products/export.xlsx", summary="Export completed product quantities")
def export_product_quantity_report(
    date_from: date,
    date_to: date,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    _: object = Depends(require_any_role("reports")),
    session: Session = Depends(get_session),
) -> Response:
    content, filename = ReportService(session).build_product_quantity_xlsx(
        date_from,
        date_to,
        product_id,
    )
    return _xlsx_response(content, filename)


@router.get(
    "/product-time",
    response_model=ProductTimeReport,
    summary="Average product and operation time by day",
)
def get_product_time_report(
    date_from: date,
    date_to: date,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    worker_user_id: Annotated[int | None, Query(ge=1)] = None,
    order_number: Annotated[str | None, Query(max_length=64)] = None,
    _: object = Depends(require_any_role("reports")),
    session: Session = Depends(get_session),
) -> ProductTimeReport:
    return ReportService(session).get_product_time_report(
        date_from,
        date_to,
        product_id,
        worker_user_id,
        order_number,
    )


@router.get("/product-time/export.xlsx", summary="Export product operation time")
def export_product_time_report(
    date_from: date,
    date_to: date,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    worker_user_id: Annotated[int | None, Query(ge=1)] = None,
    order_number: Annotated[str | None, Query(max_length=64)] = None,
    _: object = Depends(require_any_role("reports")),
    session: Session = Depends(get_session),
) -> Response:
    content, filename = ReportService(session).build_product_time_xlsx(
        date_from,
        date_to,
        product_id,
        worker_user_id,
        order_number,
    )
    return _xlsx_response(content, filename)


@router.get(
    "/order-batches",
    response_model=OrderBatchReport,
    summary="Completed order batches with operation time details",
)
def get_order_batch_report(
    date_from: date,
    date_to: date,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    worker_user_id: Annotated[int | None, Query(ge=1)] = None,
    operation_catalog_entry_id: Annotated[int | None, Query(ge=1)] = None,
    order_number: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    _: object = Depends(require_any_role("reports")),
    session: Session = Depends(get_session),
) -> OrderBatchReport:
    return ReportService(session).get_order_batch_report(
        date_from,
        date_to,
        product_id,
        worker_user_id,
        operation_catalog_entry_id,
        order_number,
        page,
        page_size,
    )


@router.get(
    "/order-batches/export.xlsx",
    summary="Export completed order batches with operation time details",
)
def export_order_batch_report(
    date_from: date,
    date_to: date,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    worker_user_id: Annotated[int | None, Query(ge=1)] = None,
    operation_catalog_entry_id: Annotated[int | None, Query(ge=1)] = None,
    order_number: Annotated[str | None, Query(max_length=64)] = None,
    _: object = Depends(require_any_role("reports")),
    session: Session = Depends(get_session),
) -> Response:
    content, filename = ReportService(session).build_order_batch_xlsx(
        date_from,
        date_to,
        product_id,
        worker_user_id,
        operation_catalog_entry_id,
        order_number,
    )
    return _xlsx_response(content, filename)


def _xlsx_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
