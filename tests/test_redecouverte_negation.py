"""Portée de la négation dans la requête : comportement garanti et défauts connus.

Formes couvertes : « pas pour », « sans », « ne … pas », « sans GPU », « pas avec », « mais », et leurs
équivalents anglais (« not for », « without », « does not … », « without GPU », « not with », « but »).

La correction de la portée « pas pour X » (un mot de liaison placé juste après le déclencheur ne ferme plus la
négation) a été essayée puis RETIRÉE : elle corrigeait I26 et K14, mais dégradait K15 et K17 du jeu de contrôle
(docs/QUALIFICATION_INDEPENDANTE_LOT4.md, § 10). Les cas qu'elle visait restent marqués xfail(strict=True) : ils
documentent le défaut et signaleront sa correction. Hors ligne, aucune base Notion réelle.
"""
import json

import pytest
from redecouverte_outils import FIXTURES, preparer

I26 = next(q for q in json.loads((FIXTURES / 'requetes_independantes_lot4.json').read_text(encoding='utf-8'))
           ['requetes'] if q['id'] == 'I26')
DEFAUT = ("défaut connu : un mot de liaison (pour, avec, ou, for, with…) placé juste après un déclencheur "
          "(pas, not, sans, ni…) ferme la négation ; correction retirée après le jeu de contrôle")


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


def _analyse(rd, texte):
    requete = rd.analyser_requete(texte)
    return requete.nies, [(c.cle, c.role) for c in requete.concepts]


@pytest.mark.parametrize('texte, nies, concepts', [
    # « sans », « without »
    ('un OCR sans GPU', ['GPU'], [('ocr', 'normal')]),
    ('an OCR without GPU', ['GPU'], [('ocr', 'normal')]),
    # « ne … pas », « does not … »
    ('ne pas utiliser de GPU', ['GPU'], []),
    ('an OCR that does not require a GPU', ['require', 'GPU'], [('ocr', 'normal')]),
    # « sans GPU, pour … » : la virgule ou un mot de liaison après le mot nié ferme la portée
    ('sans GPU, pour mes vidéos', ['GPU'], [('video', 'contexte')]),
    ('sans GPU pour mes vidéos', ['GPU'], [('video', 'contexte')]),
    ('without GPU, for my videos', ['GPU'], [('video', 'contexte')]),
    ('without GPU for my videos', ['GPU'], [('video', 'contexte')]),
    ('avec ou sans GPU', ['GPU'], []),
    # « mais », « but » ferment la négation
    ('un OCR sans GPU mais avec Docker', ['GPU'], [('ocr', 'normal'), ('docker', 'normal')]),
    ('un OCR, mais pas de GPU', ['GPU'], [('ocr', 'normal')]),
    ('non mais je cherche un OCR', [], [('ocr', 'normal')]),
    ('OCR without GPU but with docker', ['GPU'], [('ocr', 'normal'), ('docker', 'normal')]),
    ('an OCR, but no GPU', ['GPU'], [('ocr', 'normal')]),
    ('no but an OCR', [], [('ocr', 'normal')]),
])
def test_negation_comportement_garanti(banc, texte, nies, concepts):
    assert _analyse(banc.rd, texte) == (nies, concepts)


def test_n04_ne_pas_de_gpu(banc):
    nies, concepts = _analyse(banc.rd, 'Un OCR qui ne nécessite pas de GPU, pour les PC Windows de la salle '
                                       'informatique')
    assert nies == ['GPU'] and 'gpu' not in [c for c, _ in concepts]
    assert {'ocr', 'windows'} <= {c for c, _ in concepts}


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=DEFAUT)
@pytest.mark.parametrize('texte, nies, concepts', [
    ('pas pour analyser des PDF', ['analyser', 'PDF'], []),
    ('not for PDF analysis', ['PDF', 'analysis'], []),
    ('pas avec Docker', ['Docker'], []),
    ('un OCR, pas avec Docker', ['Docker'], [('ocr', 'normal')]),
    ('not with Docker', ['Docker'], []),
    ('un OCR qui ne fonctionne pas avec Docker', ['Docker'], [('ocr', 'normal')]),
    ('an OCR but not with Docker', ['Docker'], [('ocr', 'normal')]),
    ('sans ou avec GPU', ['GPU'], []),
    ('sans GPU ni pour la vidéo', ['GPU', 'vidéo'], []),
])
def test_negation_defaut_connu_pas_pour_pas_avec(banc, texte, nies, concepts):
    assert _analyse(banc.rd, texte) == (nies, concepts)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=DEFAUT)
def test_i26_negation_defaut_connu(banc):
    assert _analyse(banc.rd, I26['requete'])[0] == ['analyser', 'PDF']


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="défaut connu : « pas » de « pas à pas » (étape par étape) est lu comme une négation")
def test_pas_a_pas_defaut_connu(banc):
    assert _analyse(banc.rd, 'un guide pas à pas Python')[0] == []
