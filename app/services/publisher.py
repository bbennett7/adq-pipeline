import logging

logger = logging.getLogger(__name__)


async def auto_publish() -> None:
    """Execute the auto-publish fallback chain (9am PT).

    Priority:
    1. Question already scheduled for today -> publish as-is
    2. Unreviewed pipeline run -> choose top candidate -> resources -> style -> publish
    3. Unpublished questions in pool -> pick one, style, publish
    4. Rejected candidates in pool -> pick one, style, publish
    5. Nothing available -> send "nothing to publish" push
    """
    # TODO: implement fallback chain — needs DB reads + Ground Ctrl calls
    raise NotImplementedError
