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
        "lifecycle_test", "manifest_recheck", "sandbox_smoke", "git_preview", "git_import"
    ]
    payload: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.\-]+$"
    )
    priority: int = Field(default=0, ge=0, le=1000)
    max_attempts: int | None = Field(default=None, ge=1, le=25)
