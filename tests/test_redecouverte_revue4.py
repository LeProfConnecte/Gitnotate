"""Lot 5, quatrième revue contradictoire (docs/QUALIFICATION_LOT5.md § 6) : un cas par constat confirmé.

La quatrième revue a surtout trouvé des régressions introduites par les corrections de la troisième ; les règles ont
été resserrées (une règle étroite pour « requis » ou « non requis », tout le reste en « mention ») :
- Fiches : double négation limitée au verbe juste avant « sans » (« You can run it without a GPU » n'est plus une
  exigence), facultatif après un adverbe ou un adjectif (« Docker is completely optional ») ou après une parenthèse
  refermée (« An NVIDIA GPU (RTX 3060 or newer) is recommended »), « No NVIDIA GPU required », « Does not require a
  dedicated GPU », CPU possible resserré (« a CPU with AVX2 » n'en est pas un), « ou équivalent », Description qui
  commence par « Si », listes et offres, bénéfice d'un autre membre, « into n8n like any other template », lignes de
  commande resserrées, « optional: » suivi d'une phrase, fonction conditionnelle (« GPU acceleration requires
  CUDA »), négation d'un autre nom (« aucune clé d'API nécessaire »), exemple fourni, « (preferred) », autre marque
  non prise en charge (« AMD GPUs are not supported »), ligne de continuation d'un élément.
- Requête : mémoire et indifférence (« I can't find the n8n workflow I saved », « je ne retrouve plus le dépôt n8n »,
  « doesn't matter if it's React or Vue »), interdiction stricte (« car le cloud est interdit » ne vise pas Zapier),
  « Comme Zapier, mais open source », liaison devant un système (« without installation on Windows »), « on my
  codebase », verbe de qualité (« qui ne plante jamais sous Windows »), « I haven't used n8n ».
- Coût linéaire sur une fiche longue qui cite souvent la technologie exclue.
Hors ligne, aucune base Notion réelle.
"""
import re
import time

import pytest
from redecouverte_outils import preparer


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


_NATURES = {'gpu': 'materiel', 'docker': 'plateforme', 'kubernetes': 'plateforme', 'windows': 'plateforme',
            'n8n': 'produit', 'zapier': 'produit', 'react': 'produit'}
_FORMES = {'gpu': r'gpus?|cuda|vram|cartes? graphiques?', 'docker': 'docker', 'kubernetes': 'kubernetes',
           'windows': 'windows', 'n8n': 'n8n', 'zapier': 'zapier', 'react': 'react'}


def _sortes(rd, texte, colonne, cible, n):
    occurrences = [m.span() for m in re.finditer(r'(?i)\b(?:' + _FORMES[cible] + r')\b', texte)][:n]
    return [rd.sorte_mention(texte, a, b, colonne, _NATURES[cible]) for a, b in occurrences]


@pytest.mark.parametrize('texte, colonne, cible, attendu', [
    ('Transcription audio de réunions en local. You can run it without a GPU.', 'description', 'gpu', ['non_requis']),
    ('Can be used without a GPU.', 'description', 'gpu', ['non_requis']),
    ('You can run it without Docker, using plain Python.', 'description', 'docker', ['non_requis']),
    ('Does not require Docker and runs without a GPU.', 'description', 'gpu', ['non_requis']),
    ('Ne nécessite pas Docker et fonctionne sans GPU.', 'description', 'gpu', ['non_requis']),
    ('Runs without a GPU (no CUDA required).', 'description', 'gpu', ['non_requis', 'non_requis']),
    ('- GPU: not required (runs fine without a GPU)', 'prerequis', 'gpu', ['non_requis', 'non_requis']),
    ('- Docker: not needed (works without Docker)', 'prerequis', 'docker', ['non_requis', 'non_requis']),
    ('Ne nécessite aucune clé API et fonctionne sans GPU.', 'description', 'gpu', ['non_requis']),
    ('Can run without a GPU (CPU mode).', 'prerequis', 'gpu', ['non_requis']),
    ('Ne fonctionne pas sans GPU.', 'description', 'gpu', ['requis']),
    ("This won't work without a CUDA GPU.", 'description', 'gpu', ['requis', 'requis']),
    ('- Python 3.10+\n- Docker is completely optional', 'prerequis', 'docker', ['non_requis']),
    ('- Docker (entirely optional)', 'prerequis', 'docker', ['non_requis']),
    ('- Docker est totalement facultatif', 'prerequis', 'docker', ['non_requis']),
    ('- A Kubernetes cluster is optional', 'prerequis', 'kubernetes', ['non_requis']),
    ('- GPU NVIDIA récent recommandé', 'prerequis', 'gpu', ['non_requis']),
    ('- GPU NVIDIA dédié recommandé', 'prerequis', 'gpu', ['non_requis']),
    ('- Une carte graphique NVIDIA récente est conseillée', 'prerequis', 'gpu', ['non_requis']),
    ('- Docker (24+) optional', 'prerequis', 'docker', ['non_requis']),
    ('- An NVIDIA GPU (RTX 3060 or newer) is recommended', 'prerequis', 'gpu', ['non_requis']),
    ('- Docker installation is optional', 'prerequis', 'docker', ['non_requis']),
    ('- Requires Docker (Compose v2 recommended)', 'prerequis', 'docker', ['requis']),
    ('Transcription audio de réunions en local. No NVIDIA GPU required.', 'description', 'gpu', ['non_requis']),
    ('Does not require an NVIDIA GPU.', 'description', 'gpu', ['non_requis']),
    ('Does not require a dedicated GPU.', 'description', 'gpu', ['non_requis']),
    ('Requires an NVIDIA GPU and a CPU with AVX2.', 'description', 'gpu', ['requis']),
    ('- 16 GB RAM, CPU with AVX, NVIDIA GPU', 'prerequis', 'gpu', ['requis']),
    ('- Runs on both GPU and CPU', 'prerequis', 'gpu', ['non_requis']),
    ('- Supports CUDA, ROCm and CPU', 'prerequis', 'gpu', ['non_requis']),
    ('- Docker ou équivalent', 'prerequis', 'docker', ['mention']),
    ('- Docker or equivalent container runtime', 'prerequis', 'docker', ['mention']),
    ('If you need speed, this tool requires a GPU.', 'description', 'gpu', ['requis']),
    ('Quand le volume est élevé, Docker est requis.', 'description', 'docker', ['requis']),
    ('Collection de workflows n8n, prêts à importer.', 'description', 'n8n', ['requis']),
    ("Fournit des workflows n8n prêts à l'emploi.", 'description', 'n8n', ['requis']),
    ('Workflow templates for n8n and Make.', 'description', 'n8n', ['mention']),
    ('Workflow templates for n8n, Make and Zapier.', 'description', 'n8n', ['mention']),
    ('- NVIDIA GPU for training and inference', 'prerequis', 'gpu', ['requis']),
    ('Requires an NVIDIA GPU with CUDA acceleration.', 'description', 'gpu', ['requis', 'mention']),
    ('- Docker and an NVIDIA GPU for faster inference', 'prerequis', 'docker', ['requis']),
    ('Import the JSON into n8n like any other template.', 'installation', 'n8n', ['mention']),
    ('Build Zapier-like workflows on your own server.', 'description', 'zapier', ['non_requis']),
    ('- Python 3.11\n- helm 3+ and a running Kubernetes cluster', 'prerequis', 'kubernetes', ['requis']),
    ('- make sure Docker is installed', 'prerequis', 'docker', ['requis']),
    ('- python 3.10+ and docker', 'prerequis', 'docker', ['requis']),
    ('- docker compose v2', 'prerequis', 'docker', ['requis']),
    ('docker compose up -d', 'installation', 'docker', ['mention']),
    ('pip install zapier-alternative', 'installation', 'zapier', ['mention']),
    ('Docker is optional: you can also run it directly with Python.', 'description', 'docker', ['non_requis']),
    ('- Docker >= 20.10 (recommended: 24+)', 'prerequis', 'docker', ['requis']),
    ("Transcription audio de réunions en local, sur CPU ; l'accélération "
     'GPU nécessite CUDA.', 'description', 'gpu', ['mention', 'mention']),
    ('- GPU acceleration requires CUDA 12', 'prerequis', 'gpu', ['mention', 'mention']),
    ('- GPU support requires CUDA 11.8+', 'prerequis', 'gpu', ['mention', 'mention']),
    ('Requires CUDA 12.', 'description', 'gpu', ['requis']),
    ("Transcription audio de réunions en local sur GPU (aucune clé d'API "
     'nécessaire).', 'description', 'gpu', ['mention']),
    ('- Docker (no other dependency needed)', 'prerequis', 'docker', ['requis']),
    ('- Docker (aucune autre dépendance)', 'prerequis', 'docker', ['requis']),
    ('Requires only Docker (no Python or Node.js needed).', 'description', 'docker', ['requis']),
    ('- Docker is not a hard requirement', 'prerequis', 'docker', ['non_requis']),
    ('Extraction des données de factures PDF en Python. Un exemple de '
     'workflow n8n est fourni dans le dossier examples.', 'description', 'n8n', ['mention']),
    ('Comes with ready-to-use n8n workflows.', 'description', 'n8n', ['mention']),
    ('An n8n workflow is provided in examples/.', 'description', 'n8n', ['mention']),
    ('- Python 3.10+\n- ffmpeg\n- NVIDIA GPU (preferred)', 'prerequis', 'gpu', ['non_requis']),
    ('- Preferably an NVIDIA GPU with 8 GB VRAM', 'prerequis', 'gpu', ['non_requis', 'non_requis']),
    ('- GPU NVIDIA de préférence', 'prerequis', 'gpu', ['non_requis']),
    ('- Idéalement un GPU NVIDIA', 'prerequis', 'gpu', ['non_requis']),
    ('- NVIDIA GPU (nice to have)', 'prerequis', 'gpu', ['non_requis']),
    ('- NVIDIA GPU (suggested)', 'prerequis', 'gpu', ['non_requis']),
    ('- Python 3.10+\n- NVIDIA GPU with CUDA 12 (AMD GPUs are not supported)', 'prerequis', 'gpu', ['requis']),
    ('- NVIDIA GPU (AMD not supported)', 'prerequis', 'gpu', ['requis']),
    ('- NVIDIA GPU (Apple Silicon is not supported)', 'prerequis', 'gpu', ['requis']),
    ('- CUDA 12 (ROCm is not supported)', 'prerequis', 'gpu', ['requis']),
    ('- Python 3.10+\n- Docker\n  (optional, for the full stack)', 'prerequis', 'docker', ['non_requis']),
    ('Running without Docker Desktop is not supported.', 'description', 'docker', ['mention']),
])
def test_sorte_revue4(banc, texte, colonne, cible, attendu):
    assert _sortes(banc.rd, texte, colonne, cible, len(attendu)) == attendu


@pytest.mark.parametrize('texte, present, exclusions', [
    ("I can't find the n8n workflow I saved to sync my CRM", 'n8n', []),
    ("I can't find that React component library I starred", 'react', []),
    ("I don't remember which n8n workflow template I saved", 'n8n', []),
    ("I can't remember the name of the OCR tool", 'ocr', []),
    ("I can't recall the Claude Code plugin for code review", 'claude_code', []),
    ("I don't remember the name of the Docker image for OCR", 'ocr', []),
    ('je ne retrouve plus le dépôt n8n pour synchroniser un CRM', 'n8n', []),
    ('je ne trouve plus le projet FastAPI de génération de factures', 'fastapi', []),
    ("je ne sais plus quel outil Docker j'avais enregistré pour l'OCR", 'ocr', []),
    ("je ne retrouve pas le workflow n8n que j'avais enregistré", 'n8n', []),
    ("Je ne me souviens plus du nom de l'outil d'OCR en Python", 'ocr', []),
    ('une alternative à Zapier car le cloud est interdit chez nous', 'workflow', [('zapier', 'reference')]),
    ('un serveur OCR sous Docker car les API cloud sont interdites chez nous', 'docker', []),
    ('FastAPI middleware that returns 403 Forbidden for unauthorized requests', 'fastapi', []),
    ('React admin panel to manage banned users', 'react', []),
    ('un OCR sans Docker : les conteneurs sont interdits sur ce serveur', 'ocr', [('docker', 'exclusion')]),
    ('A tool to merge and compress PDFs without Docker, because Docker is '
     'not allowed on our laptops', 'pdf', [('docker', 'exclusion')]),
    ("Self-hosted workflow automation that doesn't rely on Docker — "
     "containers aren't allowed on that server.", 'workflow', [('docker', 'exclusion')]),
    ("un OCR avec Docker, Docker n'est pas interdit ici", 'docker', []),
    ('Comme Zapier, mais open source', 'workflow', [('zapier', 'reference')]),
    ('Comme n8n est déjà installé sur mon serveur, je cherche des modèles de workflows', 'n8n', []),
    ('without installation on Windows', 'windows', []),
    ('un outil de transcription sans installation sur Linux', 'linux', []),
    ('an OCR tool without installing anything on Windows', 'windows', []),
    ('without relying on Docker', None, [('docker', 'exclusion')]),
    ('an OCR without running on a GPU', 'ocr', [('gpu', 'exclusion')]),
    ('semantic search on my codebase', 'recherche_code', []),
    ('un éditeur Markdown qui ne plante jamais sous Windows', 'windows', []),
    ('un éditeur qui ne rame pas sous Windows', 'windows', []),
    ("a markdown editor that doesn't crash on Linux", 'linux', []),
    ("I haven't used n8n before, I need workflow templates", 'workflow', []),
    ("je n'ai pas utilisé n8n, je cherche des modèles de workflows", 'workflow', []),
    # indifférence : ni cherché ni exclu (revue 5 : chercher la technologie favorisait ses dépôts)
    ("a dashboard component library, doesn't matter if it's React or Vue", 'tableau_bord', []),
    ("I don't care whether it uses React or Vue, I need a Kanban board component", 'component', []),
    ("ça ne me dérange pas d'utiliser Docker pour l'OCR", 'ocr', []),
    ("je n'hésite pas à utiliser Docker pour l'OCR", 'ocr', []),
    ("I don't mind using Docker for OCR", 'ocr', []),
    ("an OCR that doesn't need a GPU", 'ocr', [('gpu', 'exclusion')]),
    ("I don't want n8n", None, [('n8n', 'exclusion')]),
    ('un OCR, je ne veux plus de Docker', 'ocr', [('docker', 'exclusion')]),
    ('un OCR qui ne nécessite pas de GPU', 'ocr', [('gpu', 'exclusion')]),
    ("un outil qui n'utilise pas Docker", None, [('docker', 'exclusion')]),
    ('sans utiliser n8n', None, [('n8n', 'exclusion')]),
    ("je n'utilise plus Zapier", None, [('zapier', 'exclusion')]),
    ("Je n'ai jamais utilisé n8n", None, []),
    ('sans GPU sous Windows', 'windows', [('gpu', 'exclusion')]),
])
def test_requete_revue4(banc, texte, present, exclusions):
    requete = banc.rd.analyser_requete(texte)
    assert [(e['cible'], e['source']) for e in requete.exclusions] == exclusions
    if present:
        assert present in {c.cle for c in requete.concepts}


def test_memoire_cherche_encore_l_objet(banc):
    # « I can't find… » ne nie rien : la recherche garde ses notions (elle échouait avec le code 1)
    requete = banc.rd.analyser_requete("I can't find the n8n workflow I saved to sync my CRM")
    concepts = {c.cle for c in requete.concepts}
    assert {'n8n', 'workflow', 'crm'} <= concepts


def test_cout_lineaire_sur_une_fiche_longue(banc):
    rd = banc.rd
    duree = {}
    for n in (300, 1200):
        texte = ' '.join(f"Étape {i} : lancer Docker pour le service {i}, puis vérifier les journaux."
                         for i in range(n))
        debut = time.perf_counter()
        for m in re.finditer('Docker', texte):
            rd.sorte_mention(texte, m.start(), m.end(), 'notes', 'plateforme')
        duree[n] = time.perf_counter() - debut
    assert duree[1200] < 3.0 and duree[1200] < 12 * max(duree[300], 0.01)
