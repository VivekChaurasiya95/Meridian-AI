"""Unified-diff parsing and application (M8).

Parsing is pure and strict: only plain unified diffs with
``---``/``+++``/``@@`` structure are accepted — no git extensions, no
mode changes, no binaries, no renames. Application is fuzz-free and
confined to one staging directory; every target resolves inside it or
the whole application aborts before writing anything.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from app.envelope import ApiError
from app.services.patch_paths import check_repo_path

MAX_FILES = 20
MAX_HUNKS_PER_FILE = 100

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_GIT_HEADERS = (
    "diff --git",
    "index ",
    "new file mode",
    "deleted file mode",
    "old mode",
    "new mode",
    "similarity index",
    "rename from",
    "rename to",
    "Binary files ",
)


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class DiffFile:
    path: str
    change: str  # added | modified | deleted
    hunks: tuple[DiffHunk, ...] = ()
    additions: int = 0
    deletions: int = 0


def _strip_prefix(path: str) -> str:
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix) :]
    return path


def parse_unified_diff(text: str) -> list[DiffFile]:
    """Parse and validate a unified diff (pure, unit-tested)."""
    if not isinstance(text, str) or not text.strip():
        raise ApiError(422, "PATCH_DIFF_INVALID", "The diff is empty.")
    lines = text.splitlines()
    for line in lines:
        if line.startswith(_GIT_HEADERS):
            raise ApiError(422, "PATCH_DIFF_INVALID", "Extended diff headers are not supported.")
    files: list[DiffFile] = []
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        if not line.startswith("--- "):
            if line.strip() == "":
                index += 1
                continue
            raise ApiError(422, "PATCH_DIFF_INVALID", "The diff has an unexpected line.")
        old_name = line[4:].split("\t", 1)[0].strip()
        index += 1
        if index >= total or not lines[index].startswith("+++ "):
            raise ApiError(422, "PATCH_DIFF_INVALID", "The diff is missing a +++ header.")
        new_name = lines[index][4:].split("\t", 1)[0].strip()
        index += 1
        if old_name == "/dev/null" and new_name == "/dev/null":
            raise ApiError(422, "PATCH_DIFF_INVALID", "The diff touches /dev/null twice.")
        if old_name == "/dev/null":
            change = "added"
            raw_path = _strip_prefix(new_name)
        elif new_name == "/dev/null":
            change = "deleted"
            raw_path = _strip_prefix(old_name)
        else:
            change = "modified"
            old_path = _strip_prefix(old_name)
            new_path = _strip_prefix(new_name)
            if old_path != new_path:
                raise ApiError(422, "PATCH_DIFF_INVALID", "Renames are not supported.")
            raw_path = old_path
        try:
            path = check_repo_path(raw_path, "A diff path")
        except ApiError as exc:
            raise ApiError(422, "PATCH_DIFF_INVALID", exc.message) from exc
        hunks: list[DiffHunk] = []
        additions = 0
        deletions = 0
        while index < total and lines[index].startswith("@@"):
            match = _HUNK_RE.match(lines[index].split(" @@", 1)[0] + " @@")
            if match is None:
                raise ApiError(422, "PATCH_DIFF_INVALID", "A hunk header is invalid.")
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            index += 1
            hunk_lines: list[str] = []
            seen_old = 0
            seen_new = 0
            while index < total:
                body = lines[index]
                if body.startswith("@@") or body.startswith("--- "):
                    break
                if body.startswith("\\"):
                    index += 1
                    continue
                if not body or body[0] not in (" ", "+", "-"):
                    raise ApiError(422, "PATCH_DIFF_INVALID", "A hunk body line is invalid.")
                hunk_lines.append(body)
                if body.startswith(" "):
                    seen_old += 1
                    seen_new += 1
                elif body.startswith("-"):
                    seen_old += 1
                    deletions += 1
                else:
                    seen_new += 1
                    additions += 1
                index += 1
            if seen_old != old_count or seen_new != new_count:
                raise ApiError(422, "PATCH_DIFF_INVALID", "A hunk size disagrees with its header.")
            hunks.append(
                DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=tuple(hunk_lines),
                )
            )
            if len(hunks) > MAX_HUNKS_PER_FILE:
                raise ApiError(422, "PATCH_DIFF_INVALID", "A file has too many hunks.")
        if not hunks:
            raise ApiError(422, "PATCH_DIFF_INVALID", "A file entry has no hunks.")
        files.append(
            DiffFile(
                path=path,
                change=change,
                hunks=tuple(hunks),
                additions=additions,
                deletions=deletions,
            )
        )
        if len(files) > MAX_FILES:
            raise ApiError(422, "PATCH_DIFF_INVALID", "The diff touches too many files.")
    if not files:
        raise ApiError(422, "PATCH_DIFF_INVALID", "The diff has no files.")
    return files


def files_changed_summary(files: list[DiffFile]) -> list[dict]:
    return [
        {
            "path": item.path,
            "change": item.change,
            "additions": item.additions,
            "deletions": item.deletions,
        }
        for item in files
    ]


def apply_unified_diff(tree_dir: str, files: list[DiffFile]) -> list[str]:
    """Apply parsed files onto a staging tree (worker side, fuzz-free).

    Validates every target resolves inside ``tree_dir`` and every hunk
    applies cleanly BEFORE writing anything; on any conflict the tree
    is untouched and PATCH_APPLY_CONFLICT is raised.
    """
    root = os.path.realpath(tree_dir)
    planned: list[tuple[str, str | None]] = []
    for item in files:
        candidate = os.path.realpath(os.path.join(root, item.path))
        if candidate != root and not candidate.startswith(root + os.sep):
            raise ApiError(422, "PATCH_DIFF_INVALID", "A diff path escapes the tree.")
        if item.change == "added":
            if os.path.lexists(candidate):
                raise ApiError(409, "PATCH_APPLY_CONFLICT", f"Already exists: {item.path}.")
            planned.append((candidate, _apply_to_lines([], item, item.path)))
        elif item.change == "deleted":
            if not os.path.isfile(candidate) or os.path.islink(candidate):
                raise ApiError(409, "PATCH_APPLY_CONFLICT", f"Missing file: {item.path}.")
            planned.append((candidate, None))
        else:
            if not os.path.isfile(candidate) or os.path.islink(candidate):
                raise ApiError(409, "PATCH_APPLY_CONFLICT", f"Missing file: {item.path}.")
            with open(candidate, encoding="utf-8") as handle:
                original = handle.read().splitlines()
            planned.append((candidate, _apply_to_lines(original, item, item.path)))
    written: list[str] = []
    for candidate, content in planned:
        if content is None:
            os.remove(candidate)
        else:
            os.makedirs(os.path.dirname(candidate), exist_ok=True)
            with open(candidate, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        written.append(os.path.relpath(candidate, root))
    return written


def _apply_to_lines(original: list[str], item: DiffFile, path: str) -> str:
    """Apply hunks with zero fuzz; offsets must match exactly."""
    result: list[str] = []
    cursor = 0
    for hunk in item.hunks:
        start = hunk.old_start - 1 if hunk.old_count else hunk.old_start
        if start < cursor or start + hunk.old_count > len(original):
            raise ApiError(409, "PATCH_APPLY_CONFLICT", f"Hunk out of range: {path}.")
        result.extend(original[cursor:start])
        cursor = start
        for line in hunk.lines:
            marker, text = line[0], line[1:]
            if marker == " ":
                if cursor >= len(original) or original[cursor] != text:
                    raise ApiError(409, "PATCH_APPLY_CONFLICT", f"Context mismatch: {path}.")
                result.append(original[cursor])
                cursor += 1
            elif marker == "-":
                if cursor >= len(original) or original[cursor] != text:
                    raise ApiError(409, "PATCH_APPLY_CONFLICT", f"Removal mismatch: {path}.")
                cursor += 1
            else:
                result.append(text)
    result.extend(original[cursor:])
    return "\n".join(result) + ("\n" if result else "")
