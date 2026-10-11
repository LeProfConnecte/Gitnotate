#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitNotate v7.2 - LLM FULL-CONTEXT SCORING EDITION

Nouveautés v7.2 (stabilisation — aucune donnée n'est jamais supprimée dans Notion) :
  ✅ Jamais de création implicite de base : DATABASE_ID illisible → arrêt avec le code HTTP ;
     création seulement avec CREATE_DATABASE=true (hors DRY_RUN), id mémorisé dans .gitnotate_state.json
  ✅ Noms ET types des colonnes vérifiés avant toute écriture
  ✅ Lecture complète ou arrêt : aucune création après une lecture partielle (base ou page source)
  ✅ Codes de sortie : 0 succès · 1 configuration/erreur fatale · 2 erreurs ou lecture partielle · 130 Ctrl-C
  ✅ Niveau de log 'error' toujours affiché (stderr) ; bilan avec la liste des URL en erreur
  ✅ Réponses LLM validées dans la cascade (contenu liste/null, JSON tolérant, score borné 0-10)
  ✅ Repli lexical robuste (language/topics/README absents), langage comparé par égalité
  ✅ Créations Notion jamais réessayées après un timeout (pas de doublon) ; attentes plafonnées
  ✅ Extraction stricte des liens (hôte exact, pages non-dépôt ignorées, tous les blocs texte et tableaux)
  ✅ Cache GitHub par entrée (cached_at), écritures atomiques, fichiers dans le dossier du script
  ✅ DRY_RUN sans aucune écriture Notion, MAX_REPOS, options --dry-run --max-repos --log-level --version

Fournisseurs LLM (v7.2) :
  ✅ Ordre configurable LLM_PROVIDERS (défaut : Mistral direct 'mistral-small-2603', puis OpenRouter
     'openrouter/free') ; un fournisseur sans clé est ignoré
  ✅ Tests de démarrage sans quota OpenRouter (GET /api/v1/key, quota gratuit du jour) et complétion
     Mistral avec les paramètres de production (reasoning_effort / response_format retirés si refusés)
  ✅ Mode reprise REQUIRE_LLM=true : aucune fiche sans réponse LLM valide, le dépôt est « reporté »
     et repris au run suivant ; aucun fournisseur au démarrage → arrêt avant tout appel GitHub
  ✅ Coupe-circuit par fournisseur (401/402, quota OpenRouter épuisé, échecs consécutifs), limiteur de
     débit, timeout LLM dédié, au plus 1 nouvelle tentative (429/5xx)
  ✅ « Déjà présent » détecté avant tout appel GitHub ; budget MAX_NEW_PER_RUN
  ✅ Traçabilité : modèle réellement servi et empreinte du profil dans la Justification et les stats

Historique :
  v7.1  README dans le contexte LLM, justification 800 caractères
  v7.0  traduction + score sémantique en un seul appel, profil user_profile.json, colonne Justification
  v6.9  cascade OpenRouter → Mistral
  v6.8  cache GitHub, métadonnées + README en parallèle, statistiques thread-safe
"""

import argparse
import atexit
import base64
import email.utils
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

import requests

__version__ = "7.2.0"

# =============================================================================
# DOSSIER DE DONNÉES ET FICHIER .env
# =============================================================================
# Tous les fichiers d'état sont relatifs au dossier du script (ou à GITNOTATE_DATA_DIR),
# jamais au répertoire courant.
BASE_DIR = Path(os.environ.get('GITNOTATE_DATA_DIR') or Path(__file__).resolve().parent)

if 'GITNOTATE_NO_DOTENV' not in os.environ:
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / '.env')
    except ImportError:
        pass

PROFILE_FILE = BASE_DIR / 'user_profile.json'
CACHE_FILE   = BASE_DIR / '.gitnotate_cache.json'
STATS_FILE   = BASE_DIR / 'gitnotate_stats.json'
STATE_FILE   = BASE_DIR / '.gitnotate_state.json'
URLS_FILE    = BASE_DIR / 'extracted_urls_unique.txt'

# =============================================================================
# CODES DE SORTIE
# =============================================================================
EXIT_OK          = 0    # succès
EXIT_CONFIG      = 1    # configuration invalide ou erreur fatale avant traitement
EXIT_INCOMPLETE  = 2    # run terminé avec au moins une erreur, ou lecture partielle
EXIT_INTERRUPTED = 130  # interruption clavier (Ctrl-C)

# =============================================================================
# LECTURE DE LA CONFIGURATION
# =============================================================================
# Erreurs de configuration collectées à la lecture ; main() les affiche et sort
# en code 1 avant tout appel réseau.
CONFIG_ERRORS: Dict[str, str] = {}
CONFIG_WARNINGS: List[str] = []

_LOG_LEVELS = {'quiet': 0, 'normal': 1, 'verbose': 2}


def _env_str(name: str, default: str = '') -> str:
    return os.environ.get(name, '').strip() or default


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() == 'true'


def _env_int(name: str, default: int, min_value: int = 0) -> int:
    """Entier lu dans l'environnement. Valeur invalide ou sous le minimum :
    erreur de configuration collectée (pas de traceback) et valeur par défaut."""
    raw = os.environ.get(name, '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        CONFIG_ERRORS[name] = f"{name}='{raw[:40]}' n'est pas un entier valide (défaut : {default})"
        return default
    if value < min_value:
        CONFIG_ERRORS[name] = f"{name}={value} est invalide (minimum : {min_value})"
        return default
    return value


def _env_choice(name: str, default: str, choices: Tuple[str, ...]) -> str:
    """Valeur parmi une liste fermée (insensible à la casse) ; vide → défaut ;
    valeur inconnue → erreur de configuration collectée."""
    value = os.environ.get(name, '').strip().lower()
    if not value:
        return default
    if value not in choices:
        CONFIG_ERRORS[name] = (f"{name}='{value[:30]}' invalide "
                               f"(valeurs possibles : {', '.join(c for c in choices if c)})")
        return default
    return value


LLM_PROVIDERS_KNOWN = ('mistral', 'openrouter')


def _env_providers(name: str, default: str) -> List[str]:
    """Liste ordonnée de fournisseurs LLM (« mistral,openrouter »), sans doublon."""
    raw = os.environ.get(name, '').strip() or default
    providers: List[str] = []
    for item in raw.replace(';', ',').split(','):
        item = item.strip().lower()
        if not item:
            continue
        if item not in LLM_PROVIDERS_KNOWN:
            CONFIG_ERRORS[name] = (f"{name} : fournisseur inconnu '{item[:20]}' "
                                   f"(valeurs possibles : {', '.join(LLM_PROVIDERS_KNOWN)})")
            continue
        if item not in providers:
            providers.append(item)
    if not providers:
        CONFIG_ERRORS.setdefault(name, f"{name} ne contient aucun fournisseur "
                                       f"(valeurs possibles : {', '.join(LLM_PROVIDERS_KNOWN)})")
        return default.split(',')
    return providers


# =============================================================================
# CONFIGURATION
# =============================================================================
NOTION_TOKEN       = _env_str('NOTION_TOKEN')
GITHUB_TOKEN       = _env_str('GITHUB_TOKEN')
OPENROUTER_API_KEY = _env_str('OPENROUTER_API_KEY')
MISTRAL_API_KEY    = _env_str('MISTRAL_API_KEY')
DATABASE_ID        = _env_str('DATABASE_ID')
PARENT_PAGE_ID     = _env_str('PARENT_PAGE_ID')   # vérifié dans main()
CREATE_DATABASE    = _env_bool('CREATE_DATABASE', 'false')

MAX_WORKERS         = _env_int('MAX_WORKERS', 5, 1)
TRANSLATION_ENABLED = _env_bool('TRANSLATION_ENABLED', 'true')
LLM_SCORING_ENABLED = _env_bool('LLM_SCORING_ENABLED', 'true')
BACKOFF_FACTOR      = 2
GITHUB_SECONDARY_RATE_LIMIT_WAIT = 60

# --- Fournisseurs LLM ---
# Ordre d'essai (le premier disponible est primaire, le suivant sert de secours).
LLM_PROVIDERS    = _env_providers('LLM_PROVIDERS', 'mistral,openrouter')
MISTRAL_MODEL    = _env_str('MISTRAL_MODEL', 'mistral-small-2603')
# OPENROUTER_MODEL, sinon l'ancienne variable TRANSLATION_MODEL (compatibilité), sinon le routeur gratuit
OPENROUTER_MODEL = _env_str('OPENROUTER_MODEL') or _env_str('TRANSLATION_MODEL') or 'openrouter/free'
if not _env_str('OPENROUTER_MODEL') and _env_str('TRANSLATION_MODEL'):
    CONFIG_WARNINGS.append(f"TRANSLATION_MODEL est obsolète : renommez-la OPENROUTER_MODEL "
                           f"(modèle OpenRouter utilisé : {OPENROUTER_MODEL[:60]})")

LLM_MAX_TOKENS        = _env_int('LLM_MAX_TOKENS', 3000, 16)    # budget de sortie (raisonnement compris)
LLM_TIMEOUT           = _env_int('LLM_TIMEOUT', 120, 1)          # secondes, appels LLM uniquement
LLM_BREAKER_THRESHOLD = _env_int('LLM_BREAKER_THRESHOLD', 3, 1)  # échecs consécutifs avant désactivation
LLM_RETRY_WAIT_MAX    = 60                                       # attente max avant la nouvelle tentative
OPENROUTER_RPM        = _env_int('OPENROUTER_RPM', 18, 0)        # requêtes/minute côté client (0 = sans limite)
MISTRAL_RPM           = _env_int('MISTRAL_RPM', 60, 0)
MAX_NEW_PER_RUN       = _env_int('MAX_NEW_PER_RUN', 0, 0)        # 0 = illimité

# Mode reprise : seule la valeur explicite 'false' revient au comportement historique (fiche lexicale)
REQUIRE_LLM = os.environ.get('REQUIRE_LLM', 'true').strip().lower() != 'false'

MISTRAL_RESPONSE_FORMAT = _env_choice('MISTRAL_RESPONSE_FORMAT', 'json_object', ('json_object', 'none'))
# Variable absente → 'none' ; variable vide → paramètre non envoyé
MISTRAL_REASONING_EFFORT = (os.environ['MISTRAL_REASONING_EFFORT'].strip()
                            if 'MISTRAL_REASONING_EFFORT' in os.environ else 'none')
OPENROUTER_RESPONSE_FORMAT = _env_choice('OPENROUTER_RESPONSE_FORMAT', 'none',
                                         ('none', 'json_object', 'json_schema'))
OPENROUTER_ATTRIBUTION     = _env_bool('OPENROUTER_ATTRIBUTION', 'false')
OPENROUTER_DATA_COLLECTION = _env_choice('OPENROUTER_DATA_COLLECTION', '', ('', 'allow', 'deny'))

DRY_RUN         = _env_bool('DRY_RUN', 'false')
MIN_UPDATE_DAYS = _env_int('MIN_UPDATE_DAYS', 0, 0)
CACHE_ENABLED   = _env_bool('CACHE_ENABLED', 'true')

DEFAULT_TIMEOUT        = _env_int('HTTP_TIMEOUT', 60, 1)
MAX_RETRIES            = _env_int('MAX_RETRIES', 3, 1)
CACHE_TTL_SECONDS      = _env_int('CACHE_TTL_HOURS', 24, 0) * 3600
README_MAX_CHARS       = _env_int('README_MAX_CHARS', 2500, 0)
README_LLM_CHARS       = _env_int('README_LLM_CHARS', 1500, 0)
NOTION_FIELD_MAX_CHARS = 2000
STATS_HISTORY_MAX      = 50
SCORE_MIN_THRESHOLD    = _env_int('SCORE_MIN_THRESHOLD', 0, 0)
MAX_WAIT_SECONDS       = _env_int('MAX_WAIT_SECONDS', 120, 0)   # plafond de toute attente (rate limit)
MAX_REPOS              = _env_int('MAX_REPOS', 0, 0)            # 0 = illimité
REASONING_MAX_CHARS    = 800
ERRORS_DISPLAY_MAX     = 30

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'normal').strip().lower() or 'normal'
if LOG_LEVEL not in _LOG_LEVELS:
    CONFIG_WARNINGS.append(f"LOG_LEVEL='{LOG_LEVEL[:20]}' inconnu (quiet, normal, verbose) — 'normal' utilisé")
    LOG_LEVEL = 'normal'

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
PROFILE_SOURCE_DEFAULT = "profil par défaut (intégré au script)"

# Chargé dans main() (aucune lecture de fichier à l'import)
USER_PROFILE: Dict = USER_PROFILE_DEFAULT
USER_PROFILE_SOURCE: str = PROFILE_SOURCE_DEFAULT

# =============================================================================
# UTILITAIRES
# =============================================================================
print_lock         = Lock()
existing_urls_lock = Lock()
cache_lock         = Lock()


def log(msg: str, level: str = 'normal') -> None:
    """Niveaux : quiet < normal < verbose. 'error' est toujours affiché (stderr),
    'always' toujours affiché (stdout)."""
    if level == 'error':
        stream = sys.stderr
    elif level == 'always' or _LOG_LEVELS.get(level, 1) <= _LOG_LEVELS.get(LOG_LEVEL, 1):
        stream = sys.stdout
    else:
        return
    with print_lock:
        print(msg, file=stream, flush=True)


def _warn(context: str, e: Exception) -> None:
    with print_lock:
        print(f"⚠️  [{context}] {type(e).__name__}: {e}", file=sys.stderr, flush=True)


def _mask_token(token: str) -> str:
    if not token or len(token) < 8:
        return "****"
    return f"{token[:4]}...{token[-4:]}"


def _configure_console() -> None:
    """Évite le plantage UnicodeEncodeError (emojis) quand la sortie est redirigée
    vers un fichier sous Windows (cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def _json_dict(response) -> Optional[Dict]:
    """Corps JSON d'une réponse s'il s'agit d'un objet, sinon None (jamais d'exception)."""
    try:
        data = response.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _api_error_message(response, limit: int = 200) -> str:
    """Message d'erreur renvoyé par l'API (champ "message" du JSON), tronqué."""
    if response is None:
        return ''
    body = _json_dict(response)
    if body is None:
        return ''
    err = body.get('error')
    msg: Any = ''
    if isinstance(body.get('message'), str):
        msg = body['message']
    elif isinstance(err, dict) and isinstance(err.get('message'), str):
        msg = err['message']
    elif isinstance(err, str):
        msg = err
    elif isinstance(body.get('detail'), str):
        msg = body['detail']
    msg = ' '.join(msg.split())
    return msg[:limit] + ('…' if len(msg) > limit else '')


def _api_error_text(response, limit: int = 200) -> str:
    """Message de l'API, ou à défaut le début du corps brut (tronqué, sur une ligne)."""
    msg = _api_error_message(response, limit)
    if msg or response is None:
        return msg
    try:
        text = ' '.join((response.text or '').split())
    except Exception:
        return ''
    return text[:limit] + ('…' if len(text) > limit else '')


def _profile_list(key: str) -> List[str]:
    values = USER_PROFILE.get(key, []) if isinstance(USER_PROFILE, dict) else []
    if not isinstance(values, list):
        return []
    return [v for v in values if isinstance(v, str)]


def load_user_profile() -> Tuple[Dict, str]:
    """Renvoie (profil, source) : variable USER_PROFILE_JSON, fichier user_profile.json
    (dans BASE_DIR) ou profil par défaut."""
    profile_json = os.environ.get('USER_PROFILE_JSON', '').strip()
    if profile_json:
        try:
            data = json.loads(profile_json)
            if not isinstance(data, dict):
                raise ValueError("objet JSON attendu")
            return data, "variable USER_PROFILE_JSON"
        except ValueError as e:
            _warn("load_user_profile/env", e)
    if PROFILE_FILE.exists():
        try:
            with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("objet JSON attendu")
            return data, f"fichier {PROFILE_FILE}"
        except (ValueError, OSError) as e:
            _warn("load_user_profile/file", e)
    return USER_PROFILE_DEFAULT, PROFILE_SOURCE_DEFAULT


def _atomic_write_json(path: Path, data: Any, **dump_kwargs) -> None:
    """Écrit dans un fichier .tmp puis le renomme (os.replace) : jamais de fichier à moitié écrit."""
    tmp = path.with_name(path.name + '.tmp')
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _backup_path(path: Path) -> Path:
    backup = path.with_name(path.name + '.bak')
    if backup.exists():
        backup = path.with_name(f"{path.name}.{time.strftime('%Y%m%d-%H%M%S')}.bak")
    return backup

# =============================================================================
# PROMPT COMBINÉ DYNAMIQUE — v7.1 : README inclus, reasoning 40 mots
# =============================================================================
def build_system_prompt_combined() -> str:
    """Prompt traduction + scoring sémantique.
    Injecte le profil utilisateur chargé dynamiquement.
    Le message utilisateur inclura un extrait README pour contexte complet."""
    languages  = ', '.join(_profile_list('languages'))
    frameworks = ', '.join(_profile_list('frameworks'))
    domains    = ', '.join(_profile_list('domains'))
    interests  = ', '.join(_profile_list('interests'))
    infra      = ', '.join(_profile_list('infra'))

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
        '  "reasoning": "<justification du score en 40 mots maximum>"\n'
        "}"
    )


def compute_profile_hash() -> str:
    """Empreinte de la grille de notation : 6 premiers caractères du sha1 du profil JSON
    canonique suivi du prompt système utilisé. Deux fiches de même empreinte ont été notées
    avec le même profil et le même prompt."""
    try:
        canonical = json.dumps(USER_PROFILE, sort_keys=True, ensure_ascii=False,
                               separators=(',', ':'), default=str)
    except (TypeError, ValueError):
        canonical = repr(USER_PROFILE)
    prompt = build_system_prompt_combined() if LLM_SCORING_ENABLED else SYSTEM_PROMPT_TRANSLATE
    return hashlib.sha1((canonical + prompt).encode('utf-8')).hexdigest()[:6]

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

# Aucun en-tête d'attribution par défaut : avec HTTP-Referer, OpenRouter crée une page
# d'application publique (classements). OPENROUTER_ATTRIBUTION=true les réactive.
OPENROUTER_HEADERS = {
    'Authorization': f'Bearer {OPENROUTER_API_KEY}',
    'Content-Type':  'application/json',
}
if OPENROUTER_ATTRIBUTION:
    OPENROUTER_HEADERS['HTTP-Referer']       = 'https://github.com/leprofconnecte/gitnotate'
    OPENROUTER_HEADERS['X-OpenRouter-Title'] = 'GitNotate'
MISTRAL_HEADERS = {
    'Authorization': f'Bearer {MISTRAL_API_KEY}',
    'Content-Type':  'application/json',
}

# =============================================================================
# SESSION HTTP PAR THREAD
# =============================================================================
thread_local = threading.local()
_STOP_EVENT  = threading.Event()   # positionné sur Ctrl-C : plus aucune nouvelle écriture


def get_session() -> requests.Session:
    if not hasattr(thread_local, 'session'):
        thread_local.session = requests.Session()
    return thread_local.session


def _set_last_http_error(description: str) -> None:
    thread_local.last_http_error = description


def last_http_error() -> str:
    """Cause du dernier échec réseau dans ce thread (timeout, connexion impossible...)."""
    return getattr(thread_local, 'last_http_error', '') or 'réseau'

# =============================================================================
# STATS THREAD-SAFE
# =============================================================================
@dataclass
class ThreadSafeStats:
    _lock:               object = field(default_factory=Lock, repr=False)
    success:             int = 0   # créations (ou simulées en DRY_RUN)
    errors:              int = 0
    duplicates:          int = 0   # liens en double sur la page source
    already_present:     int = 0   # déjà dans la base
    filtered:            int = 0   # âge, seuil de score, dépôt privé
    ignored:             int = 0   # liens GitHub qui ne sont pas des dépôts
    translation_success: int = 0
    translation_failed:  int = 0
    llm_score_success:   int = 0
    llm_score_fallback:  int = 0
    deferred:            int = 0   # reportés au prochain run (aucune fiche écrite)
    error_details:       List[Tuple[str, str]] = field(default_factory=list)
    errors_by_reason:    Dict[str, int] = field(default_factory=dict)
    deferred_by_reason:  Dict[str, int] = field(default_factory=dict)
    models_used:         Dict[str, int] = field(default_factory=dict)   # modèle réel → fiches
    providers_used:      Dict[str, int] = field(default_factory=dict)   # fournisseur → fiches

    def inc(self, field_name: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, field_name, getattr(self, field_name) + amount)

    def add_error(self, url: str, reason: str, reason_key: Optional[str] = None) -> None:
        with self._lock:
            self.errors += 1
            self.error_details.append((url, reason))
            key = reason_key or reason
            self.errors_by_reason[key] = self.errors_by_reason.get(key, 0) + 1

    def add_deferred(self, reason: str) -> None:
        with self._lock:
            self.deferred += 1
            self.deferred_by_reason[reason] = self.deferred_by_reason.get(reason, 0) + 1

    def add_model(self, provider: str, model: str) -> None:
        with self._lock:
            self.models_used[model] = self.models_used.get(model, 0) + 1
            self.providers_used[provider] = self.providers_used.get(provider, 0) + 1

    @property
    def skipped(self) -> int:
        return self.already_present + self.filtered

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
# CACHE GITHUB — JSON, validité par entrée (cached_at)
# =============================================================================
GITHUB_CACHE: Dict[str, Dict] = {}
GITHUB_CACHE_DIRTY: bool = False
_ATEXIT_REGISTERED: bool = False


def _cache_entry_valid(entry: Any, now: Optional[float] = None) -> bool:
    if not isinstance(entry, dict):
        return False
    cached_at = entry.get('cached_at')
    if isinstance(cached_at, bool) or not isinstance(cached_at, (int, float)):
        return False
    age = (time.time() if now is None else now) - cached_at
    return 0 <= age < CACHE_TTL_SECONDS


def load_github_cache() -> Dict[str, Dict]:
    if not CACHE_ENABLED or not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Type racine inattendu")
    except ValueError as e:
        _warn("load_github_cache", e)
        backup = CACHE_FILE.with_name(CACHE_FILE.name + '.bak')
        try:
            os.replace(CACHE_FILE, backup)
            log(f"⚠️  Cache corrompu → {backup}")
        except OSError:
            pass
        return {}
    except OSError as e:
        _warn("load_github_cache", e)
        return {}
    now   = time.time()
    valid = {k: v for k, v in data.items() if _cache_entry_valid(v, now)}
    log(f"📦 Cache chargé ({len(valid)} entrées valides sur {len(data)})", 'verbose')
    return valid


def save_github_cache(cache: Dict[str, Dict]) -> bool:
    if not CACHE_ENABLED:
        return False
    with cache_lock:
        snapshot = dict(cache)
    try:
        _atomic_write_json(CACHE_FILE, snapshot, separators=(',', ':'))
    except OSError as e:
        _warn("save_github_cache", e)
        return False
    log(f"💾 Cache GitHub sauvegardé ({len(snapshot)} entrées)", 'verbose')
    return True


def flush_github_cache() -> None:
    """Sauvegarde le cache s'il a changé, puis remet le drapeau dirty à False."""
    global GITHUB_CACHE_DIRTY
    if not CACHE_ENABLED or not GITHUB_CACHE_DIRTY:
        return
    with cache_lock:
        GITHUB_CACHE_DIRTY = False
    if not save_github_cache(GITHUB_CACHE):
        with cache_lock:
            GITHUB_CACHE_DIRTY = True


def init_github_cache() -> None:
    """Chargé dans main() : aucun effet de bord à l'import."""
    global GITHUB_CACHE, GITHUB_CACHE_DIRTY, _ATEXIT_REGISTERED
    GITHUB_CACHE = load_github_cache()
    GITHUB_CACHE_DIRTY = False
    if not _ATEXIT_REGISTERED:
        atexit.register(flush_github_cache)
        _ATEXIT_REGISTERED = True

# =============================================================================
# FICHIER D'ÉTAT (.gitnotate_state.json)
# =============================================================================
def read_state() -> Tuple[Dict, Optional[str]]:
    """Renvoie (contenu, erreur). Fichier absent : ({}, None)."""
    if not STATE_FILE.exists():
        return {}, None
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("objet JSON attendu")
    except (ValueError, OSError) as e:
        return {}, f"{type(e).__name__}: {e}"
    return data, None


def write_state(data: Dict) -> bool:
    try:
        _atomic_write_json(STATE_FILE, data, indent=2)
        return True
    except OSError as e:
        _warn("write_state", e)
        return False

# =============================================================================
# STATISTIQUES JSON
# =============================================================================
def save_execution_stats(run_stats: Dict) -> None:
    history: List = []
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
            if not isinstance(history, list):
                raise ValueError("liste JSON attendue")
        except (ValueError, OSError) as e:
            _warn("save_execution_stats/load", e)
            backup = _backup_path(STATS_FILE)
            try:
                os.replace(STATS_FILE, backup)
                log(f"⚠️  Historique des statistiques illisible → conservé dans {backup.name}")
            except OSError as e2:
                # Jamais écraser un fichier qu'on n'a pas pu mettre de côté
                _warn("save_execution_stats/backup", e2)
                return
            history = []

    history.append({
        'timestamp':             time.strftime("%Y-%m-%d %H:%M:%S"),
        'version':               __version__,
        'duration_seconds':      run_stats['duration'],
        'repos_processed':       run_stats['success'] + run_stats['errors'] + run_stats['skipped'],
        'success_count':         run_stats['success'],
        'error_count':           run_stats['errors'],
        'skipped_count':         run_stats['skipped'],
        'already_present_count': run_stats.get('already_present', 0),
        'filtered_count':        run_stats.get('filtered', 0),
        'ignored_count':         run_stats.get('ignored', 0),
        'duplicates_count':      run_stats.get('duplicates', 0),
        'errors_by_reason':      run_stats.get('errors_by_reason', {}),
        'deferred_count':        run_stats.get('deferred', 0),
        'deferred_by_reason':    run_stats.get('deferred_by_reason', {}),
        'translation_rate':      run_stats.get('translation_success_rate', 0),
        'llm_score_rate':        run_stats.get('llm_score_rate', 0),
        'translation_provider':  run_stats.get('translation_provider', 'none'),
        # Modèles réellement servis (champ "model" des réponses), par fiche écrite ou simulée
        'models_used':           run_stats.get('models_used', {}),
        'providers_used':        run_stats.get('providers_used', {}),
        'llm_disabled':          run_stats.get('llm_disabled', {}),
        'profile_hash':          run_stats.get('profile_hash', ''),
        'llm_providers':         LLM_PROVIDERS,
        'require_llm':           REQUIRE_LLM,
        'max_new_per_run':       MAX_NEW_PER_RUN,
        'llm_scoring':           LLM_SCORING_ENABLED,
        'readme_llm_chars':      README_LLM_CHARS,
        'dry_run':               DRY_RUN,
        'max_repos':             MAX_REPOS,
        'interrupted':           run_stats.get('interrupted', False),
        'exit_code':             run_stats.get('exit_code'),
    })
    history = history[-STATS_HISTORY_MAX:]
    try:
        _atomic_write_json(STATS_FILE, history, indent=2)
    except OSError as e:
        _warn("save_execution_stats/write", e)

# =============================================================================
# HTTP AVEC RETRY ET BACKOFF EXPONENTIEL
# =============================================================================
def _parse_retry_after(value: Any) -> Optional[int]:
    """Retry-After en secondes ou au format date HTTP (RFC 9110)."""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return max(0, math.ceil(float(value)))
    except (ValueError, OverflowError):
        pass
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, math.ceil(dt.timestamp() - time.time()))


def _reset_wait(reset_value: Any) -> Optional[int]:
    """Attente jusqu'à X-RateLimit-Reset (secondes epoch, ou millisecondes)."""
    try:
        reset = float(str(reset_value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(reset):
        return None
    if reset > 1e11:   # horodatage en millisecondes
        reset /= 1000.0
    return max(1, math.ceil(reset - time.time()))


def _is_secondary_rate_limit(response) -> bool:
    try:
        text = response.text or ''
    except Exception:
        return False
    return 'secondary rate limit' in text.lower()


def _rate_limit_wait(response, attempt: int, is_github: bool) -> int:
    headers = response.headers or {}
    wait_s = _parse_retry_after(headers.get('Retry-After'))
    if wait_s is not None:
        return wait_s
    if headers.get('X-RateLimit-Remaining') == '0' and headers.get('X-RateLimit-Reset'):
        wait_s = _reset_wait(headers.get('X-RateLimit-Reset'))
        if wait_s is not None:
            return wait_s
    if is_github:
        return GITHUB_SECONDARY_RATE_LIMIT_WAIT
    return BACKOFF_FACTOR ** attempt


def http_request_with_retry(
    method:      str,
    url:         str,
    headers:     Dict,
    json_data:   Optional[Dict] = None,
    params:      Optional[Dict] = None,
    timeout:     Optional[int] = None,
    max_retries: Optional[int] = None,
    idempotent:  bool = True,
) -> Optional[requests.Response]:
    """Requête HTTP avec nouvelles tentatives.

    idempotent=False (création de page ou de base) : aucune nouvelle tentative sur
    Timeout, erreur de connexion ou 5xx — seul le 429 est réessayé — pour ne jamais
    créer deux fois la même fiche. Toute attente est plafonnée à MAX_WAIT_SECONDS :
    au-delà, la réponse est renvoyée sans attendre (échec rapide).
    Renvoie None si aucune réponse n'a été obtenue (cause : last_http_error()).
    """
    timeout     = DEFAULT_TIMEOUT if timeout is None else timeout
    max_retries = MAX_RETRIES if max_retries is None else max(1, max_retries)
    session     = get_session()
    is_github   = 'api.github.com' in url
    method      = method.upper()
    _set_last_http_error('')

    for attempt in range(1, max_retries + 1):
        last_attempt = attempt >= max_retries
        try:
            if method == 'GET':
                response = session.get(url, headers=headers, params=params, timeout=timeout)
            elif method == 'POST':
                response = session.post(url, headers=headers, json=json_data, timeout=timeout)
            else:
                raise ValueError(f"Méthode non supportée: {method}")
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            kind = 'timeout' if isinstance(e, requests.exceptions.Timeout) else 'connexion impossible'
            _set_last_http_error(kind)
            if idempotent and not last_attempt and not _STOP_EVENT.is_set():
                time.sleep(BACKOFF_FACTOR ** attempt)
                continue
            log(f"   ⚠️  {method} {url[:80]} — {kind}", 'verbose')
            return None
        except Exception as e:
            _set_last_http_error(type(e).__name__)
            _warn(f"http_request_with_retry({url[:60]})", e)
            return None

        status = response.status_code
        if status in (200, 201):
            return response

        rate_limited = status == 429
        if status == 403 and idempotent:
            h = response.headers or {}
            if (h.get('Retry-After')
                    or (h.get('X-RateLimit-Remaining') == '0' and h.get('X-RateLimit-Reset'))
                    or (is_github and _is_secondary_rate_limit(response))):
                rate_limited = True

        if rate_limited:
            if last_attempt or _STOP_EVENT.is_set():
                return response
            wait_s = _rate_limit_wait(response, attempt, is_github)
            if wait_s > MAX_WAIT_SECONDS:
                log(f"⏳ Rate limit ({status}) — attente demandée {wait_s}s > plafond "
                    f"MAX_WAIT_SECONDS={MAX_WAIT_SECONDS}s : requête abandonnée")
                return response
            log(f"⏳ Rate limit ({status}) — attente {wait_s}s")
            time.sleep(wait_s)
            continue

        if 500 <= status < 600 and idempotent and not last_attempt and not _STOP_EVENT.is_set():
            time.sleep(BACKOFF_FACTOR ** attempt)
            continue

        return response

    return None


def _describe_failure(response, hints: Optional[Dict[int, str]] = None) -> str:
    """Code HTTP + message de l'API + piste éventuelle, ou cause réseau si pas de réponse."""
    if response is None:
        return f"pas de réponse ({last_http_error()}) — réseau ou timeout"
    msg  = _api_error_message(response)
    text = f"HTTP {response.status_code}" + (f" — {msg}" if msg else "")
    hint = (hints or {}).get(response.status_code)
    if hint:
        text += f"\n   → Piste : {hint}"
    return text

# =============================================================================
# VALIDATION DES TOKENS
# =============================================================================
GITHUB_AUTH_STATUS = 'absent'   # 'ok' après validation réussie du jeton
GITHUB_LOGIN       = ''


def validate_all_tokens() -> bool:
    global GITHUB_AUTH_STATUS, GITHUB_LOGIN
    log("🔐 Validation des tokens...\n")
    all_valid = True
    GITHUB_AUTH_STATUS, GITHUB_LOGIN = 'absent', ''

    if NOTION_TOKEN:
        response = http_request_with_retry(
            'GET', 'https://api.notion.com/v1/users/me', NOTION_HEADERS, timeout=10)
        if response is None:
            log(f"   ❌ Notion injoignable ({last_http_error()}) — vérifiez la connexion réseau", 'error')
            all_valid = False
        elif response.status_code == 200:
            log(f"   ✅ Notion: {(_json_dict(response) or {}).get('name') or 'OK'}")
        elif response.status_code == 401:
            log(f"   ❌ NOTION_TOKEN invalide ou révoqué (HTTP 401, {_mask_token(NOTION_TOKEN)})", 'error')
            all_valid = False
        else:
            log(f"   ❌ Notion: {_describe_failure(response)} ({_mask_token(NOTION_TOKEN)})", 'error')
            all_valid = False
    else:
        log("   ❌ NOTION_TOKEN manquant", 'error')
        all_valid = False

    if GITHUB_TOKEN:
        response = http_request_with_retry(
            'GET', 'https://api.github.com/user', GITHUB_HEADERS, timeout=10)
        if response is None:
            log(f"   ❌ GitHub injoignable ({last_http_error()}) — vérifiez la connexion réseau", 'error')
            all_valid = False
        elif response.status_code == 200:
            u    = _json_dict(response) or {}
            plan = u.get('plan') if isinstance(u.get('plan'), dict) else {}
            GITHUB_AUTH_STATUS, GITHUB_LOGIN = 'ok', str(u.get('login') or '')
            log(f"   ✅ GitHub: {GITHUB_LOGIN or 'OK'} ({plan.get('name', 'free')})")
        elif response.status_code in (401, 403):
            if response.status_code == 403 and (response.headers or {}).get('X-RateLimit-Remaining') == '0':
                log("   ❌ Quota de l'API GitHub épuisé pour ce jeton — réessayez plus tard", 'error')
            else:
                log(f"   ❌ GITHUB_TOKEN invalide ou expiré (HTTP {response.status_code}, "
                    f"{_mask_token(GITHUB_TOKEN)}) — régénérez-le, ou videz GITHUB_TOKEN "
                    "pour travailler sans jeton (60 req/h)", 'error')
            all_valid = False
        else:
            log(f"   ❌ GitHub injoignable ({_describe_failure(response)})", 'error')
            all_valid = False
    else:
        log("   ⚠️  GITHUB_TOKEN absent (rate limit 60 req/h)")

    log("")
    return all_valid

# =============================================================================
# FOURNISSEURS LLM — état du run (coupe-circuit, budget, limiteur de débit)
# =============================================================================
LLM_ENDPOINTS = {
    'mistral':    'https://api.mistral.ai/v1/chat/completions',
    'openrouter': 'https://openrouter.ai/api/v1/chat/completions',
}
OPENROUTER_KEY_URL = 'https://openrouter.ai/api/v1/key'   # lecture de la clé : ne consomme aucun quota
_PROVIDER_NAMES    = {'mistral': 'Mistral AI', 'openrouter': 'OpenRouter'}
_PROVIDER_KEY_VARS = {'mistral': 'MISTRAL_API_KEY', 'openrouter': 'OPENROUTER_API_KEY'}
_OPENROUTER_DAILY_QUOTA_MARKERS = ('per-day', 'per day', 'daily')


class LLMProviderState:
    """État d'un fournisseur pendant le run, partagé entre threads : coupe-circuit,
    budget de requêtes (quota gratuit OpenRouter) et intervalle minimal entre requêtes."""

    def __init__(self, name: str, rpm: int):
        self.name                       = name
        self._lock                      = Lock()
        self.disabled_reason: Optional[str] = None
        self.consecutive_failures       = 0
        self.budget: Optional[int]      = None    # requêtes restantes ; None = non limité
        self.min_interval               = 60.0 / rpm if rpm > 0 else 0.0
        self._next_slot                 = 0.0
        self.dropped_params: Set[str]   = set()   # paramètres refusés au test de démarrage

    @property
    def available(self) -> bool:
        with self._lock:
            return self.disabled_reason is None

    def disable(self, reason: str) -> None:
        with self._lock:
            if self.disabled_reason is not None:
                return
            self.disabled_reason = reason
        log(f"   ⛔ {_provider_label(self.name)} désactivé pour la suite du run : {reason}")

    def record_success(self) -> None:
        with self._lock:
            self.consecutive_failures = 0

    def record_failure(self, reason: str) -> None:
        with self._lock:
            self.consecutive_failures += 1
            count = self.consecutive_failures
        if count >= LLM_BREAKER_THRESHOLD:
            self.disable(f"{count} échecs consécutifs (dernier : {reason})")

    def try_consume(self) -> bool:
        """Réserve une requête sur le budget. Budget épuisé → fournisseur désactivé."""
        with self._lock:
            if self.disabled_reason is not None:
                return False
            if self.budget is None:
                return True
            if self.budget > 0:
                self.budget -= 1
                return True
        self.disable("quota gratuit du jour épuisé (budget lu au démarrage)")
        return False

    def wait_turn(self) -> None:
        """Limiteur de débit côté client : réserve le prochain créneau puis attend."""
        if self.min_interval <= 0:
            return
        with self._lock:
            now   = time.monotonic()
            start = max(now, self._next_slot)
            self._next_slot = start + self.min_interval
        if start > now:
            time.sleep(start - now)


class NewRepoBudget:
    """MAX_NEW_PER_RUN : une place est réservée AVANT l'appel GitHub et rendue si aucune
    fiche n'est finalement écrite (déjà présent, filtré, erreur, reporté)."""

    def __init__(self, limit: int):
        self.limit = limit
        self.used  = 0
        self._lock = Lock()

    def acquire(self) -> bool:
        if self.limit <= 0:
            return True
        with self._lock:
            if self.used >= self.limit:
                return False
            self.used += 1
            return True

    def release(self) -> None:
        if self.limit <= 0:
            return
        with self._lock:
            self.used = max(0, self.used - 1)


def _new_llm_states() -> Dict[str, LLMProviderState]:
    return {'mistral':    LLMProviderState('mistral', MISTRAL_RPM),
            'openrouter': LLMProviderState('openrouter', OPENROUTER_RPM)}


LLM_STATES: Dict[str, LLMProviderState] = _new_llm_states()
NEW_REPO_BUDGET = NewRepoBudget(MAX_NEW_PER_RUN)
_ANNOUNCED: Set[str] = set()
_announce_lock = Lock()


def reset_llm_runtime() -> None:
    """État neuf pour un run (appelé par _run)."""
    global LLM_STATES, NEW_REPO_BUDGET
    LLM_STATES      = _new_llm_states()
    NEW_REPO_BUDGET = NewRepoBudget(MAX_NEW_PER_RUN)
    with _announce_lock:
        _ANNOUNCED.clear()


def _announce_once(key: str, msg: str, level: str = 'normal') -> bool:
    """Affiche un message une seule fois par run ; renvoie False s'il l'a déjà été."""
    with _announce_lock:
        if key in _ANNOUNCED:
            return False
        _ANNOUNCED.add(key)
    log(msg, level)
    return True


def _provider_state(provider: str) -> LLMProviderState:
    state = LLM_STATES.get(provider)
    if state is None:
        state = LLM_STATES.setdefault(provider, LLMProviderState(provider, 0))
    return state


def _provider_model(provider: str) -> str:
    return MISTRAL_MODEL if provider == 'mistral' else OPENROUTER_MODEL


def _provider_label(provider: str) -> str:
    return f"{_PROVIDER_NAMES.get(provider, provider)} ({_provider_model(provider)})"


def _provider_key(provider: str) -> str:
    return {'mistral': MISTRAL_API_KEY, 'openrouter': OPENROUTER_API_KEY}.get(provider, '')


def _provider_headers(provider: str) -> Dict[str, str]:
    return MISTRAL_HEADERS if provider == 'mistral' else OPENROUTER_HEADERS


def configured_providers() -> List[str]:
    """Fournisseurs retenus au démarrage, dans l'ordre d'essai."""
    return [p for p in (TRANSLATION_PROVIDER, TRANSLATION_FALLBACK) if p]


def llm_required() -> bool:
    """Mode reprise actif : aucune fiche sans réponse LLM valide."""
    return REQUIRE_LLM and TRANSLATION_ENABLED


def llm_available() -> bool:
    """Au moins un fournisseur retenu et non désactivé par le coupe-circuit."""
    return TRANSLATION_ENABLED and any(_provider_state(p).available for p in configured_providers())


def _openrouter_model_is_free() -> bool:
    model = OPENROUTER_MODEL.lower()
    return model == 'openrouter/free' or model.endswith(':free')


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _response_text(response) -> str:
    try:
        return response.text or ''
    except Exception:
        return ''

# =============================================================================
# CORPS DES REQUÊTES LLM (mêmes paramètres pour le test de démarrage et la production)
# =============================================================================
def _llm_json_schema() -> Dict:
    properties: Dict[str, Any] = {
        'description_fr': {'type': 'string'},
        'use_cases_fr':   {'type': 'string'},
    }
    if LLM_SCORING_ENABLED:
        # Bornes en description (minimum/maximum ne sont pas acceptés partout en mode strict) ;
        # le score reste validé côté client (_coerce_score)
        properties['score']     = {'type': 'integer', 'description': 'entier de 0 à 10'}
        properties['reasoning'] = {'type': 'string'}
    return {'type': 'json_schema', 'json_schema': {
        'name': 'gitnotate', 'strict': True,
        'schema': {'type': 'object', 'properties': properties,
                   'required': list(properties), 'additionalProperties': False},
    }}


def build_llm_body(provider: str, messages: List[Dict], temperature: float, max_tokens: int) -> Dict:
    body: Dict[str, Any] = {
        'model':       _provider_model(provider),
        'messages':    messages,
        'temperature': temperature,
    }
    if provider == 'mistral':
        dropped = _provider_state('mistral').dropped_params
        body['max_tokens'] = max_tokens
        if MISTRAL_RESPONSE_FORMAT == 'json_object' and 'response_format' not in dropped:
            body['response_format'] = {'type': 'json_object'}
        if MISTRAL_REASONING_EFFORT and 'reasoning_effort' not in dropped:
            body['reasoning_effort'] = MISTRAL_REASONING_EFFORT
    else:
        # max_tokens est déprécié chez OpenRouter ; aucun paramètre de raisonnement envoyé
        # (certains modèles gratuits le refusent)
        body['max_completion_tokens'] = max_tokens
        if OPENROUTER_RESPONSE_FORMAT == 'json_object':
            body['response_format'] = {'type': 'json_object'}
        elif OPENROUTER_RESPONSE_FORMAT == 'json_schema':
            body['response_format'] = _llm_json_schema()
        if OPENROUTER_DATA_COLLECTION == 'deny':
            body['provider'] = {'data_collection': 'deny'}
    return body

# =============================================================================
# TESTS DE DÉMARRAGE DES FOURNISSEURS
# =============================================================================
_PROBE_MESSAGES  = [{'role': 'user', 'content': 'Réponds uniquement par ce JSON : {"ok": true}'}]
PROBE_MAX_TOKENS = 16


def _probe_openrouter() -> Tuple[bool, str]:
    """GET /api/v1/key : validité de la clé et quota gratuit du jour, sans consommer de quota."""
    name  = _provider_label('openrouter')
    state = _provider_state('openrouter')
    try:
        response = get_session().get(OPENROUTER_KEY_URL,
                                     headers={'Authorization': f'Bearer {OPENROUTER_API_KEY}'},
                                     timeout=15)
    except requests.exceptions.Timeout:
        return False, f"⚠️  {name} — injoignable (timeout) : ignoré pour ce run"
    except requests.exceptions.ConnectionError:
        return False, f"⚠️  {name} — injoignable (connexion impossible) : ignoré pour ce run"
    except Exception as e:
        return False, f"⚠️  {name} — injoignable ({type(e).__name__}) : ignoré pour ce run"

    detail = _api_error_text(response)
    suffix = f" — {detail}" if detail else ""
    if response.status_code == 401:
        return False, (f"❌ {name} — clé invalide (HTTP 401{suffix}, "
                       f"{_mask_token(OPENROUTER_API_KEY)}) : ignoré")
    if response.status_code != 200:
        return False, f"❌ {name} — test de la clé en échec (HTTP {response.status_code}{suffix}) : ignoré"

    data  = (_json_dict(response) or {}).get('data')
    quota = data.get('free_model_daily_requests') if isinstance(data, dict) else None
    quota = quota if isinstance(quota, dict) else {}
    limit, remaining = _int_or_none(quota.get('limit')), _int_or_none(quota.get('remaining'))
    if remaining is None:
        return True, f"✅ {name} — clé valide (quota gratuit non communiqué)"
    quota_text = (f"quota gratuit : {remaining}/{'?' if limit is None else limit} "
                  "(remis à zéro à minuit UTC)")
    if not _openrouter_model_is_free():
        return True, f"✅ {name} — clé valide ; {quota_text}, non applicable (modèle payant)"
    if remaining <= 0:
        return False, f"⛔ {name} — {quota_text} : quota épuisé, OpenRouter désactivé pour ce run"
    state.budget = remaining
    return True, f"✅ {name} — clé valide ; {quota_text}"


def _probe_mistral() -> Tuple[bool, str]:
    """Petite complétion avec les paramètres de production (max_tokens 16). Un paramètre
    optionnel refusé (400/422 qui le mentionne) est retiré pour tout le run."""
    name  = _provider_label('mistral')
    state = _provider_state('mistral')
    for _ in range(3):
        body = build_llm_body('mistral', _PROBE_MESSAGES, 0.1, PROBE_MAX_TOKENS)
        state.wait_turn()
        try:
            response = get_session().post(LLM_ENDPOINTS['mistral'], headers=MISTRAL_HEADERS,
                                          json=body, timeout=min(LLM_TIMEOUT, 30))
        except requests.exceptions.Timeout:
            return False, f"⚠️  {name} — indisponible (timeout) : ignoré pour ce run"
        except requests.exceptions.ConnectionError:
            return False, f"⚠️  {name} — indisponible (connexion impossible) : ignoré pour ce run"
        except Exception as e:
            return False, f"⚠️  {name} — indisponible ({type(e).__name__}) : ignoré pour ce run"

        status = response.status_code
        detail = _api_error_text(response)
        suffix = f" — {detail}" if detail else ""
        if status == 200:
            note = (f" (sans {', '.join(sorted(state.dropped_params))}, mémorisé pour ce run)"
                    if state.dropped_params else "")
            return True, f"✅ {name} — OK{note}"
        if status in (400, 422):
            raw = _response_text(response).lower()
            if 'reasoning' in raw and 'reasoning_effort' in body:
                dropped = 'reasoning_effort'
            elif (any(m in raw for m in ('response_format', 'response format', 'json_object'))
                  and 'response_format' in body):
                dropped = 'response_format'
            else:
                return False, f"❌ {name} — requête refusée (HTTP {status}{suffix})"
            state.dropped_params.add(dropped)
            log(f"   ⚠️  {name} — paramètre {dropped} refusé (HTTP {status}{suffix}) : "
                "nouvel essai sans ce paramètre")
            continue
        if status == 401:
            return False, f"❌ {name} — clé invalide (HTTP 401{suffix}, {_mask_token(MISTRAL_API_KEY)})"
        if status == 404:
            return False, f"❌ {name} — modèle '{MISTRAL_MODEL}' introuvable (HTTP 404{suffix})"
        if status == 429:
            return True, f"⚠️  {name} — joignable mais limité (HTTP 429{suffix}) : gardé actif"
        return False, f"❌ {name} — indisponible (HTTP {status}{suffix}) : ignoré pour ce run"
    return False, f"❌ {name} — requête refusée même sans les paramètres optionnels"


def init_translation_providers() -> Tuple[Optional[str], Optional[str]]:
    """Teste les fournisseurs dans l'ordre LLM_PROVIDERS ; renvoie (primaire, secours).
    Un échec n'est jamais présenté comme « OK »."""
    if not TRANSLATION_ENABLED:
        log("   ℹ️  Traduction désactivée (TRANSLATION_ENABLED=false) — scoring lexical, REQUIRE_LLM sans effet")
        return None, None

    log(f"🔍 Détection des fournisseurs LLM (ordre : {' → '.join(LLM_PROVIDERS)})...")
    active: List[str] = []
    for provider in LLM_PROVIDERS:
        if not _provider_key(provider):
            log(f"   ℹ️  {_provider_label(provider)} ignoré : {_PROVIDER_KEY_VARS[provider]} absente")
            continue
        ok, msg = _probe_mistral() if provider == 'mistral' else _probe_openrouter()
        log(f"   {msg}", 'error' if msg.startswith('❌') else 'normal')
        if ok:
            active.append(provider)

    primary  = active[0] if active else None
    fallback = active[1] if len(active) > 1 else None
    if primary and fallback:
        log(f"   💡 Stratégie: {_provider_label(primary)} (primaire) → {_provider_label(fallback)} (secours)")
    elif primary:
        log(f"   💡 Stratégie: {_provider_label(primary)} uniquement")
    elif llm_required():
        log("   ❌ Aucun fournisseur LLM disponible", 'error')
    else:
        log("   ❌ Aucun fournisseur LLM disponible — scoring lexical uniquement (REQUIRE_LLM=false)", 'error')
    log("")
    return primary, fallback

# =============================================================================
# APPEL API LLM — unifié Mistral + OpenRouter
# Ne lève jamais d'exception : renvoie (texte, modèle réellement servi) ou None.
# =============================================================================
_REASONING_BLOCK_TYPES = {'thinking', 'reasoning'}


def _normalize_llm_content(content: Any) -> str:
    """Contenu texte d'une réponse : chaîne, ou liste de blocs {"type": "text", "text": ...}
    (formats OpenAI et Mistral) ; les blocs de raisonnement sont ignorés."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict) or block.get('type') in _REASONING_BLOCK_TYPES:
                continue
            if block.get('type') == 'text' and isinstance(block.get('text'), str):
                parts.append(block['text'])
        return ''.join(parts).strip()
    return ''


def _openrouter_quota_exhausted(response) -> bool:
    """429 d'OpenRouter dû au quota (X-RateLimit-Remaining à 0 ou message de quota journalier)."""
    if (response.headers or {}).get('X-RateLimit-Remaining') == '0':
        return True
    text = f"{_api_error_message(response, 500)} {_response_text(response)[:1000]}".lower()
    return any(marker in text for marker in _OPENROUTER_DAILY_QUOTA_MARKERS)


def _call_translation_api(provider: str, messages: List[Dict],
                          temperature: float = 0.3) -> Optional[Tuple[str, str]]:
    """Un appel LLM avec le timeout LLM_TIMEOUT. Pas de nouvelle tentative sur timeout ou
    coupure (fournisseur suivant) ; au plus une sur 429 ou 5xx, après une attente ≤ 60 s.
    Chaque échec est signalé au coupe-circuit du fournisseur."""
    if provider not in LLM_ENDPOINTS:
        return None
    state     = _provider_state(provider)
    requested = _provider_model(provider)
    try:
        body     = build_llm_body(provider, messages, temperature, LLM_MAX_TOKENS)
        response = None
        for attempt in (1, 2):
            if _STOP_EVENT.is_set() or not state.try_consume():
                return None
            state.wait_turn()
            if _STOP_EVENT.is_set():          # Ctrl-C pendant l'attente du limiteur
                return None
            try:
                response = get_session().post(LLM_ENDPOINTS[provider], headers=_provider_headers(provider),
                                              json=body, timeout=LLM_TIMEOUT)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                kind = 'timeout' if isinstance(e, requests.exceptions.Timeout) else 'connexion impossible'
                log(f"   ⚠️  {provider} : pas de réponse ({kind}) — fournisseur suivant", 'verbose')
                state.record_failure(kind)
                return None

            status = response.status_code
            if status == 200:
                break
            detail = _api_error_text(response)
            reason = f"HTTP {status}" + (f" — {detail}" if detail else "")
            if status in (401, 402):
                state.disable(("clé refusée" if status == 401 else "crédits insuffisants") + f" ({reason})")
                return None
            if status == 429 and provider == 'openrouter' and _openrouter_quota_exhausted(response):
                state.disable(f"quota OpenRouter épuisé ({reason})")
                return None
            if attempt == 1 and (status == 429 or 500 <= status < 600):
                wait_s = BACKOFF_FACTOR
                if status == 429:
                    retry_after = _parse_retry_after((response.headers or {}).get('Retry-After'))
                    wait_s = BACKOFF_FACTOR if retry_after is None else retry_after
                cap = min(LLM_RETRY_WAIT_MAX, MAX_WAIT_SECONDS)
                if wait_s <= cap:
                    log(f"   ⏳ {provider} : {reason} — nouvelle tentative dans {wait_s}s", 'verbose')
                    if wait_s > 0:
                        time.sleep(wait_s)
                    continue
                log(f"   ⏳ {provider} : attente demandée {wait_s}s > {cap}s — fournisseur suivant", 'verbose')
            log(f"   ⚠️  {provider} : {reason}", 'verbose')
            state.record_failure(reason)
            return None

        payload = _json_dict(response)
        choices = payload.get('choices') if payload else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            log(f"   ⚠️  {provider} : réponse sans 'choices' exploitable", 'verbose')
            state.record_failure("réponse sans 'choices'")
            return None
        choice = choices[0]
        if choice.get('finish_reason') == 'length':
            log(f"   ⚠️  {provider} : réponse tronquée (finish_reason=length)", 'verbose')
            state.record_failure("réponse tronquée (finish_reason=length)")
            return None
        message = choice.get('message') if isinstance(choice.get('message'), dict) else {}
        text = _normalize_llm_content(message.get('content'))
        if not text:
            log(f"   ⚠️  {provider} : réponse vide", 'verbose')
            state.record_failure("réponse vide")
            return None
        served = payload.get('model')
        model  = served.strip() if isinstance(served, str) and served.strip() else requested
        return text, model
    except Exception as e:
        _warn(f"_call_translation_api/{provider}", e)
        state.record_failure(type(e).__name__)
        return None

# =============================================================================
# RÉPONSE LLM — parsing tolérant et validation
# =============================================================================
_JSON_FENCE_RE = re.compile(r'```(?:json)?\s*(.*?)```', re.IGNORECASE | re.DOTALL)


def _parse_llm_json(raw_text: str) -> Optional[Dict]:
    """Extrait l'objet JSON d'une réponse : bloc ```json, texte autour, sauts de ligne
    littéraux dans les chaînes (strict=False)."""
    if not isinstance(raw_text, str):
        return None
    text = raw_text.strip()
    candidates = [m.group(1) for m in _JSON_FENCE_RE.finditer(text)] + [text]
    decoder = json.JSONDecoder(strict=False)
    first_dict: Optional[Dict] = None
    for candidate in candidates:
        start = candidate.find('{')
        tries = 0
        while start != -1 and tries < 20:
            tries += 1
            try:
                obj, _ = decoder.raw_decode(candidate, start)
            except ValueError:
                obj = None
            if isinstance(obj, dict):
                if 'description_fr' in obj:
                    return obj
                if first_dict is None:
                    first_dict = obj
            start = candidate.find('{', start + 1)
    return first_dict


def _coerce_score(value: Any) -> Optional[int]:
    """Score 0-10 : int/float ou chaîne numérique ; booléen refusé ; hors bornes → None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip().replace(',', '.'))
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number) or not 0 <= number <= 10:
        return None
    return int(round(number))


def _clean_use_cases(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        lines = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip().lstrip('•-*–').strip()
            if text:
                lines.append(f"• {text}")
        return '\n'.join(lines)
    return None


def _validate_llm_payload(parsed: Any, need_score: bool) -> Tuple[Optional[Dict], str]:
    """Renvoie (champs nettoyés, '') ou (None, raison). Un score invalide n'invalide pas
    la traduction : il est renvoyé à None."""
    if not isinstance(parsed, dict):
        return None, "pas d'objet JSON"
    description = parsed.get('description_fr')
    if not isinstance(description, str) or not description.strip():
        return None, "description_fr absente ou vide"
    use_cases = _clean_use_cases(parsed.get('use_cases_fr'))
    if use_cases is None:
        return None, "use_cases_fr ni chaîne ni liste"
    cleaned: Dict[str, Any] = {
        'description_fr': description.strip(),
        'use_cases_fr':   use_cases,
        'score':          None,
        'reasoning':      '',
    }
    if need_score:
        reasoning = parsed.get('reasoning')
        if reasoning is None or isinstance(reasoning, str):
            cleaned['score']     = _coerce_score(parsed.get('score'))
            cleaned['reasoning'] = (reasoning or '').strip()[:REASONING_MAX_CHARS]
    return cleaned, ''

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
    updated_at = repo_info.get('updated_at') or ''
    if not updated_at:
        return True
    try:
        days_old = (datetime.now(timezone.utc).timestamp() - _parse_github_date(updated_at)) / 86400
        return days_old <= MIN_UPDATE_DAYS
    except (ValueError, OSError) as e:
        _warn("is_repo_recent_enough", e)
        return True

# =============================================================================
# PROGRESS BAR — uniquement dans un terminal interactif
# =============================================================================
def _progress_enabled() -> bool:
    if LOG_LEVEL == 'quiet':
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


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
    with print_lock:
        print(f"\r  {bar} {progress * 100:.1f}% | {current}/{total} | ETA: {eta_str} ", end='', flush=True)

# =============================================================================
# SCORING LEXICAL — fallback si LLM indisponible
# =============================================================================
def calculate_relevance_score(repo_info: Dict) -> int:
    score      = 0
    language   = (repo_info.get('language') or '').lower()
    desc       = (repo_info.get('description') or '').lower()
    topics     = [t.lower() for t in (repo_info.get('topics') or []) if isinstance(t, str)]
    topics_str = ' '.join(topics)
    readme     = (repo_info.get('readme') or '').lower()

    # Égalité stricte : 'java' ne correspond plus à 'javascript'
    if language and any(language == lang.lower() for lang in _profile_list('languages')):
        score += 3

    fw_found = sum(
        1 for fw in _profile_list('frameworks')
        if fw.lower() in desc or fw.lower() in topics_str or fw.lower() in readme[:500]
    )
    score += min(fw_found * 2, 4)

    score += min(sum(1 for d in _profile_list('domains') if d in desc or d in topics_str), 3)
    score += min(sum(1 for i in _profile_list('interests')
                     if i.replace('-', ' ') in desc or i in topics_str), 2)
    score += min(sum(1 for t in _profile_list('infra')
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
        if not any(d in topics_str for d in _profile_list('domains')):
            score = max(score - 2, 0)
    if any(t in topics_str for t in irrelevant_topics):
        score = max(score - 2, 0)

    return min(max(score, 0), 10)

# =============================================================================
# TRADUCTION + SCORING SÉMANTIQUE — README inclus dans le contexte
# =============================================================================
def translate_and_score(
    description: str,
    use_cases:   str,
    repo_info:   Dict,
    repo_name:   str = "",
) -> Dict[str, Any]:
    """Appel LLM unique : traduction EN→FR + scoring sémantique avec contexte README.

    Le README (README_LLM_CHARS premiers caractères) est inclus dans le message
    utilisateur. Chaque réponse est analysée et validée DANS la cascade : une réponse
    vide, tronquée, non JSON ou invalide fait passer au fournisseur suivant. Les
    fournisseurs désactivés par le coupe-circuit sont sautés.

    Le résultat porte 'provider', 'model' (modèle réellement servi), 'profile_hash' et
    'llm_status' : 'ok' (réponse valide), 'partial' (traduction valide, score invalide),
    'failed' (aucune réponse valide), 'unavailable' (aucun fournisseur utilisable) ou
    'not_requested' (aucun LLM nécessaire). En mode reprise (REQUIRE_LLM), seuls 'ok' et
    'not_requested' donnent une fiche ; sinon le score lexical sert de repli.
    """
    description = description or ''
    use_cases   = use_cases or ''
    result: Dict[str, Any] = {
        'description_fr': description,
        'use_cases_fr':   use_cases,
        'score':          None,
        'reasoning':      '',
        'translated':     False,
        'provider':       None,
        'model':          None,
        'scoring_method': 'lexical',
        'llm_status':     'not_requested',
        'profile_hash':   compute_profile_hash(),
    }

    already_fr = detect_language(description) == 'fr'
    providers  = configured_providers()

    # Cas 1: traduction désactivée ou aucun provider
    if not TRANSLATION_ENABLED or not providers:
        result['llm_status']     = 'unavailable' if TRANSLATION_ENABLED else 'not_requested'
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

        readme_preview = ((repo_info.get('readme') or '')[:README_LLM_CHARS].strip()
                          if README_LLM_CHARS > 0 else '')
        topics = [t for t in (repo_info.get('topics') or []) if isinstance(t, str)]

        user_content = (
            f"Nom du repo: {repo_info.get('name') or 'N/A'}\n"
            f"Langage principal: {repo_info.get('language') or 'N/A'}\n"
            f"Topics GitHub: {', '.join(topics) or 'aucun'}\n"
            f"Stars: {repo_info.get('stars') or 0}\n"
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

    # Cascade dans l'ordre LLM_PROVIDERS : parsing et validation DANS la boucle
    chosen: Optional[Dict] = None
    chosen_provider: Optional[str] = None
    chosen_model: Optional[str] = None
    partial: Optional[Dict] = None          # traduction valide mais score invalide
    partial_provider: Optional[str] = None
    partial_model: Optional[str] = None
    attempted = False
    for provider in providers:
        state = _provider_state(provider)
        if not state.available:
            log(f"   ⏭️  [{repo_name}] {provider} désactivé pour ce run — ignoré", 'verbose')
            continue
        attempted = True
        answer = _call_translation_api(provider, messages, temperature)
        if isinstance(answer, tuple) and len(answer) == 2:
            raw_text, model = answer
        else:                                   # texte seul (compatibilité)
            raw_text, model = answer, _provider_model(provider)
        if not raw_text:
            log(f"   ⚠️  [{repo_name}] {provider} échec — basculement fallback", 'verbose')
            continue
        parsed = _parse_llm_json(raw_text)
        cleaned, why = (_validate_llm_payload(parsed, LLM_SCORING_ENABLED) if parsed is not None
                        else (None, "aucun JSON trouvé"))
        if cleaned is None:
            log(f"   ⚠️  [{repo_name}] {provider} ({model}) : réponse invalide ({why}) — "
                "basculement fallback", 'verbose')
            state.record_failure(f"réponse invalide ({why})")
            continue
        if LLM_SCORING_ENABLED and cleaned['score'] is None:
            log(f"   ⚠️  [{repo_name}] {provider} ({model}) : score LLM invalide "
                f"('{str(parsed.get('score'))[:20]}') — basculement fallback", 'verbose')
            state.record_failure("score invalide")
            if partial is None:
                partial, partial_provider, partial_model = cleaned, provider, model
            continue
        state.record_success()
        chosen, chosen_provider, chosen_model = cleaned, provider, model
        break

    if chosen is not None:
        result['llm_status'] = 'ok'
    elif partial is not None:
        result['llm_status'] = 'partial'
        chosen, chosen_provider, chosen_model = partial, partial_provider, partial_model
    else:
        result['llm_status'] = 'failed' if attempted else 'unavailable'

    # Fallback total : aucune réponse exploitable
    if chosen is None:
        stats.inc('translation_failed')
        result['score']          = calculate_relevance_score(repo_info)
        result['scoring_method'] = 'lexical'
        stats.inc('llm_score_fallback')
        return result

    result['description_fr'] = chosen['description_fr']
    result['use_cases_fr']   = chosen['use_cases_fr']
    result['translated']     = True
    result['provider']       = chosen_provider
    result['model']          = chosen_model
    stats.inc('translation_success')

    if LLM_SCORING_ENABLED and chosen['score'] is not None:
        result['score']          = chosen['score']
        result['reasoning']      = chosen['reasoning']
        result['scoring_method'] = 'llm'
        stats.inc('llm_score_success')
        log(f"   🧠 [{repo_name}] Score LLM: {result['score']}/10 — {result['reasoning']}", 'verbose')
    else:
        result['score']          = calculate_relevance_score(repo_info)
        result['scoring_method'] = 'lexical'
        stats.inc('llm_score_fallback')
        if LLM_SCORING_ENABLED:
            log(f"   ⚠️  [{repo_name}] Score LLM invalide → fallback lexical", 'verbose')

    return result

# =============================================================================
# NOTION — EXTRACTION DES BLOCS (lecture complète ou PartialReadError)
# =============================================================================
class PartialReadError(Exception):
    """Lecture Notion incomplète : le run s'arrête sans rien créer."""


def get_all_blocks_recursive(
    block_id: str, blocks: Optional[List] = None, depth: int = 0, max_depth: int = 50
) -> List[Dict]:
    """Lit tous les blocs de la page (sous-blocs compris).
    Tout échec (racine, curseur, sous-bloc) lève PartialReadError."""
    if blocks is None:
        blocks = []
    if depth >= max_depth:
        raise PartialReadError(f"profondeur maximale ({max_depth}) atteinte sous le bloc {block_id[:8]}")
    url          = f"https://api.notion.com/v1/blocks/{block_id}/children"
    start_cursor = None
    first_page   = True
    while True:
        params = {'page_size': 100}
        if start_cursor:
            params['start_cursor'] = start_cursor
        response = http_request_with_retry('GET', url, NOTION_HEADERS, params=params)
        if response is not None and response.status_code in (403, 404) and depth == 0 and first_page:
            raise PartialReadError(
                f"page source introuvable ou non partagée avec l'intégration "
                f"(HTTP {response.status_code}) — dans Notion : page source → ••• → Connexions → "
                f"ajoutez votre intégration ; vérifiez aussi PARENT_PAGE_ID")
        if response is None or response.status_code not in (200, 201):
            raise PartialReadError(f"bloc {block_id[:8]} : {_describe_failure(response)}")
        data = _json_dict(response)
        if data is None:
            raise PartialReadError(f"bloc {block_id[:8]} : réponse Notion illisible")
        for block in data.get('results') or []:
            if not isinstance(block, dict):
                continue
            blocks.append(block)
            if block.get('has_children', False) and block.get('id'):
                get_all_blocks_recursive(block['id'], blocks, depth + 1, max_depth)
        if not data.get('has_more', False):
            break
        start_cursor = data.get('next_cursor')
        if not start_cursor:
            raise PartialReadError(f"bloc {block_id[:8]} : has_more sans next_cursor")
        first_page = False
    return blocks

# =============================================================================
# URLS GITHUB — une seule fonction de parsing
# =============================================================================
GITHUB_HOSTS = {'github.com', 'www.github.com'}
# Premiers segments de chemin qui ne désignent pas un dépôt
RESERVED_GITHUB_PATHS = {
    'topics', 'orgs', 'sponsors', 'marketplace', 'settings', 'features', 'collections',
    'trending', 'explore', 'login', 'apps', 'about', 'pricing', 'enterprise', 'search',
    'notifications', 'issues', 'pulls', 'codespaces', 'users', 'site', 'security',
    'readme', 'new',
}
_PATH_SEGMENT_RE = re.compile(r'^[A-Za-z0-9_.-]+$')
_URL_IN_TEXT_RE  = re.compile(r'https?://(?:www\.)?github\.com/[^\s<>"«»]+', re.IGNORECASE)
_TRAILING_PUNCT  = '.,;:)]}>»"\''
_RICH_TEXT_EXCLUDED_TYPES = {'code'}


def _is_github_host(url: str) -> bool:
    try:
        parts = urlsplit((url or '').strip())
        host  = (parts.hostname or '').lower()
    except ValueError:
        return False
    return parts.scheme.lower() in ('http', 'https') and host in GITHUB_HOSTS


def parse_github_url(url: str) -> Tuple[Optional[Dict[str, str]], str]:
    """Renvoie ({'owner', 'repo'}, 'ok'), ou (None, 'hors_github' | 'non_depot')."""
    if not _is_github_host(url):
        return None, 'hors_github'
    segments = [s for s in urlsplit(url.strip()).path.split('/') if s]
    if len(segments) < 2:
        return None, 'non_depot'
    owner = segments[0]
    repo  = re.sub(r'\.git$', '', segments[1], flags=re.IGNORECASE)
    if owner.lower() in RESERVED_GITHUB_PATHS:
        return None, 'non_depot'
    if (not _PATH_SEGMENT_RE.match(owner) or not _PATH_SEGMENT_RE.match(repo)
            or not owner.strip('.') or not repo.strip('.')):
        return None, 'non_depot'
    return {'owner': owner, 'repo': repo}, 'ok'


def extract_github_info(url: str) -> Optional[Dict[str, str]]:
    return parse_github_url(url)[0]


def normalize_github_url(url: str) -> str:
    """Clé de dédoublonnage 'owner/repo' en minuscules (ou l'URL en minuscules)."""
    info = extract_github_info(url)
    if info:
        return f"{info['owner'].lower()}/{info['repo'].lower()}"
    return (url or '').strip().rstrip('/').lower()


def _urls_from_rich_text(rich_text: Any) -> List[str]:
    found: List[str] = []
    if not isinstance(rich_text, list):
        return found
    for obj in rich_text:
        if not isinstance(obj, dict):
            continue
        candidates: List[str] = []
        if obj.get('type') == 'text':
            text    = obj.get('text') if isinstance(obj.get('text'), dict) else {}
            content = text.get('content') or ''
            candidates += [m.rstrip(_TRAILING_PUNCT) for m in _URL_IN_TEXT_RE.findall(content)]
            link = text.get('link')
            if isinstance(link, dict) and isinstance(link.get('url'), str):
                candidates.append(link['url'])
        elif obj.get('type') == 'mention':
            mention = obj.get('mention') if isinstance(obj.get('mention'), dict) else {}
            for sub in ('link_preview', 'link_mention'):
                data = mention.get(sub) if isinstance(mention.get(sub), dict) else {}
                for key in ('url', 'href'):
                    if isinstance(data.get(key), str):
                        candidates.append(data[key])
        if isinstance(obj.get('href'), str):
            candidates.append(obj['href'])
        seen: Set[str] = set()
        for candidate in candidates:
            candidate = candidate.strip()
            if candidate and candidate not in seen and _is_github_host(candidate):
                seen.add(candidate)
                found.append(candidate)
    return found


def extract_urls_from_blocks(blocks: List[Dict]) -> List[str]:
    """Liens github.com de tous les blocs : bookmark/embed/link_preview, tout bloc à
    rich_text (sauf code), cellules de tableau, liens et mentions (href)."""
    github_urls: List[str] = []
    for block in blocks:
        block_type = block.get('type')
        payload    = block.get(block_type) if block_type else None
        if not isinstance(payload, dict):
            continue
        if block_type in ('bookmark', 'link_preview', 'embed'):
            url = (payload.get('url') or '').strip()
            if _is_github_host(url):
                github_urls.append(url)
        elif block_type == 'table_row':
            for cell in payload.get('cells') or []:
                github_urls.extend(_urls_from_rich_text(cell))
        elif block_type not in _RICH_TEXT_EXCLUDED_TYPES and 'rich_text' in payload:
            github_urls.extend(_urls_from_rich_text(payload.get('rich_text')))
    return github_urls


def split_repo_urls(urls: List[str]) -> Tuple[List[str], List[str]]:
    """Sépare les liens de dépôts des autres liens GitHub (topics, orgs, profils...)."""
    repo_urls, ignored = [], []
    for url in urls:
        (repo_urls if extract_github_info(url) else ignored).append(url)
    return repo_urls, ignored


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
    log("\n📊 Résumé doublons:")
    log(f"   • URLs totales:       {len(urls)}")
    log(f"   • URLs uniques:       {len(unique_urls)}")
    log(f"   • Doublons supprimés: {len(duplicates)}")
    log("")
    return {
        'unique_urls': unique_urls,
        'duplicates':  duplicates,
        'stats': {'total': len(urls), 'unique': len(unique_urls), 'duplicates': len(duplicates)},
    }

# =============================================================================
# GITHUB — fetch metadata + README en parallèle
# =============================================================================
_GITHUB_HTTP_HINTS = {
    401: "jeton refusé",
    403: "accès refusé ou quota épuisé",
    404: "dépôt introuvable, supprimé ou inaccessible",
    451: "bloqué pour raisons légales",
}


def fetch_github_repo(owner: str, repo: str) -> Tuple[Optional[Dict], str]:
    """Renvoie (infos du dépôt, '') ou (None, raison de l'échec)."""
    global GITHUB_CACHE_DIRTY
    cache_key = f"{owner}/{repo}"

    if CACHE_ENABLED:
        cached = GITHUB_CACHE.get(cache_key)
        if cached is not None and _cache_entry_valid(cached):
            log(f"   📦 Cache hit: {cache_key}", 'verbose')
            return cached, ''

    with ThreadPoolExecutor(max_workers=2) as inner:
        f_meta   = inner.submit(http_request_with_retry, 'GET',
                                f"https://api.github.com/repos/{owner}/{repo}",
                                GITHUB_HEADERS, None, None, 15)
        f_readme = inner.submit(http_request_with_retry, 'GET',
                                f"https://api.github.com/repos/{owner}/{repo}/readme",
                                GITHUB_HEADERS, None, None, 15)
        response, readme_response = f_meta.result(), f_readme.result()

    if response is None:
        return None, "GitHub injoignable (réseau/timeout)"
    if response.status_code not in (200, 201):
        hint = _GITHUB_HTTP_HINTS.get(response.status_code)
        return None, f"GitHub HTTP {response.status_code}" + (f" — {hint}" if hint else "")

    data = _json_dict(response)
    if data is None:
        return None, "GitHub : réponse illisible"

    private        = bool(data.get('private'))
    readme_content = ''
    if not private and readme_response is not None and readme_response.status_code in (200, 201):
        try:
            readme_content = base64.b64decode(
                (_json_dict(readme_response) or {}).get('content') or ''
            ).decode('utf-8', errors='ignore')
        except Exception as e:
            _warn(f"readme_decode ({owner}/{repo})", e)

    result = {
        'name':        data.get('name'),
        'full_name':   data.get('full_name'),
        'description': data.get('description'),
        'stars':       data.get('stargazers_count') or 0,
        'language':    data.get('language', 'Autre'),
        'updated_at':  data.get('updated_at'),
        'topics':      data.get('topics') or [],
        'readme':      readme_content[:README_MAX_CHARS],
        'html_url':    data.get('html_url'),
        'private':     private,
        'cached_at':   time.time(),
    }

    if CACHE_ENABLED and not private:
        with cache_lock:
            GITHUB_CACHE[cache_key] = result
            GITHUB_CACHE_DIRTY = True

    return result, ''


def get_github_repo_info(owner: str, repo: str) -> Optional[Dict]:
    return fetch_github_repo(owner, repo)[0]

# =============================================================================
# ANALYSE README
# =============================================================================
def analyze_repo_for_usage(repo_info: Dict) -> Dict[str, str]:
    description = repo_info.get('description') or "GitHub project"
    readme      = repo_info.get('readme') or ''
    language    = repo_info.get('language') or ''
    topics      = [t for t in (repo_info.get('topics') or []) if isinstance(t, str)]

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
            lines = [ln.strip() for ln in install_text.split('\n') if ln.strip() and len(ln.strip()) > 3]
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

    repo_name = repo_info.get('name') or ''
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
# NOTION — DATABASE (jamais de création implicite)
# =============================================================================
REQUIRED_DB_PROPERTIES = {
    'Nom':          'title',
    'URL':          'url',
    'Description':  'rich_text',
    "Cas d'usage":  'rich_text',
    'Installation': 'rich_text',
    'Exemple':      'rich_text',
    'Prérequis':    'rich_text',
    'Stars':        'number',
    'Pertinence':   'number',
    'Langage':      'select',
    'Statut':       'select',
    'Type':         'multi_select',
    'Dernière MAJ': 'date',
    'Analysé le':   'date',
}
_NOTION_TYPE_LABELS = {
    'title': 'Titre', 'url': 'URL', 'rich_text': 'Texte', 'number': 'Nombre',
    'select': 'Sélection', 'multi_select': 'Sélection multiple', 'date': 'Date',
}
_NOTION_DB_HINTS = {
    400: "ID mal formé, ou base devenue multi-sources (non supportée avec Notion-Version 2022-06-28)",
    401: "NOTION_TOKEN invalide ou révoqué",
    403: "l'intégration n'a pas les capacités nécessaires (lire et insérer du contenu) — "
         "réglages de l'intégration sur notion.so/my-integrations",
    404: "base introuvable ou non partagée avec l'intégration — dans Notion : base → ••• → "
         "Connexions → ajoutez votre intégration",
}


def _type_label(notion_type: str) -> str:
    label = _NOTION_TYPE_LABELS.get(notion_type)
    return f"{notion_type} ({label})" if label else str(notion_type)


def check_database_schema(db_data: Dict) -> List[str]:
    """Liste des problèmes de schéma (colonne manquante ou mauvais type)."""
    props    = db_data.get('properties') or {}
    problems = []
    for name, expected in REQUIRED_DB_PROPERTIES.items():
        prop = props.get(name)
        if not isinstance(prop, dict):
            problems.append(f"colonne manquante : '{name}' (type attendu : {_type_label(expected)})")
        elif prop.get('type') != expected:
            problems.append(f"mauvais type pour '{name}' : {_type_label(prop.get('type'))} "
                            f"au lieu de {_type_label(expected)}")
    return problems


def create_database(parent_page_id: str) -> Optional[Dict]:
    """POST /v1/databases, jamais réessayé après timeout (pas de base en double)."""
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
        'POST', 'https://api.notion.com/v1/databases', NOTION_HEADERS,
        json_data=payload, idempotent=False)
    if response is None:
        log(f"❌ Création de la base : pas de réponse de Notion ({last_http_error()}) — "
            "non réessayée pour éviter un doublon.", 'error')
        log("   → Vérifiez dans Notion si « Ressources GitHub » a été créée ; si oui, "
            "renseignez DATABASE_ID=<son id> et CREATE_DATABASE=false.", 'error')
        return None
    if response.status_code not in (200, 201):
        log(f"❌ Création de la base refusée : {_describe_failure(response, _NOTION_DB_HINTS)}", 'error')
        return None
    db_data = _json_dict(response)
    if not db_data or not db_data.get('id'):
        log("❌ Création de la base : réponse Notion illisible — vérifiez dans Notion.", 'error')
        return None
    return {'id': db_data['id'], 'url': db_data.get('url', ''), 'has_justification': True}


def setup_database() -> Tuple[Optional[int], Optional[Dict]]:
    """Renvoie (None, infos de la base) si l'import peut continuer, sinon (code de sortie, None).

    - DATABASE_ID renseigné : lecture + validation du schéma ; aucun échec ne crée de base.
    - DATABASE_ID vide : création seulement si CREATE_DATABASE=true et hors DRY_RUN, une
      seule fois (id mémorisé dans .gitnotate_state.json) ; le run s'arrête ensuite (code 0).
    """
    if DATABASE_ID:
        log(f"📋 Réutilisation database {DATABASE_ID[:8]}...")
        response = http_request_with_retry(
            'GET', f"https://api.notion.com/v1/databases/{DATABASE_ID}", NOTION_HEADERS)
        if response is None or response.status_code not in (200, 201):
            log(f"❌ Impossible de lire la base DATABASE_ID={DATABASE_ID[:8]}… : "
                f"{_describe_failure(response, _NOTION_DB_HINTS)}", 'error')
            log("   → Aucune base n'a été créée. Corrigez DATABASE_ID ou le partage, puis relancez.", 'error')
            return EXIT_CONFIG, None
        db_data = _json_dict(response)
        if not db_data or not db_data.get('id'):
            log("❌ Réponse Notion illisible pour la base — aucune base n'a été créée.", 'error')
            return EXIT_CONFIG, None
        problems = check_database_schema(db_data)
        if problems:
            log("❌ ERREUR SCHEMA DATABASE", 'error')
            for problem in problems:
                log(f"   • {problem}", 'error')
            log("   → Ajoutez ou corrigez ces colonnes dans la base Notion (nom exact et type), "
                "puis relancez.", 'error')
            return EXIT_CONFIG, None
        log("✅ Schema validé")
        props    = db_data.get('properties') or {}
        has_just = (props.get('Justification') or {}).get('type') == 'rich_text'
        if 'Justification' not in props:
            log("⚠️  Colonne 'Justification' absente — reasoning LLM non sauvegardé dans Notion")
            log("   → Ajoutez une colonne 'Justification' (type Texte) pour l'activer")
        elif not has_just:
            log("⚠️  Colonne 'Justification' présente mais pas de type Texte — reasoning non sauvegardé")
        return None, {'id': db_data['id'], 'url': db_data.get('url', ''), 'has_justification': has_just}

    # DATABASE_ID vide
    state, state_error = read_state()
    known_id = state.get('database_id') if isinstance(state.get('database_id'), str) else None
    if not CREATE_DATABASE or DRY_RUN:
        log("❌ DATABASE_ID n'est pas renseigné.", 'error')
        if known_id:
            log(f"   → Une base a déjà été créée par Gitnotate : ajoutez DATABASE_ID={known_id} dans .env", 'error')
        else:
            log("   → Renseignez DATABASE_ID=<id de votre base> dans .env "
                "(les 32 caractères de l'URL de la base).", 'error')
            if DRY_RUN:
                log("   → DRY_RUN ne crée jamais de base.", 'error')
            else:
                log("   → Pour créer une NOUVELLE base (une seule fois), mettez CREATE_DATABASE=true.", 'error')
        return EXIT_CONFIG, None
    if state_error:
        log(f"❌ Fichier d'état {STATE_FILE.name} illisible ({state_error}) : "
            "création de base refusée par sécurité.", 'error')
        return EXIT_CONFIG, None
    if known_id:
        log(f"❌ Une base a déjà été créée par Gitnotate (id {known_id}) : "
            "nouvelle création refusée pour éviter un doublon.", 'error')
        log(f"   → Ajoutez DATABASE_ID={known_id} dans .env puis mettez CREATE_DATABASE=false.", 'error')
        return EXIT_CONFIG, None

    log("🆕 CREATE_DATABASE=true : création d'une nouvelle base « Ressources GitHub »...")
    db = create_database(PARENT_PAGE_ID)
    if db is None:
        return EXIT_CONFIG, None
    saved = write_state({
        'database_id':    db['id'],
        'database_url':   db['url'],
        'created_at':     datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'parent_page_id': PARENT_PAGE_ID,
        'version':        __version__,
    })
    log("=" * 70, 'always')
    log(f"✅ Base Notion créée : {db['url']}", 'always')
    log("", 'always')
    log(f"👉 Ajoutez DATABASE_ID={db['id']} dans .env puis mettez CREATE_DATABASE=false", 'always')
    log("   Relancez ensuite le script pour importer les dépôts (aucun import pendant ce run).", 'always')
    if saved:
        log(f"   (id également enregistré dans {STATE_FILE.name})", 'always')
    else:
        log(f"⚠️  Impossible d'écrire {STATE_FILE.name} : notez bien l'id ci-dessus.", 'error')
    log("=" * 70, 'always')
    return EXIT_OK, None


def load_existing_urls(database_id: str) -> Optional[Tuple[Set[str], Set[str]]]:
    """Précharge les URL déjà présentes dans la base.
    Renvoie (URLs, clés 'owner/repo' normalisées), ou None si la lecture est incomplète."""
    log("⏳ Préchargement des URLs existantes...")
    existing_urls: Set[str] = set()
    existing_keys: Set[str] = set()
    query_url               = f"https://api.notion.com/v1/databases/{database_id}/query"
    start_cursor            = None
    page_no                 = 0
    while True:
        page_no += 1
        payload = {'page_size': 100}
        if start_cursor:
            payload['start_cursor'] = start_cursor
        response = http_request_with_retry('POST', query_url, NOTION_HEADERS, json_data=payload)
        if response is None or response.status_code not in (200, 201):
            log(f"❌ Lecture de la base interrompue (page {page_no}) : "
                f"{_describe_failure(response, _NOTION_DB_HINTS)}", 'error')
            return None
        data = _json_dict(response)
        if data is None:
            log(f"❌ Lecture de la base interrompue (page {page_no}) : réponse Notion illisible", 'error')
            return None
        for page in data.get('results') or []:
            if not isinstance(page, dict):
                continue
            url_prop = (page.get('properties') or {}).get('URL') or {}
            if url_prop.get('type') == 'url' and url_prop.get('url'):
                existing_urls.add(url_prop['url'])
                existing_keys.add(normalize_github_url(url_prop['url']))
        if not data.get('has_more', False):
            break
        start_cursor = data.get('next_cursor')
        if not start_cursor:
            log(f"❌ Lecture de la base interrompue (page {page_no}) : has_more sans next_cursor", 'error')
            return None
    log(f"✅ {len(existing_urls)} URLs déjà présentes\n")
    return existing_urls, existing_keys

# =============================================================================
# TRAITEMENT D'UN REPO
# =============================================================================
def build_page_properties(
    repo_info:         Dict,
    html_url:          str,
    analysis:          Dict[str, str],
    llm_result:        Dict[str, Any],
    has_justification: bool,
) -> Dict:
    """Propriétés de la fiche Notion (construites aussi en DRY_RUN)."""
    topics = [t for t in (repo_info.get('topics') or []) if isinstance(t, str)]
    desc   = repo_info.get('description') or ''
    types  = []
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

    updated        = (repo_info.get('updated_at') or '')[:10]
    reasoning      = llm_result.get('reasoning') or ''
    scoring_method = llm_result.get('scoring_method') or 'lexical'

    def _text(value: Any) -> List[Dict]:
        return [{'text': {'content': str(value or '')[:NOTION_FIELD_MAX_CHARS]}}]

    properties = {
        'Nom':          {'title':     [{'text': {'content': (repo_info.get('name') or '')[:100]}}]},
        'URL':          {'url':       html_url or None},
        'Description':  {'rich_text': _text(llm_result.get('description_fr'))},
        "Cas d'usage":  {'rich_text': _text(llm_result.get('use_cases_fr'))},
        'Installation': {'rich_text': _text(analysis.get('installation'))},
        'Exemple':      {'rich_text': _text(analysis.get('example'))},
        'Prérequis':    {'rich_text': _text(analysis.get('prerequisites'))},
        'Stars':        {'number':    repo_info.get('stars') or 0},
        'Pertinence':   {'number':    llm_result.get('score')},
        'Langage':      {'select':    {'name': language}},
        'Type':         {'multi_select': types},
        'Statut':       {'select':    {'name': 'À explorer'}},
        'Dernière MAJ': {'date':      {'start': updated} if updated else None},
        'Analysé le':   {'date':      {'start': time.strftime("%Y-%m-%d")}},
    }

    # Justification (800 caractères) préfixée par la méthode, le modèle réellement servi
    # et l'empreinte du profil : « [LLM <modèle> · profil <hash6>] » ou « [LEXICAL · profil <hash6>] »
    if has_justification:
        profile_hash = llm_result.get('profile_hash') or compute_profile_hash()
        if scoring_method == 'llm':
            tag = f"[LLM {llm_result.get('model') or '?'} · profil {profile_hash}]"
        else:
            tag = f"[LEXICAL · profil {profile_hash}]"
        justif_text = f"{tag} {reasoning}".strip()
        properties['Justification'] = {'rich_text': [{'text': {'content': justif_text[:REASONING_MAX_CHARS]}}]}

    return properties


DEFER_LLM_FAILED = "aucune réponse LLM valide"
DEFER_NO_LLM     = "aucun fournisseur LLM disponible"
DEFER_BUDGET     = "MAX_NEW_PER_RUN atteint"


def _mark_deferred(result: Dict, reason: str) -> Dict:
    """Dépôt reporté : aucune fiche écrite ; absent de la base, il sera repris au prochain run."""
    result['deferred']        = True
    result['deferred_reason'] = reason
    stats.add_deferred(reason)
    return result


def _count_model(llm_result: Dict) -> None:
    provider, model = llm_result.get('provider'), llm_result.get('model')
    if provider in LLM_PROVIDERS_KNOWN and model:
        stats.add_model(provider, model)


def process_single_repo(
    url:               str,
    database_id:       str,
    existing_urls:     Set[str],
    has_justification: bool,
    idx:               int,
    total:             int,
    existing_keys:     Optional[Set[str]] = None,
    in_progress:       Optional[Set[str]] = None,
) -> Dict:
    result: Dict[str, Any] = {'url': url, 'success': False, 'error': None}
    existing_keys = existing_keys if existing_keys is not None else set()
    in_progress   = in_progress if in_progress is not None else set()

    if _STOP_EVENT.is_set():
        result['interrupted'] = True
        return result

    github_info = extract_github_info(url)
    if not github_info:
        result['ignored'] = True
        stats.inc('ignored')
        log(f"[{idx}/{total}] ↪️  {url} — ignorée (non-dépôt)", 'verbose')
        return result

    owner, repo = github_info['owner'], github_info['repo']
    label       = f"{owner}/{repo}"

    # Pré-contrôle sans appel réseau : clé owner/repo de l'URL source déjà en base
    with existing_urls_lock:
        already_present = f"{owner.lower()}/{repo.lower()}" in existing_keys or url in existing_urls
    if already_present:
        result['success'] = True
        result['skipped'] = True
        stats.inc('already_present')
        log(f"[{idx}/{total}] ⏭️  {label} — Déjà présent")
        return result

    # Mode reprise : plus aucun fournisseur LLM utilisable → report immédiat, sans appel GitHub
    if llm_required() and not llm_available():
        _mark_deferred(result, DEFER_NO_LLM)
        if not _announce_once('no_llm', "⏸️  Plus aucun fournisseur LLM disponible : les dépôts restants "
                                        "sont reportés au prochain run (aucun appel GitHub, rien n'est écrit)",
                              'error'):
            log(f"[{idx}/{total}] ⏸️  {label} — reporté ({DEFER_NO_LLM})", 'verbose')
        return result

    # Budget MAX_NEW_PER_RUN : place réservée avant l'appel GitHub, rendue si rien n'est écrit
    if not NEW_REPO_BUDGET.acquire():
        _mark_deferred(result, DEFER_BUDGET)
        if not _announce_once('budget', f"⏸️  MAX_NEW_PER_RUN={MAX_NEW_PER_RUN} atteint : les dépôts "
                                        "restants sont reportés au prochain run (aucun appel GitHub)"):
            log(f"[{idx}/{total}] ⏸️  {label} — reporté ({DEFER_BUDGET})", 'verbose')
        return result

    try:
        return _process_repo(result, owner, repo, database_id, existing_urls, has_justification,
                             idx, total, existing_keys, in_progress)
    finally:
        if not result.get('created'):
            NEW_REPO_BUDGET.release()


def _process_repo(
    result:            Dict[str, Any],
    owner:             str,
    repo:              str,
    database_id:       str,
    existing_urls:     Set[str],
    has_justification: bool,
    idx:               int,
    total:             int,
    existing_keys:     Set[str],
    in_progress:       Set[str],
) -> Dict:
    """Suite du traitement après les pré-contrôles : GitHub, LLM, puis création de la fiche.
    result['created'] passe à True quand une fiche est écrite (ou simulée en DRY_RUN)."""
    url   = result['url']
    label = f"{owner}/{repo}"

    repo_info, gh_error = fetch_github_repo(owner, repo)
    if not repo_info:
        reason = gh_error or "GitHub échec"
        result['error'] = reason
        stats.add_error(url, reason, reason.split(' — ')[0])
        log(f"[{idx}/{total}] ❌ {label} — {reason}", 'error')
        return result

    if repo_info.get('private'):
        result['skipped'] = True
        stats.inc('filtered')
        log(f"[{idx}/{total}] 🔒 {label} — Dépôt privé ignoré (aucune donnée envoyée au LLM)")
        return result

    if not is_repo_recent_enough(repo_info):
        result['skipped'] = True
        stats.inc('filtered')
        log(f"[{idx}/{total}] ⏳ {label} — Trop ancien ({(repo_info.get('updated_at') or '')[:10]})")
        return result

    html_url = repo_info.get('html_url') or f"https://github.com/{owner}/{repo}"
    key      = normalize_github_url(html_url)

    # Vérification « déjà présent » (dépôts renommés : html_url canonique) et réservation
    # sous le même verrou : deux URL menant au même dépôt ne créent jamais deux fiches.
    with existing_urls_lock:
        if html_url in existing_urls or key in existing_keys:
            result['success'] = True
            result['skipped'] = True
            stats.inc('already_present')
            log(f"[{idx}/{total}] ⏭️  {label} — Déjà présent")
            return result
        if key in in_progress:
            result['skipped'] = True
            stats.inc('duplicates')
            log(f"[{idx}/{total}] ⏭️  {label} — Même dépôt qu'une autre URL en cours de traitement")
            return result
        in_progress.add(key)

    created = False
    try:
        analysis   = analyze_repo_for_usage(repo_info)
        llm_result = translate_and_score(
            analysis['description'], analysis['use_cases_text'], repo_info, label
        )

        # Mode reprise : aucune fiche dégradée (pas de réponse LLM valide → reporté)
        if llm_required() and llm_result.get('llm_status') not in ('ok', 'not_requested'):
            reason = DEFER_NO_LLM if llm_result.get('llm_status') == 'unavailable' else DEFER_LLM_FAILED
            _mark_deferred(result, reason)
            log(f"[{idx}/{total}] ⏸️  {label} — reporté au prochain run ({reason}) : aucune fiche écrite")
            return result

        relevance_score = llm_result['score']
        reasoning       = llm_result.get('reasoning') or ''
        scoring_method  = llm_result.get('scoring_method', 'lexical')

        if SCORE_MIN_THRESHOLD > 0 and relevance_score < SCORE_MIN_THRESHOLD:
            result['skipped'] = True
            stats.inc('filtered')
            log(f"[{idx}/{total}] ⏭️  {label} — Score {relevance_score}/10 < seuil {SCORE_MIN_THRESHOLD}")
            return result

        score_icon     = "🧠" if scoring_method == 'llm' else "📐"
        provider_label = llm_result.get('provider', '?') if llm_result.get('translated') else None
        trans_icon     = f"🌍 [{provider_label}]" if provider_label else "⚠️ EN"

        # Payload construit avant le court-circuit DRY_RUN (révèle les erreurs de payload)
        properties = build_page_properties(repo_info, html_url, analysis, llm_result, has_justification)
        payload    = {'parent': {'database_id': database_id}, 'properties': properties}

        if DRY_RUN:
            reasoning_preview = f" — {reasoning[:80]}" if reasoning else ""
            log(f"[{idx}/{total}] 🔍 DRY-RUN: {label} "
                f"({repo_info.get('stars') or 0} ⭐ | {score_icon} {relevance_score}/10) "
                f"{trans_icon}{reasoning_preview}")
            result['success']   = True
            result['simulated'] = True
            result['created']   = True
            stats.inc('success')
            _count_model(llm_result)
            created = True
            return result

        if _STOP_EVENT.is_set():
            result['interrupted'] = True
            log(f"[{idx}/{total}] ⏹️  {label} — interrompu avant création")
            return result

        response = http_request_with_retry(
            'POST', 'https://api.notion.com/v1/pages', NOTION_HEADERS,
            json_data=payload, idempotent=False)

        if response is not None and response.status_code in (200, 201):
            result['success'] = True
            result['created'] = True
            created = True
            stats.inc('success')
            _count_model(llm_result)
            reasoning_preview = f" — {reasoning[:80]}" if reasoning and LOG_LEVEL == 'verbose' else ""
            log(f"[{idx}/{total}] ✅ {label} "
                f"({repo_info.get('stars') or 0} ⭐ | {score_icon} {relevance_score}/10) "
                f"{trans_icon}{reasoning_preview}")
        elif response is not None:
            msg    = _api_error_message(response)
            reason = f"Notion HTTP {response.status_code}" + (f" — {msg}" if msg else "")
            result['error'] = reason
            stats.add_error(url, reason, f"Notion HTTP {response.status_code}")
            log(f"[{idx}/{total}] ❌ {label} — création Notion refusée ({reason})", 'error')
        else:
            reason = (f"Notion sans réponse ({last_http_error()}) — création non réessayée pour "
                      "éviter un doublon ; sera reprise au prochain run si absente")
            result['error'] = reason
            stats.add_error(url, reason, "Notion sans réponse")
            log(f"[{idx}/{total}] ❌ {label} — {reason}", 'error')
        return result
    finally:
        with existing_urls_lock:
            in_progress.discard(key)
            if created:
                existing_urls.add(html_url)
                existing_keys.add(key)

# =============================================================================
# LIGNE DE COMMANDE
# =============================================================================
def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"entier attendu : '{value}'")
    if number < 0:
        raise argparse.ArgumentTypeError("valeur ≥ 0 attendue")
    return number


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='gitnotate',
        description="Analyse les liens GitHub d'une page Notion et crée une fiche par dépôt "
                    "dans une base Notion.",
        epilog="Les options priment sur les variables d'environnement (.env). "
               "Codes de sortie : 0 succès, 1 configuration, 2 erreurs ou lecture partielle, 130 Ctrl-C.",
    )
    parser.add_argument('--dry-run', action='store_true',
                        help="simulation : aucune écriture dans Notion")
    parser.add_argument('--max-repos', type=_non_negative_int, metavar='N',
                        help="ne traiter que les N premiers dépôts uniques (0 = illimité)")
    parser.add_argument('--log-level', type=str.lower, choices=['quiet', 'normal', 'verbose'],
                        help="verbosité (quiet = erreurs seulement)")
    parser.add_argument('--version', action='version', version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def apply_cli_overrides(args: argparse.Namespace) -> None:
    global DRY_RUN, MAX_REPOS, LOG_LEVEL
    if args.dry_run:
        DRY_RUN = True
    if args.max_repos is not None:
        MAX_REPOS = args.max_repos
        CONFIG_ERRORS.pop('MAX_REPOS', None)
    if args.log_level:
        LOG_LEVEL = args.log_level

# =============================================================================
# MAIN
# =============================================================================
def check_config() -> List[str]:
    errors = list(CONFIG_ERRORS.values())
    if not PARENT_PAGE_ID:
        errors.append("PARENT_PAGE_ID non défini — ajoutez PARENT_PAGE_ID=<id de la page source Notion> dans .env")
    if not NOTION_TOKEN:
        errors.append("NOTION_TOKEN manquant — ajoutez NOTION_TOKEN=<jeton d'intégration Notion> dans .env")
    return errors


def print_configuration() -> None:
    log("⚡ Configuration:")
    log(f"   • Workers:          {MAX_WORKERS}")
    if GITHUB_AUTH_STATUS == 'ok':
        log(f"   • GitHub auth:      ✅ jeton valide ({GITHUB_LOGIN or 'OK'})")
    else:
        log("   • GitHub auth:      ⚠️  sans jeton — rate limit réduit (60 req/h)")

    readme_info = f" + README {README_LLM_CHARS} chars" if README_LLM_CHARS > 0 else ""
    providers   = configured_providers()
    if not TRANSLATION_ENABLED:
        log("   • Traduction:       ❌ désactivée")
        log("   • Scoring:          📐 lexical uniquement")
    elif providers:
        log(f"   • Traduction:       ✅ {_provider_label(providers[0])} [primaire]")
        for fallback in providers[1:]:
            budget = _provider_state(fallback).budget
            quota  = f" — quota gratuit restant {budget}" if budget is not None else ""
            log(f"   • Fallback:         ✅ {_provider_label(fallback)}{quota}")
        if providers[0] == 'openrouter' and _provider_state('openrouter').budget is not None:
            log(f"   • Quota OpenRouter: {_provider_state('openrouter').budget} requêtes gratuites restantes")
        if LLM_SCORING_ENABLED:
            log(f"   • Scoring:          🧠 LLM sémantique (t=0.1{readme_info})")
        else:
            log("   • Scoring:          📐 lexical (LLM_SCORING_ENABLED=false)")
    else:
        log("   • Traduction:       ❌ aucun fournisseur")
        log("   • Scoring:          📐 lexical uniquement (REQUIRE_LLM=false)")
    if TRANSLATION_ENABLED:
        log(f"   • Appels LLM:       timeout {LLM_TIMEOUT}s | max_tokens {LLM_MAX_TOKENS} | "
            f"coupe-circuit après {LLM_BREAKER_THRESHOLD} échecs consécutifs")
        log("   • Mode reprise:     " + ("✅ REQUIRE_LLM=true (aucune fiche sans réponse LLM valide)"
                                         if REQUIRE_LLM else
                                         "❌ REQUIRE_LLM=false (fiche au score lexical si aucun LLM)"))
    log(f"   • Nouvelles fiches: {MAX_NEW_PER_RUN if MAX_NEW_PER_RUN > 0 else 'illimité'} par run "
        "(MAX_NEW_PER_RUN)")

    log(f"   • Retry:            {MAX_RETRIES} tentatives (créations Notion : jamais après timeout)")
    log(f"   • HTTP timeout:     {DEFAULT_TIMEOUT}s | attente max: {MAX_WAIT_SECONDS}s")
    log(f"   • Cache GitHub:     {'✅ JSON (' + str(CACHE_TTL_SECONDS // 3600) + 'h)' if CACHE_ENABLED else '❌'}")
    log(f"   • Dry-run:          {'✅' if DRY_RUN else '❌'}")
    log(f"   • Max dépôts:       {MAX_REPOS if MAX_REPOS > 0 else 'illimité'}")
    log(f"   • Filtre âge:       {'✅ ' + str(MIN_UPDATE_DAYS) + ' jours' if MIN_UPDATE_DAYS > 0 else '❌ désactivé'}")
    log(f"   • Score minimum:    {SCORE_MIN_THRESHOLD if SCORE_MIN_THRESHOLD > 0 else '❌ (tous acceptés)'}")
    log(f"   • Log level:        {LOG_LEVEL}")
    log(f"   • README cache:     {README_MAX_CHARS} chars | LLM context: {README_LLM_CHARS} chars")
    log(f"   • Profil:           {USER_PROFILE_SOURCE}")
    log(f"   • Dossier données:  {BASE_DIR}")
    log("")


def print_summary(elapsed: float, total: int, interrupted: bool) -> None:
    log("")
    log("=" * 70)
    if interrupted:
        head = "🛑 INTERROMPU"
    elif stats.errors:
        head = "⚠️  TERMINÉ AVEC ERREURS"
    elif stats.deferred:
        head = "⏸️  TERMINÉ (dépôts reportés au prochain run)"
    else:
        head = "✅ TERMINÉ"
    log(f"{head} en {int(elapsed // 60)}min {int(elapsed % 60)}s")
    if DRY_RUN:
        log(f"   • Simulées:        {stats.success}  (DRY_RUN : rien n'a été écrit)")
    else:
        log(f"   • Créations:       {stats.success}")
    log(f"   • Déjà présents:   {stats.already_present}")
    log(f"   • Ignorées:        {stats.ignored}  (liens GitHub non-dépôt)")
    log(f"   • Filtrées:        {stats.filtered}  (âge / seuil / privés)")
    log(f"   • Erreurs:         {stats.errors}")
    log(f"   • Doublons:        {stats.duplicates}  (liens en double sur la page source)")
    log(f"   • Reportés:        {stats.deferred}  (aucune fiche écrite, repris au prochain run)")

    if stats.translation_total > 0:
        provider_label = TRANSLATION_PROVIDER or 'none'
        if TRANSLATION_FALLBACK:
            provider_label += f" + {TRANSLATION_FALLBACK}"
        log(f"   • Traductions:     {stats.translation_success}/{stats.translation_total} "
            f"({stats.translation_rate:.1f}%) — {provider_label}")

    if LLM_SCORING_ENABLED and stats.llm_score_total > 0:
        # En mode reprise, un dépôt sans score LLM n'est pas écrit (reporté) : pas de « fallback »
        fallback_label = "sans score LLM (non écrits)" if llm_required() else "fallbacks lexicaux"
        log(f"   • Scores LLM:      {stats.llm_score_success}/{stats.llm_score_total} "
            f"({stats.llm_score_rate:.1f}%) | "
            f"{stats.llm_score_fallback} {fallback_label}")

    if stats.models_used:
        log(f"   • Modèles LLM:     {_format_counts(stats.models_used, ' ×')}  (modèles réellement servis)")
    for provider, state in LLM_STATES.items():
        if state.disabled_reason:
            log(f"   • ⛔ {_provider_label(provider)} désactivé : {state.disabled_reason}")

    if elapsed > 0 and total:
        log(f"   • Vitesse:         {total / elapsed:.1f} dépôts/sec")
    log("=" * 70)

    if stats.error_details:
        log("", 'error')
        log(f"❌ URLs en erreur ({len(stats.error_details)}) :", 'error')
        for url, reason in stats.error_details[:ERRORS_DISPLAY_MAX]:
            log(f"   • {url} — {reason}", 'error')
        remaining = len(stats.error_details) - ERRORS_DISPLAY_MAX
        if remaining > 0:
            log(f"   … et {remaining} autres", 'error')

    if stats.deferred:
        n = stats.deferred
        plural = 's' if n > 1 else ''
        log("", 'error')
        log(f"⏸️  {n} dépôt{plural} reporté{plural} au prochain run "
            f"({_format_counts(stats.deferred_by_reason, ' : ')}) — aucune fiche écrite pour "
            f"{'eux' if n > 1 else 'lui'} ; relancez plus tard.", 'error')
    log("")


def _format_counts(counts: Dict[str, int], sep: str) -> str:
    """{'a': 2, 'b': 5} → 'b<sep>5, a<sep>2' (du plus fréquent au moins fréquent)."""
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ', '.join(f"{name}{sep}{count}" for name, count in items)


def _run() -> int:
    global TRANSLATION_PROVIDER, TRANSLATION_FALLBACK, USER_PROFILE, USER_PROFILE_SOURCE, stats
    stats = ThreadSafeStats()
    _STOP_EVENT.clear()

    log("=" * 70)
    log(f"🚀 GITNOTATE v{__version__} — LLM FULL-CONTEXT SCORING EDITION")
    log("=" * 70)
    log("")

    for warning in CONFIG_WARNINGS:
        log(f"⚠️  {warning}")

    # Configuration vérifiée avant tout appel réseau
    errors = check_config()
    if errors:
        log("❌ ERREUR DE CONFIGURATION", 'error')
        for error in errors:
            log(f"   • {error}", 'error')
        log("   → Corrigez le fichier .env (voir env.example) puis relancez.", 'error')
        return EXIT_CONFIG

    USER_PROFILE, USER_PROFILE_SOURCE = load_user_profile()
    profile_hash = compute_profile_hash()
    log(f"👤 Profil de pertinence : {USER_PROFILE_SOURCE} (empreinte {profile_hash})")
    log("")
    init_github_cache()
    reset_llm_runtime()

    # Fournisseurs LLM testés avant tout appel GitHub et toute écriture Notion
    TRANSLATION_PROVIDER, TRANSLATION_FALLBACK = init_translation_providers()
    if llm_required() and not configured_providers():
        log("❌ Aucun fournisseur LLM disponible : rien n'est écrit (REQUIRE_LLM=true).", 'error')
        log("   → Vérifiez les clés avec « python scripts/check_llm.py » et relancez plus tard, ou mettez "
            "REQUIRE_LLM=false pour créer des fiches au score lexical.", 'error')
        return EXIT_CONFIG

    if not validate_all_tokens():
        return EXIT_CONFIG

    log("📋 Database Notion...")
    code, db_result = setup_database()
    if code is not None or db_result is None:
        return EXIT_CONFIG if code is None else code

    db_id, db_url         = db_result['id'], db_result['url']
    has_justification_col = db_result.get('has_justification', False)
    log("✅ Database prête!")
    log(f"   • ID:             {db_id}")
    log(f"   • URL:            {db_url}")
    log(f"   • Justification:  {'✅ activée' if has_justification_col else '⚠️  colonne absente'}")
    log("")

    print_configuration()

    existing = load_existing_urls(db_id)
    if existing is None:
        log("❌ Lecture incomplète de la base Notion : arrêt sans aucune création (relancez plus tard).", 'error')
        return EXIT_INCOMPLETE
    existing_urls, existing_keys = existing

    log("🔍 Extraction URLs (pagination complète)...")
    try:
        blocks = get_all_blocks_recursive(PARENT_PAGE_ID)
    except PartialReadError as e:
        log(f"❌ Lecture de la page source incomplète : {e}", 'error')
        log(f"   → Arrêt sans aucune création ({URLS_FILE.name} n'est pas modifié).", 'error')
        return EXIT_INCOMPLETE
    except Exception as e:
        log(f"❌ Erreur extraction blocs: {type(e).__name__}: {e}", 'error')
        return EXIT_INCOMPLETE
    urls = extract_urls_from_blocks(blocks)
    log(f"✅ {len(urls)} URLs GitHub extraites ({len(blocks)} blocs lus)")

    repo_urls, ignored_urls = split_repo_urls(urls)
    if ignored_urls:
        stats.inc('ignored', len(ignored_urls))
        log(f"↪️  {len(ignored_urls)} lien(s) GitHub ignoré(s) (non-dépôt : topics, orgs, profils...)")
        for ignored in ignored_urls:
            log(f"   ↪️  ignorée (non-dépôt) : {ignored}", 'verbose')

    if not repo_urls:
        log("❌ Aucune URL de dépôt GitHub trouvée sur la page source", 'error')
        return EXIT_CONFIG

    log("")
    dedup_result     = detect_duplicates(repo_urls)
    unique_urls      = dedup_result['unique_urls']
    stats.duplicates = dedup_result['stats']['duplicates']

    try:
        with open(URLS_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(unique_urls) + '\n')
        log(f"💾 URLs uniques → {URLS_FILE.name}")
    except OSError as e:
        _warn("save_extracted_urls", e)

    if MAX_REPOS > 0 and len(unique_urls) > MAX_REPOS:
        log(f"✂️  MAX_REPOS={MAX_REPOS} : traitement limité aux {MAX_REPOS} premiers dépôts "
            f"sur {len(unique_urls)}")
        unique_urls = unique_urls[:MAX_REPOS]

    total = len(unique_urls)
    log("")
    log(f"📊 Traitement de {total} dépôts...")
    if DRY_RUN:
        log("🔍 MODE DRY-RUN activé (aucune écriture dans Notion)")
    log("")

    start_time    = time.time()
    show_progress = _progress_enabled()
    in_progress: Set[str] = set()
    interrupted   = False
    executor      = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        futures = {
            executor.submit(
                process_single_repo,
                url, db_id, existing_urls, has_justification_col, idx, total,
                existing_keys, in_progress,
            ): url
            for idx, url in enumerate(unique_urls, 1)
        }
        pending   = set(futures)
        processed = 0
        # wait() avec timeout : Ctrl-C reste réactif (y compris sous Windows)
        while pending:
            done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            for future in done:
                url = futures[future]
                try:
                    future.result()
                except Exception as e:
                    stats.add_error(url, f"Exception non gérée {type(e).__name__}: {e}",
                                    f"Exception {type(e).__name__}")
                    log(f"\n❌ Exception non gérée [{url}]: {type(e).__name__}: {e}", 'error')
                processed += 1
                if show_progress:
                    print_progress_bar(processed, total, time.time() - start_time)
    except KeyboardInterrupt:
        interrupted = True
        _STOP_EVENT.set()
        log("\n🛑 Interruption (Ctrl-C) — dépôts en attente annulés, fin des traitements en cours...", 'error')
        executor.shutdown(wait=True, cancel_futures=True)
    finally:
        executor.shutdown(wait=True)

    if show_progress:
        print()

    flush_github_cache()
    elapsed = time.time() - start_time

    if interrupted:
        exit_code = EXIT_INTERRUPTED
    elif stats.errors:
        exit_code = EXIT_INCOMPLETE
    else:
        exit_code = EXIT_OK

    print_summary(elapsed, total, interrupted)

    save_execution_stats({
        'duration':                 int(elapsed),
        'success':                  stats.success,
        'errors':                   stats.errors,
        'skipped':                  stats.skipped,
        'already_present':          stats.already_present,
        'filtered':                 stats.filtered,
        'ignored':                  stats.ignored,
        'duplicates':               stats.duplicates,
        'errors_by_reason':         dict(stats.errors_by_reason),
        'deferred':                 stats.deferred,
        'deferred_by_reason':       dict(stats.deferred_by_reason),
        'models_used':              dict(stats.models_used),
        'providers_used':           dict(stats.providers_used),
        'llm_disabled':             {p: s.disabled_reason for p, s in LLM_STATES.items() if s.disabled_reason},
        'profile_hash':             profile_hash,
        'translation_success_rate': stats.translation_rate,
        'llm_score_rate':           stats.llm_score_rate,
        'translation_provider':     TRANSLATION_PROVIDER or 'none',
        'interrupted':              interrupted,
        'exit_code':                exit_code,
    })

    if interrupted:
        log("🛑 Run interrompu : cache et statistiques sauvegardés. Relancez pour reprendre.", 'error')
        return exit_code

    log("📊 DATABASE NOTION:")
    log(f"   → {db_url}")
    log("")
    log("💡 Tri recommandé: Pertinence ↓ + Stars ↓")
    log("   Icônes: 🧠 = scoré par LLM (avec README)   📐 = fallback lexical")
    log("=" * 70)
    return exit_code


def main(argv: Optional[List[str]] = None) -> int:
    """Point d'entrée. Renvoie le code de sortie (0, 1, 2 ou 130).
    argv=None lit sys.argv ; les tests passent une liste explicite."""
    _configure_console()
    args = parse_args(argv)
    apply_cli_overrides(args)
    try:
        return _run()
    except KeyboardInterrupt:
        _STOP_EVENT.set()
        flush_github_cache()
        log("\n🛑 Interruption (Ctrl-C) — arrêt du programme.", 'error')
        return EXIT_INTERRUPTED


if __name__ == '__main__':
    sys.exit(main())
