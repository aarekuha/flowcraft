# ruff: noqa: I001
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_any_role
from app.services.bitrix_client import BitrixError
from app.services.bitrix_service import (
    begin_sync,
    catalog_data,
    connection_status,
    save_connection,
    saved_client,
    save_mapping,
    set_mapping_not_required,
    sync_catalog,
    stop_sync,
)

from app.services.bitrix_deal_service import (
    deals_status,
    deals_data,
    deal_details,
    sync_deals,
)
from typing import Literal
from uuid import UUID

router = APIRouter(dependencies=[Depends(require_any_role("admin"))])


class MappingWrite(BaseModel):
    bitrix_ids: list[int] = Field(max_length=10000)


@router.get("/settings")
def settings(session: Session = Depends(get_session)) -> dict:
    return connection_status(session)


@router.put("/settings")
async def update_settings(
    request: Request, session: Session = Depends(get_session)
) -> dict:
    # Валидация не должна возвращать входной секрет в поле input ошибки Pydantic
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(413, "Слишком длинный URL вебхука")
    import json

    try:
        payload = json.loads(raw)
        value = payload.get("webhook") if isinstance(payload, dict) else None
        if not isinstance(value, str):
            raise ValueError()
        return save_connection(session, value)
    except (ValueError, BitrixError):
        raise HTTPException(
            400,
            "Не удалось сохранить вебхук. Проверить URL и серверный ключ шифрования",
        ) from None


@router.post("/check")
def check(session: Session = Depends(get_session)) -> dict:
    try:
        saved_client(session).call("catalog.catalog.list", {})
    except BitrixError as error:
        raise HTTPException(502, str(error)) from None
    return {"ok": True}


@router.post("/sync", status_code=202)
def sync(
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    job = begin_sync(session)
    background.add_task(sync_catalog, request.app.state.session_factory, job)
    return {"accepted": True}


@router.get("/catalog")
def catalog(session: Session = Depends(get_session)) -> dict:
    return catalog_data(session)


@router.put("/mappings/{product_id}")
def mapping(
    product_id: int, payload: MappingWrite, session: Session = Depends(get_session)
) -> dict:
    save_mapping(session, product_id, payload.bitrix_ids)
    return {"ok": True}


@router.get("/deals/status")
def deal_status(session: Session = Depends(get_session)) -> dict:
    return deals_status(session)


@router.post("/deals/sync", status_code=202)
def start_deal_sync(
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    job = begin_sync(session, "deals")
    background.add_task(sync_deals, request.app.state.session_factory, job)
    return {"accepted": True}


@router.get("/deals")
def deals(
    search: str = Query("", max_length=200),
    state: Literal["all", "open", "closed", "missing"] = "all",
    category_id: int | None = None,
    page: int = Query(1, ge=1),
    session: Session = Depends(get_session),
) -> dict:
    return deals_data(session, search, state, category_id, page)


@router.get("/deals/{identifier}")
def deal(identifier: int, session: Session = Depends(get_session)) -> dict:
    return deal_details(session, identifier)


class MappingRequirementWrite(BaseModel):
    not_required: bool


@router.put("/mappings/{product_id}/requirement")
def mapping_requirement(
    product_id: int,
    payload: MappingRequirementWrite,
    session: Session = Depends(get_session),
) -> dict:
    set_mapping_not_required(session, product_id, payload.not_required)
    return {"ok": True}


class CancelSyncWrite(BaseModel):
    job_id: UUID


@router.post("/sync/cancel")
def cancel_sync(
    payload: CancelSyncWrite, session: Session = Depends(get_session)
) -> dict:
    stop_sync(
        session,
        str(payload.job_id),
        "Загрузка прервана администратором. Предыдущие данные сохранены",
    )
    return {"ok": True}
