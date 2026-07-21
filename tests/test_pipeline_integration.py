"""Integration test: POST /run lifecycle through Ground Ctrl.

The pipeline completes the full flow: sources -> generate -> review -> persist."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.candidates import Agent, GeneratedCandidate, ReviewedCandidate
from app.models.sources import SourceItem

FAKE_SOURCES = [
    SourceItem(title="Test Article", url="https://example.com/1", source="Hacker News"),
    SourceItem(title="Another Post", url="https://example.com/2", source="r/MachineLearning"),
]

_Q = "Why do we have eyebrows if they do not keep the rain out?"
_A = "**Eyebrows** serve a surprisingly important role in human communication. " * 3

FAKE_CANDIDATES = [
    GeneratedCandidate(agent=Agent.CLAUDE, question_md=_Q, answer_md=_A),
    GeneratedCandidate(agent=Agent.CLAUDE, question_md=_Q, answer_md=_A),
    GeneratedCandidate(agent=Agent.GPT4, question_md=_Q, answer_md=_A),
    GeneratedCandidate(agent=Agent.GPT4, question_md=_Q, answer_md=_A),
    GeneratedCandidate(agent=Agent.GEMINI, question_md=_Q, answer_md=_A),
    GeneratedCandidate(agent=Agent.GEMINI, question_md=_Q, answer_md=_A),
]

FAKE_REVIEWED = [
    ReviewedCandidate(
        agent=Agent.GEMINI, question_md=_Q, answer_md=_A, score=9, review_reason="Great"
    ),
    ReviewedCandidate(
        agent=Agent.CLAUDE, question_md=_Q, answer_md=_A, score=8, review_reason="Good"
    ),
    ReviewedCandidate(
        agent=Agent.GPT4, question_md=_Q, answer_md=_A, score=7, review_reason="Decent"
    ),
]

FAKE_PERSISTED = [
    {"id": "c-1", "agent": "gemini", "score": 9},
    {"id": "c-2", "agent": "claude", "score": 8},
    {"id": "c-3", "agent": "gpt4", "score": 7},
]

RUN_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


@pytest.fixture()
def mock_ground_ctrl():
    gc = AsyncMock()
    gc.submit_candidates.return_value = FAKE_PERSISTED
    gc.get_recent_questions.return_value = ["What is a **_token_**?"]
    # None = similarity check unavailable — the gate fails open.
    gc.check_similarity.return_value = None
    with patch("app.services.pipeline.get_ground_ctrl", return_value=gc):
        yield gc


@pytest.fixture()
def mock_sources():
    with patch("app.services.pipeline.fetch_all_sources", return_value=FAKE_SOURCES):
        yield


@pytest.fixture(autouse=True)
def mock_moments():
    with patch("app.services.pipeline.detect_moments", return_value=[]):
        yield


@pytest.fixture()
def mock_generation():
    with patch("app.services.pipeline.generate_candidates", return_value=FAKE_CANDIDATES):
        yield


@pytest.fixture()
def mock_review():
    with patch("app.services.pipeline.review_candidates", return_value=FAKE_REVIEWED):
        yield


def test_run_requires_auth(client):
    resp = client.post("/run", json={"run_id": RUN_ID})
    assert resp.status_code == 401


def test_run_rejects_bad_token(client):
    resp = client.post(
        "/run",
        json={"run_id": RUN_ID},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


def test_run_accepts_and_runs_pipeline(
    client, auth_headers, mock_ground_ctrl, mock_sources, mock_generation, mock_review
):
    """POST /run should return 202 immediately and run pipeline in background."""
    resp = client.post("/run", json={"run_id": RUN_ID}, headers=auth_headers)
    assert resp.status_code == 202

    data = resp.json()
    assert data["run_id"] == RUN_ID
    assert data["status"] == "accepted"

    mock_ground_ctrl.submit_candidates.assert_called_once_with(RUN_ID, FAKE_REVIEWED, topic=None)


def test_run_accepts_topic(
    client, auth_headers, mock_ground_ctrl, mock_sources, mock_generation, mock_review
):
    """POST /run with a topic strips it and threads it through to persistence."""
    resp = client.post(
        "/run",
        json={"run_id": RUN_ID, "topic": "  open source  "},
        headers=auth_headers,
    )
    assert resp.status_code == 202

    mock_ground_ctrl.submit_candidates.assert_called_once_with(
        RUN_ID, FAKE_REVIEWED, topic="open source"
    )


def test_gate_filters_before_review(
    client, auth_headers, mock_ground_ctrl, mock_sources, mock_generation
):
    """Similarity results over threshold shrink the slate review receives."""
    # First candidate is a corpus repeat; the rest are novel.
    mock_ground_ctrl.check_similarity.return_value = [
        {
            "corpusSimilarity": 0.9 if i == 0 else 0.2,
            "corpusMatch": "What is a token?" if i == 0 else None,
            "corpusSource": "candidate" if i == 0 else None,
            "siblingSimilarity": None,
            "siblingIndex": None,
        }
        for i in range(len(FAKE_CANDIDATES))
    ]
    review_mock = AsyncMock(return_value=FAKE_REVIEWED)
    with patch("app.services.pipeline.review_candidates", review_mock):
        resp = client.post("/run", json={"run_id": RUN_ID}, headers=auth_headers)
    assert resp.status_code == 202

    reviewed_candidates = review_mock.call_args[0][0]
    assert len(reviewed_candidates) == len(FAKE_CANDIDATES) - 1


def test_run_calls_fail_on_error(
    client_no_raise, auth_headers, mock_ground_ctrl, mock_sources, mock_generation
):
    """If pipeline fails in background, it reports to Ground Ctrl via fail_run."""
    with patch(
        "app.services.pipeline.review_candidates",
        side_effect=ValueError("Review broke"),
    ):
        resp = client_no_raise.post("/run", json={"run_id": RUN_ID}, headers=auth_headers)
    assert resp.status_code == 202

    mock_ground_ctrl.fail_run.assert_called_once()
    call_args = mock_ground_ctrl.fail_run.call_args
    assert call_args[0][0] == RUN_ID


async def test_pipeline_completes_full_flow(
    mock_ground_ctrl, mock_sources, mock_generation, mock_review
):
    """Pipeline fetches sources, generates, reviews, and persists."""
    from app.services.pipeline import run_pipeline

    result = await run_pipeline(RUN_ID)

    assert result["run_id"] == RUN_ID
    assert len(result["candidates"]) == 3
    mock_ground_ctrl.submit_candidates.assert_called_once_with(RUN_ID, FAKE_REVIEWED, topic=None)


async def test_pipeline_topic_run_skips_moments_and_threads_topic(mock_ground_ctrl, mock_sources):
    """A topic run never calls zeitgeist detection and passes the topic through."""
    from app.services.pipeline import run_pipeline

    detect_mock = AsyncMock(return_value=[])
    generate_mock = AsyncMock(return_value=FAKE_CANDIDATES)
    review_mock = AsyncMock(return_value=FAKE_REVIEWED)
    with (
        patch("app.services.pipeline.detect_moments", detect_mock),
        patch("app.services.pipeline.generate_candidates", generate_mock),
        patch("app.services.pipeline.review_candidates", review_mock),
    ):
        result = await run_pipeline(RUN_ID, topic="open source")

    assert result["run_id"] == RUN_ID
    detect_mock.assert_not_called()
    assert generate_mock.call_args.kwargs["topic"] == "open source"
    assert review_mock.call_args.kwargs["topic"] == "open source"
    mock_ground_ctrl.submit_candidates.assert_called_once_with(
        RUN_ID, FAKE_REVIEWED, topic="open source"
    )


async def test_pipeline_survives_recent_questions_failure(
    mock_ground_ctrl, mock_sources, mock_generation, mock_review
):
    """A failure fetching dedup history must not kill the run."""
    from app.services.pipeline import run_pipeline

    mock_ground_ctrl.get_recent_questions.side_effect = RuntimeError("GC unreachable")
    result = await run_pipeline(RUN_ID)

    assert result["run_id"] == RUN_ID
    mock_ground_ctrl.submit_candidates.assert_called_once()
    mock_ground_ctrl.fail_run.assert_not_called()


async def test_pipeline_fails_and_reports(mock_ground_ctrl, mock_sources, mock_generation):
    """Pipeline catches errors and reports them to Ground Ctrl via fail_run."""
    with (
        patch(
            "app.services.pipeline.review_candidates",
            side_effect=ValueError("Review broke"),
        ),
        pytest.raises(ValueError, match="Review broke"),
    ):
        from app.services.pipeline import run_pipeline

        await run_pipeline(RUN_ID)

    mock_ground_ctrl.fail_run.assert_called_once()
