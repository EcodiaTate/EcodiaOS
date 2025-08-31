from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SIMULA_", env_file=None)

    # Core
    repo_root: str = "/app"

    # Tool timeouts (seconds)
    fmt_timeout: int = 600
    test_timeout: int = 1800

    # Health/limits
    max_apply_bytes: int = 5_000_000


settings = Settings()
