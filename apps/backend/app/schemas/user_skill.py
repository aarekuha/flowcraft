from pydantic import BaseModel, Field

from app.schemas.operation_catalog import OperationCatalogEntryKind


class UserSkillCreate(BaseModel):
    operation_catalog_entry_id: int = Field(ge=1)


class UserSkillsCopy(BaseModel):
    source_user_id: int = Field(ge=1)


class UserSkillRead(BaseModel):
    operation_catalog_entry_id: int
    operation_name: str
    operation_kind: OperationCatalogEntryKind
    created_at: int


class UserSkillsRead(BaseModel):
    user_id: int
    user_name: str
    skills: list[UserSkillRead]
    total_count: int
    hidden_inactive_count: int
