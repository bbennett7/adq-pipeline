import asyncio
import logging
from pathlib import Path

from pydantic import ValidationError

from app.clients.anthropic import get_client, send_with_continuation
from app.jsonutil import extract_json_object
from app.models.moments import Moment
from app.models.sources import SourceItem

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "zeitgeist.txt").read_text().strip()

MAX_MOMENTS = 5


def _build_user_prompt(sources: list[SourceItem]) -> str:
    """Group headlines by source, preserving each feed's hot/recency order.

    Position within a feed is the popularity signal (Reddit RSS carries no
    upvote counts), and grouping makes cross-feed repetition visible.
    """
    by_source: dict[str, list[SourceItem]] = {}
    for s in sources:
        by_source.setdefault(s.source, []).append(s)
    blocks = []
    for name, items in by_source.items():
        lines = "\n".join(f"  {i + 1}. {s.title}" for i, s in enumerate(items))
        blocks.append(f"{name}:\n{lines}")
    return "Today's source material, ranked within each feed:\n\n" + "\n\n".join(blocks)


def _parse_moments(raw: str) -> list[Moment]:
    data = extract_json_object(raw)
    moments: list[Moment] = []
    for i, m in enumerate(data.get("moments", [])):
        try:
            moments.append(Moment(**m))
        except (ValidationError, TypeError) as e:
            logger.warning("Skipping invalid moment %d: %s", i, e)
    return moments[:MAX_MOMENTS]


async def detect_moments(sources: list[SourceItem]) -> list[Moment]:
    """Cluster today's headlines into cultural moments.

    Fail-open: moment detection must never kill a run — on any failure the
    generators simply run without moment context.
    """
    if not sources:
        return []
    try:
        client = get_client()
        async with asyncio.timeout(120):
            raw, _ = await send_with_continuation(
                client,
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_user_prompt(sources)}],
            )
        moments = _parse_moments(raw)
        logger.info(
            "Zeitgeist: %d moment(s) detected (%d strong): %s",
            len(moments),
            sum(1 for m in moments if m.strength == "strong"),
            [m.title for m in moments],
        )
        return moments
    except Exception:
        logger.warning("Zeitgeist detection failed, proceeding without moments", exc_info=True)
        return []
