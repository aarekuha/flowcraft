from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_any_role
from app.schemas.leather_type import (
    LeatherTypeCreate,
    LeatherTypePage,
    LeatherTypeRead,
    LeatherTypeSortDirection,
    LeatherTypeStatusUpdate,
)
from app.services.leather_type_service import LeatherTypeService

router = APIRouter()


@router.get("", response_model=LeatherTypePage, summary="List leather types")
def list_leather_types(
    search: str | None = Query(default=None, max_length=128),
    include_inactive: bool = Query(default=False),
    sort_direction: LeatherTypeSortDirection = Query(
        default=LeatherTypeSortDirection.ASC,
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> LeatherTypePage:
    return LeatherTypeService(session).list_leather_types(
        search=search,
        include_inactive=include_inactive,
        sort_direction=sort_direction,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=LeatherTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create leather type",
)
def create_leather_type(
    payload: LeatherTypeCreate,
    _: object = Depends(require_any_role("constructor", "admin")),
    session: Session = Depends(get_session),
) -> LeatherTypeRead:
    return LeatherTypeService(session).create_leather_type(payload)


@router.patch(
    "/{leather_type_id}/status",
    response_model=LeatherTypeRead,
    summary="Update leather type status",
)
def update_leather_type_status(
    leather_type_id: int,
    payload: LeatherTypeStatusUpdate,
    _: object = Depends(require_any_role("constructor", "admin")),
    session: Session = Depends(get_session),
) -> LeatherTypeRead:
    return LeatherTypeService(session).update_leather_type_status(
        leather_type_id=leather_type_id,
        payload=payload,
    )
