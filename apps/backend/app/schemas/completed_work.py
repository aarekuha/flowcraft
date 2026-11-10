from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BonusInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    amount_cents: int = Field(ge=0, le=999999999)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Указать наименование премии")
        return value


class BonusRead(BonusInput):
    model_config = ConfigDict(from_attributes=True)
    id: int


class UserBonusesInput(BaseModel):
    bonus_ids: list[int] = Field(max_length=1000)


class MonthlyBonusSelection(BaseModel):
    selected: bool = Field(strict=True)


class CompletedWorkBonus(BonusRead):
    selected: bool


class CompletedWorkRow(BaseModel):
    order_id: int
    order_number: str
    completed_at: int
    product_name: str
    product_version: str
    operation_id: int | None
    operation_name: str
    quantity: Decimal
    price_cents: int | None
    amount_cents: int | None


class PersonalWorkReport(BaseModel):
    user_id: int
    user_name: str
    year: int
    month: int
    work_days: int
    work_hours: Decimal
    sick_days: int
    vacation_days: int
    absence_days: int
    items: list[CompletedWorkRow]
    total_quantity: Decimal
    piecework_cents: int | None


class CompletedWorkReport(PersonalWorkReport):
    bonuses: list[CompletedWorkBonus]
    bonuses_cents: int
    payout_cents: int | None


class PersonalReportUnlock(BaseModel):
    password: str = Field(min_length=1, max_length=255)


class PersonalReportAccess(BaseModel):
    token: str
    expires_at: int


class WorkSummaryRow(BaseModel):
    user_id: int
    user_name: str
    sick_days: int
    vacation_days: int
    piecework_cents: int | None
    bonuses_cents: int


class WorkSummary(BaseModel):
    year: int
    month: int
    items: list[WorkSummaryRow]
