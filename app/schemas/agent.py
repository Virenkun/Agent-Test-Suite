import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    phone_number: str = Field(..., min_length=4, max_length=32)
    description: str | None = None
    retell_agent_override_id: str | None = Field(default=None, max_length=128)

    @field_validator("phone_number")
    @classmethod
    def _validate_e164(cls, v: str) -> str:
        v = v.strip()
        if not _E164_RE.match(v):
            raise ValueError(
                "phone_number must be in E.164 format (e.g. +15551234567)"
            )
        return v


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    phone_number: str | None = Field(None, min_length=4, max_length=32)
    description: str | None = None
    retell_agent_override_id: str | None = Field(None, max_length=128)

    @field_validator("phone_number")
    @classmethod
    def _validate_e164(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not _E164_RE.match(v):
            raise ValueError(
                "phone_number must be in E.164 format (e.g. +15551234567)"
            )
        return v


class AgentRead(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
