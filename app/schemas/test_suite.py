import re
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.test_run import TestRunStatus
from app.schemas.test_run import TestRunRead

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


class TestSuiteBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class TestSuiteCreate(TestSuiteBase):
    test_case_ids: list[UUID] = Field(default_factory=list)


class TestSuiteUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None


class TestSuiteCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    test_case_id: UUID
    order_index: int
    name: str | None = None


class TestSuiteRead(TestSuiteBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    cases: list[TestSuiteCaseRead] = []


class AddCasePayload(BaseModel):
    test_case_id: UUID
    order_index: int | None = None


class TestSuiteRunCreate(BaseModel):
    test_suite_id: UUID
    agent_id: UUID | None = None
    agent_phone_number: str | None = Field(default=None, min_length=4, max_length=32)
    calls_per_case: int = Field(..., ge=1)
    max_cost_usd: Decimal | None = Field(default=None, ge=0)
    max_duration_sec: int | None = Field(default=None, ge=10)

    @field_validator("agent_phone_number")
    @classmethod
    def _validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not _E164_RE.match(v):
            raise ValueError("Invalid E.164 phone")
        return v


class TestSuiteRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_suite_id: UUID
    agent_id: UUID | None
    agent_phone_number: str
    status: TestRunStatus
    calls_per_case: int
    max_cost_usd: Decimal | None
    max_duration_sec: int | None
    total_cost_usd: Decimal
    average_aggregate_score: Decimal | None
    pass_rate: Decimal | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class TestSuiteRunDetailRead(TestSuiteRunRead):
    test_runs: list[TestRunRead] = []
