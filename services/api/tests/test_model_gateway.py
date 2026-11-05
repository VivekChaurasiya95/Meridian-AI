"""Model gateway tests (M7): pure, no database needed."""

import json
import pathlib

import httpx
import pytest

from app.config import Settings
from app.envelope import ApiError
from app.services.model_gateway import (
    SCHEMA_REPORT,
    FakeModelProvider,
    HttpModelProvider,
    get_configured_provider,
    parse_hypotheses,
    parse_report,
)

FIXTURE = (
    pathlib.Path(__file__).resolve().parent / "fixtures" / "model" / "hypotheses_response.json"
)


def provider(handler, **overrides):  # type: ignore[no-untyped-def]
    return HttpModelProvider(
        api_base="https://model.invalid/v1",
        api_key="secret",
        model="test-reasoner",
        timeout_seconds=5,
        max_attempts=overrides.get("max_attempts", 3),
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda seconds: None)


def test_parse_valid_document() -> None:
    drafts = parse_hypotheses(
        {
            "hypotheses": [
                {
                    "title": "Race in submit handler",
                    "description": "Two competing state writes.",
                    "confidence": 0.75,
                    "evidence_refs": [
                        {"evidence_id": "a", "relationship": "supports", "note": "log line"}
                    ],
                },
                {"title": "No data", "description": "Empty state.", "confidence": None},
            ]
        }
    )
    assert len(drafts) == 2
    assert drafts[0].evidence_refs[0].relationship == "supports"
    assert drafts[1].confidence is None


@pytest.mark.parametrize(
    "document",
    [
        "not-an-object",
        {},
        {"hypotheses": []},
        {"hypotheses": [{"title": "x", "description": "y"}] * 11},
        {"hypotheses": [{"title": "", "description": "ok"}]},
        {"hypotheses": [{"title": "ok", "description": ""}]},
        {"hypotheses": [{"title": "ok", "description": "ok", "confidence": 2}]},
        {"hypotheses": [{"title": "ok", "description": "ok", "confidence": True}]},
        {
            "hypotheses": [
                {
                    "title": "ok",
                    "description": "ok",
                    "evidence_refs": [{"evidence_id": "", "relationship": "supports"}],
                }
            ]
        },
        {
            "hypotheses": [
                {
                    "title": "ok",
                    "description": "ok",
                    "evidence_refs": [{"evidence_id": "a", "relationship": "maybe"}],
                }
            ]
        },
    ],
)
def test_parse_rejects_invalid_documents(document: object) -> None:
    with pytest.raises(ApiError) as exc:
        parse_hypotheses(document)
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


def test_http_success_parses_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        body = json.loads(request.content.decode())
        assert body["model"] == "test-reasoner"
        assert body["temperature"] == 0
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"hypotheses": []}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            },
        )

    result = provider(handler).complete_json("sys", "user", "hypotheses_v1")
    assert result.document == {"hypotheses": []}
    assert (result.input_tokens, result.output_tokens, result.attempts) == (10, 4, 1)


def test_http_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    result = provider(handler).complete_json("sys", "user", "hypotheses_v1")
    assert result.attempts == 3


def test_http_client_fault_fails_fast() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(ApiError) as exc:
        provider(handler).complete_json("sys", "user", "hypotheses_v1")
    assert exc.value.code == "MODEL_PROVIDER_UNAVAILABLE"
    assert calls["n"] == 1


def test_http_exhaustion_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    with pytest.raises(ApiError) as exc:
        provider(handler, max_attempts=2).complete_json("sys", "user", "hypotheses_v1")
    assert exc.value.code == "MODEL_PROVIDER_UNAVAILABLE"


def test_http_non_json_output_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "nope"}}]})

    with pytest.raises(ApiError) as exc:
        provider(handler).complete_json("sys", "user", "hypotheses_v1")
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


def test_recorded_fixture_end_to_end() -> None:
    recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=recorded)

    result = provider(handler).complete_json("sys", "user", "hypotheses_v1")
    assert result.input_tokens == 812
    drafts = parse_hypotheses(result.document)
    assert drafts[0].title.startswith("Submit handler")
    assert drafts[0].evidence_refs[0].relationship == "supports"


def test_fake_provider_scripts_calls() -> None:
    fake = FakeModelProvider([{"hypotheses": []}, ApiError(503, "MODEL_PROVIDER_UNAVAILABLE", "x")])
    assert fake.complete_json("s", "u", "hypotheses_v1").document == {"hypotheses": []}
    with pytest.raises(ApiError):
        fake.complete_json("s", "u", "hypotheses_v1")
    assert len(fake.calls) == 2


def test_configured_provider_defaults_unconfigured() -> None:
    settings = Settings()
    assert settings.model_provider == "fake"
    resolved = get_configured_provider(settings)
    assert resolved.configured is False


def test_configured_provider_needs_complete_settings() -> None:
    settings = Settings(
        model_provider="openai-compatible",
        model_api_base="https://m.invalid/v1",
        model_api_key="k",
        model_name="m",
    )
    resolved = get_configured_provider(settings)
    assert resolved.configured is True
    assert isinstance(resolved.provider, HttpModelProvider)
    incomplete = Settings(model_provider="openai-compatible")
    assert get_configured_provider(incomplete).configured is False


def test_parse_report_valid_document() -> None:
    draft = parse_report(
        {
            "report": {
                "title": "Login bug fixed",
                "summary": "A stale flag broke login; the patch resets it.",
                "sections": [
                    {"heading": "Root cause", "body": "The flag never reset."},
                    {"heading": "Fix", "body": "Reset on submit."},
                ],
            }
        }
    )
    assert draft.title == "Login bug fixed"
    assert len(draft.sections) == 2
    assert draft.sections[0].heading == "Root cause"


@pytest.mark.parametrize(
    "document",
    [
        "not-an-object",
        {},
        {"report": None},
        {"report": {"title": "", "summary": "s", "sections": [{"heading": "h", "body": "b"}]}},
        {"report": {"title": "t", "summary": "", "sections": [{"heading": "h", "body": "b"}]}},
        {"report": {"title": "t", "summary": "s", "sections": []}},
        {
            "report": {
                "title": "t",
                "summary": "s",
                "sections": [{"heading": "h", "body": "b"}] * 9,
            }
        },
        {"report": {"title": "t", "summary": "s", "sections": [{"heading": "", "body": "b"}]}},
        {"report": {"title": "t", "summary": "s", "sections": [{"heading": "h", "body": ""}]}},
        {"report": {"title": "t", "summary": "s", "sections": ["nope"]}},
    ],
)
def test_parse_report_rejects_invalid_documents(document: object) -> None:
    with pytest.raises(ApiError) as exc:
        parse_report(document)
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


def test_http_meta_shaped_round_trip() -> None:
    """Meta Model API contract: chat completions + Bearer + usage (D69)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret"
        body = json.loads(request.content.decode())
        assert body["model"] == "muse-spark-1.3"
        assert body["response_format"] == {"type": "json_object"}
        assert [m["role"] for m in body["messages"]] == ["system", "user"]
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-meta-1",
                "object": "chat.completion",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                '{"report": {"title": "t", "summary": "s", '
                                '"sections": [{"heading": "h", "body": "b"}]}}'
                            ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 25, "completion_tokens": 19},
            },
        )

    provider = HttpModelProvider(
        api_base="https://api.meta.ai/v1",
        api_key="secret",
        model="muse-spark-1.3",
        timeout_seconds=5,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )
    result = provider.complete_json("sys", "user", SCHEMA_REPORT)
    assert (result.input_tokens, result.output_tokens) == (25, 19)
    assert parse_report(result.document).title == "t"
