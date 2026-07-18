from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    pipeline_secret: str
    ground_ctrl_url: str

    anthropic_api_key: str
    openai_api_key: str
    google_api_key: str

    # Similarity gate: candidates scoring above this against the corpus of
    # published questions + past candidates (or against a same-batch sibling)
    # are dropped as repeats. Calibrated 2026-07-17 against the live corpus:
    # exact repeats 0.84-0.86, paraphrased repeats ~0.80, same-topic fresh
    # angle ~0.71, novel <0.4. Embeddings are question+answer text.
    similarity_threshold: float = 0.78
    # Never deliver fewer than this many candidates to review — backfill with
    # the least-similar dropped ones (flagged) rather than thin the slate.
    gate_floor: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
