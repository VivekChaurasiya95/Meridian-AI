"""Scanner profile and build-context tests (V1, D63/D64).

Pure tests: profile pins, container-spec controls, trusted FROM
parameterization, and reserved rules-directory handling.
"""

import io
import pathlib
import sys
import tarfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from sandbox import container_spec, execution_policy, workspace
from sandbox.exceptions import SandboxError

EXECUTION_ID = "b" * 32


def test_unknown_profile_rejected() -> None:
    with pytest.raises(SandboxError) as exc:
        execution_policy.get_policy("nope")
    assert exc.value.code == "UNKNOWN_PROFILE"


def test_semgrep_profile_pinned() -> None:
    policy = execution_policy.get_policy("semgrep_preflight")
    assert policy.image == "semgrep/semgrep:1.183.0"
    assert policy.command[:3] == ("semgrep", "scan", "--config")
    assert "/work/Meridian.rules" in policy.command
    assert "--json" in policy.command
    assert policy.command[-1] == "/work"
    assert policy.env["HOME"] == "/tmp"


def test_gitleaks_profile_pinned() -> None:
    policy = execution_policy.get_policy("gitleaks_preflight")
    assert policy.image == "zricethezav/gitleaks:v8.30.1"
    assert policy.command[:3] == ("gitleaks", "dir", "/work")
    assert "--report-format" in policy.command
    assert policy.command[policy.command.index("--report-path") + 1] == "-"
    assert "--redact" in policy.command


def test_validate_image_ref() -> None:
    assert execution_policy.validate_image_ref("x/y:1.2") == "x/y:1.2"
    for bad in ("", "no-tag", "x/y:latest", None, 42):
        with pytest.raises(SandboxError):
            execution_policy.validate_image_ref(bad)  # type: ignore[arg-type]


def test_scanner_spec_keeps_baseline_controls() -> None:
    for profile in ("semgrep_preflight", "gitleaks_preflight"):
        policy = execution_policy.get_policy(profile)
        spec = container_spec.build_spec(policy, EXECUTION_ID, image="tag")
        assert spec["user"] == "65534:65534"
        assert spec["read_only"] is True
        assert spec["network_mode"] == "none"
        assert spec["privileged"] is False
        assert spec["cap_drop"] == ["ALL"]
        assert "volumes" not in spec and "ports" not in spec
        assert spec["labels"]["meridian.profile"] == profile
        assert spec["environment"]["HOME"] == "/tmp"


def _write(root: pathlib.Path, rel: str, content: str = "x") -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def test_pack_default_unchanged(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "a.py", "print(1)\n")
    context, _digest = workspace.pack_build_context(str(tmp_path))
    with tarfile.open(fileobj=io.BytesIO(context), mode="r") as tar:
        names = tar.getnames()
        dockerfile = tar.extractfile("Meridian.Dockerfile").read().decode()  # type: ignore[union-attr]
    assert "a.py" in names
    assert dockerfile == workspace.BUILD_DOCKERFILE
    assert dockerfile.startswith("FROM python:3.12-slim\n")


def test_pack_base_image_override(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "a.py")
    context, _ = workspace.pack_build_context(
        str(tmp_path), base_image="semgrep/semgrep:1.183.0"
    )
    with tarfile.open(fileobj=io.BytesIO(context), mode="r") as tar:
        dockerfile = tar.extractfile("Meridian.Dockerfile").read().decode()  # type: ignore[union-attr]
    assert dockerfile.startswith("FROM semgrep/semgrep:1.183.0\n")
    assert "RUN" not in dockerfile


def test_pack_base_image_validated(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "a.py")
    for bad in ("notag", "evil:latest"):
        with pytest.raises(SandboxError):
            workspace.pack_build_context(str(tmp_path), base_image=bad)
    for default in (None, ""):
        context, _ = workspace.pack_build_context(str(tmp_path), base_image=default)
        with tarfile.open(fileobj=io.BytesIO(context), mode="r") as tar:
            dockerfile = tar.extractfile("Meridian.Dockerfile").read().decode()  # type: ignore[union-attr]
        assert dockerfile.startswith("FROM python:3.12-slim\n")


def test_pack_extras_land_under_rules_root(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "a.py")
    context, first = workspace.pack_build_context(
        str(tmp_path),
        base_image="semgrep/semgrep:1.183.0",
        extra_root_files={"Meridian.rules/r.yml": b"rules:\n"},
    )
    _context2, second = workspace.pack_build_context(
        str(tmp_path),
        base_image="semgrep/semgrep:1.183.0",
        extra_root_files={"Meridian.rules/r.yml": b"rules:\n"},
    )
    assert first == second
    with tarfile.open(fileobj=io.BytesIO(context), mode="r") as tar:
        names = tar.getnames()
        body = tar.extractfile("Meridian.rules/r.yml").read()  # type: ignore[union-attr]
    assert "Meridian.rules" in names
    assert body == b"rules:\n"


def test_pack_extras_reject_escape_and_snapshot_collision(tmp_path: pathlib.Path) -> None:
    _write(tmp_path, "a.py")
    for bad in ("r.yml", "Meridian.rules/", "Meridian.rules/a/b.yml", "Meridian.rules/.."):
        with pytest.raises(SandboxError):
            workspace.pack_build_context(
                str(tmp_path), extra_root_files={bad: b"x"}
            )
    _write(tmp_path, "Meridian.rules/evil.yml", "x")
    with pytest.raises(SandboxError) as exc:
        workspace.pack_build_context(str(tmp_path))
    assert exc.value.code == "RESERVED_FILENAME"


def test_ruleset_loads_pinned_files() -> None:
    from security import rules

    loaded = rules.load_rules()
    assert set(loaded) == set(rules.RULE_FILENAMES)
    assert rules.RULESET_VERSION == "preflight-v1"
    for body in loaded.values():
        assert body.startswith(b"# Meridian preflight ruleset")
