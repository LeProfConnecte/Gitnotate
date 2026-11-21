#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gitnotate V3-C : interface Web uniquement locale pour le catalogue des signets.

Aucune lecture ou ecriture Notion au demarrage. L'interface s'appuie sur
catalogue_v3.py et sur son index isole, sans toucher aux 443 fiches historiques.
"""
from __future__ import annotations

import os
import re
import secrets
import threading
import time
import webbrowser
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware


# Evite les erreurs recurrentes lorsque PowerShell s'ouvre dans C:\Users\Fabrice.
# Un dossier utilisateur explicite a toujours priorite.
if not os.environ.get("GITNOTATE_DATA_DIR"):
    default_data = Path.home() / "gitnotate-validation"
    if (default_data / ".env").is_file() or (
            default_data / ".gitnotate_catalogue" / "catalogue.sqlite").is_file():
        os.environ["GITNOTATE_DATA_DIR"] = str(default_data)

import catalogue_v3 as catalogue  # noqa: E402 - variable d'environnement initialisee avant import
import avis_v3 as avis  # noqa: E402 - secrets lus uniquement dans le backend local


ASSETS = Path(__file__).resolve().parent / "web_v3"
WEB_HOST = "127.0.0.1"
WEB_PORT = 8765
_VALID_HOSTS = frozenset(("127.0.0.1", "localhost"))
_VALID_ORIGINS = frozenset((
    "http://127.0.0.1:8765", "http://localhost:8765",
))


class SourceRequest(BaseModel):
    url: str = Field(min_length=15, max_length=2048)


class EnrichRequest(BaseModel):
    repos: list[str] = Field(min_length=1, max_length=5)


class AIPreviewRequest(BaseModel):
    need: str = Field(min_length=5, max_length=400)
    repos: list[str] = Field(min_length=1, max_length=5)
    provider: Literal["mistral", "openrouter", "openai", "anthropic"]


class AIConsentRequest(BaseModel):
    preview_id: str = Field(min_length=20, max_length=120)
    consent: bool


def create_app(path: Optional[Path] = None, csrf_token: Optional[str] = None) -> FastAPI:
    """Fabrique testable : aucune requete reseau avant une action explicite."""
    app = FastAPI(
        title="Gitnotate V3 — local uniquement",
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(_VALID_HOSTS))
    app.state.catalogue_path = path if path is not None else catalogue.DB_PATH
    app.state.csrf_token = csrf_token or secrets.token_urlsafe(32)
    app.state.ai_previews = {}
    app.state.ai_lock = threading.Lock()
    app.state.ai_busy = False
    app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") not in _VALID_ORIGINS:
                return JSONResponse({"detail": "Origine non autorisee"}, status_code=403)
            if not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), app.state.csrf_token
            ):
                return JSONResponse({"detail": "Confirmation de session manquante"},
                                    status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
            "script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "form-action 'self'"
        )
        return response

    @app.get("/")
    def home():
        return FileResponse(ASSETS / "index.html", media_type="text/html")

    @app.get("/api/session")
    def session():
        # Token anti-CSRF : pas une cle API, jamais partage avec les fournisseurs.
        return {"csrf": app.state.csrf_token, "backend": "local",
                "notion_writes": False, "llm_calls": False}

    @app.get("/api/state")
    def state():
        if not app.state.catalogue_path.exists():
            return {"missing": True, "sources": [], "repos": 0, "enriched": 0,
                    "already_in_historical": 0, "not_in_historical": 0,
                    "comparison_available": False}
        try:
            return catalogue.state(app.state.catalogue_path)
        except (catalogue.CatalogueError, OSError, ValueError) as exc:
            raise HTTPException(503, detail=str(exc)) from None

    @app.get("/api/search")
    def search(q: str = Query(min_length=2, max_length=400),
               limit: int = Query(20, ge=1, le=50),
               source: Optional[list[str]] = Query(None)):
        try:
            return catalogue.search(q, limit=limit, only_sources=source or [],
                                    path=app.state.catalogue_path)
        except catalogue.CatalogueError as exc:
            raise HTTPException(400, detail=str(exc)) from None
        except OSError:
            raise HTTPException(503, detail="Catalogue local indisponible") from None

    @app.post("/api/source")
    def add_source(data: SourceRequest):
        try:
            catalogue.source_id(data.url)
            return catalogue.inventory([data.url], path=app.state.catalogue_path)
        except catalogue.CatalogueError as exc:
            raise HTTPException(400, detail=str(exc)) from None

    @app.post("/api/sources/refresh")
    def refresh_sources():
        try:
            return catalogue.inventory([], path=app.state.catalogue_path)
        except catalogue.CatalogueError as exc:
            raise HTTPException(400, detail=str(exc)) from None

    @app.post("/api/enrich")
    def enrich_selected(data: EnrichRequest):
        # Uniquement 1 a 5 depots selectionnes et deja indexes. Le module catalogue
        # refuse ceux non presents dans les signets; aucun LLM ni ecriture Notion.
        keys = list(dict.fromkeys(data.repos))
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", key)
               for key in keys):
            raise HTTPException(400, detail="Identifiant de depot invalide")
        try:
            return catalogue.enrich(
                limit=len(keys), selected_repos=keys,
                path=app.state.catalogue_path)
        except catalogue.CatalogueError as exc:
            raise HTTPException(400, detail=str(exc)) from None

    @app.get("/api/ai/providers")
    def ai_providers():
        return {"providers": avis.providers(), "explicit_consent_required": True,
                "server_stores_keys": False, "notion_writes": False}

    @app.post("/api/ai/preview")
    def ai_preview(data: AIPreviewRequest):
        """Prépare le texte exact sans appeler l'API du fournisseur."""
        try:
            preview = avis.make_preview(
                app.state.catalogue_path, data.need, data.repos, data.provider)
        except avis.AvisError as exc:
            raise HTTPException(400, detail=str(exc)) from None
        preview_id = secrets.token_urlsafe(32)
        now = time.monotonic()
        with app.state.ai_lock:
            # Petit registre borné en RAM : rien de sensible n'est persisté.
            live = {key: value for key, value in app.state.ai_previews.items()
                    if value["expires"] > now}
            if len(live) >= 8:
                live.pop(next(iter(live)))
            live[preview_id] = {"preview": preview, "expires": now + 300}
            app.state.ai_previews = live
        return {"preview_id": preview_id, "expires_in_seconds": 300,
                "provider": preview["provider"], "repos": preview["repos"],
                "messages": preview["messages"], "characters": preview["characters"],
                "required_constraints": preview["required_constraints"],
                "constraint_labels": preview["constraint_labels"],
                "fields": preview["fields"], "disclosure": preview["disclosure"]}

    @app.post("/api/ai/evaluate")
    def ai_evaluate(data: AIConsentRequest):
        """Un consentement et un aperçu encore valable pour un unique appel IA."""
        if data.consent is not True:
            raise HTTPException(403, detail="Consentement explicite requis.")
        with app.state.ai_lock:
            if app.state.ai_busy:
                raise HTTPException(409, detail="Une évaluation IA est déjà en cours.")
            record = app.state.ai_previews.pop(data.preview_id, None)
            if record is None or record["expires"] <= time.monotonic():
                raise HTTPException(410, detail="Aperçu absent ou expiré : préparez un nouvel aperçu.")
            app.state.ai_busy = True
        try:
            return avis.evaluate(record["preview"])
        except avis.AvisError as exc:
            raise HTTPException(502, detail=str(exc)) from None
        finally:
            with app.state.ai_lock:
                app.state.ai_busy = False

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    print("Gitnotate V3 — Interface Web locale")
    print("URL: http://127.0.0.1:8765")
    print("Dossier donnees:", catalogue.gn.BASE_DIR)
    print("Notion : lecture seule uniquement ; aucune analyse IA automatique.")
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT, log_level="warning")
