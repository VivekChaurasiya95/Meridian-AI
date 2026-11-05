"""Model gateway (M7): one typed door to the reasoning provider.

The pipeline never touches HTTP or API keys directly: it calls a
:class:`ModelProvider` for validated JSON, and records usage on the
owning tool run. The HTTP provider speaks OpenAI-compatible chat
completions with bounded retries; tests inject fakes or recorded
fixtures instead. No autonomous actions exist behind this door —
every output is schema-validated data the worker decides how to use.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings, get_settings
from app.envelope import ApiError

logger = logging.getLogger("meridian.models")

SCHEMA_HYPOTHESES = "hypotheses_v1"
SCHEMA_REGRESSION_TESTS = "regression_tests_v1"
SCHEMA_PATCH = "patch_v1"
SCHEMA_REPORT = "report_v1"
MAX_HYPOTHESES = 10
MAX_EVIDENCE_REFS = 10
MAX_REGRESSION_TESTS = 5
MAX_REPORT_SECTIONS = 8

# Retryable HTTP outcomes: rate limits, overload, and server faults.
# Anything else 4xx fails fast so bad requests never spin.
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class ModelResult:
    """One validated model completion plus its accounting."""

    document: dict
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    attempts: int = 1


@dataclass(frozen=True)
class HypothesisRef:
    evidence_id: str
    relationship: str
    note: str | None = None


@dataclass(frozen=True)
class HypothesisDraft:
    title: str
    description: str
    confidence: float | None
    evidence_refs: tuple[HypothesisRef, ...] = ()


@dataclass(frozen=True)
class RegressionTestDraft:
    title: str
    description: str | None
    test_type: str
    file_path: str | None
    test_name: str | None
    steps: tuple[dict, ...]


@dataclass(frozen=True)
class PatchDraft:
    summary: str
    diff: str


@dataclass(frozen=True)
class ReportSection:
    heading: str
    body: str


@dataclass(frozen=True)
class ReportDraft:
    title: str
    summary: str
    sections: tuple[ReportSection, ...] = ()


def parse_hypotheses(document: object) -> list[HypothesisDraft]:
    """Strictly validate a hypotheses document (pure, unit-tested).

    Shape errors raise 422 MODEL_OUTPUT_INVALID. Callers decide
    whether a fresh sample is worth one more attempt.
    """
    if not isinstance(document, dict):
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model output must be an object.")
    items = document.get("hypotheses")
    if not isinstance(items, list) or not items:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model proposed no hypotheses.")
    if len(items) > MAX_HYPOTHESES:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model proposed too many hypotheses.")
    drafts: list[HypothesisDraft] = []
    for item in items:
        if not isinstance(item, dict):
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A hypothesis must be an object.")
        title = item.get("title")
        description = item.get("description")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A hypothesis title is invalid.")
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 2000:
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A hypothesis description is invalid.")
        confidence = item.get("confidence")
        if confidence is not None and (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= float(confidence) <= 1
        ):
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A hypothesis confidence is invalid.")
        refs: list[HypothesisRef] = []
        raw_refs = item.get("evidence_refs", [])
        if not isinstance(raw_refs, list) or len(raw_refs) > MAX_EVIDENCE_REFS:
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "Hypothesis evidence refs are invalid.")
        for ref in raw_refs:
            if not isinstance(ref, dict):
                raise ApiError(422, "MODEL_OUTPUT_INVALID", "An evidence ref must be an object.")
            evidence_id = ref.get("evidence_id")
            relationship = ref.get("relationship")
            note = ref.get("note")
            if not isinstance(evidence_id, str) or not evidence_id:
                raise ApiError(422, "MODEL_OUTPUT_INVALID", "An evidence ref id is invalid.")
            if relationship not in ("supports", "contradicts", "context"):
                raise ApiError(422, "MODEL_OUTPUT_INVALID", "An evidence ref kind is invalid.")
            if note is not None and (not isinstance(note, str) or len(note) > 500):
                raise ApiError(422, "MODEL_OUTPUT_INVALID", "An evidence ref note is invalid.")
            refs.append(
                HypothesisRef(evidence_id=evidence_id, relationship=relationship, note=note)
            )
        drafts.append(
            HypothesisDraft(
                title=title.strip(),
                description=description.strip(),
                confidence=None if confidence is None else float(confidence),
                evidence_refs=tuple(refs),
            )
        )
    return drafts


def parse_regression_tests(document: object, settings: Settings) -> list[RegressionTestDraft]:
    """Strictly validate a regression-tests document (pure, unit-tested).

    M8 executes e2e tests only: every test needs at least one assertion
    step in the reproduction DSL, and file paths stay repo-relative.
    """
    from app.services import patch_paths
    from app.services.repro_spec import validate_step

    if not isinstance(document, dict):
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model output must be an object.")
    items = document.get("tests")
    if not isinstance(items, list) or not items:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model proposed no tests.")
    if len(items) > MAX_REGRESSION_TESTS:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model proposed too many tests.")
    drafts: list[RegressionTestDraft] = []
    for item in items:
        if not isinstance(item, dict):
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A test must be an object.")
        title = item.get("title")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A test title is invalid.")
        description = item.get("description")
        if description is not None and (
            not isinstance(description, str) or len(description) > 2000
        ):
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A test description is invalid.")
        if item.get("test_type", "e2e") != "e2e":
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "Only e2e tests are supported.")
        file_path = item.get("file_path")
        if file_path is not None:
            patch_paths.check_repo_path(file_path, "A test file path")
        test_name = item.get("test_name")
        if test_name is not None and (
            not isinstance(test_name, str) or not 1 <= len(test_name) <= 300
        ):
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A test name is invalid.")
        raw_steps = item.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A test needs steps.")
        steps = tuple(validate_step(step, settings) for step in raw_steps)
        if not any(step["action"] == "assert_text" for step in steps):
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A test needs an assertion.")
        drafts.append(
            RegressionTestDraft(
                title=title.strip(),
                description=description.strip() if description else None,
                test_type="e2e",
                file_path=file_path,
                test_name=test_name,
                steps=steps,
            )
        )
    return drafts


def parse_patch_proposal(document: object, max_diff_bytes: int) -> PatchDraft:
    """Strictly validate a patch document (pure, unit-tested).

    Shape only — diff safety (paths, hunks) is enforced separately by
    the patch parser before anything is stored or applied.
    """
    if not isinstance(document, dict):
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model output must be an object.")
    summary = document.get("summary")
    if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 2000:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The patch summary is invalid.")
    diff = document.get("diff")
    if not isinstance(diff, str) or not diff.strip():
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The patch diff is missing.")
    if len(diff.encode("utf-8")) > max_diff_bytes:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The patch diff is too large.")
    return PatchDraft(summary=summary.strip(), diff=diff)


def parse_report(document: object) -> ReportDraft:
    """Strictly validate an investigation-report document (pure, unit-tested).

    Shape: ``{"report": {"title", "summary", "sections": [...]}}``.
    Sections carry prose only — evidence linkage already lives on
    hypotheses, so the report cannot invent citations.
    """
    if not isinstance(document, dict):
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model output must be an object.")
    report = document.get("report")
    if not isinstance(report, dict):
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model report is missing.")
    title = report.get("title")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The report title is invalid.")
    summary = report.get("summary")
    if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 2000:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The report summary is invalid.")
    raw_sections = report.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The report needs sections.")
    if len(raw_sections) > MAX_REPORT_SECTIONS:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The report has too many sections.")
    sections: list[ReportSection] = []
    for item in raw_sections:
        if not isinstance(item, dict):
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A report section must be an object.")
        heading = item.get("heading")
        body = item.get("body")
        if not isinstance(heading, str) or not 1 <= len(heading.strip()) <= 120:
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A report heading is invalid.")
        if not isinstance(body, str) or not 1 <= len(body.strip()) <= 4000:
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A report body is invalid.")
        sections.append(ReportSection(heading=heading.strip(), body=body.strip()))
    return ReportDraft(title=title.strip(), summary=summary.strip(), sections=tuple(sections))


class ModelProvider(Protocol):
    """Something that returns validated JSON for a named schema."""

    @property
    def model_label(self) -> str: ...
    def complete_json(self, system: str, user: str, schema_name: str) -> ModelResult: ...


class FakeModelProvider:
    """Scripted double for tests: pops one document per call.

    Script entries may be dicts, exceptions, or zero-argument callables
    returning dicts (for documents that need runtime ids).
    """

    def __init__(
        self, script: list[dict | Exception | Callable[[], dict]], model: str = "fake-test"
    ) -> None:
        self._script = list(script)
        self._model = model
        self.calls: list[dict] = []

    @property
    def model_label(self) -> str:
        return self._model

    def complete_json(self, system: str, user: str, schema_name: str) -> ModelResult:
        self.calls.append({"system": system, "user": user, "schema": schema_name})
        if not self._script:
            raise AssertionError("FakeModelProvider script exhausted.")
        next_item = self._script.pop(0)
        if callable(next_item):
            next_item = next_item()
        if isinstance(next_item, Exception):
            raise next_item
        assert isinstance(next_item, dict)
        return ModelResult(document=next_item, model=self._model)


class HttpModelProvider:
    """OpenAI-compatible chat completions with bounded retries."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        max_attempts: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._transport = transport

    @property
    def model_label(self) -> str:
        return self._model

    def complete_json(self, system: str, user: str, schema_name: str) -> ModelResult:
        started = time.monotonic()
        last_error = "unknown error"
        with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    response = client.post(
                        f"{self._api_base}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json={
                            "model": self._model,
                            "temperature": 0,
                            "response_format": {"type": "json_object"},
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                        },
                    )
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = f"{type(exc).__name__}"
                    logger.warning("model attempt failed attempt=%d error=%s", attempt, last_error)
                    self._sleep(attempt)
                    continue
                if response.status_code in RETRYABLE_STATUS:
                    last_error = f"HTTP {response.status_code}"
                    logger.warning("model attempt failed attempt=%d error=%s", attempt, last_error)
                    self._sleep(attempt)
                    continue
                if response.status_code != 200:
                    # Auth, quota-shape, and client faults fail fast with a
                    # generic code: key validity must not leak through errors.
                    logger.warning("model rejected status=%d", response.status_code)
                    raise ApiError(
                        503, "MODEL_PROVIDER_UNAVAILABLE", "The model provider is unavailable."
                    )
                try:
                    payload = response.json()
                    content = payload["choices"][0]["message"]["content"]
                    document = json.loads(content)
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise ApiError(
                        422, "MODEL_OUTPUT_INVALID", "The model output was not valid JSON."
                    ) from exc
                if not isinstance(document, dict):
                    raise ApiError(
                        422, "MODEL_OUTPUT_INVALID", "The model output must be an object."
                    )
                usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
                return ModelResult(
                    document=document,
                    model=self._model,
                    input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                    output_tokens=int(usage.get("completion_tokens", 0) or 0),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    attempts=attempt,
                )
        raise ApiError(
            503, "MODEL_PROVIDER_UNAVAILABLE", f"The model provider is unavailable ({last_error})."
        )

    def _sleep(self, attempt: int) -> None:
        time.sleep(min(2.0**attempt, 10.0))


@dataclass
class ProviderConfig:
    configured: bool
    provider: ModelProvider | None = None
    reason: str = ""


def get_configured_provider(settings: Settings | None = None) -> ProviderConfig:
    """Resolve the operator-configured provider, or report why none is.

    ``fake`` (the default) is UNCONFIGURED by definition: reasoning
    stages block honestly instead of emitting canned output.
    """
    active = settings or get_settings()
    if active.model_provider == "fake":
        return ProviderConfig(configured=False, reason="model provider is not configured")
    if not active.model_api_base or not active.model_api_key or not active.model_name:
        return ProviderConfig(configured=False, reason="model provider settings are incomplete")
    return ProviderConfig(
        configured=True,
        provider=HttpModelProvider(
            api_base=active.model_api_base,
            api_key=active.model_api_key,
            model=active.model_name,
            timeout_seconds=active.model_timeout_seconds,
            max_attempts=active.model_max_attempts,
        ),
    )
