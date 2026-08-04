from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.clients.anthropic import send_with_continuation
from app.errors import TruncatedOutputError


def _response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(output_tokens=len(text)),
    )


def _client(*responses):
    return SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(side_effect=list(responses)))
    )


async def test_returns_the_text_when_the_model_finished():
    client = _client(_response("A complete answer."))

    text, _ = await send_with_continuation(
        client, model="claude-sonnet-4-6", max_tokens=100, messages=[]
    )

    assert text == "A complete answer."


async def test_continues_a_truncated_response():
    client = _client(
        _response("The first half", stop_reason="max_tokens"),
        _response(" and the second half."),
    )

    text, _ = await send_with_continuation(
        client, model="claude-sonnet-4-6", max_tokens=100, messages=[]
    )

    assert text == "The first half and the second half."


async def test_a_response_still_truncated_after_continuing_is_a_failure():
    # Half a JSON envelope is unparseable and half an answer is unpublishable,
    # so this has to surface as an error rather than as content.
    client = _client(
        _response("Still going", stop_reason="max_tokens"),
        _response(" and still going", stop_reason="max_tokens"),
    )

    with pytest.raises(TruncatedOutputError):
        await send_with_continuation(
            client, model="claude-sonnet-4-6", max_tokens=100, messages=[]
        )
