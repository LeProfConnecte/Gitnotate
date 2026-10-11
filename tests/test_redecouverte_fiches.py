"""Moteur de redécouverte — fiches (spécification du lot 4, § 22.3, et amendements v7.4).

D. Extraction · E. Provenance · F. Fiabilité · G. Doublons.
Corpus synthétique : tests/fixtures/redecouverte/corpus.json (60 fiches de conception + 3 fiches v7.4).
"""
import dataclasses
import json
import random

import pytest

from redecouverte_outils import (
    SCHEMA_GITNOTATE, charger_bases, charger_corpus, fiche_du_corpus, index_du_corpus, lignes, p_autre, p_date,
    p_formule, p_multi, p_nombre, p_select, p_texte, p_titre, p_url, page, pages_du_corpus, preparer,
    requete_fts, rt, schema_base,
)

CORPUS = charger_corpus()
IDS_CORPUS = [c['id_corpus'] for c in CORPUS]
FAMILLES_CORPUS = {'v7.0-v7.1': 'v7.1', 'v7.2.0': 'v7.2', 'ancien': 'ancienne', 'indéterminée': 'indeterminee'}
# Correspondance des niveaux du corpus avec ceux du moteur (§ 12.4)
NIVEAUX_CORPUS = {
    'fiable': {'github'}, 'traduction': {'llm', 'github'}, 'original-github': {'github'}, 'llm': {'llm'},
    'llm-justifie': {'llm'}, 'llm-avis': {'avis_llm'}, 'extrait-partiel': {'readme_partiel'},
    'extrait-verifie': {'readme'}, 'verbatim': {'readme'}, 'generique': {'gabarit'}, 'fabrique': {'gabarit'},
    'heuristique': {'gabarit'}, 'non-verifie': {'non_verifie'}, 'utilisateur': {'utilisateur'},
    'hors-github': {'utilisateur'}, 'defaut': {'defaut'}, 'technique': {'vide'}, 'vide': {'vide'},
}
AFFICHAGE_SEUL = {'fiable-a-date', 'fiable-grossier', 'non-comparable'}
GABARIT_EN = "• Task automation via AI agents\n• Multi-agent orchestration\n• Agent integration"
GABARIT_FR = "• Ajustement fin du modèle\n• Déploiement en production\n• Expérimentation ML"


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


def _fiche(rd, props=None, colonnes=None, v73=True, **options):
    cols = rd.resoudre_colonnes(SCHEMA_GITNOTATE if colonnes is None else colonnes)
    return rd.construire_fiche(rd.aplatir_page(page(props=props, v73=v73, **options)), cols)


def _ancienne(**props):
    """Fiche des versions 6.7 à 7.2 (Prérequis « Python recent », gabarits)."""
    base = {'Description': p_texte('Convertit des documents en Markdown.'), "Cas d'usage": p_texte(GABARIT_EN),
            'Installation': p_texte('See documentation'), 'Exemple': p_texte('pip install outil'),
            'Prérequis': p_texte('Python recent'), 'Stars': p_nombre(10), 'Pertinence': p_nombre(7),
            'Langage': p_select('Python'), 'Statut': p_select('À explorer'), 'Type': p_multi('Outils'),
            'Analysé le': p_date('2026-01-14')}
    base.update(props)
    return base

# =============================================================================
# D. Extraction
# =============================================================================
@pytest.mark.parametrize('prop, attendu', [
    (p_titre('Paddle', 'OCR'), {'type': 'title', 'texte': 'PaddleOCR', 'segments': 2}),
    ({'type': 'rich_text', 'rich_text': [{'type': 'equation', 'equation': {'expression': 'E=mc^2'}}]},
     {'texte': 'E=mc^2', 'segments': 1}),
    (p_texte(), {'texte': '', 'segments': 0}),
    ({'type': 'rich_text', 'rich_text': None}, {'texte': '', 'illisible': False}),
    ({'type': 'rich_text', 'rich_text': 'pas une liste'}, {'illisible': True}),
    (p_select('Python'), {'type': 'select', 'texte': 'Python'}),
    (p_select(None), {'texte': ''}),
    (p_select('En test', 'status'), {'type': 'status', 'texte': 'En test'}),
    ({'type': 'select', 'select': ['x']}, {'illisible': True}),
    (p_multi('OCR', '', 'PDF'), {'valeurs': ('OCR', 'PDF')}),
    ({'type': 'multi_select', 'multi_select': 'OCR'}, {'illisible': True}),
    (p_url('https://github.com/a/b'), {'texte': 'https://github.com/a/b'}),
    (p_url(None), {'texte': ''}),
    ({'type': 'url', 'url': 5}, {'illisible': True}),
    (p_nombre(48100), {'nombre': 48100.0}),
    (p_nombre(7.5), {'nombre': 7.5}),
    (p_nombre(None), {'nombre': None, 'illisible': False}),
    (p_nombre(True), {'nombre': None, 'illisible': True}),
    (p_nombre('12'), {'illisible': True}),
    (p_nombre(float('nan')), {'illisible': True}),
    (p_date('2026-01-10'), {'texte': '2026-01-10'}),
    (p_date('2026-01-10T12:00:00.000+11:00'), {'texte': '2026-01-10T12:00:00.000+11:00'}),
    (p_date(None), {'texte': ''}),
    ({'type': 'date', 'date': 'hier'}, {'illisible': True}),
    (p_formule('string', 'calculé'), {'type': 'formula', 'texte': 'calculé'}),
    (p_formule('number', 42), {'texte': '42', 'nombre': 42.0}),
    (p_formule('number', 2.5), {'texte': '2.5', 'nombre': 2.5}),
    (p_formule('date', {'start': '2026-03-08'}), {'texte': '2026-03-08'}),
    (p_formule('boolean', True), {'texte': '', 'nombre': None, 'illisible': False}),
])
def test_texte_propriete_tous_types(banc, prop, attendu):
    valeur = banc.rd.texte_propriete(prop)
    assert valeur is not None
    for cle, val in attendu.items():
        assert getattr(valeur, cle) == val, cle


@pytest.mark.parametrize('prop', [
    None, {}, 'texte', 5, {'type': None}, {'type': ['x']}, p_autre('checkbox', True), p_autre('people', []),
    p_autre('created_time', '2026-01-01T00:00:00.000Z'), p_autre('last_edited_time', '2026-01-01T00:00:00.000Z'),
    p_autre('relation', []), p_autre('rollup', {'type': 'number', 'number': 3}), p_autre('files', []),
    p_autre('email', 'a@b.c'), p_autre('phone_number', '+687'), p_autre('unique_id', {'number': 3}),
    p_autre('button', {}), p_autre('place', None), p_autre('verification', None), p_autre('inconnu', 'x'),
])
def test_texte_propriete_types_non_conserves(banc, prop):
    assert banc.rd.texte_propriete(prop) is None


def test_concatenation_segments_et_modification(banc):
    rd = banc.rd
    f = _fiche(rd, {'Description': p_texte(rt('Outil '), rt('très', bold=True), rt(' pratique', lien='https://x.y'))})
    ch = f.champs['Description']
    assert ch.texte == 'Outil très pratique' and ch.modifie is True and ch.fiabilite == 'llm'
    assert 'modifie-a-la-main:Description' in f.provenance.drapeaux
    seul = _fiche(rd, {'Description': p_texte('Outil très pratique')})
    assert seul.champs['Description'].modifie is False
    assert not any(d.startswith('modifie-a-la-main') for d in seul.provenance.drapeaux)
    couleur = _fiche(rd, {'Installation': p_texte(rt('pip install x', color='red'))})
    assert couleur.champs['Installation'].modifie and couleur.champs['Installation'].fiabilite == 'readme'


def test_troncature_mentions(banc):
    rd = banc.rd
    f = _fiche(rd, {'Notes': p_texte(*[rt(f'@page{i} ', mention=True) for i in range(25)])})
    assert ('Notes', 'troncature_possible') in {(a[0], a[1]) for a in f.anomalies}
    f24 = _fiche(rd, {'Description': p_texte(*[rt(f'@p{i} ', mention=True) for i in range(24)])})
    assert 'troncature_possible' not in {a[1] for a in f24.anomalies}
    assert f24.champs['Description'].modifie                 # une mention suffit à signaler la modification


def test_normalisation_caracteres(banc):
    rd = banc.rd
    brut = "L’outil open‑source et l‐autre été   "
    assert rd.normaliser(brut) == "L'outil open-source et l-autre été"
    f = _fiche(rd, {'Description': p_texte(brut)})
    assert f.champs['Description'].texte == "L'outil open-source et l-autre été"


def test_colonnes_connues_types_toleres(banc):
    rd = banc.rd
    colonnes = dict(SCHEMA_GITNOTATE, Statut='status', Langage='multi_select', **{
        'Dernière MAJ': 'rich_text', 'Licence': 'select', 'Brique pour': 'rich_text', 'Catégorie': 'multi_select'},
        Stars='rich_text')
    cols = rd.resoudre_colonnes(colonnes)
    schema_anomalies = {(a[0], a[1]) for a in cols.anomalies}
    assert schema_anomalies == {('Catégorie', 'type_inattendu'), ('Stars', 'type_inattendu')}
    props = {'Statut': p_select('En test', 'status'), 'Langage': p_multi('Python', 'Rust'),
             'Dernière MAJ': p_texte('2026-01-10 (GitHub)'), 'Licence': p_select('MIT'),
             'Brique pour': p_texte('Documents et OCR, Enseignement'), 'Catégorie': p_multi('OCR/Documents', 'Autre'),
             'Stars': p_texte('48 100')}
    f = _fiche(rd, props, colonnes)
    assert (f.statut, f.langage, f.derniere_maj, f.licence) == ('En test', 'Python', '2026-01-10', 'MIT')
    assert f.brique_pour == ('Documents et OCR', 'Enseignement') and f.categorie == 'OCR/Documents'
    assert f.stars is None
    mauvaise_date = _fiche(rd, {'Dernière MAJ': p_texte('janvier 2026')}, colonnes)
    assert mauvaise_date.derniere_maj == ''
    assert ('Dernière MAJ', 'type_inattendu') in {(a[0], a[1]) for a in mauvaise_date.anomalies}


def test_colonne_renommee_et_ambigue(banc):
    rd = banc.rd
    renommee = dict(SCHEMA_GITNOTATE, Categorie='select')
    cols = rd.resoudre_colonnes(renommee)
    assert cols.reelles['Catégorie'] == 'Categorie' and 'Categorie' not in cols.personnelles
    f = _fiche(rd, {'Categorie': p_select('OCR/Documents'), 'Justification': p_texte('')}, renommee)
    assert f.categorie == 'OCR/Documents'
    ambigue = dict(SCHEMA_GITNOTATE, categorie='select', CATÉGORIE='rich_text')
    cols = rd.resoudre_colonnes(ambigue)
    assert 'Catégorie' not in cols.reelles
    assert ('Catégorie', 'colonne_ambigue') in {(a[0], a[1]) for a in cols.anomalies}
    assert not {'categorie', 'CATÉGORIE'} & set(cols.personnelles)
    f = _fiche(rd, {'categorie': p_select('OCR/Documents'), 'CATÉGORIE': p_texte('Autre')}, ambigue)
    assert f.categorie == '' and f.champs['Catégorie'].fiabilite == 'vide'


def test_colonnes_personnelles(banc):
    rd = banc.rd
    colonnes = dict(SCHEMA_GITNOTATE, Tags='multi_select', Favori='checkbox', **{'Projet lié': 'relation',
                                                                              'Échéance': 'date'})
    cols = rd.resoudre_colonnes(colonnes)
    assert cols.personnelles == ('Notes', 'Tags')
    assert cols.ignorees == {'Favori': 'checkbox', 'Projet lié': 'relation', 'Échéance': 'date'}
    f = _fiche(rd, {'Notes': p_texte('Testé en salle B12'), 'Tags': p_multi('OCR', 'PDF'),
                    'Favori': p_autre('checkbox', True), 'Projet lié': p_autre('relation', [{'id': 'x'}]),
                    'Échéance': p_date('2026-12-01')}, colonnes)
    assert f.autres == {'Notes': 'Testé en salle B12', 'Tags': 'OCR, PDF'}
    assert rd.contenu_fts(f)['notes'] == 'Notes : Testé en salle B12\nTags : OCR, PDF'


def test_valeurs_nulles_partout(banc):
    rd = banc.rd
    nulles = {'Nom': p_titre(), 'URL': p_url(None), 'Description': p_texte(), "Cas d'usage": p_texte(),
              'Installation': p_texte(), 'Exemple': p_texte(), 'Prérequis': p_texte(), 'Stars': p_nombre(None),
              'Pertinence': p_nombre(None), 'Langage': p_select(None), 'Statut': p_select(None), 'Type': p_multi(),
              'Dernière MAJ': p_date(None), 'Analysé le': p_date(None), 'Justification': p_texte(),
              'Notes': p_texte()}
    f = _fiche(rd, nulles, v73=False, id='0123456789abcdef0123456789abcdef')
    assert f.provenance.famille == 'manuelle' and f.cle_depot == 'page:0123456789abcdef0123456789abcdef'
    assert f.nom == '(sans titre)' and f.stars is None and f.pertinence is None
    assert {a[1] for a in f.anomalies} == {'url_absente', 'titre_absent'}
    assert all(ch.fiabilite == 'vide' for ch in f.champs.values())
    assert rd.contenu_fts(f) == {colonne: '' for colonne in rd.COLONNES_FTS}


@pytest.mark.parametrize('url', [
    'https://github.com/docling-project/docling', 'https://github.com/docling-project/docling/',
    'https://github.com/Docling-Project/Docling', 'https://github.com/docling-project/docling.git',
    'https://github.com/docling-project/docling/tree/main/docs', 'https://github.com/docling-project/docling?tab=readme-ov-file',
    'https://github.com/docling-project/docling?utm_source=x', 'github.com/docling-project/docling',
    'http://www.github.com/docling-project/docling#readme',
])
def test_cle_depot_variantes(banc, url):
    f = _fiche(banc.rd, {'URL': p_url(url)})
    assert f.cle_depot == 'docling-project/docling'
    assert not {a[1] for a in f.anomalies} & {'url_absente', 'url_non_github'}


def test_cle_depot_hors_github_et_absente(banc):
    rd = banc.rd
    gitlab = _fiche(rd, {'URL': p_url('https://GitLab.com/Groupe/Projet/')})
    assert gitlab.cle_depot == 'url:https://gitlab.com/groupe/projet'
    assert gitlab.champs['URL'].fiabilite == 'utilisateur'
    assert ('URL', 'url_non_github') in {(a[0], a[1]) for a in gitlab.anomalies}
    sujet = _fiche(rd, {'URL': p_url('https://github.com/topics/ocr')})
    assert sujet.cle_depot.startswith('url:')
    absente = _fiche(rd, {'URL': p_url(None)}, id='abcdefabcdefabcdefabcdefabcdefab')
    assert absente.cle_depot == 'page:abcdefabcdefabcdefabcdefabcdefab'
    texte = _fiche(rd, {'URL': p_texte('voir https://github.com/allenai/olmocr. merci')},
                   dict(SCHEMA_GITNOTATE, URL='rich_text'))
    assert texte.cle_depot == 'allenai/olmocr'


def test_titre_absent(banc):
    f = _fiche(banc.rd, {'Nom': p_titre(), 'URL': p_url('https://github.com/UB-Mannheim/tesseract/wiki')})
    assert f.nom == 'UB-Mannheim/tesseract' and f.cle_depot == 'ub-mannheim/tesseract'
    assert ('Nom', 'titre_absent') in {(a[0], a[1]) for a in f.anomalies}
    assert banc.rd.contenu_fts(f)['nom'] == 'ub mannheim tesseract'

# =============================================================================
# E. Provenance
# =============================================================================
@pytest.mark.parametrize('id_corpus', [i for i, c in zip(IDS_CORPUS, CORPUS, strict=True)
                                       if c['version_attendue'] != 'corbeille'])
def test_famille_corpus(banc, id_corpus):
    c = next(x for x in CORPUS if x['id_corpus'] == id_corpus)
    f = fiche_du_corpus(banc.rd, id_corpus, CORPUS)
    attendue = FAMILLES_CORPUS.get(c['version_attendue'], c['version_attendue'])
    assert f.provenance.famille == attendue
    for drapeau in c['attendu']['drapeaux']:
        assert drapeau in f.provenance.drapeaux
    if c['cle_depot'] and '://' not in c['cle_depot']:
        assert f.cle_depot == c['cle_depot']
    else:                                       # adresse hors GitHub ou absente : fiche seule, clé url:/page:
        assert f.cle_depot.startswith(('url:', 'page:'))


def test_corbeille_du_corpus_ignoree_par_la_lecture(banc):
    jetees = [c for c in CORPUS if c['version_attendue'] == 'corbeille']
    assert len(jetees) == 1 and jetees[0]['page']['in_trash']
    assert len(pages_du_corpus(CORPUS)) == len(CORPUS) - 1


def test_prefixe_v73_llm_composantes(banc):
    p = fiche_du_corpus(banc.rd, 'A10', CORPUS).provenance
    assert (p.famille, p.regle, p.methode, p.modele) == ('v7.3', 'R73', 'LLM', 'mistral-small-2603')
    assert (p.profil_version, p.profil_empreinte) == ('2026-10-11', '8c41d2')
    assert (p.composantes, p.note_justification, p.drapeaux) == ('U1·P3·T1·I2·C1·M2·L?', 9, ())
    assert banc.rd.libelle_fiche(p) == 'fiche v7.3+'


def test_format_v74_plafond_llm(banc):
    rd = banc.rd
    f = fiche_du_corpus(rd, 'A53', CORPUS)
    p = f.provenance
    assert (p.famille, p.regle, p.methode, p.profil_empreinte) == ('v7.3', 'R73', 'LLM', 'a41f07')
    assert (p.composantes, p.note_justification) == ('U0·P3·T2·I2·C2·M2·L2', 8)
    assert 'note-plafonnee:10' in p.drapeaux and 'pertinence-modifiee' not in p.drapeaux
    assert 'composantes-absentes' not in p.drapeaux
    j = f.champs['Justification']
    assert j.fiabilite == 'avis_llm' and j.texte.startswith('Client Git en terminal')
    assert rd.contenu_fts(f)['justification'] == j.texte
    plafond = ("[LLM m · profil v1/abcdef] U0·P3·T2·I2·C2·M2·L2 = 10, plafonnée à 8 (aucune brique du profil) — "
               "Avis.")
    modifiee = _fiche(rd, {'Justification': p_texte(plafond), 'Pertinence': p_nombre(10)})
    assert modifiee.provenance.note_justification == 8
    assert 'pertinence-modifiee' in modifiee.provenance.drapeaux
    sans_corps = _fiche(rd, {'Justification': p_texte(plafond[:plafond.index(' Avis.')])})
    assert 'composantes-absentes' not in sans_corps.provenance.drapeaux
    assert sans_corps.champs['Justification'].fiabilite == 'vide'


def test_prefixe_v73_lexical(banc):
    rd = banc.rd
    for id_corpus, note in (('A49', None), ('A54', 8)):
        f = fiche_du_corpus(rd, id_corpus, CORPUS)
        assert (f.provenance.famille, f.provenance.methode, f.provenance.note_justification) == ('v7.3', 'LEXICAL', note)
        assert f.champs['Justification'].fiabilite == 'vide'
        assert rd.contenu_fts(f)['justification'] == ''
        assert f.champs['Description'].fiabilite == 'github'
    a54 = fiche_du_corpus(rd, 'A54', CORPUS)
    assert 'note-plafonnee:10' in a54.provenance.drapeaux and 'pertinence-modifiee' not in a54.provenance.drapeaux


def test_format_v74_non_note(banc):
    rd = banc.rd
    f = fiche_du_corpus(rd, 'A55', CORPUS)
    p = f.provenance
    assert (p.famille, p.regle, p.methode, p.note_justification) == ('v7.3', 'R74N', 'NON NOTÉ', None)
    assert p.drapeaux == ('non-notee',) and f.pertinence is None
    assert f.champs['Justification'].fiabilite == 'vide'
    for champ in ('Description', "Cas d'usage", 'Installation', 'Exemple', 'Prérequis', 'Licence'):
        assert f.champs[champ].fiabilite == 'non_verifie', champ
    assert rd.libelle_fiche(p) == 'fiche v7.3+' and 'non notée' in rd.libelle_fiche(p, f.analyse_le, True)
    assert rd.LIMITE_NON_NOTEE == ("Fiche non notée : le dépôt n'avait ni description, ni topics, ni README "
                                   "exploitable")
    contenu = rd.contenu_fts(f)
    assert all(contenu[c] == '' for c in rd.COLONNES_FTS if c not in ('nom', 'langage'))
    notee = _fiche(rd, {'Justification': p_texte(CORPUS_NON_NOTE), 'Pertinence': p_nombre(5)})
    assert 'pertinence-modifiee' in notee.provenance.drapeaux
    reecrite = _fiche(rd, {'Justification': p_texte(CORPUS_NON_NOTE), 'Description': p_texte('Mon résumé.')})
    assert reecrite.champs['Description'].fiabilite == 'inconnu'


CORPUS_NON_NOTE = "[NON NOTÉ] Ni description, ni topics, ni README exploitable : Pertinence laissée vide."


def test_prefixe_v72_modele_barre_deux_points(banc):
    rd = banc.rd
    p = fiche_du_corpus(rd, 'A07', CORPUS).provenance
    assert (p.famille, p.regle, p.modele, p.profil_empreinte) == ('v7.2', 'R72', 'meta-llama/llama-3.3-70b-instruct:free',
                                                                 '3f9a1c')
    f = _fiche(rd, {'Justification': p_texte('[LLM openai/gpt-oss-20b:free · profil 1a2b3c] Avis.'),
                    'Prérequis': p_texte('Python recent')})
    assert (f.provenance.famille, f.provenance.modele) == ('v7.2', 'openai/gpt-oss-20b:free')
    assert f.champs['Justification'].texte == 'Avis.' and f.champs['Justification'].fiabilite == 'avis_llm'
    modifie = _fiche(rd, {'Justification': p_texte('[LLM x · profil 1a2b3c] Avis.'),
                          'Prérequis': p_texte('Python 3.10+')})
    assert 'prerequis-modifie' in modifie.provenance.drapeaux


def test_v72_nv(banc):
    p = fiche_du_corpus(banc.rd, 'A35', CORPUS).provenance
    assert (p.famille, p.regle, p.methode) == ('v7.2-nv', 'R72N', 'LLM')
    assert banc.rd.libelle_fiche(p) == 'fiche v7.2'


def test_v71(banc):
    f = fiche_du_corpus(banc.rd, 'A02', CORPUS)
    assert (f.provenance.famille, f.provenance.regle, f.provenance.methode) == ('v7.1', 'R71', 'LLM')
    assert f.champs['Justification'].fiabilite == 'avis_llm'
    assert not f.champs['Justification'].texte.startswith('[LLM]')
    assert banc.rd.libelle_fiche(f.provenance, f.analyse_le, True) == \
        'fiche v7.0/v7.1 · avis LLM (modèle non noté) · analysée le 2026-03-08'


def test_prefixe_coupe_entre_segments(banc):
    rd = banc.rd
    f = fiche_du_corpus(rd, 'A39', CORPUS)
    assert (f.provenance.famille, f.provenance.regle) == ('v7.3', 'R73')
    assert f.champs['Justification'].modifie
    coupe = _fiche(rd, {'Justification': p_texte('[LLM mistral-sm', 'all-2603 · profil 2026-10-11/8c41d2] '
                                                 'U1·P3·T2·I2·C2·M2·L2 = 9 — Avis coupé.')})
    assert (coupe.provenance.regle, coupe.provenance.modele) == ('R73', 'mistral-small-2603')
    assert coupe.champs['Justification'].texte == 'Avis coupé.'


def test_justification_non_reconnue_utilisateur(banc):
    rd = banc.rd
    f = fiche_du_corpus(rd, 'A40', CORPUS)
    assert 'justification-non-reconnue' in f.provenance.drapeaux
    j = f.champs['Justification']
    assert j.fiabilite == 'utilisateur' and j.texte == 'À tester avec mes cours de métré (PDF) avant la rentrée.'
    contenu = rd.contenu_fts(f)
    assert contenu['justification'] == '' and 'Justification : À tester avec mes cours de métré' in contenu['notes']


def test_categorie_saisie_sur_fiche_ancienne_reste_ancienne(banc):
    colonnes = dict(SCHEMA_GITNOTATE, **{'Catégorie': 'select'})
    f = _fiche(banc.rd, _ancienne(**{'Catégorie': p_select('OCR/Documents'), 'Justification': p_texte()}),
               colonnes, v73=False)
    assert (f.provenance.famille, f.provenance.regle) == ('ancienne', 'S1')
    assert f.champs['Catégorie'].fiabilite == 'utilisateur'


def test_pertinence_modifiee(banc):
    rd = banc.rd
    j = "[LLM m · profil v1/abcdef] U1·P3·T2·I2·C2·M2·L2 = 9 — Avis."
    assert 'pertinence-modifiee' in _fiche(rd, {'Justification': p_texte(j), 'Pertinence': p_nombre(7)}).provenance.drapeaux
    assert 'pertinence-modifiee' not in _fiche(rd, {'Justification': p_texte(j),
                                                    'Pertinence': p_nombre(9)}).provenance.drapeaux
    assert 'pertinence-modifiee' not in _fiche(rd, {'Justification': p_texte(j),
                                                    'Pertinence': p_nombre(None)}).provenance.drapeaux
    sans = _fiche(rd, {'Justification': p_texte('[LLM m · profil v1/abcdef] Avis sans composantes.')})
    assert 'composantes-absentes' in sans.provenance.drapeaux


def test_aucun_indice_de_date(banc):
    """Amendement 3 : aucune version n'est devinée d'après une date ; seule la date d'analyse est affichée."""
    rd = banc.rd
    assert 'indice_date' not in {f.name for f in dataclasses.fields(rd.Provenance)}
    assert 'indice_date' not in rd.DDL and 'indice_date' not in rd.COLONNES_FICHES
    janvier = _fiche(rd, _ancienne(**{'Analysé le': p_date('2026-01-14')}), v73=False)
    octobre = _fiche(rd, _ancienne(**{'Analysé le': p_date('2026-10-20')}), v73=False)
    assert janvier.provenance == octobre.provenance
    for f in (janvier, octobre, fiche_du_corpus(rd, 'A02', CORPUS)):
        libelle = rd.libelle_fiche(f.provenance, f.analyse_le, True)
        assert libelle.endswith(f"analysée le {f.analyse_le}")
        for interdit in ('indice', 'v6.7', 'janvier', 'mars', 'octobre', 'v6.9'):
            assert interdit not in libelle
    source = open(rd.__file__, encoding='utf-8').read()
    assert 'v6.7 (janvier)' not in source and '(mars)' not in source


def test_modifiee_apres_creation(banc):
    rd = banc.rd
    assert _fiche(rd, cree='2026-01-14T10:12:00.000Z', modifie='2026-01-14T10:15:00.000Z').modifiee_apres_creation
    assert not _fiche(rd, cree='2026-01-14T10:12:00.000Z', modifie='2026-01-14T10:13:00.000Z').modifiee_apres_creation
    assert not _fiche(rd, cree='hier', modifie='2026-01-14T10:13:00.000Z').modifiee_apres_creation

# =============================================================================
# F. Fiabilité
# =============================================================================
@pytest.mark.parametrize('id_corpus', [i for i, c in zip(IDS_CORPUS, CORPUS, strict=True)
                                       if c['version_attendue'] != 'corbeille'])
def test_fiabilite_corpus(banc, id_corpus):
    rd = banc.rd
    c = next(x for x in CORPUS if x['id_corpus'] == id_corpus)
    f = fiche_du_corpus(rd, id_corpus, CORPUS)
    for champ, niveau in c['attendu']['champs'].items():
        if champ not in f.champs:
            continue                            # colonnes personnelles, nombres et dates : affichage seulement
        if niveau in AFFICHAGE_SEUL:
            if champ != 'Langage':
                continue
            niveau = 'fiable'
        obtenu = f.champs[champ]
        attendus = NIVEAUX_CORPUS[niveau]
        if champ == 'Licence' and rd.gn._fold(obtenu.texte) in ('non verifiee', 'non renseignee'):
            # Règle F2 de la spécification (prioritaire sur le corpus de conception) : « Non vérifiée » et
            # « Non renseignée » sont « non vérifié par Gitnotate », jamais indexés
            attendus = {'non_verifie'}
        assert obtenu.fiabilite in attendus, (champ, niveau, obtenu)
        if niveau == 'traduction' and obtenu.fiabilite == 'github' and f.provenance.methode != 'LEXICAL':
            assert 'description-anglaise' in f.provenance.drapeaux


def test_gabarits_jamais_indexes(banc):
    rd = banc.rd
    index_du_corpus(rd)
    for expression in ('installation : "see documentation"', 'exemple : "see docs"', 'prerequis : "see docs"',
                       'prerequis : recent', 'cas_usage : "task automation"', 'cas_usage : "ajustement fin"',
                       'cas_usage : "deploiement en production"', 'type : outils',
                       'exemple : "pip install open notebook"', 'exemple : "npm install dexter"'):
        assert requete_fts(rd, expression) == {}, expression
    fabriques = [
        _fiche(rd, _ancienne(), v73=False),
        _fiche(rd, _ancienne(**{"Cas d'usage": p_texte(GABARIT_FR), 'Prérequis': p_texte('Jupyter Notebook recent')}),
               v73=False),
        _fiche(rd, {'Description': p_texte('GitHub project'), 'Justification': p_texte()}),
        _fiche(rd, {'Description': p_texte('Projet GitHub.'), "Cas d'usage": p_texte(GABARIT_EN)}),
    ]
    for f in fabriques:
        contenu = rd.contenu_fts(f)
        tout = '\n'.join(contenu.values()).casefold()
        for gabarit in ('see documentation', 'see docs', 'python recent', 'jupyter notebook recent',
                        'task automation', 'ajustement fin', 'github project', 'projet github', 'pip install outil'):
            assert gabarit not in tout, (gabarit, contenu)
        assert contenu['type'] == ''


def test_non_verifie_jamais_indexe(banc):
    rd = banc.rd
    colonnes = dict(SCHEMA_GITNOTATE, Licence='select')
    for valeur in ('Non vérifié', 'Non vérifiée', 'Non renseignée', 'non verifie'):
        f = _fiche(rd, {'Exemple': p_texte(valeur), 'Licence': p_select(valeur), 'Description': p_texte(valeur)},
                   colonnes)
        for champ in ('Exemple', 'Licence', 'Description'):
            assert f.champs[champ].fiabilite == 'non_verifie'
        contenu = rd.contenu_fts(f)
        assert contenu['exemple'] == contenu['licence'] == contenu['description'] == ''
    vide = _fiche(rd, {"Cas d'usage": p_texte('• Aucun cas d\'usage identifié\n• N/A')})
    assert vide.champs["Cas d'usage"].fiabilite == 'non_verifie'
    index_du_corpus(rd)
    assert requete_fts(rd, '"non verifie"') == {} and requete_fts(rd, '"non renseignee"') == {}


def test_v72nv_exemple_verifie_indexe(banc):
    rd = banc.rd
    f = _fiche(rd, {'Justification': p_texte('[LLM m · profil 1a2b3c] Avis.'), 'Prérequis': p_texte('Non vérifié'),
                    'Exemple': p_texte('from docling import DocumentConverter'),
                    "Cas d'usage": p_texte(GABARIT_EN)})
    assert f.provenance.famille == 'v7.2-nv'
    assert f.champs['Exemple'].fiabilite == 'readme'
    assert f.champs["Cas d'usage"].fiabilite == 'gabarit'
    contenu = rd.contenu_fts(f)
    assert contenu['exemple'] == 'from docling import DocumentConverter' and contenu['cas_usage'] == ''


def test_description_lexicale_et_anglaise(banc):
    rd = banc.rd
    lexicale = fiche_du_corpus(rd, 'A49', CORPUS)
    assert lexicale.champs['Description'].fiabilite == 'github'
    assert 'description-anglaise' not in lexicale.provenance.drapeaux
    anglaise = fiche_du_corpus(rd, 'A20', CORPUS)
    assert anglaise.champs['Description'].fiabilite == 'github'
    assert 'description-anglaise' in anglaise.provenance.drapeaux
    traduite = fiche_du_corpus(rd, 'A01', CORPUS)
    assert traduite.champs['Description'].fiabilite == 'llm'
    # Repli lexical avec une description française : GitHub d'origine ou traduction LLM (non établi)
    francaise = _fiche(rd, {'Justification': p_texte('[LEXICAL · profil v1/abcdef]'),
                            'Description': p_texte('Bibliothèque pour convertir des PDF en Markdown.')})
    assert francaise.champs['Description'].fiabilite == 'inconnu'


def test_cas_usage_ancien_reecrit_par_utilisateur(banc):
    rd = banc.rd
    reecrit = _fiche(rd, _ancienne(**{"Cas d'usage": p_texte(rt('• Extraire les tableaux des DPGF'),
                                                             rt(' en PDF', bold=True))}), v73=False)
    ch = reecrit.champs["Cas d'usage"]
    assert ch.modifie and ch.fiabilite == 'utilisateur'
    assert rd.contenu_fts(reecrit)['cas_usage'] == '• Extraire les tableaux des DPGF en PDF'
    gabarit_modifie = _fiche(rd, _ancienne(**{"Cas d'usage": p_texte(rt(GABARIT_EN, bold=True))}), v73=False)
    assert gabarit_modifie.champs["Cas d'usage"].fiabilite == 'gabarit'
    non_modifie = _fiche(rd, _ancienne(**{"Cas d'usage": p_texte('• Extraire les tableaux des DPGF')}), v73=False)
    assert non_modifie.champs["Cas d'usage"].fiabilite == 'gabarit'


def test_statut_par_defaut_non_signal(banc):
    rd = banc.rd
    assert _fiche(rd, {'Statut': p_select('À explorer')}).champs['Statut'].fiabilite == 'defaut'
    en_test = _fiche(rd, {'Statut': p_select('En test')})
    assert en_test.champs['Statut'].fiabilite == 'utilisateur'
    assert 'statut' not in rd.COLONNES_FTS
    assert all('En test' not in texte for texte in rd.contenu_fts(en_test).values())


def test_prefixe_justification_non_indexe(banc):
    rd = banc.rd
    index_du_corpus(rd)
    for expression in ('justification : "profil 2026 10 11"', 'justification : "8c41d2"', 'justification : mistral',
                       'justification : lexical', '"u1 p3 t1 i2 c1 m2 l"', 'justification : "non note"'):
        assert requete_fts(rd, expression) == {}, expression
    for (texte,) in lignes(rd, 'SELECT justification FROM recherche'):
        assert not texte.startswith('[')
    # « LLM » ne trouve que des fiches dont l'avis parle de LLM, jamais une fiche par son préfixe « [LLM … »
    trouvees = lignes(rd, "SELECT justification FROM recherche WHERE recherche MATCH 'justification : llm'")
    assert all('llm' in texte.casefold() for (texte,) in trouvees)
    prefixe_llm = lignes(rd, "SELECT count(*) FROM fiches WHERE methode = 'LLM'")[0][0]
    assert 0 < len(trouvees) < prefixe_llm


# =============================================================================
# G. Doublons
# =============================================================================
def test_meme_depot_un_groupe_preuves_par_fiche(banc):
    rd = banc.rd
    index_du_corpus(rd)
    con = rd.ouvrir_index_lecture()
    try:
        fiches = rd.lire_fiches(con, 'cle_depot = ?', ('docling-project/docling',))
        assert len(fiches) == 4 and sum(f['principale'] for f in fiches) == 1
        principale = next(f for f in fiches if f['principale'])
        assert principale['famille'] == 'v7.3' and rd.ordonner_fiches(fiches)[0] is principale
        notes = dict(con.execute('SELECT rowid, notes FROM recherche'))
    finally:
        con.close()
    avec_tags = [f for f in fiches if f['autres'].get('Tags')]
    assert len(avec_tags) == 1 and 'Tags : OCR, PDF' in notes[avec_tags[0]['id']]
    sans_tags = [f for f in fiches if f is not avec_tags[0]]
    assert all('Tags' not in notes[f['id']] for f in sans_tags)


def test_fiche_principale_deterministe(banc):
    rd = banc.rd
    bases = charger_bases()
    cols = rd.resoudre_colonnes({n: t for cle in ('B', 'C', 'A') for n, t in schema_base(bases[cle]).items()})
    fiches = [rd.construire_fiche(rd.aplatir_page(p), cols) for p in pages_du_corpus(CORPUS)]
    reference = rd.fiches_principales(fiches)
    hasard = random.Random(4)
    for _ in range(5):
        melange = fiches[:]
        hasard.shuffle(melange)
        assert rd.fiches_principales(melange) == reference
    pages = pages_du_corpus(CORPUS)
    index_du_corpus(rd, list(reversed(pages)))
    inverse = {p for (p,) in lignes(rd, 'SELECT page_id FROM fiches WHERE principale = 1')}
    index_du_corpus(rd, pages)
    assert {p for (p,) in lignes(rd, 'SELECT page_id FROM fiches WHERE principale = 1')} == inverse == reference


def test_statut_utilisateur_conserve(banc):
    rd = banc.rd
    index_du_corpus(rd)
    con = rd.ouvrir_index_lecture()
    try:
        statuts = rd.statuts_du_depot(rd.lire_fiches(con, 'cle_depot = ?', ('docling-project/docling',)))
    finally:
        con.close()
    assert [(s['statut'], s['utilisateur'], s['fiches']) for s in statuts] == [('Utilisé', True, 2),
                                                                             ('À explorer', False, 2)]
    assert statuts[0]['analyse_le'] == '2026-01-14'


def test_homonymes_non_fusionnes_voir_aussi(banc):
    rd = banc.rd
    index_du_corpus(rd)
    cles = {c for (c,) in lignes(rd, "SELECT cle_depot FROM fiches WHERE nom_plie LIKE '%openhands%'")}
    assert cles == {'all-hands-ai/openhands', 'openhands/openhands'}
    con = rd.ouvrir_index_lecture()
    try:
        assert rd.voir_aussi(con, 'openhands/openhands') == [{'depot': 'all-hands-ai/openhands',
                                                              'nom': 'OpenHands (ancien nom)'}]
        assert rd.voir_aussi(con, 'all-hands-ai/openhands') == [{'depot': 'openhands/openhands', 'nom': 'OpenHands'}]
        assert rd.voir_aussi(con, 'huginn/huginn') == []
    finally:
        con.close()
    assert lignes(rd, "SELECT count(*) FROM fiches WHERE principale = 1 AND cle_depot LIKE '%openhands'")[0][0] == 2


def test_fiches_sans_depot_a_part(banc):
    rd = banc.rd
    index_du_corpus(rd)
    sans = lignes(rd, "SELECT nom, cle_depot, principale FROM fiches WHERE cle_depot LIKE 'page:%' "
                      "OR cle_depot LIKE 'url:%' ORDER BY nom")
    assert [(n, c.split(':')[0], p) for n, c, p in sans] == [('Idée : OCR des DPGF', 'page', 1),
                                                            ('explaingithub.com', 'url', 1)]
    meta = dict(lignes(rd, 'SELECT cle, valeur FROM meta'))
    assert meta['nb_sans_depot'] == '2'


def test_etat_doublons_et_anomalies(banc, capsys):
    rd = banc.rd
    index_du_corpus(rd)
    capsys.readouterr()
    assert banc.lancer('etat', '--doublons', '--anomalies') == 0
    sortie = capsys.readouterr().out
    assert 'Index de redécouverte' in sortie and 'Fiches      : 62 (' in sortie
    assert 'Versions    : v7.3+ ×16 · v7.2 ×5 · v7.0/v7.1 ×20 · ancienne ×18 · manuelle ×3' in sortie
    assert 'docling-project/docling (4 fiches)' in sortie and '[principale]' in sortie
    assert 'url_non_github' in sortie and 'url_absente' in sortie
    assert 'personnelles indexées : Tags, Notes' in sortie
    assert 'ignorées : Créé le (created_time), Favori (checkbox), Projet lié (relation)' in sortie
    assert 'le moteur ne supprime rien' in sortie
    assert banc.lancer('etat', '--format', 'json', '--doublons', '--anomalies') == 0
    etat = json.loads(capsys.readouterr().out)
    assert etat['fiches'] == 62 and etat['sans_depot'] == 2 and etat['depots_multiples'] == 6
    assert {d['depot'] for d in etat['doublons']} == {'docling-project/docling', 'huginn/huginn',
                                                       'ub-mannheim/tesseract', 'virattt/dexter',
                                                       'unclecode/crawl4ai', 'paddlepaddle/paddleocr'}
    assert all(sum(f['principale'] for f in d['fiches']) == 1 for d in etat['doublons'])
    assert {a['code'] for a in etat['anomalies']} == {'url_non_github', 'url_absente'}
    assert etat['familles']['v7.3'] == 16 and etat['moteur']['format_index'] == 1
