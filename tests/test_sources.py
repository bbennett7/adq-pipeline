from unittest.mock import patch

import httpx
import pytest

from app.models.sources import SourceItem
from app.services.sources import fetch_all_sources, fetch_rss_sources

FAKE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <item>
    <title>Test Article 1</title>
    <link>https://example.com/1</link>
    <description>A summary of article 1</description>
  </item>
  <item>
    <title>Test Article 2</title>
    <link>https://example.com/2</link>
    <description>A summary of article 2</description>
  </item>
</channel>
</rss>"""


def _mock_all_feeds(httpx_mock):
    for url in [
        "https://hnrss.org/frontpage",
        "https://rss.arxiv.org/rss/cs.AI",
        "https://www.latent.space/feed",
    ]:
        httpx_mock.add_response(url=url, text=FAKE_RSS_XML)


@pytest.fixture()
def _fake_feeds(httpx_mock):
    """Mock HTTP responses for all RSS feeds."""
    _mock_all_feeds(httpx_mock)


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


async def test_rss_feed_failure_is_graceful(httpx_mock):
    """A single feed failing shouldn't break the whole fetch."""
    httpx_mock.add_exception(
        httpx.ConnectError("DNS failure"),
        url="https://hnrss.org/frontpage",
    )
    httpx_mock.add_response(url="https://rss.arxiv.org/rss/cs.AI", text=FAKE_RSS_XML)
    httpx_mock.add_response(url="https://www.latent.space/feed", text=FAKE_RSS_XML)
    items = await fetch_rss_sources()
    assert len(items) == 4  # 2 feeds succeeded with 2 entries each


async def test_rss_feed_timeout_is_graceful(httpx_mock):
    """A feed that times out shouldn't block the pipeline."""
    httpx_mock.add_exception(
        httpx.ReadTimeout("timed out"),
        url="https://hnrss.org/frontpage",
    )
    httpx_mock.add_response(url="https://rss.arxiv.org/rss/cs.AI", text=FAKE_RSS_XML)
    httpx_mock.add_response(url="https://www.latent.space/feed", text=FAKE_RSS_XML)
    items = await fetch_rss_sources()
    assert len(items) == 4  # 2 feeds succeeded


async def test_reddit_failure_does_not_crash_pipeline(httpx_mock):
    """Reddit going down should not prevent RSS sources from returning."""
    _mock_all_feeds(httpx_mock)
    with patch(
        "app.services.sources.fetch_reddit_posts",
        side_effect=RuntimeError("Reddit OAuth 500"),
    ):
        items = await fetch_all_sources()
    assert len(items) == 6  # all RSS items still returned
    assert all(isinstance(i, SourceItem) for i in items)
