import asyncio
import logging

import httpx

from app.models.sources import SourceItem

logger = logging.getLogger(__name__)

SUBREDDITS = ["MachineLearning", "LocalLLaMA", "singularity", "LLMDevs"]
USER_AGENT = "adq-pipeline/0.1"


async def _fetch_subreddit(client: httpx.AsyncClient, sub: str) -> list[SourceItem]:
    resp = await client.get(
        f"https://www.reddit.com/r/{sub}/hot.json",
        headers={"User-Agent": USER_AGENT},
        params={"limit": 10},
    )
    resp.raise_for_status()
    items: list[SourceItem] = []
    for post in resp.json().get("data", {}).get("children", []):
        d = post["data"]
        items.append(
            SourceItem(
                title=d["title"],
                url=f"https://reddit.com{d['permalink']}",
                source=f"r/{sub}",
                summary=d.get("selftext", ""),
            )
        )
    return items


async def fetch_reddit_posts() -> list[SourceItem]:
    """Fetch top posts from target subreddits."""
    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(
            *[_fetch_subreddit(client, sub) for sub in SUBREDDITS],
            return_exceptions=True,
        )
        items: list[SourceItem] = []
        for sub, result in zip(SUBREDDITS, results, strict=True):
            if isinstance(result, Exception):
                logger.warning("Reddit fetch failed for r/%s: %s", sub, result)
                continue
            items.extend(result)
        return items
