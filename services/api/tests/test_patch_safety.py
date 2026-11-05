"""Patch safety tests (M8): pure, no database needed."""

import pytest

from app.config import get_settings
from app.envelope import ApiError
from app.services.model_gateway import parse_patch_proposal, parse_regression_tests
from app.services.patch_diff import (
    apply_unified_diff,
    files_changed_summary,
    parse_unified_diff,
)
from app.services.patch_paths import check_repo_path

GOOD_DIFF = """--- a/index.html
+++ b/index.html
@@ -1,3 +1,3 @@
 <h1>hi</h1>
-<button disabled>go</button>
+<button>go</button>
 <p>end</p>
"""


def test_check_repo_path() -> None:
    assert check_repo_path("a/b.js", "x") == "a/b.js"
    assert check_repo_path("a/./b.js", "x") == "a/b.js"
    for bad in ["", "/abs", "../escape", "a/../../x", "Meridian.rules/evil", ".git/x", "a\x00b"]:
        with pytest.raises(ApiError):
            check_repo_path(bad, "x")


def test_parse_good_diff() -> None:
    files = parse_unified_diff(GOOD_DIFF)
    assert len(files) == 1
    assert files[0].path == "index.html"
    assert files[0].change == "modified"
    assert files_changed_summary(files) == [
        {"path": "index.html", "change": "modified", "additions": 1, "deletions": 1}
    ]


def test_parse_added_and_deleted() -> None:
    diff = (
        "--- /dev/null\n+++ b/new.js\n@@ -0,0 +1 @@\n+console.log(1)\n"
        "--- a/old.js\n+++ /dev/null\n@@ -1 +0,0 @@\n-console.log(0)\n"
    )
    files = parse_unified_diff(diff)
    assert [(f.path, f.change) for f in files] == [("new.js", "added"), ("old.js", "deleted")]


@pytest.mark.parametrize(
    "diff",
    [
        "",
        "not a diff",
        "--- a/x\n",
        "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
        "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n",
        "--- a/x\n+++ b/y\n@@ -1 +1 @@\n-a\n+b\n",
        "--- a/../evil\n+++ b/../evil\n@@ -1 +1 @@\n-a\n+b\n",
        "--- /dev/null\n+++ /dev/null\n@@ -0,0 +0,0 @@\n",
        "Binary files a/x and b/x differ\n",
    ],
)
def test_parse_rejects_bad_diffs(diff: str) -> None:
    with pytest.raises(ApiError) as exc:
        parse_unified_diff(diff)
    assert exc.value.code == "PATCH_DIFF_INVALID"


def test_apply_round_trip_and_conflict(tmp_path) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "index.html"
    target.write_text("<h1>hi</h1>\n<button disabled>go</button>\n<p>end</p>\n", encoding="utf-8")
    files = parse_unified_diff(GOOD_DIFF)
    written = apply_unified_diff(str(tmp_path), files)
    assert written == ["index.html"]
    assert "<button>go</button>" in target.read_text(encoding="utf-8")
    with pytest.raises(ApiError) as exc:
        apply_unified_diff(str(tmp_path), files)
    assert exc.value.code == "PATCH_APPLY_CONFLICT"
    # Failed application left the tree untouched.
    assert "<button>go</button>" in target.read_text(encoding="utf-8")


def test_apply_rejects_escape(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.services.patch_diff import DiffFile, DiffHunk

    hunk = DiffHunk(old_start=1, old_count=0, new_start=1, new_count=1, lines=("+x",))
    with pytest.raises(ApiError):
        apply_unified_diff(str(tmp_path), [DiffFile(path="../evil", change="added", hunks=(hunk,))])


def test_parse_regression_tests() -> None:
    settings = get_settings()
    drafts = parse_regression_tests(
        {
            "tests": [
                {
                    "title": "button enables",
                    "description": "after load",
                    "test_type": "e2e",
                    "file_path": "tests/button.spec.ts",
                    "test_name": "enables",
                    "steps": [{"action": "assert_text", "selector": "button", "text": "go"}],
                }
            ]
        },
        settings,
    )
    assert len(drafts) == 1
    assert drafts[0].steps[0]["action"] == "assert_text"
    with pytest.raises(ApiError):
        parse_regression_tests({"tests": []}, settings)
    with pytest.raises(ApiError):
        parse_regression_tests(
            {
                "tests": [
                    {
                        "title": "t",
                        "test_type": "unit",
                        "steps": [{"action": "assert_text", "selector": "b", "text": "x"}],
                    }
                ]
            },
            settings,
        )
    with pytest.raises(ApiError):
        parse_regression_tests(
            {"tests": [{"title": "t", "steps": [{"action": "wait", "ms": 100}]}]}, settings
        )


def test_parse_patch_proposal() -> None:
    draft = parse_patch_proposal({"summary": "fix it", "diff": GOOD_DIFF}, 1024 * 1024)
    assert draft.summary == "fix it"
    with pytest.raises(ApiError):
        parse_patch_proposal({"summary": "x", "diff": "   "}, 1024)
    with pytest.raises(ApiError):
        parse_patch_proposal({"summary": "x", "diff": "y" * 2000}, 100)
