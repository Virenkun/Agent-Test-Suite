from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.call import CallStatus


class CallEvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    call_id: UUID
    criterion_id: UUID
    passed: bool | None
    score: Decimal | None
    reasoning: str | None
    confidence: Decimal | None
    llm_cost_usd: Decimal
    created_at: datetime


class CallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_run_id: UUID
    retell_call_id: str | None
    status: CallStatus
    duration_sec: int | None
    transcript: str | None
    recording_url: str | None
    cost_usd: Decimal
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class CallDetailRead(CallRead):
    evaluations: list[CallEvaluationRead] = []
