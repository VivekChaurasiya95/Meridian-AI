"""Sandbox spec + policy unit tests (M5.2.2): pure, no Docker, no DB."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from sandbox import container_spec, execution_policy
from sandbox.exceptions import SandboxError

EXECUTION_ID = "a" * 32


def make_spec(**kwargs):  # type: ignore[no-untyped-def]
    policy = execution_policy.get_policy("sandbox_smoke")
    return container_spec.build_spec(policy, EXECUTION_ID, **kwargs)


def test_smoke_profile_resolves_exact_argv() -> None:
    policy = execution_policy.get_policy("sandbox_smoke")
    assert policy.image == "python:3.12-slim"
    assert execution_policy.resolve_command(policy) == (
        "python",
        "-c",
        "print('meridian-sandbox-ok')",
    )
    assert policy.timeout_seconds == 120
    assert policy.max_output_bytes == 1_048_576
    assert policy.env == {}


def test_unknown_profile_rejected() -> None:
    with pytest.raises(SandboxError) as exc_info:
        execution_policy.get_policy("npm_install")
    assert exc_info.value.code == "UNKNOWN_PROFILE"


def test_spec_runs_non_root() -> None:
    spec = make_spec()
    user = spec["user"]
    assert user != "root" and not str(user).startswith("0")


def test_spec_read_only_privilege_drop() -> None:
    spec = make_spec()
    assert spec["read_only"] is True
    assert spec["privileged"] is False
    assert "ALL" in spec["cap_drop"]
    assert "no-new-privileges:true" in spec["security_opt"]
    assert spec["stdin_open"] is False
    assert spec["tty"] is False


def test_spec_network_is_none() -> None:
    assert make_spec()["network_mode"] == "none"


def test_spec_uses_daemon_default_seccomp() -> None:
    """No custom or weakened seccomp: the daemon default applies.

    M5.3 evaluation: a custom profile path must live inside the Docker
    Desktop VM (unshippable from this repo), and the default already
    constrains our non-root, capability-free, network-less containers.
    If a custom profile ever ships, this test must be replaced by
    allowlist-compatibility tests, never deleted.
    """
    spec = make_spec()
    assert "unconfined" not in repr(spec["security_opt"])
    assert not any(str(opt).startswith("seccomp=") for opt in spec["security_opt"])
    assert "no-new-privileges:true" in spec["security_opt"]


def test_spec_has_no_mounts_ports_or_socket() -> None:
    spec = make_spec()
    for forbidden in ("volumes", "mounts", "ports", "devices", "device_requests"):
        assert forbidden not in spec
    blob = repr(sorted(spec.items()))
    assert "docker.sock" not in blob
    assert "/var/run" not in blob


def test_spec_exposes_no_host_environment() -> None:
    spec = make_spec()
    assert spec["environment"] == {}
    for secret_name in ("DATABASE_URL", "S3_SECRET", "SECRET_KEY", "FIREBASE"):
        assert secret_name not in repr(spec).upper()


def test_spec_tmpfs_never_shadows_workdir() -> None:
    spec = make_spec()
    assert "/tmp" in spec["tmpfs"]
    assert "size=" in spec["tmpfs"]["/tmp"]
    # /work comes from the source image layer: a tmpfs mount there would
    # hide the transferred files.
    assert spec["working_dir"] not in spec["tmpfs"]


def test_spec_image_override_selects_source_image() -> None:
    policy = execution_policy.get_policy("sandbox_smoke")
    default = container_spec.build_spec(policy, EXECUTION_ID)
    assert default["image"] == policy.image
    overridden = container_spec.build_spec(
        policy, EXECUTION_ID, image="meridian-sandbox-src-abc123"
    )
    assert overridden["image"] == "meridian-sandbox-src-abc123"
    assert overridden["command"] == default["command"]
    assert overridden["user"] == default["user"]


def test_spec_resource_limits_default() -> None:
    spec = make_spec()
    assert spec["nano_cpus"] == 500_000_000
    assert spec["mem_limit"] == "512m"
    assert spec["pids_limit"] == 128


def test_spec_labels_carry_execution_identity() -> None:
    spec = make_spec()
    assert spec["labels"]["meridian.managed"] == "true"
    assert spec["labels"]["meridian.execution_id"] == EXECUTION_ID
    assert spec["labels"]["meridian.profile"] == "sandbox_smoke"
    assert spec["name"].startswith("meridian-sandbox-")


def test_spec_volumes_opt_in_for_named_output_volumes() -> None:
    policy = execution_policy.get_policy("browser_repro")
    mapping = {"meridian-out-abc123": {"bind": "/work/Meridian.rules", "mode": "rw"}}
    spec = container_spec.build_spec(policy, EXECUTION_ID, volumes=mapping)
    assert spec["volumes"] == mapping


def test_spec_rejects_bind_mount_sources() -> None:
    policy = execution_policy.get_policy("browser_repro")
    for bad in ("/host/data", "C:\\data", "../escape", "name:withcolon", ""):
        with pytest.raises(SandboxError) as exc_info:
            container_spec.build_spec(
                policy, EXECUTION_ID, volumes={bad: {"bind": "/out", "mode": "rw"}}
            )
        assert exc_info.value.code == "INVALID_VOLUME"


def test_spec_rejects_bad_execution_id() -> None:
    policy = execution_policy.get_policy("sandbox_smoke")
    for bad in ("", "root", "A" * 32, "z" * 32, "../../etc"):
        with pytest.raises(SandboxError) as exc_info:
            container_spec.build_spec(policy, bad)
        assert exc_info.value.code == "INVALID_EXECUTION_ID"


def test_spec_rejects_bad_limits() -> None:
    policy = execution_policy.get_policy("sandbox_smoke")
    with pytest.raises(SandboxError):
        container_spec.build_spec(policy, EXECUTION_ID, nano_cpus=0)
    with pytest.raises(SandboxError):
        container_spec.build_spec(policy, EXECUTION_ID, pids_limit=-1)


def test_image_tag_must_be_pinned() -> None:
    policy = execution_policy.get_policy("sandbox_smoke")
    assert ":" in policy.image
    assert not policy.image.endswith(":latest")
