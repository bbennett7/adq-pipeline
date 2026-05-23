from fastapi import APIRouter, Depends

from app.auth import verify_token
from app.services.pipeline import run_pipeline

router = APIRouter(dependencies=[Depends(verify_token)])


@router.post("/run")
async def trigger_run(body: dict | None = None) -> dict:
    """Manual trigger / retry today's pipeline run."""
    date_str = body.get("date") if body else None
    result = await run_pipeline(date_str)
    return result
