from fastapi import APIRouter, HTTPException

from app.schemas.travel import PlanRequest, PlanResponse
from app.services.planner import PlannerService


router = APIRouter(prefix="/api/v1", tags=["travel"])
service = PlannerService()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/plan", response_model=PlanResponse)
async def create_plan(payload: PlanRequest) -> PlanResponse:
    if payload.check_out <= payload.check_in:
        raise HTTPException(status_code=422, detail="check_out must be after check_in")

    return await service.generate(payload)
