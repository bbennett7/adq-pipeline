from fastapi import APIRouter, Depends

from app.auth import verify_token
from app.services.generator import generate_candidates
from app.services.sources import fetch_all_sources

router = APIRouter(dependencies=[Depends(verify_token)])


@router.post("/generate")
async def generate() -> dict:
    """Fresh candidate generation on demand (e.g. vacation mode queuing)."""
    sources = await fetch_all_sources()
    candidates = await generate_candidates(sources)
    return {
        "candidates": [
            {
                "agent": c.agent.value,
                "questionMd": c.question_md,
                "answerMd": c.answer_md,
            }
            for c in candidates
        ]
    }
