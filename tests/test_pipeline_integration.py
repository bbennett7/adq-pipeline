"""Integration test: POST /run lifecycle through Ground Ctrl.

Phase 4: generation and review are implemented, so the pipeline completes
the full flow: sources -> generate -> review -> persist -> notify."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.candidates import Agent, GeneratedCandidate, ReviewedCandidate, Run, RunStatus
from app.models.sources import SourceItem

FAKE_RUN = Run(
    id="run-123",
    targetDate=datetime(2026, 5, 23, tzinfo=UTC),
    status=RunStatus.RUNNING,
    createdAt=datetime(2026, 5, 23, 6, 0, 0, tzinfo=UTC),
)

FAKE_FAILED_RUN = Run(
    id="run-123",
    targetDate=datetime(2026, 5, 23, tzinfo=UTC),
    status=RunStatus.FAILED,
    errorMessage="Something went wrong",
    createdAt=datetime(2026, 5, 23, 6, 0, 0, tzinfo=UTC),
)

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


@pytest.fixture()
def mock_ground_ctrl():
    gc = AsyncMock()
    gc.create_run.return_value = FAKE_RUN
    gc.fail_run.return_value = FAKE_FAILED_RUN
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


@pytest.fixture()
def mock_notify():
    with patch("app.services.pipeline.notify_candidates_ready", new_callable=AsyncMock):
        yield


def test_run_requires_auth(client):
    resp = client.post("/run", json={"date": "2026-05-23"})
    assert resp.status_code == 401


def test_run_rejects_bad_token(client):
    resp = client.post("/run", json={}, headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_run_completes_full_pipeline(
    client, auth_headers, mock_ground_ctrl, mock_sources, mock_generation, mock_review, mock_notify
):
    """POST /run should complete the full pipeline and return results."""
    resp = client.post("/run", json={"date": "2026-05-23"}, headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["run_id"] == "run-123"
    assert data["date"] == "2026-05-23"
    assert len(data["candidates"]) == 3

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
    mock_ground_ctrl.submit_candidates.assert_called_once_with("run-123", FAKE_REVIEWED)


def test_run_calls_fail_on_error(
    client_no_raise, auth_headers, mock_ground_ctrl, mock_sources, mock_generation
):
    """If review raises, pipeline catches the error and calls fail_run."""
    with patch(
        "app.services.pipeline.review_candidates",
        side_effect=ValueError("Review broke"),
    ):
        resp = client_no_raise.post("/run", json={"date": "2026-05-23"}, headers=auth_headers)
    assert resp.status_code == 500

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
    mock_ground_ctrl.fail_run.assert_called_once()
    call_args = mock_ground_ctrl.fail_run.call_args
    assert call_args[0][0] == "run-123"


async def test_pipeline_completes_full_flow(
    mock_ground_ctrl, mock_sources, mock_generation, mock_review, mock_notify
):
    """Pipeline creates run, fetches sources, generates, reviews, persists, and notifies."""
    from app.services.pipeline import run_pipeline

    result = await run_pipeline("2026-05-23")

    assert result["run_id"] == "run-123"
    assert result["date"] == "2026-05-23"
    assert len(result["candidates"]) == 3
    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
    mock_ground_ctrl.submit_candidates.assert_called_once_with("run-123", FAKE_REVIEWED)


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

        await run_pipeline("2026-05-23")

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
    mock_ground_ctrl.fail_run.assert_called_once()


async def test_pipeline_uses_today_when_no_date(
    mock_ground_ctrl, mock_sources, mock_generation, mock_review, mock_notify
):
    from app.services.pipeline import run_pipeline

    with patch("app.services.pipeline.today_pt") as mock_today:
        mock_today.return_value.isoformat.return_value = "2026-05-23"
        result = await run_pipeline()

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
    assert result["date"] == "2026-05-23"
