"""Lot 5, cinquième revue contradictoire (docs/QUALIFICATION_LOT5.md § 6) : un cas par constat confirmé.

La cinquième revue a surtout trouvé des régressions des règles ajoutées à la quatrième, côté requête surtout :
- Requête : la mémoire, l'indifférence et la qualité ne se lisent plus que sur le verbe que la négation régit (entre
  « ne » et « pas », ou juste après « can't ») et jamais sur « sans » / « without » (« Find a web scraper without
  Docker » exclut Docker) ; « je n'arrive pas à installer Docker » exclut Docker ; l'indifférence (« I don't care
  about GPU acceleration ») rend la technologie indifférente au lieu de la chercher ; « Comme n8n a déjà… » en tête
  est causal ; adverbes avant « interdit » ; exception « système » réservée à l'installation ; « no GPU installed »
  exclut le GPU.
- Fiches : adverbes après la négation (« no longer required »), double négation jusqu'à trois mots (« You can't run
  the app without Docker »), facultatif d'un autre nom dans une parenthèse ouverte (« (Compose plugin
  recommended) »), « RTX 3060 or equivalent », « A GPU is required: without a GPU, … », négation d'un autre nom
  à travers un verbe d'exigence (« no cloud: requires an NVIDIA GPU »), « Runs on GPU and CPU », usages annexes
  coordonnés, intégrations offertes (« Ships with an n8n node »), fonction de l'identifiant (« The backend requires
  Docker »), collections d'exemples, version niée (« older versions are not supported »), affiliation (« not
  affiliated with n8n GmbH »), « pour n8n, prêts à importer », coordination de la même technologie (« Docker and
  Docker Compose (optional) »).
- Classement et sorties : énumération longue en temps linéaire, « No coding required », fiche principale citée,
  une même phrase citée une fois.
Hors ligne, aucune base Notion réelle.
"""
import re
import time

import pytest
from redecouverte_outils import index_du_corpus, p_date, p_multi, p_select, p_texte, page, preparer


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


_NATURES = {'gpu': 'materiel', 'docker': 'plateforme', 'kubernetes': 'plateforme', 'windows': 'plateforme',
            'n8n': 'produit', 'zapier': 'produit', 'react': 'produit'}
_FORMES = {'gpu': r'gpus?|cuda|vram|cartes? graphiques?', 'docker': 'docker', 'kubernetes': 'kubernetes',
           'windows': 'windows', 'n8n': 'n8n', 'zapier': 'zapier', 'react': 'react'}


def _sortes(rd, texte, colonne, cible, n):
    occurrences = [m.span() for m in re.finditer(r'(?i)\b(?:' + _FORMES[cible] + r')\b', texte)][:n]
    return [rd.sorte_mention(texte, a, b, colonne, _NATURES[cible]) for a, b in occurrences]


# =============================================================================
# Fiches
# =============================================================================
@pytest.mark.parametrize('texte, colonne, cible, attendu', [
    ('- Docker is no longer required', 'prerequis', 'docker', ['non_requis']),
    ("- Docker n'est pas vraiment nécessaire", 'prerequis', 'docker', ['non_requis']),
    ('- GPU is not always required', 'prerequis', 'gpu', ['non_requis']),
    ("- Un GPU n'est pas nécessairement requis", 'prerequis', 'gpu', ['non_requis']),
    ('- Docker is not technically required', 'prerequis', 'docker', ['non_requis']),
    ('- Docker is not even required', 'prerequis', 'docker', ['non_requis']),
    ('- Docker is not entirely necessary', 'prerequis', 'docker', ['non_requis']),
    ('- GPU NVIDIA (pas nécessairement requis)', 'prerequis', 'gpu', ['non_requis']),
    ('- GPU NVIDIA (pas toujours nécessaire)', 'prerequis', 'gpu', ['non_requis']),
    ('Docker is no longer required since v2.', 'description', 'docker', ['non_requis']),
    ('- Aucune autre dépendance que Docker', 'prerequis', 'docker', ['mention']),
    ('- Docker (no other dependency needed)', 'prerequis', 'docker', ['requis']),
    ("- Docker (aucune clé d'API nécessaire)", 'prerequis', 'docker', ['requis']),
    ("You can't run the app without Docker.", 'description', 'docker', ['requis']),
    ('You cannot use this tool without Docker installed.', 'description', 'docker', ['requis']),
    ("On ne peut pas lancer l'application sans Docker.", 'description', 'docker', ['requis']),
    ('Il est impossible de lancer le projet sans Docker.', 'description', 'docker', ['requis']),
    ("It won't work properly without a GPU.", 'description', 'gpu', ['requis']),
    ('This will not work on machines without an NVIDIA GPU.', 'description', 'gpu', ['requis']),
    ("You can't use this project without Kubernetes.", 'description', 'kubernetes', ['requis']),
    ("Doesn't work properly without a GPU.", 'description', 'gpu', ['requis']),
    ('It cannot really run without a GPU.', 'description', 'gpu', ['requis']),
    ('does not perform well without a GPU', 'description', 'gpu', ['requis']),
    ('Not really usable without a GPU.', 'description', 'gpu', ['requis']),
    ('It is not possible to run this model without a GPU.', 'description', 'gpu', ['requis']),
    ("Il n'est pas possible d'utiliser ce modèle sans GPU.", 'description', 'gpu', ['requis']),
    ('You can run it without a GPU.', 'description', 'gpu', ['non_requis']),
    ('Does not require Python and runs without Docker.', 'description', 'docker', ['non_requis']),
    ('- Docker: not needed (works without Docker)', 'prerequis', 'docker', ['non_requis', 'non_requis']),
    ('Runs without a GPU (no CUDA required).', 'description', 'gpu', ['non_requis']),
    ('- Requires Docker (Compose plugin recommended)', 'prerequis', 'docker', ['requis']),
    ('- CUDA-capable GPU (Ampere or later recommended)', 'prerequis', 'gpu', ['requis']),
    ('- NVIDIA GPU (RTX series recommended)', 'prerequis', 'gpu', ['requis']),
    ('- GPU NVIDIA (pilotes récents recommandés)', 'prerequis', 'gpu', ['requis']),
    ('- Carte graphique NVIDIA (architecture Ampere conseillée)', 'prerequis', 'gpu', ['requis']),
    ('- Docker (rootless mode recommended)', 'prerequis', 'docker', ['requis']),
    ('- Windows (PowerShell recommended)', 'prerequis', 'windows', ['requis']),
    ('- Kubernetes cluster (managed service recommended)', 'prerequis', 'kubernetes', ['requis']),
    ('- Docker (entirely optional)', 'prerequis', 'docker', ['non_requis']),
    ('- GPU NVIDIA (fortement recommandé)', 'prerequis', 'gpu', ['non_requis']),
    ('- NVIDIA GPU (optional but recommended)', 'prerequis', 'gpu', ['non_requis']),
    ('- Docker (strongly recommended)', 'prerequis', 'docker', ['non_requis']),
    ('Docker is completely optional.', 'description', 'docker', ['non_requis']),
    ('A Kubernetes cluster is optional.', 'description', 'kubernetes', ['non_requis']),
    ('- Docker (latest version recommended)', 'prerequis', 'docker', ['requis']),
    ('Requires Docker (latest version recommended).', 'description', 'docker', ['requis']),
    ('Requires an NVIDIA GPU (RTX 3060 or equivalent).', 'description', 'gpu', ['requis']),
    ('Requires an RTX 3060 or equivalent GPU.', 'description', 'gpu', ['requis']),
    ('- NVIDIA GPU (RTX 3060 or equivalent)', 'prerequis', 'gpu', ['requis']),
    ('- 8 GB VRAM (RTX 3070 or equivalent)', 'prerequis', 'gpu', ['requis']),
    ('- GPU: RTX 3060 or equivalent', 'prerequis', 'gpu', ['requis']),
    ('- Docker ou équivalent', 'prerequis', 'docker', ['mention']),
    ('- Docker or equivalent container runtime', 'prerequis', 'docker', ['mention']),
    ('A GPU is required: without a GPU, inference takes hours.', 'description', 'gpu', ['requis', 'mention']),
    ('Un GPU est indispensable : sans GPU, le traitement prend des heures.',
     'description', 'gpu', ['requis', 'mention']),
    ('Docker est obligatoire : sans Docker, rien ne démarre.', 'description', 'docker', ['requis', 'mention']),
    ('- NVIDIA GPU required (without a GPU, inference is very slow)', 'prerequis', 'gpu', ['requis', 'mention']),
    ('- GPU: not required (runs fine without a GPU)', 'prerequis', 'gpu', ['non_requis', 'non_requis']),
    ('Fully offline, no cloud: requires an NVIDIA GPU.', 'description', 'gpu', ['requis']),
    ('100 % local, sans cloud : nécessite un GPU NVIDIA avec 8 Go de VRAM.',
     'description', 'gpu', ['requis', 'mention']),
    ('Pas de cloud : nécessite Docker.', 'description', 'docker', ['requis']),
    ('No external services: requires Docker.', 'description', 'docker', ['requis']),
    ('Outil de transcription audio de réunions sans API externe qui nécessite un GPU.',
     'description', 'gpu', ['requis']),
    ('Aucune dépendance sauf Docker.', 'description', 'docker', ['mention']),
    ('Aucun prérequis à part Docker.', 'description', 'docker', ['mention']),
    ('No requirements beyond Docker.', 'description', 'docker', ['mention']),
    ('Does not require a dedicated NVIDIA GPU.', 'description', 'gpu', ['non_requis']),
    ('No dependency on Docker.', 'description', 'docker', ['non_requis']),
    ('Ne nécessite pas de carte graphique dédiée.', 'description', 'gpu', ['non_requis']),
    ('Not compatible with Docker.', 'description', 'docker', ['non_requis']),
    ("Doesn't require or need a GPU.", 'description', 'gpu', ['non_requis']),
    ('Does not require a powerful dedicated GPU.', 'description', 'gpu', ['non_requis']),
    ('- Runs on GPU and CPU', 'prerequis', 'gpu', ['non_requis']),
    ('- Fonctionne sur GPU et CPU', 'prerequis', 'gpu', ['non_requis']),
    ('- GPU, CPU', 'prerequis', 'gpu', ['non_requis']),
    ('- Supports GPU and CPU', 'prerequis', 'gpu', ['non_requis']),
    ('- Compatible GPU et CPU', 'prerequis', 'gpu', ['non_requis']),
    ('Inference works on GPU and CPU.', 'description', 'gpu', ['non_requis']),
    ('Requires an NVIDIA GPU and a CPU with AVX2.', 'description', 'gpu', ['requis']),
    ('- 16 GB RAM, CPU with AVX, NVIDIA GPU', 'prerequis', 'gpu', ['requis']),
    ('- NVIDIA GPU and CPU with AVX2', 'prerequis', 'gpu', ['requis']),
    ('- Runs on both GPU and CPU', 'prerequis', 'gpu', ['non_requis']),
    ('- Works on CPU and GPU', 'prerequis', 'gpu', ['non_requis']),
    ('- Docker (for local development and testing)', 'prerequis', 'docker', ['mention']),
    ('- Docker (pour le développement et les tests)', 'prerequis', 'docker', ['mention']),
    ('- Docker (for tests and CI)', 'prerequis', 'docker', ['mention']),
    ('- Docker (for development or testing)', 'prerequis', 'docker', ['mention']),
    ('- NVIDIA GPU for training and inference', 'prerequis', 'gpu', ['requis']),
    ('PDF extraction API in Python. Ships with an n8n community node.', 'description', 'n8n', ['mention']),
    ('Provides an n8n node for no-code users.', 'description', 'n8n', ['requis']),
    ('Includes an n8n node and a Zapier integration.', 'description', 'n8n', ['mention']),
    ('API PDF en Python ; inclut un nœud n8n.', 'description', 'n8n', ['mention']),
    ("Fournit des workflows n8n prêts à l'emploi.", 'description', 'n8n', ['requis']),
    ('Provides 50 n8n workflows.', 'description', 'n8n', ['requis']),
    ('n8n community node to generate PDF invoices.', 'description', 'n8n', ['requis']),
    ('The backend requires Docker and PostgreSQL.', 'description', 'docker', ['requis']),
    ('Le backend nécessite Docker.', 'description', 'docker', ['requis']),
    ('Backend: requires Docker.', 'description', 'docker', ['requis']),
    ('The API backend requires a GPU.', 'description', 'gpu', ['requis']),
    ('- NVIDIA GPU support', 'prerequis', 'gpu', ['requis']),
    ('- Docker support', 'prerequis', 'docker', ['requis']),
    ('- GPU acceleration requires CUDA 12', 'prerequis', 'gpu', ['mention', 'mention']),
    ('- CUDA 11.8+ (for GPU acceleration)', 'prerequis', 'gpu', ['mention', 'mention']),
    ('Offline mode requires a GPU.', 'description', 'gpu', ['mention']),
    ('Collection of example n8n workflows.', 'description', 'n8n', ['requis']),
    ('Exemples de workflows n8n pour synchroniser un CRM.', 'description', 'n8n', ['requis']),
    ('A set of sample workflows for n8n.', 'description', 'n8n', ['requis']),
    ('Un exemple de workflow n8n est fourni.', 'description', 'n8n', ['mention']),
    ('An n8n workflow is provided in examples/.', 'description', 'n8n', ['mention']),
    ('- Docker 20.10+ (older versions are not supported)', 'prerequis', 'docker', ['requis']),
    ('- Docker 20.10+ (older versions not supported)', 'prerequis', 'docker', ['requis']),
    ('- React 18+ (not compatible with React 17)', 'prerequis', 'react', ['requis', 'mention']),
    ('- n8n 1.x (not compatible with n8n 0.x)', 'prerequis', 'n8n', ['requis', 'mention']),
    ('- Docker 20.10 ou plus récent (les versions antérieures ne sont pas prises en charge)',
     'prerequis', 'docker', ['requis']),
    ('- CUDA 12+ (CUDA 11 is not supported)', 'prerequis', 'gpu', ['requis', 'requis']),
    ('- Docker 24+ is not required', 'prerequis', 'docker', ['non_requis']),
    ('Nœud communautaire non officiel pour n8n qui génère des PDF.', 'description', 'n8n', ['requis']),
    ('This project is not affiliated with n8n GmbH.', 'description', 'n8n', ['mention']),
    ('Not an official n8n product.', 'description', 'n8n', ['mention']),
    ('This is not an official Docker image.', 'description', 'docker', ['mention']),
    ('Intégration non officielle avec Zapier.', 'description', 'zapier', ['mention']),
    ('Non affilié à n8n GmbH.', 'description', 'n8n', ['mention']),
    ('Unofficial n8n community node, not affiliated with n8n GmbH.', 'description', 'n8n', ['requis', 'mention']),
    ('Modèles de workflows pour n8n, prêts à importer.', 'description', 'n8n', ['requis']),
    ('Workflow templates for n8n, ready to import.', 'description', 'n8n', ['requis']),
    ('Custom nodes for n8n, written in TypeScript.', 'description', 'n8n', ['requis']),
    ('UI components for React, fully typed.', 'description', 'react', ['requis']),
    ('Modèles de workflows pour n8n, Make ou Zapier.', 'description', 'n8n', ['mention']),
    ('Wrappers for React, Vue and Angular.', 'description', 'react', ['mention']),
    ('- Docker and Docker Compose (optional, for local PostgreSQL)',
     'prerequis', 'docker', ['non_requis', 'non_requis']),
    ('- Docker et Docker Compose (facultatifs, pour PostgreSQL en local)',
     'prerequis', 'docker', ['non_requis', 'non_requis']),
    ('Docker and docker-compose are not required.', 'prerequis', 'docker', ['non_requis', 'non_requis']),
    ('- Docker Engine (Docker Desktop not required)', 'prerequis', 'docker', ['requis', 'mention']),
    ('- NVIDIA GPU (speeds up inference)', 'prerequis', 'gpu', ['mention']),
    ('- Docker Engine or Podman', 'prerequis', 'docker', ['mention']),
    ('- Docker Compose or Podman Compose', 'prerequis', 'docker', ['mention']),
    ("Without a GPU, it won't run.", 'description', 'gpu', ['non_requis']),
])
def test_sorte_revue5(banc, texte, colonne, cible, attendu):
    assert _sortes(banc.rd, texte, colonne, cible, len(attendu)) == attendu


def test_parenthese_dans_le_surlignage(banc):
    # fiches 2 : le surlignage FTS de « docker compose » couvre « Docker (Compose »
    texte = '- Requires Docker (Compose plugin recommended)'
    a, b = texte.index('Docker'), texte.index('Compose') + len('Compose')
    assert banc.rd.sorte_mention(texte, a, b, 'prerequis', 'plateforme') == 'requis'


def test_enumeration_longue_en_temps_lineaire(banc):
    # classement 0 : le motif d'énumération revenait en arrière de façon exponentielle (8 s pour 7 éléments)
    rd = banc.rd
    for texte, mot, nature in [
            ('API de transcription audio auto-hébergée. Stack : Docker, FastAPI, React, PostgreSQL, Redis, Celery, '
             'Nginx, RabbitMQ, Traefik, Grafana, Loki.', 'Docker', 'plateforme'),
            ('Intègre Docker, Kubernetes, Helm, Terraform, Ansible, Prometheus, Grafana et Loki.', 'Docker',
             'plateforme'),
            ('Fonctionne avec n8n, Make, Zapier, Pipedream, Activepieces, IFTTT et Power Automate.', 'n8n',
             'produit')]:
        a = texte.index(mot)
        debut = time.perf_counter()
        rd.sorte_mention(texte, a, a + len(mot), 'description', nature)
        assert time.perf_counter() - debut < 0.5
    assert rd._ENUMERATION_RE.match(', make ou zapier') and rd._ENUMERATION_RE.match(', podman, or any oci runtime')


# =============================================================================
# Requête
# =============================================================================
@pytest.mark.parametrize('texte, present, absent, exclusions, indifferent', [
    ('Find a web scraper without Docker', 'scraping', 'docker', [('docker', 'exclusion')], None),
    ('Trouve un OCR sans Docker', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('Retrouve le scraper sans Docker', None, 'docker', [('docker', 'exclusion')], None),
    ('a tool to find duplicate photos without a GPU', None, 'gpu', [('gpu', 'exclusion')], None),
    ("N'importe quel OCR sans GPU", 'ocr', 'gpu', [('gpu', 'exclusion')], None),
    ('un OCR qui arrive à tourner sans GPU', 'ocr', 'gpu', [('gpu', 'exclusion')], None),
    ("I can't find a tool without Docker", None, 'docker', [('docker', 'exclusion')], None),
    ('je ne trouve aucun outil sans Docker', None, 'docker', [('docker', 'exclusion')], None),
    ('a RAG pipeline that can retrieve documents without GPU', None, 'gpu', [('gpu', 'exclusion')], None),
    ("Find tools that don't require Docker", None, 'docker', [('docker', 'exclusion')], None),
    ('find an OCR without Docker', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('retrouver un OCR sans Docker', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('je cherche à retrouver un OCR sans Docker', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('find workflows without n8n', None, 'n8n', [('n8n', 'exclusion')], None),
    ('je veux retrouver des workflows sans n8n', None, 'n8n', [('n8n', 'exclusion')], None),
    ('I want to locate an OCR without Docker', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('remember the OCR without Docker', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ("Je n'arrive pas à installer Docker, je cherche un OCR sans Docker",
     'ocr', 'docker', [('docker', 'exclusion')], None),
    ('je ne sais pas configurer Kubernetes, je cherche un outil de déploiement sans Kubernetes',
     None, 'kubernetes', [('kubernetes', 'exclusion')], None),
    ("je n'arrive pas à utiliser Docker, je cherche un OCR", 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('Je ne sais pas utiliser Docker', None, 'docker', [('docker', 'exclusion')], None),
    ("I can't figure out Docker, I need a simple OCR tool", 'ocr', 'docker', [], None),
    ('Comme n8n a déjà un nœud HTTP, je cherche des workflows n8n pour Slack', 'n8n', None, [], None),
    ('Comme React me plaît, je cherche une bibliothèque de composants React pour tableaux de bord',
     'react', None, [], None),
    ('Comme n8n gère les webhooks, je cherche des modèles de workflows', 'n8n', None, [], None),
    ('Comme FastAPI génère déjà la doc OpenAPI, je cherche un générateur de client', 'fastapi', None, [], None),
    ('Comme Zapier, mais open source', 'workflow', None, [('zapier', 'reference')], None),
    ('Comme Zapier mais open source', 'workflow', None, [('zapier', 'reference')], None),
    ('un outil comme n8n en open source', None, None, [('n8n', 'reference')], None),
    ('Comme n8n est déjà installé sur mon serveur, je cherche des modèles de workflows', 'n8n', None, [], None),
    ("un OCR, Docker n'est malheureusement pas autorisé", 'ocr', 'docker', [('docker', 'exclusion')], None),
    ("un OCR, Docker n'est pas vraiment autorisé chez nous", 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('un OCR, Docker est également interdit chez nous', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('un OCR, Docker est désormais interdit', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('un OCR, Docker est toujours interdit au bureau', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('un OCR ; au bureau, Docker y est interdit', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('an OCR tool, Docker is unfortunately not allowed at work', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('an OCR tool, Docker is still not allowed at work', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ('an OCR tool, Docker is now banned on our servers', 'ocr', 'docker', [('docker', 'exclusion')], None),
    ("un OCR, Docker n'est plus autorisé", 'ocr', 'docker', [('docker', 'exclusion')], None),
    ("un OCR avec Docker, Docker n'est pas interdit ici", 'docker', None, [], None),
    ('une alternative à Zapier car le cloud est interdit chez nous', 'workflow', None, [('zapier', 'reference')], None),
    ('a Markdown note-taking app without relying on Windows', None, 'windows', [('windows', 'exclusion')], None),
    ("an OCR that doesn't depend on Windows", 'ocr', 'windows', [('windows', 'exclusion')], None),
    ('an OCR tool without relying on Windows', 'ocr', 'windows', [('windows', 'exclusion')], None),
    ('a note app without depending on macOS', None, 'macos', [('macos', 'exclusion')], None),
    ('convert Word documents to PDF without relying on Windows', None, 'windows', [('windows', 'exclusion')], None),
    ('a backup tool without depending on Linux', None, 'linux', [('linux', 'exclusion')], None),
    ('without installation on Windows', 'windows', None, [], None),
    ('un outil de transcription sans installation sur Linux', 'linux', None, [], None),
    ('an OCR tool without installing anything on Windows', 'windows', None, [], None),
    ('a self-hosted bug tracker without relying on Docker', None, 'docker', [('docker', 'exclusion')], None),
    ("a self-hosted bug tracker that doesn't depend on Docker", None, 'docker', [('docker', 'exclusion')], None),
    ('a bug tracker without depending on Docker', None, 'docker', [('docker', 'exclusion')], None),
    ('a crash reporter without depending on Docker', None, 'docker', [('docker', 'exclusion')], None),
    ('un éditeur Markdown qui ne plante jamais sous Windows', 'windows', None, [], None),
    ("a markdown editor that doesn't crash on Linux", 'linux', None, [], None),
    ('un outil qui ne plante pas sans Docker', None, 'docker', [('docker', 'exclusion')], None),
    ('Aucun GPU installé sur ma machine, je cherche un OCR', 'ocr', 'gpu', [('gpu', 'exclusion')], None),
    ('I have no GPU installed, looking for an OCR tool', 'ocr', 'gpu', [('gpu', 'exclusion')], None),
    ('no CUDA installed on this machine, I need speech to text', None, 'gpu', [('gpu', 'exclusion')], None),
    ("je n'ai pas Docker installé, je cherche un OCR", 'ocr', 'docker', [('docker', 'exclusion')], None),
    ("I haven't used n8n before, I need workflow templates", 'workflow', None, [], None),
    ("Je n'ai jamais utilisé n8n", None, None, [], None),
    ("I don't care about GPU acceleration, I need a lightweight OCR", 'ocr', 'gpu', [], 'GPU'),
    ("je ne vois pas l'intérêt de Docker pour un simple OCR", 'ocr', 'docker', [], None),
    ("I don't care about React, I need a Vue component library", 'vue', 'react', [], 'React'),
    ("a dashboard component library, doesn't matter if it's React or Vue", None, 'react', [], 'React'),
    ("ça ne me dérange pas d'utiliser Docker pour l'OCR", 'ocr', 'docker', [], 'Docker'),
    ("I can't find the n8n workflow I saved to sync my CRM", 'n8n', None, [], None),
    ("je ne sais plus quel outil Docker j'avais enregistré pour l'OCR", 'ocr', None, [], None),
    ('je ne sais pas quel outil n8n choisir pour synchroniser un CRM', 'n8n', None, [], None),
    ("je n'arrive pas à retrouver le dépôt n8n pour synchroniser un CRM", 'n8n', None, [], None),
    ('je trouve plus le dépôt n8n pour synchroniser un CRM', 'n8n', None, [], None),
    ("I don't want n8n", None, None, [('n8n', 'exclusion')], None),
    ('sans GPU sous Windows', 'windows', None, [('gpu', 'exclusion')], None),
    # permission et capacité ; « n'ai » n'est pas « AI »
    ("I'm not allowed to install Docker, I need an OCR", 'ocr', 'docker', [('docker', 'exclusion')], None),
    ("je n'ai pas le droit d'installer Docker, je cherche un OCR", 'ocr', 'ia', [('docker', 'exclusion')], None),
    ("I'm not able to find the n8n workflow I saved", 'n8n', None, [], None),
    ("je n'ai pas de GPU, je cherche un OCR", 'ocr', 'ia', [('gpu', 'exclusion')], None),
])
def test_requete_revue5(banc, texte, present, absent, exclusions, indifferent):
    requete = banc.rd.analyser_requete(texte)
    cles = {c.cle for c in requete.concepts}
    assert [(e['cible'], e['source']) for e in requete.exclusions] == exclusions
    if present:
        assert present in cles
    if absent:
        assert absent not in cles
    if indifferent:
        assert indifferent in requete.indifferents


def test_verbe_regi_hors_des_notions(banc):
    # requête 0, 7 : le verbe que la négation régit n'est pas une notion du besoin
    rd = banc.rd
    for texte, verbe in [('je ne retrouve plus le dépôt n8n pour synchroniser un CRM', 'retrouve'),
                         ("ça ne me dérange pas d'utiliser Docker pour l'OCR", 'derange'),
                         ('un éditeur Markdown qui ne plante jamais sous Windows', 'plante'),
                         ("I don't care about GPU acceleration, I need a lightweight OCR", 'care')]:
        assert verbe not in {c.cle for c in rd.analyser_requete(texte).concepts}
    requete = rd.analyser_requete("I don't care about GPU acceleration, I need a lightweight OCR")
    assert requete.indifferents == ['GPU'] and 'acceleration' not in {c.cle for c in requete.concepts}


def test_reference_renommee_reste_a_remplacer(banc):
    # revue 6 (requête 3, classement 1) : un produit à remplacer renommé ailleurs reste à remplacer, jamais cherché
    rd = banc.rd
    for texte, produit in [('une alternative à Zapier, Zapier est trop cher pour nous', 'zapier'),
                           ("J'utilise n8n aujourd'hui, je cherche une alternative open source à n8n", 'n8n'),
                           ('I currently use Zapier but want a self-hosted Zapier alternative', 'zapier')]:
        requete = rd.analyser_requete(texte)
        assert [(e['cible'], e['source']) for e in requete.exclusions] == [(produit, 'reference')]
        assert produit not in {c.cle for c in requete.concepts} and 'workflow' in {c.cle for c in requete.concepts}


# =============================================================================
# Classement et sorties
# =============================================================================
def _fiche(nom, url=None, analyse='2026-10-11', **champs):
    props = {'Catégorie': p_select('OCR/Documents'), 'Brique pour': p_multi(), 'Analysé le': p_date(analyse)}
    props.update({colonne: p_texte(texte) for colonne, texte in champs.items()})
    return page(nom, url or f'https://github.com/synth/{nom}', props=props, cree=f'{analyse}T08:00:00.000Z')


def test_no_coding_ne_nie_pas_la_suite(banc):
    # classement 4 : « No coding required to build workflows » parle de workflows
    rd = banc.rd
    texte = 'Self-hosted automation platform. No coding required to build workflows.'
    a = texte.index('workflows')
    assert not rd.occurrence_niee(texte, a, a + len('workflows'))
    assert not rd.occurrence_niee('Aucune programmation nécessaire pour créer des workflows.', 47, 56)
    assert rd.occurrence_niee('Fonctionne sans GPU.', 16, 19)
    index_du_corpus(rd, [_fiche('flowcraft', Description=texte),
                         _fiche('flow-simple', Description='Self-hosted automation platform to build workflows.')])
    reponse = _chercher(rd, 'an alternative to n8n to build workflows')
    assert {r.cle: r.m.get('workflow') for r in reponse.resultats} == {'synth/flowcraft': 1.0,
                                                                       'synth/flow-simple': 1.0}


def test_fiche_principale_citee(banc):
    # classement 6 : à état égal, la preuve de la fiche principale (la plus récente), pas d'une plus ancienne
    rd = banc.rd
    url = 'https://github.com/synth/ocr-a'
    index_du_corpus(rd, [
        _fiche('ocr-a', url, '2025-03-01', Description='OCR de documents scannés. Nécessite Docker.'),
        _fiche('ocr-a', url, '2026-10-20', Description='OCR de documents scannés.', **{'Prérequis': '- Docker 24+'})])
    r = _chercher(rd, 'un OCR de documents scannés sans Docker').resultats[0]
    assert r.exclusions[0]['etat'] == 'requis'
    assert '2026-10-20' in r.exclusions[0]['texte'] and '2025-03-01' not in r.exclusions[0]['texte']


def test_meme_phrase_citee_une_fois(banc):
    # classement 5 : une phrase qui contient les deux preuves d'un « contradictoire » n'est citée qu'une fois
    rd = banc.rd
    index_du_corpus(rd, [_fiche('ocr-b', Description='OCR de documents scannés.',
                                **{'Prérequis': '- Docker required (Docker optional for tests)'})])
    x = _chercher(rd, 'un OCR de documents scannés sans Docker').resultats[0].exclusions[0]
    assert x['etat'] == 'contradictoire' and x['texte'].count('Docker required') == 1
