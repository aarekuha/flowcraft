from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.phone import normalize_phone


class UserRole(StrEnum):
    WORKER = "worker"
    BRIGADIER = "brigadier"
    CONSTRUCTOR = "constructor"
    ADMIN = "admin"


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=32)
    roles: list[UserRole] = Field(min_length=1)
    is_active: bool = True
    author_user_id: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be empty.")
        return normalized

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return normalize_phone(value)


class UserUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=32)
    roles: list[UserRole] = Field(min_length=1)
    is_active: bool
    author_user_id: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be empty.")
        return normalized

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return normalize_phone(value)


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    password_hash: str | None = None
    author: str | None = None
    author_user_id: int | None = None
    roles: list[UserRole]
    is_active: bool
    created_at: int
    updated_at: int
    deleted_at: int | None = None
