"""Tests de régression de la v7.4 (phase A du lot 4) : règles de notation A1 à A4 et version.

A1 : Pertinence plafonnée à 8 sans « brique pour » validée (jamais déduit du schéma Notion).
A2 : dépôt sans description, sans topics et sans README exploitable → fiche créée, Pertinence vide.
A3 : distribution Docker seulement pour une image qui désigne le dépôt analysé.
A4 : repli lexical neutre (ni bonus de langage, ni pénalité non établie par le profil).

Réseau entièrement simulé (fausse API à tous verbes du lot 3), aucun secret, aucun .env lu (conftest).
"""
import hashlib
import json
import time
from pathlib import Path

import pytest
import requests

from test_gitnotate_lot1 import chat, make_response
from test_gitnotate_lot2 import BASE_ENV2, _wire, history, pages_posted
from test_lot3 import (
    _DROP, ALL_COMBOS, ANSWER, FRESH, README_DOCLING, TEST_PROFILE, V71_COLUMNS, RecordingAPI,
    assert_read_and_create_only, justification, notion_db, readme_route, text,
)

ROOT = Path(__file__).resolve().parent.parent
SHIPPED_PROFILE = json.loads((ROOT / 'user_profile.json').read_text(encoding='utf-8'))
OPTIONAL_TEXT = dict(V71_COLUMNS, **{'Licence': ('rich_text', None), 'Catégorie': ('rich_text', None),
                                     'Brique pour': ('rich_text', None)})
# U0·P3·T2·I2·C2 avec M2·L2 : note brute 10 (valeur = P3 ; U ≥ 2 exigerait un projet actif cité)
UNLINKED = dict(ANSWER, brique_pour=[], utilite_immediate=0, potentiel_futur=3, interet=2, integration=2)
EMPTY_REPO = dict(FRESH, description=None, topics=[])
NO_INFO = "[NON NOTÉ] Ni description, ni topics, ni README exploitable : Pertinence laissée vide."
CAP_MARK = "plafonnée à 8 (aucune brique du profil)"
# Dépôt riche en mots-clés du profil livré : score lexical brut 10 quel que soit son langage
RICH = dict(FRESH, description='automation workflow trading education ai llm ocr finance with react fastapi',
            topics=['ai', 'llm', 'automation', 'n8n', 'docker', 'trading'], language='Rust')
NO_PROVIDER = {'REQUIRE_LLM': 'false', 'MISTRAL_API_KEY': None, 'LLM_PROVIDERS': 'mistral'}


@pytest.fixture
def world3(load_gn, monkeypatch):
    """Comme la fixture world3 du lot 3 : module rechargé (Mistral seul par défaut), profil écrit dans le
    dossier de données, fausse API à tous verbes, toute requête hors fausse session refusée."""
    def _escaped(self, method, url, *a, **k):
        raise RuntimeError(f"requête hors fausse session : {method} {url}")
    monkeypatch.setattr(requests.Session, 'request', _escaped)

    def _make(profile=TEST_PROFILE, answer=ANSWER, readme=README_DOCLING, columns=None, repo=None, **env):
        merged = dict(BASE_ENV2, OPENROUTER_API_KEY=None)
        merged.update(env)
        gn = load_gn(**merged)
        if profile is not None:
            gn.PROFILE_FILE.write_text(json.dumps(profile, ensure_ascii=False), encoding='utf-8')
        api = RecordingAPI()
        api.escaped = []
        api.db = notion_db(V71_COLUMNS if columns is None else columns)
        api.mistral_content = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        for key, value in (repo or {}).items():
            if value is _DROP:
                api.repos['owner/repo'].pop(key, None)
            else:
                api.repos['owner/repo'][key] = value
        readme_route(api, readme)
        _wire(gn, monkeypatch, api)
        return gn, api
    return _make

# =============================================================================
# A1 — plafond 8 sans rattachement validé à un projet ou un domaine du profil
# =============================================================================
@pytest.mark.parametrize('brique', [[], ['Projet inconnu'], 'n/a', None])
def test_a1_unlinked_answer_capped_at_8_and_marked(world3, brique):
    gn, api = world3(answer=dict(UNLINKED, brique_pour=brique), repo=FRESH)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': 8}
    assert f'U0·P3·T2·I2·C2·M2·L2 = 10, {CAP_MARK} —' in justification(page)
    assert history(gn)[-1]['scores_distribution'] == {'8': 1}


def test_a1_verbose_log_shows_raw_note(world3, capsys):
    gn, api = world3(answer=UNLINKED, repo=FRESH, LOG_LEVEL='verbose')
    assert gn.main([]) == 0
    assert f'Score LLM: U0·P3·T2·I2·C2·M2·L2 = 10, {CAP_MARK} —' in capsys.readouterr().out


@pytest.mark.parametrize('brique', [['Documents et OCR'], ['IA et agents'], ['Gitnotate'], ['Gitnotate (actif)']])
def test_a1_validated_brique_keeps_10(world3, brique):
    gn, api = world3(answer=dict(UNLINKED, brique_pour=brique), repo=FRESH)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': 10}
    assert 'U0·P3·T2·I2·C2·M2·L2 = 10 —' in justification(page) and 'plafonnée' not in justification(page)


@pytest.mark.parametrize('columns', [V71_COLUMNS, dict(V71_COLUMNS, **{'Brique pour': ('multi_select', ['Autre'])})],
                         ids=['colonne absente', 'option absente'])
def test_a1_cap_ignores_notion_schema(world3, columns):
    """La note suit la réponse validée, jamais le schéma : colonne ou option absente → aucun plafond."""
    gn, api = world3(answer=dict(UNLINKED, brique_pour=['Documents et OCR']), repo=FRESH, columns=columns)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': 10}
    assert 'Brique pour' not in page['properties'] and 'plafonnée' not in justification(page)


def test_a1_note_at_or_below_8_is_unchanged_and_unmarked(world3):
    gn, api = world3(answer=dict(UNLINKED, interet=0, integration=1), repo=FRESH)    # U0·P3·T0·I1·C2 → 8
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': 8} and 'plafonnée' not in justification(page)


def test_a1_cap_changes_only_9_and_10(load_gn):
    gn = load_gn()
    assert gn.PERTINENCE_MAX_SANS_BRIQUE == 8
    for combo in ALL_COMBOS:
        raw = gn.compute_pertinence(combo)
        capped, uncapped = gn.cap_unlinked(raw, [])
        assert capped == min(raw, 8) and uncapped == (raw if raw > 8 else None)
        assert gn.cap_unlinked(raw, ['x']) == (raw, None)


def test_a1_compute_pertinence_unchanged(load_gn):
    """Agrégation pure inchangée : le plafond s'applique après, sur la note finale."""
    gn = load_gn()
    combo = {'utilite_immediate': 0, 'potentiel_futur': 3, 'interet': 2, 'integration': 2, 'compatibilite': 2,
             'maturite': 2, 'licence': 2}
    assert gn.compute_pertinence(combo) == 10
    assert gn.format_components(combo, 10) == 'U0·P3·T2·I2·C2·M2·L2 = 10'
    assert gn.format_components(combo, 8, 10) == f'U0·P3·T2·I2·C2·M2·L2 = 10, {CAP_MARK}'


def test_a1_zero_value_guard_still_applies(load_gn):
    gn = load_gn()
    combo = {'utilite_immediate': 0, 'potentiel_futur': 0, 'interet': 2, 'integration': 2, 'compatibilite': 2,
             'maturite': 2, 'licence': 2}
    assert gn.cap_unlinked(gn.compute_pertinence(combo), []) == (2, None)


def test_a1_immediate_utility_guard_then_cap(load_gn):
    gn = load_gn()
    cleaned, why = gn._validate_llm_payload(dict(UNLINKED, utilite_immediate=3), True,
                                            gn.normalize_profile(TEST_PROFILE)[0])
    assert why == '' and cleaned['judgements']['utilite_immediate'] == 1 and cleaned['brique_pour'] == []


def test_a1_profile_without_names_caps_every_llm_score_and_warns(world3, capsys):
    profile = dict(TEST_PROFILE, domaines=[], projets=[], domains=[], interests=[])
    gn, api = world3(profile=profile, answer=dict(UNLINKED, brique_pour=['IA et agents']), repo=FRESH)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': 8} and CAP_MARK in justification(page)
    assert 'Profil : ni projet ni domaine' in capsys.readouterr().err
    assert gn.normalize_profile(TEST_PROFILE)[1] == []                    # profil nommé : aucun avertissement


def test_a1_lexical_fallback_capped_and_marked(world3):
    gn, api = world3(profile=SHIPPED_PROFILE, repo=RICH, readme='docker postgres redis', **NO_PROVIDER)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': 8}
    assert justification(page).startswith('[LEXICAL · profil ')
    assert justification(page).endswith(f'] Note 10, {CAP_MARK}.')


def test_a1_lexical_note_at_or_below_8_is_unmarked(world3):
    gn, api = world3(profile=SHIPPED_PROFILE, repo=dict(FRESH, description='A small tool', topics=['cli']),
                     readme='# repo\nA small tool.', **NO_PROVIDER)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence']['number'] <= 8
    assert justification(page).endswith(']') and 'plafonnée' not in justification(page)


def test_a1_partial_answer_without_reprise_mode_is_capped(world3):
    gn, api = world3(profile=SHIPPED_PROFILE, repo=RICH, readme='docker postgres redis', REQUIRE_LLM='false',
                     answer=dict(ANSWER, utilite_immediate='beaucoup'))
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': 8}
    assert justification(page).endswith(f'Note 10, {CAP_MARK}.')
    assert 'Brique pour' not in page['properties'] and 'Catégorie' not in page['properties']


def test_a1_translation_only_is_capped(world3):
    gn, api = world3(profile=SHIPPED_PROFILE, repo=RICH, readme='docker postgres redis', LLM_SCORING_ENABLED='false',
                     answer={'description_fr': 'Automatisation de flux de travail pour le trading.',
                             'use_cases_fr': '• alertes'})
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': 8}
    assert justification(page).endswith(f'Note 10, {CAP_MARK}.')

# =============================================================================
# A2 — aucune information : fiche créée, Pertinence vide, aucun appel LLM
# =============================================================================
@pytest.mark.parametrize('env', [{}, NO_PROVIDER, {'LLM_SCORING_ENABLED': 'false'}, {'TRANSLATION_ENABLED': 'false'}],
                         ids=['LLM', 'sans fournisseur', 'traduction seule', 'sans traduction'])
def test_a2_every_path_writes_null_pertinence_without_llm(world3, env):
    gn, api = world3(repo=EMPTY_REPO, readme=None, columns=OPTIONAL_TEXT,
                     answer=dict(ANSWER, categorie='Agent IA', brique_pour=['Gitnotate']), **env)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    props = page['properties']
    assert props['Pertinence'] == {'number': None}
    assert justification(page) == NO_INFO
    assert text(page, 'Description') == 'Non vérifié' and text(page, "Cas d'usage") == 'Non vérifié'
    assert 'Catégorie' not in props and 'Brique pour' not in props
    assert text(page, 'Licence') == 'MIT' and props['Stars'] == {'number': 42}       # faits GitHub écrits
    assert api.llm_bodies('mistral') == []                                            # aucun appel LLM
    assert gn.stats.llm_score_total == 0 and gn.stats.translation_total == 0


def test_a2_v71_schema_unchanged_and_null_pertinence_in_payload(world3):
    """Schéma v7.1 inchangé (aucune colonne ni option créée) ; Pertinence null acceptée dans le corps
    POST /v1/pages (même forme que URL ou Dernière MAJ vides), Notion-Version 2022-06-28."""
    gn, api = world3(repo=EMPTY_REPO, readme=None)
    assert {name: kind for name, kind in gn.REQUIRED_DB_PROPERTIES.items()} == \
        {name: kind for name, (kind, _) in V71_COLUMNS.items() if name != 'Justification'}
    assert gn.OPTIONAL_DB_PROPERTIES == {'Licence': ('rich_text', 'select'), 'Catégorie': ('select', 'rich_text'),
                                         'Brique pour': ('multi_select', 'rich_text')}
    assert gn.NOTION_HEADERS['Notion-Version'] == '2022-06-28'
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert set(page['properties']) == set(V71_COLUMNS)
    assert '"Pertinence": {"number": null}' in json.dumps(page, ensure_ascii=False)
    assert_read_and_create_only(api)


@pytest.mark.parametrize('readme', ['# repo\n', 'repo\n====\n', '# Repo #\n\n---\n',
                                    '<p align="center"><img src="x.png"></p>\n# Repo\n',
                                    '[![CI](https://x/badge.svg)](https://x)\n', '![logo](logo.png)\n'])
def test_a2_title_or_badges_only_readme_is_not_information(world3, readme):
    gn, api = world3(repo=EMPTY_REPO, readme=readme)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': None} and api.llm_bodies('mistral') == []


@pytest.mark.parametrize('readme', ['# repo\nConvertit des PDF.\n', '# Convertisseur PDF\n', 'TODO\n',
                                    '# repo\n\n将 PDF 转换为 Markdown 的工具\n'])
def test_a2_readme_with_any_other_text_is_information(load_gn, readme):
    gn = load_gn()
    info = {'full_name': 'owner/repo', 'readme': readme, 'topics': []}
    assert gn.repo_has_no_information(info, '') is False
    assert gn.readme_is_exploitable(gn.clean_readme(readme), 'owner/repo') is True


@pytest.mark.parametrize('info,description', [
    ({'full_name': 'owner/repo', 'topics': ['  ', 3]}, '   '),
    ({'full_name': 'owner/repo', 'topics': None, 'readme': '# REPO\n'}, ''),
    ({'name': 'repo', 'readme': 'Repo\n----\n'}, None),
])
def test_a2_no_information_cases(load_gn, info, description):
    gn = load_gn()
    assert gn.repo_has_no_information(info, description) is True


def test_a2_description_or_topics_are_information(load_gn):
    gn = load_gn()
    assert gn.repo_has_no_information({'full_name': 'owner/repo'}, 'PDF converter') is False
    assert gn.repo_has_no_information({'full_name': 'owner/repo', 'topics': ['ocr']}, '') is False


def test_a2_readme_not_sent_counts_as_absent(load_gn):
    gn = load_gn(README_LLM_CHARS='0')
    info = {'full_name': 'owner/repo', 'readme': 'Convertit des PDF en Markdown.', 'topics': []}
    assert gn.repo_has_no_information(info, '') is True


@pytest.mark.parametrize('extra', [{'fork': True}, {'archived': True}])
def test_a2_fork_or_archived_without_information_is_unscored(world3, extra):
    gn, api = world3(repo=dict(EMPTY_REPO, **extra), readme=None)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': None} and justification(page) == NO_INFO


def test_a2_threshold_never_filters_or_crashes_unscored(world3):
    gn, api = world3(repo=EMPTY_REPO, readme=None, SCORE_MIN_THRESHOLD='5')
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': None}
    assert gn.stats.filtered == 0 and gn.stats.errors == 0 and gn.stats.success == 1


def test_a2_reprise_mode_never_defers_unscored_repo(world3):
    gn, api = world3(repo=EMPTY_REPO, readme=None)
    api.route('POST', r'api\.mistral\.ai', lambda u, p: make_response(200, chat('pas de json'))
              if p.get('max_tokens') != 16 else make_response(200, chat('{"ok": true}')))
    assert gn.main([]) == 0
    assert len(pages_posted(api)) == 1 and gn.stats.deferred == 0


def test_a2_console_summary_and_stats(world3, capsys):
    gn, api = world3(repo=EMPTY_REPO, readme=None)
    assert gn.main([]) == 0
    out = capsys.readouterr().out
    assert '(42 ⭐ | ∅ non notée) (aucune information)' in out
    assert '• Pertinence:      non notée ×1' in out and 'None/10' not in out and 'aucun/10' not in out
    assert history(gn)[-1]['scores_distribution'] == {'aucun': 1}


def test_a2_dry_run_console(world3, capsys):
    gn, api = world3(repo=EMPTY_REPO, readme=None, DRY_RUN='true')
    assert gn.main([]) == 0
    assert '∅ non notée' in capsys.readouterr().out and pages_posted(api) == []


def test_a2_honest_non_verifie_answer_still_written_for_minimal_readme(world3):
    """Dépôt qui dit quelque chose (« TODO ») : le LLM est appelé comme en v7.3 et sa réponse honnête
    « Non vérifié » est écrite telle quelle."""
    gn, api = world3(repo=EMPTY_REPO, readme='TODO\n',
                     answer=dict(ANSWER, description_fr='Non vérifié', cas_usage=[]))
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert len(api.llm_bodies('mistral')) == 1
    assert text(page, 'Description') == 'Non vérifié' and text(page, "Cas d'usage") == 'Non vérifié'
    assert isinstance(page['properties']['Pertinence']['number'], int) and gn.stats.deferred == 0

# =============================================================================
# A3 — distribution Docker seulement pour une image du dépôt analysé
# =============================================================================
@pytest.mark.parametrize('readme,full_name,expected', [
    ('docker run -d -p 5432:5432 postgres:16', 'me/pdf-app', []),
    ('docker run -d redis', 'me/pdf-app', []),
    ('docker pull ollama/ollama', 'open-webui/open-webui', []),
    ('docker pull ollama/ollama', 'ollama/ollama-python', []),          # image au nom du propriétaire : non
    ('docker run -d -p 11434:11434 ollama/ollama', 'ollama/ollama', ['Docker']),
    ('docker run -d --name open-webui ghcr.io/open-webui/open-webui:main', 'open-webui/open-webui', ['Docker']),
    ('docker compose up -d', 'me/pdf-app', []),
    ('docker-compose up', 'me/pdf-app', []),
    ('docker build -t pdf-app .', 'me/pdf-app', []),
    ('docker build -t pdf-app .\ndocker run -p 8000:8000 pdf-app', 'me/pdf-app', ['Docker']),
    ('docker build -t pocketflow-app .\ndocker run -it pocketflow-app', 'The-Pocket/Tutorial-Codebase-Knowledge', []),
    ('services:\n  app:\n    image: ghcr.io/me/pdf-app:1.2\n', 'me/pdf-app', ['Docker']),
    ('services:\n  db:\n    image: postgres:16\n', 'me/pdf-app', []),
    ('[pulls]: https://hub.docker.com/r/lobehub/lobehub', 'lobehub/lobe-chat', []),
    ('See https://hub.docker.com/_/postgres', 'me/pdf-app', []),
    ('Images on ghcr.io/', 'me/pdf-app', []),
    ('docker run --name n8n -d postgres', 'n8n-io/n8n', []),
    ('docker run -it --rm --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n', 'n8n-io/n8n',
     ['Docker']),
    ('docker run \\\n  -p 8080:8080 \\\n  --gpus all \\\n  localai/localai:latest-gpu', 'mudler/LocalAI', ['Docker']),
    ('docker run `\n  -p 8080:8080 `\n  localai/localai', 'mudler/LocalAI', ['Docker']),
    ('docker run ^\n  -p 8080:8080 ^\n  localai/localai', 'mudler/LocalAI', ['Docker']),
    ('Start it with `docker run -p 80:80`\npdf-app converts PDF files.', 'me/pdf-app', []),   # code en ligne
    ('docker run -e KEY=VAL --env=X me/pdf-app', 'me/pdf-app', ['Docker']),
    ('docker run -p 3000:3000 vezlo/src-to-kb-api', 'vezlo/src-to-kb', ['Docker']),
    ('docker run -p 3000:3000 other/src-to-kb-api', 'vezlo/src-to-kb', []),
    ('![pulls](https://img.shields.io/docker/pulls/me/pdf-app)', 'me/pdf-app', ['Docker']),
    ('docker run the image', 'me/pdf-app', []),
    ('docker run -p 80:80 o/x', 'o/x', []),                       # nom de moins de 3 caractères : jamais
    ('docker run -p 80:80 o/x-api', 'o/x', []),
])
def test_a3_docker_only_for_the_repo_image(load_gn, readme, full_name, expected):
    gn = load_gn()
    assert gn.readme_hints(readme, full_name)['distribution'] == expected


def test_a3_third_party_image_not_in_llm_message(world3):
    readme = '# pdf-app\n\nConverts PDF files.\n\n```\ndocker run -d -p 5432:5432 postgres:16\n```\n'
    gn, api = world3(repo=dict(FRESH, full_name='me/pdf-app'), readme=readme)
    assert gn.main([]) == 0
    (body,) = api.llm_bodies('mistral')
    user = body['messages'][1]['content']
    assert 'distribution détectée' not in user and 'indices : aucun' in user
    assert 'docker run -d -p 5432:5432 postgres:16' in user                    # README toujours transmis


def test_a3_cache_format_4_rereads_old_hints(world3):
    gn, api = world3(repo=FRESH)
    assert gn.CACHE_FORMAT >= 4          # 5 depuis la revue du lot 4 (README illisible jamais mis en cache)
    old = {'name': 'repo', 'full_name': 'owner/repo', 'description': 'x', 'stars': 1, 'readme': 'x',
           'readme_hints': {'distribution': ['Docker'], 'gpu': None, 'gpu_source': ''}, 'readme_sections': {},
           'cached_at': time.time(), 'cache_format': 3, 'private': False}
    assert gn._cache_entry_valid(old) is False
    gn.CACHE_FILE.write_text(json.dumps({'owner/repo': old}), encoding='utf-8')
    assert gn.main([]) == 0
    assert api.count('GET', r'api\.github\.com/repos/owner/repo$') == 1
    (body,) = api.llm_bodies('mistral')
    assert 'Docker' not in body['messages'][1]['content'].split('README (extrait nettoyé)')[0]

# =============================================================================
# A4 — repli lexical : langage neutre, pénalité seulement si établie par le profil
# =============================================================================
def test_a4_language_never_changes_lexical_score(load_gn):
    gn = load_gn()
    gn.USER_PROFILE = SHIPPED_PROFILE
    base = {'description': 'Self-hosted workflow automation for trading alerts', 'topics': ['automation']}
    scores = {gn.calculate_relevance_score(dict(base, language=lang)) for lang in
              ('Python', 'JavaScript', 'TypeScript', 'Rust', 'Go', 'Java', 'C++', None)}
    assert len(scores) == 1
    assert gn.calculate_relevance_score({'language': 'Python'}) == 0


def test_a4_empty_python_repo_lexical_path_is_unscored_not_3(world3):
    """En v7.3, un dépôt vide en Python valait 3 en repli lexical (bonus de langage seul)."""
    gn, api = world3(profile=SHIPPED_PROFILE, repo=dict(EMPTY_REPO, language='Python'), readme=None, **NO_PROVIDER)
    assert gn.main([]) == 0
    (page,) = pages_posted(api)
    assert page['properties']['Pertinence'] == {'number': None}


@pytest.mark.parametrize('topic', ['game', 'games', 'gamedev', 'game-engine', 'ios', 'android', 'mobile-app'])
def test_a4_no_hardcoded_topic_penalty(load_gn, topic):
    gn = load_gn()
    gn.USER_PROFILE = SHIPPED_PROFILE
    base = {'description': 'Finance toolkit', 'topics': ['finance']}
    assert gn.calculate_relevance_score(dict(base, topics=['finance', topic])) == gn.calculate_relevance_score(base)


def test_a4_slug_exclusion_caps_lexical_at_2(load_gn):
    gn = load_gn()
    gn.USER_PROFILE = dict(TEST_PROFILE, exclusions=['jeux vidéo', 'game-engine', 'Game Engine'])
    assert gn.lexical_exclusion_topics() == {'game-engine'}
    rich = {'description': 'ai ocr fastapi docker automation trading', 'topics': ['ai', 'ocr', 'game-engine']}
    assert gn.calculate_relevance_score(rich) == 2
    assert gn.calculate_relevance_score(dict(rich, topics=['ai', 'ocr', 'game'])) > 2       # « game » non exclu
    gn.USER_PROFILE = dict(TEST_PROFILE, exclusions=['jeux vidéo et moteurs de jeu'])
    assert gn.lexical_exclusion_topics() == set()
    assert gn.calculate_relevance_score(rich) > 2                                             # phrase : non lue
    assert not hasattr(gn, 'IRRELEVANT_TOPICS')


def test_a4_shipped_profile_has_no_slug_exclusion(load_gn):
    """Avec le profil livré (exclusion écrite en phrase), le repli lexical n'applique aucune exclusion."""
    gn = load_gn()
    assert gn.lexical_exclusion_topics(gn.normalize_profile(SHIPPED_PROFILE)[0]) == set()

# =============================================================================
# VERSION 7.4.0 ET EMPREINTE
# =============================================================================
def test_version_and_scoring_rules(load_gn):
    gn = load_gn()
    assert gn.__version__ == '7.4.0' and gn.SCORING_RULES == '7.4'
    assert gn.__doc__.lstrip().startswith('GitNotate v7.4') and 'Nouveautés v7.4' in gn.__doc__


def test_hash_includes_scoring_rules(load_gn):
    gn = load_gn()
    canonical = json.dumps(gn.USER_PROFILE, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    prompt = gn.build_system_prompt_combined()
    v73 = hashlib.sha1((canonical + prompt).encode('utf-8')).hexdigest()[:6]
    assert gn.compute_profile_hash() == hashlib.sha1((canonical + prompt + '7.4').encode('utf-8')).hexdigest()[:6]
    assert gn.compute_profile_hash() != v73


def test_end_banner_mentions_v74(world3, capsys):
    gn, api = world3(repo=FRESH)
    assert gn.main([]) == 0
    assert 'Notes v7.4' in capsys.readouterr().out
