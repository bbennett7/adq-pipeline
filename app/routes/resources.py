from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import verify_token
from app.services.resources import retrieve_resources

router = APIRouter(dependencies=[Depends(verify_token)])


class ResourceRequest(BaseModel):
    question_md: str
    answer_md: str


@router.post("/retrieve-resources")
async def get_resources(body: ResourceRequest) -> dict:
    """Vector search for resources; generative fallback if no match."""
    resources = await retrieve_resources(body.question_md, body.answer_md)
    return {"resources": resources}
