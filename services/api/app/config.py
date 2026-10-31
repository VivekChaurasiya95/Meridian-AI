"""Application configuration with startup validation.

All secrets arrive via environment variables. ``Settings`` is constructed once
at application startup; missing or invalid configuration fails fast instead of
surfacing later as a runtime error. Secret values are never logged.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    app_name: str = "meridian-api"
    environment: Literal["dev", "test", "prod"] = "dev"

    # SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/meridian
    database_url: str = Field(min_length=1)
    test_database_url: str | None = None

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8010, ge=1, le=65535)

    # Comma-separated origins. Both loopback spellings are allowed so opening
    # the app via localhost or 127.0.0.1 works identically (D22).
    cors_allow_origins: str = (
        "http://localhost:3010,http://localhost:3000,http://127.0.0.1:3010,http://127.0.0.1:3000"
    )

    # Firebase social sign-in (Google/GitHub). Empty disables the endpoint.
    # Only the project ID is needed: ID tokens verify against Google's
    # published certs, so no service-account secret lives on this server.
    firebase_project_id: str = ""

    # Session auth (M2, decisions D17/D19/D20).
    session_cookie_name: str = "meridian_session"
    session_ttl_hours: int = 24
    secure_cookies: bool = False
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)
    login_max_attempts: int = 10
    login_window_seconds: int = 600

    page_default_limit: int = 25
    page_max_limit: int = 100

    @field_validator("database_url")
    @classmethod
    def _require_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("database_url must use the postgresql+psycopg:// scheme")
        return value

    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
