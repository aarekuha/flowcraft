# ruff: noqa: I001
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import String, cast as sql_cast, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from app.models.bitrix import BitrixConnection, BitrixDeal
from app.services.bitrix_client import BitrixError
from app.services.bitrix_service import busy, now_ms, saved_client
from app.services.bitrix_progress import SyncProgress, SyncCancelled, logger


def deals_status(session: Session) -> dict:
    connection = session.get(BitrixConnection, 1)
    return {
        "progress": connection.sync_progress
        if connection and busy(connection)
        else None,
        "job_id": connection.job_id if connection else None,
        "configured": connection is not None,
        "syncing": busy(connection) if connection else False,
        "synced_at": connection.deals_synced_at if connection else None,
        "last_error": (
            connection.deals_last_error
            or (
                "Загрузка прервана. Повторить обновление"
                if connection.job_id
                and connection.job_kind == "deals"
                and not busy(connection)
                else None
            )
        )
        if connection
        else None,
    }


def sync_deals(factory: sessionmaker[Session], job: str) -> None:
    progress = SyncProgress(factory, job, "deals")
    try:
        with factory() as session:
            client = saved_client(session)
            known_ids = list(session.scalars(select(BitrixDeal.id)))
        client.progress = progress.heartbeat
        client.on_progress = progress.report
        progress.report("Загрузка сделок")
        items, metadata = client.deals_snapshot(known_ids)
        progress.report("Сохранение сделок в БД", 0, len(items))
        with factory() as session:
            timestamp = now_ms()
            result = session.execute(
                update(BitrixConnection)
                .where(
                    BitrixConnection.id == 1,
                    BitrixConnection.job_id == job,
                )
                .values(
                    job_id=None,
                    deals_synced_at=timestamp,
                    deals_last_error=None,
                    deals_metadata=metadata,
                )
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                session.rollback()
                return
            session.execute(update(BitrixDeal).values(present=False))
            for raw in items:
                fields = raw["fields"]
                identifier = int(fields["ID"])
                item = session.get(BitrixDeal, identifier)
                if item is None:
                    item = BitrixDeal(id=identifier)
                    session.add(item)
                item.title = str(fields.get("TITLE", ""))
                item.category_id = int(fields.get("CATEGORY_ID", 0))
                item.stage_id = str(fields.get("STAGE_ID", ""))
                item.closed = fields.get("CLOSED") == "Y"
                item.present = True
                item.payload = fields
                item.product_rows = raw["product_rows"]
                item.updated_at = timestamp
            session.commit()
        progress.finished(len(items))
    except SyncCancelled:
        logger.info("Bitrix24 sync job=%s stopped", job)
    except Exception as error:
        progress.failed()
        message = (
            str(error)
            if isinstance(error, BitrixError)
            else "Не удалось загрузить сделки. Предыдущие данные сохранены"
        )
        with factory() as session:
            session.execute(
                update(BitrixConnection)
                .where(
                    BitrixConnection.id == 1,
                    BitrixConnection.job_id == job,
                )
                .values(job_id=None, deals_last_error=message)
            )
            session.commit()


def deals_data(
    session: Session, search: str, state: str, category_id: int | None, page: int
) -> dict:
    connection = session.get(BitrixConnection, 1)
    conditions = []
    if search.strip():
        conditions.append(
            or_(
                BitrixDeal.title.contains(search.strip(), autoescape=True),
                sql_cast(BitrixDeal.id, String).contains(
                    search.strip(), autoescape=True
                ),
            )
        )
    if state == "open":
        conditions.extend([BitrixDeal.closed.is_(False), BitrixDeal.present.is_(True)])
    elif state == "closed":
        conditions.append(BitrixDeal.closed.is_(True))
    elif state == "missing":
        conditions.append(BitrixDeal.present.is_(False))
    if category_id is not None:
        conditions.append(BitrixDeal.category_id == category_id)
    total = (
        session.scalar(select(func.count()).select_from(BitrixDeal).where(*conditions))
        or 0
    )
    items = session.scalars(
        select(BitrixDeal)
        .where(*conditions)
        .order_by(BitrixDeal.id.desc())
        .offset((page - 1) * 25)
        .limit(25)
    )
    return {
        "total": total,
        "page": page,
        "page_size": 25,
        "metadata": connection.deals_metadata if connection else {},
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "category_id": item.category_id,
                "stage_id": item.stage_id,
                "closed": item.closed,
                "present": item.present,
                "amount": item.payload.get("OPPORTUNITY"),
                "currency": item.payload.get("CURRENCY_ID"),
                "updated_at": item.updated_at,
            }
            for item in items
        ],
    }


def deal_details(session: Session, identifier: int) -> dict:
    item = session.get(BitrixDeal, identifier)
    if item is None:
        raise HTTPException(404, "Сделка не найдена")
    return {
        "id": item.id,
        "title": item.title,
        "fields": item.payload,
        "product_rows": item.product_rows,
    }
