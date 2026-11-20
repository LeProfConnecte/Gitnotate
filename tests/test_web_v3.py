"""Contrats Web V3-C : moteur local, isolation, CSRF, sources et enrichissement ciblé.

Toutes les APIs externes sont simulées ou interdites par tests/conftest.py.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import catalogue_v3 as cat
import web_v3

HOST = "http://127.0.0.1:8765"
SOURCE = "0123456789abcdef0123456789abcdef"
REPO = "demo/finance-watch"


def make_catalogue(path: Path):
    with cat.staged_db(path) as con:
        con.execute("INSERT INTO sources(source_id,url,label,scanned_at,links_total,excluded) "
                    "VALUES (?,?,?,?,?,?)",
                    (SOURCE, "https://app.notion.com/p/0123456789abcdef0123456789abcdef",
                     "Signets test", "2026-11-20T00:00:00+00:00", 1, 0))
        con.execute("INSERT INTO links(source_id,repo_key,original_url) VALUES(?,?,?)",
                    (SOURCE, REPO, "https://github.com/Demo/finance-watch"))
        con.execute("INSERT INTO repos(repo_key,owner,repo_name) VALUES(?,?,?)",
                    (REPO, "Demo", "finance-watch"))
        cat.reindex(con, REPO)


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    make_catalogue(path)
    app = web_v3.create_app(path, csrf_token="test-csrf-123")
    with TestClient(app, base_url=HOST) as c:
        yield c


def test_root_and_security_headers(client):
    html = client.get("/")
    assert html.status_code == 200
    assert "Gitnotate V3" in html.text
    assert "sources" in html.text
    assert html.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in html.headers["content-security-policy"]
    assert html.headers["x-frame-options"] == "DENY"
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/styles.css").status_code == 200
    assert ".innerHTML =" not in client.get("/assets/app.js").text
    assert client.get("/docs").status_code == 404


def test_bad_host_rejected(client):
    bad = client.get("/", headers={"host": "evil.example"})
    assert bad.status_code == 400


def test_session_state_and_local_search(client):
    session = client.get("/api/session")
    assert session.status_code == 200
    assert session.json() == {"csrf": "test-csrf-123", "backend": "local",
                             "notion_writes": False, "llm_calls": False}
    current = client.get("/api/state").json()
    assert current["repos"] == 1
    assert current["enriched"] == 0
    assert len(current["sources"]) == 1

    results = client.get("/api/search", params={"q": "finance"})
    assert results.status_code == 200
    hits = results.json()["results"]
    assert len(hits) == 1 and hits[0]["repo"] == REPO
    assert hits[0]["evidence"] == "Signet seul — non enrichi"
    assert hits[0]["source_pages"] == ["Signets test"]


def test_unknown_source_returns_error(client):
    response = client.get("/api/search",
                          params={"q": "finance", "source": "fedcba9876543210fedcba9876543210"})
    assert response.status_code == 400
    assert "source" in response.json()["detail"].lower()


def test_post_requires_session_token_and_origin(client):
    body = {"repos": [REPO]}
    assert client.post("/api/enrich", json=body).status_code == 403
    assert client.post("/api/enrich", json=body,
                       headers={"x-csrf-token": "wrong"}).status_code == 403
    assert client.post("/api/enrich", json=body,
                       headers={"x-csrf-token": "test-csrf-123",
                                "origin": "https://evil.example"}).status_code == 403


def test_unknown_candidate_rejected_before_http(client):
    response = client.post(
        "/api/enrich", json={"repos": ["outsider/unknown"]},
        headers={"x-csrf-token": "test-csrf-123", "origin": HOST})
    assert response.status_code == 400
    assert "absent" in response.json()["detail"].lower()


def test_selected_candidate_routes_to_catalogue(client, monkeypatch):
    calls = []

    def fake_enrich(**kwargs):
        calls.append(kwargs)
        return {"attempted": 1, "updated": 1, "errors": [], "stopped": "",
                "github_auth": False}

    monkeypatch.setattr(web_v3.catalogue, "enrich", fake_enrich)
    response = client.post(
        "/api/enrich", json={"repos": [REPO]},
        headers={"x-csrf-token": "test-csrf-123", "origin": HOST})
    assert response.status_code == 200
    assert response.json()["updated"] == 1
    assert calls[0]["selected_repos"] == [REPO]
    assert calls[0]["limit"] == 1
    assert isinstance(calls[0]["path"], Path)


def test_targeted_enrichment_validates_allowlist_and_cache(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    make_catalogue(path)
    with pytest.raises(cat.CatalogueError, match="absent"):
        cat.enrich(path=path, limit=1, selected_repos=["nobody/unknown"])
    with pytest.raises(cat.CatalogueError, match="Sélection invalide"):
        cat.enrich(path=path, limit=1, selected_repos=[REPO, "demo/other"])
    with pytest.raises(cat.CatalogueError, match="Identifiant"):
        cat.enrich(path=path, limit=1, selected_repos=["../../internal"])


def test_source_url_validation_before_network(client):
    bad = client.post(
        "/api/source", json={"url": "https://evil.example/0123456789abcdef0123456789abcdef"},
        headers={"x-csrf-token": "test-csrf-123", "origin": HOST})
    assert bad.status_code == 400


def test_missing_catalogue_is_read_only(tmp_path):
    app = web_v3.create_app(tmp_path / "missing.sqlite", csrf_token="test")
    with TestClient(app, base_url=HOST) as c:
        result = c.get("/api/state")
        assert result.status_code == 200
        assert result.json()["missing"] is True
        assert not (tmp_path / "missing.sqlite").exists()
