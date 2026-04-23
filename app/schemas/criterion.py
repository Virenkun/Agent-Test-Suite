from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.criterion import CriterionType


class CriterionBase(BaseModel):
    name: str = Field(..., max_length=200)
    type: CriterionType
    instructions: str
    weight: Decimal = Field(default=Decimal("1.0"), ge=0)
    max_score: int | None = Field(default=None, ge=1)
    order_index: int = 0

    @model_validator(mode="after")
    def _validate_type_vs_max_score(self) -> "CriterionBase":
        if self.type == CriterionType.SCORE and self.max_score is None:
            raise ValueError("max_score is required when type is 'score'")
        if self.type == CriterionType.BOOLEAN and self.max_score is not None:
            raise ValueError("max_score must be null when type is 'boolean'")
        return self


class CriterionCreate(CriterionBase):
    pass


class CriterionUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    type: CriterionType | None = None
    instructions: str | None = None
    weight: Decimal | None = Field(None, ge=0)
    max_score: int | None = Field(None, ge=1)
    order_index: int | None = None


class CriterionRead(CriterionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_case_id: UUID
    created_at: datetime
    updated_at: datetime
