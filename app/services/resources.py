import asyncio
import json
import logging
import re
from pathlib import Path

from app.clients.anthropic import get_client
from app.models.resources import ResourceSuggestion

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
RETRIEVE_PROMPT = (_PROMPTS_DIR / "resources.txt").read_text().strip()
VALIDATE_PROMPT = (_PROMPTS_DIR / "validate_resources.txt").read_text().strip()

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    m = _CODE_FENCE_RE.match(text.strip())
    return m.group(1) if m else text


async def retrieve_resources(question_md: str, answer_md: str) -> list[dict]:
    """Ask Claude to suggest relevant resources for a question/answer pair.

    Returns a list of resource dicts (url, label, source, author?).
    On failure, returns an empty list — resource suggestions are non-critical.
    """
    client = get_client()
    user_input = f"Question: {question_md}\n\nAnswer: {answer_md}"

    async with asyncio.timeout(120):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=RETRIEVE_PROMPT,
            messages=[{"role": "user", "content": user_input}],
        )
    raw = response.content[0].text

    try:
        data = json.loads(_strip_code_fences(raw))
        suggestions = [ResourceSuggestion(**r) for r in data["resources"]]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.error("Resource retrieval parse failed: %s — raw: %.500s", e, raw)
        return []

    return [s.model_dump(exclude_none=True) for s in suggestions]


async def validate_resources(question_md: str, answer_md: str, resources: list[dict]) -> list[dict]:
    """Select the best 2-4 resources from a candidate list for a question/answer pair.

    Returns the filtered/ranked resource dicts.
    On failure, returns the original list unchanged.
    """
    if len(resources) <= 2:
        return resources

    client = get_client()
    resources_text = json.dumps(resources, indent=2)
    user_input = (
        f"Question: {question_md}\n\nAnswer: {answer_md}\n\nCandidate resources:\n{resources_text}"
    )

    async with asyncio.timeout(120):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=VALIDATE_PROMPT,
            messages=[{"role": "user", "content": user_input}],
        )
    raw = response.content[0].text

    try:
        data = json.loads(_strip_code_fences(raw))
        validated = [ResourceSuggestion(**r) for r in data["resources"]]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.error("Resource validation parse failed: %s — raw: %.500s", e, raw)
        return resources

    return [v.model_dump(exclude_none=True) for v in validated]
