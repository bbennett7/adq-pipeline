import asyncio
import logging

import httpx

from app.config import get_settings
from app.models.sources import SourceItem

logger = logging.getLogger(__name__)

SUBREDDITS = ["MachineLearning", "LocalLLaMA", "singularity", "LLMDevs"]


async def _fetch_subreddit(client: httpx.AsyncClient, token: str, sub: str) -> list[SourceItem]:
    resp = await client.get(
        f"https://oauth.reddit.com/r/{sub}/hot",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "adq-pipeline/0.1"},
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
    s = get_settings()
    if not s.reddit_client_id:
        logger.info("Reddit credentials not configured, skipping")
        return []

    auth = (s.reddit_client_id, s.reddit_client_secret)
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": "adq-pipeline/0.1"},
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        results = await asyncio.gather(
            *[_fetch_subreddit(client, token, sub) for sub in SUBREDDITS],
            return_exceptions=True,
        )
        items: list[SourceItem] = []
        for sub, result in zip(SUBREDDITS, results, strict=True):
            if isinstance(result, Exception):
                logger.warning("Reddit fetch failed for r/%s: %s", sub, result)
                continue
            items.extend(result)
        return items
