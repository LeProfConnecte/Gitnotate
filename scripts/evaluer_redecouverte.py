#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mesure hors ligne du moteur de redécouverte sur des requêtes de référence (outil de développement).

  python scripts/evaluer_redecouverte.py tests/fixtures/redecouverte/requetes.json [--details]

Ouvre l'index local en lecture seule (BASE_DIR/.gitnotate_index/redecouverte.sqlite, construit par
« python redecouverte.py sync »), lance chaque requête avec ses options et affiche nDCG@10, P@5, MRR,
intrus@3, intrus@5 et les attendus manquants, puis les moyennes par jeu. Seuls les dépôts visibles
(correspondances forte et partielle) sont classés, suivis des fiches sans dépôt GitHub. Les requêtes
avec filtres (options) sont mesurées à part, hors moyennes. Aucune écriture, aucun réseau.

Format du fichier : {"requetes": [{"id", "jeu", "requete", "options", "en_tete", "acceptables",
"a_exclure"}]} avec des clés de dépôt « owner/repo » (gain 2 en tête, 1 acceptable).

Codes de sortie : 0 mesures affichées · 1 fichier illisible (position de l'erreur JSON affichée), option
inconnue ou mal formée, ou index absent.
"""

import contextlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import gitnotate as gn  # noqa: E402
import redecouverte as rd  # noqa: E402

METRIQUES = ('ndcg10', 'p5', 'mrr', 'intrus3', 'intrus5')


def jugements(requete: Dict[str, Any]) -> Tuple[Dict[str, int], Set[str]]:
    """(gain par dépôt, intrus) : 2 en tête, 1 acceptable ; un attendu n'est jamais un intrus."""
    gain: Dict[str, int] = {}
    for cle in requete.get('acceptables', []):
        gain[cle] = max(gain.get(cle, 0), 1)
    for cle in requete.get('en_tete', []):
        gain[cle] = 2
    return gain, set(requete.get('a_exclure', [])) - set(gain)


def mesurer(classement: List[str], requete: Dict[str, Any], k: int = 10) -> Dict[str, Any]:
    """Mesures d'un classement (clés de dépôt dans l'ordre affiché) ; None si la mesure n'a pas de sens."""
    gain, intrus = jugements(requete)
    dcg = sum((2 ** gain.get(cle, 0) - 1) / math.log2(i + 2) for i, cle in enumerate(classement[:k]))
    ideal = sorted(gain.values(), reverse=True)[:k]
    idcg = sum((2 ** v - 1) / math.log2(i + 2) for i, v in enumerate(ideal))
    pertinents = [cle for cle, g in gain.items() if g >= 1]
    p5 = (sum(1 for cle in classement[:5] if gain.get(cle, 0) >= 1) / min(5, len(pertinents))) if pertinents else None
    tete = [cle for cle, g in gain.items() if g == 2]
    mrr = next((1 / (i + 1) for i, cle in enumerate(classement) if gain.get(cle) == 2), 0.0) if tete else None
    return {'ndcg10': dcg / idcg if idcg else None, 'p5': p5, 'mrr': mrr,
            'intrus3': sum(1 for cle in classement[:3] if cle in intrus),
            'intrus5': sum(1 for cle in classement[:5] if cle in intrus),
            'manquants': [cle for cle in tete if cle not in classement[:k]]}


def lancer(con, requete: Dict[str, Any]) -> 'rd.Reponse':
    """Recherche complète (limite maximale) avec les options de la requête."""
    analyse = rd.analyser_requete(requete.get('requete', ''))
    return rd.rechercher(con, analyse, requete.get('options') or {}, rd.RESULTATS_MAX, False)


def classement_de(reponse: 'rd.Reponse') -> List[str]:
    return [r.cle for r in reponse.resultats] + [r.cle for r in reponse.sans_depot]


def _format(valeur: Optional[float]) -> str:
    return '—' if valeur is None else f"{valeur:.2f}".replace('.', ',')


def evaluer(con, requetes: List[Dict[str, Any]], details: bool = False) -> Dict[str, Dict[str, float]]:
    """Affiche les mesures de chaque requête et renvoie les moyennes par jeu (requêtes sans filtre)."""
    sommes: Dict[str, Dict[str, List[float]]] = {}
    connues = {cle for (cle,) in con.execute('SELECT DISTINCT cle_depot FROM fiches')}
    for requete in requetes:
        inconnues = [cle for champ in ('en_tete', 'acceptables', 'a_exclure') for cle in requete.get(champ, [])
                     if cle not in connues]
        if inconnues:                        # faute de frappe, majuscules : la mesure serait faussée
            gn.log(f"Attention : {requete.get('id', '?')} cite des dépôts absents de l'index : "
                   f"{', '.join(inconnues)} (clés « propriétaire/dépôt » en minuscules)", 'error')
        reponse = lancer(con, requete)
        classement = classement_de(reponse)
        m = mesurer(classement, requete)
        filtres = bool(requete.get('options'))
        jeu = requete.get('jeu', 'reference') + (' (filtres, hors moyenne)' if filtres else '')
        forts = sum(1 for r in reponse.resultats if r.niveau == 'forte')
        manquants = f"  manquants : {', '.join(m['manquants'])}" if m['manquants'] else ''
        gn.log(f"{requete.get('id', '?'):<4} nDCG@10={_format(m['ndcg10'])}  P@5={_format(m['p5'])}  "
               f"MRR={_format(m['mrr'])}  intrus@3={m['intrus3']}  intrus@5={m['intrus5']}  forts={forts}{manquants}",
               'always')
        if details:
            for r in reponse.resultats[:8] + reponse.sans_depot:
                gn.log(f"       {r.rang or '-':>2} {r.cle:<45} {r.niveau:<9} {r.score:.3f}", 'always')
        if not filtres:
            for cle in METRIQUES:
                if m[cle] is not None:
                    sommes.setdefault(jeu, {}).setdefault(cle, []).append(m[cle])
    moyennes = {jeu: {cle: sum(v) / len(v) for cle, v in valeurs.items()} for jeu, valeurs in sommes.items()}
    for jeu, valeurs in moyennes.items():
        gn.log(f"--- {jeu} : " + '  '.join(f"{cle}={_format(v)}" for cle, v in valeurs.items()), 'always')
    return moyennes


def verifier_options(requetes: List[Dict[str, Any]]) -> List[str]:
    """Options de chaque requête : clés de rd.FILTRES, valeurs en liste de textes (un texte seul est mis dans
    une liste) ; renvoie les erreurs (une option mal écrite fausserait la mesure sans rien signaler)."""
    erreurs = []
    for requete in requetes:
        options = requete.get('options') or {}
        nom = requete.get('id', '?')
        if not isinstance(options, dict):
            erreurs.append(f"{nom} : « options » doit être un objet JSON")
            continue
        for cle, valeur in list(options.items()):
            if cle not in rd.FILTRES:
                erreurs.append(f"{nom} : option inconnue « {cle} » (possibles : {', '.join(rd.FILTRES)})")
            elif isinstance(valeur, str):
                options[cle] = [valeur]
            elif not isinstance(valeur, list) or not all(isinstance(v, str) for v in valeur):
                erreurs.append(f"{nom} : l'option « {cle} » attend un texte ou une liste de textes")
        requete['options'] = options
    return erreurs


def main(argv: Optional[List[str]] = None) -> int:
    gn._configure_console()
    parseur = gn._Parser(prog='evaluer_redecouverte', description="Mesure hors ligne de la redécouverte.")
    parseur.add_argument('fichier', help="fichier JSON des requêtes de référence")
    parseur.add_argument('--details', action='store_true', help="affiche les premiers dépôts de chaque requête")
    try:
        args = parseur.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else gn.EXIT_CONFIG
    try:
        # utf-8-sig : un fichier enregistré avec BOM (PowerShell 5.1, Bloc-notes) reste lisible
        donnees = json.loads(Path(args.fichier).read_text(encoding='utf-8-sig'))
        requetes = donnees['requetes']
        if not isinstance(requetes, list) or not all(isinstance(q, dict) for q in requetes):
            raise ValueError('requetes')
    except json.JSONDecodeError as e:
        gn.log(f"Fichier de requêtes illisible : {args.fichier} (JSON invalide ligne {e.lineno}, colonne "
               f"{e.colno} ; virgule en trop ou guillemet manquant ?)", 'error')
        return gn.EXIT_CONFIG
    except UnicodeDecodeError:
        gn.log(f"Fichier de requêtes illisible : {args.fichier} (encodage UTF-8 attendu)", 'error')
        return gn.EXIT_CONFIG
    except OSError:
        gn.log(f"Fichier de requêtes illisible : {args.fichier}", 'error')
        return gn.EXIT_CONFIG
    except (ValueError, KeyError, TypeError):
        gn.log(f"Fichier de requêtes illisible : {args.fichier} (objet {{\"requetes\": [...]}} attendu)", 'error')
        return gn.EXIT_CONFIG
    erreurs = verifier_options(requetes)
    if erreurs:
        for erreur in erreurs:
            gn.log(f"Fichier de requêtes : {erreur}", 'error')
        return gn.EXIT_CONFIG
    try:
        con, _ = rd.ouvrir_index_valide()
    except rd.Arret as e:
        gn.log(e.message, 'error')
        return e.code
    with contextlib.closing(con):
        evaluer(con, requetes, args.details)
    return gn.EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
