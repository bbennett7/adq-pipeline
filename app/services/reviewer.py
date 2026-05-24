import json
import logging
from pathlib import Path

from app.clients.anthropic import get_client
from app.models.candidates import GeneratedCandidate, ReviewedCandidate

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "reviewer.txt").read_text().strip()

TOP_N = 3


def _build_review_input(candidates: list[GeneratedCandidate]) -> str:
    entries = []
    for i, c in enumerate(candidates):
        entries.append(
            f"--- Candidate {i} (model: {c.agent.value}) ---\n"
            f"Question: {c.question_md}\n"
            f"Answer: {c.answer_md}"
        )
    return "\n\n".join(entries)


def _strip_markdown_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _parse_review(raw: str, candidates: list[GeneratedCandidate]) -> list[ReviewedCandidate]:
    data = json.loads(_strip_markdown_fences(raw))
    scored = data["reviewed"]

    seen: set[int] = set()
    reviewed = []
    for entry in scored:
        idx = entry["index"]
        if idx < 0 or idx >= len(candidates):
            logger.warning("Review returned out-of-range index %d, skipping", idx)
            continue
        if idx in seen:
            logger.warning("Review returned duplicate index %d, skipping", idx)
            continue
        seen.add(idx)
        c = candidates[idx]
        reviewed.append(
            ReviewedCandidate(
                agent=c.agent,
                question_md=c.question_md,
                answer_md=c.answer_md,
                score=max(1, min(10, int(entry["score"]))),
                review_reason=str(entry["reason"])[:200],
            )
        )

    reviewed.sort(key=lambda r: r.score, reverse=True)
    return reviewed[:TOP_N]


async def review_candidates(
    candidates: list[GeneratedCandidate],
) -> list[ReviewedCandidate]:
    """Score all candidates with Claude. Returns top 3 by score."""
    if not candidates:
        raise ValueError("No candidates to review")

    logger.info("Reviewing %d candidates", len(candidates))
    client = get_client()
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_review_input(candidates)}],
    )
    raw = response.content[0].text

    try:
        reviewed = _parse_review(raw, candidates)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error("Review parse failed: %s — raw: %.500s", e, raw)
        raise ValueError(f"Claude review returned unparseable response: {e}") from e

    if not reviewed:
        raise ValueError("Review produced zero valid candidates")

    logger.info(
        "Review complete — top %d scores: %s",
        len(reviewed),
        [r.score for r in reviewed],
    )
    return reviewed
