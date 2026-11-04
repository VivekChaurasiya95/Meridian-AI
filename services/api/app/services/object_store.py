"""Private object storage for immutable snapshot content (M5.1).

Only the trusted backend uses this module: the bucket is private, keys
are content-addressed, and no credentials ever leave the server process
(no signed URLs, no keys in responses, logs, or errors).

Design (docs/DECISIONS.md D51): deterministic tarballs of the indexed
file set, keyed ``snapshots/<sha256[0:2]>/<sha256>.tar``. Identical
bytes share a key (safe cross-snapshot dedup); deletion removes the
object only when no live snapshot references it.
"""

import hashlib
import logging
import os
from typing import Protocol

logger = logging.getLogger("meridian.storage")

TAR_MIME = "application/x-tar"


class StorageError(Exception):
    """Object-storage failure with a safe code (never credentials)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def storage_key_for_digest(object_sha256: str) -> str:
    """Content-addressed key; caller must validate the digest shape."""
    return f"snapshots/{object_sha256[:2]}/{object_sha256}.tar"


class ObjectStore(Protocol):
    """Minimal surface the pipeline needs (fakeable in pure tests)."""

    def ensure_bucket(self, bucket: str) -> None: ...
    def put_file(self, bucket: str, key: str, path: str) -> int: ...
    def get_bytes(self, bucket: str, key: str) -> bytes: ...
    def download_file(self, bucket: str, key: str, path: str) -> None: ...
    def object_exists(self, bucket: str, key: str) -> bool: ...
    def delete_object(self, bucket: str, key: str) -> None: ...
    def list_objects(self, bucket: str, prefix: str) -> list[tuple[str, int]]: ...


class MinioObjectStore:
    """boto3-backed store. Buckets stay private: nothing here creates
    policies, signed URLs, or public access."""

    def __init__(
        self, endpoint_url: str, access_key: str, secret_key: str, region: str
    ) -> None:
        import boto3
        from botocore.config import Config

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=60),
        )

    def _wrap(self, operation: str, key: str) -> StorageError:
        return StorageError("STORAGE_UNAVAILABLE", f"Object storage {operation} failed.")

    def ensure_bucket(self, bucket: str) -> None:
        import botocore.exceptions

        try:
            self._client.head_bucket(Bucket=bucket)
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchBucket", "NotFound"):
                try:
                    self._client.create_bucket(Bucket=bucket)
                    return
                except botocore.exceptions.ClientError:
                    pass
            logger.warning("object storage bucket check failed bucket=%s", bucket)
            raise self._wrap("unavailable", bucket) from exc
        except Exception as exc:
            raise self._wrap("unavailable", bucket) from exc

    def put_file(self, bucket: str, key: str, path: str) -> int:
        try:
            self.ensure_bucket(bucket)
            self._client.upload_file(
                path, bucket, key, ExtraArgs={"ContentType": TAR_MIME}
            )
            head = self._client.head_object(Bucket=bucket, Key=key)
            return int(head.get("ContentLength", 0))
        except StorageError:
            raise
        except Exception as exc:
            raise self._wrap("upload", key) from exc

    def get_bytes(self, bucket: str, key: str) -> bytes:
        import botocore.exceptions

        try:
            response = self._client.get_object(Bucket=bucket, Key=key)
            body = response["Body"].read()
            if not isinstance(body, bytes):
                raise self._wrap("download", key)
            return body
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                raise StorageError("OBJECT_NOT_FOUND", "The stored object is missing.") from exc
            raise self._wrap("download", key) from exc
        except Exception as exc:
            raise self._wrap("download", key) from exc

    def download_file(self, bucket: str, key: str, path: str) -> None:
        import botocore.exceptions

        try:
            self._client.download_file(bucket, key, path)
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                raise StorageError("OBJECT_NOT_FOUND", "The stored object is missing.") from exc
            raise self._wrap("download", key) from exc
        except Exception as exc:
            raise self._wrap("download", key) from exc

    def object_exists(self, bucket: str, key: str) -> bool:
        import botocore.exceptions

        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                return False
            raise self._wrap("lookup", key) from exc
        except Exception as exc:
            raise self._wrap("lookup", key) from exc

    def delete_object(self, bucket: str, key: str) -> None:
        try:
            self._client.delete_object(Bucket=bucket, Key=key)
        except Exception as exc:
            raise self._wrap("delete", key) from exc

    def list_objects(self, bucket: str, prefix: str) -> list[tuple[str, int]]:
        import botocore.exceptions

        try:
            found: list[tuple[str, int]] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for entry in page.get("Contents", []):
                    found.append((str(entry["Key"]), int(entry.get("Size", 0))))
            return found
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchBucket", "404", "NotFound"):
                return []
            raise self._wrap("list", prefix) from exc
        except Exception as exc:
            raise self._wrap("list", prefix) from exc


class FakeObjectStore:
    """In-memory store for pure unit tests (never used in production)."""

    def __init__(self, fail_with: StorageError | None = None) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_with = fail_with

    def _maybe_fail(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    def ensure_bucket(self, bucket: str) -> None:
        self._maybe_fail()

    def put_file(self, bucket: str, key: str, path: str) -> int:
        self._maybe_fail()
        with open(path, "rb") as handle:
            data = handle.read()
        self.objects[f"{bucket}/{key}"] = data
        return len(data)

    def get_bytes(self, bucket: str, key: str) -> bytes:
        self._maybe_fail()
        try:
            return self.objects[f"{bucket}/{key}"]
        except KeyError:
            raise StorageError("OBJECT_NOT_FOUND", "The stored object is missing.") from None

    def download_file(self, bucket: str, key: str, path: str) -> None:
        self._maybe_fail()
        try:
            data = self.objects[f"{bucket}/{key}"]
        except KeyError:
            raise StorageError("OBJECT_NOT_FOUND", "The stored object is missing.") from None
        with open(path, "wb") as handle:
            handle.write(data)

    def object_exists(self, bucket: str, key: str) -> bool:
        self._maybe_fail()
        return f"{bucket}/{key}" in self.objects

    def delete_object(self, bucket: str, key: str) -> None:
        self._maybe_fail()
        self.objects.pop(f"{bucket}/{key}", None)

    def list_objects(self, bucket: str, prefix: str) -> list[tuple[str, int]]:
        # S3 returns full keys (prefix included); match that exactly so
        # comparisons against stored storage_key values are valid.
        self._maybe_fail()
        base = f"{bucket}/"
        want = f"{bucket}/{prefix}"
        return sorted(
            (key.removeprefix(base), len(data))
            for key, data in self.objects.items()
            if key.startswith(want)
        )


def sha256_file(path: str) -> str:
    """Stream a file's SHA-256 without loading it into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_snapshot_tar(indexed: list[tuple[str, str]], source_dir: str, tar_path: str) -> None:
    """Write a deterministic tarball of indexed files.

    ``indexed`` holds (relative_posix_path, sha256) sorted by path.
    Determinism: sorted members, PAX_FORMAT, zeroed mtime/uid/gid/names,
    fixed file/dir modes. Only regular files are written; anything else
    in ``source_dir`` is ignored (the index is authoritative).
    """
    import tarfile

    with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as tar:
        for rel_path, _digest in sorted(indexed):
            full = os.path.join(source_dir, *rel_path.split("/"))
            info = tar.gettarinfo(full, arcname=rel_path)
            if info is None or not info.isfile():
                raise StorageError(
                    "TAR_BUILD_FAILED", f"Indexed file is missing: {rel_path}"
                )
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o600
            with open(full, "rb") as handle:
                tar.addfile(info, handle)
