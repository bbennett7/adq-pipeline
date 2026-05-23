from google import genai

from app.config import get_settings

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=get_settings().google_api_key,
            http_options={"timeout": 180_000},
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        # genai.Client does not expose a close/aclose method;
        # dropping the reference lets GC clean up the underlying httpx transport.
        _client = None
