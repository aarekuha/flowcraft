# ruff: noqa: I001
from time import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import CursorResult
from typing import Any, cast

from app.models.bitrix import BitrixConnection, BitrixMapping, BitrixProduct
from app.models.product import Product
from app.services.bitrix_client import (
    BitrixClient,
    BitrixError,
    decrypt_webhook,
    encrypt_webhook,
    normalize_webhook,
)

from app.services.bitrix_progress import SyncProgress, logger, SyncCancelled

LEASE_MS = 15 * 60 * 1000


def now_ms() -> int:
    return int(time() * 1000)


def busy(connection: BitrixConnection) -> bool:
    return bool(
        connection.job_id and (connection.started_at or 0) > now_ms() - LEASE_MS
    )


def connection_status(session: Session) -> dict:
    connection = session.get(BitrixConnection, 1)
    if connection is None:
        return {
            "configured": False,
            "syncing": False,
            "synced_at": None,
            "last_error": None,
        }
    return {
        "job_id": connection.job_id,
        "progress": connection.sync_progress if busy(connection) else None,
        "configured": True,
        "syncing": busy(connection),
        "synced_at": connection.synced_at,
        "last_error": connection.last_error
        or (
            "Загрузка прервана. Повторить обновление"
            if connection.job_id and not busy(connection)
            else None
        ),
    }


def save_connection(session: Session, value: str) -> dict:
    webhook = normalize_webhook(value)
    portal = BitrixClient(webhook).portal
    connection = session.get(BitrixConnection, 1)
    if connection and connection.portal != portal:
        raise HTTPException(
            409, "Замена портала недоступна при существующих настройках"
        )
    encrypted = encrypt_webhook(webhook)
    if connection:
        result = session.execute(
            update(BitrixConnection)
            .where(
                BitrixConnection.id == 1,
                or_(
                    BitrixConnection.job_id.is_(None),
                    BitrixConnection.started_at <= now_ms() - LEASE_MS,
                ),
            )
            .values(encrypted_webhook=encrypted, last_error=None, job_id=None)
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            raise HTTPException(409, "Дождаться завершения загрузки Bitrix24")
    else:
        session.add(
            BitrixConnection(
                id=1, portal=portal, encrypted_webhook=encrypted, catalog_metadata={}
            )
        )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Настройки изменились. Повторить сохранение") from None
    session.expire_all()
    return connection_status(session)


def saved_client(session: Session) -> BitrixClient:
    connection = session.get(BitrixConnection, 1)
    if connection is None:
        raise HTTPException(409, "Сначала сохранить вебхук")
    return BitrixClient(decrypt_webhook(connection.encrypted_webhook))


def begin_sync(session: Session, kind: str = "catalog") -> str:
    if session.get(BitrixConnection, 1) is None:
        raise HTTPException(409, "Сначала сохранить вебхук")
    job = str(uuid4())
    result = session.execute(
        update(BitrixConnection)
        .where(
            BitrixConnection.id == 1,
            or_(
                BitrixConnection.job_id.is_(None),
                BitrixConnection.started_at <= now_ms() - LEASE_MS,
            ),
        )
        .values(
            job_id=job,
            job_kind=kind,
            sync_progress={
                "kind": kind,
                "stage": "Подготовка загрузки",
                "completed": 0,
                "total": None,
                "updated_at": now_ms(),
            },
            started_at=now_ms(),
            **{"deals_last_error" if kind == "deals" else "last_error": None},
        )
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        raise HTTPException(409, "Загрузка уже выполняется")
    session.commit()
    logger.info("Bitrix24 sync job=%s kind=%s started", job, kind)
    return job


def sync_catalog(factory: sessionmaker[Session], job: str) -> None:
    progress = SyncProgress(factory, job, "catalog")
    try:
        with factory() as session:
            client = saved_client(session)
        client.progress = progress.heartbeat
        client.on_progress = progress.report
        progress.report("Загрузка каталога")
        items, metadata = client.snapshot()
        progress.report("Сохранение товаров в БД", 0, len(items))
        with factory() as session:
            # Захват записи сериализует публикацию и замену настроек
            result = session.execute(
                update(BitrixConnection)
                .where(
                    BitrixConnection.id == 1,
                    BitrixConnection.job_id == job,
                )
                .values(
                    job_id=None,
                    synced_at=now_ms(),
                    last_error=None,
                    catalog_metadata=metadata,
                )
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                session.rollback()
                return
            session.execute(update(BitrixProduct).values(present=False))
            for raw in items:
                payload = dict(raw)
                prices = payload.pop("_prices")
                identifier = int(payload["id"])
                parent = payload.get("parentId")
                if isinstance(parent, dict):
                    parent = parent.get("value")
                item = session.get(BitrixProduct, identifier)
                if item is None:
                    item = BitrixProduct(id=identifier)
                    session.add(item)
                item.catalog_id = int(payload["iblockId"])
                item.name = str(payload.get("name", ""))
                item.active = payload.get("active") == "Y"
                item.present = True
                item.parent_id = int(parent) if parent else None
                item.payload = payload
                item.prices = prices
            session.commit()
        progress.finished(len(items))
    except SyncCancelled:
        logger.info("Bitrix24 sync job=%s stopped", job)
    except Exception as error:
        progress.failed()
        message = (
            str(error)
            if isinstance(error, BitrixError)
            else "Не удалось загрузить каталог. Предыдущие данные сохранены"
        )
        with factory() as session:
            session.execute(
                update(BitrixConnection)
                .where(
                    BitrixConnection.id == 1,
                    BitrixConnection.job_id == job,
                )
                .values(job_id=None, last_error=message)
            )
            session.commit()


def catalog_data(session: Session) -> dict:
    connection = session.get(BitrixConnection, 1)
    mappings = {
        bitrix_id: product_id
        for bitrix_id, product_id in session.execute(
            select(BitrixMapping.bitrix_id, BitrixMapping.product_id)
        )
    }
    products = session.scalars(
        select(BitrixProduct).order_by(BitrixProduct.name, BitrixProduct.id)
    ).all()
    return {
        "metadata": connection.catalog_metadata if connection else {},
        "items": [
            {
                "id": item.id,
                "catalog_id": item.catalog_id,
                "name": item.name,
                "active": item.active,
                "present": item.present,
                "parent_id": item.parent_id,
                "fields": item.payload,
                "prices": item.prices,
                "mapped_product_id": mappings.get(item.id),
            }
            for item in products
        ],
        "products": [
            {
                "id": product.id,
                "name": product.name,
                "version": product.version,
                "mapping_not_required": product.bitrix_mapping_not_required,
                "bitrix_ids": [
                    key for key, value in mappings.items() if value == product.id
                ],
            }
            for product in session.scalars(
                select(Product)
                .where(Product.is_active.is_(True))
                .order_by(Product.name, Product.version, Product.id)
            )
        ],
    }


def save_mapping(session: Session, product_id: int, identifiers: list[int]) -> None:
    product = session.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(409, "Изделие удалено или неактивно")
    if identifiers and product.bitrix_mapping_not_required:
        raise HTTPException(409, "Сначала снять статус «Не требует сопоставления»")
    ids = set(identifiers)
    if ids:
        existing = set(
            session.scalars(select(BitrixProduct.id).where(BitrixProduct.id.in_(ids)))
        )
        if existing != ids:
            raise HTTPException(422, "Товар Bitrix24 не найден")
        conflict = session.scalar(
            select(BitrixMapping)
            .where(
                BitrixMapping.bitrix_id.in_(ids),
                BitrixMapping.product_id != product_id,
            )
            .limit(1)
        )
        if conflict is not None:
            raise HTTPException(
                409,
                (
                    f"Товар Bitrix24 {conflict.bitrix_id} уже связан "
                    f"с изделием {conflict.product_id}"
                ),
            )
    session.execute(delete(BitrixMapping).where(BitrixMapping.product_id == product_id))
    session.add_all(
        [
            BitrixMapping(bitrix_id=identifier, product_id=product_id)
            for identifier in ids
        ]
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            409, "Сопоставления изменились. Обновить список и повторить сохранение"
        ) from None


def set_mapping_not_required(session: Session, product_id: int, value: bool) -> None:
    product = session.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(409, "Изделие удалено или неактивно")
    if (
        value
        and session.scalar(
            select(BitrixMapping).where(BitrixMapping.product_id == product_id).limit(1)
        )
        is not None
    ):
        raise HTTPException(
            409, "Сначала удалить и сохранить существующие сопоставления"
        )
    product.bitrix_mapping_not_required = value
    session.commit()


def stop_sync(session: Session, job: str, reason: str) -> None:
    connection = session.get(BitrixConnection, 1)
    if connection is None or connection.job_id != job:
        raise HTTPException(409, "Загрузка уже завершена или заменена новым заданием")
    error_field = "deals_last_error" if connection.job_kind == "deals" else "last_error"
    result = session.execute(
        update(BitrixConnection)
        .where(
            BitrixConnection.id == 1,
            BitrixConnection.job_id == job,
        )
        .values(
            job_id=None, started_at=None, sync_progress=None, **{error_field: reason}
        )
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        session.rollback()
        raise HTTPException(409, "Загрузка уже завершена или заменена новым заданием")
    session.commit()
    logger.info("Bitrix24 sync job=%s interrupted: %s", job, reason)


def recover_interrupted_sync(factory: sessionmaker[Session]) -> None:
    # Фоновые задания принадлежат единственному процессу backend
    with factory() as session:
        connection = session.get(BitrixConnection, 1)
        if connection is not None and connection.job_id:
            stop_sync(
                session,
                connection.job_id,
                "Загрузка прервана перезапуском сервера. Повторить обновление",
            )
