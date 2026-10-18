"""Runtime settings from the environment and .env (never read .env any other way).

Additive changes are fine in a lane's branch; keep every key in .env.example too.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    model_reader: str = "claude-sonnet-5-5"
    model_checker: str = "claude-haiku-5-5"
    jev_model: str = "typesafe/jev-1.13"
    jev_enabled: bool = True
    cache_mode: Literal["record", "replay", "live"] = "replay"
    database_url: str = "postgresql://alinka:alinka@localhost:5432/alinka"
    edge_secret: SecretStr | None = None  # empty locally: the API then accepts direct calls
    admin_token: SecretStr | None = None
    app_secret: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
