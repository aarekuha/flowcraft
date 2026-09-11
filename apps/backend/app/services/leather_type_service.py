from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.leather_type import LeatherType
from app.schemas.leather_type import (
    LeatherTypeCreate,
    LeatherTypePage,
    LeatherTypeRead,
    LeatherTypeSortDirection,
    LeatherTypeStatusUpdate,
)


class LeatherTypeService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_leather_types(
        self,
        *,
        search: str | None,
        include_inactive: bool,
        sort_direction: LeatherTypeSortDirection,
        page: int,
        page_size: int,
    ) -> LeatherTypePage:
        stmt = select(LeatherType)
        if not include_inactive:
            stmt = stmt.where(LeatherType.is_active.is_(True))

        rows = self.session.scalars(stmt).all()
        normalized_search = self._normalize_search(search or "")
        items = [
            self._serialize_leather_type(leather_type)
            for leather_type in rows
            if self._matches_search(leather_type.name, normalized_search)
        ]
        items.sort(
            key=lambda item: (self._normalize_search(item.name), item.id),
            reverse=sort_direction == LeatherTypeSortDirection.DESC,
        )

        total = len(items)
        pages = max(1, (total + page_size - 1) // page_size)
        page_start = (page - 1) * page_size
        page_end = page_start + page_size

        return LeatherTypePage(
            items=items[page_start:page_end],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def create_leather_type(self, payload: LeatherTypeCreate) -> LeatherTypeRead:
        self._validate_unique_name(payload.name)
        timestamp = self._now_ts()
        leather_type = LeatherType(
            name=payload.name,
            is_active=True,
            created_at=timestamp,
            updated_at=timestamp,
        )

        self.session.add(leather_type)
        self.session.commit()
        self.session.refresh(leather_type)
        return self._serialize_leather_type(leather_type)

    def update_leather_type_status(
        self,
        leather_type_id: int,
        payload: LeatherTypeStatusUpdate,
    ) -> LeatherTypeRead:
        leather_type = self._get_leather_type_or_404(leather_type_id)
        leather_type.is_active = payload.is_active
        leather_type.updated_at = self._now_ts()

        self.session.commit()
        self.session.refresh(leather_type)
        return self._serialize_leather_type(leather_type)

    def _get_leather_type_or_404(self, leather_type_id: int) -> LeatherType:
        leather_type = self.session.get(LeatherType, leather_type_id)
        if leather_type is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Leather type {leather_type_id} not found.",
            )
        return leather_type

    def _validate_unique_name(self, name: str) -> None:
        normalized_name = self._normalize_search(name)
        stmt: Select[tuple[LeatherType]] = select(LeatherType)

        for leather_type in self.session.scalars(stmt):
            if self._normalize_search(leather_type.name) == normalized_name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Leather type with this name already exists.",
                )

    def _matches_search(self, name: str, normalized_search: str) -> bool:
        if not normalized_search:
            return True

        return normalized_search in self._normalize_search(name)

    def _normalize_search(self, value: str) -> str:
        return value.strip().casefold()

    def _serialize_leather_type(self, leather_type: LeatherType) -> LeatherTypeRead:
        return LeatherTypeRead(
            id=leather_type.id,
            name=leather_type.name,
            is_active=leather_type.is_active,
            created_at=leather_type.created_at,
            updated_at=leather_type.updated_at,
        )

    def _now_ts(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)
