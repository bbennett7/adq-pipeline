import asyncio
import logging

import httpx

from app.config import get_settings
from app.models.candidates import ReviewedCandidate

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2


class GroundCtrlClient:
    def __init__(self) -> None:
        s = get_settings()
        self._client = httpx.AsyncClient(
            base_url=s.ground_ctrl_url.rstrip("/"),
            headers={"Authorization": f"Bearer {s.pipeline_secret}"},
            timeout=30,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _post_with_retry(self, path: str, json: dict) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._client.post(path, json=json)
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                last_exc = e
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                    raise
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BACKOFF_BASE**attempt
                    logger.warning(
                        "Ground Ctrl request to %s failed (attempt %d/%d), retrying in %ds: %s",
                        path,
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

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
        resp = await self._post_with_retry(f"/api/pipeline/runs/{run_id}/candidates", payload)
        return resp.json()["candidates"]

    async def fail_run(self, run_id: str, reason: str | None = None) -> None:
        """POST /api/pipeline/runs/{runId}/fail — mark a run as failed."""
        body = {"reason": reason} if reason else {}
        await self._post_with_retry(f"/api/pipeline/runs/{run_id}/fail", body)


_instance: GroundCtrlClient | None = None


def get_ground_ctrl() -> GroundCtrlClient:
    global _instance
    if _instance is None:
        _instance = GroundCtrlClient()
    return _instance


async def close_ground_ctrl() -> None:
    global _instance
    if _instance is not None:
        await _instance.close()
        _instance = None
