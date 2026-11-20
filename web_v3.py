#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gitnotate V3-C : interface web LOCALE, sans import Notion ni génération IA.

Le catalogue des signets est le moteur unique de recherche de cette V3 pilote.
Les fiches historiques sont consultées exclusivement en lecture via catalogue_v3.
"""
from __future__ import annotations

import contextlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

import catalogue_v3 as catalogue
import gitnotate as gn

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "web_v3_assets"
ENV_PATH = Path(gn.BASE_DIR) / ".env"
CSRF_TOKEN = secrets.token_urlsafe(32)
MUTATION_LOCK = threading.Lock()
PROVIDERS = {
    "mistral": ("Mistral AI", "MISTRAL_API_KEY", "MISTRAL_MODEL", "mistral-small-2603"),
    "openrouter": ("OpenRouter", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "openrouter/free"),
    "openai": ("OpenAI", "OPENAI_API_KEY", "OPENAI_MODEL", "gpt-6-luna"),
    "anthropic": ("Anthropic", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "claude-sonnet-4-6"),
}
ENV_NAME = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")
MODEL_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/+-]{0,127}$")

app = FastAPI(title="Gitnotate V3", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"], www_redirect=False)
app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")


@app.middleware("http")
async def local_security(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "POST"):
        return JSONResponse({"detail": "Méthode interdite"}, status_code=405)
    if request.method == "POST":
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if origin is not None and origin != "http://" + host:
            return JSONResponse({"detail": "Origine interdite"}, status_code=403)
        if not hmac.compare_digest(request.headers.get("x-gitnotate-csrf", ""), CSRF_TOKEN):
            return JSONResponse({"detail": "Jeton de session invalide"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'")
    return response


def api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, catalogue.CatalogueError):
        return HTTPException(400, str(exc))
    return HTTPException(500, "Erreur locale ; consulter le terminal de lancement")


@contextlib.contextmanager
def exclusive_operation():
    if not MUTATION_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Une opération est déjà en cours")
    try:
        yield
    finally:
        MUTATION_LOCK.release()


class SearchBody(BaseModel):
    besoin: str = Field(min_length=2, max_length=1000)
    nombre: int = Field(default=10, ge=1, le=30)
    sources: list[str] = Field(default_factory=list, max_length=25)


class SourceBody(BaseModel):
    url: str = Field(min_length=20, max_length=500)


class EnrichBody(BaseModel):
    limite: int = Field(default=10, ge=1, le=20)


class ProviderBody(BaseModel):
    fournisseur: str
    modele: str
    cle: str = ""
    principal: bool = False


def load_env_values() -> dict[str, str]:
    values = dotenv_values(ENV_PATH) if ENV_PATH.is_file() else {}
    return {key: str(value or "") for key, value in values.items()}


def save_env_values(updates: dict[str, str]) -> None:
    """Écriture atomique, lignes non concernées inchangées, sans backup de secrets."""
    if any(key not in {"LLM_PROVIDERS", "GITHUB_TOKEN", *(v[1] for v in PROVIDERS.values()),
                       *(v[2] for v in PROVIDERS.values())} for key in updates):
        raise ValueError("Variable non autorisée")
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    original = ENV_PATH.read_text(encoding="utf-8-sig") if ENV_PATH.is_file() else ""
    lines = original.splitlines(keepends=True)
    remaining = dict(updates)
    new_lines: list[str] = []
    for line in lines:
        match = ENV_NAME.match(line)
        if match and match.group(1) in updates:
            name = match.group(1)
            if name in remaining:
                new_lines.append(name + "=" + json.dumps(updates[name], ensure_ascii=False) + "\n")
                remaining.pop(name)
            # Un ancien doublon de la même clé n'est pas conservé.
        else:
            new_lines.append(line)
    if new_lines and not new_lines[-1].endswith(("\n", "\r")):
        new_lines.append("\n")
    for name, value in remaining.items():
        new_lines.append(name + "=" + json.dumps(value, ensure_ascii=False) + "\n")
    fd, tempname = tempfile.mkstemp(dir=ENV_PATH.parent, prefix=".env-v3-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.writelines(new_lines)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(tempname, 0o600)
        os.replace(tempname, ENV_PATH)
    finally:
        if os.path.exists(tempname):
            os.unlink(tempname)


@app.get("/")
def page():
    return FileResponse(ASSETS / "index.html", media_type="text/html")


@app.get("/api/bootstrap")
def bootstrap():
    return {"csrf": CSRF_TOKEN, "version": "3-C pilote", "mode": "local"}


@app.get("/api/etat")
def etat():
    try:
        return {"catalogue_present": True, **catalogue.state()}
    except catalogue.CatalogueError:
        return {"catalogue_present": False, "sources": [], "repos": 0,
                "enriched": 0, "comparison_available": False,
                "already_in_historical": None, "not_in_historical": None}


@app.post("/api/recherche")
def recherche(body: SearchBody):
    try:
        return catalogue.search(body.besoin.strip(), limit=body.nombre,
                                only_sources=body.sources or None)
    except (catalogue.CatalogueError, ValueError) as exc:
        raise api_error(exc) from None


@app.post("/api/sources/ajouter")
def ajouter_source(body: SourceBody):
    raw = body.url.strip()
    if not raw.startswith("https://"):
        raise HTTPException(400, "Collez une URL HTTPS d'une page Notion")
    try:
        catalogue.source_id(raw)
        with exclusive_operation():
            return catalogue.inventory([raw])
    except (catalogue.CatalogueError, ValueError) as exc:
        raise api_error(exc) from None


@app.post("/api/sources/actualiser")
def actualiser():
    try:
        with exclusive_operation():
            return catalogue.inventory([])
    except (catalogue.CatalogueError, ValueError) as exc:
        raise api_error(exc) from None


@app.post("/api/depot/enrichir")
def enrichir(body: EnrichBody):
    try:
        with exclusive_operation():
            # Le token Github modifié dans l'interface est chargé pour ce seul lot.
            # Aucune modification permanente des variables d'environnement du serveur.
            previous = os.environ.get("GITHUB_TOKEN")
            configured = load_env_values().get("GITHUB_TOKEN", "")
            try:
                if configured:
                    os.environ["GITHUB_TOKEN"] = configured
                else:
                    os.environ.pop("GITHUB_TOKEN", None)
                return catalogue.enrich(limit=body.limite)
            finally:
                if previous is None:
                    os.environ.pop("GITHUB_TOKEN", None)
                else:
                    os.environ["GITHUB_TOKEN"] = previous
    except (catalogue.CatalogueError, ValueError) as exc:
        raise api_error(exc) from None


class GithubKeyBody(BaseModel):
    cle: str = Field(min_length=8, max_length=1024)


@app.get("/api/github")
def github_status():
    return {"cle_presente": bool(load_env_values().get("GITHUB_TOKEN"))}


@app.post("/api/github/enregistrer")
def github_key(body: GithubKeyBody):
    key = body.cle.strip()
    if any(x.isspace() or ord(x) < 32 for x in key):
        raise HTTPException(400, "Jeton GitHub invalide")
    try:
        with exclusive_operation():
            save_env_values({"GITHUB_TOKEN": key})
    except OSError:
        raise HTTPException(500, "Impossible d'enregistrer le jeton GitHub privé") from None
    return {"ok": True, "cle_presente": True}


@app.get("/api/fournisseurs")
def fournisseurs():
    config = load_env_values()
    configured = [s.strip() for s in config.get("LLM_PROVIDERS", "mistral,openrouter").split(",")]
    result = []
    for key, (label, secret_key, model_key, default_model) in PROVIDERS.items():
        result.append({"id": key, "nom": label, "modele": config.get(model_key) or default_model,
                       "cle_presente": bool(config.get(secret_key)), "principal": configured[:1] == [key],
                       "actif": key in configured})
    return {"providers": result, "ordre": configured}


@app.post("/api/fournisseurs/enregistrer")
def enregistrer_fournisseur(body: ProviderBody):
    if body.fournisseur not in PROVIDERS:
        raise HTTPException(400, "Fournisseur inconnu")
    model = body.modele.strip()
    key = body.cle.strip()
    if not MODEL_ID.fullmatch(model):
        raise HTTPException(400, "Identifiant de modèle invalide")
    if len(key) > 1024 or any(x.isspace() or ord(x) < 32 for x in key):
        raise HTTPException(400, "Clé API invalide")
    label, secret_key, model_key, _ = PROVIDERS[body.fournisseur]
    try:
        with exclusive_operation():
            current = load_env_values()
            existing = bool(current.get(secret_key))
            if body.principal and not (key or existing):
                raise HTTPException(400, "Enregistrez une clé API avant de définir ce fournisseur principal")
            updates = {model_key: model}
            if key:
                updates[secret_key] = key
            if body.principal:
                previous = [v.strip() for v in
                            current.get("LLM_PROVIDERS", "mistral,openrouter").split(",")]
                others = [p for p in previous if p in PROVIDERS and p != body.fournisseur]
                updates["LLM_PROVIDERS"] = ",".join([body.fournisseur] + list(dict.fromkeys(others)))
            save_env_values(updates)
    except OSError as exc:
        raise HTTPException(500, "Impossible d'enregistrer le fichier privé .env") from None
    return {"ok": True, "fournisseur": label, "cle_presente": bool(key or existing),
            "note": "L'ordre des fournisseurs s'appliquera au prochain appel CLI."}


@app.post("/api/fournisseurs/verifier")
def verifier_fournisseurs():
    """GET /models seulement, aucun appel de génération ni envoi vers Notion."""
    with exclusive_operation():
        env = os.environ.copy()
        env["GITNOTATE_DATA_DIR"] = str(gn.BASE_DIR)
        env.pop("GITNOTATE_NO_DOTENV", None)
        try:
            process = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_llm.py")],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, "Vérification trop longue") from None
    output = (process.stdout + "\n" + process.stderr)[:12000]
    for name, val in load_env_values().items():
        if name.endswith("_API_KEY") and len(val) > 8:
            output = output.replace(val, "[clé masquée]")
    return {"ok": process.returncode == 0, "diagnostic": output}
