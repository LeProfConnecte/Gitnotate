"""Revue du lot 4 : tests de non-régression des constats corrigés (moteur de redécouverte et gitnotate.py).

Constats confirmés : P1 (citation répétée quand deux surlignages se chevauchent), P2 (« forte » sans l'objet du
besoin, « Ne couvre pas » muet), P3 (« Établi » sur un champ modifié dans Notion), P4 (texte modifié envoyé au
LLM), SEC-R1 (marqueurs de surlignage dans une fiche), SEC-R2 (séquences d'échappement du terminal), PA-1
(README illisible pris pour un README absent), M9 (index sur un partage réseau), M11 (filtres : message
faux), M12 (légende Markdown fausse). Mineurs : P5, P7, P8, SEC-R3, SEC-R4, PA-2, PA-3, PA-4, M1, M2, M3, M4,
M5, M6, M7, M10, M14, M15.

Hors ligne : faux Notion et fausses API (tests/redecouverte_outils.py, fixtures locales du lot 3), garde réseau
de conftest.py active, aucun .env lu.
"""
import importlib.util
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
import requests

from redecouverte_outils import (
    BASE_ID, FIXTURES, JETON_TEST, SCHEMA_GITNOTATE, erreur_notion, index_du_corpus, make_response, p_nombre,
    p_texte, page, pages_du_corpus, preparer, rt, schema,
)
from test_gitnotate_lot2 import BASE_ENV2, _wire, pages_posted
from test_lot3 import ANSWER, FRESH, README_DOCLING, TEST_PROFILE, V71_COLUMNS, RecordingAPI, notion_db, readme_route

ROOT = Path(__file__).resolve().parent.parent
REQUETES = json.loads((FIXTURES / 'requetes.json').read_text(encoding='utf-8'))['requetes']
PAR_ID = {q['id']: q for q in REQUETES}
JUSTIF = "[LLM mistral-small-2603 · profil 2026-10-11/8c41d2] U1·P3·T2·I2·C2·M2·L2 = 9 — "
LLM_LOCAL = "un LLM local"
R09 = "faire tourner un LLM en local sans GPU"
R10 = "gérer mes commits git depuis le terminal"
R05 = "scrape websites to feed an LLM pipeline"
EMPTY_REPO = dict(FRESH, description=None, topics=[])
NO_INFO = "[NON NOTÉ] Ni description, ni topics, ni README exploitable : Pertinence laissée vide."


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


@pytest.fixture
def corpus(banc):
    index_du_corpus(banc.rd)
    return banc


def _sorties(capsys):
    sortie = capsys.readouterr()
    return ' '.join((sortie.out + sortie.err).split())


def _chercher(rd, texte, filtres=None, limite=50, tout=False):
    con, meta = rd.ouvrir_index_valide()
    try:
        reponse = rd.rechercher(con, rd.analyser_requete(texte), filtres or {}, limite, tout, meta)
        rd.expliquer(con, reponse)
    finally:
        con.close()
    return reponse


def _resultat(reponse, cle):
    return next(r for r in reponse.resultats + reponse.faibles + reponse.sans_depot if r.cle == cle)


def _fiche(nom, description, **props):
    proprietes = {'Description': p_texte(description), "Cas d'usage": p_texte('• Usage de démonstration'),
                  'Justification': p_texte(JUSTIF + 'Avis de test.')}
    proprietes.update(props)
    return page(nom, f'https://github.com/test/{nom}', props=proprietes)


def _synchroniser(banc, pages):
    banc.notion.pages = pages
    assert banc.lancer('sync', '--accepter-baisse') == 0


class FauxLLM:
    """Fournisseur LLM simulé (aucun réseau) : une réponse programmée par fournisseur."""

    def __init__(self, reponses):
        self.reponses = reponses
        self.appels = []

    def post(self, url, headers=None, json=None, timeout=None):
        fournisseur = 'mistral' if 'mistral' in url else 'openrouter'
        self.appels.append((fournisseur, json))
        texte, modele = self.reponses[fournisseur]
        return make_response(200, {'model': modele, 'choices': [{'finish_reason': 'stop',
                                                                  'message': {'content': texte}}]})

    def get(self, *args, **kwargs):
        raise AssertionError('GET inattendu')

# =============================================================================
# P1 — une citation « mot pour mot » ne répète jamais un mot (surlignages fusionnés)
# =============================================================================
def _citation_md_sans_marques(citation):
    """Markdown → texte : échappements retirés, « ** » (marques) supprimées."""
    return ''.join(m.group(1) or m.group(2) or '' for m in re.finditer(r'\\(.)|\*\*|(.)', citation, re.S))


def _sans_bornes(citation, e):
    citation = citation[1:] if e.get('avant') else citation
    return citation[:-1] if e.get('apres') else citation


def test_p1_fusion_des_intervalles(banc):
    rd = banc.rd
    assert rd._fusionner([(37, 51), (14, 33), (48, 51), (75, 78), (78, 80)]) == [[14, 33], [37, 51], [75, 80]]
    e = rd._extrait("Crawl4AI : robot d'exploration et extracteur web open source adapté aux LLM.",
                    [(11, 30), (34, 48), (45, 48)], champ='Description', fiabilite='llm')
    assert e['surlignes'] == [[11, 30], [34, 48]]
    assert rd._citation(e) == "Crawl4AI : *robot d'exploration* et *extracteur web* open source adapté aux LLM."


@pytest.mark.parametrize('requete', [q['requete'] for q in REQUETES if not q['options']]
                         + [R05, "scrape websites", "crawler de sites web"])
def test_p1_citations_identiques_au_texte_stocke(corpus, requete):
    rd = corpus.rd
    reponse = _chercher(rd, requete, limite=10)
    vus = 0
    for r in reponse.affiches:
        for e in r.extraits + r.etabli:
            s = e['surlignes']
            assert all(a < b for a, b in s) and all(s[i][1] < s[i + 1][0] for i in range(len(s) - 1)), s
            assert _sans_bornes(rd._citation(e, '\x00'), e).replace('\x00', '') == e['texte']
            assert _citation_md_sans_marques(_sans_bornes(rd._citation(e, '**', rd._md), e)) == e['texte']
            vus += 1
    assert vus or not reponse.affiches


def test_p1_crawl4ai_sans_mot_double(corpus):
    reponse = _chercher(corpus.rd, R05, limite=10)
    texte, markdown = corpus.rd.en_texte(reponse), corpus.rd.en_markdown(reponse)
    assert '*extracteur web*' in texte and 'web**web' not in texte and 'web*web' not in texte
    assert '****' not in markdown

# =============================================================================
# P2 — « forte » exige l'objet du besoin ; « Ne couvre pas » liste toutes les notions absentes
# =============================================================================
@pytest.mark.parametrize('requete', [LLM_LOCAL, R09, "modèle de langage hors ligne", PAR_ID['H04']['requete']])
def test_p2_synthese_vocale_jamais_forte_pour_un_llm_local(corpus, requete):
    reponse = _chercher(corpus.rd, requete)
    piper = _resultat(reponse, 'ohf-voice/piper1-gpl')
    assert piper.niveau == 'partielle'
    assert any(n.endswith('(notion secondaire)') for n in piper.ne_couvre_pas), piper.ne_couvre_pas
    llama = _resultat(reponse, 'ggml-org/llama.cpp')
    assert llama.niveau == 'forte'
    if requete != LLM_LOCAL:            # « un LLM local » : gpt-researcher (« LLM », « locales ») reste fort
        assert reponse.resultats[0].cle == 'ggml-org/llama.cpp'


def test_p2_contexte_compte_quand_une_seule_notion_est_essentielle(corpus):
    reponse = _chercher(corpus.rd, R10)
    assert reponse.resultats[0].cle == 'jesseduffield/lazygit' and reponse.resultats[0].niveau == 'forte'
    assert [r.cle for r in reponse.resultats if r.niveau == 'forte'] == ['jesseduffield/lazygit']
    llama = _resultat(reponse, 'ggml-org/llama.cpp')
    assert llama.niveau != 'forte'
    assert {'commits [contexte]', 'git [contexte]'} <= set(llama.ne_couvre_pas)


def test_p2_possessif_anglais_ne_rend_plus_python_seul_fort(corpus):
    reponse = _chercher(corpus.rd, "Which saved repos help me write my own MCP server in Python?")
    fortes = [r.cle for r in reponse.resultats if r.niveau == 'forte']
    assert fortes[0] == 'jlowin/fastmcp' and 'thealgorithms/python' not in fortes and len(fortes) <= 5


def test_p2_plusieurs_notions_essentielles_regle_inchangee(corpus):
    rd = corpus.rd
    actifs = [c for c in rd.analyser_requete(PAR_ID['Q09']['requete']).concepts]
    for c in actifs:
        c.retire = False
    essentiels, couverts, exiges = rd.ensembles_niveau(actifs)
    assert len(essentiels) > 1 and couverts == essentiels and exiges == []


def test_p2_sorties_texte_markdown_json(corpus, capsys):
    assert corpus.lancer('cherche', LLM_LOCAL) == 0
    assert 'Ne couvre pas : LLM (notion secondaire)' in _sorties(capsys)
    assert corpus.lancer('cherche', LLM_LOCAL, '--format', 'markdown') == 0
    sortie = capsys.readouterr().out
    assert re.search(r'\| \d+ \| \[piper1-gpl\]\([^)]*\) \| partielle \|', sortie)
    assert '**Ne couvre pas** : LLM (notion secondaire)' in sortie
    assert corpus.lancer('cherche', LLM_LOCAL, '--format', 'json') == 0
    donnees = json.loads(capsys.readouterr().out)
    piper = next(r for r in donnees['resultats'] if r['depot'] == 'ohf-voice/piper1-gpl')
    assert piper['niveau'] == 'partielle' and piper['ne_couvre_pas'] == ['LLM (notion secondaire)']


def test_p2_reference_jamais_dans_ne_couvre_pas(corpus):
    reponse = _chercher(corpus.rd, PAR_ID['Q11']['requete'])
    assert any(c.role == 'reference' for c in reponse.requete.concepts)
    assert not any('[référence]' in n for r in reponse.affiches for n in r.ne_couvre_pas)

# =============================================================================
# P3 — un champ README modifié dans Notion n'est jamais « Établi » ni « mot pour mot »
# =============================================================================
def _fiches_modifiees():
    return [
        _fiche('outilx', 'Moteur OCR en Python.', Installation=p_texte(
            'pip install outilx', rt('\nTesté sur le PC de la salle B12 : OCR sans GPU OK', bold=True))),
        _fiche('outilw', 'Autre moteur OCR.', Installation=p_texte('pip install outilw  # OCR de la salle B12')),
        _fiche('outily', 'Logiciel de dessin vectoriel.', Installation=p_texte(
            rt('Ne fonctionne pas sous Windows 7', code=True), '\npip install outily')),
        _fiche('outilz', 'Bibliothèque de géodésie.',
               Exemple=p_texte('outilz run', rt(' voir aussi le tableur de topographie', lien='https://exemple.org')),
               **{'Prérequis': p_texte('Python 3.10 et un tableur de topographie', rt(' @date', mention=True))}),
    ]


def test_p3_zone_modifiee_absente_d_etabli(banc, capsys):
    _synchroniser(banc, _fiches_modifiees())
    rd = banc.rd
    reponse = _chercher(rd, "OCR sur le PC de la salle B12")
    x, w = _resultat(reponse, 'test/outilx'), _resultat(reponse, 'test/outilw')
    assert not any(e['champ'] == 'Installation' for e in x.etabli)
    assert any(e['champ'] == 'Installation' and e['modifie'] is False for e in w.etabli)       # témoin
    extrait = next(e for e in x.extraits if e['champ'] == 'Installation')
    assert extrait['modifie'] is True and rd._source(extrait).startswith(
        'Installation [README, modifié dans Notion — à vérifier')
    assert any(a['code'] == 'modifie' and 'Installation' in a['champs'] for a in x.a_verifier)
    capsys.readouterr()
    assert banc.lancer('cherche', "OCR sur le PC de la salle B12", '--format', 'json') == 0
    donnees = json.loads(capsys.readouterr().out)
    resultat = next(r for r in donnees['resultats'] if r['depot'] == 'test/outilx')
    assert all(e['champ'] != 'Installation' for e in resultat['etabli'])
    assert any(e['champ'] == 'Installation' and e['modifie'] for e in resultat['extraits'])


def test_p3_repli_sur_une_installation_modifiee(banc, capsys):
    _synchroniser(banc, _fiches_modifiees())
    reponse = _chercher(banc.rd, "dessin vectoriel")
    y = _resultat(reponse, 'test/outily')
    assert y.etabli == [] and y.etabli_note == "Installation modifiée dans Notion : voir À vérifier"
    assert banc.lancer('cherche', 'dessin vectoriel') == 0
    sortie = _sorties(capsys)
    assert ('Établi : rien de vérifié mot pour mot dans le README (Installation modifiée dans Notion : voir À '
            'vérifier)') in sortie
    assert 'Ne fonctionne pas sous Windows 7' not in sortie.split('Établi')[1].split('À vérifier')[0]


def test_p3_exemple_et_prerequis_modifies(banc, capsys):
    _synchroniser(banc, _fiches_modifiees())
    z = _resultat(_chercher(banc.rd, "tableur de topographie"), 'test/outilz')
    assert not any(e['champ'] in ('Exemple', 'Prérequis') for e in z.etabli)
    for e in z.extraits:
        if e['champ'] in ('Exemple', 'Prérequis'):
            assert e['modifie'] and 'mot pour mot' not in banc.rd._source(e)
    assert banc.lancer('cherche', 'tableur de topographie') == 0
    sortie = _sorties(capsys)
    assert 'Exemple [README, mot pour mot' not in sortie and 'Prérequis [README, mot pour mot' not in sortie
    assert 'Exemple [README, modifié dans Notion — à vérifier' in sortie

# =============================================================================
# P4 — un champ modifié dans Notion n'est jamais envoyé au LLM
# =============================================================================
def test_p4_texte_ajoute_dans_notion_non_envoye(load_gn, monkeypatch, capsys):
    banc = preparer(load_gn, monkeypatch, MISTRAL_API_KEY='cle-mistral-de-test', OPENROUTER_API_KEY='')
    _synchroniser(banc, [
        _fiche('outilx', 'Moteur OCR en Python.', **{
            'Description': p_texte('Moteur OCR en Python.', rt(' Installé chez M. Dupont, salle B12.', bold=True)),
            "Cas d'usage": p_texte('• Lire des factures scannées', rt('\n• Utilisé pour le TP du lycée'))}),
        _fiche('outilv', 'Moteur OCR pour les plans.')])
    capsys.readouterr()
    assert banc.lancer('cherche', 'moteur OCR', '--llm', '--llm-apercu') == 0
    sortie = capsys.readouterr().out
    message = sortie.split('--- Message utilisateur ---')[1]
    assert 'Dupont' not in message and 'lycée' not in message and 'factures' not in message
    assert 'Description : Moteur OCR pour les plans.' in message                   # témoin non modifié
    assert 'Dépôt : test/outilx' in message                                      # le dépôt reste évalué

# =============================================================================
# SEC-R1 — marqueurs de surlignage (U+E000, U+E001) dans le texte d'une fiche
# =============================================================================
@pytest.mark.parametrize('champ', ['Description', "Cas d'usage", 'Exemple'])
def test_sec_r1_marqueur_seul_ne_fait_pas_planter(banc, capsys, champ):
    _synchroniser(banc, [_fiche('icone', 'Outil de thème.', **{champ: p_texte('Icône \ue000 du thème'),
                                                               'Installation': p_texte('Lire un pdf')})])
    assert banc.lancer('cherche', 'pdf') == 0
    sortie = _sorties(capsys)
    assert 'Erreur inattendue' not in sortie and 'icone' in sortie and '\ue000' not in sortie


def test_sec_r1_paire_de_marqueurs_sans_fausse_preuve(banc, capsys):
    _synchroniser(banc, [
        _fiche('temoin', 'Recettes de gateaux au chocolat.', Installation=p_texte('Lire un pdf')),
        _fiche('hostile', 'Recettes de \ue000gateaux\ue001 au chocolat.', Installation=p_texte('Lire un pdf'))])
    reponse = _chercher(banc.rd, 'pdf')
    temoin, hostile = _resultat(reponse, 'test/temoin'), _resultat(reponse, 'test/hostile')
    assert {p.rowid: p.colonnes for p in hostile.preuves['pdf'].values()}.popitem()[1] == ['installation']
    assert round(hostile.score, 6) == round(temoin.score, 6)
    assert not any(e['champ'] == 'Description' for e in hostile.extraits)
    assert banc.lancer('cherche', 'pdf') == 0
    assert 'gateaux' not in _sorties(capsys).split('hostile')[1].split('Établi')[0]


def test_sec_r1_index_construit_avant_le_correctif(banc, monkeypatch, capsys):
    """Défense en profondeur : un index qui contient encore un marqueur ne fait pas planter « cherche »."""
    rd = banc.rd
    monkeypatch.setattr(rd, 'normaliser', lambda texte: unicodedata.normalize('NFC', texte).rstrip())
    _synchroniser(banc, [_fiche('icone', 'Icône \ue000 du thème', Installation=p_texte('Lire un pdf'))])
    monkeypatch.undo()
    monkeypatch.setattr(banc.gn, 'get_session', lambda: banc.notion)
    assert '\ue000' in banc.rd.lire_fiches(rd.ouvrir_index_lecture())[0]['champs']['Description']['texte']
    assert banc.lancer('cherche', 'pdf') == 0
    assert 'Erreur inattendue' not in _sorties(capsys)


def test_sec_r1_normaliser_retire_les_marqueurs(banc):
    rd = banc.rd
    assert rd.normaliser('a\ue000b\ue001c') == 'a b c'
    assert rd.MARQUE_DEBUT not in rd.normaliser('x' + rd.MARQUE_DEBUT)

# =============================================================================
# SEC-R2 — séquences d'échappement du terminal : jamais affichées
# =============================================================================
ESC_INSTALL = 'pip install pdfoutil\x1b]52;c;cm0gLXJmIH4K\x07\x1b[2K\x1b[1A\rfaux'
ESC_DESCRIPTION = 'Extraire des tableaux de PDF \x1b[2K\x1b[1A\x1b]0;titre\x07faux texte \u202eabc'


def _sans_controle(texte):
    return not any(c in texte for c in ('\x1b', '\x07', '\r', '\u202e', '\x9b'))


def test_sec_r2_normaliser_neutralise_les_controles(banc):
    rd = banc.rd
    assert rd.normaliser('a\x1b[2Kb\x07c\rd\te\nf\x9bg\u202eh') == 'a [2Kb cd\te\nf gh'
    assert rd.normaliser(rd.normaliser(ESC_INSTALL)) == rd.normaliser(ESC_INSTALL)       # idempotente


@pytest.mark.parametrize('options', [(), ('--details',), ('--format', 'markdown')])
def test_sec_r2_cherche_n_affiche_aucune_sequence(banc, capsys, options):
    _synchroniser(banc, [_fiche('pdfoutil', ESC_DESCRIPTION, Installation=p_texte(ESC_INSTALL))])
    capsys.readouterr()
    assert banc.lancer('cherche', 'tableaux pdf', *options) == 0
    sortie = capsys.readouterr()
    assert _sans_controle(sortie.out + sortie.err)
    assert 'pip install pdfoutil' in sortie.out and 'faux texte' in sortie.out


def test_sec_r2_capture_ancienne_normalisee_au_rejeu(banc, tmp_path):
    rd = banc.rd
    plate = rd.aplatir_page(_fiche('pdfoutil', 'Outil PDF.'))
    donnees = rd.dataclasses.asdict(plate)
    donnees['colonnes']['Installation']['texte'] = ESC_INSTALL            # capture d'une version antérieure
    capture = tmp_path / 'ancienne.json'
    capture.write_text(json.dumps({'format': rd.FORMAT_CAPTURE, 'database_id': BASE_ID, 'base_titre': 'Base',
                                   'lu_le': '2026-10-11T12:00:00+00:00', 'schema': SCHEMA_GITNOTATE,
                                   'nb_requetes': 1, 'ignorees': {}, 'pages': [donnees]}), encoding='utf-8')
    plates, _ = rd.charger_capture(str(capture))
    assert _sans_controle(plates[0].colonnes['Installation'].texte)


def test_sec_r2_raison_et_modele_du_llm_filtres(load_gn, monkeypatch, capsys):
    banc = preparer(load_gn, monkeypatch, MISTRAL_API_KEY='cle-mistral-de-test', OPENROUTER_API_KEY='')
    index_du_corpus(banc.rd)
    raison = 'bibliothèque démonstration \u001b]0;pwn\u0007\u001b[2K'
    avis = json.dumps({'avis': [{'id': f'R{i}', 'adequation': 2, 'raison': raison} for i in range(1, 4)]})
    faux = FauxLLM({'mistral': (avis, 'modele\u001b[31m')})
    monkeypatch.setattr(banc.gn, 'get_session', lambda: faux)
    assert banc.lancer('cherche', PAR_ID['Q03']['requete'], '-n', '3', '--llm', '--oui') == 0
    sortie = capsys.readouterr()
    assert faux.appels and _sans_controle(sortie.out + sortie.err)
    assert 'modèle servi modele [31m' in sortie.out

# =============================================================================
# PA-1 — README illisible (5xx, timeout, quota) : jamais « ni README exploitable »
# =============================================================================
@pytest.fixture
def world3(load_gn, monkeypatch):
    """Fausse API à tous verbes (lot 3), module rechargé, profil de test, toute requête hors fausse session
    refusée."""
    def _escaped(self, method, url, *a, **k):
        raise RuntimeError(f"requête hors fausse session : {method} {url}")
    monkeypatch.setattr(requests.Session, 'request', _escaped)

    def _make(readme=README_DOCLING, repo=None, **env):
        merged = dict(BASE_ENV2, OPENROUTER_API_KEY=None)
        merged.update(env)
        gn = load_gn(**merged)
        gn.PROFILE_FILE.write_text(json.dumps(TEST_PROFILE, ensure_ascii=False), encoding='utf-8')
        api = RecordingAPI()
        api.escaped = []
        api.db = notion_db(V71_COLUMNS)
        api.mistral_content = json.dumps(ANSWER, ensure_ascii=False)
        api.repos['owner/repo'].update(repo or {})
        readme_route(api, readme)
        _wire(gn, monkeypatch, api)
        return gn, api
    return _make


def _justification(payload):
    return ''.join(s['text']['content'] for s in payload['properties']['Justification']['rich_text'])


def _readme_en_panne(api, panne):
    route = r'api\.github\.com/repos/owner/repo/readme$'
    if panne == 'timeout':
        def lever(url, corps):
            raise requests.exceptions.Timeout('délai')
        api.route('GET', route, lever)
    elif panne == '403':
        reset = str(int(datetime.now(timezone.utc).timestamp()) + 3600)
        api.route('GET', route, lambda u, p: make_response(
            403, {'message': 'API rate limit exceeded'},
            headers={'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': reset}))
    else:
        api.route('GET', route, lambda u, p: make_response(502, {'message': 'Bad Gateway'}))


def _cache(gn):
    try:
        return json.loads(gn.CACHE_FILE.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


@pytest.mark.parametrize('panne', ['502', 'timeout', '403'])
def test_pa1_readme_illisible_aucune_fiche_et_reprise(world3, capsys, panne):
    gn, api = world3(repo=EMPTY_REPO)
    _readme_en_panne(api, panne)
    assert gn.main([]) == gn.EXIT_INCOMPLETE
    assert pages_posted(api) == [] and api.llm_bodies('mistral') == []
    assert 'owner/repo' not in _cache(gn)
    assert gn.stats.errors == 1 and 'README illisible' in capsys.readouterr().err
    readme_route(api, "# repo\n\nConvertit des PDF en Markdown avec OCR.")      # run suivant : README lisible
    assert gn.main([]) == gn.EXIT_OK
    (fiche,) = pages_posted(api)
    assert _justification(fiche).startswith('[LLM ') and fiche['properties']['Pertinence']['number'] is not None


def test_pa1_readme_absent_404_reste_non_note(world3):
    gn, api = world3(repo=EMPTY_REPO, readme=None)
    assert gn.main([]) == gn.EXIT_OK
    (fiche,) = pages_posted(api)
    assert _justification(fiche) == NO_INFO and fiche['properties']['Pertinence'] == {'number': None}
    assert _cache(gn)['owner/repo']['readme_state'] == 'absent'


def test_pa1_depot_decrit_avec_readme_illisible_fiche_creee_sans_cache(world3):
    gn, api = world3(repo=FRESH)
    _readme_en_panne(api, '502')
    assert gn.main([]) == gn.EXIT_OK
    assert len(pages_posted(api)) == 1 and 'owner/repo' not in _cache(gn)


def test_pa1_cache_format_releve(load_gn):
    gn = load_gn()
    ancienne = {'cached_at': datetime.now(timezone.utc).timestamp(), 'cache_format': 4, 'readme': ''}
    assert gn.CACHE_FORMAT == 5 and gn._cache_entry_valid(ancienne) is False

# =============================================================================
# PA-2, PA-3, PA-4 — fiche non notée exacte, titre « owner/repo », version de profil avec crochets
# =============================================================================
def test_pa2_readme_non_transmis_dit_la_verite(world3, banc):
    gn, api = world3(repo=EMPTY_REPO, README_LLM_CHARS='0')
    assert gn.main([]) == gn.EXIT_OK
    (fiche,) = pages_posted(api)
    justification = _justification(fiche)
    assert justification == ("[NON NOTÉ] Ni description, ni topics ; README non transmis au LLM "
                             "(README_LLM_CHARS=0) : Pertinence laissée vide.")
    rd = banc.rd
    corps, reconnu = rd._corps_justification(justification)
    assert reconnu and rd.R74N.match(justification)
    assert rd._limite_non_notee({'champs': {'Justification': {'texte': corps}}}) == rd.LIMITE_NON_NOTEE_README
    assert rd._limite_non_notee({'champs': {'Justification': {'texte': rd._corps_justification(NO_INFO)[0]}}}) \
        == rd.LIMITE_NON_NOTEE


def test_pa3_readme_reduit_au_nom_complet_non_exploitable(world3):
    gn, api = world3(repo=EMPTY_REPO, readme='# owner/repo\n')
    assert gn.main([]) == gn.EXIT_OK
    (fiche,) = pages_posted(api)
    assert fiche['properties']['Pertinence'] == {'number': None} and api.llm_bodies('mistral') == []
    assert gn.readme_is_exploitable(gn.clean_readme('# owner/repo\nConvertit des PDF.\n'), 'owner/repo') is True


def test_pa4_version_de_profil_avec_crochets(banc):
    rd = banc.rd
    justification = ("[LLM mistral-small-2603 · profil v2 [octobre]/2a6f97] U3·P3·T1·I1·C2·M2·L2 = 9 — "
                     "Bibliothèque Python, OCR et tableaux PDF.")
    fiche = rd.construire_fiche(rd.aplatir_page(page('outil', props={'Justification': p_texte(justification)})),
                                rd.resoudre_colonnes(SCHEMA_GITNOTATE))
    p = fiche.provenance
    assert (p.famille, p.regle, p.methode, p.profil_version, p.profil_empreinte) == (
        'v7.3', 'R73', 'LLM', 'v2 [octobre]', '2a6f97')
    assert fiche.champs['Justification'].fiabilite == 'avis_llm'
    assert rd.contenu_fts(fiche)['notes'] == ''

# =============================================================================
# M9 — index sur un partage réseau : URI SQLite sans autorité
# =============================================================================
def test_m9_uri_sans_autorite(banc):
    rd = banc.rd
    unc = rd.uri_lecture(PureWindowsPath(r'\\serveur\partage\Gitnotate\.gitnotate_index\redecouverte.sqlite'))
    assert unc == 'file:////serveur/partage/Gitnotate/.gitnotate_index/redecouverte.sqlite?mode=ro'
    assert rd.uri_lecture(PureWindowsPath(r'C:\Users\é t\a#b?.sqlite')) == \
        'file:///C:/Users/%C3%A9%20t/a%23b%3F.sqlite?mode=ro'
    assert rd.uri_lecture(PurePosixPath('/tmp/a b/x.sqlite')) == 'file:///tmp/a%20b/x.sqlite?mode=ro'
    with pytest.raises(sqlite3.OperationalError) as erreur:
        sqlite3.connect(unc, uri=True)
    assert 'authority' not in str(erreur.value)


def test_m9_index_dans_un_dossier_au_nom_difficile(load_gn, monkeypatch, tmp_path, capsys):
    dossier = tmp_path / 'Données #1 ?'
    dossier.mkdir()
    banc = preparer(load_gn, monkeypatch, GITNOTATE_DATA_DIR=str(dossier))
    index_du_corpus(banc.rd)
    assert str(banc.index).startswith(str(dossier))
    assert banc.lancer('cherche', 'pdf') == 0 and banc.lancer('etat') == 0
    assert 'Index illisible' not in _sorties(capsys)

# =============================================================================
# M11, M12 — filtres sans résultat, légende Markdown
# =============================================================================
@pytest.mark.parametrize('filtre', [('--statut', 'Abandonné'), ('--licence', 'GPL')])
def test_m11_filtres_qui_ecartent_tout(corpus, capsys, filtre):
    assert corpus.lancer('cherche', 'extraire des données de PDF', *filtre) == 0
    sortie = _sorties(capsys)
    assert 'Aucune fiche ne contient ces concepts' not in sortie and 'Piste' not in sortie
    assert re.search(r'Aucun résultat ne passe les filtres : \d+ fiches ou dépôts correspondent au besoin mais sont '
                     r'écartés\.', sortie)
    assert re.search(r'\d+ fiches ou dépôts écartés par les filtres\.', sortie)
    assert corpus.lancer('cherche', 'extraire des données de PDF', *filtre, '--format', 'markdown') == 0
    assert 'Aucun résultat ne passe les filtres' in capsys.readouterr().out


def test_m11_sans_filtre_message_inchange(corpus, capsys):
    assert corpus.lancer('cherche', 'jeux vidéo cybersécurité') == 0
    assert 'Aucune fiche ne contient ces concepts' in _sorties(capsys)


def test_m12_legende_markdown_exacte(corpus, capsys):
    rd = corpus.rd
    assert corpus.lancer('cherche', PAR_ID['Q03']['requete'], '--format', 'markdown') == 0
    sortie = capsys.readouterr().out
    assert rd.LEGENDE_MARKDOWN in sortie and f"{round(rd.SEUIL_FORTE * 100)} %" in rd.LEGENDE_MARKDOWN
    assert 'toutes les notions importantes' not in sortie and 'concepts voisins) sont masquées' not in sortie
    assert "un concept voisin compte pour moitié" in sortie
    doc = (ROOT / 'docs' / 'REDECOUVERTE.md').read_text(encoding='utf-8')
    assert 'plus de 60 % du poids des notions essentielles' in doc

# =============================================================================
# Mineurs du moteur : P5, P7, P8, SEC-R3, SEC-R4, M2, M3, M4, M6, M7, M10
# =============================================================================
def test_p5_licence_non_renseignee_lue_sur_github(banc):
    banc.notion.base = schema(dict(SCHEMA_GITNOTATE, Licence='rich_text'))
    _synchroniser(banc, [_fiche('sanslicence', 'Outil PDF.', Licence=p_texte('Non renseignée')),
                         _fiche('incertaine', 'Outil PDF bis.', Licence=p_texte('Non vérifiée'))])
    reponse = _chercher(banc.rd, 'outil pdf')
    textes = {r.cle: next(a['texte'] for a in r.a_verifier if a['code'] == 'licence_inconnue') for r in reponse.affiches}
    assert textes['test/sanslicence'] == ("Licence « Non renseignée » : aucune licence déclarée sur GitHub "
                                          "(fiche v7.3+) ; vérifiez les droits de réutilisation")
    assert textes['test/incertaine'] == "Licence « Non vérifiée » : Gitnotate n'a pas pu l'identifier"


@pytest.mark.parametrize('description, contrainte', [
    ('Moteur OCR. GPU facultatif.', False), ('Moteur OCR. GPU optional.', False), ('Moteur OCR. GPU non requis.', False),
    ('Moteur OCR. Nécessite un GPU NVIDIA.', True)])
def test_p7_gpu_facultatif_n_est_pas_une_contrainte(banc, description, contrainte):
    _synchroniser(banc, [_fiche('ocr', description)])
    r = _resultat(_chercher(banc.rd, 'moteur ocr'), 'test/ocr')
    assert any(a['code'] == 'materiel' for a in r.a_verifier) is contrainte


def test_p8_feed_et_surveillance(corpus):
    rd = corpus.rd
    assert 'feed' not in rd.lexique.CONCEPTS['veille'][1] and 'rss feed' in rd.lexique.CONCEPTS['veille'][1]
    reponse = _chercher(rd, R05)
    assert reponse.resultats[0].cle == 'unclecode/crawl4ai' and reponse.resultats[0].niveau == 'forte'
    veille = _chercher(rd, "un outil pour la veille")
    assert 'evidentlyai/evidently' not in [r.cle for r in veille.resultats]
    concept = rd.analyser_requete("un outil pour la veille").concepts[0]
    assert '"surveillance"' not in concept.termes_voisins and '"surveiller"' in concept.termes_voisins


def test_sec_r3_jeton_coupe_par_une_page_de_debordement(banc, monkeypatch):
    """Masquage défaillant simulé : l'analyse des valeurs décodées refuse l'index, quelle que soit la place du
    jeton par rapport aux pages de débordement SQLite."""
    rd = banc.rd
    monkeypatch.setattr(rd, 'masquer', lambda texte, secrets=(): texte)
    meta = rd.MetaLecture(BASE_ID, 'Base', 'notion', dict(SCHEMA_GITNOTATE), 1, 1, {}, '2026-10-11T00:00:00+00:00')
    for longueur in range(4000, 4100, 4):
        notes = 'a' * 2430 + f" {JETON_TEST} " + 'y' * longueur
        plates = [rd.aplatir_page(page('fuite', 'https://github.com/o/fuite', props={'Notes': p_texte(notes)}))]
        with pytest.raises(rd.Arret) as erreur:
            rd.construire_et_remplacer(plates, meta, (JETON_TEST,), accepter_baisse=True)
        assert erreur.value.code == 2 and JETON_TEST not in erreur.value.message
    assert not rd.chemin_index().exists()


def test_sec_r4_ctrl_c_juste_apres_le_remplacement(banc, monkeypatch, capsys):
    banc.notion.pages = [page(f'depot-{i}', f'https://github.com/o/depot-{i}') for i in range(3)]
    assert banc.lancer('sync') == 0
    banc.notion.pages = [page(f'depot-{i}', f'https://github.com/o/depot-{i}') for i in range(5)]

    def interrompt(dossier):
        raise KeyboardInterrupt
    monkeypatch.setattr(banc.rd, '_fsync_dossier', interrompt)
    capsys.readouterr()
    assert banc.lancer('sync') == 130
    sortie = _sorties(capsys)
    assert 'Interruption : index remplacé.' in sortie and 'précédent est conservé' not in sortie
    assert len(banc.rd.lire_fiches(banc.rd.ouvrir_index_lecture())) == 5
    banc.rd.liberer_verrou(banc.rd.prendre_verrou())


def test_sec_r4_erreur_inattendue_de_cherche_sans_index_conserve(corpus, monkeypatch, capsys):
    def panne(*args, **kwargs):
        raise IndexError('panne simulée')
    monkeypatch.setattr(corpus.rd, 'expliquer', panne)
    assert corpus.lancer('cherche', 'pdf') == 2
    sortie = _sorties(capsys)
    assert 'Erreur inattendue (IndexError).' in sortie and 'index précédent' not in sortie


def test_m2_messages_de_commande_en_francais(corpus, capsys):
    assert corpus.lancer('cherche', 'extraire', 'des', 'PDF') == 1
    sortie = _sorties(capsys)
    assert 'arguments en trop : des PDF' in sortie and 'entre guillemets' in sortie
    assert 'unrecognized' not in sortie and '\u274c' not in sortie
    assert corpus.lancer('--log-level', 'verbose', 'cherche', 'pdf') == 1
    assert 'les options se placent après la commande' in _sorties(capsys)
    assert corpus.lancer('état') == 0 and corpus.lancer('Cherche', 'pdf') == 0
    assert 'Commande inconnue' not in _sorties(capsys)


def test_m2_piste_notion_encodable_cp1252(banc, capsys):
    banc.notion.panne_schema = erreur_notion(404, 'Could not find database', 'object_not_found')
    assert banc.lancer('sync') == 1
    sortie = _sorties(capsys)
    assert '- Piste' in sortie and chr(0x2192) not in sortie
    sortie.encode('cp1252')


def _capture_ancienne(banc, tmp_path, lu_le):
    rd = banc.rd
    plates = [rd.aplatir_page(p) for p in pages_du_corpus()[:5]]
    capture = tmp_path / 'vieille.json'
    capture.write_text(json.dumps({'format': rd.FORMAT_CAPTURE, 'database_id': BASE_ID, 'base_titre': 'Base',
                                   'lu_le': lu_le, 'schema': SCHEMA_GITNOTATE, 'nb_requetes': 1, 'ignorees': {},
                                   'pages': [rd.dataclasses.asdict(p) for p in plates]}), encoding='utf-8')
    return capture


def test_m3_capture_rejouee_garde_sa_date_de_lecture(banc, tmp_path, capsys):
    rd = banc.rd
    lu = datetime.now(timezone.utc) - timedelta(days=200)
    capture = _capture_ancienne(banc, tmp_path, lu.isoformat(timespec='seconds'))
    run = (lu + timedelta(days=10)).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    Path(banc.gn.STATS_FILE).write_text(json.dumps([{'timestamp': run, 'success_count': 12, 'dry_run': False}]),
                                        encoding='utf-8')
    assert banc.lancer('sync', '--depuis', str(capture)) == 0
    capsys.readouterr()
    assert banc.lancer('cherche', 'pdf') == 0
    sortie = _sorties(capsys)
    local = lu.astimezone().strftime('%Y-%m-%d')
    assert f"données lues dans Notion le {local}" in sortie and "(il y a 200 jours)" in sortie
    assert "capture vieille.json rejouée le" in sortie and "aujourd'hui" not in sortie
    assert 'Données lues dans Notion il y a 200 jours : relancez sync' in sortie
    assert f"gitnotate.py a créé 12 fiches le {run[:16]}, après cette synchronisation" in sortie
    assert banc.lancer('etat') == 0
    sortie = _sorties(capsys)
    assert f"données lues dans Notion le {lu.astimezone().strftime('%Y-%m-%d %H:%M')} (il y a 200 jours)" in sortie
    assert sortie.count('il y a 200 jours') == 2                 # ligne Synchronisé et alerte Attention
    con, meta = rd.ouvrir_index_valide()
    with con:
        assert len(rd.alertes_index(meta)) == 2
    con.close()


def test_m4_json_tres_imbrique_rejete_sans_perdre_les_resultats(load_gn, monkeypatch, capsys):
    banc = preparer(load_gn, monkeypatch, MISTRAL_API_KEY='cle-mistral-de-test', OPENROUTER_API_KEY='')
    index_du_corpus(banc.rd)
    monkeypatch.setattr(banc.gn, 'get_session', lambda: FauxLLM({'mistral': ('{"avis": ' + '[' * 200000, 'm')}))
    assert banc.lancer('cherche', 'pdf', '--llm', '--oui', '--sortie', 'r.md', '--format', 'markdown') == 2
    sortie = _sorties(capsys)
    assert 'Réponse du LLM inexploitable' in sortie and 'Erreur inattendue' not in sortie
    assert (Path(banc.gn.BASE_DIR) / 'exports' / 'r.md').is_file()


def test_m6_option_prime_et_sync_ignore_les_variables(load_gn, monkeypatch, capsys, tmp_path):
    banc = preparer(load_gn, monkeypatch, REDECOUVERTE_RESULTATS='99', REDECOUVERTE_LLM_MAX='20')
    index_du_corpus(banc.rd)
    assert banc.lancer('cherche', 'pdf', '-n', '5') == 0                  # -n prime ; LLM_MAX inutile sans --llm
    assert banc.lancer('cherche', 'pdf') == 1
    assert 'REDECOUVERTE_RESULTATS=99 est invalide' in _sorties(capsys)
    assert banc.lancer('cherche', 'pdf', '-n', '5', '--llm', '--llm-apercu') == 1
    assert 'REDECOUVERTE_LLM_MAX=20 est invalide' in _sorties(capsys)
    assert banc.lancer('cherche', 'pdf', '-n', '5', '--llm-max', '3', '--llm-apercu') == 0
    capture = _capture_ancienne(banc, tmp_path, '2026-10-11T12:00:00+00:00')
    assert banc.lancer('sync', '--depuis', str(capture), '--accepter-baisse') == 0


def test_m7_pas_de_ci_dessus_sans_resultats_au_dessus(corpus, capsys):
    assert corpus.lancer('cherche', 'pdf', '--llm', '--format', 'markdown') == 2
    sortie = capsys.readouterr()
    assert 'Avis LLM impossible (aucune clé configurée) ; résultats locaux conservés' in sortie.err
    assert 'ci-dessus' not in sortie.err
    assert corpus.lancer('cherche', 'pdf', '--llm') == 2
    assert 'résultats locaux ci-dessus' in capsys.readouterr().err


def test_m10_etabli_ne_repete_pas_un_extrait(corpus, capsys):
    rd = corpus.rd
    reponse = _chercher(rd, PAR_ID['Q01']['requete'], limite=3)
    doublons = [(r, e) for r in reponse.resultats for e in r.etabli if rd._deja_cite(e, r)]
    assert doublons
    texte = rd.en_texte(reponse)
    r, e = doublons[0]
    assert f"{rd._source(e)} : extrait cité ci-dessus" in ' '.join(texte.split())
    assert texte.count(rd._citation(e).split('\n')[0]) == 1
    assert 'extrait cité ci-dessus' in rd.en_markdown(reponse)

# =============================================================================
# M5 — script d'évaluation : options et JSON contrôlés
# =============================================================================
def _evaluateur():
    spec = importlib.util.spec_from_file_location('evaluer_redecouverte_revue',
                                                  ROOT / 'scripts' / 'evaluer_redecouverte.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m5_options_et_erreurs_de_fichier(corpus, tmp_path, capsys):
    evaluer = _evaluateur()
    requete = {'id': 'L1', 'jeu': 'test', 'requete': 'extraire des données de PDF',
               'en_tete': ['docling-project/docling'], 'acceptables': [], 'a_exclure': []}
    fichiers = {}
    for nom, options in (('liste', {'statut': ['Utilisé']}), ('chaine', {'statut': 'Utilisé'})):
        fichiers[nom] = tmp_path / f'{nom}.json'
        fichiers[nom].write_text(json.dumps({'requetes': [dict(requete, options=options)]}), encoding='utf-8')
    assert evaluer.main([str(fichiers['liste'])]) == 0
    liste = capsys.readouterr().out
    assert evaluer.main([str(fichiers['chaine'])]) == 0
    assert capsys.readouterr().out == liste and 'nDCG@10=1,00' in liste
    inconnue = tmp_path / 'inconnue.json'
    inconnue.write_text(json.dumps({'requetes': [dict(requete, options={'statu': ['Utilisé']})]}), encoding='utf-8')
    assert evaluer.main([str(inconnue)]) == 1
    assert 'option inconnue « statu »' in capsys.readouterr().err
    bom = tmp_path / 'bom.json'
    bom.write_text(json.dumps({'requetes': [dict(requete, options={})]}), encoding='utf-8-sig')
    assert evaluer.main([str(bom)]) == 0
    virgule = tmp_path / 'virgule.json'
    virgule.write_text('{"requetes": [\n {"id": "X", "requete": "pdf"},\n]}', encoding='utf-8')
    assert evaluer.main([str(virgule)]) == 1
    # La ligne signalée dépend de la version de Python (3.13 : ligne 2, 3.10 : ligne 3, colonne 1)
    erreur = capsys.readouterr().err
    assert re.search(r'JSON invalide ligne [23]\b', erreur) and 'virgule en trop' in erreur
    faute = tmp_path / 'faute.json'
    faute.write_text(json.dumps({'requetes': [dict(requete, options={}, en_tete=['Docling-Project/Docling'])]}),
                     encoding='utf-8')
    assert evaluer.main([str(faute)]) == 0
    assert "cite des dépôts absents de l'index : Docling-Project/Docling" in capsys.readouterr().err

# =============================================================================
# M15 — branches visibles jusque-là sans test
# =============================================================================
def test_m15_log_level_verbose(corpus, capsys):
    assert corpus.lancer('cherche', 'pdf', '--log-level', 'verbose') == 0
    sortie = _sorties(capsys)
    assert '[pdf] direct :' in sortie and 'Recherche locale en' in sortie


def test_m15_pertinence_modifiee(banc):
    _synchroniser(banc, [
        _fiche('modifiee', 'Outil OCR.', Pertinence=p_nombre(7)),
        _fiche('nonnotee', 'Outil OCR bis.', Pertinence=p_nombre(5), Justification=p_texte(NO_INFO))])
    reponse = _chercher(banc.rd, 'outil ocr')
    textes = {r.cle: [a['texte'] for a in r.a_verifier if a['code'] == 'pertinence_modifiee'] for r in reponse.affiches}
    assert textes['test/modifiee'] == ["La note de la Justification (9) diffère de la Pertinence (7) : fiche "
                                       "peut-être modifiée"]
    assert textes['test/nonnotee'] == ["Pertinence renseignée (5) alors que Gitnotate l'avait laissée vide : fiche "
                                       "peut-être modifiée"]


def test_m15_markdown_negation_filtres_et_fiches_sans_depot(corpus, capsys):
    assert corpus.lancer('cherche', PAR_ID['Q01']['requete'] + ' sans GPU', '--exclure-statut', 'Écarté',
                         '--format', 'markdown') == 0
    sortie = capsys.readouterr().out
    assert 'Non pris en compte (négation) : GPU' in sortie and 'Filtres : statut exclu « Écarté »' in sortie
    assert '## Fiches sans dépôt GitHub (notes, adresses hors GitHub)' in sortie


def test_m15_llm_avis_dans_le_fichier_texte(load_gn, monkeypatch):
    banc = preparer(load_gn, monkeypatch, MISTRAL_API_KEY='cle-mistral-de-test', OPENROUTER_API_KEY='')
    index_du_corpus(banc.rd)
    avis = json.dumps({'avis': [{'id': f'R{i}', 'adequation': 2, 'raison': 'Surveille des flux RSS et envoie des '
                                 'alertes'} for i in range(1, 4)]})
    monkeypatch.setattr(banc.gn, 'get_session', lambda: FauxLLM({'mistral': (avis, 'mistral-servi')}))
    assert banc.lancer('cherche', PAR_ID['Q03']['requete'], '-n', '3', '--llm', '--oui', '--sortie', 'r.txt') == 0
    texte = (Path(banc.gn.BASE_DIR) / 'exports' / 'r.txt').read_text(encoding='utf-8')
    assert 'Avis du LLM — Mistral AI, modèle servi mistral-servi' in texte and 'Avis LLM   : 2/3' in texte


def test_m15_famille_non_reconnue(banc):
    _synchroniser(banc, [page('inconnu', 'https://github.com/test/inconnu', v73=False, props={
        'Description': p_texte('Outil OCR inconnu.'), 'Installation': p_texte('make install')})])
    r = _resultat(_chercher(banc.rd, 'outil ocr'), 'test/inconnu')
    assert r.principale['famille'] == 'indeterminee'
    assert ("Version de la fiche non reconnue : toutes ses informations sont à vérifier"
            in [a['texte'] for a in r.a_verifier if a['code'] == 'famille_incertaine'])


def test_m15_markdown_alertes_et_avis_llm(load_gn, monkeypatch, capsys):
    banc = preparer(load_gn, monkeypatch, MISTRAL_API_KEY='cle-mistral-de-test', OPENROUTER_API_KEY='')
    index_du_corpus(banc.rd)
    con, meta = banc.rd.ouvrir_index_valide()
    con.close()
    apres = (datetime.strptime(meta['sync_fin_locale'], '%Y-%m-%d %H:%M:%S') + timedelta(hours=1))
    Path(banc.gn.STATS_FILE).write_text(json.dumps([{'timestamp': apres.strftime('%Y-%m-%d %H:%M:%S'),
                                                     'success_count': 4, 'dry_run': False}]), encoding='utf-8')
    avis = json.dumps({'avis': [{'id': f'R{i}', 'adequation': 3, 'raison': 'Surveille des flux RSS et envoie des '
                                 'alertes'} for i in range(1, 4)]})
    monkeypatch.setattr(banc.gn, 'get_session', lambda: FauxLLM({'mistral': (avis, 'mistral-servi')}))
    assert banc.lancer('cherche', PAR_ID['Q03']['requete'], '-n', '3', '--llm', '--oui', '--format', 'markdown') == 0
    sortie = capsys.readouterr().out
    assert '**Attention** : gitnotate.py a créé 4 fiches le' in sortie
    assert '## Avis du LLM (facultatif, non vérifié)' in sortie and '**Avis LLM (non vérifié)** : 3/3' in sortie


def test_m15_alerte_plusieurs_runs(corpus, capsys):
    rd = corpus.rd
    con, meta = rd.ouvrir_index_valide()
    con.close()
    fin = datetime.strptime(meta['sync_fin_locale'], '%Y-%m-%d %H:%M:%S')
    runs = [(fin + timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S') for h in (1, 2)]
    Path(corpus.gn.STATS_FILE).write_text(json.dumps([{'timestamp': t, 'success_count': n, 'dry_run': False}
                                                      for t, n in zip(runs, (7, 12), strict=True)]), encoding='utf-8')
    assert corpus.lancer('etat') == 0
    assert (f"gitnotate.py a créé 19 fiches en 2 runs après cette synchronisation (dernier le {runs[1][:16]})"
            in _sorties(capsys))

# =============================================================================
# Documentation (M1, M8, M14, P1) — phrases corrigées
# =============================================================================
def test_documentation_corrigee():
    doc = (ROOT / 'docs' / 'REDECOUVERTE.md').read_text(encoding='utf-8')
    validation = (ROOT / 'docs' / 'VALIDATION.md').read_text(encoding='utf-8')
    lexique = (ROOT / 'redecouverte_lexique.py').read_text(encoding='utf-8')
    for texte in (doc, validation, lexique):
        assert 'GABARITS_CAS_USAGE' in texte                                      # M1 : exception documentée
    assert "Modifier le lexique n'exige pas de resynchronisation :" not in lexique
    assert 'les caractères qu\'il ne connaît pas\n  deviennent « ? »' not in doc                     # M8
    assert 'PowerShell' in doc.split('## 7. Windows')[1].split('## 8.')[0]
    assert 'apostrophe' in doc.split('## 5. Lire un résultat')[1].split('## 6.')[0]                # M14
    assert 'apostrophe' in validation.split('## H.')[1]
    assert 'README, modifié dans Notion — à vérifier' in doc                                        # P3
    assert 'README_LLM_CHARS=0' in (ROOT / 'README.md').read_text(encoding='utf-8')                # PA-2


# =============================================================================
# Âge de l'index en jours de calendrier (lecture de la veille : pas « aujourd'hui »)
# =============================================================================
def test_age_index_en_jours_de_calendrier(load_gn, monkeypatch):
    load_gn()
    import redecouverte as rd
    rd = importlib.reload(rd)
    maintenant = datetime.now(timezone.utc).astimezone()
    veille = (maintenant - timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)
    if (maintenant - veille).total_seconds() >= 86400:      # instant présent après 23 h 59 : rien à vérifier ici
        veille = maintenant - timedelta(minutes=maintenant.hour * 60 + maintenant.minute + 1)
    monkeypatch.setattr(rd, '_lecture', lambda meta: veille)
    assert rd._age_jours({}) == 1
    assert rd._il_y_a(rd._age_jours({})) == 'il y a 1 jour'
    monkeypatch.setattr(rd, '_lecture', lambda meta: maintenant)
    assert rd._il_y_a(rd._age_jours({})) == "aujourd'hui"
