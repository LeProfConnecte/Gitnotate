#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic des clés LLM de Gitnotate — sans consommer de quota de génération.

  • OpenRouter : GET https://openrouter.ai/api/v1/key
                 validité de la clé + quota gratuit du jour (used / limit / remaining)
  • Mistral    : GET https://api.mistral.ai/v1/models
                 validité de la clé + présence de MISTRAL_MODEL dans la liste

Les clés ne sont jamais affichées en clair (4 premiers et 4 derniers caractères au plus).
Le fichier .env est lu au même endroit que gitnotate.py (dossier du projet, ou GITNOTATE_DATA_DIR).

Codes de sortie : 0 = au moins une clé et toutes les clés présentes sont utilisables
                  1 = aucune clé, clé refusée, service injoignable ou modèle Mistral absent
Un quota gratuit OpenRouter épuisé est signalé mais ne fait pas échouer le diagnostic
(il est remis à zéro à minuit UTC).

Usage : python scripts/check_llm.py
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# Même dossier de données que gitnotate.py : GITNOTATE_DATA_DIR, sinon la racine du projet
BASE_DIR = Path(os.environ.get('GITNOTATE_DATA_DIR') or Path(__file__).resolve().parent.parent)

OPENROUTER_KEY_URL  = 'https://openrouter.ai/api/v1/key'
MISTRAL_MODELS_URL  = 'https://api.mistral.ai/v1/models'
DEFAULT_MISTRAL     = 'mistral-small-2603'
DEFAULT_OPENROUTER  = 'openrouter/free'
TIMEOUT             = 15


def load_env() -> None:
    """Charge BASE_DIR/.env, comme gitnotate.py : sauf si GITNOTATE_NO_DOTENV a une valeur « vraie »
    (vide, 0, false, no, non ou off n'empêchent pas la lecture)."""
    if os.environ.get('GITNOTATE_NO_DOTENV', '').strip().lower() not in ('', '0', 'false', 'no', 'non', 'off'):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(BASE_DIR / '.env')


def mask(secret: Optional[str]) -> str:
    """Jamais plus de 4 premiers et 4 derniers caractères ; clé courte → entièrement masquée."""
    secret = (secret or '').strip()
    if len(secret) < 12:
        return '****'
    return f"{secret[:4]}...{secret[-4:]}"


def _http_get(url: str, headers: Dict[str, str]) -> requests.Response:
    return requests.get(url, headers=headers, timeout=TIMEOUT)


def _json(response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _api_message(response, limit: int = 200) -> str:
    body = _json(response)
    err = body.get('error')
    msg: Any = body.get('message')
    if not isinstance(msg, str):
        msg = err.get('message') if isinstance(err, dict) else err
    if not isinstance(msg, str):
        msg = body.get('detail') if isinstance(body.get('detail'), str) else ''
    if not msg:
        try:
            msg = response.text or ''
        except Exception:
            msg = ''
    msg = ' '.join(msg.split())
    return msg[:limit] + ('…' if len(msg) > limit else '')


def _get(url: str, key: str) -> Tuple[Optional[requests.Response], str]:
    try:
        return _http_get(url, {'Authorization': f'Bearer {key}'}), ''
    except requests.exceptions.Timeout:
        return None, 'timeout'
    except requests.exceptions.ConnectionError:
        return None, 'connexion impossible'
    except requests.exceptions.RequestException as e:
        return None, type(e).__name__


def check_openrouter(key: str, model: str) -> Tuple[bool, List[str]]:
    lines = [f"OpenRouter — clé {mask(key)} — modèle {model}"]
    response, error = _get(OPENROUTER_KEY_URL, key)
    if response is None:
        return False, lines + [f"   ❌ injoignable ({error})"]
    if response.status_code == 401:
        return False, lines + [f"   ❌ clé invalide (HTTP 401 — {_api_message(response)})"]
    if response.status_code != 200:
        return False, lines + [f"   ❌ HTTP {response.status_code} — {_api_message(response)}"]

    data  = _json(response).get('data')
    data  = data if isinstance(data, dict) else {}
    quota = data.get('free_model_daily_requests')
    lines.append("   ✅ clé valide")
    if isinstance(quota, dict) and isinstance(quota.get('remaining'), int):
        remaining, limit, used = quota.get('remaining'), quota.get('limit', '?'), quota.get('used', '?')
        lines.append(f"   • quota gratuit : {remaining}/{limit} restantes ({used} utilisées), "
                     "remis à zéro à minuit UTC")
        if remaining <= 0:
            lines.append("   ⚠️  quota gratuit du jour épuisé : OpenRouter sera désactivé par gitnotate.py "
                         "jusqu'à minuit UTC")
    else:
        lines.append("   • quota gratuit : non communiqué")
    return True, lines


def check_mistral(key: str, model: str) -> Tuple[bool, List[str]]:
    lines = [f"Mistral AI — clé {mask(key)} — modèle {model}"]
    response, error = _get(MISTRAL_MODELS_URL, key)
    if response is None:
        return False, lines + [f"   ❌ injoignable ({error})"]
    if response.status_code == 401:
        return False, lines + [f"   ❌ clé invalide (HTTP 401 — {_api_message(response)})"]
    if response.status_code != 200:
        return False, lines + [f"   ❌ HTTP {response.status_code} — {_api_message(response)}"]

    lines.append("   ✅ clé valide")
    names = set()
    for item in _json(response).get('data') or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get('id'), str):
            names.add(item['id'])
        names.update(a for a in (item.get('aliases') or []) if isinstance(a, str))
    if model in names:
        lines.append(f"   ✅ modèle '{model}' disponible")
        return True, lines
    lines.append(f"   ❌ modèle '{model}' absent de la liste ({len(names)} modèles) — "
                 "corrigez MISTRAL_MODEL dans .env")
    return False, lines


def main() -> int:
    load_env()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError, OSError):
            pass

    openrouter_key = os.environ.get('OPENROUTER_API_KEY', '').strip()
    mistral_key    = os.environ.get('MISTRAL_API_KEY', '').strip()
    mistral_model  = os.environ.get('MISTRAL_MODEL', '').strip() or DEFAULT_MISTRAL
    openrouter_model = (os.environ.get('OPENROUTER_MODEL', '').strip()
                        or os.environ.get('TRANSLATION_MODEL', '').strip() or DEFAULT_OPENROUTER)

    print("🔐 Diagnostic des clés LLM (aucun quota de génération consommé)\n")
    if not openrouter_key and not mistral_key:
        print("❌ Aucune clé trouvée : renseignez MISTRAL_API_KEY et/ou OPENROUTER_API_KEY "
              f"dans {BASE_DIR / '.env'}")
        return 1

    all_ok = True
    for key, name, check, model in (
        (mistral_key, 'MISTRAL_API_KEY', check_mistral, mistral_model),
        (openrouter_key, 'OPENROUTER_API_KEY', check_openrouter, openrouter_model),
    ):
        if not key:
            print(f"ℹ️  {name} absente : fournisseur ignoré\n")
            continue
        ok, lines = check(key, model)
        all_ok = all_ok and ok
        print('\n'.join(lines) + '\n')

    print("✅ Diagnostic terminé : clés utilisables" if all_ok
          else "❌ Diagnostic terminé : au moins un problème à corriger")
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
