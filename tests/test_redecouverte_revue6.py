"""Lot 5, sixième revue contradictoire (docs/QUALIFICATION_LOT5.md § 6) : un cas par constat confirmé.

La sixième revue a trouvé surtout des régressions des corrections de la cinquième ; chaque cas est vérifié sur l'état
du texte entier (comme etat_exclusion : requis et non requis ensemble donnent « contradictoire ») :
- Fiches : verbes d'exigence et adverbes de nouveau neutres entre la négation et la technologie, mais « : », tiret
  long et relatif bornent la négation (« Does not require any GPU », « no cloud: requires an NVIDIA GPU ») ; double
  négation sans négation de nom ni « not only » (« Pas de cloud : fonctionne sans GPU », « hors ligne sans GPU ») et
  suite niée avec adverbe (« is no longer supported ») ; « (used if available) » ; CPU possible seulement après « on
  / supports / compatible » ou en élément seul ; « Docker is required but Docker Desktop is not needed » ; version
  niée seulement avec une autre mention du même mot ; autre marque juste avant (« AMD GPUs are not yet
  supported ») ; « Provides an n8n node… » en tête de champ ; « No official Docker image yet » ; recommandation d'un
  modèle (« (preferably an RTX 3090 or better) »).
- Requête : l'indifférence ne vise que les technologies (le besoin qui suit reste cherché), sujet compris (« Docker
  doesn't matter ») ; adverbes avant le verbe de mémoire (« I can no longer find ») ; capacité sans mémoire : la
  tâche reste cherchée ; un produit à remplacer renommé reste à remplacer ; exception « système » sauf après un mot
  de dépendance ; « Comme <produit> » causal seulement en tête d'une requête sans remplacement ; « Docker n'est pas
  installé » exclut Docker.
Hors ligne, aucune base Notion réelle.
"""
import re

import pytest
from redecouverte_outils import index_du_corpus, p_multi, p_select, p_texte, page, preparer


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


_NATURES = {'gpu': 'materiel', 'docker': 'plateforme', 'kubernetes': 'plateforme', 'windows': 'plateforme',
            'n8n': 'produit', 'zapier': 'produit', 'react': 'produit', 'claude_code': 'produit'}
_FORMES = {'gpu': r'gpus?|cuda|vram|cartes? graphiques?', 'docker': r'docker(?: compose)?', 'kubernetes': 'kubernetes',
           'windows': 'windows', 'n8n': 'n8n', 'zapier': 'zapier', 'react': 'react', 'claude_code': 'claude code'}


def _etat(rd, texte, colonne, cible):
    sortes = {rd.sorte_mention(texte, m.start(), m.end(), colonne, _NATURES[cible])
              for m in re.finditer(r'(?i)\b(?:' + _FORMES[cible] + r')\b', texte)}
    if {'requis', 'non_requis'} <= sortes:
        return 'contradictoire'
    return next((x for x in ('requis', 'non_requis', 'mention') if x in sortes), 'inconnu')


@pytest.mark.parametrize('texte, colonne, cible, attendu', [
    ('Does not require any GPU.', 'description', 'gpu', 'non_requis'),
    ('No longer requires Docker.', 'description', 'docker', 'non_requis'),
    ("Doesn't actually need Docker.", 'description', 'docker', 'non_requis'),
    ("Doesn't necessarily need a GPU.", 'description', 'gpu', 'non_requis'),
    ("Doesn't even need Docker.", 'description', 'docker', 'non_requis'),
    ("You don't really need a GPU.", 'description', 'gpu', 'non_requis'),
    ('Does not require an expensive GPU.', 'description', 'gpu', 'non_requis'),
    ('None of the models require a GPU.', 'description', 'gpu', 'non_requis'),
    ('Aucune étape ne nécessite de GPU.', 'description', 'gpu', 'non_requis'),
    ('Aucun composant ne nécessite Docker.', 'description', 'docker', 'non_requis'),
    ('No deployment requires Kubernetes.', 'description', 'kubernetes', 'non_requis'),
    ('Fully offline, no cloud: requires an NVIDIA GPU.', 'description', 'gpu', 'requis'),
    ('Pas de cloud : nécessite Docker.', 'description', 'docker', 'requis'),
    ('Outil de transcription audio de réunions sans API externe qui nécessite un GPU.', 'description', 'gpu', 'requis'),
    ("Doesn't require or need a GPU.", 'description', 'gpu', 'non_requis'),
    ('OCR de documents scannés. 100 % local, pas de cloud : fonctionne sans GPU.', 'description', 'gpu', 'non_requis'),
    ('No cloud: runs without a GPU.', 'description', 'gpu', 'non_requis'),
    ('No API key: runs without a GPU.', 'description', 'gpu', 'non_requis'),
    ('Sans cloud : fonctionne sans GPU.', 'description', 'gpu', 'non_requis'),
    ('Aucune installation : fonctionne sans Docker.', 'description', 'docker', 'non_requis'),
    ("N'utilise pas d'API externe : tourne sans GPU.", 'description', 'gpu', 'non_requis'),
    ('Ne nécessite aucune inscription : fonctionne sans GPU.', 'description', 'gpu', 'non_requis'),
    ('Not a SaaS — runs locally without a GPU.', 'description', 'gpu', 'non_requis'),
    ("Doesn't need internet: runs without a GPU.", 'description', 'gpu', 'non_requis'),
    ('Not only does it run without Docker, it also runs on a Raspberry Pi.', 'description', 'docker', 'non_requis'),
    ("You can't run the app without Docker.", 'description', 'docker', 'requis'),
    ('Ne fonctionne pas sans GPU.', 'description', 'gpu', 'requis'),
    ('OCR de documents scannés. Fonctionne hors ligne sans GPU.', 'description', 'gpu', 'non_requis'),
    ('Transcription 100 % hors ligne sans GPU.', 'description', 'gpu', 'non_requis'),
    ('Fonctionne hors ligne sans Docker.', 'description', 'docker', 'non_requis'),
    ('- Python 3.10+\n- NVIDIA GPU (used if available)', 'prerequis', 'gpu', 'non_requis'),
    ('- NVIDIA GPU (only if you have one)', 'prerequis', 'gpu', 'non_requis'),
    ('- GPU NVIDIA (utilisé si disponible)', 'prerequis', 'gpu', 'non_requis'),
    ('- GPU NVIDIA (uniquement si disponible)', 'prerequis', 'gpu', 'non_requis'),
    ('- GPU NVIDIA (détecté automatiquement si disponible)', 'prerequis', 'gpu', 'non_requis'),
    ('- CUDA GPU (automatically used if available)', 'prerequis', 'gpu', 'non_requis'),
    ('- Docker (only if you want to run it in a container)', 'prerequis', 'docker', 'non_requis'),
    ('- NVIDIA GPU (even better if available)', 'prerequis', 'gpu', 'non_requis'),
    ('- NVIDIA GPU (RTX series recommended)', 'prerequis', 'gpu', 'requis'),
    ('- Requires Docker (Compose plugin recommended)', 'prerequis', 'docker', 'requis'),
    ('OCR for scanned documents. Requires a powerful GPU and CPU.', 'description', 'gpu', 'requis'),
    ('- Hardware: NVIDIA GPU, CPU, 16 GB RAM', 'prerequis', 'gpu', 'requis'),
    ('Requires an NVIDIA GPU with 8 GB VRAM. Shows GPU and CPU usage in the web UI.', 'description', 'gpu', 'requis'),
    ('Training requires a decent GPU and CPU.', 'description', 'gpu', 'mention'),      # entraînement seul
    ('Nécessite un GPU et CPU puissants.', 'description', 'gpu', 'requis'),
    ('High-end GPU and CPU required.', 'description', 'gpu', 'requis'),
    ('- Minimum: NVIDIA GPU, CPU 4 cores, 16 GB RAM', 'prerequis', 'gpu', 'requis'),
    ('- Runs on GPU and CPU', 'prerequis', 'gpu', 'non_requis'),
    ('- Supports GPU and CPU', 'prerequis', 'gpu', 'non_requis'),
    ('- GPU, CPU', 'prerequis', 'gpu', 'non_requis'),
    ('Inference works on GPU and CPU.', 'description', 'gpu', 'non_requis'),
    ('OCR for scanned documents. Docker is required but Docker Desktop is not needed.',
     'description', 'docker', 'requis'),
    ('Docker est requis mais Docker Desktop est facultatif.', 'description', 'docker', 'requis'),
    ('Docker Engine is required and Docker Desktop is optional.', 'description', 'docker', 'requis'),
    ('Docker is mandatory but Docker Desktop is optional.', 'description', 'docker', 'requis'),
    ('- Docker and Docker Compose (optional, for local PostgreSQL)', 'prerequis', 'docker', 'non_requis'),
    ('- Docker 20.10+ (not a hard requirement)', 'prerequis', 'docker', 'non_requis'),
    ("- Docker 24+ (n'est pas un prérequis)", 'prerequis', 'docker', 'non_requis'),
    ('- Kubernetes 1.27+ (not a hard requirement)', 'prerequis', 'kubernetes', 'non_requis'),
    ('- Python 3.10+\n- Windows 10/11: not supported', 'prerequis', 'windows', 'non_requis'),
    ('- Docker 20.10+ (older versions are not supported)', 'prerequis', 'docker', 'requis'),
    ('- CUDA 12+ (CUDA 11 is not supported)', 'prerequis', 'gpu', 'requis'),
    ('- React 18+ (not compatible with React 17)', 'prerequis', 'react', 'requis'),
    ('OCR for scanned documents. Requires an NVIDIA GPU; AMD GPUs are not yet supported.',
     'description', 'gpu', 'requis'),
    ('Requires an NVIDIA GPU. Multi-GPU is not currently supported.', 'description', 'gpu', 'requis'),
    ('Requires an NVIDIA GPU (AMD GPUs are not currently supported).', 'description', 'gpu', 'requis'),
    ('- NVIDIA GPU (AMD GPUs not yet supported)', 'prerequis', 'gpu', 'requis'),
    ("Fournit un nœud n8n pour l'API Pennylane : synchronise factures et écritures comptables.",
     'description', 'n8n', 'requis'),
    ('Provides an n8n node to generate PDF invoices.', 'description', 'n8n', 'requis'),
    ('This package provides an n8n community node for the Notion API.', 'description', 'n8n', 'requis'),
    ('Provides a plugin for Claude Code that adds slash commands.', 'description', 'claude_code', 'requis'),
    ('PDF extraction API in Python. Ships with an n8n community node.', 'description', 'n8n', 'mention'),
    ('- Python 3.10+\n- Tesseract 5\n- No official Docker image yet (run from source)',
     'prerequis', 'docker', 'non_requis'),
    ('- No official n8n node yet', 'prerequis', 'n8n', 'non_requis'),
    ('This project is not affiliated with n8n GmbH.', 'description', 'n8n', 'mention'),
    ('This is not an official Docker image.', 'description', 'docker', 'mention'),
    ('OCR server for scanned documents. Running without a GPU is no longer supported.', 'description', 'gpu', 'requis'),
    ("Depuis la v2, l'exécution sans GPU n'est plus prise en charge.", 'description', 'gpu', 'requis'),
    ('Running without a GPU is not supported.', 'description', 'gpu', 'requis'),
    ('- NVIDIA GPU (recommended: RTX 3060 or better)', 'prerequis', 'gpu', 'requis'),
    ('- NVIDIA GPU (preferably an RTX 3090 or better)', 'prerequis', 'gpu', 'requis'),
    ('- NVIDIA GPU (de préférence RTX 3060)', 'prerequis', 'gpu', 'requis'),
    ('- Docker (preferably the latest version)', 'prerequis', 'docker', 'requis'),
    ('- NVIDIA GPU (optional: speeds up training)', 'prerequis', 'gpu', 'non_requis'),
    ('- NVIDIA GPU (optional 8 GB+)', 'prerequis', 'gpu', 'non_requis'),
    ('Requirements: none except Docker.', 'description', 'docker', 'mention'),
    ('- None except Docker', 'prerequis', 'docker', 'mention'),
    ('- A GPU is not explicitly required', 'prerequis', 'gpu', 'non_requis'),
    ('- Docker is not particularly needed', 'prerequis', 'docker', 'non_requis'),
    ('Non requis : Docker', 'description', 'docker', 'non_requis'),
    ('- Non requis : Docker', 'prerequis', 'docker', 'non_requis'),
])
def test_etat_revue6(banc, texte, colonne, cible, attendu):
    assert _etat(banc.rd, texte, colonne, cible) == attendu


@pytest.mark.parametrize('texte, presents, absents, exclusions, indifferents', [
    ("ça ne me dérange pas d'utiliser Docker et je cherche un OCR pour des factures",
     ['ocr', 'factures'], ['docker'], [], ['Docker']),
    ("I don't mind Docker and I want a self-hosted OCR", ['ocr', 'auto_heberge'], ['docker'], [], ['Docker']),
    ("I don't care about GPU acceleration and I need a lightweight OCR", ['ocr'], ['gpu', 'acceleration'], [], ['GPU']),
    ("I don't mind Docker if it's a good OCR for receipts", ['ocr'], ['docker', 'if'], [], ['Docker']),
    ("Docker doesn't matter as long as it's a self-hosted OCR",
     ['ocr', 'auto_heberge'], ['docker', 'long'], [], ['Docker']),
    ("a dashboard component library, doesn't matter if it's React or Vue",
     ['tableau_bord'], ['react', 'vue'], [], ['React']),
    ("I don't mind using Docker for OCR", ['ocr'], ['docker'], [], ['Docker']),
    ("It doesn't matter if it runs in Docker, I need an OCR tool", ['ocr'], ['docker'], [], ['Docker']),
    ('I can no longer find the n8n workflow I saved for my CRM', ['n8n', 'workflow', 'crm'], [], [], None),
    ('I can no longer find the Docker compose file for my OCR stack', ['ocr'], [], [], None),
    ("I can't even remember the name of the n8n repo", ['n8n'], [], [], None),
    ("I can't actually find the n8n workflow I starred", ['n8n'], [], [], None),
    ("I don't really remember the name of the n8n workflow I saved", ['n8n'], [], [], None),
    ("I can't quite remember which React library I bookmarked", ['react'], [], [], None),
    ("I really don't want Docker", [], ['docker'], [('docker', 'exclusion')], None),
    ('I no longer use Zapier', [], ['zapier'], [('zapier', 'exclusion')], None),
    ('I can no longer use Docker at work', [], ['docker'], [('docker', 'exclusion')], None),
    ("je n'arrive pas à transcrire mes réunions audio en texte", ['stt', 'reunions'], [], [], None),
    ("je n'arrive pas à convertir mes PDF scannés en Markdown", ['pdf', 'markdown'], [], [], None),
    ('je ne sais pas extraire les tableaux de mes PDF', ['tableau', 'pdf'], [], [], None),
    ("je n'arrive pas à installer Docker, je cherche un OCR", ['ocr'], ['docker'], [('docker', 'exclusion')], None),
    ("je n'arrive pas à faire tourner Stable Diffusion sans GPU", ['image_gen'], ['gpu'], [('gpu', 'exclusion')], None),
    ('une alternative à Zapier, Zapier est trop cher pour nous',
     ['workflow'], ['zapier'], [('zapier', 'reference')], None),
    ('a self-hosted n8n alternative because n8n is too heavy', ['workflow'], ['n8n'], [('n8n', 'reference')], None),
    ('I currently use Zapier but want a self-hosted Zapier alternative',
     ['workflow'], ['zapier'], [('zapier', 'reference')], None),
    ('a password manager without a subscription on macOS', ['macos'], [], [], None),
    ('une app de notes qui marche sans compte sur Linux', ['linux'], [], [], None),
    ('a Markdown note-taking app without relying on Windows', [], ['windows'], [('windows', 'exclusion')], None),
    ("un outil d'automatisation open source, comme Zapier par exemple",
     ['workflow'], ['zapier'], [('zapier', 'reference')], None),
    ('Comme Zapier sous Windows', [], ['zapier'], [('zapier', 'reference')], None),
    ("Comme Zapier sauf que c'est open source", [], ['zapier'], [('zapier', 'reference')], None),
    ('Comme n8n devient trop cher, je cherche une alternative open source pour automatiser mes workflows',
     ['workflow'], ['n8n'], [('n8n', 'reference')], None),
    ("Comme Zapier coûte trop cher, je cherche un outil d'automatisation de workflows open source",
     ['workflow'], ['zapier'], [('zapier', 'reference')], None),
    ('Comme n8n a déjà un nœud HTTP, je cherche des workflows n8n pour Slack', ['n8n', 'workflow'], [], [], None),
    ('Comme React me plaît, je cherche une bibliothèque de composants React pour tableaux de bord',
     ['react'], [], [], None),
    ('je cherche un outil comme Zapier compatible avec mon CRM',
     ['workflow'], ['zapier'], [('zapier', 'reference')], None),
    ("an open source mind map app, I don't mind if it needs Docker", ['mind'], ['docker'], [], ['Docker']),
    ("a health care dashboard, I don't care if it's React or Vue", ['care'], ['react'], [], ['React']),
    ('Docker is not installed on my laptop, I need an OCR tool', ['ocr'], ['docker'], [('docker', 'exclusion')], None),
    ("Docker n'est pas installé sur mon PC, je cherche un OCR", ['ocr'], ['docker'], [('docker', 'exclusion')], None),
    ('un OCR avec Docker, Docker est installé sur le serveur', ['ocr', 'docker'], [], [], None),
    ('je trouve pas le dépôt n8n pour synchroniser un CRM', ['n8n'], [], [], None),
    ("ça me dérange pas d'utiliser Docker pour l'OCR", ['ocr'], ['docker'], [], ['Docker']),
    ("I can't remember the name of the n8n tool I saved", ['n8n'], ['remember'], [], None),
])
def test_requete_revue6(banc, texte, presents, absents, exclusions, indifferents):
    requete = banc.rd.analyser_requete(texte)
    cles = {c.cle for c in requete.concepts}
    assert [(e['cible'], e['source']) for e in requete.exclusions] == exclusions
    assert set(presents) <= cles and not set(absents) & cles
    if indifferents is not None:
        assert {x.lower() for x in indifferents} <= {x.lower() for x in requete.indifferents}


def _fiche(nom, **champs):
    props = {'Catégorie': p_select('OCR/Documents'), 'Brique pour': p_multi()}
    props.update({colonne: p_texte(texte) for colonne, texte in champs.items()})
    return page(nom, f'https://github.com/synth/{nom}', props=props)


def _chercher(rd, texte):
    con, meta = rd.ouvrir_index_valide()
    try:
        reponse = rd.rechercher(con, rd.analyser_requete(texte), {}, 50, False, meta)
        rd.expliquer(con, reponse)
    finally:
        con.close()
    return reponse


def test_does_not_require_any_gpu_garde_la_forte(banc):
    # fiches 0 : « Does not require any GPU » n'est plus lu « requis » (le dépôt perdait « forte »)
    rd = banc.rd
    index_du_corpus(rd, [_fiche('ocr-any', Description='OCR for scanned documents. Does not require any GPU.'),
                         _fiche('ocr-plain', Description='OCR for scanned documents.')])
    resultats = {r.cle: r for r in _chercher(rd, 'an OCR for scanned documents without a GPU').resultats}
    assert resultats['synth/ocr-any'].niveau == 'forte'
    assert resultats['synth/ocr-any'].exclusions[0]['etat'] == 'non_requis'


def test_no_official_ne_supprime_pas_la_negation(banc):
    # classement 3 : « no official n8n integration yet » nie toujours n8n dans le score ; « non officiel » ne nie rien
    rd = banc.rd
    texte = 'Workflow automation platform for CRM sync; no official n8n integration yet.'
    a = texte.index('n8n')
    assert rd.occurrence_niee(texte, a, a + 3)
    texte = 'Nœud communautaire non officiel pour n8n qui génère des PDF.'
    a = texte.index('génère')
    assert not rd.occurrence_niee(texte, a, a + len('génère'))


def test_negation_citee_une_fois_dans_a_verifier(banc):
    # docs 7 : deux notions niées par la même phrase : une seule ligne « La fiche précise »
    rd = banc.rd
    index_du_corpus(rd, [_fiche('pdf-sorter', Description="Classe des factures PDF scannées par fournisseur. Ne fait "
                                                          "pas d'OCR ni d'extraction de tableaux de factures.")])
    r = _chercher(rd, 'extraction de tableaux de factures PDF').resultats[0]
    assert [a['code'] for a in r.a_verifier].count('negation') == 1


def test_citation_markdown_sur_une_ligne(banc):
    # classement 5 : une citation à cheval sur deux éléments de liste ne crée pas de puce en Markdown
    rd = banc.rd
    long = ('- Docker 24+ is required to run the full stack, including the PostgreSQL database, the Redis queue, the '
            'background workers, the web dashboard and the reverse proxy that serves the API on Linux')
    index_du_corpus(rd, [_fiche('ocr-stack', Description='OCR de documents scannés.',
                                **{'Prérequis': '- Python 3.10+\n' + long + '\n- 8 GB of RAM'})])
    sortie = rd.en_markdown(_chercher(rd, 'un OCR de documents scannés sans Docker'))
    ligne = next(x for x in sortie.splitlines() if x.startswith('- **Exclusion**'))
    assert 'Docker 24+' in ligne and '- Docker 24+ is required' not in sortie.replace(ligne, '')
