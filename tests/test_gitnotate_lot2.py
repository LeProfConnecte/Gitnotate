"""Tests du lot 2 (fournisseurs LLM, mode reprise, coupe-circuit, traçabilité) — réseau simulé.

Réutilise la fausse API du lot 1 (FakeAPI) en l'étendant : en-têtes et timeouts enregistrés,
GET https://openrouter.ai/api/v1/key simulé, modèle servi distinct par fournisseur.
"""
import hashlib
import importlib.util
import json
import os
import re
import threading
import time
from pathlib import Path

import pytest
import requests

from test_gitnotate_lot1 import (
    GOOD_JSON, GOOD_LLM, FakeAPI, chat, existing_page, make_response, repo_data,
)

ROOT = Path(__file__).resolve().parent.parent
MISTRAL_SERVED = 'mistral-small-2603'
OR_SERVED = 'google/gemma-4-31b-it:free'
OR_KEY = 'sk-or-v1-0123456789abcdef0123456789abcdef'
MISTRAL_KEY = 'mistral-key-ABCDEFGH12345678'
MESSAGES = [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}]


class FakeAPI2(FakeAPI):
    """FakeAPI + en-têtes/timeouts enregistrés, /api/v1/key et modèle servi par fournisseur."""

    def __init__(self):
        super().__init__()
        self.log = []                       # (méthode, url, en-têtes, timeout, corps ou params)
        self.or_quota = {'used': 0, 'limit': 50, 'remaining': 50}
        self.mistral_content, self.mistral_model = GOOD_JSON, MISTRAL_SERVED
        self.or_content, self.or_model = GOOD_JSON, OR_SERVED

    def get(self, url, headers=None, params=None, timeout=None):
        with self._lock:
            self.log.append(('GET', url, dict(headers or {}), timeout, params))
        return self._dispatch('GET', url, params)

    def post(self, url, headers=None, json=None, timeout=None):
        with self._lock:
            self.log.append(('POST', url, dict(headers or {}), timeout, json))
        return self._dispatch('POST', url, json)

    def _default(self, method, url, payload):
        if method == 'GET' and url == 'https://openrouter.ai/api/v1/key':
            data = {'label': 'sk-or-v1-012...def', 'is_free_tier': False}
            if self.or_quota is not None:
                data['free_model_daily_requests'] = self.or_quota
            return make_response(200, {'data': data})
        if method == 'POST' and 'api.mistral.ai' in url:
            return make_response(200, chat(self.mistral_content, model=self.mistral_model))
        if method == 'POST' and 'openrouter.ai' in url:
            return make_response(200, chat(self.or_content, model=self.or_model))
        return super()._default(method, url, payload)

    def entries(self, method, pattern):
        with self._lock:
            return [e for e in self.log if e[0] == method and re.search(pattern, e[1])]

    def llm_bodies(self, provider):
        """Corps des requêtes de génération (hors test de démarrage, max_tokens=16)."""
        pattern = r'api\.mistral\.ai' if provider == 'mistral' else r'openrouter\.ai/api/v1/chat'
        return [e[4] for e in self.entries('POST', pattern)
                if e[4].get('max_tokens') != 16 and e[4].get('max_completion_tokens') != 16]


BASE_ENV2 = {
    'PARENT_PAGE_ID': 'page-1',
    'NOTION_TOKEN': 'ntn_test_token_1234',
    'DATABASE_ID': 'db-1',
    'MISTRAL_API_KEY': MISTRAL_KEY,
    'OPENROUTER_API_KEY': OR_KEY,
    'MAX_WORKERS': '1',
}


def _wire(gn, monkeypatch, api):
    monkeypatch.setattr(gn, 'get_session', lambda: api)
    monkeypatch.setattr(gn.time, 'sleep', lambda s: api.sleeps.append(s))
    monkeypatch.setattr(gn.atexit, 'register', lambda f, *a, **k: None)


@pytest.fixture
def world2(load_gn, monkeypatch):
    """Module rechargé (BASE_ENV2 + surcharges ; None retire une variable) et fausse API."""
    def _make(**env):
        merged = dict(BASE_ENV2)
        merged.update(env)
        gn = load_gn(**merged)
        api = FakeAPI2()
        _wire(gn, monkeypatch, api)
        return gn, api
    return _make


@pytest.fixture
def llm2(world2):
    """Cascade configurée sans test de démarrage (ordre LLM_PROVIDERS)."""
    def _make(mistral=None, openrouter=None, **env):
        gn, api = world2(**env)
        if mistral is not None:
            api.route('POST', r'api\.mistral\.ai', mistral)
        if openrouter is not None:
            api.route('POST', r'openrouter\.ai/api/v1/chat', openrouter)
        order = [p for p in gn.LLM_PROVIDERS if gn._provider_key(p)]
        gn.TRANSLATION_PROVIDER = order[0] if order else None
        gn.TRANSLATION_FALLBACK = order[1] if len(order) > 1 else None
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


def pages_posted(api):
    return [e[4] for e in api.entries('POST', r'api\.notion\.com/v1/pages$')]


def justification(page_payload):
    return page_payload['properties']['Justification']['rich_text'][0]['text']['content']


REPO = {'name': 'demo', 'language': 'Python', 'topics': ['ai'], 'readme': 'README', 'description': 'A tool',
        'stars': 3}

# =============================================================================
# 1. FOURNISSEURS : ORDRE, MODÈLES, CLÉS
# =============================================================================
def test_default_providers_and_models(load_gn):
    gn = load_gn()
    assert gn.LLM_PROVIDERS == ['mistral', 'openrouter']
    assert gn.MISTRAL_MODEL == 'mistral-small-2603'
    assert gn.OPENROUTER_MODEL == 'openrouter/free'
    assert gn.REQUIRE_LLM is True and gn.CONFIG_ERRORS == {}


def test_openrouter_model_compat_with_translation_model(load_gn):
    gn = load_gn(TRANSLATION_MODEL='openai/gpt-oss-20b:free')
    assert gn.OPENROUTER_MODEL == 'openai/gpt-oss-20b:free'
    assert any('TRANSLATION_MODEL (v7.1) est obsolète' in w for w in gn.CONFIG_WARNINGS)
    gn = load_gn(TRANSLATION_MODEL='ancien/modele', OPENROUTER_MODEL='mistralai/mistral-small-2603')
    assert gn.OPENROUTER_MODEL == 'mistralai/mistral-small-2603'


def test_llm_providers_order_and_invalid_values(world2, capsys):
    gn, _ = world2(LLM_PROVIDERS=' OpenRouter ; mistral, openrouter ')
    assert gn.LLM_PROVIDERS == ['openrouter', 'mistral'] and gn.CONFIG_ERRORS == {}
    gn, api = world2(LLM_PROVIDERS='mistral,claude')
    assert 'LLM_PROVIDERS' in gn.CONFIG_ERRORS
    assert gn.main([]) == 1
    assert api.calls == [] and 'claude' in capsys.readouterr().err


@pytest.mark.parametrize('name,value', [
    ('MISTRAL_RESPONSE_FORMAT', 'xml'), ('OPENROUTER_RESPONSE_FORMAT', 'yaml'),
    ('OPENROUTER_DATA_COLLECTION', 'parfois'), ('LLM_TIMEOUT', '0'), ('LLM_MAX_TOKENS', '8'),
    ('LLM_BREAKER_THRESHOLD', '0'), ('OPENROUTER_RPM', '-1'), ('MAX_NEW_PER_RUN', 'beaucoup'),
])
def test_invalid_llm_config_exits_1_before_network(world2, capsys, name, value):
    gn, api = world2(**{name: value})
    assert name in gn.CONFIG_ERRORS
    assert gn.main([]) == 1
    assert api.calls == [] and name in capsys.readouterr().err


def test_provider_without_key_is_ignored(world2, capsys):
    gn, api = world2(OPENROUTER_API_KEY=None)
    assert gn.main([]) == 0
    assert "OpenRouter (openrouter/free) ignoré : OPENROUTER_API_KEY absente" in capsys.readouterr().out
    assert api.entries('GET', r'openrouter\.ai') == [] and api.entries('POST', r'openrouter\.ai') == []
    assert (gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK) == ('mistral', None)


def test_order_openrouter_first(world2):
    gn, api = world2(LLM_PROVIDERS='openrouter,mistral')
    assert gn.main([]) == 0
    assert (gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK) == ('openrouter', 'mistral')
    assert len(api.llm_bodies('openrouter')) == 1 and api.llm_bodies('mistral') == []
    assert history(gn)[-1]['providers_used'] == {'openrouter': 1}

# =============================================================================
# 2. PARAMÈTRES DE REQUÊTE ET EN-TÊTES
# =============================================================================
def test_mistral_request_parameters(llm2):
    gn, api = llm2()
    text, model = gn._call_translation_api('mistral', MESSAGES, 0.1)
    method, url, headers, timeout, body = api.entries('POST', r'api\.mistral\.ai')[-1]
    assert url == 'https://api.mistral.ai/v1/chat/completions' and timeout == 120
    assert body['model'] == 'mistral-small-2603' and body['temperature'] == 0.1
    assert body['max_tokens'] == 3000 and 'max_completion_tokens' not in body
    assert body['response_format'] == {'type': 'json_object'}
    assert body['reasoning_effort'] == 'none'
    assert headers['Authorization'] == f'Bearer {MISTRAL_KEY}'
    assert model == MISTRAL_SERVED and json.loads(text) == GOOD_LLM


@pytest.mark.parametrize('env,expected', [
    ({'MISTRAL_RESPONSE_FORMAT': 'none', 'MISTRAL_REASONING_EFFORT': ''}, {}),
    ({'MISTRAL_REASONING_EFFORT': 'high'}, {'response_format': {'type': 'json_object'},
                                           'reasoning_effort': 'high'}),
    ({'MISTRAL_REASONING_EFFORT': '  '}, {'response_format': {'type': 'json_object'}}),
])
def test_mistral_optional_parameters(llm2, env, expected):
    gn, api = llm2(LLM_MAX_TOKENS='4000', **env)
    gn._call_translation_api('mistral', MESSAGES, 0.1)
    body = api.llm_bodies('mistral')[-1]
    assert body['max_tokens'] == 4000
    assert {k: body[k] for k in ('response_format', 'reasoning_effort') if k in body} == expected


def test_openrouter_request_parameters_and_no_attribution_headers(llm2):
    gn, api = llm2(LLM_PROVIDERS='openrouter')
    text, model = gn._call_translation_api('openrouter', MESSAGES, 0.1)
    method, url, headers, timeout, body = api.entries('POST', r'openrouter\.ai')[-1]
    assert url == 'https://openrouter.ai/api/v1/chat/completions' and timeout == 120
    assert body['model'] == 'openrouter/free' and body['max_completion_tokens'] == 3000
    assert 'max_tokens' not in body and 'response_format' not in body and 'provider' not in body
    assert not any(k.startswith('reasoning') for k in body)
    for header in ('HTTP-Referer', 'X-Title', 'X-OpenRouter-Title'):
        assert header not in headers
    assert headers['Authorization'] == f'Bearer {OR_KEY}'
    assert model == OR_SERVED


def test_openrouter_attribution_headers_on_request(llm2):
    gn, api = llm2(OPENROUTER_ATTRIBUTION='true')
    gn._call_translation_api('openrouter', MESSAGES, 0.1)
    headers = api.entries('POST', r'openrouter\.ai')[-1][2]
    assert headers['X-OpenRouter-Title'] == 'GitNotate'
    assert headers['HTTP-Referer'].startswith('https://github.com/')
    assert 'X-Title' not in headers


def test_openrouter_response_format_options(llm2):
    gn, api = llm2(OPENROUTER_RESPONSE_FORMAT='json_object')
    gn._call_translation_api('openrouter', MESSAGES, 0.1)
    assert api.llm_bodies('openrouter')[-1]['response_format'] == {'type': 'json_object'}
    gn, api = llm2(OPENROUTER_RESPONSE_FORMAT='JSON_SCHEMA')
    gn._call_translation_api('openrouter', MESSAGES, 0.1)
    rf = api.llm_bodies('openrouter')[-1]['response_format']
    assert rf['type'] == 'json_schema' and rf['json_schema']['strict'] is True
    schema = rf['json_schema']['schema']
    # v7.3 : schéma de la réponse v2 (jugements entiers, catégorie et type en énumération)
    assert schema['required'] == ['description_fr', 'cas_usage', 'categorie', 'type_reutilisation', 'brique_pour',
                                  'utilite_immediate', 'potentiel_futur', 'interet', 'integration',
                                  'compatibilite', 'justification']
    assert schema['properties']['potentiel_futur']['type'] == 'integer'
    assert schema['properties']['type_reutilisation']['enum'] == list(gn.REUSE_TYPES)
    assert schema['additionalProperties'] is False


@pytest.mark.parametrize('value,expected', [('deny', {'data_collection': 'deny'}), ('', None), ('allow', None)])
def test_openrouter_data_collection(llm2, value, expected):
    gn, api = llm2(OPENROUTER_DATA_COLLECTION=value)
    gn._call_translation_api('openrouter', MESSAGES, 0.1)
    assert api.llm_bodies('openrouter')[-1].get('provider') == expected


def test_scoring_uses_temperature_0_1(llm2):
    gn, api = llm2()
    gn.translate_and_score('A tool', '• x', REPO, 'o/demo')
    assert api.llm_bodies('mistral')[-1]['temperature'] == 0.1

# =============================================================================
# 3. TESTS DE DÉMARRAGE
# =============================================================================
def test_openrouter_probe_reads_quota_without_generation(world2, capsys):
    gn, api = world2()
    api.or_quota = {'used': 12, 'limit': 50, 'remaining': 38}
    assert gn.main([]) == 0
    out = capsys.readouterr().out
    assert 'quota gratuit : 38/50 (remis à zéro à minuit UTC)' in out
    (method, url, headers, timeout, params), = api.entries('GET', r'openrouter\.ai')
    assert url == 'https://openrouter.ai/api/v1/key' and headers == {'Authorization': f'Bearer {OR_KEY}'}
    assert api.entries('POST', r'openrouter\.ai') == []          # aucune requête de génération
    assert gn._provider_state('openrouter').budget == 38
    assert (gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK) == ('mistral', 'openrouter')


def test_openrouter_probe_remaining_zero_disables_for_run(world2, capsys):
    gn, api = world2()
    api.or_quota = {'used': 50, 'limit': 50, 'remaining': 0}
    api.route('POST', r'api\.mistral\.ai', lambda u, p: make_response(200, chat('safe')))
    assert gn.main([]) == 0
    err = capsys.readouterr().err               # fournisseur écarté : cause sur stderr (visible en quiet)
    assert 'quota gratuit : 0/50' in err and 'OpenRouter désactivé pour ce run' in err
    assert gn.TRANSLATION_FALLBACK is None
    assert api.entries('POST', r'openrouter\.ai') == []
    assert pages_posted(api) == [] and history(gn)[-1]['deferred_count'] == 1


@pytest.mark.parametrize('response,fragment', [
    (make_response(401, {'error': {'message': 'No auth credentials found', 'code': 401}}), 'clé invalide'),
    (make_response(500, {'error': {'message': 'Internal error'}}), 'HTTP 500 — Internal error'),
    (requests.exceptions.ConnectTimeout('lent'), 'injoignable (timeout)'),
    (requests.exceptions.ConnectionError('dns'), 'injoignable (connexion impossible)'),
])
def test_openrouter_probe_failures_never_ok(world2, response, fragment):
    gn, api = world2()
    api.route('GET', r'openrouter\.ai/api/v1/key', lambda u, p: response)
    ok, msg = gn._probe_openrouter()
    assert ok is False and fragment in msg and '✅' not in msg and 'OK' not in msg
    assert OR_KEY not in msg


def test_openrouter_probe_without_quota_field_and_paid_model(world2):
    gn, api = world2()
    api.or_quota = None
    ok, msg = gn._probe_openrouter()
    assert ok and 'quota gratuit non communiqué' in msg and gn._provider_state('openrouter').budget is None
    gn, api = world2(OPENROUTER_MODEL='mistralai/mistral-small-2603')
    api.or_quota = {'used': 50, 'limit': 50, 'remaining': 0}
    ok, msg = gn._probe_openrouter()
    assert ok and 'non applicable (modèle payant)' in msg and gn._provider_state('openrouter').budget is None


def test_openrouter_budget_decrements_then_disables(llm2, capsys):
    gn, api = llm2()
    gn._provider_state('openrouter').budget = 2
    assert gn._call_translation_api('openrouter', MESSAGES, 0.1)
    assert gn._call_translation_api('openrouter', MESSAGES, 0.1)
    assert gn._call_translation_api('openrouter', MESSAGES, 0.1) is None
    assert len(api.llm_bodies('openrouter')) == 2
    state = gn._provider_state('openrouter')
    assert state.available is False and 'quota gratuit du jour épuisé' in state.disabled_reason
    assert 'désactivé pour la suite du run' in capsys.readouterr().err


def test_mistral_probe_uses_production_parameters(world2):
    gn, api = world2(OPENROUTER_API_KEY=None)
    ok, msg = gn._probe_mistral()
    assert ok and msg.startswith('✅') and 'OK' in msg
    (method, url, headers, timeout, body), = api.entries('POST', r'api\.mistral\.ai')
    assert body['max_tokens'] == 16 and body['model'] == 'mistral-small-2603'
    assert body['response_format'] == {'type': 'json_object'} and body['reasoning_effort'] == 'none'
    assert body['temperature'] == 0.1 and timeout == 30


def test_mistral_probe_400_reasoning_retries_without_parameter(world2, capsys):
    gn, api = world2(OPENROUTER_API_KEY=None)

    def mistral(url, payload):
        if 'reasoning_effort' in payload:
            return make_response(400, {'object': 'error', 'type': 'invalid_request_error',
                                       'message': 'Invalid parameter: reasoning_effort is not supported'})
        return make_response(200, chat(GOOD_JSON, model=MISTRAL_SERVED))
    api.route('POST', r'api\.mistral\.ai', mistral)
    assert gn.main([]) == 0
    probes = [e[4] for e in api.entries('POST', r'api\.mistral\.ai') if e[4]['max_tokens'] == 16]
    assert len(probes) == 2 and 'reasoning_effort' in probes[0] and 'reasoning_effort' not in probes[1]
    assert 'response_format' in probes[1]
    production = api.llm_bodies('mistral')
    assert len(production) == 1 and 'reasoning_effort' not in production[0]   # choix mémorisé
    out = capsys.readouterr().out
    assert 'paramètre reasoning_effort refusé (HTTP 400 — Invalid parameter' in out
    assert 'sans reasoning_effort, mémorisé pour ce run' in out
    assert len(pages_posted(api)) == 1


def test_mistral_probe_422_response_format_retries_without_parameter(world2):
    gn, api = world2(OPENROUTER_API_KEY=None)

    def mistral(url, payload):
        if 'response_format' in payload:
            return make_response(422, {'object': 'error', 'message': {'detail': [
                {'type': 'extra_forbidden', 'loc': ['body', 'response_format'],
                 'msg': 'Extra inputs are not permitted'}]}, 'type': 'invalid_request_error'})
        return make_response(200, chat(GOOD_JSON))
    api.route('POST', r'api\.mistral\.ai', mistral)
    ok, msg = gn._probe_mistral()
    assert ok and 'sans response_format' in msg
    gn.TRANSLATION_PROVIDER = 'mistral'
    gn._call_translation_api('mistral', MESSAGES, 0.1)
    body = api.llm_bodies('mistral')[-1]
    assert 'response_format' not in body and body['reasoning_effort'] == 'none'


@pytest.mark.parametrize('response,ok,fragment', [
    (make_response(401, {'message': 'Unauthorized'}), False, 'clé invalide (HTTP 401 — Unauthorized'),
    (make_response(404, {'message': "Invalid model: mistral-small-2603"}), False,
     "modèle 'mistral-small-2603' introuvable (HTTP 404 — Invalid model: mistral-small-2603)"),
    (make_response(400, {'message': 'Prompt is too long'}), False, 'requête refusée (HTTP 400 — Prompt is too long)'),
    (make_response(503, {'message': 'Service unavailable'}), False, 'indisponible (HTTP 503'),
    (requests.exceptions.ReadTimeout('lent'), False, 'indisponible (timeout)'),
    (requests.exceptions.ConnectionError('dns'), False, 'indisponible (connexion impossible)'),
    (make_response(429, {'message': 'Requests rate limit exceeded'}), True,
     'joignable mais limité (HTTP 429 — Requests rate limit exceeded) : gardé actif'),
])
def test_mistral_probe_outcomes(world2, response, ok, fragment):
    gn, api = world2(OPENROUTER_API_KEY=None)
    api.route('POST', r'api\.mistral\.ai', lambda u, p: response)
    result, msg = gn._probe_mistral()
    assert result is ok and fragment in msg
    if not ok:
        assert '✅' not in msg and ' OK' not in msg
    assert MISTRAL_KEY not in msg
    # un seul nouvel essai, et seulement sur incident passager (5xx, timeout, coupure)
    transient = isinstance(response, requests.exceptions.RequestException) or response.status_code >= 500
    assert len(api.entries('POST', r'api\.mistral\.ai')) == (2 if transient else 1)


def test_mistral_probe_failure_is_logged_as_error(world2, capsys):
    gn, api = world2()
    api.route('POST', r'api\.mistral\.ai', lambda u, p: make_response(401, {'message': 'Unauthorized'}))
    assert gn.init_translation_providers() == ('openrouter', None)
    cap = capsys.readouterr()
    assert 'Mistral AI (mistral-small-2603) — clé invalide' in cap.err
    assert 'Stratégie: OpenRouter (openrouter/free) uniquement' in cap.out

# =============================================================================
# 4. TRAÇABILITÉ : MODÈLE RÉEL, EMPREINTE DU PROFIL, STATISTIQUES
# =============================================================================
def test_call_translation_api_returns_served_model(llm2):
    gn, api = llm2(openrouter=lambda u, p: make_response(200, chat(GOOD_JSON, model=OR_SERVED)))
    assert gn._call_translation_api('openrouter', MESSAGES, 0.1) == (GOOD_JSON, OR_SERVED)
    body = chat(GOOD_JSON)
    del body['model']
    gn, api = llm2(openrouter=lambda u, p: make_response(200, body))
    assert gn._call_translation_api('openrouter', MESSAGES, 0.1) == (GOOD_JSON, 'openrouter/free')


def test_translate_and_score_reports_provider_model_and_status(llm2):
    gn, api = llm2(mistral=lambda u, p: make_response(200, chat('safe')))
    result = gn.translate_and_score('A tool', '• x', REPO, 'o/demo')
    assert (result['provider'], result['model'], result['llm_status']) == ('openrouter', OR_SERVED, 'ok')
    assert result['profile_hash'] == gn.compute_profile_hash() and len(result['profile_hash']) == 6


def test_profile_hash_definition(load_gn):
    gn = load_gn()
    canonical = json.dumps(gn.USER_PROFILE, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    # v7.4 : les règles de calcul du code (SCORING_RULES) font partie de l'empreinte
    expected = hashlib.sha1((canonical + gn.build_system_prompt_combined() + gn.SCORING_RULES)
                            .encode('utf-8')).hexdigest()[:6]
    assert gn.compute_profile_hash() == expected
    gn.USER_PROFILE = {'languages': ['Go']}
    assert gn.compute_profile_hash() != expected
    gn = load_gn(LLM_SCORING_ENABLED='false')
    assert gn.compute_profile_hash() != expected                     # autre prompt système


def test_justification_prefixed_with_served_model_and_profile(world2, capsys):
    gn, api = world2(LLM_PROVIDERS='openrouter')
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    text = justification(page)
    profile_hash = gn.compute_profile_hash()
    # v7.3 : version du profil et détail des sept critères (maturité et licence non vérifiées ici)
    assert text == f"[LLM {OR_SERVED} · profil v1/{profile_hash}] U0·P2·T2·I1·C2·M?·L? = 7 — pertinent pour le profil"
    assert f"(empreinte {profile_hash})" in capsys.readouterr().out
    assert history(gn)[-1]['profile_hash'] == profile_hash


def test_lexical_justification_prefix_when_require_llm_false(world2):
    gn, api = world2(REQUIRE_LLM='false')
    api.route('POST', r'api\.mistral\.ai', lambda u, p: make_response(200, chat('pas de json')))
    api.route('POST', r'openrouter\.ai/api/v1/chat', lambda u, p: make_response(200, chat('safe')))
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert justification(page) == f"[LEXICAL · profil v1/{gn.compute_profile_hash()}]"


def test_stats_models_used_and_console_summary(world2, capsys):
    gn, api = world2()
    api.set_page_urls(['https://github.com/owner/a', 'https://github.com/owner/b'])
    answers = iter([make_response(200, chat(GOOD_JSON, model=MISTRAL_SERVED)),
                    make_response(200, chat('safe', model=MISTRAL_SERVED))])
    api.route('POST', r'api\.mistral\.ai',
              lambda u, p: make_response(200, chat('{}')) if p['max_tokens'] == 16 else next(answers))
    assert gn.main([]) == 0
    last = history(gn)[-1]
    assert last['models_used'] == {MISTRAL_SERVED: 1, OR_SERVED: 1}
    assert last['providers_used'] == {'mistral': 1, 'openrouter': 1}
    assert 'model_used' not in last
    assert last['llm_providers'] == ['mistral', 'openrouter'] and last['require_llm'] is True
    out = capsys.readouterr().out
    assert f'Modèles LLM:     {OR_SERVED} ×1, {MISTRAL_SERVED} ×1' in out      # égalité : ordre alphabétique

# =============================================================================
# 11. SCÉNARIOS S1-S9 (prototype t_freerouter.py), ordre Mistral → OpenRouter
# =============================================================================
THINKING_BLOCKS = [
    {'type': 'thinking', 'thinking': [{'type': 'text', 'text': '{"description_fr": "piège"}'}]},
    {'type': 'text', 'text': GOOD_JSON},
]
S_SCENARIOS = [
    # (libellé, réponse Mistral, fournisseur retenu, modèle tracé, appels Mistral)
    ('S1 content null + length', make_response(200, chat(None, finish='length')), 'openrouter', OR_SERVED, 1),
    ('S2 vide + length', make_response(200, chat('', finish='length')), 'openrouter', OR_SERVED, 1),
    ('S3 réponse non JSON « safe »', make_response(200, chat('safe')), 'openrouter', OR_SERVED, 1),
    ('S4 blocs thinking + text', make_response(200, chat(THINKING_BLOCKS, model=MISTRAL_SERVED)),
     'mistral', MISTRAL_SERVED, 1),
    ('S5 bloc ```json, modèle tracé', make_response(200, chat('```json\n' + GOOD_JSON + '\n```',
                                                               model='mistral-small-2603-v2')),
     'mistral', 'mistral-small-2603-v2', 1),
    ('S6 200 avec corps error', make_response(200, {'error': {'code': 502, 'message': 'Provider error'}}),
     'openrouter', OR_SERVED, 1),
    ('S7 429 répété', make_response(429, {'message': 'rate limited'}), 'openrouter', OR_SERVED, 2),
    ('S8 score chaîne "7"', make_response(200, chat(json.dumps(dict(GOOD_LLM, potentiel_futur='2')),
                                                    model=MISTRAL_SERVED)),
     'mistral', MISTRAL_SERVED, 1),
    ('JSON complet mais length', make_response(200, chat(GOOD_JSON, finish='length')), 'openrouter', OR_SERVED, 1),
    ('score booléen refusé', make_response(200, chat(json.dumps(dict(GOOD_LLM, interet=True)))),
     'openrouter', OR_SERVED, 1),
    ('5xx répété', make_response(502, {'message': 'Bad gateway'}), 'openrouter', OR_SERVED, 2),
    ('timeout', requests.exceptions.ReadTimeout('lent'), 'openrouter', OR_SERVED, 1),
]


@pytest.mark.parametrize('label,response,provider,model,mistral_calls', S_SCENARIOS,
                         ids=[s[0] for s in S_SCENARIOS])
def test_s_scenarios_mistral_then_openrouter(llm2, label, response, provider, model, mistral_calls):
    gn, api = llm2(mistral=lambda u, p: response)
    result = gn.translate_and_score('A tool', '• x', dict(REPO, language=None), 'o/demo')
    assert (result['provider'], result['model'], result['llm_status']) == (provider, model, 'ok')
    assert result['score'] == 7 and result['scoring_method'] == 'llm'
    assert result['description_fr'].startswith('Un outil')
    assert len(api.llm_bodies('mistral')) == mistral_calls
    assert len(api.llm_bodies('openrouter')) == (1 if provider == 'openrouter' else 0)


def test_s5_openrouter_router_model_is_traced(llm2):
    gn, api = llm2(LLM_PROVIDERS='openrouter,mistral', openrouter=lambda u, p: make_response(
        200, chat('```json\n' + GOOD_JSON + '\n```', model='qwen/qwen3-coder:free')))
    result = gn.translate_and_score('A tool', '• x', REPO, 'o/demo')
    assert (result['provider'], result['model']) == ('openrouter', 'qwen/qwen3-coder:free')
    props = gn.build_page_properties(REPO, 'https://github.com/o/demo', gn.analyze_repo_for_usage(REPO),
                                     result, True)
    assert props['Justification']['rich_text'][0]['text']['content'].startswith(
        f"[LLM qwen/qwen3-coder:free · profil v1/{result['profile_hash']}]")


def test_s9_truncated_json_without_fallback_is_deferred(world2, capsys):
    gn, api = world2(OPENROUTER_API_KEY=None)
    api.repos['owner/repo']['language'] = None
    api.route('POST', r'api\.mistral\.ai', lambda u, p: make_response(200, chat('{}')) if p['max_tokens'] == 16
              else make_response(200, chat('{"description_fr": "Outil', finish='length')))
    assert gn.main([]) == 0
    assert pages_posted(api) == []
    assert history(gn)[-1]['deferred_by_reason'] == {'aucune réponse LLM valide': 1}
    assert '1 dépôt reporté au prochain run' in capsys.readouterr().err

# =============================================================================
# 5. MODE REPRISE
# =============================================================================
def test_no_page_when_no_llm_answers(world2, capsys):
    gn, api = world2()
    api.route('POST', r'api\.mistral\.ai',
              lambda u, p: make_response(200, chat('{}')) if p['max_tokens'] == 16 else make_response(200, chat('safe')))
    api.route('POST', r'openrouter\.ai/api/v1/chat', lambda u, p: make_response(200, chat(None, finish='length')))
    assert gn.main([]) == 0
    assert api.entries('POST', r'/v1/pages') == []
    assert gn.stats.deferred == 1 and gn.stats.success == 0 and gn.stats.errors == 0
    cap = capsys.readouterr()
    assert 'reporté au prochain run (aucune réponse LLM valide) : aucune fiche écrite' in cap.out
    assert 'Reportés:        1' in cap.out
    assert "1 dépôt reporté au prochain run (aucune réponse LLM valide : 1)" in cap.err
    last = history(gn)[-1]
    assert last['deferred_count'] == 1 and last['exit_code'] == 0 and last['success_count'] == 0


def test_partial_llm_answer_is_deferred_not_degraded(world2):
    gn, api = world2(OPENROUTER_API_KEY=None)
    bad_score = json.dumps(dict(GOOD_LLM, interet='beaucoup'))
    api.route('POST', r'api\.mistral\.ai',
              lambda u, p: make_response(200, chat('{}')) if p['max_tokens'] == 16 else make_response(200, chat(bad_score)))
    assert gn.main([]) == 0
    assert pages_posted(api) == [] and gn.stats.deferred == 1


def test_translation_only_mode_is_not_deferred(world2):
    gn, api = world2(LLM_SCORING_ENABLED='false', OPENROUTER_API_KEY=None)
    api.mistral_content = json.dumps({'description_fr': 'Un outil', 'use_cases_fr': '• a'})
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert justification(page).startswith('[LEXICAL · profil ')
    assert page['properties']['Description']['rich_text'][0]['text']['content'] == 'Un outil'


@pytest.mark.parametrize('env,routes', [
    ({'MISTRAL_API_KEY': None, 'OPENROUTER_API_KEY': None}, {}),
    ({}, {'mistral': make_response(401, {'message': 'Unauthorized'}),
          'key': make_response(200, {'data': {'free_model_daily_requests':
                                              {'used': 50, 'limit': 50, 'remaining': 0}}})}),
])
def test_stop_before_github_when_no_provider(world2, capsys, env, routes):
    gn, api = world2(GITHUB_TOKEN='ghp_valid_token_1234', **env)
    if 'mistral' in routes:
        api.route('POST', r'api\.mistral\.ai', lambda u, p: routes['mistral'])
    if 'key' in routes:
        api.route('GET', r'openrouter\.ai/api/v1/key', lambda u, p: routes['key'])
    assert gn.main([]) == 1
    assert api.entries('GET', r'api\.github\.com') == []
    assert api.entries('GET', r'api\.notion\.com') == [] and api.entries('POST', r'api\.notion\.com') == []
    assert "Aucun fournisseur LLM disponible : rien n'est écrit" in capsys.readouterr().err
    assert not gn.STATS_FILE.exists() and not gn.URLS_FILE.exists()


def test_require_llm_false_keeps_historical_lexical_page(world2):
    gn, api = world2(MISTRAL_API_KEY=None, OPENROUTER_API_KEY=None, REQUIRE_LLM='false')
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert justification(page).startswith('[LEXICAL · profil ')
    assert history(gn)[-1]['require_llm'] is False


def test_translation_disabled_ignores_require_llm(world2):
    gn, api = world2(TRANSLATION_ENABLED='false')
    assert gn.main([]) == 0
    assert len(pages_posted(api)) == 1
    assert api.entries('POST', r'api\.mistral\.ai') == [] and api.entries('GET', r'openrouter\.ai') == []


def test_deferred_plus_error_exits_2(world2):
    gn, api = world2(OPENROUTER_API_KEY=None)
    api.set_page_urls(['https://github.com/owner/repo', 'https://github.com/ghost/missing'])
    api.route('POST', r'api\.mistral\.ai',
              lambda u, p: make_response(200, chat('{}')) if p['max_tokens'] == 16 else make_response(200, chat('safe')))
    assert gn.main([]) == 2
    assert gn.stats.deferred == 1 and gn.stats.errors == 1


@pytest.mark.parametrize('value,expected', [('false', False), (' FALSE ', False), ('true', True),
                                            ('0', True), ('non', True), ('', True)])
def test_require_llm_only_explicit_false_disables(load_gn, value, expected):
    assert load_gn(REQUIRE_LLM=value).REQUIRE_LLM is expected

# =============================================================================
# 6. COUPE-CIRCUIT
# =============================================================================
@pytest.mark.parametrize('provider,status', [('mistral', 401), ('mistral', 402),
                                             ('openrouter', 401), ('openrouter', 402)])
def test_breaker_disables_on_401_402(llm2, capsys, provider, status):
    response = make_response(status, {'error': {'message': 'refusé'}})
    gn, api = llm2(**{provider: lambda u, p: response})
    assert gn._call_translation_api(provider, MESSAGES, 0.1) is None
    assert gn._call_translation_api(provider, MESSAGES, 0.1) is None
    assert len(api.llm_bodies(provider)) == 1 and api.sleeps == []
    assert gn._provider_state(provider).available is False
    assert f'HTTP {status}' in gn._provider_state(provider).disabled_reason


@pytest.mark.parametrize('response', [
    make_response(429, {'error': {'code': 429, 'message': 'Rate limit exceeded'}},
                  {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(int((time.time() + 5 * 3600) * 1000))}),
    make_response(429, {'error': {'code': 429, 'message': 'Rate limit exceeded: free-models-per-day. '
                                                         'Add 10 credits to unlock 1000 free model requests per day'}}),
])
def test_breaker_openrouter_quota_429(llm2, response):
    gn, api = llm2(LLM_PROVIDERS='openrouter,mistral', openrouter=lambda u, p: response)
    first = gn.translate_and_score('A tool', '• x', REPO, 'o/a')
    second = gn.translate_and_score('A tool', '• x', REPO, 'o/b')
    assert first['provider'] == second['provider'] == 'mistral'
    assert len(api.llm_bodies('openrouter')) == 1                            # ni nouvelle tentative ni 2e appel
    assert 'quota OpenRouter épuisé' in gn._provider_state('openrouter').disabled_reason


def test_mistral_429_with_remaining_zero_is_not_a_quota_disable(llm2):
    response = make_response(429, {'message': 'rate'}, {'X-RateLimit-Remaining': '0'})
    gn, api = llm2(mistral=lambda u, p: response)
    assert gn._call_translation_api('mistral', MESSAGES, 0.1) is None
    assert gn._provider_state('mistral').available is True
    assert len(api.llm_bodies('mistral')) == 2


def test_breaker_after_consecutive_invalid_answers(llm2):
    gn, api = llm2(LLM_PROVIDERS='mistral')
    answers = []
    api.route('POST', r'api\.mistral\.ai', lambda u, p: make_response(200, chat(answers.pop(0))))
    state = gn._provider_state('mistral')
    for content in ('safe', 'safe', GOOD_JSON, 'safe', 'safe'):        # un succès remet à zéro
        answers.append(content)
        gn.translate_and_score('A tool', '• x', REPO, 'o/demo')
    assert state.available and state.consecutive_failures == 2
    answers.append('safe')
    gn.translate_and_score('A tool', '• x', REPO, 'o/demo')
    assert not state.available and '3 échecs consécutifs' in state.disabled_reason
    before = len(api.llm_bodies('mistral'))
    result = gn.translate_and_score('A tool', '• x', REPO, 'o/demo')
    assert len(api.llm_bodies('mistral')) == before and result['llm_status'] == 'unavailable'


def test_breaker_threshold_configurable_and_counts_http_failures(llm2):
    gn, api = llm2(LLM_PROVIDERS='mistral', LLM_BREAKER_THRESHOLD='1',
                   mistral=lambda u, p: requests.exceptions.ReadTimeout('lent'))
    gn.translate_and_score('A tool', '• x', REPO, 'o/demo')
    assert '1 échecs consécutifs (dernier : timeout)' in gn._provider_state('mistral').disabled_reason


def test_breaker_is_thread_safe(load_gn, capsys):
    gn = load_gn()
    state = gn._provider_state('mistral')
    barrier = threading.Barrier(16)

    def fail():
        barrier.wait()
        state.record_failure('x')
    threads = [threading.Thread(target=fail) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert state.consecutive_failures == 16 and not state.available
    assert capsys.readouterr().err.count('désactivé pour la suite du run') == 1


def test_all_providers_disabled_defers_remaining_without_github(world2, capsys):
    gn, api = world2(LLM_PROVIDERS='openrouter', MISTRAL_API_KEY=None)
    api.set_page_urls([f'https://github.com/owner/r{i}' for i in range(4)])
    far_reset = str(int((time.time() + 5 * 3600) * 1000))             # quota du jour : remise à zéro lointaine
    api.route('POST', r'openrouter\.ai/api/v1/chat', lambda u, p: make_response(
        429, {'error': {'message': 'Rate limit exceeded'}},
        {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': far_reset}))
    assert gn.main([]) == 0
    assert len(api.entries('GET', r'/repos/owner/r0')) == 2               # métadonnées + README
    assert api.entries('GET', r'/repos/owner/r[123]') == []                # aucun appel GitHub ensuite
    assert len(api.llm_bodies('openrouter')) == 1 and pages_posted(api) == []
    cap = capsys.readouterr()
    assert cap.err.count('Plus aucun fournisseur LLM disponible') == 1     # un seul message
    assert '4 dépôts reportés au prochain run' in cap.err
    last = history(gn)[-1]
    assert last['deferred_by_reason'] == {'aucun fournisseur LLM disponible': 3, 'aucune réponse LLM valide': 1}
    assert 'quota OpenRouter épuisé' in last['llm_disabled']['openrouter']


def test_breaker_with_require_llm_false_continues_lexically(world2):
    gn, api = world2(LLM_PROVIDERS='openrouter', MISTRAL_API_KEY=None, REQUIRE_LLM='false')
    api.set_page_urls([f'https://github.com/owner/r{i}' for i in range(3)])
    api.route('POST', r'openrouter\.ai/api/v1/chat', lambda u, p: make_response(402, {'error': {'message': 'x'}}))
    assert gn.main([]) == 0
    assert len(pages_posted(api)) == 3 and len(api.llm_bodies('openrouter')) == 1

# =============================================================================
# 7. PRÉ-CONTRÔLE « DÉJÀ PRÉSENT » ET MAX_NEW_PER_RUN
# =============================================================================
def test_already_present_detected_without_github_call(world2, capsys):
    gn, api = world2(GITHUB_TOKEN='ghp_valid_token_1234')
    api.query_pages = [[existing_page('https://github.com/Owner/Repo')]]
    api.set_page_urls(['https://github.com/owner/repo/tree/main'])
    assert gn.main([]) == 0
    assert api.entries('GET', r'/repos/') == [] and api.llm_bodies('mistral') == []
    assert 'Déjà présents:   1' in capsys.readouterr().out


def test_renamed_repo_still_detected_after_github_call(world2, capsys):
    gn, api = world2()
    api.query_pages = [[existing_page('https://github.com/neworg/tool')]]
    api.set_page_urls(['https://github.com/oldowner/tool'])
    api.repos['oldowner/tool'] = repo_data('neworg', 'tool')
    assert gn.main([]) == 0
    assert len(api.entries('GET', r'/repos/oldowner/tool$')) == 1
    assert pages_posted(api) == [] and api.llm_bodies('mistral') == []
    assert 'Déjà présents:   1' in capsys.readouterr().out


def test_max_new_per_run_defers_rest_without_github(world2, capsys):
    gn, api = world2(MAX_NEW_PER_RUN='1')
    api.set_page_urls([f'https://github.com/owner/r{i}' for i in range(3)])
    assert gn.main([]) == 0
    assert len(pages_posted(api)) == 1
    assert api.entries('GET', r'/repos/owner/r[12]') == []
    cap = capsys.readouterr()
    assert cap.out.count('MAX_NEW_PER_RUN=1 atteint') == 1
    assert '2 dépôts reportés au prochain run (MAX_NEW_PER_RUN atteint : 2)' in cap.err
    assert history(gn)[-1]['max_new_per_run'] == 1


def test_max_new_slot_released_when_nothing_written(world2):
    gn, api = world2(MAX_NEW_PER_RUN='1')
    api.set_page_urls(['https://github.com/owner/private', 'https://github.com/ghost/gone',
                       'https://github.com/owner/ok', 'https://github.com/owner/late'])
    api.repos['owner/private']['private'] = True
    assert gn.main([]) == 2                                                # ghost/gone : erreur GitHub
    (page,) = pages_posted(api)
    assert page['properties']['Nom']['title'][0]['text']['content'] == 'ok'
    assert gn.stats.deferred == 1 and api.entries('GET', r'/repos/owner/late') == []


def test_new_repo_budget_thread_safe(load_gn):
    gn = load_gn()
    budget = gn.NewRepoBudget(5)
    barrier = threading.Barrier(20)
    results = []

    def take():
        barrier.wait()
        ok = budget.acquire()
        results.append(ok)
        if ok:
            budget.commit()                    # fiche écrite : la place est définitivement utilisée
    threads = [threading.Thread(target=take, daemon=True) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert results.count(True) == 5 and results.count(False) == 15
    assert (budget.committed, budget.reserved) == (5, 0)
    assert budget.acquire() is False
    assert gn.NewRepoBudget(0).acquire() is True


def test_new_repo_budget_waits_for_reserved_slot(load_gn):
    """Places seulement réservées : le dépôt suivant attend leur issue au lieu d'être reporté."""
    gn = load_gn()
    budget = gn.NewRepoBudget(1)
    assert budget.acquire() is True
    got = []
    waiter = threading.Thread(target=lambda: got.append(budget.acquire()), daemon=True)
    waiter.start()
    waiter.join(0.2)
    assert waiter.is_alive() and got == []        # en attente, pas refusé
    budget.release()                              # 1er dépôt sans fiche : place rendue
    waiter.join(5)
    assert got == [True]
    budget.commit()                               # 2e dépôt : fiche écrite
    assert budget.acquire() is False              # limite atteinte par des fiches écrites


def test_new_repo_budget_wait_stops_on_ctrl_c(load_gn):
    gn = load_gn()
    budget = gn.NewRepoBudget(1)
    assert budget.acquire() is True
    got = []
    waiter = threading.Thread(target=lambda: got.append(budget.acquire()), daemon=True)
    waiter.start()
    gn._STOP_EVENT.set()
    try:
        waiter.join(5)
        assert got == [False]
    finally:
        gn._STOP_EVENT.clear()

# =============================================================================
# 8. TIMEOUT, NOUVELLES TENTATIVES, LIMITEUR DE DÉBIT
# =============================================================================
def test_llm_timeout_and_no_retry_on_timeout(llm2):
    gn, api = llm2(LLM_TIMEOUT='45', mistral=lambda u, p: requests.exceptions.ReadTimeout('lent'))
    result = gn.translate_and_score('A tool', '• x', REPO, 'o/demo')
    mistral_calls = api.entries('POST', r'api\.mistral\.ai')
    assert len(mistral_calls) == 1 and mistral_calls[0][3] == 45
    assert result['provider'] == 'openrouter' and api.entries('POST', r'openrouter\.ai')[0][3] == 45


def test_llm_429_retried_once_after_retry_after(llm2):
    gn, api = llm2(mistral=sequence(make_response(429, {'message': 'rate'}, {'Retry-After': '5'}),
                                    make_response(200, chat(GOOD_JSON))))
    assert gn._call_translation_api('mistral', MESSAGES, 0.1)
    assert len(api.llm_bodies('mistral')) == 2 and 5 in api.sleeps
    gn, api = llm2(mistral=lambda u, p: make_response(429, {'message': 'rate'}, {'Retry-After': '1'}))
    assert gn._call_translation_api('mistral', MESSAGES, 0.1) is None
    assert len(api.llm_bodies('mistral')) == 2                            # au plus 1 nouvelle tentative
    assert gn._provider_state('mistral').consecutive_failures == 1


def test_llm_retry_after_above_60s_is_not_waited(llm2):
    gn, api = llm2(mistral=lambda u, p: make_response(429, {'message': 'rate'}, {'Retry-After': '120'}))
    assert gn._call_translation_api('mistral', MESSAGES, 0.1) is None
    assert len(api.llm_bodies('mistral')) == 1 and 120 not in api.sleeps


def test_llm_5xx_retried_once(llm2):
    gn, api = llm2(mistral=sequence(make_response(503, {'message': 'down'}), make_response(200, chat(GOOD_JSON))))
    assert gn._call_translation_api('mistral', MESSAGES, 0.1)
    assert len(api.llm_bodies('mistral')) == 2
    gn, api = llm2(mistral=lambda u, p: make_response(500, {'message': 'down'}))
    assert gn._call_translation_api('mistral', MESSAGES, 0.1) is None
    assert len(api.llm_bodies('mistral')) == 2


def test_llm_4xx_not_retried(llm2):
    gn, api = llm2(mistral=lambda u, p: make_response(400, {'message': 'bad request'}))
    assert gn._call_translation_api('mistral', MESSAGES, 0.1) is None
    assert len(api.llm_bodies('mistral')) == 1


def test_rate_limiter_min_interval(load_gn, monkeypatch):
    gn = load_gn(MISTRAL_RPM='60', OPENROUTER_RPM='18')
    sleeps = []
    monkeypatch.setattr(gn.time, 'sleep', sleeps.append)
    monkeypatch.setattr(gn.time, 'monotonic', lambda: 1000.0)
    mistral = gn._provider_state('mistral')
    for _ in range(3):
        mistral.wait_turn()
    assert sleeps == [1.0, 2.0]
    sleeps.clear()
    openrouter = gn._provider_state('openrouter')
    openrouter.wait_turn()
    openrouter.wait_turn()
    assert sleeps == [pytest.approx(60 / 18)]
    sleeps.clear()
    gn = load_gn(MISTRAL_RPM='0')
    gn._provider_state('mistral').wait_turn()
    gn._provider_state('mistral').wait_turn()
    assert sleeps == []


def test_rate_limiter_thread_safe_slots(load_gn, monkeypatch):
    gn = load_gn(OPENROUTER_RPM='30')
    sleeps, lock = [], threading.Lock()

    def record(s):
        with lock:
            sleeps.append(s)
    monkeypatch.setattr(gn.time, 'sleep', record)
    monkeypatch.setattr(gn.time, 'monotonic', lambda: 50.0)
    state = gn._provider_state('openrouter')
    threads = [threading.Thread(target=state.wait_turn) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert sorted(sleeps) == [pytest.approx(2.0 * i) for i in range(1, 10)]   # créneaux distincts

# =============================================================================
# 10. scripts/check_llm.py
# =============================================================================
def load_check_llm():
    spec = importlib.util.spec_from_file_location('check_llm_under_test', ROOT / 'scripts' / 'check_llm.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_llm_import_has_no_side_effects(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv('GITNOTATE_NO_DOTENV')
    (tmp_path / '.env').write_text(f'MISTRAL_API_KEY={MISTRAL_KEY}\n', encoding='utf-8')
    module = load_check_llm()
    assert 'MISTRAL_API_KEY' not in os.environ                      # .env lu seulement par main()
    assert capsys.readouterr().out == ''
    assert module.BASE_DIR == tmp_path and callable(module.main)
    source = (ROOT / 'scripts' / 'check_llm.py').read_text(encoding='utf-8')
    assert "if __name__ == '__main__':" in source


def test_check_llm_mask_never_reveals_more_than_4_plus_4(monkeypatch):
    module = load_check_llm()
    assert module.mask(OR_KEY) == 'sk-o...cdef'
    assert module.mask('  ' + MISTRAL_KEY + '\n') == 'mist...5678'
    for short in ('', None, 'abc', '12345678901'):
        assert module.mask(short) == '****'
    masked = module.mask(OR_KEY)
    assert len(masked.replace('...', '')) == 8 and OR_KEY[4:-4] not in masked


def _check_env(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_check_llm_main_ok_without_generation(monkeypatch, capsys):
    module = load_check_llm()
    _check_env(monkeypatch, OPENROUTER_API_KEY=OR_KEY, MISTRAL_API_KEY=MISTRAL_KEY)
    calls = []

    def fake_get(url, headers):
        calls.append((url, headers))
        if 'openrouter' in url:
            return make_response(200, {'data': {'free_model_daily_requests': {'used': 3, 'limit': 50, 'remaining': 47}}})
        return make_response(200, {'object': 'list', 'data': [
            {'id': 'mistral-small-4-0-26-03', 'aliases': ['mistral-small-2603', 'mistral-small-latest']},
            {'id': 'mistral-large-2512', 'aliases': []}]})
    monkeypatch.setattr(module, '_http_get', fake_get)
    assert module.main() == 0
    assert [u for u, _ in calls] == ['https://api.mistral.ai/v1/models', 'https://openrouter.ai/api/v1/key']
    out = capsys.readouterr().out
    assert 'quota gratuit : 47/50 restantes (3 utilisées)' in out
    assert "modèle 'mistral-small-2603' disponible" in out
    assert OR_KEY not in out and MISTRAL_KEY not in out and 'sk-o...cdef' in out


@pytest.mark.parametrize('openrouter,mistral,expected', [
    (make_response(401, {'error': {'message': 'No auth credentials found'}}), None, 'clé invalide (HTTP 401'),
    (None, make_response(200, {'data': [{'id': 'open-mistral-nemo', 'aliases': []}]}),
     "modèle 'mistral-small-2603' absent"),
    (requests.exceptions.ConnectionError('dns'), None, 'injoignable (connexion impossible)'),
])
def test_check_llm_main_failures(monkeypatch, capsys, openrouter, mistral, expected):
    module = load_check_llm()
    env = {}
    if openrouter is not None:
        env['OPENROUTER_API_KEY'] = OR_KEY
    if mistral is not None:
        env['MISTRAL_API_KEY'] = MISTRAL_KEY
    _check_env(monkeypatch, **env)

    def fake_get(url, headers):
        response = openrouter if 'openrouter' in url else mistral
        if isinstance(response, BaseException):
            raise response
        return response
    monkeypatch.setattr(module, '_http_get', fake_get)
    assert module.main() == 1
    assert expected in capsys.readouterr().out


def test_check_llm_no_key_and_quota_exhausted(monkeypatch, capsys):
    module = load_check_llm()
    assert module.main() == 1
    assert 'Aucune clé trouvée' in capsys.readouterr().out
    _check_env(monkeypatch, OPENROUTER_API_KEY=OR_KEY)
    monkeypatch.setattr(module, '_http_get', lambda url, headers: make_response(
        200, {'data': {'free_model_daily_requests': {'used': 50, 'limit': 50, 'remaining': 0}}}))
    assert module.main() == 0
    assert 'quota gratuit du jour épuisé' in capsys.readouterr().out


def test_check_llm_reads_env_from_base_dir(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv('GITNOTATE_NO_DOTENV')
    (tmp_path / '.env').write_text(f'MISTRAL_API_KEY={MISTRAL_KEY}\nMISTRAL_MODEL=mistral-large-2512\n',
                                   encoding='utf-8')
    for key in ('MISTRAL_API_KEY', 'MISTRAL_MODEL'):     # restaurés (absents) en fin de test
        monkeypatch.setenv(key, 'x')
        monkeypatch.delenv(key)
    module = load_check_llm()
    monkeypatch.setattr(module, '_http_get', lambda url, headers: make_response(
        200, {'data': [{'id': 'mistral-large-2512'}]}))
    assert module.main() == 0
    assert "modèle 'mistral-large-2512' disponible" in capsys.readouterr().out
