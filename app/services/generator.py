import asyncio

from app.models.candidates import GeneratedCandidate
from app.models.sources import SourceItem


async def _generate_claude(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    """Generate 2 candidates using claude-sonnet-4-6."""
    # TODO: implement with Anthropic client
    raise NotImplementedError


async def _generate_gpt4(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    """Generate 2 candidates using gpt-4o."""
    # TODO: implement with OpenAI client
    raise NotImplementedError


async def _generate_gemini(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    """Generate 2 candidates using gemini-2.0-flash."""
    # TODO: implement with Gemini client
    raise NotImplementedError


async def generate_candidates(sources: list[SourceItem]) -> list[GeneratedCandidate]:
    """Run all three models in parallel, returning 6 candidates."""
    results = await asyncio.gather(
        _generate_claude(sources),
        _generate_gpt4(sources),
        _generate_gemini(sources),
    )
    return [c for batch in results for c in batch]
