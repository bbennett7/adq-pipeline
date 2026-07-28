import asyncio
import logging

from app.clients.ground_ctrl import get_ground_ctrl
from app.config import get_settings
from app.services.gate import apply_gate
from app.services.generator import generate_candidates
from app.services.reviewer import review_candidates
from app.services.sources import fetch_all_sources
from app.services.zeitgeist import detect_moments

logger = logging.getLogger(__name__)


async def _fetch_recent_questions(gc) -> list[str]:
    """Recent question history for dedup. A failure here must not kill the run."""
    try:
        recent = await gc.get_recent_questions()
        logger.info("Fetched %d recent questions for dedup", len(recent))
        return recent
    except Exception as e:
        logger.warning("Could not fetch recent questions, proceeding without dedup: %s", e)
        return []


async def run_pipeline(run_id: str, topic: str | None = None) -> dict:
    """Execute the full pipeline: sources -> generate -> review -> persist.

    With a topic, this is an owner-requested run: generation is steered toward
    the topic instead of today's detected moments, and the resulting
    candidates append to the run's existing slate in Ground Ctrl.

    Returns the run and candidate data from Ground Ctrl.
    """
    gc = get_ground_ctrl()
    logger.info("Started run %s%s", run_id, f" (topic: {topic})" if topic else "")

    try:
        async with asyncio.timeout(600):
            settings = get_settings()
            sources, recent = await asyncio.gather(
                fetch_all_sources(),
                _fetch_recent_questions(gc),
            )
            if not sources:
                raise RuntimeError("No source material fetched from any provider")
            logger.info("Fetched %d source items", len(sources))

            # The topic IS the moment on a topic run — skip zeitgeist detection.
            moments = [] if topic else await detect_moments(sources)

            candidates = await generate_candidates(sources, recent, moments, topic=topic)
            logger.info("Generated %d candidates", len(candidates))

            # Similarity gate: drop near-repeats of anything already
            # published or previously offered before review sees them.
            sim_results = await gc.check_similarity(
                [{"questionMd": c.question_md, "answerMd": c.answer_md} for c in candidates]
            )
            outcome = apply_gate(
                candidates,
                sim_results,
                threshold=settings.similarity_threshold,
                floor=settings.gate_floor,
            )
            gated = [g.candidate for g in outcome.kept]
            near_repeats = {
                i: g.near_repeat_of for i, g in enumerate(outcome.kept) if g.near_repeat_of
            }

            reviewed = await review_candidates(gated, recent, moments, near_repeats, topic=topic)
            logger.info("Reviewed — top %d candidates scored", len(reviewed))

            # Surface the gate flag in the owner-facing review reason.
            flagged = {
                g.candidate.question_md: g.near_repeat_of for g in outcome.kept if g.near_repeat_of
            }
            for r in reviewed:
                repeat_of = flagged.get(r.question_md)
                if repeat_of:
                    r.review_reason = f'⚠ near-repeat of "{repeat_of[:60]}" · {r.review_reason}'[
                        :300
                    ]

            persisted = await gc.submit_candidates(run_id, reviewed, topic=topic)
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
