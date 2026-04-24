from uuid import UUID

from pydantic import BaseModel, Field


class GeneratePersonaRequest(BaseModel):
    brief: str = Field(..., min_length=3, max_length=2000)


class GenerateTestCaseRequest(BaseModel):
    brief: str = Field(..., min_length=3, max_length=2000)
    persona_id: UUID | None = None
    desired_criteria_count: int = Field(default=5, ge=2, le=10)
