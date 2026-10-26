"""Lot 5 : identifiants techniques selon leur rôle, exclusions prouvées, recherche de code sémantique.

- Rôle d'un identifiant nommé (lexique.IDENTIFIANTS) : cible, contrainte (après une préposition ou un possessif),
  référence à remplacer (catégorie + exclusion implicite), exclusion (« sans n8n ») ; en français et en anglais,
  pour n8n et d'autres technologies (Docker, FastAPI, React, Claude Code, Kubernetes, GPU).
- Exclusion : ce que la fiche dit de l'identifiant (requis, non requis, contradictoire, mention, inconnu ; avis du
  LLM à part) ; seul « requis » retire la « forte » et place le dépôt après les autres ; une fiche muette n'est
  jamais déclassée ; l'avis du LLM seul ne suffit pas.
- Cas de la revue contradictoire du lot 5 (B1-B3, I1-I8, M1-M8) : portée de la négation, négation après
  l'identifiant, éléments de liste, restrictifs, formes de Docker, « no-code », coordination, « code » dans un autre
  sens, « tutoriel sur React ».
- Recherche sémantique : code (notion recherche_code, composition « recherche sémantique » + « code ») et documents
  (recherche_semantique) restent distincts, y compris avec une négation.
Hors ligne, aucune base Notion réelle.
"""
import json

import pytest
from redecouverte_outils import index_du_corpus, p_multi, p_select, p_texte, page, preparer


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


@pytest.fixture
def corpus(banc):
    index_du_corpus(banc.rd)
    return banc


def _roles(rd, texte):
    requete = rd.analyser_requete(texte)
    return ([(c.cle, c.classe, c.role) for c in requete.concepts],
            [(e['cible'], e.get('source', 'exclusion')) for e in requete.exclusions])


def _chercher(rd, texte, limite=50):
    con, meta = rd.ouvrir_index_valide()
    try:
        reponse = rd.rechercher(con, rd.analyser_requete(texte), {}, limite, False, meta)
        rd.expliquer(con, reponse)
    finally:
        con.close()
    return reponse

# =============================================================================
# Lexique
# =============================================================================
def test_identifiants_du_lexique(banc):
    lexique = banc.rd.lexique
    for cid, (nature, categorie) in lexique.IDENTIFIANTS.items():
        assert cid in lexique.CONCEPTS and nature in ('produit', 'plateforme', 'materiel')
        assert categorie is None or (nature == 'produit' and categorie in lexique.CONCEPTS)
    formes = {cid: {f.casefold() for f in lexique.CONCEPTS[cid][1]} for cid in lexique.CONCEPTS}
    # un produit n'est plus une forme de sa catégorie : citer n8n ne dit pas qu'une fiche parle de workflows
    assert 'n8n' not in formes['workflow'] and 'zapier' not in formes['workflow']
    assert 'react' not in formes['frontend'] and 'kubernetes' not in formes['docker']
    assert lexique.CONCEPTS['kubernetes'][0] == lexique.C and lexique.CONCEPTS['n8n'][0] == lexique.E
    assert 'recherche de code sémantique' in formes['recherche_code']
    assert 'semantic code search' in formes['recherche_code']
    assert 'recherche de code sémantique' not in formes['recherche_semantique']

# =============================================================================
# Rôle d'un identifiant dans la requête
# =============================================================================
@pytest.mark.parametrize('texte, concepts, exclusions', [
    # n8n : les quatre formulations demandées, en français puis en anglais
    ('une bibliothèque de workflows pour n8n',
     [('plateforme', 'faible', 'normal'), ('workflow', 'essentiel', 'normal'), ('n8n', 'essentiel', 'normal')], []),
    ('a library of n8n workflows',
     [('plateforme', 'faible', 'normal'), ('n8n', 'essentiel', 'normal'), ('workflow', 'essentiel', 'normal')], []),
    ('des workflows exécutés avec n8n',
     [('workflow', 'essentiel', 'normal'), ('executes', 'libre', 'normal'), ('n8n', 'contrainte', 'normal')], []),
    ('workflows running on n8n',
     [('workflow', 'essentiel', 'normal'), ('running', 'libre', 'normal'), ('n8n', 'contrainte', 'normal')], []),
    # « no-code » placé après « alternative » prend aussi le rôle référence (règle antérieure au lot 5, qui vaut pour
    # toute notion) : seul le rôle de n8n est vérifié ici, voir test_alternative_no_code_a_n8n

    ('a no-code alternative to n8n',
     [('nocode', 'essentiel', 'normal'), ('workflow', 'essentiel', 'reference')], [('n8n', 'reference')]),
    ('automatiser mes factures sans n8n', [('automatisation', 'essentiel', 'normal'), ('factures', 'libre', 'contexte')],
     [('n8n', 'exclusion')]),
    ('automate my invoices without n8n', [('automatisation', 'essentiel', 'normal'), ('invoices', 'libre', 'contexte')],
     [('n8n', 'exclusion')]),
    # possessif : le produit reste une contrainte de rôle normal (comptée dans la couverture)
    ('surveiller les workflows de mon instance n8n',
     [('monitoring', 'essentiel', 'normal'), ('workflow', 'essentiel', 'normal'), ('instance', 'libre', 'contexte'),
      ('n8n', 'contrainte', 'normal')], []),
    # Zapier, même règle
    ('une alternative à Zapier', [('workflow', 'essentiel', 'reference')], [('zapier', 'reference')]),
    # Docker, Kubernetes : plateformes, déjà des contraintes ; seule l'exclusion change
    ('un OCR avec Docker', [('ocr', 'essentiel', 'normal'), ('docker', 'contrainte', 'normal')], []),
    ('un OCR sans Docker', [('ocr', 'essentiel', 'normal')], [('docker', 'exclusion')]),
    ('an OCR, not with Docker', [('ocr', 'essentiel', 'normal')], [('docker', 'exclusion')]),
    ('déployer sur Kubernetes', [('deployer', 'libre', 'normal'), ('kubernetes', 'contrainte', 'normal')], []),
    ('a web UI for containers, no Kubernetes',
     [('site_web', 'essentiel', 'normal'), ('frontend', 'essentiel', 'normal'), ('docker', 'contrainte', 'normal')],
     [('kubernetes', 'exclusion')]),
    # FastAPI : cible, contrainte, référence
    ('un gabarit de projet FastAPI', [('gabarit', 'libre', 'normal'), ('fastapi', 'essentiel', 'normal')], []),
    ('des modules réutilisables dans une application FastAPI',
     [('modules', 'libre', 'normal'), ('application', 'faible', 'normal'), ('fastapi', 'contrainte', 'normal')], []),
    ('an alternative to FastAPI', [('api', 'essentiel', 'reference')], [('fastapi', 'reference')]),
    # React : cible, contrainte, exclusion, référence (« instead of »)
    ('une bibliothèque de composants React',
     [('plateforme', 'faible', 'normal'), ('composants', 'libre', 'normal'), ('react', 'essentiel', 'normal')], []),
    ('des vidéos avec des composants React',
     [('video', 'essentiel', 'normal'), ('composants', 'libre', 'normal'), ('react', 'contrainte', 'normal')], []),
    ('des composants d\'interface sans React',
     [('composants', 'libre', 'normal'), ('interface', 'libre', 'normal')], [('react', 'exclusion')]),
    ('a UI kit instead of React', [('frontend', 'essentiel', 'normal'), ('kit', 'libre', 'normal')],
     [('react', 'reference')]),
    # Claude Code : cible, référence
    ('des skills pour Claude Code', [('skills', 'libre', 'normal'), ('claude_code', 'essentiel', 'normal')], []),
    ('une alternative à Claude Code', [('agent_code', 'essentiel', 'reference')], [('claude_code', 'reference')]),
    # GPU : matériel
    ('un OCR qui tourne sans GPU', [('ocr', 'essentiel', 'normal')], [('gpu', 'exclusion')]),
])
def test_role_identifiant(banc, texte, concepts, exclusions):
    assert _roles(banc.rd, texte) == (concepts, exclusions)


def test_alternative_no_code_a_n8n(banc):
    requete = banc.rd.analyser_requete('une alternative no-code à n8n')
    concepts = {c.cle: c for c in requete.concepts}
    assert 'n8n' not in concepts and concepts['workflow'].role == 'reference'
    assert [(e['cible'], e['source']) for e in requete.exclusions] == [('n8n', 'reference')]


def test_produit_cite_comme_cible_et_comme_contrainte(banc):
    # une seule mention cible suffit : la notion garde sa classe
    concepts, _ = _roles(banc.rd, 'des workflows n8n exécutés avec n8n')
    assert ('n8n', 'essentiel', 'normal') in concepts


def test_reference_garde_le_nom_du_produit(banc):
    requete = banc.rd.analyser_requete('une alternative no-code à n8n')
    workflow = next(c for c in requete.concepts if c.cle == 'workflow')
    assert '"n8n"' in workflow.termes                     # une fiche « alternative à n8n » en parle
    assert workflow.nom == 'workflow (comme n8n)'
    # nom composé compris ; mais pas quand la catégorie est aussi demandée pour elle-même
    claude = next(c for c in banc.rd.analyser_requete('une alternative à Claude Code').concepts)
    assert claude.cle == 'agent_code' and '"claude code"' in claude.termes
    q11 = banc.rd.analyser_requete('Un agent de code open source, alternative à Claude Code ?')
    assert '"claude code"' not in next(c for c in q11.concepts if c.cle == 'agent_code').termes


def test_identifiant_nie_jamais_positif(banc):
    for texte in ('sans n8n', 'without n8n', 'pas avec Docker', 'not for Windows', 'sans GPU', 'no Kubernetes'):
        requete = banc.rd.analyser_requete(texte)
        assert requete.concepts == [] and len(requete.exclusions) == 1, texte

# =============================================================================
# Preuves lues dans la fiche (sorte_mention, etat_exclusion)
# =============================================================================
def _sorte(rd, texte, mot, colonne='description', nature='produit'):
    a = texte.index(mot)
    return rd.sorte_mention(texte, a, a + len(mot), colonne, nature)


@pytest.mark.parametrize('texte, mot, colonne, nature, sorte', [
    ('- Docker and Docker Compose', 'Docker', 'prerequis', 'plateforme', 'requis'),
    ('Nécessite un GPU NVIDIA avec CUDA.', 'GPU', 'description', 'materiel', 'requis'),
    ('Requires a running Docker daemon.', 'Docker', 'installation', 'plateforme', 'requis'),
    ('Collection de 2 000 workflows pour n8n.', 'n8n', 'description', 'produit', 'requis'),
    ('Des workflows n8n prêts à importer.', 'n8n', 'description', 'produit', 'requis'),
    ('Skills for Claude Code.', 'Claude Code', 'description', 'produit', 'requis'),
    ('Fonctionne sans Docker : un simple binaire.', 'Docker', 'description', 'plateforme', 'non_requis'),
    ('Ne nécessite pas de GPU.', 'GPU', 'description', 'materiel', 'non_requis'),
    ('GPU facultatif, tourne sur CPU.', 'GPU', 'prerequis', 'materiel', 'non_requis'),
    ('Docker optional.', 'Docker', 'prerequis', 'plateforme', 'non_requis'),
    ('Alternative open source à n8n et Zapier.', 'n8n', 'description', 'produit', 'non_requis'),
    ('Image Docker disponible.', 'Docker', 'installation', 'plateforme', 'mention'),
    ('Automatisations n8n', 'n8n', 'brique_pour', 'produit', 'mention'),
    ('Linux, macOS ou Windows', 'Windows', 'prerequis', 'plateforme', 'mention'),
    ('Docker ou Podman', 'Docker', 'prerequis', 'plateforme', 'mention'),
    ('Compatible avec n8n.', 'n8n', 'description', 'produit', 'mention'),
])
def test_sorte_mention(banc, texte, mot, colonne, nature, sorte):
    assert _sorte(banc.rd, texte, mot, colonne, nature) == sorte


def test_etat_exclusion(banc):
    rd = banc.rd
    e = {'cible': 'gpu', 'mot': 'GPU', 'nature': 'materiel', 'source': 'exclusion'}

    def preuves(*occurrences):
        return {'gpu': {1: [(colonne, 't', 0, 1, sorte) for colonne, sorte in occurrences]}}
    assert rd.etat_exclusion(e, [1], preuves(('prerequis', 'requis')))['etat'] == 'requis'
    assert rd.etat_exclusion(e, [1], preuves(('prerequis', 'requis'), ('notes', 'non_requis')))['etat'] == \
        'contradictoire'
    assert rd.etat_exclusion(e, [1], preuves(('justification', 'requis')))['etat'] == 'avis_requis'
    assert rd.etat_exclusion(e, [1], preuves(('description', 'mention'), ('justification', 'requis')))['etat'] == \
        'avis_requis'
    assert rd.etat_exclusion(e, [1], preuves(('justification', 'mention')))['etat'] == 'mention'
    assert rd.etat_exclusion(e, [2], preuves(('prerequis', 'requis')))['etat'] == 'inconnu'

# =============================================================================
# Classement : seule une exigence lue dans la fiche déclasse
# =============================================================================
def _pages_exclusion():
    def fiche(nom, prerequis, description):
        return page(nom, f'https://github.com/synth/{nom}', props={
            'Description': p_texte(description), "Cas d'usage": p_texte("• Extraire le texte de documents scannés"),
            'Prérequis': p_texte(prerequis), 'Catégorie': p_select('OCR/Documents'), 'Brique pour': p_multi(),
            'Licence': p_select('MIT')})
    return [fiche('ocr-gpu', '- NVIDIA GPU with CUDA support', "OCR rapide de documents scannés."),
            fiche('ocr-cpu', '- Python 3.10', "OCR de documents scannés qui fonctionne sans GPU, sur CPU."),
            fiche('ocr-muet', 'Non vérifié', "OCR de documents scannés.")]


def test_exclusion_requis_declasse_seulement_la_preuve(banc):
    rd = banc.rd
    index_du_corpus(rd, _pages_exclusion())
    sans = _chercher(rd, 'un OCR pour documents scannés sans GPU')
    etats = {r.cle: (r.niveau, [x['etat'] for x in r.exclusions]) for r in sans.resultats}
    assert etats['synth/ocr-gpu'] == ('partielle', ['requis'])
    assert etats['synth/ocr-cpu'][1] == ['non_requis'] and etats['synth/ocr-muet'][1] == ['inconnu']
    assert [r.cle for r in sans.resultats][-1] == 'synth/ocr-gpu'
    # sans exclusion, le même dépôt n'est pas déclassé
    avec = _chercher(rd, 'un OCR pour documents scannés')
    assert next(r for r in avec.resultats if r.cle == 'synth/ocr-gpu').niveau == 'forte'
    assert all(not r.exclusions for r in avec.resultats)
    # une fiche muette n'est jamais déclassée : même rang relatif avec ou sans « sans GPU »
    ordre_sans = [r.cle for r in sans.resultats if r.cle != 'synth/ocr-gpu']
    ordre_avec = [r.cle for r in avec.resultats if r.cle != 'synth/ocr-gpu']
    assert ordre_sans == ordre_avec


def test_exclusion_affichee_avec_citation(banc, capsys):
    rd = banc.rd
    index_du_corpus(rd, _pages_exclusion())
    assert banc.lancer('cherche', 'un OCR pour documents scannés sans GPU') == 0
    sortie = ' '.join(capsys.readouterr().out.split())        # lignes enveloppées
    assert 'Exclus : GPU' in sortie
    assert "« GPU » exclu : requis d'après la fiche (Prérequis · fiche v7.3+" in sortie
    assert "(Prérequis · fiche v7.3+ du 2026-10-11 : « - NVIDIA GPU with CUDA support »)" in sortie
    assert "la fiche ne le présente pas comme requis (Description · fiche v7.3+ du 2026-10-11 : « OCR de documents " \
           "scannés qui fonctionne sans GPU, sur CPU. »)" in sortie
    assert "« GPU » exclu : la fiche n'en parle pas, non vérifié" in sortie
    assert banc.lancer('cherche', 'un OCR pour documents scannés sans GPU', '--format', 'json') == 0
    donnees = json.loads(capsys.readouterr().out)
    assert donnees['requete']['exclusions'] == [{'cible': 'gpu', 'mot': 'GPU', 'nature': 'materiel',
                                                 'source': 'exclusion'}]
    gpu = next(r for r in donnees['resultats'] if r['depot'] == 'synth/ocr-gpu')
    assert gpu['exclusions'][0]['etat'] == 'requis'
    assert gpu['exclusions'][0]['preuves'][0]['citation'] == '- NVIDIA GPU with CUDA support'
    assert banc.lancer('cherche', 'un OCR pour documents scannés sans GPU', '--format', 'markdown') == 0
    assert "- **Exclusion** : « GPU » exclu : requis d'après la fiche" in capsys.readouterr().out


def test_alternative_a_un_produit(banc):
    rd = banc.rd

    def fiche(nom, description):
        return page(nom, f'https://github.com/synth/{nom}', props={
            'Description': p_texte(description), "Cas d'usage": p_texte("• Automatiser des tâches"),
            'Catégorie': p_select('Automatisation/No-code'), 'Brique pour': p_multi()})
    index_du_corpus(rd, [
        fiche('flow-alt', "Plateforme d'automatisation no-code de workflows, alternative open source à n8n."),
        fiche('n8n-recettes', "Collection de workflows pour n8n, prêts à importer."),
        fiche('autre-flux', "Moteur de workflows no-code auto-hébergé.")])
    reponse = _chercher(rd, 'une plateforme de workflows no-code, alternative à n8n')
    cles = [r.cle for r in reponse.resultats]
    assert cles[-1] == 'synth/n8n-recettes'               # dépend de n8n : ce n'est pas une alternative
    recettes = next(r for r in reponse.resultats if r.cle == 'synth/n8n-recettes')
    assert recettes.niveau == 'partielle' and recettes.exclusions[0]['etat'] == 'requis'
    assert recettes.exclusions[0]['texte'].startswith("Alternative à « n8n » : requis d'après la fiche")
    # état inconnu non affiché pour un produit à remplacer
    assert next(r for r in reponse.resultats if r.cle == 'synth/autre-flux').exclusions == []


def test_corpus_n04_deepseek_ocr_app_declasse(corpus):
    # « ne nécessite pas de GPU » : deepseek_ocr_app indique un GPU NVIDIA dans ses Prérequis
    reponse = _chercher(corpus.rd, 'Un OCR qui ne nécessite pas de GPU, pour les PC Windows de la salle informatique')
    app = next(r for r in reponse.resultats if r.cle == 'rdumasia303/deepseek_ocr_app')
    assert app.niveau == 'partielle' and [x['etat'] for x in app.exclusions] == ['requis']
    assert app.rang > 5
    # avis du LLM seul (Justification « … demande un GPU CUDA puissant ») : affiché, jamais déclassé
    ocr = next(r for r in reponse.resultats if r.cle == 'deepseek-ai/deepseek-ocr')
    assert [x['etat'] for x in ocr.exclusions] == ['avis_requis'] and ocr.rang <= 5

# =============================================================================
# Recherche sémantique : code contre documents
# =============================================================================
@pytest.mark.parametrize('texte, attendu', [
    ('Je cherche un moteur de recherche de code sémantique local', 'recherche_code'),
    ('semantic code search across my repositories', 'recherche_code'),
    ('une recherche sémantique dans mon code source', 'recherche_code'),
    ('Semantic search through my source code in a local repository', 'recherche_code'),
    ('recherche sémantique de code Python', 'recherche_code'),
    ('Recherche sémantique pour interroger des documents PDF', 'recherche_semantique'),
    ('semantic search over my PDF documents', 'recherche_semantique'),
    # négation : « code » exclu ne compose pas (le défaut « not for X » laisse « code » positif, sans composition)
    ('Semantic search for my lesson notes and PDFs, not for source code.', 'recherche_semantique'),
    ('recherche sémantique dans mes cours, pas dans le code', 'recherche_semantique'),
])
def test_code_ou_documents(banc, texte, attendu):
    cles = [c.cle for c in banc.rd.analyser_requete(texte).concepts]
    assert attendu in cles
    assert {'recherche_code', 'recherche_semantique'} - {attendu} - set(cles) == \
        {'recherche_code', 'recherche_semantique'} - {attendu}


def _pages_semantiques():
    def fiche(nom, description):
        return page(nom, f'https://github.com/synth/{nom}', props={
            'Description': p_texte(description), "Cas d'usage": p_texte("• Retrouver un passage"),
            'Catégorie': p_select('RAG/Recherche'), 'Brique pour': p_multi()})
    return [fiche('code-seek', "Moteur de recherche de code sémantique local-first pour vos dépôts."),
            fiche('pdf-seek', "Recherche sémantique dans des documents PDF et des notes de cours."),
            fiche('grep-plus', "Recherche rapide dans des fichiers texte.")]


def test_code_et_documents_restent_distincts(banc):
    rd = banc.rd
    index_du_corpus(rd, _pages_semantiques())
    code = _chercher(rd, 'une recherche sémantique dans mon code source')
    assert code.resultats[0].cle == 'synth/code-seek' and code.resultats[0].niveau == 'forte'
    assert next(r for r in code.resultats if r.cle == 'synth/pdf-seek').niveau != 'forte'
    pdf = _chercher(rd, 'Recherche sémantique pour interroger des documents PDF')
    cles = [r.cle for r in pdf.resultats]
    assert cles[0] == 'synth/pdf-seek'
    assert 'synth/code-seek' not in cles or next(r for r in pdf.resultats if r.cle == 'synth/code-seek').niveau != 'forte'
    negation = _chercher(rd, 'Semantic search for my lesson notes and PDFs, not for source code.')
    assert negation.resultats[0].cle == 'synth/pdf-seek'

# =============================================================================
# Revue contradictoire du lot 5
# =============================================================================
@pytest.mark.parametrize('texte, concepts, exclusions', [
    # B1 : une préposition referme la négation ; M5 : la négation se referme après l'identifiant
    ('Un OCR qui tourne sans GPU sous Windows', ['ocr', 'windows'], ['gpu']),
    ('un outil sans internet sous Windows', ['windows'], []),
    ('Une appli sans backend en React', ['appli', 'react'], []),
    ('an OCR without GPU using Docker', ['ocr', 'docker'], ['gpu']),
    ('un agent sans abonnement via Claude Code', ['agent', 'claude_code'], []),
    ('un OCR pas avec Docker sous Windows', ['ocr', 'windows'], ['docker']),
    ('un OCR pas avec Docker en Python', ['ocr', 'python'], ['docker']),
    ('an OCR, not for Windows desktop apps in Python', ['ocr', 'desktop', 'application', 'python'], ['windows']),
    # coordination : « ou » entre deux identifiants niés ; « et avec » rouvre
    ('without GPU or Docker', [], ['gpu', 'docker']),
    ('sans GPU et avec Docker', ['docker'], ['gpu']),
    # I6 : « on » pronom français ; « un tutoriel sur React » : React est le sujet
    ('on cherche des workflows n8n', ['workflow', 'n8n'], []),
    ('un tutoriel sur React', ['cours', 'react'], []),
    ('a tutorial on React', ['cours', 'react'], []),
])
def test_revue_portee_negation_et_roles(banc, texte, concepts, exclusions):
    requete = banc.rd.analyser_requete(texte)
    assert [c.cle for c in requete.concepts] == concepts
    assert [e['cible'] for e in requete.exclusions] == exclusions
    react = next((c for c in requete.concepts if c.cle == 'react'), None)
    if 'tutoriel' in texte or 'tutorial' in texte:
        assert react.classe == 'essentiel'


@pytest.mark.parametrize('texte, attendu', [
    # I5a : une négation déjà fermée n'empêche pas la composition ; I5b : même segment, et pas un autre sens
    ('Une recherche sémantique sans cloud dans mon code source', 'recherche_code'),
    ('recherche sémantique pas chère pour du code', 'recherche_code'),
    ('Recherche sémantique dans mes PDF de cours. Le code doit être en Python.', 'recherche_semantique'),
    ("recherche sémantique dans le Code de l'urbanisme", 'recherche_semantique'),
    ('recherche sémantique dans le code du travail', 'recherche_semantique'),
    ('semantic search over legal codes', 'recherche_semantique'),
    ('une recherche sémantique avec QR codes', 'recherche_semantique'),
    ('une recherche sémantique dans le code de mes projets', 'recherche_code'),
])
def test_revue_composition(banc, texte, attendu):
    cles = [c.cle for c in banc.rd.analyser_requete(texte).concepts]
    assert attendu in cles and ({'recherche_code', 'recherche_semantique'} - {attendu}).isdisjoint(cles)


@pytest.mark.parametrize('texte, mot, colonne, nature, sorte', [
    # B2 : négation placée après l'identifiant
    ("Docker n'est pas requis.", 'Docker', 'installation', 'plateforme', 'non_requis'),
    ("Docker isn't required.", 'Docker', 'description', 'plateforme', 'non_requis'),
    ('A GPU is not needed.', 'GPU', 'description', 'materiel', 'non_requis'),
    ('GPU non nécessaire.', 'GPU', 'prerequis', 'materiel', 'non_requis'),
    ("Le GPU n'est pas indispensable.", 'GPU', 'description', 'materiel', 'non_requis'),
    ('Docker: not required', 'Docker', 'prerequis', 'plateforme', 'non_requis'),
    ("doesn't require Docker", 'Docker', 'description', 'plateforme', 'non_requis'),
    # B3 : l'élément de liste entier compte (parenthèses, deux-points, énumérations)
    ('- GPU NVIDIA (optionnel)', 'GPU', 'prerequis', 'materiel', 'non_requis'),
    ('- Docker (recommandé)', 'Docker', 'prerequis', 'plateforme', 'non_requis'),
    ('Optional: Docker', 'Docker', 'prerequis', 'plateforme', 'non_requis'),
    ('- CUDA: optional', 'CUDA', 'prerequis', 'materiel', 'non_requis'),
    ('Windows, macOS ou Linux', 'Windows', 'prerequis', 'plateforme', 'mention'),
    ('Windows / macOS / Linux', 'Windows', 'prerequis', 'plateforme', 'mention'),
    ('- Docker / Podman', 'Docker', 'prerequis', 'plateforme', 'mention'),
    ('- Python 3.10 ou plus récent\n- Docker', 'Docker', 'prerequis', 'plateforme', 'requis'),
    ('Requires Python 3.10 or later and Docker', 'Docker', 'description', 'plateforme', 'requis'),
    # I1 : restrictifs et conditions
    ('Docker est uniquement utilisé pour les tests.', 'Docker', 'description', 'plateforme', 'non_requis'),
    ('Docker only needed for development.', 'Docker', 'description', 'plateforme', 'non_requis'),
    ('Only tested on Windows.', 'Windows', 'description', 'plateforme', 'mention'),
    ('Utilise le GPU si nécessaire.', 'GPU', 'description', 'materiel', 'non_requis'),
    ('If you need GPU acceleration, install CUDA.', 'GPU', 'description', 'materiel', 'non_requis'),
    ('Docker only.', 'Docker', 'description', 'plateforme', 'requis'),
    ('Fonctionne uniquement sous Windows.', 'Windows', 'description', 'plateforme', 'requis'),
    # I3 : « no-code », négation d'un autre nom
    ('Éditeur no-code de workflows pour n8n', 'n8n', 'description', 'produit', 'requis'),
    ('Workflows sans code pour n8n', 'n8n', 'description', 'produit', 'requis'),
    ('No setup needed for n8n workflows', 'n8n', 'description', 'produit', 'requis'),
    # I4 : mot souple ou CPU qui vise un autre élément
    ('Requires an NVIDIA GPU and optionally Docker.', 'GPU', 'description', 'materiel', 'requis'),
    ('Requires an NVIDIA GPU and optionally Docker.', 'Docker', 'description', 'plateforme', 'non_requis'),
    ('Requires a CUDA GPU with no CPU fallback', 'GPU', 'description', 'materiel', 'requis'),
    ("GPU NVIDIA (l'exécution sur CPU n'est pas prise en charge)", 'GPU', 'prerequis', 'materiel', 'requis'),
    ('GPU ou CPU', 'GPU', 'prerequis', 'materiel', 'non_requis'),
    # M1, M2 : « nœud », « comme »
    ('Un nœud n8n pour Notion', 'n8n', 'description', 'produit', 'requis'),
    ('Fonctionne comme n8n', 'n8n', 'description', 'produit', 'non_requis'),
    # optionnel parmi d'autres : « un workflow n8n, Make ou Zapier »
    ('Déclencher un workflow n8n, Make ou Zapier par webhook', 'n8n', 'cas_usage', 'produit', 'mention'),
])
def test_revue_sorte_mention(banc, texte, mot, colonne, nature, sorte):
    assert _sorte(banc.rd, texte, mot, colonne, nature) == sorte


def test_revue_nom_du_depot(banc):
    # M3, revue 2 #27 et #29 : le titre seul (jamais owner/repo) ; « zapier-alternative » n'est pas Zapier
    rd = banc.rd
    assert rd.sorte_titre('n8n', [('n8n',)]) == ('requis', 0, 3)
    assert rd.sorte_titre('n8n-nodes-pdfgen', [('n8n',)]) == ('requis', 0, 3)
    assert rd.sorte_titre('awesome-n8n', [('n8n',)]) == ('mention', 8, 11)     # cite n8n sans en porter le nom
    assert rd.sorte_titre('zapier-alternative', [('zapier',)])[0] == 'mention'
    assert rd.sorte_titre('gpu-free-ocr', [('gpu',)])[0] == 'mention'
    assert rd.sorte_titre('NeMo', [('gpu',), ('cuda',)]) is None
    nom = rd.texte_nom_indexe('n8n', 'n8n-io/n8n')
    assert rd.sorte_mention(nom, 0, 3, 'nom', 'produit') == 'mention'           # lu par sorte_titre


def test_revue_docker_n_est_pas_tout_conteneur(banc):
    # I2 : « sans Docker » ne déclasse pas un dépôt qui demande Podman
    rd = banc.rd

    def fiche(nom, prerequis):
        return page(nom, f'https://github.com/synth/{nom}', props={
            'Description': p_texte("Outil de fusion de PDF."), 'Prérequis': p_texte(prerequis),
            'Catégorie': p_select('OCR/Documents'), 'Brique pour': p_multi()})
    index_du_corpus(rd, [fiche('pdf-podman', '- Podman (conteneur rootless)'), fiche('pdf-docker', '- Docker')])
    reponse = _chercher(rd, 'un outil de fusion de PDF sans Docker')
    etats = {r.cle: [x['etat'] for x in r.exclusions] for r in reponse.resultats}
    assert etats == {'synth/pdf-podman': ['inconnu'], 'synth/pdf-docker': ['requis']}


def test_revue_cartes_graphiques_forme_du_gpu(banc):
    # I7 : « cartes graphiques » est une forme du GPU exclu (la limite matérielle elle-même : test_redecouverte_revue2)
    rd = banc.rd
    index_du_corpus(rd, [page('ocr-cartes', 'https://github.com/synth/ocr-cartes', props={
        'Description': p_texte("OCR de documents scannés."),
        'Prérequis': p_texte('- Deux cartes graphiques récentes avec 16 Go de mémoire'),
        'Catégorie': p_select('OCR/Documents'), 'Brique pour': p_multi()})])
    r = _chercher(rd, 'un OCR pour documents scannés sans GPU').resultats[0]
    assert [x['etat'] for x in r.exclusions] == ['requis']             # « cartes graphiques » est une forme
    assert r.niveau == 'partielle'


def test_revue_liste_filtree_avec_exclusion(banc):
    # I8 : « sans n8n » seul (liste filtrée) : les états sont aussi calculés et affichés
    rd = banc.rd

    def fiche(nom, description):
        return page(nom, f'https://github.com/synth/{nom}', props={'Description': p_texte(description)})
    index_du_corpus(rd, [fiche('n8n-recettes', "Collection de workflows pour n8n."), fiche('autre', "Outil.")])
    reponse = _chercher(rd, 'sans n8n')
    etats = {r.cle: [x['etat'] for x in r.exclusions] for r in reponse.resultats}
    assert etats == {'synth/autre': ['inconnu'], 'synth/n8n-recettes': ['requis']}
    assert [r.cle for r in reponse.resultats] == ['synth/autre', 'synth/n8n-recettes']    # ordre alphabétique
