"""Outils communs des tests du moteur de redécouverte (fichier non collecté par pytest).

- FausseNotion remplace gn.get_session : la vraie http_request_with_retry est exercée (nouvelles
  tentatives, 429, 5xx) ; sert le schéma et les fiches par tranches de 100 avec curseurs ; journal de
  tous les appels ; pannes injectables par numéro de réponse ; toute URL hors Notion est refusée.
- Fabriques de propriétés, de pages et de schémas au format Notion-Version 2022-06-28.
- Chargement des fixtures (corpus synthétique de 63 fiches, 3 bases) et index du corpus.
- Application des patchs de variantes mesurées (qualification du lot 5).
"""
import copy
import hashlib
import importlib
import json
import re
import threading
import uuid
from pathlib import Path

import requests

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'redecouverte'
BASE_ID = '1a2b3c4d5e6f40718293a4b5c6d7e8f9'
JETON_TEST = 'ntn_test' + 'A1b2C3d4' * 5
JETON_LECTURE = 'ntn_lecture' + 'Z9y8X7w6' * 5
NON_JSON = object()
JUSTIFICATION_V73 = ("[LLM mistral-small-2603 · profil 2026-10-11/8c41d2] U1·P3·T2·I2·C2·M2·L2 = 9 — "
                     "Avis de test.")

SCHEMA_GITNOTATE = {
    'Nom': 'title', 'URL': 'url', 'Description': 'rich_text', "Cas d'usage": 'rich_text',
    'Installation': 'rich_text', 'Exemple': 'rich_text', 'Prérequis': 'rich_text', 'Stars': 'number',
    'Pertinence': 'number', 'Langage': 'select', 'Statut': 'select', 'Type': 'multi_select',
    'Dernière MAJ': 'date', 'Analysé le': 'date', 'Justification': 'rich_text', 'Notes': 'rich_text',
}


def tirets(identifiant):
    """32 hexadécimaux → forme UUID avec tirets (comme Notion)."""
    h = identifiant.replace('-', '')
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def make_response(status, body=None, headers=None):
    """Vrai requests.Response (un 4xx est « falsy », comme en production)."""
    r = requests.Response()
    r.status_code = status
    r._content = b'<html>erreur</html>' if body is NON_JSON else json.dumps(body).encode('utf-8')
    r.encoding = 'utf-8'
    if headers:
        r.headers.update(headers)
    return r


def erreur_notion(status, message='erreur', code='validation_error', headers=None):
    return make_response(status, {'object': 'error', 'status': status, 'code': code, 'message': message},
                         headers)

# --- Propriétés (Notion-Version 2022-06-28) -----------------------------------------------------------
def rt(texte, lien=None, mention=False, **annotations):
    ann = {'bold': False, 'italic': False, 'strikethrough': False, 'underline': False, 'code': False,
           'color': 'default'}
    ann.update(annotations)
    if mention:
        return {'type': 'mention', 'mention': {'type': 'date', 'date': {'start': '2026-02-10'}},
                'annotations': ann, 'plain_text': texte, 'href': None}
    return {'type': 'text', 'text': {'content': texte, 'link': {'url': lien} if lien else None},
            'annotations': ann, 'plain_text': texte, 'href': lien}


def _segments(segments):
    return [s if isinstance(s, dict) else rt(s) for s in segments if s != '']


def p_titre(*segments):
    return {'id': 'title', 'type': 'title', 'title': _segments(segments)}


def p_texte(*segments):
    return {'id': 'txt', 'type': 'rich_text', 'rich_text': _segments(segments)}


def p_url(url):
    return {'id': 'url', 'type': 'url', 'url': url}


def p_select(nom, sorte='select'):
    return {'id': 'sel', 'type': sorte, sorte: {'id': 'o1', 'name': nom, 'color': 'gray'} if nom else None}


def p_multi(*noms):
    return {'id': 'ms', 'type': 'multi_select',
            'multi_select': [{'id': f'o{i}', 'name': n, 'color': 'gray'} for i, n in enumerate(noms)]}


def p_nombre(valeur):
    return {'id': 'num', 'type': 'number', 'number': valeur}


def p_date(debut):
    return {'id': 'dt', 'type': 'date', 'date': {'start': debut, 'end': None, 'time_zone': None} if debut else None}


def p_formule(sorte, valeur):
    return {'id': 'f', 'type': 'formula', 'formula': {'type': sorte, sorte: valeur}}


def p_autre(sorte, valeur):
    """Propriété d'un type non conservé (checkbox, people, email, files, relation…)."""
    return {'id': 'x', 'type': sorte, sorte: valeur}


def page(nom='docling', url='https://github.com/docling-project/docling', base_id=BASE_ID, props=None, *,
         id=None, cree='2026-10-11T08:00:00.000Z', modifie=None, corbeille=False, v73=True):
    """Fiche Notion ; par défaut une fiche v7.3 minimale. props complète ou remplace les colonnes."""
    pid = id or str(uuid.uuid5(uuid.NAMESPACE_URL, f'page|{nom}|{url}|{cree}'))
    proprietes = {'Nom': p_titre(nom) if nom else p_titre(), 'URL': p_url(url)}
    if v73:
        proprietes.update({
            'Description': p_texte(f"Bibliothèque {nom} de démonstration."),
            "Cas d'usage": p_texte("• Convertir des fichiers de test"),
            'Installation': p_texte(f"pip install {nom}"), 'Exemple': p_texte('Non vérifié'),
            'Prérequis': p_texte('Non vérifié'), 'Stars': p_nombre(120), 'Pertinence': p_nombre(9),
            'Langage': p_select('Python'), 'Statut': p_select('À explorer'), 'Type': p_multi(),
            'Dernière MAJ': p_date('2026-10-01'), 'Analysé le': p_date('2026-10-11'),
            'Justification': p_texte(JUSTIFICATION_V73), 'Notes': p_texte()})
    proprietes.update(props or {})
    return {'object': 'page', 'id': pid, 'created_time': cree, 'last_edited_time': modifie or cree,
            'created_by': {'object': 'user', 'id': 'u-1'}, 'last_edited_by': {'object': 'user', 'id': 'u-1'},
            'cover': None, 'icon': None, 'parent': {'type': 'database_id', 'database_id': tirets(base_id)},
            'archived': corbeille, 'in_trash': corbeille,
            'url': 'https://www.notion.so/' + pid.replace('-', ''), 'public_url': None, 'properties': proprietes}


def pages_numerotees(n, debut=0, **options):
    return [page(f'depot-{i}', f'https://github.com/owner{i}/depot-{i}',
                 cree=f'2026-10-{1 + i // 1440:02d}T{(i // 60) % 24:02d}:{i % 60:02d}:00.000Z', **options)
            for i in range(debut, debut + n)]


def schema(colonnes=None, base_id=BASE_ID, titre='Ressources GitHub', **champs):
    colonnes = SCHEMA_GITNOTATE if colonnes is None else colonnes
    proprietes = {nom: {'id': f'c{i}', 'name': nom, 'type': t, t: {}} for i, (nom, t) in enumerate(colonnes.items())}
    base = {'object': 'database', 'id': tirets(base_id), 'title': [rt(titre)], 'description': [],
            'is_inline': False, 'archived': False, 'in_trash': False, 'properties': proprietes}
    base.update(champs)
    return base

# --- Faux client Notion -------------------------------------------------------------------------------
class FausseNotion:
    """Session HTTP simulée (méthodes get/post de requests.Session)."""

    def __init__(self, pages=None, base_id=BASE_ID, colonnes=None, taille=100):
        self.base_id = base_id
        self.base = schema(colonnes, base_id)
        self.pages = list(pages or [])
        self.taille = taille
        self.journal = []            # (méthode, url, corps, en-têtes)
        self.hors_notion = []
        self.pannes = {}             # numéro de réponse → f(corps normal, numéro) → corps | réponse | exception
        self.panne_schema = None     # réponse ou exception servie au GET du schéma
        self._verrou = threading.Lock()

    def get(self, url, headers=None, params=None, timeout=None):
        return self._appel('GET', url, None, headers)

    def post(self, url, headers=None, json=None, timeout=None):
        return self._appel('POST', url, json, headers)

    def _appel(self, methode, url, corps, entetes):
        with self._verrou:
            self.journal.append((methode, url, copy.deepcopy(corps), dict(entetes or {})))
        if not url.startswith('https://api.notion.com/'):
            self.hors_notion.append(url)
            raise AssertionError(f"appel hors Notion : {url}")
        if methode == 'GET' and url == f'https://api.notion.com/v1/databases/{self.base_id}':
            if isinstance(self.panne_schema, BaseException):
                raise self.panne_schema
            return self.panne_schema if self.panne_schema is not None else make_response(200, self.base)
        if methode == 'POST' and url == f'https://api.notion.com/v1/databases/{self.base_id}/query':
            return self._requete(corps or {})
        return erreur_notion(404, 'Could not find object', 'object_not_found')

    def _requete(self, corps):
        curseur = corps.get('start_cursor')
        numero = int(curseur.rsplit('-', 1)[1]) if curseur else 1
        debut = (numero - 1) * self.taille
        suite = debut + self.taille < len(self.pages)
        reponse = {'object': 'list', 'results': copy.deepcopy(self.pages[debut:debut + self.taille]),
                   'next_cursor': f'curseur-{numero + 1}' if suite else None, 'has_more': suite,
                   'type': 'page_or_database', 'page_or_database': {}}
        panne = self.pannes.get(numero)
        if panne is not None:
            resultat = panne(reponse, numero)
            if isinstance(resultat, BaseException):
                raise resultat
            if isinstance(resultat, requests.Response):
                return resultat
            if resultat is not None:
                reponse = resultat
        return make_response(200, reponse)

    def appels(self, methode=None):
        return [(m, u) for m, u, _, _ in self.journal if methode is None or m == methode]

    @property
    def nb_requetes(self):
        return sum(1 for m, u, _, _ in self.journal if m == 'POST' and u.endswith('/query'))


# Pannes prêtes à l'emploi
def panne_statut(code, message='erreur', headers=None):
    return lambda reponse, numero: erreur_notion(code, message, headers=headers)


def panne_non_json(reponse, numero):
    return make_response(200, NON_JSON)


def panne_sans_curseur(reponse, numero):
    return dict(reponse, has_more=True, next_cursor=None)


def panne_curseur_repete(reponse, numero):
    return dict(reponse, has_more=True, next_cursor=f'curseur-{numero}')


def panne_ajout(objet):
    def ajouter(reponse, numero):
        reponse['results'].append(copy.deepcopy(objet))
        return reponse
    return ajouter


def panne_exception(exception):
    return lambda reponse, numero: exception

# --- Banc d'essai -------------------------------------------------------------------------------------
class Banc:
    """gitnotate et redecouverte rechargés, faux Notion branché, time.sleep neutralisé (enregistré)."""

    def __init__(self, gn, rd, notion, sommeils):
        self.gn, self.rd, self.notion, self.sommeils = gn, rd, notion, sommeils

    def lancer(self, *arguments):
        return self.rd.main([str(a) for a in arguments])

    @property
    def index(self):
        return self.rd.chemin_index()


def preparer(load_gn, monkeypatch, **env):
    valeurs = {'DATABASE_ID': BASE_ID, 'NOTION_TOKEN': JETON_TEST}
    valeurs.update(env)
    gn = load_gn(**valeurs)
    import redecouverte
    rd = importlib.reload(redecouverte)
    notion = FausseNotion()
    monkeypatch.setattr(gn, 'get_session', lambda: notion)
    sommeils = []
    monkeypatch.setattr(gn.time, 'sleep', sommeils.append)
    return Banc(gn, rd, notion, sommeils)

# --- Fixtures du corpus -------------------------------------------------------------------------------
def charger_corpus():
    return json.loads((FIXTURES / 'corpus.json').read_text(encoding='utf-8'))


def charger_bases():
    return json.loads((FIXTURES / 'bases.json').read_text(encoding='utf-8'))


def schema_base(base):
    return {nom: p['type'] for nom, p in base['properties'].items()}


def schema_fusionne(bases):
    """Les 3 bases dans un même index : colonnes de B et C, types de A prioritaires."""
    fusion = {}
    for cle in ('B', 'C', 'A'):
        fusion.update(schema_base(bases[cle]))
    return fusion


def pages_du_corpus(corpus=None):
    corpus = charger_corpus() if corpus is None else corpus
    return [c['page'] for c in corpus if c['version_attendue'] != 'corbeille']


# format d'un supplément de fiches fictives -> préfixe de l'identifiant de page (uuid5)
FORMATS_SUPPLEMENT = {'gitnotate-supplement-lot5/1': 'gitnotate-lot5/',
                      'gitnotate-lot6-supplement/1': 'gitnotate-lot6-jeu-r/'}


def pages_du_supplement(nom):
    """Fiches fictives v7.3+ d'un supplément (lot 5 : gitnotate-supplement-lot5/1 ; jeu R du lot 6 :
    gitnotate-lot6-supplement/1), en pages Notion : mêmes champs et mêmes dates que l'outil de conversion utilisé
    pour les mesures (docs/QUALIFICATION_LOT5.md ; provenance du jeu R : qualification_lot6/jeu_R/LISEZMOI.md)."""
    donnees = json.loads((FIXTURES / nom).read_text(encoding='utf-8'))
    prefixe = FORMATS_SUPPLEMENT[donnees['format']]
    pages = []
    for f in donnees['fiches']:
        justification = ("[LLM mistral-small-2603 · profil 2026-10-20/8c41d2] U1·P2·T1·I1·C1·M1·L0 = 7 — "
                         + f['justification'].strip())
        prerequis = '\n'.join('- ' + x for x in f['prerequis']) if f['prerequis'] else 'Non vérifié'
        pages.append(page(f['nom'], 'https://github.com/' + f['depot'], id=str(uuid.uuid5(uuid.NAMESPACE_URL,
                          prefixe + f['id'])), cree='2026-10-20T10:00:00.000Z', props={
            'Description': p_texte(f['description']),
            "Cas d'usage": p_texte('\n'.join('• ' + x for x in f['cas_usage'])),
            'Installation': p_texte(f['installation']), 'Exemple': p_texte(f['exemple']),
            'Prérequis': p_texte(prerequis), 'Stars': p_nombre(f['stars']), 'Pertinence': p_nombre(7),
            'Langage': p_select(f['langage']), 'Statut': p_select('À explorer'), 'Type': p_multi(*f.get('type', [])),
            'Dernière MAJ': p_date('2026-09-15'), 'Analysé le': p_date('2026-10-20'),
            'Justification': p_texte(justification), 'Licence': p_select(f['licence']),
            'Catégorie': p_select(f['categorie']), 'Brique pour': p_multi(*f['brique_pour']),
            'Notes': p_texte(f['notes']) if f.get('notes') else p_texte()}))
    return pages


def index_du_corpus(rd, pages=None, secrets=()):
    """Index construit depuis les pages hors corbeille des 3 bases (sans V7, propre à la lecture)."""
    bases = charger_bases()
    pages = pages_du_corpus() if pages is None else pages
    plates = [rd.aplatir_page(p, secrets) for p in pages]
    meta = rd.MetaLecture(database_id=rd.normaliser_id(bases['A']['id']), base_titre='Corpus synthétique',
                          source='notion', schema=schema_fusionne(bases), nb_requetes=1,
                          nb_objets_recus=len(plates), ignorees={'corbeille': 0, 'base_imbriquee': 0},
                          debut_utc='2026-10-11T12:00:00+00:00')
    return rd.construire_et_remplacer(plates, meta, secrets, accepter_baisse=True)


def fiche_du_corpus(rd, id_corpus, corpus=None, bases=None):
    corpus = charger_corpus() if corpus is None else corpus
    bases = charger_bases() if bases is None else bases
    c = next(x for x in corpus if x['id_corpus'] == id_corpus)
    return rd.construire_fiche(rd.aplatir_page(c['page']), rd.resoudre_colonnes(schema_base(bases[c['base']])))

# --- Lecture de l'index -------------------------------------------------------------------------------
DATES_META = ('sync_debut_utc', 'sync_fin_utc', 'sync_fin_locale')


def contenu_index(rd, chemin=None):
    """Tables de l'index (fiches, anomalies, texte FTS, meta hors dates) pour comparer deux index."""
    chemin = rd.chemin_index() if chemin is None else chemin
    con = rd.ouvrir_index_lecture(chemin)
    try:
        meta = {c: v for c, v in con.execute('SELECT cle, valeur FROM meta') if c not in DATES_META}
        return {'fiches': con.execute('SELECT * FROM fiches ORDER BY id').fetchall(),
                'anomalies': con.execute('SELECT page_id, champ, code, detail FROM anomalies ORDER BY id').fetchall(),
                'recherche': con.execute('SELECT rowid, * FROM recherche ORDER BY rowid').fetchall(),
                'meta': meta}
    finally:
        con.close()


def requete_fts(rd, expression, chemin=None):
    """rowid → nom des fiches qui correspondent à une expression FTS (lecture seule)."""
    con = rd.ouvrir_index_lecture(rd.chemin_index() if chemin is None else chemin)
    try:
        return {r: n for r, n in con.execute(
            'SELECT f.id, f.nom FROM recherche JOIN fiches f ON f.id = recherche.rowid '
            'WHERE recherche MATCH ?', (expression,))}
    finally:
        con.close()


def empreinte(chemin):
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest()


def lignes(rd, sql, parametres=(), chemin=None):
    con = rd.ouvrir_index_lecture(rd.chemin_index() if chemin is None else chemin)
    try:
        return con.execute(sql, parametres).fetchall()
    finally:
        con.close()


# --- Variantes mesurées (patchs unifiés) -------------------------------------------------------------
def appliquer_patch(code, patch):
    """Applique un patch unifié (« --- a/<nom> », blocs à contexte exact) à {nom de fichier: texte} ; renvoie la
    nouvelle version."""
    code = dict(code)
    for partie in re.split(r'^--- a/', patch, flags=re.MULTILINE)[1:]:
        nom = partie.split('\n', 1)[0].strip()
        lignes, sortie, i = code[nom].splitlines(keepends=True), [], 0
        for bloc in re.finditer(r'^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@.*\n((?:[ +\-\\].*\n?)*)', partie,
                                re.MULTILINE):
            debut = int(bloc.group(1)) - 1
            sortie += lignes[i:debut]
            i = debut
            for ligne in bloc.group(2).splitlines(keepends=True):
                if ligne.startswith('\\'):
                    sortie[-1] = sortie[-1].rstrip('\n')
                elif ligne.startswith('+'):
                    sortie.append(ligne[1:])
                else:
                    assert lignes[i] == ligne[1:], (nom, i, ligne)
                    if ligne.startswith(' '):
                        sortie.append(lignes[i])
                    i += 1
        code[nom] = ''.join(sortie + lignes[i:])
    return code


def empreinte_code(code):
    """16 premiers caractères du SHA-256 de redecouverte.py puis redecouverte_lexique.py (octets UTF-8)."""
    brut = code['redecouverte.py'].encode('utf-8') + code['redecouverte_lexique.py'].encode('utf-8')
    return hashlib.sha256(brut).hexdigest()[:16]
