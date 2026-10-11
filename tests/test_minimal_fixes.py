"""Tests de non-régression des correctifs minimaux (avant le lot 3).

MF1 : Installation, Exemple, Prérequis et Type ne sont plus présentés comme des faits sans preuve
dans les métadonnées GitHub ou le README : sans preuve, « Non vérifié » (texte) ou liste vide (Type).
Réseau entièrement simulé (FakeAPI du lot 1) ; time.sleep est neutralisé.
"""
import base64

import pytest

from test_gitnotate_lot1 import BASE_ENV, FakeAPI, make_response, repo_data

# Dépôt du diagnostic lot3/diag/test_diag_invention.py : README muet sur l'installation,
# « agent » seulement dans « user-agent »
REPO = {'name': 'foo', 'full_name': 'o/foo', 'language': 'Python', 'description': 'A fast user-agent string parser',
        'topics': [], 'stars': 3, 'updated_at': '2026-09-01T00:00:00Z',
        'readme': '# foo\nParse HTTP User-Agent headers. Usage: see the source.'}

SCHEMA_TYPE_OPTIONS = {'Agent IA', 'ML/AI', 'Web', 'Outils'}


def _text(props, name):
    return ''.join(part['text']['content'] for part in props[name]['rich_text'])


def _props(gn, repo):
    analysis = gn.analyze_repo_for_usage(dict(repo))
    return gn.build_page_properties(dict(repo), 'https://github.com/o/foo', analysis, {'score': 5}, False)


@pytest.fixture
def world(load_gn, monkeypatch):
    def _make(readme=b'# Demo\nREADME', **repo_extra):
        gn = load_gn(**BASE_ENV)
        api = FakeAPI()
        api.repos['owner/repo'] = repo_data('owner', 'repo', **repo_extra)
        api.route('GET', r'api\.github\.com/repos/owner/repo/readme$',
                  lambda u, p: make_response(200, {'content': base64.b64encode(readme).decode()}))
        monkeypatch.setattr(gn, 'get_session', lambda: api)
        monkeypatch.setattr(gn.time, 'sleep', lambda s: api.sleeps.append(s))
        monkeypatch.setattr(gn.atexit, 'register', lambda f, *a, **k: None)
        return gn, api
    return _make


def _posted_pages(api):
    return [payload for method, url, payload in api.calls
            if method == 'POST' and url == 'https://api.notion.com/v1/pages']

# =============================================================================
# MF1 — champs heuristiques
# =============================================================================
def test_mf1_silent_readme_gives_non_verifie(load_gn):
    gn = load_gn()
    analysis = gn.analyze_repo_for_usage(dict(REPO))
    assert analysis['example'] == 'Non vérifié'               # plus de « pip install foo » supposé
    assert analysis['prerequisites'] == 'Non vérifié'         # plus de « Python recent »
    assert analysis['installation'] == 'Non vérifié'          # plus de « See documentation »
    props = _props(gn, REPO)
    for name in ('Exemple', 'Prérequis', 'Installation'):
        assert _text(props, name) == 'Non vérifié'
    assert props['Type'] == {'multi_select': []}              # « user-agent » n'est pas un agent IA


@pytest.mark.parametrize('language', ['Python', 'JavaScript', 'TypeScript', 'Go', None])
def test_mf1_prerequisites_never_guessed_from_language(load_gn, language):
    gn = load_gn()
    assert gn.analyze_repo_for_usage(dict(REPO, language=language))['prerequisites'] == 'Non vérifié'


# v7.3 : Exemple = premier bloc de code d'une section Usage / Example(s) / Exemple(s) / Utilisation du
# README complet, recopié tel quel ; une commande hors section n'est plus reconstruite (« pip install <nom> »)
@pytest.mark.parametrize('name,readme,expected', [
    ('foo', 'Install with `pip install foo`.', 'Non vérifié'),
    ('foo', 'Run:\n\n    python -m pip install foo\n', 'Non vérifié'),
    ('foo', 'pip3 install foo', 'Non vérifié'),
    ('foo', '```\nnpm install foo --save\n```', 'Non vérifié'),            # bloc de code hors section
    ('FastAPI', 'pip install fastapi', 'Non vérifié'),
    ('foo', '## Usage\n\n```python\nimport foo\nfoo.run()\n```\n', 'import foo\nfoo.run()'),
    ('foo', '## Exemples\n```\nnpm install foo --save\n```', 'npm install foo --save'),
    ('foo', '## Usage\nSee the source.\n', 'Non vérifié'),                 # section sans bloc de code
    ('foo', 'pip install "foo[all]"', 'Non vérifié'),
    ('foo', 'pip install foo-bar', 'Non vérifié'),                         # autre paquet
    ('foo', 'pip install foobar', 'Non vérifié'),
    ('foo', 'npm install foo.js', 'Non vérifié'),
    ('foo', 'pipx install foo', 'Non vérifié'),
    ('foo', 'pip install -r requirements.txt', 'Non vérifié'),
    ('foo', 'pip install git+https://github.com/o/foo', 'Non vérifié'),
    ('foo', 'yarn add foo', 'Non vérifié'),
    ('a.b', 'pip install aXb', 'Non vérifié'),                             # nom échappé dans le motif
    ('', 'pip install foo', 'Non vérifié'),
    ('foo', '', 'Non vérifié'),
])
def test_mf1_example_only_when_readme_contains_command(load_gn, name, readme, expected):
    gn = load_gn()
    assert gn.analyze_repo_for_usage(dict(REPO, name=name, readme=readme))['example'] == expected


def test_mf1_example_independent_of_language(load_gn):
    gn = load_gn()
    # Le README prouve la commande npm même si GitHub annonce Python ; rien n'est déduit du langage
    readme = '## Usage\n```\nnpm install foo\n```'
    assert gn.analyze_repo_for_usage(dict(REPO, readme=readme))['example'] == 'npm install foo'
    assert gn.analyze_repo_for_usage(dict(REPO, language='JavaScript', readme='# foo'))['example'] == 'Non vérifié'


def test_mf1_installation_still_extracted_from_readme(load_gn):
    gn = load_gn()
    block = '# foo\n\n## Installation\n\n```bash\npip install foo\n```\n\n## Usage\nfoo --help\n'
    assert gn.analyze_repo_for_usage(dict(REPO, readme=block))['installation'] == 'pip install foo'
    # v7.3 : seulement le premier bloc de code de la section (verbatim) ; du texte seul → Non vérifié
    lines = '# foo\n\n## Getting Started\n\nClone the repository then run make.\n\n## License\nMIT\n'
    assert gn.analyze_repo_for_usage(dict(REPO, readme=lines))['installation'] == 'Non vérifié'
    empty = '# foo\n\n## Installation\n\n## Usage\n'
    assert gn.analyze_repo_for_usage(dict(REPO, readme=empty))['installation'] == 'Non vérifié'


@pytest.mark.parametrize('topics,description,expected', [
    (['agent'], '', ['Agent IA']),
    (['agents'], '', ['Agent IA']),
    (['ai-agent'], '', ['Agent IA']),
    (['ai-agents'], '', ['Agent IA']),
    (['AI-Agent'], '', ['Agent IA']),
    (['user-agent'], '', []),                                    # plus de recherche par sous-chaîne
    (['agentic-workflow'], '', []),
    ([], 'An autonomous AI agent framework', []),               # la description ne suffit plus
    (['machine-learning'], '', ['ML/AI']),
    (['ai'], '', ['ML/AI']),
    (['deep-learning'], '', []),
    (['web'], '', ['Web']),
    (['frontend'], '', ['Web']),
    (['backend', 'react'], '', []),
    (['ai-agents', 'ai', 'frontend', 'cli'], '', ['Agent IA', 'ML/AI', 'Web']),
    ([], '', []),                                               # plus d'« Outils » par défaut
    (None, '', []),
    ([None, 3, 'web'], '', ['Web']),
])
def test_mf1_type_only_from_exact_topics(load_gn, topics, description, expected):
    gn = load_gn()
    props = _props(gn, dict(REPO, topics=topics, description=description))
    assert props['Type'] == {'multi_select': [{'name': n} for n in expected]}
    assert set(expected) <= SCHEMA_TYPE_OPTIONS


def test_mf1_type_values_are_existing_schema_options(world):
    """Aucune nouvelle option : les valeurs possibles de Type existent déjà dans le schéma de création."""
    gn, api = world()
    assert gn.create_database('page-1') is not None
    payload = [p for m, u, p in api.calls if m == 'POST' and u == 'https://api.notion.com/v1/databases'][0]
    options = {o['name'] for o in payload['properties']['Type']['multi_select']['options']}
    assert options == SCHEMA_TYPE_OPTIONS
    assert {name for name, _ in gn._TYPE_TOPICS} <= options
    assert gn.REQUIRED_DB_PROPERTIES['Type'] == 'multi_select'


def test_mf1_full_run_writes_non_verifie_and_empty_type(world):
    gn, api = world(readme=b'# repo\nParse HTTP User-Agent headers.', topics=[],
                    description='A fast user-agent string parser')
    assert gn.main([]) == 0
    pages = _posted_pages(api)
    assert len(pages) == 1
    props = pages[0]['properties']
    for name in ('Exemple', 'Prérequis', 'Installation'):
        assert _text(props, name) == 'Non vérifié'
    assert props['Type'] == {'multi_select': []}


def test_mf1_full_run_keeps_proven_values(world):
    readme = b'# repo\n\n## Installation\n\n```bash\npip install repo\n```\n\n## Usage\n```\nrepo --help\n```\n'
    gn, api = world(readme=readme, topics=['ai-agents', 'web'])
    assert gn.main([]) == 0
    props = _posted_pages(api)[0]['properties']
    assert _text(props, 'Exemple') == 'repo --help'                  # v7.3 : bloc de la section Usage
    assert _text(props, 'Installation') == 'pip install repo'
    assert _text(props, 'Prérequis') == 'Non vérifié'
    assert props['Type'] == {'multi_select': [{'name': 'Agent IA'}, {'name': 'Web'}]}
