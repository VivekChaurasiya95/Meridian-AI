"""Pydantic request/response schemas for the M1 API surface.

Unknown fields are rejected at the boundary (``extra="forbid"``) so clients
cannot silently set server-owned attributes.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AuthModel(BaseModel):
    # Like StrictModel but WITHOUT whitespace stripping: passwords must be
    # hashed exactly as typed. Email is normalized in the service layer.
    model_config = ConfigDict(extra="forbid")


class WorkspaceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=SLUG_PATTERN)


class WorkspaceUpdate(StrictModel):
    # Allowlist: name only (API.md §6.3). Slug changes are treated carefully
    # and are not offered in M1.
    name: str = Field(min_length=1, max_length=200)


class SignupRequest(AuthModel):
    email: EmailStr
    # Any non-empty password is accepted (same floor as login); no strength
    # policy is enforced server-side.
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(AuthModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class FirebaseLoginRequest(AuthModel):
    # Firebase ID token (RS256 JWT) from a Google/GitHub popup sign-in.
    id_token: str = Field(min_length=1, max_length=8192)


class UserUpdate(StrictModel):
    # Allowlist: display_name only (API.md §6.2).
    display_name: str = Field(min_length=1, max_length=100)


AssignableRole = Literal["admin", "developer", "viewer"]


class MemberCreate(StrictModel):
    email: EmailStr
    role: AssignableRole


class MemberUpdate(StrictModel):
    role: AssignableRole


class ProjectCreate(StrictModel):
    # M3 accepts uploaded archives only; git_provider arrives with the
    # (unbuilt) provider integration. The runtime profile is server-derived
    # from inspection — clients cannot set execution configuration.
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(StrictModel):
    # Allowlist: name and description only. Source, slug, status, and
    # runtime profile change through their own guarded operations.
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class GitValidateRequest(StrictModel):
    repository_url: str = Field(min_length=1, max_length=2048)


class GitImportCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=2000)
    repository_url: str = Field(min_length=1, max_length=2048)
    branch: str | None = Field(default=None, max_length=256)
    commit_sha: str | None = Field(default=None, max_length=40)
    idempotency_key: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.\-]+$"
    )


class JobSubmit(StrictModel):
    # Payload stays a caller-supplied object; the worker validates the
    # fields its own job type needs. Result/worker internals are never
    # accepted here.
    job_type: Literal[
        "lifecycle_test",
        "manifest_recheck",
        "sandbox_smoke",
        "git_preview",
        "git_import",
        "security_preflight",
        "investigation",
    ]
    payload: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.\-]+$"
    )
    priority: int = Field(default=0, ge=0, le=1000)
    max_attempts: int | None = Field(default=None, ge=1, le=25)


Severity = Literal["low", "medium", "high", "critical", "unspecified"]


class InvestigationCreate(StrictModel):
    # reproduction_context stays a caller-supplied object: the pure
    # repro_spec validator (shared with the worker) checks route,
    # browser, viewport, and steps against operator caps.
    title: str = Field(min_length=1, max_length=200)
    bug_report: str = Field(min_length=1, max_length=20000)
    severity: Severity = "unspecified"
    repository_snapshot_id: str = Field(min_length=1, max_length=64)
    attachments: list[dict] = Field(default_factory=list)
    reproduction_context: dict = Field(default_factory=dict)


class InvestigationRetry(StrictModel):
    from_stage: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class RegressionTestCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    test_type: Literal["unit", "integration", "e2e", "regression", "manual"] = "e2e"
    file_path: str | None = Field(default=None, max_length=500)
    test_name: str | None = Field(default=None, min_length=1, max_length=300)


class HypothesisReviewUpdate(StrictModel):
    # A user verdict on one hypothesis. Appended to the review history;
    # the newest review is the effective one (M7-FINISH).
    verdict: Literal["useful", "rejected", "needs_evidence"]
    note: str | None = Field(default=None, max_length=500)


class PatchApprove(StrictModel):
    diff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_snapshot_id: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class PatchReject(StrictModel):
    reason: str = Field(min_length=1, max_length=500)


class ReportCreate(StrictModel):
    # The only user input is the output format. Content always covers
    # the full persisted investigation state (summary, snapshot,
    # evidence, hypotheses, patches, verification) — no subset, no
    # model-written IDs, so generation is deterministic per state (M10).
    format: Literal["md", "html"]


class VerificationRunCreate(StrictModel):
    # Optional subset of regression-test ids to execute. Omitted or empty
    # means every runnable test of the investigation. Items are validated
    # as investigation-owned runnable tests in the service layer. Status
    # is never accepted here: user-created runs always start queued and
    # only the worker moves them (M9).
    selected_check_keys: list[str] | None = Field(default=None, max_length=100)
