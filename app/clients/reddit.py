import asyncio
import logging

import httpx

from app.models.sources import SourceItem

logger = logging.getLogger(__name__)

SUBREDDITS = ["MachineLearning", "LocalLLaMA", "singularity", "LLMDevs"]
USER_AGENT = "web:askdumbquestions.ai:0.1 (by /u/askdumbquestions)"


async def _fetch_subreddit(client: httpx.AsyncClient, sub: str) -> list[SourceItem]:
    for attempt in range(3):
        resp = await client.get(
            f"https://www.reddit.com/r/{sub}/hot.json",
            headers={"User-Agent": USER_AGENT},
            params={"limit": 10},
        )
        if resp.status_code == 403 and attempt < 2:
            await asyncio.sleep(2**attempt)
            continue
        resp.raise_for_status()
        break
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
    items: list[SourceItem] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for sub in SUBREDDITS:
            try:
                items.extend(await _fetch_subreddit(client, sub))
            except Exception:
                logger.warning("Reddit fetch failed for r/%s", sub, exc_info=True)
            await asyncio.sleep(1)
    return items
