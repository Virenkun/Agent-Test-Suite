from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.ai import GeneratePersonaRequest, GenerateTestCaseRequest
from app.services.ai_generation_service import AIGenerationService

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/generate-persona")
async def generate_persona(
    payload: GeneratePersonaRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    return AIGenerationService(db).generate_persona(payload.brief)


@router.post("/generate-test-case")
async def generate_test_case(
    payload: GenerateTestCaseRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    return await AIGenerationService(db).generate_test_case(
        brief=payload.brief,
        persona_id=payload.persona_id,
        desired_criteria_count=payload.desired_criteria_count,
    )
