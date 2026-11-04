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

    # Project archive ingestion (M3). All sizes in bytes unless named *_mb.
    # Uploads are processed synchronously in the request (no M4 job queue
    # yet), so caps stay conservative. Documented in .env.example.
    upload_max_mb: int = Field(default=25, ge=1, le=256)
    extracted_max_mb: int = Field(default=200, ge=1, le=2048)
    max_archive_files: int = Field(default=5000, ge=1, le=50000)
    max_archive_depth: int = Field(default=20, ge=1, le=64)
    max_compression_ratio: int = Field(default=100, ge=1, le=1000)
    preview_max_bytes: int = Field(default=65536, ge=1024, le=1048576)
    index_budget_bytes: int = Field(default=2097152, ge=65536, le=16777216)

    # Upload rate limiting (M4 hardening, same dev-scale sliding window as
    # login per D20): per-user caps so concurrent uploads cannot exhaust
    # the API workers that process archives synchronously.
    upload_rate_max: int = Field(default=20, ge=1, le=1000)
    upload_rate_window_seconds: int = Field(default=3600, ge=60, le=86400)

    # Durable jobs (M4). Lease/heartbeat follow D10 (60s TTL default).
    worker_lease_seconds: int = Field(default=60, ge=10, le=3600)
    worker_heartbeat_seconds: int = Field(default=20, ge=5, le=600)
    worker_poll_seconds: int = Field(default=5, ge=1, le=120)
    job_max_attempts: int = Field(default=5, ge=1, le=25)
    job_retry_base_seconds: int = Field(default=30, ge=1, le=3600)
    job_retry_max_seconds: int = Field(default=3600, ge=60, le=86400)

    # Sandbox quotas (M5.3). Trusted operator configuration: API payloads
    # can never override these. Running jobs with expired leases do not
    # count (they are reclaimable, not live).
    sandbox_max_running_jobs_per_workspace: int = Field(default=10, ge=1, le=1000)

    # Immutable snapshot content storage (M5.1, private MinIO bucket).
    # NOTE for local runs: the host-mapped MinIO API port is 9010, so a
    # local .env needs S3_ENDPOINT_URL=http://localhost:9010 (the
    # in-container default below only fits Docker networking).
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    s3_repositories_bucket: str = "meridian-repositories"

    @property
    def upload_max_bytes(self) -> int:
        return self.upload_max_mb * 1024 * 1024

    @property
    def extracted_max_bytes(self) -> int:
        return self.extracted_max_mb * 1024 * 1024

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
