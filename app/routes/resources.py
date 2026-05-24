from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import verify_token
from app.models.resources import ResourceSuggestion
from app.services.resources import retrieve_resources, validate_resources

router = APIRouter(dependencies=[Depends(verify_token)])


class ResourceRequest(BaseModel):
    question_md: str
    answer_md: str


class ValidateResourcesRequest(BaseModel):
    question_md: str
    answer_md: str
    resources: list[ResourceSuggestion]


@router.post("/retrieve-resources")
async def get_resources(body: ResourceRequest) -> dict:
    """Ask Claude to suggest relevant resources for a question/answer pair."""
    resources = await retrieve_resources(body.question_md, body.answer_md)
    return {"resources": resources}


@router.post("/validate-resources")
async def post_validate_resources(body: ValidateResourcesRequest) -> dict:
    """Select the best 2-4 resources from a candidate list."""
    resource_dicts = [r.model_dump(exclude_none=True) for r in body.resources]
    validated = await validate_resources(body.question_md, body.answer_md, resource_dicts)
    return {"resources": validated}
