"""Untrusted archive validation and safe extraction (M3, SECURITY.md §6.1).

Every uploaded repository archive is treated as hostile until inspected.
This module is pure (no database, no settings import): limits arrive as
arguments so the logic is unit-testable anywhere.

Policy summary (also recorded in ``docs/DECISIONS.md`` D37):
- Only ZIP archives (``.zip`` extension + ``PK`` magic) are accepted.
- Rejected before extraction: absolute paths, ``..`` traversal, drive
  letters, backslashes, null bytes, symlinks/hardlinks, device and
  socket entries, duplicate paths after normalization, empty archives.
- Enforced caps: compressed size, expanded size, file count, nesting
  depth, and compression ratio (ZIP-bomb defense).
- Extraction goes to a fresh caller-provided directory with restrictive
  permissions. Nothing is executed; no lifecycle hooks run.
- Generated/vendor directories and secret files are excluded from the
  indexed source tree (recorded in the manifest, never silently).
"""

import hashlib
import io
import os
import posixpath
import stat
import zipfile
from dataclasses import dataclass, field

# Directories never indexed: generated output, dependencies, VCS metadata.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".eggs",
        "node_modules",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "out",
        "coverage",
        ".coverage",
        "target",
        "vendor",
        ".idea",
        ".vscode",
    }
)

# Basenames (or suffixes) excluded from indexing: secrets and credentials.
# Their names are still listed for transparency; contents never are.
SECRET_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "credentials.json",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "id_rsa",
        "id_ed25519",
    }
)
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx")

ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

POLICY_VERSION = "m3.1"


class ArchiveRejected(Exception):
    """A rejected archive: ``code`` maps to the API error code."""

    def __init__(self, code: str, message: str, entry: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        # BaseException.message was removed in Python 3: keep our own copy.
        self.message = message
        # Entry names are caller-supplied data, safe to echo (truncated).
        self.entry = entry[:200] if entry else None


@dataclass
class ArchiveLimits:
    """Byte/file caps for one archive (from application settings)."""

    max_upload_bytes: int
    max_extracted_bytes: int
    max_files: int
    max_depth: int
    max_compression_ratio: int


@dataclass
class ValidatedEntry:
    """One archive member cleared for extraction."""

    path: str  # normalized relative posix path
    size: int  # declared uncompressed size
    sha256: str = ""  # filled during streaming extraction


@dataclass
class ValidationReport:
    entries: list[ValidatedEntry] = field(default_factory=list)
    total_uncompressed: int = 0
    archive_sha256: str = ""


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _is_unsafe_type(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode in (stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK)


def _normalize(name: str) -> str:
    """Normalize to a relative posix path; raise ArchiveRejected if unsafe."""
    if not name or "\x00" in name:
        raise ArchiveRejected(
            "ARCHIVE_UNSAFE_PATH", "The archive contains an invalid entry name.", name
        )
    if "\\" in name:
        raise ArchiveRejected(
            "ARCHIVE_UNSAFE_PATH",
            "The archive contains a Windows-style path, which is not supported.",
            name,
        )
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        raise ArchiveRejected(
            "ARCHIVE_ABSOLUTE_PATH", "The archive contains an absolute path.", name
        )
    normalized = posixpath.normpath(name)
    if normalized in ("", "."):
        raise ArchiveRejected(
            "ARCHIVE_UNSAFE_PATH", "The archive contains an invalid entry name.", name
        )
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ArchiveRejected(
            "ARCHIVE_TRAVERSAL", "The archive attempts path traversal outside its root.", name
        )
    if len(parts) > 64:
        # Hard structural ceiling; the configured depth cap applies below.
        raise ArchiveRejected("ARCHIVE_TOO_DEEP", "The archive nesting is too deep.", name)
    return normalized


def validate_archive(data: bytes, limits: ArchiveLimits) -> ValidationReport:
    """Validate raw archive bytes without extracting anything.

    Raises ArchiveRejected on any policy violation. Returns the cleared
    entry list plus archive digest for the happy path.
    """
    if len(data) > limits.max_upload_bytes:
        raise ArchiveRejected(
            "ARCHIVE_TOO_LARGE",
            f"The archive exceeds the {limits.max_upload_bytes // (1024 * 1024)} MB upload limit.",
        )
    if len(data) == 0 or data[:4] not in ZIP_MAGIC:
        raise ArchiveRejected(
            "ARCHIVE_NOT_ZIP", "The file is not a ZIP archive. Only .zip uploads are accepted."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise ArchiveRejected("ARCHIVE_NOT_ZIP", "The file is not a valid ZIP archive.") from exc

    seen: set[str] = set()
    entries: list[ValidatedEntry] = []
    total_uncompressed = 0
    for info in infos:
        if info.is_dir():
            continue
        path = _normalize(info.filename)
        if path in seen:
            raise ArchiveRejected(
                "ARCHIVE_DUPLICATE_PATH",
                "The archive contains conflicting duplicate paths.",
                path,
            )
        seen.add(path)
        if len(path.split("/")) > limits.max_depth:
            raise ArchiveRejected("ARCHIVE_TOO_DEEP", "The archive nesting is too deep.", path)
        if _is_symlink(info):
            raise ArchiveRejected(
                "ARCHIVE_SYMLINK", "The archive contains a symlink, which is not allowed.", path
            )
        if _is_unsafe_type(info):
            raise ArchiveRejected(
                "ARCHIVE_UNSUPPORTED_ENTRY",
                "The archive contains a device, socket, or FIFO entry.",
                path,
            )
        entries.append(ValidatedEntry(path=path, size=info.file_size))
        total_uncompressed += info.file_size

    if not entries:
        raise ArchiveRejected("ARCHIVE_EMPTY", "The archive contains no files.")
    if len(entries) > limits.max_files:
        raise ArchiveRejected(
            "ARCHIVE_TOO_MANY_FILES",
            f"The archive exceeds the {limits.max_files} file limit.",
        )
    if total_uncompressed > limits.max_extracted_bytes:
        raise ArchiveRejected(
            "ARCHIVE_EXPANDED_TOO_LARGE",
            "The archive would expand beyond the allowed size.",
        )
    ratio = total_uncompressed / max(len(data), 1)
    if ratio > limits.max_compression_ratio:
        raise ArchiveRejected(
            "ARCHIVE_COMPRESSION_BOMB",
            "The archive compression ratio looks like a ZIP bomb.",
        )
    return ValidationReport(
        entries=entries,
        total_uncompressed=total_uncompressed,
        archive_sha256=hashlib.sha256(data).hexdigest(),
    )


def is_secret_file(basename: str) -> bool:
    lowered = basename.lower()
    return lowered in SECRET_BASENAMES or lowered.endswith(SECRET_SUFFIXES)


def extract_archive(data: bytes, entries: list[ValidatedEntry], dest: str) -> list[ValidatedEntry]:
    """Stream validated entries to ``dest`` (an empty, private directory).

    Hashes while writing so no entry is ever fully buffered in memory.
    Declared sizes are re-verified against streamed bytes; a mismatch
    rejects the archive (lying headers). Returns entries with digests.
    """
    os.makedirs(dest, mode=0o700, exist_ok=True)
    done: list[ValidatedEntry] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in entries:
            try:
                source = archive.open(entry.path, "r")
            except KeyError as exc:
                # Normalized name has no exact member (e.g. "a//b.py"):
                # legal ZIP, unreadable entry — reject, never 500.
                raise ArchiveRejected(
                    "ARCHIVE_UNREADABLE_ENTRY",
                    "An archive entry cannot be read.",
                    entry.path,
                ) from exc
            target = os.path.join(dest, *entry.path.split("/"))
            parent = os.path.dirname(target)
            os.makedirs(parent, mode=0o700, exist_ok=True)
            digest = hashlib.sha256()
            written = 0
            with source, open(target, "wb") as out:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    out.write(chunk)
                    written += len(chunk)
            os.chmod(target, 0o600)
            if written != entry.size:
                raise ArchiveRejected(
                    "ARCHIVE_SIZE_MISMATCH",
                    "An archive entry disagrees with its declared size.",
                    entry.path,
                )
            done.append(ValidatedEntry(path=entry.path, size=written, sha256=digest.hexdigest()))
    return done


def compute_tree_digest(entries: list[ValidatedEntry]) -> str:
    """Deterministic SHA-256 over the sorted indexed file set."""
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda e: e.path):
        digest.update(f"{entry.path}\0{entry.size}\0{entry.sha256}\n".encode())
    return digest.hexdigest()
