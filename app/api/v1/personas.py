from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError as DomainValidationError
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.import_result import ImportResult
from app.schemas.persona import PersonaCreate, PersonaRead, PersonaUpdate
from app.services.persona_import_service import PersonaImportService
from app.services.persona_service import PersonaService

router = APIRouter(prefix="/personas", tags=["personas"])


@router.post("", response_model=PersonaRead, status_code=status.HTTP_201_CREATED)
async def create_persona(payload: PersonaCreate, db: AsyncSession = Depends(get_db)) -> PersonaRead:
    persona = await PersonaService(db).create(payload)
    return PersonaRead.model_validate(persona)


@router.get("/import-template.xlsx")
async def download_import_template() -> Response:
    content = PersonaImportService.build_template_xlsx()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="personas-template.xlsx"'
        },
    )


@router.post(
    "/bulk-import",
    response_model=ImportResult,
    status_code=status.HTTP_200_OK,
)
async def bulk_import_personas(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    content = await file.read()
    try:
        return await PersonaImportService(db).import_file(
            filename=file.filename or "upload", content=content
        )
    except ValueError as e:
        raise DomainValidationError(str(e)) from e


@router.get("", response_model=Page[PersonaRead])
async def list_personas(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[PersonaRead]:
    items, total = await PersonaService(db).list(limit=limit, offset=offset)
    return Page[PersonaRead](
        items=[PersonaRead.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{persona_id}", response_model=PersonaRead)
async def get_persona(persona_id: UUID, db: AsyncSession = Depends(get_db)) -> PersonaRead:
    persona = await PersonaService(db).get(persona_id)
    return PersonaRead.model_validate(persona)


@router.patch("/{persona_id}", response_model=PersonaRead)
async def update_persona(
    persona_id: UUID, payload: PersonaUpdate, db: AsyncSession = Depends(get_db)
) -> PersonaRead:
    persona = await PersonaService(db).update(persona_id, payload)
    return PersonaRead.model_validate(persona)


@router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(persona_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    await PersonaService(db).delete(persona_id)
