"""Configuration commune des tests Gitnotate.

Les tests ne doivent JAMAIS accéder au réseau ni lire un vrai fichier .env :
- GITNOTATE_NO_DOTENV=1 empêche le chargement du .env à l'import ;
- toute tentative de connexion réseau lève une erreur ;
- GITNOTATE_DATA_DIR pointe vers un dossier temporaire (cache, stats, journaux).
"""
import importlib
import os
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ['GITNOTATE_NO_DOTENV'] = '1'

# Variables lues par les scripts : purgées avant chaque test pour qu'un
# environnement de développement ne fuie jamais dans les tests.
_GITNOTATE_ENV_PREFIXES = (
    'NOTION_', 'GITHUB_', 'OPENROUTER_', 'MISTRAL_', 'TRANSLATION_', 'LLM_',
    'DATABASE_ID', 'PARENT_PAGE_ID', 'MAX_', 'DRY_RUN', 'MIN_UPDATE_DAYS',
    'CACHE_', 'HTTP_TIMEOUT', 'README_', 'SCORE_MIN_THRESHOLD', 'LOG_LEVEL',
    'USER_PROFILE_JSON', 'CREATE_DATABASE', 'REQUIRE_LLM', 'CLEANER_',
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError("Accès réseau interdit pendant les tests")
    monkeypatch.setattr(socket.socket, 'connect', _blocked)
    monkeypatch.setattr(socket, 'create_connection', _blocked)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    for key in list(os.environ):
        if key.startswith(_GITNOTATE_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('GITNOTATE_NO_DOTENV', '1')
    monkeypatch.setenv('GITNOTATE_DATA_DIR', str(tmp_path))
    monkeypatch.chdir(tmp_path)


# Tests du lot 1 qui créent volontairement une fiche SANS LLM disponible (comportement
# historique : fiche au score lexical). Depuis le lot 2, le mode reprise (REQUIRE_LLM=true
# par défaut) interdit ces fiches ; ces tests tournent donc avec REQUIRE_LLM=false.
_LEGACY_LEXICAL_TESTS = {
    ('test_gitnotate_lot1', 'test_null_fields_through_full_run'),
    ('test_gitnotate_lot1', 'test_same_repo_via_two_urls_creates_one_page'),
    ('test_gitnotate_lot1', 'test_reservation_released_when_creation_fails'),
}


@pytest.fixture(autouse=True)
def _legacy_lexical_mode(request, monkeypatch, _isolated_env):
    module = request.module.__name__.rsplit('.', 1)[-1]
    if (module, request.node.originalname) in _LEGACY_LEXICAL_TESTS:
        monkeypatch.setenv('REQUIRE_LLM', 'false')


@pytest.fixture
def load_gn(monkeypatch):
    """Recharge gitnotate avec les variables d'environnement données.

    Usage : gn = load_gn(PARENT_PAGE_ID='x', DRY_RUN='true')
    """
    def _load(**env):
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, str(value))
        module = importlib.import_module('gitnotate')
        return importlib.reload(module)
    return _load
