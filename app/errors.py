"""Shared exception types for provider calls."""


class TruncatedOutputError(RuntimeError):
    """A provider stopped because it hit its output-token ceiling.

    The text that comes back is a real answer that simply stops — usually
    mid-sentence — and it is short enough that no length check will ever look
    at it. Treating it as a failed call gives `with_retries` a chance at a
    complete one instead of publishing half a thought.
    """
