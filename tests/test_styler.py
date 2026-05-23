import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.styler import style_content

_Q = "Why do we have eyebrows if they do not actually keep the rain out of our eyes?"
_A = (
    "Eyebrows serve a surprisingly important role in human communication and expression. "
    "They help channel sweat and rain away from your eyes, but their real superpower is social."
)

_STYLED_Q = "Why do we have **_eyebrows_** if they don't actually keep rain out of our eyes?"
_STYLED_A = (
    "**Eyebrows** serve a surprisingly important role in human communication and expression. "
    "They help channel sweat and rain away from your eyes, but their real superpower is social."
)

FAKE_STYLE_JSON = json.dumps({"questionMd": _STYLED_Q, "answerMd": _STYLED_A})


async def test_style_content_calls_claude():
    mock_response = SimpleNamespace(content=[SimpleNamespace(text=FAKE_STYLE_JSON)])
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    with patch("app.services.styler.get_client", return_value=mock_client):
        q, a = await style_content(_Q, _A)

    assert q == _STYLED_Q
    assert a == _STYLED_A
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert "Question:" in call_kwargs["messages"][0]["content"]
    assert "Answer:" in call_kwargs["messages"][0]["content"]


async def test_style_content_bad_json():
    mock_response = SimpleNamespace(content=[SimpleNamespace(text="not json")])
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    with (
        patch("app.services.styler.get_client", return_value=mock_client),
        pytest.raises(ValueError, match="unparseable"),
    ):
        await style_content(_Q, _A)


async def test_style_content_missing_key():
    mock_response = SimpleNamespace(
        content=[SimpleNamespace(text=json.dumps({"questionMd": "ok"}))]
    )
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    with (
        patch("app.services.styler.get_client", return_value=mock_client),
        pytest.raises(ValueError, match="unparseable"),
    ):
        await style_content(_Q, _A)
