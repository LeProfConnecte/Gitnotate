"""Tests du lot 1 (stabilisation v7.2) — réseau entièrement simulé.

Une fausse API (FakeAPI) remplace la session HTTP : Notion, GitHub, Mistral et
OpenRouter sont simulés ; time.sleep est neutralisé et enregistré.
"""
import atexit
import base64
import email.utils
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent

# =============================================================================
# OUTILS DE SIMULATION
# =============================================================================
SCHEMA_TYPES = {
    'Nom': 'title', 'URL': 'url', 'Description': 'rich_text', "Cas d'usage": 'rich_text',
    'Installation': 'rich_text', 'Exemple': 'rich_text', 'Prérequis': 'rich_text',
    'Stars': 'number', 'Pertinence': 'number', 'Langage': 'select', 'Statut': 'select',
    'Type': 'multi_select', 'Dernière MAJ': 'date', 'Analysé le': 'date',
}
# Réponse LLM v2 (v7.3) : avec maturité et licence non vérifiées (dépôts simulés sans pushed_at
# ni licence), Pertinence = arrondi de 10 × (4×2/3 + 1×2/2 + 2×1/2 + 1×2/2) / 8 = 7 (comme en v7.2)
GOOD_LLM = {'description_fr': 'Un outil en français', 'cas_usage': ['usage'],
            'categorie': 'Automatisation/No-code', 'type_reutilisation': 'bibliotheque', 'brique_pour': [],
            'utilite_immediate': 0, 'potentiel_futur': 2, 'interet': 2, 'integration': 1, 'compatibilite': 2,
            'justification': 'pertinent pour le profil'}
GOOD_JSON = json.dumps(GOOD_LLM, ensure_ascii=False)


def make_response(status=200, body=None, headers=None, text=None):
    """Vrai requests.Response (un 4xx est « falsy », comme en production)."""
    r = requests.Response()
    r.status_code = status
    if text is not None:
        r._content = text.encode('utf-8')
    elif body is not None:
        r._content = json.dumps(body).encode('utf-8')
    else:
        r._content = b''
    r.encoding = 'utf-8'
    if headers:
        r.headers.update(headers)
    return r


def chat(content, finish='stop', model='mistral-small-2503'):
    return {'id': 'gen-1', 'model': model,
            'choices': [{'index': 0, 'finish_reason': finish,
                         'message': {'role': 'assistant', 'content': content}}]}


def db_body(types=None, justification='rich_text'):
    types = dict(SCHEMA_TYPES if types is None else types)
    if justification:
        types['Justification'] = justification
    return {'object': 'database', 'id': 'db-1', 'url': 'https://www.notion.so/db1',
            'properties': {n: {'id': n, 'type': t, t: {}} for n, t in types.items()}}


def rt_text(content, link=None):
    return {'type': 'text', 'text': {'content': content, 'link': {'url': link} if link else None},
            'plain_text': content, 'href': link}


def rt_mention(url):
    return {'type': 'mention', 'mention': {'type': 'link_preview', 'link_preview': {'url': url}},
            'plain_text': url, 'href': url}


def text_block(btype, rich_text, block_id=None, has_children=False):
    return {'object': 'block', 'id': block_id or f'blk-{btype}', 'type': btype,
            'has_children': has_children, btype: {'rich_text': rich_text}}


def existing_page(url):
    return {'object': 'page', 'properties': {'URL': {'id': 'u', 'type': 'url', 'url': url}}}


def repo_data(owner, repo, **extra):
    data = {'name': repo, 'full_name': f'{owner}/{repo}',
            'description': 'An automation tool for AI workflows', 'stargazers_count': 42,
            'language': 'Python', 'updated_at': '2026-09-01T10:00:00Z',
            'topics': ['ai', 'automation'], 'html_url': f'https://github.com/{owner}/{repo}',
            'private': False}
    data.update(extra)
    return data


class FakeAPI:
    """Session HTTP simulée. Routes prioritaires via route(), sinon comportement nominal."""

    def __init__(self):
        self.calls = []
        self.routes = []
        self._lock = threading.Lock()
        self.db = db_body()
        self.query_pages = [[]]
        self.blocks = {}
        self.repos = {}
        self.llm_content = GOOD_JSON
        self.sleeps = []
        self.set_page_urls(['https://github.com/owner/repo'])

    def set_page_urls(self, urls, root='page-1'):
        self.blocks[root] = [[text_block('paragraph', [rt_text(u)], f'blk-{i}')
                              for i, u in enumerate(urls)]]
        for u in urls:
            parts = [p for p in u.split('github.com/', 1)[-1].split('/') if p]
            if len(parts) >= 2 and parts[0] != 'ghost':   # ghost/* → 404 GitHub
                self.repos.setdefault(f'{parts[0]}/{parts[1]}', repo_data(parts[0], parts[1]))

    def route(self, method, pattern, handler):
        self.routes.insert(0, (method, re.compile(pattern), handler))

    def count(self, method, pattern):
        with self._lock:
            return sum(1 for m, u, _ in self.calls if m == method and re.search(pattern, u))

    def get(self, url, headers=None, params=None, timeout=None):
        return self._dispatch('GET', url, params)

    def post(self, url, headers=None, json=None, timeout=None):
        return self._dispatch('POST', url, json)

    def _dispatch(self, method, url, payload):
        with self._lock:
            self.calls.append((method, url, payload))
        for m, rx, handler in list(self.routes):
            if m == method and rx.search(url):
                res = handler(url, payload)
                if isinstance(res, BaseException):
                    raise res
                return res
        return self._default(method, url, payload)

    @staticmethod
    def _paginate(pages, cursor):
        idx = int(cursor) if cursor else 0
        more = idx + 1 < len(pages)
        return make_response(200, {'object': 'list', 'results': pages[idx], 'has_more': more,
                                   'next_cursor': str(idx + 1) if more else None})

    def _default(self, method, url, payload):
        payload = payload or {}
        if method == 'GET' and url == 'https://api.notion.com/v1/users/me':
            return make_response(200, {'object': 'user', 'name': 'Gitnotate bot'})
        if method == 'GET' and re.fullmatch(r'https://api\.notion\.com/v1/databases/[^/]+', url):
            return make_response(200, self.db)
        if method == 'POST' and re.fullmatch(r'https://api\.notion\.com/v1/databases/[^/]+/query', url):
            return self._paginate(self.query_pages, payload.get('start_cursor'))
        m = re.fullmatch(r'https://api\.notion\.com/v1/blocks/([^/]+)/children', url)
        if method == 'GET' and m:
            pages = self.blocks.get(m.group(1))
            if pages is None:
                return make_response(404, {'message': 'Could not find block'})
            return self._paginate(pages, payload.get('start_cursor'))
        if method == 'POST' and url == 'https://api.notion.com/v1/pages':
            return make_response(200, {'object': 'page', 'id': 'page-new'})
        if method == 'POST' and url == 'https://api.notion.com/v1/databases':
            return make_response(200, {'object': 'database', 'id': 'new-db',
                                       'url': 'https://www.notion.so/new-db'})
        if method == 'GET' and url == 'https://api.github.com/user':
            return make_response(200, {'login': 'me', 'plan': {'name': 'free'}})
        m = re.fullmatch(r'https://api\.github\.com/repos/([^/]+)/([^/]+)(/readme)?', url)
        if method == 'GET' and m:
            data = self.repos.get(f'{m.group(1)}/{m.group(2)}')
            if data is None:
                return make_response(404, {'message': 'Not Found'})
            if m.group(3):
                return make_response(200, {'content': base64.b64encode(b'# Demo\nREADME').decode()})
            return make_response(200, data)
        if method == 'POST' and ('api.mistral.ai' in url or 'openrouter.ai' in url):
            return make_response(200, chat(self.llm_content))
        raise AssertionError(f'appel inattendu {method} {url}')


BASE_ENV = {
    'PARENT_PAGE_ID': 'page-1',
    'NOTION_TOKEN': 'ntn_test_token_1234',
    'DATABASE_ID': 'db-1',
    'MISTRAL_API_KEY': 'mistral-test-key',
    'MAX_WORKERS': '1',
}


@pytest.fixture
def world(load_gn, monkeypatch):
    """Recharge gitnotate avec BASE_ENV (+ surcharges) et branche la fausse API."""
    def _make(**env):
        merged = dict(BASE_ENV)
        merged.update(env)
        gn = load_gn(**merged)
        api = FakeAPI()
        monkeypatch.setattr(gn, 'get_session', lambda: api)
        monkeypatch.setattr(gn.time, 'sleep', lambda s: api.sleeps.append(s))
        api.atexit_registered = []
        monkeypatch.setattr(gn.atexit, 'register', lambda f, *a, **k: api.atexit_registered.append(f))
        return gn, api
    return _make


@pytest.fixture
def http(load_gn, monkeypatch):
    """Module rechargé + fausse API, pour tester http_request_with_retry seul."""
    def _make(**env):
        gn = load_gn(**env)
        api = FakeAPI()
        monkeypatch.setattr(gn, 'get_session', lambda: api)
        monkeypatch.setattr(gn.time, 'sleep', lambda s: api.sleeps.append(s))
        return gn, api
    return _make


def sequence(*responses):
    """Handler renvoyant les réponses dans l'ordre (la dernière est répétée)."""
    items = list(responses)

    def handler(url, payload):
        return items.pop(0) if len(items) > 1 else items[0]
    return handler


def history(gn):
    return json.loads(gn.STATS_FILE.read_text(encoding='utf-8'))


NULL_REPO = {'name': 'demo', 'language': None, 'topics': None, 'readme': None,
             'description': None, 'stars': None, 'updated_at': None, 'html_url': None}

# =============================================================================
# 1. VERSION
# =============================================================================
def test_version_constant_banner_and_stats(world, capsys):
    gn, api = world()
    assert gn.__version__ == "7.3.0"
    assert 'Nouveautés v7.3' in gn.__doc__ and 'Nouveautés v7.2' in gn.__doc__
    assert gn.main([]) == 0
    assert "GITNOTATE v7.3.0" in capsys.readouterr().out
    assert history(gn)[-1]['version'] == '7.3.0'


def test_version_option(load_gn, capsys):
    gn = load_gn()
    with pytest.raises(SystemExit) as exc:
        gn.main(['--version'])
    assert exc.value.code == 0
    assert '7.3.0' in capsys.readouterr().out

# =============================================================================
# 2. AUCUN EFFET DE BORD À L'IMPORT, BASE_DIR, .env, PROFIL, JETONS
# =============================================================================
def test_import_has_no_side_effects(load_gn, monkeypatch, tmp_path):
    (tmp_path / '.gitnotate_cache.json').write_text('{corrompu', encoding='utf-8')
    registered = []
    monkeypatch.setattr(atexit, 'register', lambda f, *a, **k: registered.append(f))
    gn = load_gn(PARENT_PAGE_ID=None)          # plus de SystemExit à l'import
    assert gn.PARENT_PAGE_ID == ''
    assert registered == []
    assert gn.GITHUB_CACHE == {}
    assert (tmp_path / '.gitnotate_cache.json').exists()   # cache non lu à l'import
    assert not (tmp_path / '.gitnotate_cache.json.bak').exists()


def test_cache_and_atexit_initialized_in_main(world):
    gn, api = world()
    assert gn.main([]) == 0
    assert gn.flush_github_cache in api.atexit_registered


def test_missing_parent_page_id_exits_1_without_network(world, capsys):
    gn, api = world(PARENT_PAGE_ID=None)
    assert gn.main([]) == 1
    assert api.calls == []
    assert 'PARENT_PAGE_ID' in capsys.readouterr().err


def test_dotenv_only_without_no_dotenv_flag(load_gn, monkeypatch, tmp_path):
    (tmp_path / '.env').write_text('PARENT_PAGE_ID=depuis_fichier_env\n', encoding='utf-8')
    gn = load_gn()
    assert gn.PARENT_PAGE_ID == ''               # GITNOTATE_NO_DOTENV=1 : .env ignoré
    # Enregistre la variable pour qu'elle soit retirée à la fin du test
    monkeypatch.setenv('PARENT_PAGE_ID', 'x')
    monkeypatch.delenv('PARENT_PAGE_ID')
    monkeypatch.delenv('GITNOTATE_NO_DOTENV')
    gn = load_gn()
    assert gn.BASE_DIR == tmp_path
    assert gn.PARENT_PAGE_ID == 'depuis_fichier_env'   # chemin explicite BASE_DIR/.env


def test_state_files_relative_to_base_dir(load_gn, monkeypatch, tmp_path):
    data_dir, other = tmp_path / 'donnees', tmp_path / 'ailleurs'
    data_dir.mkdir()
    other.mkdir()
    monkeypatch.chdir(other)
    (data_dir / 'user_profile.json').write_text(json.dumps({'languages': ['Go']}), encoding='utf-8')
    (other / 'user_profile.json').write_text(json.dumps({'languages': ['Cobol']}), encoding='utf-8')
    gn = load_gn(GITNOTATE_DATA_DIR=str(data_dir))
    for path in (gn.CACHE_FILE, gn.STATS_FILE, gn.STATE_FILE, gn.URLS_FILE, gn.PROFILE_FILE):
        assert path.parent == data_dir
    profile, source = gn.load_user_profile()
    assert profile == {'languages': ['Go']} and source.startswith('fichier')
    monkeypatch.setenv('USER_PROFILE_JSON', '{"languages": ["Rust"]}')
    assert gn.load_user_profile() == ({'languages': ['Rust']}, 'variable USER_PROFILE_JSON')
    monkeypatch.delenv('USER_PROFILE_JSON')
    (data_dir / 'user_profile.json').unlink()
    profile, source = gn.load_user_profile()
    assert profile is gn.USER_PROFILE_DEFAULT and 'défaut' in source


def test_default_base_dir_is_script_directory(load_gn, monkeypatch):
    monkeypatch.delenv('GITNOTATE_DATA_DIR')
    gn = load_gn()
    assert gn.BASE_DIR == ROOT


def test_profile_source_displayed_at_startup(world, capsys, tmp_path):
    (tmp_path / 'user_profile.json').write_text(json.dumps({'languages': ['Python']}), encoding='utf-8')
    gn, api = world()
    assert gn.main([]) == 0
    out = capsys.readouterr().out
    assert f"Profil de pertinence : fichier {tmp_path / 'user_profile.json'}" in out


def test_tokens_are_stripped(load_gn):
    gn = load_gn(NOTION_TOKEN='  ntn_abc123456 \n', GITHUB_TOKEN=' ghp_x123456789 ', PARENT_PAGE_ID=' p1 ')
    assert gn.NOTION_TOKEN == 'ntn_abc123456'
    assert gn.NOTION_HEADERS['Authorization'] == 'Bearer ntn_abc123456'
    assert gn.GITHUB_HEADERS['Authorization'] == 'Bearer ghp_x123456789'
    assert gn.PARENT_PAGE_ID == 'p1'

# =============================================================================
# 3. VARIABLES ENTIÈRES
# =============================================================================
@pytest.mark.parametrize('name,value', [
    ('MAX_WORKERS', '0'), ('MAX_WORKERS', 'abc'), ('MAX_RETRIES', '0'), ('HTTP_TIMEOUT', '0'),
    ('MIN_UPDATE_DAYS', '-1'), ('README_LLM_CHARS', '1.5'), ('MAX_WAIT_SECONDS', '-3'),
    ('MAX_REPOS', 'x'), ('CACHE_TTL_HOURS', '-2'), ('SCORE_MIN_THRESHOLD', 'sept'),
])
def test_invalid_int_config_exits_1_before_network(world, capsys, name, value):
    gn, api = world(**{name: value})
    assert name in gn.CONFIG_ERRORS
    assert gn.main([]) == 1
    assert api.calls == []
    err = capsys.readouterr().err
    assert name in err and 'Traceback' not in err


def test_env_int_valid_values(load_gn):
    gn = load_gn(MAX_WORKERS='3', MIN_UPDATE_DAYS='0', CACHE_TTL_HOURS='2', MAX_WAIT_SECONDS=' 30 ')
    assert (gn.MAX_WORKERS, gn.MIN_UPDATE_DAYS, gn.CACHE_TTL_SECONDS, gn.MAX_WAIT_SECONDS) == (3, 0, 7200, 30)
    assert gn.CONFIG_ERRORS == {}
    assert gn._env_int('GITNOTATE_ABSENT_X', 7, 1) == 7

# =============================================================================
# 4. CODES DE SORTIE
# =============================================================================
def test_exit_code_2_when_a_repo_fails(world, capsys):
    gn, api = world()
    api.set_page_urls(['https://github.com/owner/repo', 'https://github.com/ghost/missing'])
    assert gn.main([]) == 2
    err = capsys.readouterr().err
    assert 'ghost/missing' in err and 'GitHub HTTP 404' in err
    assert history(gn)[-1]['exit_code'] == 2


def test_keyboard_interrupt_during_processing(world, monkeypatch, capsys):
    gn, api = world()
    api.set_page_urls([f'https://github.com/owner/r{i}' for i in range(4)])
    cancel_flags = []
    real_shutdown = gn.ThreadPoolExecutor.shutdown

    def spy_shutdown(self, wait=True, *, cancel_futures=False):
        cancel_flags.append(cancel_futures)
        return real_shutdown(self, wait=wait, cancel_futures=cancel_futures)

    def interrupted_wait(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(gn.ThreadPoolExecutor, 'shutdown', spy_shutdown)
    monkeypatch.setattr(gn, 'wait', interrupted_wait)
    assert gn.main([]) == 130
    assert True in cancel_flags
    last = history(gn)[-1]
    assert last['interrupted'] is True and last['exit_code'] == 130
    assert gn.GITHUB_CACHE_DIRTY is False
    assert api.count('POST', r'/v1/pages$') <= 1
    assert 'Interruption' in capsys.readouterr().err


def test_keyboard_interrupt_before_processing(world, monkeypatch):
    gn, api = world()

    def boom():
        raise KeyboardInterrupt
    monkeypatch.setattr(gn, 'validate_all_tokens', boom)
    assert gn.main([]) == 130


def _subprocess_env(tmp_path, **extra):
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONUTF8', 'PYTHONIOENCODING')}
    env.update(GITNOTATE_NO_DOTENV='1', GITNOTATE_DATA_DIR=str(tmp_path), **extra)
    return env


def test_script_exit_code_via_sys_exit(tmp_path):
    script = str(ROOT / 'gitnotate.py')
    r = subprocess.run([sys.executable, script], env=_subprocess_env(tmp_path, PYTHONIOENCODING='utf-8'),
                       capture_output=True, timeout=60)
    assert r.returncode == 1
    assert 'PARENT_PAGE_ID' in r.stderr.decode('utf-8')
    r = subprocess.run([sys.executable, script, '--version'], env=_subprocess_env(tmp_path),
                       capture_output=True, timeout=60)
    assert r.returncode == 0 and b'7.3.0' in r.stdout

# =============================================================================
# 5. JOURNALISATION
# =============================================================================
def test_log_levels_and_errors_on_stderr(load_gn, capsys):
    gn = load_gn(LOG_LEVEL='QUIET')
    assert gn.LOG_LEVEL == 'quiet'
    gn.log('message normal')
    gn.log('détail', 'verbose')
    gn.log('❌ grave', 'error')
    cap = capsys.readouterr()
    assert cap.out == '' and '❌ grave' in cap.err
    gn = load_gn(LOG_LEVEL='Verbose')
    gn.log('détail', 'verbose')
    assert 'détail' in capsys.readouterr().out


def test_unknown_log_level_falls_back_to_normal(load_gn):
    gn = load_gn(LOG_LEVEL='debug')
    assert gn.LOG_LEVEL == 'normal' and gn.CONFIG_WARNINGS


def test_quiet_run_prints_only_errors(world, capsys):
    gn, api = world(LOG_LEVEL='quiet')
    api.set_page_urls(['https://github.com/owner/repo', 'https://github.com/ghost/missing'])
    assert gn.main([]) == 2
    cap = capsys.readouterr()
    assert cap.out == ''
    assert 'ghost/missing' in cap.err


def test_progress_bar_only_on_tty(world, capsys, monkeypatch):
    gn, api = world()
    assert gn.main([]) == 0                         # capsys : pas un terminal
    out = capsys.readouterr().out
    assert '█' not in out and '░' not in out and '\r' not in out
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: True)
    assert gn._progress_enabled() is True
    gn.LOG_LEVEL = 'quiet'
    assert gn._progress_enabled() is False


def test_configure_console_replaces_unencodable_chars(load_gn, monkeypatch):
    gn = load_gn()
    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding='cp1252')
    monkeypatch.setattr(sys, 'stdout', stream)
    gn._configure_console()
    print('🚀 ok')
    stream.flush()
    assert buf.getvalue() == b'? ok\n'


def test_redirected_cp1252_output_does_not_crash(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / 'gitnotate.py')],
                       env=_subprocess_env(tmp_path, PYTHONIOENCODING='cp1252'),
                       capture_output=True, timeout=60)
    err = r.stderr.decode('cp1252', errors='replace')
    assert r.returncode == 1
    assert 'Traceback' not in err and 'PARENT_PAGE_ID' in err

# =============================================================================
# 6. BASE NOTION — JAMAIS DE CRÉATION IMPLICITE
# =============================================================================
@pytest.mark.parametrize('status,body,expected', [
    (404, {'object': 'error', 'code': 'object_not_found',
           'message': 'Could not find database with ID: db-1.'},
     ['HTTP 404', 'Could not find database', 'Connexions']),
    (400, {'message': 'Databases with multiple data sources are not supported.'},
     ['HTTP 400', 'multi-sources']),
    (401, {'message': 'API token is invalid.'}, ['HTTP 401', 'NOTION_TOKEN']),
    (403, {'message': 'Insufficient permissions for this endpoint.'}, ['HTTP 403', 'capacités']),
])
def test_unreadable_database_never_creates(world, capsys, status, body, expected):
    gn, api = world()
    api.route('GET', r'/v1/databases/db-1$', lambda u, p: make_response(status, body))
    assert gn.main([]) == 1
    assert api.count('POST', r'/v1/databases$') == 0
    assert api.count('POST', r'/v1/pages') == 0
    err = capsys.readouterr().err
    for fragment in expected:
        assert fragment in err


def test_database_network_failure_never_creates(world, capsys):
    gn, api = world()
    api.route('GET', r'/v1/databases/db-1$', lambda u, p: requests.exceptions.ConnectionError('dns'))
    assert gn.main([]) == 1
    assert api.count('POST', r'/v1/databases$') == 0
    assert 'réseau' in capsys.readouterr().err


def test_empty_database_id_without_create_flag(world, capsys):
    gn, api = world(DATABASE_ID=None)
    assert gn.main([]) == 1
    assert api.count('POST', r'/v1/databases$') == 0
    assert 'CREATE_DATABASE=true' in capsys.readouterr().err


def test_create_database_refused_in_dry_run(world, capsys):
    gn, api = world(DATABASE_ID=None, CREATE_DATABASE='true', DRY_RUN='true')
    assert gn.main([]) == 1
    assert api.count('POST', r'/v1/databases$') == 0
    assert 'DRY_RUN' in capsys.readouterr().err


def test_create_database_once_then_stop(world, capsys):
    gn, api = world(DATABASE_ID=None, CREATE_DATABASE='true')
    assert gn.main([]) == 0
    assert api.count('POST', r'/v1/databases$') == 1
    assert api.count('POST', r'/query$') == 0 and api.count('POST', r'/v1/pages$') == 0
    assert api.count('GET', r'/blocks/') == 0                       # aucun import
    assert json.loads(gn.STATE_FILE.read_text(encoding='utf-8'))['database_id'] == 'new-db'
    assert 'Ajoutez DATABASE_ID=new-db dans .env puis mettez CREATE_DATABASE=false' in capsys.readouterr().out
    # Run suivant sans DATABASE_ID : refus, aucune deuxième base
    assert gn.main([]) == 1
    assert api.count('POST', r'/v1/databases$') == 1
    assert 'DATABASE_ID=new-db' in capsys.readouterr().err


def test_create_database_refused_when_state_unreadable(world, capsys):
    gn, api = world(DATABASE_ID=None, CREATE_DATABASE='true')
    gn.STATE_FILE.write_text('{illisible', encoding='utf-8')
    assert gn.main([]) == 1
    assert api.count('POST', r'/v1/databases$') == 0


def test_create_database_timeout_not_retried(world, capsys):
    gn, api = world(DATABASE_ID=None, CREATE_DATABASE='true')
    api.route('POST', r'/v1/databases$', lambda u, p: requests.exceptions.ReadTimeout('lent'))
    assert gn.main([]) == 1
    assert api.count('POST', r'/v1/databases$') == 1
    assert 'doublon' in capsys.readouterr().err
    assert not gn.STATE_FILE.exists()


def test_schema_types_validated(world, capsys):
    gn, api = world()
    types = dict(SCHEMA_TYPES)
    types['Type'] = 'select'
    del types['Stars']
    api.db = db_body(types)
    assert gn.main([]) == 1
    err = capsys.readouterr().err
    assert "'Type'" in err and 'multi_select' in err and "'Stars'" in err
    assert 'supprimez DATABASE_ID' not in err
    assert api.count('POST', r'/v1/pages') == 0


def test_justification_with_wrong_type_is_not_written(world):
    gn, api = world()
    api.db = db_body(justification='number')
    assert gn.check_database_schema(api.db) == []
    assert gn.main([]) == 0
    payloads = [p for m, u, p in api.calls if m == 'POST' and u.endswith('/v1/pages')]
    assert len(payloads) == 1 and 'Justification' not in payloads[0]['properties']

# =============================================================================
# 7. LECTURE COMPLÈTE OU ARRÊT
# =============================================================================
def test_partial_database_read_stops_without_creation(world, capsys):
    gn, api = world()

    def query(url, payload):
        if payload.get('start_cursor'):
            return make_response(502, {'message': 'Bad gateway'})
        return make_response(200, {'results': [existing_page('https://github.com/a/b')],
                                   'has_more': True, 'next_cursor': 'c2'})
    api.route('POST', r'/query$', query)
    assert gn.main([]) == 2
    assert api.count('POST', r'/v1/pages$') == 0
    assert api.count('GET', r'/blocks/') == 0
    assert 'Lecture de la base interrompue' in capsys.readouterr().err


def test_load_existing_urls_has_more_without_cursor(world):
    gn, api = world()
    api.route('POST', r'/query$', lambda u, p: make_response(
        200, {'results': [], 'has_more': True, 'next_cursor': None}))
    assert gn.load_existing_urls('db-1') is None


def test_load_existing_urls_returns_urls_and_keys(world):
    gn, api = world()
    api.query_pages = [[existing_page('https://github.com/Owner/Repo')],
                       [existing_page('https://github.com/x/y.git')]]
    urls, keys = gn.load_existing_urls('db-1')
    assert urls == {'https://github.com/Owner/Repo', 'https://github.com/x/y.git'}
    assert keys == {'owner/repo', 'x/y'}


def test_partial_block_read_stops_and_keeps_url_file(world, capsys):
    gn, api = world()
    gn.URLS_FILE.write_text('ancien contenu\n', encoding='utf-8')
    api.blocks['page-1'] = [[text_block('paragraph', [rt_text('https://github.com/owner/repo')], 'b1'),
                             text_block('toggle', [rt_text('dossier')], 'child-1', has_children=True)]]
    api.route('GET', r'/blocks/child-1/children', lambda u, p: make_response(500, {'message': 'oops'}))
    assert gn.main([]) == 2
    assert gn.URLS_FILE.read_text(encoding='utf-8') == 'ancien contenu\n'
    assert api.count('POST', r'/v1/pages') == 0
    assert 'incomplète' in capsys.readouterr().err


def test_block_cursor_failure_stops(world):
    gn, api = world()

    def children(url, params):
        if params.get('start_cursor'):
            return requests.exceptions.ConnectionError('coupure')
        return make_response(200, {'results': [], 'has_more': True, 'next_cursor': 'c2'})
    api.route('GET', r'/blocks/page-1/children', children)
    assert gn.main([]) == 2
    assert api.count('POST', r'/v1/pages') == 0


def test_block_has_more_without_cursor_is_partial(world):
    gn, api = world()
    api.route('GET', r'/blocks/page-1/children', lambda u, p: make_response(
        200, {'results': [text_block('paragraph', [rt_text('https://github.com/owner/repo')])],
              'has_more': True, 'next_cursor': None}))
    with pytest.raises(gn.PartialReadError):
        gn.get_all_blocks_recursive('page-1')
    assert gn.main([]) == 2
    assert api.count('POST', r'/v1/pages') == 0


def test_root_page_not_shared_message(world, capsys):
    gn, api = world()
    api.route('GET', r'/blocks/page-1/children',
              lambda u, p: make_response(404, {'message': 'Could not find block'}))
    assert gn.main([]) == 1                       # erreur de configuration (README : code 1)
    assert "page source introuvable ou non partagée avec l'intégration" in capsys.readouterr().err
    assert api.count('POST', r'/v1/pages') == 0

# =============================================================================
# 8. VALIDATION DES JETONS
# =============================================================================
def test_notion_token_network_error(world, capsys):
    gn, api = world()
    api.route('GET', r'/v1/users/me', lambda u, p: requests.exceptions.ConnectionError('dns'))
    assert gn.main([]) == 1
    assert 'Notion injoignable' in capsys.readouterr().err
    assert api.count('GET', r'/v1/databases') == 0


def test_notion_token_401(world, capsys):
    gn, api = world()
    api.route('GET', r'/v1/users/me', lambda u, p: make_response(401, {'message': 'API token is invalid.'}))
    assert gn.main([]) == 1
    cap = capsys.readouterr()
    assert 'NOTION_TOKEN invalide' in cap.err and 'HTTP 401' in cap.err
    assert 'ntn_test_token_1234' not in cap.out + cap.err


def test_notion_token_other_status(world, capsys):
    gn, api = world()
    api.route('GET', r'/v1/users/me', lambda u, p: make_response(503, {'message': 'Service unavailable'}))
    assert gn.main([]) == 1
    assert 'HTTP 503' in capsys.readouterr().err


def test_invalid_github_token_stops(world, capsys):
    gn, api = world(GITHUB_TOKEN='ghp_invalid_token_9999')
    api.route('GET', r'api\.github\.com/user$', lambda u, p: make_response(401, {'message': 'Bad credentials'}))
    assert gn.main([]) == 1
    cap = capsys.readouterr()
    assert 'GITHUB_TOKEN invalide ou expiré' in cap.err
    assert 'ghp_invalid_token_9999' not in cap.out + cap.err
    assert api.count('GET', r'/repos/') == 0


def test_github_unreachable_stops(world, capsys):
    gn, api = world(GITHUB_TOKEN='ghp_valid_token_1234')
    api.route('GET', r'api\.github\.com/user$', lambda u, p: requests.exceptions.ConnectTimeout('lent'))
    assert gn.main([]) == 1
    assert 'GitHub injoignable' in capsys.readouterr().err


def test_no_github_token_warns_and_continues(world, capsys):
    gn, api = world()
    assert gn.main([]) == 0
    out = capsys.readouterr().out
    assert 'GITHUB_TOKEN absent' in out and 'GitHub auth:      ⚠️' in out
    assert api.count('GET', r'api\.github\.com/user$') == 0


def test_github_auth_line_reflects_validation(world, capsys):
    gn, api = world(GITHUB_TOKEN='ghp_valid_token_1234')
    assert gn.main([]) == 0
    assert 'GitHub auth:      ✅ jeton valide (me)' in capsys.readouterr().out

# =============================================================================
# 9. ROBUSTESSE DES DONNÉES
# =============================================================================
def test_lexical_score_handles_nulls(load_gn):
    gn = load_gn()
    assert gn.calculate_relevance_score(dict(NULL_REPO)) == 0
    assert gn.calculate_relevance_score({}) == 0


def test_lexical_language_compared_by_equality(load_gn):
    gn = load_gn()
    gn.USER_PROFILE = {'languages': ['Python', 'JavaScript']}
    assert gn.calculate_relevance_score({'language': 'Py'}) == 0        # 'py' ⊂ 'python' : plus compté
    assert gn.calculate_relevance_score({'language': 'Java'}) == 0      # 'java' ⊂ 'javascript' : plus compté
    assert gn.calculate_relevance_score({'language': 'JavaScript'}) == 3


@pytest.mark.parametrize('path', ['sans_fournisseur', 'fr_sans_scoring', 'score_invalide',
                                  'scoring_desactive', 'tous_echouent'])
def test_five_lexical_paths_with_null_fields(load_gn, monkeypatch, path):
    env = {'LLM_SCORING_ENABLED': 'false'} if path in ('fr_sans_scoring', 'scoring_desactive') else {}
    gn = load_gn(**env)
    gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK = (None, None) if path == 'sans_fournisseur' \
        else ('mistral', None)
    answers = {
        'score_invalide': json.dumps(dict(GOOD_LLM, interet=42)),
        'scoring_desactive': json.dumps({'description_fr': 'Outil', 'use_cases_fr': '• a'}),
        'tous_echouent': None,
    }
    monkeypatch.setattr(gn, '_call_translation_api', lambda p, m, t: answers.get(path))
    description = ("Les outils pour les élèves avec des cours dans une école qui sont libres"
                   if path == 'fr_sans_scoring' else 'A tool')
    analysis = gn.analyze_repo_for_usage(dict(NULL_REPO))
    result = gn.translate_and_score(description, analysis['use_cases_text'], dict(NULL_REPO), 'demo')
    assert result['scoring_method'] == 'lexical'
    assert isinstance(result['score'], int) and 0 <= result['score'] <= 10
    assert result['translated'] is (path in ('fr_sans_scoring', 'score_invalide', 'scoring_desactive'))
    props = gn.build_page_properties(dict(NULL_REPO), '', analysis, result, True)
    assert props['Dernière MAJ'] == {'date': None} and props['URL'] == {'url': None}


def test_null_fields_through_full_run(world):
    gn, api = world()
    api.repos['owner/repo'] = repo_data('owner', 'repo', language=None, topics=None,
                                        description=None, updated_at=None, stargazers_count=None)
    gn_llm_down = make_response(503, {'message': 'down'})
    api.route('POST', r'api\.mistral\.ai', lambda u, p: gn_llm_down)
    assert gn.main([]) == 0
    assert api.count('POST', r'/v1/pages$') == 1


def test_private_repo_is_ignored_without_llm_call(world, capsys):
    gn, api = world()
    api.repos['owner/repo']['private'] = True
    assert gn.main([]) == 0
    assert api.count('POST', r'api\.mistral\.ai') == 1        # seulement le test de démarrage
    assert api.count('POST', r'/v1/pages$') == 0
    assert 'privé' in capsys.readouterr().out
    assert 'owner/repo' not in gn.GITHUB_CACHE

# =============================================================================
# 10. RÉPONSES LLM ROBUSTES
# =============================================================================
THINKING_THEN_TEXT = [
    {'type': 'thinking', 'thinking': [{'type': 'text', 'text': '{"description_fr": "piège"}'}]},
    {'type': 'text', 'text': GOOD_JSON},
]

LLM_SCENARIOS = [
    ('S1 content None + length', make_response(200, chat(None, finish='length')), 'mistral'),
    ('S2 vide + length', make_response(200, chat('', finish='length')), 'mistral'),
    ('JSON complet mais length', make_response(200, chat(GOOD_JSON, finish='length')), 'mistral'),
    ('S3 texte non JSON', make_response(200, chat('safe')), 'mistral'),
    ('S4 blocs thinking + text', make_response(200, chat(THINKING_THEN_TEXT)), 'openrouter'),
    ('S5 bloc ```json', make_response(200, chat('```json\n' + GOOD_JSON + '\n```')), 'openrouter'),
    ('S6 200 avec error', make_response(200, {'error': {'code': 502, 'message': 'Provider error'}}), 'mistral'),
    ('S7 429 quota', make_response(429, {'error': {'code': 429}}, {'X-RateLimit-Remaining': '0'}), 'mistral'),
    ('S8 score chaîne', make_response(200, chat(json.dumps(dict(GOOD_LLM, potentiel_futur='2')))), 'openrouter'),
    ('corps non JSON', make_response(200, text='<html>oops</html>'), 'mistral'),
    ('texte autour + accolades', make_response(200, chat('Voici {le résultat} :\n' + GOOD_JSON + '\nFin {ok}')),
     'openrouter'),
    ('saut de ligne littéral', make_response(200, chat(
        json.dumps(GOOD_LLM, ensure_ascii=False).replace('Un outil en', 'Un outil\nen'))), 'openrouter'),
    ('blocs reasoning OpenAI', make_response(200, chat([{'type': 'reasoning', 'text': 'réflexion'},
                                                        {'type': 'text', 'text': GOOD_JSON}])), 'openrouter'),
    ('score booléen', make_response(200, chat(json.dumps(dict(GOOD_LLM, interet=True)))), 'mistral'),
    ('score hors bornes', make_response(200, chat(json.dumps(dict(GOOD_LLM, interet=3)))), 'mistral'),
    ('content objet', make_response(200, chat({'foo': 1})), 'mistral'),
    ('choices vide', make_response(200, {'choices': []}), 'mistral'),
    ('description vide', make_response(200, chat(json.dumps(dict(GOOD_LLM, description_fr='')))), 'mistral'),
    ('use_cases nombre', make_response(200, chat(json.dumps(dict(GOOD_LLM, cas_usage=3)))), 'mistral'),
    ('exception réseau', requests.exceptions.ConnectionError('coupure'), 'mistral'),
]


@pytest.fixture
def llm(load_gn, monkeypatch):
    def _make(openrouter_handler, mistral_handler=None, **env):
        gn = load_gn(OPENROUTER_API_KEY='sk-or-test-key', MISTRAL_API_KEY='mistral-test-key', **env)
        api = FakeAPI()
        api.route('POST', r'openrouter\.ai', openrouter_handler)
        if mistral_handler:
            api.route('POST', r'api\.mistral\.ai', mistral_handler)
        monkeypatch.setattr(gn, 'get_session', lambda: api)
        monkeypatch.setattr(gn.time, 'sleep', lambda s: api.sleeps.append(s))
        gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK = 'openrouter', 'mistral'
        return gn, api
    return _make


@pytest.mark.parametrize('label,response,expected_provider', LLM_SCENARIOS, ids=[s[0] for s in LLM_SCENARIOS])
def test_llm_cascade_scenarios(llm, label, response, expected_provider):
    gn, api = llm(lambda u, p: response)
    result = gn.translate_and_score('A tool', '• x', dict(NULL_REPO, language='Python'), 'demo')
    assert result['provider'] == expected_provider
    assert result['translated'] is True and result['scoring_method'] == 'llm'
    assert result['description_fr'].startswith('Un outil')
    assert result['score'] == 7
    assert (gn.stats.translation_success, gn.stats.translation_failed) == (1, 0)
    assert (gn.stats.llm_score_success, gn.stats.llm_score_fallback) == (1, 0)


def test_s9_truncated_json_without_fallback(llm):
    gn, api = llm(lambda u, p: make_response(200, chat('{"description_fr": "Outil', finish='length')))
    gn.TRANSLATION_FALLBACK = None
    result = gn.translate_and_score('A tool', '• x', dict(NULL_REPO), 'demo')
    assert result['translated'] is False and result['scoring_method'] == 'lexical'
    assert (gn.stats.translation_success, gn.stats.translation_failed) == (0, 1)


def test_partial_translation_kept_when_all_scores_invalid(llm):
    bad = make_response(200, chat(json.dumps(dict(GOOD_LLM, interet='beaucoup'))))
    gn, api = llm(lambda u, p: bad, lambda u, p: make_response(200, chat('pas de json')))
    result = gn.translate_and_score('A tool', '• x', dict(NULL_REPO), 'demo')
    assert result['translated'] is True and result['provider'] == 'openrouter'
    assert result['scoring_method'] == 'lexical'
    assert (gn.stats.translation_success, gn.stats.translation_failed) == (1, 0)
    assert (gn.stats.llm_score_success, gn.stats.llm_score_fallback) == (0, 1)


def test_call_translation_api_never_raises(llm):
    def explode(url, payload):
        raise ValueError('inattendu')
    gn, api = llm(explode)
    assert gn._call_translation_api('openrouter', [{'role': 'user', 'content': 'x'}]) is None


def test_normalize_llm_content(load_gn):
    gn = load_gn()
    assert gn._normalize_llm_content('  abc ') == 'abc'
    assert gn._normalize_llm_content([{'type': 'text', 'text': 'a'}, {'type': 'thinking', 'text': 'x'},
                                      {'type': 'text', 'text': 'b'}, 'brut']) == 'ab'
    assert gn._normalize_llm_content(None) == ''
    assert gn._normalize_llm_content([]) == ''


def test_validate_llm_payload_rules(load_gn):
    """v7.3 : mêmes règles sur la réponse v2 (jugements bornés au lieu du score 0-10, justification
    tronquée à 400 caractères ; le score est calculé ensuite par le code)."""
    gn = load_gn()
    validate = gn._validate_llm_payload
    ok, _ = validate(dict(GOOD_LLM, description_fr=' Outil ', cas_usage=['a', '• b', None, ''],
                          potentiel_futur='2.0', justification='x' * 900), True)
    assert ok['description_fr'] == 'Outil' and ok['use_cases_fr'] == '• a\n• b'
    assert ok['judgements']['potentiel_futur'] == 2 and len(ok['reasoning']) == 400
    assert validate(dict(GOOD_LLM, description_fr=''), True)[0] is None
    assert validate(dict(GOOD_LLM, cas_usage=3), True)[0] is None
    assert validate({'description_fr': 'x'}, True)[0] is None
    for bad in (True, -1, 2.6, 'sept', float('nan'), None, [2], 4):
        assert validate(dict(GOOD_LLM, potentiel_futur=bad), True)[0]['judgements'] is None
    assert gn._coerce_scale('2', 3) == 2 and gn._coerce_scale(3, 3) == 3 and gn._coerce_scale(0.0, 2) == 0
    assert validate(dict(GOOD_LLM, justification=3), True)[0]['judgements'] is None


def test_parse_llm_json_tolerant(load_gn):
    gn = load_gn()
    assert gn._parse_llm_json('```json\n{"description_fr": "a"}\n```') == {'description_fr': 'a'}
    assert gn._parse_llm_json('{} puis {"description_fr": "b"} fin') == {'description_fr': 'b'}
    assert gn._parse_llm_json('{"description_fr": "l1\nl2"}') == {'description_fr': 'l1\nl2'}
    assert gn._parse_llm_json('rien ici') is None
    assert gn._parse_llm_json(None) is None


def test_translation_counters_never_double_count(load_gn, monkeypatch):
    gn = load_gn()
    gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK = 'openrouter', 'mistral'
    plans = [
        {'openrouter': GOOD_JSON},
        {'openrouter': 'pas de json', 'mistral': GOOD_JSON},
        {'openrouter': json.dumps(dict(GOOD_LLM, interet=99)), 'mistral': None},
        {'openrouter': None, 'mistral': None},
        {'openrouter': json.dumps(dict(GOOD_LLM, justification={'x': 1})), 'mistral': GOOD_JSON},
    ]
    for plan in plans:
        monkeypatch.setattr(gn, '_call_translation_api', lambda p, m, t, plan=plan: plan.get(p))
        gn.translate_and_score('A tool', '• x', dict(NULL_REPO), 'demo')
    assert gn.stats.translation_success + gn.stats.translation_failed == len(plans)
    assert gn.stats.llm_score_success + gn.stats.llm_score_fallback == len(plans)
    assert (gn.stats.translation_success, gn.stats.llm_score_success) == (4, 3)

# =============================================================================
# 11. ERREURS NOTION À LA CRÉATION DE PAGE
# =============================================================================
def test_notion_page_error_shows_http_code_and_message(world, capsys):
    gn, api = world()
    api.route('POST', r'/v1/pages$', lambda u, p: make_response(
        400, {'object': 'error', 'code': 'validation_error', 'message': 'Type is expected to be multi_select.'}))
    assert gn.main([]) == 2
    err = capsys.readouterr().err
    assert 'Notion HTTP 400 — Type is expected to be multi_select.' in err
    assert 'timeout' not in err.lower()
    assert api.count('POST', r'/v1/pages$') == 1
    assert history(gn)[-1]['errors_by_reason'] == {'Notion HTTP 400': 1}

# =============================================================================
# 12. ÉCRITURES NON IDEMPOTENTES
# =============================================================================
@pytest.mark.parametrize('failure', [
    requests.exceptions.ReadTimeout('lent'),
    requests.exceptions.ConnectionError('reset'),
    make_response(502, {'message': 'Bad gateway'}),
])
def test_non_idempotent_post_not_retried(http, failure):
    gn, api = http()
    api.route('POST', r'/v1/pages$', lambda u, p: failure)
    gn.http_request_with_retry('POST', 'https://api.notion.com/v1/pages', {}, json_data={}, idempotent=False)
    assert api.count('POST', r'/v1/pages$') == 1
    assert api.sleeps == []


def test_non_idempotent_post_retries_only_429(http):
    gn, api = http()
    api.route('POST', r'/v1/pages$', sequence(make_response(429, {}, {'Retry-After': '1'}),
                                              make_response(200, {'id': 'p'})))
    r = gn.http_request_with_retry('POST', 'https://api.notion.com/v1/pages', {}, json_data={}, idempotent=False)
    assert r.status_code == 200 and api.count('POST', r'/v1/pages$') == 2 and api.sleeps == [1]


def test_idempotent_requests_are_retried(http):
    gn, api = http()
    api.route('GET', r'/v1/users/me', lambda u, p: requests.exceptions.ReadTimeout('lent'))
    assert gn.http_request_with_retry('GET', 'https://api.notion.com/v1/users/me', {}) is None
    assert api.count('GET', r'/v1/users/me') == gn.MAX_RETRIES == 3
    assert gn.last_http_error() == 'timeout'
    api.route('POST', r'/query$', sequence(make_response(500, {}), make_response(200, {'results': []})))
    r = gn.http_request_with_retry('POST', 'https://api.notion.com/v1/databases/x/query', {}, json_data={})
    assert r.status_code == 200


def test_page_creation_timeout_message(world, capsys):
    gn, api = world()
    api.route('POST', r'/v1/pages$', lambda u, p: requests.exceptions.ReadTimeout('lent'))
    assert gn.main([]) == 2
    assert api.count('POST', r'/v1/pages$') == 1
    err = capsys.readouterr().err
    assert 'non réessayée pour éviter un doublon' in err and 'prochain run' in err

# =============================================================================
# 13. ATTENTES PLAFONNÉES
# =============================================================================
def test_retry_after_above_cap_fails_fast(http, capsys):
    gn, api = http(MAX_WAIT_SECONDS='30')
    api.route('GET', r'/repos/a/b$', lambda u, p: make_response(429, {}, {'Retry-After': '3600'}))
    r = gn.http_request_with_retry('GET', 'https://api.github.com/repos/a/b', {})
    assert r.status_code == 429 and api.sleeps == [] and api.count('GET', r'/repos/a/b$') == 1
    assert 'plafond' in capsys.readouterr().out


def test_retry_after_http_date_announced_at_normal_level(http, capsys):
    gn, api = http()
    when = email.utils.format_datetime(datetime.now(timezone.utc) + timedelta(seconds=40), usegmt=True)
    api.route('GET', r'/v1/users/me', sequence(make_response(429, {}, {'Retry-After': when}),
                                               make_response(200, {})))
    r = gn.http_request_with_retry('GET', 'https://api.notion.com/v1/users/me', {})
    assert r.status_code == 200
    assert len(api.sleeps) == 1 and 35 <= api.sleeps[0] <= 41
    assert '⏳ Rate limit (429) — attente' in capsys.readouterr().out


def test_parse_retry_after(load_gn):
    gn = load_gn()
    assert gn._parse_retry_after('5') == 5
    assert gn._parse_retry_after(' 2.5 ') == 3
    assert gn._parse_retry_after('') is None and gn._parse_retry_after(None) is None
    assert gn._parse_retry_after('n importe quoi') is None
    assert gn._parse_retry_after('Wed, 21 Oct 2015 07:28:00 GMT') == 0


def test_github_secondary_rate_limit_403_treated_as_429(http):
    body = '{"message": "You have exceeded a secondary rate limit. Please wait a few minutes."}'
    gn, api = http()
    api.route('GET', r'/repos/a/b$', sequence(make_response(403, text=body), make_response(200, {})))
    assert gn.http_request_with_retry('GET', 'https://api.github.com/repos/a/b', {}).status_code == 200
    assert api.sleeps == [60]
    gn, api = http(MAX_WAIT_SECONDS='30')
    api.route('GET', r'/repos/a/b$', lambda u, p: make_response(403, text=body))
    assert gn.http_request_with_retry('GET', 'https://api.github.com/repos/a/b', {}).status_code == 403
    assert api.sleeps == []


def test_x_ratelimit_reset_is_capped(http):
    gn, api = http()
    far = {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(int(time.time()) + 3600)}
    api.route('GET', r'/repos/a/b$', lambda u, p: make_response(403, {}, far))
    assert gn.http_request_with_retry('GET', 'https://api.github.com/repos/a/b', {}).status_code == 403
    assert api.sleeps == []
    near = {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(int(time.time()) + 10)}
    api.route('GET', r'/repos/c/d$', sequence(make_response(403, {}, near), make_response(200, {})))
    assert gn.http_request_with_retry('GET', 'https://api.github.com/repos/c/d', {}).status_code == 200
    assert len(api.sleeps) == 1 and 8 <= api.sleeps[0] <= 11

# =============================================================================
# 14. CONCURRENCE — UNE SEULE FICHE PAR DÉPÔT
# =============================================================================
def test_same_repo_via_two_urls_creates_one_page(world):
    gn, api = world()
    api.repos['oldowner/tool'] = repo_data('neworg', 'tool')   # dépôt renommé : même html_url
    api.repos['neworg/tool'] = repo_data('neworg', 'tool')
    in_post, release = threading.Event(), threading.Event()

    def pages(url, payload):
        in_post.set()
        release.wait(5)
        return make_response(200, {'id': 'p'})
    api.route('POST', r'/v1/pages$', pages)
    gn.TRANSLATION_PROVIDER = gn.TRANSLATION_FALLBACK = None
    existing, keys, in_progress, results = set(), set(), set(), {}

    def first():
        results['a'] = gn.process_single_repo('https://github.com/oldowner/tool', 'db-1', existing,
                                              True, 1, 2, keys, in_progress)
    worker = threading.Thread(target=first)
    worker.start()
    assert in_post.wait(5)
    results['b'] = gn.process_single_repo('https://github.com/neworg/tool', 'db-1', existing,
                                          True, 2, 2, keys, in_progress)
    release.set()
    worker.join(5)
    assert api.count('POST', r'/v1/pages$') == 1
    assert results['a']['success'] and results['b']['skipped']
    assert in_progress == set() and 'https://github.com/neworg/tool' in existing and 'neworg/tool' in keys


def test_reservation_released_when_creation_fails(world):
    """Refus CERTAIN de Notion (400) : la réservation est rendue, le dépôt peut être recréé."""
    gn, api = world()
    api.route('POST', r'/v1/pages$', lambda u, p: make_response(400, {'message': 'validation'}))
    existing, keys, in_progress, uncertain = set(), set(), set(), set()
    r = gn.process_single_repo('https://github.com/owner/repo', 'db-1', existing, True, 1, 1, keys,
                               in_progress, uncertain)
    assert r['error'] and in_progress == set() and existing == set() and uncertain == set()
    api.routes.pop(0)
    r = gn.process_single_repo('https://github.com/owner/repo', 'db-1', existing, True, 1, 1, keys,
                               in_progress, uncertain)
    assert r['success'] and existing == {'https://github.com/owner/repo'}


@pytest.mark.parametrize('failure', [make_response(500, {'message': 'oops'}),
                                     requests.exceptions.ReadTimeout('lent')])
def test_uncertain_creation_keeps_key_reserved_for_the_run(world, failure):
    """Issue incertaine (5xx, pas de réponse) : la clé reste bloquée jusqu'à la fin du run."""
    gn, api = world()
    gn.TRANSLATION_PROVIDER = 'mistral'                 # réponse LLM valide (FakeAPI)
    api.route('POST', r'/v1/pages$', lambda u, p: failure)
    existing, keys, in_progress, uncertain = set(), set(), set(), set()
    r = gn.process_single_repo('https://github.com/owner/repo', 'db-1', existing, True, 1, 1, keys,
                               in_progress, uncertain)
    assert r['error'] and in_progress == set() and existing == set() and uncertain == {'owner/repo'}
    api.routes.pop(0)
    r = gn.process_single_repo('https://github.com/owner/repo', 'db-1', existing, True, 1, 1, keys,
                               in_progress, uncertain)
    assert r['skipped'] and not r.get('created')
    assert api.count('POST', r'/v1/pages$') == 1


def test_main_two_urls_same_repo_one_page(world):
    gn, api = world(MAX_WORKERS='2')
    api.set_page_urls(['https://github.com/oldowner/tool', 'https://github.com/neworg/tool'])
    api.repos['oldowner/tool'] = repo_data('neworg', 'tool')
    assert gn.main([]) == 0
    assert api.count('POST', r'/v1/pages$') == 1


def test_existing_url_matched_case_insensitively(world, capsys):
    gn, api = world()
    api.query_pages = [[existing_page('https://github.com/Owner/Repo')]]
    assert gn.main([]) == 0
    assert api.count('POST', r'/v1/pages$') == 0
    assert 'Déjà présents:   1' in capsys.readouterr().out

# =============================================================================
# 15. EXTRACTION DES URL
# =============================================================================
def test_parse_and_normalize_github_urls(load_gn):
    gn = load_gn()
    assert gn.normalize_github_url('https://github.com/Foo/Bar.git/') == 'foo/bar'
    assert gn.normalize_github_url('https://github.com/foo/bargit') == 'foo/bargit'   # regex '\.git$'
    assert gn.extract_github_info('https://www.github.com/a/b/tree/main?tab=readme#x') == {'owner': 'a', 'repo': 'b'}
    for url in ('https://gist.github.com/a/b', 'https://github.com.evil.com/a/b', 'https://notgithub.com/a/b',
                'ftp://github.com/a/b', 'https://raw.githubusercontent.com/a/b/main/x', ''):
        assert gn.parse_github_url(url) == (None, 'hors_github')
    for url in ('https://github.com/topics/ai', 'https://github.com/orgs/x/repositories',
                'https://github.com/someone', 'https://github.com/', 'https://github.com/sponsors/x',
                'https://github.com/Marketplace/actions', 'https://github.com/a/.git'):
        assert gn.parse_github_url(url) == (None, 'non_depot')


def test_extract_urls_from_all_text_blocks(load_gn):
    gn = load_gn()
    blocks = [
        text_block('paragraph', [rt_text('Voir (https://github.com/a/p).')]),
        text_block('to_do', [rt_text('https://github.com/a/todo,')]),
        text_block('toggle', [rt_text('lien', 'https://github.com/a/toggle')]),
        text_block('quote', [rt_text('« https://github.com/a/quote »')]),
        text_block('callout', [rt_mention('https://github.com/a/callout')]),
        text_block('heading_3', [rt_text('https://github.com/a/h3;')]),
        text_block('code', [rt_text('https://github.com/a/code')]),
        {'type': 'table_row', 'id': 't', 'has_children': False,
         'table_row': {'cells': [[rt_text('https://github.com/a/cell1')],
                                 [rt_text('x', 'https://github.com/a/cell2')]]}},
        {'type': 'bookmark', 'id': 'bm', 'bookmark': {'url': 'https://github.com/a/bookmark', 'caption': []}},
        {'type': 'bookmark', 'id': 'bm2', 'bookmark': {'url': 'https://gist.github.com/a/b'}},
        text_block('paragraph', [rt_text('https://github.com/a/same', 'https://github.com/a/same')]),
        text_block('paragraph', [rt_text('https://notgithub.com/x/y')]),
    ]
    assert gn.extract_urls_from_blocks(blocks) == [
        'https://github.com/a/p', 'https://github.com/a/todo', 'https://github.com/a/toggle',
        'https://github.com/a/quote', 'https://github.com/a/callout', 'https://github.com/a/h3',
        'https://github.com/a/cell1', 'https://github.com/a/cell2', 'https://github.com/a/bookmark',
        'https://github.com/a/same',
    ]


def test_non_repo_links_are_ignored_not_errors(world, capsys):
    gn, api = world(LOG_LEVEL='verbose')
    api.set_page_urls(['https://github.com/owner/repo', 'https://github.com/topics/ai',
                       'https://github.com/someone'])
    assert gn.main([]) == 0
    out = capsys.readouterr().out
    assert 'Ignorées:        2' in out
    assert 'ignorée (non-dépôt) : https://github.com/topics/ai' in out
    last = history(gn)[-1]
    assert last['ignored_count'] == 2 and last['error_count'] == 0
    assert api.count('GET', r'/repos/topics') == 0

# =============================================================================
# 16. DRY_RUN ET MAX_REPOS
# =============================================================================
def test_dry_run_builds_payload_without_writing(world, monkeypatch, capsys):
    gn, api = world(DRY_RUN='true')
    built = []
    real_build = gn.build_page_properties
    monkeypatch.setattr(gn, 'build_page_properties', lambda *a, **k: built.append(1) or real_build(*a, **k))
    assert gn.main([]) == 0
    assert built == [1]
    assert api.count('POST', r'/v1/pages$') == 0 and api.count('POST', r'/v1/databases$') == 0
    out = capsys.readouterr().out
    assert 'Simulées:' in out and 'Créations:' not in out
    assert history(gn)[-1]['dry_run'] is True


def test_dry_run_reveals_payload_errors(world, monkeypatch):
    gn, api = world(DRY_RUN='true')

    def broken(*args, **kwargs):
        raise ValueError('payload invalide')
    monkeypatch.setattr(gn, 'build_page_properties', broken)
    assert gn.main([]) == 2


def test_max_repos_limits_processing(world):
    gn, api = world(MAX_REPOS='1')
    api.set_page_urls([f'https://github.com/owner/r{i}' for i in range(3)])
    assert gn.main([]) == 0
    assert api.count('POST', r'/v1/pages$') == 1
    assert len(gn.URLS_FILE.read_text(encoding='utf-8').split()) == 3

# =============================================================================
# 17. LIGNE DE COMMANDE
# =============================================================================
def test_cli_overrides_environment(world, capsys):
    gn, api = world(DRY_RUN='false', MAX_REPOS='0', LOG_LEVEL='verbose')
    api.set_page_urls(['https://github.com/owner/r1', 'https://github.com/owner/r2'])
    assert gn.main(['--dry-run', '--max-repos', '1', '--log-level', 'QUIET']) == 0
    assert gn.DRY_RUN is True and gn.MAX_REPOS == 1 and gn.LOG_LEVEL == 'quiet'
    assert api.count('POST', r'/v1/pages$') == 0
    assert api.count('GET', r'/repos/owner/r2$') == 0
    assert capsys.readouterr().out == ''


def test_cli_max_repos_overrides_invalid_env(world):
    gn, api = world(MAX_REPOS='abc')
    assert gn.main(['--max-repos', '1']) == 0


@pytest.mark.parametrize('argv', [['--inconnu'], ['--max-repos', '-1'], ['--log-level', 'debug']])
def test_cli_invalid_arguments(load_gn, argv, capsys):
    gn = load_gn()
    with pytest.raises(SystemExit) as exc:
        gn.main(argv)
    assert exc.value.code == 1                    # configuration (épilogue de --help), pas « erreurs »
    err = capsys.readouterr().err
    assert 'usage: gitnotate' in err and '❌' in err

# =============================================================================
# 18. CACHE GITHUB ET STATISTIQUES
# =============================================================================
def test_cache_validity_per_entry(world):
    gn, api = world()
    now = time.time()
    fresh = dict(repo_data('owner', 'repo'), cached_at=now - 60, stars=42, readme='', cache_format=gn.CACHE_FORMAT)
    gn.CACHE_FILE.write_text(json.dumps({
        'owner/repo': fresh,
        'old/one': dict(fresh, cached_at=now - 48 * 3600),
        'legacy/x': {k: v for k, v in fresh.items() if k != 'cached_at'},
    }), encoding='utf-8')
    gn.init_github_cache()
    assert set(gn.GITHUB_CACHE) == {'owner/repo'}
    info, error = gn.fetch_github_repo('owner', 'repo')
    assert info['name'] == 'repo' and error == '' and api.count('GET', r'api\.github\.com') == 0
    api.repos['legacy/x'] = repo_data('legacy', 'x')
    info, error = gn.fetch_github_repo('legacy', 'x')
    assert api.count('GET', r'/repos/legacy/x$') == 1
    assert isinstance(gn.GITHUB_CACHE['legacy/x']['cached_at'], float) and gn.GITHUB_CACHE_DIRTY


def test_cache_save_is_atomic_and_resets_dirty(load_gn, monkeypatch):
    gn = load_gn()
    gn.GITHUB_CACHE = {'a/b': {'cached_at': time.time(), 'name': 'b'}}
    gn.GITHUB_CACHE_DIRTY = True
    replaced = []
    real_replace = os.replace

    def spy_replace(src, dst):
        replaced.append((Path(src).name, Path(dst).name))
        return real_replace(src, dst)
    monkeypatch.setattr(gn.os, 'replace', spy_replace)
    gn.flush_github_cache()
    assert replaced == [('.gitnotate_cache.json.tmp', '.gitnotate_cache.json')]
    assert gn.GITHUB_CACHE_DIRTY is False
    assert json.loads(gn.CACHE_FILE.read_text(encoding='utf-8'))['a/b']['name'] == 'b'
    assert not gn.CACHE_FILE.with_name('.gitnotate_cache.json.tmp').exists()


def test_cache_write_failure_keeps_dirty_flag(load_gn, monkeypatch):
    gn = load_gn()
    gn.GITHUB_CACHE, gn.GITHUB_CACHE_DIRTY = {'a/b': {}}, True

    def fail(*args, **kwargs):
        raise OSError('disque plein')
    monkeypatch.setattr(gn, '_atomic_write_json', fail)
    gn.flush_github_cache()
    assert gn.GITHUB_CACHE_DIRTY is True


def test_unreadable_stats_file_is_backed_up(load_gn):
    gn = load_gn()
    run = {'duration': 1, 'success': 1, 'errors': 0, 'skipped': 0}
    gn.STATS_FILE.write_text('{pas du json', encoding='utf-8')
    gn.save_execution_stats(run)
    backup = gn.STATS_FILE.with_name('gitnotate_stats.json.bak')
    assert backup.read_text(encoding='utf-8') == '{pas du json'
    assert len(history(gn)) == 1
    gn.STATS_FILE.write_text('{"pas": "une liste"}', encoding='utf-8')
    gn.save_execution_stats(run)
    assert backup.read_text(encoding='utf-8') == '{pas du json'           # première sauvegarde intacte
    assert len(list(gn.STATS_FILE.parent.glob('gitnotate_stats.json.*.bak'))) == 1
    assert len(history(gn)) == 1

# =============================================================================
# 19. BILAN DE FIN
# =============================================================================
def test_summary_lists_errors_with_reasons_and_truncates(world, capsys):
    gn, api = world()
    api.set_page_urls(['https://github.com/owner/repo'] + [f'https://github.com/ghost/r{i}' for i in range(35)])
    assert gn.main([]) == 2
    cap = capsys.readouterr()
    assert 'URLs en erreur (35)' in cap.err
    assert 'https://github.com/ghost/r0 — GitHub HTTP 404' in cap.err
    assert '… et 5 autres' in cap.err
    for line in ('Créations:       1', 'Déjà présents:   0', 'Ignorées:        0',
                 'Filtrées:        0', 'Erreurs:         35'):
        assert line in cap.out
    assert history(gn)[-1]['errors_by_reason'] == {'GitHub HTTP 404': 35}


def test_filtered_repos_counted(world, capsys):
    gn, api = world(MIN_UPDATE_DAYS='30')
    api.repos['owner/repo']['updated_at'] = '2020-01-01T00:00:00Z'
    assert gn.main([]) == 0
    assert 'Filtrées:        1' in capsys.readouterr().out
    assert history(gn)[-1]['filtered_count'] == 1

# =============================================================================
# 20. DÉPENDANCES
# =============================================================================
def test_requirements_bounds():
    content = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    assert 'requests>=2.33,<3' in content
    assert 'python-dotenv>=1.2.2,<2' in content
