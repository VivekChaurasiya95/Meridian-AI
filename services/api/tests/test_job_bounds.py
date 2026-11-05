"""Job JSON-bound tests (M4 hardening): pure, no database needed."""

import pytest

from app.envelope import ApiError
from app.services.jobs import MAX_JSON_DEPTH, MAX_JSON_KEYS, check_json_bounds


def test_small_objects_pass() -> None:
    check_json_bounds({"note": "hi"}, max_bytes=1024, label="payload")
    check_json_bounds({}, max_bytes=1024, label="payload")
    check_json_bounds({"a": [1, 2, {"b": None}]}, max_bytes=1024, label="result")


def test_oversized_object_rejected() -> None:
    with pytest.raises(ApiError) as exc:
        check_json_bounds({"blob": "x" * 4096}, max_bytes=1024, label="payload")
    assert exc.value.code == "VALIDATION_ERROR"
    assert exc.value.status_code == 422


def test_boundary_size_passes() -> None:
    # {"k":"..."} compacts to 8 + N bytes; N=1016 lands exactly on 1024.
    check_json_bounds({"k": "x" * 1016}, max_bytes=1024, label="payload")


def test_too_many_keys_rejected() -> None:
    wide = {f"k{i}": i for i in range(MAX_JSON_KEYS + 1)}
    with pytest.raises(ApiError) as exc:
        check_json_bounds(wide, max_bytes=10**6, label="payload")
    assert exc.value.code == "VALIDATION_ERROR"


def test_too_deep_rejected() -> None:
    deep: dict = {}
    node = deep
    for _ in range(MAX_JSON_DEPTH + 1):
        node["n"] = {}
        node = node["n"]
    with pytest.raises(ApiError) as exc:
        check_json_bounds(deep, max_bytes=10**6, label="result")
    assert exc.value.code == "VALIDATION_ERROR"


def test_unserializable_rejected() -> None:
    with pytest.raises(ApiError) as exc:
        check_json_bounds({"when": object()}, max_bytes=10**6, label="result")  # type: ignore[dict-item]
    assert exc.value.code == "VALIDATION_ERROR"
