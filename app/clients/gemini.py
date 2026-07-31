import logging

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=get_settings().google_api_key,
            http_options={"timeout": 180_000},
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        # genai.Client does not expose a close/aclose method;
        # dropping the reference lets GC clean up the underlying httpx transport.
        _client = None


def extract_text(response) -> str:
    """Concatenate the answer parts, skipping thought summaries.

    `response.text` returns None whenever the candidate holds anything other
    than plain text parts, which is how a perfectly good answer used to come
    back as "Gemini returned empty content".
    """
    if not response.candidates:
        return ""
    content = response.candidates[0].content
    if content is None or not content.parts:
        return ""
    return "".join(
        part.text
        for part in content.parts
        if getattr(part, "text", None) and not getattr(part, "thought", False)
    )


async def generate_text(
    *,
    model: str,
    contents: str,
    system: str | None = None,
    max_output_tokens: int,
    web_search: bool = True,
) -> str:
    """Generate text with thinking disabled and Google Search on by default.

    2.5 models think by default and thinking tokens are billed against
    `max_output_tokens` — a long reasoning pass would consume the whole budget
    and return a candidate with no answer in it. Nothing here needs a reasoning
    pass, so the budget is set to zero and the full allowance goes to the
    answer.
    """
    # Google Search cannot be combined with a JSON response mime type, so
    # callers that need JSON ask for it in the prompt instead.
    tools = [types.Tool(google_search=types.GoogleSearch())] if web_search else None
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        tools=tools,
    )

    response = await get_client().aio.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    text = extract_text(response)
    finish_reason = response.candidates[0].finish_reason if response.candidates else None
    logger.info("Gemini %s: finish_reason=%s, %d chars", model, finish_reason, len(text))
    if not text:
        raise ValueError(f"Gemini returned empty content (finish_reason={finish_reason})")
    return text.strip()
