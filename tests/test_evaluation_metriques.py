"""Définitions des mesures de scripts/evaluer_redecouverte.py (P@5 à dénominateur fixe, R@5, cas limites).

Aucun index ni réseau : seule la fonction pure mesurer() est exercée.
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'evaluer_redecouverte.py'


@pytest.fixture
def ev(load_gn):
    load_gn()
    spec = importlib.util.spec_from_file_location('evaluer_metriques', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _requete(en_tete=(), acceptables=(), a_exclure=()):
    return {'en_tete': list(en_tete), 'acceptables': list(acceptables), 'a_exclure': list(a_exclure)}


def test_p5_denominateur_fixe_et_r5(ev):
    # 1 seul pertinent jugé, trouvé au rang 1 : P@5 = 1/5 (et non 1/1), R@5 = 1
    m = ev.mesurer(['a/a', 'x/x', 'y/y'], _requete(en_tete=['a/a']))
    assert m['p5'] == pytest.approx(0.2) and m['r5'] == 1.0 and m['mrr'] == 1.0


def test_classement_court_non_avantage(ev):
    # 2 dépôts seulement dans le classement, tous deux pertinents : P@5 = 2/5
    m = ev.mesurer(['a/a', 'b/b'], _requete(en_tete=['a/a'], acceptables=['b/b']))
    assert m['p5'] == pytest.approx(0.4) and m['r5'] == 1.0


def test_plus_de_cinq_pertinents(ev):
    pertinents = [f'p/{i}' for i in range(8)]
    m = ev.mesurer(pertinents[:5] + ['x/x'], _requete(acceptables=pertinents))
    assert m['p5'] == 1.0 and m['r5'] == pytest.approx(5 / 8)
    assert m['mrr'] is None                      # aucun dépôt « en tête » jugé


def test_pertinents_apres_le_rang_5_ignores(ev):
    m = ev.mesurer(['x/1', 'x/2', 'x/3', 'x/4', 'x/5', 'a/a'], _requete(en_tete=['a/a']))
    assert m['p5'] == 0.0 and m['r5'] == 0.0 and m['mrr'] == pytest.approx(1 / 6)
    assert m['manquants'] == []                  # présent dans les 10 premiers


def test_requete_sans_reponse_attendue(ev):
    # aucune clé pertinente : P@5, R@5, nDCG@10 et MRR non définis ; intrus comptés
    m = ev.mesurer(['x/x', 'z/z'], _requete(a_exclure=['z/z']))
    assert m['p5'] is None and m['r5'] is None and m['ndcg10'] is None and m['mrr'] is None
    assert m['intrus3'] == 1 and m['intrus5'] == 1


def test_attendu_jamais_intrus_et_gain_maximal(ev):
    # une clé à la fois « en tête » et « à exclure » reste pertinente (gain 2), jamais intrus
    m = ev.mesurer(['a/a'], _requete(en_tete=['a/a'], acceptables=['a/a'], a_exclure=['a/a']))
    assert m['intrus3'] == 0 and m['p5'] == pytest.approx(0.2) and m['r5'] == 1.0 and m['ndcg10'] == 1.0


def test_metriques_moyennees_comprennent_r5(ev):
    assert ev.METRIQUES == ('ndcg10', 'p5', 'r5', 'mrr', 'intrus3', 'intrus5')
