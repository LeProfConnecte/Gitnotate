"""Moteur de redécouverte — synchronisation (spécification du lot 4, § 22.2).

A. Garde et sécurité · B. Lecture et validation · C. Atomicité, fichiers, Windows.
Aucun réseau : faux client Notion branché sur gn.get_session (redecouverte_outils.FausseNotion).
"""
import copy
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta
from fnmatch import fnmatch
from pathlib import Path

import pytest
import requests

from redecouverte_outils import (
    BASE_ID, JETON_LECTURE, JETON_TEST, SCHEMA_GITNOTATE, charger_bases, charger_corpus, contenu_index,
    empreinte, lignes, p_autre, p_texte, p_titre, page, pages_numerotees, panne_ajout, panne_curseur_repete,
    panne_exception, panne_non_json, panne_sans_curseur, panne_statut, preparer, requete_fts, schema,
    schema_base,
)

ROOT = Path(__file__).resolve().parent.parent
CORPS_ATTENDU = {'page_size': 100, 'sorts': [{'timestamp': 'created_time', 'direction': 'ascending'}]}


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


def _premiere_sync(banc, n=150):
    banc.notion.pages = pages_numerotees(n)
    assert banc.lancer('sync') == 0
    return empreinte(banc.index)


def _intact(banc, avant):
    assert empreinte(banc.index) == avant
    assert not list(banc.rd.dossier_index().glob('*.tmp*'))


def _sorties(capsys):
    out, err = capsys.readouterr()
    return out + err

# =============================================================================
# A. Garde et sécurité
# =============================================================================
def test_garde_refuse_post_pages(banc):
    with pytest.raises(banc.rd.EcritureNotionInterdite):
        banc.rd._appel_notion('POST', '/v1/pages', {'parent': {'database_id': BASE_ID}}, jeton=JETON_TEST)
    assert banc.notion.journal == []


@pytest.mark.parametrize('methode, chemin', [
    ('PATCH', f'/v1/pages/{BASE_ID}'),
    ('DELETE', f'/v1/blocks/{BASE_ID}'),
    ('POST', '/v1/databases'),
    ('POST', '/v1/pages'),
    ('GET', f'/v1/blocks/{BASE_ID}/children'),
    ('GET', '/v1/users/me'),
    ('PUT', f'/v1/databases/{BASE_ID}'),
    ('POST', f'/v1/databases/{BASE_ID}'),
    ('GET', f'/v1/databases/{BASE_ID}/query'),
    ('GET', '/v1/databases/pas-un-identifiant-hexadecimal-xx'),
    ('GET', f'/v1/databases/{BASE_ID.upper()}'),
    ('GET', f'/v1/databases/{BASE_ID}\n'),
    ('GET', f'/v1/databases/{BASE_ID}?filter_properties=x'),
    ('get', f'/v1/databases/{BASE_ID}'),
])
def test_garde_refuse_methodes_et_chemins(banc, methode, chemin):
    with pytest.raises(banc.rd.EcritureNotionInterdite):
        banc.rd._appel_notion(methode, chemin, None if methode != 'POST' else {}, jeton=JETON_TEST)
    assert banc.notion.journal == []


@pytest.mark.parametrize('methode, suffixe, corps', [
    ('POST', '/query', {'filter': {'property': 'URL'}}),
    ('POST', '/query', {'properties': {}}),
    ('POST', '/query', {'parent': {'database_id': BASE_ID}}),
    ('POST', '/query', {'archived': True}),
    ('POST', '/query', {'page_size': 100, 'in_trash': False}),
    ('POST', '/query', 'page_size=100'),
    ('GET', '', {'page_size': 100}),
])
def test_garde_refuse_corps_inattendu(banc, methode, suffixe, corps):
    with pytest.raises(banc.rd.EcritureNotionInterdite):
        banc.rd._appel_notion(methode, f'/v1/databases/{BASE_ID}{suffixe}', corps, jeton=JETON_TEST)
    assert banc.notion.journal == []


def test_sync_complete_seulement_lectures(banc):
    banc.notion.pages = pages_numerotees(250)
    assert banc.lancer('sync') == 0
    appels = banc.notion.appels()
    assert appels[0] == ('GET', f'https://api.notion.com/v1/databases/{BASE_ID}')
    assert appels[1:] == [('POST', f'https://api.notion.com/v1/databases/{BASE_ID}/query')] * 3
    assert all(h.get('Notion-Version') == '2022-06-28' for _, _, _, h in banc.notion.journal)
    assert banc.notion.hors_notion == []


def test_source_sans_ecriture_notion():
    interdits = ('v1/pages', 'v1/blocks', "'PATCH'", '"PATCH"', "'DELETE'", '"DELETE"', "'PUT'", '"PUT"',
                 'requests.', 'urllib', 'http.client', 'idempotent=False')
    for nom in ('redecouverte.py', 'redecouverte_lexique.py'):
        source = (ROOT / nom).read_text(encoding='utf-8')
        for motif in interdits:
            assert motif not in source, f"{motif} trouvé dans {nom}"


def test_version_notion_inattendue_refusee(banc, monkeypatch, capsys):
    banc.notion.pages = pages_numerotees(3)
    monkeypatch.setitem(banc.gn.NOTION_HEADERS, 'Notion-Version', '2025-09-03')
    assert banc.lancer('sync') == 1
    assert banc.notion.journal == []
    assert "Version de l'API Notion inattendue" in _sorties(capsys)
    assert not banc.index.exists()


def test_jeton_lecture_prioritaire(load_gn, monkeypatch, capsys):
    banc = preparer(load_gn, monkeypatch, NOTION_READONLY_TOKEN=JETON_LECTURE)
    banc.notion.pages = pages_numerotees(3)
    assert banc.lancer('sync') == 0
    assert banc.notion.journal
    assert all(h['Authorization'] == f'Bearer {JETON_LECTURE}' for _, _, _, h in banc.notion.journal)
    sortie = _sorties(capsys)
    assert '(NOTION_READONLY_TOKEN)' in sortie and 'Conseil' not in sortie


@pytest.mark.parametrize('valeur', [None, 'ntn_abc def' + 'x' * 30, 'ntn_abc\ndef' + 'x' * 30])
def test_jeton_absent_ou_coupe(load_gn, monkeypatch, capsys, valeur):
    banc = preparer(load_gn, monkeypatch, NOTION_TOKEN=valeur)
    assert banc.lancer('sync') == 1
    assert banc.notion.journal == []
    sortie = _sorties(capsys)
    assert 'Fichier .env attendu' in sortie and str(banc.gn.ENV_FILE) in sortie
    if valeur:
        assert valeur not in sortie and 'def' + 'x' * 30 not in sortie


@pytest.mark.parametrize('valeur, code', [
    ('', 1), ('https://www.notion.so/Ressources-' + BASE_ID, 1), (BASE_ID[:31], 1), (BASE_ID[:31] + 'z', 1),
    (BASE_ID[:16] + ' ' + BASE_ID[16:], 1), ('-'.join([BASE_ID[:8], BASE_ID[8:12], BASE_ID[12:16],
                                                      BASE_ID[16:20], BASE_ID[20:]]), 0),
    (BASE_ID.upper(), 0), ('  ' + BASE_ID + '  ', 0),
])
def test_database_id_invalide(load_gn, monkeypatch, capsys, valeur, code):
    banc = preparer(load_gn, monkeypatch, DATABASE_ID=valeur)
    banc.notion.pages = pages_numerotees(2)
    assert banc.lancer('sync') == code
    if code:
        assert banc.notion.journal == []
        assert 'DATABASE_ID' in _sorties(capsys)


@pytest.mark.parametrize('nom, valeur, attendu', [
    ('REDECOUVERTE_RESULTATS', '0', 'minimum : 1'),
    ('REDECOUVERTE_RESULTATS', 'abc', "n'est pas un entier valide"),
    ('REDECOUVERTE_RESULTATS', '51', 'maximum : 50'),
    ('REDECOUVERTE_LLM_MAX', '16', 'REDECOUVERTE_LLM_MAX=16 est invalide (maximum : 15)'),
])
def test_variables_redecouverte_invalides(banc, monkeypatch, capsys, nom, valeur, attendu):
    monkeypatch.setenv(nom, valeur)
    # Revue du lot 4 : contrôlées par la commande qui les lit (cherche ; --llm pour REDECOUVERTE_LLM_MAX),
    # plus par sync
    assert banc.lancer('cherche', 'pdf', *(['--llm'] if nom == 'REDECOUVERTE_LLM_MAX' else [])) == 1
    assert banc.notion.journal == []
    assert attendu in _sorties(capsys)
    assert nom not in banc.gn.CONFIG_ERRORS          # aucune trace laissée dans gitnotate


def test_variables_redecouverte_valides(banc, monkeypatch):
    monkeypatch.setenv('REDECOUVERTE_RESULTATS', '50')
    monkeypatch.setenv('REDECOUVERTE_LLM_MAX', '15')
    cfg = banc.rd.lire_config()
    assert (cfg.resultats, cfg.llm_max, cfg.erreurs) == (50, 15, ())
    assert banc.rd.lire_config(notion=False).erreurs == ()


def test_import_sans_effet_de_bord(banc, tmp_path):
    import importlib
    importlib.reload(banc.rd)
    assert list(tmp_path.iterdir()) == []
    assert banc.notion.journal == []


def test_index_sans_jeton(load_gn, monkeypatch, capsys):
    secrets = {'MISTRAL_API_KEY': 'mistral-cle-secrete-0123456789', 'GITHUB_TOKEN': 'ghp_' + 'G7h8' * 9,
               'OPENROUTER_API_KEY': 'sk-or-v1-' + 'ab' * 24, 'NOTION_CLEANER_TOKEN': 'nettoyeur-secret-42'}
    banc = preparer(load_gn, monkeypatch, **secrets)
    fuite = page('fuite', 'https://github.com/o/fuite', props={
        'Notes': p_texte(f"Jeton : {JETON_TEST} à ne pas garder"),
        'Description': p_texte(f"Clé {secrets['MISTRAL_API_KEY'].upper()} et {secrets['NOTION_CLEANER_TOKEN']}.")})
    banc.notion.pages = pages_numerotees(3) + [fuite]
    assert banc.lancer('sync') == 0
    donnees = banc.index.read_bytes()
    for valeur in list(secrets.values()) + [JETON_TEST]:
        assert valeur.encode() not in donnees and valeur.lower().encode() not in donnees
    assert '[jeton masqué]'.encode() in donnees
    codes = lignes(banc.rd, "SELECT champ, code FROM anomalies WHERE code = 'jeton_masque'")
    assert ('Notes', 'jeton_masque') in codes and ('Description', 'jeton_masque') in codes
    assert JETON_TEST not in _sorties(capsys)


def test_masquage_motifs_jetons(banc):
    masquer = banc.rd.masquer
    for jeton in ('ntn_' + 'a1B2' * 6, 'secret_' + 'Q' * 25, 'ghp_' + 'B' * 36, 'gho_' + 'c' * 30,
                  'github_pat_' + '11ABC_' * 5, 'sk-or-v1-' + 'f0' * 20):
        assert masquer(f"avant {jeton} après") == 'avant [jeton masqué] après'
    for intact in ('sk-...', 'export OPENAI_API_KEY=sk-xxxx', 'ntn_court', 'ghp_abc', 'secret_court'):
        assert masquer(intact) == intact
    assert masquer('clé AbCdEfGh123 ici', ('abcdefgh123',)) == 'clé [jeton masqué] ici'


def test_controle_octets_refuse_remplacement(banc, monkeypatch, capsys):
    avant = _premiere_sync(banc, 20)
    banc.notion.pages = pages_numerotees(20) + [page('fuite', 'https://github.com/o/fuite',
                                                    props={'Notes': p_texte(f"jeton {JETON_TEST}")})]
    monkeypatch.setattr(banc.rd, 'masquer', lambda texte, secrets=(): texte)
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    sortie = _sorties(capsys)
    assert 'Un jeton a été détecté' in sortie and JETON_TEST not in sortie


def test_exports_et_capture_sans_jeton(banc, capsys):
    banc.notion.pages = pages_numerotees(3) + [page('fuite', 'https://github.com/o/fuite',
                                                    props={'Notes': p_texte(f"jeton {JETON_TEST}")})]
    assert banc.lancer('sync', '--capture', 'cap.json') == 0
    capture = Path(banc.gn.BASE_DIR) / 'exports' / 'cap.json'
    texte = capture.read_text(encoding='utf-8')
    assert JETON_TEST not in texte and JETON_TEST.lower() not in texte and '[jeton masqué]' in texte
    # Une capture qui contiendrait un jeton n'est jamais écrite
    rd = banc.rd
    plate = rd.PagePlate('a' * 32, '', '', '', {'Notes': rd.ValeurPlate('rich_text', texte=JETON_TEST)})
    meta = rd.MetaLecture(BASE_ID, 'Base', 'notion', dict(SCHEMA_GITNOTATE), 1, 1, {}, '2026-10-11T00:00:00+00:00')
    with pytest.raises(rd.Arret) as erreur:
        rd.ecrire_capture('refusee.json', [plate], meta, (JETON_TEST,))
    assert erreur.value.code == 2 and JETON_TEST not in erreur.value.message
    assert not (Path(banc.gn.BASE_DIR) / 'exports' / 'refusee.json').exists()
    assert JETON_TEST not in _sorties(capsys)


def test_jeton_jamais_affiche(banc, monkeypatch, capsys):
    banc.notion.pages = pages_numerotees(2)
    banc.notion.panne_schema = requests.exceptions.InvalidHeader(f"Invalid header value b'Bearer {JETON_TEST}'")
    assert banc.lancer('sync') == 2
    from redecouverte_outils import erreur_notion
    banc.notion.panne_schema = erreur_notion(401, 'API token is invalid.', 'unauthorized')
    assert banc.lancer('sync') == 1
    banc.notion.panne_schema = None

    def explose(*args, **kwargs):
        raise ValueError(f"valeur inattendue {JETON_TEST}")
    monkeypatch.setattr(banc.rd, 'resoudre_colonnes', explose)
    assert banc.lancer('sync') == 2
    sortie = _sorties(capsys)
    assert JETON_TEST not in sortie and JETON_TEST[4:] not in sortie
    assert 'API token is invalid.' in sortie and 'Erreur inattendue (ValueError)' in sortie


CHEMINS_IGNORES = ('.gitnotate_index/redecouverte.sqlite', '.gitnotate_index/redecouverte.sqlite.tmp',
                   '.gitnotate_index/redecouverte.sqlite.tmp-journal', '.gitnotate_index/sync.lock',
                   'exports/capture-notion-20261011-120000.json', 'exports/redecouverte-20261011-120000.md')


def test_gitignore_couvre_index_exports_capture():
    git = shutil.which('git')
    if git and (ROOT / '.git').exists():
        for chemin in CHEMINS_IGNORES:
            resultat = subprocess.run([git, 'check-ignore', '-q', '--no-index', chemin], cwd=ROOT,
                                      capture_output=True, check=False)
            assert resultat.returncode == 0, chemin
    motifs = [ligne.strip() for ligne in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
              if ligne.strip() and not ligne.startswith('#')]
    for chemin in CHEMINS_IGNORES:
        assert any(chemin.startswith(m) or fnmatch(chemin, m) or fnmatch(Path(chemin).name, m) for m in motifs), chemin


def test_capture_sans_donnees_personnelles(banc):
    colonnes = dict(SCHEMA_GITNOTATE, Responsable='people', Courriel='email', Téléphone='phone_number',
                    Pièce='files', **{'Créé par': 'created_by'})
    banc.notion.base = schema(colonnes)
    personnelles = {
        'Responsable': p_autre('people', [{'object': 'user', 'id': 'utilisateur-secret-1', 'name': 'Jean Dupont',
                                           'person': {'email': 'jean.dupont@example.com'}}]),
        'Courriel': p_autre('email', 'jean.dupont@example.com'),
        'Téléphone': p_autre('phone_number', '+687 12 34 56'),
        'Pièce': p_autre('files', [{'name': 'plan.pdf', 'type': 'file',
                                    'file': {'url': 'https://s3.example.com/plan.pdf?X-Amz-Signature=abc',
                                             'expiry_time': '2026-10-11T13:00:00.000Z'}}]),
        'Créé par': p_autre('created_by', {'object': 'user', 'id': 'utilisateur-secret-2', 'name': 'Marie Martin'}),
    }
    banc.notion.pages = [page('docling', props=personnelles)]
    assert banc.lancer('sync', '--capture') == 0
    captures = list((Path(banc.gn.BASE_DIR) / 'exports').glob('capture-notion-*.json'))
    assert len(captures) == 1
    for donnees in (captures[0].read_bytes(), banc.index.read_bytes()):
        for secret in ('jean.dupont@example.com', 'Jean Dupont', '+687 12 34 56', 's3.example.com',
                       'utilisateur-secret-1', 'utilisateur-secret-2', 'Marie Martin'):
            assert secret.encode() not in donnees
    capture = json.loads(captures[0].read_text(encoding='utf-8'))
    assert capture['format'] == 'gitnotate-capture/1' and capture['gitnotate'] == banc.gn.__version__
    assert set(capture['pages'][0]['colonnes']) & {'Responsable', 'Courriel', 'Téléphone', 'Pièce', 'Créé par'} == set()

# =============================================================================
# B. Lecture et validation
# =============================================================================
def test_sync_pagination_complete(banc):
    banc.notion.pages = pages_numerotees(355)
    assert banc.lancer('sync') == 0
    assert banc.notion.nb_requetes == 4
    curseurs = [c.get('start_cursor') for m, _, c, _ in banc.notion.journal if m == 'POST']
    assert curseurs == [None, 'curseur-2', 'curseur-3', 'curseur-4']
    assert lignes(banc.rd, 'SELECT count(*) FROM fiches')[0][0] == 355
    assert lignes(banc.rd, "SELECT valeur FROM meta WHERE cle = 'nb_requetes'")[0][0] == '4'


def test_corps_de_requete_exact(banc):
    banc.notion.pages = pages_numerotees(150)
    assert banc.lancer('sync') == 0
    corps = [c for m, _, c, _ in banc.notion.journal if m == 'POST']
    assert corps == [CORPS_ATTENDU, dict(CORPS_ATTENDU, start_cursor='curseur-2')]
    assert [c for m, _, c, _ in banc.notion.journal if m == 'GET'] == [None]


def test_has_more_sans_curseur(banc, capsys):
    avant = _premiere_sync(banc)
    banc.notion.pannes[1] = panne_sans_curseur
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    assert 'has_more sans next_cursor' in _sorties(capsys)


def test_curseur_repete(banc, capsys):
    avant = _premiere_sync(banc)
    banc.notion.pannes[2] = panne_curseur_repete
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    assert 'curseur répété' in _sorties(capsys)


def test_trop_de_reponses(banc, monkeypatch, capsys):
    avant = _premiere_sync(banc, 450)
    monkeypatch.setattr(banc.rd, 'MAX_REPONSES', 3)
    banc.notion.journal.clear()
    assert banc.lancer('sync') == 2
    assert banc.notion.nb_requetes == 3
    _intact(banc, avant)
    assert 'pagination anormalement longue' in _sorties(capsys)


def test_request_status_incomplet(banc, capsys):
    avant = _premiere_sync(banc)
    banc.notion.pannes[1] = lambda r, n: dict(r, request_status={'type': 'incomplete',
                                                                  'incomplete_reason': 'query_result_limit_reached'})
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    assert 'lecture incomplète' in _sorties(capsys)


@pytest.mark.parametrize('panne, attendu', [
    (panne_statut(500, 'Internal error'), 'HTTP 500'),
    (panne_statut(429, 'Rate limited', headers={'Retry-After': '999'}), 'HTTP 429'),
    (panne_exception(requests.exceptions.ConnectionError('refus')), 'pas de réponse (connexion impossible)'),
    (panne_statut(400, 'Bad request'), 'HTTP 400'),
    (panne_statut(401, 'API token is invalid.'), 'HTTP 401'),
])
def test_erreur_http_pendant_lecture(banc, capsys, panne, attendu):
    avant = _premiere_sync(banc)
    banc.notion.pannes[2] = panne
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    sortie = _sorties(capsys)
    assert 'Lecture interrompue (réponse 2)' in sortie and attendu in sortie


@pytest.mark.parametrize('panne', [
    panne_non_json,
    lambda r, n: dict(r, object='page'),
    lambda r, n: dict(r, results={'0': r['results']}),
    lambda r, n: dict(r, has_more='true'),
])
def test_reponse_illisible(banc, capsys, panne):
    avant = _premiere_sync(banc)
    banc.notion.pannes[1] = panne
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    assert 'réponse illisible' in _sorties(capsys)


def test_page_partielle_abandon(banc, capsys):
    avant = _premiere_sync(banc)
    banc.notion.pannes[1] = panne_ajout({'object': 'page', 'id': 'f' * 32})
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    assert 'fiche illisible' in _sorties(capsys)


def test_base_imbriquee_ignoree_et_comptee(banc, capsys):
    banc.notion.pages = pages_numerotees(5)
    banc.notion.pannes[1] = panne_ajout({'object': 'database', 'id': 'e' * 32, 'title': []})
    assert banc.lancer('sync') == 0
    meta = dict(lignes(banc.rd, 'SELECT cle, valeur FROM meta'))
    assert json.loads(meta['ignorees_json']) == {'corbeille': 0, 'base_imbriquee': 1}
    assert (meta['nb_fiches'], meta['nb_objets_recus']) == ('5', '6')
    assert '1 base imbriquée ignorée' in _sorties(capsys)


def test_page_autre_base(banc, capsys):
    avant = _premiere_sync(banc)
    banc.notion.pannes[2] = panne_ajout(page('etrangere', 'https://github.com/o/x', base_id='f' * 32))
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    assert "page d'une autre base reçue" in _sorties(capsys)


def test_page_recue_deux_fois(banc, capsys):
    avant = _premiere_sync(banc)
    banc.notion.pannes[2] = panne_ajout(banc.notion.pages[0])
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    assert 'la base a changé pendant la lecture' in _sorties(capsys)


def test_corbeille_ignoree_et_comptee(banc, capsys):
    banc.notion.pages = pages_numerotees(4) + [page('jetee', 'https://github.com/o/jetee', corbeille=True)]
    assert banc.lancer('sync') == 0
    assert [n for (n,) in lignes(banc.rd, 'SELECT nom FROM fiches')] == [f'depot-{i}' for i in range(4)]
    meta = dict(lignes(banc.rd, 'SELECT cle, valeur FROM meta'))
    assert json.loads(meta['ignorees_json'])['corbeille'] == 1
    assert '1 à la corbeille ignorée' in _sorties(capsys)


@pytest.mark.parametrize('statut, message, code, piste', [
    (400, 'Databases with multiple data sources are not supported.', 1, 'multi-sources'),
    (401, 'API token is invalid.', 1, 'NOTION_READONLY_TOKEN, sinon NOTION_TOKEN'),
    (403, 'Insufficient permissions.', 1, '« Read content »'),
    (404, 'Could not find database.', 1, 'Connexions'),
    (500, 'Internal error.', 2, 'incident passager'),
])
def test_schema_erreurs_http(banc, capsys, statut, message, code, piste):
    from redecouverte_outils import erreur_notion
    banc.notion.panne_schema = erreur_notion(statut, message)
    assert banc.lancer('sync') == code
    assert banc.notion.nb_requetes == 0
    sortie = _sorties(capsys)
    assert piste in sortie and message in sortie
    assert not banc.index.exists()


def test_schema_sans_colonne_url(banc, capsys):
    banc.notion.base = schema({nom: t for nom, t in SCHEMA_GITNOTATE.items() if nom != 'URL'})
    assert banc.lancer('sync') == 1
    assert 'colonne URL absente' in _sorties(capsys)
    assert banc.notion.nb_requetes == 0


def test_schema_titre_autre_nom(banc):
    colonnes = {('Name' if nom == 'Nom' else nom): t for nom, t in SCHEMA_GITNOTATE.items()}
    banc.notion.base = schema(colonnes)
    fiche = page('olmocr', 'https://github.com/allenai/olmocr')
    fiche['properties']['Name'] = fiche['properties'].pop('Nom')
    banc.notion.pages = [fiche]
    assert banc.lancer('sync') == 0
    assert lignes(banc.rd, 'SELECT nom, cle_depot FROM fiches') == [('olmocr', 'allenai/olmocr')]
    assert requete_fts(banc.rd, 'nom : olmocr')


def _brancher_base(banc, monkeypatch, cle):
    """Branche une base du corpus (A, B ou C) avec ses fiches hors corbeille."""
    bases, corpus = charger_bases(), charger_corpus()
    base_id = bases[cle]['id'].replace('-', '')
    monkeypatch.setattr(banc.gn, 'DATABASE_ID', bases[cle]['id'])
    banc.notion.base_id = base_id
    banc.notion.base = copy.deepcopy(bases[cle])
    banc.notion.pages = [c['page'] for c in corpus if c['base'] == cle]
    return bases[cle]


def test_colonnes_facultatives_absentes_sans_erreur(banc, monkeypatch):
    _brancher_base(banc, monkeypatch, 'B')
    assert banc.lancer('sync') == 0
    meta = dict(lignes(banc.rd, 'SELECT cle, valeur FROM meta'))
    assert set(json.loads(meta['colonnes_absentes_json'])) == {'Justification', 'Licence', 'Catégorie', 'Brique pour'}
    assert json.loads(meta['colonnes_personnelles_json']) == ['Tags']
    assert json.loads(meta['colonnes_ignorees_json']) == {'Créé le': 'created_time'}
    codes = {c for (c,) in lignes(banc.rd, 'SELECT code FROM anomalies')}
    assert 'type_inattendu' not in codes and 'colonne_ambigue' not in codes
    assert lignes(banc.rd, 'SELECT count(*) FROM fiches')[0][0] == 4


def test_aucune_fiche_perdue(banc):
    cassees = [
        page('cassee-1', 'https://github.com/o/c1', props={
            'Description': {'type': 'rich_text', 'rich_text': 'pas une liste'},
            'Stars': {'type': 'number', 'number': True}, 'Statut': {'type': 'select', 'select': ['x']},
            'Type': {'type': 'multi_select', 'multi_select': 'Outils'},
            'Analysé le': {'type': 'date', 'date': 'hier'}, 'Notes': {'type': None}}),
        page('cassee-2', 'https://github.com/o/c2', props={'Nom': 'texte brut', 'URL': {'type': 'url', 'url': 5}}),
        page('cassee-3', 'https://github.com/o/c3', props={'Justification': 42, 'Pertinence': {'type': 'number'}}),
        page(None, '', props={'Nom': p_titre(), 'URL': {'type': 'url', 'url': None}}, v73=False),
    ]
    banc.notion.pages = pages_numerotees(3) + cassees
    assert banc.lancer('sync') == 0
    assert lignes(banc.rd, 'SELECT count(*) FROM fiches')[0][0] == 7
    codes = {c for (c,) in lignes(banc.rd, 'SELECT code FROM anomalies')}
    assert {'valeur_illisible', 'titre_absent', 'url_absente'} <= codes

# =============================================================================
# C. Atomicité, fichiers, Windows
# =============================================================================
def test_premiere_synchronisation(banc):
    assert not banc.rd.dossier_index().exists()
    banc.notion.pages = pages_numerotees(12)
    assert banc.lancer('sync') == 0
    assert banc.rd.dossier_index().is_dir() and banc.index.is_file()
    assert banc.lancer('etat') == 0
    con = banc.rd.ouvrir_index_lecture()
    try:
        meta = banc.rd.verifier_format(con)
    finally:
        con.close()
    assert meta['nb_fiches'] == '12' and meta['source'] == 'notion' and meta['database_id'] == BASE_ID
    assert meta['gitnotate_version'] == banc.gn.__version__ and meta['moteur_version'] == banc.rd.__version__


def test_ctrl_c_pendant_lecture(banc, capsys):
    avant = _premiere_sync(banc)
    banc.notion.pannes[2] = panne_exception(KeyboardInterrupt())
    assert banc.lancer('sync') == 130
    _intact(banc, avant)
    assert banc.gn._STOP_EVENT.is_set()
    banc.rd.liberer_verrou(banc.rd.prendre_verrou())        # verrou repris aussitôt
    assert "Interruption : l'index précédent est conservé" in _sorties(capsys)


def test_ctrl_c_pendant_construction(banc, monkeypatch):
    avant = _premiere_sync(banc)
    vrai = banc.rd._inserer_fiche
    appels = []

    def interrompt(con, rowid, fiche, principale):
        appels.append(rowid)
        if len(appels) == 3:
            raise KeyboardInterrupt
        vrai(con, rowid, fiche, principale)
    monkeypatch.setattr(banc.rd, '_inserer_fiche', interrompt)
    assert banc.lancer('sync') == 130
    _intact(banc, avant)
    banc.rd.liberer_verrou(banc.rd.prendre_verrou())


def test_reprise_apres_interruption(banc, monkeypatch, tmp_path):
    banc.notion.pages = pages_numerotees(230)
    banc.notion.pannes[2] = panne_exception(KeyboardInterrupt())
    assert banc.lancer('sync') == 130
    assert not banc.index.exists()
    banc.notion.pannes.clear()
    banc.gn._STOP_EVENT.clear()
    assert banc.lancer('sync') == 0
    repris = contenu_index(banc.rd)
    monkeypatch.setattr(banc.gn, 'BASE_DIR', tmp_path / 'sans-interruption')
    assert banc.lancer('sync') == 0
    assert contenu_index(banc.rd) == repris


def test_tmp_orphelin_supprime(banc):
    dossier = banc.rd.dossier_index()
    dossier.mkdir(parents=True)
    (dossier / 'redecouverte.sqlite.tmp').write_bytes(b'reste d une synchronisation tuee')
    (dossier / 'redecouverte.sqlite.tmp-journal').write_bytes(b'journal')
    banc.notion.pages = pages_numerotees(3)
    assert banc.lancer('sync') == 0
    assert sorted(p.name for p in dossier.iterdir()) == ['redecouverte.sqlite', 'sync.lock']


def test_verrou_detenu(banc, capsys):
    dossier = banc.rd.dossier_index()
    dossier.mkdir(parents=True)
    fd = banc.rd.prendre_verrou(dossier)
    try:
        banc.notion.pages = pages_numerotees(3)
        assert banc.lancer('sync') == 2
        assert banc.notion.journal == []
        assert 'Une autre synchronisation est en cours' in _sorties(capsys)
    finally:
        banc.rd.liberer_verrou(fd)
    assert banc.lancer('sync') == 0


def test_verrou_libere_apres_erreur(banc):
    from redecouverte_outils import erreur_notion
    banc.notion.panne_schema = erreur_notion(401, 'API token is invalid.')
    assert banc.lancer('sync') == 1
    banc.rd.liberer_verrou(banc.rd.prendre_verrou())
    banc.notion.panne_schema = None
    banc.notion.pages = pages_numerotees(150)
    banc.notion.pannes[2] = panne_statut(500)
    assert banc.lancer('sync') == 2
    banc.rd.liberer_verrou(banc.rd.prendre_verrou())


def test_remplacement_bloque_windows(banc, monkeypatch, capsys):
    avant = _premiere_sync(banc, 10)
    vrai = os.replace
    essais = []

    def bloque(src, dst):
        essais.append(src)
        raise PermissionError(13, 'Accès refusé')
    monkeypatch.setattr(banc.rd.os, 'replace', bloque)
    banc.sommeils.clear()
    banc.notion.pages = pages_numerotees(12)
    assert banc.lancer('sync') == 2
    assert len(essais) == 20 and banc.sommeils == [0.25] * 19
    _intact(banc, avant)
    assert "L'index est ouvert par un autre programme" in _sorties(capsys)

    def deux_echecs(src, dst):
        essais.append(src)
        if len(essais) <= 22:
            raise PermissionError(13, 'Accès refusé')
        vrai(src, dst)
    monkeypatch.setattr(banc.rd.os, 'replace', deux_echecs)
    assert banc.lancer('sync') == 0
    assert len(essais) == 23
    assert lignes(banc.rd, 'SELECT count(*) FROM fiches')[0][0] == 12


def test_baisse_importante_refusee_puis_acceptee(banc, capsys):
    toutes = pages_numerotees(100)
    banc.notion.pages = toutes
    assert banc.lancer('sync') == 0
    avant = empreinte(banc.index)
    banc.notion.pages = toutes[:50]
    capsys.readouterr()
    assert banc.lancer('sync') == 2
    sortie = _sorties(capsys)
    assert "50 fiches de l'index précédent sont absentes" in sortie and '--accepter-baisse' in sortie
    assert 'depot-50' in sortie
    _intact(banc, avant)
    assert banc.lancer('sync', '--accepter-baisse') == 0
    assert lignes(banc.rd, 'SELECT count(*) FROM fiches')[0][0] == 50
    banc.notion.pages = toutes
    assert banc.lancer('sync') == 0
    capsys.readouterr()
    banc.notion.pages = toutes[:40] + toutes[42:]
    assert banc.lancer('sync') == 0
    sortie = _sorties(capsys)
    assert '+0 fiche, -2 depuis la synchronisation' in sortie
    assert 'Disparues   : depot-40, depot-41' in sortie


def test_base_vide(banc, capsys):
    banc.notion.pages = []
    assert banc.lancer('sync') == 0
    assert 'base vide' in _sorties(capsys)
    banc.notion.pages = pages_numerotees(3)
    assert banc.lancer('sync') == 0
    avant = empreinte(banc.index)
    banc.notion.pages = []
    assert banc.lancer('sync') == 2
    _intact(banc, avant)


def test_autre_base_refusee_sans_option(banc, monkeypatch, capsys):
    _premiere_sync(banc, 5)
    autre = 'abcdef0123456789abcdef0123456789'
    monkeypatch.setattr(banc.gn, 'DATABASE_ID', autre)
    banc.notion.base_id = autre
    banc.notion.base = schema(base_id=autre)
    banc.notion.pages = [page(f'autre-{i}', f'https://github.com/x/autre-{i}', base_id=autre) for i in range(5)]
    assert banc.lancer('sync') == 2
    assert f"l'index précédent venait d'une autre base ({BASE_ID[:8]}…)" in _sorties(capsys).replace('L\'', 'l\'')
    assert banc.lancer('sync', '--accepter-baisse') == 0
    assert lignes(banc.rd, "SELECT valeur FROM meta WHERE cle = 'database_id'")[0][0] == autre


def test_controles_construction(banc, monkeypatch, capsys):
    avant = _premiere_sync(banc, 10)
    integrite = banc.rd._integrite
    monkeypatch.setattr(banc.rd, '_integrite', lambda con: 'corruption simulée')
    banc.notion.pages = pages_numerotees(11)
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    assert "contrôle d'intégrité SQLite" in _sorties(capsys)
    monkeypatch.setattr(banc.rd, '_integrite', integrite)

    def disque_plein(con, rowid, fiche, principale):
        raise sqlite3.OperationalError('database or disk is full')
    monkeypatch.setattr(banc.rd, '_inserer_fiche', disque_plein)
    assert banc.lancer('sync') == 2
    _intact(banc, avant)
    assert "Construction de l'index impossible (OperationalError)" in _sorties(capsys)


def test_index_supprime_puis_reconstruit_identique(banc, capsys):
    banc.notion.pages = pages_numerotees(30)
    assert banc.lancer('sync') == 0
    premier = contenu_index(banc.rd)
    shutil.rmtree(banc.rd.dossier_index())
    capsys.readouterr()
    assert banc.lancer('etat') == 1
    assert "Index absent : lancez d'abord python redecouverte.py sync" in _sorties(capsys)
    assert banc.lancer('cherche', 'pdf') == 1
    assert not banc.rd.dossier_index().exists()            # etat et cherche ne créent rien
    assert banc.lancer('sync') == 0
    assert contenu_index(banc.rd) == premier


def test_format_index_different(banc, capsys):
    _premiere_sync(banc, 5)
    con = sqlite3.connect(str(banc.index))
    con.execute('PRAGMA user_version = 0')
    con.commit()
    con.close()
    capsys.readouterr()
    assert banc.lancer('etat') == 1
    assert 'Index créé par une autre version du moteur' in _sorties(capsys)
    assert banc.lancer('cherche', 'pdf') == 1
    assert banc.lancer('sync') == 0
    assert "index précédent d'un autre format : remplacé après comparaison des fiches" in _sorties(capsys)
    assert banc.lancer('etat') == 0
    assert ("Remarque    : index précédent d'un autre format : remplacé après comparaison des fiches (dernière "
            "synchronisation)") in _sorties(capsys)


def test_sync_idempotente(banc):
    banc.notion.pages = pages_numerotees(120)
    assert banc.lancer('sync') == 0
    premier = contenu_index(banc.rd)
    assert banc.lancer('sync') == 0
    assert contenu_index(banc.rd) == premier


def test_capture_puis_depuis_identique_sans_reseau(banc, monkeypatch):
    bases = charger_bases()
    _brancher_base(banc, monkeypatch, 'A')
    assert banc.lancer('sync', '--capture', 'cap.json') == 0
    lu = contenu_index(banc.rd)
    assert (Path(banc.gn.BASE_DIR) / 'exports' / 'cap.json').is_file()
    shutil.rmtree(banc.rd.dossier_index())
    banc.notion.journal.clear()
    monkeypatch.setattr(banc.gn, 'NOTION_TOKEN', '')       # ni jeton ni DATABASE_ID exigés
    monkeypatch.setattr(banc.gn, 'DATABASE_ID', '')
    assert banc.lancer('sync', '--depuis', 'cap.json') == 0
    assert banc.notion.journal == []
    rejoue = contenu_index(banc.rd)
    assert rejoue['meta'].pop('source') == 'capture:cap.json' and lu['meta'].pop('source') == 'notion'
    assert rejoue == lu
    assert rejoue['meta']['database_id'] == bases['A']['id'].replace('-', '')


@pytest.mark.parametrize('contenu', [None, '{pas du json', json.dumps({'format': 'autre/1', 'pages': []}),
                                     json.dumps({'format': 'gitnotate-capture/1', 'database_id': BASE_ID,
                                                 'schema': SCHEMA_GITNOTATE, 'pages': [{'page_id': 3}]})])
def test_depuis_fichier_invalide(banc, tmp_path, capsys, contenu):
    chemin = tmp_path / 'entree' / 'capture.json'
    if contenu is not None:
        chemin.parent.mkdir()
        chemin.write_text(contenu, encoding='utf-8')
    assert banc.lancer('sync', '--depuis', str(chemin)) == 1
    assert 'Capture' in _sorties(capsys)
    assert not banc.index.exists()


def test_capture_et_depuis_exclusifs(banc, capsys):
    assert banc.lancer('sync', '--capture', '--depuis', 'x.json') == 1
    assert 'incompatibles' in _sorties(capsys)
    assert banc.notion.journal == []


def test_chemin_avec_espaces_et_accents(load_gn, monkeypatch, tmp_path):
    dossier = tmp_path / 'Prof Génie' / 'données'
    banc = preparer(load_gn, monkeypatch, GITNOTATE_DATA_DIR=str(dossier))
    banc.notion.pages = pages_numerotees(4)
    assert banc.lancer('sync') == 0
    assert banc.index == dossier / '.gitnotate_index' / 'redecouverte.sqlite'
    assert banc.lancer('etat') == 0
    assert banc.lancer('sync') == 0


def test_cherche_lecture_seule_et_connexion_fermee(banc, tmp_path):
    _premiere_sync(banc, 20)
    avant = empreinte(banc.index)
    for _ in range(10):
        assert banc.lancer('etat', '--anomalies', '--doublons') == 0
    assert empreinte(banc.index) == avant
    con = banc.rd.ouvrir_index_lecture()
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("INSERT INTO meta (cle, valeur) VALUES ('x', 'y')")
    finally:
        con.close()
    copie = tmp_path / 'copie.sqlite'
    shutil.copyfile(banc.index, copie)
    assert banc.lancer('etat') == 0
    os.replace(copie, banc.index)                           # aucune connexion laissée ouverte
    assert empreinte(banc.index) == avant


def test_fts5_absent(banc, monkeypatch, capsys):
    assert banc.rd.verifier_fts5() == ''
    version = banc.rd.sqlite3.sqlite_version_info
    monkeypatch.setattr(banc.rd.sqlite3, 'sqlite_version_info', (3, 26, 0))
    assert 'module FTS5' in banc.rd.verifier_fts5()
    monkeypatch.setattr(banc.rd.sqlite3, 'sqlite_version_info', version)
    message = banc.rd._MESSAGE_FTS5.format(version='3.22.0')
    monkeypatch.setattr(banc.rd, 'verifier_fts5', lambda: message)
    banc.notion.pages = pages_numerotees(3)
    for commande in ('sync', 'cherche', 'etat'):
        assert banc.lancer(commande) == 1
    assert banc.notion.journal == []
    assert 'Aucune donnée n\'a été lue ni modifiée' in _sorties(capsys)


def test_bilan_sync_affiche(banc, monkeypatch, capsys):
    _brancher_base(banc, monkeypatch, 'A')
    assert banc.lancer('sync') == 0
    sortie = _sorties(capsys)
    assert "Synchronisation de l'index de redécouverte" in sortie
    assert '« Ressources GitHub » 5da35c51…' in sortie and '(NOTION_TOKEN)' in sortie
    assert 'Conseil     : un jeton d\'intégration limité à « Read content » (NOTION_READONLY_TOKEN)' in sortie
    assert '1 requête, 54 fiches (1 à la corbeille ignorée)' in sortie
    assert 'Versions    : v7.3+ ×12 · v7.2 ×5 · v7.0/v7.1 ×20 · ancienne ×15 · manuelle ×2' in sortie
    assert 'personnelles indexées : Notes ; ignorées : Favori (checkbox), Projet lié (relation)' in sortie
    assert 'Anomalies   : 1 (etat --anomalies)' in sortie
    assert '51 distincts ; 2 dépôts sur plusieurs fiches (etat --doublons) ; 1 fiche sans dépôt GitHub' in sortie
    assert 'fiches hors corbeille et hors pages archivées' in sortie
    assert str(banc.index) in sortie


def test_alerte_runs_gitnotate_posterieurs(banc, capsys):
    _premiere_sync(banc, 3)
    fin = lignes(banc.rd, "SELECT valeur FROM meta WHERE cle = 'sync_fin_locale'")[0][0]
    avant = (datetime.strptime(fin, '%Y-%m-%d %H:%M:%S') - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    apres = (datetime.strptime(fin, '%Y-%m-%d %H:%M:%S') + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    stats = Path(banc.gn.STATS_FILE)
    stats.write_text(json.dumps([
        {'timestamp': avant, 'success_count': 5, 'dry_run': False},
        {'timestamp': apres, 'success_count': 7, 'dry_run': True},
        {'timestamp': apres, 'success_count': 12, 'dry_run': False},
    ]), encoding='utf-8')
    capsys.readouterr()
    assert banc.lancer('etat') == 0
    assert f"gitnotate.py a créé 12 fiches le {apres[:16]}, après cette synchronisation" in _sorties(capsys)
    assert banc.rd.alerte_runs_gitnotate(apres) == ''
    stats.write_text('{illisible', encoding='utf-8')
    assert banc.lancer('etat') == 0
    assert 'gitnotate.py a créé' not in _sorties(capsys)
    stats.unlink()
    assert banc.rd.alerte_runs_gitnotate(fin) == ''


def test_schema_du_corpus_lu_sans_anomalie_de_schema(banc, monkeypatch):
    base = _brancher_base(banc, monkeypatch, 'C')
    assert banc.lancer('sync') == 0
    assert dict(lignes(banc.rd, 'SELECT cle, valeur FROM meta'))['colonnes_json'] == json.dumps(
        schema_base(base), ensure_ascii=False)


def test_age_de_l_index_signale(banc, capsys):
    _premiere_sync(banc, 3)
    con = sqlite3.connect(str(banc.index))
    con.execute("UPDATE meta SET valeur = '2000-01-01T00:00:00+00:00' WHERE cle = 'sync_fin_utc'")
    con.commit()
    con.close()
    capsys.readouterr()
    assert banc.lancer('etat') == 0
    sortie = _sorties(capsys)
    assert 'Attention   : Index synchronisé il y a' in sortie and 'relancez sync' in sortie


def test_interruption_pendant_la_capture(banc, monkeypatch, capsys):
    _premiere_sync(banc, 3)
    banc.notion.pages = pages_numerotees(5)

    def interrompt(*args):
        raise KeyboardInterrupt
    monkeypatch.setattr(banc.rd, 'ecrire_capture', interrompt)
    assert banc.lancer('sync', '--capture') == 130
    assert 'Interruption : index remplacé, capture non écrite.' in _sorties(capsys)
    assert lignes(banc.rd, 'SELECT count(*) FROM fiches')[0][0] == 5
    banc.rd.liberer_verrou(banc.rd.prendre_verrou())


def test_capture_dans_un_dossier_absent(banc, tmp_path, capsys):
    banc.notion.pages = pages_numerotees(3)
    assert banc.lancer('sync', '--capture', str(tmp_path / 'absent' / 'cap.json')) == 2
    assert 'Index remplacé, mais capture non écrite (FileNotFoundError)' in _sorties(capsys)
    assert lignes(banc.rd, 'SELECT count(*) FROM fiches')[0][0] == 3


def test_ligne_de_commande(banc, capsys):
    assert banc.lancer('pdf') == 1
    assert 'Commande inconnue « pdf ». Pour chercher : python redecouverte.py cherche "pdf"' in _sorties(capsys)
    assert banc.lancer() == 1
    assert 'Indiquez une commande' in _sorties(capsys)
    assert banc.lancer('--version') == 0
    assert f"redecouverte {banc.rd.__version__} (gitnotate {banc.gn.__version__})" in _sorties(capsys)
    assert banc.lancer('sync', '--option-inconnue') == 1
    assert banc.lancer('etat', '--format', 'xml') == 1
    assert banc.lancer('cherche', 'extraire des données de PDF') == 1      # aucun index : rien n'est créé
    assert "Index absent : lancez d'abord python redecouverte.py sync" in _sorties(capsys)
    assert banc.notion.journal == []
