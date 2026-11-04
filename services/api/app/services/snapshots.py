"""Compatibility alias — the canonical implementation lives in app.services.storage.

This module re-exports the snapshot retrieval/verification surface so
any ``app.services.snapshots`` imports keep working. Do not add a
second implementation here.
"""

from app.services.storage import (
    delete_snapshot_content,
    download_snapshot_object,
    get_store,
    materialize_snapshot,
    verify_snapshot,
)

__all__ = [
    "delete_snapshot_content",
    "download_snapshot_object",
    "get_store",
    "materialize_snapshot",
    "verify_snapshot",
]
