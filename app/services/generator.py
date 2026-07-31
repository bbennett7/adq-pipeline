import asyncio
import logging
from pathlib import Path

from pydantic import ValidationError

from app.clients.anthropic import (
    WEB_SEARCH_TOOL,
    send_with_continuation,
)
from app.clients.anthropic import (
    get_client as get_anthropic,
)
from app.clients.gemini import generate_text as gemini_generate_text
from app.clients.openai import create_text as openai_create_text
from app.jsonutil import extract_json_object
from app.models.candidates import Agent, Category, GeneratedCandidate
from app.models.moments import Moment
from app.models.sources import SourceItem
from app.retry import with_retries
from app.services.answer_text import (
    MAX_ANSWER_LEN,
    enforce_length,
    revise_with_claude,
    revise_with_gemini,
    revise_with_gpt4,
    sanitize_answer,
)

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "generator.txt").read_text().strip()

_PROVIDERS = ["Claude", "GPT-4o", "Gemini"]


_MAX_PROMPT_ITEMS = 40
_MAX_PER_SOURCE = 3


def _sample_sources(sources: list[SourceItem]) -> list[SourceItem]:
    """Round-robin up to 3 headlines per source so every feed is represented.

    A flat sources[:N] slice would only ever show the first feeds fetched.
    """
    by_source: dict[str, list[SourceItem]] = {}
    for s in sources:
        by_source.setdefault(s.source, []).append(s)
    sampled: list[SourceItem] = []
    for rank in range(_MAX_PER_SOURCE):
        for items in by_source.values():
            if rank < len(items):
                sampled.append(items[rank])
                if len(sampled) >= _MAX_PROMPT_ITEMS:
                    return sampled
    return sampled


def _format_moments(moments: list[Moment]) -> str:
    if not moments:
        return (
            "\n\nToday's cultural moments: none detected — it's a quiet day. "
            "Do not strain for timeliness; favor discourse-aware and evergreen angles."
        )
    lines = []
    for m in moments:
        lines.append(
            f"- [{m.strength.value}] {m.title}\n"
            f"  why now: {m.why_now}\n"
            f"  teachable angle: {m.teachable_angle}"
        )
    return "\n\nToday's cultural moments (strongest first):\n" + "\n".join(lines)


def _format_topic(topic: str) -> str:
    return (
        f'\n\nOWNER-REQUESTED TOPIC: "{topic}"\n'
        "The site owner has asked for candidates about this specific topic today, "
        "so skip the usual moment-led selection. ALL 3 candidates must be about "
        "this topic, with the three categories serving as three distinct angles "
        'on it: "current" = what is happening with it in AI right now (use web '
        'search to check), "cultural" = the discourse, buzzwords, or vibes around '
        'it, "foundational" = the core concept underneath it, explained from '
        "scratch. The three questions must still cover clearly different "
        "territory from each other, and every question must still teach the "
        "reader something about AI — if the topic is broad, find its AI angle."
    )


def _build_user_prompt(
    sources: list[SourceItem],
    recent_questions: list[str],
    moments: list[Moment] | None = None,
    topic: str | None = None,
) -> str:
    if not sources:
        raise ValueError("Cannot generate candidates without source material")
    source_lines = [f"- {s.title} ({s.source})" for s in _sample_sources(sources)]
    prompt = "Today's source material:\n" + "\n".join(source_lines)
    prompt += _format_topic(topic) if topic else _format_moments(moments or [])
    if recent_questions:
        recent_lines = [f"- {q}" for q in recent_questions]
        prompt += (
            "\n\nQuestions already published or offered as candidates recently "
            "(including earlier today) — every candidate you write must be on a "
            "clearly different topic from ALL of these, not a rephrasing:\n"
            + "\n".join(recent_lines)
        )
    return prompt


def _parse_raw_json(raw: str) -> list[dict]:
    try:
        data = extract_json_object(raw)
    except ValueError as e:
        raise ValueError(f"Unparseable response: {e}") from e
    return data.get("candidates", [])


def _parse_category(raw: object) -> Category:
    try:
        return Category(str(raw).strip().lower())
    except ValueError:
        return Category.CULTURAL


def _build_candidates(raw_items: list[dict], agent: Agent) -> list[GeneratedCandidate]:
    candidates: list[GeneratedCandidate] = []
    for i, c in enumerate(raw_items):
        try:
            candidates.append(
                GeneratedCandidate(
                    agent=agent,
                    category=_parse_category(c.get("category")),
                    question_md=sanitize_answer(c["questionMd"]),
                    answer_md=c["answerMd"],
                )
            )
        except (ValidationError, KeyError, TypeError) as e:
            logger.warning("Skipping invalid candidate %d from %s: %s", i, agent, e)
    return candidates


async def _normalize_answers(raw_items: list[dict], revise_fn, label: str) -> None:
    """Clean provider markup out of every answer and bring over-long ones down."""
    for c in raw_items:
        answer = c.get("answerMd")
        if not isinstance(answer, str):
            continue
        c["answerMd"] = await enforce_length(
            answer, revise_fn, limit=MAX_ANSWER_LEN, label=f"{label} answer"
        )


async def _generate_claude(
    sources: list[SourceItem],
    recent_questions: list[str],
    moments: list[Moment] | None = None,
    topic: str | None = None,
) -> list[GeneratedCandidate]:
    logger.info("Requesting candidates from Claude")
    client = get_anthropic()
    raw, response = await send_with_continuation(
        client,
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        tools=[WEB_SEARCH_TOOL],
        messages=[
            {
                "role": "user",
                "content": _build_user_prompt(sources, recent_questions, moments, topic),
            }
        ],
    )
    try:
        raw_items = _parse_raw_json(raw)
    except ValueError:
        logger.error("Claude raw response: %.500s", raw)
        raise
    await _normalize_answers(raw_items, revise_with_claude, "Claude")
    candidates = _build_candidates(raw_items, Agent.CLAUDE)
    logger.info("Claude generated %d candidates", len(candidates))
    return candidates


async def _generate_gpt4(
    sources: list[SourceItem],
    recent_questions: list[str],
    moments: list[Moment] | None = None,
    topic: str | None = None,
) -> list[GeneratedCandidate]:
    logger.info("Requesting candidates from GPT-4o")
    raw = await openai_create_text(
        model="gpt-4o",
        system=SYSTEM_PROMPT,
        user=_build_user_prompt(sources, recent_questions, moments, topic),
        max_output_tokens=4096,
        json_object=True,
    )
    if not raw:
        raise ValueError("GPT-4o returned empty content")
    try:
        raw_items = _parse_raw_json(raw)
    except ValueError:
        logger.error("GPT-4o raw response: %.500s", raw)
        raise
    await _normalize_answers(raw_items, revise_with_gpt4, "GPT-4o")
    candidates = _build_candidates(raw_items, Agent.GPT4)
    logger.info("GPT-4o generated %d candidates", len(candidates))
    return candidates


async def _generate_gemini(
    sources: list[SourceItem],
    recent_questions: list[str],
    moments: list[Moment] | None = None,
    topic: str | None = None,
) -> list[GeneratedCandidate]:
    logger.info("Requesting candidates from Gemini")
    raw = await gemini_generate_text(
        model="gemini-2.5-flash",
        contents=_build_user_prompt(sources, recent_questions, moments, topic),
        system=SYSTEM_PROMPT,
        max_output_tokens=8192,
    )
    try:
        raw_items = _parse_raw_json(raw)
    except ValueError:
        logger.error("Gemini raw response (%d chars): %s", len(raw), raw)
        raise
    await _normalize_answers(raw_items, revise_with_gemini, "Gemini")
    candidates = _build_candidates(raw_items, Agent.GEMINI)
    logger.info("Gemini generated %d candidates", len(candidates))
    return candidates


async def generate_candidates(
    sources: list[SourceItem],
    recent_questions: list[str] | None = None,
    moments: list[Moment] | None = None,
    topic: str | None = None,
) -> list[GeneratedCandidate]:
    """Run all three models in parallel, returning up to 9 candidates."""
    recent = recent_questions or []
    async with asyncio.timeout(420):
        results = await asyncio.gather(
            with_retries(
                lambda: _generate_claude(sources, recent, moments, topic),
                label="Claude generation",
            ),
            with_retries(
                lambda: _generate_gpt4(sources, recent, moments, topic),
                label="GPT-4o generation",
            ),
            with_retries(
                lambda: _generate_gemini(sources, recent, moments, topic),
                label="Gemini generation",
            ),
            return_exceptions=True,
        )
    candidates: list[GeneratedCandidate] = []
    failures = 0
    for provider, result in zip(_PROVIDERS, results, strict=True):
        if isinstance(result, Exception):
            failures += 1
            logger.error("Generation failed for %s: %s", provider, result)
            continue
        candidates.extend(result)
    if not candidates:
        raise RuntimeError("All three generation providers failed")
    if failures:
        logger.warning("%d/%d generation providers failed", failures, len(results))
    successes = len(results) - failures
    logger.info(
        "Generated %d total candidates from %d/%d providers",
        len(candidates),
        successes,
        len(results),
    )
    return candidates
