from pydantic import BaseModel, field_validator


class SourceItem(BaseModel):
    """A headline or post from an RSS feed or Reddit."""

    title: str
    url: str
    source: str
    summary: str = ""

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        cleaned = "".join(c for c in v if c.isprintable())
        return cleaned[:200] if len(cleaned) > 200 else cleaned

    @field_validator("source")
    @classmethod
    def sanitize_source(cls, v: str) -> str:
        cleaned = "".join(c for c in v if c.isprintable())
        return cleaned[:100] if len(cleaned) > 100 else cleaned

    @field_validator("summary")
    @classmethod
    def truncate_summary(cls, v: str) -> str:
        cleaned = "".join(c for c in v if c.isprintable())
        return cleaned[:500] if len(cleaned) > 500 else cleaned
