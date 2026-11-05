"""Reproduction-spec tests (M6): pure, no database needed."""

import pytest

from app.config import get_settings
from app.envelope import ApiError
from app.services.repro_spec import validate_context


def settings():  # type: ignore[no-untyped-def]
    return get_settings()


def test_defaults_applied() -> None:
    assert validate_context({}, settings()) == {
        "route": "/",
        "browser": "chromium",
        "viewport": {"width": 1440, "height": 900},
        "steps": [],
    }


def test_all_actions_validate() -> None:
    context = validate_context(
        {
            "route": "/login?next=/",
            "viewport": {"width": 390, "height": 844},
            "steps": [
                {"action": "click", "selector": "button[type=submit]"},
                {"action": "fill", "selector": "#email", "text": "a@example.com"},
                {"action": "wait", "ms": 500},
                {"action": "assert_text", "selector": ".error", "text": "disabled"},
                {"action": "screenshot", "name": "after-submit"},
            ],
        },
        settings(),
    )
    assert [step["action"] for step in context["steps"]] == [
        "click",
        "fill",
        "wait",
        "assert_text",
        "screenshot",
    ]


def test_validation_is_idempotent() -> None:
    once = validate_context({"steps": [{"action": "wait", "ms": 100}]}, settings())
    assert validate_context(once, settings()) == once


@pytest.mark.parametrize(
    "context",
    [
        {"browser": "firefox"},
        {"browser": "chromium --headless=new --evil"},
        {"viewport": {"width": 1440, "height": 901}},
        {"viewport": {"width": True, "height": 900}},
        {"viewport": [1440, 900]},
        {"route": "login"},
        {"route": "https://evil.example/"},
        {"route": "/a b"},
        {"route": "/x" * 1000},
        {"steps": [{"action": "eval", "selector": "x"}]},
        {"steps": [{"action": "click"}]},
        {"steps": [{"action": "click", "selector": "ok", "run": "rm -rf /"}]},
        {"steps": [{"action": "fill", "selector": "x", "text": ""}]},
        {"steps": [{"action": "wait", "ms": 50}]},
        {"steps": [{"action": "wait", "ms": True}]},
        {"steps": [{"action": "screenshot", "name": "../../evil"}]},
        {"steps": [{"action": "click", "selector": "a\x00b"}]},
        {"steps": "not-a-list"},
        {"navigations": []},
        "not-an-object",
    ],
)
def test_invalid_contexts_rejected(context: object) -> None:
    with pytest.raises(ApiError) as exc:
        validate_context(context, settings())
    assert exc.value.code == "VALIDATION_ERROR"


def test_too_many_steps_rejected() -> None:
    cap = settings().repro_max_steps
    ok = {"steps": [{"action": "wait", "ms": 100}] * cap}
    assert len(validate_context(ok, settings())["steps"]) == cap
    with pytest.raises(ApiError):
        validate_context({"steps": [{"action": "wait", "ms": 100}] * (cap + 1)}, settings())
