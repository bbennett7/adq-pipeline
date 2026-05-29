import asyncio
import json
import logging
from pathlib import Path

from google.genai import types
from pydantic import BaseModel as _BaseModel
from pydantic import ValidationError

from app.clients.anthropic import get_client as get_anthropic
from app.clients.gemini import get_client as get_gemini
from app.clients.openai import get_client as get_openai
from app.models.candidates import Agent, GeneratedCandidate
from app.models.sources import SourceItem

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "generator.txt").read_text().strip()

_PROVIDERS = ["Claude", "GPT-4o", "Gemini"]


class _CandidateItem(_BaseModel):
    questionMd: str  # noqa: N815
    answerMd: str  # noqa: N815


class _GenerationResponse(_BaseModel):
    candidates: list[_CandidateItem]


def _build_user_prompt(sources: list[SourceItem]) -> str:
    if not sources:
        raise ValueError("Cannot generate candidates without source material")
    source_lines = [f"- {s.title} ({s.source})" for s in sources[:20]]
    return "Today's source material:\n" + "\n".join(source_lines)


def _strip_markdown_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


_MAX_ANSWER_LEN = 1000


def _parse_raw_json(raw: str) -> list[dict]:
    cleaned = _strip_markdown_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Unparseable response: {e}") from e
    return data.get("candidates", [])


def _build_candidates(raw_items: list[dict], agent: Agent) -> list[GeneratedCandidate]:
    candidates: list[GeneratedCandidate] = []
    for i, c in enumerate(raw_items):
        try:
            candidates.append(
                GeneratedCandidate(
                    agent=agent,
                    question_md=c["questionMd"],
                    answer_md=c["answerMd"],
                )
            )
        except (ValidationError, KeyError, TypeError) as e:
            logger.warning("Skipping invalid candidate %d from %s: %s", i, agent, e)
    return candidates


def _needs_revision(raw_items: list[dict]) -> list[dict]:
    return [c for c in raw_items if len(c.get("answerMd", "")) > _MAX_ANSWER_LEN]


_REVISE_PROMPT = (
    "The following answer is too long. Rewrite it to be under {limit} characters "
    "while preserving the key insight and markdown formatting. "
    "Return ONLY the revised answer text, nothing else.\n\n{answer}"
)


async def _revise_claude(answer: str) -> str:
    client = get_anthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": _REVISE_PROMPT.format(limit=_MAX_ANSWER_LEN, answer=answer),
            },
        ],
    )
    return response.content[0].text.strip()


async def _revise_gpt4(answer: str) -> str:
    client = get_openai()
    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": _REVISE_PROMPT.format(limit=_MAX_ANSWER_LEN, answer=answer),
            },
        ],
    )
    return (response.choices[0].message.content or "").strip()


async def _revise_gemini(answer: str) -> str:
    client = get_gemini()
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=_REVISE_PROMPT.format(limit=_MAX_ANSWER_LEN, answer=answer),
        config=types.GenerateContentConfig(max_output_tokens=1024),
    )
    return (response.text or "").strip()


async def _revise_overlong(raw_items: list[dict], revise_fn) -> None:
    for c in _needs_revision(raw_items):
        original_len = len(c["answerMd"])
        logger.info("Revising overlong answer (%d chars) via %s", original_len, revise_fn.__name__)
        try:
            c["answerMd"] = await revise_fn(c["answerMd"])
            logger.info("Revised answer: %d -> %d chars", original_len, len(c["answerMd"]))
        except Exception as e:
            logger.warning("Revision failed, will skip candidate: %s", e)


async def _generate_claude(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    logger.info("Requesting candidates from Claude")
    client = get_anthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(sources)}],
    )
    raw = response.content[0].text
    try:
        raw_items = _parse_raw_json(raw)
    except ValueError:
        logger.error("Claude raw response: %.500s", raw)
        raise
    await _revise_overlong(raw_items, _revise_claude)
    candidates = _build_candidates(raw_items, Agent.CLAUDE)
    logger.info("Claude generated %d candidates", len(candidates))
    return candidates


async def _generate_gpt4(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    logger.info("Requesting candidates from GPT-4o")
    client = get_openai()
    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=4096,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(sources)},
        ],
    )
    raw = response.choices[0].message.content
    if raw is None:
        raise ValueError("GPT-4o returned empty content")
    try:
        raw_items = _parse_raw_json(raw)
    except ValueError:
        logger.error("GPT-4o raw response: %.500s", raw)
        raise
    await _revise_overlong(raw_items, _revise_gpt4)
    candidates = _build_candidates(raw_items, Agent.GPT4)
    logger.info("GPT-4o generated %d candidates", len(candidates))
    return candidates


async def _generate_gemini(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    logger.info("Requesting candidates from Gemini")
    client = get_gemini()
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=_build_user_prompt(sources),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_GenerationResponse,
            max_output_tokens=4096,
        ),
    )
    raw = response.text
    finish = response.candidates[0].finish_reason if response.candidates else None
    logger.info(
        "Gemini response: finish_reason=%s, length=%d chars",
        finish,
        len(raw) if raw else 0,
    )
    if not raw:
        raise ValueError("Gemini returned empty content")
    try:
        raw_items = _parse_raw_json(raw)
    except ValueError:
        logger.error("Gemini raw response (%d chars): %s", len(raw), raw)
        raise
    await _revise_overlong(raw_items, _revise_gemini)
    candidates = _build_candidates(raw_items, Agent.GEMINI)
    logger.info("Gemini generated %d candidates", len(candidates))
    return candidates


async def generate_candidates(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    """Run all three models in parallel, returning up to 6 candidates."""
    async with asyncio.timeout(300):
        results = await asyncio.gather(
            _generate_claude(sources),
            _generate_gpt4(sources),
            _generate_gemini(sources),
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
