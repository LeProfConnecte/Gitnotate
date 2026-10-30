"""Jeu R du lot 6 (R01-R48) : corpus historique de non-régression du moteur stable (9aa4c6e).

- 24 fiches nouvelles (W1), 48 besoins avec leurs jugements (W2), un contre-jugement (X) et la qualification à
  l'aveugle des 5 premiers et des « forte » de 9aa4c6e et de la v2 refusée (A, B), chacun écrit dans une session
  isolée sans code ni classement ; besoins et jugements figés (SHA-256) avant toute exécution du moteur, fichiers
  conservés à l'octet (provenance : qualification_lot6/jeu_R/LISEZMOI.md).
- Le jeu a servi à refuser la v2 : il est consommé et n'est pas indépendant. Il ne valide aucune nouvelle variante ;
  réviser une valeur attendue suit les conditions du LISEZMOI (requalification à l'aveugle de tout couple nouveau).
- Index : fiches du corpus synthétique, suppléments N et M du lot 5 et fiches de W1. Les mesures attendues sont
  celles de 9aa4c6e ; celles de la v2 refusée ne figurent qu'en commentaire historique. Tout couple affiché dans les
  5 premiers ou en « forte » est qualifié par A et B (KeyError sinon).
Hors ligne : aucune base Notion réelle.
"""
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest
import redecouverte_outils as outils

ROOT = Path(__file__).resolve().parent.parent
JEU = 'qualification_lot6/jeu_R'
DOSSIER = ROOT / 'tests' / 'fixtures' / 'redecouverte' / JEU
# les 11 fichiers historiques figés, repris à l'octet de l'archive du lot 6 ; LISEZMOI.md est de la documentation
HISTORIQUES = {
    'supplement_R.json': '1057e4e4ca0fb5ebdb71fb3d9fd346795b0c85ba29af8d5e30a1bcd78138c231',
    'requetes_R.json': '2c98a91d6fa3faf1db1bdf759600c77697863af1d82233c0bf77789df9a6c7ba',
    'contre_R.json': '72d999061a7ad8e589ddbf6b5559088f03897c4d12554bf5d84bf27698c16c8d',
    'A_QUALIFIER_R.json': '38c75cfd392ac099b2a3aa712d5819ba24e9d9019b3371ff7a1f480375a7a29a',
    'analyste_A.json': 'c73735bafcedc4abfab13205ba99dcca32d23268c4c78125ba551110d883b35c',
    'analyste_B.json': '47c711ecb5d7feff9e8069ba5cc6dd62090473d2fefac115dd0bef5feaa583eb',
    'DECISIONS_LOT6_R.md': 'edbcc6705b4d18a31fa9105507d3248afd35dd38246733191a6e0e84b4b976e8',
    'EMPREINTES_GEL1.sha256': '6048f961869ffc16ae661ca5568158614990e599bd9e9b1dc330b13dc54b5abf',
    'EMPREINTES_GEL2.sha256': 'ce8c3d432528e6d040ab7d36ed8866993790844962bbd7a7770e5fc607689b69',
    'EMPREINTES_GEL3.sha256': 'e271ea5a3d6d2c068ddb78e9d997ea951175e2ce487da006ba555050725cd7ca',
    'EMPREINTES_GEL4.sha256': '7eba69049bc54d8332b1f19451a638fec29d42106b38b450019d64892037f810',
}
DOCUMENTATION = 'LISEZMOI.md'
# protocole non versionné (identifiants de sessions) : conservé dans l'archive, cité par son empreinte
SHA_PROTOCOLE = '69c88b5fdc4d0b9d3a05b63e4795129df7bb14bed66fe4563bc9eb76de1c3d9a'
# gel où chaque fichier a été figé (avant l'exécution du moteur pour les gels 1 à 3)
GELS = {'supplement_R.json': 1, 'requetes_R.json': 2, 'DECISIONS_LOT6_R.md': 2, 'contre_R.json': 3,
        'A_QUALIFIER_R.json': 4, 'analyste_A.json': 4, 'analyste_B.json': 4}
# 9aa4c6e (moteur stable) ; la v2 refusée du lot 6 en commentaire historique (même index, mêmes jugements)
MESURES = {
    'W2': {'ndcg10': 0.9152, 'mrr': 0.9348, 'p5': 0.3783, 'r5': 0.9062, 'intrus3': 0.0625, 'intrus5': 0.125,
           'premiers': 41},     # v2 refusée : ndcg10 0.9136, mrr 0.9312, p5 0.3739, r5 0.8953, le reste identique
    'X': {'ndcg10': 0.9053, 'mrr': 0.9348, 'p5': 0.3957, 'r5': 0.8565, 'intrus3': 0.0833, 'intrus5': 0.1875,
          'premiers': 41},      # v2 refusée : ndcg10 0.9057, p5 0.387, r5 0.842, intrus3 0.1042, le reste identique
}
QUALIFICATION = {
    'aucun_fort_viole_W2': 2, 'aucun_fort_viole_X': 2,
    'pertinent5_A': 61, 'pertinent5_B': 64,                    # v2 refusée : 60, 63
    'hors_sujet5_A': 131, 'hors_sujet5_B': 127,                # v2 refusée : 133, 129
    'fortes_non_pertinentes_A': 60, 'fortes_non_pertinentes_B': 59,
    'fortes': 109,                                             # v2 refusée : 108
}
ROLES = {'W2_juste': 28, 'W2_faux': 1, 'X_juste': 28, 'X_faux': 1}     # v2 refusée : identique (R04, zapier)


def _lire(nom):
    return json.loads((DOSSIER / nom).read_text(encoding='utf-8'))


def _evaluateur():
    spec = importlib.util.spec_from_file_location('evaluer_lot6', ROOT / 'scripts' / 'evaluer_redecouverte.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jugements(source):
    """Besoins au format de l'évaluateur, avec les jugements de W2 ou de X."""
    besoins = _lire('requetes_R.json')['requetes']
    juges = {q['id']: q for q in (besoins if source == 'W2' else _lire('contre_R.json')['requetes'])}
    return [{'id': q['id'], 'requete': q['requete'], 'options': {},
             **{k: juges[q['id']][k] for k in ('en_tete', 'acceptables', 'a_exclure', 'aucun_fort')}}
            for q in besoins]


@pytest.fixture
def banc(load_gn, monkeypatch):
    banc = outils.preparer(load_gn, monkeypatch)
    pages = outils.pages_du_corpus() + [p for s in ('lot5_supplement_N.json', 'lot5_supplement_M.json',
                                                    f'{JEU}/supplement_R.json') for p in outils.pages_du_supplement(s)]
    outils.index_du_corpus(banc.rd, pages)
    return banc


def test_fichiers_intacts_a_l_octet():
    assert len(HISTORIQUES) == 11
    assert sorted(p.name for p in DOSSIER.iterdir()) == sorted([*HISTORIQUES, DOCUMENTATION])
    for nom, sha in HISTORIQUES.items():
        assert hashlib.sha256((DOSSIER / nom).read_bytes()).hexdigest() == sha, nom
        assert b'\r' not in (DOSSIER / nom).read_bytes()
    lisezmoi = (DOSSIER / DOCUMENTATION).read_text(encoding='utf-8')
    assert SHA_PROTOCOLE in lisezmoi and 'PROTOCOLE_R.md' in lisezmoi     # protocole cité, non versionné


def test_fichiers_figes_dans_leur_gel():
    """Chaque fichier du jeu figure avec la même empreinte dans le gel daté où il a été figé."""
    for nom, gel in GELS.items():
        lignes = (DOSSIER / f'EMPREINTES_GEL{gel}.sha256').read_text(encoding='utf-8').splitlines()
        empreintes = {ligne.split()[1].rsplit('/', 1)[-1]: ligne.split()[0] for ligne in lignes
                      if ligne and not ligne.startswith('#')}
        assert empreintes[nom] == HISTORIQUES[nom], (nom, gel)


def test_gitattributes_protege_le_jeu():
    lignes = (ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()
    assert 'tests/fixtures/redecouverte/qualification_lot6/** -text' in lignes


def test_jeu_bien_forme():
    besoins = _lire('requetes_R.json')['requetes']
    assert [q['id'] for q in besoins] == [f'R{i:02d}' for i in range(1, 49)]
    assert Counter(q['theme'] for q in besoins) == {'A': 14, 'B': 8, 'C': 12, 'D': 6, 'E': 6, 'F': 2}
    assert Counter(q['langue'] for q in besoins) == {'fr': 31, 'en': 17}
    for source in ('W2', 'X'):
        for q in _jugements(source):
            listes = [set(q[k]) for k in ('en_tete', 'acceptables', 'a_exclure')]
            assert not (listes[0] & listes[1] or listes[0] & listes[2] or listes[1] & listes[2]), (source, q['id'])
            assert q['aucun_fort'] is (not q['en_tete'] and not q['acceptables']), (source, q['id'])
    a_qualifier = {r['id']: set(r['candidats']) for r in _lire('A_QUALIFIER_R.json')['requetes']}
    for qui in 'AB':
        jugements = _lire(f'analyste_{qui}.json')['jugements']
        assert {q: set(d) for q, d in jugements.items()} == a_qualifier, qui
        assert {v['etiquette'] for d in jugements.values() for v in d.values()} <= {'pertinent', 'plausible',
                                                                                    'hors_sujet'}


def test_mesures_figees(banc):
    rd, ev = banc.rd, _evaluateur()
    qualif = {qui: {q: {c: v['etiquette'] for c, v in d.items()} for q, d in _lire(f'analyste_{qui}.json')
                    ['jugements'].items()} for qui in 'AB'}
    sommes = {source: {} for source in ('W2', 'X')}
    compte = Counter()
    con, _ = rd.ouvrir_index_valide()
    try:
        connues = {cle for (cle,) in con.execute('SELECT DISTINCT cle_depot FROM fiches')}
        for source in ('W2', 'X'):
            for q in _jugements(source):
                assert {c for k in ('en_tete', 'acceptables', 'a_exclure') for c in q[k]} <= connues, q['id']
                reponse = ev.lancer(con, q)
                m = ev.mesurer(ev.classement_de(reponse), q)
                for cle in ('ndcg10', 'mrr', 'p5', 'r5', 'intrus3', 'intrus5'):
                    if m[cle] is not None:
                        sommes[source].setdefault(cle, []).append(m[cle])
                sommes[source].setdefault('premiers', []).append(m['mrr'] == 1.0)
                if q['aucun_fort'] and any(r.niveau == 'forte' for r in reponse.resultats + reponse.sans_depot):
                    compte[f'aucun_fort_viole_{source}'] += 1
                if source == 'W2':
                    for qui in 'AB':          # tout couple affiché dans les 5 premiers ou en « forte » est qualifié
                        top = [r.cle for r in reponse.resultats[:5]]
                        compte[f'pertinent5_{qui}'] += sum(qualif[qui][q['id']][c] == 'pertinent' for c in top)
                        compte[f'hors_sujet5_{qui}'] += sum(qualif[qui][q['id']][c] == 'hors_sujet' for c in top)
                        fortes = [r.cle for r in reponse.resultats + reponse.sans_depot
                                  if r.niveau == 'forte' and '/' in r.cle]
                        compte[f'fortes_non_pertinentes_{qui}'] += sum(qualif[qui][q['id']][c] != 'pertinent'
                                                                       for c in fortes)
                    compte['fortes'] += sum(r.niveau == 'forte' and '/' in r.cle
                                            for r in reponse.resultats + reponse.sans_depot)
    finally:
        con.close()
    mesures = {source: {cle: round(sum(v) / len(v), 4) if cle != 'premiers' else sum(v)
                        for cle, v in sommes[source].items()} for source in sommes}
    assert mesures == MESURES
    assert dict(compte) == QUALIFICATION


def test_roles_des_technologies(load_gn, monkeypatch):
    rd = outils.preparer(load_gn, monkeypatch).rd
    justes = Counter()
    for source in ('W2', 'X'):
        besoins = {q['id']: q for q in (_lire('requetes_R.json') if source == 'W2' else _lire('contre_R.json'))
                   ['requetes']}
        textes = {q['id']: q['requete'] for q in _lire('requetes_R.json')['requetes']}
        for qid, q in besoins.items():
            analyse = rd.analyser_requete(textes[qid])
            for r in q['roles']:
                sources = [e['source'] for e in analyse.exclusions if e['cible'] == r['identifiant']]
                lu = ('exclu' if 'exclusion' in sources else 'reference' if 'reference' in sources else
                      'cherche' if any(c.cle == r['identifiant'] and c.role != 'reference' for c in analyse.concepts)
                      else 'neutre')
                justes[(source, lu == r['role'])] += 1
    assert {f'{s}_{"juste" if ok else "faux"}': n for (s, ok), n in justes.items()} == ROLES
