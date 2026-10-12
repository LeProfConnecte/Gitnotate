"""Définitions des mesures de scripts/evaluer_redecouverte.py (P@5 à dénominateur fixe, R@5, cas limites).

Aucun index ni réseau : seules les fonctions pures mesurer() et empreinte_jugements(), l'option --empreinte
(qui n'ouvre pas l'index) et le compte des correspondances fortes d'evaluer() (base SQLite en mémoire, recherche
remplacée par des réponses fabriquées) sont exercés.
"""
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'evaluer_redecouverte.py'


@pytest.fixture
def ev(load_gn):
    load_gn()
    spec = importlib.util.spec_from_file_location('evaluer_metriques', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _requete(en_tete=(), acceptables=(), a_exclure=()):
    return {'en_tete': list(en_tete), 'acceptables': list(acceptables), 'a_exclure': list(a_exclure)}


def test_p5_denominateur_fixe_et_r5(ev):
    # 1 seul pertinent jugé, trouvé au rang 1 : P@5 = 1/5 (et non 1/1), R@5 = 1
    m = ev.mesurer(['a/a', 'x/x', 'y/y'], _requete(en_tete=['a/a']))
    assert m['p5'] == pytest.approx(0.2) and m['r5'] == 1.0 and m['mrr'] == 1.0


def test_classement_court_non_avantage(ev):
    # 2 dépôts seulement dans le classement, tous deux pertinents : P@5 = 2/5
    m = ev.mesurer(['a/a', 'b/b'], _requete(en_tete=['a/a'], acceptables=['b/b']))
    assert m['p5'] == pytest.approx(0.4) and m['r5'] == 1.0


def test_plus_de_cinq_pertinents(ev):
    pertinents = [f'p/{i}' for i in range(8)]
    m = ev.mesurer(pertinents[:5] + ['x/x'], _requete(acceptables=pertinents))
    assert m['p5'] == 1.0 and m['r5'] == pytest.approx(5 / 8)
    assert m['mrr'] is None                      # aucun dépôt « en tête » jugé


def test_pertinents_apres_le_rang_5_ignores(ev):
    m = ev.mesurer(['x/1', 'x/2', 'x/3', 'x/4', 'x/5', 'a/a'], _requete(en_tete=['a/a']))
    assert m['p5'] == 0.0 and m['r5'] == 0.0 and m['mrr'] == pytest.approx(1 / 6)
    assert m['manquants'] == []                  # présent dans les 10 premiers


def test_requete_sans_reponse_attendue(ev):
    # aucune clé pertinente : P@5, R@5, nDCG@10 et MRR non définis ; intrus comptés
    m = ev.mesurer(['x/x', 'z/z'], _requete(a_exclure=['z/z']))
    assert m['p5'] is None and m['r5'] is None and m['ndcg10'] is None and m['mrr'] is None
    assert m['intrus3'] == 1 and m['intrus5'] == 1


def test_attendu_jamais_intrus_et_gain_maximal(ev):
    # une clé à la fois « en tête » et « à exclure » reste pertinente (gain 2), jamais intrus
    m = ev.mesurer(['a/a'], _requete(en_tete=['a/a'], acceptables=['a/a'], a_exclure=['a/a']))
    assert m['intrus3'] == 0 and m['p5'] == pytest.approx(0.2) and m['r5'] == 1.0 and m['ndcg10'] == 1.0


def test_metriques_moyennees_comprennent_r5(ev):
    assert ev.METRIQUES == ('ndcg10', 'p5', 'r5', 'mrr', 'intrus3', 'intrus5')


# =============================================================================
# --empreinte : prouver qu'un jeu de requêtes intégré n'a pas été modifié
# =============================================================================
FIXTURE_REQUETES = Path(__file__).resolve().parent / 'fixtures' / 'redecouverte' / 'requetes.json'
JUGES = ('id', 'requete', 'options', 'en_tete', 'acceptables', 'a_exclure', 'aucun_fort')
EXTERNES = [
    {'id': 'X02', 'jeu': 'externe', 'requete': 'un OCR sans GPU', 'options': {}, 'en_tete': ['a/ocr'],
     'acceptables': ['b/ocr', 'c/ocr'], 'a_exclure': ['d/gpu'], 'aucun_fort': False, 'raisons': 'gpu exclu'},
    {'id': 'X01', 'jeu': 'externe', 'requete': 'planning de chantier', 'options': {}, 'en_tete': [],
     'acceptables': [], 'a_exclure': ['e/x'], 'aucun_fort': True},
    {'id': 'X03', 'jeu': 'filtre', 'requete': '', 'options': {'licence': ['MIT']}, 'en_tete': ['a/ocr'],
     'acceptables': [], 'a_exclure': []},
]


def _empreinte_documentee(requetes):
    """Algorithme décrit dans docs/REDECOUVERTE.md § 9, réécrit indépendamment du script."""
    entrees = sorted(({k: q[k] for k in JUGES if k in q} for q in requetes), key=lambda e: e['id'])
    texte = json.dumps(entrees, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(texte.encode('ascii')).hexdigest()


def _ecrire(chemin, requetes, **dump):
    chemin.write_text(json.dumps({'requetes': requetes}, **dump), encoding='utf-8')
    return chemin


@pytest.fixture
def sans_recherche(ev, monkeypatch):
    def interdit(*a, **k):
        raise AssertionError("--empreinte ne doit ni ouvrir l'index ni lancer de recherche")
    for nom in ('ouvrir_index_valide', 'rechercher', 'analyser_requete'):
        monkeypatch.setattr(ev.rd, nom, interdit)
    return ev


def test_empreinte_sans_index_ni_recherche(sans_recherche, tmp_path, capsys):
    ev = sans_recherche
    fichier = _ecrire(tmp_path / 'externe.json', EXTERNES, ensure_ascii=False, indent=2)
    assert ev.main([str(fichier), '--empreinte']) == 0
    sortie = capsys.readouterr().out
    assert f"Empreinte des jugements (SHA-256) : {_empreinte_documentee(EXTERNES)}" in sortie
    assert f"Empreinte du fichier (SHA-256 des octets) : {hashlib.sha256(fichier.read_bytes()).hexdigest()}" in sortie
    assert 'Requêtes : 3 ;' in sortie
    assert f"  externe : 2 requêtes  {_empreinte_documentee(EXTERNES[:2])}" in sortie
    assert f"  filtre : 1 requête, dont 1 avec filtres (hors moyenne)  {_empreinte_documentee(EXTERNES[2:])}" in sortie
    assert 'nDCG@10' not in sortie
    # options écrites en texte seul : empreinte calculée avant la mise en liste, sans erreur
    texte = _ecrire(tmp_path / 'texte.json', [dict(EXTERNES[2], options={'licence': 'MIT'})])
    assert ev.main([str(texte), '--empreinte']) == 0
    assert _empreinte_documentee([dict(EXTERNES[2], options={'licence': 'MIT'})]) in capsys.readouterr().out
    # fichier illisible : même contrôle que pour les mesures (code 1)
    (tmp_path / 'casse.json').write_text('{"requetes": [}', encoding='utf-8')
    assert ev.main([str(tmp_path / 'casse.json'), '--empreinte']) == 1
    assert 'JSON invalide' in capsys.readouterr().err


def test_empreinte_insensible_a_la_mise_en_forme(sans_recherche, tmp_path):
    ev = sans_recherche
    reference = ev.empreinte_jugements(EXTERNES)
    # ordre des requêtes et des clés, champs hors jugements (jeu, raisons, commentaire) : sans effet
    autre = [dict(reversed(list(dict(q, jeu='independant', commentaire='rangé ailleurs').items())))
             for q in reversed(EXTERNES)]
    for q in autre:
        q.pop('raisons', None)
    assert ev.empreinte_jugements(autre) == reference
    # indentation, BOM, fins de ligne Windows : même empreinte des jugements, octets différents
    compact = _ecrire(tmp_path / 'compact.json', EXTERNES)
    bom = tmp_path / 'bom.json'
    bom.write_bytes(b'\xef\xbb\xbf' + json.dumps({'requetes': EXTERNES}, ensure_ascii=False, indent=1)
                    .replace('\n', '\r\n').encode('utf-8'))
    lus = [json.loads(f.read_bytes().decode('utf-8-sig'))['requetes'] for f in (compact, bom)]
    assert [ev.empreinte_jugements(r) for r in lus] == [reference, reference]
    assert compact.read_bytes() != bom.read_bytes()


@pytest.mark.parametrize('modification', [
    lambda q: q['en_tete'].append('z/z'),
    lambda q: q['acceptables'].remove('c/ocr'),
    lambda q: q['a_exclure'].clear(),
    lambda q: (q['acceptables'].remove('b/ocr'), q['a_exclure'].append('b/ocr')),   # jugement déplacé
    lambda q: q.update(aucun_fort=True),
    lambda q: q.update(requete='un OCR avec GPU'),
    lambda q: q.update(options={'statut': ['En test']}),
    lambda q: q.update(id='X09'),
    lambda q: q.pop('aucun_fort'),
    lambda q: q['en_tete'].insert(0, q['acceptables'].pop()),
], ids=['ajout_en_tete', 'retrait_acceptable', 'a_exclure_vide', 'deplace', 'aucun_fort', 'requete',
        'options', 'id', 'champ_retire', 'promu'])
def test_empreinte_detecte_toute_modification_de_jugement(sans_recherche, modification):
    ev = sans_recherche
    modifies = json.loads(json.dumps(EXTERNES))
    modification(modifies[0])
    assert ev.empreinte_jugements(modifies) != ev.empreinte_jugements(EXTERNES)


def test_empreinte_signale_les_identifiants_en_double(sans_recherche, tmp_path, capsys):
    ev = sans_recherche
    double = [EXTERNES[0], dict(EXTERNES[1], id='X02'), {k: v for k, v in EXTERNES[2].items() if k != 'id'}]
    assert ev.main([str(_ecrire(tmp_path / 'double.json', double)), '--empreinte']) == 0
    erreurs = capsys.readouterr().err
    assert 'identifiants en double : X02' in erreurs and '1 requête(s) sans « id »' in erreurs
    # à id égal, l'ordre du fichier ne change pas l'empreinte
    assert ev.empreinte_jugements(double) == ev.empreinte_jugements(list(reversed(double)))


def test_empreinte_des_jeux_figes_du_depot(ev):
    """Jugements des jeux de tests/fixtures/redecouverte/requetes.json : un changement de seuil ou de moteur ne
    doit jamais s'accompagner d'une retouche des attendus. Un nouveau jeu s'ajoute sous un nouveau nom de jeu,
    sans toucher ces empreintes. « nouvelles » a la même empreinte que le fichier figé avant tout résultat
    (requetes_nouvelles.json, SHA-256 des octets debd09a2…), intégré sans changement."""
    requetes = json.loads(FIXTURE_REQUETES.read_text(encoding='utf-8'))['requetes']
    jeux = {}
    for q in requetes:
        jeux.setdefault(q['jeu'], []).append(q)
    assert {jeu: (len(liste), ev.empreinte_jugements(liste)) for jeu, liste in jeux.items()
            if jeu in ('reference', 'hors_echantillon', 'anglais', 'nouvelles')} == {
        'reference': (15, '31f6704ff33acdae4b8666bbc2783294bbc11b0c759e8290c9e85f51cf1e9bd3'),
        'hors_echantillon': (10, '8b73b1e29059a901f1af06ddf2106e7b6b5d7022e87838ee90115a736e667976'),
        'anglais': (1, 'c9a7059c08ba5303aad6e41ab267891356d603da6ddc61ada198bec5aa53a37e'),
        'nouvelles': (8, '186d639603ae083c834d3c58b308fa29730678803f00e23de57e711c069767ae'),
    }


# =============================================================================
# Correspondances fortes et requêtes sans réponse attendue (« aucun_fort »)
# =============================================================================
def _resultat(cle, niveau, rang=None):
    return SimpleNamespace(cle=cle, niveau=niveau, rang=rang, score=0.5)


def test_forts_comptent_les_fiches_sans_depot_et_aucun_fort_est_controle(ev, monkeypatch, capsys):
    """« forts » compte aussi les fiches sans dépôt GitHub (elles peuvent être « forte ») ; une requête
    « aucun_fort »: true qui donne une correspondance forte est signalée, avec le compte par jeu."""
    reponses = {
        'S1': SimpleNamespace(resultats=[_resultat('a/a', 'partielle', 1)],
                              sans_depot=[_resultat('page:0001', 'forte')]),
        'S2': SimpleNamespace(resultats=[_resultat('b/b', 'partielle', 1)], sans_depot=[]),
        'S3': SimpleNamespace(resultats=[_resultat('a/a', 'forte', 1)], sans_depot=[_resultat('page:0001', 'forte')]),
    }
    monkeypatch.setattr(ev, 'lancer', lambda con, requete: reponses[requete['id']])
    requetes = [
        {'id': 'S1', 'jeu': 'externe', 'requete': 'x', 'en_tete': [], 'acceptables': [], 'a_exclure': [],
         'aucun_fort': True},
        {'id': 'S2', 'jeu': 'externe', 'requete': 'y', 'en_tete': [], 'acceptables': [], 'a_exclure': ['b/b'],
         'aucun_fort': True},
        {'id': 'S3', 'jeu': 'externe', 'requete': 'z', 'en_tete': ['a/a'], 'acceptables': [], 'a_exclure': [],
         'aucun_fort': False},
    ]
    con = sqlite3.connect(':memory:')
    try:
        con.execute('CREATE TABLE fiches (cle_depot TEXT)')
        con.executemany('INSERT INTO fiches VALUES (?)', [('a/a',), ('b/b',), ('page:0001',)])
        moyennes = ev.evaluer(con, requetes)
    finally:
        con.close()
    sortie = [ligne for ligne in capsys.readouterr().out.splitlines() if ligne.strip()]
    lignes = {ligne.split()[0]: ligne for ligne in sortie if not ligne.startswith('---')}
    assert 'forts=1  aucun_fort non respecté' in lignes['S1']       # la fiche sans dépôt « forte » compte
    assert 'forts=0' in lignes['S2'] and 'aucun_fort non respecté' not in lignes['S2']
    assert 'forts=2' in lignes['S3'] and 'aucun_fort non respecté' not in lignes['S3']
    assert '--- externe : aucun_fort non respecté pour 1 requête sur 2' in sortie
    assert any(ligne.startswith('--- externe : ') and 'ndcg10=1,00' in ligne for ligne in sortie)
    # les mesures ne changent pas : seules les requêtes avec des pertinents jugés entrent dans P@5
    assert moyennes['externe']['p5'] == pytest.approx(0.2) and moyennes['externe']['intrus3'] == pytest.approx(1 / 3)
