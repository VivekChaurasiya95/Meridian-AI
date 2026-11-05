"""OSV-Scanner wrapper (deferred past V1, security.md Phase 6).

Present so the package layout matches the approved design; dependency
scanning is not wired to any profile, handler, or API until the
Semgrep + Gitleaks foundation is stable.
"""

from __future__ import annotations

OSV = "osv"


def parse(*args: object, **kwargs: object) -> object:
    raise NotImplementedError("OSV-Scanner integration is deferred past V1.")
