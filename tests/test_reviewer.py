import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.candidates import Agent, GeneratedCandidate, ReviewedCandidate
from app.services.reviewer import _build_review_input, _parse_review, review_candidates

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
_Q3 = "What makes the sky blue instead of any other color that light could possibly scatter into?"
_A3 = (
    "The sky appears blue because of **Rayleigh scattering**, where shorter blue wavelengths of "
    "sunlight scatter more than longer red ones when hitting tiny molecules in the atmosphere."
)

CANDIDATES = [
    GeneratedCandidate(agent=Agent.CLAUDE, question_md=_Q1, answer_md=_A1),
    GeneratedCandidate(agent=Agent.GPT4, question_md=_Q2, answer_md=_A2),
    GeneratedCandidate(agent=Agent.GEMINI, question_md=_Q3, answer_md=_A3),
]

FAKE_REVIEW_JSON = json.dumps(
    {
        "reviewed": [
            {"index": 0, "score": 8, "reason": "Strong question with clear answer"},
            {"index": 1, "score": 6, "reason": "Decent but common knowledge"},
            {"index": 2, "score": 9, "reason": "Great topic, well explained"},
        ]
    }
)


def test_build_review_input():
    text = _build_review_input(CANDIDATES, [])
    assert "Candidate 0" in text
    assert "Candidate 1" in text
    assert "Candidate 2" in text
    assert "claude" in text
    assert "gpt4" in text
    assert "gemini" in text
    assert "eyebrows" in text.lower()
    assert "category: cultural" in text
    assert "already published or offered" not in text


def test_build_review_input_with_recent_questions():
    text = _build_review_input(CANDIDATES, ["What is a **_token_**?"])
    assert "already published or offered" in text
    assert "What is a **_token_**?" in text


def test_build_review_input_with_moments_and_near_repeats():
    from app.models.moments import Moment, MomentStrength

    moments = [
        Moment(
            title="Model X release dominates the week",
            why_now="Released Tuesday, every feed is reacting",
            teachable_angle="What benchmark scores actually measure",
            strength=MomentStrength.STRONG,
        )
    ]
    text = _build_review_input(CANDIDATES, [], moments, {1: "What is a token?"})
    assert "cultural moments" in text
    assert "Model X release dominates the week" in text
    assert "near-repeat" in text
    # The flag lands on candidate 1 only
    c0, c1 = text.split("--- Candidate 1")
    assert "near-repeat" not in c0
    assert 'near-repeat of "What is a token?"' in c1


def test_parse_review_prefixes_category():
    reviewed = _parse_review(FAKE_REVIEW_JSON, CANDIDATES)
    assert all(r.review_reason.startswith("[cultural] ") for r in reviewed)


def test_parse_review_returns_top_3():
    reviewed = _parse_review(FAKE_REVIEW_JSON, CANDIDATES)
    assert len(reviewed) == 3
    assert all(isinstance(r, ReviewedCandidate) for r in reviewed)
    assert reviewed[0].score >= reviewed[1].score >= reviewed[2].score


def test_parse_review_top_3_sorted():
    reviewed = _parse_review(FAKE_REVIEW_JSON, CANDIDATES)
    assert reviewed[0].score == 9
    assert reviewed[0].agent == Agent.GEMINI
    assert reviewed[1].score == 8
    assert reviewed[1].agent == Agent.CLAUDE
    assert reviewed[2].score == 6
    assert reviewed[2].agent == Agent.GPT4


def test_parse_review_clamps_scores():
    raw = json.dumps(
        {
            "reviewed": [
                {"index": 0, "score": 15, "reason": "Too high"},
                {"index": 1, "score": -2, "reason": "Too low"},
                {"index": 2, "score": 7, "reason": "Normal"},
            ]
        }
    )
    reviewed = _parse_review(raw, CANDIDATES)
    scores = [r.score for r in reviewed]
    assert all(1 <= s <= 10 for s in scores)


def test_parse_review_skips_bad_index():
    raw = json.dumps(
        {
            "reviewed": [
                {"index": 0, "score": 8, "reason": "Good"},
                {"index": 99, "score": 10, "reason": "Invalid index"},
                {"index": 2, "score": 7, "reason": "Fine"},
            ]
        }
    )
    reviewed = _parse_review(raw, CANDIDATES)
    assert len(reviewed) == 2


def test_parse_review_truncates_long_reason():
    raw = json.dumps(
        {
            "reviewed": [
                {"index": 0, "score": 8, "reason": "x" * 300},
            ]
        }
    )
    reviewed = _parse_review(raw, CANDIDATES)
    assert len(reviewed[0].review_reason) <= 200


def test_parse_review_bad_json():
    with pytest.raises((ValueError, KeyError)):
        _parse_review("not json", CANDIDATES)


def test_parse_review_wrong_schema():
    with pytest.raises(KeyError):
        _parse_review('{"results": []}', CANDIDATES)


async def test_review_candidates_calls_claude():
    mock_response = SimpleNamespace(
        content=[SimpleNamespace(text=FAKE_REVIEW_JSON, type="text")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=200),
    )
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    with patch("app.services.reviewer.get_client", return_value=mock_client):
        reviewed = await review_candidates(CANDIDATES)

    assert len(reviewed) == 3
    assert all(isinstance(r, ReviewedCandidate) for r in reviewed)
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert "tools" in call_kwargs


async def test_review_candidates_empty_input():
    with pytest.raises(ValueError, match="No candidates"):
        await review_candidates([])


async def test_review_candidates_unparseable():
    mock_response = SimpleNamespace(
        content=[SimpleNamespace(text="garbage", type="text")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=10),
    )
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = mock_response

    with (
        patch("app.services.reviewer.get_client", return_value=mock_client),
        pytest.raises(ValueError, match="unparseable"),
    ):
        await review_candidates(CANDIDATES)

    assert mock_client.messages.create.call_count == 3


async def test_review_candidates_retries_then_succeeds():
    good_response = SimpleNamespace(
        content=[SimpleNamespace(text=FAKE_REVIEW_JSON, type="text")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=200),
    )
    bad_response = SimpleNamespace(
        content=[SimpleNamespace(text="garbage", type="text")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=10),
    )
    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = [bad_response, good_response]

    with patch("app.services.reviewer.get_client", return_value=mock_client):
        reviewed = await review_candidates(CANDIDATES)

    assert len(reviewed) == 3
    assert mock_client.messages.create.call_count == 2
