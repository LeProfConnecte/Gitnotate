#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redécouverte — retrouver, hors ligne, les dépôts déjà enregistrés dans la base Notion de Gitnotate.

    python redecouverte.py sync     copie locale des fiches (Notion est seulement lu)
    python redecouverte.py etat     état de la copie locale
    python redecouverte.py cherche  recherche hors ligne (prochaine étape du moteur)

Garanties :
  - Notion est seulement LU : deux appels autorisés, vérifiés avant tout envoi par une liste blanche
    (GET /v1/databases/{id}, POST /v1/databases/{id}/query) ; aucune écriture, aucun appel à GitHub.
  - Synchronisation « tout ou rien » : lecture intégrale et validée, construction dans un fichier
    temporaire contrôlé (intégrité, comptes, absence de jeton), puis remplacement atomique. Toute erreur,
    tout Ctrl-C conserve l'index précédent. Verrou du système : une seule synchronisation à la fois.
  - Seul fichier écrit : BASE_DIR/.gitnotate_index/redecouverte.sqlite (régénérable : supprimer le dossier
    ne fait rien perdre), et la capture demandée par « sync --capture ».
  - Rien n'est inventé : chaque champ garde son texte (normalisé) et son niveau de fiabilité ; les
    gabarits des anciennes versions de Gitnotate et les « Non vérifié » ne sont jamais indexés ; la
    version d'une fiche n'est jamais devinée d'après sa date.

Codes de sortie : 0 succès · 1 configuration, index absent ou FTS5 absent · 2 lecture Notion incomplète
ou refusée (index précédent conservé) · 130 interruption (Ctrl-C).
"""

import argparse
import contextlib
import dataclasses
import json
import math
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import gitnotate as gn
import redecouverte_lexique as lexique

try:
    import fcntl
except ImportError:                 # Windows
    fcntl = None
try:
    import msvcrt
except ImportError:                 # POSIX
    msvcrt = None

__version__ = "1.0.0"

# =============================================================================
# CONSTANTES (aucune variable d'environnement)
# =============================================================================
FORMAT_INDEX = 1                     # PRAGMA user_version et meta['format_index']
FORMAT_CAPTURE = 'gitnotate-capture/1'
NOTION_VERSION = '2022-06-28'        # doit égaler gn.NOTION_HEADERS['Notion-Version']
NOTION_API = 'https://api.notion.com'
DOSSIER_INDEX = '.gitnotate_index'
NOM_INDEX = 'redecouverte.sqlite'
NOM_VERROU = 'sync.lock'
DOSSIER_EXPORTS = 'exports'
TOKENIZER = "unicode61 remove_diacritics 2"
PAGE_SIZE = 100
MAX_REPONSES = 1000
BAISSE_MIN_FICHES = 10
BAISSE_MIN_PART = 0.10
REMPLACEMENT_ESSAIS = 20
REMPLACEMENT_PAUSE = 0.25            # secondes
ATTENTE_FIL = 0.5                    # secondes (Ctrl-C réactif sous Windows)
AGE_ALERTE_JOURS = 30
MODIF_APRES_CREATION_S = 120
RESULTATS_MAX = 50                   # REDECOUVERTE_RESULTATS : 1 à 50
LLM_MAX_MAX = 15                     # REDECOUVERTE_LLM_MAX : 1 à 15
NOMS_AFFICHES_MAX = 10               # noms des fiches disparues listés
MASQUE = '[jeton masqué]'
COMMANDES = ('sync', 'cherche', 'etat')

# =============================================================================
# ERREURS
# =============================================================================
class EcritureNotionInterdite(Exception):
    """Erreur de programmation : appel Notion hors de la liste blanche. Jamais rattrapée en silence."""


class Arret(Exception):
    """Arrêt contrôlé d'une commande : code de sortie et message en français (jamais de jeton)."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

# =============================================================================
# CONFIGURATION (même .env que gitnotate.py, lu à l'appel)
# =============================================================================
@dataclass(frozen=True)
class Config:
    jeton: str                 # NOTION_READONLY_TOKEN, sinon gn.NOTION_TOKEN
    source_jeton: str          # 'NOTION_READONLY_TOKEN' | 'NOTION_TOKEN' | ''
    database_id: str           # 32 hex minuscules, sans tirets ('' si absent)
    resultats: int             # REDECOUVERTE_RESULTATS
    llm_max: int               # REDECOUVERTE_LLM_MAX
    erreurs: Tuple[str, ...]   # messages en français, sans jeton


_ID_HEX_RE = re.compile(r'[0-9a-f]{32}')


def normaliser_id(valeur: Any) -> str:
    """Identifiant Notion comparable : sans espaces de bord ni tirets, en minuscules."""
    return valeur.strip().replace('-', '').lower() if isinstance(valeur, str) else ''


def _entier_borne(nom: str, defaut: int, maximum: int, erreurs: List[str]) -> int:
    valeur = gn._env_int(nom, defaut, 1)
    # _env_int range son erreur dans gn.CONFIG_ERRORS : reprise ici, sans effet durable sur gitnotate
    message = gn.CONFIG_ERRORS.pop(nom, None)
    if message:
        erreurs.append(message)
    elif valeur > maximum:
        erreurs.append(f"{nom}={valeur} est invalide (maximum : {maximum})")
        valeur = defaut
    return valeur


def lire_config(notion: bool = True) -> Config:
    """Variables du moteur, lues à l'appel. notion=False (sync --depuis, recherche) : ni jeton ni
    DATABASE_ID exigés."""
    erreurs: List[str] = []
    lecture_seule = gn._env_str('NOTION_READONLY_TOKEN')
    if lecture_seule:
        jeton, source = lecture_seule, 'NOTION_READONLY_TOKEN'
    else:
        jeton, source = gn.NOTION_TOKEN or '', ('NOTION_TOKEN' if gn.NOTION_TOKEN else '')
    database_id = normaliser_id(gn.DATABASE_ID)
    resultats = _entier_borne('REDECOUVERTE_RESULTATS', 10, RESULTATS_MAX, erreurs)
    llm_max = _entier_borne('REDECOUVERTE_LLM_MAX', 8, LLM_MAX_MAX, erreurs)
    if notion:
        if not jeton:
            erreurs.append("Jeton Notion manquant — ajoutez NOTION_READONLY_TOKEN=<jeton d'une intégration "
                           "en lecture seule> (ou NOTION_TOKEN) dans .env")
        elif gn._has_blank_or_control(jeton):
            erreurs.append(f"{source} contient un espace ou un saut de ligne — recopiez-le sur une seule "
                           "ligne dans .env")
        if not database_id:
            erreurs.append("DATABASE_ID manquant — ajoutez DATABASE_ID=<32 caractères hexadécimaux de la "
                           "base> dans .env")
        elif not _ID_HEX_RE.fullmatch(database_id):
            erreurs.append("DATABASE_ID invalide : indiquez les 32 caractères hexadécimaux de la base "
                           "(sans l'URL)")
        for cle in ('HTTP_TIMEOUT', 'MAX_RETRIES', 'MAX_WAIT_SECONDS'):
            if cle in gn.CONFIG_ERRORS:
                erreurs.append(gn.CONFIG_ERRORS[cle])
    return Config(jeton, source, database_id, resultats, llm_max, tuple(erreurs))


def erreur_version_notion() -> str:
    """'' si gitnotate.py parle toujours la version de l'API Notion vérifiée pour ce moteur."""
    entetes = gn.NOTION_HEADERS if isinstance(gn.NOTION_HEADERS, dict) else {}
    vue = entetes.get('Notion-Version')
    if vue == NOTION_VERSION:
        return ''
    return (f"Version de l'API Notion inattendue ({vue} au lieu de {NOTION_VERSION}) : le moteur de "
            "redécouverte doit être vérifié avant toute migration")

# =============================================================================
# NOTION : LISTE BLANCHE ET APPEL INTERRUPTIBLE (seul accès à api.notion.com)
# =============================================================================
_LECTURES_AUTORISEES = (
    ('GET',  re.compile(r'^/v1/databases/[0-9a-f]{32}$')),
    ('POST', re.compile(r'^/v1/databases/[0-9a-f]{32}/query$')),
)
_CLES_CORPS_QUERY = frozenset({'page_size', 'start_cursor', 'sorts'})


def _verifier_appel(methode: Any, chemin: Any, corps: Any) -> None:
    """Garde technique : tout appel hors liste blanche lève EcritureNotionInterdite AVANT le réseau."""
    autorise = (isinstance(methode, str) and isinstance(chemin, str)
                and any(methode == m and rx.fullmatch(chemin) for m, rx in _LECTURES_AUTORISEES))
    if not autorise:
        raise EcritureNotionInterdite(f"Appel Notion refusé (hors liste blanche) : {methode} {str(chemin)[:80]}")
    if methode == 'GET' and corps:
        raise EcritureNotionInterdite("Appel Notion refusé : corps inattendu pour une lecture GET")
    if methode == 'POST' and (not isinstance(corps, dict) or not set(corps) <= _CLES_CORPS_QUERY):
        cles = sorted(set(corps) - _CLES_CORPS_QUERY) if isinstance(corps, dict) else ['(corps non objet)']
        raise EcritureNotionInterdite(f"Appel Notion refusé : clés de requête interdites {cles}")


def _appel_notion(methode: str, chemin: str, corps: Optional[Dict] = None,
                  jeton: str = '') -> Tuple[Optional[Any], str]:
    """Seul point d'accès à api.notion.com. Garde, en-têtes (jeton de lecture), puis appel de
    gn.http_request_with_retry dans un fil « daemon » : le fil principal attend par petites tranches,
    Ctrl-C reste immédiat sous Windows. Renvoie (réponse ou None, cause de l'échec réseau)."""
    _verifier_appel(methode, chemin, corps)
    erreur = erreur_version_notion()
    if erreur:
        raise Arret(gn.EXIT_CONFIG, erreur)
    if not jeton:
        raise ValueError("appel Notion sans jeton (erreur de programmation)")
    entetes = dict(gn.NOTION_HEADERS)
    entetes['Authorization'] = f'Bearer {jeton}'
    url = NOTION_API + chemin
    issue: Dict[str, Any] = {}

    def _fil() -> None:
        try:
            reponse = gn.http_request_with_retry(methode, url, entetes, json_data=corps)
            # La cause d'un échec réseau est propre au fil : elle est lue ici
            issue['resultat'] = (reponse, gn.last_http_error() if reponse is None else '')
        except BaseException as e:          # Ctrl-C compris : relancée dans le fil principal
            issue['erreur'] = e

    fil = threading.Thread(target=_fil, name='redecouverte-notion', daemon=True)
    fil.start()
    try:
        while fil.is_alive():
            fil.join(ATTENTE_FIL)
    except KeyboardInterrupt:
        gn._STOP_EVENT.set()                # plus aucune nouvelle tentative dans le fil abandonné
        raise
    if 'erreur' in issue:
        if isinstance(issue['erreur'], KeyboardInterrupt):
            gn._STOP_EVENT.set()
        raise issue['erreur']
    return issue['resultat']


def _pistes() -> Dict[int, str]:
    pistes = dict(gn._NOTION_DB_HINTS)
    pistes[401] = "jeton Notion invalide ou révoqué (NOTION_READONLY_TOKEN, sinon NOTION_TOKEN)"
    pistes[403] = ("l'intégration doit avoir la capacité « Read content » et être connectée à la base "
                   "(menu ••• de la base > Connexions)")
    return pistes


def _decrire_echec(reponse: Any, cause: str) -> str:
    if reponse is None:
        return f"pas de réponse ({cause or 'réseau'}) — réseau ou timeout"
    return gn._describe_failure(reponse, _pistes())


def _texte_riche(segments: Any) -> str:
    if not isinstance(segments, list):
        return ''
    return ''.join(s['plain_text'] for s in segments
                   if isinstance(s, dict) and isinstance(s.get('plain_text'), str))


def _resoudre_nom(canonique: str, schema: Dict[str, str]) -> Tuple[str, List[str]]:
    """Nom réel d'une colonne : nom exact, sinon l'unique colonne de même forme repliée."""
    if canonique in schema:
        return canonique, [canonique]
    pli = gn._fold(canonique)
    candidates = [nom for nom in schema if gn._fold(nom) == pli]
    return (candidates[0] if len(candidates) == 1 else ''), candidates


def verifier_schema(schema: Dict[str, str]) -> str:
    """V11 : une colonne titre et une colonne URL lisible ; '' si la base ressemble à une base Gitnotate."""
    if sum(1 for t in schema.values() if t == 'title') != 1:
        return ("Cette base ne ressemble pas à une base Gitnotate (colonne titre introuvable) : "
                "vérifiez DATABASE_ID")
    nom, _ = _resoudre_nom('URL', schema)
    if not nom or schema[nom] not in ('url', 'rich_text', 'title'):
        return ("Cette base ne ressemble pas à une base Gitnotate (colonne URL absente) : "
                "vérifiez DATABASE_ID")
    return ''


def lire_schema(cfg: Config) -> Dict[str, Any]:
    """GET /v1/databases/{id} : identifiant, titre et {colonne: type}."""
    reponse, cause = _appel_notion('GET', f'/v1/databases/{cfg.database_id}', jeton=cfg.jeton)
    if reponse is None or reponse.status_code == 429 or reponse.status_code >= 500:
        raise Arret(gn.EXIT_INCOMPLETE, "Lecture du schéma de la base impossible (incident passager, "
                    f"relancez plus tard) : {_decrire_echec(reponse, cause)}")
    if reponse.status_code != 200:
        raise Arret(gn.EXIT_CONFIG, f"Base Notion illisible : {_decrire_echec(reponse, cause)}")
    data = gn._json_dict(reponse)
    if data is None or not isinstance(data.get('properties'), dict):
        raise Arret(gn.EXIT_CONFIG, "Schéma de la base illisible (réponse inattendue de Notion)")
    if data.get('in_trash') or data.get('archived'):
        raise Arret(gn.EXIT_CONFIG, "La base Notion est dans la corbeille : restaurez-la ou vérifiez DATABASE_ID")
    if normaliser_id(data.get('id')) != cfg.database_id:
        raise Arret(gn.EXIT_CONFIG, "Notion a renvoyé une autre base que DATABASE_ID : vérifiez l'identifiant")
    schema = {nom: p['type'] for nom, p in data['properties'].items()
              if isinstance(nom, str) and isinstance(p, dict) and isinstance(p.get('type'), str)}
    erreur = verifier_schema(schema)
    if erreur:
        raise Arret(gn.EXIT_CONFIG, erreur)
    return {'id': cfg.database_id, 'titre': normaliser(_texte_riche(data.get('title'))), 'schema': schema}


@dataclass
class Lecture:
    pages: List[Dict[str, Any]]
    nb_requetes: int
    nb_objets_recus: int
    ignorees: Dict[str, int]


def _abandon(num: int, motif: str) -> Arret:
    return Arret(gn.EXIT_INCOMPLETE, f"Lecture interrompue (réponse {num}) : {motif}. "
                                     "L'index précédent est conservé.")


def lire_pages(cfg: Config) -> Lecture:
    """POST /v1/databases/{id}/query, toutes les réponses en mémoire, contrôles V1 à V9 : lecture
    complète ou Arret (code 2), jamais de résultat partiel."""
    chemin = f'/v1/databases/{cfg.database_id}/query'
    corps: Dict[str, Any] = {'page_size': PAGE_SIZE,
                             'sorts': [{'timestamp': 'created_time', 'direction': 'ascending'}]}
    pages: List[Dict[str, Any]] = []
    vus: Set[str] = set()
    curseurs: Set[str] = set()
    ignorees = {'corbeille': 0, 'base_imbriquee': 0}
    recus = 0
    num = 0
    while True:
        num += 1
        if num > MAX_REPONSES:                                                       # V4
            raise _abandon(num, "pagination anormalement longue")
        reponse, cause = _appel_notion('POST', chemin, corps, jeton=cfg.jeton)
        if reponse is None or reponse.status_code != 200:                            # V1
            raise _abandon(num, _decrire_echec(reponse, cause))
        data = gn._json_dict(reponse)
        if (data is None or data.get('object') != 'list' or not isinstance(data.get('results'), list)
                or not isinstance(data.get('has_more', False), bool)):
            raise _abandon(num, "réponse illisible (liste de fiches attendue)")
        statut = data.get('request_status')
        if isinstance(statut, dict) and statut.get('type') == 'incomplete':          # V5
            raise _abandon(num, "Notion signale une lecture incomplète")
        for objet in data['results']:
            recus += 1
            if isinstance(objet, dict) and objet.get('object') == 'database':        # V6
                ignorees['base_imbriquee'] += 1
                continue
            if (not isinstance(objet, dict) or objet.get('object') != 'page'
                    or not isinstance(objet.get('id'), str) or not isinstance(objet.get('properties'), dict)):
                raise _abandon(num, "fiche illisible : vérifiez le partage de l'intégration")
            parent = objet.get('parent')
            if normaliser_id(parent.get('database_id') if isinstance(parent, dict) else '') != cfg.database_id:
                raise _abandon(num, "page d'une autre base reçue")                     # V7
            page_id = normaliser_id(objet['id'])
            if page_id in vus:                                                        # V8
                raise _abandon(num, "fiche reçue deux fois : la base a changé pendant la lecture — "
                                    "relancez sync")
            vus.add(page_id)
            if objet.get('in_trash') or objet.get('archived'):                       # V9
                ignorees['corbeille'] += 1
                continue
            pages.append(objet)
        gn.log(f"   Réponse {num} : {len(data['results'])} objets reçus", 'verbose')
        if not data.get('has_more'):
            break
        curseur = data.get('next_cursor')
        if not isinstance(curseur, str) or not curseur:                              # V2
            raise _abandon(num, "has_more sans next_cursor")
        if curseur in curseurs:                                                       # V3
            raise _abandon(num, "curseur répété : pagination incohérente")
        curseurs.add(curseur)
        corps = dict(corps, start_cursor=curseur)
    return Lecture(pages, num, recus, ignorees)

# =============================================================================
# JETONS : MASQUAGE ET ANALYSE DES OCTETS
# =============================================================================
_NOMS_SECRETS = ('NOTION_TOKEN', 'NOTION_READONLY_TOKEN', 'NOTION_CLEANER_TOKEN', 'GITHUB_TOKEN',
                 'MISTRAL_API_KEY', 'OPENROUTER_API_KEY')
_MOTIFS_JETONS = re.compile(r'ntn_[A-Za-z0-9]{20,}|secret_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}'
                            r'|github_pat_[A-Za-z0-9_]{20,}|sk-or-v1-[0-9a-f]{20,}')


def secrets_connus() -> Tuple[str, ...]:
    """Valeurs (8 caractères ou plus) des jetons et clés configurés, lues à l'appel."""
    valeurs: Set[str] = set()
    for nom in _NOMS_SECRETS:
        for valeur in (gn._env_str(nom), getattr(gn, nom, '')):
            if isinstance(valeur, str) and len(valeur) >= 8:
                valeurs.add(valeur)
    return tuple(sorted(valeurs, key=lambda s: (-len(s), s)))


def masquer(texte: str, secrets: Iterable[str] = ()) -> str:
    """Chaque secret connu (toute casse), puis les formes de jetons connues -> « [jeton masqué] »."""
    for secret in secrets:
        texte = re.sub(re.escape(secret), MASQUE, texte, flags=re.IGNORECASE)
    return _MOTIFS_JETONS.sub(MASQUE, texte)


def contient_secret(donnees: bytes, secrets: Iterable[str]) -> bool:
    """Analyse des octets avant toute publication : chaque secret et sa forme minuscule."""
    for secret in secrets:
        for forme in {secret, secret.lower()}:
            if forme.encode('utf-8') in donnees:
                return True
    return False

# =============================================================================
# APLATISSEMENT TOLÉRANT DES PAGES (ne lève jamais d'exception)
# =============================================================================
_TABLE_NORMALISATION = {0x00A0: ' ', 0x202F: ' ', 0x2009: ' ', 0x2011: '-', 0x2010: '-', 0x2019: "'"}
TYPES_CONSERVES = frozenset({'title', 'rich_text', 'select', 'status', 'multi_select', 'url', 'number',
                             'date', 'formula'})
_ANNOTATIONS = ('bold', 'italic', 'strikethrough', 'underline', 'code')


def normaliser(texte: str) -> str:
    """Forme « verbatim » d'un texte : NFC, espaces et traits d'union insécables simplifiés, apostrophe
    typographique droite, espaces de fin retirés."""
    return unicodedata.normalize('NFC', texte).translate(_TABLE_NORMALISATION).rstrip()


@dataclass(frozen=True)
class ValeurPlate:             # une propriété aplatie
    type: str                  # type Notion ('' : propriété illisible)
    texte: str = ''            # title, rich_text, select, status, url, date, formula
    valeurs: Tuple[str, ...] = ()   # multi_select
    nombre: Optional[float] = None  # number, formula number
    segments: int = 0          # title/rich_text : nombre de segments
    mise_en_forme: bool = False     # annotation non par défaut, lien ou couleur
    mentions: int = 0
    illisible: bool = False    # valeur de forme imprévue (signalée, jamais interprétée)


@dataclass(frozen=True)
class PagePlate:               # entrée de construction ; format de la capture
    page_id: str               # 32 hex minuscules
    url_notion: str
    cree_le: str               # created_time ISO
    modifie_le: str            # last_edited_time ISO
    colonnes: Dict[str, ValeurPlate]


def _nombre(valeur: Any) -> Optional[float]:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not math.isfinite(valeur):
        return None
    return float(valeur)


def _texte_nombre(nombre: float) -> str:
    return str(int(nombre)) if nombre.is_integer() else repr(nombre)


def _segment_texte(seg: Dict[str, Any]) -> str:
    texte = seg.get('plain_text')
    if isinstance(texte, str):
        return texte
    for cle, sous_cle in (('text', 'content'), ('equation', 'expression')):
        bloc = seg.get(cle)
        if isinstance(bloc, dict) and isinstance(bloc.get(sous_cle), str):
            return bloc[sous_cle]
    return ''


def _segment_mis_en_forme(seg: Dict[str, Any]) -> bool:
    annotations = seg.get('annotations')
    if isinstance(annotations, dict) and (any(annotations.get(a) is True for a in _ANNOTATIONS)
                                          or annotations.get('color') not in (None, 'default')):
        return True
    texte = seg.get('text')
    return bool(seg.get('href')) or (isinstance(texte, dict) and bool(texte.get('link')))


def _valeur_plate(kind: str, val: Any) -> ValeurPlate:
    illisible = ValeurPlate(kind, illisible=True)
    if val is None:
        return ValeurPlate(kind)
    if kind in ('title', 'rich_text'):
        if not isinstance(val, list):
            return illisible
        segments = [s for s in val if isinstance(s, dict)]
        return ValeurPlate(kind, texte=normaliser(''.join(_segment_texte(s) for s in segments)),
                           segments=len(segments),
                           mise_en_forme=any(_segment_mis_en_forme(s) for s in segments),
                           mentions=sum(1 for s in segments if s.get('type') == 'mention'),
                           illisible=len(segments) != len(val))
    if kind in ('select', 'status'):
        if not isinstance(val, dict):
            return illisible
        nom = val.get('name')
        return ValeurPlate(kind, texte=normaliser(nom) if isinstance(nom, str) else '')
    if kind == 'multi_select':
        if not isinstance(val, list):
            return illisible
        noms = (normaliser(o['name']) for o in val if isinstance(o, dict) and isinstance(o.get('name'), str))
        return ValeurPlate(kind, valeurs=tuple(n for n in noms if n),
                           illisible=any(not isinstance(o, dict) for o in val))
    if kind == 'url':
        return ValeurPlate(kind, texte=normaliser(val)) if isinstance(val, str) else illisible
    if kind == 'number':
        nombre = _nombre(val)
        return ValeurPlate(kind, nombre=nombre) if nombre is not None else illisible
    if kind == 'date':
        if not isinstance(val, dict):
            return illisible
        debut = val.get('start')
        return ValeurPlate(kind, texte=normaliser(debut) if isinstance(debut, str) else '')
    # formula : chaîne, nombre ou date ; booléen ignoré
    if not isinstance(val, dict):
        return illisible
    sorte = val.get('type')
    interieur = val.get(sorte) if isinstance(sorte, str) else None
    if sorte == 'string':
        return ValeurPlate(kind, texte=normaliser(interieur) if isinstance(interieur, str) else '')
    if sorte == 'number':
        nombre = _nombre(interieur)
        return ValeurPlate(kind, texte=_texte_nombre(nombre) if nombre is not None else '', nombre=nombre)
    if sorte == 'date' and isinstance(interieur, dict) and isinstance(interieur.get('start'), str):
        return ValeurPlate(kind, texte=normaliser(interieur['start']))
    return ValeurPlate(kind)


def texte_propriete(prop: Any) -> Optional[ValeurPlate]:
    """Propriété Notion -> ValeurPlate ; None pour un type non conservé (personnes, fichiers, case à
    cocher, relation…) ou une propriété qui n'est pas un objet. Ne lève jamais d'exception."""
    if not isinstance(prop, dict):
        return None
    kind = prop.get('type')
    if not isinstance(kind, str) or kind not in TYPES_CONSERVES:
        return None
    try:
        return _valeur_plate(kind, prop.get(kind))
    except Exception:                   # forme imprévue : signalée, jamais interprétée
        return ValeurPlate(kind, illisible=True)


def _masquer_valeur(valeur: ValeurPlate, secrets: Iterable[str]) -> ValeurPlate:
    secrets = tuple(secrets)
    texte = masquer(valeur.texte, secrets)
    valeurs = tuple(masquer(v, secrets) for v in valeur.valeurs)
    if texte == valeur.texte and valeurs == valeur.valeurs:
        return valeur
    return dataclasses.replace(valeur, texte=texte, valeurs=valeurs)


def _masquer_plate(plate: PagePlate, secrets: Iterable[str]) -> PagePlate:
    secrets = tuple(secrets)
    return dataclasses.replace(plate, colonnes={nom: _masquer_valeur(v, secrets)
                                                for nom, v in plate.colonnes.items()})


def _chaine(valeur: Any) -> str:
    return valeur if isinstance(valeur, str) else ''


def aplatir_page(page: Dict[str, Any], secrets: Iterable[str] = ()) -> PagePlate:
    """Page Notion -> PagePlate (types conservés seulement, jetons masqués). Les colonnes de données
    personnelles (personnes, e-mail, téléphone, fichiers) ne sont jamais conservées."""
    props = page.get('properties') if isinstance(page.get('properties'), dict) else {}
    secrets = tuple(secrets)
    colonnes: Dict[str, ValeurPlate] = {}
    for nom, prop in props.items():
        if not isinstance(nom, str):
            continue
        kind = prop.get('type') if isinstance(prop, dict) else None
        if not isinstance(kind, str):
            colonnes[nom] = ValeurPlate('', illisible=True)
            continue
        valeur = texte_propriete(prop)
        if valeur is not None:
            colonnes[nom] = _masquer_valeur(valeur, secrets)
    return PagePlate(page_id=normaliser_id(page.get('id')), url_notion=_chaine(page.get('url')),
                     cree_le=_chaine(page.get('created_time')), modifie_le=_chaine(page.get('last_edited_time')),
                     colonnes=colonnes)


_CHAMPS_VALEUR = {'type': (str,), 'texte': (str,), 'valeurs': (list, tuple), 'nombre': (int, float, type(None)),
                  'segments': (int,), 'mise_en_forme': (bool,), 'mentions': (int,), 'illisible': (bool,)}


def plate_depuis_dict(donnees: Any) -> PagePlate:
    """PagePlate relue d'une capture ; ValueError si la forme est inattendue."""
    if not isinstance(donnees, dict) or not isinstance(donnees.get('colonnes'), dict):
        raise ValueError('page')
    for cle in ('page_id', 'url_notion', 'cree_le', 'modifie_le'):
        if not isinstance(donnees.get(cle), str):
            raise ValueError(cle)
    colonnes: Dict[str, ValeurPlate] = {}
    for nom, brute in donnees['colonnes'].items():
        if not isinstance(brute, dict) or not isinstance(brute.get('type'), str) or set(brute) - set(_CHAMPS_VALEUR):
            raise ValueError(nom)
        for cle, sortes in _CHAMPS_VALEUR.items():
            if cle in brute and (not isinstance(brute[cle], sortes)
                                 or (bool not in sortes and isinstance(brute[cle], bool))):
                raise ValueError(f'{nom}.{cle}')
        valeurs = tuple(brute.get('valeurs', ()))
        if not all(isinstance(v, str) for v in valeurs):
            raise ValueError(f'{nom}.valeurs')
        nombre = brute.get('nombre')
        colonnes[nom] = ValeurPlate(**dict(brute, valeurs=valeurs,
                                           nombre=None if nombre is None else _nombre(nombre)))
    return PagePlate(donnees['page_id'], donnees['url_notion'], donnees['cree_le'], donnees['modifie_le'],
                     colonnes)

# =============================================================================
# COLONNES DU SCHÉMA
# =============================================================================
_TEXTES = ('rich_text', 'title', 'formula')
# colonne canonique -> types acceptés (premier = attendu)
CANONIQUES: Dict[str, Tuple[str, ...]] = {
    'URL':          ('url', 'rich_text', 'title'),
    'Description':  _TEXTES,
    "Cas d'usage":  _TEXTES,
    'Installation': _TEXTES,
    'Exemple':      _TEXTES,
    'Prérequis':    _TEXTES,
    'Justification': _TEXTES,
    'Statut':       ('select', 'status', 'rich_text'),
    'Langage':      ('select', 'multi_select', 'rich_text'),
    'Type':         ('multi_select', 'select', 'rich_text'),
    'Catégorie':    ('select', 'rich_text', 'multi_select'),
    'Brique pour':  ('multi_select', 'rich_text', 'select'),
    'Licence':      ('rich_text', 'select'),
    'Stars':        ('number', 'formula'),
    'Pertinence':   ('number', 'formula'),
    'Dernière MAJ': ('date', 'rich_text'),
    'Analysé le':   ('date', 'rich_text'),
}
_AVEC_PERTE = {('Catégorie', 'multi_select')}           # lu, mais seul le premier élément compte
_LISTES = ('Type', 'Brique pour')
_NOMBRES = ('Stars', 'Pertinence')
_DATES = ('Dernière MAJ', 'Analysé le')
TYPES_PERSONNELS = ('rich_text', 'select', 'multi_select', 'status', 'url', 'formula')


@dataclass(frozen=True)
class Colonnes:
    schema: Dict[str, str]                       # {nom réel: type}
    titre: str                                   # nom de la colonne de type title
    reelles: Dict[str, str]                      # canonique -> nom réel
    absentes: Tuple[str, ...]                    # canoniques absentes (cas normal des anciennes bases)
    personnelles: Tuple[str, ...]                # colonnes personnelles indexées (colonne FTS notes)
    ignorees: Dict[str, str]                     # autres colonnes : {nom: type}
    anomalies: Tuple[Tuple[str, str, str], ...]  # anomalies du schéma (colonne, code, détail)


def resoudre_colonnes(schema: Dict[str, str]) -> Colonnes:
    titres = [nom for nom, t in schema.items() if t == 'title']
    titre = titres[0] if len(titres) == 1 else ''
    reelles: Dict[str, str] = {}
    absentes: List[str] = []
    anomalies: List[Tuple[str, str, str]] = []
    prises = {titre} if titre else set()
    for canonique, acceptes in CANONIQUES.items():
        nom, candidates = _resoudre_nom(canonique, schema)
        if nom:
            reelles[canonique] = nom
            prises.add(nom)
            sorte = schema[nom]
            if sorte not in acceptes:
                anomalies.append((nom, 'type_inattendu', f"type {sorte} inattendu pour {canonique} "
                                                         f"(attendu : {', '.join(acceptes)}) : colonne non lue"))
            elif (canonique, sorte) in _AVEC_PERTE:
                anomalies.append((nom, 'type_inattendu', f"{canonique} en {sorte} : seul le premier "
                                                         "élément est lu"))
        elif candidates:
            prises.update(candidates)
            anomalies.append((canonique, 'colonne_ambigue', f"plusieurs colonnes possibles "
                                                            f"({', '.join(candidates)}) : aucune n'est lue"))
        else:
            absentes.append(canonique)
    personnelles = tuple(nom for nom, t in schema.items() if nom not in prises and t in TYPES_PERSONNELS)
    ignorees = {nom: t for nom, t in schema.items() if nom not in prises and nom not in personnelles}
    return Colonnes(dict(schema), titre, reelles, tuple(absentes), personnelles, ignorees, tuple(anomalies))

# =============================================================================
# FICHES : LECTURE DES COLONNES, PROVENANCE, FIABILITÉ
# =============================================================================
@dataclass(frozen=True)
class Champ:
    texte: str                 # verbatim normalisé
    fiabilite: str             # niveau (NIVEAUX)
    motif: str                 # règle appliquée, en clair
    modifie: bool              # indice de modification manuelle


@dataclass(frozen=True)
class Provenance:
    famille: str               # v7.3 (v7.3 et v7.4) | v7.2-nv | v7.2 | v7.1 | ancienne | manuelle | indeterminee
    regle: str                 # R73, R74N, R72N, R72, R71, S1…S8
    methode: str               # 'LLM' | 'LEXICAL' | 'NON NOTÉ' | ''
    modele: str
    profil_version: str
    profil_empreinte: str
    composantes: str           # « U2·P3·T1·I2·C2·M2·L2 » ou ''
    note_justification: Optional[int]
    drapeaux: Tuple[str, ...]


@dataclass(frozen=True)
class Fiche:
    page_id: str
    url_notion: str
    cree_le: str
    modifie_le: str
    modifiee_apres_creation: bool
    cle_depot: str
    url_github: str
    nom: str
    provenance: Provenance
    champs: Dict[str, Champ]
    autres: Dict[str, str]     # colonnes personnelles textuelles
    statut: str
    licence: str
    categorie: str
    brique_pour: Tuple[str, ...]
    types: Tuple[str, ...]
    langage: str
    stars: Optional[float]
    pertinence: Optional[float]
    derniere_maj: str
    analyse_le: str
    anomalies: Tuple[Tuple[str, str, str], ...]   # (colonne, code, détail)


@dataclass
class _Lus:
    textes: Dict[str, str] = field(default_factory=dict)
    listes: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    nombres: Dict[str, Optional[float]] = field(default_factory=dict)
    valeurs: Dict[str, ValeurPlate] = field(default_factory=dict)
    autres: Dict[str, str] = field(default_factory=dict)
    anomalies: List[Tuple[str, str, str]] = field(default_factory=list)


_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def _extraire(canonique: str, reel: str, v: ValeurPlate, lus: _Lus) -> None:
    if canonique == 'URL':
        texte = v.texte
        if v.type != 'url':
            trouve = gn._URL_IN_TEXT_RE.search(texte)
            texte = trouve.group(0).rstrip(gn._TRAILING_PUNCT) if trouve else texte
        lus.textes[canonique] = texte.strip()
    elif canonique in _LISTES:
        if v.type == 'multi_select':
            valeurs = v.valeurs
        elif v.type == 'select':
            valeurs = (v.texte,) if v.texte else ()
        else:
            valeurs = tuple(p.strip() for p in v.texte.split(',') if p.strip())
        lus.listes[canonique] = valeurs
        lus.textes[canonique] = ', '.join(valeurs)
    elif canonique in _NOMBRES:
        lus.nombres[canonique] = v.nombre
        if v.nombre is None and v.texte:
            lus.anomalies.append((reel, 'type_inattendu', "formule non numérique : valeur ignorée"))
    elif canonique in _DATES:
        if v.type == 'date' or _DATE_RE.match(v.texte):
            lus.textes[canonique] = v.texte[:10]
        elif v.texte:
            lus.anomalies.append((reel, 'type_inattendu', "texte qui ne commence pas par une date "
                                                          "AAAA-MM-JJ : ignoré"))
    elif v.type == 'multi_select':          # Langage, Catégorie : premier élément
        lus.textes[canonique] = v.valeurs[0] if v.valeurs else ''
    else:
        lus.textes[canonique] = v.texte


def _lire(plate: PagePlate, cols: Colonnes) -> _Lus:
    lus = _Lus()
    titre = plate.colonnes.get(cols.titre) if cols.titre else None
    if titre is not None:
        lus.valeurs['Nom'] = titre
        lus.textes['Nom'] = titre.texte if titre.type == 'title' and not titre.illisible else ''
        if titre.illisible:
            lus.anomalies.append((cols.titre, 'valeur_illisible', "titre de forme imprévue : ignoré"))
    for canonique, reel in cols.reelles.items():
        v = plate.colonnes.get(reel)
        if v is None:
            continue
        lus.valeurs[canonique] = v
        if v.illisible:
            lus.anomalies.append((reel, 'valeur_illisible', f"valeur {v.type or 'sans type'} de forme "
                                                            "imprévue : ignorée"))
            continue
        acceptes = CANONIQUES[canonique]
        if v.type not in acceptes:
            if cols.schema.get(reel) in acceptes:   # sinon déjà signalée une fois pour le schéma
                lus.anomalies.append((reel, 'type_inattendu', f"valeur de type {v.type} : ignorée"))
            continue
        _extraire(canonique, reel, v, lus)
    for reel in cols.personnelles:
        v = plate.colonnes.get(reel)
        if v is None:
            continue
        if v.illisible:
            lus.anomalies.append((reel, 'valeur_illisible', f"valeur {v.type or 'sans type'} de forme "
                                                            "imprévue : ignorée"))
            continue
        texte = ', '.join(v.valeurs) if v.type == 'multi_select' else v.texte
        if texte:
            lus.autres[reel] = texte
    for nom, v in plate.colonnes.items():
        if v.mentions >= 25:
            lus.anomalies.append((nom, 'troncature_possible', "25 mentions ou plus : Notion n'en renvoie "
                                                              "que 25, texte peut-être incomplet"))
        if MASQUE in v.texte or any(MASQUE in x for x in v.valeurs):
            lus.anomalies.append((nom, 'jeton_masque', "texte ressemblant à un jeton : masqué"))
    return lus


# --- Provenance (première règle applicable) -------------------------------------------------------
R73 = re.compile(r'^\[(?:LLM (?P<modele>.+?)|LEXICAL) · profil (?P<pver>[^\]\n]+)/(?P<empreinte>[0-9a-f]{6})\]'
                 r'(?=\s|$)')
R72 = re.compile(r'^\[(?:LLM (?P<modele>.+?)|LEXICAL) · profil (?P<empreinte>[0-9a-f]{6})\](?=\s|$)')
R71 = re.compile(r'^\[(?P<methode>LLM|LEXICAL)\](?=\s|$)')
R74N = re.compile(r'^\[NON NOTÉ\](?=\s|$)')
# Composantes v7.3, et plafond v7.4 « = 10, plafonnée à 8 (aucune brique du profil) »
RCOMP = re.compile(r'^ U([0-3?])·P([0-3?])·T([0-2?])·I([0-2?])·C([0-2?])·M([0-2?])·L([0-2?]) = (10|\d)'
                   r'(?:, plafonnée à (10|\d) \(aucune brique du profil\))? —(?: |$)')
# Repli lexical v7.4 plafonné : « Note 10, plafonnée à 8 (aucune brique du profil). »
RLEX = re.compile(r'^ Note (10|\d), plafonnée à (10|\d) \(aucune brique du profil\)\.(?=\s|$)')
GEN_PREREQ = re.compile(r'^(?:See docs|[^\s\d•*+\-][^\n\d]{0,39} recent)$')
FAB_EXEMPLE = re.compile(r'^(?:pip|npm) install \S+$')
_GABARITS_FR = tuple(re.compile(motif) for motif in lexique.GABARITS_CAS_USAGE_FR)

LIBELLES_FAMILLE = {
    'v7.3': 'fiche v7.3+', 'v7.2-nv': 'fiche v7.2', 'v7.2': 'fiche v7.2', 'v7.1': 'fiche v7.0/v7.1',
    'ancienne': 'fiche ancienne', 'manuelle': 'fiche saisie à la main',
    'indeterminee': 'fiche de version non reconnue',
}
NOMS_FAMILLE = {'v7.3': 'v7.3+', 'v7.2-nv': 'v7.2', 'v7.2': 'v7.2', 'v7.1': 'v7.0/v7.1', 'ancienne': 'ancienne',
                'manuelle': 'manuelle', 'indeterminee': 'indéterminée'}
RANG_FAMILLE = {'v7.3': 6, 'v7.2-nv': 5, 'v7.2': 4, 'v7.1': 3, 'ancienne': 2, 'indeterminee': 1, 'manuelle': 0}
LIMITE_NON_NOTEE = ("Fiche non notée : le dépôt n'avait ni description, ni topics, ni README exploitable")


def est_gabarit_cas_usage(texte: str) -> bool:
    """Cas d'usage recopiés de la liste générique des versions 7.2 et antérieures (anglais ou traduits)."""
    lignes = [gn._fold(ligne).lstrip('•*-– ').strip(' .;') for ligne in texte.split('\n') if ligne.strip()]
    touches = sum(1 for ligne in lignes
                  if ligne in lexique.GABARITS_CAS_USAGE_EN or any(m.match(ligne) for m in _GABARITS_FR))
    return bool(lignes) and (touches >= 2 or touches == len(lignes))


def _note_differente(note: Optional[int], pertinence: Optional[float]) -> bool:
    return note is not None and pertinence is not None and float(note) != pertinence


def _detecter(lus: _Lus) -> Provenance:
    t = lus.textes.get
    j, p, i, e, c = (t(n, '') for n in ('Justification', 'Prérequis', 'Installation', 'Exemple', "Cas d'usage"))
    nv = gn.NON_VERIFIE
    pertinence = lus.nombres.get('Pertinence')
    drapeaux: List[str] = []

    m = R73.match(j)
    if m:
        methode = 'LLM' if m.group('modele') is not None else 'LEXICAL'
        reste = j[m.end():]
        note: Optional[int] = None
        composantes = ''
        if methode == 'LLM':
            mc = RCOMP.match(reste)
            if mc:
                composantes = '·'.join(f'{lettre}{val}' for lettre, val in zip('UPTICML', mc.groups()[:7], strict=True))
                note = int(mc.group(9) or mc.group(8))
                if mc.group(9):
                    drapeaux.append(f'note-plafonnee:{mc.group(8)}')
            else:
                drapeaux.append('composantes-absentes')
        else:
            ml = RLEX.match(reste)
            if ml:
                note = int(ml.group(2))
                drapeaux.append(f'note-plafonnee:{ml.group(1)}')
        if _note_differente(note, pertinence):
            drapeaux.append('pertinence-modifiee')
        return Provenance('v7.3', 'R73', methode, m.group('modele') or '', m.group('pver'), m.group('empreinte'),
                          composantes, note, tuple(drapeaux))
    if R74N.match(j):
        if pertinence is not None:          # « Pertinence laissée vide » par Gitnotate
            drapeaux.append('pertinence-modifiee')
        drapeaux.append('non-notee')
        return Provenance('v7.3', 'R74N', 'NON NOTÉ', '', '', '', '', None, tuple(drapeaux))
    m = R72.match(j)
    if m:
        methode = 'LLM' if m.group('modele') is not None else 'LEXICAL'
        if p == nv:
            return Provenance('v7.2-nv', 'R72N', methode, m.group('modele') or '', '', m.group('empreinte'),
                              '', None, ())
        if not GEN_PREREQ.match(p):
            drapeaux.append('prerequis-modifie')
        return Provenance('v7.2', 'R72', methode, m.group('modele') or '', '', m.group('empreinte'), '', None,
                          tuple(drapeaux))
    m = R71.match(j)
    if m:
        return Provenance('v7.1', 'R71', m.group('methode'), '', '', '', '', None, ())
    if j:
        drapeaux.append('justification-non-reconnue')

    def sans_justification(famille: str, regle: str, *extra: str) -> Provenance:
        return Provenance(famille, regle, '', '', '', '', '', None, tuple(drapeaux) + extra)

    gabarit = est_gabarit_cas_usage(c)
    if GEN_PREREQ.match(p):
        return sans_justification('ancienne', 'S1')
    if gabarit and nv in (p, i, e):
        return sans_justification('v7.2-nv', 'S2')
    if (gn._fold(i) == 'see documentation' or gn._fold(e) == 'see docs'
            or 'Outils' in lus.listes.get('Type', ()) or gabarit):
        return sans_justification('ancienne', 'S3', 'prerequis-modifie')
    if any(t(n, '') for n in ('Licence', 'Catégorie', 'Brique pour')):
        return sans_justification('v7.3', 'S4')
    if p == nv:
        if c == nv:
            return sans_justification('v7.3', 'S5')
        return sans_justification('v7.2-nv', 'S5', 'ambigu-v7.2-nv-ou-v7.3')
    if p:
        return sans_justification('v7.3', 'S6')
    if not (c or i or e) and not t('Analysé le', ''):
        return sans_justification('manuelle', 'S7')
    return sans_justification('indeterminee', 'S8')


def detecter_provenance(plate: PagePlate, cols: Colonnes) -> Provenance:
    """Famille et provenance d'une fiche, d'après le contenu seulement (jamais d'après la date)."""
    return _detecter(_lire(plate, cols))


def libelle_fiche(prov: Provenance, analyse_le: str = '', complet: bool = False) -> str:
    """Libellé court (« fiche v7.3+ ») ou complet (modèle, profil, date d'analyse) : cp1252, sans indice."""
    libelle = LIBELLES_FAMILLE.get(prov.famille, prov.famille)
    if not complet:
        return libelle
    parties = [libelle]
    if prov.methode == 'LLM' and prov.famille == 'v7.1':
        parties.append('avis LLM (modèle non noté)')
    elif prov.methode == 'LLM':
        parties.append(f"LLM {prov.modele}")
    elif prov.methode == 'LEXICAL':
        parties.append('repli lexical (sans LLM)')
    elif prov.methode == 'NON NOTÉ':
        parties.append('non notée')
    elif prov.famille == 'ancienne':
        parties[0] = 'fiche ancienne (v7.2 ou antérieure, sans Justification)'
    elif prov.famille in ('v7.3', 'v7.2-nv', 'v7.2'):
        parties.append('sans Justification')
    if prov.profil_empreinte:
        profil = f"{prov.profil_version}/{prov.profil_empreinte}" if prov.profil_version else prov.profil_empreinte
        parties.append(f"profil {profil}")
    if analyse_le:
        parties.append(f"analysée le {analyse_le}")
    return ' · '.join(parties)


# --- Fiabilité par champ ------------------------------------------------------------------------------
NIVEAUX_INDEXES = frozenset({'github', 'readme', 'readme_partiel', 'llm', 'avis_llm', 'utilisateur', 'inconnu'})
ETIQUETTES_NIVEAU = {
    'github': 'GitHub', 'readme': 'README, mot pour mot', 'readme_partiel': 'README, extrait ancien',
    'llm': 'LLM, à vérifier', 'avis_llm': 'avis du LLM, ne prouve rien', 'utilisateur': 'saisi par vous',
    'inconnu': 'origine inconnue', 'defaut': '', 'gabarit': "gabarit de l'ancienne version, ignoré",
    'non_verifie': 'non vérifié par Gitnotate', 'vide': '',
}
CHAMPS = ('Nom', 'URL', 'Description', "Cas d'usage", 'Installation', 'Exemple', 'Prérequis', 'Justification',
          'Catégorie', 'Brique pour', 'Licence', 'Type', 'Langage', 'Statut')
CHAMPS_PRODUITS = ('Nom', 'Description', "Cas d'usage", 'Installation', 'Exemple', 'Prérequis', 'Justification')
_NON_VERIFIES = frozenset({'non verifie', 'non verifiee', 'non renseignee'})
_DESCRIPTIONS_DEFAUT = frozenset({'github project', 'projet github', 'un projet github'})
_ANCIENNES = frozenset({'v7.1', 'v7.2', 'v7.2-nv', 'ancienne'})


def _corps_justification(j: str) -> Tuple[str, bool]:
    """Texte après le préfixe de Gitnotate (et après les composantes) ; (texte, préfixe reconnu)."""
    for motif in (R73, R72, R71, R74N):
        m = motif.match(j)
        if m:
            reste = j[m.end():]
            suite = RCOMP.match(reste) or RLEX.match(reste)
            if suite:
                reste = reste[suite.end():]
            return reste.strip(), True
    return j, False


def _semble_francais(texte: str) -> bool:
    """Indice français (mot-outil, élision ou lettre accentuée), avec les marqueurs de gitnotate."""
    return any(mot in gn._FRENCH_MARKERS or re.match(r"(?:d|l|qu|s|n|j)'", mot) or re.search(r'[à-ÿ]', mot)
               for mot in gn._WORD_RE.findall(texte.lower()))


def _modifie(v: Optional[ValeurPlate]) -> bool:
    return v is not None and (v.segments > 1 or v.mise_en_forme or v.mentions > 0)


def _fiabilite(lus: _Lus, prov: Provenance, url_github: bool) -> Tuple[Dict[str, Champ], List[str]]:
    fam, meth = prov.famille, prov.methode
    modele = prov.modele or 'inconnu'
    t = lus.textes.get
    drapeaux: List[str] = []
    champs: Dict[str, Champ] = {}

    def poser(champ: str, texte: str, regle) -> None:
        modifie = champ in CHAMPS_PRODUITS and _modifie(lus.valeurs.get(champ))
        if modifie:
            drapeaux.append(f'modifie-a-la-main:{champ}')
        if not texte:
            niveau, motif = 'vide', 'champ vide'
        elif fam == 'manuelle':
            niveau, motif = 'utilisateur', 'fiche saisie à la main'
        elif gn._fold(texte) in _NON_VERIFIES:
            niveau, motif = 'non_verifie', f"« {texte} » : information absente, jamais négative"
        else:
            niveau, motif = regle(texte, modifie)
        champs[champ] = Champ(texte, niveau, motif, modifie)

    def nom(texte, modifie):
        return 'github', 'nom du dépôt copié de GitHub'

    def url(texte, modifie):
        return ('github', 'adresse GitHub du dépôt') if url_github else ('utilisateur', 'adresse hors GitHub')

    def description(texte, modifie):
        if gn._fold(texte).strip(' .') in _DESCRIPTIONS_DEFAUT:
            return 'gabarit', "description par défaut quand GitHub n'en a pas"
        if fam == 'v7.3' and gn._description_is_template(texte):
            return 'gabarit', 'gabarit du prompt recopié par le LLM'
        if meth == 'NON NOTÉ':
            return 'inconnu', "texte différent de « Non vérifié » sur une fiche non notée"
        if meth == 'LEXICAL' and fam in ('v7.2', 'v7.2-nv', 'v7.3'):
            # Un repli lexical garde la description GitHub, sauf en traduction seule ou en réponse
            # partielle : un texte français peut alors venir du LLM
            if not _semble_francais(texte):
                return 'github', "description GitHub d'origine (repli lexical)"
            return 'inconnu', ("repli lexical : description GitHub d'origine ou traduite par un LLM, "
                               "impossible à distinguer")
        if fam == 'v7.3':
            return 'llm', f"rédigée par LLM {modele}"
        if fam in _ANCIENNES:
            if gn._looks_english(texte):
                drapeaux.append('description-anglaise')
                return 'github', "texte GitHub d'origine, traduction absente"
            return 'llm', 'traduction LLM de la description GitHub'
        return 'inconnu', 'origine inconnue'

    def cas_usage(texte, modifie):
        gabarit = est_gabarit_cas_usage(texte)
        if fam in _ANCIENNES:
            if modifie and not gabarit:
                return 'utilisateur', "cas d'usage réécrits dans Notion"
            return 'gabarit', "cas d'usage génériques des versions 7.2 et antérieures"
        if gabarit or gn._use_cases_are_template(texte):
            return 'gabarit', "cas d'usage recopiés d'un gabarit"
        lignes = [ligne.strip().lstrip('•*-– ') for ligne in texte.split('\n') if ligne.strip()]
        if lignes and all(gn._is_empty_use_case(ligne) for ligne in lignes):
            return 'non_verifie', "aucun cas d'usage établi"
        if fam == 'v7.3' and meth != 'NON NOTÉ':
            return 'llm', "cas d'usage rédigés par LLM, justifiés par le README"
        return 'inconnu', 'origine inconnue'

    def installation(texte, modifie):
        if gn._fold(texte) == 'see documentation':
            return 'gabarit', "valeur par défaut « See documentation »"
        if fam == 'v7.3':
            return 'readme', 'extrait mot pour mot du README, vérifié par Gitnotate'
        if fam in _ANCIENNES:
            return 'readme_partiel', "extrait ancien du README, peut être tronqué"
        return 'inconnu', 'origine inconnue'

    def exemple(texte, modifie):
        if gn._fold(texte) == 'see docs':
            return 'gabarit', "valeur par défaut « See docs »"
        if fam in ('v7.1', 'v7.2', 'ancienne', 'indeterminee') and FAB_EXEMPLE.match(texte):
            return 'gabarit', 'commande construite à partir du nom du dépôt'
        if fam in ('v7.3', 'v7.2-nv'):
            return 'readme', 'extrait mot pour mot du README, vérifié par Gitnotate'
        return 'inconnu', "valeur que cette version n'écrivait pas"

    def prerequis(texte, modifie):
        if gn._fold(texte) == 'see docs' or GEN_PREREQ.match(texte):
            return 'gabarit', "langage GitHub suivi de « recent » (ou « See docs »)"
        if fam == 'v7.3':
            return 'readme', 'extrait mot pour mot du README, vérifié par Gitnotate'
        return 'inconnu', 'origine inconnue'

    def classement(texte, modifie):           # Catégorie, Brique pour
        if fam == 'v7.3' and meth == 'LLM':
            profil = f"{prov.profil_version}/{prov.profil_empreinte}"
            return 'llm', f"jugement du LLM {modele}, profil {profil}"
        if fam == 'v7.3' and not meth:
            return 'llm', "jugement d'un LLM (fiche v7.3 sans Justification : modèle inconnu)"
        return 'utilisateur', "colonne remplie hors d'une analyse LLM v7.3"

    def licence(texte, modifie):
        if fam == 'v7.3':
            return 'github', 'identifiant SPDX lu sur GitHub'
        return 'utilisateur', "colonne remplie hors de la v7.3"

    def types(texte, modifie):
        if fam in ('v7.3', 'v7.2-nv'):
            return 'github', 'catégories déduites des topics GitHub exacts'
        if fam in ('v7.1', 'v7.2', 'ancienne'):
            return 'gabarit', "catégorie heuristique ou « Outils » par défaut"
        if lus.listes.get('Type') == ('Outils',):
            return 'gabarit', "« Outils » : valeur par défaut des anciennes versions"
        return 'inconnu', 'origine inconnue'

    def langage(texte, modifie):
        return 'github', 'langage principal indiqué par GitHub'

    def statut(texte, modifie):
        if gn._fold(texte) == 'a explorer':
            return 'defaut', 'valeur par défaut de Gitnotate'
        return 'utilisateur', 'statut posé dans Notion'

    poser('Nom', t('Nom', ''), nom)
    poser('URL', t('URL', ''), url)
    poser('Description', t('Description', ''), description)
    poser("Cas d'usage", t("Cas d'usage", ''), cas_usage)
    poser('Installation', t('Installation', ''), installation)
    poser('Exemple', t('Exemple', ''), exemple)
    poser('Prérequis', t('Prérequis', ''), prerequis)
    poser('Catégorie', t('Catégorie', ''), classement)
    poser('Brique pour', t('Brique pour', ''), classement)
    poser('Licence', t('Licence', ''), licence)
    poser('Type', t('Type', ''), types)
    poser('Langage', t('Langage', ''), langage)
    poser('Statut', t('Statut', ''), statut)

    # Justification : le corps seul (sans préfixe ni composantes) est un avis du LLM
    j = t('Justification', '')
    corps, reconnu = _corps_justification(j)
    modifie = _modifie(lus.valeurs.get('Justification'))
    if modifie:
        drapeaux.append('modifie-a-la-main:Justification')
    if not j:
        niveau, motif = 'vide', 'champ vide'
    elif fam == 'manuelle':
        niveau, motif = 'utilisateur', 'fiche saisie à la main'
    elif not reconnu:
        niveau, motif = 'utilisateur', 'Justification sans préfixe Gitnotate : texte saisi dans Notion'
    elif meth == 'LLM' and corps:
        niveau, motif = 'avis_llm', f"avis du LLM {modele if fam != 'v7.1' else '(modèle non noté)'}"
    elif meth == 'LEXICAL':
        niveau, motif = 'vide', 'repli lexical : aucun avis'
    elif meth == 'NON NOTÉ':
        niveau, motif = 'vide', 'fiche non notée : aucun avis'
    else:
        niveau, motif = 'vide', 'préfixe seul : aucun avis'
    champs['Justification'] = Champ(corps if reconnu else j, niveau, motif, modifie)
    return {nom_champ: champs[nom_champ] for nom_champ in CHAMPS}, drapeaux


def fiabilite_champs(plate: PagePlate, cols: Colonnes, prov: Provenance) -> Dict[str, Champ]:
    """Niveau de fiabilité de chaque champ (texte, niveau, motif, indice de modification manuelle)."""
    lus = _lire(plate, cols)
    return _fiabilite(lus, prov, bool(cle_depot(lus.textes.get('URL', ''), plate.page_id)[1]))[0]


def est_depot(cle: str) -> bool:
    """Clé 'owner/repo' (et non 'url:…' ni 'page:…')."""
    return not cle.startswith(('url:', 'page:'))


def cle_depot(url: str, page_id: str) -> Tuple[str, str, str]:
    """(clé de regroupement, 'Owner/Repo' tel qu'écrit, code d'anomalie ou '')."""
    brut = (url or '').strip()
    complete = brut
    if '://' not in brut and brut.lower().startswith(('github.com/', 'www.github.com/')):
        complete = 'https://' + brut
    info = gn.extract_github_info(complete)
    if info:
        return gn.normalize_github_url(brut), f"{info['owner']}/{info['repo']}", ''
    if brut:
        return 'url:' + gn._fold(brut).rstrip('/'), '', 'url_non_github'
    return 'page:' + page_id, '', 'url_absente'


def _secondes_entre(debut: str, fin: str) -> Optional[float]:
    try:
        return (datetime.fromisoformat(fin.replace('Z', '+00:00'))
                - datetime.fromisoformat(debut.replace('Z', '+00:00'))).total_seconds()
    except (ValueError, TypeError):
        return None


def construire_fiche(plate: PagePlate, cols: Colonnes) -> Fiche:
    lus = _lire(plate, cols)
    prov = _detecter(lus)
    url = lus.textes.get('URL', '')
    cle, owner_repo, code = cle_depot(url, plate.page_id)
    champs, drapeaux = _fiabilite(lus, prov, bool(owner_repo))
    prov = dataclasses.replace(prov, drapeaux=tuple(dict.fromkeys(prov.drapeaux + tuple(drapeaux))))
    anomalies = list(lus.anomalies)
    colonne_url = cols.reelles.get('URL', 'URL')
    if code == 'url_non_github':
        anomalies.append((colonne_url, code, "adresse hors GitHub : fiche indexée, sans dépôt"))
    elif code == 'url_absente':
        anomalies.append((colonne_url, code, "aucune adresse : fiche indexée, sans dépôt"))
    titre = lus.textes.get('Nom', '')
    if not titre:
        anomalies.append((cols.titre or 'Nom', 'titre_absent', "fiche sans titre"))
    ecart = _secondes_entre(plate.cree_le, plate.modifie_le)
    return Fiche(
        page_id=plate.page_id, url_notion=plate.url_notion, cree_le=plate.cree_le, modifie_le=plate.modifie_le,
        modifiee_apres_creation=ecart is not None and ecart > MODIF_APRES_CREATION_S,
        cle_depot=cle, url_github=url, nom=titre or owner_repo or '(sans titre)', provenance=prov,
        champs=champs, autres=dict(lus.autres), statut=lus.textes.get('Statut', ''),
        licence=lus.textes.get('Licence', ''), categorie=lus.textes.get('Catégorie', ''),
        brique_pour=lus.listes.get('Brique pour', ()), types=lus.listes.get('Type', ()),
        langage=lus.textes.get('Langage', ''), stars=lus.nombres.get('Stars'),
        pertinence=lus.nombres.get('Pertinence'), derniere_maj=lus.textes.get('Dernière MAJ', ''),
        analyse_le=lus.textes.get('Analysé le', ''), anomalies=tuple(anomalies))

# =============================================================================
# CONTENU INDEXÉ ET FICHE PRINCIPALE
# =============================================================================
COLONNES_FTS = ('nom', 'description', 'cas_usage', 'categorie', 'brique_pour', 'type', 'langage', 'licence',
                'installation', 'exemple', 'prerequis', 'notes', 'justification')
CHAMP_FTS = {'Description': 'description', "Cas d'usage": 'cas_usage', 'Catégorie': 'categorie',
             'Brique pour': 'brique_pour', 'Type': 'type', 'Langage': 'langage', 'Licence': 'licence',
             'Installation': 'installation', 'Exemple': 'exemple', 'Prérequis': 'prerequis',
             'Justification': 'justification'}
_CHAMEAU_RE = re.compile(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+')


def texte_nom_indexe(titre: str, cle: str) -> str:
    """Titre, son découpage CamelCase (« PaddleOCR » -> « Paddle OCR ») et owner/repo tirés de la clé."""
    morceaux = [titre] if titre else []
    parties = _CHAMEAU_RE.findall(titre)
    if len(parties) >= 2:
        morceaux.append(' '.join(parties))
    if est_depot(cle) and '/' in cle:
        morceaux.append(re.sub(r'[-_./]', ' ', cle))
    return ' '.join(morceaux)


def contenu_fts(fiche: Fiche) -> Dict[str, str]:
    """Texte de chaque colonne FTS : le texte stocké du champ (sauf nom et notes), champs indexables seuls."""
    contenu = {colonne: '' for colonne in COLONNES_FTS}
    contenu['nom'] = texte_nom_indexe(fiche.champs['Nom'].texte, fiche.cle_depot)
    for champ, colonne in CHAMP_FTS.items():
        ch = fiche.champs.get(champ)
        if ch is None or ch.fiabilite not in NIVEAUX_INDEXES:
            continue
        if champ == 'Justification' and ch.fiabilite != 'avis_llm':
            continue                        # Justification réécrite par l'utilisateur : colonne notes
        contenu[colonne] = ch.texte
    if gn._fold(contenu['langage']).startswith('autre'):
        contenu['langage'] = ''
    lignes = [f"{nom} : {valeur}" for nom, valeur in fiche.autres.items()]
    justification = fiche.champs.get('Justification')
    if justification is not None and justification.fiabilite == 'utilisateur':
        lignes.append(f"Justification : {justification.texte}")
    contenu['notes'] = '\n'.join(lignes)
    return contenu


def _tri_principal(elements: List[Any], valeurs) -> List[Any]:
    """Ordre de la fiche principale : famille la plus récente, puis date d'analyse et de création les plus
    récentes, puis page_id croissant. valeurs(e) -> (famille, analyse_le, cree_le, page_id)."""
    tri = sorted(elements, key=lambda e: valeurs(e)[3])
    tri.sort(key=lambda e: (RANG_FAMILLE.get(valeurs(e)[0], 0), valeurs(e)[1], valeurs(e)[2]), reverse=True)
    return tri


def fiches_principales(fiches: List[Fiche]) -> Set[str]:
    """page_id de la fiche principale de chaque dépôt (une fiche 'page:'/'url:' est seule dans son groupe)."""
    groupes: Dict[str, List[Fiche]] = {}
    for f in fiches:
        groupes.setdefault(f.cle_depot if est_depot(f.cle_depot) else 'seule:' + f.page_id, []).append(f)
    return {_tri_principal(g, lambda f: (f.provenance.famille, f.analyse_le, f.cree_le, f.page_id))[0].page_id
            for g in groupes.values()}

# =============================================================================
# INDEX SQLITE
# =============================================================================
DDL = f"""
PRAGMA user_version = {FORMAT_INDEX};

CREATE TABLE meta (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL) WITHOUT ROWID;

CREATE TABLE fiches (
  id                       INTEGER PRIMARY KEY,
  page_id                  TEXT NOT NULL UNIQUE,
  url_notion               TEXT NOT NULL,
  cree_le                  TEXT NOT NULL DEFAULT '',
  modifie_le               TEXT NOT NULL DEFAULT '',
  modifiee_apres_creation  INTEGER NOT NULL DEFAULT 0,
  cle_depot                TEXT NOT NULL,
  url_github               TEXT NOT NULL DEFAULT '',
  nom                      TEXT NOT NULL DEFAULT '',
  nom_plie                 TEXT NOT NULL DEFAULT '',
  famille                  TEXT NOT NULL,
  regle_famille            TEXT NOT NULL,
  methode                  TEXT NOT NULL DEFAULT '',
  modele                   TEXT NOT NULL DEFAULT '',
  profil_version           TEXT NOT NULL DEFAULT '',
  profil_empreinte         TEXT NOT NULL DEFAULT '',
  composantes              TEXT NOT NULL DEFAULT '',
  note_justification       INTEGER,
  statut                   TEXT NOT NULL DEFAULT '',
  langage                  TEXT NOT NULL DEFAULT '',
  licence                  TEXT NOT NULL DEFAULT '',
  categorie                TEXT NOT NULL DEFAULT '',
  brique_pour_json         TEXT NOT NULL DEFAULT '[]',
  type_json                TEXT NOT NULL DEFAULT '[]',
  stars                    REAL,
  pertinence               REAL,
  derniere_maj             TEXT NOT NULL DEFAULT '',
  analyse_le               TEXT NOT NULL DEFAULT '',
  champs_json              TEXT NOT NULL,
  autres_json              TEXT NOT NULL DEFAULT '{{}}',
  drapeaux_json            TEXT NOT NULL DEFAULT '[]',
  principale               INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX fiches_cle_depot ON fiches(cle_depot);
CREATE INDEX fiches_nom_plie ON fiches(nom_plie);

CREATE TABLE anomalies (
  id      INTEGER PRIMARY KEY,
  page_id TEXT NOT NULL,
  champ   TEXT NOT NULL,
  code    TEXT NOT NULL,
  detail  TEXT NOT NULL
);

CREATE VIRTUAL TABLE recherche USING fts5(
  {', '.join(COLONNES_FTS)},
  tokenize = '{TOKENIZER}'
);
"""

COLONNES_FICHES = ('id', 'page_id', 'url_notion', 'cree_le', 'modifie_le', 'modifiee_apres_creation', 'cle_depot',
                   'url_github', 'nom', 'nom_plie', 'famille', 'regle_famille', 'methode', 'modele',
                   'profil_version', 'profil_empreinte', 'composantes', 'note_justification', 'statut',
                   'langage', 'licence', 'categorie', 'brique_pour_json', 'type_json', 'stars', 'pertinence',
                   'derniere_maj', 'analyse_le', 'champs_json', 'autres_json', 'drapeaux_json', 'principale')
CLES_META = ('format_index', 'moteur_version', 'gitnotate_version', 'notion_version', 'sqlite_version',
             'database_id', 'base_titre', 'source', 'sync_debut_utc', 'sync_fin_utc', 'sync_fin_locale',
             'nb_requetes', 'nb_objets_recus', 'nb_fiches', 'nb_depots', 'nb_sans_depot', 'ignorees_json',
             'familles_json', 'colonnes_json', 'colonnes_lues_json', 'colonnes_absentes_json',
             'colonnes_personnelles_json', 'colonnes_ignorees_json', 'nb_anomalies', 'avertissements_json')
_MESSAGE_FTS5 = (
    "La redécouverte nécessite SQLite avec le module FTS5 (version 3.27 ou plus récente), absent de cette\n"
    "installation de Python (SQLite {version}).\n"
    "   Windows : installez Python 3.10 ou plus récent depuis python.org (FTS5 inclus).\n"
    "   Linux   : utilisez le python3 de votre distribution, puis vérifiez :\n"
    "     python3 -c \"import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using "
    "fts5(x)'); print('FTS5 OK')\"\n"
    "Aucune donnée n'a été lue ni modifiée. gitnotate.py et le nettoyeur ne sont pas concernés.")


def verifier_fts5() -> str:
    """'' si SQLite (3.27 ou plus) fournit FTS5 et fts5vocab ; sinon le message à afficher."""
    message = _MESSAGE_FTS5.format(version=sqlite3.sqlite_version)
    if sqlite3.sqlite_version_info < (3, 27, 0):
        return message
    con = sqlite3.connect(':memory:')
    try:
        con.execute(f"CREATE VIRTUAL TABLE t USING fts5(x, tokenize='{TOKENIZER}')")
        con.execute("CREATE VIRTUAL TABLE v USING fts5vocab(t, instance)")
    except sqlite3.Error:
        return message
    finally:
        con.close()
    return ''


def dossier_index() -> Path:
    return Path(gn.BASE_DIR) / DOSSIER_INDEX


def chemin_index() -> Path:
    return dossier_index() / NOM_INDEX


def prendre_verrou(dossier: Optional[Path] = None) -> int:
    """Verrou du système sur sync.lock (libéré aussi à la mort du processus). Arret code 2 s'il est pris."""
    dossier = dossier_index() if dossier is None else dossier
    fd = os.open(str(dossier / NOM_VERROU), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if os.name == 'nt':
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise Arret(gn.EXIT_INCOMPLETE, "Une autre synchronisation est en cours ; relancez quand elle sera "
                                        "terminée") from None
    return fd


def liberer_verrou(fd: int) -> None:
    try:
        if os.name == 'nt':
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        os.close(fd)


def ouvrir_index_lecture(chemin: Optional[Path] = None) -> sqlite3.Connection:
    """Connexion en lecture seule (URI mode=ro + query_only) : espaces et accents du chemin encodés."""
    chemin = chemin_index() if chemin is None else chemin
    con = sqlite3.connect(chemin.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        con.execute('PRAGMA query_only=1')
    except sqlite3.Error:
        con.close()
        raise
    return con


def lire_meta(con: sqlite3.Connection) -> Dict[str, str]:
    return {cle: valeur for cle, valeur in con.execute('SELECT cle, valeur FROM meta')}


def verifier_format(con: sqlite3.Connection) -> Dict[str, str]:
    """meta d'un index au bon format ; Arret code 1 sinon (jamais de migration : relancer sync)."""
    autre = Arret(gn.EXIT_CONFIG, "Index créé par une autre version du moteur : relancez "
                                  "python redecouverte.py sync")
    try:
        if con.execute('PRAGMA user_version').fetchone()[0] != FORMAT_INDEX:
            raise autre
        meta = lire_meta(con)
    except sqlite3.Error:
        raise autre from None
    if meta.get('format_index') != str(FORMAT_INDEX) or set(CLES_META) - set(meta):
        raise autre
    return meta


@dataclass
class MetaLecture:
    """Ce que la lecture (Notion ou capture) apporte à l'index."""
    database_id: str
    base_titre: str
    source: str                          # 'notion' | 'capture:<nom du fichier>'
    schema: Dict[str, str]
    nb_requetes: int
    nb_objets_recus: int
    ignorees: Dict[str, int]
    debut_utc: str


@dataclass
class Bilan:
    chemin: Path
    taille: int
    meta: Dict[str, str]
    nb_doublons: int = 0
    precedent: str = ''                  # date locale de la synchronisation précédente
    apparues: int = 0
    disparues: List[str] = field(default_factory=list)   # noms (NOMS_AFFICHES_MAX premiers)
    nb_disparues: int = 0
    source_jeton: str = ''


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _json(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False)


def _supprimer_tmp(dossier: Path) -> None:
    for nom in (NOM_INDEX + '.tmp', NOM_INDEX + '.tmp-journal'):
        try:
            (dossier / nom).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            gn.log(f"   Fichier temporaire non supprimé : {dossier / nom}", 'verbose')


def _index_precedent(cible: Path) -> Optional[Dict[str, Any]]:
    """Index actif (page_id -> nom, meta) pour le garde-fou ; {'illisible': motif} s'il est inutilisable."""
    if not cible.exists():
        return None
    try:
        with contextlib.closing(ouvrir_index_lecture(cible)) as con:
            if con.execute('PRAGMA user_version').fetchone()[0] != FORMAT_INDEX:
                return {'illisible': "index précédent d'un autre format"}
            meta = lire_meta(con)
            if meta.get('format_index') != str(FORMAT_INDEX):
                return {'illisible': "index précédent d'un autre format"}
            pages = {page_id: nom for page_id, nom in con.execute('SELECT page_id, nom FROM fiches ORDER BY id')}
    except sqlite3.Error:
        return {'illisible': 'index précédent illisible'}
    return {'meta': meta, 'pages': pages}


def _garde_fou(precedent: Optional[Dict[str, Any]], fiches: List[Fiche], database_id: str,
               accepter_baisse: bool, bilan: Bilan, avertissements: List[str]) -> None:
    """Refuse (code 2) une baisse brutale ou une autre base sans --accepter-baisse."""
    if precedent is None:
        return
    if 'illisible' in precedent:
        avertissements.append(f"{precedent['illisible']} : remplacé sans comparaison")
        return
    anciens: Dict[str, str] = precedent['pages']
    nouveaux = {f.page_id for f in fiches}
    disparues = [page_id for page_id in anciens if page_id not in nouveaux]
    bilan.precedent = precedent['meta'].get('sync_fin_locale', '')
    bilan.apparues = len(nouveaux - set(anciens))
    bilan.nb_disparues = len(disparues)
    bilan.disparues = [anciens[p] or p for p in disparues[:NOMS_AFFICHES_MAX]]
    ancienne_base = precedent['meta'].get('database_id', '')
    conseil = "Si c'est voulu : python redecouverte.py sync --accepter-baisse"
    if ancienne_base and ancienne_base != database_id and not accepter_baisse:
        raise Arret(gn.EXIT_INCOMPLETE, f"L'index précédent venait d'une autre base ({ancienne_base[:8]}…) : "
                                        f"l'ancien index est conservé. {conseil}")
    baisse = ((len(disparues) >= BAISSE_MIN_FICHES and len(disparues) >= BAISSE_MIN_PART * len(anciens))
              or (bool(anciens) and not nouveaux))
    if baisse and not accepter_baisse:
        n = len(disparues)
        noms = ', '.join(bilan.disparues) + (' …' if n > NOMS_AFFICHES_MAX else '')
        sujet = "1 fiche de l'index précédent est absente" if n == 1 else \
            f"{n} fiches de l'index précédent sont absentes"
        raise Arret(gn.EXIT_INCOMPLETE, f"{sujet} de la lecture (DATABASE_ID changé ? partage de "
                                        "l'intégration retiré ? fiches supprimées ?). L'ancien index est "
                                        f"conservé. {conseil}\n   Absentes : {noms}")
    if baisse:
        avertissements.append(f"baisse acceptée (--accepter-baisse) : {len(disparues)} fiches disparues")
    if ancienne_base and ancienne_base != database_id:
        avertissements.append(f"autre base acceptée (--accepter-baisse) : l'index venait de {ancienne_base[:8]}…")


def _meta_index(meta: MetaLecture, fiches: List[Fiche], cols: Colonnes, nb_anomalies: int,
                avertissements: List[str]) -> Dict[str, str]:
    familles: Dict[str, int] = {}
    for famille in RANG_FAMILLE:
        n = sum(1 for f in fiches if f.provenance.famille == famille)
        if n:
            familles[famille] = n
    lues = dict({'Nom': cols.titre} if cols.titre else {}, **cols.reelles)
    return {
        'format_index': str(FORMAT_INDEX), 'moteur_version': __version__, 'gitnotate_version': gn.__version__,
        'notion_version': NOTION_VERSION, 'sqlite_version': sqlite3.sqlite_version,
        'database_id': meta.database_id, 'base_titre': meta.base_titre, 'source': meta.source,
        'sync_debut_utc': meta.debut_utc, 'sync_fin_utc': _utc_iso(),
        'sync_fin_locale': time.strftime('%Y-%m-%d %H:%M:%S'),
        'nb_requetes': str(meta.nb_requetes), 'nb_objets_recus': str(meta.nb_objets_recus),
        'nb_fiches': str(len(fiches)),
        'nb_depots': str(len({f.cle_depot for f in fiches if est_depot(f.cle_depot)})),
        'nb_sans_depot': str(sum(1 for f in fiches if not est_depot(f.cle_depot))),
        'ignorees_json': _json(meta.ignorees), 'familles_json': _json(familles),
        'colonnes_json': _json(cols.schema), 'colonnes_lues_json': _json(lues),
        'colonnes_absentes_json': _json(list(cols.absentes)),
        'colonnes_personnelles_json': _json(list(cols.personnelles)),
        'colonnes_ignorees_json': _json(cols.ignorees), 'nb_anomalies': str(nb_anomalies),
        'avertissements_json': _json(avertissements),
    }


def _ligne_fiche(rowid: int, f: Fiche, principale: bool) -> Tuple[Any, ...]:
    p = f.provenance
    champs = {nom: dataclasses.asdict(ch) for nom, ch in f.champs.items()}
    return (rowid, f.page_id, f.url_notion, f.cree_le, f.modifie_le, int(f.modifiee_apres_creation), f.cle_depot,
            f.url_github, f.nom, gn._fold(f.nom), p.famille, p.regle, p.methode, p.modele,
            p.profil_version, p.profil_empreinte, p.composantes, p.note_justification, f.statut, f.langage,
            f.licence, f.categorie, _json(list(f.brique_pour)), _json(list(f.types)), f.stars, f.pertinence,
            f.derniere_maj, f.analyse_le, _json(champs), _json(f.autres), _json(list(p.drapeaux)),
            int(principale))


def _inserer_fiche(con: sqlite3.Connection, rowid: int, fiche: Fiche, principale: bool) -> None:
    con.execute(f"INSERT INTO fiches ({', '.join(COLONNES_FICHES)}) "
                f"VALUES ({', '.join('?' * len(COLONNES_FICHES))})", _ligne_fiche(rowid, fiche, principale))
    contenu = contenu_fts(fiche)
    con.execute(f"INSERT INTO recherche (rowid, {', '.join(COLONNES_FTS)}) "
                f"VALUES (?, {', '.join('?' * len(COLONNES_FTS))})",
                (rowid, *(contenu[c] for c in COLONNES_FTS)))


def _integrite(con: sqlite3.Connection) -> str:
    return con.execute('PRAGMA integrity_check').fetchone()[0]


def _controler(con: sqlite3.Connection, attendu: int, temoin: Optional[Tuple[int, str]]) -> None:
    """Contrôles du .tmp avant remplacement ; Arret code 2 au premier échec."""
    def refus(motif: str) -> Arret:
        return Arret(gn.EXIT_INCOMPLETE, f"Index en construction refusé ({motif}) : l'index précédent "
                                         "est conservé")
    try:
        if _integrite(con) != 'ok':
            raise refus("contrôle d'intégrité SQLite")
        con.execute("INSERT INTO recherche(recherche) VALUES('integrity-check')")
        nb_fiches = con.execute('SELECT count(*) FROM fiches').fetchone()[0]
        nb_recherche = con.execute('SELECT count(*) FROM recherche').fetchone()[0]
        if not nb_fiches == nb_recherche == attendu:
            raise refus(f"{nb_fiches} fiches, {nb_recherche} entrées de recherche, {attendu} attendues")
        if con.execute('PRAGMA user_version').fetchone()[0] != FORMAT_INDEX:
            raise refus("version du format")
        if set(CLES_META) - set(lire_meta(con)):
            raise refus("informations de synchronisation incomplètes")
        if temoin is not None:
            rowid, titre = temoin
            expression = 'nom : "' + titre.replace('"', '""') + '"'
            trouves = {r for (r,) in con.execute('SELECT rowid FROM recherche WHERE recherche MATCH ?',
                                                 (expression,))}
            if rowid not in trouves:
                raise refus("requête témoin sans résultat")
        con.commit()
    except sqlite3.Error as e:
        raise refus(f"erreur SQLite {type(e).__name__}") from None


def _remplacer(tmp: Path, cible: Path) -> None:
    """os.replace avec réessais : sous Windows, un index ouvert (recherche, DB Browser, OneDrive,
    antivirus) refuse le remplacement quelques instants."""
    for essai in range(1, REMPLACEMENT_ESSAIS + 1):
        try:
            os.replace(tmp, cible)
            return
        except PermissionError:
            if essai == REMPLACEMENT_ESSAIS:
                raise Arret(gn.EXIT_INCOMPLETE, "L'index est ouvert par un autre programme ; fermez-le puis "
                            "relancez sync. L'ancien index est conservé et reste utilisable") from None
            time.sleep(REMPLACEMENT_PAUSE)


def _fsync_dossier(dossier: Path) -> None:
    if os.name == 'nt':
        return
    try:
        fd = os.open(str(dossier), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def construire_et_remplacer(plates: List[PagePlate], meta: MetaLecture, secrets: Iterable[str] = (),
                            accepter_baisse: bool = False) -> Bilan:
    """Seule écriture de l'index : fiches construites, garde-fou de baisse, .tmp en une transaction,
    contrôles, analyse des octets, os.replace. Le .tmp et son journal sont supprimés dans tous les cas."""
    dossier = dossier_index()
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / NOM_INDEX
    tmp = dossier / (NOM_INDEX + '.tmp')
    secrets = tuple(secrets)
    cols = resoudre_colonnes(meta.schema)
    fiches = [construire_fiche(p, cols) for p in plates]
    bilan = Bilan(cible, 0, {})
    avertissements: List[str] = []
    _garde_fou(_index_precedent(cible), fiches, meta.database_id, accepter_baisse, bilan, avertissements)
    principales = fiches_principales(fiches)
    anomalies = [('', *a) for a in cols.anomalies] + [(f.page_id, *a) for f in fiches for a in f.anomalies]
    meta_index = _meta_index(meta, fiches, cols, len(anomalies), avertissements)
    temoin = next(((i, f.champs['Nom'].texte) for i, f in enumerate(fiches, 1)
                   if any(ch.isalnum() for ch in f.champs['Nom'].texte)), None)
    con: Optional[sqlite3.Connection] = None
    try:
        _supprimer_tmp(dossier)
        con = sqlite3.connect(str(tmp))
        con.executescript(DDL)
        with con:                                           # une seule transaction
            for rowid, fiche in enumerate(fiches, 1):
                _inserer_fiche(con, rowid, fiche, fiche.page_id in principales)
            con.executemany('INSERT INTO anomalies (page_id, champ, code, detail) VALUES (?, ?, ?, ?)', anomalies)
            con.executemany('INSERT INTO meta (cle, valeur) VALUES (?, ?)', meta_index.items())
        con.execute("INSERT INTO recherche(recherche) VALUES('optimize')")
        con.commit()
        _controler(con, len(plates), temoin)
        con.close()
        con = None
        if contient_secret(tmp.read_bytes(), secrets):
            raise Arret(gn.EXIT_INCOMPLETE, "Un jeton a été détecté dans l'index en construction : écriture "
                                            "refusée (valeur non affichée). L'index précédent est conservé")
        _remplacer(tmp, cible)
        _fsync_dossier(dossier)
    except (sqlite3.Error, OSError) as e:             # disque plein, dossier protégé… (type seulement)
        raise Arret(gn.EXIT_INCOMPLETE, f"Construction de l'index impossible ({type(e).__name__}) : l'index "
                                        "précédent est conservé") from None
    finally:
        if con is not None:
            con.close()
        _supprimer_tmp(dossier)
    comptes: Dict[str, int] = {}
    for f in fiches:
        if est_depot(f.cle_depot):
            comptes[f.cle_depot] = comptes.get(f.cle_depot, 0) + 1
    bilan.nb_doublons = sum(1 for n in comptes.values() if n > 1)
    bilan.meta = meta_index
    bilan.taille = cible.stat().st_size
    return bilan

# =============================================================================
# CAPTURE ET REJEU
# =============================================================================
def chemin_sortie(valeur: str, nom_defaut: str) -> Path:
    """Un nom seul (ou rien) va dans BASE_DIR/exports/ ; un chemin est respecté."""
    exports = Path(gn.BASE_DIR) / DOSSIER_EXPORTS
    if not valeur:
        return exports / nom_defaut
    if '/' in valeur or '\\' in valeur:
        return Path(valeur).expanduser()
    return exports / valeur


def ecrire_capture(valeur: str, plates: List[PagePlate], meta: MetaLecture, secrets: Iterable[str]) -> Path:
    """Pages aplaties (sans jeton ni données personnelles) : rejouables par sync --depuis, sans réseau."""
    chemin = chemin_sortie(valeur, f"capture-notion-{time.strftime('%Y%m%d-%H%M%S')}.json")
    donnees = {'format': FORMAT_CAPTURE, 'moteur': __version__, 'gitnotate': gn.__version__,
               'notion_version': NOTION_VERSION, 'database_id': meta.database_id, 'base_titre': meta.base_titre,
               'lu_le': meta.debut_utc, 'schema': meta.schema, 'nb_requetes': meta.nb_requetes,
               'ignorees': meta.ignorees, 'pages': [dataclasses.asdict(p) for p in plates]}
    if contient_secret(json.dumps(donnees, ensure_ascii=False, indent=1).encode('utf-8'), tuple(secrets)):
        raise Arret(gn.EXIT_INCOMPLETE, "Un jeton a été détecté dans la capture : écriture refusée "
                                        "(valeur non affichée)")
    if chemin.parent == Path(gn.BASE_DIR) / DOSSIER_EXPORTS:
        chemin.parent.mkdir(parents=True, exist_ok=True)
    gn._atomic_write_json(chemin, donnees, indent=1)
    return chemin


def trouver_capture(valeur: str) -> Path:
    chemin = Path(valeur).expanduser()
    if chemin.is_file():
        return chemin
    if '/' not in valeur and '\\' not in valeur:
        dans_exports = Path(gn.BASE_DIR) / DOSSIER_EXPORTS / valeur
        if dans_exports.is_file():
            return dans_exports
    raise Arret(gn.EXIT_CONFIG, f"Capture introuvable : {valeur}")


def charger_capture(valeur: str, secrets: Iterable[str] = ()) -> Tuple[List[PagePlate], MetaLecture]:
    """Capture relue avec les mêmes contrôles (V10) ; Arret code 1 si elle est illisible ou d'un autre format."""
    chemin = trouver_capture(valeur)
    try:
        donnees = json.loads(chemin.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise Arret(gn.EXIT_CONFIG, f"Capture illisible (JSON invalide) : {chemin}") from None
    if not isinstance(donnees, dict) or donnees.get('format') != FORMAT_CAPTURE:
        raise Arret(gn.EXIT_CONFIG, f"Capture d'un autre format (attendu : {FORMAT_CAPTURE}) : {chemin}")
    schema, pages, ignorees = donnees.get('schema'), donnees.get('pages'), donnees.get('ignorees', {})
    database_id = donnees.get('database_id')
    if (not isinstance(schema, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in schema.items())
            or not isinstance(pages, list) or not isinstance(database_id, str)
            or not _ID_HEX_RE.fullmatch(database_id) or not isinstance(ignorees, dict)
            or not all(isinstance(v, int) for v in ignorees.values())):
        raise Arret(gn.EXIT_CONFIG, f"Capture illisible (contenu inattendu) : {chemin}")
    erreur = verifier_schema(schema)
    if erreur:
        raise Arret(gn.EXIT_CONFIG, erreur)
    try:
        plates = [_masquer_plate(plate_depuis_dict(p), secrets) for p in pages]
    except (ValueError, TypeError):
        raise Arret(gn.EXIT_CONFIG, f"Capture illisible (page mal formée) : {chemin}") from None
    if len(plates) != len(pages) or len({p.page_id for p in plates}) != len(plates):        # V10
        raise Arret(gn.EXIT_CONFIG, f"Capture illisible (pages manquantes ou en double) : {chemin}")
    nb_requetes = donnees.get('nb_requetes')
    meta = MetaLecture(database_id=database_id, base_titre=masquer(_chaine(donnees.get('base_titre')), secrets),
                       source=f"capture:{chemin.name}", schema=schema,
                       nb_requetes=nb_requetes if isinstance(nb_requetes, int) else 0,
                       nb_objets_recus=len(plates) + sum(ignorees.values()), ignorees=dict(ignorees),
                       debut_utc=_utc_iso())
    return plates, meta

# =============================================================================
# PRÉSENTATION : BILAN DE SYNCHRONISATION ET ÉTAT
# =============================================================================
def _n(nombre: int, singulier: str, pluriel: Optional[str] = None) -> str:
    return f"{nombre} {singulier if nombre <= 1 else (pluriel or singulier + 's')}"   # 0 et 1 : singulier


def _taille(octets: int) -> str:
    if octets < 1024 * 1024:
        return f"{max(1, round(octets / 1024))} Ko"
    return f"{octets / (1024 * 1024):.1f} Mo".replace('.', ',')


def _liste(noms: Iterable[str]) -> str:
    noms = list(noms)
    return ', '.join(noms) if noms else 'aucune'


def _charger(meta: Dict[str, str], cle: str, defaut: Any) -> Any:
    try:
        valeur = json.loads(meta.get(cle, ''))
    except ValueError:
        return defaut
    return valeur if isinstance(valeur, type(defaut)) else defaut


def texte_familles(familles: Dict[str, int]) -> str:
    """« v7.3+ ×13 · v7.2 ×5 · v7.0/v7.1 ×20 · ancienne ×18 · manuelle ×3 » (v7.2 et v7.2-nv réunies)."""
    comptes: Dict[str, int] = {}
    for famille in ('v7.3', 'v7.2-nv', 'v7.2', 'v7.1', 'ancienne', 'manuelle', 'indeterminee'):
        if familles.get(famille):
            nom = NOMS_FAMILLE[famille]
            comptes[nom] = comptes.get(nom, 0) + familles[famille]
    return ' · '.join(f"{nom} ×{n}" for nom, n in comptes.items()) or 'aucune fiche'


def _texte_ignorees(ignorees: Dict[str, int]) -> str:
    parties = []
    if ignorees.get('corbeille'):
        parties.append(f"{ignorees['corbeille']} à la corbeille ignorée{'s' if ignorees['corbeille'] > 1 else ''}")
    if ignorees.get('base_imbriquee'):
        parties.append(_n(ignorees['base_imbriquee'], 'base imbriquée ignorée', 'bases imbriquées ignorées'))
    return ', '.join(parties)


def _texte_colonnes(meta: Dict[str, str], absentes: bool) -> str:
    ignorees = _charger(meta, 'colonnes_ignorees_json', {})
    parties = []
    if absentes:
        parties.append(f"facultatives absentes : {_liste(_charger(meta, 'colonnes_absentes_json', []))}")
    parties.append(f"personnelles indexées : {_liste(_charger(meta, 'colonnes_personnelles_json', []))}")
    parties.append(f"ignorées : {_liste(f'{nom} ({sorte})' for nom, sorte in ignorees.items())}")
    return ' ; '.join(parties)


def _source_capture(meta: Dict[str, str]) -> str:
    source = meta.get('source', '')
    return source[len('capture:'):] if source.startswith('capture:') else ''


def texte_bilan_sync(bilan: Bilan) -> str:
    m = bilan.meta
    nb_fiches = int(m.get('nb_fiches', '0'))
    capture = _source_capture(m)
    lignes = ["Synchronisation de l'index de redécouverte"]
    base = f"« {m.get('base_titre', '')} » {m.get('database_id', '')[:8]}…"
    ignorees = _texte_ignorees(_charger(m, 'ignorees_json', {}))
    if capture:
        lignes.append(f"   Base Notion : {base} — capture {capture}, aucun appel réseau")
        lecture = f"{_n(nb_fiches, 'fiche')} relue{'s' if nb_fiches > 1 else ''} dans la capture"
    else:
        jeton = f" ({bilan.source_jeton})" if bilan.source_jeton else ''
        lignes.append(f"   Base Notion : {base} — Notion-Version {m.get('notion_version', '')}, lecture seule{jeton}")
        if bilan.source_jeton == 'NOTION_TOKEN':
            lignes.append("   Conseil     : un jeton d'intégration limité à « Read content » (NOTION_READONLY_TOKEN) "
                          "garantit côté Notion qu'aucune écriture n'est possible")
        lecture = (f"{_n(int(m.get('nb_requetes', '0')), 'requête')}, {_n(nb_fiches, 'fiche')}"
                   + (f" ({ignorees})" if ignorees else '')
                   + " — fiches hors corbeille et hors pages archivées")
    if not nb_fiches:
        lecture += " — base vide"
    lignes.append(f"   Lecture     : {lecture}")
    lignes.append(f"   Versions    : {texte_familles(_charger(m, 'familles_json', {}))}")
    lignes.append(f"   Dépôts      : {m.get('nb_depots', '0')} distincts ; "
                  f"{_n(bilan.nb_doublons, 'dépôt')} sur plusieurs fiches (etat --doublons) ; "
                  f"{_n(int(m.get('nb_sans_depot', '0')), 'fiche')} sans dépôt GitHub")
    lignes.append(f"   Colonnes    : {_texte_colonnes(m, absentes=False)}")
    nb_anomalies = int(m.get('nb_anomalies', '0'))
    lignes.append(f"   Anomalies   : {nb_anomalies} (etat --anomalies)" if nb_anomalies else "   Anomalies   : aucune")
    if bilan.precedent:
        lignes.append(f"   Différence  : +{_n(bilan.apparues, 'fiche')}, -{bilan.nb_disparues} depuis la "
                      f"synchronisation du {bilan.precedent[:16]}")
        if bilan.disparues:
            suite = ' …' if bilan.nb_disparues > len(bilan.disparues) else ''
            lignes.append(f"   Disparues   : {', '.join(bilan.disparues)}{suite}")
    for avertissement in _charger(m, 'avertissements_json', []):
        lignes.append(f"   Attention   : {avertissement}")
    lignes.append(f"   Index       : {bilan.chemin} ({_taille(bilan.taille)}) — recherche hors ligne possible")
    return '\n'.join(lignes)


def _age_jours(meta: Dict[str, str]) -> Optional[int]:
    try:
        fin = datetime.fromisoformat(meta.get('sync_fin_utc', ''))
    except ValueError:
        return None
    if fin.tzinfo is None:
        fin = fin.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - fin).total_seconds() // 86400))


def _il_y_a(jours: Optional[int]) -> str:
    if jours is None:
        return 'date inconnue'
    return "aujourd'hui" if jours == 0 else f"il y a {_n(jours, 'jour')}"


def alerte_runs_gitnotate(sync_fin_locale: str) -> str:
    """Fiches créées par gitnotate.py après la synchronisation (gitnotate_stats.json, lecture tolérante)."""
    try:
        with open(gn.STATS_FILE, 'r', encoding='utf-8') as f:
            historique = json.load(f)
    except (OSError, ValueError):
        return ''
    if not isinstance(historique, list) or not sync_fin_locale:
        return ''
    runs = [e for e in historique
            if isinstance(e, dict) and e.get('dry_run') is not True and isinstance(e.get('timestamp'), str)
            and isinstance(e.get('success_count'), int) and not isinstance(e.get('success_count'), bool)
            and e['success_count'] > 0 and e['timestamp'] > sync_fin_locale]
    if not runs:
        return ''
    total = sum(e['success_count'] for e in runs)
    dernier = max(e['timestamp'] for e in runs)[:16]
    if len(runs) == 1:
        return (f"gitnotate.py a créé {_n(total, 'fiche')} le {dernier}, après cette synchronisation : "
                "relancez python redecouverte.py sync")
    return (f"gitnotate.py a créé {_n(total, 'fiche')} en {len(runs)} runs après cette synchronisation "
            f"(dernier le {dernier}) : relancez python redecouverte.py sync")


def alertes_index(meta: Dict[str, str]) -> List[str]:
    alertes = []
    jours = _age_jours(meta)
    if jours is not None and jours > AGE_ALERTE_JOURS:
        alertes.append(f"Index synchronisé il y a {jours} jours : relancez sync pour inclure les fiches récentes")
    runs = alerte_runs_gitnotate(meta.get('sync_fin_locale', ''))
    if runs:
        alertes.append(runs)
    return alertes


def ouvrir_index_valide() -> Tuple[sqlite3.Connection, Dict[str, str]]:
    """Index en lecture seule et vérifié (commandes etat et cherche) ; Arret code 1 sinon."""
    message = verifier_fts5()
    if message:
        raise Arret(gn.EXIT_CONFIG, message)
    chemin = chemin_index()
    if not chemin.is_file():
        raise Arret(gn.EXIT_CONFIG, "Index absent : lancez d'abord python redecouverte.py sync")
    try:
        con = ouvrir_index_lecture(chemin)
    except sqlite3.Error:
        raise Arret(gn.EXIT_CONFIG, "Index illisible : relancez python redecouverte.py sync") from None
    try:
        return con, verifier_format(con)
    except BaseException:
        con.close()
        raise


def lire_fiches(con: sqlite3.Connection, condition: str = '1', parametres: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    """Fiches de l'index (dictionnaires ; champs, autres, drapeaux et listes décodés)."""
    curseur = con.execute(f"SELECT {', '.join(COLONNES_FICHES)} FROM fiches WHERE {condition} ORDER BY id",
                          parametres)
    fiches = []
    for ligne in curseur:
        f = dict(zip(COLONNES_FICHES, ligne, strict=True))
        for cle, cible in (('champs_json', 'champs'), ('autres_json', 'autres'), ('drapeaux_json', 'drapeaux'),
                           ('brique_pour_json', 'brique_pour'), ('type_json', 'types')):
            f[cible] = json.loads(f.pop(cle))
        fiches.append(f)
    return fiches


def ordonner_fiches(fiches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fiches d'un même dépôt dans l'ordre de la fiche principale (§ 14)."""
    return _tri_principal(fiches, lambda f: (f['famille'], f['analyse_le'], f['cree_le'], f['page_id']))


def statuts_du_depot(fiches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Statuts distincts d'un dépôt : ceux posés par l'utilisateur d'abord, chacun avec la fiche qui le
    porte (la première dans l'ordre principal) et le nombre de fiches."""
    statuts: Dict[str, Dict[str, Any]] = {}
    for f in ordonner_fiches(fiches):
        statut = f['statut']
        if not statut:
            continue
        if statut in statuts:
            statuts[statut]['fiches'] += 1
            continue
        niveau = (f['champs'].get('Statut') or {}).get('fiabilite')
        statuts[statut] = {'statut': statut, 'page_id': f['page_id'], 'analyse_le': f['analyse_le'],
                           'utilisateur': niveau == 'utilisateur', 'fiches': 1}
    return sorted(statuts.values(), key=lambda s: not s['utilisateur'])


def voir_aussi(con: sqlite3.Connection, cle: str) -> List[Dict[str, str]]:
    """Autres dépôts de même nom (titre replié, ou nom du dépôt dans l'adresse) : dépôt renommé,
    transféré ou homonyme ? Jamais fusionnés."""
    if not est_depot(cle):
        return []
    noms = {n for (n,) in con.execute("SELECT nom_plie FROM fiches WHERE cle_depot = ? AND nom_plie != ''",
                                      (cle,))}
    depot = cle.split('/', 1)[-1]
    autres: Dict[str, str] = {}
    for autre, nom, nom_plie in con.execute("SELECT cle_depot, nom, nom_plie FROM fiches WHERE cle_depot != ? "
                                            "ORDER BY principale DESC, id", (cle,)):
        if est_depot(autre) and (nom_plie in noms or autre.split('/', 1)[-1] == depot):
            autres.setdefault(autre, nom)
    return [{'depot': d, 'nom': n} for d, n in sorted(autres.items())]


def lister_doublons(con: sqlite3.Connection) -> List[Dict[str, Any]]:
    cles = [c for (c,) in con.execute('SELECT cle_depot FROM fiches GROUP BY cle_depot HAVING count(*) > 1 '
                                      'ORDER BY cle_depot') if est_depot(c)]
    doublons = []
    for cle in cles:
        fiches = ordonner_fiches(lire_fiches(con, 'cle_depot = ?', (cle,)))
        doublons.append({'depot': cle, 'fiches': [
            {'page_id': f['page_id'], 'nom': f['nom'], 'famille': f['famille'],
             'libelle': LIBELLES_FAMILLE.get(f['famille'], f['famille']), 'analyse_le': f['analyse_le'],
             'statut': f['statut'], 'url_notion': f['url_notion'], 'principale': bool(f['principale'])}
            for f in fiches]})
    return doublons


def lister_anomalies(con: sqlite3.Connection) -> List[Dict[str, str]]:
    lignes = con.execute('SELECT a.page_id, a.champ, a.code, a.detail, f.nom, f.url_notion FROM anomalies a '
                         'LEFT JOIN fiches f ON f.page_id = a.page_id ORDER BY a.code, a.id')
    return [{'page_id': p, 'colonne': c, 'code': code, 'detail': d, 'nom': n or '', 'url_notion': u or ''}
            for p, c, code, d, n, u in lignes]


def lire_etat(con: sqlite3.Connection, meta: Dict[str, str], anomalies: bool = False,
              doublons: bool = False) -> Dict[str, Any]:
    chemin = chemin_index()
    nb_multiples = con.execute("SELECT count(*) FROM (SELECT cle_depot FROM fiches WHERE cle_depot NOT LIKE "
                               "'page:%' AND cle_depot NOT LIKE 'url:%' GROUP BY cle_depot "
                               "HAVING count(*) > 1)").fetchone()[0]
    etat: Dict[str, Any] = {
        'fichier': str(chemin), 'taille_octets': chemin.stat().st_size,
        'synchronise_le': meta['sync_fin_utc'], 'synchronise_le_local': meta['sync_fin_locale'],
        'age_jours': _age_jours(meta), 'source': meta['source'], 'nb_requetes': int(meta['nb_requetes']),
        'base': {'titre': meta['base_titre'], 'database_id': meta['database_id'],
                 'notion_version': meta['notion_version']},
        'fiches': int(meta['nb_fiches']), 'depots': int(meta['nb_depots']), 'depots_multiples': nb_multiples,
        'sans_depot': int(meta['nb_sans_depot']), 'ignorees': _charger(meta, 'ignorees_json', {}),
        'familles': _charger(meta, 'familles_json', {}),
        'colonnes': {'absentes': _charger(meta, 'colonnes_absentes_json', []),
                     'personnelles': _charger(meta, 'colonnes_personnelles_json', []),
                     'ignorees': _charger(meta, 'colonnes_ignorees_json', {})},
        'nb_anomalies': int(meta['nb_anomalies']),
        'avertissements': _charger(meta, 'avertissements_json', []),
        'moteur': {'version': meta['moteur_version'], 'format_index': int(meta['format_index']),
                   'sqlite': sqlite3.sqlite_version, 'gitnotate': meta['gitnotate_version']},
        'alertes': alertes_index(meta),
    }
    if anomalies:
        etat['anomalies'] = lister_anomalies(con)
    if doublons:
        etat['doublons'] = lister_doublons(con)
    return etat


def texte_etat(etat: Dict[str, Any]) -> str:
    source = etat['source']
    if source.startswith('capture:'):
        provenance = f"capture {source[len('capture:'):]} (aucun appel réseau)"
    else:
        provenance = f"Notion, {_n(etat['nb_requetes'], 'requête')}"
    base = etat['base']
    ignorees = _texte_ignorees(etat['ignorees'])
    lignes = [
        "Index de redécouverte",
        f"   Fichier     : {etat['fichier']} ({_taille(etat['taille_octets'])})",
        f"   Synchronisé : {etat['synchronise_le_local'][:16]} ({_il_y_a(etat['age_jours'])}) — source : {provenance}",
        f"   Base Notion : « {base['titre']} » {base['database_id'][:8]}… — Notion-Version "
        f"{base['notion_version']}, lecture seule",
        f"   Fiches      : {etat['fiches']} ({_n(etat['depots'], 'dépôt')} ; {_n(etat['depots_multiples'], 'dépôt')} "
        f"sur plusieurs fiches ; {_n(etat['sans_depot'], 'fiche')} sans dépôt GitHub)"
        + (f" ; {ignorees}" if ignorees else ''),
        f"   Versions    : {texte_familles(etat['familles'])}",
        "   Colonnes    : " + _texte_colonnes({
            'colonnes_absentes_json': _json(etat['colonnes']['absentes']),
            'colonnes_personnelles_json': _json(etat['colonnes']['personnelles']),
            'colonnes_ignorees_json': _json(etat['colonnes']['ignorees'])}, absentes=True),
        f"   Anomalies   : {etat['nb_anomalies']} (etat --anomalies)" if etat['nb_anomalies']
        else "   Anomalies   : aucune",
        f"   Moteur      : redecouverte {etat['moteur']['version']} · format d'index {etat['moteur']['format_index']}"
        f" · SQLite {etat['moteur']['sqlite']} (FTS5 disponible)",
    ]
    lignes += [f"   Remarque    : {a} (dernière synchronisation)" for a in etat['avertissements']]
    lignes += [f"   Attention   : {a}" for a in etat['alertes']]
    if 'anomalies' in etat:
        lignes.append('')
        lignes.append(f"Anomalies ({len(etat['anomalies'])})")
        code = None
        for a in etat['anomalies']:
            if a['code'] != code:
                code = a['code']
                lignes.append(f"   {code}")
            fiche = f"{a['nom'] or a['page_id']} — {a['url_notion']}" if a['page_id'] else '(schéma de la base)'
            lignes.append(f"     - {fiche} · colonne {a['colonne']} : {a['detail']}")
        if not etat['anomalies']:
            lignes.append("   aucune")
    if 'doublons' in etat:
        lignes.append('')
        lignes.append(f"Dépôts sur plusieurs fiches ({len(etat['doublons'])}) — tri manuel dans Notion, le moteur "
                      "ne supprime rien")
        for d in etat['doublons']:
            lignes.append(f"   {d['depot']} ({_n(len(d['fiches']), 'fiche')})")
            for f in d['fiches']:
                principale = ' [principale]' if f['principale'] else ''
                date = f" du {f['analyse_le']}" if f['analyse_le'] else ''
                statut = f" · {f['statut']}" if f['statut'] else ''
                lignes.append(f"     - {f['nom']} · {f['libelle']}{date}{statut}{principale} — {f['url_notion']}")
        if not etat['doublons']:
            lignes.append("   aucun")
    return '\n'.join(lignes)

# =============================================================================
# LIGNE DE COMMANDE
# =============================================================================
_NIVEAUX_LOG = ('quiet', 'normal', 'verbose')


def construire_parseur() -> argparse.ArgumentParser:
    parseur = gn._Parser(
        prog='redecouverte',
        description="Retrouve, hors ligne, les dépôts déjà enregistrés dans la base Notion de Gitnotate "
                    "(Notion est seulement lu).",
        epilog="Codes de sortie : 0 succès (même sans résultat), 1 configuration, index absent ou FTS5 absent, "
               "2 lecture Notion incomplète ou refusée (index précédent conservé), 130 Ctrl-C.")
    parseur.add_argument('--version', action='version',
                         version=f"%(prog)s {__version__} (gitnotate {gn.__version__})")
    sous = parseur.add_subparsers(dest='commande', metavar='{sync,cherche,etat}', parser_class=gn._Parser)

    sync = sous.add_parser('sync', help="copie locale des fiches de la base Notion (lecture seule)",
                           description="Lit toute la base DATABASE_ID, valide, reconstruit et remplace l'index "
                                       "local. Toute erreur conserve l'index précédent.")
    sync.add_argument('--capture', nargs='?', const='', default=None, metavar='FICHIER',
                      help="après un remplacement réussi, écrit les fiches lues (sans jeton ni données "
                           "personnelles) ; nom seul ou rien : dossier exports/")
    sync.add_argument('--depuis', metavar='FICHIER',
                      help="reconstruit l'index depuis une capture, sans réseau ni jeton")
    sync.add_argument('--accepter-baisse', action='store_true',
                      help="accepte la disparition d'au moins 10 fiches et 10 %% de l'index, ou une autre base")
    sync.add_argument('--log-level', type=str.lower, choices=_NIVEAUX_LOG, help="verbosité")

    cherche = sous.add_parser('cherche', help="recherche hors ligne dans l'index (prochaine étape du moteur)")
    cherche.add_argument('besoin', nargs='?', default='', metavar='BESOIN')
    cherche.add_argument('-n', '--nombre', type=int, metavar='N')
    cherche.add_argument('--tout', action='store_true')
    cherche.add_argument('--details', action='store_true')
    for option in ('--statut', '--exclure-statut', '--licence', '--categorie', '--projet'):
        cherche.add_argument(option, action='append', default=[], metavar='VALEUR')
    cherche.add_argument('--format', choices=('texte', 'markdown', 'json'), default='texte')
    cherche.add_argument('--sortie', metavar='FICHIER')
    cherche.add_argument('--llm', action='store_true')
    cherche.add_argument('--llm-max', type=int, metavar='N')
    cherche.add_argument('--oui', action='store_true')
    cherche.add_argument('--llm-apercu', action='store_true')
    cherche.add_argument('--log-level', type=str.lower, choices=_NIVEAUX_LOG)

    etat = sous.add_parser('etat', help="état de l'index local",
                           description="Résume l'index local : fiches, versions, colonnes, anomalies.")
    etat.add_argument('--anomalies', action='store_true', help="liste détaillée des anomalies")
    etat.add_argument('--doublons', action='store_true', help="dépôts présents sur plusieurs fiches")
    etat.add_argument('--format', choices=('texte', 'json'), default='texte')
    return parseur


def _afficher_erreurs_config(cfg: Config) -> None:
    for erreur in cfg.erreurs:
        gn.log(f"Configuration : {erreur}", 'error')
    gn.log(f"   Fichier .env attendu : {gn.ENV_FILE} ({gn.DOTENV_STATUS})", 'error')


def cmd_sync(args: argparse.Namespace) -> int:
    if args.capture is not None and args.depuis:
        gn.log("Options incompatibles : --capture et --depuis ne peuvent pas être utilisées ensemble.", 'error')
        return gn.EXIT_CONFIG
    message = verifier_fts5()
    if message:
        gn.log(message, 'error')
        return gn.EXIT_CONFIG
    cfg = lire_config(notion=not args.depuis)
    if cfg.erreurs:
        _afficher_erreurs_config(cfg)
        return gn.EXIT_CONFIG
    if not args.depuis:
        erreur = erreur_version_notion()
        if erreur:
            gn.log(erreur, 'error')
            return gn.EXIT_CONFIG
    secrets = secrets_connus()
    plates: List[PagePlate] = []
    meta: Optional[MetaLecture] = None
    if args.depuis:
        plates, meta = charger_capture(args.depuis, secrets)
    gn._STOP_EVENT.clear()
    remplace = False
    dossier = dossier_index()
    dossier.mkdir(parents=True, exist_ok=True)
    verrou = prendre_verrou(dossier)
    try:
        _supprimer_tmp(dossier)                 # orphelins : le verrou garantit qu'aucun écrivain n'existe
        if not args.depuis:
            debut = _utc_iso()
            info = lire_schema(cfg)
            gn.log(f"Lecture de la base Notion « {info['titre']} » (lecture seule)…")
            lecture = lire_pages(cfg)
            plates = [aplatir_page(page, secrets) for page in lecture.pages]
            if len(plates) != len(lecture.pages):                                    # V10
                raise Arret(gn.EXIT_INCOMPLETE, "Extraction incomplète (bogue) : l'index précédent est conservé")
            meta = MetaLecture(database_id=cfg.database_id, base_titre=masquer(info['titre'], secrets),
                               source='notion', schema=info['schema'], nb_requetes=lecture.nb_requetes,
                               nb_objets_recus=lecture.nb_objets_recus, ignorees=lecture.ignorees,
                               debut_utc=debut)
        bilan = construire_et_remplacer(plates, meta, secrets, args.accepter_baisse)
        remplace = True
        bilan.source_jeton = '' if args.depuis else cfg.source_jeton
        gn.log(texte_bilan_sync(bilan))
        if args.capture is not None:
            try:
                chemin = ecrire_capture(args.capture, plates, meta, secrets)
            except OSError as e:
                gn.log(f"Index remplacé, mais capture non écrite ({type(e).__name__}).", 'error')
                return gn.EXIT_INCOMPLETE
            except Arret as e:
                gn.log(f"Index remplacé, mais capture non écrite : {e.message}", 'error')
                return gn.EXIT_INCOMPLETE
            gn.log(f"   Capture     : {chemin} (rejouable : python redecouverte.py sync --depuis FICHIER)")
        return gn.EXIT_OK
    except KeyboardInterrupt:
        gn._STOP_EVENT.set()
        gn.log("Interruption : index remplacé, capture non écrite." if remplace
               else "Interruption : l'index précédent est conservé.", 'error')
        return gn.EXIT_INTERRUPTED
    finally:
        liberer_verrou(verrou)


def cmd_cherche(args: argparse.Namespace) -> int:
    # Emplacement de la recherche (requête, lexique, classement, explications, sorties, avis LLM)
    gn.log("Commande cherche non disponible dans cette version du moteur : seules sync et etat sont prêtes.",
           'error')
    return gn.EXIT_CONFIG


def cmd_etat(args: argparse.Namespace) -> int:
    con, meta = ouvrir_index_valide()
    try:
        with contextlib.closing(con):
            etat = lire_etat(con, meta, anomalies=args.anomalies, doublons=args.doublons)
    except (sqlite3.Error, KeyError, ValueError):
        raise Arret(gn.EXIT_CONFIG, "Index illisible : relancez python redecouverte.py sync") from None
    if args.format == 'json':
        gn.log(json.dumps(etat, ensure_ascii=False, indent=2), 'always')
    else:
        gn.log(texte_etat(etat), 'always')
    return gn.EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    gn._configure_console()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and not arguments[0].startswith('-') and arguments[0] not in COMMANDES:
        gn.log(f"Commande inconnue « {arguments[0]} ». Pour chercher : python redecouverte.py cherche "
               f"\"{arguments[0]}\"", 'error')
        return gn.EXIT_CONFIG
    parseur = construire_parseur()
    try:
        args = parseur.parse_args(arguments)
    except SystemExit as e:                  # --help, --version (0) ou option invalide (1)
        return e.code if isinstance(e.code, int) else gn.EXIT_CONFIG
    if not args.commande:
        parseur.print_usage(sys.stderr)
        gn.log("Indiquez une commande : sync, cherche ou etat (python redecouverte.py --help).", 'error')
        return gn.EXIT_CONFIG
    if getattr(args, 'log_level', None):
        gn.LOG_LEVEL = args.log_level
    action = {'sync': cmd_sync, 'cherche': cmd_cherche, 'etat': cmd_etat}[args.commande]
    try:
        return action(args)
    except KeyboardInterrupt:
        gn._STOP_EVENT.set()
        gn.log("Interruption (Ctrl-C) : l'index précédent est conservé.", 'error')
        return gn.EXIT_INTERRUPTED
    except Arret as e:
        gn.log(e.message, 'error')
        return e.code
    except EcritureNotionInterdite:
        raise
    except Exception as e:                   # type seulement : un message pourrait recopier un jeton
        gn.log(f"Erreur inattendue ({type(e).__name__}) : l'index précédent est conservé.", 'error')
        return gn.EXIT_INCOMPLETE


if __name__ == '__main__':
    sys.exit(main())
