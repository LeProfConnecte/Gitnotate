#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitNotate - Nettoyeur SÛR des doublons de la PAGE SOURCE v2.0

Retire de la page Notion source (PARENT_PAGE_ID) les blocs lien (bookmark,
aperçu de lien, intégration) qui pointent vers un lien GitHub déjà présent.
Rien d'autre n'est modifié.

Usage :
  python clean_page_duplicates.py                          → simulation (par défaut)
  python clean_page_duplicates.py --apply                  → suppression après saisie de « SUPPRIMER <n> »
  python clean_page_duplicates.py --restore JOURNAL        → simulation de restauration
  python clean_page_duplicates.py --restore JOURNAL --apply → restauration après saisie de « RESTAURER <n> »

Garanties :
  - la page est lue en entier, sinon aucune suppression ;
  - sous-pages, bases, liens vers pages et copies de blocs synchronisés ne sont jamais parcourus ;
  - clé de doublon stricte : seules les variantes cosmétiques d'une URL sont ignorées ;
  - seuls bookmark / link_preview / embed sont supprimés ; un lien dans du texte n'est jamais touché ;
  - aucune légende perdue, aucun bloc avec enfants supprimé ;
  - bloc conservé et bloc à supprimer relus juste avant chaque suppression ;
  - journal écrit sur disque AVANT chaque suppression (annulation avec --restore) ;
  - au plus CLEANER_MAX_DELETE suppressions (défaut 50), sinon abandon total.

Jeton : NOTION_CLEANER_TOKEN (intégration dédiée, capacité « Update content »),
sinon NOTION_TOKEN. La variable DRY_RUN du script principal n'est PAS lue ici.

Codes de sortie : 0 OK ; 1 configuration ; 2 abandon, lecture partielle ou au moins un échec.
"""

import argparse
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit

import requests

# =============================================================================
# CONFIGURATION
# =============================================================================
NOTION_API     = 'https://api.notion.com/v1'
NOTION_VERSION = '2022-06-28'


def trash_field(version: str) -> str:
    """Champ « corbeille » accepté par l'API Notion pour une Notion-Version donnée.

    Avant 2026-03-11 : 'archived' (alias d'in_trash) ; à partir de 2026-03-11 : 'in_trash' seul.
    """
    return 'in_trash' if version >= '2026-03-11' else 'archived'


TRASH_FIELD = trash_field(NOTION_VERSION)

# Seuls types supprimables, et seuls types pouvant servir de bloc conservé
DELETABLE_TYPES = ('bookmark', 'link_preview', 'embed')
# Liens dans du texte : signalés, jamais supprimés ni conservés à la place d'un bloc lien
TEXT_TYPES = ('paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item',
              'numbered_list_item', 'to_do', 'toggle', 'quote', 'callout')
# Hors périmètre : jamais parcourus
NO_DESCEND_TYPES = ('child_page', 'child_database', 'link_to_page')

DEFAULT_MAX_DELETE = 50
MAX_DEPTH          = 20      # profondeur d'imbrication maximale lue (au-delà : lecture partielle)
HTTP_TIMEOUT       = 30      # secondes
MAX_ATTEMPTS       = 4       # tentatives par requête (429, 5xx, erreur réseau)
RETRY_AFTER_MAX    = 30      # plafond d'attente entre deux tentatives (secondes)
WRITE_PAUSE        = 0.35    # pause entre deux écritures (limite Notion ≈ 3 req/s)
JOURNAL_DIRNAME    = 'journal'

EXIT_OK, EXIT_CONFIG, EXIT_ABORT = 0, 1, 2

_SAFE_ID_RE = re.compile(r'[0-9A-Za-z-]{1,64}')
_RAW_GITHUB_URL_RE = re.compile(r'https?://(?:www\.)?github\.com/[^\s<>()\[\]{}"\']+', re.IGNORECASE)


class ConfigError(Exception):
    """Configuration absente ou invalide (code de sortie 1)."""


class PartialRead(Exception):
    """Lecture incomplète : aucune suppression ne doit avoir lieu."""

    def __init__(self, message: str, status: Optional[int] = None, path: str = ''):
        super().__init__(message)
        self.status = status
        self.path = path


class NetworkError(Exception):
    """Aucune réponse HTTP obtenue après toutes les tentatives."""


class Abort(Exception):
    """Abandon volontaire (confirmation impossible ou refusée)."""


class JournalError(Exception):
    """Journal de suppression illisible ou incohérent."""


# =============================================================================
# UTILITAIRES
# =============================================================================
def _mask_token(token: str) -> str:
    if not token or len(token) < 8:
        return "****"
    return f"{token[:4]}...{token[-4:]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short(text: str, limit: int = 80) -> str:
    text = ' '.join((text or '').split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _safe_console() -> None:
    """Évite un plantage si la console (Windows) ne sait pas afficher un caractère."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def norm_id(block_id: str) -> str:
    return (block_id or '').replace('-', '').lower()


def is_trashed(obj: Dict) -> bool:
    return bool(obj.get('in_trash') or obj.get('archived'))


def _parent_key(parent) -> Optional[Tuple[str, str]]:
    """Parent comparable (type, id normalisé), indépendant des tirets et de la casse."""
    if not isinstance(parent, dict):
        return None
    ptype = str(parent.get('type') or '')
    value = parent.get(ptype)
    return ptype, norm_id(value) if isinstance(value, str) else str(value)


def base_dir() -> Path:
    """Dossier de données : GITNOTATE_DATA_DIR s'il est défini, sinon le dossier du script."""
    data_dir = os.environ.get('GITNOTATE_DATA_DIR', '').strip()
    return Path(data_dir).expanduser() if data_dir else Path(__file__).resolve().parent


def load_env_file(base: Path) -> str:
    """Charge BASE_DIR/.env (sans écraser l'environnement). Renvoie un message d'état."""
    flag = os.environ.get('GITNOTATE_NO_DOTENV', '').strip().lower()
    if flag not in ('', '0', 'false', 'no', 'non', 'off'):
        return "non chargé (GITNOTATE_NO_DOTENV)"
    env_path = base / '.env'
    if not env_path.is_file():
        return f"absent ({env_path})"
    try:
        from dotenv import load_dotenv
    except ImportError:
        return f"non chargé : python-dotenv n'est pas installé ({env_path})"
    load_dotenv(dotenv_path=env_path)
    return f"chargé ({env_path})"


@dataclass
class Config:
    token: str
    token_source: str
    page_id: str
    max_delete: int


def read_config(require_page: bool = True) -> Config:
    token = os.environ.get('NOTION_CLEANER_TOKEN', '').strip()
    source = 'NOTION_CLEANER_TOKEN'
    if not token:
        token = os.environ.get('NOTION_TOKEN', '').strip()
        source = 'NOTION_TOKEN'
    if not token:
        raise ConfigError("Jeton Notion manquant : définissez NOTION_CLEANER_TOKEN (recommandé) "
                          "ou NOTION_TOKEN dans le .env")

    page_id = os.environ.get('PARENT_PAGE_ID', '').strip()
    if require_page:
        if not page_id:
            raise ConfigError("PARENT_PAGE_ID manquant (identifiant de la page source)")
        if not _SAFE_ID_RE.fullmatch(page_id):
            raise ConfigError("PARENT_PAGE_ID invalide : indiquez l'identifiant de la page "
                              "(32 caractères), pas son URL")

    raw_max = os.environ.get('CLEANER_MAX_DELETE', '').strip()
    if raw_max:
        try:
            max_delete = int(raw_max)
        except ValueError:
            raise ConfigError(f"CLEANER_MAX_DELETE invalide : '{raw_max}' (entier attendu)") from None
        if max_delete < 0:
            raise ConfigError("CLEANER_MAX_DELETE doit être positif ou nul")
    else:
        max_delete = DEFAULT_MAX_DELETE
    return Config(token, source, page_id, max_delete)


# =============================================================================
# CLIENT NOTION (lecture complète ou PartialRead ; seules écritures : DELETE et restauration)
# =============================================================================
class NotionClient:
    def __init__(self, token: str, session=None, sleep: Callable[[float], None] = time.sleep,
                 max_attempts: int = MAX_ATTEMPTS):
        self.session = session if session is not None else requests.Session()
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Notion-Version': NOTION_VERSION,
        }
        self.sleep = sleep
        self.max_attempts = max(1, max_attempts)

    @staticmethod
    def _retry_delay(attempt: int, response) -> float:
        delay = float(min(2 ** attempt, RETRY_AFTER_MAX))
        if response is not None:
            retry_after = str(response.headers.get('Retry-After', '')).strip()
            try:
                value = float(retry_after)
            except ValueError:
                value = math.nan
            if math.isfinite(value):
                delay = min(max(value, 0.0), float(RETRY_AFTER_MAX))
        return delay

    def _send(self, method: str, path: str, **kwargs) -> requests.Response:
        """Envoie la requête ; nouvelles tentatives sur 429, 5xx et erreur réseau.

        Renvoie la dernière réponse reçue, ou lève NetworkError si aucune réponse n'a été obtenue.
        """
        response, last_error = None, None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.request(method, NOTION_API + path, headers=self.headers,
                                                timeout=HTTP_TIMEOUT, **kwargs)
            except requests.RequestException as e:
                response, last_error = None, e
            else:
                if response.status_code != 429 and response.status_code < 500:
                    return response
            if attempt < self.max_attempts:
                self.sleep(self._retry_delay(attempt, response))
        if response is not None:
            return response
        raise NetworkError(f"{method} {path} : {type(last_error).__name__} : {last_error}")

    # --- lectures : réponse 200 complète ou PartialRead ----------------------------------
    def get_json(self, path: str, params: Optional[Dict] = None) -> Dict:
        try:
            response = self._send('GET', path, params=params)
        except NetworkError as e:
            raise PartialRead(str(e), path=path) from e
        if response.status_code != 200:
            raise PartialRead(f"GET {path} → HTTP {response.status_code}",
                              status=response.status_code, path=path)
        try:
            data = response.json()
        except ValueError:
            raise PartialRead(f"GET {path} : réponse illisible", path=path) from None
        if not isinstance(data, dict):
            raise PartialRead(f"GET {path} : réponse inattendue", path=path)
        return data

    def list_children(self, block_id: str):
        path = f'/blocks/{block_id}/children'
        cursor = None
        while True:
            params = {'page_size': 100}
            if cursor:
                params['start_cursor'] = cursor
            data = self.get_json(path, params=params)
            results = data.get('results')
            if not isinstance(results, list):
                raise PartialRead(f"GET {path} : liste 'results' absente", path=path)
            yield from results
            if not data.get('has_more'):
                return
            cursor = data.get('next_cursor')
            if not cursor:
                raise PartialRead(f"GET {path} : has_more sans next_cursor", path=path)

    def get_block(self, block_id: str) -> Dict:
        return self.get_json(f'/blocks/{block_id}')

    # --- écritures : les deux seules autorisées -----------------------------------------
    def delete_block(self, block_id: str) -> int:
        """Met le bloc à la corbeille (restaurable). Renvoie le code HTTP ; NetworkError possible."""
        return self._send('DELETE', f'/blocks/{block_id}').status_code

    def restore_block(self, block_id: str) -> int:
        """Sort le bloc de la corbeille. Renvoie le code HTTP ; NetworkError possible.

        Le champ envoyé suit la Notion-Version de CE client (pas celle notée dans le journal).
        """
        return self._send('PATCH', f'/blocks/{block_id}', json={TRASH_FIELD: False}).status_code


# =============================================================================
# CLÉ DE DOUBLON STRICTE
# =============================================================================
def strict_github_key(url: str) -> Optional[str]:
    """Clé de doublon STRICTE d'un lien GitHub (None si ce n'est pas un lien github.com/owner/repo…).

    Ignorés (cosmétiques) : schéma, www., « / » final, .git, casse de owner/repo, ?tab=…, utm_*,
    #readme et #readme-ov-file. Tout le reste du chemin est conservé tel quel, casse comprise :
    /tree/main/examples n'est pas la racine du dépôt.
    """
    raw = (url or '').strip()
    if not raw:
        return None
    if '://' not in raw:
        raw = 'https://' + raw
    try:
        parts_url = urlsplit(raw)
        query = parse_qsl(parts_url.query, keep_blank_values=True)
    except ValueError:
        return None
    host = parts_url.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    if host != 'github.com':
        return None
    parts = [p for p in parts_url.path.split('/') if p]
    if len(parts) < 2:
        return None
    owner = parts[0].lower()
    repo = re.sub(r'\.git$', '', parts[1], flags=re.IGNORECASE).lower()
    if not repo:
        return None
    key = f'github.com/{owner}/{repo}' + ''.join('/' + p for p in parts[2:])
    kept = sorted((k, v) for k, v in query if k != 'tab' and not k.lower().startswith('utm_'))
    if kept:
        key += '?' + urlencode(kept)
    if parts_url.fragment and parts_url.fragment.lower() not in ('readme', 'readme-ov-file'):
        key += '#' + parts_url.fragment
    return key


# =============================================================================
# LECTURE DE LA PAGE SOURCE (complète ou rien)
# =============================================================================
@dataclass
class Entry:
    block_id: str
    type: str
    url: str
    key: str
    caption: str = ''
    order: int = 0
    depth: int = 0
    in_synced: bool = False
    has_children: bool = False
    created_time: str = ''
    last_edited_time: str = ''
    parent: Optional[Dict] = None

    @property
    def is_link_block(self) -> bool:
        return self.type in DELETABLE_TYPES


@dataclass
class SourceScan:
    entries: List[Entry] = field(default_factory=list)
    blocks_read: int = 0
    repeated_ids: int = 0
    out_of_scope: List[Tuple[str, str]] = field(default_factory=list)
    synced_copies: List[str] = field(default_factory=list)


def _plain_text(rich) -> str:
    if not isinstance(rich, list):
        return ''
    parts = []
    for item in rich:
        if isinstance(item, dict):
            parts.append(item.get('plain_text') or (item.get('text') or {}).get('content') or '')
    return ''.join(parts).strip()


def _text_links(rich) -> List[str]:
    """URL présentes dans un texte riche : liens explicites et URL GitHub écrites en clair."""
    if not isinstance(rich, list):
        return []
    urls = []
    for item in rich:
        if not isinstance(item, dict):
            continue
        text = item.get('text') or {}
        href = item.get('href') or (text.get('link') or {}).get('url')
        if href:
            urls.append(href)
        content = text.get('content') or item.get('plain_text') or ''
        urls.extend(u.rstrip('.,;:!?') for u in _RAW_GITHUB_URL_RE.findall(content))
    return urls


def read_source(nc: NotionClient, root_id: str, max_depth: int = MAX_DEPTH) -> SourceScan:
    """Lit TOUTE la page source (hors sous-pages, bases et copies synchronisées).

    Lève PartialRead si une partie quelconque n'a pas pu être lue.
    """
    scan = SourceScan()
    seen = set()

    def walk(parent_id: str, depth: int, in_synced: bool) -> None:
        if depth > max_depth:
            raise PartialRead(f"profondeur maximale ({max_depth}) dépassée sous le bloc {parent_id}")
        for block in nc.list_children(parent_id):
            if not isinstance(block, dict) or not block.get('id'):
                raise PartialRead(f"bloc sans identifiant sous {parent_id}")
            block_id = block['id']
            if norm_id(block_id) in seen:          # même bloc vu deux fois : ignoré
                scan.repeated_ids += 1
                continue
            seen.add(norm_id(block_id))
            scan.blocks_read += 1
            btype = block.get('type') or ''
            if btype in NO_DESCEND_TYPES:
                scan.out_of_scope.append((block_id, btype))
                continue
            payload = block.get(btype)
            payload = payload if isinstance(payload, dict) else {}
            common = dict(order=scan.blocks_read, depth=depth, in_synced=in_synced,
                          has_children=bool(block.get('has_children')),
                          created_time=block.get('created_time') or '',
                          last_edited_time=block.get('last_edited_time') or '',
                          parent=block.get('parent'))
            if btype in DELETABLE_TYPES:
                url = payload.get('url') or ''
                key = strict_github_key(url)
                if key:
                    scan.entries.append(Entry(block_id, btype, url, key,
                                              caption=_plain_text(payload.get('caption')), **common))
            elif btype in TEXT_TYPES:
                keys = set()
                for url in _text_links(payload.get('rich_text')):
                    key = strict_github_key(url)
                    if key and key not in keys:
                        keys.add(key)
                        scan.entries.append(Entry(block_id, btype, url, key, **common))
            if block.get('has_children'):
                if btype == 'synced_block' and payload.get('synced_from') is not None:
                    scan.synced_copies.append(block_id)   # copie : contenu d'un autre bloc, non parcouru
                    continue
                walk(block_id, depth + 1, in_synced or btype == 'synced_block')

    walk(root_id, 0, False)
    return scan


# =============================================================================
# PLAN DE SUPPRESSION
# =============================================================================
@dataclass
class Plan:
    deletions: List[Tuple[Entry, Entry]] = field(default_factory=list)            # (à supprimer, conservé)
    manual: List[Tuple[Entry, str, Optional[Entry]]] = field(default_factory=list)  # (bloc, raison, conservé)
    duplicate_links: int = 0


def keeper_rank(entry: Entry):
    """Bloc conservé : premier niveau, puis avec légende, puis le plus ancien, puis ordre de lecture."""
    return (entry.depth > 0, entry.caption == '', entry.created_time or '9999', entry.order)


def _manual_reason(entry: Entry, keeper: Entry) -> Optional[str]:
    if not entry.is_link_block:
        return "lien dans du texte (jamais supprimé)"
    if entry.in_synced:
        return "bloc synchronisé (jamais supprimé)"
    if entry.has_children:
        return "bloc avec enfants"
    if entry.caption and entry.caption not in keeper.caption:
        return "légende absente du bloc conservé"
    return None


def build_plan(entries: List[Entry]) -> Plan:
    groups: Dict[str, Dict[str, Entry]] = {}
    for entry in entries:
        groups.setdefault(entry.key, {}).setdefault(norm_id(entry.block_id), entry)  # 1 entrée par bloc

    plan = Plan()
    for by_id in groups.values():
        if len(by_id) < 2:
            continue
        plan.duplicate_links += 1
        candidates = [e for e in by_id.values() if e.is_link_block and not e.in_synced]
        if not candidates:
            plan.manual.extend((e, "aucun bloc lien à conserver", None) for e in by_id.values())
            continue
        keeper = min(candidates, key=keeper_rank)
        for entry in by_id.values():
            if norm_id(entry.block_id) == norm_id(keeper.block_id):
                continue
            reason = _manual_reason(entry, keeper)
            if reason:
                plan.manual.append((entry, reason, keeper))
            else:
                plan.deletions.append((entry, keeper))

    # Défense en profondeur : un bloc conservé n'est jamais supprimé, un bloc ne l'est qu'une fois
    keeper_ids = {norm_id(k.block_id) for _, k in plan.deletions}
    seen, safe = set(), []
    for entry, keeper in plan.deletions:
        nid = norm_id(entry.block_id)
        if nid in keeper_ids or nid in seen:
            plan.manual.append((entry, "bloc également conservé ailleurs", keeper))
            continue
        seen.add(nid)
        safe.append((entry, keeper))
    plan.deletions = safe
    return plan


# =============================================================================
# JOURNAL (écrit et synchronisé sur disque AVANT chaque écriture Notion)
# =============================================================================
class Journal:
    """Journal JSONL en ajout seul ; chaque ligne est suivie de flush + os.fsync."""

    def __init__(self, path: Path):
        self.path = path
        self._file = open(path, 'x', encoding='utf-8', newline='\n')

    @classmethod
    def create(cls, base: Path, stamp: str) -> 'Journal':
        folder = base / JOURNAL_DIRNAME
        folder.mkdir(parents=True, exist_ok=True)
        for n in range(1, 100):
            suffix = '' if n == 1 else f'-{n}'
            try:
                return cls(folder / f'cleaner-{stamp}{suffix}.jsonl')
            except FileExistsError:
                continue
        raise OSError(f"impossible de créer un nouveau journal dans {folder}")

    def write(self, record: Dict) -> None:
        self._file.write(json.dumps(record, ensure_ascii=False) + '\n')
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        try:
            self._file.close()
        except OSError:
            pass


def read_journal(path: Path) -> Tuple[List[Dict], List[str]]:
    """Lignes « intent » d'un journal (une par bloc). Renvoie (intents, avertissements).

    Une dernière ligne tronquée (arrêt brutal pendant l'écriture) est ignorée : la suppression
    correspondante n'a pas pu être envoyée, puisque le journal est écrit avant.
    """
    with open(path, encoding='utf-8') as f:
        lines = [(n, line.strip()) for n, line in enumerate(f, 1) if line.strip()]
    intents, warnings, seen = [], [], set()
    for idx, (n, line) in enumerate(lines):
        try:
            record = json.loads(line)
        except ValueError:
            if idx == len(lines) - 1:
                warnings.append(f"dernière ligne ({n}) incomplète : ignorée")
                continue
            raise JournalError(f"ligne {n} illisible") from None
        if not isinstance(record, dict):
            raise JournalError(f"ligne {n} inattendue")
        if record.get('event') != 'intent':
            continue
        block_id = record.get('block_id')
        if not isinstance(block_id, str) or not _SAFE_ID_RE.fullmatch(block_id):
            raise JournalError(f"ligne {n} : identifiant de bloc invalide")
        if norm_id(block_id) in seen:
            continue
        seen.add(norm_id(block_id))
        intents.append(record)
    return intents, warnings


# =============================================================================
# SUPPRESSION (relecture, journal, DELETE)
# =============================================================================
@dataclass
class RunResult:
    deleted: List[str] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)
    aborted: Optional[str] = None


def recheck(nc: NotionClient, target: Entry, keeper: Entry) -> Tuple[Optional[str], Optional[Dict]]:
    """Relit le bloc conservé puis la cible. Renvoie (raison d'ignorer, None) ou (None, cible relue)."""
    try:
        current_keeper = nc.get_block(keeper.block_id)
    except PartialRead as e:
        return f"bloc conservé illisible ({e})", None
    if is_trashed(current_keeper):
        return "bloc conservé à la corbeille", None
    keeper_type = current_keeper.get('type')
    keeper_payload = current_keeper.get(keeper_type) or {}
    if (keeper_type not in DELETABLE_TYPES
            or strict_github_key(keeper_payload.get('url') or '') != target.key):
        return "bloc conservé modifié (lien différent)", None
    if _parent_key(current_keeper.get('parent')) != _parent_key(keeper.parent):
        return "bloc conservé déplacé", None

    try:
        current = nc.get_block(target.block_id)
    except PartialRead as e:
        return f"bloc à supprimer illisible ({e})", None
    if norm_id(current.get('id') or target.block_id) == norm_id(current_keeper.get('id') or keeper.block_id):
        return "même bloc que le bloc conservé", None
    if is_trashed(current):
        return "déjà à la corbeille", None
    if current.get('last_edited_time') != target.last_edited_time:
        return "modifié depuis la lecture", None
    payload = current.get(current.get('type')) or {}
    if current.get('type') != target.type or payload.get('url') != target.url:
        return "lien modifié depuis la lecture", None
    if _parent_key(current.get('parent')) != _parent_key(target.parent):
        return "déplacé depuis la lecture", None
    if current.get('has_children'):
        return "bloc avec enfants", None
    caption = _plain_text(payload.get('caption'))
    if caption and caption not in _plain_text(keeper_payload.get('caption')):
        return "légende absente du bloc conservé", None
    return None, current


def apply_deletions(nc: NotionClient, deletions: List[Tuple[Entry, Entry]], journal: Journal,
                    run_id: str, page_id: str, sleep: Callable[[float], None]) -> RunResult:
    result = RunResult()
    total = len(deletions)
    try:
        for i, (target, keeper) in enumerate(deletions, 1):
            if i > 1:
                sleep(WRITE_PAUSE)
            label = f"[{i}/{total}] {target.block_id}"
            reason, current = recheck(nc, target, keeper)
            if reason:
                result.skipped.append((target.block_id, reason))
                print(f"  ⚠️  {label} ignoré : {reason}")
                continue
            try:
                journal.write({
                    'event': 'intent', 'run_id': run_id, 'ts': _utc_now(), 'page_id': page_id,
                    'block_id': target.block_id, 'type': target.type, 'url': target.url,
                    'key': target.key, 'caption': target.caption, 'parent': current.get('parent'),
                    'keeper_id': keeper.block_id, 'keeper_key': keeper.key,
                    'block': current,
                    'restore': {'method': 'PATCH', 'path': f'/v1/blocks/{target.block_id}',
                                'body': {TRASH_FIELD: False}, 'notion_version': NOTION_VERSION},
                })
            except OSError as e:
                result.aborted = f"journal non inscriptible ({e})"
                break
            try:
                status = nc.delete_block(target.block_id)
                error = None if status == 200 else f"HTTP {status}"
            except NetworkError as e:
                status, error = None, str(e)
            if status == 200:
                result.deleted.append(target.block_id)
                print(f"  ✅ {label} supprimé : {_short(target.url, 60)}")
            else:
                result.failed.append((target.block_id, error))
                print(f"  ❌ {label} échec : {error}")
            try:
                journal.write({'event': 'result', 'run_id': run_id, 'ts': _utc_now(),
                               'block_id': target.block_id, 'status': status,
                               'ok': status == 200, 'error': error})
            except OSError as e:
                result.aborted = f"journal non inscriptible ({e})"
                break
    except KeyboardInterrupt:
        result.aborted = "interruption clavier (Ctrl+C)"
    return result


# =============================================================================
# CONFIRMATION
# =============================================================================
def _stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin) and sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def ask_phrase(phrase: str) -> Optional[str]:
    """Demande au clavier la phrase exacte ; terminal interactif obligatoire."""
    if not _stdin_is_tty():
        raise Abort("pas de terminal interactif : confirmation impossible")
    try:
        return input(f"\n❓ Pour confirmer, tapez exactement « {phrase} » (o / oui ne suffisent pas) : ")
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _confirmed(confirm: Callable[[str], Optional[str]], phrase: str) -> bool:
    try:
        answer = confirm(phrase)
    except Abort as e:
        print(f"\n🛑 ABANDON : {e}.")
        return False
    if (answer or '').strip() != phrase:
        print("\n❌ Phrase incorrecte : abandon.")
        return False
    return True


# =============================================================================
# AFFICHAGE
# =============================================================================
def print_plan(scan: SourceScan, plan: Plan, max_delete: int) -> None:
    link_blocks = sum(1 for e in scan.entries if e.is_link_block)
    print(f"\n📊 Analyse :")
    print(f"  • Blocs lus : {scan.blocks_read}")
    print(f"  • Liens GitHub : {len(scan.entries)} (dont {link_blocks} blocs lien)")
    print(f"  • Liens présents plusieurs fois : {plan.duplicate_links}")
    print(f"  • Sous-pages / bases / liens de page non parcourus : {len(scan.out_of_scope)}")
    print(f"  • Copies de blocs synchronisés non parcourues : {len(scan.synced_copies)}")

    if plan.deletions:
        print(f"\n🗑️  DOUBLONS À SUPPRIMER ({len(plan.deletions)}) :")
        for i, (entry, keeper) in enumerate(plan.deletions, 1):
            print(f"  [{i}] {entry.url}")
            print(f"      🗑️  supprimé : {entry.block_id} ({entry.type})"
                  + (f" — légende : « {_short(entry.caption)} »" if entry.caption else ""))
            print(f"      📌 conservé : {keeper.block_id} ({keeper.type})"
                  + (f" — légende : « {_short(keeper.caption)} »" if keeper.caption else ""))

    if plan.manual:
        print(f"\n✋ À TRAITER À LA MAIN ({len(plan.manual)}) — non supprimés :")
        for entry, reason, keeper in plan.manual:
            print(f"  • {entry.url}")
            print(f"      bloc {entry.block_id} ({entry.type}) : {reason}"
                  + (f" — légende : « {_short(entry.caption)} »" if entry.caption else ""))
            if keeper is not None:
                print(f"      bloc conservé : {keeper.block_id}")

    if len(plan.deletions) > max_delete:
        print(f"\n⚠️  {len(plan.deletions)} suppressions prévues > plafond CLEANER_MAX_DELETE={max_delete} :"
              f" --apply abandonnerait sans rien supprimer.")


def print_summary(result: RunResult, planned: int, journal_path: Optional[Path]) -> None:
    print("\n" + "=" * 70)
    print("📊 BILAN")
    print(f"  ✅ Supprimés : {len(result.deleted)} / {planned} prévus")
    print(f"  ⚠️  Ignorés (relecture) : {len(result.skipped)}")
    for block_id, reason in result.skipped:
        print(f"      - {block_id} : {reason}")
    print(f"  ❌ Échecs : {len(result.failed)}")
    for block_id, error in result.failed:
        print(f"      - {block_id} : {error}")
    if result.aborted:
        print(f"  🛑 Arrêt avant la fin : {result.aborted}")
    if journal_path is not None:
        print(f"  📝 Journal : {journal_path}")
        if result.deleted or result.failed:
            print(f"  ♻️  Annuler : python clean_page_duplicates.py --restore \"{journal_path}\"")
    print("=" * 70)


# =============================================================================
# NETTOYAGE
# =============================================================================
_ROOT_HINTS = {
    401: "jeton refusé : vérifiez NOTION_CLEANER_TOKEN / NOTION_TOKEN",
    403: "accès refusé : partagez la page source avec l'intégration Notion",
    404: "page introuvable : vérifiez PARENT_PAGE_ID et partagez la page avec l'intégration",
}


def run_clean(cfg: Config, nc: NotionClient, apply: bool,
              confirm: Callable[[str], Optional[str]], sleep: Callable[[float], None]) -> int:
    print(f"📄 Page source : {cfg.page_id}")
    print("🔍 MODE SUPPRESSION (--apply)" if apply else "🔍 MODE SIMULATION : aucune suppression")
    print("\n📥 Lecture complète de la page source...")
    try:
        scan = read_source(nc, cfg.page_id)
    except PartialRead as e:
        print(f"\n❌ Lecture incomplète : {e}")
        if e.status in _ROOT_HINTS and e.path == f'/blocks/{cfg.page_id}/children':
            print(f"💡 {_ROOT_HINTS[e.status]}")
            return EXIT_CONFIG
        print("🛑 ABANDON : aucune suppression (la page doit être lue en entier).")
        return EXIT_ABORT

    plan = build_plan(scan.entries)
    print_plan(scan, plan, cfg.max_delete)

    if not plan.deletions:
        print("\n✅ Aucun doublon supprimable.")
        return EXIT_OK
    if not apply:
        print("\n🔍 SIMULATION : aucune suppression effectuée.")
        print("💡 Pour supprimer : python clean_page_duplicates.py --apply")
        return EXIT_OK

    planned = len(plan.deletions)
    if planned > cfg.max_delete:
        print(f"\n🛑 ABANDON : {planned} suppressions > plafond CLEANER_MAX_DELETE={cfg.max_delete}."
              " Aucune suppression.")
        return EXIT_ABORT
    if not _confirmed(confirm, f"SUPPRIMER {planned}"):
        print("Aucune suppression.")
        return EXIT_ABORT

    run_id = datetime.now().strftime('%Y%m%d-%H%M%S')
    try:
        journal = Journal.create(base_dir(), run_id)
        journal.write({'event': 'start', 'run_id': run_id, 'ts': _utc_now(), 'page_id': cfg.page_id,
                       'notion_version': NOTION_VERSION, 'trash_field': TRASH_FIELD,
                       'planned': planned})
    except OSError as e:
        print(f"\n❌ Journal impossible à écrire ({e}).")
        print("🛑 ABANDON : aucune suppression sans journal.")
        return EXIT_ABORT

    print(f"\n📝 Journal : {journal.path}")
    print("🗑️  Suppression en cours...")
    try:
        result = apply_deletions(nc, plan.deletions, journal, run_id, cfg.page_id, sleep)
        try:
            journal.write({'event': 'end', 'run_id': run_id, 'ts': _utc_now(),
                           'deleted': len(result.deleted), 'skipped': len(result.skipped),
                           'failed': len(result.failed), 'aborted': result.aborted})
        except OSError:
            pass
    finally:
        journal.close()

    print_summary(result, planned, journal.path)
    return EXIT_ABORT if (result.failed or result.aborted) else EXIT_OK


# =============================================================================
# RESTAURATION
# =============================================================================
def run_restore(journal_arg: str, nc: NotionClient, apply: bool,
                confirm: Callable[[str], Optional[str]], sleep: Callable[[float], None]) -> int:
    path = Path(journal_arg).expanduser()
    print(f"♻️  RESTAURATION depuis : {path}")
    print("🔍 MODE RESTAURATION (--apply)" if apply else "🔍 MODE SIMULATION : aucune restauration")
    if not path.is_file():
        print("❌ Journal introuvable.")
        return EXIT_CONFIG
    try:
        intents, warnings = read_journal(path)
    except (OSError, UnicodeDecodeError, JournalError) as e:
        print(f"❌ Journal illisible : {e}")
        print("🛑 ABANDON : aucune restauration.")
        return EXIT_ABORT
    for warning in warnings:
        print(f"⚠️  {warning}")
    if not intents:
        print("✅ Aucune suppression dans ce journal : rien à restaurer.")
        return EXIT_OK

    to_restore, in_place = [], []
    for record in intents:
        try:
            current = nc.get_block(record['block_id'])
        except PartialRead as e:
            to_restore.append((record, f"état inconnu ({e})"))
            continue
        if is_trashed(current):
            to_restore.append((record, "à la corbeille"))
        else:
            in_place.append(record)

    print(f"\n📊 {len(intents)} bloc(s) dans le journal ; {len(in_place)} déjà en place ;"
          f" {len(to_restore)} à restaurer :")
    for record, state in to_restore:
        caption = record.get('caption') or ''
        print(f"  • {record['block_id']} ({state}) : {record.get('url', '')}"
              + (f" — légende : « {_short(caption)} »" if caption else ""))
    if not to_restore:
        print("\n✅ Rien à restaurer.")
        return EXIT_OK
    if not apply:
        print("\n🔍 SIMULATION : aucune restauration effectuée.")
        print(f"💡 Pour restaurer : python clean_page_duplicates.py --restore \"{path}\" --apply")
        return EXIT_OK
    if not _confirmed(confirm, f"RESTAURER {len(to_restore)}"):
        print("Aucune restauration.")
        return EXIT_ABORT

    restored, failed = [], []
    for i, (record, _) in enumerate(to_restore, 1):
        if i > 1:
            sleep(WRITE_PAUSE)
        block_id = record['block_id']
        try:
            status = nc.restore_block(block_id)
            error = None if status == 200 else f"HTTP {status}"
        except NetworkError as e:
            status, error = None, str(e)
        if status == 200:
            restored.append(block_id)
            print(f"  ✅ [{i}/{len(to_restore)}] restauré : {block_id}")
        else:
            failed.append((block_id, error))
            print(f"  ❌ [{i}/{len(to_restore)}] échec : {block_id} ({error})")

    print("\n" + "=" * 70)
    print("📊 BILAN")
    print(f"  ✅ Restaurés : {len(restored)} / {len(to_restore)}")
    print(f"  ❌ Échecs : {len(failed)}")
    for block_id, error in failed:
        print(f"      - {block_id} : {error}")
    print("=" * 70)
    return EXIT_ABORT if failed else EXIT_OK


# =============================================================================
# MAIN
# =============================================================================
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"❌ {message}", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog='clean_page_duplicates.py',
        description="Retire les blocs doublons de liens GitHub de la page source Notion "
                    "(simulation par défaut).")
    parser.add_argument('--apply', action='store_true',
                        help="effectuer réellement l'opération (confirmation au clavier exigée)")
    parser.add_argument('--restore', metavar='JOURNAL',
                        help="remettre en place les blocs supprimés listés dans un journal .jsonl")
    return parser


def main(argv: Optional[List[str]] = None, *, session=None,
         confirm: Optional[Callable[[str], Optional[str]]] = None,
         sleep: Callable[[float], None] = time.sleep) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (EXIT_OK if e.code is None else EXIT_CONFIG)

    _safe_console()
    base = base_dir()
    print("=" * 70)
    print("🧹 NETTOYEUR DE DOUBLONS - PAGE SOURCE NOTION")
    print("=" * 70)
    print(f"📂 Dossier : {base}")
    print(f"📄 Fichier .env : {load_env_file(base)}")

    try:
        cfg = read_config(require_page=not args.restore)
    except ConfigError as e:
        print(f"\n❌ {e}")
        return EXIT_CONFIG

    print(f"🔑 Jeton : {_mask_token(cfg.token)} ({cfg.token_source})")
    if cfg.token_source != 'NOTION_CLEANER_TOKEN':
        print("⚠️  NOTION_CLEANER_TOKEN absent : utilisation de NOTION_TOKEN.")
        print("    Conseil : créez une intégration Notion dédiée au nettoyeur (capacité « Update content »)")
        print("    et limitez celle du script principal à Lecture + Insertion.")

    nc = NotionClient(cfg.token, session=session, sleep=sleep)
    confirm = confirm or ask_phrase
    if args.restore:
        return run_restore(args.restore, nc, args.apply, confirm, sleep)
    return run_clean(cfg, nc, args.apply, confirm, sleep)


if __name__ == '__main__':
    sys.exit(main())
