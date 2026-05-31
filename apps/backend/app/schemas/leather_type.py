from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LeatherTypeSortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class LeatherTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Leather type name must not be empty.")
        return normalized


class LeatherTypeStatusUpdate(BaseModel):
    is_active: bool


class LeatherTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    created_at: int
    updated_at: int


class LeatherTypePage(BaseModel):
    items: list[LeatherTypeRead]
    total: int
    page: int
    page_size: int
    pages: int
