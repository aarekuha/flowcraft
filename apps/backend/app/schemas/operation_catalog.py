from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OperationCatalogSortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class OperationCatalogEntryKind(StrEnum):
    REGULAR = "regular"
    CUTTING = "cutting"
    ADJACENT = "adjacent"


class OperationCatalogEntryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    operation_kind: OperationCatalogEntryKind = OperationCatalogEntryKind.REGULAR

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Operation name must not be empty.")
        return normalized


class OperationCatalogEntryStatusUpdate(BaseModel):
    is_active: bool


class OperationCatalogEntryKindUpdate(BaseModel):
    operation_kind: OperationCatalogEntryKind


class OperationCatalogEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    operation_kind: OperationCatalogEntryKind
    is_active: bool
    created_at: int
    updated_at: int


class OperationCatalogEntryPage(BaseModel):
    items: list[OperationCatalogEntryRead]
    total: int
    page: int
    page_size: int
    pages: int
