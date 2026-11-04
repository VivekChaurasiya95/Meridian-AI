"""Pure unit tests for static stack inspection (no DB, no sockets)."""

import json
import os

from app.services.inspection import inspect_tree, runtime_profile


def write(root: str, relpath: str, content: str = "") -> None:
    full = os.path.join(root, *relpath.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(content)


def test_detects_node_stack(tmp_path) -> None:  # type: ignore[no-untyped-def]
    package = {
        "name": "demo",
        "dependencies": {"next": "15.1.0", "react": "19.0.0"},
        "devDependencies": {"typescript": "5.7.0"},
        "scripts": {"dev": "next dev"},
    }
    write(str(tmp_path), "package.json", json.dumps(package))
    write(str(tmp_path), "package-lock.json", "{}")
    write(str(tmp_path), "jest.config.js", "module.exports = {};")
    write(str(tmp_path), "tsconfig.json", "{}")
    write(str(tmp_path), "app/page.tsx", "export default function Page() {}")
    write(str(tmp_path), "README.md", "# demo")

    result = inspect_tree(str(tmp_path), set())
    assert result.package_manager == "npm"
    names = [f["name"] for f in result.frameworks]
    assert "Next.js" in names and "React" in names
    assert result.test_framework == "Jest"
    assert "TypeScript" in (result.build_system or "")
    assert result.entry_points.get("readme") == "present"
    assert result.languages.get("TypeScript") == 1

    profile = runtime_profile(result)
    assert profile["package_manager"] == "npm"
    assert set(profile) == {
        "languages",
        "frameworks",
        "package_manager",
        "test_framework",
        "build_system",
    }


def test_detects_python_stack(tmp_path) -> None:  # type: ignore[no-untyped-def]
    write(str(tmp_path), "requirements.txt", "fastapi==0.115\npytest>=8\n")
    write(str(tmp_path), "pytest.ini", "[pytest]\n")
    write(str(tmp_path), "app/main.py", "app = 1\n")

    result = inspect_tree(str(tmp_path), set())
    assert result.package_manager == "pip"
    assert [f["name"] for f in result.frameworks] == ["FastAPI"]
    assert result.test_framework == "pytest"
    assert result.languages == {"Python": 1}


def test_unknown_project_reports_not_detected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    write(str(tmp_path), "notes.txt", "hello\n")

    result = inspect_tree(str(tmp_path), set())
    assert result.package_manager is None
    assert result.frameworks == []
    assert result.test_framework is None
    assert any("Not detected" in warning for warning in result.warnings)
    profile = runtime_profile(result)
    assert profile["frameworks"] == []


def test_skipped_dirs_are_invisible(tmp_path) -> None:  # type: ignore[no-untyped-def]
    write(str(tmp_path), "node_modules/react/index.js", "x\n")
    write(str(tmp_path), "src/app.js", "y\n")

    result = inspect_tree(str(tmp_path), {"node_modules"})
    assert result.languages == {"JavaScript": 1}


def test_output_is_deterministic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    write(str(tmp_path), "b.py", "x\n")
    write(str(tmp_path), "a.py", "y\n")
    first = inspect_tree(str(tmp_path), set())
    second = inspect_tree(str(tmp_path), set())
    assert first.languages == second.languages == {"Python": 2}
