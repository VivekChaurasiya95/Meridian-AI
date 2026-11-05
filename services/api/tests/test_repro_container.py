"""Container repro-script tests (M6): pure, no Playwright needed."""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from investigation import repro_container


def test_scrub_url() -> None:
    assert repro_container.scrub_url("http://x:8077/a?token=abc&n=1") == (
        "http://x:8077/a?token=[REDACTED]&n=1"
    )
    assert repro_container.scrub_url("http://x:8077/plain") == "http://x:8077/plain"
    assert len(repro_container.scrub_url("http://x/" + "a" * 1000)) <= 500


def test_load_steps_valid_and_defensive(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "steps.json"
    path.write_text(
        json.dumps(
            {
                "route": "/login",
                "viewport": {"width": 390, "height": 844},
                "steps": [{"action": "click", "selector": "button"}],
            }
        ),
        encoding="utf-8",
    )
    spec = repro_container.load_steps(str(path))
    assert spec["route"] == "/login"
    assert spec["steps"] == [{"action": "click", "selector": "button"}]

    path.write_text(json.dumps({"steps": [{"action": "eval"}]}), encoding="utf-8")
    try:
        repro_container.load_steps(str(path))
    except ValueError:
        pass
    else:
        raise AssertionError("eval step must be rejected")
