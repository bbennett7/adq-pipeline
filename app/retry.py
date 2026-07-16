import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 2


async def with_retries[T](
    fn: Callable[[], Awaitable[T]],
    *,
    label: str,
    max_retries: int = MAX_RETRIES,
) -> T:
    """Run fn, retrying on any exception up to max_retries times with exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                delay = RETRY_BACKOFF_BASE**attempt
                logger.warning(
                    "%s failed (attempt %d/%d), retrying in %ds: %s",
                    label,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)
    logger.error("%s failed after %d attempts: %s", label, max_retries + 1, last_exc)
    raise last_exc  # type: ignore[misc]
