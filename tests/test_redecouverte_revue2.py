"""Lot 5, seconde revue contradictoire (docs/QUALIFICATION_LOT5.md § 6) : un cas par constat confirmé.

- Fiches : « requis » n'est retenu que sur une tournure sans ambiguïté (sinon « mention », qui ne change pas le
  classement) ; groupe de la mention, coordination, négations sans mot d'exigence, « ne … que », exigence qui
  gouverne un autre membre, listes de plateformes, références, formes du GPU, CPU possible, disjonctions de versions
  ou de marques, noms ambigus, titre seul, adresses, citation entière, limite matérielle.
- Requête : identifiant demandé et nié, négation qui ne touche pas l'identifiant, prépositions, produit avant
  « alternatives » ou après « comme », composition en rôle référence ou dans un autre sens, coordination après
  « pas avec », sujet d'un cours, « ne … plus », « on » pronom.
- Sorties : en-têtes « À remplacer », « Indifférent », négations filtrées, source par résultat dans le JSON.
Hors ligne, aucune base Notion réelle.
"""
import json
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


_NATURES = {'gpu': 'materiel', 'docker': 'plateforme', 'windows': 'plateforme', 'linux': 'plateforme',
            'macos': 'plateforme', 'n8n': 'produit', 'zapier': 'produit'}
_FORMES = {'gpu': r'gpus?|cuda|vram|graphics cards?|cartes? graphiques?', 'docker': 'docker', 'windows': 'windows',
           'linux': 'linux', 'macos': 'macos', 'n8n': 'n8n', 'zapier': 'zapier'}


def _sortes(rd, texte, colonne, cible, n):
    occurrences = [m.span() for m in re.finditer(r'(?i)\b(?:' + _FORMES[cible] + r')\b', texte)][:n]
    return [rd.sorte_mention(texte, a, b, colonne, _NATURES[cible]) for a, b in occurrences]

# =============================================================================
# Fiches : ce que dit chaque mention
# =============================================================================
@pytest.mark.parametrize('texte, colonne, cible, attendu', [
    # #13 : le « facultatif » ou la négation d'un groupe coordonné vaut pour tous ses membres
    ("- GPU et Docker facultatifs", 'prerequis', 'gpu', 'non_requis'),
    ("- GPU et Docker facultatifs", 'prerequis', 'docker', 'non_requis'),
    ("- GPU acceleration is supported but not required", 'prerequis', 'gpu', 'non_requis'),
    ("Docker and a GPU are optional", 'description', 'docker', 'non_requis'),
    ("Docker and a GPU are optional", 'description', 'gpu', 'non_requis'),
    ("Docker is supported but not required", 'description', 'docker', 'non_requis'),
    ("GPU and optionally Docker", 'prerequis', 'gpu', 'requis'),
    ("GPU and optionally Docker", 'prerequis', 'docker', 'non_requis'),
    # #14 : neither / nor
    ("OCR de documents scannés. Neither Docker nor a GPU is required.", 'description', 'gpu', 'non_requis'),
    ("Neither Docker nor a GPU is required.", 'prerequis', 'docker', 'non_requis'),
    # #15 : négation sans mot d'exigence, ou seule en fin d'élément
    ("- GPU : non", 'prerequis', 'gpu', 'non_requis'),
    ("- GPU: none", 'prerequis', 'gpu', 'non_requis'),
    ("- Un GPU n'est pas un prérequis", 'prerequis', 'gpu', 'non_requis'),
    ("- Docker is not a requirement", 'prerequis', 'docker', 'non_requis'),
    ("- Docker: not a hard requirement", 'prerequis', 'docker', 'non_requis'),
    # #16 : exigence restreinte placée après (« ne … que », « required only for »)
    ("Un GPU n'est nécessaire que pour l'entraînement.", 'description', 'gpu', 'non_requis'),
    ("A GPU is required only for training.", 'description', 'gpu', 'non_requis'),
    ("GPU needed only for fine-tuning.", 'description', 'gpu', 'non_requis'),
    ("Docker n'est requis que pour le déploiement.", 'description', 'docker', 'non_requis'),
    # #17 : l'exigence gouverne un autre membre de la phrase
    ("Requires Python 3.10 and supports GPU acceleration via CUDA.", 'description', 'gpu', 'mention'),
    ("Requires Python 3.10 and can also run in Docker.", 'description', 'docker', 'mention'),
    ("Needs Node.js 18 and ships a Docker Compose file.", 'description', 'docker', 'mention'),
    ("Requires Python and Docker", 'description', 'docker', 'requis'),
    # #18, #34 : plateformes multiples ; « Windows 10 ou 11 uniquement » reste une exigence
    ("- Windows 10/11, macOS 12+, Ubuntu 22.04+", 'prerequis', 'windows', 'mention'),
    ("- Fonctionne sous Windows et Linux", 'prerequis', 'windows', 'mention'),
    ("- Windows : utiliser WSL2", 'prerequis', 'windows', 'mention'),
    ("- Windows, macOS, Linux", 'prerequis', 'windows', 'mention'),
    ("- Windows, macOS et Linux", 'prerequis', 'windows', 'mention'),
    ("- Windows 10 ou 11 uniquement", 'prerequis', 'windows', 'requis'),
    # #19 : produit à remplacer, migration
    ("a self-hosted substitute for Zapier", 'description', 'zapier', 'non_requis'),
    ("solution de remplacement pour Zapier", 'description', 'zapier', 'non_requis'),
    ("Importez vos workflows Zapier existants en un clic", 'description', 'zapier', 'mention'),
    ("Convertisseur qui transforme des Zaps exportés depuis Zapier en workflows n8n", 'description', 'zapier',
     'mention'),
    ("Collection de workflows pour Zapier", 'description', 'zapier', 'requis'),
    # #21, #22 : CPU possible ; négation avant ou après « CPU »
    ("- NVIDIA GPU (CPU inference supported)", 'prerequis', 'gpu', 'non_requis'),
    ("- GPU NVIDIA (mode CPU disponible, plus lent)", 'prerequis', 'gpu', 'non_requis'),
    ("- GPU NVIDIA (le mode CPU fonctionne aussi)", 'prerequis', 'gpu', 'non_requis'),
    ("GPU NVIDIA obligatoire, aucun repli sur CPU.", 'description', 'gpu', 'requis'),
    ("Requiert un GPU NVIDIA et ne fonctionne pas sur CPU.", 'description', 'gpu', 'requis'),
    ("Requires an NVIDIA GPU, without CPU fallback.", 'description', 'gpu', 'requis'),
    ("Requires an NVIDIA GPU and does not run on CPU.", 'description', 'gpu', 'requis'),
    ("Requires a GPU (on CPU it is unusably slow).", 'description', 'gpu', 'requis'),
    # #23 : la virgule borne le groupe
    ("- GPU NVIDIA obligatoire, Docker facultatif", 'prerequis', 'gpu', 'requis'),
    ("- GPU NVIDIA obligatoire, Docker facultatif", 'prerequis', 'docker', 'non_requis'),
    ("- Docker requis, GPU optionnel", 'prerequis', 'docker', 'requis'),
    ("- Docker requis, GPU optionnel", 'prerequis', 'gpu', 'non_requis'),
    ("Requires an NVIDIA GPU, Docker optional.", 'description', 'gpu', 'requis'),
    ("- Pas de GPU, Docker obligatoire", 'prerequis', 'docker', 'requis'),
    ("- No GPU, Docker only", 'prerequis', 'docker', 'requis'),
    # #24 : « comme » / « like » seulement pour un produit
    ("Se déploie comme un conteneur Docker.", 'installation', 'docker', 'mention'),
    ("Requires a dedicated graphics card like an NVIDIA RTX 3060.", 'description', 'gpu', 'requis'),
    ("S'installe comme un service Windows.", 'installation', 'windows', 'mention'),
    ("Install it like any other n8n community node.", 'installation', 'n8n', 'requis'),
    # #25 : versions ou marques d'un même identifiant
    ("Requires an NVIDIA or AMD GPU.", 'description', 'gpu', 'requis'),
    ("- GPU NVIDIA ou AMD", 'prerequis', 'gpu', 'requis'),
    ("- CUDA 11.8 ou 12.1", 'prerequis', 'gpu', 'requis'),
    ("- Python 3.10+ ou Docker (au choix)", 'prerequis', 'docker', 'mention'),
    # #26, #36 : noms polysémiques
    ("Peut déléguer l'inférence à des GPU cloud à la demande.", 'description', 'gpu', 'mention'),
    ("Image Docker disponible sur demande.", 'description', 'docker', 'mention'),
    ("Fournit tout le nécessaire pour un déploiement Docker.", 'description', 'docker', 'mention'),
    ("Extraction de factures PDF en JSON. Exporte vers n8n à la demande.", 'description', 'n8n', 'mention'),
    ("Génère des sous-titres à la demande sur GPU", 'description', 'gpu', 'mention'),
    ("Covers all your automation needs with n8n", 'description', 'n8n', 'mention'),
    # #33 : non pris en charge, incompatible
    ("- Linux avec systemd (Windows et macOS non pris en charge)", 'prerequis', 'windows', 'non_requis'),
    ("- GPU not supported", 'prerequis', 'gpu', 'non_requis'),
    ("Windows is not supported", 'prerequis', 'windows', 'non_requis'),
    ("Docker non supporté", 'prerequis', 'docker', 'non_requis'),
    ("Incompatible avec Windows", 'prerequis', 'windows', 'non_requis'),
    ("Requires a GPU and does not support Windows.", 'description', 'gpu', 'requis'),
    ("Docker: Windows not supported", 'prerequis', 'docker', 'requis'),
    # #37 : restrictif collé : exigence, sauf usage annexe
    ("Windows only for now.", 'description', 'windows', 'requis'),
    ("Linux uniquement pour le moment.", 'description', 'linux', 'requis'),
    ("Linux only in this release.", 'description', 'linux', 'requis'),
    ("Windows uniquement en version 1.", 'description', 'windows', 'requis'),
    ("macOS only with Apple Silicon", 'description', 'macos', 'requis'),
    ("Ne fonctionne que sous Linux.", 'description', 'linux', 'requis'),
    ("Docker only needed for development.", 'description', 'docker', 'non_requis'),
    ("Docker est uniquement utilisé pour les tests.", 'description', 'docker', 'non_requis'),
    # « ne … plus », en-tête facultatif, adresse
    ("Docker n'est plus nécessaire depuis la v2.", 'description', 'docker', 'non_requis'),
    ("Ne nécessite plus Docker.", 'description', 'docker', 'non_requis'),
    ("Recommandé : 16 Go de RAM, GPU NVIDIA", 'prerequis', 'gpu', 'non_requis'),
    ("git clone https://github.com/synth-zapkit/zapier-app-starter.git", 'installation', 'zapier', 'mention'),
    ("Déclencher un workflow n8n, Make ou Zapier par webhook", 'cas_usage', 'n8n', 'mention'),
])
def test_sorte_prudente(banc, texte, colonne, cible, attendu):
    assert _sortes(banc.rd, texte, colonne, cible, 1) == [attendu]


def test_occurrences_d_un_meme_texte(banc):
    rd = banc.rd
    assert _sortes(rd, "- NVIDIA GPU with 8 GB VRAM, 32 GB RAM recommended", 'prerequis', 'gpu', 2) == \
        ['requis', 'requis']
    assert _sortes(rd, "Requires a CUDA GPU with no CPU fallback", 'description', 'gpu', 2) == ['requis', 'requis']


def test_nvidia_seul_n_est_pas_un_gpu(banc):
    # #20 : une clé d'API NVIDIA NIM ou un modèle NVIDIA ne prouve pas un GPU
    rd = banc.rd
    assert 'nvidia' not in rd.lexique.FORMES_EXCLUSION['gpu']

    def fiche(nom, prerequis):
        return page(nom, f'https://github.com/synth/{nom}', props={
            'Description': p_texte("OCR de documents scannés."), 'Prérequis': p_texte(prerequis),
            'Catégorie': p_select('OCR/Documents'), 'Brique pour': p_multi()})
    index_du_corpus(rd, [fiche('ocr-nim', "- Clé d'API NVIDIA NIM (gratuite)"),
                         fiche('ocr-parakeet', "- Modèle NVIDIA Parakeet (téléchargé automatiquement)")])
    reponse = _chercher(rd, 'un OCR pour documents scannés sans GPU')
    assert {r.cle: [x['etat'] for x in r.exclusions] for r in reponse.resultats} == {
        'synth/ocr-nim': ['inconnu'], 'synth/ocr-parakeet': ['inconnu']}
    assert all(r.niveau == 'forte' for r in reponse.resultats)

# =============================================================================
# Fiches : titre, citation, limite matérielle
# =============================================================================
def _fiche(nom, cle, **champs):
    props = {'Catégorie': p_select('OCR/Documents'), 'Brique pour': p_multi()}
    props.update({colonne: p_texte(texte) for colonne, texte in champs.items()})
    return page(nom, f'https://github.com/{cle}', props=props)


def test_titre_seul_jamais_le_proprietaire(banc):
    # #27 : NVIDIA/NeMo, docker/awesome-compose : le propriétaire n'est pas une preuve ; #29 : « zapier-alternative »
    rd = banc.rd
    index_du_corpus(rd, [
        _fiche('NeMo', 'NVIDIA/NeMo', Description="OCR de documents scannés et reconnaissance vocale."),
        _fiche('gpu-free-ocr', 'synth/gpu-free-ocr', Description="OCR de documents scannés."),
        _fiche('gpu-ocr', 'synth/gpu-ocr', Description="OCR de documents scannés.")])
    reponse = _chercher(rd, 'un OCR pour documents scannés sans GPU')
    etats = {r.cle: [x['etat'] for x in r.exclusions] for r in reponse.resultats}
    assert etats == {'nvidia/nemo': ['inconnu'], 'synth/gpu-free-ocr': ['mention'], 'synth/gpu-ocr': ['requis']}
    gpu_free = next(r for r in reponse.resultats if r.cle == 'synth/gpu-free-ocr')
    assert gpu_free.niveau == 'forte'               # citée par la commande d'installation, avant le titre
    assert gpu_free.exclusions[0]['citations'][0]['citation'] == 'pip install gpu-free-ocr'


def test_titre_alternative_a_un_produit(banc):
    rd = banc.rd
    index_du_corpus(rd, [page('zapier-alternative', 'https://github.com/synth/zapier-alternative', props={
        'Description': p_texte("Plateforme d'automatisation de workflows open source et auto-hébergée."),
        'Catégorie': p_select('Automatisation/No-code'), 'Brique pour': p_multi()})])
    r = _chercher(rd, 'une alternative à Zapier').resultats[0]
    assert r.niveau == 'forte' and r.exclusions == []       # « mention » d'un produit à remplacer : non affichée


def test_citation_entiere_jusqu_a_220_caracteres(banc):
    # #31 : le mot qui fonde l'état reste dans la citation
    rd = banc.rd
    description = ("Cet outil de fusion de PDF nécessite une installation préalable de Docker sur la machine hôte "
                   "pour fonctionner correctement.")
    index_du_corpus(rd, [_fiche('pdf-docker', 'synth/pdf-docker', Description=description)])
    x = _chercher(rd, 'un outil de fusion de PDF sans Docker').resultats[0].exclusions[0]
    assert x['etat'] == 'requis' and x['citations'][0]['citation'] == description


def _limites(r):
    return [entree['code'] for entree in r.a_verifier]


def test_limite_materielle_dans_les_deux_sens(banc):
    # #30, #38, #43 : la limite matérielle factuelle reste affichée sauf si la ligne Exclusion cite un champ factuel
    rd = banc.rd
    justification = ("[LLM mistral-small-2603 · profil 2026-10-11/8c41d2] U1·P3·T2·I2·C2·M2·L2 = 9 — "
                     "Fonctionne aussi sans GPU d'après le README.")
    index_du_corpus(rd, [
        _fiche('ocr-cuda', 'synth/ocr-cuda', Description="OCR de documents scannés accéléré par CUDA sur carte NVIDIA.",
               Justification=justification),
        _fiche('ocr-gpu', 'synth/ocr-gpu', Description="OCR de documents scannés.",
               **{'Prérequis': '- NVIDIA GPU with CUDA support'}),
        _fiche('ocr-nvidia', 'synth/ocr-nvidia', Description="OCR de documents scannés, optimisé pour NVIDIA.")])
    sans = {r.cle: r for r in _chercher(rd, 'un OCR pour documents scannés sans GPU').resultats}
    avec = {r.cle: r for r in _chercher(rd, 'un OCR pour documents scannés').resultats}
    # #30 : seul l'avis du LLM se prononce (« fonctionne aussi sans GPU ») : la limite factuelle reste affichée
    assert 'materiel' in _limites(avec['synth/ocr-cuda'])
    assert sans['synth/ocr-cuda'].exclusions[0]['etat'] == 'avis_non_requis'
    assert 'materiel' in _limites(sans['synth/ocr-cuda'])
    # preuve factuelle (Prérequis) : la ligne Exclusion la cite et remplace la limite
    assert 'materiel' in _limites(avec['synth/ocr-gpu'])
    assert 'materiel' not in _limites(sans['synth/ocr-gpu']) and sans['synth/ocr-gpu'].exclusions[0]['etat'] == 'requis'
    # aucune preuve (NVIDIA seul n'est pas une forme du GPU exclu) : la limite reste
    assert sans['synth/ocr-nvidia'].exclusions[0]['etat'] == 'inconnu'
    assert 'materiel' in _limites(sans['synth/ocr-nvidia']) and 'materiel' in _limites(avec['synth/ocr-nvidia'])


def test_avis_seul_ne_masque_pas_la_limite(banc):
    rd = banc.rd
    justification = ("[LLM mistral-small-2603 · profil 2026-10-11/8c41d2] U1·P3·T2·I2·C2·M2·L2 = 9 — "
                     "Demande un GPU puissant.")
    index_du_corpus(rd, [_fiche('ocr-vram', 'synth/ocr-vram', Description="OCR de documents scannés, optimisé NVIDIA.",
                                Justification=justification)])
    r = _chercher(rd, 'un OCR pour documents scannés sans GPU').resultats[0]
    assert r.exclusions[0]['etat'] == 'avis_requis' and r.niveau == 'forte'
    assert 'materiel' in _limites(r)

# =============================================================================
# Requête
# =============================================================================
def _analyse(rd, texte):
    q = rd.analyser_requete(texte)
    return ({c.cle: (c.classe, c.role) for c in q.concepts},
            [(e['cible'], e['source']) for e in q.exclusions], q.nies)


@pytest.mark.parametrize('texte, present, exclusions', [
    # #0 : identifiant demandé et nié : la variante niée n'exclut pas l'identifiant
    ('a React web app, not React Native', 'react', []),
    ('workflows for self-hosted n8n, not n8n cloud', 'n8n', []),
    ('un OCR avec Docker mais pas Docker Desktop', 'docker', []),
    ('un serveur OCR sous Debian, pas sous Ubuntu', 'linux', []),
    ('transcription audio sur GPU AMD (pas NVIDIA)', 'gpu', []),
    # #1 : la négation porte sur un autre mot
    ("I'm not sure whether to use n8n or Zapier for invoice automation", 'automatisation', []),   # indifférents
    ('Je ne sais pas si je dois utiliser n8n ou Zapier pour automatiser mes factures', 'zapier', []),
    ("je n'ai pas encore choisi entre n8n et Zapier", 'zapier', []),
    ('pas que pour n8n', 'n8n', []),
    ('not only for n8n', 'n8n', []),
    # … mais un verbe d'usage garde l'exclusion
    ('des scripts Python sans passer par n8n', 'python', [('n8n', 'exclusion')]),
    ('A tool to merge PDFs, without installing Docker.', 'pdf', [('docker', 'exclusion')]),
    ('une recherche sémantique dans mes PDF, mais sans être obligé de passer par Docker', 'pdf',
     [('docker', 'exclusion')]),
    ('back up my VPS without needing Kubernetes', 'auto_heberge', [('kubernetes', 'exclusion')]),
    # #3 : produit avant « alternatives », après « comme », « like », « similar to », « remplacer »
    ('open-source n8n alternatives', 'workflow', [('n8n', 'reference')]),
    ('self-hosted Zapier alternatives', 'workflow', [('zapier', 'reference')]),
    ('un outil comme n8n mais auto-hébergé', 'workflow', [('n8n', 'reference')]),
    ('something like Zapier but self-hosted', 'workflow', [('zapier', 'reference')]),
    ('similar to n8n', 'workflow', [('n8n', 'reference')]),
    ('remplacer Zapier par un outil open source', 'workflow', [('zapier', 'reference')]),
    ('a Zapier clone', 'workflow', [('zapier', 'reference')]),
    ('An open-source coding agent similar to Claude Code', 'agent_code', [('claude_code', 'reference')]),
    # #5, #35 : « pas avec X ou Y » exclut les deux
    ('an OCR server, not with Docker or Kubernetes', 'ocr', [('docker', 'exclusion'), ('kubernetes', 'exclusion')]),
    ('a desktop app not for Windows or macOS', 'application', [('windows', 'exclusion'), ('macos', 'exclusion')]),
    ('un OCR, pas avec Docker ou Kubernetes', 'ocr', [('docker', 'exclusion'), ('kubernetes', 'exclusion')]),
    ('an automation tool, not for n8n or Zapier', 'automatisation', [('n8n', 'exclusion'), ('zapier', 'exclusion')]),
    ('pas avec Docker en Python', 'python', [('docker', 'exclusion')]),
    ('without GPU or a Docker', None, [('gpu', 'exclusion'), ('docker', 'exclusion')]),
    # #9 : « ne … plus », « no longer »
    ('un OCR, je ne veux plus de Docker', 'ocr', [('docker', 'exclusion')]),
    ("je n'utilise plus Zapier", None, [('zapier', 'exclusion')]),
    ('I no longer use Zapier', None, [('zapier', 'exclusion')]),
])
def test_exclusion_selon_la_requete(banc, texte, present, exclusions):
    concepts, obtenues, _ = _analyse(banc.rd, texte)
    assert obtenues == exclusions
    if present:
        assert present in concepts
    assert not {cible for cible, source in exclusions if source == 'exclusion'} & set(concepts)


def test_identifiant_nie_reste_non_cherche(banc):
    concepts, exclusions, nies = _analyse(banc.rd, "I'm not sure whether to use n8n or Zapier")
    assert 'n8n' not in concepts and 'n8n' in nies and exclusions == []


@pytest.mark.parametrize('texte, cherches, nies', [
    # #2 : une préposition ne referme la négation que devant un identifiant
    ('transcrire des réunions sans passer via un service cloud', [], ['passer', 'service', 'cloud']),
    ('un générateur de quiz sans programmation en JavaScript', [], ['programmation', 'JavaScript']),
    ('créer un site web sans écrire de code en Python', [], ['écrire', 'code', 'Python']),
    ('OCR de factures sans envoi des données via une API externe', [], ['envoi', 'données', 'API', 'externe']),
    ('sans GPU sous Windows', ['windows'], ['GPU']),
    ('without GPU using Docker', ['docker'], ['GPU']),
])
def test_preposition_et_negation(banc, texte, cherches, nies):
    concepts, _, obtenus = _analyse(banc.rd, texte)
    assert obtenus == nies
    assert set(cherches) <= set(concepts)
    assert not {'javascript', 'python', 'api', 'service', 'cloud'} & set(concepts)


@pytest.mark.parametrize('texte, attendu', [
    # #4 : « code » en rôle référence
    ('Semantic search over my PDFs rather than code', 'recherche_semantique'),
    ('recherche sémantique de PDF plutôt que de code', 'recherche_semantique'),
    # #7, #41 : « code » dans un autre sens (liste ou majuscule en cours de phrase)
    ('recherche sémantique dans le Code général des impôts', 'recherche_semantique'),
    ('recherche sémantique dans le Code monétaire et financier', 'recherche_semantique'),
    ('recherche sémantique dans les codes juridiques', 'recherche_semantique'),
    ('semantic search over the tax code', 'recherche_semantique'),
    ('semantic search in the French civil code', 'recherche_semantique'),
    ("recherche sémantique pour retrouver le bon code comptable d'une facture", 'recherche_semantique'),
    # #8 : quantité de code à écrire
    ('Je veux intégrer une recherche sémantique en quelques lignes de code dans mon appli', 'recherche_semantique'),
    ('add semantic search to my app with little code', 'recherche_semantique'),
    # #42 : négation sans ponctuation
    ('semantic search but not for source code', 'recherche_semantique'),
    ('recherche sémantique mais pas pour le code source', 'recherche_semantique'),
    # composition gardée
    ('une recherche sémantique dans mon code source', 'recherche_code'),
    ('recherche sémantique dans le code source de mes projets', 'recherche_code'),
    ('semantic code search for my repositories', 'recherche_code'),
])
def test_composition_code(banc, texte, attendu):
    cles = {c.cle for c in banc.rd.analyser_requete(texte).concepts}
    assert attendu in cles and not {'recherche_semantique', 'recherche_code'} - {attendu} & cles


@pytest.mark.parametrize('texte, attendu', [
    # #6 : le sujet d'un cours cité n'importe où avant « sur »
    ('une formation en ligne sur n8n', ('n8n', 'essentiel')),
    ('un cours en ligne sur React', ('react', 'essentiel')),
    ('des exercices sur React pour mes élèves', ('react', 'essentiel')),
    ('un tutoriel sur React', ('react', 'essentiel')),
    # #12 : « on » pronom seulement devant un verbe
    ('workflows running on n8n', ('n8n', 'contrainte')),
    ('workflows running on n8n to de-duplicate invoices', ('n8n', 'contrainte')),
    ('a résumé parser running on n8n', ('n8n', 'contrainte')),
    ('on cherche un outil pour n8n', ('n8n', 'essentiel')),
])
def test_classe_du_produit(banc, texte, attendu):
    concepts, _, _ = _analyse(banc.rd, texte)
    assert (attendu[0], concepts[attendu[0]][0]) == attendu

# =============================================================================
# Classement et sorties
# =============================================================================
def test_groupe_facultatif_pas_declasse(banc):
    # #13 dans le classement : « GPU et Docker facultatifs » garde la « forte »
    rd = banc.rd
    index_du_corpus(rd, [
        _fiche('ocr-facultatifs', 'synth/ocr-facultatifs', Description="OCR de documents scannés.",
               **{'Prérequis': '- GPU et Docker facultatifs'}),
        _fiche('ocr-gpu', 'synth/ocr-gpu', Description="OCR de documents scannés.",
               **{'Prérequis': '- GPU NVIDIA obligatoire, Docker facultatif'})])
    reponse = _chercher(rd, 'un OCR pour documents scannés sans GPU')
    assert [(r.cle, r.niveau, r.exclusions[0]['etat']) for r in reponse.resultats] == [
        ('synth/ocr-facultatifs', 'forte', 'non_requis'), ('synth/ocr-gpu', 'partielle', 'requis')]


def test_en_tetes_et_source_par_resultat(banc, capsys):
    # #44 : « À remplacer », « Indifférent », négations filtrées, source de chaque exclusion dans le JSON
    rd = banc.rd
    index_du_corpus(rd, [page('n8n-recettes', 'https://github.com/synth/n8n-recettes', props={
        'Description': p_texte("Collection de workflows pour n8n."), 'Catégorie': p_select('Automatisation/No-code'),
        'Brique pour': p_multi()})])
    assert banc.lancer('cherche', 'une alternative à n8n') == 0
    sortie = ' '.join(capsys.readouterr().out.split())
    assert 'À remplacer : n8n' in sortie and 'Exclus :' not in sortie
    assert banc.lancer('cherche', 'une alternative à n8n', '--format', 'markdown') == 0
    assert 'À remplacer : n8n' in capsys.readouterr().out
    assert banc.lancer('cherche', 'une alternative à n8n', '--format', 'json') == 0
    donnees = json.loads(capsys.readouterr().out)
    assert donnees['requete']['exclusions'][0]['source'] == 'reference'
    assert donnees['resultats'][0]['exclusions'][0]['source'] == 'reference'
    assert donnees['resultats'][0]['exclusions'][0]['etat'] == 'requis'
    assert banc.lancer('cherche', 'un outil de workflows avec ou sans GPU') == 0
    sortie = ' '.join(capsys.readouterr().out.split())
    assert 'Indifférent : GPU (ni exigé ni exclu)' in sortie
    assert 'Non pris en compte (négation)' not in sortie
    assert banc.lancer('cherche', 'un outil de workflows avec ou sans GPU', '--format', 'markdown') == 0
    sortie = capsys.readouterr().out
    assert 'Indifférent : GPU (ni exigé ni exclu)' in sortie and 'Non pris en compte' not in sortie
