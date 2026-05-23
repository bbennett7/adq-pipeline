import feedparser

from app.clients.reddit import fetch_reddit_posts
from app.models.sources import SourceItem

RSS_FEEDS = {
    "Hacker News": "https://hnrss.org/frontpage",
    "arxiv AI": "https://rss.arxiv.org/rss/cs.AI",
    "Latent Space": "https://www.latent.space/feed",
    "Simon Willison": "https://simonwillison.net/atom/everything/",
}


async def fetch_all_sources() -> list[SourceItem]:
    """Fetch headlines from RSS feeds and Reddit."""
    items: list[SourceItem] = []

    for source_name, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            items.append(
                SourceItem(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=source_name,
                )
            )

    reddit_items = await fetch_reddit_posts()
    items.extend(reddit_items)

    return items
