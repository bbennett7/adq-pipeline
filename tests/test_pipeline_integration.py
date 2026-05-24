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
    with patch("app.services.pipeline.get_ground_ctrl", return_value=gc):
        yield gc


@pytest.fixture()
def mock_sources():
    with patch("app.services.pipeline.fetch_all_sources", return_value=FAKE_SOURCES):
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

    mock_ground_ctrl.submit_candidates.assert_called_once_with(RUN_ID, FAKE_REVIEWED)


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
    mock_ground_ctrl.submit_candidates.assert_called_once_with(RUN_ID, FAKE_REVIEWED)


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
