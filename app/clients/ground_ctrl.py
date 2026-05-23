import httpx

from app.config import get_settings
from app.models.candidates import ReviewedCandidate, Run


class GroundCtrlClient:
    def __init__(self) -> None:
        s = get_settings()
        self._base = s.ground_ctrl_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {s.pipeline_secret}"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, headers=self._headers, timeout=30)

    async def create_run(self, date_str: str) -> Run:
        """POST /api/pipeline/runs — start or reset a run for the given date."""
        async with self._client() as client:
            resp = await client.post("/api/pipeline/runs", json={"date": date_str})
            resp.raise_for_status()
            return Run(**resp.json()["run"])

    async def submit_candidates(
        self, run_id: str, candidates: list[ReviewedCandidate]
    ) -> list[dict]:
        """POST /api/pipeline/runs/{runId}/candidates — persist reviewed candidates."""
        payload = {
            "candidates": [
                {
                    "agent": c.agent.value,
                    "questionMd": c.question_md,
                    "answerMd": c.answer_md,
                    "score": c.score,
                    "reviewReason": c.review_reason,
                }
                for c in candidates
            ]
        }
        async with self._client() as client:
            resp = await client.post(f"/api/pipeline/runs/{run_id}/candidates", json=payload)
            resp.raise_for_status()
            return resp.json()["candidates"]

    async def fail_run(self, run_id: str, reason: str | None = None) -> Run:
        """POST /api/pipeline/runs/{runId}/fail — mark a run as failed."""
        body = {"reason": reason} if reason else {}
        async with self._client() as client:
            resp = await client.post(f"/api/pipeline/runs/{run_id}/fail", json=body)
            resp.raise_for_status()
            return Run(**resp.json()["run"])

    async def get_run(self, run_id: str) -> Run:
        """GET /api/pipeline/runs/{runId} — fetch run with candidates."""
        async with self._client() as client:
            resp = await client.get(f"/api/pipeline/runs/{run_id}")
            resp.raise_for_status()
            return Run(**resp.json()["run"])

    async def choose_candidate(
        self, run_id: str, candidate_id: str, question_md: str, answer_md: str
    ) -> dict:
        """POST /api/pipeline/runs/{runId}/choose — select, style, and publish."""
        async with self._client() as client:
            resp = await client.post(
                f"/api/pipeline/runs/{run_id}/choose",
                json={
                    "candidateId": candidate_id,
                    "questionMd": question_md,
                    "answerMd": answer_md,
                },
            )
            resp.raise_for_status()
            return resp.json()


_instance: GroundCtrlClient | None = None


def get_ground_ctrl() -> GroundCtrlClient:
    global _instance
    if _instance is None:
        _instance = GroundCtrlClient()
    return _instance
