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

    # Write rate limiting (security T5, same dev-scale sliding window as
    # login/uploads per D20): per-user caps on the mutating routes that
    # otherwise let one caller queue unbounded verification reruns,
    # reports, downloads, and hypothesis reviews.
    write_rate_max: int = Field(default=60, ge=1, le=1000)
    write_rate_window_seconds: int = Field(default=3600, ge=60, le=86400)

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

    # Git import (public GitHub only). Trusted operator configuration:
    # API payloads can never override these. File-count/bytes/depth reuse
    # the archive caps so ZIP and Git share one resource language.
    git_import_timeout_seconds: int = Field(default=120, ge=10, le=600)
    git_import_max_file_mb: int = Field(default=25, ge=1, le=256)
    git_import_max_attempts: int = Field(default=2, ge=1, le=5)

    # Security preflight (V1). Trusted operator configuration: API
    # payloads can never override these. Image pins must stay explicit
    # tags (never :latest); the sandbox validates the format again at
    # execution time. Execution limits live in the sandbox profiles
    # (code, change-controlled), not here.
    preflight_enabled: bool = True
    preflight_semgrep_image: str = "semgrep/semgrep:1.183.0"
    preflight_gitleaks_image: str = "zricethezav/gitleaks:v8.30.1"
    preflight_max_findings: int = Field(default=5000, ge=100, le=50000)

    # Immutable snapshot content storage (M5.1, private MinIO bucket).
    # NOTE for local runs: the host-mapped MinIO API port is 9010, so a
    # local .env needs S3_ENDPOINT_URL=http://localhost:9010 (the
    # in-container default below only fits Docker networking).
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    s3_repositories_bucket: str = "meridian-repositories"

    # Investigation evidence (M6, private MinIO bucket). Downloads are
    # authorized per request and served as short-lived signed URLs only.
    s3_evidence_bucket: str = "meridian-evidence"
    evidence_download_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    evidence_max_artifact_mb: int = Field(default=50, ge=1, le=512)
    evidence_max_files: int = Field(default=32, ge=1, le=256)

    # Browser reproduction (M6). Trusted operator configuration: the API
    # validates user steps against these same caps; payloads never widen
    # them. Only the static-file start profile exists in M6.
    repro_max_steps: int = Field(default=20, ge=1, le=100)
    repro_step_text_max: int = Field(default=500, ge=1, le=5000)
    repro_selector_max: int = Field(default=300, ge=1, le=2000)
    repro_route_max: int = Field(default=500, ge=1, le=2000)

    # Model provider (M7). Default "fake" means UNCONFIGURED: reasoning
    # stages block honestly until an operator sets a real provider.
    # Test doubles are injected directly, never via this setting.
    model_provider: str = "fake"
    model_api_base: str = ""
    model_api_key: str = ""
    model_name: str = ""
    model_timeout_seconds: int = Field(default=60, ge=5, le=600)
    model_max_attempts: int = Field(default=3, ge=1, le=10)

    # Patches (M8): unified diffs only, validated before storage.
    patch_max_diff_kb: int = Field(default=200, ge=1, le=2048)
    patch_diff_inline_kb: int = Field(default=64, ge=1, le=1024)

    # Meta Llama provider (Slices 2-3). Disabled by default: the app
    # keeps working and reasoning stages block honestly until an operator
    # sets META_API_KEY and operator-verified model IDs. Never log keys.
    meta_enabled: bool = False
    meta_provider: str = ""
    meta_base_url: str = ""
    meta_api_key: str = ""
    meta_model_default: str = ""
    meta_model_reasoning: str = ""
    meta_model_fast: str = ""
    meta_model_report: str = ""
    meta_request_timeout: int = Field(default=60, ge=5, le=600)
    meta_max_retries: int = Field(default=3, ge=1, le=10)
    meta_max_concurrent_requests: int = Field(default=4, ge=1, le=64)
    meta_max_input_tokens: int = Field(default=32000, ge=512, le=200000)
    meta_max_output_tokens: int = Field(default=4096, ge=64, le=32768)
    ai_default_provider: str = "existing"
    ai_fallback_enabled: bool = False
    ai_log_request_metadata: bool = True
    ai_log_prompt_content: bool = False

    @property
    def upload_max_bytes(self) -> int:
        return self.upload_max_mb * 1024 * 1024

    @property
    def extracted_max_bytes(self) -> int:
        return self.extracted_max_mb * 1024 * 1024

    @property
    def git_import_max_file_bytes(self) -> int:
        return self.git_import_max_file_mb * 1024 * 1024

    @property
    def evidence_max_artifact_bytes(self) -> int:
        return self.evidence_max_artifact_mb * 1024 * 1024

    @property
    def patch_max_diff_bytes(self) -> int:
        return self.patch_max_diff_kb * 1024

    @property
    def patch_diff_inline_bytes(self) -> int:
        return self.patch_diff_inline_kb * 1024

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
