"""Tests de non-régression des constats de la revue contradictoire (après le lot 2).

Un test (ou un groupe) par constat corrigé, repéré par son identifiant (S1, S3, R1, C1, SEC-1...).
Réseau entièrement simulé (FakeAPI2 du lot 2) ; time.sleep est neutralisé.
"""
import hashlib
import importlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
import requests

from test_gitnotate_lot1 import GOOD_LLM, chat, existing_page, make_response, repo_data, rt_text, text_block
from test_gitnotate_lot2 import (
    BASE_ENV2, MESSAGES, OR_SERVED, FakeAPI2, _wire, history, pages_posted, sequence,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def world2(load_gn, monkeypatch):
    def _make(**env):
        merged = dict(BASE_ENV2)
        merged.update(env)
        gn = load_gn(**merged)
        api = FakeAPI2()
        _wire(gn, monkeypatch, api)
        return gn, api
    return _make


def _poll(predicate, timeout=2.0):
    """Attente active sans time.sleep (neutralisé par les fixtures)."""
    ev = threading.Event()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        ev.wait(0.005)
    return predicate()


def _forget_on_teardown(monkeypatch, keys):
    """load_dotenv écrit dans os.environ hors monkeypatch : l'état « absent » est enregistré."""
    for key in keys:
        monkeypatch.setenv(key, 'x')
        monkeypatch.delenv(key)


_DROP = object()


def J(**over):
    """Réponse LLM JSON : GOOD_LLM modifiée (_DROP retire le champ)."""
    data = dict(GOOD_LLM)
    data.update(over)
    for key in [k for k, v in over.items() if v is _DROP]:
        del data[key]
    return json.dumps(data, ensure_ascii=False)


def run_with_generation(world2, content=None, response=None, **env):
    """Run complet, Mistral seul : test de démarrage valide, génération = `content` (ou `response`)."""
    env.setdefault('OPENROUTER_API_KEY', None)
    gn, api = world2(**env)

    def mistral(url, payload):
        if payload.get('max_tokens') == 16:
            return make_response(200, chat('{"ok": true}', model='mistral-small-2603'))
        if response is not None:
            return response
        return make_response(200, chat(content, model='mistral-small-2603'))
    api.route('POST', r'api\.mistral\.ai', mistral)
    code = gn.main([])
    return gn, api, code


def _alias_world(world2, urls, **env):
    """Plusieurs URL de la page source pour UN même dépôt (renommé ou transféré → neworg/tool)."""
    gn, api = world2(**env)
    api.set_page_urls(urls)
    canonical = repo_data('neworg', 'tool')
    for url in urls:
        api.repos[url.split('github.com/', 1)[1]] = canonical     # GitHub suit la redirection
    return gn, api

# =============================================================================
# S1 — création à l'issue incertaine : aucun second POST pour un autre lien du même dépôt
# =============================================================================
_UNCERTAIN = {
    'timeout': lambda: requests.exceptions.ReadTimeout('réponse perdue'),
    'coupure': lambda: requests.exceptions.ConnectionError('reset'),
    '500': lambda: make_response(500, {'message': 'internal'}),
    '502': lambda: make_response(502, {'message': 'bad gateway'}),
    '503': lambda: make_response(503, {'message': 'unavailable'}),
    '504': lambda: make_response(504, {'message': 'gateway timeout'}),
}


@pytest.mark.parametrize('failure', list(_UNCERTAIN))
def test_s1_uncertain_creation_then_alias_creates_no_duplicate(world2, capsys, failure):
    urls = ['https://github.com/oldorg/tool', 'https://github.com/neworg/tool', 'https://github.com/otherorg/tool']
    gn, api = _alias_world(world2, urls)
    committed = []                          # fiches réellement présentes côté Notion

    def pages(url, payload):
        committed.append(payload['properties']['URL']['url'])    # Notion a créé la fiche...
        if len(committed) == 1:
            return _UNCERTAIN[failure]()                         # ...mais la réponse se perd
        return make_response(200, {'id': f'p{len(committed)}'})
    api.route('POST', r'/v1/pages$', pages)
    assert gn.main([]) == 2
    assert committed == ['https://github.com/neworg/tool']
    assert gn.stats.duplicates == 2 and gn.stats.errors == 1
    assert api.count('GET', r'/repos/neworg/tool$') == 0                    # pré-contrôle sans GitHub
    assert api.count('GET', r'/repos/otherorg/tool$') == 1                  # alias vu après GitHub
    assert "création à l'issue incertaine" in capsys.readouterr().out


def test_s1_uncertain_key_forgotten_at_next_run(world2, capsys):
    """Fiche finalement absente de Notion : le dépôt est repris au run suivant."""
    gn, api = world2()
    api.route('POST', r'/v1/pages$', sequence(make_response(503, {}), make_response(200, {'id': 'p'})))
    assert gn.main([]) == 2 and gn.UNCERTAIN_KEYS == {'owner/repo'}
    assert gn.main([]) == 0 and gn.stats.success == 1
    capsys.readouterr()
    assert len(pages_posted(api)) == 2


def test_s1_direct_calls_share_the_run_wide_uncertain_set(world2):
    """Appels directs sans l'ensemble explicite : la protection vaut quand même (UNCERTAIN_KEYS)."""
    gn, api = _alias_world(world2, ['https://github.com/oldorg/tool', 'https://github.com/neworg/tool'])
    gn.TRANSLATION_PROVIDER = 'mistral'
    api.route('POST', r'/v1/pages$', sequence(make_response(502, {}), make_response(200, {'id': 'p'})))
    existing, keys, in_progress = set(), set(), set()
    gn.process_single_repo('https://github.com/oldorg/tool', 'db-1', existing, True, 1, 2, keys, in_progress)
    r2 = gn.process_single_repo('https://github.com/neworg/tool', 'db-1', existing, True, 2, 2, keys, in_progress)
    assert r2['skipped'] and len(pages_posted(api)) == 1 and gn.UNCERTAIN_KEYS == {'neworg/tool'}


def test_s1_uncertain_5xx_message_says_outcome_is_uncertain(world2, capsys):
    gn, api = world2()
    api.route('POST', r'/v1/pages$', lambda u, p: make_response(504, {'message': 'gateway timeout'}))
    assert gn.main([]) == 2
    err = capsys.readouterr().err
    assert 'Notion HTTP 504 — gateway timeout — issue incertaine' in err and 'refusée' not in err
    assert history(gn)[-1]['errors_by_reason'] == {'Notion HTTP 504': 1}


def test_s1_definitive_refusal_then_alias_creates_one_page(world2):
    """Témoin : un refus certain (400) libère la clé ; l'alias crée l'unique fiche."""
    gn, api = _alias_world(world2, ['https://github.com/oldorg/tool', 'https://github.com/neworg/tool'])
    api.route('POST', r'/v1/pages$', sequence(make_response(400, {'message': 'validation'}),
                                              make_response(200, {'id': 'p'})))
    assert gn.main([]) == 2
    assert len(pages_posted(api)) == 2 and gn.stats.success == 1 and gn.stats.duplicates == 0

# =============================================================================
# S3 — mode reprise : réponses dégradées refusées (champs vides, gabarit du prompt recopié)
# =============================================================================
DEGRADED = {
    'use_cases vide': J(use_cases_fr=''),
    'use_cases liste vide': J(use_cases_fr=[]),
    "use_cases [None, '']": J(use_cases_fr=[None, '']),
    'reasoning absent': J(reasoning=_DROP),
    'reasoning vide': J(reasoning='  '),
    'gabarit du prompt recopié': json.dumps({
        'description_fr': 'traduction française de la description',
        'use_cases_fr': "• cas d'usage 1\n• cas d'usage 2\n• cas d'usage 3",
        'score': 7, 'reasoning': '<justification du score en 40 mots maximum>'}, ensure_ascii=False),
    'description du gabarit seule': J(description_fr='Traduction française de la description.'),
    'cas d’usage du gabarit seuls': J(use_cases_fr="• cas d’usage 1\n• cas d’usage 2"),
    'reasoning du gabarit seul': J(reasoning='<justification du score en 40 mots maximum>'),
}


@pytest.mark.parametrize('label', list(DEGRADED))
def test_s3_degraded_answers_are_deferred(world2, label):
    gn, api, code = run_with_generation(world2, DEGRADED[label])
    assert pages_posted(api) == [], label
    assert gn.stats.deferred == 1 and code == 0
    assert history(gn)[-1]['deferred_by_reason'] == {gn.DEFER_LLM_FAILED: 1}


def test_s3_translation_only_template_is_deferred(world2):
    content = json.dumps({'description_fr': 'traduction de la description',
                          'use_cases_fr': "traduction des cas d'usage avec puces • "})
    gn, api, code = run_with_generation(world2, content, LLM_SCORING_ENABLED='false')
    assert pages_posted(api) == [] and gn.stats.deferred == 1


@pytest.mark.parametrize('content', [J(), J(use_cases_fr=['a', '• b']), J(reasoning='x' * 900)])
def test_s3_valid_answers_still_written(world2, content):
    gn, api, code = run_with_generation(world2, content)
    (page,) = pages_posted(api)
    justification = page['properties']['Justification']['rich_text'][0]['text']['content']
    assert justification.startswith('[LLM mistral-small-2603') and len(justification) <= 800
    assert page['properties']['Pertinence']['number'] == 7


def test_s3_missing_reasoning_keeps_translation_when_require_llm_false(world2):
    """Justification absente : score LLM écarté (réponse partielle) mais traduction conservée."""
    gn, api, code = run_with_generation(world2, J(reasoning=_DROP), REQUIRE_LLM='false')
    (page,) = pages_posted(api)
    assert page['properties']['Description']['rich_text'][0]['text']['content'] == 'Un outil en français'
    assert page['properties']['Justification']['rich_text'][0]['text']['content'].startswith('[LEXICAL')


def test_s3_template_markers_match_prompts(load_gn):
    gn = load_gn()
    combined = gn.build_system_prompt_combined().replace('\\n', '\n')
    assert gn._TEMPLATE_DESCRIPTIONS[0] in combined and gn._TEMPLATE_USE_CASES[0] in combined
    assert gn._TEMPLATE_REASONING in combined
    assert gn._TEMPLATE_DESCRIPTIONS[1] in gn.SYSTEM_PROMPT_TRANSLATE
    assert gn._TEMPLATE_USE_CASES[1] in gn.SYSTEM_PROMPT_TRANSLATE

# =============================================================================
# R1 / DOC-4 — page source : sous-bloc illisible ignoré, page racine illisible = configuration
# =============================================================================
SUB_ID = 'abcdef12-3456-7890-abcd-ef1234567890'


@pytest.mark.parametrize('status', [400, 403, 404])
def test_r1_unreadable_sub_block_is_skipped_and_run_continues(world2, capsys, status):
    gn, api = world2()
    gn.URLS_FILE.write_text('ancien contenu\n', encoding='utf-8')
    api.set_page_urls(['https://github.com/owner/r0', 'https://github.com/owner/r1'])
    synced = {'object': 'block', 'id': SUB_ID, 'type': 'synced_block', 'has_children': True,
              'synced_block': {'synced_from': {'type': 'block_id', 'block_id': 'original'}}}
    api.blocks['page-1'][0].insert(1, synced)
    api.route('GET', rf'/blocks/{SUB_ID}/children', lambda u, p: make_response(status, {'message': 'refusé'}))
    assert gn.main([]) == 2                                  # lecture partielle → code 2
    assert len(pages_posted(api)) == 2                       # les autres liens sont importés
    err = capsys.readouterr().err
    assert f'synced_block {SUB_ID}' in err and f'HTTP {status}' in err
    assert 'partagez la page d' in err
    assert gn.URLS_FILE.read_text(encoding='utf-8') == 'ancien contenu\n'
    assert history(gn)[-1]['skipped_source_blocks'] == 1 and history(gn)[-1]['exit_code'] == 2


def test_r1_sub_block_server_error_still_stops(world2):
    gn, api = world2()
    api.blocks['page-1'] = [[text_block('paragraph', [rt_text('https://github.com/owner/repo')], 'b1'),
                             text_block('toggle', [rt_text('dossier')], SUB_ID, has_children=True)]]
    api.route('GET', rf'/blocks/{SUB_ID}/children', lambda u, p: make_response(503, {'message': 'down'}))
    assert gn.main([]) == 2
    assert pages_posted(api) == []


def test_r1_skip_needs_explicit_collector(world2):
    """Appel direct sans collecteur : comportement strict (PartialReadError) inchangé."""
    gn, api = world2()
    api.blocks['page-1'] = [[text_block('toggle', [rt_text('x')], SUB_ID, has_children=True)]]
    with pytest.raises(gn.PartialReadError):
        gn.get_all_blocks_recursive('page-1')
    skipped = []
    assert len(gn.get_all_blocks_recursive('page-1', skipped=skipped)) == 1 and len(skipped) == 1


def test_doc4_root_page_bad_id_is_a_config_error(world2, capsys):
    gn, api = world2()
    api.route('GET', r'/blocks/page-1/children',
              lambda u, p: make_response(400, {'message': 'path.block_id should be a valid uuid'}))
    assert gn.main([]) == 1
    assert 'vérifiez PARENT_PAGE_ID' in capsys.readouterr().err
    assert pages_posted(api) == []

# =============================================================================
# C1 — MAX_NEW_PER_RUN avec workers parallèles : pas de famine
# =============================================================================
def test_c1_failing_repo_holding_slot_does_not_starve_others(world2, monkeypatch, capsys):
    """MAX_NEW_PER_RUN=1, 2 workers ; le 1er dépôt nouveau est mort (404). Le dépôt vivant attend
    l'issue de la réservation au lieu d'être reporté : 1 fiche par run."""
    gn, api = world2(MAX_WORKERS='2', MAX_NEW_PER_RUN='1')
    api.set_page_urls(['https://github.com/ghost/dead', 'https://github.com/owner/live'])
    ghost_in_github = threading.Event()
    real_extract = gn.extract_github_info

    def extract(url):
        # le dépôt vivant démarre une fois la place prise par le dépôt mort
        if threading.current_thread() is not threading.main_thread() and 'owner/live' in url:
            ghost_in_github.wait(2)
        return real_extract(url)
    monkeypatch.setattr(gn, 'extract_github_info', extract)

    def ghost_meta(url, payload):
        ghost_in_github.set()
        _poll(lambda: gn.stats.deferred >= 1 or gn.stats.success >= 1, timeout=0.3)   # latence GitHub
        return make_response(404, {'message': 'Not Found'})
    api.route('GET', r'api\.github\.com/repos/ghost/dead$', ghost_meta)

    created = []
    for _ in range(2):
        ghost_in_github.clear()
        gn.main([])
        created.append(gn.stats.success)
        assert gn.stats.deferred_by_reason.get(gn.DEFER_BUDGET, 0) == 0
    capsys.readouterr()
    assert created == [1, 1]


def test_c1_five_workers_two_dead_repos_first_exactly_limit_created(world2, capsys):
    gn, api = world2(MAX_WORKERS='5', MAX_NEW_PER_RUN='2')
    api.set_page_urls(['https://github.com/ghost/dead1', 'https://github.com/ghost/dead2']
                      + [f'https://github.com/owner/live{i}' for i in range(8)])

    def dead(url, payload):
        threading.Event().wait(0.1)                      # vraie latence GitHub
        return make_response(404, {'message': 'Not Found'})
    api.route('GET', r'api\.github\.com/repos/ghost/dead\d$', dead)
    gn.main([])
    capsys.readouterr()
    assert len(pages_posted(api)) == 2                   # la limite est atteinte malgré les dépôts morts
    assert gn.stats.success + gn.stats.errors + gn.stats.deferred == 10
    assert set(gn.stats.deferred_by_reason) == {gn.DEFER_BUDGET}
    assert len(api.entries('GET', r'/repos/owner/live\d$')) == 2      # pas d'appel GitHub pour les reportés

# =============================================================================
# SEC-1 — jeton coupé par un saut de ligne : jamais affiché en clair
# =============================================================================
GH_TAIL = 'GHTAILsecretQQQQQQQQ'


def test_sec1_wrapped_token_in_dotenv_refused_without_printing_it(load_gn, monkeypatch, tmp_path, capsys):
    (tmp_path / '.env').write_text(
        'MISTRAL_API_KEY=mistral-key-ABCDEFGH12345678\n'
        f'GITHUB_TOKEN="ghp_HEADpart1AAAAAAAA\n{GH_TAIL}"\n'
        'NOTION_TOKEN=ntn_test_token_1234\nPARENT_PAGE_ID=page-1\nDATABASE_ID=db-1\n', encoding='utf-8')
    _forget_on_teardown(monkeypatch, ['MISTRAL_API_KEY', 'GITHUB_TOKEN', 'NOTION_TOKEN',
                                      'PARENT_PAGE_ID', 'DATABASE_ID'])
    monkeypatch.delenv('GITNOTATE_NO_DOTENV')            # vrai chargement par python-dotenv
    gn = load_gn()
    assert '\n' in gn.GITHUB_TOKEN                       # python-dotenv garde le saut de ligne
    api = FakeAPI2()
    _wire(gn, monkeypatch, api)
    assert gn.main([]) == 1
    cap = capsys.readouterr()
    assert 'GITHUB_TOKEN contient un espace ou un saut de ligne' in cap.err
    assert GH_TAIL not in cap.out + cap.err
    assert api.calls == []                               # refusé avant tout appel réseau


@pytest.mark.parametrize('name', ['NOTION_TOKEN', 'MISTRAL_API_KEY', 'OPENROUTER_API_KEY'])
def test_sec1_other_secrets_with_blank_refused(world2, capsys, name):
    gn, api = world2(**{name: 'abcd1234\nSECRETTAIL5678'})
    assert gn.main([]) == 1
    cap = capsys.readouterr()
    assert f'{name} contient un espace' in cap.err and 'SECRETTAIL' not in cap.out + cap.err
    assert api.calls == []


def test_sec1_unexpected_http_exception_shows_type_only(load_gn, monkeypatch, capsys):
    gn = load_gn()

    class Session:
        def get(self, url, **kwargs):
            raise requests.exceptions.InvalidHeader(
                f"Invalid return character in header value: 'Bearer ghp_x\\n{GH_TAIL}'")
    monkeypatch.setattr(gn, 'get_session', lambda: Session())
    assert gn.http_request_with_retry('GET', 'https://api.github.com/user', {}) is None
    err = capsys.readouterr().err
    assert 'InvalidHeader' in err and GH_TAIL not in err


def test_sec1_llm_exception_shows_type_only(load_gn, monkeypatch, capsys):
    gn = load_gn(MISTRAL_API_KEY='mistral-test-key')

    class Session:
        def post(self, url, **kwargs):
            raise requests.exceptions.InvalidHeader(f"header value: 'Bearer {GH_TAIL}'")
    monkeypatch.setattr(gn, 'get_session', lambda: Session())
    monkeypatch.setattr(gn.time, 'sleep', lambda s: None)
    assert gn._call_translation_api('mistral', MESSAGES, 0.1) is None
    err = capsys.readouterr().err
    assert 'InvalidHeader' in err and GH_TAIL not in err


CL_TAIL = 'CLTAILsecretEEEEEEEE'


def test_sec1_cleaner_wrapped_token_refused_without_printing_it(monkeypatch, capsys):
    cpd = importlib.import_module('clean_page_duplicates')
    monkeypatch.setenv('NOTION_CLEANER_TOKEN', f'ntn_CLEANpart1CCCCCCCC\n{CL_TAIL}')
    monkeypatch.setenv('PARENT_PAGE_ID', '0123456789abcdef0123456789abcdef')
    calls = []

    class Session:
        def request(self, method, url, **kwargs):
            calls.append(url)
            raise AssertionError('aucune requête attendue')
    assert cpd.main([], session=Session(), sleep=lambda s: None) == cpd.EXIT_CONFIG
    out = capsys.readouterr()
    assert 'NOTION_CLEANER_TOKEN contient un espace ou un saut de ligne' in out.out
    assert CL_TAIL not in out.out + out.err and calls == []


def test_sec1_cleaner_network_error_shows_type_only(monkeypatch, capsys):
    cpd = importlib.import_module('clean_page_duplicates')
    monkeypatch.setenv('NOTION_CLEANER_TOKEN', 'ntn_CLEANER_secret_1234567890')
    monkeypatch.setenv('PARENT_PAGE_ID', '0123456789abcdef0123456789abcdef')

    class Session:
        def request(self, method, url, **kwargs):
            raise requests.exceptions.InvalidHeader(f"header value: 'Bearer ntn_x\\n{CL_TAIL}'")
    assert cpd.main([], session=Session(), sleep=lambda s: None) == cpd.EXIT_ABORT
    out = capsys.readouterr()
    assert 'InvalidHeader' in out.out and CL_TAIL not in out.out + out.err

# =============================================================================
# SEC-2 — secrets et fichiers d'exécution ignorés par git
# (gitnotate_stats.json reste suivi tant que l'utilisateur n'a pas décidé de le retirer)
# =============================================================================
IGNORED_RUNTIME = ('.gitnotate_cache.json', 'extracted_urls_unique.txt')


@pytest.mark.skipif(shutil.which('git') is None, reason='git absent')
def test_sec2_dry_run_leaves_only_ignored_files(load_gn, monkeypatch, tmp_path, capsys):
    depot = tmp_path / 'depot'
    depot.mkdir()
    subprocess.run(['git', 'init', '-q', str(depot)], check=True)
    shutil.copy(ROOT / '.gitignore', depot / '.gitignore')
    gn = load_gn(**dict(BASE_ENV2, GITNOTATE_DATA_DIR=str(depot)))
    _wire(gn, monkeypatch, FakeAPI2())
    assert gn.main(['--dry-run']) == 0
    capsys.readouterr()
    assert all((depot / name).exists() for name in IGNORED_RUNTIME)
    status = subprocess.run(['git', '-C', str(depot), 'status', '--porcelain', '--untracked-files=all'],
                            capture_output=True, text=True, check=True).stdout
    assert sorted(status.splitlines()) == ['?? .gitignore', '?? gitnotate_stats.json'], status


@pytest.mark.skipif(shutil.which('git') is None, reason='git absent')
def test_sec2_secret_and_state_files_ignored(tmp_path):
    depot = tmp_path / 'depot'
    depot.mkdir()
    subprocess.run(['git', 'init', '-q', str(depot)], check=True)
    shutil.copy(ROOT / '.gitignore', depot / '.gitignore')
    for name in ('.env', '.env.local', '.gitnotate_cache.json', '.gitnotate_state.json',
                 'journal/cleaner-1.jsonl', 'gitnotate_stats.json.tmp'):
        path = depot / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('x', encoding='utf-8')
    (depot / 'env.example').write_text('x', encoding='utf-8')
    status = subprocess.run(['git', '-C', str(depot), 'status', '--porcelain', '--untracked-files=all'],
                            capture_output=True, text=True, check=True).stdout
    assert sorted(status.splitlines()) == ['?? .gitignore', '?? env.example'], status

# =============================================================================
# S4 — raisonnement en ligne : le brouillon n'est jamais retenu
# =============================================================================
def test_s4_inline_think_draft_is_ignored(world2):
    content = ('<think>Premier jet : {"description_fr": "brouillon", "use_cases_fr": "• x", "score": 2, '
               '"reasoning": "premier jet"} — non, le README montre un usage éducatif.</think>\n'
               + J(description_fr='Outil final', score=8, reasoning='définitif'))
    gn, api, code = run_with_generation(world2, content)
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence']['number'] == 8
    assert page['properties']['Description']['rich_text'][0]['text']['content'] == 'Outil final'


def test_s4_parse_keeps_last_answer_and_ignores_nested(load_gn):
    gn = load_gn()
    parse = gn._parse_llm_json
    assert parse('<thinking>{"description_fr": "a"}</thinking> {"description_fr": "b"}') == {'description_fr': 'b'}
    assert parse('Brouillon {"description_fr": "a"} puis final {"description_fr": "b"}') == {'description_fr': 'b'}
    nested = '{"description_fr": "a", "meta": {"description_fr": "imbriqué"}}'
    assert parse(nested)['description_fr'] == 'a'
    assert parse('{"x": 1} et {"y": 2}') == {'x': 1}

# =============================================================================
# S5 — interrupteurs : valeurs « vraies » reconnues, valeur inconnue refusée
# =============================================================================
@pytest.mark.parametrize('value', ['1', 'yes', 'oui', 'vrai', 'on', 'TRUE'])
def test_s5_dry_run_truthy_values_simulate(world2, value):
    gn, api = world2(DRY_RUN=value)
    assert gn.main([]) == 0
    assert pages_posted(api) == [] and gn.stats.success == 1 and gn.DRY_RUN is True


@pytest.mark.parametrize('name', ['DRY_RUN', 'TRANSLATION_ENABLED', 'LLM_SCORING_ENABLED', 'CACHE_ENABLED'])
def test_s5_unknown_switch_value_exits_1_before_network(world2, capsys, name):
    gn, api = world2(**{name: 'peut-être'})
    assert gn.main([]) == 1
    assert api.calls == [] and name in capsys.readouterr().err


@pytest.mark.parametrize('value', ['1', 'yes', 'oui'])
def test_s5_translation_enabled_truthy_keeps_require_llm(world2, value):
    gn, api, code = run_with_generation(world2, J(), TRANSLATION_ENABLED=value)
    (page,) = pages_posted(api)
    assert page['properties']['Justification']['rich_text'][0]['text']['content'].startswith('[LLM ')


@pytest.mark.parametrize('value,expected', [('0', False), ('non', False), ('', False), ('false', False)])
def test_s5_false_values_and_empty(load_gn, value, expected):
    gn = load_gn(DRY_RUN=value)
    assert gn.DRY_RUN is expected and 'DRY_RUN' not in gn.CONFIG_ERRORS


def test_s5_require_llm_unrecognised_value_warns(load_gn):
    gn = load_gn(REQUIRE_LLM='0')
    assert gn.REQUIRE_LLM is True                                     # mode reprise conservé
    assert any('REQUIRE_LLM' in w for w in gn.CONFIG_WARNINGS)
    assert not any('REQUIRE_LLM' in w for w in load_gn(REQUIRE_LLM='false').CONFIG_WARNINGS)

# =============================================================================
# S6 — fiche existante dont l'URL est saisie sans https://
# =============================================================================
@pytest.mark.parametrize('existing', ['github.com/acme/tool', 'www.github.com/Acme/Tool/', ' github.com/acme/tool '])
def test_s6_existing_url_without_scheme_is_recognised(world2, existing):
    gn, api = world2()
    api.set_page_urls(['https://github.com/acme/tool'])
    api.query_pages = [[existing_page(existing)]]
    assert gn.main([]) == 0
    assert pages_posted(api) == [] and gn.stats.already_present == 1


def test_s6_normalize_without_scheme(load_gn):
    gn = load_gn()
    assert gn.normalize_github_url('github.com/Acme/Tool.git') == 'acme/tool'
    assert gn.normalize_github_url('gist.github.com/a/b') == 'gist.github.com/a/b'

# =============================================================================
# R3 / R4 — .env : emplacement affiché ; ancien MISTRAL_MODEL signalé
# =============================================================================
def test_r3_config_error_shows_expected_env_file(world2, capsys):
    gn, api = world2(PARENT_PAGE_ID=None)
    assert gn.main([]) == 1
    err = capsys.readouterr().err
    assert f"Fichier .env attendu : {gn.BASE_DIR / '.env'}" in err
    assert 'GITNOTATE_NO_DOTENV' in err                              # raison pour laquelle il n'est pas lu


@pytest.mark.parametrize('model,warned', [('mistral-small-2503', True), ('mistral-small-latest', True),
                                          ('mistral-small-2603', False), ('mistral-large-2512', False),
                                          (None, False)])
def test_r4_v71_mistral_model_warns(load_gn, model, warned):
    gn = load_gn(MISTRAL_MODEL=model)
    assert any('MISTRAL_MODEL' in w and 'mistral-small-2603' in w for w in gn.CONFIG_WARNINGS) is warned

# =============================================================================
# C2 — fournisseur désactivé pendant l'attente du limiteur : requête non envoyée
# =============================================================================
def test_c2_request_not_sent_after_provider_disabled_during_limiter_wait(world2, monkeypatch):
    gn, api = world2(OPENROUTER_RPM='18')
    state = gn._provider_state('openrouter')
    a_in_flight, b_waiting, disabled = threading.Event(), threading.Event(), threading.Event()
    real_disable = state.disable

    def spy_disable(reason):
        real_disable(reason)
        disabled.set()
    monkeypatch.setattr(state, 'disable', spy_disable)

    def limiter_sleep(seconds):                   # attente du limiteur (thread B)
        b_waiting.set()
        disabled.wait(2)
    monkeypatch.setattr(gn.time, 'sleep', limiter_sleep)
    calls = []

    def openrouter(url, payload):
        calls.append(1)
        if len(calls) == 1:
            a_in_flight.set()
            b_waiting.wait(2)
        return make_response(402, {'error': {'code': 402, 'message': 'Insufficient credits'}})
    api.route('POST', r'openrouter\.ai/api/v1/chat', openrouter)
    ta = threading.Thread(target=gn._call_translation_api, args=('openrouter', MESSAGES, 0.1))
    tb = threading.Thread(target=gn._call_translation_api, args=('openrouter', MESSAGES, 0.1))
    ta.start()
    assert a_in_flight.wait(2)
    tb.start()
    ta.join(5)
    tb.join(5)
    assert state.available is False and len(calls) == 1

# =============================================================================
# C3 — 429 « par minute » d'OpenRouter : nouvelle tentative, pas de désactivation
# =============================================================================
def test_c3_openrouter_per_minute_429_is_retried_not_disabled(world2):
    reset_ms = str(int((time.time() + 20) * 1000))
    headers = {'X-RateLimit-Limit': '20', 'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': reset_ms}
    per_minute = make_response(429, {'error': {'code': 429, 'message': 'Rate limit exceeded: free-models-per-min. '}},
                               headers)
    gn, api = world2(LLM_PROVIDERS='openrouter', MISTRAL_API_KEY=None)
    api.route('POST', r'openrouter\.ai/api/v1/chat',
              sequence(per_minute, make_response(200, chat(J(), model=OR_SERVED))))
    gn._provider_state('openrouter').budget = 45
    assert gn._call_translation_api('openrouter', MESSAGES, 0.1) is not None
    state = gn._provider_state('openrouter')
    assert state.available and state.budget == 43
    assert any(18 <= s <= 21 for s in api.sleeps)                   # attente jusqu'au Reset


def test_c3_daily_quota_still_disables(world2):
    daily = make_response(429, {'error': {'message': 'Rate limit exceeded: free-models-per-day'}})
    gn, api = world2(LLM_PROVIDERS='openrouter', MISTRAL_API_KEY=None)
    api.route('POST', r'openrouter\.ai/api/v1/chat', lambda u, p: daily)
    assert gn._call_translation_api('openrouter', MESSAGES, 0.1) is None
    assert 'quota OpenRouter épuisé' in gn._provider_state('openrouter').disabled_reason
    assert len(api.llm_bodies('openrouter')) == 1

# =============================================================================
# C4 — budget OpenRouter épuisé : report « aucun fournisseur » sans appel GitHub
# =============================================================================
def test_c4_exhausted_budget_defers_without_github_call(world2, capsys):
    gn, api = world2(MISTRAL_API_KEY=None, LLM_PROVIDERS='openrouter')
    api.or_quota = {'used': 49, 'limit': 50, 'remaining': 1}
    api.set_page_urls(['https://github.com/owner/first', 'https://github.com/owner/second'])
    assert gn.main([]) == 0
    cap = capsys.readouterr()
    assert len(pages_posted(api)) == 1
    assert api.count('GET', r'api\.github\.com/repos/owner/second$') == 0
    assert dict(gn.stats.deferred_by_reason) == {gn.DEFER_NO_LLM: 1}
    assert 'quota gratuit du jour épuisé' in cap.err                 # bilan : cause visible
    assert 'quota gratuit du jour épuisé' in history(gn)[-1]['llm_disabled']['openrouter']


def test_c4_request_not_sent_is_unavailable_not_failed(world2, monkeypatch):
    """Course entre workers : le dernier crédit est pris par un autre thread entre le contrôle
    « disponible » et l'envoi → aucune requête partie → 'unavailable' (pas un échec du LLM)."""
    gn, api = world2(MISTRAL_API_KEY=None, LLM_PROVIDERS='openrouter')
    gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK = 'openrouter', None
    monkeypatch.setattr(gn._provider_state('openrouter'), 'try_consume', lambda: False)
    result = gn.translate_and_score('A tool', '• x', {'name': 'demo'}, 'o/demo')
    assert result['llm_status'] == 'unavailable' and api.llm_bodies('openrouter') == []

# =============================================================================
# C6 — Ctrl-C : pas de report « aucune réponse LLM valide »
# =============================================================================
def test_c6_interrupt_is_not_reported_as_llm_failure(world2, monkeypatch, capsys):
    gn, api = world2()
    in_github = threading.Event()

    def slow_meta(url, payload):
        in_github.set()
        _poll(gn._STOP_EVENT.is_set)
        return make_response(200, api.repos['owner/repo'])
    api.route('GET', r'api\.github\.com/repos/owner/repo$', slow_meta)

    def interrupted_wait(*args, **kwargs):
        in_github.wait(2)
        raise KeyboardInterrupt
    monkeypatch.setattr(gn, 'wait', interrupted_wait)
    assert gn.main([]) == 130
    capsys.readouterr()
    assert gn.stats.deferred == 0 and gn.stats.translation_failed == 0
    assert pages_posted(api) == []

# =============================================================================
# C7 — LOG_LEVEL=quiet : la cause d'abandon d'un fournisseur reste affichée
# =============================================================================
def test_c7_quiet_startup_shows_why_no_provider_is_available(world2, capsys):
    gn, api = world2(LOG_LEVEL='quiet')
    api.route('POST', r'api\.mistral\.ai', lambda u, p: requests.exceptions.ReadTimeout('timeout'))
    api.or_quota = {'used': 50, 'limit': 50, 'remaining': 0}
    assert gn.main([]) == 1
    err = capsys.readouterr().err
    assert 'Aucun fournisseur LLM disponible' in err and 'timeout' in err and 'quota' in err


def test_c7_quiet_midrun_key_revocation_is_visible(world2, capsys):
    gn, api = world2(LOG_LEVEL='quiet', OPENROUTER_API_KEY=None)
    api.set_page_urls(['https://github.com/owner/a', 'https://github.com/owner/b'])

    def mistral(url, payload):
        if payload.get('max_tokens') == 16:
            return make_response(200, chat('{"ok": true}', model='mistral-small-2603'))
        return make_response(401, {'message': 'Unauthorized'})
    api.route('POST', r'api\.mistral\.ai', mistral)
    gn.main([])
    cap = capsys.readouterr()
    assert gn.stats.deferred == 2 and 'clé refusée (HTTP 401' in cap.err and cap.out == ''

# =============================================================================
# C8 — incident passager au test de démarrage : une nouvelle tentative
# =============================================================================
def test_c8_transient_5xx_at_mistral_probe_is_retried(world2, capsys):
    gn, api = world2()
    api.route('POST', r'api\.mistral\.ai', sequence(
        make_response(503, {'message': 'Service unavailable'}),
        make_response(200, chat('{"ok": true}', model='mistral-small-2603'))))
    assert gn.main([]) == 0
    capsys.readouterr()
    assert gn.TRANSLATION_PROVIDER == 'mistral' and gn.BACKOFF_FACTOR in api.sleeps


@pytest.mark.parametrize('first', [make_response(502, {}), requests.exceptions.ConnectTimeout('lent')])
def test_c8_transient_failure_at_openrouter_probe_is_retried(world2, first):
    gn, api = world2()
    ok_key = make_response(200, {'data': {'free_model_daily_requests': {'used': 0, 'limit': 50, 'remaining': 50}}})
    api.route('GET', r'openrouter\.ai/api/v1/key', sequence(first, ok_key))
    ok, msg = gn._probe_openrouter()
    assert ok and 'clé valide' in msg and len(api.entries('GET', r'openrouter\.ai/api/v1/key')) == 2

# =============================================================================
# DOC-1 — aucun identifiant Notion réel de la configuration d'origine dans le dépôt
# =============================================================================
# Empreintes SHA-256 (les identifiants eux-mêmes ne sont pas recopiés ici)
_REAL_ID_HASHES = {
    '6c7065e8df5fd889b8cbb379ad16bb5de84f7483238babaf9fb1f2df6cffaf97',   # PARENT_PAGE_ID d'origine
    'f8ed88c4f209b0d0aa9029f757d47926bb90f4c557f1f42ec4218bd58d7c20f9',   # DATABASE_ID d'origine
}
_TEXT_SUFFIXES = {'.py', '.md', '.txt', '.example', '.json', '.ini', '.cfg', '.toml'}


def test_doc1_no_real_notion_id_in_repository():
    hits = []
    for path in ROOT.rglob('*'):
        rel = path.relative_to(ROOT)
        if (not path.is_file() or path.suffix not in _TEXT_SUFFIXES and path.name != 'env.example'
                or any(part.startswith('.') or part in ('__pycache__', 'venv') for part in rel.parts[:-1])):
            continue
        text = path.read_text(encoding='utf-8', errors='ignore')
        for candidate in re.findall(r'[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}', text):
            if hashlib.sha256(candidate.replace('-', '').encode()).hexdigest() in _REAL_ID_HASHES:
                hits.append(str(rel))
    assert hits == []

# =============================================================================
# DOC-2 — GITNOTATE_NO_DOTENV : même règle pour les trois scripts
# =============================================================================
@pytest.mark.parametrize('flag', ['0', '', 'false', 'non'])
def test_doc2_no_dotenv_false_values_still_load_env(load_gn, monkeypatch, tmp_path, flag):
    (tmp_path / '.env').write_text('NOTION_TOKEN=ntn_from_dotenv_file_1234\n', encoding='utf-8')
    _forget_on_teardown(monkeypatch, ['NOTION_TOKEN'])
    monkeypatch.setenv('GITNOTATE_NO_DOTENV', flag)
    cpd = importlib.import_module('clean_page_duplicates')
    assert cpd.load_env_file(tmp_path).startswith('chargé')
    monkeypatch.delenv('NOTION_TOKEN')
    gn = load_gn()
    assert gn.NOTION_TOKEN == 'ntn_from_dotenv_file_1234'
    monkeypatch.delenv('NOTION_TOKEN')
    spec = importlib.util.spec_from_file_location('check_llm_doc2', ROOT / 'scripts' / 'check_llm.py')
    ck = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ck)
    ck.load_env()
    assert os.environ.get('NOTION_TOKEN') == 'ntn_from_dotenv_file_1234'


def test_doc2_no_dotenv_true_value_skips_env(load_gn, monkeypatch, tmp_path):
    (tmp_path / '.env').write_text('NOTION_TOKEN=ntn_from_dotenv_file_1234\n', encoding='utf-8')
    _forget_on_teardown(monkeypatch, ['NOTION_TOKEN'])
    gn = load_gn(GITNOTATE_NO_DOTENV='1')
    assert gn.NOTION_TOKEN == '' and gn.DOTENV_STATUS.startswith('non lu')
    assert 'si elle a une valeur « vraie »' in (ROOT / 'env.example').read_text(encoding='utf-8')

# =============================================================================
# DOC-3 — README : ce que garantit le code 0 de check_llm.py
# =============================================================================
def test_doc3_readme_matches_check_llm_exit_code(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location('check_llm_doc3', ROOT / 'scripts' / 'check_llm.py')
    ck = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ck)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-v1-0123456789abcdef0123456789abcdef')
    monkeypatch.setattr(ck, '_http_get', lambda url, headers: make_response(
        200, {'data': {'free_model_daily_requests': {'used': 0, 'limit': 50, 'remaining': 50}}}))
    assert ck.main() == 0                                            # Mistral non vérifié : clé absente
    assert 'MISTRAL_API_KEY absente' in capsys.readouterr().out
    readme = ' '.join((ROOT / 'README.md').read_text(encoding='utf-8').split())
    assert 'clés valides et modèle Mistral disponible' not in readme
    assert 'le modèle Mistral est vérifié si `MISTRAL_API_KEY` est renseignée' in readme
