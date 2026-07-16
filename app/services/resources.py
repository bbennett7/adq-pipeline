import asyncio
import json
import logging
import time
from pathlib import Path

from app.clients.anthropic import WEB_SEARCH_TOOL, get_client, send_with_continuation
from app.jsonutil import extract_json_object
from app.models.resources import ResourceSuggestion

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
RETRIEVE_PROMPT = (_PROMPTS_DIR / "resources.txt").read_text().strip()
VALIDATE_PROMPT = (_PROMPTS_DIR / "validate_resources.txt").read_text().strip()


async def retrieve_resources(question_md: str, answer_md: str) -> list[dict]:
    client = get_client()
    user_input = f"Question: {question_md}\n\nAnswer: {answer_md}"

    start = time.monotonic()
    logger.info("Claude retrieve call starting (model=claude-sonnet-4-6)")
    async with asyncio.timeout(180):
        raw, response = await send_with_continuation(
            client,
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=RETRIEVE_PROMPT,
            tools=[WEB_SEARCH_TOOL],
            messages=[{"role": "user", "content": user_input}],
        )
    elapsed = time.monotonic() - start
    logger.info(
        "Claude retrieve call completed in %.1fs (input_tokens=%d, output_tokens=%d)",
        elapsed,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    try:
        data = extract_json_object(raw)
        suggestions = [ResourceSuggestion(**r) for r in data["resources"]]
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Resource retrieval parse failed: %s — raw: %.500s", e, raw)
        return []

    logger.info("Parsed %d resource suggestions", len(suggestions))
    return [s.model_dump(exclude_none=True) for s in suggestions]


async def validate_resources(question_md: str, answer_md: str, resources: list[dict]) -> list[dict]:
    if len(resources) <= 2:
        logger.info("Skipping validation: only %d resources (<=2)", len(resources))
        return resources

    client = get_client()
    resources_text = json.dumps(resources, indent=2)
    user_input = (
        f"Question: {question_md}\n\nAnswer: {answer_md}\n\nCandidate resources:\n{resources_text}"
    )

    start = time.monotonic()
    logger.info("Claude validate call starting with %d candidates", len(resources))
    async with asyncio.timeout(180):
        raw, response = await send_with_continuation(
            client,
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=VALIDATE_PROMPT,
            tools=[WEB_SEARCH_TOOL],
            messages=[{"role": "user", "content": user_input}],
        )
    elapsed = time.monotonic() - start
    logger.info(
        "Claude validate call completed in %.1fs (input_tokens=%d, output_tokens=%d)",
        elapsed,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    try:
        data = extract_json_object(raw)
        validated = [ResourceSuggestion(**r) for r in data["resources"]]
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Resource validation parse failed: %s — raw: %.500s", e, raw)
        return resources

    logger.info("Validated down to %d resources from %d candidates", len(validated), len(resources))
    return [v.model_dump(exclude_none=True) for v in validated]
