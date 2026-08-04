from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import openai
import pytest

from app.clients import openai as openai_client
from app.errors import TruncatedOutputError


def _bad_request(message: str) -> openai.BadRequestError:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(400, request=request, json={"error": {"message": message}})
    return openai.BadRequestError(message, response=response, body=None)


def _client_with(create: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(responses=SimpleNamespace(create=create))


@pytest.fixture(autouse=True)
def _forget_unsupported_models():
    openai_client._web_search_unsupported.clear()
    yield
    openai_client._web_search_unsupported.clear()


async def test_web_search_is_attached_and_forced():
    create = AsyncMock(return_value=SimpleNamespace(output_text="hello"))

    with patch.object(openai_client, "get_client", return_value=_client_with(create)):
        result = await openai_client.create_text(
            model="gpt-4o", user="What happened today?", max_output_tokens=100
        )

    assert result == "hello"
    kwargs = create.call_args.kwargs
    assert kwargs["tools"] == [openai_client.WEB_SEARCH_TOOL]
    assert kwargs["tool_choice"] == "required"
    # JSON mode cannot coexist with search, so it must not be sent.
    assert "text" not in kwargs


async def test_search_and_json_mode_are_never_sent_together():
    create = AsyncMock(return_value=SimpleNamespace(output_text="{}"))

    with patch.object(openai_client, "get_client", return_value=_client_with(create)):
        await openai_client.create_text(
            model="gpt-4o",
            user="Return JSON.",
            max_output_tokens=100,
            json_object=True,
        )

    assert "text" not in create.call_args.kwargs


async def test_json_mode_without_search_names_json_in_the_input():
    create = AsyncMock(return_value=SimpleNamespace(output_text="{}"))

    with patch.object(openai_client, "get_client", return_value=_client_with(create)):
        await openai_client.create_text(
            model="gpt-4o",
            user="Summarize this.",
            system="Reply with a JSON object.",
            max_output_tokens=100,
            json_object=True,
            web_search=False,
        )

    kwargs = create.call_args.kwargs
    assert kwargs["text"] == {"format": {"type": "json_object"}}
    # The API only looks at the input, not the instructions.
    assert "json" in kwargs["input"].lower()


async def test_a_model_that_rejects_web_search_retries_cleanly():
    create = AsyncMock(
        side_effect=[
            _bad_request("Web search is not supported with this model"),
            SimpleNamespace(output_text="fallback answer"),
        ]
    )

    with patch.object(openai_client, "get_client", return_value=_client_with(create)):
        result = await openai_client.create_text(
            model="gpt-4o", user="Question?", max_output_tokens=100, json_object=True
        )

    assert result == "fallback answer"
    retry_kwargs = create.call_args.kwargs
    # Both must go: "required" with no tools is itself a 400.
    assert "tools" not in retry_kwargs
    assert "tool_choice" not in retry_kwargs
    assert retry_kwargs["text"] == {"format": {"type": "json_object"}}


async def test_the_unsupported_model_is_remembered():
    create = AsyncMock(
        side_effect=[
            _bad_request("Web search is not supported with this model"),
            SimpleNamespace(output_text="one"),
            SimpleNamespace(output_text="two"),
        ]
    )

    with patch.object(openai_client, "get_client", return_value=_client_with(create)):
        await openai_client.create_text(model="gpt-4o", user="a", max_output_tokens=100)
        await openai_client.create_text(model="gpt-4o", user="b", max_output_tokens=100)

    assert create.call_count == 3
    assert "tools" not in create.call_args.kwargs


async def test_a_non_tool_bad_request_is_not_swallowed():
    create = AsyncMock(side_effect=_bad_request("context length exceeded"))

    with (
        patch.object(openai_client, "get_client", return_value=_client_with(create)),
        pytest.raises(openai.BadRequestError),
    ):
        await openai_client.create_text(
            model="gpt-4o", user="a", max_output_tokens=100, web_search=False
        )


async def test_an_incomplete_response_is_a_failure_not_a_short_answer():
    # The Responses API hands back the partial text alongside the incomplete
    # status; published as-is it reads as an answer that stops mid-sentence.
    create = AsyncMock(
        return_value=SimpleNamespace(
            output_text="Benchmarks stop being useful once every model",
            status="incomplete",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        )
    )

    with (
        patch.object(openai_client, "get_client", return_value=_client_with(create)),
        pytest.raises(TruncatedOutputError, match="max_output_tokens"),
    ):
        await openai_client.create_text(
            model="gpt-4o", user="q", max_output_tokens=32, web_search=False
        )


async def test_a_completed_response_passes_through():
    create = AsyncMock(
        return_value=SimpleNamespace(output_text="A complete answer.", status="completed")
    )

    with patch.object(openai_client, "get_client", return_value=_client_with(create)):
        result = await openai_client.create_text(
            model="gpt-4o", user="q", max_output_tokens=512, web_search=False
        )

    assert result == "A complete answer."
