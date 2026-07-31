import asyncio
import logging
from pathlib import Path

from pydantic import BaseModel

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
from app.models.candidates import Agent
from app.retry import with_retries
from app.services.answer_text import (
    MAX_ANSWER_LEN,
    enforce_length,
    revise_with_claude,
    revise_with_gemini,
    revise_with_gpt4,
)

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_SYSTEM_PROMPT = (_PROMPTS_DIR / "answer_generator.txt").read_text().strip()

_PROVIDERS = ["Claude", "GPT-4o", "Gemini"]


class GeneratedAnswer(BaseModel):
    agent: Agent
    answer_md: str


def _parse_answer(raw: str) -> str:
    """Pull the answer out of the JSON envelope, or accept a bare prose answer.

    Search-enabled models sometimes ignore the JSON instruction and simply
    answer the question. The prose is the thing we wanted, so take it rather
    than dropping the provider over an envelope.
    """
    try:
        data = extract_json_object(raw)
    except ValueError:
        # Only genuine prose is safe to pass through — a JSON envelope we
        # failed to parse would surface as visible braces in the answer.
        if raw.lstrip().startswith(("{", "```")):
            raise
        logger.info("Answer came back as prose rather than JSON; using it as-is")
        return raw
    answer = data.get("answerMd")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Response JSON has no answerMd")
    return answer


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
    answer = await enforce_length(
        answer, revise_with_claude, limit=MAX_ANSWER_LEN, label="Claude answer"
    )
    return GeneratedAnswer(agent=Agent.CLAUDE, answer_md=answer)


async def _generate_gpt4(question_md: str) -> GeneratedAnswer:
    logger.info("Requesting answer from GPT-4o")
    raw = await openai_create_text(
        model="gpt-4o",
        system=_SYSTEM_PROMPT,
        user=question_md,
        max_output_tokens=2048,
        json_object=True,
    )
    if not raw:
        raise ValueError("GPT-4o returned empty content")
    answer = _parse_answer(raw)
    answer = await enforce_length(
        answer, revise_with_gpt4, limit=MAX_ANSWER_LEN, label="GPT-4o answer"
    )
    return GeneratedAnswer(agent=Agent.GPT4, answer_md=answer)


async def _generate_gemini(question_md: str) -> GeneratedAnswer:
    logger.info("Requesting answer from Gemini")
    raw = await gemini_generate_text(
        model="gemini-2.5-flash",
        contents=question_md,
        system=_SYSTEM_PROMPT,
        max_output_tokens=4096,
    )
    answer = _parse_answer(raw)
    answer = await enforce_length(
        answer, revise_with_gemini, limit=MAX_ANSWER_LEN, label="Gemini answer"
    )
    return GeneratedAnswer(agent=Agent.GEMINI, answer_md=answer)


async def generate_answers(question_md: str) -> list[GeneratedAnswer]:
    async with asyncio.timeout(180):
        results = await asyncio.gather(
            with_retries(
                lambda: _generate_claude(question_md), label="Claude answer", max_retries=1
            ),
            with_retries(lambda: _generate_gpt4(question_md), label="GPT-4o answer", max_retries=1),
            with_retries(
                lambda: _generate_gemini(question_md), label="Gemini answer", max_retries=1
            ),
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
