from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.operation_catalog import OperationCatalogEntry
from app.schemas.operation_catalog import (
    OperationCatalogEntryCreate,
    OperationCatalogEntryPage,
    OperationCatalogEntryRead,
    OperationCatalogEntryStatusUpdate,
    OperationCatalogSortDirection,
)


class OperationCatalogService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_entries(
        self,
        *,
        search: str | None,
        include_inactive: bool,
        sort_direction: OperationCatalogSortDirection,
        page: int,
        page_size: int,
    ) -> OperationCatalogEntryPage:
        stmt = select(OperationCatalogEntry)
        if not include_inactive:
            stmt = stmt.where(OperationCatalogEntry.is_active.is_(True))

        rows = self.session.scalars(stmt).all()
        normalized_search = self._normalize_search(search or "")
        items = [
            self._serialize_entry(entry)
            for entry in rows
            if self._matches_search(entry.name, normalized_search)
        ]
        items.sort(
            key=lambda item: (self._normalize_search(item.name), item.id),
            reverse=sort_direction == OperationCatalogSortDirection.DESC,
        )

        total = len(items)
        pages = max(1, (total + page_size - 1) // page_size)
        page_start = (page - 1) * page_size
        page_end = page_start + page_size

        return OperationCatalogEntryPage(
            items=items[page_start:page_end],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def create_entry(
        self,
        payload: OperationCatalogEntryCreate,
    ) -> OperationCatalogEntryRead:
        self._validate_unique_name(payload.name)
        timestamp = self._now_ts()
        entry = OperationCatalogEntry(
            name=payload.name,
            is_active=True,
            created_at=timestamp,
            updated_at=timestamp,
        )

        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return self._serialize_entry(entry)

    def update_entry_status(
        self,
        entry_id: int,
        payload: OperationCatalogEntryStatusUpdate,
    ) -> OperationCatalogEntryRead:
        entry = self._get_entry_or_404(entry_id)
        entry.is_active = payload.is_active
        entry.updated_at = self._now_ts()

        self.session.commit()
        self.session.refresh(entry)
        return self._serialize_entry(entry)

    def _get_entry_or_404(self, entry_id: int) -> OperationCatalogEntry:
        entry = self.session.get(OperationCatalogEntry, entry_id)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Operation catalog entry {entry_id} not found.",
            )
        return entry

    def _validate_unique_name(self, name: str) -> None:
        normalized_name = self._normalize_search(name)
        stmt: Select[tuple[OperationCatalogEntry]] = select(OperationCatalogEntry)

        for entry in self.session.scalars(stmt):
            if self._normalize_search(entry.name) == normalized_name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Operation with this name already exists.",
                )

    def _matches_search(self, name: str, normalized_search: str) -> bool:
        if not normalized_search:
            return True

        return normalized_search in self._normalize_search(name)

    def _normalize_search(self, value: str) -> str:
        return value.strip().casefold()

    def _serialize_entry(
        self,
        entry: OperationCatalogEntry,
    ) -> OperationCatalogEntryRead:
        return OperationCatalogEntryRead(
            id=entry.id,
            name=entry.name,
            is_active=entry.is_active,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)
