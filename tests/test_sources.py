from unittest.mock import patch

import pytest

from app.models.sources import SourceItem
from app.services.sources import fetch_all_sources, fetch_rss_sources


@pytest.fixture()
def _fake_feeds():
    """Patch feedparser.parse to return canned entries."""
    fake_feed = type(
        "Feed",
        (),
        {
            "entries": [
                {
                    "title": "Test Article 1",
                    "link": "https://example.com/1",
                    "summary": "A summary of article 1",
                },
                {
                    "title": "Test Article 2",
                    "link": "https://example.com/2",
                    "summary": "A summary of article 2",
                },
            ]
        },
    )()
    with patch("app.services.sources.feedparser.parse", return_value=fake_feed):
        yield


@pytest.fixture()
def _no_reddit():
    """Patch Reddit client to return empty (no credentials)."""
    with patch("app.services.sources.fetch_reddit_posts", return_value=[]):
        yield


@pytest.mark.usefixtures("_fake_feeds")
async def test_fetch_rss_sources_returns_items():
    items = await fetch_rss_sources()
    assert len(items) == 6  # 2 entries × 3 feeds
    assert all(isinstance(i, SourceItem) for i in items)
    sources = {i.source for i in items}
    assert sources == {"Hacker News", "arxiv AI", "Latent Space"}


@pytest.mark.usefixtures("_fake_feeds")
async def test_rss_items_have_correct_fields():
    items = await fetch_rss_sources()
    first = items[0]
    assert first.title == "Test Article 1"
    assert first.url == "https://example.com/1"
    assert first.summary == "A summary of article 1"


@pytest.mark.usefixtures("_fake_feeds", "_no_reddit")
async def test_fetch_all_sources_combines_rss_and_reddit():
    items = await fetch_all_sources()
    assert len(items) == 6  # RSS only since Reddit returns []


async def test_rss_feed_failure_is_graceful():
    """A single feed failing shouldn't break the whole fetch."""
    call_count = 0

    def flaky_parse(url):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("DNS failure")
        return type("Feed", (), {"entries": [{"title": "OK", "link": "https://ok.com"}]})()

    with patch("app.services.sources.feedparser.parse", side_effect=flaky_parse):
        items = await fetch_rss_sources()
    assert len(items) == 2  # 2 feeds succeeded with 1 entry each
