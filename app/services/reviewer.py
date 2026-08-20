import asyncio
import logging
from pathlib import Path

from app.clients.anthropic import WEB_SEARCH_TOOL, get_client, send_with_continuation
from app.jsonutil import extract_json_object
from app.models.candidates import Category, GeneratedCandidate, ReviewedCandidate
from app.models.moments import Moment
from app.retry import with_retries

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "reviewer.txt").read_text().strip()

TOP_N = 6
# Every slate has to give the owner a real choice across all three ways a
# question gets found — today's story, the ongoing discourse, and the evergreen
# gaps — so one slot of each is reserved before score ranking fills the rest.
# Without this, a day where the news scores well produces six variations on the
# same story, and the site reads as a news digest instead of an explainer.
GUARANTEED_CATEGORIES = (Category.CURRENT, Category.CULTURAL, Category.FOUNDATIONAL)


def _balanced_top_n(reviewed: list[ReviewedCandidate], n: int) -> list[ReviewedCandidate]:
    """Take the top n by score, but never at the cost of losing a whole category.

    The best candidate of each guaranteed category is seated first; the
    remaining slots go to the highest scorers. The result stays sorted by
    score, so "choose for me" and the owner's eye still see the best first.
    """
    # Seat by position, not by value: two candidates can compare equal as models
    # (same category and score, and identical text does happen across providers),
    # and membership-testing the objects would silently collapse them into one
    # and hand back a short slate.
    by_score = sorted(range(len(reviewed)), key=lambda i: reviewed[i].score, reverse=True)
    seated: list[int] = []
    for category in GUARANTEED_CATEGORIES:
        best = next((i for i in by_score if reviewed[i].category == category), None)
        if best is not None and len(seated) < n:
            seated.append(best)
    for i in by_score:
        if len(seated) >= n:
            break
        if i not in seated:
            seated.append(i)
    slate = [reviewed[i] for i in seated]
    missing = [c.value for c in GUARANTEED_CATEGORIES if not any(r.category == c for r in slate)]
    if missing:
        logger.warning("Slate has no %s candidate — none was generated", ", ".join(missing))
    return sorted(slate, key=lambda r: r.score, reverse=True)


def _build_review_input(
    candidates: list[GeneratedCandidate],
    recent_questions: list[str],
    moments: list[Moment] | None = None,
    near_repeats: dict[int, str] | None = None,
    topic: str | None = None,
) -> str:
    entries = []
    for i, c in enumerate(candidates):
        entry = (
            f"--- Candidate {i} (model: {c.agent.value}, category: {c.category.value}) ---\n"
            f"Question: {c.question_md}\n"
            f"Answer: {c.answer_md}"
        )
        repeat_of = (near_repeats or {}).get(i)
        if repeat_of:
            entry += (
                f"\nNOTE: flagged by the similarity gate as a near-repeat of "
                f'"{repeat_of}" — it was kept only to fill the slate. '
                f"Score it 3 or lower unless the angle is genuinely new."
            )
        entries.append(entry)
    review_input = "\n\n".join(entries)
    if topic:
        review_input += (
            f'\n\nOWNER-REQUESTED TOPIC: "{topic}" — these candidates were '
            "generated on demand because the site owner asked for questions "
            "about this topic. Do not penalize them for ignoring today's news "
            "or cultural moments; score for how well each one teaches the "
            "reader something about the requested topic. A candidate that "
            "drifts off the topic should score poorly."
        )
    if moments:
        moment_lines = [
            f"- [{m.strength.value}] {m.title} (teachable angle: {m.teachable_angle})"
            for m in moments
        ]
        review_input += (
            "\n\nToday's detected cultural moments — reward candidates that "
            "genuinely engage one (especially a strong one); do not reward "
            "name-dropping without substance:\n" + "\n".join(moment_lines)
        )
    if recent_questions:
        recent_lines = [f"- {q}" for q in recent_questions]
        review_input += (
            "\n\nQuestions already published or offered as candidates recently "
            "(penalize candidates that repeat these topics):\n" + "\n".join(recent_lines)
        )
    return review_input


def _parse_review(raw: str, candidates: list[GeneratedCandidate]) -> list[ReviewedCandidate]:
    data = extract_json_object(raw)
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
                category=c.category,
                question_md=c.question_md,
                answer_md=c.answer_md,
                score=max(1, min(10, int(entry["score"]))),
                review_reason=f"[{c.category.value}] {entry['reason']}"[:200],
            )
        )

    return _balanced_top_n(reviewed, TOP_N)


async def _review_once(
    candidates: list[GeneratedCandidate],
    recent_questions: list[str],
    moments: list[Moment] | None = None,
    near_repeats: dict[int, str] | None = None,
    topic: str | None = None,
) -> list[ReviewedCandidate]:
    client = get_client()
    async with asyncio.timeout(180):
        raw, _response = await send_with_continuation(
            client,
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[WEB_SEARCH_TOOL],
            messages=[
                {
                    "role": "user",
                    "content": _build_review_input(
                        candidates, recent_questions, moments, near_repeats, topic
                    ),
                }
            ],
        )

    try:
        reviewed = _parse_review(raw, candidates)
    except (ValueError, KeyError, TypeError) as e:
        logger.error("Review parse failed: %s — raw: %.500s", e, raw)
        raise ValueError(f"Claude review returned unparseable response: {e}") from e

    if not reviewed:
        raise ValueError("Review produced zero valid candidates")
    return reviewed


async def review_candidates(
    candidates: list[GeneratedCandidate],
    recent_questions: list[str] | None = None,
    moments: list[Moment] | None = None,
    near_repeats: dict[int, str] | None = None,
    topic: str | None = None,
) -> list[ReviewedCandidate]:
    """Score all candidates with Claude. Returns a category-balanced top TOP_N."""
    if not candidates:
        raise ValueError("No candidates to review")

    logger.info("Reviewing %d candidates", len(candidates))
    reviewed = await with_retries(
        lambda: _review_once(candidates, recent_questions or [], moments, near_repeats, topic),
        label="Candidate review",
    )
    logger.info(
        "Review complete — slate of %d: %s",
        len(reviewed),
        [f"{r.category.value}:{r.score}" for r in reviewed],
    )
    return reviewed
