"""Contrats des API natives OpenAI/Anthropic — aucune requête réseau réelle.

Les clés sont factices ; tests sans Notion, sans génération facturée ni secrets réels.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


MESSAGES = [
    {'role': 'system', 'content': 'Réponds en JSON.'},
    {'role': 'user', 'content': 'Décris ce dépôt.'},
]


class FakeResponse:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status
        self.headers = {}
        self.text = ''

    def json(self):
        return self.data


def test_ancien_ordre_et_nouveaux_fournisseurs_sur_option(load_gn):
    gn = load_gn()
    assert gn.LLM_PROVIDERS == ['mistral', 'openrouter']
    assert gn.configured_providers() == []
    gn = load_gn(LLM_PROVIDERS='openai,anthropic,mistral,openrouter',
                 OPENAI_API_KEY='test-openai-key', ANTHROPIC_API_KEY='test-anthropic-key')
    assert gn.LLM_PROVIDERS == ['openai', 'anthropic', 'mistral', 'openrouter']
    assert gn._provider_key('openai') == 'test-openai-key'
    assert gn._provider_key('anthropic') == 'test-anthropic-key'
    assert gn._provider_model('openai') == 'gpt-6-luna'
    assert gn._provider_model('anthropic') == 'claude-sonnet-4-6'


def test_conservation_compatibilite_deux_fournisseurs(load_gn):
    gn = load_gn()
    gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK = 'mistral', 'openrouter'
    assert gn.configured_providers() == ['mistral', 'openrouter']


def test_requetes_natives_et_secret_headers(load_gn):
    gn = load_gn(OPENAI_API_KEY='fake-openai', ANTHROPIC_API_KEY='fake-anthropic')
    openai = gn.build_llm_body('openai', MESSAGES, 0.1, 300)
    assert openai == {'model': 'gpt-6-luna', 'input': MESSAGES,
                      'max_output_tokens': 300, 'store': False}
    anthropic = gn.build_llm_body('anthropic', MESSAGES, 0.1, 300)
    assert anthropic == {'model': 'claude-sonnet-4-6', 'max_tokens': 300,
                         'system': 'Réponds en JSON.',
                         'messages': [{'role': 'user', 'content': 'Décris ce dépôt.'}]}
    assert gn._provider_headers('openai')['Authorization'] == 'Bearer fake-openai'
    assert gn._provider_headers('anthropic')['x-api-key'] == 'fake-anthropic'
    assert gn._provider_headers('anthropic')['anthropic-version'] == '2023-06-01'


@pytest.mark.parametrize('provider,data', [
    ('openai', {'model': 'gpt-6-luna', 'status': 'completed', 'output': [
        {'type': 'reasoning', 'summary': []},
        {'type': 'message', 'content': [
            {'type': 'output_text', 'text': '{"description_fr":"Oui"}'}]}]}),
    ('anthropic', {'model': 'claude-sonnet-4-6', 'stop_reason': 'end_turn',
                   'content': [{'type': 'text', 'text': '{"description_fr":"Oui"}'}]}),
])
def test_api_parsing_reponses_valides(load_gn, monkeypatch, provider, data):
    gn = load_gn()
    calls = []

    def post(url, headers, json, timeout):
        calls.append((url, json))
        return FakeResponse(data)

    monkeypatch.setattr(gn, 'get_session', lambda: SimpleNamespace(post=post))
    resultat = gn._call_translation_api(provider, MESSAGES)
    assert resultat == ('{"description_fr":"Oui"}', data['model'])
    assert len(calls) == 1
    assert ('openai.com/v1/responses' if provider == 'openai'
            else 'anthropic.com/v1/messages') in calls[0][0]


@pytest.mark.parametrize('provider,data', [
    ('openai', {'model': 'gpt-6-luna', 'status': 'incomplete', 'output': []}),
    ('anthropic', {'model': 'claude-sonnet-4-6', 'stop_reason': 'max_tokens',
                   'content': [{'type': 'text', 'text': 'texte tronqué'}]}),
])
def test_reponses_tronquees_refusees(load_gn, monkeypatch, provider, data):
    gn = load_gn()
    monkeypatch.setattr(gn, 'get_session', lambda: SimpleNamespace(
        post=lambda **kwargs: FakeResponse(data)))
    assert gn._call_translation_api(provider, MESSAGES) is None


def test_clef_et_modele_controles_sans_generation(load_gn, monkeypatch):
    gn = load_gn(OPENAI_API_KEY='fake-openai', ANTHROPIC_API_KEY='fake-anthropic')
    urls = []

    def get(url, headers, timeout):
        urls.append(url)
        model = gn.OPENAI_MODEL if 'openai' in url else gn.ANTHROPIC_MODEL
        return FakeResponse({'data': [{'id': model}]})

    monkeypatch.setattr(gn, 'get_session', lambda: SimpleNamespace(get=get))
    assert gn._probe_direct_provider('openai')[0]
    assert gn._probe_direct_provider('anthropic')[0]
    assert urls == [gn.OPENAI_MODELS_URL, gn.ANTHROPIC_MODELS_URL]


def test_401_ne_valide_pas_le_fournisseur(load_gn, monkeypatch):
    gn = load_gn(OPENAI_API_KEY='invalid')
    monkeypatch.setattr(gn, 'get_session', lambda: SimpleNamespace(
        get=lambda url, headers, timeout: FakeResponse({}, status=401)))
    ok, msg = gn._probe_direct_provider('openai')
    assert not ok and '401' in msg
    assert gn._provider_state('openai').startup_issue == 'key'


def test_cascade_de_quatre_fournisseurs(load_gn, monkeypatch):
    gn = load_gn(LLM_PROVIDERS='openai,anthropic,mistral,openrouter',
                 OPENAI_API_KEY='test1', ANTHROPIC_API_KEY='test2',
                 MISTRAL_API_KEY='test3', OPENROUTER_API_KEY='test4')
    monkeypatch.setattr(gn, '_probe_direct_provider', lambda provider: (True, 'OK'))
    monkeypatch.setattr(gn, '_probe_mistral', lambda: (True, 'OK'))
    monkeypatch.setattr(gn, '_probe_openrouter', lambda: (True, 'OK'))
    primary, fallback = gn.init_translation_providers()
    assert (primary, fallback) == ('openai', 'anthropic')
    assert gn.configured_providers() == ['openai', 'anthropic', 'mistral', 'openrouter']


def test_secrets_sont_masques_dans_la_redecouverte(load_gn, monkeypatch):
    gn = load_gn(OPENAI_API_KEY='fake-openai-12345678',
                 ANTHROPIC_API_KEY='fake-anthropic-12345678')
    import importlib
    import redecouverte
    rd = importlib.reload(redecouverte)
    secrets = rd.secrets_connus()
    assert 'fake-openai-12345678' in secrets
    assert 'fake-anthropic-12345678' in secrets
    assert 'fake-openai-12345678' not in rd.masquer('fake-openai-12345678', secrets)
