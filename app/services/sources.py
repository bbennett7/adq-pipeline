import asyncio
import logging

import feedparser
import httpx

from app.clients.reddit import fetch_reddit_posts
from app.models.sources import SourceItem

logger = logging.getLogger(__name__)

RSS_FEED_TIMEOUT = 15

RSS_FEEDS = {
    "Hacker News": "https://hnrss.org/frontpage",
    "arxiv AI": "https://rss.arxiv.org/rss/cs.AI",
    "Latent Space": "https://www.latent.space/feed",
    "TechCrunch": "https://techcrunch.com/feed/",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    "Ars Technica Science": "https://feeds.arstechnica.com/arstechnica/science",
    "Quanta Magazine": "https://api.quantamagazine.org/feed/",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Lobsters": "https://lobste.rs/rss",
}


async def _fetch_feed(client: httpx.AsyncClient, source_name: str, url: str) -> list[SourceItem]:
    response = await client.get(url)
    response.raise_for_status()
    feed = feedparser.parse(response.text)
    if feed.bozo:
        logger.warning("Malformed feed from %s: %s", source_name, feed.bozo_exception)
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
    """Fetch headlines from all RSS feeds concurrently."""
    async with httpx.AsyncClient(
        timeout=RSS_FEED_TIMEOUT,
        headers={"User-Agent": "adq-pipeline/0.1"},
    ) as client:
        tasks = [_fetch_feed(client, name, url) for name, url in RSS_FEEDS.items()]
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
    results = await asyncio.gather(
        fetch_rss_sources(),
        fetch_reddit_posts(),
        return_exceptions=True,
    )
    items: list[SourceItem] = []
    source_names = ["RSS", "Reddit"]
    for name, result in zip(source_names, results, strict=True):
        if isinstance(result, Exception):
            logger.warning("%s source failed: %s", name, result)
            continue
        items.extend(result)
    return items
