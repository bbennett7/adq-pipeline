import asyncio
import logging
from pathlib import Path

from google.genai import types
from pydantic import BaseModel

from app.clients.anthropic import (
    WEB_SEARCH_TOOL,
    send_with_continuation,
)
from app.clients.anthropic import (
    get_client as get_anthropic,
)
from app.clients.gemini import get_client as get_gemini
from app.clients.openai import get_client as get_openai
from app.jsonutil import extract_json_object
from app.models.candidates import Agent

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_SYSTEM_PROMPT = (_PROMPTS_DIR / "answer_generator.txt").read_text().strip()

_MAX_ANSWER_LEN = 1000
_PROVIDERS = ["Claude", "GPT-4o", "Gemini"]


class GeneratedAnswer(BaseModel):
    agent: Agent
    answer_md: str


def _parse_answer(raw: str) -> str:
    data = extract_json_object(raw)
    return data["answerMd"]


def _truncate_at_sentence(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    truncated = text[:limit]
    for i in range(len(truncated) - 1, max(limit // 2, -1), -1):
        if truncated[i] in ".!?" and (i + 1 >= len(truncated) or truncated[i + 1] in " \n"):
            return truncated[: i + 1]
    last_space = truncated.rfind(" ")
    if last_space > limit // 2:
        return truncated[:last_space]
    return truncated


_REVISE_PROMPT = (
    "The following answer is too long. Rewrite it to be under {limit} characters "
    "while preserving the key insight and markdown formatting. "
    "Return ONLY the revised answer text, nothing else.\n\n{answer}"
)


async def _revise_claude(answer: str) -> str:
    client = get_anthropic()
    raw, _ = await send_with_continuation(
        client,
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": _REVISE_PROMPT.format(limit=_MAX_ANSWER_LEN, answer=answer),
            },
        ],
    )
    return raw.strip()


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


async def _ensure_within_limit(answer: str, revise_fn) -> str:
    if len(answer) <= _MAX_ANSWER_LEN:
        return answer
    logger.info(
        "Answer too long (%d chars), requesting revision via %s",
        len(answer),
        revise_fn.__name__,
    )
    try:
        revised = await revise_fn(answer)
        if len(revised) <= _MAX_ANSWER_LEN:
            logger.info("Revised: %d -> %d chars", len(answer), len(revised))
            return revised
        logger.warning("Still too long after revision (%d chars)", len(revised))
        answer = revised
    except Exception as e:
        logger.warning("Revision failed (%s), truncating at sentence", e)
    return _truncate_at_sentence(answer, _MAX_ANSWER_LEN)


async def _generate_claude(question_md: str) -> GeneratedAnswer:
    logger.info("Requesting answer from Claude")
    client = get_anthropic()
    raw, _response = await send_with_continuation(
        client,
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": question_md}],
    )
    answer = _parse_answer(raw)
    answer = await _ensure_within_limit(answer, _revise_claude)
    return GeneratedAnswer(agent=Agent.CLAUDE, answer_md=answer)


async def _generate_gpt4(question_md: str) -> GeneratedAnswer:
    logger.info("Requesting answer from GPT-4o")
    client = get_openai()
    # No web search here: gpt-4o rejects web_search_options, and the
    # search-preview models reject response_format.
    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": question_md},
        ],
    )
    raw = response.choices[0].message.content
    if raw is None:
        raise ValueError("GPT-4o returned empty content")
    answer = _parse_answer(raw)
    answer = await _ensure_within_limit(answer, _revise_gpt4)
    return GeneratedAnswer(agent=Agent.GPT4, answer_md=answer)


async def _generate_gemini(question_md: str) -> GeneratedAnswer:
    logger.info("Requesting answer from Gemini")
    client = get_gemini()
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=question_md,
        # Gemini rejects google_search combined with a JSON response mime
        # type, so rely on the prompt for JSON shape and strip fences on parse.
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=4096,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    raw = response.text
    if not raw:
        raise ValueError("Gemini returned empty content")
    answer = _parse_answer(raw)
    answer = await _ensure_within_limit(answer, _revise_gemini)
    return GeneratedAnswer(agent=Agent.GEMINI, answer_md=answer)


async def generate_answers(question_md: str) -> list[GeneratedAnswer]:
    async with asyncio.timeout(120):
        results = await asyncio.gather(
            _generate_claude(question_md),
            _generate_gpt4(question_md),
            _generate_gemini(question_md),
            return_exceptions=True,
        )

    answers: list[GeneratedAnswer] = []
    failures = 0
    for provider, result in zip(_PROVIDERS, results, strict=True):
        if isinstance(result, Exception):
            failures += 1
            logger.error("Answer generation failed for %s: %s", provider, result)
            continue
        answers.append(result)

    if not answers:
        raise RuntimeError("All three answer generation providers failed")
    if failures:
        logger.warning("%d/%d answer generation providers failed", failures, len(results))

    successes = len(results) - failures
    logger.info("Generated %d answers from %d/%d providers", len(answers), successes, len(results))
    return answers
