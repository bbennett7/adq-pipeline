from app.clients.reddit import SUBREDDITS, fetch_reddit_posts
from app.models.sources import SourceItem


async def test_fetches_from_all_subreddits(httpx_mock):
    for sub in SUBREDDITS:
        httpx_mock.add_response(
            url=f"https://www.reddit.com/r/{sub}/hot.json?limit=10",
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


async def test_subreddit_failure_skipped(httpx_mock):
    httpx_mock.add_response(
        url=f"https://www.reddit.com/r/{SUBREDDITS[0]}/hot.json?limit=10",
        status_code=403,
    )
    for sub in SUBREDDITS[1:]:
        httpx_mock.add_response(
            url=f"https://www.reddit.com/r/{sub}/hot.json?limit=10",
            json={"data": {"children": [{"data": {"title": "OK", "permalink": f"/r/{sub}/1"}}]}},
        )

    items = await fetch_reddit_posts()
    assert len(items) == 3
