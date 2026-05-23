from app.models.candidates import GeneratedCandidate, ReviewedCandidate


async def review_candidates(candidates: list[GeneratedCandidate]) -> list[ReviewedCandidate]:
    """Score all candidates with claude-sonnet-4-6. Returns top 3 by score."""
    # TODO: implement — call Claude with structured output to score each candidate 1-10
    raise NotImplementedError
