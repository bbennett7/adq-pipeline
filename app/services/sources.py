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
    "Hacker News AI": "https://hnrss.org/newest?q=AI&points=100",
    "arxiv AI": "https://rss.arxiv.org/rss/cs.AI",
    "Latent Space": "https://www.latent.space/feed",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "MIT Technology Review AI": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "Ars Technica AI": "https://arstechnica.com/ai/feed/",
    "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "Simon Willison": "https://simonwillison.net/atom/everything/",
    "OpenAI News": "https://openai.com/news/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "Import AI": "https://importai.substack.com/feed",
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
        follow_redirects=True,
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
