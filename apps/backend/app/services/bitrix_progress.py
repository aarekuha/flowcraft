# ruff: noqa: I001
import logging
from time import time
from typing import Any, cast

from sqlalchemy import update, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from app.models.bitrix import BitrixConnection
from app.services.bitrix_client import BitrixError

logger = logging.getLogger("uvicorn.error.bitrix")
logger.setLevel(logging.INFO)


class SyncCancelled(BitrixError):
    pass


class SyncProgress:
    def __init__(self, factory: sessionmaker[Session], job: str, kind: str):
        self.factory = factory
        self.job = job
        self.kind = kind
        self.last_heartbeat = 0

    def write(self, values: dict) -> None:
        timestamp = int(time() * 1000)
        with self.factory() as session:
            result = session.execute(
                update(BitrixConnection)
                .where(BitrixConnection.id == 1, BitrixConnection.job_id == self.job)
                .values(started_at=timestamp, **values)
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                raise SyncCancelled("Загрузка прервана или заменена новым обновлением")
            session.commit()
        self.last_heartbeat = timestamp

    def heartbeat(self) -> None:
        with self.factory() as session:
            job = session.scalar(
                select(BitrixConnection.job_id).where(BitrixConnection.id == 1)
            )
        if job != self.job:
            raise SyncCancelled("Загрузка прервана или заменена новым обновлением")
        if int(time() * 1000) - self.last_heartbeat >= 30000:
            self.write({})

    def report(self, stage: str, completed: int = 0, total: int | None = None) -> None:
        self.write(
            {
                "sync_progress": {
                    "kind": self.kind,
                    "stage": stage,
                    "completed": completed,
                    "total": total,
                    "updated_at": int(time() * 1000),
                }
            }
        )
        logger.info(
            "Bitrix24 sync job=%s kind=%s stage=%s completed=%s total=%s",
            self.job,
            self.kind,
            stage,
            completed,
            total if total is not None else "unknown",
        )

    def finished(self, count: int) -> None:
        logger.info(
            "Bitrix24 sync job=%s kind=%s completed items=%s",
            self.job,
            self.kind,
            count,
        )

    def failed(self) -> None:
        # Текст исключения может содержать данные портала или секретный URL
        logger.warning(
            "Bitrix24 sync job=%s kind=%s failed; previous snapshot preserved",
            self.job,
            self.kind,
        )
