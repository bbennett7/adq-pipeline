import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.auth import verify_token
from app.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_token)])

# Single-process guard — does not protect across multiple instances or restarts.
_active_runs: set[str] = set()


class RunRequest(BaseModel):
    run_id: str

    @field_validator("run_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        UUID(v)
        return v


async def _run_in_background(run_id: str) -> None:
    try:
        await run_pipeline(run_id)
    finally:
        _active_runs.discard(run_id)


@router.post("/run", status_code=202)
async def trigger_run(body: RunRequest, bg: BackgroundTasks) -> dict:
    """Trigger a pipeline run. Returns immediately; results post back to Ground Ctrl."""
    if body.run_id in _active_runs:
        raise HTTPException(409, "Run already in progress")

    _active_runs.add(body.run_id)
    bg.add_task(_run_in_background, body.run_id)
    return {"run_id": body.run_id, "status": "accepted"}
