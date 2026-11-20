"""Tests isolés de l'interface web V3-C : localhost, CSRF, sources et .env privé.

Réseau réel interdit par tests/conftest.py. Pas de données Notion ni de clés réelles.
"""
import re
import os
import socket
import traceback
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import web_v3 as ui

# Capturé à la collecte des tests, AVANT le garde réseau autouse.
_NATIVE_SOCKET_CONNECT = socket.socket.connect


def _allow_windows_socketpair_only(monkeypatch):
    """AnyIO doit ouvrir un socketpair de réveil sous Windows.
    
    Exception stricte pour le mécanisme interne de la boucle asyncio :
    toute connexion réseau classique reste interdite par conftest.py.
    """
    if os.name != "nt":
        return

    def connect_only_internal_socketpair(sock, address):
        allowed = (
            isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1")
            and any(frame.name == "socketpair" and frame.filename.endswith("socket.py")
                    for frame in traceback.extract_stack())
        )
        if not allowed:
            raise RuntimeError("Accès réseau interdit pendant les tests")
        return _NATIVE_SOCKET_CONNECT(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect_only_internal_socketpair)


FAKE_URL = "https://app.notion.com/p/Exemple-0123456789abcdef0123456789abcdef"
FAKE_SOURCE = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    _allow_windows_socketpair_only(monkeypatch)
    filename = tmp_path / ".env"
    filename.write_text(
        'NOTION_READONLY_TOKEN="fake-notion-token-private"\n'
        'DATABASE_ID="0123456789abcdef0123456789abcdef"\n'
        'OPENAI_API_KEY="fake-openai-existing-private"\n'
        'OPENAI_MODEL="gpt-6-luna"\n'
        'LLM_PROVIDERS="mistral,openrouter"\n'
        '# ligne personnelle à conserver\n', encoding="utf-8")
    monkeypatch.setattr(ui, "ENV_PATH", filename)
    status = {
        "sources":[{"source_id":FAKE_SOURCE,"url":FAKE_URL,"label":"Exemple",
                    "scanned_at":"2026-11-20T00:00:00Z","links_total":123,"excluded":0}],
        "repos":809,"enriched":10,"comparison_available":True,
        "already_in_historical":427,"not_in_historical":382
    }
    monkeypatch.setattr(ui.catalogue, "state", lambda:status)
    client=TestClient(ui.app, base_url="http://127.0.0.1:8765")
    return client, filename


def authenticated(client):
    token = client.get("/api/bootstrap").json()["csrf"]
    return {"x-gitnotate-csrf": token, "origin":"http://127.0.0.1:8765"}


def test_html_and_local_dashboard(app_client):
    client, _ = app_client
    response=client.get("/")
    assert response.status_code==200
    assert "Gitnotate" in response.text
    assert "cdn." not in response.text
    assert "Notion" in response.text
    assert "script defer" in response.text
    assert client.get("/assets/styles.css").status_code==200
    assert client.get("/assets/app.js").status_code==200
    assert client.get("/api/etat").json()["repos"]==809


def test_http_host_and_csrf_block_cross_site(app_client):
    client, _ = app_client
    assert client.get("/api/bootstrap",headers={"Host":"attacker.example"}).status_code==400
    without=client.post("/api/recherche",json={"besoin":"finance"})
    assert without.status_code==403
    headers=authenticated(client)
    origin={**headers,"origin":"https://evil.example"}
    assert client.post("/api/recherche",headers=origin,json={"besoin":"finance"}).status_code==403
    wrong={**headers,"x-gitnotate-csrf":"fake"}
    assert client.post("/api/recherche",headers=wrong,json={"besoin":"finance"}).status_code==403


def test_search_uses_only_local_catalogue(app_client,monkeypatch):
    client, _ = app_client
    calls=[]
    def fake(need,limit,only_sources):
        calls.append((need,limit,only_sources))
        return {"need":need,"results":[]}
    monkeypatch.setattr(ui.catalogue,"search",fake)
    headers=authenticated(client)
    response=client.post("/api/recherche",headers=headers,json={
        "besoin":"OCR de plans techniques","nombre":5,"sources":[FAKE_URL]})
    assert response.status_code==200
    assert calls==[("OCR de plans techniques",5,[FAKE_URL])]
    assert client.post("/api/recherche",headers=headers,json={
        "besoin":"finance","nombre":500}).status_code==422


def test_source_add_notion_only_no_writing(app_client,monkeypatch):
    client, _ = app_client
    seen=[]
    monkeypatch.setattr(ui.catalogue,"inventory",lambda pages:{
        "distinct_repos":809,"sources":seen.append(pages) or []})
    headers=authenticated(client)
    assert client.post("/api/sources/ajouter",headers=headers,json={"url":FAKE_URL}).status_code==200
    assert seen==[[FAKE_URL]]
    assert client.post("/api/sources/ajouter",headers=headers,json={
        "url":"https://evil.example/p/0123456789abcdef0123456789abcdef"}).status_code==400


def test_enrichment_requires_explicit_post_and_is_bounded(app_client,monkeypatch):
    client,_=app_client
    seen=[]
    monkeypatch.setattr(ui.catalogue,"enrich",lambda limit:{
        "updated":seen.append(limit) or limit,"errors":[],"stopped":""})
    headers=authenticated(client)
    assert client.post("/api/depot/enrichir",headers=headers,json={"limite":10}).status_code==200
    assert seen==[10]
    assert client.post("/api/depot/enrichir",headers=headers,json={"limite":809}).status_code==422


def test_provider_settings_do_not_return_key_or_overwrite_notion(app_client):
    client, filename=app_client
    headers=authenticated(client)
    initial=client.get("/api/fournisseurs").json()
    assert "fake-openai-existing-private" not in str(initial)
    assert any(p["id"]=="openai" and p["cle_presente"] for p in initial["providers"])
    response=client.post("/api/fournisseurs/enregistrer",headers=headers,json={
        "fournisseur":"openai","modele":"gpt-6.1-terra",
        "cle":"fake-openai-new-private","principal":True})
    assert response.status_code==200
    content=filename.read_text(encoding="utf-8")
    assert "fake-notion-token-private" in content
    assert 'DATABASE_ID="0123456789abcdef0123456789abcdef"' in content
    assert '# ligne personnelle à conserver' in content
    assert "gpt-6.1-terra" in content
    assert "fake-openai-new-private" in content
    assert 'LLM_PROVIDERS="openai,mistral,openrouter"' in content
    assert "fake-openai-new-private" not in response.text
    assert "fake-openai-new-private" not in str(client.get("/api/fournisseurs").json())


def test_github_key_is_private_and_used_for_bounded_enrichment(app_client, monkeypatch):
    client, filename = app_client
    headers = authenticated(client)
    assert client.get("/api/github").json() == {"cle_presente": False}
    seen = []

    def fake_enrich(limit):
        import os
        seen.append((limit, os.environ.get("GITHUB_TOKEN")))
        return {"updated": limit, "errors": [], "stopped": ""}

    monkeypatch.setattr(ui.catalogue, "enrich", fake_enrich)
    response = client.post("/api/github/enregistrer", headers=headers,
                           json={"cle": "github_pat_fake_secret_12345"})
    assert response.status_code == 200
    assert "github_pat_fake_secret_12345" not in response.text
    assert client.get("/api/github").json() == {"cle_presente": True}
    assert "fake-notion-token-private" in filename.read_text(encoding="utf-8")
    assert "github_pat_fake_secret_12345" in filename.read_text(encoding="utf-8")
    import os
    before = os.environ.get("GITHUB_TOKEN")
    assert client.post("/api/depot/enrichir", headers=headers,
                       json={"limite": 2}).status_code == 200
    assert seen == [(2, "github_pat_fake_secret_12345")]
    assert os.environ.get("GITHUB_TOKEN") == before


def test_provider_rejects_invalid_model_and_missing_priority_key(app_client):
    client, filename=app_client
    before=filename.read_bytes()
    headers=authenticated(client)
    assert client.post("/api/fournisseurs/enregistrer",headers=headers,json={
        "fournisseur":"mistral","modele":"../data ; exit",
        "cle":"","principal":False}).status_code==400
    assert client.post("/api/fournisseurs/enregistrer",headers=headers,json={
        "fournisseur":"anthropic","modele":"claude-sonnet-4-6",
        "cle":"","principal":True}).status_code==400
    assert filename.read_bytes()==before


def test_mutation_lock_gives_409_when_busy(app_client,monkeypatch):
    client,_=app_client
    headers=authenticated(client)
    assert ui.MUTATION_LOCK.acquire(blocking=False)
    try:
        response=client.post("/api/depot/enrichir",headers=headers,json={"limite":1})
        assert response.status_code==409
    finally:
        ui.MUTATION_LOCK.release()


def test_provider_check_does_not_generate(app_client,monkeypatch):
    client,_=app_client
    headers=authenticated(client)
    called=[]
    def fake_run(args, **kwargs):
        called.append(args)
        return SimpleNamespace(returncode=0, stdout="Clé valide", stderr="")
    monkeypatch.setattr(ui.subprocess,"run",fake_run)
    response=client.post("/api/fournisseurs/verifier",headers=headers,json={})
    assert response.status_code==200
    assert response.json()["ok"] is True
    assert called and called[0][-1].endswith("check_llm.py")
