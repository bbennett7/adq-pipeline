import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.candidates import Agent, Category, GeneratedCandidate
from app.models.sources import SourceItem
from app.services.generator import (
    _build_candidates,
    _build_user_prompt,
    _generate_claude,
    _generate_gemini,
    _generate_gpt4,
    _parse_raw_json,
    generate_candidates,
)

SOURCES = [
    SourceItem(title="Why cats purr", url="https://example.com/1", source="Hacker News"),
    SourceItem(title="New exoplanet found", url="https://example.com/2", source="r/science"),
]

_Q1 = "Why do we have eyebrows if they do not actually keep the rain out of our eyes?"
_A1 = (
    "**Eyebrows** serve a surprisingly important role in human communication and expression. "
    "They help channel sweat and rain away from your eyes, but their real superpower is social."
)
_Q2 = "Can fish actually drown if they are already living and breathing underwater all day?"
_A2 = (
    "Technically yes — **fish** need dissolved oxygen to survive, and if the water lacks enough "
    "of it they will suffocate. It is essentially drowning, just not the way we usually picture it."
)

FAKE_JSON = json.dumps(
    {
        "candidates": [
            {"questionMd": _Q1, "answerMd": _A1},
            {"questionMd": _Q2, "answerMd": _A2},
        ]
    }
)


def test_build_user_prompt():
    prompt = _build_user_prompt(SOURCES, [])
    assert "Why cats purr" in prompt
    assert "Hacker News" in prompt
    assert "r/science" in prompt
    assert "already published or offered" not in prompt


def test_build_user_prompt_with_recent_questions():
    prompt = _build_user_prompt(SOURCES, ["What is a **_token_**?", "What is a GPU?"])
    assert "already published or offered" in prompt
    assert "What is a **_token_**?" in prompt
    assert "What is a GPU?" in prompt


def test_sample_sources_covers_every_feed():
    from app.services.generator import _sample_sources

    sources = [
        SourceItem(title=f"{src} story {i}", url=f"https://example.com/{src}/{i}", source=src)
        for src in ["Hacker News", "arxiv AI", "r/LocalLLaMA", "OpenAI News"]
        for i in range(10)
    ]
    sampled = _sample_sources(sources)
    by_source = {s.source for s in sampled}
    assert by_source == {"Hacker News", "arxiv AI", "r/LocalLLaMA", "OpenAI News"}
    for src in by_source:
        assert sum(1 for s in sampled if s.source == src) == 3


def test_sample_sources_caps_total():
    from app.services.generator import _MAX_PROMPT_ITEMS, _sample_sources

    sources = [
        SourceItem(
            title=f"{src} story {i}", url=f"https://example.com/{src}/{i}", source=f"feed{src}"
        )
        for src in range(30)
        for i in range(3)
    ]
    assert len(_sample_sources(sources)) == _MAX_PROMPT_ITEMS


def test_build_user_prompt_moments_section():
    from app.models.moments import Moment, MomentStrength
    from app.services.generator import _build_user_prompt

    sources = [SourceItem(title="Story", url="https://e.com/1", source="Hacker News")]
    empty = _build_user_prompt(sources, [])
    assert "none detected" in empty

    moments = [
        Moment(
            title="Model X mania",
            why_now="Everyone is testing it",
            teachable_angle="How releases get benchmarked",
            strength=MomentStrength.STRONG,
        )
    ]
    with_moments = _build_user_prompt(sources, [], moments)
    assert "[strong] Model X mania" in with_moments
    assert "teachable angle: How releases get benchmarked" in with_moments


def test_build_candidates_categories():
    raw_items = [
        {"category": "current", "questionMd": _Q1, "answerMd": _A1},
        {"category": "Foundational", "questionMd": _Q2, "answerMd": _A2},
        {"category": "bogus", "questionMd": _Q1, "answerMd": _A1},
        {"questionMd": _Q2, "answerMd": _A2},
    ]
    candidates = _build_candidates(raw_items, Agent.CLAUDE)
    assert [c.category for c in candidates] == [
        Category.CURRENT,
        Category.FOUNDATIONAL,
        Category.CULTURAL,
        Category.CULTURAL,
    ]


def test_parse_and_build():
    raw_items = _parse_raw_json(FAKE_JSON)
    candidates = _build_candidates(raw_items, Agent.CLAUDE)
    assert len(candidates) == 2
    assert all(isinstance(c, GeneratedCandidate) for c in candidates)
    assert candidates[0].agent == Agent.CLAUDE
    assert "eyebrows" in candidates[0].question_md.lower()
    assert "fish" in candidates[1].question_md.lower()


def test_parse_raw_json_bad_json():
    with pytest.raises(ValueError, match="Unparseable"):
        _parse_raw_json("not json")


def test_parse_raw_json_wrong_schema():
    assert _parse_raw_json('{"results": []}') == []


def test_build_candidates_missing_fields():
    raw_items = [{"questionMd": "Q?"}]
    assert _build_candidates(raw_items, Agent.CLAUDE) == []


def test_parse_raw_json_markdown_fences():
    """Claude wraps JSON in ```json ... ``` fences."""
    raw = "```json\n" + FAKE_JSON + "\n```"
    raw_items = _parse_raw_json(raw)
    candidates = _build_candidates(raw_items, Agent.CLAUDE)
    assert len(candidates) == 2


async def test_generate_claude():
    mock_response = SimpleNamespace(
        content=[SimpleNamespace(text=FAKE_JSON, type="text")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=200),
    )
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    with patch("app.services.generator.get_anthropic", return_value=mock_client):
        candidates = await _generate_claude(SOURCES, [])

    assert len(candidates) == 2
    assert all(c.agent == Agent.CLAUDE for c in candidates)
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert "tools" in call_kwargs


async def test_generate_claude_revises_overlong_answer():
    long_answer = "A" * 1200
    overlong_json = json.dumps({"candidates": [{"questionMd": _Q1, "answerMd": long_answer}]})
    revised_answer = "Short revised answer that fits within the character limit nicely."

    gen_response = SimpleNamespace(
        content=[SimpleNamespace(text=overlong_json, type="text")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=200),
    )
    revise_response = SimpleNamespace(
        content=[SimpleNamespace(text=revised_answer, type="text")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
    )
    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = [gen_response, revise_response]

    with patch("app.services.generator.get_anthropic", return_value=mock_client):
        candidates = await _generate_claude(SOURCES, [])

    assert len(candidates) == 1
    assert candidates[0].answer_md == revised_answer
    assert mock_client.messages.create.call_count == 2


async def test_generate_gpt4():
    mock_message = SimpleNamespace(content=FAKE_JSON)
    mock_choice = SimpleNamespace(message=mock_message)
    mock_response = SimpleNamespace(choices=[mock_choice])
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("app.services.generator.get_openai", return_value=mock_client):
        candidates = await _generate_gpt4(SOURCES, [])

    assert len(candidates) == 2
    assert all(c.agent == Agent.GPT4 for c in candidates)
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"
    assert call_kwargs["response_format"] == {"type": "json_object"}


async def test_generate_gpt4_none_content():
    mock_message = SimpleNamespace(content=None)
    mock_choice = SimpleNamespace(message=mock_message)
    mock_response = SimpleNamespace(choices=[mock_choice])
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = mock_response

    with (
        patch("app.services.generator.get_openai", return_value=mock_client),
        pytest.raises(ValueError, match="empty content"),
    ):
        await _generate_gpt4(SOURCES, [])


async def test_generate_gemini():
    mock_candidate = SimpleNamespace(finish_reason="STOP")
    mock_response = SimpleNamespace(text=FAKE_JSON, candidates=[mock_candidate])
    mock_generate = AsyncMock(return_value=mock_response)
    mock_aio_models = SimpleNamespace(generate_content=mock_generate)
    mock_aio = SimpleNamespace(models=mock_aio_models)
    mock_client = SimpleNamespace(aio=mock_aio)

    with patch("app.services.generator.get_gemini", return_value=mock_client):
        candidates = await _generate_gemini(SOURCES, [])

    assert len(candidates) == 2
    assert all(c.agent == Agent.GEMINI for c in candidates)
    call_kwargs = mock_generate.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash"


async def test_generate_candidates_parallel():
    claude_candidates = [
        GeneratedCandidate(agent=Agent.CLAUDE, question_md=_Q1, answer_md=_A1),
        GeneratedCandidate(agent=Agent.CLAUDE, question_md=_Q2, answer_md=_A2),
    ]
    gpt_candidates = [
        GeneratedCandidate(agent=Agent.GPT4, question_md=_Q1, answer_md=_A1),
        GeneratedCandidate(agent=Agent.GPT4, question_md=_Q2, answer_md=_A2),
    ]
    gemini_candidates = [
        GeneratedCandidate(agent=Agent.GEMINI, question_md=_Q1, answer_md=_A1),
        GeneratedCandidate(agent=Agent.GEMINI, question_md=_Q2, answer_md=_A2),
    ]

    with (
        patch("app.services.generator._generate_claude", return_value=claude_candidates),
        patch("app.services.generator._generate_gpt4", return_value=gpt_candidates),
        patch("app.services.generator._generate_gemini", return_value=gemini_candidates),
    ):
        result = await generate_candidates(SOURCES)

    assert len(result) == 6
    agents = [c.agent for c in result]
    assert agents.count(Agent.CLAUDE) == 2
    assert agents.count(Agent.GPT4) == 2
    assert agents.count(Agent.GEMINI) == 2


async def test_generate_candidates_partial_failure():
    claude_candidates = [
        GeneratedCandidate(agent=Agent.CLAUDE, question_md=_Q1, answer_md=_A1),
        GeneratedCandidate(agent=Agent.CLAUDE, question_md=_Q2, answer_md=_A2),
    ]
    gpt_candidates = [
        GeneratedCandidate(agent=Agent.GPT4, question_md=_Q1, answer_md=_A1),
        GeneratedCandidate(agent=Agent.GPT4, question_md=_Q2, answer_md=_A2),
    ]

    with (
        patch("app.services.generator._generate_claude", return_value=claude_candidates),
        patch("app.services.generator._generate_gpt4", return_value=gpt_candidates),
        patch("app.services.generator._generate_gemini", side_effect=ValueError("Gemini down")),
    ):
        result = await generate_candidates(SOURCES)

    assert len(result) == 4
    agents = [c.agent for c in result]
    assert agents.count(Agent.CLAUDE) == 2
    assert agents.count(Agent.GPT4) == 2
    assert agents.count(Agent.GEMINI) == 0


async def test_generate_candidates_all_fail():
    with (
        patch("app.services.generator._generate_claude", side_effect=ValueError("fail")),
        patch("app.services.generator._generate_gpt4", side_effect=ValueError("fail")),
        patch("app.services.generator._generate_gemini", side_effect=ValueError("fail")),
        pytest.raises(RuntimeError, match="All three"),
    ):
        await generate_candidates(SOURCES)


async def test_generate_candidates_retries_transient_failure():
    claude_candidates = [
        GeneratedCandidate(agent=Agent.CLAUDE, question_md=_Q1, answer_md=_A1),
    ]
    with (
        patch(
            "app.services.generator._generate_claude",
            side_effect=[ValueError("transient"), claude_candidates],
        ) as mock_claude,
        patch("app.services.generator._generate_gpt4", side_effect=ValueError("fail")),
        patch("app.services.generator._generate_gemini", side_effect=ValueError("fail")),
    ):
        result = await generate_candidates(SOURCES)

    assert len(result) == 1
    assert result[0].agent == Agent.CLAUDE
    assert mock_claude.call_count == 2


def test_build_user_prompt_empty_sources():
    with pytest.raises(ValueError, match="without source material"):
        _build_user_prompt([], [])


def test_source_title_sanitization():
    item = SourceItem(
        title="Normal title\x00with\x01control\x02chars",
        url="https://example.com",
        source="test",
    )
    assert "\x00" not in item.title
    assert "\x01" not in item.title
    assert "Normal title" in item.title


def test_source_title_length_cap():
    item = SourceItem(
        title="x" * 300,
        url="https://example.com",
        source="test",
    )
    assert len(item.title) == 200


def test_source_source_sanitization():
    item = SourceItem(
        title="Test",
        url="https://example.com",
        source="sub\x00reddit\x01name",
    )
    assert "\x00" not in item.source
    assert "\x01" not in item.source
    assert "sub" in item.source


def test_source_source_length_cap():
    item = SourceItem(
        title="Test",
        url="https://example.com",
        source="x" * 200,
    )
    assert len(item.source) == 100


def test_source_summary_sanitization():
    item = SourceItem(
        title="Test",
        url="https://example.com",
        source="test",
        summary="text\x00with\x01control",
    )
    assert "\x00" not in item.summary
    assert "\x01" not in item.summary
    assert "text" in item.summary
