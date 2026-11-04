"""Git import API tests: validate, create+enqueue, authorization."""

from fastapi.testclient import TestClient


def make_workspace(client: TestClient, slug: str) -> dict:
    r = client.post("/api/v1/workspaces", json={"name": slug, "slug": slug})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_validate_normalizes(auth_client: TestClient) -> None:
    r = auth_client.post(
        "/api/v1/git/validate", json={"repository_url": "https://github.com/Owner/Repo.git/"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["canonical_url"] == "https://github.com/Owner/Repo"


def test_validate_rejects_credentials_and_private(auth_client: TestClient) -> None:
    for url in (
        "https://user:pass@github.com/o/r",
        "https://127.0.0.1/o/r",
        "ssh://git@github.com/o/r",
        "https://github.com:22/o/r",
    ):
        r = auth_client.post("/api/v1/git/validate", json={"repository_url": url})
        assert r.status_code == 422, (url, r.text)


def test_create_git_import_enqueues(auth_client: TestClient) -> None:
    ws = make_workspace(auth_client, "wsgit")
    r = auth_client.post(
        f"/api/v1/workspaces/{ws['id']}/git-imports",
        json={
            "name": "Repo",
            "slug": "repo",
            "repository_url": "https://github.com/owner/repository",
            "branch": "main",
            "idempotency_key": "git-import-1",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["project"]["source_type"] == "git_provider"
    assert data["project"]["repository_url"] == "https://github.com/owner/repository"
    assert data["job"]["job_type"] == "git_import"
    assert data["job"]["status"] == "queued"
    assert data["job"]["payload"]["repository_url"] == "https://github.com/owner/repository"
    again = auth_client.post(
        f"/api/v1/workspaces/{ws['id']}/git-imports",
        json={
            "name": "Repo2",
            "slug": "repo2",
            "repository_url": "https://github.com/owner/repository",
            "branch": "main",
            "idempotency_key": "git-import-1",
        },
    )
    # Second project creation succeeds; job submit dedupes on the key.
    assert again.status_code in (200, 201), again.text


def test_preview_submit_validates_url(auth_client: TestClient) -> None:
    ws = make_workspace(auth_client, "wsprev")
    bad = auth_client.post(
        f"/api/v1/workspaces/{ws['id']}/jobs",
        json={"job_type": "git_preview", "payload": {"repository_url": "https://localhost/o/r"}},
    )
    assert bad.status_code == 422, bad.text
    ok = auth_client.post(
        f"/api/v1/workspaces/{ws['id']}/jobs",
        json={
            "job_type": "git_preview",
            "payload": {"repository_url": "https://github.com/o/r", "evil": "x"},
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["data"]["payload"] == {"repository_url": "https://github.com/o/r"}


def test_git_import_foreign_project_404(auth_client_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("git-owner@example.com")
    other = auth_client_factory("git-other@example.com")
    ws = make_workspace(owner, "wsown")
    created = owner.post(
        f"/api/v1/workspaces/{ws['id']}/git-imports",
        json={"name": "R", "slug": "r", "repository_url": "https://github.com/o/r"},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["data"]["project"]["id"]
    ws2 = make_workspace(other, "wsother")
    foreign = other.post(
        f"/api/v1/workspaces/{ws2['id']}/jobs",
        json={
            "job_type": "git_import",
            "payload": {"project_id": project_id, "repository_url": "https://github.com/o/r"},
        },
    )
    assert foreign.status_code == 404, foreign.text
