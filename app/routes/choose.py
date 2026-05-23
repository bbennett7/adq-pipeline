import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import verify_token
from app.clients.ground_ctrl import get_ground_ctrl
from app.services.styler import style_content

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_token)])


class ChooseRequest(BaseModel):
    run_id: str
    candidate_id: str | None = None


@router.post("/choose")
async def choose(body: ChooseRequest) -> dict:
    """Pick top candidate from a run, style it, and publish via Ground Ctrl."""
    gc = get_ground_ctrl()

    if body.candidate_id:
        candidate_id = body.candidate_id
        run = await gc.get_run(body.run_id)
        candidate = next(
            (c for c in run.candidates if c.id == candidate_id and c.deleted_at is None),
            None,
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found in run")
    else:
        run = await gc.get_run(body.run_id)
        active = [c for c in run.candidates if c.deleted_at is None]
        if not active:
            raise HTTPException(status_code=404, detail="No candidates available in run")
        active.sort(key=lambda c: c.score, reverse=True)
        candidate = active[0]
        candidate_id = candidate.id

    logger.info("Choosing candidate %s from run %s", candidate_id, body.run_id)

    styled_q, styled_a = await style_content(candidate.question_md, candidate.answer_md)
    logger.info("Styled candidate %s", candidate_id)

    result = await gc.choose_candidate(body.run_id, candidate_id, styled_q, styled_a)
    logger.info("Published candidate %s via Ground Ctrl", candidate_id)

    return {
        "candidateId": candidate_id,
        "runId": body.run_id,
        "result": result,
    }
