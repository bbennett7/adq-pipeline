import logging

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(
            api_key=get_settings().anthropic_api_key,
            timeout=180.0,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def extract_text(response) -> str:
    """Return the last text block from the response, skipping tool-use/search blocks."""
    last_text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            last_text = block.text
    return last_text


async def send_with_continuation(
    client: anthropic.AsyncAnthropic,
    *,
    max_continuations: int = 1,
    **kwargs,
) -> tuple[str, object]:
    """Send a message and automatically continue if the response is truncated.

    Returns (extracted_text, final_response).
    """
    response = await client.messages.create(**kwargs)
    text = extract_text(response)

    continuations = 0
    while response.stop_reason == "max_tokens" and continuations < max_continuations:
        continuations += 1
        logger.warning(
            "Response truncated at %d output tokens, requesting continuation %d/%d",
            response.usage.output_tokens,
            continuations,
            max_continuations,
        )
        messages = list(kwargs.get("messages", []))
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": "Continue exactly where you left off."})

        continuation_kwargs = {**kwargs, "messages": messages}
        continuation_kwargs.pop("tools", None)

        response = await client.messages.create(**continuation_kwargs)
        text += extract_text(response)

    if response.stop_reason == "max_tokens":
        logger.warning("Response still truncated after %d continuations", max_continuations)

    return text, response
