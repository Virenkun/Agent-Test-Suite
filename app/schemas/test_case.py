from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.criterion import CriterionCreate, CriterionRead


class TestCaseBase(BaseModel):
    name: str = Field(..., max_length=200)
    description: str | None = None
    persona_id: UUID
    context: str | None = None


class TestCaseCreate(TestCaseBase):
    criteria: list[CriterionCreate] = Field(default_factory=list)


class TestCaseUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    persona_id: UUID | None = None
    context: str | None = None


class TestCaseRead(TestCaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    criteria: list[CriterionRead] = Field(default_factory=list)
