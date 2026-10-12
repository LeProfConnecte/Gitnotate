"""Jeu de qualification indépendant du lot 4 (I01-I26) et son protocole, reçus le 2026-10-12.

- Les deux fichiers originaux sont conservés à l'octet près (empreintes de PASSATION_CLAUDE_CODE.md).
- Le jeu dérivé ne diffère de l'original que par « aucun_fort »: true sur I01, I02, I03 et I26.
- Aucun seuil de qualité n'est figé ici : seule la règle du protocole « aucune correspondance forte sans
  preuve pertinente » pour les requêtes sans réponse attendue est vérifiée.
Hors ligne : index construit depuis le corpus synthétique, aucune base Notion réelle.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from redecouverte_outils import index_du_corpus, preparer

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'tests' / 'fixtures' / 'redecouverte'
ORIGINAL = FIXTURES / 'requetes_independantes_lot4.json'
PROTOCOLE = FIXTURES / 'PROTOCOLE_QUALIFICATION_LOT4.md'
DERIVE = FIXTURES / 'requetes_independantes_lot4_derive_aucun_fort.json'
SHA_ORIGINAL = 'e32f0fc29e75d5db4eef45e2f018ad148004cc941f4a6d5947dfeba6fcb8e6e7'
SHA_PROTOCOLE = 'bbc9aaed67fa0b43bdadd7071182ff41ce1713b49d05aded17ed5d2f4a8f6f0d'
EMPREINTE_JUGEMENTS = '5444aa4f44b4a40370238d857396917d11f4f48f6866fa3ee76b97bb466f0b8a'
SANS_REPONSE = ('I01', 'I02', 'I03', 'I26')
# Jeu de contrôle K01-K24 : rédigé à l'aveugle (sans consulter le moteur) et figé avant toute mesure, puis exécuté
# une seule fois pour confirmer les corrections choisies sur I01-I26 (docs/QUALIFICATION_INDEPENDANTE_LOT4.md, § 10)
CONTROLE = FIXTURES / 'requetes_controle_lot4.json'
SHA_CONTROLE = 'fa233122d046611832b00c9774d4a1b58caceaf4f462621b8b93dfb99a3efe47'
EMPREINTE_CONTROLE = '5dff44e4d1d6b40d83ee75d2fdb4c051aed74ded06d4ab5866694fd427dadbe3'


def _sha(chemin):
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _evaluateur():
    spec = importlib.util.spec_from_file_location('evaluer_qualification', ROOT / 'scripts' / 'evaluer_redecouverte.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def corpus(load_gn, monkeypatch):
    banc = preparer(load_gn, monkeypatch)
    index_du_corpus(banc.rd)
    return banc


def test_originaux_intacts_a_l_octet():
    assert _sha(ORIGINAL) == SHA_ORIGINAL
    assert _sha(PROTOCOLE) == SHA_PROTOCOLE
    assert b'\r' not in ORIGINAL.read_bytes() and b'\r' not in PROTOCOLE.read_bytes()


def test_gitattributes_protege_les_originaux():
    lignes = (ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()
    for chemin in (ORIGINAL, PROTOCOLE, CONTROLE):
        assert f"{chemin.relative_to(ROOT).as_posix()} -text" in lignes


def test_derive_ne_differe_que_par_aucun_fort():
    original = json.loads(ORIGINAL.read_text(encoding='utf-8'))
    derive = json.loads(DERIVE.read_text(encoding='utf-8'))
    assert derive['derive_de'] == {'fichier': ORIGINAL.name, 'sha256': SHA_ORIGINAL}
    assert 'NON IDENTIQUE' in derive['modification']
    assert {k: v for k, v in derive.items() if k not in ('derive_de', 'modification')}.keys() == original.keys()
    assert [q['id'] for q in derive['requetes']] == [q['id'] for q in original['requetes']]
    for q_orig, q_der in zip(original['requetes'], derive['requetes'], strict=True):
        attendu = dict(q_orig, aucun_fort=True) if q_orig['id'] in SANS_REPONSE else q_orig
        assert q_der == attendu, q_orig['id']
    for q in original['requetes']:
        assert ('aucun_fort' in q) is False
        assert (not q['en_tete'] and not q['acceptables']) == (q['id'] in SANS_REPONSE)


def test_empreinte_des_jugements_de_l_original(load_gn, capsys):
    load_gn()
    ev = _evaluateur()
    assert ev.main([str(ORIGINAL), '--empreinte']) == 0
    sortie = capsys.readouterr().out
    assert f"Empreinte des jugements (SHA-256) : {EMPREINTE_JUGEMENTS}" in sortie
    assert f"Empreinte du fichier (SHA-256 des octets) : {SHA_ORIGINAL}" in sortie
    assert 'qualification_independante : 26 requêtes' in sortie


def test_sans_reponse_aucune_correspondance_forte(corpus, capsys):
    """Règle du protocole (§ 4) : aucune correspondance forte affirmée sans preuve pertinente, fiches sans
    dépôt comprises, pour les quatre requêtes sans dépôt en tête ni acceptable (jeu dérivé)."""
    ev = _evaluateur()
    assert ev.main([str(DERIVE)]) == 0
    sortie = capsys.readouterr().out
    assert 'aucun_fort non respecté pour 0 requête sur 4' in sortie
    requetes = {q['id']: q for q in json.loads(DERIVE.read_text(encoding='utf-8'))['requetes']}
    con, _ = corpus.rd.ouvrir_index_valide()
    try:
        for ident in SANS_REPONSE:
            reponse = ev.lancer(con, requetes[ident])
            assert not any(r.niveau == 'forte' for r in reponse.resultats + reponse.sans_depot), ident
    finally:
        con.close()


def test_controle_fige_a_l_octet(load_gn, capsys):
    assert _sha(CONTROLE) == SHA_CONTROLE and b'\r' not in CONTROLE.read_bytes()
    load_gn()
    ev = _evaluateur()
    assert ev.main([str(CONTROLE), '--empreinte']) == 0
    sortie = capsys.readouterr().out
    assert f"Empreinte des jugements (SHA-256) : {EMPREINTE_CONTROLE}" in sortie
    assert 'controle_lot4 : 24 requêtes' in sortie


def test_controle_sans_reponse_aucune_correspondance_forte(corpus, capsys):
    """Règle du protocole sur les cinq requêtes du contrôle sans dépôt pertinent (aucun_fort: true)."""
    ev = _evaluateur()
    assert ev.main([str(CONTROLE)]) == 0
    assert 'aucun_fort non respecté pour 0 requête sur 5' in capsys.readouterr().out
