from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PersonaBase(BaseModel):
    name: str = Field(..., max_length=200)
    tone: str | None = Field(None, max_length=200)
    personality: str | None = None
    goal: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    prompt_instructions: str | None = None


class PersonaCreate(PersonaBase):
    pass


class PersonaUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    tone: str | None = Field(None, max_length=200)
    personality: str | None = None
    goal: str | None = None
    constraints: dict[str, Any] | None = None
    prompt_instructions: str | None = None


class PersonaRead(PersonaBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
