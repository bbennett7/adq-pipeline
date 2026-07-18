import asyncio
import logging
import re

import feedparser
import httpx

from app.models.sources import SourceItem

logger = logging.getLogger(__name__)

SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "singularity",
    "LLMDevs",
    # Mainstream-user subs: where the site's non-expert reader's AI discourse
    # actually happens — required for consumer-side moment detection.
    "ChatGPT",
    "OpenAI",
]
USER_AGENT = "web:askdumbquestions.ai:0.1 (by /u/askdumbquestions)"

# hot.rss includes pinned meta posts that are noise for question generation
_MEGATHREAD_RE = re.compile(
    r"self[- ]promotion|who'?s hiring|wants? to be hired|megathread"
    r"|(monthly|weekly|daily) (discussion|thread)|open thread",
    re.IGNORECASE,
)


async def _fetch_subreddit(client: httpx.AsyncClient, sub: str) -> list[SourceItem]:
    for attempt in range(3):
        resp = await client.get(
            f"https://www.reddit.com/r/{sub}/hot.rss",
            headers={"User-Agent": USER_AGENT},
            params={"limit": 10},
        )
        if resp.status_code in (403, 429) and attempt < 2:
            wait = 2**attempt
            logger.warning("Reddit r/%s returned %d, retrying in %ds", sub, resp.status_code, wait)
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        break

    feed = feedparser.parse(resp.text)
    items: list[SourceItem] = []
    for entry in feed.entries:
        title = entry.get("title", "")
        if _MEGATHREAD_RE.search(title):
            logger.info("r/%s: skipping pinned/meta post: %s", sub, title)
            continue
        items.append(
            SourceItem(
                title=title,
                url=entry.get("link", ""),
                source=f"r/{sub}",
                summary=entry.get("summary", ""),
            )
        )
        if len(items) >= 10:
            break
    logger.info("r/%s: fetched %d posts via RSS", sub, len(items))
    for item in items[:3]:
        logger.info("  → %s", item.title)
    return items


async def fetch_reddit_posts() -> list[SourceItem]:
    """Fetch hot posts from target subreddits via RSS feeds."""
    items: list[SourceItem] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for sub in SUBREDDITS:
            try:
                items.extend(await _fetch_subreddit(client, sub))
            except Exception:
                logger.warning("Reddit fetch failed for r/%s", sub, exc_info=True)
            await asyncio.sleep(1)
    logger.info("Fetched %d Reddit posts from %d subreddits", len(items), len(SUBREDDITS))
    return items
