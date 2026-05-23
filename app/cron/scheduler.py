import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.dates import PT

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _is_weekday() -> bool:
    return datetime.now(PT).weekday() < 5


async def _morning_run() -> None:
    if not _is_weekday():
        return
    from app.services.pipeline import run_pipeline

    logger.info("Cron: starting morning pipeline run")
    try:
        await run_pipeline()
    except Exception:
        logger.exception("Cron: morning run failed")


async def _warning_push() -> None:
    if not _is_weekday():
        return
    from app.services.notifications import notify_publish_warning

    logger.info("Cron: sending 8:45am warning")
    # TODO: only send if run is still awaiting_review
    await notify_publish_warning()


async def _auto_publish() -> None:
    if not _is_weekday():
        return
    from app.services.publisher import auto_publish

    logger.info("Cron: running auto-publish at 9am")
    try:
        await auto_publish()
    except Exception:
        logger.exception("Cron: auto-publish failed")


def start_scheduler() -> None:
    scheduler.add_job(_morning_run, CronTrigger(hour=6, minute=0, timezone=PT), id="morning_run")
    scheduler.add_job(_warning_push, CronTrigger(hour=8, minute=45, timezone=PT), id="warning_push")
    scheduler.add_job(_auto_publish, CronTrigger(hour=9, minute=0, timezone=PT), id="auto_publish")
    scheduler.start()
    logger.info("Scheduler started — 6:00am / 8:45am / 9:00am PT weekdays")
