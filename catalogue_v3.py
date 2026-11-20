#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Catalogue V3 expérimental : signets Notion -> GitHub -> SQLite FTS5.

Ce programme ne modifie jamais Notion, la base de fiches, ni l'index de redécouverte.
Trois commandes indépendantes : inventaire (GET Notion), enrichir (GET GitHub),
cherche (hors ligne). Les écritures locales utilisent une copie temporaire atomique.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import re
import sqlite3
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
import gitnotate as gn

VERSION = "0.1.0"
NOTION_API = "https://api.notion.com"
GITHUB_API = "https://api.github.com"
NOTION_VERSION = "2022-06-28"
MAX_BLOCKS = 30000
MAX_DEPTH = 30
README_LIMIT = 12000
CATALOG_DIR = Path(gn.BASE_DIR) / ".gitnotate_catalogue"
DB_PATH = CATALOG_DIR / "catalogue.sqlite"
ID_RE = re.compile(r"^[0-9a-f]{32}$", re.I)
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
STOP = frozenset(("je", "cherche", "un", "une", "des", "les", "le", "la", "de", "du", "d", "en",
                  "pour", "avec", "sur", "et", "ou", "qui", "dans", "est", "ce", "me", "mon",
                  "mes", "outil", "outils", "open", "source", "the", "that", "with", "for",
                  "and", "to", "from", "systeme", "application"))
SYNONYMS = {
    "automatiser": ("automation", "automate", "automated", "workflow"),
    "automatisation": ("automation", "automated", "workflow"),
    "veille": ("monitoring", "watch", "tracking", "news", "research"),
    "financiere": ("finance", "financial", "invest", "investment", "trading", "stocks"),
    "financier": ("finance", "financial", "investment", "trading"),
    "boursieres": ("stocks", "trading", "market", "finance"),
    "boursiere": ("stocks", "trading", "market"),
    "analyser": ("analysis", "analytics", "analyze"),
    "analyse": ("analysis", "analytics", "analyze"),
    "donnees": ("data", "dataset", "datasets"),
    "pdf": ("document", "documents", "ocr"),
    "extraire": ("extract", "extraction", "parsing"),
}
TABLES = """
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    label TEXT NOT NULL,
    scanned_at TEXT NOT NULL,
    links_total INTEGER NOT NULL,
    excluded INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    source_id TEXT NOT NULL,
    repo_key TEXT NOT NULL,
    original_url TEXT NOT NULL,
    PRIMARY KEY(source_id, repo_key),
    FOREIGN KEY(source_id) REFERENCES sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_links_repo ON links(repo_key);
CREATE TABLE IF NOT EXISTS repos (
    repo_key TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    topics TEXT NOT NULL DEFAULT '',
    readme TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    stars INTEGER,
    archived INTEGER NOT NULL DEFAULT 0,
    pushed_at TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL DEFAULT '',
    fetch_status TEXT NOT NULL DEFAULT 'pending'
);
CREATE VIRTUAL TABLE IF NOT EXISTS repo_fts USING fts5(
    repo_key UNINDEXED, title, description, topics, readme,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


class CatalogueError(Exception):
    pass


class LimitReached(CatalogueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def source_id(value: str) -> str:
    raw = (value or "").strip()
    if ID_RE.fullmatch(raw):
        return raw.lower()
    if re.fullmatch(r"[0-9a-f-]{36}", raw, re.I):
        norm = raw.replace("-", "")
        if ID_RE.fullmatch(norm):
            return norm.lower()
    try:
        parts = urlsplit(raw)
    except ValueError:
        raise CatalogueError("URL Notion invalide") from None
    if parts.scheme != "https" or parts.hostname not in {
            "notion.so", "www.notion.so", "app.notion.com", "notion.com", "www.notion.com"}:
        raise CatalogueError("Seules les URL HTTPS de pages Notion sont acceptées")
    found = re.findall(r"[0-9a-f]{32}", parts.path, flags=re.I)
    if not found:
        raise CatalogueError("Identifiant de page Notion absent de l'URL")
    return found[-1].lower()


def display_name(value: str, identity: str) -> str:
    slug = urlsplit(value).path.strip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"[-_]?[0-9a-f]{32}$", "", slug, flags=re.I).replace("-", " ").strip()
    return slug[:90] if slug and slug != identity else "Page Notion " + identity[:8]


def clean_token(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", errors="ignore").decode("ascii").lower()


def read_blocks(session: requests.Session, identity: str, token: str) -> tuple[list[dict], int]:
    """GET strict : traverse les blocs de contenu, pas les sous-pages et bases enfant."""
    if not token:
        raise CatalogueError("NOTION_READONLY_TOKEN absent du fichier de configuration privé")
    headers = {"Authorization": "Bearer " + token, "Notion-Version": NOTION_VERSION,
               "Accept": "application/json"}
    all_blocks: list[dict] = []
    skipped_containers = 0
    stack = [(identity, 0)]
    visited: set[str] = set()
    while stack:
        block_id, depth = stack.pop()
        if block_id in visited:
            continue
        visited.add(block_id)
        if depth >= MAX_DEPTH:
            raise CatalogueError("Profondeur maximale Notion dépassée ; ancien catalogue conservé")
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            url = NOTION_API + "/v1/blocks/" + block_id + "/children"
            try:
                response = session.get(url, headers=headers, params=params, timeout=20)
            except requests.RequestException:
                raise CatalogueError("Lecture Notion interrompue (réseau) ; ancien catalogue conservé") from None
            if response.status_code != 200:
                raise CatalogueError(
                    "Lecture Notion refusée (HTTP %s, bloc %s...) ; ancien catalogue conservé"
                    % (response.status_code, block_id[:8]))
            try:
                payload = response.json()
            except ValueError:
                raise CatalogueError("Réponse JSON Notion invalide ; ancien catalogue conservé") from None
            page_blocks = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(page_blocks, list):
                raise CatalogueError("Liste de blocs Notion absente ; ancien catalogue conservé")
            for block in page_blocks:
                if not isinstance(block, dict):
                    raise CatalogueError("Bloc Notion incorrect ; ancien catalogue conservé")
                all_blocks.append(block)
                if len(all_blocks) > MAX_BLOCKS:
                    raise CatalogueError("Trop de blocs Notion ; ancien catalogue conservé")
                typ = block.get("type", "")
                if block.get("has_children"):
                    if typ in ("child_page", "child_database"):
                        skipped_containers += 1
                    else:
                        child = block.get("id")
                        if not isinstance(child, str) or not ID_RE.fullmatch(child.replace("-", "")):
                            raise CatalogueError("Sous-bloc Notion sans identifiant valide")
                        stack.append((child.replace("-", "").lower(), depth + 1))
            if not payload.get("has_more"):
                break
            nxt = payload.get("next_cursor")
            if not isinstance(nxt, str) or not nxt or nxt in seen_cursors:
                raise CatalogueError("Pagination Notion invalide ; ancien catalogue conservé")
            seen_cursors.add(nxt)
            cursor = nxt
    return all_blocks, skipped_containers


def normalise_bookmarks(blocks: list[dict]) -> tuple[dict[str, dict], int, int]:
    raw_urls = gn.extract_urls_from_blocks(blocks)
    found: dict[str, dict] = {}
    ignored = 0
    for url in raw_urls:
        info, status = gn.parse_github_url(url)
        if status != "ok" or info is None:
            ignored += 1
            continue
        key = gn.normalize_github_url(url)
        found.setdefault(key, {"owner": info["owner"], "repo": info["repo"], "url": url})
    return found, len(raw_urls), ignored


def open_db(path: Path = DB_PATH, readonly: bool = False) -> sqlite3.Connection:
    if readonly and not path.is_file():
        raise CatalogueError("Catalogue V3 absent : lancez d'abord inventaire")
    if readonly:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
        connection.executescript(TABLES)
    connection.row_factory = sqlite3.Row
    return connection


@contextlib.contextmanager
def staged_db(path: Path = DB_PATH):
    """Snapshot puis remplacement atomique. Jamais d'écriture sur l'index historique."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, scratch = tempfile.mkstemp(prefix=".catalogue-", suffix=".sqlite", dir=path.parent)
    os.close(descriptor)
    temporary = Path(scratch)
    source = None
    connection = None
    try:
        if path.exists():
            source = open_db(path, readonly=True)
            connection = sqlite3.connect(temporary)
            source.backup(connection)
            source.close()
            source = None
            connection.close()
            connection = None
        connection = open_db(temporary)
        yield connection
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise CatalogueError("Contrôle intégrité SQLite échoué")
        connection.close()
        connection = None
        os.replace(temporary, path)
    finally:
        if connection is not None:
            connection.close()
        if source is not None:
            source.close()
        temporary.unlink(missing_ok=True)


def reindex(con: sqlite3.Connection, key: str) -> None:
    repo = con.execute("SELECT * FROM repos WHERE repo_key=?", (key,)).fetchone()
    if not repo:
        return
    con.execute("DELETE FROM repo_fts WHERE repo_key=?", (key,))
    con.execute(
        "INSERT INTO repo_fts(repo_key,title,description,topics,readme) VALUES(?,?,?,?,?)",
        (key, key + " " + repo["repo_name"], repo["description"], repo["topics"], repo["readme"]))


def inventory(pages: list[str], allow_drop: bool = False,
              session: requests.Session | None = None, path: Path = DB_PATH) -> dict:
    session = session or requests.Session()
    token = gn._env_str("NOTION_READONLY_TOKEN")
    if not token:
        raise CatalogueError("NOTION_READONLY_TOKEN manquant ; aucune requête effectuée")
    if not pages:
        with contextlib.closing(open_db(path, readonly=True)) as con:
            pages = [row["url"] for row in con.execute("SELECT url FROM sources ORDER BY label")]
    if not pages:
        raise CatalogueError("Aucune page : passez --page URL_NOTION (répétable)")
    snapshots = []
    for page in dict.fromkeys(pages):
        identity = source_id(page)
        blocks, omitted = read_blocks(session, identity, token)
        repos, total, ignored = normalise_bookmarks(blocks)
        snapshots.append((identity, page, display_name(page, identity), repos, total, ignored, omitted))
    with staged_db(path) as con:
        now = utc_now()
        report = []
        for identity, url, label, entries, total, ignored, omitted in snapshots:
            previous = con.execute(
                "SELECT COUNT(*) FROM links WHERE source_id=?", (identity,)).fetchone()[0]
            if previous > 0 and len(entries) < previous and (
                    previous - len(entries) >= 10 and
                    (previous - len(entries)) / previous >= 0.10) and not allow_drop:
                raise CatalogueError(
                    f"Chute de {previous} à {len(entries)} dépôts pour {label} : "
                    "ancien catalogue conservé. Vérifiez la page avant --accepter-baisse.")
            con.execute(
                "INSERT OR REPLACE INTO sources(source_id,url,label,scanned_at,links_total,excluded) "
                "VALUES(?,?,?,?,?,?)", (identity, url, label, now, total, ignored))
            con.execute("DELETE FROM links WHERE source_id=?", (identity,))
            for key, info in entries.items():
                con.execute("INSERT INTO links(source_id,repo_key,original_url) VALUES(?,?,?)",
                            (identity, key, info["url"]))
                cur = con.execute(
                    "INSERT OR IGNORE INTO repos(repo_key,owner,repo_name) VALUES(?,?,?)",
                    (key, info["owner"], info["repo"]))
                if cur.rowcount:
                    reindex(con, key)
            report.append({"source": label, "page": identity, "urls": total,
                           "unique_repos": len(entries), "non_repo": ignored,
                           "subpages_skipped": omitted})
        active = con.execute(
            "SELECT COUNT(DISTINCT repo_key) FROM links").fetchone()[0]
    return {"sources": report, "distinct_repos": active, "index": str(path)}


def github_get(session: requests.Session, url: str, token: str) -> dict | None:
    """GET GitHub sur hôte fixe seulement ; 404 est une absence, toute autre erreur bloque."""
    if not url.startswith(GITHUB_API + "/repos/"):
        raise CatalogueError("Hôte GitHub API non autorisé")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Gitnotate-V3/0.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        response = session.get(url, headers=headers, timeout=20)
    except requests.RequestException:
        raise CatalogueError("GitHub injoignable ; aucune suppression de données") from None
    if response.status_code == 404:
        return None
    if response.status_code in (403, 429):
        raise LimitReached("GitHub HTTP %s (quota ou accès) : batch interrompu, cache conservé"
                           % response.status_code)
    if response.status_code != 200:
        raise CatalogueError("GitHub HTTP %s : cache existant conservé" % response.status_code)
    try:
        obj = response.json()
    except ValueError:
        raise CatalogueError("Réponse JSON GitHub invalide") from None
    if not isinstance(obj, dict):
        raise CatalogueError("Réponse GitHub inattendue")
    return obj


def github_details(session: requests.Session, key: str, token: str) -> dict:
    info = gn.parse_github_url("https://github.com/" + key)[0]
    if not info:
        raise CatalogueError("Identifiant de dépôt invalide")
    route = GITHUB_API + "/repos/" + info["owner"] + "/" + info["repo"]
    metadata = github_get(session, route, token)
    if metadata is None:
        return {"status": "not_found"}
    readme_data = github_get(session, route + "/readme", token)
    readme = ""
    if readme_data:
        raw = readme_data.get("content", "")
        if readme_data.get("encoding") == "base64" and isinstance(raw, str):
            # Bornage avant décodage, sans télécharger des README géants.
            if len(raw) <= 1500000:
                try:
                    readme = base64.b64decode(raw, validate=False).decode("utf-8", "replace")
                except (ValueError, UnicodeError):
                    readme = ""
    return {
        "status": "ok",
        "owner": str((metadata.get("owner") or {}).get("login") or info["owner"]),
        "name": str(metadata.get("name") or info["repo"]),
        "description": str(metadata.get("description") or "")[:2000],
        "topics": " ".join(x for x in (metadata.get("topics") or [])
                           if isinstance(x, str))[:3000],
        "readme": readme[:README_LIMIT],
        "language": str(metadata.get("language") or ""),
        "license": str((metadata.get("license") or {}).get("spdx_id") or ""),
        "stars": metadata.get("stargazers_count")
                 if isinstance(metadata.get("stargazers_count"), int) else None,
        "archived": int(bool(metadata.get("archived"))),
        "pushed_at": str(metadata.get("pushed_at") or ""),
    }


def enrich(limit: int = 20, cache_days: int = 14,
           session: requests.Session | None = None, path: Path = DB_PATH) -> dict:
    if not 1 <= limit <= 100 or not 0 <= cache_days <= 3650:
        raise CatalogueError("Limite (1–100) ou durée de cache (0–3650) invalide")
    session = session or requests.Session()
    token = gn._env_str("GITHUB_TOKEN")
    threshold = (datetime.now(timezone.utc) - timedelta(days=cache_days)).isoformat()
    with contextlib.closing(open_db(path, readonly=True)) as con:
        queue = [row["repo_key"] for row in con.execute(
            "SELECT r.repo_key FROM repos r WHERE EXISTS "
            "(SELECT 1 FROM links l WHERE l.repo_key = r.repo_key) "
            "AND (r.fetched_at = '' OR r.fetched_at < ?) "
            "ORDER BY CASE WHEN r.fetched_at='' THEN 0 ELSE 1 END, r.repo_key LIMIT ?",
            (threshold, limit))]
    updates = []
    errors: list[str] = []
    stopped = ""
    for key in queue:
        try:
            updates.append((key, github_details(session, key, token)))
        except LimitReached as exc:
            stopped = str(exc)
            break
        except CatalogueError as exc:
            errors.append(key + " : " + str(exc))
    if updates:
        with staged_db(path) as con:
            for key, item in updates:
                if item["status"] == "not_found":
                    con.execute("UPDATE repos SET fetch_status='not_found',fetched_at=? "
                                "WHERE repo_key=?", (utc_now(), key))
                    continue
                con.execute(
                    "UPDATE repos SET owner=?,repo_name=?,description=?,topics=?,readme=?,"
                    "language=?,license=?,stars=?,archived=?,pushed_at=?,fetched_at=?,fetch_status='ok' "
                    "WHERE repo_key=?",
                    (item["owner"], item["name"], item["description"], item["topics"], item["readme"],
                     item["language"], item["license"], item["stars"], item["archived"],
                     item["pushed_at"], utc_now(), key))
                reindex(con, key)
    return {"attempted": len(updates) + len(errors), "updated": len(updates),
            "errors": errors[:10], "stopped": stopped, "github_auth": bool(token)}


def words(value: str) -> list[str]:
    norm = clean_token(value)
    return [s for s in TOKEN_RE.findall(norm) if len(s) >= 3 and s not in STOP][:12]


def query_groups(phrase: str) -> list[list[str]]:
    groups = []
    for term in words(phrase):
        options = [term, *SYNONYMS.get(term, ())]
        group = [x for x in dict.fromkeys(options) if re.fullmatch(r"[a-z0-9]+", x)]
        if group:
            groups.append(group)
    return groups


def search(need: str, limit: int = 10, only_sources: list[str] | None = None,
           path: Path = DB_PATH) -> dict:
    if not 1 <= limit <= 50:
        raise CatalogueError("Nombre de résultats invalide (1–50)")
    groups = query_groups(need)
    if not groups:
        raise CatalogueError("Recherche vide : indiquez un besoin plus précis")
    expression = " OR ".join('"' + token + '"' for group in groups for token in group)
    filtered = [source_id(s) for s in only_sources] if only_sources else []
    with contextlib.closing(open_db(path, readonly=True)) as con:
        source_names = {row["source_id"]: row["label"] for row in
                        con.execute("SELECT source_id,label FROM sources")}
        if filtered and any(s not in source_names for s in filtered):
            raise CatalogueError("Une source demandée n'a pas été inventoriée")
        sql = (
            "SELECT r.*,bm25(repo_fts,0,7,4,3,1) AS rank "
            "FROM repo_fts JOIN repos r ON r.repo_key=repo_fts.repo_key "
            "WHERE repo_fts MATCH ? AND EXISTS "
            "(SELECT 1 FROM links l WHERE l.repo_key=r.repo_key")
        values: list[Any] = [expression]
        if filtered:
            sql += " AND l.source_id IN (" + ",".join("?" for _ in filtered) + ")"
            values.extend(filtered)
        sql += ") ORDER BY rank ASC LIMIT 500"
        results = con.execute(sql, values).fetchall()
        candidates = []
        for repo in results:
            docs = clean_token(" ".join(
                (repo["repo_key"], repo["repo_name"], repo["description"], repo["topics"], repo["readme"])))
            covered = [group[0] for group in groups if any(
                re.search(r"\b" + re.escape(w) + r"\b", docs) for w in group)]
            refs = list(con.execute("SELECT source_id FROM links WHERE repo_key=?", (repo["repo_key"],)))
            source_labels = [source_names[x["source_id"]] for x in refs if (
                not filtered or x["source_id"] in filtered)]
            if not source_labels:
                continue
            candidates.append({
                "repo": repo["repo_key"],
                "github": "https://github.com/" + repo["repo_key"],
                "description": repo["description"],
                "coverage": len(covered),
                "total_concepts": len(groups),
                "concepts": covered,
                "source_pages": source_labels,
                "evidence": "GitHub actuel" if repo["fetch_status"] == "ok"
                            else "Signet seul — non enrichi",
                "checked_at": repo["fetched_at"] or None,
                "language": repo["language"],
                "license": repo["license"],
                "stars": repo["stars"],
                "archived": bool(repo["archived"]),
                "_rank": float(repo["rank"]),
            })
    candidates.sort(key=lambda c: (-c["coverage"], c["_rank"], c["repo"]))
    for result in candidates:
        del result["_rank"]
    return {"need": need, "concepts": [g[0] for g in groups],
            "results": candidates[:limit],
            "notice": "Classement lexical exploratoire ; vérifiez les fiches et README GitHub."}


def state(path: Path = DB_PATH) -> dict:
    with contextlib.closing(open_db(path, readonly=True)) as con:
        sources = [dict(row) for row in con.execute(
            "SELECT source_id,url,label,scanned_at,links_total,excluded "
            "FROM sources ORDER BY label")]
        counts = con.execute(
            "SELECT COUNT(*) AS repos, "
            "SUM(CASE WHEN fetch_status='ok' THEN 1 ELSE 0 END) AS enriched "
            "FROM repos WHERE repo_key IN (SELECT repo_key FROM links)").fetchone()
        return {"sources": sources, "repos": counts["repos"],
                "enriched": counts["enriched"] or 0, "index": str(path)}


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gitnotate V3 — signets Notion avant fiches historiques")
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventaire", help="GET Notion, sans import ni LLM")
    inv.add_argument("--page", action="append", default=[],
                     help="URL d'une page de signets (répétable). Sans option : sources déjà enregistrées.")
    inv.add_argument("--accepter-baisse", action="store_true",
                     help="Autoriser explicitement une baisse importante du nombre de signets")
    en = sub.add_parser("enrichir", help="GET GitHub, cache local, aucun LLM")
    en.add_argument("--limite", type=int, default=20)
    en.add_argument("--jours-cache", type=int, default=14)
    se = sub.add_parser("cherche", help="SQLite FTS5 local")
    se.add_argument("besoin")
    se.add_argument("-n", type=int, default=10)
    se.add_argument("--source", action="append", default=[],
                    help="N'afficher que cette page Notion (répétable)")
    sub.add_parser("etat", help="État du catalogue local")
    args = parser.parse_args(argv)
    try:
        if args.command == "inventaire":
            result = inventory(args.page, args.accepter_baisse)
        elif args.command == "enrichir":
            result = enrich(args.limite, args.jours_cache)
        elif args.command == "cherche":
            result = search(args.besoin, args.n, args.source)
        else:
            result = state()
    except (CatalogueError, sqlite3.Error, OSError) as exc:
        print("STOP : " + str(exc))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
