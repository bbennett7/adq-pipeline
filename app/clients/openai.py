import logging

import openai

from app.config import get_settings
from app.errors import TruncatedOutputError

logger = logging.getLogger(__name__)

_client: openai.AsyncOpenAI | None = None

WEB_SEARCH_TOOL = {"type": "web_search"}

# Remembers a model that has rejected the web search tool, so we stop paying
# for a round trip we already know will 400 on every subsequent call.
_web_search_unsupported: set[str] = set()


def get_client() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI(
            api_key=get_settings().openai_api_key,
            timeout=180.0,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def create_text(
    *,
    model: str,
    user: str,
    system: str | None = None,
    max_output_tokens: int,
    json_object: bool = False,
    web_search: bool = True,
) -> str:
    """Call the Responses API and return the model's text output.

    The Responses API is what gives GPT-4o web search — the older
    chat.completions endpoint rejects the tool outright, which is why GPT
    answers used to be stuck with training-data-only knowledge.

    The API refuses to combine web search with JSON mode. An up-to-date answer
    matters more than a guaranteed-parseable envelope, so when a caller asks
    for both, search wins and the JSON shape is left to the prompt —
    `extract_json_object` pulls the object back out of whatever prose wraps it.
    If a model turns out not to support the tool at all we retry once without
    it rather than losing the answer entirely.
    """
    client = get_client()
    kwargs: dict = {
        "model": model,
        "input": user,
        "max_output_tokens": max_output_tokens,
    }
    if system:
        kwargs["instructions"] = system

    use_search = web_search and model not in _web_search_unsupported
    if use_search:
        kwargs["tools"] = [WEB_SEARCH_TOOL]
        # Left to its own judgement the model skips the search and answers from
        # training data, which is the whole problem this is here to fix.
        kwargs["tool_choice"] = "required"
    elif json_object:
        # The word "json" has to appear in the input itself, not just the
        # instructions, or the API rejects the format outright.
        kwargs["text"] = {"format": {"type": "json_object"}}
        if "json" not in user.lower():
            kwargs["input"] = f"{user}\n\nRespond with a single JSON object."

    try:
        response = await client.responses.create(**kwargs)
    except openai.BadRequestError as e:
        if not use_search:
            raise
        logger.warning("%s rejected the web_search tool (%s); retrying without it", model, e)
        _web_search_unsupported.add(model)
        # tool_choice must go with the tools — "required" with an empty tool
        # list is itself a 400, which would sink the retry too.
        kwargs.pop("tools")
        kwargs.pop("tool_choice")
        if json_object:
            kwargs["text"] = {"format": {"type": "json_object"}}
            if "json" not in user.lower():
                kwargs["input"] = f"{user}\n\nRespond with a single JSON object."
        response = await client.responses.create(**kwargs)

    text = (response.output_text or "").strip()
    # The Responses API reports a budget overrun as an incomplete response and
    # still hands back the partial text, which reads as an answer that simply
    # stops mid-sentence. Fail the call so it can be retried.
    if getattr(response, "status", None) == "incomplete":
        reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
        raise TruncatedOutputError(
            f"OpenAI {model} response incomplete ({reason}) after {len(text)} chars"
        )
    return text
