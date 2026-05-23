from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import verify_token
from app.services.styler import style_content

router = APIRouter(dependencies=[Depends(verify_token)])


class StyleRequest(BaseModel):
    question_md: str
    answer_md: str


@router.post("/style")
async def style(body: StyleRequest) -> dict:
    """Claude styling pass — normalize content format."""
    q, a = await style_content(body.question_md, body.answer_md)
    return {"questionMd": q, "answerMd": a}
