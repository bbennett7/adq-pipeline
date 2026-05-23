import httpx

from app.config import get_settings
from app.models.sources import SourceItem

SUBREDDITS = ["MachineLearning", "LocalLLaMA", "singularity", "LLMDevs"]


async def fetch_reddit_posts() -> list[SourceItem]:
    """Fetch top posts from target subreddits."""
    s = get_settings()
    if not s.reddit_client_id:
        return []

    auth = (s.reddit_client_id, s.reddit_client_secret)
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": "adq-pipeline/0.1"},
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]

        items: list[SourceItem] = []
        for sub in SUBREDDITS:
            resp = await client.get(
                f"https://oauth.reddit.com/r/{sub}/hot",
                headers={"Authorization": f"Bearer {token}", "User-Agent": "adq-pipeline/0.1"},
                params={"limit": 10},
            )
            if resp.status_code != 200:
                continue
            for post in resp.json().get("data", {}).get("children", []):
                d = post["data"]
                items.append(
                    SourceItem(
                        title=d["title"],
                        url=f"https://reddit.com{d['permalink']}",
                        source=f"r/{sub}",
                        summary=d.get("selftext", "")[:500],
                    )
                )
        return items
