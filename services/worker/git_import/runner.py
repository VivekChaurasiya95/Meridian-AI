"""Trusted-worker GitHub fetch (Git import slice 4).

Only this package invokes git. Hardened argv/env/config per
docs/GIT_IMPORT_DESIGN.md §8.2-§8.3: pinned IP, redirects off, no
credential helpers, no hooks/filters/submodules/LFS, fresh env.
"""

import os
import shutil
import subprocess


class GitFetchError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def git_binary() -> str:
    found = shutil.which("git")
    if not found:
        raise GitFetchError("GIT_UNAVAILABLE", "Git is not available on this worker.", False)
    return found


def build_env(home_dir: str, tmp_dir: str) -> dict[str, str]:
    env: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "PATHEXT", "COMSPEC"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    env["TEMP"] = tmp_dir
    env["TMP"] = tmp_dir
    env["HOME"] = home_dir
    env["XDG_CONFIG_HOME"] = home_dir
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    global_cfg = os.path.join(home_dir, "gitconfig")
    open(global_cfg, "w").close()
    env["GIT_CONFIG_GLOBAL"] = global_cfg
    env["GIT_CONFIG_SYSTEM"] = global_cfg
    env["GIT_ASKPASS"] = ""
    return env


def config_args(pinned_ip: str, hooks_dir: str, template_dir: str) -> list[str]:
    pairs = [
        ("credential.helper", ""),
        ("core.hooksPath", hooks_dir),
        ("init.templateDir", template_dir),
        ("protocol.allow", "never"),
        ("protocol.https.allow", "always"),
        ("protocol.file.allow", "never"),
        ("filter.lfs.clean", ""),
        ("filter.lfs.smudge", ""),
        ("filter.lfs.process", ""),
        ("filter.lfs.required", "false"),
        ("core.autocrlf", "false"),
        ("core.symlinks", "false"),
        ("http.followRedirects", "false"),
        ("http.curloptResolve", f"github.com:443:{pinned_ip}"),
        ("fetch.recurseSubmodules", "false"),
        ("submodule.recurse", "false"),
    ]
    args: list[str] = []
    for key, value in pairs:
        args += ["-c", f"{key}={value}"]
    return args


def _map_failure(stderr: str) -> GitFetchError:
    low = stderr.lower()
    if "redirect" in low:
        return GitFetchError(
            "GIT_REDIRECT_REFUSED",
            "The repository moved; renamed repositories are not followed.",
            False,
        )
    if "couldn't find remote ref" in low or "could not find remote branch" in low:
        return GitFetchError("GIT_BRANCH_NOT_FOUND", "The requested branch was not found.", False)
    if "couldn't find remote" in low or "not our ref" in low:
        return GitFetchError("GIT_COMMIT_NOT_FOUND", "The requested commit was not found.", False)
    if any(w in low for w in ("could not resolve", "connection", "timed out", "network")):
        return GitFetchError("GIT_FETCH_FAILED", "The repository could not be fetched.", True)
    return GitFetchError("GIT_FETCH_FAILED", "The repository could not be fetched.", False)


def run_git(argv: list[str], cwd: str, env: dict[str, str], timeout: int) -> str:
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            shell=False,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        raise GitFetchError(
            "GIT_UNAVAILABLE", "Git is not available on this worker.", False
        ) from None
    except subprocess.TimeoutExpired:
        raise GitFetchError(
            "GIT_FETCH_TIMEOUT", "Fetching the repository timed out.", True
        ) from None
    stderr = proc.stderr.decode("utf-8", errors="replace")[-4000:]
    if proc.returncode != 0:
        raise _map_failure(stderr)
    return proc.stdout.decode("utf-8", errors="replace")


def make_workspace(base: str) -> tuple[str, dict[str, str], str, str]:
    hooks = os.path.join(base, "hooks")
    templates = os.path.join(base, "templates")
    home = os.path.join(base, "home")
    for path in (hooks, templates, home):
        os.makedirs(path, exist_ok=True)
    return base, build_env(home, base), hooks, templates


def ls_remote(canonical_url: str, pinned_ip: str, base: str, timeout: int) -> dict:
    _b, env, hooks, templates = make_workspace(base)
    argv = [
        git_binary(),
        *config_args(pinned_ip, hooks, templates),
        "ls-remote",
        "--symref",
        canonical_url,
        "HEAD",
        "refs/heads/*",
    ]
    out = run_git(argv, base, env, timeout)
    default_branch: str | None = None
    branches: list[dict[str, str]] = []
    head_sha: str | None = None
    for line in out.splitlines():
        if line.startswith("ref: refs/heads/"):
            default_branch = line.split()[1].removeprefix("refs/heads/")
        elif "\trefs/heads/" in line:
            sha, ref = line.split("\t", 1)
            branches.append({"name": ref.removeprefix("refs/heads/"), "commit_sha": sha.lower()})
        elif line.endswith("\tHEAD"):
            head_sha = line.split("\t", 1)[0].lower()
    if default_branch is None and branches:
        for b in branches:
            if b["commit_sha"] == head_sha:
                default_branch = b["name"]
                break
    return {"default_branch": default_branch, "branches": branches}


def fetch_and_checkout(
    canonical_url: str,
    ref: str,
    pinned_ip: str,
    base: str,
    timeout: int,
    expected_sha: str | None,
) -> str:
    _b, env, hooks, templates = make_workspace(base)
    git = git_binary()
    cfg = config_args(pinned_ip, hooks, templates)
    repo_dir = os.path.join(base, "repo")
    os.makedirs(repo_dir, exist_ok=True)
    run_git([git, *cfg, "init", "--quiet", repo_dir], base, env, timeout)
    run_git(
        [git, *cfg, "-C", repo_dir, "remote", "add", "origin", canonical_url],
        base,
        env,
        timeout,
    )
    run_git(
        [
            git,
            *cfg,
            "-C",
            repo_dir,
            "fetch",
            "--depth",
            "1",
            "--no-tags",
            "--no-recurse-submodules",
            "origin",
            ref,
        ],
        base,
        env,
        timeout,
    )
    sha = (
        run_git([git, *cfg, "-C", repo_dir, "rev-parse", "FETCH_HEAD"], base, env, timeout)
        .strip()
        .lower()
    )
    if expected_sha and sha != expected_sha:
        raise GitFetchError("GIT_COMMIT_NOT_FOUND", "The requested commit was not found.", False)
    run_git(
        [git, *cfg, "-C", repo_dir, "checkout", "--quiet", "--detach", sha],
        base,
        env,
        timeout,
    )
    head = (
        run_git([git, *cfg, "-C", repo_dir, "rev-parse", "HEAD"], base, env, timeout)
        .strip()
        .lower()
    )
    if head != sha:
        raise GitFetchError("GIT_FETCH_FAILED", "The repository could not be fetched.", False)
    return sha
