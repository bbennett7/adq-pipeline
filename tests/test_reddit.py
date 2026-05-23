from unittest.mock import patch

import pytest

from app.clients.reddit import SUBREDDITS, fetch_reddit_posts
from app.models.sources import SourceItem


@pytest.fixture()
def _reddit_creds():
    with patch("app.clients.reddit.get_settings") as mock:
        mock.return_value.reddit_client_id = "test-id"
        mock.return_value.reddit_client_secret = "test-secret"
        yield


async def test_no_credentials_returns_empty():
    with patch("app.clients.reddit.get_settings") as mock:
        mock.return_value.reddit_client_id = ""
        result = await fetch_reddit_posts()
    assert result == []


@pytest.mark.usefixtures("_reddit_creds")
async def test_fetches_from_all_subreddits(httpx_mock):
    httpx_mock.add_response(
        url="https://www.reddit.com/api/v1/access_token",
        json={"access_token": "fake-token"},
    )
    for sub in SUBREDDITS:
        httpx_mock.add_response(
            url=f"https://oauth.reddit.com/r/{sub}/hot?limit=10",
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": f"Post from {sub}",
                                "permalink": f"/r/{sub}/123",
                                "selftext": f"Body of {sub} post",
                            }
                        },
                    ]
                }
            },
        )

    items = await fetch_reddit_posts()
    assert len(items) == 4
    assert all(isinstance(i, SourceItem) for i in items)
    assert {i.source for i in items} == {f"r/{s}" for s in SUBREDDITS}
    assert all(i.summary for i in items)


@pytest.mark.usefixtures("_reddit_creds")
async def test_subreddit_failure_skipped(httpx_mock):
    httpx_mock.add_response(
        url="https://www.reddit.com/api/v1/access_token",
        json={"access_token": "fake-token"},
    )
    httpx_mock.add_response(
        url=f"https://oauth.reddit.com/r/{SUBREDDITS[0]}/hot?limit=10",
        status_code=403,
    )
    for sub in SUBREDDITS[1:]:
        httpx_mock.add_response(
            url=f"https://oauth.reddit.com/r/{sub}/hot?limit=10",
            json={"data": {"children": [{"data": {"title": "OK", "permalink": f"/r/{sub}/1"}}]}},
        )

    items = await fetch_reddit_posts()
    assert len(items) == 3
