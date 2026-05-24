import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import verify_token
from app.services.answer_generator import generate_answers

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_token)])


class GenerateAnswersRequest(BaseModel):
    question_md: str = Field(min_length=1, max_length=500)


@router.post("/generate-answers")
async def handle_generate_answers(body: GenerateAnswersRequest) -> dict:
    """Generate answers from all three models for a given question. Synchronous."""
    answers = await generate_answers(body.question_md)
    return {
        "answers": [{"agent": a.agent.value, "answerMd": a.answer_md} for a in answers],
    }
