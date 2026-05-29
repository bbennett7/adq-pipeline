import logging
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import verify_token
from app.models.resources import ResourceSuggestion
from app.services.resources import retrieve_resources, validate_resources

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_token)])


class ResourceRequest(BaseModel):
    question_md: str = Field(max_length=500)
    answer_md: str = Field(max_length=2000)


class ChooseResourcesRequest(BaseModel):
    question_md: str = Field(max_length=500)
    answer_md: str = Field(max_length=2000)
    resources: list[ResourceSuggestion] = Field(max_length=20)


@router.post("/retrieve-resources")
async def get_resources(body: ResourceRequest) -> dict:
    """Ask Claude to suggest relevant resources for a question/answer pair."""
    start = time.monotonic()
    logger.info("retrieve-resources: starting Claude call")
    resources = await retrieve_resources(body.question_md, body.answer_md)
    elapsed = time.monotonic() - start
    logger.info(
        "retrieve-resources: completed in %.1fs, returned %d resources",
        elapsed,
        len(resources),
    )
    return {"resources": resources}


@router.post("/choose-resources")
async def choose_resources(body: ChooseResourcesRequest) -> dict:
    """Select the best 2-4 resources from a candidate list."""
    start = time.monotonic()
    logger.info("choose-resources: starting with %d candidates", len(body.resources))
    resource_dicts = [r.model_dump(exclude_none=True) for r in body.resources]
    validated = await validate_resources(body.question_md, body.answer_md, resource_dicts)
    elapsed = time.monotonic() - start
    logger.info("choose-resources: completed in %.1fs, chose %d resources", elapsed, len(validated))
    return {"resources": validated}
