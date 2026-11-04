"""Pure unit tests for untrusted-archive validation (no DB, no sockets).

These run everywhere, including locked-down sandboxes (D16 pure tier).
"""

import io
import os
import stat
import zipfile

import pytest

from app.services.archive_security import (
    ArchiveLimits,
    ArchiveRejected,
    _normalize,
    compute_tree_digest,
    extract_archive,
    validate_archive,
)

LIMITS = ArchiveLimits(
    max_upload_bytes=25 * 1024 * 1024,
    max_extracted_bytes=200 * 1024 * 1024,
    max_files=5000,
    max_depth=20,
    max_compression_ratio=100,
)


def make_zip(entries: dict[str, bytes | str], **kwargs) -> bytes:  # type: ignore[no-untyped-def]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            data = content.encode() if isinstance(content, str) else content
            archive.writestr(name, data, **kwargs)
    return buffer.getvalue()


def test_valid_zip_passes() -> None:
    data = make_zip({"app/main.py": "print('hi')\n", "README.md": "# demo\n"})
    report = validate_archive(data, LIMITS)
    assert len(report.entries) == 2
    assert report.total_uncompressed > 0
    assert len(report.archive_sha256) == 64


def test_non_zip_rejected() -> None:
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(b"definitely not a zip file at all....", LIMITS)
    assert exc_info.value.code == "ARCHIVE_NOT_ZIP"


def test_empty_bytes_rejected() -> None:
    with pytest.raises(ArchiveRejected):
        validate_archive(b"", LIMITS)


def test_empty_archive_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("emptydir/", "")
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(buffer.getvalue(), LIMITS)
    assert exc_info.value.code == "ARCHIVE_EMPTY"


def test_path_traversal_rejected() -> None:
    data = make_zip({"../../evil.py": "x = 1\n"})
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(data, LIMITS)
    assert exc_info.value.code == "ARCHIVE_TRAVERSAL"


def test_absolute_path_rejected() -> None:
    data = make_zip({"/etc/evil.py": "x = 1\n"})
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(data, LIMITS)
    assert exc_info.value.code == "ARCHIVE_ABSOLUTE_PATH"


def test_backslash_path_rejected() -> None:
    # Windows' stdlib converts "\\" to "/" on both the write AND read
    # paths, so no byte sequence can surface a backslash member through
    # ZipFile on this platform (verified: even patched raw bytes read
    # back clean). Exercise the normalization guard directly instead:
    # hostile zips built elsewhere still hit it on every platform.
    with pytest.raises(ArchiveRejected) as exc_info:
        _normalize("src\\evil.py")
    assert exc_info.value.code == "ARCHIVE_UNSAFE_PATH"


def test_symlink_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("link.py")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target.py")
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(buffer.getvalue(), LIMITS)
    assert exc_info.value.code == "ARCHIVE_SYMLINK"


def test_duplicate_paths_rejected() -> None:
    data = make_zip({"a/./b.py": "x = 1\n", "a/b.py": "x = 2\n"})
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(data, LIMITS)
    assert exc_info.value.code == "ARCHIVE_DUPLICATE_PATH"


def test_too_many_files_rejected() -> None:
    tight = ArchiveLimits(10**9, 10**12, 3, 20, 10**6)
    data = make_zip({f"f{i}.py": "x\n" for i in range(5)})
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(data, tight)
    assert exc_info.value.code == "ARCHIVE_TOO_MANY_FILES"


def test_expanded_size_cap_rejected() -> None:
    tight = ArchiveLimits(10**9, 100, 5000, 20, 10**6)
    data = make_zip({"big.py": "x" * 1000})
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(data, tight)
    assert exc_info.value.code == "ARCHIVE_EXPANDED_TOO_LARGE"


def test_compression_bomb_rejected() -> None:
    tight = ArchiveLimits(10**9, 10**12, 5000, 20, 10)
    data = make_zip({"bomb.bin": b"\x00" * 100000})
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(data, tight)
    assert exc_info.value.code == "ARCHIVE_COMPRESSION_BOMB"


def test_upload_size_cap_rejected() -> None:
    tight = ArchiveLimits(10, 10**12, 5000, 20, 10**6)
    data = make_zip({"a.py": "x\n"})
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(data, tight)
    assert exc_info.value.code == "ARCHIVE_TOO_LARGE"


def test_depth_cap_rejected() -> None:
    tight = ArchiveLimits(10**9, 10**12, 5000, 3, 10**6)
    data = make_zip({"a/b/c/d.py": "x\n"})
    with pytest.raises(ArchiveRejected) as exc_info:
        validate_archive(data, tight)
    assert exc_info.value.code == "ARCHIVE_TOO_DEEP"


def test_extract_hashes_and_sets_permissions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    data = make_zip({"src/app.py": "print(1)\n"})
    report = validate_archive(data, LIMITS)
    dest = str(tmp_path / "out")
    done = extract_archive(data, report.entries, dest)
    assert len(done) == 1
    assert len(done[0].sha256) == 64
    target = os.path.join(dest, "src", "app.py")
    with open(target, encoding="utf-8") as handle:
        assert handle.read() == "print(1)\n"
    if os.name == "nt":
        pytest.skip("Windows emulates POSIX modes; 0600 is enforced on Linux deployments")
    assert oct(os.stat(target).st_mode & 0o777) == "0o600"


def test_doubled_slash_entry_rejected_at_extract(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Legal ZIP whose member name has no exact normalized match.
    data = make_zip({"a//b.py": "x = 1\n"})
    report = validate_archive(data, LIMITS)
    with pytest.raises(ArchiveRejected) as exc_info:
        extract_archive(data, report.entries, str(tmp_path / "out"))
    assert exc_info.value.code == "ARCHIVE_UNREADABLE_ENTRY"


def test_tree_digest_is_deterministic() -> None:
    first = make_zip({"b.py": "2\n", "a.py": "1\n"})
    second = make_zip({"a.py": "1\n", "b.py": "2\n"})
    from app.services.archive_security import ValidatedEntry

    def digest(data: bytes) -> str:
        report = validate_archive(data, LIMITS)
        entries = [
            ValidatedEntry(path=e.path, size=e.size, sha256="0" * 64) for e in report.entries
        ]
        return compute_tree_digest(entries)

    assert digest(first) == digest(second)
    assert len(digest(first)) == 64
