"""Moteur de redécouverte — affinage de la pertinence (après les mesures du lot 4, défauts D1 à D5).

M. Invariant « Répond à » (aucune correspondance sans occurrence réelle) · N. Requête (contraintes,
références, possessifs, variantes, nombres) · O. Affichage des concepts absents · P. Seuils des requêtes
nouvelles (écrites avant tout résultat, attendus inchangés) · Q. Seconde revue contradictoire (objet du
besoin et mots hors lexique, féminin sans « e » ajouté, portée d'une comparaison, garde-fou au changement
de format, mot du seul propriétaire/dépôt).
"""
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from redecouverte_outils import (
    FIXTURES,
    SCHEMA_GITNOTATE,
    index_du_corpus,
    p_multi,
    p_texte,
    page,
    pages_du_corpus,
    pages_numerotees,
    preparer,
    schema,
)

REQUETES = json.loads((FIXTURES / 'requetes.json').read_text(encoding='utf-8'))['requetes']
PAR_ID = {q['id']: q for q in REQUETES}
NOUVELLES = [q for q in REQUETES if q['jeu'] == 'nouvelles']
JUSTIF = "[LLM mistral-small-2603 · profil 2026-10-11/8c41d2] U1·P3·T2·I2·C2·M2·L2 = 9 — Avis de test."


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


def _chercher(rd, texte, filtres=None, limite=50, tout=False, expliquer=True):
    con, meta = rd.ouvrir_index_valide()
    try:
        reponse = rd.rechercher(con, rd.analyser_requete(texte), filtres or {}, limite, tout, meta)
        if expliquer:
            rd.expliquer(con, reponse)
    finally:
        con.close()
    return reponse


def _concepts(rd, texte):
    return {c.cle: c for c in rd.analyser_requete(texte).concepts}


def _synchroniser(banc, pages, colonnes=None):
    if colonnes is not None:
        banc.notion.base = schema(colonnes)
    banc.notion.pages = pages
    assert banc.lancer('sync', '--accepter-baisse') == 0

# =============================================================================
# M. Invariant « Répond à »
# =============================================================================
def _texte_cite(rd, fiche, occurrence):
    """Texte stocké du champ cité : valeur de la colonne personnelle, titre (Nom) ou adresse (URL, pour un mot
    du seul propriétaire/dépôt) de la fiche, ou texte du champ."""
    if occurrence['colonne'] == 'nom':
        assert occurrence['champ'] in ('Nom', 'URL'), occurrence
        return fiche['champs'][occurrence['champ']]['texte']
    if occurrence['colonne'] == 'notes':
        if occurrence['champ'] in fiche['autres']:
            return fiche['autres'][occurrence['champ']]
        justification = fiche['champs']['Justification']
        assert occurrence['champ'] == 'Justification' and justification['fiabilite'] == 'utilisateur'
        return justification['texte']
    return fiche['champs'][occurrence['champ']]['texte']


def _termes_du_concept(concept, mode):
    """Termes FTS (sans guillemets) de l'expression qui a produit la preuve : (exacts, préfixes)."""
    termes = concept.termes if mode == 'direct' else concept.termes_voisins
    exacts = {t.strip('"') for t in termes if not t.endswith('*')}
    prefixes = {t[:-1].strip('"') for t in termes if t.endswith('*')}
    return exacts, prefixes


def verifier_repond_a(rd, reponse, contexte=''):
    """Pour chaque résultat affiché et chaque concept de « Répond à » (m > 0) : chaque champ cité contient une
    occurrence surlignée du concept dans le texte stocké de la fiche citée (sous-chaîne exacte, formée des
    termes de l'expression du concept), et le concept a un extrait, sauf raison : occurrence dans le seul
    Nom ou dans le seul propriétaire/dépôt (cité URL ; exclus des extraits) ou nombre maximal d'extraits
    atteint."""
    concepts = {c.cle: c for c in reponse.requete.concepts}
    verifies = 0
    for r in reponse.affiches:
        fiches = {f['page_id']: f for f in r.fiches}
        for entree in r.repond_a + r.indices_faibles:
            ou = (contexte, r.cle, entree['concept'])
            assert entree['m'] > 0 and entree['champs'], ou
            fiche = fiches[entree['page_id']]
            cites = {o['champ'] for o in entree['occurrences']}
            assert cites == set(entree['champs']), ou
            exacts, prefixes = _termes_du_concept(concepts[entree['concept']], entree['mode'])
            for o in entree['occurrences']:
                stocke = _texte_cite(rd, fiche, o)
                assert o['texte'] and stocke[o['debut']:o['fin']] == o['texte'], ou + (o,)
                forme = ' '.join(rd.jetons(o['texte']))
                assert forme in exacts or any(forme.startswith(p) for p in prefixes), ou + (o, forme)
                verifies += 1
        for entree in r.repond_a:
            ou = (contexte, r.cle, entree['concept'])
            extrait = any(entree['concept'] in e['concepts'] for e in r.extraits)
            nom_seul = set(entree['champs']) <= {'Nom', 'URL'}
            assert extrait or nom_seul or len(r.extraits) == rd.EXTRAITS_PAR_RESULTAT, ou
            if nom_seul:
                assert {o['colonne'] for o in entree['occurrences']} == {'nom'}, ou
            assert 'Notes' not in entree['champs'] or 'Notes' in fiches[entree['page_id']]['autres'], ou
    return verifies


def test_invariant_repond_a_sur_toutes_les_requetes(corpus):
    rd = corpus.rd
    total = 0
    for q in REQUETES:
        total += verifier_repond_a(rd, _chercher(rd, q['requete'], q['options'], tout=True), q['id'])
    for texte in ('notes', 'tags', 'Tags et notes', 'justification', 'Gérer les notes de mes élèves'):
        total += verifier_repond_a(rd, _chercher(rd, texte, tout=True), texte)
    assert total > 300


def test_noms_des_colonnes_personnelles_non_indexes(corpus):
    """D1 : « notes » ou « tags » ne trouvent plus toute fiche qui a une valeur dans ces colonnes."""
    rd = corpus.rd
    for mot in ('notes', 'tags', 'justification'):
        reponse = _chercher(rd, mot, tout=True)
        for r in reponse.affiches:
            for f in r.fiches:
                valeurs = list(f['autres'].values())
                justification = f['champs'].get('Justification') or {}
                if justification.get('fiabilite') == 'utilisateur':
                    valeurs.append(justification['texte'])
                if any(e['page_id'] == f['page_id'] and 'Notes' in e['champs'] for e in r.repond_a):
                    assert any(mot in rd.jetons(v) or any(t.startswith(mot[:-1]) for t in rd.jetons(v))
                               for v in valeurs), (mot, r.cle)
    tags = _chercher(rd, 'tags', tout=True)
    assert not any(e['champs'] == ['Tags'] for r in tags.affiches for e in r.repond_a)
    n06 = _chercher(rd, PAR_ID['N06']['requete'])
    assert {'ub-mannheim/tesseract', 'docling-project/docling'}.isdisjoint(r.cle for r in n06.affiches)


def test_valeurs_separees_sans_expression_a_cheval(banc):
    """Une expression de plusieurs mots ne franchit jamais deux valeurs personnelles ; la colonne citée est
    celle dont la valeur contient l'occurrence."""
    rd = banc.rd
    colonnes = dict(SCHEMA_GITNOTATE, Tags='multi_select')
    pages = [page('outil-a', 'https://github.com/test/outil-a', props={
                 'Description': p_texte('Bibliothèque de démonstration.'), 'Justification': p_texte(JUSTIF),
                 'Tags': p_multi('Fichier'), 'Notes': p_texte('PDF testé en salle B12')}),
             page('outil-b', 'https://github.com/test/outil-b', props={
                 'Description': p_texte('Bibliothèque de démonstration.'), 'Justification': p_texte(JUSTIF),
                 'Notes': p_texte('Lit un fichier PDF sans erreur')})]
    _synchroniser(banc, pages, colonnes)
    assert rd.normaliser('a' + rd.SEPARATEUR_NOTES.strip() + 'b') == 'a b'  # jamais dans un texte de fiche
    con, _ = rd.ouvrir_index_valide()
    try:
        trouves = {n for (n,) in con.execute('SELECT f.nom FROM recherche JOIN fiches f ON f.id = recherche.rowid '
                                             'WHERE recherche MATCH ?', ('"fichier pdf"',))}
    finally:
        con.close()
    assert trouves == {'outil-b'}
    reponse = _chercher(rd, 'salle')
    entree = reponse.resultats[0].repond_a[0]
    assert entree['champs'] == ['Notes'] and entree['occurrences'][0]['texte'] == 'salle'
    assert verifier_repond_a(rd, _chercher(rd, 'fichier pdf salle', tout=True)) >= 3
    reponse = _chercher(rd, 'fichier')
    outil_a = next(r for r in reponse.affiches if r.cle == 'test/outil-a')
    champs = outil_a.repond_a[0]['champs']
    assert 'Tags' in champs and 'Notes' not in champs                     # « Notes » ne contient pas « fichier »

# =============================================================================
# N. Requête : contraintes, références, possessifs, variantes, nombres
# =============================================================================
CONTRAINTES = {'windows', 'linux', 'macos', 'gpu', 'cli', 'docker', 'kubernetes', 'local', 'python', 'javascript',
               'systeme_mobile'}


def test_classe_contrainte_dans_le_lexique(banc):
    rd = banc.rd
    classes = {cid: classe for cid, (classe, _, _) in rd.lexique.CONCEPTS.items()}
    assert {cid for cid, classe in classes.items() if classe == 'contrainte'} == CONTRAINTES
    # mesurés sans gain (voir docs/REDECOUVERTE.md) : auto-hébergé et navigateur restent essentiels (objet de
    # H10, H03 et Q11), gratuit et open source restent faibles (poids 0,3, déjà sous 0,5)
    assert classes['auto_heberge'] == classes['navigateur'] == 'essentiel'
    assert classes['gratuit'] == classes['opensource'] == 'faible'
    assert rd.CLASSES['contrainte'] == 0.5
    assert {c.cle: c.classe for c in rd.analyser_requete('OCR sous Windows, Linux ou macOS, sur Android').concepts} \
        == {'ocr': 'essentiel', 'windows': 'contrainte', 'linux': 'contrainte', 'macos': 'contrainte',
            'systeme_mobile': 'contrainte'}


def test_contrainte_rare_ne_pese_plus_que_l_objet(corpus):
    """D4 (N04) : « Windows » (3 fiches) pesait plus que « OCR » (11 fiches)."""
    rd = corpus.rd
    reponse = _chercher(rd, PAR_ID['N04']['requete'])
    concepts = {c.cle: c for c in reponse.requete.concepts}
    objets = [c.poids for c in concepts.values() if c.classe == 'essentiel' and c.role == 'normal' and not c.retire]
    assert concepts['windows'].poids == pytest.approx(0.5 * max(objets))
    assert concepts['windows'].poids < concepts['ocr'].poids
    cles = [r.cle for r in reponse.resultats]
    assert cles[:2] == ['ub-mannheim/tesseract', 'tesseract-ocr/tesseract']
    windows = next(r for r in reponse.resultats if r.cle == 'dockur/windows')
    assert windows.niveau == 'partielle' and cles.index('dockur/windows') > cles.index('paddlepaddle/paddleocr')


def test_contrainte_jamais_suffisante_seule_pour_forte(banc):
    """Une fiche qui ne couvre que la contrainte reste partielle, même si elle pèse 60 % ; quand le besoin
    n'est fait que de contraintes, elles sont l'objet."""
    rd = banc.rd
    _synchroniser(banc, [
        page('lanceur', 'https://github.com/test/lanceur', props={
            'Description': p_texte('Lanceur de jeux pour Windows et Linux.'), 'Justification': p_texte(JUSTIF)}),
        page('ocr-pc', 'https://github.com/test/ocr-pc', props={
            'Description': p_texte('Moteur OCR pour Windows.'), 'Justification': p_texte(JUSTIF)}),
        page('autre', 'https://github.com/test/autre', props={
            'Description': p_texte('Éditeur de texte.'), 'Justification': p_texte(JUSTIF)})])
    reponse = _chercher(rd, 'OCR sous Windows et Linux')
    niveaux = {r.cle: r.niveau for r in reponse.resultats}
    assert niveaux['test/ocr-pc'] == 'forte'
    lanceur = next(r for r in reponse.resultats if r.cle == 'test/lanceur')
    assert lanceur.couverture >= rd.SEUIL_FORTE and lanceur.niveau == 'partielle'
    seules = _chercher(rd, 'Windows et Linux')                           # que des contraintes : l'objet
    assert {r.cle: r.niveau for r in seules.resultats}['test/lanceur'] == 'forte'
    concepts = [c for c in rd.analyser_requete('en Python pour mes vidéos').concepts]
    essentiels = rd.ensembles_niveau(concepts)[0]
    assert [c.cle for c in rd.objets_du_besoin(concepts, essentiels)] == ['video']


def test_contrainte_frequente_departage_encore(corpus):
    """N03 : « Python » (33 fiches) départage les serveurs MCP ; jamais un dépôt « Python » seul en forte."""
    reponse = _chercher(corpus.rd, PAR_ID['N03']['requete'])
    assert reponse.resultats[0].cle == 'jlowin/fastmcp'
    fortes = [r.cle for r in reponse.resultats if r.niveau == 'forte']
    assert 'thealgorithms/python' not in fortes and 'marimo-team/marimo' not in fortes


@pytest.mark.parametrize('texte, attendu', [
    ('Une interface pour Git, plus simple que la ligne de commande', [('interface', 'normal'), ('git', 'normal'),
                                                                     ('cli', 'reference')]),
    ('un tableur plutôt que Notion', [('tableur', 'normal'), ('notion', 'reference')]),
    ("un OCR au lieu d'Excel", [('ocr', 'normal'), ('tableur', 'reference')]),
    ('un tableur à la place de Notion', [('tableur', 'normal'), ('notion', 'reference')]),
    ('un tableur mieux que Notion', [('tableur', 'normal'), ('notion', 'reference')]),
    ('a spreadsheet instead of Notion', [('tableur', 'normal'), ('notion', 'reference')]),
    ('a spreadsheet rather than Notion', [('tableur', 'normal'), ('notion', 'reference')]),
    ('a CLI simpler than Docker', [('cli', 'normal'), ('docker', 'reference')]),
    ('a CLI better than Docker', [('cli', 'normal'), ('docker', 'reference')]),
    # portée arrêtée par une préposition, prolongée par « ou »/« et » (seconde revue, R2P-3)
    ('un OCR plus simple que Tesseract pour les plans scannés', [('ocr', 'normal'), ('tesseract', 'reference'),
                                                                ('plan', 'normal'), ('scan', 'normal')]),
    ('a CLI simpler than Docker for Windows', [('cli', 'normal'), ('docker', 'reference'), ('windows', 'normal')]),
    ('un tableur plutôt que Notion ou Airtable', [('tableur', 'normal'), ('notion', 'reference'),
                                                 ('airtable', 'reference')]),
])
def test_expressions_de_reference(banc, texte, attendu):
    requete = banc.rd.analyser_requete(texte)
    assert [(c.cle, c.role) for c in requete.concepts] == attendu
    assert not {'simple', 'simpler', 'mieux', 'better', 'lieu', 'place', 'instead', 'rather'} & {
        c.cle for c in requete.concepts}


def test_expression_de_reference_n07(corpus):
    """N07 : « plus simple que la ligne de commande » ne fait plus remonter un outil en ligne de commande."""
    reponse = _chercher(corpus.rd, PAR_ID['N07']['requete'])
    assert 'simple' not in {c.cle for c in reponse.requete.concepts}
    cles = [r.cle for r in reponse.resultats]
    assert cles[0] == 'jesseduffield/lazygit'
    assert 'davila7/claude-code-templates' not in cles[:3] and 'microsoft/omniparser' not in cles[:5]


def test_possessif_suivi_de_propre(banc):
    rd = banc.rd

    def roles(texte):
        return [(c.cle, c.role) for c in rd.analyser_requete(texte).concepts]

    assert roles('héberger mon propre serveur MCP') == [('heberger', 'normal'), ('serveur', 'normal'),
                                                        ('mcp', 'normal')]
    assert roles('write my own MCP server') == [('write', 'normal'), ('mcp', 'normal'), ('serveur', 'normal')]
    assert roles('nos propres vidéos') == [('video', 'normal')]
    assert roles('pour mes vidéos') == [('video', 'contexte')]                  # possessif seul : inchangé
    assert roles('for our videos') == [('video', 'contexte')]                  # « our » comme « my »
    assert roles('our own videos') == [('video', 'normal')]
    assert roles('un code propre') == [('code', 'normal'), ('propre', 'normal')]   # « propre » sans possessif
    requete = rd.analyser_requete('my own server')
    assert 'own' in requete.ignores


def test_variantes_feminines_des_mots_libres(corpus):
    rd = corpus.rd
    assert [rd.feminin(m) for m in ('interactif', 'premier', 'ancien', 'reel', 'createur')] == [
        'interactive', 'premiere', 'ancienne', 'reelle', 'createuse']
    # aucun « e » ajouté après une consonne (seconde revue) : « test » + e rejoindrait « testé »
    assert [rd.feminin(m) for m in ('structure', 'gerer', 'data', 'git', 'v2', 'test', 'local', 'gratuit')] == [
        'structure', 'gerer', 'data', 'git', 'v2', 'test', 'local', 'gratuit']
    assert '"local"*' in rd._termes_mot('local', libre=True)          # « locale » : par le préfixe
    termes = rd._termes_mot('interactifs', libre=True)
    assert '"interactive"' in termes and '"interactives"' in termes
    assert rd._termes_mot('interactifs') == ['"interactifs"', '"interactif"', '"interactif"*']   # forme du lexique
    assert not any('plane' in t for t in _concepts(rd, 'des plans').get('plan').termes)      # jamais au lexique
    reponse = _chercher(rd, PAR_ID['N08']['requete'])
    pagelm = next(r for r in reponse.resultats if r.cle == 'caviraoss/pagelm')
    assert pagelm.m['interactifs'] == 1.0                     # « ressources interactives » (D5)
    entree = next(e for e in pagelm.repond_a if e['concept'] == 'interactifs')
    assert entree['occurrences'][0]['texte'] == 'interactives'


def test_nombre_isole_ignore(corpus):
    """D5 (N05) : « Eurocode 2 » ne trouve plus « Apache-2.0 » ; un nombre plus long ou un mot avec chiffre
    reste un mot de la requête."""
    rd = corpus.rd
    requete = rd.analyser_requete(PAR_ID['N05']['requete'])
    assert '2' in requete.ignores and '2' not in {c.cle for c in requete.concepts}
    assert [c.cle for c in rd.analyser_requete('rapport 2024 en 3D, version 12').concepts] == ['rapport', '2024', '3d',
                                                                                                'version']
    assert 'evidentlyai/evidently' not in [r.cle for r in _chercher(rd, PAR_ID['N05']['requete'], tout=True).affiches]


def test_calcul_de_structures_forme_du_lexique(corpus, capsys):
    """D5 (N05) : « calcul de structures » est la notion du lexique, plus le mot libre « structures » qui
    trouvait « données structurées »."""
    rd = corpus.rd
    concepts = _concepts(rd, PAR_ID['N05']['requete'])
    assert concepts['structure'].mots == ['calcul de structures', 'béton armé', 'Eurocode']
    assert 'structures' not in concepts and 'calcul' not in concepts
    reponse = _chercher(rd, PAR_ID['N05']['requete'], tout=True)
    assert not reponse.resultats and not reponse.faibles and reponse.absents == ['calcul de structures', 'selon']
    assert corpus.lancer('cherche', PAR_ID['N05']['requete']) == 0
    assert 'Aucune fiche ne contient ces concepts : calcul de structures, selon.' in _sorties(capsys)


def test_absences_notion_du_lexique(corpus):
    """N06 : « absences » est une notion du lexique (vie scolaire), absente de toutes les fiches : elle garde
    son poids et aucune fiche n'est « forte » par le seul mot « notes » (« notes structurées » de PageLM)."""
    rd = corpus.rd
    reponse = _chercher(rd, PAR_ID['N06']['requete'], tout=True)
    concepts = {c.cle: c for c in reponse.requete.concepts}
    assert concepts['vie_scolaire'].classe == 'essentiel' and concepts['vie_scolaire'].df == 0
    assert not concepts['vie_scolaire'].retire and concepts['vie_scolaire'].poids > concepts['notes'].poids
    assert not any(r.niveau == 'forte' for r in reponse.affiches)
    assert rd.lexique.CONCEPTS['vie_scolaire'][2] == []      # sans voisin : pas un outil pédagogique

# =============================================================================
# O. Affichage des concepts absents
# =============================================================================
def test_absents_directement_et_forme_saisie(corpus, capsys):
    rd = corpus.rd
    texte = PAR_ID['N06']['requete']
    reponse = _chercher(rd, texte)
    assert reponse.absents == ['gérer', 'absences'] and reponse.par_voisin == ['élèves']
    assert corpus.lancer('cherche', texte) == 0
    sortie = _sorties(capsys)
    assert 'Aucune fiche ne mentionne : gérer, absences' in sortie
    assert 'Aucune fiche ne mentionne directement : élèves (trouvé seulement par un concept voisin)' in sortie
    assert 'Gérer' not in sortie.split('»', 1)[1]                 # la ligne « Recherche » garde le texte tapé
    assert corpus.lancer('cherche', texte, '--format', 'markdown') == 0
    sortie = capsys.readouterr().out
    assert 'Aucune fiche ne mentionne directement : élèves (trouvé seulement par un concept voisin)' in sortie
    assert corpus.lancer('cherche', texte, '--format', 'json') == 0
    requete = json.loads(capsys.readouterr().out)['requete']
    assert requete['absents_partout'] == ['gérer', 'absences'] and requete['trouves_par_voisin'] == ['élèves']


def test_forme_saisie_homogene(banc):
    rd = banc.rd

    def noms(texte):
        return [c.nom for c in rd.analyser_requete(texte).concepts]

    assert noms('Gérer les absences') == ['gérer', 'absences']
    assert noms('Windows dans Docker. Synthèse vocale') == ['windows', 'Docker', 'synthèse vocale']
    assert noms('BIM et PaddleOCR sous Windows') == ['BIM', 'PaddleOCR', 'Windows']   # sigle, casse mixte
    assert noms('« Gérer » les absences') == ['Gérer', 'absences']           # pas un début de phrase
    assert noms('outils ? Gérer') == ['gérer']

# =============================================================================
# P. Requêtes nouvelles (écrites avant tout résultat, attendus inchangés)
# =============================================================================
def test_requetes_nouvelles_seuils(corpus):
    """Seuils = mesures après l'affinage moins 0,05 (intrus@3 : plus 0,05). Mesures (8 requêtes, 6 avec des
    attendus en tête) : nDCG@10 0,858, MRR 0,857, P@5 0,728, intrus@3 0,25 (N04 : deepseek_ocr_app, qui
    exige un GPU, 3e ; N06 : PageLM, partielle). Avant l'affinage : 0,842 · 0,854 · 0,728 · 0,375.
    P@5 recalculé le 2026-10-12 avec la définition corrigée (pertinents parmi les 5 premiers / 5, et non plus
    / min(5, pertinents)) : 0,533 sur les mêmes classements, seuil 0,483 ; R@5 0,650, seuil 0,600."""
    rd = corpus.rd
    spec = importlib.util.spec_from_file_location(
        'evaluer_affinage', Path(__file__).resolve().parent.parent / 'scripts' / 'evaluer_redecouverte.py')
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    assert [q['id'] for q in NOUVELLES] == [f'N0{i}' for i in range(1, 9)]
    mesures = {}
    con, _ = rd.ouvrir_index_valide()
    try:
        for q in NOUVELLES:
            reponse = ev.lancer(con, q)
            mesures[q['id']] = (ev.mesurer(ev.classement_de(reponse), q), reponse)
    finally:
        con.close()
    def moyenne(cle):
        valeurs = [m[cle] for m, _ in mesures.values() if m[cle] is not None]
        return sum(valeurs) / len(valeurs)
    assert moyenne('ndcg10') >= 0.808
    assert moyenne('mrr') >= 0.807
    assert moyenne('p5') >= 0.483
    assert moyenne('r5') >= 0.600
    assert moyenne('intrus3') <= 0.30
    for ident in ('N05', 'N06'):                              # aucun résultat attendu
        assert PAR_ID[ident]['aucun_fort']
        reponse = mesures[ident][1]
        assert not any(r.niveau == 'forte' for r in reponse.resultats + reponse.sans_depot), ident
    for ident in ('N01', 'N02', 'N03', 'N04', 'N07'):          # attendu en tête au premier rang
        assert mesures[ident][0]['mrr'] == 1.0, ident

# =============================================================================
# Q. Seconde revue contradictoire
# =============================================================================
def test_objet_sans_notion_du_lexique_mot_hors_lexique_present_ailleurs(banc):
    """R2P-1 : un mot hors lexique (« installer », « tester ») présent dans une fiche sans rapport ne devient
    plus l'objet du besoin : il ne réduit plus les contraintes à la moitié de son poids et n'est plus exigé
    pour « forte » ; dockur/windows (« Windows inside a Docker container ») reste premier et fort."""
    rd = banc.rd
    pyenv = page('pyenv', 'https://github.com/pyenv/pyenv', props={
        'Description': p_texte("Permet d'installer plusieurs versions de Python côte à côte."),
        'Justification': p_texte(JUSTIF)})
    index_du_corpus(rd, pages_du_corpus() + [pyenv])
    for texte, mot in (('installer Windows dans un conteneur Docker', 'installer'),
                       ('tester un logiciel Windows dans Docker', 'tester')):
        reponse = _chercher(rd, texte)
        concepts = {c.cle: c for c in reponse.requete.concepts}
        assert concepts[mot].classe == 'libre' and concepts[mot].df >= 1, texte      # trouvé ailleurs
        essentiels = rd.ensembles_niveau([c for c in concepts.values() if not c.retire])[0]
        assert {'windows', 'docker'} <= {c.cle for c in rd.objets_du_besoin(list(concepts.values()), essentiels)}
        tete = reponse.resultats[0]
        assert (tete.cle, tete.niveau) == ('dockur/windows', 'forte'), [(r.cle, r.niveau) for r in
                                                                         reponse.resultats[:3]]
        assert mot in tete.ne_couvre_pas
        assert all(r.niveau != 'forte' for r in reponse.resultats[1:]), texte          # pyenv : partielle
    assert verifier_repond_a(rd, _chercher(rd, 'installer Windows dans un conteneur Docker', tout=True)) >= 2


def test_objet_du_lexique_toujours_exige_avec_des_contraintes(corpus):
    """Une notion essentielle du lexique reste l'objet : pour « un OCR Windows dans Docker », dockur/windows
    (Windows et Docker, pas d'OCR) reste partiel. Limite documentée (docs/REDECOUVERTE.md, Limites) : une
    notion générique (« serveur ») est aussi l'objet, faute de pouvoir lire « serveur Windows » comme une
    édition de Windows."""
    rd = corpus.rd
    reponse = _chercher(rd, 'un OCR Windows dans Docker')
    niveaux = {r.cle: r.niveau for r in reponse.resultats}
    assert reponse.resultats[0].cle == 'ub-mannheim/tesseract' and niveaux['dockur/windows'] == 'partielle'
    concepts = {c.cle: c for c in reponse.requete.concepts}
    assert concepts['windows'].poids == pytest.approx(0.5 * concepts['ocr'].poids)
    serveur = _chercher(rd, 'un serveur Windows dans Docker')
    niveaux = {r.cle: r.niveau for r in serveur.resultats}
    assert serveur.resultats[0].cle == 'awesome-selfhosted/awesome-selfhosted'
    assert niveaux['awesome-selfhosted/awesome-selfhosted'] == 'forte' and niveaux['dockur/windows'] == 'partielle'


@pytest.mark.parametrize('texte', ['test', 'tests unitaires', 'lancer des tests unitaires', 'framework de test'])
def test_feminin_ne_trouve_plus_teste(corpus, texte):
    """R2P-2 / R2-1 : « test » + e = « teste », qui rejoignait après repli des accents le participe « Testé »
    des notes (docling : « Testé pour extraire les tableaux » ; PaddleOCR : « Testé : bon sur les plans
    scannés ») ; evidently (« de test et de surveillance ») redevient le seul résultat, comme avant
    l'affinage."""
    rd = corpus.rd
    reponse = _chercher(rd, texte, tout=True)
    assert [r.cle for r in reponse.resultats] == ['evidentlyai/evidently']
    for r in reponse.affiches:
        for e in r.repond_a + r.indices_faibles:
            assert all(rd.gn._fold(o['texte']) != 'teste' for o in e['occurrences']), (r.cle, e)
    assert verifier_repond_a(rd, reponse, texte) >= 1


def test_feminin_aucun_terme_construit_apres_une_consonne(banc):
    rd = banc.rd
    assert rd._termes_mot('test', libre=True) == ['"test"']
    assert rd._termes_mot('tests', libre=True) == ['"tests"', '"test"']
    for mot in ('post', 'port', 'vent', 'sort', 'edit', 'list'):
        assert rd._termes_mot(mot, libre=True) == [f'"{mot}"'], mot
    assert rd._termes_mot('interactifs', libre=True)[-2:] == ['"interactive"', '"interactives"']


def test_comparaison_arretee_par_une_preposition(corpus):
    """R2P-3 : dans « un OCR plus simple que Tesseract pour les plans scannés », seul Tesseract est la
    référence ; les deux dépôts tesseract (à remplacer) ne sortent plus « forte »."""
    rd = corpus.rd
    reponse = _chercher(rd, 'un OCR plus simple que Tesseract pour les plans scannés')
    niveaux = {r.cle: r.niveau for r in reponse.resultats}
    assert reponse.resultats[0].cle == 'paddlepaddle/paddleocr' and niveaux['paddlepaddle/paddleocr'] == 'forte'
    assert niveaux['ub-mannheim/tesseract'] == niveaux['tesseract-ocr/tesseract'] == 'partielle'
    virgule = _chercher(rd, 'un OCR plus simple que Tesseract, pour les plans scannés')
    assert [(r.cle, r.niveau) for r in virgule.resultats] == [(r.cle, r.niveau) for r in reponse.resultats]


def test_garde_fou_au_premier_sync_apres_changement_de_format(banc, capsys):
    """R2-2 : un index d'un autre format (version précédente du moteur) dont les fiches et la base se lisent
    est comparé : une baisse brutale ou une autre base est refusée (code 2, ancien index conservé) ; seul un
    index illisible est remplacé sans comparaison."""
    rd = banc.rd
    banc.notion.pages = pages_numerotees(30)
    assert banc.lancer('sync') == 0

    def ancien_format(*sql):
        con = sqlite3.connect(str(banc.index))
        con.execute('PRAGMA user_version = 1')
        con.execute("UPDATE meta SET valeur = '1' WHERE cle = 'format_index'")
        for requete in sql:
            con.execute(requete)
        con.commit()
        con.close()
        return banc.index.read_bytes()

    avant = ancien_format()
    banc.notion.pages = pages_numerotees(3)
    capsys.readouterr()
    assert banc.lancer('sync') == 2
    sortie = _sorties(capsys)
    assert "27 fiches de l'index précédent sont absentes de la lecture" in sortie
    assert "L'ancien index est conservé" in sortie and banc.index.read_bytes() == avant
    banc.notion.pages = pages_numerotees(30)
    avant = ancien_format("UPDATE meta SET valeur = 'ffffffffffffffffffffffffffffffff' WHERE cle = 'database_id'")
    assert banc.lancer('sync') == 2
    assert "L'index précédent venait d'une autre base (ffffffff…)" in _sorties(capsys)
    assert banc.index.read_bytes() == avant
    ancien_format("UPDATE meta SET valeur = '" + rd.normaliser_id(banc.gn.DATABASE_ID) + "' WHERE cle = 'database_id'")
    banc.notion.pages = pages_numerotees(3)
    assert banc.lancer('sync', '--accepter-baisse') == 0
    sortie = _sorties(capsys)
    assert "index précédent d'un autre format : remplacé après comparaison des fiches" in sortie
    assert "baisse acceptée (--accepter-baisse) : 27 fiches disparues" in sortie
    ancien_format('ALTER TABLE fiches RENAME TO fiches_v1')
    assert banc.lancer('sync') == 0
    assert "index précédent d'un autre format : remplacé sans comparaison" in _sorties(capsys)
    con, meta = rd.ouvrir_index_valide()
    con.close()
    assert meta['nb_fiches'] == '3'


def test_mot_du_seul_depot_cite_dans_url(corpus):
    """R2-3 : « mannheim » ne vient que de propriétaire/dépôt (ub-mannheim/tesseract) : il est cité dans le
    champ URL, tel qu'écrit dans l'adresse (« Mannheim »), plus dans le Nom (« tesseract », « Installeur
    Tesseract pour Windows ») ; un mot du découpage CamelCase est situé dans le titre."""
    rd = corpus.rd
    reponse = _chercher(rd, 'mannheim')
    r = reponse.resultats[0]
    assert r.cle == 'ub-mannheim/tesseract'
    entree = r.repond_a[0]
    fiche = {f['page_id']: f for f in r.fiches}[entree['page_id']]
    assert entree['champs'] == ['URL'] and entree['texte'].startswith('mannheim (URL · ')
    o = entree['occurrences'][0]
    assert (o['champ'], o['colonne'], o['texte']) == ('URL', 'nom', 'Mannheim')
    assert fiche['champs']['URL']['texte'][o['debut']:o['fin']] == 'Mannheim'
    assert 'mannheim' not in fiche['champs']['Nom']['texte'].lower()
    assert verifier_repond_a(rd, reponse) >= 1
    paddle = _chercher(rd, 'paddle').resultats[0]
    nom = next(o for e in paddle.repond_a for o in e['occurrences'] if o['colonne'] == 'nom')
    assert (nom['champ'], nom['debut'], nom['fin'], nom['texte']) == ('Nom', 0, 6, 'Paddle')
    tesseract = _chercher(rd, 'tesseract')
    for r in tesseract.resultats:                      # titre qui contient le mot : Nom, sans URL en double
        entree = r.repond_a[0]
        assert 'URL' not in entree['champs'], (r.cle, entree['champs'])
    assert rd.sources_nom_indexe('PaddleOCR', 'paddlepaddle/paddleocr') == [
        (0, 9, 'titre', 0), (10, 16, 'titre', 0), (17, 20, 'titre', 6), (21, 43, 'depot', 0)]
