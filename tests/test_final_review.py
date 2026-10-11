"""Tests de non-régression de la revue finale (correctifs de revue, migration v7.1, documentation).

Un groupe de tests par constat corrigé, repéré par son identifiant (FC-1, MIG-1, DOC-A...).
Réseau entièrement simulé (FakeAPI2 du lot 2, FakeNotion du nettoyeur) ; time.sleep est neutralisé.
"""
import importlib
import importlib.util
import json
from pathlib import Path

import pytest
import requests

from test_gitnotate_lot1 import GOOD_LLM, chat, make_response
from test_gitnotate_lot2 import BASE_ENV2, FakeAPI2, _wire, pages_posted, sequence
from test_cleaner import FakeNotion, simple_dup

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / 'README.md').read_text(encoding='utf-8')
README_FLAT = ' '.join(README.split())

GOOD = {'description_fr': "Un outil d'automatisation pour les flux IA",
        'use_cases_fr': '• Automatiser des tâches\n• Orchestrer des agents',
        'score': 8, 'reasoning': 'Stack Python identique, domaine automatisation'}
GOOD_TEXT = json.dumps(GOOD, ensure_ascii=False)
TEMPLATE_ANSWER = {'description_fr': 'traduction française de la description',
                   'use_cases_fr': "• cas d'usage 1\n• cas d'usage 2", 'score': 0,
                   'reasoning': 'justification du score en 40 mots maximum'}
OLD_OR_MODEL = 'openai/gpt-oss-20b:free'


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


def _mistral_generation(api, content):
    """Mistral : test de démarrage valide, génération = `content`."""
    def handler(url, payload):
        if payload.get('max_tokens') == 16:
            return make_response(200, chat('{"ok": true}', model='mistral-small-2603'))
        return make_response(200, chat(content, model='mistral-small-2603'))
    api.route('POST', r'api\.mistral\.ai', handler)


def _models(*ids):
    return lambda url, payload: make_response(200, {'data': [{'id': i, 'name': i} for i in ids]})


def _text_of(page, prop):
    return ''.join(part['text']['content'] for part in page['properties'][prop]['rich_text'])


def _validate(gn, **over):
    return gn._validate_llm_payload(dict(GOOD, **over), True)

# =============================================================================
# FC-1 — cas d'usage numérotés avec un vrai contenu : acceptés (gabarit exact seulement rejeté)
# =============================================================================
@pytest.mark.parametrize('use_cases,expected', [
    ("• Cas d'usage 1 : automatiser la correction de copies\n• Cas d'usage 2 : générer des quiz",
     "• automatiser la correction de copies\n• générer des quiz"),
    (["Cas d'usage 1 : automatiser des workflows n8n", "Cas d'usage 2 : orchestrer des agents"],
     "• automatiser des workflows n8n\n• orchestrer des agents"),
    ("• Cas d’usage 1 – intégration à une API de traduction", "• intégration à une API de traduction"),
    ("• Cas d'usage 1 : X • Cas d'usage 2 : Y", "• X • Y"),
    ("• Automatisation\n• Voir cas d'usage 12 de la doc", "• Automatisation\n• Voir cas d'usage 12 de la doc"),
    ("• Traduction des cas d'usage métier en workflows n8n",
     "• Traduction des cas d'usage métier en workflows n8n"),
    ("1. Corriger des copies\n2. Générer des quiz", "1. Corriger des copies\n2. Générer des quiz"),
])
def test_fc1_numbered_real_use_cases_accepted_and_label_removed(load_gn, use_cases, expected):
    gn = load_gn()
    cleaned, why = _validate(gn, use_cases_fr=use_cases)
    assert cleaned is not None and why == ''
    assert cleaned['use_cases_fr'] == expected and cleaned['score'] == 8


@pytest.mark.parametrize('use_cases', [
    "• cas d'usage 1\n• cas d'usage 2\n• cas d'usage 3",
    "• Cas d’usage 1\n• Cas d’usage 2.",
    "• cas d'usage 1 • cas d'usage 2 • cas d'usage 3",          # gabarit sur une seule ligne
    "• cas d'usage 1\\n• cas d'usage 2",                        # « \n » littéral
    ["cas d'usage 1", "cas d'usage 2"],
    "- Cas d'usage 1 :\n- Cas d'usage 2 : ...",
    "- Cas d'usage 1 : …\n- Cas d'usage 2 : …",
    "traduction des cas d'usage avec puces • ",                 # gabarit du prompt de traduction seule
    "Traduction des cas d'usage",
    # P1 : numérotation, séparateurs « , » / « ; », gabarit de traduction précédé d'une puce
    "1. cas d'usage 1\n2. cas d'usage 2\n3. cas d'usage 3",
    "1) Cas d'usage 1\n2) Cas d'usage 2",
    "• 1. cas d'usage 1\n• 2. cas d'usage 2",
    "cas d'usage 1, cas d'usage 2, cas d'usage 3",
    "cas d'usage 1 ; cas d'usage 2",
    "• cas d'usage 1, • cas d'usage 2",
    "• traduction des cas d'usage avec puces",
    "• traduction des cas d'usage avec puces •",
    "- Traduction des cas d'usage avec puces\n- Automatiser des tâches",
    "• Traduction des cas d'usage avec",                        # gabarit tronqué
    ["traduction des cas d'usage avec puces"],
])
def test_fc1_prompt_templates_still_rejected(load_gn, use_cases):
    gn = load_gn()
    cleaned, why = _validate(gn, use_cases_fr=use_cases)
    assert cleaned is None and why == "use_cases_fr recopiés du gabarit du prompt"


@pytest.mark.parametrize('use_cases', [
    "1. Corriger des copies, 2. Générer des quiz",
    "• Cas d'usage 1, automatiser la veille",
    "• Automatiser des tâches ; cas d'usage 2 : orchestrer des agents",
    "Traduction des cas d'usage métier en workflows n8n",
    "• Traduction des cas d'usage, des guides et des docs",
])
def test_p1_real_use_cases_with_separators_accepted(load_gn, use_cases):
    gn = load_gn()
    cleaned, why = _validate(gn, use_cases_fr=use_cases)
    assert cleaned is not None and why == '' and cleaned['score'] == 8


@pytest.mark.parametrize('use_cases', [
    '["cas d\'usage 1", "cas d\'usage 2", "cas d\'usage 3"]',
    "• « cas d'usage 1 »\n• « cas d'usage 2 »",
    "cas d'usage 1 et cas d'usage 2",
    "cas d'usage 1 / cas d'usage 2 | cas d'usage 3",
    "cas d'usage 1\tcas d'usage 2",
    "(1) cas d'usage 1 (2) cas d'usage 2",
    "<cas d'usage 1>\n<cas d'usage 2>",
    "Cas d'usage 1 - Cas d'usage 2",
    "• cas d’usage 1\\n• cas d’usage 2",
])
def test_residual_template_forms_rejected(load_gn, use_cases):
    gn = load_gn()
    cleaned, why = _validate(gn, use_cases_fr=use_cases)
    assert cleaned is None and why == "use_cases_fr recopiés du gabarit du prompt"


@pytest.mark.parametrize('use_cases', [
    "• Cas d'usage 1 : automatiser la veille",
    "Voir cas d'usage 12 de la doc",
    "Cas d'usage 1 - générer des QCM ; cas d'usage 2 - corriger des copies",
    "• Extraction de tableaux PDF (CCTP, DPGF)",
])
def test_residual_rule_keeps_real_use_cases(load_gn, use_cases):
    gn = load_gn()
    cleaned, why = _validate(gn, use_cases_fr=use_cases)
    assert cleaned is not None and why == ''


@pytest.mark.parametrize('env,use_cases', [
    ({}, '["cas d\'usage 1", "cas d\'usage 2", "cas d\'usage 3"]'),
    ({}, "1. cas d'usage 1\n2. cas d'usage 2\n3. cas d'usage 3"),
    ({}, "cas d'usage 1, cas d'usage 2, cas d'usage 3"),
    ({'LLM_SCORING_ENABLED': 'false'}, "• traduction des cas d'usage avec puces"),
])
def test_p1_full_run_template_use_cases_are_deferred(world2, env, use_cases):
    gn, api = world2(OPENROUTER_API_KEY=None, **env)
    api.set_page_urls(['https://github.com/org/repo0'])
    _mistral_generation(api, json.dumps(dict(GOOD, use_cases_fr=use_cases), ensure_ascii=False))
    assert gn.main([]) == 0
    assert pages_posted(api) == [] and gn.stats.deferred == 1


def test_fc1_template_markers_match_prompts(load_gn):
    gn = load_gn()
    combined = gn.build_system_prompt_combined()
    assert gn._TEMPLATE_USE_CASES[0] in combined.replace('\\n', '\n')
    assert gn._TEMPLATE_USE_CASES[1] in gn.SYSTEM_PROMPT_TRANSLATE
    assert gn._TEMPLATE_USE_CASE_LINE_RE.fullmatch(gn._TEMPLATE_USE_CASES[0])
    assert gn._TEMPLATE_USE_CASES_TRANSLATE in gn.SYSTEM_PROMPT_TRANSLATE
    assert f'"<{gn._TEMPLATE_REASONING_FULL}>"' in combined
    # Les gabarits réellement écrits dans les prompts sont rejetés tels quels
    combined_template = json.loads('{' + combined.split('{', 1)[1].split('"score"')[0].rstrip(' ,\n') + '}')
    assert gn._use_cases_are_template(combined_template['use_cases_fr'])
    translate_template = json.loads('{' + gn.SYSTEM_PROMPT_TRANSLATE.split('{', 1)[1].split('}')[0] + '}')
    assert gn._use_cases_are_template(translate_template['use_cases_fr'])


def test_fc1_full_run_numbered_use_cases_are_written(world2):
    gn, api = world2(OPENROUTER_API_KEY=None)
    api.set_page_urls([f'https://github.com/org/repo{i}' for i in range(4)])
    _mistral_generation(api, json.dumps(dict(GOOD, use_cases_fr="• Cas d'usage 1 : automatiser des tâches\n"
                                                                 "• Cas d'usage 2 : orchestrer des agents"),
                                        ensure_ascii=False))
    assert gn.main([]) == 0
    pages = pages_posted(api)
    assert len(pages) == 4 and gn.stats.deferred == 0
    assert _text_of(pages[0], "Cas d'usage") == "• automatiser des tâches\n• orchestrer des agents"
    assert not gn.LLM_STATES['mistral'].is_disabled

# =============================================================================
# FC-2 — justification réelle entre chevrons : acceptée (chevrons d'encadrement retirés)
# =============================================================================
@pytest.mark.parametrize('reasoning,expected', [
    ("<Outil Python d'automatisation, stack identique au profil>",
     "Outil Python d'automatisation, stack identique au profil"),
    ("<5 étoiles seulement, mais domaine éducation au cœur du profil",
     "<5 étoiles seulement, mais domaine éducation au cœur du profil"),
    ("  < Stack identique >  ", "Stack identique"),
])
def test_fc2_real_reasoning_in_angle_brackets_accepted(load_gn, reasoning, expected):
    gn = load_gn()
    cleaned, why = _validate(gn, reasoning=reasoning)
    assert why == '' and cleaned['score'] == 8 and cleaned['reasoning'] == expected


@pytest.mark.parametrize('reasoning', ['<…>', '<...>', '<>', '< . >',
                                       '<justification du score en 40 mots maximum>',
                                       'Justification du score en 40 mots maximum',
                                       # P1 : gabarit tronqué, avec ou sans chevrons
                                       '<justification>', '<justification du score>', '< Justification du score… >',
                                       '<justification du score en 40>', '<justification du score',
                                       'Justification du score'])
def test_fc2_template_reasoning_still_rejected(load_gn, reasoning):
    gn = load_gn()
    cleaned, why = _validate(gn, reasoning=reasoning)
    assert cleaned['score'] is None and why == "reasoning recopié du gabarit du prompt"

# =============================================================================
# FC-3 — réponse enveloppée dans un objet décodé
# =============================================================================
@pytest.mark.parametrize('raw', [
    json.dumps({'result': GOOD}, ensure_ascii=False),
    json.dumps({'choices': [{'answer': GOOD}]}, ensure_ascii=False),
    'Voici : ```json\n' + json.dumps({'data': {'result': GOOD}}, ensure_ascii=False) + '\n```',
])
def test_fc3_wrapped_answer_is_found(load_gn, raw):
    gn = load_gn()
    parsed = gn._parse_llm_json(raw)
    assert parsed == GOOD
    assert gn._validate_llm_payload(parsed, True) == (dict(GOOD), '')


def test_fc3_nested_objects_of_an_answer_still_ignored(load_gn):
    gn = load_gn()
    assert gn._parse_llm_json('{"description_fr": "a", "meta": {"description_fr": "imbriqué"}}')['description_fr'] == 'a'
    assert gn._parse_llm_json('{"x": 1} et {"y": 2}') == {'x': 1}

# =============================================================================
# FC-4 — le DERNIER objet qui passe la validation l'emporte ; pas de plafond bas d'accolades
# =============================================================================
def test_fc4_trailing_template_example_does_not_win(load_gn):
    gn = load_gn()
    raw = GOOD_TEXT + '\n\nFormat respecté : ' + json.dumps(TEMPLATE_ANSWER, ensure_ascii=False)
    assert gn._parse_llm_json(raw) == GOOD


@pytest.mark.parametrize('braces', [25, 300])
def test_fc4_valid_draft_before_many_braces_never_wins(load_gn, braces):
    gn = load_gn()
    draft = dict(GOOD, description_fr='BROUILLON', score=2)
    noise = ' '.join('{x}' for _ in range(braces))
    raw = (json.dumps(draft, ensure_ascii=False) + '\nRéflexion : ' + noise
           + '\nRéponse finale :\n' + GOOD_TEXT)
    assert gn._parse_llm_json(raw) == GOOD


def test_fc4_complete_answer_beats_later_partial_and_s4_kept(load_gn):
    gn = load_gn()
    partial = dict(GOOD, description_fr='Partielle', score='beaucoup')
    assert gn._parse_llm_json(GOOD_TEXT + ' puis ' + json.dumps(partial, ensure_ascii=False)) == GOOD
    # Sans score demandé (traduction seule), la plus tardive des réponses valides l'emporte
    assert gn._parse_llm_json(GOOD_TEXT + ' ' + json.dumps(partial), need_score=False)['description_fr'] == 'Partielle'
    # S4 : brouillon <think> ignoré même s'il est valide
    think = '<think>' + json.dumps(dict(GOOD, description_fr='brouillon')) + '</think>' + GOOD_TEXT
    assert gn._parse_llm_json(think) == GOOD
    # Aucun objet valide : le dernier trouvé (comportement inchangé)
    assert gn._parse_llm_json('Brouillon {"description_fr": "a"} puis {"description_fr": "b"}') == {'description_fr': 'b'}


def test_fc4_translate_and_score_keeps_answer_before_example(world2):
    gn, api = world2(LLM_PROVIDERS='mistral', OPENROUTER_API_KEY=None)
    gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK = 'mistral', None
    content = GOOD_TEXT + '\nRappel du format : ' + json.dumps(TEMPLATE_ANSWER, ensure_ascii=False)
    api.route('POST', r'api\.mistral\.ai', lambda u, p: make_response(200, chat(content)))
    result = gn.translate_and_score('A tool', '• x', {'name': 'demo', 'readme': ''}, 'o/demo')
    assert result['llm_status'] == 'ok' and result['score'] == 8
    assert result['description_fr'] == GOOD['description_fr']

# =============================================================================
# FC-5 — --dry-run prime sur une valeur DRY_RUN invalide
# =============================================================================
def test_fc5_cli_dry_run_overrides_invalid_env(world2, capsys):
    gn, api = world2(DRY_RUN='simulation')
    assert gn.main(['--dry-run']) == 0
    assert gn.DRY_RUN is True and pages_posted(api) == [] and gn.stats.success == 1
    assert 'DRY_RUN' not in capsys.readouterr().err


def test_fc5_invalid_dry_run_without_option_still_stops(world2, capsys):
    gn, api = world2(DRY_RUN='simulation')
    assert gn.main([]) == 1
    assert api.calls == [] and "DRY_RUN='simulation' invalide" in capsys.readouterr().err

# =============================================================================
# MIG-1 — modèle OpenRouter vérifié au démarrage, sans quota (GET /api/v1/models)
# =============================================================================
def test_mig1_unknown_openrouter_model_is_discarded_without_quota(world2):
    gn, api = world2(OPENROUTER_MODEL=OLD_OR_MODEL)
    api.route('GET', r'openrouter\.ai/api/v1/models$', _models('openrouter/free', 'google/gemma-4-31b-it:free'))
    ok, msg = gn._probe_openrouter()
    assert ok is False and '✅' not in msg
    assert (f"modèle '{OLD_OR_MODEL}' introuvable chez OpenRouter — utilisez OPENROUTER_MODEL=openrouter/free"
            in msg)
    assert api.entries('POST', r'openrouter\.ai') == []                    # aucun quota consommé
    (_, url, headers, _, _), = api.entries('GET', r'/api/v1/models')
    assert url == 'https://openrouter.ai/api/v1/models' and 'Authorization' not in headers
    assert gn._provider_state('openrouter').startup_issue == 'model'


@pytest.mark.parametrize('model', ['google/gemma-4-31b-it:free', 'Google/Gemma-4-31B-it:free',
                                   'mistralai/mistral-small-2603:nitro'])
def test_mig1_listed_model_is_kept(world2, model):
    gn, api = world2(OPENROUTER_MODEL=model)
    api.route('GET', r'openrouter\.ai/api/v1/models$',
              _models('google/gemma-4-31b-it:free', 'mistralai/mistral-small-2603'))
    ok, msg = gn._probe_openrouter()
    assert ok is True and 'clé valide' in msg


def test_mig1_openrouter_free_needs_no_model_list(world2):
    gn, api = world2()
    ok, _ = gn._probe_openrouter()
    assert ok is True and api.entries('GET', r'/api/v1/models') == []


@pytest.mark.parametrize('failure', [requests.exceptions.ConnectionError('dns'),
                                     make_response(503, {'error': {'message': 'down'}}),
                                     make_response(200, {'data': 'inattendu'})])
def test_mig1_model_list_failure_warns_and_keeps_openrouter(world2, capsys, failure):
    gn, api = world2(OPENROUTER_MODEL=OLD_OR_MODEL)
    api.route('GET', r'openrouter\.ai/api/v1/models$', lambda u, p: failure)
    ok, msg = gn._probe_openrouter()
    assert ok is True and 'clé valide' in msg
    assert 'liste des modèles illisible' in capsys.readouterr().out


def test_mig1_mistral_ok_and_unknown_fallback_is_not_announced(world2, capsys):
    gn, api = world2(OPENROUTER_MODEL=OLD_OR_MODEL)
    api.route('GET', r'openrouter\.ai/api/v1/models$', _models('openrouter/free'))
    assert gn.main([]) == 0
    assert (gn.TRANSLATION_PROVIDER, gn.TRANSLATION_FALLBACK) == ('mistral', None)
    cap = capsys.readouterr()
    assert 'introuvable chez OpenRouter' in cap.err and 'Fallback' not in cap.out
    assert len(pages_posted(api)) == 1 and api.entries('POST', r'openrouter\.ai') == []


def test_mig1_no_usable_provider_stops_before_github(world2, capsys):
    gn, api = world2(OPENROUTER_MODEL=OLD_OR_MODEL, GITHUB_TOKEN='ghp_valid_token_1234')
    api.route('POST', r'api\.mistral\.ai', lambda u, p: make_response(401, {'message': 'Unauthorized'}))
    api.route('GET', r'openrouter\.ai/api/v1/models$', _models('openrouter/free'))
    assert gn.main([]) == 1
    assert api.entries('GET', r'api\.github\.com') == [] and api.entries('POST', r'api\.notion\.com') == []
    err = capsys.readouterr().err
    assert 'modèle introuvable' in err and 'OPENROUTER_MODEL=openrouter/free' in err
    assert 'REQUIRE_LLM=false' not in err


def _load_check_llm():
    spec = importlib.util.spec_from_file_location('check_llm_final', ROOT / 'scripts' / 'check_llm.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_llm_get(models):
    calls = []

    def fake_get(url, headers):
        calls.append((url, headers))
        if url.endswith('/api/v1/key'):
            return make_response(200, {'data': {'free_model_daily_requests':
                                                {'used': 1, 'limit': 50, 'remaining': 49}}})
        if isinstance(models, BaseException):
            raise models
        return models
    return fake_get, calls


@pytest.mark.parametrize('model,models,code,fragment', [
    (OLD_OR_MODEL, make_response(200, {'data': [{'id': 'openrouter/free'}]}), 1,
     f"modèle '{OLD_OR_MODEL}' introuvable chez OpenRouter — utilisez OPENROUTER_MODEL=openrouter/free"),
    (OLD_OR_MODEL, make_response(200, {'data': [{'id': OLD_OR_MODEL}]}), 0, f"modèle '{OLD_OR_MODEL}' disponible"),
    (OLD_OR_MODEL, requests.exceptions.ConnectionError('dns'), 0, 'liste des modèles OpenRouter illisible'),
    ('openrouter/free', None, 0, "modèle 'openrouter/free' (routeur des modèles gratuits)"),
])
def test_mig1_check_llm_verifies_openrouter_model(monkeypatch, capsys, model, models, code, fragment):
    module = _load_check_llm()
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-v1-0123456789abcdef0123456789abcdef')
    monkeypatch.setenv('OPENROUTER_MODEL', model)
    fake_get, calls = _check_llm_get(models)
    monkeypatch.setattr(module, '_http_get', fake_get)
    assert module.main() == code
    assert fragment in capsys.readouterr().out
    model_calls = [(u, h) for u, h in calls if u.endswith('/api/v1/models')]
    assert len(model_calls) == (0 if model == 'openrouter/free' else 1)
    assert all('Authorization' not in h for _, h in model_calls)

# =============================================================================
# MIG-3 — avertissements TRANSLATION_MODEL et ancien défaut OPENROUTER_MODEL de la v7.1
# =============================================================================
def test_mig3_translation_model_warning_text(load_gn):
    gn = load_gn(TRANSLATION_MODEL=OLD_OR_MODEL)
    assert ("TRANSLATION_MODEL (v7.1) est obsolète : supprimez la ligne pour utiliser openrouter/free "
            "(ou écrivez OPENROUTER_MODEL=openrouter/free)") in gn.CONFIG_WARNINGS
    assert not any('renommez' in w for w in gn.CONFIG_WARNINGS)


def test_mig3_old_openrouter_default_is_reported(load_gn):
    gn = load_gn(OPENROUTER_MODEL=OLD_OR_MODEL)
    (warning,) = gn.CONFIG_WARNINGS
    assert "l'ancien défaut de la v7.1" in warning and 'OPENROUTER_MODEL=openrouter/free' in warning
    assert load_gn(OPENROUTER_MODEL='openrouter/free').CONFIG_WARNINGS == []
    assert load_gn(OPENROUTER_MODEL=None).CONFIG_WARNINGS == []

# =============================================================================
# MIG-4 — arrêt « aucun fournisseur » : piste selon la cause, jamais REQUIRE_LLM=false
# =============================================================================
def _stop_message(world2, capsys, routes=(), **env):
    gn, api = world2(GITHUB_TOKEN='ghp_valid_token_1234', **env)
    for method, pattern, handler in routes:
        api.route(method, pattern, handler)
    assert gn.main([]) == 1
    assert api.entries('GET', r'api\.github\.com') == []
    err = capsys.readouterr().err
    assert "Aucun fournisseur LLM disponible : rien n'est écrit" in err and 'REQUIRE_LLM=false' not in err
    return err


def test_mig4_key_refused_and_quota_exhausted(world2, capsys):
    err = _stop_message(world2, capsys, routes=[
        ('POST', r'api\.mistral\.ai', lambda u, p: make_response(401, {'message': 'Unauthorized'})),
        ('GET', r'openrouter\.ai/api/v1/key', lambda u, p: make_response(200, {'data': {
            'free_model_daily_requests': {'used': 50, 'limit': 50, 'remaining': 0}}})),
    ])
    assert 'clé refusée — corrigez MISTRAL_API_KEY dans .env, puis lancez « python scripts/check_llm.py »' in err
    assert 'quota gratuit du jour épuisé — relancez après minuit UTC' in err


def test_mig4_model_not_found(world2, capsys):
    err = _stop_message(world2, capsys, OPENROUTER_API_KEY=None, MISTRAL_MODEL='mistral-small-2503', routes=[
        ('POST', r'api\.mistral\.ai',
         lambda u, p: make_response(400, {'message': 'Invalid model: mistral-small-2503'})),
    ])
    assert ('modèle introuvable — corrigez le modèle dans .env '
            '(supprimez la ligne MISTRAL_MODEL pour utiliser mistral-small-2603)') in err


def test_mig4_no_key_and_network(world2, capsys):
    err = _stop_message(world2, capsys, MISTRAL_API_KEY=None, OPENROUTER_API_KEY=None)
    assert 'Renseignez MISTRAL_API_KEY et/ou OPENROUTER_API_KEY dans .env' in err
    err = _stop_message(world2, capsys, OPENROUTER_API_KEY=None, routes=[
        ('POST', r'api\.mistral\.ai', lambda u, p: requests.exceptions.ConnectionError('dns')),
    ])
    assert 'injoignable ou indisponible — vérifiez la connexion' in err

# =============================================================================
# MIG-5 — erreur 422 au format FastAPI (message.detail = liste)
# =============================================================================
DETAIL_422 = {'object': 'error', 'type': 'invalid_request_error', 'message': {'detail': [
    {'type': 'extra_forbidden', 'loc': ['body', 'reasoning_effort'],
     'msg': 'Extra inputs are not permitted', 'input': 'none'}]}}


def test_mig5_api_error_message_with_detail_list(load_gn):
    gn = load_gn()
    assert gn._api_error_message(make_response(422, DETAIL_422)) == 'reasoning_effort : Extra inputs are not permitted'
    two = {'message': {'detail': [{'loc': ['body', 'a'], 'msg': 'x requis'}, {'loc': [], 'msg': 'y'},
                                  'ignoré', {'loc': ['body', 'b']}]}}
    assert gn._api_error_message(make_response(422, two)) == 'a : x requis ; y'
    assert gn._api_error_message(make_response(422, {'detail': [{'loc': ['body', 'c'], 'msg': 'z'}]})) == 'c : z'
    long = {'message': {'detail': [{'loc': ['body', f'champ{i}'], 'msg': 'invalide'} for i in range(30)]}}
    text = gn._api_error_message(make_response(422, long), 50)
    assert len(text) == 51 and text.endswith('…') and text.startswith('champ0 : invalide ; champ1')


def test_mig5_probe_log_shows_readable_422(world2, capsys):
    gn, api = world2(OPENROUTER_API_KEY=None)
    api.route('POST', r'api\.mistral\.ai', sequence(make_response(422, DETAIL_422),
                                                    make_response(200, chat('{"ok": true}'))))
    ok, msg = gn._probe_mistral()
    assert ok and 'sans reasoning_effort' in msg
    out = capsys.readouterr().out
    assert ('paramètre reasoning_effort refusé (HTTP 422 — reasoning_effort : Extra inputs are not permitted)'
            in out)

# =============================================================================
# DOC-A — premier essai : MAX_NEW_PER_RUN=10 avec --dry-run (et non --max-repos)
# =============================================================================
def test_doca_max_new_per_run_limits_dry_run(world2):
    gn, api = world2(MAX_NEW_PER_RUN='2')
    api.set_page_urls([f'https://github.com/owner/r{i}' for i in range(4)])
    assert gn.main(['--dry-run']) == 0
    assert gn.stats.success == 2 and gn.stats.deferred == 2 and pages_posted(api) == []


def test_doca_shell_variable_wins_over_dotenv(load_gn, monkeypatch, tmp_path):
    pytest.importorskip('dotenv')
    for key in ('MAX_NEW_PER_RUN', 'NOTION_TOKEN'):          # « absentes » restaurées en fin de test
        monkeypatch.setenv(key, 'x')
        monkeypatch.delenv(key)
    (tmp_path / '.env').write_text('MAX_NEW_PER_RUN=0\nNOTION_TOKEN=ntn_from_dotenv_1234\n', encoding='utf-8')
    gn = load_gn(GITNOTATE_NO_DOTENV='', MAX_NEW_PER_RUN='10')
    assert gn.MAX_NEW_PER_RUN == 10 and gn.NOTION_TOKEN == 'ntn_from_dotenv_1234'


def test_doca_readme_and_a_lire():
    a_lire = (ROOT / 'A lire.txt').read_text(encoding='utf-8')
    for text in (README, a_lire):
        assert '--max-repos 10' not in text.replace('`--max-repos 10` pour cet essai', '')
        assert '$env:MAX_NEW_PER_RUN=10' in text and 'MAX_NEW_PER_RUN=10 python gitnotate.py --dry-run' in text
    assert '`MAX_NEW_PER_RUN=10` dans `.env`' in README_FLAT
    assert '`--max-repos` compte aussi les dépôts déjà présents' in README_FLAT
    # P3 : qui a choisi .env doit y remettre MAX_NEW_PER_RUN=0 avant l'import complet
    a_lire_flat = ' '.join(a_lire.split())
    assert 'MAX_NEW_PER_RUN=10 dans .env' in a_lire_flat
    step4 = a_lire_flat.split('4. Lancer', 1)[1].split('5. ', 1)[0]
    assert 'Remove-Item Env:MAX_NEW_PER_RUN' in step4 and 'remettez MAX_NEW_PER_RUN=0 dans .env' in step4
    assert 'Remettez ensuite `MAX_NEW_PER_RUN=0` dans `.env`' in README_FLAT

# =============================================================================
# DOC-B — le mode reprise dépend de TRANSLATION_ENABLED et LLM_SCORING_ENABLED
# =============================================================================
def test_docb_readme_states_conditions_and_empty_switch(load_gn):
    assert ("Le mode reprise ne garantit une fiche entièrement issue du LLM (traduction, cas d'usage, note "
            "et justification) que si `TRANSLATION_ENABLED=true` et `LLM_SCORING_ENABLED=true`" in README_FLAT)
    assert "s'applique que si" not in README_FLAT
    assert ('un interrupteur laissé vide (`TRANSLATION_ENABLED=`) vaut **false** (sauf `REQUIRE_LLM`, '
            'que seule la valeur `false` désactive)') in README_FLAT
    gn = load_gn(TRANSLATION_ENABLED='')                       # ce que décrit le README
    assert gn.TRANSLATION_ENABLED is False and gn.REQUIRE_LLM is True and gn.llm_required() is False
    # P2 : sans notation LLM, le mode reprise reste actif pour la traduction
    gn = load_gn(TRANSLATION_ENABLED=None, LLM_SCORING_ENABLED='false')
    assert gn.LLM_SCORING_ENABLED is False and gn.llm_required() is True
    # REQUIRE_LLM vide : le mode reprise reste actif
    gn = load_gn(LLM_SCORING_ENABLED=None, REQUIRE_LLM='')
    assert gn.REQUIRE_LLM is True and gn.llm_required() is True and gn.CONFIG_WARNINGS == []


def test_p2_scoring_disabled_invalid_translation_is_deferred(world2):
    gn, api = world2(OPENROUTER_API_KEY=None, LLM_SCORING_ENABLED='false')
    api.set_page_urls(['https://github.com/org/repo0'])
    _mistral_generation(api, json.dumps(dict(GOOD, description_fr=''), ensure_ascii=False))
    assert gn.main([]) == 0
    assert pages_posted(api) == [] and gn.stats.deferred == 1

# =============================================================================
# DOC-C — nettoyeur : page racine en HTTP 400 = configuration (code 1)
# =============================================================================
def _cleaner(monkeypatch):
    monkeypatch.setenv('NOTION_CLEANER_TOKEN', 'ntn_CLEANER_secret_1234567890')
    monkeypatch.setenv('PARENT_PAGE_ID', 'root')
    return importlib.import_module('clean_page_duplicates')


def test_docc_cleaner_root_400_is_config_error(monkeypatch, capsys):
    cpd = _cleaner(monkeypatch)
    fake = FakeNotion()
    simple_dup(fake)
    fake.errors[('GET', r'/blocks/root/children')] = [400]
    assert cpd.main(['--apply'], session=fake, confirm=lambda p: p, sleep=lambda s: None) == 1
    assert [c for c in fake.calls if c[0] in ('DELETE', 'PATCH')] == []
    assert 'PARENT_PAGE_ID invalide' in capsys.readouterr().out


def test_docc_cleaner_400_on_next_page_is_still_partial_read(monkeypatch, capsys):
    cpd = _cleaner(monkeypatch)
    fake = FakeNotion()
    fake.page_size = 1
    simple_dup(fake)
    orig = fake.request

    def flaky(method, url, params=None, **kw):
        if url.endswith('/blocks/root/children') and (params or {}).get('start_cursor'):
            return make_response(400, {'object': 'error', 'status': 400})     # curseur refusé
        return orig(method, url, params=params, **kw)
    fake.request = flaky
    assert cpd.main(['--apply'], session=fake, confirm=lambda p: p, sleep=lambda s: None) == 2
    out = capsys.readouterr().out
    assert 'ABANDON' in out and 'PARENT_PAGE_ID invalide' not in out

# =============================================================================
# DOC-D / DOC-E / DOC-F / DOC-G / DOC-H — exactitude de la documentation
# =============================================================================
def test_docd_stats_history_only_for_runs_reaching_processing(world2):
    assert "historique des 50 derniers runs allés jusqu'au traitement des dépôts" in README_FLAT
    gn, api = world2(PARENT_PAGE_ID=None)
    assert gn.main([]) == 1 and not gn.STATS_FILE.exists()
    gn, api = world2()
    assert gn.main([]) == 0 and gn.STATS_FILE.exists()


def test_doce_private_repositories(world2, capsys):
    assert "aucune donnée d'un dépôt privé n'est envoyée au LLM" in README_FLAT
    assert '« GitHub HTTP 404 » (run en code 2) ; retirez ce lien de la page source' in README_FLAT
    gn, api = world2()
    api.repos['owner/repo']['private'] = True
    assert gn.main([]) == 0
    assert gn.stats.filtered == 1 and api.llm_bodies('mistral') == [] and pages_posted(api) == []
    gn, api = world2()
    api.set_page_urls(['https://github.com/ghost/private-repo'])      # jeton sans portée privée : 404
    assert gn.main([]) == 2
    assert 'GitHub HTTP 404' in capsys.readouterr().err and api.llm_bodies('mistral') == []


def test_docf_min_update_days_migration_note(load_gn):
    assert "`MIN_UPDATE_DAYS` valait 180 dans l'ancien `env.example`" in README_FLAT
    assert 'Recopiez `MIN_UPDATE_DAYS=180` dans votre `.env` pour garder ce filtre' in README_FLAT
    assert load_gn().MIN_UPDATE_DAYS == 0 and load_gn(MIN_UPDATE_DAYS='180').MIN_UPDATE_DAYS == 180


def test_docg_comparison_document_is_marked_obsolete():
    text = (ROOT / 'COMPARAISON_MODELES.md').read_text(encoding='utf-8')
    first, rest = text.split('\n', 1)
    assert 'Document obsolète (v2.5 / modèles retirés) : voir README.md' in first
    assert rest.lstrip('\n').startswith('# 🔬 Comparaison des Modèles OpenRouter Gratuits')


def test_doch_virtual_environment_reactivation():
    assert 'À chaque nouvelle fenêtre de terminal' in README_FLAT
    assert '`.\\.venv\\Scripts\\Activate.ps1` sous Windows' in README_FLAT
    assert '`source .venv/bin/activate` sous Linux' in README_FLAT
    a_lire = (ROOT / 'A lire.txt').read_text(encoding='utf-8')
    assert 'py -m venv .venv' in a_lire and '.\\.venv\\Scripts\\Activate.ps1' in a_lire
    assert 'source .venv/bin/activate' in a_lire and 'À chaque nouvelle fenêtre' in a_lire

# =============================================================================
# DOC-I — même résolution de GITNOTATE_DATA_DIR dans les trois scripts
# =============================================================================
def test_doci_data_dir_resolution_is_identical(load_gn, monkeypatch, tmp_path):
    home = tmp_path / 'home'
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setenv('GITNOTATE_DATA_DIR', '  ~/gitnotate_data  ')
    expected = home / 'gitnotate_data'
    cpd = importlib.import_module('clean_page_duplicates')
    assert load_gn().BASE_DIR == expected
    assert _load_check_llm().BASE_DIR == expected
    assert cpd.base_dir() == expected
    # Valeur vide ou faite d'espaces : dossier du script (racine du projet pour check_llm.py)
    monkeypatch.setenv('GITNOTATE_DATA_DIR', '   ')
    assert load_gn().BASE_DIR == ROOT
    assert _load_check_llm().BASE_DIR == ROOT
    assert cpd.base_dir() == ROOT


def test_good_llm_fixture_still_valid(load_gn):
    """Témoin : la réponse nominale des autres tests reste acceptée telle quelle."""
    gn = load_gn()
    cleaned, why = gn._validate_llm_payload(dict(GOOD_LLM), True)
    assert why == '' and cleaned['use_cases_fr'] == GOOD_LLM['use_cases_fr']
