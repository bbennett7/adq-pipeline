from unittest.mock import patch

import pytest

from app.clients.ground_ctrl import GroundCtrlClient
from app.models.candidates import Agent, ReviewedCandidate

_Q = "Why do we have eyebrows if they do not actually keep the rain out of our eyes?"
_A = (
    "**Eyebrows** serve a surprisingly important role in human communication "
    "and expression. They help channel sweat and rain away from your eyes."
)


@pytest.fixture()
def gc_client():
    with patch("app.clients.ground_ctrl.get_settings") as mock:
        mock.return_value.ground_ctrl_url = "https://ground-ctrl.test"
        mock.return_value.pipeline_secret = "test-secret"
        return GroundCtrlClient()


async def test_fail_run(gc_client, httpx_mock):
    httpx_mock.add_response(
        url="https://ground-ctrl.test/api/pipeline/runs/run-abc/fail",
        method="POST",
        json={
            "run": {
                "id": "run-abc",
                "targetDate": "2026-05-23T00:00:00Z",
                "status": "failed",
                "errorMessage": "something broke",
                "createdAt": "2026-05-23T06:00:00Z",
            }
        },
    )

    await gc_client.fail_run("run-abc", "something broke")

    request = httpx_mock.get_request()
    assert request.headers["authorization"] == "Bearer test-secret"


async def test_submit_candidates(gc_client, httpx_mock):
    httpx_mock.add_response(
        url="https://ground-ctrl.test/api/pipeline/runs/run-abc/candidates",
        method="POST",
        json={
            "candidates": [
                {
                    "id": "cand-1",
                    "runId": "run-abc",
                    "agent": "claude",
                    "questionMd": _Q,
                    "answerMd": _A,
                    "score": 8,
                    "reviewReason": "Good",
                    "status": "pending",
                    "createdAt": "2026-05-23T06:00:00Z",
                }
            ]
        },
    )

    candidates = [
        ReviewedCandidate(
            agent=Agent.CLAUDE,
            question_md=_Q,
            answer_md=_A,
            score=8,
            review_reason="Good",
        )
    ]
    result = await gc_client.submit_candidates("run-abc", candidates)
    assert len(result) == 1
    assert result[0]["agent"] == "claude"
