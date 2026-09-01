from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OperationCreate(BaseModel):
    operation_catalog_entry_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    price_cents: int | None = Field(default=None, ge=0)
    standard_time_seconds: int | None = Field(
        default=None,
        ge=0,
        le=2_147_483_647,
    )
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
        return self


class OperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operation_catalog_entry_id: int | None
    name: str
    price_cents: int | None = None
    standard_time_seconds: int | None = None
    children: list["OperationRead"] = Field(default_factory=list)


class OperationCostUpdate(BaseModel):
    id: int
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
    author_user_id: int | None = None
    material_cost_cents: int | None = Field(default=None, ge=0)
    operations: list[OperationCreate] = Field(default_factory=list)

    @field_validator("name", "version")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field must not be empty.")
        return normalized


class ProductStatusUpdate(BaseModel):
    is_active: bool


class ProductCostsUpdate(BaseModel):
    material_cost_cents: int | None = Field(default=None, ge=0)
    operations: list[OperationCostUpdate] = Field(default_factory=list)


class ProductListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: str
    author: str
    author_user_id: int | None = None
    material_cost_cents: int | None = None
    is_active: bool
    created_at: int
    operations_count: int


class ProductDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: str
    author: str
    author_user_id: int | None = None
    material_cost_cents: int | None = None
    is_active: bool
    created_at: int
    operations: list[OperationRead] = Field(default_factory=list)


OperationCreate.model_rebuild()
OperationRead.model_rebuild()
OperationCostUpdate.model_rebuild()
