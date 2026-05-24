import asyncio
import logging

from app.clients.ground_ctrl import get_ground_ctrl
from app.services.generator import generate_candidates
from app.services.reviewer import review_candidates
from app.services.sources import fetch_all_sources

logger = logging.getLogger(__name__)


async def run_pipeline(run_id: str) -> dict:
    """Execute the full pipeline: sources -> generate -> review -> persist.

    Returns the run and candidate data from Ground Ctrl.
    """
    gc = get_ground_ctrl()
    logger.info("Started run %s", run_id)

    try:
        async with asyncio.timeout(600):
            sources = await fetch_all_sources()
            if not sources:
                raise RuntimeError("No source material fetched from any provider")
            logger.info("Fetched %d source items", len(sources))

            candidates = await generate_candidates(sources)
            logger.info("Generated %d candidates", len(candidates))

            reviewed = await review_candidates(candidates)
            logger.info("Reviewed — top %d candidates scored", len(reviewed))

            persisted = await gc.submit_candidates(run_id, reviewed)
            logger.info("Persisted %d candidates to Ground Ctrl", len(persisted))

            return {"run_id": run_id, "candidates": persisted}

    except Exception as e:
        logger.exception("Pipeline failed for run %s", run_id)
        safe_reason = f"{type(e).__name__}: {str(e)[:200]}"
        try:
            await gc.fail_run(run_id, safe_reason)
        except Exception:
            logger.exception("Additionally, fail_run itself failed for run %s", run_id)
        raise
