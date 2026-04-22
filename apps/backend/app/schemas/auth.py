from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.phone import normalize_phone
from app.schemas.user import UserRole


class AuthSessionRead(BaseModel):
    user_id: int
    user_name: str
    user_roles: list[UserRole]
    expires_at: int
    idle_expires_at: int


class AuthLogin(BaseModel):
    phone: str = Field(min_length=1, max_length=32)
    password: str = Field(default="", max_length=255)

    @field_validator("phone")
    @classmethod
    def strip_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("password")
    @classmethod
    def strip_password(cls, value: str) -> str:
        return value.strip()


class AuthLoginResult(BaseModel):
    status: Literal["authenticated", "password_setup_required"]
    session: AuthSessionRead | None = None
    user_name: str | None = None


class AuthSetupPassword(BaseModel):
    phone: str = Field(min_length=1, max_length=32)
    new_password: str = Field(min_length=8, max_length=255)

    @field_validator("phone")
    @classmethod
    def strip_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("new_password")
    @classmethod
    def strip_new_password(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be empty.")
        return normalized


class AuthChangePassword(BaseModel):
    current_password: str | None = Field(default=None, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)

    @field_validator("current_password", "new_password")
    @classmethod
    def strip_optional_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be empty.")
        return normalized
