"""Portée de la négation dans la requête : comportement garanti et défauts connus.

Formes couvertes : « pas pour », « sans », « ne … pas », « sans GPU », « pas avec », « mais », et leurs
équivalents anglais (« not for », « without », « does not … », « without GPU », « not with », « but »).

La correction générale de la portée « pas pour X » (un mot de liaison placé juste après le déclencheur ne ferme plus
la négation) a été essayée puis RETIRÉE au lot 4 : elle corrigeait I26 et K14, mais dégradait K15 et K17 du jeu de
contrôle (docs/QUALIFICATION_INDEPENDANTE_LOT4.md, § 10). Le lot 5 la limite aux identifiants techniques
(« pas avec Docker », « not for Windows » : lexique.LIAISONS_EXCLUSION, IDENTIFIANTS), traite « avec ou sans X »
(indifférent : ni exigé ni exclu) et « pas à pas » ; ces cas sont désormais garantis. Les autres (« pas pour analyser
des PDF », « not for PDF analysis », I26) restent marqués xfail(strict=True). Hors ligne, aucune base Notion réelle.
"""
import json

import pytest
from redecouverte_outils import FIXTURES, preparer

I26 = next(q for q in json.loads((FIXTURES / 'requetes_independantes_lot4.json').read_text(encoding='utf-8'))
           ['requetes'] if q['id'] == 'I26')
DEFAUT = ("défaut connu : hors identifiant technique, un mot de liaison (pour, avec, for, with…) placé juste après "
          "un déclencheur (pas, not, sans, ni…) ferme la négation ; correction générale retirée après le jeu de "
          "contrôle du lot 4")


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
    # « require », « nécessite » : verbes du cadre de question depuis le lot 5 (MOTS_VIDES_REQUETE)
    ('an OCR that does not require a GPU', ['GPU'], [('ocr', 'normal')]),
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
    # lot 5 : liaison suivie d'un identifiant technique (lexique.IDENTIFIANTS)
    ('pas avec Docker', ['Docker'], []),
    ('un OCR, pas avec Docker', ['Docker'], [('ocr', 'normal')]),
    ('not with Docker', ['Docker'], []),
    ('un OCR qui ne fonctionne pas avec Docker', ['Docker'], [('ocr', 'normal')]),
    ('an OCR but not with Docker', ['Docker'], [('ocr', 'normal')]),
    ('pas pour Windows', ['Windows'], []),
    ('not for Windows', ['Windows'], []),
    # « sans ou avec », « with or without » : indifférent (ni exigé ni exclu)
    ('sans ou avec GPU', ['GPU'], []),
    ('with or without GPU', ['GPU'], []),
    # « pas à pas » : étape par étape, pas une négation
    ('un guide pas à pas Python', [], [('guide', 'normal'), ('python', 'normal')]),
    ('un tutoriel pas-à-pas pour Python', [], [('cours', 'normal'), ('python', 'normal')]),
])
def test_negation_comportement_garanti(banc, texte, nies, concepts):
    assert _analyse(banc.rd, texte) == (nies, concepts)


@pytest.mark.parametrize('texte, exclusions, indifferents', [
    ('un OCR sans GPU', ['gpu'], []),
    ('pas avec Docker', ['docker'], []),
    ('without n8n', ['n8n'], []),
    ('avec ou sans GPU', [], ['GPU']),
    ('sans ou avec GPU', [], ['GPU']),
    ('with or without GPU', [], ['GPU']),
    ('sans GPU, pour mes vidéos', ['gpu'], []),
    ('pas pour analyser des PDF', [], []),            # PDF n'est pas un identifiant technique
])
def test_exclusion_et_indifference(banc, texte, exclusions, indifferents):
    requete = banc.rd.analyser_requete(texte)
    assert [e['cible'] for e in requete.exclusions] == exclusions
    assert requete.indifferents == indifferents


def test_n04_ne_pas_de_gpu(banc):
    nies, concepts = _analyse(banc.rd, 'Un OCR qui ne nécessite pas de GPU, pour les PC Windows de la salle '
                                       'informatique')
    assert nies == ['GPU'] and 'gpu' not in [c for c, _ in concepts]
    assert {'ocr', 'windows'} <= {c for c, _ in concepts}


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=DEFAUT)
@pytest.mark.parametrize('texte, nies, concepts', [
    ('pas pour analyser des PDF', ['analyser', 'PDF'], []),
    ('not for PDF analysis', ['PDF', 'analysis'], []),
    ('sans GPU ni pour la vidéo', ['GPU', 'vidéo'], []),
])
def test_negation_defaut_connu_pas_pour_pas_avec(banc, texte, nies, concepts):
    assert _analyse(banc.rd, texte) == (nies, concepts)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=DEFAUT)
def test_i26_negation_defaut_connu(banc):
    assert _analyse(banc.rd, I26['requete'])[0] == ['analyser', 'PDF']
