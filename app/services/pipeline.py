import logging

from app.clients.ground_ctrl import get_ground_ctrl
from app.dates import today_pt
from app.services.generator import generate_candidates
from app.services.notifications import notify_candidates_ready
from app.services.reviewer import review_candidates
from app.services.sources import fetch_all_sources

logger = logging.getLogger(__name__)


async def run_pipeline(date_str: str | None = None) -> dict:
    """Execute the full pipeline: sources -> generate -> review -> persist -> notify.

    Returns the run and candidate data from Ground Ctrl.
    """
    if date_str is None:
        date_str = today_pt().isoformat()

    gc = get_ground_ctrl()
    run = await gc.create_run(date_str)
    logger.info("Started run %s for %s", run.id, date_str)

    try:
        sources = await fetch_all_sources()
        logger.info("Fetched %d source items", len(sources))

        candidates = await generate_candidates(sources)
        logger.info("Generated %d candidates", len(candidates))

        reviewed = await review_candidates(candidates)
        logger.info("Reviewed — top %d candidates scored", len(reviewed))

        persisted = await gc.submit_candidates(run.id, reviewed)
        logger.info("Persisted %d candidates to Ground Ctrl", len(persisted))

        await notify_candidates_ready()

        return {"run_id": run.id, "date": date_str, "candidates": persisted}

    except Exception as e:
        logger.exception("Pipeline failed for %s", date_str)
        await gc.fail_run(run.id, str(e)[:1000])
        raise
