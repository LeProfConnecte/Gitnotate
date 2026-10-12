"""Seuil « forte » strict (couverture > SEUIL_FORTE), sans effet de l'arrondi flottant.

Qualification indépendante du lot 4 (§ 7) : open-notebook (I06, à exclure) et huginn (I15, acceptable) étaient
« forte » à couverture exactement 0,600 = 1,5 / 2,5. Une égalité reste partielle ; selon le nombre de fiches,
la même égalité se calcule 0.6, 0.6000000000000001 ou 0.5999999999999999 : le niveau n'en dépend pas.
Hors ligne : bancs synthétiques et corpus synthétique, aucune base Notion réelle.
"""
import json
from fractions import Fraction

import pytest
from redecouverte_outils import FIXTURES, index_du_corpus, p_texte, page, preparer

INDEPENDANTES = {q['id']: q for q in json.loads(
    (FIXTURES / 'requetes_independantes_lot4.json').read_text(encoding='utf-8'))['requetes']}
REQUETE_BANC = 'notebook markdown zorglub'     # deux notions essentielles sans voisin + un mot hors lexique


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


@pytest.fixture
def corpus(banc):
    index_du_corpus(banc.rd)
    return banc


def _chercher(rd, texte):
    con, meta = rd.ouvrir_index_valide()
    try:
        return rd.rechercher(con, rd.analyser_requete(texte), {}, 50, True, meta)
    finally:
        con.close()


def _poids_banc(rd, n):
    """Poids réels du moteur pour REQUETE_BANC dans le banc de n fiches (chaque notion dans 3 fiches) :
    notebook et markdown pèsent I, zorglub (mot libre) I / 2, avec I = _idf(n, 3)."""
    essentiel = rd._idf(n, 3) * rd.CLASSES['essentiel'] * rd.ROLES['normal']
    libre = min(rd._idf(n, 3), rd._idf(n, 2)) * rd.CLASSES['libre'] * rd.ROLES['normal']
    return [essentiel, essentiel, libre]


def _couverture_cible(rd, n):
    """Couverture de la fiche cible (notebook et zorglub trouvés, pas markdown), calculée comme rechercher()."""
    poids = _poids_banc(rd, n)
    return sum(p * m for p, m in zip(poids, (1.0, 0.0, 1.0), strict=True)) / sum(poids)


def _taille_donnant(rd, valeur):
    return next(n for n in range(7, 200) if repr(_couverture_cible(rd, n)) == valeur)


def _synchroniser_banc(banc, n):
    """n fiches : cible (notebook + zorglub), un notebook, deux markdown, un zorglub, une fiche complète (chaque
    notion dans 3 fiches) et du remplissage sans rapport."""
    textes = {'alpha': 'Notebook zorglub pour la démonstration.', 'beta': 'Notebook interactif.',
              'gamma': 'Éditeur markdown.', 'delta': 'Visionneuse markdown.', 'epsilon': 'Projet zorglub.',
              'zeta': 'Notebook markdown zorglub complet.'}
    textes.update({f'remplissage-{i}': 'Éditeur de texte brut.' for i in range(n - len(textes))})
    banc.notion.pages = [page(nom, f'https://github.com/test/{nom}', props={'Description': p_texte(texte)})
                         for nom, texte in textes.items()]
    assert banc.lancer('sync', '--accepter-baisse') == 0


# =============================================================================
# Comparaison au seuil
# =============================================================================
def test_egalite_exacte_n_est_pas_forte(load_gn):
    load_gn()
    import redecouverte as rd
    assert rd.SEUIL_FORTE == 0.60 and rd.EPSILON_SEUIL == 1e-9
    assert not rd.depasse_seuil_forte(0.6)
    assert not rd.depasse_seuil_forte(rd.SEUIL_FORTE)
    assert not rd.depasse_seuil_forte(1.5 / 2.5)                          # 1,5 / 2,5 : I06 et I15
    assert not rd.depasse_seuil_forte(rd.SEUIL_FORTE + rd.EPSILON_SEUIL)   # tolérance incluse


def test_egalite_arrondie_au_dessus_ou_au_dessous_n_est_pas_forte(load_gn):
    load_gn()
    import redecouverte as rd
    assert 0.6000000000000001 > rd.SEUIL_FORTE                            # une comparaison naïve s'y tromperait
    assert not rd.depasse_seuil_forte(0.6000000000000001)
    assert not rd.depasse_seuil_forte(0.5999999999999999)
    assert not rd.depasse_seuil_forte(0.6 + 1e-12)


def test_nettement_au_dessus_est_forte(load_gn):
    load_gn()
    import redecouverte as rd
    assert rd.depasse_seuil_forte(0.6 + 1e-6)
    assert rd.depasse_seuil_forte(0.601) and rd.depasse_seuil_forte(0.8) and rd.depasse_seuil_forte(1.0)
    assert not rd.depasse_seuil_forte(0.6 - 1e-6) and not rd.depasse_seuil_forte(0.0)


def test_poids_reels_donnent_les_deux_arrondis(load_gn):
    """Les poids réels du moteur (_idf, CLASSES, ROLES) d'une même égalité mathématique 3/5 donnent, selon le
    nombre de fiches, 0.6, 0.6000000000000001 ou 0.5999999999999999 ; aucun n'est « forte »."""
    load_gn()
    import redecouverte as rd
    vus = set()
    for n in range(7, 200):
        poids = _poids_banc(rd, n)
        exacte = (Fraction(poids[0]) + Fraction(poids[2])) / sum(Fraction(p) for p in poids)
        assert exacte == Fraction(3, 5), n                  # I, I, I / 2 : quotient exact des flottants = 3/5
        couverture = _couverture_cible(rd, n)
        vus.add(repr(couverture))
        assert abs(couverture - 0.6) < 1e-14 and not rd.depasse_seuil_forte(couverture), n
    assert {'0.6', '0.6000000000000001', '0.5999999999999999'} <= vus


@pytest.mark.parametrize('valeur', ['0.6000000000000001', '0.5999999999999999'])
def test_banc_egalite_arrondie_reste_partielle(banc, valeur):
    """Bout en bout : le moteur calcule lui-même la couverture arrondie ; la fiche reste partielle, et une fiche
    qui couvre toutes les notions reste forte dans le même index."""
    rd = banc.rd
    n = _taille_donnant(rd, valeur)
    _synchroniser_banc(banc, n)
    reponse = _chercher(rd, REQUETE_BANC)
    assert [c.cle for c in reponse.requete.concepts] == ['notebook', 'markdown', 'zorglub']
    assert [c.poids for c in reponse.requete.concepts] == _poids_banc(rd, n)
    tous = {r.cle: r for r in reponse.resultats + reponse.faibles}
    cible = tous['test/alpha']
    assert repr(cible.couverture) == valeur and cible.m == {'notebook': 1.0, 'zorglub': 1.0}
    assert cible.niveau == 'partielle'
    assert tous['test/zeta'].couverture == 1.0 and tous['test/zeta'].niveau == 'forte'
    assert [r.cle for r in reponse.resultats][:2] == ['test/zeta', 'test/alpha']


# =============================================================================
# Jeu indépendant : I06 et I15 (couverture exacte 0,600) ; règle partielle inchangée
# =============================================================================
def test_i06_open_notebook_n_est_plus_forte(corpus):
    reponse = _chercher(corpus.rd, INDEPENDANTES['I06']['requete'])
    rangs = {r.cle: r for r in reponse.resultats}
    notebook = rangs['lfnovo/open-notebook']
    assert notebook.couverture == pytest.approx(0.6, abs=1e-12) and notebook.niveau == 'partielle'
    assert rangs['marimo-team/marimo'].niveau == 'forte' and rangs['marimo-team/marimo'].couverture > 0.7
    assert [r.cle for r in reponse.resultats][0] == 'marimo-team/marimo'
    assert [r.cle for r in reponse.resultats if r.niveau == 'forte'] == ['marimo-team/marimo']


def test_i15_huginn_n_est_plus_forte(corpus):
    reponse = _chercher(corpus.rd, INDEPENDANTES['I15']['requete'])
    rangs = {r.cle: r for r in reponse.resultats}
    huginn = rangs['huginn/huginn']
    assert huginn.couverture == pytest.approx(0.6, abs=1e-12) and huginn.niveau == 'partielle'
    assert rangs['rssnext/folo'].niveau == 'partielle'
    assert not any(r.niveau == 'forte' for r in reponse.resultats + reponse.sans_depot)


def test_regle_partielle_inchangee_a_l_egalite(corpus):
    """Signalement, sans correction : la règle partielle reste « couverture >= 0,25 », égalité comprise.
    Dans I22, quatre dépôts ne sont partiels que par cette égalité (0,5 x I / 2 I, exacte en flottants)."""
    rd = corpus.rd
    reponse = _chercher(rd, INDEPENDANTES['I22']['requete'])
    a_l_egalite = {r.cle for r in reponse.resultats if r.couverture == rd.SEUIL_PARTIELLE}
    assert a_l_egalite == {'rdumasia303/deepseek_ocr_app', 'dockur/windows', 'ohf-voice/piper1-gpl',
                           'ggml-org/llama.cpp'}
    assert all(r.niveau == 'partielle' for r in reponse.resultats if r.cle in a_l_egalite)


def test_legende_dit_plus_de_60_pour_cent(load_gn):
    load_gn()
    import redecouverte as rd
    assert '**forte** = plus de 60 % du poids' in rd.LEGENDE_MARKDOWN
    assert 'au moins 60 %' not in rd.LEGENDE_MARKDOWN
