import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.auth import verify_token
from app.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_token)])

_active_tasks: dict[str, asyncio.Task] = {}


class RunRequest(BaseModel):
    run_id: str

    @field_validator("run_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        UUID(v)
        return v


async def _run_pipeline_task(run_id: str) -> None:
    try:
        await run_pipeline(run_id)
    except Exception:
        pass
    finally:
        _active_tasks.pop(run_id, None)


async def wait_for_active_runs() -> None:
    """Block until all in-flight pipeline runs finish. Called during shutdown."""
    if not _active_tasks:
        return
    logger.info("Shutdown: waiting for %d active pipeline run(s)", len(_active_tasks))
    await asyncio.gather(*_active_tasks.values(), return_exceptions=True)
    logger.info("Shutdown: all pipeline runs completed")


@router.post("/run", status_code=202)
async def trigger_run(body: RunRequest) -> dict:
    """Trigger a pipeline run. Returns immediately; results post back to Ground Ctrl."""
    if body.run_id in _active_tasks:
        raise HTTPException(409, "Run already in progress")

    task = asyncio.create_task(_run_pipeline_task(body.run_id))
    _active_tasks[body.run_id] = task
    return {"run_id": body.run_id, "status": "accepted"}
