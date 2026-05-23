import asyncio
import logging
from functools import partial

import feedparser

from app.clients.reddit import fetch_reddit_posts
from app.models.sources import SourceItem

logger = logging.getLogger(__name__)

RSS_FEEDS = {
    "Hacker News": "https://hnrss.org/frontpage",
    "arxiv AI": "https://rss.arxiv.org/rss/cs.AI",
    "Latent Space": "https://www.latent.space/feed",
}


def _parse_feed(source_name: str, url: str) -> list[SourceItem]:
    feed = feedparser.parse(url)
    return [
        SourceItem(
            title=entry.get("title", ""),
            url=entry.get("link", ""),
            source=source_name,
            summary=entry.get("summary", ""),
        )
        for entry in feed.entries[:10]
    ]


async def fetch_rss_sources() -> list[SourceItem]:
    """Fetch headlines from all RSS feeds concurrently in thread pool."""
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, partial(_parse_feed, name, url))
        for name, url in RSS_FEEDS.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items: list[SourceItem] = []
    for name, result in zip(RSS_FEEDS, results, strict=True):
        if isinstance(result, Exception):
            logger.warning("RSS fetch failed for %s: %s", name, result)
            continue
        items.extend(result)
    return items


async def fetch_all_sources() -> list[SourceItem]:
    """Fetch headlines from RSS feeds and Reddit concurrently."""
    rss_items, reddit_items = await asyncio.gather(
        fetch_rss_sources(),
        fetch_reddit_posts(),
    )
    return rss_items + reddit_items
