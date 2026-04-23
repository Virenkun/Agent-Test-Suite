import re
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.test_run import TestRunStatus
from app.schemas.call import CallRead

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


class TestRunCreate(BaseModel):
    test_case_id: UUID
    agent_phone_number: str = Field(..., min_length=4, max_length=32)
    num_calls: int = Field(..., ge=1)
    max_cost_usd: Decimal | None = Field(default=None, ge=0)
    max_duration_sec: int | None = Field(default=None, ge=10)

    @field_validator("agent_phone_number")
    @classmethod
    def _validate_e164(cls, v: str) -> str:
        v = v.strip()
        if not _E164_RE.match(v):
            raise ValueError(
                "agent_phone_number must be in E.164 format (e.g. +15551234567)"
            )
        return v


class CriterionBreakdown(BaseModel):
    criterion_id: UUID
    criterion_name: str
    calls_evaluated: int
    pass_rate: float | None = None
    average_score: float | None = None


class TestRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_case_id: UUID
    status: TestRunStatus
    agent_phone_number: str
    requested_calls: int
    completed_calls: int
    failed_calls: int
    max_cost_usd: Decimal | None
    max_duration_sec: int | None
    total_cost_usd: Decimal
    aggregate_score: Decimal | None
    pass_: bool | None = Field(default=None, alias="pass_", serialization_alias="pass")
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class TestRunDetailRead(TestRunRead):
    calls: list[CallRead] = []
    criteria_breakdown: list[CriterionBreakdown] = []
