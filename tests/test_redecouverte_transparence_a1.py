"""Transparence A1 (P3) : « preuve directe de l'objet limitée à une étiquette ».

Une correspondance « forte » dont aucune notion objet du besoin (objets_du_besoin) n'a de preuve directe dans une
colonne de texte, sur aucune fiche du dépôt, alors qu'une étiquette de classification (Catégorie, Brique pour, Type)
en porte une, reçoit une entrée `preuve_objet_etiquette_seule` en fin de « À vérifier ». C'est une information : le
niveau, le score, la couverture, le rang et l'ordre des résultats ne changent jamais.

T1 : population exacte (cas positifs et négatifs). T2 : aucun effet de bord, sorties identiques hors de la
population. T3 : jeux historiques N, M et R, garde-fou mécanique des 11 couples avertis (pas une mesure de
pertinence). Données fictives, hors ligne, aucune base Notion réelle.
"""
import copy
import json
import re
import uuid

import pytest
from redecouverte_outils import (
    FIXTURES, charger_corpus, index_du_corpus, p_multi, p_select, p_texte, page, pages_du_corpus,
    pages_du_supplement, preparer,
)

CODE = 'preuve_objet_etiquette_seule'
JUSTIF = "[LLM mistral-small-2603 · profil 2026-10-11/8c41d2] U1·P3·T2·I2·C2·M2·L2 = 9 — "
TEXTE_CATEGORIE = ("Preuve directe de l'objet « OCR » limitée à une étiquette (Catégorie) : la correspondance reste "
                   "forte selon le calcul lexical ; cette étiquette ne suffit pas à attester la fonction du dépôt. "
                   "Vérifiez la description et les cas d'usage.")


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


def _fiche(nom, url=None, cree='2026-10-11T08:00:00.000Z', **props):
    """Fiche v7.3 fictive dont aucun texte ne parle d'OCR ; props ajoute ou remplace des colonnes."""
    proprietes = {'Description': p_texte("Outil de démonstration pour ranger des fichiers."),
                  "Cas d'usage": p_texte("• Ranger des fichiers de démonstration"),
                  'Installation': p_texte('pip install demonstration'),
                  'Justification': p_texte(JUSTIF + 'Avis de test.')}
    proprietes.update(props)
    return page(nom, url or f'https://github.com/test/{nom}', props=proprietes, cree=cree)


def _fiche_ancienne(nom, **props):
    """Fiche d'une première version de Gitnotate (modèle : A01 du corpus synthétique, sans Justification), dont
    aucun texte ne parle d'OCR ; props ajoute ou remplace des colonnes."""
    modele = copy.deepcopy(next(c['page'] for c in charger_corpus() if c['id_corpus'] == 'A01'))
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f'transparence-a1|{nom}'))
    modele.update({'id': pid, 'url': 'https://www.notion.so/' + pid.replace('-', '')})
    modele['properties'].update({'Nom': page(nom)['properties']['Nom'],
                                 'URL': page(nom, f'https://github.com/test/{nom}')['properties']['URL'],
                                 'Description': p_texte("Outil de démonstration pour ranger des fichiers."),
                                 'Notes': p_texte(), 'Type': p_multi(), **props})
    return modele


def _chercher(rd, texte, tout=False, filtres=None, limite=50):
    con, meta = rd.ouvrir_index_valide()
    try:
        reponse = rd.rechercher(con, rd.analyser_requete(texte), filtres or {}, limite, tout, meta)
        rd.expliquer(con, reponse)
    finally:
        con.close()
    return reponse


def _resultat(reponse, cle):
    return next(r for r in reponse.affiches if r.cle == cle)


def _alertes(r):
    return [a for a in r.a_verifier if a['code'] == CODE]


def _bloc(texte, cle):
    """Lignes d'un résultat dans le rendu texte : de sa ligne de titre à la ligne de titre suivante."""
    lignes = texte.splitlines()
    debut = next(i for i, ligne in enumerate(lignes) if f' — {cle} — ' in ligne)
    fin = next((i for i in range(debut + 1, len(lignes)) if re.match(r'\d+\. ', lignes[i])), len(lignes))
    return '\n'.join(lignes[debut:fin])


def _objets(rd, reponse):
    actifs = [c for c in reponse.requete.concepts if not c.retire]
    return [c.cle for c in rd.objets_du_besoin(actifs, rd.ensembles_niveau(actifs)[0])]

# =============================================================================
# Prédicat seul : partition des colonnes et règles (preuves construites à la main)
# =============================================================================
def test_partition_des_colonnes(banc):
    rd = banc.rd
    etiquettes, textes = set(rd.COLONNES_ETIQUETTES), set(rd.COLONNES_TEXTE_OBJET)
    assert etiquettes == {'categorie', 'brique_pour', 'type'}
    assert not etiquettes & textes and 'justification' not in etiquettes | textes
    assert etiquettes | textes | {'justification'} == set(rd.COLONNES_FTS)


def _concept(rd, cle, classe='essentiel'):
    return rd.Concept(cle, cle, [cle], [cle.upper()], classe, 'normal')


def _preuve(rd, rowid, colonnes, mode='direct'):
    factuelle = any(c != 'justification' for c in colonnes)
    m = (1.0 if factuelle else rd.FACTEUR_JUSTIFICATION) * (rd.FACTEUR_VOISIN if mode == 'voisin' else 1.0)
    return rd.Preuve(rowid, mode, list(colonnes), [], {}, 1.0, m, -1.0)


def _forte(rd, preuves, niveau='forte', cle='test/outil'):
    r = rd.Resultat(cle, cle, sorted({p.rowid for par in preuves.values() for p in par}), niveau=niveau)
    r.preuves = {c: {p.rowid: p for p in par} for c, par in preuves.items()}
    return r


def test_predicat_regles(banc):
    rd = banc.rd
    ocr, pdf = _concept(rd, 'ocr'), _concept(rd, 'pdf')      # « windows » : notion hors objet (clé de preuve seule)
    alerte = rd.preuve_objet_etiquette_seule
    # étiquette seule, chacune des trois colonnes
    for colonne in ('categorie', 'brique_pour', 'type'):
        a = alerte(_forte(rd, {'ocr': [_preuve(rd, 1, [colonne])]}), [ocr])
        assert a['code'] == CODE and a['concepts'] == ['ocr'] and a['colonnes'] == [colonne]
    # plusieurs étiquettes et plusieurs fiches : une seule entrée, colonnes dans l'ordre de COLONNES_ETIQUETTES
    a = alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['type', 'brique_pour']), _preuve(rd, 2, ['categorie'])]}), [ocr])
    assert a['colonnes'] == ['categorie', 'brique_pour', 'type']
    # une colonne de texte, sur la même fiche ou sur une autre fiche du dépôt, évite l'entrée
    for colonne in rd.COLONNES_TEXTE_OBJET:
        assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie', colonne])]}), [ocr]) is None
        assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie']), _preuve(rd, 2, [colonne])]}), [ocr]) is None
    # Justification, preuve voisine et notion hors de l'objet n'évitent pas l'entrée
    assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie', 'justification'])]}), [ocr]) is not None
    assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie']), _preuve(rd, 2, ['description'], 'voisin')]}),
                  [ocr]) is not None
    assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie'])], 'windows': [_preuve(rd, 1, ['description'])]}),
                  [ocr]) is not None
    # deux notions objet : un texte pour l'une suffit ; deux étiquettes : une entrée qui nomme les deux
    assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie'])], 'pdf': [_preuve(rd, 1, ['description'])]}),
                  [ocr, pdf]) is None
    deux = alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie'])], 'pdf': [_preuve(rd, 1, ['brique_pour'])]}),
                  [ocr, pdf])
    assert deux['concepts'] == ['ocr', 'pdf'] and deux['colonnes'] == ['categorie', 'brique_pour']
    assert deux['texte'].startswith("Preuve directe des objets « OCR » et « PDF » limitée à des étiquettes "
                                    "(Catégorie / Brique pour) : ")
    assert 'ces étiquettes ne suffisent pas' in deux['texte']
    # aucun niveau autre que « forte », aucune notion objet, aucune preuve directe d'étiquette : rien
    for niveau in ('partielle', 'faible', 'filtre'):
        assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie'])]}, niveau), [ocr]) is None
    assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie'])]}), []) is None
    assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['justification'])]}), [ocr]) is None
    assert alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['categorie'], 'voisin')]}), [ocr]) is None
    # résultat sans dépôt GitHub : même règle, « ressource » au lieu de « dépôt »
    sans = alerte(_forte(rd, {'ocr': [_preuve(rd, 1, ['brique_pour'])]}, cle='url:https://gitlab.com/test/outil'),
                  [ocr])
    assert 'la fonction de la ressource' in sans['texte']


def test_predicat_ne_modifie_rien(banc):
    rd = banc.rd
    r = _forte(rd, {'ocr': [_preuve(rd, 1, ['categorie'])], 'windows': [_preuve(rd, 1, ['description'])]})
    r.score, r.couverture, r.m, r.contributions = 0.8, 0.9, {'ocr': 1.0}, {'ocr': 2.0}
    avant = repr(r)
    assert rd.preuve_objet_etiquette_seule(r, [_concept(rd, 'ocr')]) is not None
    assert repr(r) == avant

# =============================================================================
# T1 : index fictif, moteur complet (rechercher puis expliquer)
# =============================================================================
@pytest.mark.parametrize('colonne, props, champ', [
    ('categorie', {'Catégorie': p_select('OCR/Documents')}, 'Catégorie'),
    ('brique_pour', {'Brique pour': p_multi('Documents et OCR')}, 'Brique pour'),
    ('type', {'Type': p_multi('OCR')}, 'Type'),
])
def test_etiquette_seule_une_alerte(banc, colonne, props, champ):
    rd = banc.rd
    index_du_corpus(rd, [_fiche('etiquette', **props), _fiche('temoin')])
    reponse = _chercher(rd, 'un OCR')
    assert _objets(rd, reponse) == ['ocr']
    r = _resultat(reponse, 'test/etiquette')
    assert r.niveau == 'forte' and r.rang == 1
    assert [p.colonnes for p in r.preuves['ocr'].values()] == [[colonne]]
    alertes = _alertes(r)
    assert len(alertes) == 1 and alertes[0]['concepts'] == ['ocr'] and alertes[0]['colonnes'] == [colonne]
    assert f"limitée à une étiquette ({champ}) : la correspondance reste forte" in alertes[0]['texte']
    assert r.a_verifier[-1] is alertes[0]                 # ajoutée après les autres lignes, ordre conservé


def test_plusieurs_etiquettes_plusieurs_fiches_une_seule_alerte(banc):
    rd = banc.rd
    url = 'https://github.com/test/mixte'
    index_du_corpus(rd, [_fiche('mixte', url, Catégorie=p_select('OCR/Documents')),
                         _fiche('mixte', url, '2026-10-12T08:00:00.000Z', **{'Brique pour': p_multi('OCR'),
                                                                             'Type': p_multi('OCR')})])
    r = _resultat(_chercher(rd, 'un OCR'), 'test/mixte')
    assert r.niveau == 'forte' and len(r.fiches) == 2
    alertes = _alertes(r)
    assert len(alertes) == 1 and alertes[0]['colonnes'] == ['categorie', 'brique_pour', 'type']
    assert "limitée à des étiquettes (Catégorie / Brique pour / Type)" in alertes[0]['texte']
    assert "ces étiquettes ne suffisent pas" in alertes[0]['texte']


TEXTES = [
    ('description', {'Description': p_texte("Moteur OCR pour ranger des fichiers.")}),
    ('cas_usage', {"Cas d'usage": p_texte("• Passer des fichiers à l'OCR")}),
    ('nom', {}),
    ('installation', {'Installation': p_texte('pip install moteur-ocr')}),
    ('exemple', {'Exemple': p_texte('moteur scan.png --ocr')}),
    ('prerequis', {'Prérequis': p_texte('- Un moteur OCR installé')}),
    ('langage', {'Langage': p_select('OCR')}),
    ('licence', {'Licence': p_select('OCR Public License')}),
    ('notes', {'Tags': p_multi('OCR')}),                  # étiquette personnelle : colonne personnelle, donc texte
]


@pytest.mark.parametrize('colonne, props', TEXTES, ids=[t[0] for t in TEXTES])
def test_preuve_textuelle_evite_l_alerte(banc, colonne, props):
    rd = banc.rd
    nom = 'lecteur-ocr' if colonne == 'nom' else 'lecteur'
    index_du_corpus(rd, [_fiche(nom, Catégorie=p_select('OCR/Documents'), **props),
                         _fiche('temoin', Catégorie=p_select('OCR/Documents'))])
    reponse = _chercher(rd, 'un OCR')
    r = _resultat(reponse, f'test/{nom}')
    assert r.niveau == 'forte'
    assert colonne in next(iter(r.preuves['ocr'].values())).colonnes
    assert _alertes(r) == []
    assert len(_alertes(_resultat(reponse, 'test/temoin'))) == 1          # même étiquette, sans le texte


def test_preuve_textuelle_sur_une_autre_fiche_du_depot(banc):
    rd = banc.rd
    url = 'https://github.com/test/deux-fiches'
    index_du_corpus(rd, [_fiche('deux-fiches', url, Catégorie=p_select('OCR/Documents')),
                         _fiche('deux-fiches', url, '2026-10-12T08:00:00.000Z',
                                Description=p_texte("Moteur OCR de démonstration."))])
    r = _resultat(_chercher(rd, 'un OCR'), 'test/deux-fiches')
    assert r.niveau == 'forte' and len(r.fiches) == 2 and _alertes(r) == []


def test_deux_objets_et_notion_hors_objet(banc):
    rd = banc.rd
    index_du_corpus(rd, [_fiche('lecteur-pdf', Catégorie=p_select('OCR/Documents'),
                                Description=p_texte("Lit les fichiers PDF.")),
                         _fiche('sous-windows', Catégorie=p_select('OCR/Documents'),
                                Description=p_texte("Fonctionne sous Windows."))])
    deux = _chercher(rd, 'un OCR pour PDF')
    assert _objets(rd, deux) == ['ocr', 'pdf']
    r = _resultat(deux, 'test/lecteur-pdf')
    assert r.niveau == 'forte' and _alertes(r) == []      # l'autre notion objet est écrite dans la Description
    contrainte = _chercher(rd, 'un OCR sous Windows')
    assert _objets(rd, contrainte) == ['ocr'] and 'windows' in {c.cle for c in contrainte.requete.concepts}
    r = _resultat(contrainte, 'test/sous-windows')
    assert r.niveau == 'forte' and 'description' in next(iter(r.preuves['windows'].values())).colonnes
    assert [a['concepts'] for a in _alertes(r)] == [['ocr']]     # Windows n'est pas l'objet du besoin


def test_justification_et_voisin_n_evitent_pas_l_alerte(banc):
    rd = banc.rd
    url = 'https://github.com/test/voisin'
    index_du_corpus(rd, [_fiche('avis', Catégorie=p_select('OCR/Documents'),
                                Justification=p_texte(JUSTIF + 'Un OCR utile.')),
                         _fiche('voisin', url, Catégorie=p_select('OCR/Documents')),
                         _fiche('voisin', url, '2026-10-12T08:00:00.000Z',
                                Description=p_texte("Lit des pages scannées."))])
    reponse = _chercher(rd, 'un OCR')
    avis = _resultat(reponse, 'test/avis')
    assert next(iter(avis.preuves['ocr'].values())).colonnes == ['categorie', 'justification']
    assert avis.niveau == 'forte' and len(_alertes(avis)) == 1
    voisin = _resultat(reponse, 'test/voisin')
    assert sorted(p.mode for p in voisin.preuves['ocr'].values()) == ['direct', 'voisin']
    assert voisin.niveau == 'forte' and len(_alertes(voisin)) == 1


def test_negation_non_reintroduite(banc):
    rd = banc.rd
    index_du_corpus(rd, [_fiche('sans-lecture', Catégorie=p_select('OCR/Documents'),
                                Description=p_texte("Cet outil ne fait pas d'OCR."))])
    r = _resultat(_chercher(rd, 'un OCR'), 'test/sans-lecture')
    p = next(iter(r.preuves['ocr'].values()))
    assert 'description' in p.niees and p.colonnes == ['categorie']
    assert r.niveau == 'forte' and len(_alertes(r)) == 1


def test_forte_retrogradee_par_exclusion_sans_alerte(banc):
    rd = banc.rd
    index_du_corpus(rd, [_fiche('avec-docker', Catégorie=p_select('OCR/Documents'),
                                Prérequis=p_texte('- Docker 24+'))])
    sans = _resultat(_chercher(rd, 'un OCR sans Docker'), 'test/avec-docker')
    assert sans.niveau == 'partielle' and [x['etat'] for x in sans.exclusions] == ['requis']
    assert _alertes(sans) == []
    avec = _resultat(_chercher(rd, 'un OCR'), 'test/avec-docker')
    assert avec.niveau == 'forte' and len(_alertes(avec)) == 1


def test_partielle_et_liste_filtree_sans_alerte(banc):
    rd = banc.rd
    index_du_corpus(rd, [_fiche('scanneur', Catégorie=p_select('Documents scannés')),
                         _fiche('etiquette', Catégorie=p_select('OCR/Documents'))])
    reponse = _chercher(rd, 'un OCR', tout=True)
    partielle = _resultat(reponse, 'test/scanneur')
    assert partielle.niveau == 'partielle' and _alertes(partielle) == []
    liste = _chercher(rd, 'un')
    assert not liste.requete.concepts and {r.niveau for r in liste.affiches} == {'filtre'}
    assert all(_alertes(r) == [] for r in liste.affiches)


def test_fiche_sans_depot_ancienne_et_colonne_personnelle(banc):
    rd = banc.rd
    ancienne = _fiche_ancienne('ancien-outil', **{'Brique pour': p_multi('Documents et OCR')})
    index_du_corpus(rd, [_fiche('hors-github', 'https://gitlab.com/test/hors-github',
                                **{'Brique pour': p_multi('Documents et OCR')}),
                         ancienne,
                         _fiche('tags', Catégorie=p_select('OCR/Documents'), Tags=p_multi('OCR'))])
    reponse = _chercher(rd, 'un OCR')
    hors = next(r for r in reponse.sans_depot if r.principale['nom'] == 'hors-github')
    assert hors.niveau == 'forte' and [a['colonnes'] for a in _alertes(hors)] == [['brique_pour']]
    assert 'la fonction de la ressource' in _alertes(hors)[0]['texte']
    vieux = _resultat(reponse, 'test/ancien-outil')
    assert vieux.principale['famille'] == 'ancienne' and vieux.niveau == 'forte'
    assert [a['colonnes'] for a in _alertes(vieux)] == [['brique_pour']]
    assert _alertes(_resultat(reponse, 'test/tags')) == []

# =============================================================================
# Rendus : texte, --details, Markdown, JSON (une ligne par résultat éligible, rien ailleurs)
# =============================================================================
def test_rendus_texte_details_markdown_json(banc, capsys):
    rd = banc.rd
    index_du_corpus(rd, [_fiche('etiquette', Catégorie=p_select('OCR/Documents')),
                         _fiche('decrit', Description=p_texte("Moteur OCR de démonstration."))])
    reponse = _chercher(rd, 'un OCR')
    for details in (False, True):
        texte = rd.en_texte(reponse, details)
        assert texte.count("Preuve directe de l'objet « OCR »") == 1
        assert "     - Preuve directe de l'objet « OCR » limitée à une étiquette (Catégorie)" in _bloc(texte, 'test/etiquette')
        assert 'Preuve directe' not in _bloc(texte, 'test/decrit')
    markdown = rd.en_markdown(reponse)
    assert markdown.count("Preuve directe de l'objet « OCR »") == 1
    assert f"  - {rd._md(TEXTE_CATEGORIE)}" in markdown
    donnees = json.loads(json.dumps(rd.en_json(reponse), ensure_ascii=False))
    par_depot = {r['depot']: r for r in donnees['resultats']}
    assert par_depot['test/etiquette']['a_verifier'][-1] == {'code': CODE, 'texte': TEXTE_CATEGORIE,
                                                            'concepts': ['ocr'], 'colonnes': ['categorie']}
    assert all(a['code'] != CODE for a in par_depot['test/decrit']['a_verifier'])
    assert banc.lancer('cherche', 'un OCR', '--format', 'json') == 0
    sortie = json.loads(capsys.readouterr().out)
    assert [a['code'] for r in sortie['resultats'] for a in r['a_verifier']].count(CODE) == 1

# =============================================================================
# T2 : aucun effet de bord ; hors population, sorties identiques à l'octet
# =============================================================================
def _photo(rd, reponse):
    """Tout ce que produit la recherche et l'explication, entrées A1 retirées de « À vérifier »."""
    resultats = []
    for r in reponse.affiches:
        resultats.append({
            'cle': r.cle, 'rang': r.rang, 'niveau': r.niveau, 'score': r.score, 'couverture': r.couverture,
            'contributions': r.contributions, 'm': r.m, 'rowids': r.rowids,
            'preuves': {c: {i: (p.mode, p.colonnes, p.niees, p.m) for i, p in par.items()} for c, par in r.preuves.items()},
            'repond_a': r.repond_a, 'indices_faibles': r.indices_faibles, 'ne_couvre_pas': r.ne_couvre_pas,
            'extraits': r.extraits, 'etabli': r.etabli, 'etabli_note': r.etabli_note,
            'a_verifier': [a for a in r.a_verifier if a['code'] != CODE], 'statuts': r.statuts,
            'voir_aussi': r.voir_aussi, 'exclusions': r.exclusions})
    q = reponse.requete
    concepts = [(c.cle, c.classe, c.role, c.poids, c.idf, c.retire, c.df, c.mentionne, c.par_voisin) for c in q.concepts]
    return json.dumps({'concepts': concepts, 'ignores': q.ignores, 'nies': q.nies, 'tronques': q.tronques,
                       'exclusions': q.exclusions, 'indifferents': q.indifferents, 'resultats': resultats,
                       'non_affiches': reponse.non_affiches, 'absents': reponse.absents,
                       'par_voisin': reponse.par_voisin}, ensure_ascii=False, sort_keys=True, default=str)


def test_aucun_effet_de_bord_sur_le_corpus(banc, monkeypatch):
    """Requêtes de référence sur le corpus synthétique : avec ou sans l'avertissement, tout est identique sauf
    l'entrée A1 ajoutée en dernier ; une requête sans résultat éligible donne texte, Markdown et JSON identiques."""
    rd = banc.rd
    index_du_corpus(rd)
    requetes = json.loads((FIXTURES / 'requetes.json').read_text(encoding='utf-8'))['requetes']
    assert len(requetes) >= 30
    reel = rd.preuve_objet_etiquette_seule
    eligibles = 0
    for q in requetes:
        texte = q['id']
        avec = _chercher(rd, q['requete'], True, q['options'])
        monkeypatch.setattr(rd, 'preuve_objet_etiquette_seule', lambda r, objets: None)
        sans = _chercher(rd, q['requete'], True, q['options'])
        monkeypatch.setattr(rd, 'preuve_objet_etiquette_seule', reel)
        assert _photo(rd, avec) == _photo(rd, sans), texte
        alertes = [(r, a) for r in avec.affiches for a in r.a_verifier if a['code'] == CODE]
        for r, a in alertes:
            assert r.niveau == 'forte' and r.a_verifier[-1] is a and len(_alertes(r)) == 1, texte
        if alertes:
            eligibles += 1
            continue
        assert rd.en_texte(avec) == rd.en_texte(sans) and rd.en_texte(avec, True) == rd.en_texte(sans, True), texte
        assert rd.en_markdown(avec) == rd.en_markdown(sans), texte
        assert json.dumps(rd.en_json(avec), sort_keys=True) == json.dumps(rd.en_json(sans), sort_keys=True), texte
    assert 0 < eligibles < len(requetes)           # les deux cas sont exercés (H05 : étiquette seule)


# =============================================================================
# T3 : témoins historiques N, M, R (garde-fou mécanique, pas une mesure de pertinence)
# =============================================================================
TEMOINS = {
    'N': {'N05-03': 'huginn/huginn', 'N14-04': 'docling-project/docling', 'N27-02': 'synth-pdfstack/pdf-toolbox-server',
          'N27-03': 'synth-notesearch/semantic-drive', 'N27-04': 'synth-nodeforge/n8n-nodes-pdfgen'},
    'M': {'M24-01': 'synth-eurocalc/ba-ec2', 'M24-02': 'rdumasia303/deepseek_ocr_app',
          'M24-03': 'synth-chantierlab/planchantier'},
    'R': {'R15-03': 'synth-k8sjobs/whisper-k8s-batch', 'R26-02': 'synth-nodeforge/n8n-nodes-pdfgen',
          'R39-04': 'synth-mailroom/inbox-parser'},
}
JEUX = {'N': (['lot5_supplement_N.json'], 'requetes_lot5_N.json', 75),
        'M': (['lot5_supplement_N.json', 'lot5_supplement_M.json'], 'requetes_lot5_M.json', 68),
        'R': (['lot5_supplement_N.json', 'lot5_supplement_M.json', 'qualification_lot6/jeu_R/supplement_R.json'],
              'qualification_lot6/jeu_R/requetes_R.json', 109)}


@pytest.mark.parametrize('jeu', sorted(JEUX))
def test_temoins_historiques(banc, jeu):
    """Jeux consommés N, M et R, limite de l'évaluateur : l'avertissement porte exactement sur les 11 couples dont la
    preuve directe de l'objet n'est qu'une étiquette, et les « forte » restent celles des traces (75, 68, 109)."""
    rd = banc.rd
    supplements, fichier, nb_fortes = JEUX[jeu]
    index_du_corpus(rd, pages_du_corpus() + [p for s in supplements for p in pages_du_supplement(s)])
    besoins = json.loads((FIXTURES / fichier).read_text(encoding='utf-8'))['requetes']
    avertis, fortes = {}, 0
    for q in besoins:
        reponse = _chercher(rd, q['requete'], filtres=q.get('options'), limite=rd.RESULTATS_MAX)
        fortes += sum(r.niveau == 'forte' for r in reponse.resultats)
        for r in reponse.affiches:
            alertes = _alertes(r)
            assert len(alertes) <= 1 and (not alertes or (r.niveau == 'forte' and r.a_verifier[-1] is alertes[0]))
            if alertes:
                avertis[f"{q['id']}-{r.rang:02d}"] = r.cle
    assert fortes == nb_fortes
    assert avertis == TEMOINS[jeu]

# =============================================================================
# Levée des réserves de la revue indépendante : L2 (repli des notions objet) et L1 (Justification)
# =============================================================================
def test_repli_des_notions_objet_type_seul(banc, monkeypatch):
    """L2 : un mot hors lexique (« zorglub ») est l'objet du besoin par repli (objets_du_besoin, faute de notion
    essentielle du lexique). Prouvé par le seul Type, il reçoit exactement une alerte, objet « zorglub », colonne
    type ; l'alerte ne change ni le niveau, ni le score, ni la couverture, ni le rang. Un avertissement calculé sur
    les seules notions essentielles du lexique (mutant X2 de la revue) n'en produit aucune."""
    rd = banc.rd
    index_du_corpus(rd, [_fiche('rangeur', Type=p_multi('zorglub')), _fiche('temoin')])
    reponse = _chercher(rd, 'un outil zorglub')
    actifs = [c for c in reponse.requete.concepts if not c.retire]
    assert [(c.cle, c.classe, c.role) for c in actifs] == [('zorglub', 'libre', 'normal')]
    assert _objets(rd, reponse) == ['zorglub']                   # repli : aucune notion essentielle du lexique
    r = _resultat(reponse, 'test/rangeur')
    assert r.niveau == 'forte' and r.rang == 1
    assert [p.colonnes for p in r.preuves['zorglub'].values()] == [['type']]
    alertes = _alertes(r)
    assert len(alertes) == 1, "objet de repli ignoré par l'avertissement"
    assert alertes[0]['concepts'] == ['zorglub'] and alertes[0]['colonnes'] == ['type']
    assert alertes[0]['texte'].startswith("Preuve directe de l'objet « zorglub » limitée à une étiquette (Type) : ")
    assert r.a_verifier[-1] is alertes[0]
    monkeypatch.setattr(rd, 'preuve_objet_etiquette_seule', lambda r, objets: None)
    sans = _resultat(_chercher(rd, 'un outil zorglub'), 'test/rangeur')
    assert (sans.niveau, sans.score, sans.couverture, sans.rang) == (r.niveau, r.score, r.couverture, r.rang)
    assert sans.a_verifier == r.a_verifier[:-1]


def test_justification_avis_du_llm_ou_saisie_par_vous(banc):
    """L1 : la même phrase en Justification. Reconnue comme avis du LLM (préfixe Gitnotate), elle est indexée en
    colonne justification et n'évite pas l'alerte ; saisie sans préfixe, elle est indexée avec les colonnes
    personnelles (notes), compte comme du texte et l'évite. Le niveau reste « forte » dans les deux cas."""
    rd = banc.rd
    index_du_corpus(rd, [_fiche('avis-llm', Catégorie=p_select('OCR/Documents'),
                                Justification=p_texte(JUSTIF + 'Un OCR utile pour les factures.')),
                         _fiche('avis-saisi', Catégorie=p_select('OCR/Documents'),
                                Justification=p_texte('Un OCR utile pour les factures.'))])
    reponse = _chercher(rd, 'un OCR')
    llm, saisi = _resultat(reponse, 'test/avis-llm'), _resultat(reponse, 'test/avis-saisi')
    assert llm.principale['champs']['Justification']['fiabilite'] == 'avis_llm'
    assert saisi.principale['champs']['Justification']['fiabilite'] == 'utilisateur'
    assert [p.colonnes for p in llm.preuves['ocr'].values()] == [['categorie', 'justification']]
    assert [p.colonnes for p in saisi.preuves['ocr'].values()] == [['categorie', 'notes']]
    assert llm.niveau == saisi.niveau == 'forte'
    assert [a['colonnes'] for a in _alertes(llm)] == [['categorie']]
    assert _alertes(saisi) == []

# =============================================================================
# X2b : repli des notions objet sur le rôle contexte (objets_du_besoin, deuxième repli)
# =============================================================================
def test_repli_des_notions_objet_role_contexte(banc, monkeypatch):
    """X2b : « en Python pour mes vidéos ». Le seul essentiel est une contrainte (Python) : aucun essentiel n'est une
    notion essentielle du lexique, l'objet du besoin est donc la notion essentielle de rôle contexte « vidéos »
    (deuxième repli d'objets_du_besoin), et non le repli final sur les essentiels (Python). Prouvée par le seul Type
    d'une des deux fiches du dépôt, alors que Python est écrit dans le Langage des deux : exactement une alerte, objet
    « video », colonne type, en dernier ; elle ne change ni le niveau, ni le score, ni la couverture, ni le rang, ni
    les preuves, ni les autres lignes. Un avertissement qui sauterait ce repli (mutant X2b) retomberait sur Python,
    prouvé par du texte, et n'en produirait aucune. Pages fictives ; valeurs mesurées sur le moteur."""
    rd = banc.rd
    url = 'https://github.com/test/monteur'
    index_du_corpus(rd, [_fiche('monteur', url, Type=p_multi('Vidéo'), Langage=p_select('Python')),
                         _fiche('monteur', url, '2026-10-12T08:00:00.000Z', Langage=p_select('Python')),
                         _fiche('temoin')])
    reponse = _chercher(rd, 'en Python pour mes vidéos')
    actifs = [c for c in reponse.requete.concepts if not c.retire]
    assert [(c.cle, c.classe, c.role) for c in actifs] == [('python', 'contrainte', 'normal'),
                                                          ('video', 'essentiel', 'contexte')]
    # premier repli inapplicable : l'unique essentiel est une contrainte, pas une notion essentielle du lexique
    assert [(c.cle, c.classe) for c in rd.ensembles_niveau(actifs)[0]] == [('python', 'contrainte')]
    assert _objets(rd, reponse) == ['video']               # deuxième repli (rôle contexte), pas ['python']
    r = _resultat(reponse, 'test/monteur')
    assert r.niveau == 'forte' and r.rang == 1 and len(r.fiches) == 2
    # l'objet n'est prouvé directement que par le Type d'une fiche : aucune colonne de texte, sur aucune des deux
    assert [(p.mode, p.colonnes) for p in r.preuves['video'].values()] == [('direct', ['type'])]
    assert [(p.mode, p.colonnes) for p in r.preuves['python'].values()] == [('direct', ['langage'])] * 2
    alertes = _alertes(r)
    assert len(alertes) == 1, "objet du repli « rôle contexte » ignoré par l'avertissement (mutant X2b)"
    assert alertes[0]['concepts'] == ['video'] and alertes[0]['colonnes'] == ['type']
    assert alertes[0]['texte'].startswith("Preuve directe de l'objet « vidéos » limitée à une étiquette (Type) : ")
    assert r.a_verifier[-1] is alertes[0]

    def preuves(x):
        return {c: {i: (p.mode, p.colonnes, p.niees, p.m) for i, p in par.items()} for c, par in x.preuves.items()}

    monkeypatch.setattr(rd, 'preuve_objet_etiquette_seule', lambda r, objets: None)
    neutre = _chercher(rd, 'en Python pour mes vidéos')
    sans = _resultat(neutre, 'test/monteur')
    assert [x.cle for x in neutre.affiches] == [x.cle for x in reponse.affiches]
    assert (sans.niveau, sans.score, sans.couverture, sans.rang) == (r.niveau, r.score, r.couverture, r.rang)
    assert preuves(sans) == preuves(r)
    assert sans.a_verifier == r.a_verifier[:-1] and _alertes(sans) == []
    assert [a['code'] for a in sans.a_verifier] == ['non_verifie', 'licence_inconnue']
