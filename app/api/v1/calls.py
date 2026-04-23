from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.call import Call
from app.schemas.call import CallDetailRead, CallEvaluationRead

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("/{call_id}", response_model=CallDetailRead)
async def get_call(call_id: UUID, db: AsyncSession = Depends(get_db)) -> CallDetailRead:
    result = await db.execute(
        select(Call).options(selectinload(Call.evaluations)).where(Call.id == call_id)
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise NotFoundError(f"Call {call_id} not found")
    return CallDetailRead(
        **{
            **CallDetailRead.model_validate(call).model_dump(exclude={"evaluations"}),
            "evaluations": [CallEvaluationRead.model_validate(e) for e in call.evaluations],
        }
    )
