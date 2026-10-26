"""Jeux du lot 5 : N01-N40 (indépendant) et M01-M30 (validation de la version retenue), docs/QUALIFICATION_LOT5.md.

- Chaque jeu a été rédigé à l'aveugle (sans voir le moteur ni ses résultats) avec un supplément de fiches fictives
  « synth-… », puis figé (SHA-256) avant toute mesure ; fichiers conservés à l'octet près.
- N a servi à choisir puis à corriger les règles (il ne vaut plus validation) ; M a été exécuté une seule fois,
  code et règles de décision figés, pour valider la version retenue.
- Les mesures de la version retenue sont figées ici (garde-fou : tout changement du moteur qui les modifie doit être
  remesuré et documenté), avec la règle de décision R3 : aucun dépôt jugé pertinent marqué « requis » par une
  exclusion.
- Règles de décision (DECISIONS_LOT5.md avant N, DECISIONS_V2.md avant M), variantes (patchs reproductibles) et
  jugements des analystes aveugles (qualification_lot5/) : versionnés à l'octet près ; les colonnes « hors sujet dans
  les 5 premiers » et « forte non pertinentes » de la version retenue en sont recalculées.
- Règle « aucun_fort » : respectée sur N ; sur M, M23 et M24 reçoivent des « forte » avec la référence f68b656 comme
  avec la version retenue (défaut antérieur au lot 5, non corrigé : M ne sert pas à régler).
Hors ligne : index construit depuis le corpus synthétique et les suppléments, aucune base Notion réelle.
"""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from redecouverte_outils import index_du_corpus, pages_du_corpus, pages_du_supplement, preparer

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'tests' / 'fixtures' / 'redecouverte'
FICHIERS = {
    'lot5_supplement_N.json': 'ff3e03dd3d523eb4033505540c3243168309c26ce434834f78b1daadb58a98b8',
    'requetes_lot5_N.json': '691bb8b33ea48f88852f9aaffae849b0a00c3de5a9154e607fd4e9ccbedce1d8',
    'PROTOCOLE_LOT5_N.md': 'e4120d7b8e79c98f55a7e82c087ac09ea2198a0109bfa2937b802a6c5d81aed6',
    'lot5_supplement_M.json': 'f4131a5630c90206133df8ccc29031a7b8d6de871f53e4ad5005e5b4613a8849',
    'requetes_lot5_M.json': '4bce0edc6b090ffce72837db27c0bdf299d67c7605eba4d79f2b682566f3da01',
    'PROTOCOLE_LOT5_M.md': '8d3d60d13d8bc27f2d5c503a61aa5cf38868ffbf097464f508f8fdb541258517',
    'qualification_lot5/DECISIONS_LOT5.md': '32c78ef6073a1f9be6c011f0f6e032945551733679daede18c47a5f1a51e9e9f',
    'qualification_lot5/DECISIONS_V2.md': 'fcc1d2a855b3c702184109ea205eafb888d62377f72602638407d28da9e9cbd3',
    'qualification_lot5/VARIANTES_CODE.txt': '94a4a29f0a51e1c65add350a188180557bb26ae5274813b689f0a7de571d90d8',
    'qualification_lot5/VARIANTES_V2_CODE.txt': 'ff1c16a95a3b8a5a69351fcd2ae82929a6cf081790cfd0ae4dceccb9d1cf8a23',
    'qualification_lot5/N/A_QUALIFIER_N.json': '4156be008ba22a2d192396b5c59bf802c19df9004e92329e9dddee5be69d5fde',
    'qualification_lot5/N/analyste_A.json': 'b6b3888e34b04e089e1e0fe7b8f790dbc8b8134149a530c9a82c4564a35b97ad',
    'qualification_lot5/N/analyste_B.json': '62e504b2e8e1ba1f7310881c5f647e96c3c97b86d593bd974baf365d2f9feeb9',
    'qualification_lot5/N/A_QUALIFIER_N_complement.json':
        '108a8aa6d7d21a83df9f9a9937676ddb2bc7d2d19b78b8400c9f828da07f1bb8',
    'qualification_lot5/N/analyste_A_complement.json':
        'a0513b39298d2f2efed64709289e47c291ff0eef30a6128218a325e83a888dfa',
    'qualification_lot5/N/analyste_B_complement.json':
        '2f51d83dcb5e903f8f3c37238c79ebb0c65740122e42ccf0a40c68d889d8a63f',
    'qualification_lot5/M/A_QUALIFIER_M.json': 'ade13ecfc440c04de08e91c34be9feb7c88c33cea1a7dd875b0b0f310ee1ab50',
    'qualification_lot5/M/analyste_A.json': '0c5a8e2e72fd845befbe1397af9eff8a6cad22401c98ef763665ce0259e6eeb5',
    'qualification_lot5/M/analyste_B.json': '29de8df0a90095ba2abfdb3912c9a86121e27bbfa3024c8bd6c79bef25e14da8',
    'qualification_lot5/M/A_QUALIFIER_M_complement.json':
        '46a73a21d03d772db5273eab1bcefd8e4ba9019bd04c59665bdd93d00972ba38',
    'qualification_lot5/M/analyste_A_complement.json':
        '299f037e1796af6c45bf74e152fa4d7e594fde132aca4dbcaaae152d259db26d',
    'qualification_lot5/M/analyste_B_complement.json':
        '919a60d7c0d81da363ae8000cf179be1315b5f593be2c94b9ff565a335e47c67',
    'qualification_lot5/N/A_QUALIFIER_N_complement2.json':
        '9888a5369f35b18f05a8869b50525e5eb1516c9ebf94eafe7bdab3c69fcbeb37',
    'qualification_lot5/N/analyste_A_complement2.json':
        '7ace034964aa5b41aa1bafee61960e766a0368906c79263b8ad6d52ccab2d837',
    'qualification_lot5/N/analyste_B_complement2.json':
        'ce7635bd0ac88090587fa822a8c1411e0ee9d42decedc42e7d4c0b299a97206f',
    'qualification_lot5/M/A_QUALIFIER_M_complement2.json':
        'fc0da7624adc048f302feaef65c80f3aeffc6f0a8ada3c9b11236ab368715b3a',
    'qualification_lot5/M/analyste_A_complement2.json':
        '1588462d96b48fbcf3fd6624828f62cb6e7b50fe1610e66099736a47e5f781c6',
    'qualification_lot5/M/analyste_B_complement2.json':
        'd791482aeeff95bc5e3c135a8fcac09333b3ca7391de05c8e753a4d7d0a70d26',
}
VARIANTES = {'P01': '452204c4bdf437ef', 'P02': '8118d03a57ee4517', 'P03': '7f6c2b75fb085945', 'L1': '45d2b3690220b98e',
             'L2': 'c7301895b27d08c4', 'L23': '8ab930f160b64313', 'L12': '7e0e0049e09f9f8f',
             'L123': '6620b47324dae6d7', 'V2a': '1d99d63008bd49c4', 'V2b': 'ba64acba82b40bc3',
             'V2c': '11634cbf62c060c0'}
# Moyennes (requêtes avec une valeur définie) de la version retenue après les revues (remesurées après l'exécution
# unique de M : QUALIFICATION_LOT5 § 6) ; V2b telle que validée sur M, puis référence f68b656, entre parenthèses
MESURES = {
    'N': {'ndcg10': 0.8876, 'mrr': 0.9213, 'p5': 0.3500, 'r5': 0.8170, 'intrus3': 0.275, 'intrus5': 0.450,
          'premiers': 31},
    # (V2b 0,885 0,921 0,339 0,803 0,325 0,575 31 ; f68b656 0,870 0,894 0,328 0,775 0,500 0,750 30)
    'M': {'ndcg10': 0.8141, 'mrr': 0.8349, 'p5': 0.3037, 'r5': 0.6977, 'intrus3': 0.300, 'intrus5': 0.4667,
          'premiers': 21},
    # (V2b 0,818 0,847 0,311 0,710 0,367 0,533 21 ; f68b656 0,791 0,795 0,304 0,698 0,567 0,667 19)
}
AUCUN_FORT_NON_RESPECTE = {'N': [], 'M': ['M23', 'M24']}      # identique avec la référence f68b656
# Qualification exhaustive (analystes A / B) : hors sujet dans les 5 premiers, « forte » de dépôts, « forte » non
# pertinentes ; référence f68b656 : N 118 / 115, 92, 58 ; M 95 / 93, 82, 54
QUALIFICATION = {'N': {'hors_sujet5': (110, 107), 'fortes': 75, 'fortes_non_pertinentes': (40, 40)},
                 'M': {'hors_sujet5': (95, 93), 'fortes': 68, 'fortes_non_pertinentes': (41, 41)}}


def _sha(chemin):
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _evaluateur():
    spec = importlib.util.spec_from_file_location('evaluer_lot5', ROOT / 'scripts' / 'evaluer_redecouverte.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _requetes(jeu):
    return json.loads((FIXTURES / f'requetes_lot5_{jeu}.json').read_text(encoding='utf-8'))['requetes']


@pytest.fixture(params=['N', 'M'])
def jeu(request, load_gn, monkeypatch):
    banc = preparer(load_gn, monkeypatch)
    supplements = ['lot5_supplement_N.json'] + (['lot5_supplement_M.json'] if request.param == 'M' else [])
    index_du_corpus(banc.rd, pages_du_corpus() + [p for s in supplements for p in pages_du_supplement(s)])
    return request.param, banc


def test_fichiers_intacts_a_l_octet():
    for nom, sha in FICHIERS.items():
        assert _sha(FIXTURES / nom) == sha, nom
        assert b'\r' not in (FIXTURES / nom).read_bytes()


def test_gitattributes_protege_les_fichiers():
    lignes = (ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()
    for nom in FICHIERS:
        assert (f"tests/fixtures/redecouverte/{nom} -text" in lignes
                or (nom.startswith('qualification_lot5/')
                    and "tests/fixtures/redecouverte/qualification_lot5/** -text" in lignes)), nom


def _appliquer(texte, patch):
    """Applique les blocs d'un patch unifié (contexte exact) à un texte."""
    lignes, sortie, i = texte.splitlines(keepends=True), [], 0
    for bloc in re.finditer(r'^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@.*\n((?:[ +\-\\].*\n?)*)', patch, re.MULTILINE):
        debut = int(bloc.group(1)) - 1
        sortie += lignes[i:debut]
        i = debut
        for ligne in bloc.group(2).splitlines(keepends=True):
            if ligne.startswith('\\'):
                sortie[-1] = sortie[-1].rstrip('\n')
            elif ligne.startswith('+'):
                sortie.append(ligne[1:])
            else:
                assert lignes[i] == ligne[1:], (i, ligne)
                if ligne.startswith(' '):
                    sortie.append(lignes[i])
                i += 1
    return ''.join(sortie + lignes[i:])


def test_variantes_reproductibles():
    """Chaque patch de qualification_lot5/variantes, appliqué à f68b656, redonne l'empreinte annoncée."""
    if not shutil.which('git') or subprocess.run(['git', 'cat-file', '-e', 'f68b656^{commit}'], cwd=ROOT,
                                                capture_output=True).returncode:
        pytest.skip('dépôt git sans le commit f68b656')
    ref = {nom: subprocess.run(['git', 'show', f'f68b656:{nom}'], cwd=ROOT, capture_output=True, check=True
                               ).stdout.decode('utf-8') for nom in ('redecouverte.py', 'redecouverte_lexique.py')}
    for variante, empreinte in VARIANTES.items():
        patch = (FIXTURES / 'qualification_lot5' / 'variantes' / f'{variante}.patch').read_text(encoding='utf-8')
        parties = re.split(r'^--- a/', patch, flags=re.MULTILINE)[1:]
        code = dict(ref)
        for partie in parties:
            nom = partie.split('\n', 1)[0].strip()
            code[nom] = _appliquer(code[nom], partie)
        brut = code['redecouverte.py'].encode('utf-8') + code['redecouverte_lexique.py'].encode('utf-8')
        assert hashlib.sha256(brut).hexdigest()[:16] == empreinte, variante


def _jugements(jeu):
    """Analyste -> besoin -> dépôt -> étiquette (jugements initiaux et complément, sans recouvrement)."""
    dossier = FIXTURES / 'qualification_lot5' / jeu
    jugements = {}
    for qui in 'AB':
        tous = json.loads((dossier / f'analyste_{qui}.json').read_text(encoding='utf-8'))['jugements']
        for suffixe in ('_complement', '_complement2'):        # couples entrés dans les 5 premiers après les revues
            complement = json.loads((dossier / f'analyste_{qui}{suffixe}.json').read_text(encoding='utf-8'))
            for q, depots in complement['jugements'].items():
                assert not set(depots) & set(tous.get(q, {}))
                tous.setdefault(q, {}).update(depots)
        jugements[qui] = {q: {c: j['etiquette'] for c, j in depots.items()} for q, depots in tous.items()}
    return jugements


def test_jugements_complets_et_valides():
    for jeu in ('N', 'M'):
        jugements = _jugements(jeu)
        a_qualifier = {}
        for nom in (f'A_QUALIFIER_{jeu}.json', f'A_QUALIFIER_{jeu}_complement.json',
                    f'A_QUALIFIER_{jeu}_complement2.json'):
            for q in json.loads((FIXTURES / 'qualification_lot5' / jeu / nom).read_text(encoding='utf-8'))['requetes']:
                a_qualifier.setdefault(q['id'], set()).update(q['candidats'])
        for qui in 'AB':
            assert {q: set(d) for q, d in jugements[qui].items()} == a_qualifier
            assert {e for d in jugements[qui].values() for e in d.values()} <= {'pertinent', 'plausible', 'hors_sujet'}


def test_jeux_bien_formes():
    for jeu, attendu in (('N', 40), ('M', 30)):
        requetes = _requetes(jeu)
        assert len(requetes) == attendu and len({q['id'] for q in requetes}) == attendu
        for q in requetes:
            assert not set(q['en_tete']) & set(q['acceptables']) and not set(q['a_exclure']) & set(q['en_tete'])
            assert q['aucun_fort'] is (not q['en_tete'] and not q['acceptables'])


def test_mesures_et_regles(jeu):
    nom, banc = jeu
    rd, ev = banc.rd, _evaluateur()
    sommes, premiers, fautes, fortes_sans_reponse = {}, 0, [], []
    jugements = _jugements(nom)
    hors_sujet5, fortes, non_pertinentes = [0, 0], 0, [0, 0]
    con, _ = rd.ouvrir_index_valide()
    try:
        connues = {cle for (cle,) in con.execute('SELECT DISTINCT cle_depot FROM fiches')}
        for q in _requetes(nom):
            assert {c for champ in ('en_tete', 'acceptables', 'a_exclure') for c in q[champ]} <= connues, q['id']
            reponse = ev.lancer(con, q)
            m = ev.mesurer(ev.classement_de(reponse), q)
            for cle in ('ndcg10', 'mrr', 'p5', 'r5', 'intrus3', 'intrus5'):
                if m[cle] is not None:
                    sommes.setdefault(cle, []).append(m[cle])
            premiers += m['mrr'] == 1.0
            pertinents = set(q['en_tete']) | set(q['acceptables'])
            fautes += [(q['id'], r.cle) for r in reponse.resultats
                       if r.cle in pertinents and any(x['etat'] == 'requis' for x in r.exclusions)]
            if q['aucun_fort'] and any(r.niveau == 'forte' for r in reponse.resultats + reponse.sans_depot):
                fortes_sans_reponse.append(q['id'])
            for i, qui in enumerate('AB'):          # tout couple affiché est jugé (KeyError sinon)
                hors_sujet5[i] += sum(jugements[qui][q['id']][r.cle] == 'hors_sujet' for r in reponse.resultats[:5])
                non_pertinentes[i] += sum(jugements[qui][q['id']][r.cle] != 'pertinent' for r in reponse.resultats
                                          if r.niveau == 'forte')
            fortes += sum(r.niveau == 'forte' for r in reponse.resultats)
    finally:
        con.close()
    moyennes = {cle: sum(v) / len(v) for cle, v in sommes.items()}
    for cle in ('ndcg10', 'mrr', 'p5', 'r5', 'intrus3', 'intrus5'):
        assert moyennes[cle] == pytest.approx(MESURES[nom][cle], abs=5e-4), cle
    assert premiers == MESURES[nom]['premiers']
    assert fautes == []
    assert fortes_sans_reponse == AUCUN_FORT_NON_RESPECTE[nom]
    assert (tuple(hors_sujet5), fortes, tuple(non_pertinentes)) == (
        QUALIFICATION[nom]['hors_sujet5'], QUALIFICATION[nom]['fortes'], QUALIFICATION[nom]['fortes_non_pertinentes'])
