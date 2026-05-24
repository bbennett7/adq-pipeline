from pydantic import BaseModel


class ResourceSuggestion(BaseModel):
    url: str
    label: str
    source: str
    author: str | None = None
