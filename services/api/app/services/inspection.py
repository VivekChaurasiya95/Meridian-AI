"""Static repository inspection (M3, SECURITY.md §6.2).

Reads file names and dependency manifests from an extracted tree. Nothing
is executed: no installs, no builds, no scripts. Output is deterministic
(key order fixed, framework lists sorted) so snapshots stay comparable.

Undetectable fields are reported as ``None`` ("Not detected" in the UI);
the inspector never guesses.
"""

import json
import os
from dataclasses import dataclass, field

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
}

# Dependency key (package.json) or manifest marker -> framework name.
JS_FRAMEWORKS = {
    "next": "Next.js",
    "react": "React",
    "react-dom": "React",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "@angular/core": "Angular",
    "svelte": "Svelte",
    "@sveltejs/kit": "SvelteKit",
    "express": "Express",
    "fastify": "Fastify",
    "nest": "NestJS",
    "@nestjs/core": "NestJS",
    "gatsby": "Gatsby",
    "remix": "Remix",
    "@remix-run/react": "Remix",
    "astro": "Astro",
}
PYTHON_FRAMEWORKS = {
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "tornado": "Tornado",
    "sanic": "Sanic",
    "starlette": "Starlette",
    "pyramid": "Pyramid",
}

# Manifest filename -> package manager name.
PACKAGE_MANAGERS = {
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "Yarn",
    "package-lock.json": "npm",
    "bun.lockb": "Bun",
    "bun.lock": "Bun",
    "poetry.lock": "Poetry",
    "Pipfile.lock": "Pipenv",
    "Pipfile": "Pipenv",
    "pyproject.toml": "pip",
    "requirements.txt": "pip",
    "setup.py": "pip",
    "go.mod": "Go modules",
    "Cargo.toml": "Cargo",
    "Cargo.lock": "Cargo",
    "Gemfile": "Bundler",
    "composer.json": "Composer",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
}

TEST_SIGNALS = {
    "jest.config.js": "Jest",
    "jest.config.ts": "Jest",
    "jest.config.cjs": "Jest",
    "vitest.config.ts": "Vitest",
    "vitest.config.js": "Vitest",
    "pytest.ini": "pytest",
    "tox.ini": "pytest",
    "conftest.py": "pytest",
    "phpunit.xml": "PHPUnit",
    "phpunit.xml.dist": "PHPUnit",
}

BUILD_SIGNALS = {
    "vite.config.ts": "Vite",
    "vite.config.js": "Vite",
    "webpack.config.js": "webpack",
    "next.config.js": "Next.js",
    "next.config.mjs": "Next.js",
    "next.config.ts": "Next.js",
    "tsconfig.json": "TypeScript",
    "Makefile": "Make",
    "Dockerfile": "Docker",
    "turbo.json": "Turborepo",
}

# Small, safe manifest reads: name -> max bytes parsed.
MANIFEST_READ_CAP = 1024 * 1024


@dataclass
class InspectionResult:
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: list[dict[str, str | None]] = field(default_factory=list)
    package_manager: str | None = None
    test_framework: str | None = None
    build_system: str | None = None
    entry_points: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _read_text_capped(path: str) -> str | None:
    try:
        if os.path.getsize(path) > MANIFEST_READ_CAP:
            return None
        with open(path, encoding="utf-8", errors="strict") as handle:
            return handle.read(MANIFEST_READ_CAP + 1)[: MANIFEST_READ_CAP + 1]
    except (OSError, UnicodeDecodeError):
        return None


def _js_frameworks(package_json: dict) -> list[dict[str, str | None]]:
    found: dict[str, str | None] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        deps = package_json.get(section)
        if not isinstance(deps, dict):
            continue
        for key, version in deps.items():
            name = JS_FRAMEWORKS.get(key)
            if name and name not in found:
                found[name] = version if isinstance(version, str) else None
    return [{"name": name, "version": found[name]} for name in sorted(found)]


def _python_frameworks(requirements: list[str]) -> list[dict[str, str | None]]:
    found: dict[str, None] = {}
    for line in requirements:
        token = line.strip().split("#", 1)[0].strip().lower()
        if not token or token.startswith(("-", " ")):
            continue
        name = "".join(
            c for c in token.split("=")[0].split(">")[0].split("<")[0].strip().split()[0]
        )
        pretty = PYTHON_FRAMEWORKS.get(name)
        if pretty and pretty not in found:
            found[pretty] = None
    return [{"name": name, "version": None} for name in sorted(found)]


def inspect_tree(root: str, skip_dirs: set[str]) -> InspectionResult:
    """Walk an extracted tree and report the detected stack.

    ``skip_dirs`` holds top-level directory names excluded from indexing
    (the archive policy); anything under them is invisible here.
    """
    result = InspectionResult()
    manifest_names: set[str] = set()
    package_json: dict | None = None
    requirements: list[str] = []
    test_signals: set[str] = set()
    build_signals: set[str] = set()

    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in skip_dirs)
        rel = os.path.relpath(current, root)
        depth_root = rel == "."
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            language = LANGUAGE_BY_EXTENSION.get(ext)
            if language:
                result.languages[language] = result.languages.get(language, 0) + 1
            if depth_root:
                manifest_names.add(name)
            full = os.path.join(current, name)
            if name in TEST_SIGNALS:
                test_signals.add(TEST_SIGNALS[name])
            if name in BUILD_SIGNALS:
                build_signals.add(BUILD_SIGNALS[name])
            if name == "package.json" and package_json is None and depth_root:
                text = _read_text_capped(full)
                if text:
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            package_json = parsed
                    except json.JSONDecodeError:
                        result.warnings.append("package.json could not be parsed.")
            if name in ("requirements.txt", "requirements-dev.txt") and depth_root:
                text = _read_text_capped(full)
                if text:
                    requirements.extend(text.splitlines())

    if package_json is not None:
        result.frameworks.extend(_js_frameworks(package_json))
        main = package_json.get("main")
        if isinstance(main, str) and main:
            result.entry_points["node_main"] = main[:256]
        scripts = package_json.get("scripts")
        if isinstance(scripts, dict):
            for key in sorted(scripts)[:8]:
                if isinstance(key, str):
                    result.entry_points[f"npm:{key}"] = str(scripts[key])[:256]
    if requirements:
        result.frameworks.extend(_python_frameworks(requirements))

    for lockfile in sorted(manifest_names):
        manager = PACKAGE_MANAGERS.get(lockfile)
        if manager and result.package_manager is None:
            result.package_manager = manager
    # pyproject.toml alone still names the Python toolchain.
    if result.package_manager is None and "pyproject.toml" in manifest_names:
        result.package_manager = "pip"
    if len(test_signals) == 1:
        result.test_framework = sorted(test_signals)[0]
    elif test_signals:
        result.test_framework = ", ".join(sorted(test_signals))
    if len(build_signals) == 1:
        result.build_system = sorted(build_signals)[0]
    elif build_signals:
        result.build_system = ", ".join(sorted(build_signals))
    if "README.md" in manifest_names or "README.rst" in manifest_names:
        result.entry_points["readme"] = "present"
    if "Dockerfile" in manifest_names:
        result.entry_points["dockerfile"] = "present"

    has_manifest = bool(manifest_names.intersection(PACKAGE_MANAGERS))
    if not has_manifest and not requirements and package_json is None:
        result.warnings.append("No dependency manifest found; stack shows Not detected.")
    result.languages = dict(sorted(result.languages.items(), key=lambda item: (-item[1], item[0])))
    result.warnings = sorted(set(result.warnings))
    return result


def runtime_profile(result: InspectionResult) -> dict:
    """Server-owned allowlisted profile stored on the project row."""
    return {
        "languages": list(result.languages)[:5],
        "frameworks": [f["name"] for f in result.frameworks][:8],
        "package_manager": result.package_manager,
        "test_framework": result.test_framework,
        "build_system": result.build_system,
    }
