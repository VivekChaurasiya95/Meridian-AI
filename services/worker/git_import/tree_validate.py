"""Post-checkout tree validation for Git imports (design §8.4).

Recursive lstat walk: rejects links/special files, submodules, LFS
pointers, Windows-unsafe names; mirrors ZIP skip/secret policy.
"""

import hashlib
import os
import stat
from dataclasses import dataclass, field

from app.services.archive_security import SKIP_DIRS, ValidatedEntry, is_secret_file
from app.services.git_url_policy import GitUrlError

LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"
RESERVED = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


@dataclass
class TreeLimits:
    max_files: int
    max_bytes: int
    max_file_bytes: int
    max_depth: int


@dataclass
class TreeResult:
    indexed: list[ValidatedEntry] = field(default_factory=list)
    skipped_dirs: dict[str, int] = field(default_factory=dict)
    secrets_excluded: int = 0


def _unsafe_component(name: str) -> bool:
    if "\\" in name or ":" in name or "\x00" in name:
        return True
    if name.endswith((".", " ")):
        return True
    stem = name.split(".", 1)[0].upper()
    return stem in RESERVED


def validate_tree(root: str, limits: TreeLimits) -> TreeResult:
    result = TreeResult()
    seen_folded: set[str] = set()
    total = 0

    def fail(code: str, msg: str) -> GitUrlError:
        return GitUrlError(code, msg)

    def count_files(path: str) -> int:
        count = 0
        for _cur, _dirs, files in os.walk(path, followlinks=False):
            count += len(files)
        return count

    def walk(current: str, rel_parts: list[str]) -> None:
        nonlocal total
        with os.scandir(current) as it:
            entries = sorted(it, key=lambda e: e.name)
        for entry in entries:
            name = entry.name
            parts = [*rel_parts, name]
            rel = "/".join(parts)
            info = entry.stat(follow_symlinks=False)
            mode = info.st_mode
            is_link = stat.S_ISLNK(mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)
            if is_link:
                raise fail(
                    "GIT_SYMLINK_NOT_ALLOWED",
                    "The repository contains a symbolic link.",
                )
            if entry.is_dir(follow_symlinks=False):
                if name == ".gitmodules":
                    raise fail("GIT_SUBMODULES_NOT_SUPPORTED", "Submodules are not supported.")
                if name in SKIP_DIRS:
                    result.skipped_dirs[name] = result.skipped_dirs.get(name, 0) + count_files(
                        entry.path
                    )
                    continue
                if _unsafe_component(name):
                    raise fail("GIT_PATH_UNSAFE", "The repository contains an unsafe path.")
                if len(parts) > limits.max_depth:
                    raise fail("GIT_PATH_TOO_DEEP", "The repository nesting is too deep.")
                walk(entry.path, parts)
                continue
            if not entry.is_file(follow_symlinks=False):
                raise fail("GIT_UNSUPPORTED_ENTRY", "The repository contains a special file.")
            if name == ".gitmodules":
                raise fail("GIT_SUBMODULES_NOT_SUPPORTED", "Submodules are not supported.")
            if _unsafe_component(name):
                raise fail("GIT_PATH_UNSAFE", "The repository contains an unsafe path.")
            if len(parts) > limits.max_depth:
                raise fail("GIT_PATH_TOO_DEEP", "The repository nesting is too deep.")
            skipped = next((p for p in parts[:-1] if p in SKIP_DIRS), None)
            if skipped is not None:
                result.skipped_dirs[skipped] = result.skipped_dirs.get(skipped, 0) + 1
                continue
            if is_secret_file(name):
                result.secrets_excluded += 1
                continue
            folded = rel.casefold()
            if folded in seen_folded:
                raise fail(
                    "GIT_DUPLICATE_PATH",
                    "The repository contains conflicting duplicate paths.",
                )
            seen_folded.add(folded)
            size = info.st_size
            if size > limits.max_file_bytes:
                raise fail("GIT_FILE_TOO_LARGE", "A repository file exceeds the size limit.")
            total += size
            if total > limits.max_bytes:
                raise fail("GIT_REPO_TOO_LARGE", "The repository exceeds the size limit.")
            if len(result.indexed) + 1 > limits.max_files:
                raise fail("GIT_TOO_MANY_FILES", "The repository exceeds the file limit.")
            digest = hashlib.sha256()
            with open(entry.path, "rb") as handle:
                first = handle.read(1024)
                if first.startswith(LFS_HEADER):
                    raise fail("GIT_LFS_NOT_SUPPORTED", "Git LFS files are not supported.")
                digest.update(first)
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            result.indexed.append(ValidatedEntry(path=rel, size=size, sha256=digest.hexdigest()))

    walk(root, [])
    if not result.indexed:
        raise fail("GIT_REPO_EMPTY", "The repository contains no indexable files.")
    return result
