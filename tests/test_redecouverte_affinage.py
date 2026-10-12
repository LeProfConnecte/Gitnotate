"""Moteur de redécouverte — affinage de la pertinence (après les mesures du lot 4, défauts D1 à D5).

M. Invariant « Répond à » (aucune correspondance sans occurrence réelle) · N. Requête (contraintes,
références, possessifs, variantes, nombres) · O. Affichage des concepts absents · P. Seuils des requêtes
nouvelles (écrites avant tout résultat, attendus inchangés).
"""
import importlib.util
import json
from pathlib import Path

import pytest
from redecouverte_outils import (
    FIXTURES,
    SCHEMA_GITNOTATE,
    index_du_corpus,
    p_multi,
    p_texte,
    page,
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
    """Texte stocké du champ cité : valeur de la colonne personnelle, nom indexé, ou texte du champ."""
    if occurrence['colonne'] == 'nom':
        return rd.texte_nom_indexe(fiche['nom'], fiche['cle_depot'])
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
    Nom (exclu des extraits) ou nombre maximal d'extraits atteint."""
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
            assert extrait or entree['champs'] == ['Nom'] or len(r.extraits) == rd.EXTRAITS_PAR_RESULTAT, ou
            if entree['champs'] == ['Nom']:
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
CONTRAINTES = {'windows', 'linux', 'macos', 'gpu', 'cli', 'docker', 'local', 'python', 'javascript', 'systeme_mobile'}


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
    objets = [c.poids for c in concepts.values() if c.classe in ('essentiel', 'libre') and c.role == 'normal'
              and not c.retire]
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
    assert [rd.feminin(m) for m in ('interactif', 'premier', 'ancien', 'reel', 'createur', 'local', 'gratuit')] == [
        'interactive', 'premiere', 'ancienne', 'reelle', 'createuse', 'locale', 'gratuite']
    assert [rd.feminin(m) for m in ('structure', 'gerer', 'data', 'git', 'v2')] == ['structure', 'gerer', 'data',
                                                                                      'git', 'v2']
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
    exige un GPU, 3e ; N06 : PageLM, partielle). Avant l'affinage : 0,842 · 0,854 · 0,728 · 0,375."""
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
    assert moyenne('p5') >= 0.677
    assert moyenne('intrus3') <= 0.30
    for ident in ('N05', 'N06'):                              # aucun résultat attendu
        assert PAR_ID[ident]['aucun_fort']
        reponse = mesures[ident][1]
        assert not any(r.niveau == 'forte' for r in reponse.resultats + reponse.sans_depot), ident
    for ident in ('N01', 'N02', 'N03', 'N04', 'N07'):          # attendu en tête au premier rang
        assert mesures[ident][0]['mrr'] == 1.0, ident
