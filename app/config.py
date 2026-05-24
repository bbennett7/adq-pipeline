from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    pipeline_secret: str
    ground_ctrl_url: str

    anthropic_api_key: str
    openai_api_key: str
    google_api_key: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
