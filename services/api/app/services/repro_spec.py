"""Reproduction-spec validation (M6): pure, shared by API and worker.

The API validates the caller's ``reproduction_context`` before storing
it; the worker re-validates the stored row before executing anything,
so a tampered row or an old client can never smuggle instructions past
the allowlists. Steps are data for a fixed server-owned Playwright
script — never code, URLs, or shell.
"""

import re

from app.config import Settings, get_settings
from app.envelope import ApiError

BROWSERS = ("chromium",)
VIEWPORTS = frozenset({(1280, 720), (1440, 900), (1920, 1080), (390, 844)})
ACTIONS = ("click", "fill", "wait", "assert_text", "screenshot")
WAIT_MS_MIN = 100
WAIT_MS_MAX = 10_000
SCREENSHOT_NAME_PATTERN = r"^[A-Za-z0-9_-]{1,40}$"

_CONTEXT_KEYS = frozenset({"route", "browser", "viewport", "steps"})
_STEP_KEYS = frozenset({"action", "selector", "text", "ms", "name"})

DEFAULT_ROUTE = "/"
DEFAULT_VIEWPORT = {"width": 1440, "height": 900}


def _fail(message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message)


def _check_selector(selector: object, cap: int) -> str:
    if not isinstance(selector, str):
        raise _fail("Reproduction selectors must be strings.")
    if not 1 <= len(selector) <= cap:
        raise _fail("A reproduction selector is missing or too long.")
    if any(ord(char) < 32 or ord(char) == 127 for char in selector):
        raise _fail("A reproduction selector contains control characters.")
    return selector


def _check_text(text: object, cap: int, what: str) -> str:
    if not isinstance(text, str):
        raise _fail(f"Reproduction {what} must be a string.")
    if not 1 <= len(text) <= cap:
        raise _fail(f"Reproduction {what} is missing or too long.")
    return text


def validate_step(step: object, settings: Settings) -> dict:
    """Validate one normalized step (pure, unit-tested)."""
    if not isinstance(step, dict):
        raise _fail("Reproduction steps must be objects.")
    unknown = set(step) - _STEP_KEYS
    if unknown:
        raise _fail(f"Unknown reproduction step fields: {sorted(unknown)[0]}.")
    action = step.get("action")
    if action not in ACTIONS:
        raise _fail("A reproduction step has an unsupported action.")
    normalized: dict = {"action": action}
    if action in ("click", "fill", "assert_text"):
        normalized["selector"] = _check_selector(step.get("selector"), settings.repro_selector_max)
    if action in ("fill", "assert_text"):
        normalized["text"] = _check_text(step.get("text"), settings.repro_step_text_max, "text")
    if action == "wait":
        ms = step.get("ms")
        if not isinstance(ms, int) or isinstance(ms, bool):
            raise _fail("A wait step needs an integer ms value.")
        if not WAIT_MS_MIN <= ms <= WAIT_MS_MAX:
            raise _fail("A wait step is outside the allowed range.")
        normalized["ms"] = ms
    if action == "screenshot" and step.get("name") is not None:
        name = step.get("name")
        if not isinstance(name, str) or not re.fullmatch(SCREENSHOT_NAME_PATTERN, name):
            raise _fail("A screenshot name is invalid.")
        normalized["name"] = name
    return normalized


def validate_context(value: object, settings: Settings | None = None) -> dict:
    """Validate and normalize a reproduction context (pure, unit-tested)."""
    active = settings or get_settings()
    if not isinstance(value, dict):
        raise _fail("The reproduction context must be an object.")
    unknown = set(value) - _CONTEXT_KEYS
    if unknown:
        raise _fail(f"Unknown reproduction context fields: {sorted(unknown)[0]}.")
    route = value.get("route", DEFAULT_ROUTE)
    if not isinstance(route, str):
        raise _fail("The reproduction route must be a string.")
    if (
        not route.startswith("/")
        or len(route) > active.repro_route_max
        or "://" in route
        or any(char.isspace() or ord(char) < 32 for char in route)
    ):
        raise _fail("The reproduction route is invalid.")
    browser = value.get("browser", "chromium")
    if browser not in BROWSERS:
        raise _fail("The reproduction browser is not supported.")
    viewport = value.get("viewport", dict(DEFAULT_VIEWPORT))
    if not isinstance(viewport, dict):
        raise _fail("The reproduction viewport must be an object.")
    width, height = viewport.get("width"), viewport.get("height")
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or isinstance(width, bool)
        or isinstance(height, bool)
        or (width, height) not in VIEWPORTS
    ):
        raise _fail("The reproduction viewport is not supported.")
    steps = value.get("steps", [])
    if not isinstance(steps, list):
        raise _fail("Reproduction steps must be a list.")
    if len(steps) > active.repro_max_steps:
        raise _fail("Too many reproduction steps.")
    return {
        "route": route,
        "browser": browser,
        "viewport": {"width": width, "height": height},
        "steps": [validate_step(step, active) for step in steps],
    }
