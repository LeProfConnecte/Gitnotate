#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitNotate v7.1 - LLM FULL-CONTEXT SCORING EDITION

Nouveautés v7.1:
  ✅ README inclus dans le contexte LLM (README_LLM_CHARS, défaut 1500)
  ✅ Reasoning Notion enrichi : 40 mots max (était 20) → 800 chars stockés
  ✅ max_tokens API augmenté à 1200 (README dans le prompt)
  ✅ README_LLM_CHARS configurable via .env (0 = désactivé)
  ✅ Coût = 0 (mistral-small-2503 gratuit au 08/03/2026)

Héritage v7.0:
  ✅ Scoring sémantique LLM dans le même appel que la traduction
  ✅ Prompt combiné dynamique depuis user_profile.json
  ✅ Colonne Justification dans Notion
  ✅ Fallback lexical automatique si LLM indisponible
  ✅ temperature=0.1 pour quasi-déterminisme du score

Héritage v6.9:
  ✅ Fallback Mistral AI si OpenRouter absent/invalide/429
  ✅ 429 → succès (clé valide, rate-limitée)
  ✅ Cascade automatique OpenRouter → Mistral par appel

Héritage v6.8:
  ✅ Cache JSON 24h — flush unique atexit
  ✅ Fetch metadata + README en parallèle
  ✅ ThreadSafeStats — UTC-aware timestamps
  ✅ Constantes nommées, _warn(), _mask_token()
"""

import requests
import time
import re
import os
import sys
import json
import base64
import atexit
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path
import threading

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# =============================================================================
# CONFIGURATION
# =============================================================================
NOTION_TOKEN       = os.environ.get('NOTION_TOKEN', '')
GITHUB_TOKEN       = os.environ.get('GITHUB_TOKEN', '')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
MISTRAL_API_KEY    = os.environ.get('MISTRAL_API_KEY', '')
DATABASE_ID        = os.environ.get('DATABASE_ID', '')

PARENT_PAGE_ID = os.environ.get('PARENT_PAGE_ID', '')
if not PARENT_PAGE_ID:
    raise SystemExit(
        "\n❌ ERREUR: PARENT_PAGE_ID non défini\n"
        "\nAjoutez dans votre fichier .env:\n"
        "PARENT_PAGE_ID=your_notion_page_id\n"
    )

MAX_WORKERS         = int(os.environ.get('MAX_WORKERS', '5'))
TRANSLATION_ENABLED = os.environ.get('TRANSLATION_ENABLED', 'true').lower() == 'true'
TRANSLATION_MODEL   = os.environ.get('TRANSLATION_MODEL', 'openai/gpt-oss-20b:free')
MISTRAL_MODEL       = os.environ.get('MISTRAL_MODEL', 'mistral-small-2503')
LLM_SCORING_ENABLED = os.environ.get('LLM_SCORING_ENABLED', 'true').lower() == 'true'
BACKOFF_FACTOR      = 2
GITHUB_SECONDARY_RATE_LIMIT_WAIT = 60

DRY_RUN         = os.environ.get('DRY_RUN', 'false').lower() == 'true'
MIN_UPDATE_DAYS = int(os.environ.get('MIN_UPDATE_DAYS', '0'))
CACHE_ENABLED   = os.environ.get('CACHE_ENABLED', 'true').lower() == 'true'

DEFAULT_TIMEOUT        = int(os.environ.get('HTTP_TIMEOUT', '60'))
MAX_RETRIES            = int(os.environ.get('MAX_RETRIES', '3'))
CACHE_TTL_SECONDS      = int(os.environ.get('CACHE_TTL_HOURS', '24')) * 3600
CACHE_STALE_SECONDS    = 7 * 24 * 3600
README_MAX_CHARS       = int(os.environ.get('README_MAX_CHARS', '2500'))
README_LLM_CHARS       = int(os.environ.get('README_LLM_CHARS', '1500'))  # 🆕 v7.1
NOTION_FIELD_MAX_CHARS = 2000
STATS_HISTORY_MAX      = 50
SCORE_MIN_THRESHOLD    = int(os.environ.get('SCORE_MIN_THRESHOLD', '0'))
LOG_LEVEL              = os.environ.get('LOG_LEVEL', 'normal')

TRANSLATION_PROVIDER: Optional[str] = None
TRANSLATION_FALLBACK: Optional[str] = None

# Prompt traduction seule (utilisé si LLM_SCORING_ENABLED=false)
SYSTEM_PROMPT_TRANSLATE = (
    "Tu es un traducteur technique expert. Traduis en français en conservant "
    "les termes techniques (API, framework, agent, LLM, ML, OCR, etc.). "
    "IMPORTANT: Réponds UNIQUEMENT avec un JSON valide au format "
    '{"description_fr": "traduction de la description", '
    '"use_cases_fr": "traduction des cas d\'usage avec puces • "} '
    "Aucun texte avant ou après le JSON."
)

# =============================================================================
# PROFIL UTILISATEUR
# =============================================================================
USER_PROFILE_DEFAULT = {
    'languages': ['Python', 'JavaScript', 'TypeScript', 'Node.js'],
    'frameworks': ['Next.js', 'React', 'Vue.js', 'FastAPI', 'Django', 'Express', 'Supabase'],
    'domains': [
        'education', 'web-dev', 'automation', 'ai', 'llm',
        'ocr', 'devops', 'data-analysis', 'finance', 'trading',
    ],
    'interests': [
        'teaching-tools', 'document-processing', 'translation',
        'workflow-automation', 'n8n', 'make', 'no-code',
        'video-generation', 'prompt-engineering', 'api-integration',
    ],
    'infra': [
        'Docker', 'Nginx', 'PostgreSQL', 'Redis',
        'VPS', 'CloudPanel', 'Supabase', 'MongoDB',
    ],
}

# =============================================================================
# UTILITAIRES
# =============================================================================
_LOG_LEVELS = {'quiet': 0, 'normal': 1, 'verbose': 2}

def log(msg: str, level: str = 'normal') -> None:
    if _LOG_LEVELS.get(level, 1) <= _LOG_LEVELS.get(LOG_LEVEL, 1):
        print(msg)

def _warn(context: str, e: Exception) -> None:
    print(f"⚠️  [{context}] {type(e).__name__}: {e}", file=sys.stderr)

def _mask_token(token: str) -> str:
    if not token or len(token) < 8:
        return "****"
    return f"{token[:4]}...{token[-4:]}"

def load_user_profile() -> Dict:
    profile_json = os.environ.get('USER_PROFILE_JSON', '')
    if profile_json:
        try:
            return json.loads(profile_json)
        except (json.JSONDecodeError, ValueError) as e:
            _warn("load_user_profile/env", e)
    if os.path.exists('user_profile.json'):
        try:
            with open('user_profile.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            _warn("load_user_profile/file", e)
    return USER_PROFILE_DEFAULT

USER_PROFILE = load_user_profile()

# =============================================================================
# PROMPT COMBINÉ DYNAMIQUE — v7.1 : README inclus, reasoning 40 mots
# =============================================================================
def build_system_prompt_combined() -> str:
    """Prompt traduction + scoring sémantique.
    Injecte le profil utilisateur chargé dynamiquement.
    Le message utilisateur inclura un extrait README pour contexte complet."""
    languages  = ', '.join(USER_PROFILE.get('languages', []))
    frameworks = ', '.join(USER_PROFILE.get('frameworks', []))
    domains    = ', '.join(USER_PROFILE.get('domains', []))
    interests  = ', '.join(USER_PROFILE.get('interests', []))
    infra      = ', '.join(USER_PROFILE.get('infra', []))

    readme_note = (
        "Tu reçois également un extrait du README du projet pour mieux "
        "comprendre ce qu'il fait réellement au-delà de sa description courte.\n\n"
        if README_LLM_CHARS > 0 else ""
    )

    return (
        "Tu es un expert en évaluation de dépôts GitHub pour ce profil utilisateur:\n"
        f"- Langages maîtrisés: {languages}\n"
        f"- Frameworks / librairies: {frameworks}\n"
        f"- Domaines d'intérêt: {domains}\n"
        f"- Outils et workflows: {interests}\n"
        f"- Infrastructure: {infra}\n\n"
        f"{readme_note}"
        "TÂCHE: Traduis la description en français ET évalue la pertinence du dépôt "
        "pour ce profil sur une échelle de 0 à 10.\n\n"
        "Critères de scoring:\n"
        "  10 = outil directement utilisable, stack identique, domaine cœur de métier\n"
        "   7 = pertinent, stack compatible, intérêt fort mais indirect\n"
        "   4 = intéressant mais éloigné du profil\n"
        "   1 = peu pertinent, hors domaines\n"
        "   0 = sans rapport\n\n"
        "Retourne UNIQUEMENT un JSON valide, aucun texte avant ou après:\n"
        "{\n"
        '  "description_fr": "traduction française de la description",\n'
        '  "use_cases_fr": "• cas d\'usage 1\\n• cas d\'usage 2\\n• cas d\'usage 3",\n'
        '  "score": <entier 0 à 10>,\n'
        '  "reasoning": "<justification du score en 40 mots maximum>"\n'  # 🆕 v7.1
        "}"
    )

# =============================================================================
# HEADERS HTTP
# =============================================================================
NOTION_HEADERS = {
    'Authorization':  f'Bearer {NOTION_TOKEN}',
    'Content-Type':   'application/json',
    'Notion-Version': '2022-06-28',
}
GITHUB_HEADERS = {
    'Accept':               'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
}
if GITHUB_TOKEN:
    GITHUB_HEADERS['Authorization'] = f'Bearer {GITHUB_TOKEN}'

OPENROUTER_HEADERS = {
    'Authorization': f'Bearer {OPENROUTER_API_KEY}',
    'Content-Type':  'application/json',
    'HTTP-Referer':  'https://github.com/leprofconnecte/gitnotate',
    'X-Title':       'GitNotate',
}
MISTRAL_HEADERS = {
    'Authorization': f'Bearer {MISTRAL_API_KEY}',
    'Content-Type':  'application/json',
}

# =============================================================================
# SESSION HTTP PAR THREAD
# =============================================================================
thread_local = threading.local()

def get_session() -> requests.Session:
    if not hasattr(thread_local, 'session'):
        thread_local.session = requests.Session()
    return thread_local.session

print_lock         = Lock()
existing_urls_lock = Lock()
cache_lock         = Lock()

# =============================================================================
# STATS THREAD-SAFE
# =============================================================================
@dataclass
class ThreadSafeStats:
    _lock:               object = field(default_factory=Lock, repr=False)
    success:             int = 0
    errors:              int = 0
    duplicates:          int = 0
    skipped:             int = 0
    translation_success: int = 0
    translation_failed:  int = 0
    llm_score_success:   int = 0
    llm_score_fallback:  int = 0

    def inc(self, field_name: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, field_name, getattr(self, field_name) + amount)

    @property
    def translation_total(self) -> int:
        return self.translation_success + self.translation_failed

    @property
    def translation_rate(self) -> float:
        return (self.translation_success / self.translation_total * 100) \
               if self.translation_total > 0 else 0.0

    @property
    def llm_score_total(self) -> int:
        return self.llm_score_success + self.llm_score_fallback

    @property
    def llm_score_rate(self) -> float:
        return (self.llm_score_success / self.llm_score_total * 100) \
               if self.llm_score_total > 0 else 0.0

stats = ThreadSafeStats()

# =============================================================================
# CACHE GITHUB — JSON
# =============================================================================
GITHUB_CACHE: Dict[str, Dict] = {}
GITHUB_CACHE_DIRTY: bool = False
CACHE_FILE = Path('.gitnotate_cache.json')

def load_github_cache() -> Dict[str, Dict]:
    if not CACHE_ENABLED or not CACHE_FILE.exists():
        return {}
    try:
        cache_age = time.time() - CACHE_FILE.stat().st_mtime
        if cache_age >= CACHE_TTL_SECONDS:
            log(f"📦 Cache expiré ({cache_age / 3600:.1f}h)", 'verbose')
            return {}
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Type racine inattendu")
        log(f"📦 Cache chargé ({len(data)} entrées)", 'verbose')
        return data
    except (json.JSONDecodeError, ValueError) as e:
        _warn("load_github_cache", e)
        backup = CACHE_FILE.with_suffix('.json.bak')
        try:
            CACHE_FILE.rename(backup)
            log(f"⚠️  Cache corrompu → {backup}")
        except OSError:
            pass
    except OSError as e:
        _warn("load_github_cache", e)
    return {}

def save_github_cache(cache: Dict[str, Dict]) -> None:
    if not CACHE_ENABLED:
        return
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, separators=(',', ':'))
        log(f"💾 Cache GitHub sauvegardé ({len(cache)} entrées)", 'verbose')
    except OSError as e:
        _warn("save_github_cache", e)

def _flush_cache_on_exit() -> None:
    global GITHUB_CACHE_DIRTY
    if CACHE_ENABLED and GITHUB_CACHE_DIRTY:
        save_github_cache(GITHUB_CACHE)

atexit.register(_flush_cache_on_exit)
GITHUB_CACHE = load_github_cache()

# =============================================================================
# STATISTIQUES JSON
# =============================================================================
def save_execution_stats(run_stats: Dict) -> None:
    stats_file = Path('gitnotate_stats.json')
    history: List = []
    if stats_file.exists():
        try:
            with open(stats_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, OSError) as e:
            _warn("save_execution_stats/load", e)
            history = []

    history.append({
        'timestamp':            time.strftime("%Y-%m-%d %H:%M:%S"),
        'version':              '7.1',
        'duration_seconds':     run_stats['duration'],
        'repos_processed':      run_stats['success'] + run_stats['errors'] + run_stats['skipped'],
        'success_count':        run_stats['success'],
        'error_count':          run_stats['errors'],
        'skipped_count':        run_stats['skipped'],
        'translation_rate':     run_stats.get('translation_success_rate', 0),
        'llm_score_rate':       run_stats.get('llm_score_rate', 0),
        'translation_provider': run_stats.get('translation_provider', 'none'),
        'model_used':           MISTRAL_MODEL,
        'llm_scoring':          LLM_SCORING_ENABLED,
        'readme_llm_chars':     README_LLM_CHARS,
        'dry_run':              DRY_RUN,
    })
    history = history[-STATS_HISTORY_MAX:]
    try:
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except OSError as e:
        _warn("save_execution_stats/write", e)

# =============================================================================
# VALIDATION DES TOKENS
# =============================================================================
def validate_all_tokens() -> bool:
    log("🔐 Validation des tokens...\n")
    all_valid = True

    if NOTION_TOKEN:
        response = http_request_with_retry(
            'GET', 'https://api.notion.com/v1/users/me', NOTION_HEADERS, timeout=10)
        if response and response.status_code == 200:
            log(f"   ✅ Notion: {response.json().get('name', 'OK')}")
        else:
            log(f"   ❌ NOTION_TOKEN invalide ({_mask_token(NOTION_TOKEN)})")
            all_valid = False
    else:
        log("   ❌ NOTION_TOKEN manquant")
        all_valid = False

    if GITHUB_TOKEN:
        response = http_request_with_retry(
            'GET', 'https://api.github.com/user', GITHUB_HEADERS, timeout=10)
        if response and response.status_code == 200:
            u = response.json()
            log(f"   ✅ GitHub: {u.get('login', 'OK')} ({u.get('plan', {}).get('name', 'free')})")
        else:
            log(f"   ⚠️  GITHUB_TOKEN invalide ({_mask_token(GITHUB_TOKEN)}) — mode limité")
    else:
        log("   ⚠️  GITHUB_TOKEN absent (rate limit 60 req/h)")

    log("")
    return all_valid

# =============================================================================
# INITIALISATION PROVIDERS DE TRADUCTION
# =============================================================================
def _test_provider_api(provider: str) -> Tuple[bool, str]:
    """Teste un provider. 429 = clé valide → succès."""
    if provider == 'openrouter':
        if not OPENROUTER_API_KEY:
            return False, "clé manquante"
        url, headers, model, name = (
            'https://openrouter.ai/api/v1/chat/completions',
            OPENROUTER_HEADERS, TRANSLATION_MODEL, f"OpenRouter ({TRANSLATION_MODEL})",
        )
    elif provider == 'mistral':
        if not MISTRAL_API_KEY:
            return False, "clé manquante"
        url, headers, model, name = (
            'https://api.mistral.ai/v1/chat/completions',
            MISTRAL_HEADERS, MISTRAL_MODEL, f"Mistral AI ({MISTRAL_MODEL})",
        )
    else:
        return False, "provider inconnu"

    try:
        response = get_session().post(
            url, headers=headers,
            json={'model': model, 'messages': [{'role': 'user', 'content': 'Hi'}], 'max_tokens': 5},
            timeout=10,
        )
        if response.status_code == 200:
            return True, f"✅ {name} — OK"
        if response.status_code == 429:
            return True, f"✅ {name} — joignable (rate limit temporaire)"
        if response.status_code == 401:
            return False, f"❌ {name} — clé invalide"
        if response.status_code == 404:
            return False, f"❌ {name} — modèle '{model}' introuvable"
        return False, f"⚠️  {name} — status HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return False, f"⚠️  {name} — timeout (10s)"
    except requests.exceptions.ConnectionError:
        return False, f"⚠️  {name} — connexion impossible"
    except Exception as e:
        return False, f"⚠️  {name} — {type(e).__name__}: {e}"


def init_translation_providers() -> Tuple[Optional[str], Optional[str]]:
    if not TRANSLATION_ENABLED:
        log("   ℹ️  Traduction désactivée (TRANSLATION_ENABLED=false)")
        return None, None

    log("🔍 Détection des providers de traduction...")

    openrouter_ok, openrouter_msg = (
        _test_provider_api('openrouter') if OPENROUTER_API_KEY
        else (False, "⚠️  OpenRouter — OPENROUTER_API_KEY manquant")
    )
    mistral_ok, mistral_msg = (
        _test_provider_api('mistral') if MISTRAL_API_KEY
        else (False, "⚠️  Mistral AI — MISTRAL_API_KEY manquant")
    )

    log(f"   {openrouter_msg}")
    log(f"   {mistral_msg}")

    primary = fallback = None
    if openrouter_ok:
        primary = 'openrouter'
        if mistral_ok:
            fallback = 'mistral'
            log("   💡 Stratégie: OpenRouter (primaire) + Mistral (fallback)")
        else:
            log("   💡 Stratégie: OpenRouter uniquement")
    elif mistral_ok:
        primary = 'mistral'
        log("   💡 Stratégie: Mistral AI (fallback actif — OpenRouter indisponible)")
    else:
        log("   ❌ Aucun provider disponible — scoring lexical uniquement")

    log("")
    return primary, fallback

# =============================================================================
# APPEL API TRADUCTION — unifié OpenRouter + Mistral
# max_tokens=1200 pour absorber le README dans le contexte (🆕 v7.1)
# =============================================================================
def _call_translation_api(provider: str, messages: List[Dict],
                           temperature: float = 0.3) -> Optional[str]:
    if provider == 'openrouter':
        url, headers, model = (
            'https://openrouter.ai/api/v1/chat/completions',
            OPENROUTER_HEADERS, TRANSLATION_MODEL,
        )
    elif provider == 'mistral':
        url, headers, model = (
            'https://api.mistral.ai/v1/chat/completions',
            MISTRAL_HEADERS, MISTRAL_MODEL,
        )
    else:
        return None

    response = http_request_with_retry(
        'POST', url, headers,
        json_data={
            'model':       model,
            'messages':    messages,
            'temperature': temperature,
            'max_tokens':  1200,  # 🆕 v7.1 — README inclus dans le prompt
        },
        timeout=DEFAULT_TIMEOUT,
    )
    if response and response.status_code == 200:
        try:
            return response.json()['choices'][0]['message']['content'].strip()
        except (KeyError, IndexError) as e:
            _warn(f"_call_translation_api/{provider}/parse", e)
    return None

# =============================================================================
# DÉTECTION LANGUE
# =============================================================================
def detect_language(text: str) -> str:
    if not text:
        return 'en'
    french_indicators = ['les', 'des', 'une', 'est', 'sont', 'pour', 'avec', 'dans', 'cette', 'qui']
    words = text.lower().split()[:50]
    return 'fr' if sum(1 for w in words if w in french_indicators) > 3 else 'en'

# =============================================================================
# FILTRE ÂGE — UTC-aware
# =============================================================================
def _parse_github_date(date_str: str) -> float:
    dt = datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
    return dt.replace(tzinfo=timezone.utc).timestamp()

def is_repo_recent_enough(repo_info: Dict) -> bool:
    if MIN_UPDATE_DAYS == 0:
        return True
    updated_at = repo_info.get('updated_at', '')
    if not updated_at:
        return True
    try:
        days_old = (datetime.now(timezone.utc).timestamp() - _parse_github_date(updated_at)) / 86400
        return days_old <= MIN_UPDATE_DAYS
    except (ValueError, OSError) as e:
        _warn("is_repo_recent_enough", e)
        return True

# =============================================================================
# PROGRESS BAR
# =============================================================================
def print_progress_bar(current: int, total: int, elapsed: float) -> None:
    if total == 0:
        return
    progress = current / total
    filled   = int(40 * progress)
    bar      = '█' * filled + '░' * (40 - filled)
    if current > 0:
        eta     = int((elapsed / current) * (total - current))
        eta_str = f"{eta // 60}min {eta % 60}s"
    else:
        eta_str = "calcul..."
    print(f"\r  {bar} {progress * 100:.1f}% | {current}/{total} | ETA: {eta_str} ", end='', flush=True)

# =============================================================================
# HTTP AVEC RETRY ET BACKOFF EXPONENTIEL
# =============================================================================
def http_request_with_retry(
    method:      str,
    url:         str,
    headers:     Dict,
    json_data:   Optional[Dict] = None,
    params:      Optional[Dict] = None,
    timeout:     int = DEFAULT_TIMEOUT,
    max_retries: int = MAX_RETRIES,
) -> Optional[requests.Response]:
    session   = get_session()
    is_github = 'api.github.com' in url

    for attempt in range(1, max_retries + 1):
        try:
            if method.upper() == 'GET':
                response = session.get(url, headers=headers, params=params, timeout=timeout)
            elif method.upper() == 'POST':
                response = session.post(url, headers=headers, json=json_data, timeout=timeout)
            else:
                raise ValueError(f"Méthode non supportée: {method}")

            if response.status_code in (200, 201):
                return response

            if response.status_code == 429 and attempt < max_retries:
                retry_after = response.headers.get('Retry-After')
                wait_time   = (GITHUB_SECONDARY_RATE_LIMIT_WAIT if is_github and not retry_after
                               else int(retry_after) if retry_after and retry_after.isdigit()
                               else BACKOFF_FACTOR ** attempt)
                log(f"⏳ Rate limit (429) — attente {wait_time}s", 'verbose')
                time.sleep(wait_time)
                continue

            if response.status_code == 403 and attempt < max_retries:
                remaining   = response.headers.get('X-RateLimit-Remaining')
                reset       = response.headers.get('X-RateLimit-Reset')
                retry_after = response.headers.get('Retry-After')
                if retry_after or (remaining == '0' and reset):
                    wait_time = (int(retry_after) if retry_after and retry_after.isdigit()
                                 else max(1, int(reset) - int(time.time())) if reset and reset.isdigit()
                                 else BACKOFF_FACTOR ** attempt)
                    log(f"⏳ Rate limit (403) — attente {wait_time}s", 'verbose')
                    time.sleep(wait_time)
                    continue
                else:
                    if 'notion.com' in url:
                        log("❌ 403 Notion: vérifiez les permissions de l'intégration")
                    return response

            if 500 <= response.status_code < 600 and attempt < max_retries:
                time.sleep(BACKOFF_FACTOR ** attempt)
                continue

            return response

        except requests.exceptions.Timeout:
            if attempt < max_retries:
                time.sleep(BACKOFF_FACTOR ** attempt)
                continue
            return None
        except requests.exceptions.ConnectionError:
            if attempt < max_retries:
                time.sleep(BACKOFF_FACTOR ** attempt)
                continue
            return None
        except Exception as e:
            _warn(f"http_request_with_retry({url[:60]})", e)
            return None

    return None

# =============================================================================
# SCORING LEXICAL — fallback si LLM indisponible
# =============================================================================
def calculate_relevance_score(repo_info: Dict) -> int:
    score      = 0
    language   = repo_info.get('language', '').lower()
    desc       = (repo_info.get('description') or '').lower()
    topics     = [t.lower() for t in repo_info.get('topics', [])]
    topics_str = ' '.join(topics)
    readme     = repo_info.get('readme', '').lower()

    if any(language in l.lower() for l in USER_PROFILE.get('languages', [])):
        score += 3

    fw_found = sum(
        1 for fw in USER_PROFILE.get('frameworks', [])
        if fw.lower() in desc or fw.lower() in topics_str or fw.lower() in readme[:500]
    )
    score += min(fw_found * 2, 4)

    score += min(sum(1 for d in USER_PROFILE.get('domains', []) if d in desc or d in topics_str), 3)
    score += min(sum(1 for i in USER_PROFILE.get('interests', [])
                     if i.replace('-', ' ') in desc or i in topics_str), 2)
    score += min(sum(1 for t in USER_PROFILE.get('infra', [])
                     if t.lower() in desc or t.lower() in topics_str or t.lower() in readme[:300]), 2)

    edu  = ['education', 'teaching', 'teacher', 'student', 'learning', 'course', 'école', 'pedagog']
    auto = ['automation', 'workflow', 'productivity', 'scraping', 'bot', 'n8n', 'make', 'pipeline']
    fin  = ['trading', 'finance', 'stock', 'market', 'backtesting', 'portfolio', 'quant', 'investing']

    if any(kw in desc or kw in topics_str for kw in edu):
        score += 1
    if any(kw in desc or kw in topics_str for kw in auto):
        score += 1
    if any(kw in desc or kw in topics_str for kw in fin):
        score += 1

    irrelevant_langs  = ['java', 'c++', 'rust', 'kotlin', 'swift', 'c#']
    irrelevant_topics = ['game', 'mobile-app', 'ios', 'android', 'blockchain']

    if language in irrelevant_langs:
        if not any(d in topics_str for d in USER_PROFILE.get('domains', [])):
            score = max(score - 2, 0)
    if any(t in topics_str for t in irrelevant_topics):
        score = max(score - 2, 0)

    return min(max(score, 0), 10)

# =============================================================================
# 🆕 v7.1: TRADUCTION + SCORING SÉMANTIQUE — README inclus dans le contexte
# =============================================================================
def translate_and_score(
    description: str,
    use_cases:   str,
    repo_info:   Dict,
    repo_name:   str = "",
) -> Dict[str, Any]:
    """Appel LLM unique : traduction EN→FR + scoring sémantique avec contexte README.

    Nouveauté v7.1: le README (README_LLM_CHARS premiers caractères) est inclus
    dans le message utilisateur → le LLM peut lire le contenu réel du projet
    même quand la description GitHub est vague ou absente.

    Fallback automatique sur scoring lexical si:
    - Aucun provider disponible
    - LLM ne retourne pas un JSON valide
    - Score hors plage 0-10
    """
    result: Dict[str, Any] = {
        'description_fr': description,
        'use_cases_fr':   use_cases,
        'score':          None,
        'reasoning':      '',
        'translated':     False,
        'provider':       None,
        'scoring_method': 'lexical',
    }

    already_fr = detect_language(description) == 'fr'

    # Cas 1: traduction désactivée ou aucun provider
    if not TRANSLATION_ENABLED or (not TRANSLATION_PROVIDER and not TRANSLATION_FALLBACK):
        result['score']          = calculate_relevance_score(repo_info)
        result['scoring_method'] = 'lexical'
        if already_fr:
            result['translated'] = True
        stats.inc('llm_score_fallback')
        return result

    # Cas 2: déjà en français + scoring LLM désactivé
    if already_fr and not LLM_SCORING_ENABLED:
        result['translated']     = True
        result['provider']       = 'none (FR)'
        result['score']          = calculate_relevance_score(repo_info)
        result['scoring_method'] = 'lexical'
        stats.inc('translation_success')
        stats.inc('llm_score_fallback')
        return result

    # Construction du prompt
    if LLM_SCORING_ENABLED:
        system_prompt = build_system_prompt_combined()

        # 🆕 v7.1 — README inclus dans le contexte utilisateur
        readme_preview = repo_info.get('readme', '')[:README_LLM_CHARS].strip() if README_LLM_CHARS > 0 else ''

        user_content = (
            f"Nom du repo: {repo_info.get('name', 'N/A')}\n"
            f"Langage principal: {repo_info.get('language', 'N/A')}\n"
            f"Topics GitHub: {', '.join(repo_info.get('topics', [])) or 'aucun'}\n"
            f"Stars: {repo_info.get('stars', 0)}\n"
            f"Description: {description}\n\n"
            f"Cas d'usage suggérés (à traduire):\n{use_cases}"
        )
        if readme_preview:
            user_content += f"\n\n--- Extrait README ({len(readme_preview)} chars) ---\n{readme_preview}"

        temperature = 0.1  # quasi-déterministe pour le score
    else:
        system_prompt = SYSTEM_PROMPT_TRANSLATE
        user_content  = f"Description: {description}\n\nCas d'usage: {use_cases}"
        temperature   = 0.3

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user',   'content': user_content},
    ]

    # Cascade OpenRouter → Mistral
    raw_text = used_provider = None
    for provider in [TRANSLATION_PROVIDER, TRANSLATION_FALLBACK]:
        if not provider:
            continue
        raw_text = _call_translation_api(provider, messages, temperature)
        if raw_text:
            used_provider = provider
            break
        log(f"   ⚠️  [{repo_name}] {provider} échec — basculement fallback", 'verbose')

    # Parsing de la réponse
    if raw_text and used_provider:
        try:
            fb, lb = raw_text.find('{'), raw_text.rfind('}')
            if fb != -1 and lb > fb:
                raw_text = raw_text[fb:lb + 1]
            parsed = json.loads(raw_text)

            result['description_fr'] = parsed.get('description_fr', description)
            result['use_cases_fr']   = parsed.get('use_cases_fr',   use_cases)
            result['translated']     = True
            result['provider']       = used_provider
            stats.inc('translation_success')

            if LLM_SCORING_ENABLED:
                llm_score = parsed.get('score')
                if isinstance(llm_score, (int, float)) and 0 <= float(llm_score) <= 10:
                    result['score']          = int(round(float(llm_score)))
                    result['reasoning']      = str(parsed.get('reasoning', ''))[:500]  # 🆕 v7.1
                    result['scoring_method'] = 'llm'
                    stats.inc('llm_score_success')
                    log(f"   🧠 [{repo_name}] Score LLM: {result['score']}/10 — {result['reasoning']}", 'verbose')
                else:
                    result['score']          = calculate_relevance_score(repo_info)
                    result['scoring_method'] = 'lexical'
                    stats.inc('llm_score_fallback')
                    log(f"   ⚠️  [{repo_name}] Score LLM invalide ('{llm_score}') → fallback lexical", 'verbose')
            else:
                result['score']          = calculate_relevance_score(repo_info)
                result['scoring_method'] = 'lexical'
                stats.inc('llm_score_fallback')

            return result

        except json.JSONDecodeError as e:
            _warn(f"translate_and_score/json ({repo_name})", e)
            stats.inc('translation_failed')
        except Exception as e:
            _warn(f"translate_and_score ({repo_name})", e)
            stats.inc('translation_failed')
    else:
        stats.inc('translation_failed')

    # Fallback total
    result['score']          = calculate_relevance_score(repo_info)
    result['scoring_method'] = 'lexical'
    stats.inc('llm_score_fallback')
    return result

# =============================================================================
# NOTION — EXTRACTION DES BLOCS
# =============================================================================
def get_all_blocks_recursive(
    block_id: str, blocks: List = None, depth: int = 0, max_depth: int = 50
) -> List[Dict]:
    if blocks is None:
        blocks = []
    if depth >= max_depth:
        return blocks
    url          = f"https://api.notion.com/v1/blocks/{block_id}/children"
    start_cursor = None
    while True:
        params = {'page_size': 100}
        if start_cursor:
            params['start_cursor'] = start_cursor
        response = http_request_with_retry('GET', url, NOTION_HEADERS, params=params)
        if not response or response.status_code not in (200, 201):
            break
        data = response.json()
        for block in data.get('results', []):
            blocks.append(block)
            if block.get('has_children', False):
                get_all_blocks_recursive(block['id'], blocks, depth + 1, max_depth)
        if not data.get('has_more', False):
            break
        start_cursor = data.get('next_cursor')
        if not start_cursor:
            break
    return blocks

def extract_urls_from_blocks(blocks: List[Dict]) -> List[str]:
    github_urls = []
    for block in blocks:
        block_type = block.get('type')
        if block_type in ('bookmark', 'link_preview', 'embed'):
            url = block.get(block_type, {}).get('url', '')
            if 'github.com' in url:
                github_urls.append(url)
        elif block_type in ('paragraph', 'heading_1', 'heading_2', 'heading_3',
                            'bulleted_list_item', 'numbered_list_item'):
            for text_obj in block.get(block_type, {}).get('rich_text', []):
                if text_obj.get('type') == 'text':
                    content = text_obj.get('text', {}).get('content', '')
                    for url in re.findall(r'https?://(?:www\.)?github\.com/[^\s\)]+', content):
                        github_urls.append(re.sub(r'[,\.\)]$', '', url))
                    link = text_obj.get('text', {}).get('link')
                    if link and 'github.com' in link.get('url', ''):
                        github_urls.append(link['url'])
    return github_urls

def normalize_github_url(url: str) -> str:
    url = url.rstrip('/').lower()
    for pattern in [r'github\.com/([^/]+)/([^/\?#]+)',
                    r'raw\.githubusercontent\.com/([^/]+)/([^/]+)']:
        m = re.search(pattern, url)
        if m:
            return f"{m.group(1)}/{re.sub(r'.git$', '', m.group(2), flags=re.IGNORECASE)}"
    return url

def detect_duplicates(urls: List[str]) -> Dict:
    log("🔍 Détection des doublons...")
    normalized: Dict[str, str] = {}
    duplicates: List[Dict]     = []
    for url in urls:
        norm = normalize_github_url(url)
        if norm in normalized:
            duplicates.append({'original': normalized[norm], 'duplicate': url})
            log(f"   ⚠️  Doublon: {url}")
        else:
            normalized[norm] = url
    unique_urls = list(normalized.values())
    log(f"\n📊 Résumé doublons:")
    log(f"   • URLs totales:       {len(urls)}")
    log(f"   • URLs uniques:       {len(unique_urls)}")
    log(f"   • Doublons supprimés: {len(duplicates)}")
    log("")
    return {
        'unique_urls': unique_urls,
        'duplicates':  duplicates,
        'stats': {'total': len(urls), 'unique': len(unique_urls), 'duplicates': len(duplicates)},
    }

def extract_github_info(url: str) -> Optional[Dict[str, str]]:
    for pattern in [r'github\.com/([^/]+)/([^/\?#]+)',
                    r'raw\.githubusercontent\.com/([^/]+)/([^/]+)']:
        m = re.search(pattern, url)
        if m:
            return {'owner': m.group(1),
                    'repo':  re.sub(r'\.git$', '', m.group(2), flags=re.IGNORECASE)}
    return None

# =============================================================================
# GITHUB — fetch metadata + README en parallèle
# =============================================================================
def get_github_repo_info(owner: str, repo: str) -> Optional[Dict]:
    global GITHUB_CACHE_DIRTY
    cache_key = f"{owner}/{repo}"

    if CACHE_ENABLED and cache_key in GITHUB_CACHE:
        cached = GITHUB_CACHE[cache_key]
        if cached.get('updated_at'):
            try:
                if (datetime.now(timezone.utc).timestamp() - _parse_github_date(cached['updated_at'])) < CACHE_STALE_SECONDS:
                    log(f"   📦 Cache hit: {cache_key}", 'verbose')
                    return cached
            except (ValueError, OSError) as e:
                _warn(f"cache_check ({cache_key})", e)

    with ThreadPoolExecutor(max_workers=2) as inner:
        f_meta   = inner.submit(http_request_with_retry, 'GET',
                                f"https://api.github.com/repos/{owner}/{repo}",
                                GITHUB_HEADERS, None, None, 15)
        f_readme = inner.submit(http_request_with_retry, 'GET',
                                f"https://api.github.com/repos/{owner}/{repo}/readme",
                                GITHUB_HEADERS, None, None, 15)
        response, readme_response = f_meta.result(), f_readme.result()

    if not response or response.status_code not in (200, 201):
        return None

    data           = response.json()
    readme_content = ''
    if readme_response and readme_response.status_code in (200, 201):
        try:
            readme_content = base64.b64decode(
                readme_response.json().get('content', '')
            ).decode('utf-8', errors='ignore')
        except Exception as e:
            _warn(f"readme_decode ({owner}/{repo})", e)

    result = {
        'name':        data.get('name'),
        'full_name':   data.get('full_name'),
        'description': data.get('description'),
        'stars':       data.get('stargazers_count', 0),
        'language':    data.get('language', 'Autre'),
        'updated_at':  data.get('updated_at'),
        'topics':      data.get('topics', []),
        'readme':      readme_content[:README_MAX_CHARS],
        'html_url':    data.get('html_url'),
    }

    if CACHE_ENABLED:
        with cache_lock:
            GITHUB_CACHE[cache_key] = result
            GITHUB_CACHE_DIRTY = True

    return result

# =============================================================================
# ANALYSE README
# =============================================================================
def analyze_repo_for_usage(repo_info: Dict) -> Dict[str, str]:
    description = repo_info.get('description') or "GitHub project"
    readme      = repo_info.get('readme', '')
    language    = repo_info.get('language', '')
    topics      = repo_info.get('topics', [])

    is_agent = 'agent' in ' '.join(topics).lower() or 'agent' in description.lower()
    is_ml    = any(t in topics for t in ['machine-learning', 'deep-learning', 'ai'])
    is_web   = any(t in topics for t in ['web', 'frontend', 'backend', 'react'])

    installation = "See documentation"
    for pattern in [r'## Installation(.{0,500}?)(?=##|\Z)', r'## Getting Started(.{0,500}?)(?=##|\Z)']:
        m = re.search(pattern, readme, re.IGNORECASE | re.DOTALL)
        if m:
            install_text = m.group(1).strip()
            commands     = re.findall(r'```(?:bash|shell)?\n(.+?)\n```', install_text, re.DOTALL)
            if commands:
                installation = commands[0].strip()[:250]
                break
            lines = [l.strip() for l in install_text.split('\n') if l.strip() and len(l.strip()) > 3]
            if lines:
                installation = '\n'.join(lines[:5])
                break

    if is_agent:
        use_cases = ["Task automation via AI agents", "Multi-agent orchestration", "Agent integration"]
    elif is_ml:
        use_cases = ["Model fine-tuning", "Production deployment", "ML experimentation"]
    elif is_web:
        use_cases = ["Web app development", "UI prototyping", "Tech stack integration"]
    else:
        use_cases = ["Development integration", "Testing", "Business adaptation"]

    repo_name = repo_info.get('name', '')
    example   = (f"pip install {repo_name}" if language == 'Python'
                 else f"npm install {repo_name}" if language in ('JavaScript', 'TypeScript')
                 else "See docs")

    return {
        'description':    description[:600],
        'use_cases_text': '\n'.join(f"• {uc}" for uc in use_cases),
        'installation':   installation,
        'example':        example,
        'prerequisites':  f"{language} recent" if language else "See docs",
    }

# =============================================================================
# NOTION — DATABASE
# =============================================================================
def assert_database_schema(db_data: Dict) -> None:
    required = {
        'Nom', 'URL', 'Description', "Cas d'usage", 'Installation',
        'Exemple', 'Prérequis', 'Stars', 'Pertinence', 'Langage',
        'Type', 'Statut', 'Dernière MAJ', 'Analysé le',
    }
    props   = set((db_data.get('properties') or {}).keys())
    missing = required - props
    if missing:
        raise SystemExit(
            f"\n❌ ERREUR SCHEMA DATABASE\n\n"
            f"Propriétés manquantes: {sorted(missing)}\n\n"
            f"Solutions:\n"
            f"1. Ajoutez ces colonnes manuellement dans Notion\n"
            f"2. OU supprimez DATABASE_ID du .env pour créer une nouvelle DB\n"
        )
    if 'Justification' not in props:
        log("⚠️  Colonne 'Justification' absente — reasoning LLM non sauvegardé dans Notion")
        log("   → Ajoutez une colonne 'Justification' (type Texte) pour l'activer")

def create_or_get_database(parent_page_id: str, database_id: str) -> Optional[Dict]:
    if database_id:
        log(f"📋 Réutilisation database {database_id[:8]}...")
        response = http_request_with_retry(
            'GET', f"https://api.notion.com/v1/databases/{database_id}", NOTION_HEADERS)
        if response and response.status_code in (200, 201):
            db_data = response.json()
            assert_database_schema(db_data)
            log("✅ Schema validé")
            return {'id': db_data['id'], 'url': db_data['url'],
                    'has_justification': 'Justification' in (db_data.get('properties') or {})}
        log("⚠️  Database introuvable → création...")

    payload = {
        'parent': {'page_id': parent_page_id},
        'title':  [{'type': 'text', 'text': {'content': 'Ressources GitHub'}}],
        'properties': {
            'Nom':           {'title': {}},
            'URL':           {'url': {}},
            'Description':   {'rich_text': {}},
            "Cas d'usage":   {'rich_text': {}},
            'Installation':  {'rich_text': {}},
            'Exemple':       {'rich_text': {}},
            'Prérequis':     {'rich_text': {}},
            'Justification': {'rich_text': {}},
            'Stars':         {'number': {}},
            'Pertinence':    {'number': {}},
            'Langage': {'select': {'options': [
                {'name': 'Python',     'color': 'blue'},
                {'name': 'JavaScript', 'color': 'yellow'},
                {'name': 'TypeScript', 'color': 'purple'},
                {'name': 'Go',         'color': 'green'},
                {'name': 'Autre',      'color': 'gray'},
            ]}},
            'Type': {'multi_select': {'options': [
                {'name': 'Agent IA', 'color': 'pink'},
                {'name': 'ML/AI',    'color': 'red'},
                {'name': 'Web',      'color': 'blue'},
                {'name': 'Outils',   'color': 'purple'},
            ]}},
            'Statut': {'select': {'options': [
                {'name': 'À explorer', 'color': 'gray'},
                {'name': 'En test',    'color': 'yellow'},
                {'name': 'Utilisé',    'color': 'green'},
            ]}},
            'Dernière MAJ': {'date': {}},
            'Analysé le':   {'date': {}},
        },
    }
    response = http_request_with_retry(
        'POST', 'https://api.notion.com/v1/databases', NOTION_HEADERS, json_data=payload)
    if response and response.status_code in (200, 201):
        db_data = response.json()
        return {'id': db_data['id'], 'url': db_data['url'], 'has_justification': True}
    return None

def load_existing_urls(database_id: str) -> Set[str]:
    log("⏳ Préchargement des URLs existantes...")
    existing_urls: Set[str] = set()
    query_url               = f"https://api.notion.com/v1/databases/{database_id}/query"
    start_cursor            = None
    while True:
        payload = {'page_size': 100}
        if start_cursor:
            payload['start_cursor'] = start_cursor
        response = http_request_with_retry('POST', query_url, NOTION_HEADERS, json_data=payload)
        if not response or response.status_code not in (200, 201):
            break
        data = response.json()
        for page in data.get('results', []):
            url_prop = page.get('properties', {}).get('URL', {})
            if url_prop.get('type') == 'url' and url_prop.get('url'):
                existing_urls.add(url_prop['url'])
        if not data.get('has_more', False):
            break
        start_cursor = data.get('next_cursor')
        if not start_cursor:
            break
    log(f"✅ {len(existing_urls)} URLs déjà présentes\n")
    return existing_urls

# =============================================================================
# TRAITEMENT D'UN REPO
# =============================================================================
def process_single_repo(
    url:               str,
    database_id:       str,
    existing_urls:     Set[str],
    has_justification: bool,
    idx:               int,
    total:             int,
) -> Dict:
    result = {'url': url, 'success': False, 'error': None}

    github_info = extract_github_info(url)
    if not github_info:
        result['error'] = "URL invalide"
        stats.inc('errors')
        return result

    owner, repo = github_info['owner'], github_info['repo']

    repo_info = get_github_repo_info(owner, repo)
    if not repo_info:
        result['error'] = "GitHub échec"
        stats.inc('errors')
        log(f"[{idx}/{total}] ❌ {owner}/{repo} — GitHub échec")
        return result

    if not is_repo_recent_enough(repo_info):
        result['skipped'] = True
        stats.inc('skipped')
        log(f"[{idx}/{total}] ⏳ {owner}/{repo} — Trop ancien ({(repo_info.get('updated_at') or '')[:10]})")
        return result

    with existing_urls_lock:
        if repo_info.get('html_url') in existing_urls:
            result['success'] = True
            result['skipped'] = True
            stats.inc('skipped')
            log(f"[{idx}/{total}] ⏭️  {owner}/{repo} — Déjà présent")
            return result

    analysis   = analyze_repo_for_usage(repo_info)
    llm_result = translate_and_score(
        analysis['description'], analysis['use_cases_text'], repo_info, f"{owner}/{repo}"
    )
    relevance_score = llm_result['score']
    reasoning       = llm_result.get('reasoning', '')
    scoring_method  = llm_result.get('scoring_method', 'lexical')

    if SCORE_MIN_THRESHOLD > 0 and relevance_score < SCORE_MIN_THRESHOLD:
        result['skipped'] = True
        stats.inc('skipped')
        log(f"[{idx}/{total}] ⏭️  {owner}/{repo} — Score {relevance_score}/10 < seuil {SCORE_MIN_THRESHOLD}")
        return result

    types  = []
    topics = repo_info.get('topics', [])
    desc   = repo_info.get('description', '') or ''
    if 'agent' in ' '.join(topics).lower() or 'agent' in desc.lower():
        types.append({'name': 'Agent IA'})
    if any(t in topics for t in ['machine-learning', 'ai']):
        types.append({'name': 'ML/AI'})
    if any(t in topics for t in ['web', 'frontend']):
        types.append({'name': 'Web'})
    if not types:
        types.append({'name': 'Outils'})

    language = repo_info.get('language') or 'Autre'
    if language not in ['Python', 'JavaScript', 'TypeScript', 'Go']:
        language = 'Autre'

    score_icon     = "🧠" if scoring_method == 'llm' else "📐"
    provider_label = llm_result.get('provider', '?') if llm_result.get('translated') else None
    trans_icon     = f"🌍 [{provider_label}]" if provider_label else "⚠️ EN"

    if DRY_RUN:
        reasoning_preview = f" — {reasoning[:80]}" if reasoning else ""
        log(f"[{idx}/{total}] 🔍 DRY-RUN: {owner}/{repo} "
            f"({repo_info.get('stars', 0)} ⭐ | {score_icon} {relevance_score}/10) "
            f"{trans_icon}{reasoning_preview}")
        result['success'] = True
        stats.inc('success')
        return result

    properties = {
        'Nom':          {'title':     [{'text': {'content': (repo_info.get('name') or '')[:100]}}]},
        'URL':          {'url':       repo_info.get('html_url', '')},
        'Description':  {'rich_text': [{'text': {'content': llm_result['description_fr'][:NOTION_FIELD_MAX_CHARS]}}]},
        "Cas d'usage":  {'rich_text': [{'text': {'content': llm_result['use_cases_fr'][:NOTION_FIELD_MAX_CHARS]}}]},
        'Installation': {'rich_text': [{'text': {'content': analysis['installation'][:NOTION_FIELD_MAX_CHARS]}}]},
        'Exemple':      {'rich_text': [{'text': {'content': analysis['example'][:NOTION_FIELD_MAX_CHARS]}}]},
        'Prérequis':    {'rich_text': [{'text': {'content': analysis['prerequisites'][:NOTION_FIELD_MAX_CHARS]}}]},
        'Stars':        {'number':    repo_info.get('stars', 0)},
        'Pertinence':   {'number':    relevance_score},
        'Langage':      {'select':    {'name': language}},
        'Type':         {'multi_select': types},
        'Statut':       {'select':    {'name': 'À explorer'}},
        'Dernière MAJ': {'date':      {'start': (repo_info.get('updated_at') or '')[:10]}},
        'Analysé le':   {'date':      {'start': time.strftime("%Y-%m-%d")}},
    }

    # Justification enrichie — 🆕 v7.1: 800 chars
    if has_justification and reasoning:
        justif_text = f"[{scoring_method.upper()}] {reasoning}"
        properties['Justification'] = {'rich_text': [{'text': {'content': justif_text[:800]}}]}

    response = http_request_with_retry(
        'POST', 'https://api.notion.com/v1/pages', NOTION_HEADERS,
        json_data={'parent': {'database_id': database_id}, 'properties': properties})

    if response and response.status_code in (200, 201):
        result['success'] = True
        with existing_urls_lock:
            existing_urls.add(repo_info.get('html_url', ''))
        stats.inc('success')
        reasoning_preview = f" — {reasoning[:80]}" if reasoning and LOG_LEVEL == 'verbose' else ""
        log(f"[{idx}/{total}] ✅ {owner}/{repo} "
            f"({repo_info.get('stars', 0)} ⭐ | {score_icon} {relevance_score}/10) "
            f"{trans_icon}{reasoning_preview}")
    else:
        result['error'] = f"Notion {response.status_code if response else 'timeout'}"
        stats.inc('errors')
        log(f"[{idx}/{total}] ❌ {owner}/{repo} — Notion échec ({result['error']})")

    return result

# =============================================================================
# MAIN
# =============================================================================
def main() -> None:
    global TRANSLATION_PROVIDER, TRANSLATION_FALLBACK

    log("=" * 70)
    log("🚀 GITNOTATE v7.1 — LLM FULL-CONTEXT SCORING EDITION")
    log("=" * 70)
    log("")

    if not NOTION_TOKEN:
        log("❌ NOTION_TOKEN manquant")
        return

    if not validate_all_tokens():
        return

    TRANSLATION_PROVIDER, TRANSLATION_FALLBACK = init_translation_providers()

    log("⚡ Configuration:")
    log(f"   • Workers:          {MAX_WORKERS}")
    log(f"   • GitHub auth:      {'✅' if GITHUB_TOKEN else '⚠️  rate limit réduit (60 req/h)'}")

    if not TRANSLATION_ENABLED:
        log("   • Traduction:       ❌ désactivée")
        log("   • Scoring:          📐 lexical uniquement")
    elif TRANSLATION_PROVIDER == 'openrouter':
        log(f"   • Traduction:       ✅ OpenRouter ({TRANSLATION_MODEL})")
        if TRANSLATION_FALLBACK == 'mistral':
            log(f"   • Fallback:         ✅ Mistral AI ({MISTRAL_MODEL})")
        if LLM_SCORING_ENABLED:
            readme_info = f" + README {README_LLM_CHARS} chars" if README_LLM_CHARS > 0 else ""
            log(f"   • Scoring:          🧠 LLM sémantique (t=0.1{readme_info})")
        else:
            log("   • Scoring:          📐 lexical (LLM_SCORING_ENABLED=false)")
    elif TRANSLATION_PROVIDER == 'mistral':
        log(f"   • Traduction:       ✅ Mistral AI ({MISTRAL_MODEL}) [fallback actif]")
        if LLM_SCORING_ENABLED:
            readme_info = f" + README {README_LLM_CHARS} chars" if README_LLM_CHARS > 0 else ""
            log(f"   • Scoring:          🧠 LLM sémantique (t=0.1{readme_info})")
        else:
            log("   • Scoring:          📐 lexical")
    else:
        log("   • Traduction:       ❌ aucun provider")
        log("   • Scoring:          📐 lexical uniquement (fallback automatique)")

    log(f"   • Retry:            {MAX_RETRIES} tentatives")
    log(f"   • HTTP timeout:     {DEFAULT_TIMEOUT}s")
    log(f"   • Cache GitHub:     {'✅ JSON (' + str(CACHE_TTL_SECONDS // 3600) + 'h)' if CACHE_ENABLED else '❌'}")
    log(f"   • Dry-run:          {'✅' if DRY_RUN else '❌'}")
    log(f"   • Filtre âge:       {'✅ ' + str(MIN_UPDATE_DAYS) + ' jours' if MIN_UPDATE_DAYS > 0 else '❌ désactivé'}")
    log(f"   • Score minimum:    {SCORE_MIN_THRESHOLD if SCORE_MIN_THRESHOLD > 0 else '❌ (tous acceptés)'}")
    log(f"   • Log level:        {LOG_LEVEL}")
    log(f"   • README cache:     {README_MAX_CHARS} chars | LLM context: {README_LLM_CHARS} chars")
    log("")

    log("📋 Database Notion...")
    db_result = create_or_get_database(PARENT_PAGE_ID, DATABASE_ID)
    if not db_result:
        log("❌ Impossible de créer ou récupérer la database Notion")
        return

    db_id, db_url         = db_result['id'], db_result['url']
    has_justification_col = db_result.get('has_justification', False)
    log("✅ Database prête!")
    log(f"   • ID:             {db_id}")
    log(f"   • URL:            {db_url}")
    log(f"   • Justification:  {'✅ activée' if has_justification_col else '⚠️  colonne absente'}")
    log("")

    existing_urls = load_existing_urls(db_id)

    log("🔍 Extraction URLs (pagination complète)...")
    try:
        blocks = get_all_blocks_recursive(PARENT_PAGE_ID)
        urls   = extract_urls_from_blocks(blocks)
        log(f"✅ {len(urls)} URLs extraites")
    except Exception as e:
        log(f"❌ Erreur extraction blocs: {type(e).__name__}: {e}")
        return

    if not urls:
        log("❌ Aucune URL GitHub trouvée sur la page source")
        return

    log("")
    dedup_result     = detect_duplicates(urls)
    unique_urls      = dedup_result['unique_urls']
    stats.duplicates = dedup_result['stats']['duplicates']

    try:
        with open('extracted_urls_unique.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(unique_urls) + '\n')
        log("💾 URLs uniques → extracted_urls_unique.txt")
    except OSError as e:
        _warn("save_extracted_urls", e)

    log("")
    log(f"📊 Traitement de {len(unique_urls)} dépôts...")
    if DRY_RUN:
        log("🔍 MODE DRY-RUN activé (aucune écriture dans Notion)")
    log("")

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                process_single_repo,
                url, db_id, existing_urls, has_justification_col, idx, len(unique_urls)
            ): url
            for idx, url in enumerate(unique_urls, 1)
        }
        processed = 0
        for future in as_completed(futures):
            url = futures[future]
            try:
                future.result()
            except Exception as e:
                stats.inc('errors')
                print(f"\n❌ Exception non gérée [{url}]: {type(e).__name__}: {e}", file=sys.stderr)
            processed += 1
            print_progress_bar(processed, len(unique_urls), time.time() - start_time)

    print()

    if CACHE_ENABLED and GITHUB_CACHE_DIRTY:
        save_github_cache(GITHUB_CACHE)

    elapsed = time.time() - start_time

    log("")
    log("=" * 70)
    log(f"✅ TERMINÉ en {int(elapsed // 60)}min {int(elapsed % 60)}s")
    log(f"   • Créations:       {stats.success}")
    log(f"   • Skipped:         {stats.skipped}  (déjà présents / filtrés)")
    log(f"   • Erreurs:         {stats.errors}")
    log(f"   • Doublons:        {stats.duplicates}")

    if stats.translation_total > 0:
        provider_label = TRANSLATION_PROVIDER or 'none'
        if TRANSLATION_FALLBACK:
            provider_label += f" + {TRANSLATION_FALLBACK}"
        log(f"   • Traductions:     {stats.translation_success}/{stats.translation_total} "
            f"({stats.translation_rate:.1f}%) — {provider_label}")

    if LLM_SCORING_ENABLED and stats.llm_score_total > 0:
        log(f"   • Scores LLM:      {stats.llm_score_success}/{stats.llm_score_total} "
            f"({stats.llm_score_rate:.1f}%) | "
            f"{stats.llm_score_fallback} fallbacks lexicaux")

    if elapsed > 0:
        log(f"   • Vitesse:         {len(unique_urls) / elapsed:.1f} dépôts/sec")
    log("=" * 70)
    log("")

    save_execution_stats({
        'duration':               int(elapsed),
        'success':                stats.success,
        'errors':                 stats.errors,
        'skipped':                stats.skipped,
        'translation_success_rate': stats.translation_rate,
        'llm_score_rate':         stats.llm_score_rate,
        'translation_provider':   TRANSLATION_PROVIDER or 'none',
    })

    log("📊 DATABASE NOTION:")
    log(f"   → {db_url}")
    log("")
    log("💡 Tri recommandé: Pertinence ↓ + Stars ↓")
    log("   Icônes: 🧠 = scoré par LLM (avec README)   📐 = fallback lexical")
    log("=" * 70)


if __name__ == '__main__':
    main()
