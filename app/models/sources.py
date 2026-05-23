from pydantic import BaseModel, field_validator


class SourceItem(BaseModel):
    """A headline or post from an RSS feed or Reddit."""

    title: str
    url: str
    source: str
    summary: str = ""

    @field_validator("summary")
    @classmethod
    def truncate_summary(cls, v: str) -> str:
        return v[:500] if len(v) > 500 else v
