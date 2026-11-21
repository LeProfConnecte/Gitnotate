#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Réglages des fournisseurs IA pour l'interface web strictement locale.

Contrat de sécurité :
- seules les huit variables API_KEY / MODEL connues sont modifiables ;
- jamais de clé renvoyée dans une réponse ; aucune sauvegarde des clés côté JS ;
- aucune lecture automatique du réseau, uniquement un test GET explicite ;
- modification atomique du .env privé, conservation des lignes Notion/autres ;
- aucune modification des paramètres chargés par gitnotate avant redémarrage.
"""
from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values

import gitnotate as gn

PROVIDERS = ("mistral", "openrouter", "openai", "anthropic")
KEY_NAMES = {p: p.upper() + "_API_KEY" for p in PROVIDERS}
MODEL_NAMES = {p: p.upper() + "_MODEL" for p in PROVIDERS}
DEFAULT_MODELS = {
    "mistral": gn.MISTRAL_MODEL_DEFAULT,
    "openrouter": gn.OPENROUTER_MODEL_DEFAULT,
    "openai": gn.OPENAI_MODEL_DEFAULT,
    "anthropic": gn.ANTHROPIC_MODEL_DEFAULT,
}
ENDPOINTS = {
    "mistral": "https://api.mistral.ai/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
}
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
_KEY_FORMAT = re.compile(r"^[A-Za-z0-9_.:/+=-]{10,4096}$")
_MODEL_FORMAT = re.compile(r"^[A-Za-z0-9_.:/+-]{2,160}$")
_ENV_ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
MAX_MODELS = 500
_TIMEOUT = 15


class SettingsError(Exception):
    """Erreur publique sans aucun secret, chemin de token ou corps de réponse distante."""


def _validate_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise SettingsError("Fournisseur inconnu.")


def validate_model(model: str) -> str:
    if not isinstance(model, str) or not _MODEL_FORMAT.fullmatch(model):
        raise SettingsError("Modèle invalide : utilise uniquement lettres, chiffres, / _ - . : +.")
    return model


def validate_secret(secret: str) -> str:
    if not isinstance(secret, str) or not _KEY_FORMAT.fullmatch(secret):
        raise SettingsError("Clé invalide : caractère interdit ou longueur hors limites.")
    return secret


def _check_path(path: Path) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise SettingsError("Le fichier ou dossier de configuration ne doit pas être un lien symbolique.")
    if path.exists() and not path.is_file():
        raise SettingsError("Le fichier de configuration n'est pas un fichier ordinaire.")


def _read(path: Path) -> dict[str, str]:
    _check_path(path)
    if not path.exists():
        return {}
    try:
        values = dotenv_values(path, interpolate=False)
    except (OSError, UnicodeError, ValueError):
        raise SettingsError("Impossible de lire le fichier privé .env.") from None
    return {k: v or "" for k, v in values.items() if isinstance(k, str)}


def status(path: Path) -> list[dict[str, Any]]:
    """Jamais de préfixe, suffixe ou longueur de clé dans l'API."""
    values = _read(path)
    return [
        {"id": p, "label": gn._PROVIDER_NAMES.get(p, p),
         "model": values.get(MODEL_NAMES[p]) or DEFAULT_MODELS[p],
         "key_configured": bool(values.get(KEY_NAMES[p])),
         "key_storage": "private_env_file"}
        for p in PROVIDERS
    ]


def _replace_vars(content: str, updates: dict[str, str]) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    visited: set[str] = set()
    for line in lines:
        match = _ENV_ASSIGN.match(line)
        name = match.group(1) if match else None
        if name in updates:
            if name in visited:
                raise SettingsError(
                    "Variable IA dupliquée dans .env : corrige-la manuellement avant de sauvegarder.")
            visited.add(name)
            ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            output.append(name + "=" + updates[name] + ending)
        else:
            output.append(line)
    if not output:
        result = ""
    else:
        result = "".join(output)
    for name, value in updates.items():
        if name not in visited:
            if result and not result.endswith(("\r", "\n")):
                result += newline
            result += name + "=" + value + newline
    return result


def save(path: Path, provider: str, model: str,
         secret: str | None = None, clear_key: bool = False) -> dict[str, Any]:
    """Modifie uniquement les variables du fournisseur demandé ; commit atomique."""
    _validate_provider(provider)
    model = validate_model(model)
    if clear_key and secret:
        raise SettingsError("Impossible de remplacer et d'effacer la clé simultanément.")
    if secret is not None and secret != "":
        secret = validate_secret(secret)
    else:
        secret = None

    values = _read(path)
    updates = {MODEL_NAMES[provider]: model}
    if clear_key:
        updates[KEY_NAMES[provider]] = ""
    elif secret is not None:
        updates[KEY_NAMES[provider]] = secret

    # Bloque les clés en double et les fichiers déjà illisibles avant écriture.
    try:
        original = path.read_bytes() if path.exists() else b""
        decoded = original.decode("utf-8-sig")
    except (OSError, UnicodeError):
        raise SettingsError("Impossible de lire .env sans perte de caractères.") from None
    new_text = _replace_vars(decoded, updates)
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    payload = bom + new_text.encode("utf-8")
    if payload == original:
        return {"saved": True, "restart_required": False,
                "provider": provider, "key_configured": bool(values.get(KEY_NAMES[provider]))}

    if not path.parent.is_dir():
        raise SettingsError("Le dossier de configuration privé est absent.")
    fd = -1
    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(
            dir=path.parent, prefix=".ai-settings-", suffix=".tmp")
        # POSIX: propriétaire uniquement ; Windows: ACL héritée du dossier utilisateur.
        old_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        if os.name != "nt":
            os.fchmod(fd, old_mode & 0o600 or 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError:
        raise SettingsError("Écriture atomique de .env impossible ; configuration précédente préservée.") from None
    finally:
        if fd >= 0:
            os.close(fd)
        if temp_name is not None:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass

    return {"saved": True, "restart_required": True,
            "provider": provider,
            "key_configured": False if clear_key else bool(secret or values.get(KEY_NAMES[provider]))}


def _headers(provider: str, api_key: str) -> dict[str, str]:
    if provider == "anthropic":
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01",
                "Accept": "application/json"}
    return {"Authorization": "Bearer " + api_key, "Accept": "application/json"}


def _remote_get(session: requests.Session, url: str, headers: dict[str, str]) -> Any:
    """Hôtes fixes uniquement ; aucune redirection avec un jeton API."""
    try:
        reply = session.get(url, headers=headers, timeout=_TIMEOUT, allow_redirects=False)
    except (requests.RequestException, OSError):
        raise SettingsError("Service indisponible ou requête expirée ; aucun modèle testé.") from None
    if reply.status_code in (301, 302, 303, 307, 308):
        raise SettingsError("Redirection inattendue refusée pour protéger la clé API.")
    if reply.status_code in (401, 403):
        raise SettingsError("Clé ou autorisation refusée par le fournisseur (HTTP %s)." %
                            reply.status_code)
    if reply.status_code == 429:
        raise SettingsError("Quota ou fréquence d'appels dépassé (HTTP 429).")
    if reply.status_code != 200:
        raise SettingsError("Réponse du fournisseur HTTP %s ; aucun modèle confirmé." %
                            reply.status_code)
    try:
        return reply.json()
    except (ValueError, TypeError):
        raise SettingsError("Réponse JSON du fournisseur invalide.") from None


def check_connection(path: Path, provider: str, model: str,
                     secret: str | None = None,
                     session: requests.Session | None = None) -> dict[str, Any]:
    """GET /models sur action explicite. AUCUNE génération de contenu."""
    _validate_provider(provider)
    model = validate_model(model)
    if secret:
        key = validate_secret(secret)
    else:
        key = _read(path).get(KEY_NAMES[provider], "")
        if not key:
            raise SettingsError("Aucune clé pour ce fournisseur ; enregistre-la d'abord.")
        validate_secret(key)
    session = session or requests.Session()
    headers = _headers(provider, key)
    if provider == "openrouter":
        # /models est public : il ne prouve PAS qu'une clé OpenRouter est valide.
        _remote_get(session, OPENROUTER_KEY_URL, headers)
    data = _remote_get(session, ENDPOINTS[provider], headers)
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SettingsError("Réponse du catalogue de modèles invalide.")
    seen: set[str] = set()
    for item in items:
        model_id = item.get("id") if isinstance(item, dict) else None
        if isinstance(model_id, str) and _MODEL_FORMAT.fullmatch(model_id):
            seen.add(model_id)
    known = model in seen
    # Alias documenté : routeur gratuit OpenRouter ; ne pas confondre avec un modèle fixe.
    alias = provider == "openrouter" and model == "openrouter/free"
    return {
        "provider": provider, "model": model, "key_accepted": True,
        "model_listed": known, "router_alias": alias,
        "model_check": ("alias" if alias else "listed" if known else "not_listed"),
        "available_models": sorted(seen)[:MAX_MODELS],
        "list_truncated": len(seen) > MAX_MODELS,
        "no_generation": True,
        "note": ("Connexion contrôlée sans génération. Une présence dans la liste "
                 "ne garantit pas les crédits, quotas ni une complétion future.")
    }
