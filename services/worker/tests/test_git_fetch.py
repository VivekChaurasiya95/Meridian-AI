"""Worker git fetch/tree tests: no network, no real GitHub."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from git_import import runner
from git_import.tree_validate import TreeLimits, validate_tree

from app.services.git_url_policy import GitUrlError

LIMITS = TreeLimits(max_files=100, max_bytes=10_000_000, max_file_bytes=1_000_000, max_depth=20)


def write(root: str, rel: str, data: bytes) -> None:
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def test_config_is_hardened() -> None:
    args = " ".join(runner.config_args("140.82.121.3", "/h", "/t"))
    for needle in (
        "credential.helper=",
        "core.hooksPath=/h",
        "protocol.allow=never",
        "protocol.https.allow=always",
        "protocol.file.allow=never",
        "http.followRedirects=false",
        "http.curloptResolve=github.com:443:140.82.121.3",
        "filter.lfs.required=false",
        "core.symlinks=false",
    ):
        assert needle in args
    assert "sslVerify=false" not in args


def test_env_excludes_secrets(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://secret")
    monkeypatch.setenv("S3_SECRET_KEY", "secret")
    env = runner.build_env(str(tmp_path), str(tmp_path))
    assert "DATABASE_URL" not in env and "S3_SECRET_KEY" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"


def test_tree_indexes_and_excludes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    root = str(tmp_path)
    write(root, "src/app.py", b"print(1)\n")
    write(root, ".env", b"SECRET=1\n")
    write(root, "node_modules/pkg/index.js", b"x")
    write(root, "README.md", b"# hi\n")
    result = validate_tree(root, LIMITS)
    paths = [e.path for e in result.indexed]
    assert paths == ["README.md", "src/app.py"]
    assert result.secrets_excluded == 1
    assert result.skipped_dirs.get("node_modules") == 1


def test_tree_rejects_submodule_lfs_and_large(tmp_path) -> None:  # type: ignore[no-untyped-def]
    write(str(tmp_path), ".gitmodules", b"[submodule]\n")
    with pytest.raises(GitUrlError) as exc:
        validate_tree(str(tmp_path), LIMITS)
    assert exc.value.code == "GIT_SUBMODULES_NOT_SUPPORTED"
    os.remove(os.path.join(str(tmp_path), ".gitmodules"))
    write(
        str(tmp_path),
        "big.bin",
        b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\n",
    )
    with pytest.raises(GitUrlError) as exc2:
        validate_tree(str(tmp_path), LIMITS)
    assert exc2.value.code == "GIT_LFS_NOT_SUPPORTED"


def test_tree_limits(tmp_path) -> None:  # type: ignore[no-untyped-def]
    write(str(tmp_path), "a.txt", b"12345")
    with pytest.raises(GitUrlError) as exc:
        validate_tree(str(tmp_path), TreeLimits(100, 100, 4, 20))
    assert exc.value.code == "GIT_FILE_TOO_LARGE"


def test_ls_remote_parsing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    sha_main = "a" * 40
    sha_dev = "b" * 40
    monkeypatch.setattr(
        runner,
        "run_git",
        lambda argv, cwd, env, timeout: (
            f"ref: refs/heads/main HEAD\n{sha_main}\tHEAD\n"
            f"{sha_main}\trefs/heads/main\n{sha_dev}\trefs/heads/dev\n"
        ),
    )
    monkeypatch.setattr(runner, "git_binary", lambda: "git")
    result = runner.ls_remote("https://github.com/o/r", "140.82.121.3", str(tmp_path), 10)
    assert result["default_branch"] == "main"
    assert {b["name"] for b in result["branches"]} == {"main", "dev"}


def test_redirect_failure_maps() -> None:
    err = runner._map_failure("fatal: unable to follow redirect")
    assert err.code == "GIT_REDIRECT_REFUSED"
    assert (
        runner._map_failure("couldn't find remote ref refs/heads/nope").code
        == "GIT_BRANCH_NOT_FOUND"
    )
