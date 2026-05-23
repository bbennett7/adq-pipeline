import asyncio
import json
import logging
from pathlib import Path

from google.genai import types

from app.clients.anthropic import get_client as get_anthropic
from app.clients.gemini import get_client as get_gemini
from app.clients.openai import get_client as get_openai
from app.models.candidates import Agent, GeneratedCandidate
from app.models.sources import SourceItem

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "generator.txt").read_text().strip()

_PROVIDERS = ["Claude", "GPT-4o", "Gemini"]


def _build_user_prompt(sources: list[SourceItem]) -> str:
    if not sources:
        raise ValueError("Cannot generate candidates without source material")
    source_lines = [f"- {s.title} ({s.source})" for s in sources[:20]]
    return "Today's source material:\n" + "\n".join(source_lines)


def _parse_candidates(raw: str, agent: Agent) -> list[GeneratedCandidate]:
    try:
        data = json.loads(raw)
        return [
            GeneratedCandidate(
                agent=agent,
                question_md=c["questionMd"],
                answer_md=c["answerMd"],
            )
            for c in data["candidates"]
        ]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ValueError(f"{agent} returned unparseable response: {e}") from e


async def _generate_claude(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    logger.info("Requesting candidates from Claude")
    client = get_anthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(sources)}],
    )
    raw = response.content[0].text
    try:
        candidates = _parse_candidates(raw, Agent.CLAUDE)
    except ValueError:
        logger.error("Claude raw response: %.500s", raw)
        raise
    logger.info("Claude generated %d candidates", len(candidates))
    return candidates


async def _generate_gpt4(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    logger.info("Requesting candidates from GPT-4o")
    client = get_openai()
    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
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
        candidates = _parse_candidates(raw, Agent.GPT4)
    except ValueError:
        logger.error("GPT-4o raw response: %.500s", raw)
        raise
    logger.info("GPT-4o generated %d candidates", len(candidates))
    return candidates


async def _generate_gemini(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    logger.info("Requesting candidates from Gemini")
    client = get_gemini()
    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=_build_user_prompt(sources),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=1024,
        ),
    )
    raw = response.text
    try:
        candidates = _parse_candidates(raw, Agent.GEMINI)
    except ValueError:
        logger.error("Gemini raw response: %.500s", raw)
        raise
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
