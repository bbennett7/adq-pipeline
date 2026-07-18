from app.clients.reddit import SUBREDDITS, fetch_reddit_posts
from app.models.sources import SourceItem

FAKE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Post from {sub}</title>
    <link href="https://www.reddit.com/r/{sub}/comments/abc/post"/>
    <summary>Body of {sub} post</summary>
  </entry>
</feed>"""


async def test_fetches_from_all_subreddits(httpx_mock):
    for sub in SUBREDDITS:
        httpx_mock.add_response(
            url=f"https://www.reddit.com/r/{sub}/hot.rss?limit=10",
            text=FAKE_RSS.format(sub=sub),
            headers={"Content-Type": "application/xml"},
        )

    items = await fetch_reddit_posts()
    assert len(items) == len(SUBREDDITS)
    assert all(isinstance(i, SourceItem) for i in items)
    assert {i.source for i in items} == {f"r/{s}" for s in SUBREDDITS}


async def test_megathreads_filtered(httpx_mock):
    meta_feed = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>[D] Self-Promotion Thread</title>
    <link href="https://www.reddit.com/r/x/comments/1/post"/>
  </entry>
  <entry>
    <title>[D] Monthly Who's Hiring and Who wants to be Hired?</title>
    <link href="https://www.reddit.com/r/x/comments/2/post"/>
  </entry>
  <entry>
    <title>A real post about a new model release</title>
    <link href="https://www.reddit.com/r/x/comments/3/post"/>
    <summary>Real content</summary>
  </entry>
</feed>"""
    for sub in SUBREDDITS:
        httpx_mock.add_response(
            url=f"https://www.reddit.com/r/{sub}/hot.rss?limit=10",
            text=meta_feed,
            headers={"Content-Type": "application/xml"},
        )

    items = await fetch_reddit_posts()
    assert len(items) == len(SUBREDDITS)
    assert all("real post" in i.title.lower() for i in items)


async def test_subreddit_failure_skipped(httpx_mock):
    for _ in range(3):
        httpx_mock.add_response(
            url=f"https://www.reddit.com/r/{SUBREDDITS[0]}/hot.rss?limit=10",
            status_code=403,
        )
    for sub in SUBREDDITS[1:]:
        httpx_mock.add_response(
            url=f"https://www.reddit.com/r/{sub}/hot.rss?limit=10",
            text=FAKE_RSS.format(sub=sub),
            headers={"Content-Type": "application/xml"},
        )

    items = await fetch_reddit_posts()
    assert len(items) == len(SUBREDDITS) - 1
