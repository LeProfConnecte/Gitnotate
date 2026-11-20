"""Tests isolés de l'inventaire de signets et du catalogue V3.

Aucun appel réel à Notion ou GitHub, aucun fichier de données personnel touché.
"""
from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

import pytest

import catalogue_v3 as cat

PAGE_A = "https://app.notion.com/p/Github-ou-similaire-d-couvrir-1cab36ca5523800292cad5f59ab1fc0c"
PAGE_B = "https://app.notion.com/p/Autres-signets-2cab36ca5523800292cad5f59ab1fc0c"
ID_A = "1cab36ca5523800292cad5f59ab1fc0c"
ID_B = "2cab36ca5523800292cad5f59ab1fc0c"


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        return self.payload


def bookmark(url, n=1):
    return {"type": "bookmark", "bookmark": {"url": url},
            "id": f"{n:032x}", "has_children": False}


def text_block(text, n=1):
    return {"type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "text": {"content": text}}]},
        "id": f"{n:032x}", "has_children": False}


class NotionFake:
    def __init__(self, pages):
        self.pages = pages
        self.requests = []
        self.status = 200

    def get(self, url, headers=None, params=None, timeout=None):
        assert url.startswith("https://api.notion.com/v1/blocks/")
        assert url.endswith("/children")
        assert headers["Authorization"] == "Bearer fake-notion-readonly"
        self.requests.append((url, dict(params or {})))
        identity = url.split("/")[-2]
        blocks = self.pages.get(identity, [])
        if self.status != 200:
            return Response({}, self.status)
        offset = int((params or {}).get("start_cursor") or "0")
        batch = blocks[offset:offset + 100]
        next_cursor = str(offset + 100) if offset + 100 < len(blocks) else None
        return Response({"results": batch, "has_more": next_cursor is not None,
                         "next_cursor": next_cursor})


class GitHubFake:
    def __init__(self, rate_limited=False):
        self.calls = []
        self.rate_limited = rate_limited

    def get(self, url, headers=None, timeout=None):
        assert url.startswith("https://api.github.com/repos/")
        assert (headers or {}).get("Authorization") is None
        self.calls.append(url)
        if self.rate_limited:
            return Response({}, 429)
        if url.endswith("/readme"):
            content = base64.b64encode(
                b"Portfolio finance financial stocks market monitoring analytics automation"
            ).decode("ascii")
            return Response({"content": content, "encoding": "base64"})
        if "notfound" in url:
            return Response({}, 404)
        return Response({
            "owner": {"login": "Demo"}, "name": urlsplit(url).path.split("/")[-1],
            "description": "Financial market stock portfolio analytics automation",
            "topics": ["finance", "stocks", "automation"],
            "language": "Python", "license": {"spdx_id": "MIT"},
            "stargazers_count": 10, "archived": False,
            "pushed_at": "2026-11-01T10:00:00Z"})


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setenv("NOTION_READONLY_TOKEN", "fake-notion-readonly")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    return tmp_path / "catalogue.sqlite"


def test_page_url_validation():
    assert cat.source_id(PAGE_A) == ID_A
    assert cat.source_id("1cab36ca-5523-8002-92ca-d5f59ab1fc0c") == ID_A
    with pytest.raises(cat.CatalogueError):
        cat.source_id("https://evil.example/p/1cab36ca5523800292cad5f59ab1fc0c")
    with pytest.raises(cat.CatalogueError):
        cat.source_id("http://app.notion.com/p/1cab36ca5523800292cad5f59ab1fc0c")


def test_pagination_no_writes_multi_sources_and_duplicates(local):
    a = [bookmark(f"https://github.com/Demo/repo-{i}", i + 1) for i in range(101)]
    a += [bookmark("https://github.com/Demo/repo-1/tree/main", 150),
          bookmark("https://github.com/topics/python", 151),
          text_block("https://github.com/Demo/extra", 152)]
    b = [bookmark("https://github.com/Demo/extra", 200),
         bookmark("https://github.com/Demo/new", 201)]
    fake = NotionFake({ID_A: a, ID_B: b})
    result = cat.inventory([PAGE_A, PAGE_B], session=fake, path=local)
    assert result["distinct_repos"] == 104
    assert len(fake.requests) == 3  # pagination de la première page, puis page B
    assert cat.state(local)["repos"] == 104
    assert cat.state(local)["enriched"] == 0
    assert local.exists()
    with sqlite3.connect(local) as con:
        assert con.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 105
        assert con.execute("SELECT COUNT(*) FROM repo_fts").fetchone()[0] == 104


def test_refused_notion_read_preserves_existing_index(local):
    first = NotionFake({ID_A: [bookmark("https://github.com/Demo/good")]})
    cat.inventory([PAGE_A], session=first, path=local)
    initial = local.read_bytes()
    denied = NotionFake({ID_A: []})
    denied.status = 403
    with pytest.raises(cat.CatalogueError, match="HTTP 403"):
        cat.inventory([PAGE_A], session=denied, path=local)
    assert local.read_bytes() == initial


def test_large_drop_guard_and_optional_explicit_override(local):
    source = [bookmark(f"https://github.com/Demo/repo-{i}", i+1) for i in range(30)]
    cat.inventory([PAGE_A], session=NotionFake({ID_A: source}), path=local)
    assert cat.state(local)["repos"] == 30
    with pytest.raises(cat.CatalogueError, match="Chute"):
        cat.inventory([PAGE_A], session=NotionFake({ID_A: source[:2]}), path=local)
    assert cat.state(local)["repos"] == 30
    cat.inventory([PAGE_A], allow_drop=True,
                  session=NotionFake({ID_A: source[:2]}), path=local)
    # Les métadonnées anciennes restent dans le cache, mais la recherche filtre les liens actifs.
    with sqlite3.connect(local) as con:
        assert con.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 2


def test_github_enrichment_and_french_search(local):
    fake_notion = NotionFake({ID_A: [
        bookmark("https://github.com/Demo/finance-watch"),
        bookmark("https://github.com/Demo/other-tool")]})
    cat.inventory([PAGE_A], session=fake_notion, path=local)
    before = cat.search("automatiser une veille financière", path=local)
    assert before["results"] == []  # Signets seuls sans contenu : pas d'invention
    fake = GitHubFake()
    outcome = cat.enrich(limit=2, session=fake, path=local)
    assert outcome["updated"] == 2
    assert len(fake.calls) == 4
    assert cat.state(local)["enriched"] == 2
    results = cat.search("automatiser une veille financière", path=local)
    assert results["results"]
    best = results["results"][0]
    assert best["repo"] in ("demo/finance-watch", "demo/other-tool")
    assert best["coverage"] >= 2
    assert best["source_pages"]
    assert best["evidence"] == "GitHub actuel"
    assert best["github"].startswith("https://github.com/demo/")
    next_call = cat.enrich(limit=2, session=fake, path=local)
    assert next_call["updated"] == 0
    assert len(fake.calls) == 4


def test_github_limit_keeps_preexisting_catalog(local):
    cat.inventory([PAGE_A], session=NotionFake({ID_A: [
        bookmark("https://github.com/Demo/repo-one")]}), path=local)
    snapshot = local.read_bytes()
    result = cat.enrich(limit=1, session=GitHubFake(rate_limited=True), path=local)
    assert "429" in result["stopped"]
    assert result["updated"] == 0
    assert local.read_bytes() == snapshot


def test_search_only_selected_sources(local):
    cat.inventory([PAGE_A, PAGE_B], session=NotionFake({
        ID_A: [bookmark("https://github.com/Demo/finance-one")],
        ID_B: [bookmark("https://github.com/Demo/finance-two")]}), path=local)
    a = cat.search("finance", only_sources=[PAGE_A], path=local)
    assert [x["repo"] for x in a["results"]] == ["demo/finance-one"]
    b = cat.search("finance", only_sources=[PAGE_B], path=local)
    assert [x["repo"] for x in b["results"]] == ["demo/finance-two"]
    with pytest.raises(cat.CatalogueError):
        cat.search("finance", only_sources=["https://app.notion.com/p/No-9cab36ca5523800292cad5f59ab1fc0c"],
                   path=local)


def test_no_readonly_token_stops_before_network(local, monkeypatch):
    monkeypatch.delenv("NOTION_READONLY_TOKEN", raising=False)
    class BlockedSession:
        def get(self, *a, **kw):
            raise AssertionError("No network request without token")
    with pytest.raises(cat.CatalogueError, match="NOTION_READONLY_TOKEN"):
        cat.inventory([PAGE_A], session=BlockedSession(), path=local)
