"""Lot 5, troisième revue contradictoire (docs/QUALIFICATION_LOT5.md § 6) : un cas par constat confirmé.

- Fiches : facultatif qui vise une version ou une quantité (« Requires Docker (Compose v2 recommended) »), virgule
  avant « optional », élément conditionnel ou de bénéfice, double négation, liste imbriquée « Optional: », produit
  « -like », intégration proposée, « GPU et CPU », usage annexe, virgule d'Oxford, variante (« Docker Desktop »),
  « dépend de votre GPU », formes d'un même identifiant, adresse, ligne de commande, valeurs de colonnes.
- Requête : « ne … plus » de mémoire, « I'd like », négations contractées et « neither … nor », mot d'usage suivi
  d'une liaison, « migrating to », « Comme » causal, « jamais utilisé », « je ne connais pas », « code » qui n'est
  pas le corpus, interdiction dans l'explication, garde-fous sans test (« on » pronom, « Code » majuscule, verbes du
  cadre de question, « clone »).
- Classement et sorties : « no-code » ne nie rien, citation du champ avant le titre, limite matérielle, date de la
  fiche citée.
Hors ligne, aucune base Notion réelle.
"""
import re

import pytest
from redecouverte_outils import index_du_corpus, p_multi, p_select, p_texte, page, preparer


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


def _chercher(rd, texte, limite=50):
    con, meta = rd.ouvrir_index_valide()
    try:
        reponse = rd.rechercher(con, rd.analyser_requete(texte), {}, limite, False, meta)
        rd.expliquer(con, reponse)
    finally:
        con.close()
    return reponse


_NATURES = {'gpu': 'materiel', 'docker': 'plateforme', 'n8n': 'produit', 'zapier': 'produit', 'react': 'produit'}
_FORMES = {'gpu': r'gpus?|cuda|vram', 'docker': 'docker', 'n8n': 'n8n', 'zapier': 'zapier', 'react': 'react'}


def _sortes(rd, texte, colonne, cible, n):
    occurrences = [m.span() for m in re.finditer(r'(?i)\b(?:' + _FORMES[cible] + r')\b', texte)][:n]
    return [rd.sorte_mention(texte, a, b, colonne, _NATURES[cible]) for a, b in occurrences]

# =============================================================================
# Fiches
# =============================================================================
@pytest.mark.parametrize('texte, colonne, cible, attendu', [
    # F0 : le facultatif vise une version, un modèle, une quantité ou une valeur qui suit
    ("Outil de fusion de PDF. Requires Docker (Compose v2 recommended).", 'description', 'docker', ['requis']),
    ("- CUDA 11.8+ (12.1 recommended)", 'prerequis', 'gpu', ['requis']),
    ("- Docker 20.10+ (24+ recommended)", 'prerequis', 'docker', ['requis']),
    ("Nécessite un GPU NVIDIA (RTX 3060 ou mieux recommandé).", 'description', 'gpu', ['requis']),
    ("- NVIDIA GPU (RTX 3090 or better recommended)", 'prerequis', 'gpu', ['requis']),
    ("Nécessite Docker (version 24+ recommandée).", 'description', 'docker', ['requis']),
    ("- Docker >= 20.10 (recommended: 24+)", 'prerequis', 'docker', ['requis']),
    ("- NVIDIA GPU with 8 GB VRAM (16 GB recommended)", 'prerequis', 'gpu', ['requis', 'requis']),     # banc
    # … mais vise l'identifiant entier, même accompagné d'une autre de ses formes (classement : un seul état)
    ("- NVIDIA GPU with CUDA (optional)", 'prerequis', 'gpu', ['non_requis', 'non_requis']),
    ("- GPU NVIDIA avec 8 Go de VRAM (recommandé)", 'prerequis', 'gpu', ['non_requis', 'non_requis']),
    ("- A CUDA GPU is (strongly) recommended", 'prerequis', 'gpu', ['non_requis', 'non_requis']),
    # F1 : virgule avant le facultatif
    ("- Docker, optional", 'prerequis', 'docker', ['non_requis']),
    ("- NVIDIA GPU, if available", 'prerequis', 'gpu', ['non_requis']),
    ("- GPU NVIDIA, si disponible", 'prerequis', 'gpu', ['non_requis']),
    ("- GPU, recommended", 'prerequis', 'gpu', ['non_requis']),
    ("- CUDA-capable GPU, optional but recommended", 'prerequis', 'gpu', ['non_requis', 'non_requis']),
    ("- GPU NVIDIA obligatoire, Docker facultatif", 'prerequis', 'gpu', ['requis']),
    # F2, classe 3 : élément conditionnel ou de bénéfice
    ("- If you have an NVIDIA GPU, install CUDA 12.1", 'prerequis', 'gpu', ['non_requis', 'non_requis']),
    ("- Si vous avez un GPU NVIDIA, installez CUDA 12", 'prerequis', 'gpu', ['non_requis', 'non_requis']),
    ("- For GPU acceleration: CUDA 11.8+", 'prerequis', 'gpu', ['mention', 'mention']),
    ("- CUDA 11.8+ (for GPU acceleration)", 'prerequis', 'gpu', ['mention', 'mention']),
    ("- CUDA 11.8+ for GPU support", 'prerequis', 'gpu', ['mention', 'mention']),
    ("- Python 3.10+\n- ffmpeg\n- NVIDIA GPU (for faster inference)", 'prerequis', 'gpu', ['mention']),
    ("- A GPU makes it much faster", 'prerequis', 'gpu', ['mention']),
    ("- GPU NVIDIA pour accélérer l'inférence", 'prerequis', 'gpu', ['mention']),
    ("Requires a GPU for faster inference.", 'description', 'gpu', ['requis']),
    # F3 : double négation
    ("OCR de documents scannés. Ne fonctionne pas sans GPU.", 'description', 'gpu', ['requis']),
    ("This won't work without a CUDA GPU.", 'description', 'gpu', ['requis', 'requis']),
    ("Cannot run without a GPU.", 'description', 'gpu', ['requis']),
    ("Running without Docker is not supported.", 'description', 'docker', ['requis']),
    ("L'exécution sans GPU n'est pas prise en charge.", 'description', 'gpu', ['requis']),
    ("Impossible à utiliser sans GPU.", 'description', 'gpu', ['requis']),
    ("Fonctionne sans GPU.", 'description', 'gpu', ['non_requis']),
    # F4 : élément parent « Optional: » d'une liste imbriquée
    ("- Python 3.10+\n- Optional:\n  - Docker\n  - NVIDIA GPU (CUDA 12)", 'prerequis', 'docker', ['non_requis']),
    ("- Python 3.10+\n- Optional:\n  - Docker\n  - NVIDIA GPU (CUDA 12)", 'prerequis', 'gpu',
     ['non_requis', 'non_requis']),
    # F5 : « X-like », « X-style »
    ("Plateforme d'automatisation open source. Build Zapier-like workflows on your own server.", 'description',
     'zapier', ['non_requis']),
    ("Self-hosted, n8n-like workflow automation platform.", 'description', 'n8n', ['non_requis']),
    ("Self-hosted n8n-style workflows for developers.", 'description', 'n8n', ['non_requis']),
    # F6 : intégration proposée, liste de cibles
    ("Framework-agnostic, with official wrappers for React, Vue and Angular.", 'description', 'react', ['mention']),
    ("Intégrations : nœud n8n, Zapier, Make.", 'description', 'n8n', ['mention']),
    ("Also ships an n8n community node.", 'description', 'n8n', ['mention']),
    ("Fournit aussi un nœud n8n.", 'description', 'n8n', ['mention']),
    ("Nœud communautaire pour n8n qui génère des PDF.", 'description', 'n8n', ['requis']),
    ("Convertisseur qui transforme des Zaps exportés depuis Zapier en workflows n8n importables, en signalant les "
     "étapes sans équivalent.", 'description', 'n8n', ['requis']),
    # F7 : GPU et CPU
    ("- Runs on both GPU and CPU", 'prerequis', 'gpu', ['non_requis']),
    ("- GPU and CPU supported", 'prerequis', 'gpu', ['non_requis']),
    ("- Supports CUDA, ROCm and CPU", 'prerequis', 'gpu', ['non_requis']),
    # F8 : usage annexe, avec ou sans « only »
    ("- Docker (for running the integration tests)", 'prerequis', 'docker', ['mention']),
    ("Transcription audio auto-hébergée. GPU required for training only.", 'description', 'gpu', ['non_requis']),
    ("- Docker (for development only)", 'prerequis', 'docker', ['non_requis']),
    ("GPU requis pour l'entraînement uniquement.", 'description', 'gpu', ['non_requis']),
    ("- Docker to run the tests", 'prerequis', 'docker', ['mention']),
    ("- Docker (to run the demo)", 'prerequis', 'docker', ['mention']),
    # F9 : virgule d'Oxford
    ("- Docker, Podman, or any OCI runtime", 'prerequis', 'docker', ['mention']),
    ("- Works with React, Vue, Angular, or vanilla JS", 'prerequis', 'react', ['mention']),
    # F10 : variante niée
    ("- Docker Desktop n'est pas nécessaire : Docker Engine suffit.", 'prerequis', 'docker', ['mention', 'requis']),
    ("- Docker Desktop is not required; Docker Engine is enough.", 'prerequis', 'docker', ['mention', 'requis']),
    ("- Docker Engine (Docker Desktop not required)", 'prerequis', 'docker', ['requis', 'mention']),
    # F11 : performance qui dépend du GPU
    ("Transcription audio auto-hébergée. Le temps de traitement dépend de votre GPU.", 'description', 'gpu',
     ['mention']),
    ("La vitesse dépend du GPU utilisé.", 'description', 'gpu', ['mention']),
    ("Ce projet dépend de Docker.", 'description', 'docker', ['requis']),
    # docs 2 : adresse, ligne de commande
    ("- Image docker.io/acme/ocr:latest", 'prerequis', 'docker', ['mention']),
    ("pip install zapier-alternative", 'installation', 'zapier', ['mention']),
    ("docker compose up -d", 'installation', 'docker', ['mention']),
    ("Docker Compose is required.", 'installation', 'docker', ['requis']),
])
def test_sorte_revue3(banc, texte, colonne, cible, attendu):
    assert _sortes(banc.rd, texte, colonne, cible, len(attendu)) == attendu


def test_valeurs_de_colonnes_jamais_une_preuve(banc):
    # docs 2 : « Workflows n8n » en Brique pour serait « requis » sans la garde des colonnes valeurs
    rd = banc.rd
    for colonne in ('brique_pour', 'categorie', 'type'):
        for texte in ('Workflows n8n', 'Nœuds n8n'):
            a = texte.index('n8n')
            assert rd.sorte_mention(texte, a, a + 3, colonne, 'produit') == 'mention'
    assert rd.sorte_mention('Workflows n8n', 10, 13, 'description', 'produit') == 'requis'

# =============================================================================
# Requête
# =============================================================================
def _analyse(rd, texte):
    q = rd.analyser_requete(texte)
    return ({c.cle: (c.classe, c.role) for c in q.concepts}, [(e['cible'], e['source']) for e in q.exclusions],
            q.nies)


@pytest.mark.parametrize('texte, present, exclusions', [
    # R0 : « ne … plus » de mémoire ; devant une technologie, une exclusion
    ("Je ne me souviens plus du nom de l'outil d'OCR en Python", 'ocr', []),
    ("je ne sais plus quel dépôt faisait de la transcription audio", 'stt', []),
    ("je n'arrive plus à retrouver l'outil de scraping que j'avais enregistré", 'scraping', []),
    ("Je ne trouve plus ce projet de tableau de bord en React", 'tableau_bord', []),
    ("un OCR, je ne veux plus de Docker", 'ocr', [('docker', 'exclusion')]),
    # R1 : « I'd like » est un souhait
    ("I'd like a React component library with sortable data tables for an admin dashboard", 'react', []),
    ("I would like n8n templates to automate my CRM", 'n8n', []),
    ("something like n8n but self-hosted", 'workflow', [('n8n', 'reference')]),
    # R2 : négations contractées, neither … nor
    ("I want to orchestrate my Python invoice-processing scripts, but I don't want n8n.", 'python',
     [('n8n', 'exclusion')]),
    ("an OCR that doesn't need a GPU", 'ocr', [('gpu', 'exclusion')]),
    ("OCR tool, can't use Docker", 'ocr', [('docker', 'exclusion')]),
    ("OCR, I cannot install Docker", 'ocr', [('docker', 'exclusion')]),
    ("Neither n8n nor Zapier", None, [('n8n', 'exclusion'), ('zapier', 'exclusion')]),
    ("an OCR that needs neither Docker nor a GPU", 'ocr', [('docker', 'exclusion'), ('gpu', 'exclusion')]),
    # R3 : mot d'usage suivi d'une liaison
    ("I need incoming order emails turned into JSON records, without depending on n8n or Zapier.", 'email',
     [('n8n', 'exclusion'), ('zapier', 'exclusion')]),
    ("self-hosted workflow automation without relying on Docker", 'workflow', [('docker', 'exclusion')]),
    ("automate my invoices without paying for Zapier", 'automatisation', [('zapier', 'exclusion')]),
    ("un outil d'automatisation sans payer pour Zapier", 'automatisation', [('zapier', 'exclusion')]),
    ("an OCR without running on a GPU", 'ocr', [('gpu', 'exclusion')]),
    ("un OCR sans devoir tourner sur un GPU", 'ocr', [('gpu', 'exclusion')]),
    # R4 : destination d'une migration, « Comme » causal
    ("I'm migrating to n8n and need ready-made workflow templates", 'n8n', []),
    ("Comme n8n est déjà installé sur mon serveur, je cherche des modèles de workflows prêts à importer", 'n8n', []),
    ("migrer de Zapier vers n8n", 'n8n', [('zapier', 'reference')]),
    # R5 : expérience ou connaissance de l'utilisateur
    ("Je n'ai jamais utilisé n8n, je cherche des modèles de workflows prêts à importer", 'workflow', []),
    ("I've never used n8n before, I need ready-made workflow templates to get started", 'workflow', []),
    ("je ne connais pas n8n, je voudrais des modèles de workflows tout prêts", 'workflow', []),
    ("I don't know Docker, I need a simple OCR", 'ocr', []),
    ("sans utiliser n8n", None, [('n8n', 'exclusion')]),
    # R7 : interdiction dans l'explication
    ("un OCR sans Docker : les conteneurs sont interdits sur ce serveur", 'ocr', [('docker', 'exclusion')]),
    ("A tool to merge and compress PDFs without Docker, because Docker is not allowed on our laptops", 'pdf',
     [('docker', 'exclusion')]),
    ("Self-hosted workflow automation that doesn't rely on Docker — containers aren't allowed on that server.",
     'workflow', [('docker', 'exclusion')]),
    # inchangés
    ("a React web app, not React Native", 'react', []),
    ("pas pour analyser des PDF", 'pdf', []),
])
def test_requete_revue3(banc, texte, present, exclusions):
    concepts, obtenues, _ = _analyse(banc.rd, texte)
    assert obtenues == exclusions
    if present:
        assert present in concepts
    assert not {cible for cible, source in exclusions if source == 'exclusion'} & set(concepts)


def test_identifiant_seulement_nie(banc):
    rd = banc.rd
    for texte in ("Je n'ai jamais utilisé n8n", "je ne connais pas n8n"):
        concepts, exclusions, nies = _analyse(rd, texte)
        assert 'n8n' in nies and 'n8n' not in concepts and exclusions == []
    concepts, _, nies = _analyse(rd, 'sans passer via un service cloud')
    assert nies == ['passer', 'service', 'cloud'] and not concepts


@pytest.mark.parametrize('texte, attendu', [
    # R6 : « code » qui n'est pas le corpus où l'on cherche
    ('semantic search over my PDFs with code examples', 'recherche_semantique'),
    ('I want to code a semantic search for my PDF library', 'recherche_semantique'),
    ('a vs code extension for semantic search in my markdown notes', 'recherche_semantique'),
    # docs 3 : « Code » avec une majuscule en cours de phrase (hors liste)
    ('recherche sémantique dans le Code du sport', 'recherche_semantique'),
    ('recherche sémantique dans le Code de la sécurité intérieure', 'recherche_semantique'),
    # gardés
    ('Semantic search through my source code in a local repository', 'recherche_code'),
    ('semantic search across my Python code', 'recherche_code'),
    ('une recherche sémantique dans mon code source', 'recherche_code'),
    ('recherche sémantique de code Python', 'recherche_code'),
])
def test_composition_revue3(banc, texte, attendu):
    cles = {c.cle for c in banc.rd.analyser_requete(texte).concepts}
    assert attendu in cles and not {'recherche_semantique', 'recherche_code'} - {attendu} & cles


def test_garde_fous_requete(banc):
    # docs 3 : « on » pronom (cible), verbes du cadre de question, « clone » après un produit
    rd = banc.rd
    concepts, _, _ = _analyse(rd, 'on cherche des workflows n8n')
    assert concepts['n8n'][0] == 'essentiel'
    concepts, _, _ = _analyse(rd, 'workflows running on n8n')
    assert concepts['n8n'][0] == 'contrainte'
    concepts, _, _ = _analyse(rd, "un outil d'OCR qui nécessite peu de ressources")
    assert 'necessite' not in concepts and 'ocr' in concepts
    concepts, exclusions, _ = _analyse(rd, 'a Zapier clone')
    assert 'clone' not in concepts and exclusions == [('zapier', 'reference')]

# =============================================================================
# Classement et sorties
# =============================================================================
def _fiche(nom, **champs):
    props = {'Catégorie': p_select('Automatisation/No-code'), 'Brique pour': p_multi()}
    props.update({colonne: p_texte(texte) for colonne, texte in champs.items()})
    return page(nom, f'https://github.com/synth/{nom}', props=props)


def test_no_code_ne_nie_rien(banc):
    # classement 2 : « No-code workflow automation platform » parle de workflows
    rd = banc.rd
    assert not rd.occurrence_niee('No-code workflow automation platform.', 8, 16)
    assert rd.occurrence_niee('Fonctionne sans GPU.', 16, 19)
    index_du_corpus(rd, [_fiche('flow-nocode', Description="No-code workflow automation platform, an open-source "
                                                           "alternative to Zapier."),
                         _fiche('flow-simple', Description="Workflow automation platform.")])
    reponse = _chercher(rd, 'an alternative to n8n')
    assert {r.cle: r.m.get('workflow') for r in reponse.resultats} == {'synth/flow-nocode': 1.0,
                                                                       'synth/flow-simple': 1.0}


def test_citation_du_champ_avant_le_titre(banc):
    # classement 5 : à sorte égale, le Prérequis ou la Description avant le Nom ; la limite matérielle reste
    rd = banc.rd
    index_du_corpus(rd, [
        page('whisper-gpu', 'https://github.com/synth/whisper-gpu', props={
            'Description': p_texte("Transcription audio de réunions, accélérée par CUDA sur carte NVIDIA."),
            'Catégorie': p_select('Audio'), 'Brique pour': p_multi()}),
        page('gpu-ocr-server', 'https://github.com/synth/gpu-ocr-server', props={
            'Description': p_texte("Transcription audio de réunions."),
            'Prérequis': p_texte('- NVIDIA GPU with at least 8 GB VRAM (required)'),
            'Catégorie': p_select('Audio'), 'Brique pour': p_multi()})])
    resultats = {r.cle: r for r in _chercher(rd, 'transcription audio de réunions sans GPU').resultats}
    serveur = resultats['synth/gpu-ocr-server'].exclusions[0]
    assert serveur['etat'] == 'requis' and serveur['citations'][0]['champ'] == 'Prérequis'
    whisper = resultats['synth/whisper-gpu']
    assert whisper.exclusions[0]['citations'][0]['champ'] == 'Description'
    assert 'materiel' not in [a['code'] for a in whisper.a_verifier]   # la Description est citée
    # une seule preuve, le titre : la limite matérielle factuelle reste affichée
    index_du_corpus(rd, [page('gpu-tools', 'https://github.com/synth/gpu-tools', props={
        'Description': p_texte("Transcription audio de réunions sur carte NVIDIA."),
        'Catégorie': p_select('Audio'), 'Brique pour': p_multi()})])
    r = _chercher(rd, 'transcription audio de réunions sans GPU').resultats[0]
    assert r.exclusions[0]['citations'][0]['champ'] == 'Nom'
    assert 'materiel' in [a['code'] for a in r.a_verifier]


def test_citation_datee(banc, capsys):
    # classement 6 : la ligne Exclusion dit de quelle fiche du dépôt vient la citation
    rd = banc.rd
    index_du_corpus(rd, [page('ocr-gpu', 'https://github.com/synth/ocr-gpu', props={
        'Description': p_texte("OCR de documents scannés."), 'Prérequis': p_texte('- NVIDIA GPU avec CUDA 12'),
        'Catégorie': p_select('OCR/Documents'), 'Brique pour': p_multi()})])
    assert banc.lancer('cherche', 'un OCR pour documents scannés sans GPU') == 0
    sortie = ' '.join(capsys.readouterr().out.split())
    assert "(Prérequis · fiche v7.3+ du 2026-10-11 : « - NVIDIA GPU avec CUDA 12 »)" in sortie
