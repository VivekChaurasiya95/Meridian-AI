"""Meridian-owned Semgrep ruleset loading (V1).

Rules ship inside the worker image and enter scanner containers as
trusted extra files — repository content can never add, remove, or
alter them. The ruleset version is recorded on every assessment.
"""

from __future__ import annotations

import os

RULESET_VERSION = "preflight-v1"

RULES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules")

RULE_FILENAMES = (
    "python-security.yml",
    "javascript-security.yml",
    "typescript-security.yml",
)


def load_rules() -> dict[str, bytes]:
    """Read the pinned ruleset files. Missing files are a loud error."""
    rules: dict[str, bytes] = {}
    for name in RULE_FILENAMES:
        path = os.path.join(RULES_DIR, name)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Preflight ruleset file is missing: {name}.")
        with open(path, "rb") as handle:
            rules[name] = handle.read()
    return rules
