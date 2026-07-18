import json
from unittest.mock import AsyncMock, patch

from app.models.moments import MomentStrength
from app.models.sources import SourceItem
from app.services.zeitgeist import _build_user_prompt, _parse_moments, detect_moments

SOURCES = [
    SourceItem(title="Model X breaks benchmark", url="https://a.com/1", source="Hacker News"),
    SourceItem(title="Everyone testing Model X", url="https://b.com/2", source="r/ChatGPT"),
    SourceItem(title="Quiet arxiv paper", url="https://c.com/3", source="arxiv AI"),
]

FAKE_MOMENTS_JSON = json.dumps(
    {
        "moments": [
            {
                "title": "Model X release dominates the week",
                "why_now": "Released Tuesday, every feed is reacting",
                "teachable_angle": "What benchmark scores actually measure",
                "strength": "strong",
                "sources": ["Hacker News", "r/ChatGPT"],
            },
            {
                "title": "Bogus entry",
                # missing why_now/teachable_angle -> dropped, not fatal
            },
        ]
    }
)


def test_build_user_prompt_groups_by_source():
    prompt = _build_user_prompt(SOURCES)
    assert "Hacker News:" in prompt
    assert "r/ChatGPT:" in prompt
    assert "1. Model X breaks benchmark" in prompt


def test_parse_moments_skips_invalid():
    moments = _parse_moments(FAKE_MOMENTS_JSON)
    assert len(moments) == 1
    assert moments[0].strength == MomentStrength.STRONG
    assert moments[0].teachable_angle


async def test_detect_moments_empty_sources():
    assert await detect_moments([]) == []


async def test_detect_moments_fails_open():
    with patch(
        "app.services.zeitgeist.send_with_continuation",
        AsyncMock(side_effect=RuntimeError("api down")),
    ):
        assert await detect_moments(SOURCES) == []


async def test_detect_moments_parses_response():
    with patch(
        "app.services.zeitgeist.send_with_continuation",
        AsyncMock(return_value=(FAKE_MOMENTS_JSON, None)),
    ):
        moments = await detect_moments(SOURCES)
    assert len(moments) == 1
    assert moments[0].title.startswith("Model X")
