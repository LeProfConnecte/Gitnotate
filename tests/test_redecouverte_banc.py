"""Banc d'états indépendant du lot 5 (docs/QUALIFICATION_LOT5.md § 6, « Banc indépendant ») : champs de fiches et
requêtes rédigés et étiquetés à l'aveugle (GUIDE.md), sans accès au moteur, avant toute exécution.

Chaque champ est indexé comme une fiche ; l'état de la technologie est calculé comme pour une recherche qui l'exclut
(_preuves_exclusions, etat_exclusion). Chaque requête donne le rôle de chaque technologie (cherche, exclu, reference,
neutre) et ses termes clés. Les chiffres figés ici décrivent le code ; ils ne sont pas des seuils de qualification :
dev et t1 ont servi à corriger le moteur (t1 a été mesuré une fois avant d'y toucher : § 6), t2 seulement à mesurer.
Hors ligne, aucune base Notion réelle.
"""
import hashlib
import json
import os

import pytest
from redecouverte_outils import index_du_corpus, p_multi, p_select, p_texte, page, preparer

DOSSIER = os.path.join(os.path.dirname(__file__), 'fixtures', 'redecouverte', 'qualification_lot5', 'banc')
EMPREINTES = {
    'brut_t1.json': '0fc60fe05c97415081754c7006393e9aa43ff645db1c0d8f4ea5f2187b7ae245',
    'banc_dev.json': '9617afeb5383323aa148308eb2e677b63d96cb0953980a20b2b405ce6f8a6bc7',
    'banc_t1.json': '9ec799187b7d1479949f2c01b104c70c5596f43cdfa1013de14086a66ee10f6e',
    'brut_t2.json': '3fecd992c382dc4945b9c059ca110c9acb0980c78802b35654fc5d86aafcbe6c',
    'banc_t2.json': '3ca7bfa4294acde54881e45d08bd2e4e3887ae839dd16f8e93651f6db1f7a3e7',
}
CHAMPS = {'description': 'Description', 'cas_usage': "Cas d'usage", 'installation': 'Installation',
          'exemple': 'Exemple', 'prerequis': 'Prérequis', 'notes': 'Notes'}
# (exacts, faux « requis », « requis » attendus et trouvés, « requis » trouvés), (rôles justes, rôles)
MESURES = {
    'banc_dev.json': ((192, 1, 64, 65), (98, 102)),
    'banc_t1.json': ((193, 3, 65, 68), (93, 95)),
    'banc_t2.json': ((292, 27, 94, 121), (147, 176)),       # mesure finale, jamais utilisée pour corriger
}


@pytest.fixture
def banc(load_gn, monkeypatch):
    return preparer(load_gn, monkeypatch)


def _charger(nom):
    with open(os.path.join(DOSSIER, nom), encoding='utf-8') as f:
        return json.load(f)


def _etats(rd, fiches):
    pages = []
    for x in fiches:
        props = {'Description': p_texte('Outil de démonstration.'), "Cas d'usage": p_texte('• Démonstration'),
                 'Installation': p_texte('pip install outil'), 'Exemple': p_texte('Non vérifié'),
                 'Prérequis': p_texte('Non vérifié'), 'Notes': p_texte(), 'Catégorie': p_select('Autre'),
                 'Brique pour': p_multi()}
        props[CHAMPS[x['colonne']]] = p_texte(x['texte'])
        pages.append(page(x['id'].lower(), f"https://github.com/banc/{x['id'].lower()}", props=props))
    index_du_corpus(rd, pages)
    con, _ = rd.ouvrir_index_valide()
    etats = {}
    try:
        rowid = {nom: i for i, nom in con.execute('SELECT id, nom FROM fiches')}
        for cle in sorted({x['identifiant'] for x in fiches}):
            e = {'cible': cle, 'mot': cle, 'nature': rd.lexique.IDENTIFIANTS[cle][0], 'source': 'exclusion'}
            preuves = rd._preuves_exclusions(con, [e])
            for x in fiches:
                if x['identifiant'] == cle:
                    etats[x['id']] = rd.etat_exclusion(e, [rowid[x['id'].lower()]], preuves)['etat']
    finally:
        con.close()
    return etats


def _role(requete, cle):
    sources = [e['source'] for e in requete.exclusions if e['cible'] == cle]
    if 'exclusion' in sources:
        return 'exclu'
    if 'reference' in sources:
        return 'reference'
    return 'cherche' if any(c.cle == cle and c.role != 'reference' for c in requete.concepts) else 'neutre'


def test_empreintes_du_banc():
    for nom, attendue in EMPREINTES.items():
        with open(os.path.join(DOSSIER, nom), 'rb') as f:
            assert hashlib.sha256(f.read()).hexdigest() == attendue, nom


def test_banc_sans_recouvrement():
    parties = [_charger(nom) for nom in ('banc_dev.json', 'banc_t1.json', 'banc_t2.json')]
    for sorte in ('fiches', 'requetes'):
        ids = [x['id'] for p in parties for x in p[sorte]]
        assert len(ids) == len(set(ids))
    textes = [x['texte'] for p in parties for x in p['fiches']]
    assert len(textes) == len(set(textes))


@pytest.mark.parametrize('nom', sorted(MESURES))
def test_mesures_du_banc(banc, nom):
    donnees = _charger(nom)
    etats = _etats(banc.rd, donnees['fiches'])
    exacts = sum(etats[x['id']] == x['attendu'] for x in donnees['fiches'])
    faux = sum(etats[x['id']] == 'requis' and x['attendu'] != 'requis' for x in donnees['fiches'])
    justes = sum(etats[x['id']] == 'requis' and x['attendu'] == 'requis' for x in donnees['fiches'])
    trouves = sum(etats[x['id']] == 'requis' for x in donnees['fiches'])
    roles = [(x['role'], _role(banc.rd.analyser_requete(q['requete']), x['identifiant']))
             for q in donnees['requetes'] for x in q['roles']]
    assert ((exacts, faux, justes, trouves), (sum(a == b for a, b in roles), len(roles))) == MESURES[nom]
