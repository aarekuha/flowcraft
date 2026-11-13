from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.operation_catalog import OperationCatalogEntryKind


class OperationCreate(BaseModel):
    operation_catalog_entry_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    coefficient_units: int = Field(default=10000, ge=0, le=100000000)
    price_cents: int | None = Field(default=None, ge=0)
    standard_time_seconds: int | None = Field(
        default=None,
        ge=0,
        le=2_147_483_647,
    )
    stage_start: int = Field(default=1, ge=1)
    stage_end: int = Field(default=1, ge=1)
    children: list["OperationCreate"] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Operation name must not be empty.")
        return normalized

    @model_validator(mode="after")
    def validate_catalog_reference(self) -> "OperationCreate":
        if self.operation_catalog_entry_id is None and self.name is None:
            raise ValueError(
                "Operation catalog entry id or operation name must be provided."
            )
        if self.stage_end < self.stage_start:
            raise ValueError("Operation stage end must not precede stage start.")
        return self


class OperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operation_catalog_entry_id: int | None
    name: str
    operation_kind: OperationCatalogEntryKind | None = None
    coefficient_units: int = 10000
    price_cents: int | None = None
    standard_time_seconds: int | None = None
    statistical_time_seconds: int | None = None
    statistical_completed_orders_count: int = 0
    statistical_items_count: int = 0
    statistical_time_calculated_at: int | None = None
    stage_start: int = 1
    stage_end: int = 1
    children: list["OperationRead"] = Field(default_factory=list)


class OperationCostUpdate(BaseModel):
    id: int
    coefficient_units: int = Field(default=10000, ge=0, le=100000000)
    price_cents: int | None = Field(default=None, ge=0)
    standard_time_seconds: int | None = Field(
        default=None,
        ge=0,
        le=2_147_483_647,
    )
    children: list["OperationCostUpdate"] = Field(default_factory=list)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=64)
    source_product_id: int | None = Field(default=None, ge=1)
    comment: str | None = Field(default=None, max_length=1000)
    author_user_id: int | None = None
    material_cost_cents: int | None = Field(default=None, ge=0)
    stage_count: int = Field(default=1, ge=1)
    operations: list[OperationCreate] = Field(default_factory=list)

    @field_validator("name", "version")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field must not be empty.")
        return normalized

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ProductStatusUpdate(BaseModel):
    is_active: bool


class ProductCostsUpdate(BaseModel):
    material_cost_cents: int | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=1000)
    operations: list[OperationCostUpdate] = Field(default_factory=list)

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ProductOperationStageUpdate(BaseModel):
    operation_id: int = Field(ge=1)
    stage_start: int = Field(ge=1)
    stage_end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_stage_range(self) -> "ProductOperationStageUpdate":
        if self.stage_end < self.stage_start:
            raise ValueError("Operation stage end must not precede stage start.")
        return self


class ProductStagesUpdate(BaseModel):
    stage_count: int = Field(ge=1)
    operations: list[ProductOperationStageUpdate]


class ProductListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: str
    author: str
    author_user_id: int | None = None
    material_cost_cents: int | None = None
    stage_count: int
    is_active: bool
    created_at: int
    operations_count: int


class ProductDetail(BaseModel):
    base_rate_cents: int = 35000
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: str
    comment: str | None = None
    author: str
    author_user_id: int | None = None
    material_cost_cents: int | None = None
    stage_count: int
    is_active: bool
    created_at: int
    operations: list[OperationRead] = Field(default_factory=list)


OperationCreate.model_rebuild()
OperationRead.model_rebuild()
OperationCostUpdate.model_rebuild()
