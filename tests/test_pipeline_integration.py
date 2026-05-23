"""Integration test: POST /run lifecycle through Ground Ctrl.

Phase 3: generation is implemented, so the pipeline now fails at the review step
(NotImplementedError). The pipeline catches the error and calls fail_run."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.candidates import Agent, GeneratedCandidate, Run, RunStatus
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
    errorMessage="NotImplementedError",
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


@pytest.fixture()
def mock_ground_ctrl():
    gc = AsyncMock()
    gc.create_run.return_value = FAKE_RUN
    gc.fail_run.return_value = FAKE_FAILED_RUN
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


def test_run_requires_auth(client):
    resp = client.post("/run", json={"date": "2026-05-23"})
    assert resp.status_code == 401


def test_run_rejects_bad_token(client):
    resp = client.post("/run", json={}, headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_run_fails_at_review_step(
    client_no_raise, auth_headers, mock_ground_ctrl, mock_sources, mock_generation
):
    """POST /run should fetch sources, generate candidates, then fail at review
    (NotImplementedError). The pipeline catches the error and calls fail_run."""
    resp = client_no_raise.post("/run", json={"date": "2026-05-23"}, headers=auth_headers)
    assert resp.status_code == 500

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
    mock_ground_ctrl.fail_run.assert_called_once()
    call_args = mock_ground_ctrl.fail_run.call_args
    assert call_args[0][0] == "run-123"


async def test_pipeline_fails_at_review(mock_ground_ctrl, mock_sources, mock_generation):
    """Pipeline creates run, fetches sources, generates candidates, then fails at review."""
    from app.services.pipeline import run_pipeline

    with pytest.raises(NotImplementedError):
        await run_pipeline("2026-05-23")

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
    mock_ground_ctrl.fail_run.assert_called_once()


async def test_pipeline_uses_today_when_no_date(mock_ground_ctrl, mock_sources, mock_generation):
    from app.services.pipeline import run_pipeline

    with patch("app.services.pipeline.today_pt") as mock_today:
        mock_today.return_value.isoformat.return_value = "2026-05-23"
        with pytest.raises(NotImplementedError):
            await run_pipeline()

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
