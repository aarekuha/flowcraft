from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_any_role
from app.schemas.operation_catalog import (
    OperationCatalogEntryCreate,
    OperationCatalogEntryPage,
    OperationCatalogEntryRead,
    OperationCatalogEntryStatusUpdate,
    OperationCatalogSortDirection,
)
from app.services.operation_catalog_service import OperationCatalogService

router = APIRouter()


@router.get("", response_model=OperationCatalogEntryPage, summary="List operations")
def list_operation_catalog_entries(
    search: str | None = Query(default=None, max_length=128),
    include_inactive: bool = Query(default=False),
    sort_direction: OperationCatalogSortDirection = Query(
        default=OperationCatalogSortDirection.ASC,
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> OperationCatalogEntryPage:
    return OperationCatalogService(session).list_entries(
        search=search,
        include_inactive=include_inactive,
        sort_direction=sort_direction,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=OperationCatalogEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create operation",
)
def create_operation_catalog_entry(
    payload: OperationCatalogEntryCreate,
    _: object = Depends(require_any_role("constructor", "admin")),
    session: Session = Depends(get_session),
) -> OperationCatalogEntryRead:
    return OperationCatalogService(session).create_entry(payload)


@router.patch(
    "/{entry_id}/status",
    response_model=OperationCatalogEntryRead,
    summary="Update operation status",
)
def update_operation_catalog_entry_status(
    entry_id: int,
    payload: OperationCatalogEntryStatusUpdate,
    _: object = Depends(require_any_role("constructor", "admin")),
    session: Session = Depends(get_session),
) -> OperationCatalogEntryRead:
    return OperationCatalogService(session).update_entry_status(
        entry_id=entry_id,
        payload=payload,
    )
