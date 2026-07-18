from enum import StrEnum

from pydantic import BaseModel, Field


class MomentStrength(StrEnum):
    STRONG = "strong"
    WEAK = "weak"


class Moment(BaseModel):
    """A cultural moment detected across today's source material."""

    title: str = Field(min_length=5, max_length=200)
    why_now: str = Field(min_length=5, max_length=500)
    teachable_angle: str = Field(min_length=5, max_length=500)
    strength: MomentStrength = MomentStrength.WEAK
    sources: list[str] = Field(default_factory=list)
