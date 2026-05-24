from pydantic import BaseModel, Field


class ResourceSuggestion(BaseModel):
    url: str = Field(max_length=2000)
    label: str = Field(max_length=500)
    source: str = Field(max_length=200)
    author: str | None = Field(default=None, max_length=200)
