"""Trusted browser-reproduction script (M6). Runs INSIDE the sandbox container.

The worker bakes this file plus a server-validated ``steps.json`` into
the per-execution image as reserved extras. It serves the snapshot on
container loopback, drives headless Chromium through the scripted
steps, and writes findings to ``/work/Meridian.rules/out`` (a
per-execution named volume) for bounded extraction. Nothing here is caller-controlled: argv, paths, ports, and
browser flags are all fixed constants.

Assertion convention (documented, user-visible): scripted assertions
describe the BUGGY behavior from the report. All assertions passing
means the bug reproduced (``reproduced: true``); any failing means it
did not (``false``); no assertions means there is nothing to judge by
(``null`` → inconclusive downstream).

Exit codes: 0 whenever ``result.json`` is written (even for
not-reproduced or broken-step outcomes — those are valid findings);
2 for infrastructure failures where no result could be produced.

Stdlib only at import time: Playwright imports lazily inside ``run``
so unit tests can exercise the pure helpers without browsers.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse

STEPS_PATH = "/work/Meridian.rules/steps.json"
APP_ROOT = "/work"
OUT_DIR = "/work/Meridian.rules/out"
APP_HOST = "127.0.0.1"
APP_PORT = 8077
SERVER_WAIT_SECONDS = 30
NAV_TIMEOUT_MS = 30_000
ACTION_TIMEOUT_MS = 10_000
TRACE_MAX_BYTES = 30 * 1024 * 1024
EVENT_CAP = 200
TEXT_EXCERPT = 2000
URL_MAX = 500

ACTIONS = ("click", "fill", "wait", "assert_text", "screenshot")
VIEWPORTS = frozenset({(1280, 720), (1440, 900), (1920, 1080), (390, 844)})

_CREDENTIAL_QUERY = re.compile(r"(?i)(secret|password|passwd|pwd|token|api[_-]?key|auth)")


def scrub_url(url: str) -> str:
    """Drop credential-word query values; truncate (pure)."""
    try:
        parts = urllib.parse.urlsplit(url[:URL_MAX])
    except ValueError:
        return "<unparseable-url>"
    if not parts.query:
        return url[:URL_MAX]
    kept: list[str] = []
    for field in parts.query.split("&"):
        name = field.split("=", 1)[0]
        if _CREDENTIAL_QUERY.search(name):
            kept.append(f"{name}=[REDACTED]")
        else:
            kept.append(field)
    return urllib.parse.urlunsplit(parts._replace(query="&".join(kept)))[:URL_MAX]


def load_steps(path: str = STEPS_PATH) -> dict:
    """Load and defensively re-validate the server-written steps file."""
    with open(path, encoding="utf-8") as handle:
        envelope = json.load(handle)
    if not isinstance(envelope, dict):
        raise ValueError("steps envelope must be an object")
    route = envelope.get("route", "/")
    if not isinstance(route, str) or not route.startswith("/") or "://" in route:
        raise ValueError("invalid route")
    viewport = envelope.get("viewport", {"width": 1440, "height": 900})
    pair = (viewport.get("width"), viewport.get("height"))
    if pair not in VIEWPORTS:
        raise ValueError("invalid viewport")
    steps = envelope.get("steps", [])
    if not isinstance(steps, list) or len(steps) > 100:
        raise ValueError("invalid steps")
    clean: list[dict] = []
    for step in steps:
        if not isinstance(step, dict) or step.get("action") not in ACTIONS:
            raise ValueError("invalid step")
        clean.append(
            {
                key: step[key]
                for key in ("action", "selector", "text", "ms", "name")
                if key in step
            }
        )
    return {
        "route": route,
        "viewport": {"width": pair[0], "height": pair[1]},
        "steps": clean,
    }


def wait_for_port(host: str, port: int, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def run() -> int:
    """Execute the reproduction. Returns the process exit code."""
    from playwright.sync_api import sync_playwright

    spec = load_steps()
    os.makedirs(OUT_DIR, exist_ok=True)
    # Fixed argv, no shell: the only server the sandbox ever starts.
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(APP_PORT), "--bind", APP_HOST],
        cwd=APP_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    result: dict = {
        "version": 1,
        "reproduced": None,
        "route": spec["route"],
        "viewport": spec["viewport"],
        "steps_total": len(spec["steps"]),
        "assertions": [],
        "failed_step": None,
        "console_errors": 0,
        "failed_requests": 0,
        "trace_omitted": False,
        "playwright_version": None,
        "error": None,
    }
    console_events: list[dict] = []
    network_events: list[dict] = []
    try:
        if not wait_for_port(APP_HOST, APP_PORT, SERVER_WAIT_SECONDS):
            result["error"] = "APP_START_TIMEOUT"
            return 2
        with sync_playwright() as playwright:
            try:
                from importlib import metadata as _metadata

                result["playwright_version"] = _metadata.version("playwright")
            except Exception:
                result["playwright_version"] = "unknown"
            browser = playwright.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                context = browser.new_context(
                    viewport=spec["viewport"],
                    accept_downloads=False,
                )
                context.tracing.start(screenshots=True, snapshots=True, sources=False)
                page = context.new_page()
                page.on(
                    "console",
                    lambda message: console_events.append(
                        {
                            "type": message.type,
                            "text": (message.text or "")[:TEXT_EXCERPT],
                        }
                    )
                    if message.type in ("error", "warning")
                    else None,
                )
                page.on(
                    "pageerror",
                    lambda error: console_events.append(
                        {"type": "pageerror", "text": str(error)[:TEXT_EXCERPT]}
                    ),
                )
                page.on(
                    "requestfailed",
                    lambda request: network_events.append(
                        {
                            "url": scrub_url(request.url),
                            "method": request.method,
                            "failure": (request.failure or "")[:500],
                        }
                    ),
                )

                def _on_response(response):  # type: ignore[no-untyped-def]
                    try:
                        status = response.status
                    except Exception:
                        return
                    if status >= 400:
                        network_events.append(
                            {"url": scrub_url(response.url), "status": status}
                        )

                page.on("response", _on_response)
                page.goto(
                    f"http://{APP_HOST}:{APP_PORT}{spec['route']}",
                    timeout=NAV_TIMEOUT_MS,
                    wait_until="load",
                )
                page.screenshot(path=os.path.join(OUT_DIR, "00-init.png"))
                for index, step in enumerate(spec["steps"]):
                    action = step["action"]
                    try:
                        if action == "click":
                            page.locator(step["selector"]).first.click(
                                timeout=ACTION_TIMEOUT_MS
                            )
                        elif action == "fill":
                            page.locator(step["selector"]).first.fill(
                                step["text"], timeout=ACTION_TIMEOUT_MS
                            )
                        elif action == "wait":
                            page.wait_for_timeout(step["ms"])
                        elif action == "assert_text":
                            actual = page.locator(step["selector"]).first.inner_text(
                                timeout=ACTION_TIMEOUT_MS
                            )
                            wanted = " ".join(str(step["text"]).split())
                            got = " ".join(actual.split())
                            passed = wanted in got
                            result["assertions"].append(
                                {
                                    "index": index,
                                    "selector": step["selector"],
                                    "expected": step["text"][:500],
                                    "passed": passed,
                                    "actual": got[:500],
                                }
                            )
                        elif action == "screenshot":
                            name = step.get("name") or "shot"
                            safe = "".join(
                                c for c in name if c.isalnum() or c in ("-", "_")
                            )[:40]
                            page.screenshot(
                                path=os.path.join(OUT_DIR, f"{index + 1:02d}-{safe}.png")
                            )
                    except Exception as exc:
                        result["failed_step"] = {
                            "index": index,
                            "action": action,
                            "error": f"{type(exc).__name__}: {exc}"[:500],
                        }
                        break
                if result["failed_step"] is None:
                    page.screenshot(path=os.path.join(OUT_DIR, "final.png"))
                trace_path = os.path.join(OUT_DIR, "trace.zip")
                try:
                    context.tracing.stop(path=trace_path)
                    if os.path.getsize(trace_path) > TRACE_MAX_BYTES:
                        os.remove(trace_path)
                        result["trace_omitted"] = True
                except Exception:
                    result["trace_omitted"] = True
                context.close()
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()

    assertions = result["assertions"]
    if result["failed_step"] is None and assertions:
        result["reproduced"] = all(item["passed"] for item in assertions)
    result["console_errors"] = sum(
        1 for event in console_events if event.get("type") in ("error", "pageerror")
    )
    result["failed_requests"] = sum(1 for event in network_events if "failure" in event)
    with open(os.path.join(OUT_DIR, "console.json"), "w", encoding="utf-8") as handle:
        json.dump(console_events[:EVENT_CAP], handle)
    with open(os.path.join(OUT_DIR, "network.json"), "w", encoding="utf-8") as handle:
        json.dump(network_events[:EVENT_CAP], handle)
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as handle:
        json.dump(result, handle)
    if result["error"] is not None:
        return 2
    return 0


def main() -> int:
    try:
        return run()
    except Exception as exc:
        try:
            os.makedirs(OUT_DIR, exist_ok=True)
            with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "error": f"{type(exc).__name__}: {exc}"[:500]}, handle)
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
