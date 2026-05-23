"""Integration test: POST /run fetches sources, calls Ground Ctrl, and the pipeline
fails at the generation step (NotImplementedError) which is expected for Phase 2."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.candidates import Run, RunStatus
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


def test_run_requires_auth(client):
    resp = client.post("/run", json={"date": "2026-05-23"})
    assert resp.status_code == 401


def test_run_rejects_bad_token(client):
    resp = client.post("/run", json={}, headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_run_fetches_sources_then_fails_at_generation(
    client_no_raise, auth_headers, mock_ground_ctrl, mock_sources
):
    """Phase 2: POST /run should fetch sources, then fail at generate (NotImplementedError).
    The pipeline catches the error and calls fail_run on Ground Ctrl."""
    resp = client_no_raise.post("/run", json={"date": "2026-05-23"}, headers=auth_headers)
    assert resp.status_code == 500

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
    mock_ground_ctrl.fail_run.assert_called_once()
    call_args = mock_ground_ctrl.fail_run.call_args
    assert call_args[0][0] == "run-123"


async def test_pipeline_creates_run_and_fetches_sources(mock_ground_ctrl, mock_sources):
    """Verify the pipeline calls Ground Ctrl and fetches sources before generation."""
    from app.services.pipeline import run_pipeline

    with pytest.raises(NotImplementedError):
        await run_pipeline("2026-05-23")

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
    mock_ground_ctrl.fail_run.assert_called_once()


async def test_pipeline_uses_today_when_no_date(mock_ground_ctrl, mock_sources):
    from app.services.pipeline import run_pipeline

    with patch("app.services.pipeline.today_pt") as mock_today:
        mock_today.return_value.isoformat.return_value = "2026-05-23"
        with pytest.raises(NotImplementedError):
            await run_pipeline()

    mock_ground_ctrl.create_run.assert_called_once_with("2026-05-23")
