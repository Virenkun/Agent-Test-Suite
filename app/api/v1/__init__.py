from fastapi import APIRouter

from app.api.v1 import calls, criteria, personas, streams, test_cases, test_runs, webhooks

api_router = APIRouter()
api_router.include_router(personas.router)
api_router.include_router(test_cases.router)
api_router.include_router(criteria.router)
api_router.include_router(test_runs.router)
api_router.include_router(calls.router)
api_router.include_router(webhooks.router)
api_router.include_router(streams.router)
