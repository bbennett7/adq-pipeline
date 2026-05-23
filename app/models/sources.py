from datetime import datetime

from pydantic import BaseModel


class SourceItem(BaseModel):
    """A headline or post from an RSS feed or Reddit."""

    title: str
    url: str
    source: str
    summary: str = ""
    published_at: datetime | None = None
