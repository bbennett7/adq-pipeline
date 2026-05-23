async def retrieve_resources(question_md: str, answer_md: str) -> list[dict]:
    """Vector search for related resources; generative fallback if no match.

    Returns a list of resource dicts to attach to the published question.
    """
    # TODO: implement — embed with text-embedding-3-small, query resources table,
    #        fall back to Claude-generated URL + metadata if nothing above threshold
    raise NotImplementedError
