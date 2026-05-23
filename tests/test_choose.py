import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.candidates import Agent, Candidate, CandidateStatus, Run, RunStatus

_Q = "Why do we have eyebrows if they do not actually keep the rain out of our eyes?"
_A = (
    "**Eyebrows** serve a surprisingly important role in human communication and expression. "
    "They help channel sweat and rain away from your eyes, but their real superpower is social."
)
_STYLED_Q = "Why do we have **_eyebrows_** if they don't actually keep rain out of our eyes?"
_STYLED_A = (
    "**Eyebrows** serve a surprisingly important role in human communication. "
    "They help channel sweat away from your eyes, but their real superpower is social."
)

FAKE_RUN = Run(
    id="run-abc",
    targetDate="2026-05-23T00:00:00Z",
    status=RunStatus.AWAITING_REVIEW,
    createdAt="2026-05-23T06:00:00Z",
    candidates=[
        Candidate(
            id="cand-1",
            runId="run-abc",
            agent=Agent.CLAUDE,
            questionMd=_Q,
            answerMd=_A,
            score=9,
            reviewReason="Great",
            status=CandidateStatus.PENDING,
            createdAt="2026-05-23T06:00:00Z",
        ),
        Candidate(
            id="cand-2",
            runId="run-abc",
            agent=Agent.GPT4,
            questionMd="Another question that is long enough for validation purposes here?",
            answerMd=(
                "Another answer that is definitely long enough for validation"
                " purposes in this test case."
            ),
            score=6,
            reviewReason="Decent",
            status=CandidateStatus.PENDING,
            createdAt="2026-05-23T06:00:00Z",
        ),
    ],
)

FAKE_STYLE_JSON = json.dumps({"questionMd": _STYLED_Q, "answerMd": _STYLED_A})


def _mock_gc():
    gc = AsyncMock()
    gc.get_run.return_value = FAKE_RUN
    gc.choose_candidate.return_value = {"question": {"id": "q-123", "status": "published"}}
    return gc


def _mock_anthropic():
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(text=FAKE_STYLE_JSON)]
    )
    return mock_client


async def test_choose_auto_picks_top_scorer(client, auth_headers):
    gc = _mock_gc()
    anthropic_client = _mock_anthropic()

    with (
        patch("app.routes.choose.get_ground_ctrl", return_value=gc),
        patch("app.services.styler.get_client", return_value=anthropic_client),
    ):
        resp = client.post("/choose", json={"run_id": "run-abc"}, headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["candidateId"] == "cand-1"
    gc.choose_candidate.assert_called_once_with("run-abc", "cand-1", _STYLED_Q, _STYLED_A)


async def test_choose_explicit_candidate(client, auth_headers):
    gc = _mock_gc()
    anthropic_client = _mock_anthropic()

    with (
        patch("app.routes.choose.get_ground_ctrl", return_value=gc),
        patch("app.services.styler.get_client", return_value=anthropic_client),
    ):
        resp = client.post(
            "/choose",
            json={"run_id": "run-abc", "candidate_id": "cand-2"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["candidateId"] == "cand-2"
    gc.choose_candidate.assert_called_once()


async def test_choose_candidate_not_found(client, auth_headers):
    gc = _mock_gc()

    with patch("app.routes.choose.get_ground_ctrl", return_value=gc):
        resp = client.post(
            "/choose",
            json={"run_id": "run-abc", "candidate_id": "nonexistent"},
            headers=auth_headers,
        )

    assert resp.status_code == 404


async def test_choose_no_candidates(client, auth_headers):
    gc = AsyncMock()
    gc.get_run.return_value = Run(
        id="run-abc",
        targetDate="2026-05-23T00:00:00Z",
        status=RunStatus.AWAITING_REVIEW,
        createdAt="2026-05-23T06:00:00Z",
        candidates=[],
    )

    with patch("app.routes.choose.get_ground_ctrl", return_value=gc):
        resp = client.post("/choose", json={"run_id": "run-abc"}, headers=auth_headers)

    assert resp.status_code == 404


async def test_choose_requires_auth(client):
    resp = client.post("/choose", json={"run_id": "run-abc"})
    assert resp.status_code in (401, 403)
