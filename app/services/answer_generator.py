import asyncio
import json
import logging
from pathlib import Path

from google.genai import types
from pydantic import BaseModel

from app.clients.anthropic import get_client as get_anthropic
from app.clients.gemini import get_client as get_gemini
from app.clients.openai import get_client as get_openai
from app.models.candidates import Agent

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_SYSTEM_PROMPT = (_PROMPTS_DIR / "answer_generator.txt").read_text().strip()

_MAX_ANSWER_LEN = 1000
_PROVIDERS = ["Claude", "GPT-4o", "Gemini"]


class _AnswerResponse(BaseModel):
    answerMd: str  # noqa: N815


class GeneratedAnswer(BaseModel):
    agent: Agent
    answer_md: str


def _strip_markdown_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _parse_answer(raw: str) -> str:
    cleaned = _strip_markdown_fences(raw)
    data = json.loads(cleaned)
    return data["answerMd"]


async def _generate_claude(question_md: str) -> GeneratedAnswer:
    logger.info("Requesting answer from Claude")
    client = get_anthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question_md}],
    )
    raw = response.content[0].text
    answer = _parse_answer(raw)
    if len(answer) > _MAX_ANSWER_LEN:
        answer = answer[:_MAX_ANSWER_LEN]
    return GeneratedAnswer(agent=Agent.CLAUDE, answer_md=answer)


async def _generate_gpt4(question_md: str) -> GeneratedAnswer:
    logger.info("Requesting answer from GPT-4o")
    client = get_openai()
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
    if len(answer) > _MAX_ANSWER_LEN:
        answer = answer[:_MAX_ANSWER_LEN]
    return GeneratedAnswer(agent=Agent.GPT4, answer_md=answer)


async def _generate_gemini(question_md: str) -> GeneratedAnswer:
    logger.info("Requesting answer from Gemini")
    client = get_gemini()
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=question_md,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_AnswerResponse,
            max_output_tokens=4096,
        ),
    )
    raw = response.text
    if not raw:
        raise ValueError("Gemini returned empty content")
    answer = _parse_answer(raw)
    if len(answer) > _MAX_ANSWER_LEN:
        answer = answer[:_MAX_ANSWER_LEN]
    return GeneratedAnswer(agent=Agent.GEMINI, answer_md=answer)


async def generate_answers(question_md: str) -> list[GeneratedAnswer]:
    async with asyncio.timeout(60):
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
