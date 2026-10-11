"""Tests du nettoyeur sûr clean_page_duplicates.py.

Réseau 100 % simulé : FakeNotion (en mémoire) remplace requests.Session.
Le script est importé comme module : rien ne doit s'exécuter hors de main().
"""
import builtins
import importlib
import importlib.util
import io
import json
import os
import random
import re
import sys
from pathlib import Path

import pytest
import requests

cpd = importlib.import_module('clean_page_duplicates')
SCRIPT = Path(cpd.__file__)

CLEANER_TOKEN = 'ntn_CLEANER_secret_1234567890'
MAIN_TOKEN = 'ntn_MAIN_secret_0987654321'
URL = 'https://github.com/x/y'


# =============================================================================
# FAUX SERVEUR NOTION
# =============================================================================
def resp(status, payload=None, headers=None, raw=None):
    r = requests.Response()
    r.status_code = status
    r._content = raw if raw is not None else json.dumps(payload if payload is not None else {}).encode()
    r.headers.update(headers or {})
    return r


class FakeNotion:
    """Faux serveur Notion (blocs uniquement), utilisé à la place de requests.Session."""

    def __init__(self):
        self.blocks = {}          # id -> bloc (avec 'children': [ids])
        self.errors = {}          # (MÉTHODE, regex chemin) -> [statut | (statut, en-têtes) | exception, ...]
        self.calls = []           # (méthode, chemin, corps json)
        self.headers_seen = []
        self.page_size = 100
        self.before_write = None  # hook(méthode, chemin) appelé avant chaque DELETE / PATCH

    def add_block(self, bid, btype, parent='root', children=None, created='2026-01-01T00:00:00.000Z',
                  **payload):
        block = {'object': 'block', 'id': bid, 'type': btype, btype: payload,
                 'has_children': bool(children),
                 'parent': {'type': 'block_id', 'block_id': parent}, 'archived': False, 'in_trash': False,
                 'created_time': created, 'last_edited_time': '2026-01-01T00:00:00.000Z',
                 'children': list(children or [])}
        self.blocks[bid] = block
        return block

    def nest(self, bid, parent):
        self.blocks[parent]['children'].append(bid)
        self.blocks[parent]['has_children'] = True

    def request(self, method, url, headers=None, timeout=None, params=None, json=None, **kw):
        method = method.upper()
        path = url.split('/v1', 1)[1]
        self.calls.append((method, path, json))
        self.headers_seen.append(dict(headers or {}))
        for (m, rx), seq in self.errors.items():
            if m == method and re.fullmatch(rx, path) and seq:
                err = seq.pop(0)
                if isinstance(err, Exception):
                    raise err
                status, hdrs = err if isinstance(err, tuple) else (err, {})
                return resp(status, {'object': 'error', 'status': status}, headers=hdrs)
        if method in ('DELETE', 'PATCH') and self.before_write:
            self.before_write(method, path)
        m = re.fullmatch(r'/blocks/([^/]+)/children', path)
        if m and method == 'GET':
            node = self.blocks.get(m.group(1))
            if node is None:
                return resp(404)
            kids = [self.blocks[c] for c in node['children'] if not self.blocks[c]['in_trash']]
            start = int((params or {}).get('start_cursor') or 0)
            chunk = kids[start:start + self.page_size]
            more = start + self.page_size < len(kids)
            return resp(200, {'results': [self._pub(b) for b in chunk], 'has_more': more,
                              'next_cursor': str(start + self.page_size) if more else None})
        m = re.fullmatch(r'/blocks/([^/]+)', path)
        if m:
            block = self.blocks.get(m.group(1))
            if block is None:
                return resp(404)
            if method == 'GET':
                return resp(200, self._pub(block))
            if method == 'DELETE':
                block['in_trash'] = block['archived'] = True
                return resp(200, self._pub(block))
            if method == 'PATCH':
                for key in ('archived', 'in_trash'):
                    if key in (json or {}):
                        block['in_trash'] = block['archived'] = bool(json[key])
                return resp(200, self._pub(block))
        raise AssertionError(f'requête non prévue : {method} {path}')

    @staticmethod
    def _pub(block):
        return {k: v for k, v in block.items() if k != 'children'}

    def writes(self):
        return [(m, p, j) for m, p, j in self.calls if m in ('DELETE', 'PATCH', 'PUT', 'POST')]


# =============================================================================
# OUTILS DE TEST
# =============================================================================
@pytest.fixture(autouse=True)
def _cleaner_env(monkeypatch):
    monkeypatch.setenv('NOTION_CLEANER_TOKEN', CLEANER_TOKEN)
    monkeypatch.setenv('PARENT_PAGE_ID', 'root')


def page_with(fake, specs):
    """specs : (id, type, url|None, légende, parent[, created]) ; construit l'arbre sous 'root'."""
    if 'root' not in fake.blocks:
        fake.add_block('root', 'child_page', parent='ws')
    for spec in specs:
        bid, btype, url, cap, parent = spec[:5]
        extra = {'created': spec[5]} if len(spec) > 5 else {}
        payload = {'url': url, 'caption': [{'plain_text': cap}] if cap else []} if url else {'rich_text': []}
        fake.add_block(bid, btype, parent=parent, **extra, **payload)
        fake.nest(bid, parent)


def simple_dup(fake, cap_k='', cap_d=''):
    page_with(fake, [('k', 'bookmark', URL, cap_k, 'root'), ('d', 'bookmark', URL, cap_d, 'root')])


def run(fake, *argv, answer=None, confirm=None, sleep=None):
    if confirm is None:
        def confirm(phrase):
            return phrase if answer is None else answer
    return cpd.main(list(argv), session=fake, confirm=confirm, sleep=sleep or (lambda s: None))


def deleted(fake):
    return [p.rsplit('/', 1)[-1] for m, p, _ in fake.calls if m == 'DELETE']


def journal_files(base):
    return sorted((Path(base) / 'journal').glob('cleaner-*.jsonl'))


def read_records(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def write_journal(path, records, raw_tail=None):
    lines = [json.dumps(r) for r in records]
    if raw_tail is not None:
        lines.append(raw_tail)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def trashed_block(fake, bid, url=URL):
    if 'root' not in fake.blocks:
        fake.add_block('root', 'child_page', parent='ws')
    fake.add_block(bid, 'bookmark', url=url, caption=[])
    fake.blocks[bid]['in_trash'] = fake.blocks[bid]['archived'] = True


# =============================================================================
# IMPORT ET CONFIGURATION
# =============================================================================
def test_import_has_no_side_effects(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv('GITNOTATE_NO_DOTENV')
    monkeypatch.delenv('NOTION_CLEANER_TOKEN')
    (tmp_path / '.env').write_text('NOTION_CLEANER_TOKEN=fuite\n', encoding='utf-8')

    def boom(*a, **k):
        raise AssertionError('requête à l\'import')
    monkeypatch.setattr(requests.Session, 'request', boom)
    before = sorted(p.name for p in tmp_path.iterdir())
    spec = importlib.util.spec_from_file_location('cpd_import_check', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert capsys.readouterr() == ('', '')
    assert 'NOTION_CLEANER_TOKEN' not in os.environ
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert callable(module.main)


def test_notion_version_and_trash_field():
    assert cpd.NOTION_VERSION == '2022-06-28'
    assert cpd.TRASH_FIELD == 'archived'
    assert cpd.trash_field('2022-06-28') == 'archived'
    assert cpd.trash_field('2025-09-03') == 'archived'
    assert cpd.trash_field('2026-03-11') == 'in_trash'
    f = FakeNotion()
    simple_dup(f)
    run(f)
    assert {h['Notion-Version'] for h in f.headers_seen} == {'2022-06-28'}


def test_cleaner_token_has_priority(monkeypatch, capsys):
    monkeypatch.setenv('NOTION_TOKEN', MAIN_TOKEN)
    f = FakeNotion()
    simple_dup(f)
    assert run(f) == 0
    assert {h['Authorization'] for h in f.headers_seen} == {f'Bearer {CLEANER_TOKEN}'}
    assert 'NOTION_CLEANER_TOKEN absent' not in capsys.readouterr().out


def test_fallback_to_notion_token_warns(monkeypatch, capsys):
    monkeypatch.delenv('NOTION_CLEANER_TOKEN')
    monkeypatch.setenv('NOTION_TOKEN', MAIN_TOKEN)
    f = FakeNotion()
    simple_dup(f)
    assert run(f) == 0
    out = capsys.readouterr().out
    assert {h['Authorization'] for h in f.headers_seen} == {f'Bearer {MAIN_TOKEN}'}
    assert 'NOTION_CLEANER_TOKEN absent' in out
    assert 'intégration Notion dédiée' in out and 'Update content' in out


def test_token_never_printed_in_clear(monkeypatch, capsys):
    monkeypatch.setenv('NOTION_TOKEN', MAIN_TOKEN)
    f = FakeNotion()
    simple_dup(f)
    run(f, '--apply')
    out = capsys.readouterr().out
    assert CLEANER_TOKEN not in out and MAIN_TOKEN not in out
    assert 'ntn_...7890' in out


@pytest.mark.parametrize('unset', ['token', 'page'])
def test_missing_config_exit_1(monkeypatch, unset):
    if unset == 'token':
        monkeypatch.delenv('NOTION_CLEANER_TOKEN')
    else:
        monkeypatch.delenv('PARENT_PAGE_ID')
    f = FakeNotion()
    simple_dup(f)
    assert run(f, '--apply') == 1
    assert f.calls == []


@pytest.mark.parametrize('value', ['abc', '-1', '2.5'])
def test_invalid_max_delete_exit_1(monkeypatch, value):
    monkeypatch.setenv('CLEANER_MAX_DELETE', value)
    f = FakeNotion()
    simple_dup(f)
    assert run(f, '--apply') == 1
    assert f.calls == []


def test_page_id_as_url_rejected(monkeypatch):
    monkeypatch.setenv('PARENT_PAGE_ID', 'https://www.notion.so/Ma-Page-1cab36ca5523800292cad5f59ab1fc0c')
    f = FakeNotion()
    assert run(f) == 1
    assert f.calls == []


def test_unknown_argument_exit_1(capsys):
    assert cpd.main(['--bogus'], session=FakeNotion()) == 1


def test_root_unauthorized_is_config_error(capsys):
    f = FakeNotion()
    simple_dup(f)
    f.errors[('GET', r'/blocks/root/children')] = [401]
    assert run(f, '--apply') == 1
    assert deleted(f) == []
    assert 'jeton refusé' in capsys.readouterr().out


def test_dotenv_loaded_from_base_dir(tmp_path, monkeypatch):
    pytest.importorskip('dotenv')
    monkeypatch.delenv('NOTION_CLEANER_TOKEN')
    monkeypatch.delenv('PARENT_PAGE_ID')
    monkeypatch.delenv('GITNOTATE_NO_DOTENV')
    (tmp_path / '.env').write_text(f'NOTION_CLEANER_TOKEN={CLEANER_TOKEN}\nPARENT_PAGE_ID=root\n',
                                   encoding='utf-8')
    f = FakeNotion()
    simple_dup(f)
    assert run(f) == 0
    assert f.headers_seen[0]['Authorization'] == f'Bearer {CLEANER_TOKEN}'


def test_dotenv_disabled_by_flag(tmp_path, monkeypatch):
    monkeypatch.delenv('NOTION_CLEANER_TOKEN')
    (tmp_path / '.env').write_text(f'NOTION_CLEANER_TOKEN={CLEANER_TOKEN}\n', encoding='utf-8')
    f = FakeNotion()
    simple_dup(f)
    assert run(f) == 1          # GITNOTATE_NO_DOTENV=1 (conftest) : .env ignoré, jeton absent
    assert 'NOTION_CLEANER_TOKEN' not in os.environ


# =============================================================================
# SIMULATION PAR DÉFAUT ET CONFIRMATION (I9)
# =============================================================================
def test_default_is_simulation_even_with_dry_run_false(monkeypatch, capsys):
    monkeypatch.setenv('DRY_RUN', 'false')
    f = FakeNotion()
    simple_dup(f)
    asked = []
    assert run(f, confirm=lambda p: asked.append(p) or p) == 0
    assert deleted(f) == [] and f.writes() == [] and asked == []
    assert 'SIMULATION' in capsys.readouterr().out


def test_dry_run_variable_is_not_read(monkeypatch):
    monkeypatch.setenv('DRY_RUN', 'true')
    f = FakeNotion()
    simple_dup(f)
    assert run(f, '--apply') == 0       # seul --apply + phrase exacte décide
    assert deleted(f) == ['d']
    assert 'DRY_RUN' not in re.findall(r"environ\.get\('([A-Z_]+)'", SCRIPT.read_text(encoding='utf-8'))


@pytest.mark.parametrize('answer', ['o', 'O', 'y', 'YES', 'yes', 'OUI', 'oui', '', 'supprimer 1',
                                    'SUPPRIMER 2', 'SUPPRIMER'])
def test_confirmation_requires_exact_phrase(answer):
    f = FakeNotion()
    simple_dup(f)
    assert run(f, '--apply', answer=answer) == 2
    assert deleted(f) == []


def test_confirmation_phrase_tolerates_surrounding_spaces():
    f = FakeNotion()
    simple_dup(f)
    assert run(f, '--apply', answer='  SUPPRIMER 1 \n') == 0
    assert deleted(f) == ['d']


def test_plan_displayed_before_confirmation(capsys):
    f = FakeNotion()
    page_with(f, [('k', 'bookmark', URL, 'ma note', 'root'),
                  ('d', 'bookmark', 'https://github.com/X/Y/', '', 'root')])
    shown = {}

    def confirm(phrase):
        shown['out'] = capsys.readouterr().out
        shown['phrase'] = phrase
        return phrase
    assert run(f, '--apply', confirm=confirm) == 0
    assert shown['phrase'] == 'SUPPRIMER 1'
    out = shown['out']
    assert 'https://github.com/X/Y/' in out
    assert 'supprimé : d' in out and 'conservé : k' in out and 'ma note' in out
    assert deleted(f) == ['d']


class _FakeTTY(io.StringIO):
    def isatty(self):
        return True


def test_apply_without_terminal_aborts(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'stdin', io.StringIO('SUPPRIMER 1\n'))
    f = FakeNotion()
    simple_dup(f)
    assert cpd.main(['--apply'], session=f, sleep=lambda s: None) == 2
    assert deleted(f) == []
    assert 'terminal interactif' in capsys.readouterr().out


@pytest.mark.parametrize('answer', ['o', 'OUI', 'oui', 'yes', EOFError()])
def test_apply_in_terminal_refuses_short_answers(monkeypatch, answer):
    monkeypatch.setattr(sys, 'stdin', _FakeTTY())

    def fake_input(prompt=''):
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(builtins, 'input', fake_input)
    f = FakeNotion()
    simple_dup(f)
    assert cpd.main(['--apply'], session=f, sleep=lambda s: None) == 2
    assert deleted(f) == []


def test_apply_in_terminal_with_exact_phrase(monkeypatch):
    monkeypatch.setattr(sys, 'stdin', _FakeTTY())
    prompts = []
    monkeypatch.setattr(builtins, 'input', lambda prompt='': prompts.append(prompt) or 'SUPPRIMER 1')
    f = FakeNotion()
    simple_dup(f)
    assert cpd.main(['--apply'], session=f, sleep=lambda s: None) == 0
    assert deleted(f) == ['d']
    assert 'SUPPRIMER 1' in prompts[0]


# =============================================================================
# PÉRIMÈTRE (I8) ET BLOCS SYNCHRONISÉS
# =============================================================================
def test_synced_block_same_id_never_deleted():
    f = FakeNotion()
    page_with(f, [('orig', 'synced_block', None, '', 'root'), ('copy', 'synced_block', None, '', 'root')])
    f.blocks['orig']['synced_block'] = {'synced_from': None}
    f.blocks['copy']['synced_block'] = {'synced_from': {'block_id': 'orig'}}
    f.add_block('bk', 'bookmark', parent='orig', url='https://github.com/acme/tool', caption=[])
    f.blocks['orig']['children'] = ['bk']
    f.blocks['copy']['children'] = ['bk']
    f.blocks['orig']['has_children'] = f.blocks['copy']['has_children'] = True
    assert run(f, '--apply') == 0
    assert deleted(f) == []


def test_same_id_listed_twice_never_deleted():
    f = FakeNotion()
    page_with(f, [('t1', 'toggle', None, '', 'root'), ('t2', 'toggle', None, '', 'root')])
    f.add_block('bk', 'bookmark', parent='t1', url=URL, caption=[])
    f.nest('bk', 't1')
    f.nest('bk', 't2')          # même block_id renvoyé sous deux parents
    assert run(f, '--apply') == 0
    assert deleted(f) == []


def test_synced_copy_children_not_listed():
    f = FakeNotion()
    page_with(f, [('orig', 'synced_block', None, '', 'root'), ('copy', 'synced_block', None, '', 'root')])
    f.blocks['orig']['synced_block'] = {'synced_from': None}
    f.blocks['copy']['synced_block'] = {'synced_from': {'block_id': 'orig'}}
    f.add_block('bk1', 'bookmark', parent='orig', url='https://github.com/acme/tool', caption=[])
    f.add_block('bk2', 'bookmark', parent='copy', url='https://github.com/acme/tool', caption=[])
    f.blocks['orig']['children'] = ['bk1']
    f.blocks['copy']['children'] = ['bk2']
    f.blocks['orig']['has_children'] = f.blocks['copy']['has_children'] = True
    run(f, '--apply')
    assert '/blocks/copy/children' not in [p for _, p, _ in f.calls]
    assert 'DELETE' not in [m for m, _, _ in f.calls]


def test_synced_original_children_never_deleted_nor_kept():
    f = FakeNotion()
    page_with(f, [('top', 'bookmark', URL, '', 'root', '2026-05-01T00:00:00.000Z'),
                  ('orig', 'synced_block', None, '', 'root')])
    f.blocks['orig']['synced_block'] = {'synced_from': None}
    f.add_block('inside', 'bookmark', parent='orig', url=URL, caption=[], created='2020-01-01T00:00:00.000Z')
    f.nest('inside', 'orig')
    assert run(f, '--apply') == 0
    assert deleted(f) == []
    scan = cpd.read_source(cpd.NotionClient('t', session=f, sleep=lambda s: None), 'root')
    plan = cpd.build_plan(scan.entries)
    assert [(e.block_id, why) for e, why, _ in plan.manual] == [('inside', 'bloc synchronisé (jamais supprimé)')]


def test_subpage_not_touched():
    f = FakeNotion()
    page_with(f, [('top', 'bookmark', URL, '', 'root')])
    f.add_block('sub', 'child_page', parent='root', title='Projet X')
    f.nest('sub', 'root')
    f.add_block('inproj', 'bookmark', parent='sub', url=URL, caption=[])
    f.nest('inproj', 'sub')
    assert run(f, '--apply') == 0
    assert deleted(f) == []
    assert ('GET', '/blocks/sub/children', None) not in f.calls


def test_child_database_and_link_to_page_not_descended():
    f = FakeNotion()
    page_with(f, [('top', 'bookmark', URL, '', 'root')])
    f.add_block('db', 'child_database', parent='root', title='Base')
    f.nest('db', 'root')
    f.add_block('row', 'bookmark', parent='db', url=URL, caption=[])
    f.nest('row', 'db')
    f.add_block('lnk', 'link_to_page', parent='root', type='page_id', page_id='ailleurs')
    f.nest('lnk', 'root')
    f.blocks['lnk']['has_children'] = True
    f.blocks['lnk']['children'] = ['row']
    assert run(f, '--apply') == 0
    paths = [p for _, p, _ in f.calls]
    assert '/blocks/db/children' not in paths and '/blocks/lnk/children' not in paths
    assert deleted(f) == []


# =============================================================================
# CHOIX DU BLOC CONSERVÉ ET GARANTIES (I4, I6)
# =============================================================================
def test_plan_dedupes_by_block_id():
    e = cpd.Entry('same', 'bookmark', URL, 'github.com/x/y', order=1, depth=0)
    e2 = cpd.Entry('same', 'bookmark', URL, 'github.com/x/y', order=5, depth=1)
    assert cpd.build_plan([e, e2]).deletions == []
    k = cpd.Entry('k', 'bookmark', URL, 'github.com/x/y', order=0, depth=0)
    plan = cpd.build_plan([k, e, e2])
    assert [d.block_id for d, _ in plan.deletions] == ['same']       # un seul DELETE par bloc
    assert plan.manual == []


def test_never_same_id_as_keeper():
    entries = [cpd.Entry('A-b', 'bookmark', URL, 'github.com/x/y', order=1),
               cpd.Entry('ab', 'embed', URL, 'github.com/x/y', order=2)]    # même id, tirets/casse près
    plan = cpd.build_plan(entries)
    assert plan.deletions == []
    for target, keeper in cpd.build_plan(entries + [cpd.Entry('c', 'bookmark', URL, 'github.com/x/y',
                                                              order=3)]).deletions:
        assert cpd.norm_id(target.block_id) != cpd.norm_id(keeper.block_id)


def test_plan_defense_in_depth_same_block_in_two_groups():
    # Impossible depuis read_source (un bloc lien n'a qu'une URL) : barrière de secours du plan
    a, b = 'github.com/x/a', 'github.com/x/b'
    entries = [cpd.Entry('ka', 'bookmark', URL, a, order=1), cpd.Entry('x', 'bookmark', URL, a, order=2),
               cpd.Entry('kb', 'bookmark', URL, b, order=3), cpd.Entry('x', 'bookmark', URL, b, order=4)]
    assert [t.block_id for t, _ in cpd.build_plan(entries).deletions] == ['x']
    entries = [cpd.Entry('y', 'bookmark', URL, a, order=1), cpd.Entry('z', 'bookmark', URL, a, order=2),
               cpd.Entry('w', 'bookmark', URL, b, order=0), cpd.Entry('y', 'bookmark', URL, b, order=3)]
    plan = cpd.build_plan(entries)
    assert [t.block_id for t, _ in plan.deletions] == ['z']          # y est conservé ailleurs : jamais supprimé
    assert [e.block_id for e, _, _ in plan.manual] == ['y']


def test_caption_never_lost():
    f = FakeNotion()
    page_with(f, [('a', 'bookmark', URL, '', 'root'), ('b', 'bookmark', URL + '/', 'note perso', 'root')])
    assert run(f, '--apply') == 0
    assert deleted(f) == ['a']                  # on garde b (légende), on supprime a
    f2 = FakeNotion()
    page_with(f2, [('a', 'bookmark', URL, 'note A', 'root'), ('b', 'bookmark', URL, 'note B', 'root')])
    assert run(f2, '--apply') == 0
    assert deleted(f2) == []                    # deux légendes différentes : rien


def test_caption_contained_in_keeper_caption_allows_delete(capsys):
    f = FakeNotion()
    page_with(f, [('k', 'bookmark', URL, 'outil de veille utile', 'root'),
                  ('d', 'bookmark', URL, 'veille', 'root'),
                  ('e', 'bookmark', URL, 'autre note', 'root')])
    assert run(f, '--apply') == 0
    assert deleted(f) == ['d']
    out = capsys.readouterr().out
    assert 'À TRAITER À LA MAIN' in out and 'légende absente du bloc conservé' in out


def test_text_mention_is_not_a_keeper():
    f = FakeNotion()
    page_with(f, [('b1', 'bookmark', URL, '', 'root')])
    f.add_block('p1', 'paragraph', parent='root', rich_text=[
        {'plain_text': 'alt.', 'text': {'content': 'alt.', 'link': {'url': URL}}}])
    f.blocks['root']['children'].insert(0, 'p1')
    plan = cpd.build_plan(cpd.read_source(cpd.NotionClient('t', session=f, sleep=lambda s: None), 'root').entries)
    assert plan.deletions == []
    assert [(e.block_id, k.block_id) for e, _, k in plan.manual] == [('p1', 'b1')]
    assert run(f, '--apply') == 0
    assert deleted(f) == []


def test_text_links_never_deleted():
    f = FakeNotion()
    page_with(f, [('bk', 'bookmark', URL, '', 'root')])
    for pid, content in (('p1', 'voir https://github.com/x/y.'), ('p2', 'encore https://github.com/X/Y')):
        f.add_block(pid, 'paragraph', parent='root',
                    rich_text=[{'plain_text': content, 'text': {'content': content, 'link': None}}])
        f.nest(pid, 'root')
    assert run(f, '--apply') == 0
    assert deleted(f) == []
    scan = cpd.read_source(cpd.NotionClient('t', session=f, sleep=lambda s: None), 'root')
    assert sorted(e.block_id for e in scan.entries) == ['bk', 'p1', 'p2']
    plan = cpd.build_plan(scan.entries)
    assert {e.block_id for e, _, _ in plan.manual} == {'p1', 'p2'}


def test_block_with_children_never_deleted(capsys):
    f = FakeNotion()
    simple_dup(f)
    f.add_block('child', 'paragraph', parent='d', rich_text=[])
    f.nest('child', 'd')
    plan = cpd.build_plan(cpd.read_source(cpd.NotionClient('t', session=f, sleep=lambda s: None), 'root').entries)
    assert plan.deletions == []
    assert [(e.block_id, why) for e, why, _ in plan.manual] == [('d', 'bloc avec enfants')]
    assert run(f, '--apply') == 0
    assert deleted(f) == []
    assert 'bloc avec enfants' in capsys.readouterr().out


def test_keeper_prefers_top_level_then_caption_then_oldest_then_order():
    # premier niveau (même plus récent) plutôt qu'un bloc imbriqué plus ancien
    f = FakeNotion()
    page_with(f, [('t', 'toggle', None, '', 'root'),
                  ('old', 'bookmark', URL, '', 't', '2020-01-01T00:00:00.000Z'),
                  ('new', 'bookmark', URL, '', 'root', '2026-06-01T00:00:00.000Z')])
    run(f, '--apply')
    assert deleted(f) == ['old']
    # le plus ancien, même placé après
    f = FakeNotion()
    page_with(f, [('a', 'bookmark', URL, '', 'root', '2026-05-01T00:00:00.000Z'),
                  ('b', 'bookmark', URL, '', 'root', '2026-01-01T00:00:00.000Z')])
    run(f, '--apply')
    assert deleted(f) == ['a']
    # même date : ordre de lecture
    f = FakeNotion()
    page_with(f, [('a', 'embed', URL, '', 'root'), ('b', 'link_preview', URL, '', 'root')])
    run(f, '--apply')
    assert deleted(f) == ['b']
    # la légende passe avant l'ancienneté
    f = FakeNotion()
    page_with(f, [('a', 'bookmark', URL, '', 'root', '2020-01-01T00:00:00.000Z'),
                  ('b', 'bookmark', URL, 'note', 'root', '2026-01-01T00:00:00.000Z')])
    run(f, '--apply')
    assert deleted(f) == ['a']


# =============================================================================
# CLÉ DE DOUBLON STRICTE (I7)
# =============================================================================
def test_strict_key():
    k = cpd.strict_github_key
    assert k('https://github.com/a/b/blob/main/Docs/X.md') != k('https://github.com/a/b/blob/main/docs/x.md')
    assert k('https://github.com/a/b/tree/main') != k('https://github.com/a/b')
    same = {k(u) for u in ['https://github.com/A/B', 'http://www.github.com/a/b/', 'https://github.com/a/b.git',
                           'https://github.com/a/b?tab=readme-ov-file', 'https://github.com/a/b#readme',
                           'https://github.com/a/b?utm_source=x']}
    assert same == {'github.com/a/b'}
    assert k('https://gist.github.com/a/b') is None


def test_strict_key_more_cases():
    k = cpd.strict_github_key
    assert k('https://github.com/a/b/tree/main/examples') != k('https://github.com/a/b')
    assert k('https://github.com/a/b/tree/main/examples') != k('https://github.com/a/b/tree/main')
    assert k('https://github.com/a/b#readme-ov-file') == 'github.com/a/b'
    assert k('https://github.com/a/b#installation') == 'github.com/a/b#installation'
    assert k('https://github.com/a/b?utm_medium=m&utm_source=s&tab=stars') == 'github.com/a/b'
    assert k('https://github.com/a/b?x=1&y=2') == k('https://github.com/a/b?y=2&x=1') == 'github.com/a/b?x=1&y=2'
    assert k('https://github.com/a/b?x=1') != k('https://github.com/a/b')
    assert k('https://github.com/a/b/issues/12') == 'github.com/a/b/issues/12'
    assert k('https://GitHub.com/Owner/Repo/tree/Main') == 'github.com/owner/repo/tree/Main'
    assert k('github.com/a/b') == 'github.com/a/b'
    assert k('https://github.com/a') is None
    assert k('https://gitlab.com/a/b') is None
    assert k('https://github.com.evil.example/a/b') is None
    assert k('') is None and k(None) is None


def test_strict_key_applied_by_cleaner():
    f = FakeNotion()
    page_with(f, [('r', 'bookmark', 'https://github.com/acme/tool', '', 'root'),
                  ('e', 'bookmark', 'https://github.com/acme/tool/tree/main/examples', '', 'root'),
                  ('c', 'bookmark', 'https://github.com/acme/tool/blob/main/README.md', '', 'root'),
                  ('c2', 'bookmark', 'https://github.com/acme/tool/blob/main/readme.md', '', 'root'),
                  ('w', 'bookmark', 'https://www.github.com/Acme/Tool/?tab=readme-ov-file', '', 'root')])
    assert run(f, '--apply') == 0
    assert deleted(f) == ['w']


# =============================================================================
# LECTURE COMPLÈTE OU RIEN (I3)
# =============================================================================
def _page_with_toggle(f):
    page_with(f, [('a', 'bookmark', URL, '', 'root'), ('b', 'bookmark', URL, '', 'root'),
                  ('t', 'toggle', None, '', 'root')])
    f.add_block('c', 'bookmark', parent='t', url='https://github.com/x/z', caption=[])
    f.nest('c', 't')


def test_partial_read_aborts():
    f = FakeNotion()
    _page_with_toggle(f)
    f.errors[('GET', r'/blocks/t/children')] = [429] * 10
    assert run(f, '--apply') == 2
    assert deleted(f) == []


@pytest.mark.parametrize('error', [500, 502, 503, requests.ConnectionError('coupure'), requests.Timeout('lent'),
                                   400, 404])
def test_partial_read_variants_abort(error, capsys):
    f = FakeNotion()
    _page_with_toggle(f)
    f.errors[('GET', r'/blocks/t/children')] = [error] * 10
    asked = []
    assert run(f, '--apply', confirm=lambda p: asked.append(p) or p) == 2
    assert deleted(f) == [] and asked == []
    assert 'ABANDON' in capsys.readouterr().out


def test_unreadable_json_aborts():
    f = FakeNotion()
    _page_with_toggle(f)
    orig = f.request

    def broken(method, url, **kw):
        if url.endswith('/blocks/t/children'):
            orig(method, url, **kw)
            return resp(200, raw=b'<html>erreur</html>')
        return orig(method, url, **kw)
    f.request = broken
    assert run(f, '--apply') == 2
    assert deleted(f) == []


def test_has_more_without_cursor_aborts():
    f = FakeNotion()
    simple_dup(f)
    orig = f.request

    def broken(method, url, **kw):
        r = orig(method, url, **kw)
        if url.endswith('/blocks/root/children'):
            d = r.json()
            d['has_more'] = True
            d['next_cursor'] = None
            r._content = json.dumps(d).encode()
        return r
    f.request = broken
    assert run(f, '--apply') == 2
    assert deleted(f) == []


def test_failure_on_second_page_aborts():
    f = FakeNotion()
    f.page_size = 1
    page_with(f, [('a', 'bookmark', URL, '', 'root'), ('b', 'bookmark', URL, '', 'root'),
                  ('c', 'bookmark', URL, '', 'root')])
    orig = f.request

    def flaky(method, url, params=None, **kw):
        if url.endswith('/blocks/root/children') and (params or {}).get('start_cursor') == '2':
            return resp(400, {'object': 'error'})
        return orig(method, url, params=params, **kw)
    f.request = flaky
    assert run(f, '--apply') == 2
    assert deleted(f) == []


def test_pagination_reads_everything():
    f = FakeNotion()
    f.page_size = 2
    page_with(f, [(f'b{i}', 'bookmark', URL if i in (0, 4) else f'https://github.com/x/r{i}', '', 'root')
                  for i in range(5)])
    assert run(f, '--apply') == 0
    assert deleted(f) == ['b4']


def test_max_depth_exceeded_is_partial_read():
    f = FakeNotion()
    page_with(f, [('t1', 'toggle', None, '', 'root'), ('t2', 'toggle', None, '', 't1'),
                  ('bk', 'bookmark', URL, '', 't2')])
    nc = cpd.NotionClient('t', session=f, sleep=lambda s: None)
    with pytest.raises(cpd.PartialRead):
        cpd.read_source(nc, 'root', max_depth=1)
    assert len(cpd.read_source(nc, 'root', max_depth=2).entries) == 1


def test_transient_429_then_success_with_capped_retry_after():
    f = FakeNotion()
    simple_dup(f)
    f.errors[('GET', r'/blocks/root/children')] = [(429, {'Retry-After': '3600'}), (429, {'Retry-After': '2'})]
    sleeps = []
    assert run(f, '--apply', sleep=sleeps.append) == 0
    assert deleted(f) == ['d']
    assert sleeps[:2] == [cpd.RETRY_AFTER_MAX, 2.0]
    assert max(sleeps) <= cpd.RETRY_AFTER_MAX


@pytest.mark.parametrize('header, expected', [('3600', 30.0), ('1.5', 1.5), ('-5', 0.0), ('nan', 2.0),
                                               ('inf', 2.0), ('Wed, 21 Oct 2026 07:28:00 GMT', 2.0), ('', 2.0)])
def test_retry_after_is_capped_and_robust(header, expected):
    assert cpd.RETRY_AFTER_MAX == 30
    assert cpd.NotionClient._retry_delay(1, resp(429, headers={'Retry-After': header})) == expected
    assert cpd.NotionClient._retry_delay(10, None) == cpd.RETRY_AFTER_MAX


def test_transient_5xx_then_success():
    f = FakeNotion()
    simple_dup(f)
    f.errors[('GET', r'/blocks/root/children')] = [500, 503, requests.ConnectionError('x')]
    assert run(f, '--apply') == 0
    assert deleted(f) == ['d']


# =============================================================================
# RELECTURE AVANT SUPPRESSION (I4, I5)
# =============================================================================
def test_toctou_keeper_gone():
    f = FakeNotion()
    page_with(f, [('k', 'bookmark', URL, 'note', 'root'), ('d', 'bookmark', URL, '', 'root')])

    def confirm(p):
        f.blocks['k']['in_trash'] = True     # le bloc conservé disparaît pendant la question
        return p
    run(f, '--apply', confirm=confirm)
    assert 'DELETE' not in [m for m, _, _ in f.calls]


def test_target_modified_is_skipped(capsys):
    f = FakeNotion()
    simple_dup(f)

    def confirm(p):
        f.blocks['d']['last_edited_time'] = '2026-10-10T00:00:00.000Z'
        return p
    assert run(f, '--apply', confirm=confirm) == 0
    assert 'DELETE' not in [m for m, _, _ in f.calls]
    assert 'modifié depuis la lecture' in capsys.readouterr().out


@pytest.mark.parametrize('change', ['target_url', 'keeper_url', 'keeper_moved', 'target_moved',
                                    'target_trashed', 'keeper_404', 'target_caption_vs_keeper',
                                    'target_children', 'keeper_now_text'])
def test_recheck_skips_changed_blocks(change):
    f = FakeNotion()
    simple_dup(f)

    def confirm(p):
        if change == 'target_url':
            f.blocks['d']['bookmark']['url'] = 'https://github.com/x/autre'
        elif change == 'keeper_url':
            f.blocks['k']['bookmark']['url'] = 'https://github.com/x/autre'
        elif change == 'keeper_moved':
            f.blocks['k']['parent'] = {'type': 'page_id', 'page_id': 'autre-page'}
        elif change == 'target_trashed':
            f.blocks['d']['in_trash'] = True
        elif change == 'keeper_404':
            del f.blocks['k']
        elif change == 'target_moved':
            f.blocks['d']['parent'] = {'type': 'block_id', 'block_id': 'toggle-ailleurs'}
        elif change == 'target_caption_vs_keeper':
            f.blocks['d']['bookmark']['caption'] = [{'plain_text': 'note ajoutée'}]
        elif change == 'target_children':
            f.blocks['d']['has_children'] = True
        elif change == 'keeper_now_text':
            f.blocks['k']['type'] = 'paragraph'
            f.blocks['k']['paragraph'] = {'rich_text': [{'plain_text': 'x', 'href': URL}]}
        return p
    assert run(f, '--apply', confirm=confirm) == 0
    assert deleted(f) == []


# =============================================================================
# JOURNAL AVANT ÉCRITURE (I10) ET RESTAURATION
# =============================================================================
def test_journal_before_delete_and_restore(tmp_path):
    f = FakeNotion()
    simple_dup(f)
    seen = {}

    def check(method, path):
        if method == 'DELETE':
            seen['records'] = read_records(journal_files(tmp_path)[0])
    f.before_write = check
    assert run(f, '--apply') == 0
    assert deleted(f) == ['d']
    assert seen['records'][-1]['event'] == 'intent' and seen['records'][-1]['block_id'] == 'd'
    jf = journal_files(tmp_path)[0]
    assert f.blocks['d']['in_trash']
    assert run(f, '--restore', str(jf), '--apply') == 0
    assert not f.blocks['d']['in_trash']
    assert ('PATCH', '/blocks/d', {'archived': False}) in f.calls


def test_journal_fsynced_before_delete(monkeypatch):
    synced = []
    real_fsync = os.fsync
    monkeypatch.setattr(cpd.os, 'fsync', lambda fd: synced.append(fd) or real_fsync(fd))
    f = FakeNotion()
    simple_dup(f)
    at_delete = {}
    f.before_write = lambda m, p: at_delete.setdefault(p, len(synced))
    assert run(f, '--apply') == 0
    assert at_delete['/blocks/d'] >= 2          # ligne « start » puis ligne « intent » synchronisées


def test_journal_location_and_content(tmp_path, capsys):
    f = FakeNotion()
    page_with(f, [('k', 'bookmark', URL, 'note longue', 'root'), ('d', 'bookmark', URL, 'note', 'root')])
    assert run(f, '--apply') == 0
    files = journal_files(tmp_path)
    assert len(files) == 1 and re.fullmatch(r'cleaner-\d{8}-\d{6}\.jsonl', files[0].name)
    records = read_records(files[0])
    assert [r['event'] for r in records] == ['start', 'intent', 'result', 'end']
    intent, result = records[1], records[2]
    assert intent['block_id'] == 'd' and intent['keeper_id'] == 'k'
    assert intent['block']['bookmark']['url'] == URL
    assert intent['block']['bookmark']['caption'] == [{'plain_text': 'note'}]
    assert intent['caption'] == 'note' and intent['parent'] == {'type': 'block_id', 'block_id': 'root'}
    assert intent['restore'] == {'method': 'PATCH', 'path': '/v1/blocks/d', 'body': {'archived': False},
                                 'notion_version': '2022-06-28'}
    assert result == {**result, 'block_id': 'd', 'status': 200, 'ok': True}
    out = capsys.readouterr().out
    assert '--restore' in out and str(files[0]) in out


def test_journal_unwritable_blocks_delete(tmp_path, capsys):
    (tmp_path / 'journal').write_text('ceci est un fichier, pas un dossier', encoding='utf-8')
    f = FakeNotion()
    simple_dup(f)
    assert run(f, '--apply') == 2               # code 2, pas de trace d'erreur
    assert 'DELETE' not in [m for m, _, _ in f.calls]
    assert 'Journal impossible' in capsys.readouterr().out


def test_journal_failure_mid_run_stops(monkeypatch):
    f = FakeNotion()
    page_with(f, [('k', 'bookmark', URL, '', 'root'), ('d1', 'bookmark', URL, '', 'root'),
                  ('d2', 'bookmark', URL, '', 'root')])
    original = cpd.Journal.write

    def flaky(self, record):
        if record.get('event') == 'intent' and record.get('block_id') == 'd2':
            raise OSError('disque plein')
        return original(self, record)
    monkeypatch.setattr(cpd.Journal, 'write', flaky)
    assert run(f, '--apply') == 2
    assert deleted(f) == ['d1']


def test_restore_is_simulation_by_default(tmp_path, capsys):
    f = FakeNotion()
    trashed_block(f, 'd')
    jf = write_journal(tmp_path / 'j.jsonl', [{'event': 'intent', 'block_id': 'd', 'url': URL}])
    assert run(f, '--restore', str(jf)) == 0
    assert f.writes() == []
    assert f.blocks['d']['in_trash']
    assert 'SIMULATION' in capsys.readouterr().out


@pytest.mark.parametrize('answer', ['oui', 'OUI', 'o', 'RESTAURER', 'restaurer 1', 'SUPPRIMER 1'])
def test_restore_refuses_wrong_phrase(tmp_path, answer):
    f = FakeNotion()
    trashed_block(f, 'd')
    jf = write_journal(tmp_path / 'j.jsonl', [{'event': 'intent', 'block_id': 'd'}])
    assert run(f, '--restore', str(jf), '--apply', answer=answer) == 2
    assert f.writes() == []


def test_restore_with_exact_phrase_and_skips_blocks_in_place(tmp_path):
    f = FakeNotion()
    trashed_block(f, 'd1')
    f.add_block('d2', 'bookmark', url=URL, caption=[])        # déjà en place
    jf = write_journal(tmp_path / 'j.jsonl', [
        {'event': 'start'}, {'event': 'intent', 'block_id': 'd1'}, {'event': 'result', 'block_id': 'd1'},
        {'event': 'intent', 'block_id': 'd2'}, {'event': 'intent', 'block_id': 'd1'}])
    phrases = []
    assert run(f, '--restore', str(jf), '--apply', confirm=lambda p: phrases.append(p) or p) == 0
    assert phrases == ['RESTAURER 1']
    assert f.writes() == [('PATCH', '/blocks/d1', {'archived': False})]
    assert not f.blocks['d1']['in_trash']


def test_restore_does_not_need_parent_page_id(tmp_path, monkeypatch):
    monkeypatch.delenv('PARENT_PAGE_ID')
    f = FakeNotion()
    trashed_block(f, 'd')
    jf = write_journal(tmp_path / 'j.jsonl', [{'event': 'intent', 'block_id': 'd'}])
    assert run(f, '--restore', str(jf), '--apply') == 0
    assert not f.blocks['d']['in_trash']


def test_restore_missing_journal_exit_1(tmp_path):
    f = FakeNotion()
    assert run(f, '--restore', str(tmp_path / 'absent.jsonl'), '--apply') == 1
    assert f.calls == []


def test_restore_corrupted_journal_aborts(tmp_path):
    f = FakeNotion()
    trashed_block(f, 'd')
    jf = tmp_path / 'j.jsonl'
    jf.write_text('{"event": "intent", "block_id": "d"}\n{cassé\n{"event": "intent", "block_id": "d"}\n',
                  encoding='utf-8')
    assert run(f, '--restore', str(jf), '--apply') == 2
    assert f.writes() == []


def test_restore_ignores_truncated_last_line(tmp_path, capsys):
    f = FakeNotion()
    trashed_block(f, 'd')
    jf = write_journal(tmp_path / 'j.jsonl', [{'event': 'intent', 'block_id': 'd'}],
                       raw_tail='{"event": "intent", "block_id": "e"')
    assert run(f, '--restore', str(jf), '--apply') == 0
    assert f.writes() == [('PATCH', '/blocks/d', {'archived': False})]
    assert 'incomplète' in capsys.readouterr().out


def test_restore_rejects_unsafe_block_id(tmp_path):
    f = FakeNotion()
    jf = write_journal(tmp_path / 'j.jsonl', [{'event': 'intent', 'block_id': '../pages/xyz'}])
    assert run(f, '--restore', str(jf), '--apply') == 2
    assert f.calls == []


def test_restore_failure_listed_exit_2(tmp_path, capsys):
    f = FakeNotion()
    trashed_block(f, 'd')
    f.errors[('PATCH', r'/blocks/d')] = [404]
    jf = write_journal(tmp_path / 'j.jsonl', [{'event': 'intent', 'block_id': 'd'}])
    assert run(f, '--restore', str(jf), '--apply') == 2
    assert '- d : HTTP 404' in capsys.readouterr().out


# =============================================================================
# PLAFOND (I11), CODES DE SORTIE ET BILAN (I14)
# =============================================================================
def test_cap():
    f = FakeNotion()
    page_with(f, [(f'b{i}', 'bookmark', URL, '', 'root') for i in range(60)])
    asked = []
    assert run(f, '--apply', confirm=lambda p: asked.append(p) or p) == 2
    assert deleted(f) == [] and asked == []
    assert f.writes() == []


def test_cap_configurable(monkeypatch):
    monkeypatch.setenv('CLEANER_MAX_DELETE', '1')
    f = FakeNotion()
    page_with(f, [('k', 'bookmark', URL, '', 'root'), ('d1', 'bookmark', URL, '', 'root'),
                  ('d2', 'bookmark', URL, '', 'root')])
    assert run(f, '--apply') == 2
    assert deleted(f) == []
    monkeypatch.setenv('CLEANER_MAX_DELETE', '2')
    assert run(f, '--apply') == 0
    assert deleted(f) == ['d1', 'd2']


def test_cap_in_simulation_only_warns(capsys):
    f = FakeNotion()
    page_with(f, [(f'b{i}', 'bookmark', URL, '', 'root') for i in range(60)])
    assert run(f) == 0
    assert 'plafond' in capsys.readouterr().out
    assert f.writes() == []


def test_delete_failure_reported_with_id_and_exit_2(capsys):
    f = FakeNotion()
    page_with(f, [('k', 'bookmark', URL, '', 'root'), ('d1', 'bookmark', URL, '', 'root'),
                  ('d2', 'bookmark', URL, '', 'root')])
    f.errors[('DELETE', r'/blocks/d1')] = [500] * 10
    assert run(f, '--apply') == 2
    out = capsys.readouterr().out
    assert f.blocks['d2']['in_trash'] and not f.blocks['d1']['in_trash']
    assert 'Supprimés : 1 / 2 prévus' in out
    assert '- d1 : HTTP 500' in out


def test_network_error_on_delete_is_a_failure(tmp_path, capsys):
    f = FakeNotion()
    simple_dup(f)
    f.errors[('DELETE', r'/blocks/d')] = [requests.ConnectionError('coupure')] * 10
    assert run(f, '--apply') == 2
    out = capsys.readouterr().out
    assert 'Supprimés : 0 / 1 prévus' in out and '- d : ' in out
    records = read_records(journal_files(tmp_path)[0])
    assert [r['event'] for r in records] == ['start', 'intent', 'result', 'end']
    assert records[2]['ok'] is False and records[2]['status'] is None


def test_nothing_to_delete_exit_0(capsys):
    f = FakeNotion()
    page_with(f, [('a', 'bookmark', URL, '', 'root'), ('b', 'bookmark', 'https://github.com/x/z', '', 'root')])
    assert run(f, '--apply') == 0
    assert f.writes() == []
    assert 'Aucun doublon supprimable' in capsys.readouterr().out


# =============================================================================
# PROPRIÉTÉ : chaque suppression laisse un bloc distinct, de même clé, sans perte de légende
# =============================================================================
def test_property_every_delete_has_surviving_distinct_keeper(tmp_path, monkeypatch):
    rnd = random.Random(20261010)
    urls = ['https://github.com/a/b', 'https://github.com/A/B/', 'https://github.com/a/b/tree/main',
            'https://github.com/a/b/blob/main/X.md', 'https://github.com/a/b/blob/main/x.md',
            'https://github.com/c/d', 'https://www.github.com/c/d?tab=readme-ov-file']
    total_deleted = 0
    for trial in range(300):
        monkeypatch.setenv('GITNOTATE_DATA_DIR', str(tmp_path / f't{trial}'))
        f = FakeNotion()
        specs, parents = [], ['root']
        for i in range(rnd.randint(1, 12)):
            btype = rnd.choice(['bookmark', 'bookmark', 'embed', 'link_preview', 'toggle'])
            parent = rnd.choice(parents)
            cap = rnd.choice(['', '', 'note'])
            specs.append((f'n{i}', btype, None if btype == 'toggle' else rnd.choice(urls), cap, parent))
            if btype == 'toggle':
                parents.append(f'n{i}')
        page_with(f, specs)
        before = {b: json.loads(json.dumps(v)) for b, v in f.blocks.items()}
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sys, 'stdout', io.StringIO())
            run(f, '--apply')
        assert all(m == 'DELETE' and re.fullmatch(r'/blocks/n\d+', p) for m, p, _ in f.writes()), trial
        dels = deleted(f)
        assert len(dels) == len(set(dels)), trial
        total_deleted += len(dels)
        for d in dels:
            bd = before[d]
            assert bd['type'] in cpd.DELETABLE_TYPES and not bd['has_children'], (trial, d)
            key = cpd.strict_github_key(bd[bd['type']]['url'])
            survivors = [b for b, v in f.blocks.items() if b != d and not v['in_trash']
                         and v['type'] in cpd.DELETABLE_TYPES
                         and cpd.strict_github_key(v[v['type']].get('url', '')) == key]
            assert survivors, (trial, d, specs)
            cap = bd[bd['type']]['caption']
            if cap:
                assert any(cap[0]['plain_text'] in ''.join(c['plain_text'] for c in
                                                           before[s][before[s]['type']]['caption'])
                           for s in survivors), (trial, d)
    assert total_deleted > 100          # le test n'est pas vide
