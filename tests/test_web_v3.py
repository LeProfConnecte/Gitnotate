"""Contrats Web V3-C : moteur local, isolation, CSRF, sources et enrichissement ciblé.

Toutes les APIs externes sont simulées ou interdites par tests/conftest.py.
"""
from pathlib import Path
import socket

import pytest
from fastapi.testclient import TestClient

import catalogue_v3 as cat
import avis_v3 as avis
import web_v3

# Pendant la collecte pytest, la primitive native n'est pas encore remplacée par
# tests/conftest.py. Sous Windows, asyncio utilise un socketpair TCP en loopback.
_NATIVE_CONNECT = socket.socket.connect


@pytest.fixture(autouse=True)
def allow_asyncio_loopback(monkeypatch, _no_network):
    """Garde l'interdiction réseau externe, mais permet le réveil interne asyncio."""
    def guarded_connect(sock, address):
        if (isinstance(address, tuple) and address
                and address[0] in ("127.0.0.1", "::1")):
            return _NATIVE_CONNECT(sock, address)
        raise RuntimeError("Accès réseau externe interdit pendant les tests")
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


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


# ---------------------------------------------------------------------------
# V3-D : IA facultative, previsualisation et preuves controlables
# ---------------------------------------------------------------------------

def make_enriched_catalogue(path):
    """Une fiche GitHub simulee, deja enrichie : aucun reseau necessaire."""
    make_catalogue(path)
    with cat.staged_db(path) as con:
        con.execute(
            "UPDATE repos SET description=?, topics=?, readme=?, "
            "fetch_status='ok', fetched_at=? WHERE repo_key=?",
            ("Market signals with alerts and automation webhooks.",
             "finance stocks automation",
             "Monitor financial market trends with configurable webhook alerts "
             "and dashboard charts. Educational use only.",
             "2026-11-21T00:00:00+00:00", REPO))
        cat.reindex(con, REPO)


@pytest.fixture
def ai_client(tmp_path, monkeypatch):
    path = tmp_path / "catalogue.sqlite"
    make_enriched_catalogue(path)
    monkeypatch.setattr(avis.gn, "OPENAI_API_KEY", "fake-openai-key-for-tests")
    monkeypatch.setattr(avis.gn, "OPENAI_MODEL", "gpt-6.1-terra")
    application = web_v3.create_app(path, csrf_token="unit-test-csrf")
    with TestClient(application, base_url=HOST) as client:
        yield client, application, path


def test_ai_providers_return_no_secrets(ai_client):
    client, app, _ = ai_client
    providers = client.get("/api/ai/providers")
    assert providers.status_code == 200
    raw = providers.text
    assert "fake-openai-key-for-tests" not in raw
    assert "gpt-6.1-terra" in raw
    assert "OPENAI_API_KEY" not in raw
    assert providers.json()["notion_writes"] is False
    assert providers.json()["explicit_consent_required"] is True


def _ai_headers():
    return {"x-csrf-token": "unit-test-csrf", "origin": HOST}


def _ai_preview(client, repo=REPO, need="automatiser une veille financière"):
    return client.post("/api/ai/preview", headers=_ai_headers(), json={
        "need": need, "repos": [repo], "provider": "openai"})


def test_ai_preview_never_calls_provider_and_minimizes_fields(ai_client, monkeypatch):
    client, app, path = ai_client
    monkeypatch.setattr(avis.gn, "_call_translation_api",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("appel IA interdit dans l'aperçu")))
    before = path.read_bytes()
    response = _ai_preview(client)
    assert response.status_code == 200
    data = response.json()
    assert len(data["preview_id"]) >= 20
    assert data["characters"] > 100
    assert data["provider"]["model"] == "gpt-6.1-terra"
    assert data["messages"][0]["role"] == "system"
    user_text = data["messages"][1]["content"]
    assert "demo/finance-watch" in user_text
    assert "Market signals with alerts" in user_text
    assert "Monitor financial market trends" in user_text
    assert "notion" not in user_text.lower()
    assert "fake-openai-key-for-tests" not in response.text
    assert path.read_bytes() == before


def test_ai_refuses_preview_without_enrichment(client, monkeypatch):
    monkeypatch.setattr(avis.gn, "OPENAI_API_KEY", "dummy")
    response = client.post("/api/ai/preview",
                           headers={"x-csrf-token": "test-csrf-123", "origin": HOST},
                           json={"need": "un outil pour analyser la finance",
                                 "repos": [REPO], "provider": "openai"})
    assert response.status_code == 400
    assert "enrich" in response.json()["detail"].lower()


def test_ai_refuses_outsider_and_duplicate(ai_client):
    client, _, _ = ai_client
    assert _ai_preview(client, repo="outsider/unknown").status_code == 400
    dup = client.post("/api/ai/preview", headers=_ai_headers(), json={
        "need": "analyser les actions", "provider": "openai",
        "repos": [REPO, REPO]})
    assert dup.status_code == 400


def test_ai_confirm_exactly_once_and_keeps_catalogue_unchanged(ai_client, monkeypatch):
    import json
    client, _, path = ai_client
    called = []

    def fake_completion(provider, messages, temperature):
        called.append((provider, messages, temperature))
        data = {"avis": [{
            "id": "R1", "adequation": 3,
            "raison": "Présente des signaux de marché et des alertes configurables.",
            "preuve": "Market signals with alerts and automation webhooks.",
        }]}
        return json.dumps(data), "gpt-6.1-terra"

    monkeypatch.setattr(avis.gn, "_call_translation_api", fake_completion)
    snapshot = path.read_bytes()
    preview = _ai_preview(client).json()
    pid = preview["preview_id"]
    assert called == []
    assert client.post("/api/ai/evaluate", headers=_ai_headers(), json={
        "preview_id": pid, "consent": False}).status_code == 403
    assert called == []
    result = client.post("/api/ai/evaluate", headers=_ai_headers(), json={
        "preview_id": pid, "consent": True})
    assert result.status_code == 200, result.text
    assert len(called) == 1 and called[0][0] == "openai"
    assert result.json()["convincing"] is True
    assert result.json()["results"][0]["ancrage_verifie"] is True
    assert result.json()["results"][0]["adequation"] == 3
    assert result.json()["model_served"] == "gpt-6.1-terra"
    assert client.post("/api/ai/evaluate", headers=_ai_headers(), json={
        "preview_id": pid, "consent": True}).status_code == 410
    assert len(called) == 1
    assert path.read_bytes() == snapshot


def test_ai_expired_preview_never_contacts_provider(ai_client, monkeypatch):
    client, app, _ = ai_client
    preview = _ai_preview(client).json()
    with app.state.ai_lock:
        app.state.ai_previews[preview["preview_id"]]["expires"] = 0
    monkeypatch.setattr(avis.gn, "_call_translation_api",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("expired preview must not call API")))
    response = client.post("/api/ai/evaluate", headers=_ai_headers(), json={
        "preview_id": preview["preview_id"], "consent": True})
    assert response.status_code == 410


def test_ai_no_silent_provider_fallback(ai_client, monkeypatch):
    client, _, _ = ai_client
    preview = _ai_preview(client).json()
    calls = []
    def failure(provider, messages, temperature):
        calls.append(provider)
        return None
    monkeypatch.setattr(avis.gn, "_call_translation_api", failure)
    result = client.post("/api/ai/evaluate", headers=_ai_headers(), json={
        "preview_id": preview["preview_id"], "consent": True})
    assert result.status_code == 502
    assert calls == ["openai"]


def test_ai_rejects_unsupported_high_score_and_wrong_repo_evidence():
    candidate = avis.Candidate(
        "R1", "demo/finance-watch",
        "Automated stock alerts with trade signals.", "stocks",
        "Financial dashboard with automated investment reports.", "")
    bad = '{"avis":[{"id":"R1","adequation":3,"raison":"Ce dépôt répond au besoin.",' \
          '"preuve":"Provides production-grade algorithmic trading."}]}'
    with pytest.raises(avis.AvisError, match="preuve"):
        avis.parse_output(bad, [candidate])
    no_evidence = '{"avis":[{"id":"R1","adequation":3,"raison":"Candidat excellent.",' \
                  '"preuve":""}]}'
    with pytest.raises(avis.AvisError, match="preuve"):
        avis.parse_output(no_evidence, [candidate])


def test_ai_can_conclude_no_suitable_candidate():
    candidate = avis.Candidate("R1", "demo/other", "A design system.",
                              "", "UI components and color tokens.", "")
    low = '{"avis":[{"id":"R1","adequation":0,"raison":"Aucun rapport avec la finance.",' \
          '"preuve":""}]}'
    result = avis.parse_output(low, [candidate])
    assert result[0]["adequation"] == 0
    assert result[0]["ancrage_verifie"] is False


def test_ai_csrf_required_before_preview(ai_client):
    client, _, _ = ai_client
    body = {"need": "un moteur de veille financière", "repos": [REPO], "provider": "openai"}
    assert client.post("/api/ai/preview", json=body).status_code == 403
    assert client.post("/api/ai/preview", json=body,
                       headers={"x-csrf-token": "unit-test-csrf",
                                "origin": "https://attacker.example"}).status_code == 403


def test_ai_disallows_second_concurrent_evaluation(ai_client, monkeypatch):
    client, app, _ = ai_client
    preview = _ai_preview(client).json()
    app.state.ai_busy = True
    monkeypatch.setattr(avis.gn, "_call_translation_api",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("no double charge")))
    response = client.post("/api/ai/evaluate", headers=_ai_headers(), json={
        "preview_id": preview["preview_id"], "consent": True})
    assert response.status_code == 409
    # Le jeton n'est pas consommé par un appel refusé faute de place.
    assert preview["preview_id"] in app.state.ai_previews
