# Redécouverte : retrouver un dépôt déjà enregistré

`redecouverte.py` répond à la question « parmi les dépôts que j'ai déjà enregistrés, lesquels
pourraient servir à ce besoin ? », à partir des fiches de votre base Notion Gitnotate, même quand
aucun projet actif n'y est associé. Version 1.0.0 (`python redecouverte.py --version`, qui affiche
aussi la version de `gitnotate.py`).

Commandes données pour PowerShell (Windows). Sous Linux, elles sont identiques (remplacez `python`
par `python3` si besoin) ; les différences sont signalées. Comme pour `gitnotate.py`, réactivez
l'environnement virtuel dans chaque nouvelle fenêtre (`.\.venv\Scripts\Activate.ps1`, ou
`source .venv/bin/activate` sous Linux).

Sommaire : [1. À quoi ça sert](#1-à-quoi-ça-sert) · [2. Prérequis](#2-prérequis) ·
[3. Synchroniser](#3-synchroniser) · [4. Chercher](#4-chercher) · [5. Lire un résultat](#5-lire-un-résultat) ·
[6. Avis LLM facultatif](#6-avis-llm-facultatif---llm) · [7. Windows](#7-windows) ·
[8. Fichiers et codes de sortie](#8-fichiers-et-codes-de-sortie) ·
[9. Valider et mesurer](#9-valider-sur-la-base-réelle-et-mesurer) ·
[10. Mesures sur le corpus synthétique](#10-mesures-sur-le-corpus-synthétique) · [11. Limites](#11-limites)

## 1. À quoi ça sert

```text
python redecouverte.py sync                     copie locale des fiches (Notion est seulement lu)
python redecouverte.py cherche "votre besoin"   recherche hors ligne dans la copie locale
python redecouverte.py etat                     état de la copie locale
```

`sync` lit toute la base Notion et en fait une copie locale (un index SQLite). `cherche` interroge
cette copie, sans réseau : vous pouvez chercher aussi souvent que vous voulez sans consommer de
quota. Chaque résultat cite mot pour mot les champs de la fiche qui répondent au besoin, avec le nom
du champ, sa fiabilité, la version et la date de la fiche.

Ce que le moteur ne fait **jamais** :

- **écrire dans Notion** : seuls deux appels sont autorisés, `GET /v1/databases/{id}` (schéma de la
  base) et `POST /v1/databases/{id}/query` (lecture des fiches), avec la version d'API
  `2022-06-28` de `gitnotate.py`. Une liste blanche les vérifie avant tout envoi : tout autre appel
  est bloqué avant le réseau. Il ne modifie, n'archive et ne supprime rien, même un doublon ;
- **appeler GitHub** : il ne connaît que ce que contiennent vos fiches ;
- **inventer** : les explications sont des extraits mot pour mot de vos fiches et des phrases fixes.
  Les textes de remplissage écrits par les premières versions de Gitnotate (cas d'usage génériques,
  « See documentation »…) et les « Non vérifié » ne sont jamais pris en compte par la recherche. La
  version d'une fiche n'est jamais devinée d'après sa date ;
- **envoyer quoi que ce soit à un LLM** sans l'option `--llm` et sans votre confirmation ;
- **classer d'après les étoiles, la Pertinence ou le Statut** (voir la [section 5](#5-lire-un-résultat)).

## 2. Prérequis

**Python 3.10 ou plus récent avec SQLite FTS5.** Sous Windows, le Python de python.org inclut FTS5.
Vérification :

```powershell
python -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)'); print('FTS5 OK')"
```

(Linux : même commande avec `python3`.) Sans FTS5, chaque commande s'arrête (code 1) avec un message
qui l'explique ; rien n'est lu ni modifié, et `gitnotate.py` n'est pas concerné.

**Le même `.env` que `gitnotate.py`** (dossier du projet, ou `GITNOTATE_DATA_DIR`) : `DATABASE_ID` (les
32 caractères hexadécimaux de la base) et un jeton Notion. `PARENT_PAGE_ID` n'est pas nécessaire. Les
clés LLM ne servent qu'avec `--llm`. Les variables propres au moteur sont décrites dans la section
« REDÉCOUVERTE » de `env.example`.

**Recommandé : une intégration Notion en lecture seule.** Le moteur ne fait que lire, mais une
intégration limitée à « Read content » le garantit aussi du côté de Notion : Notion refuserait toute
écriture.

1. Ouvrez <https://www.notion.so/my-integrations> et créez une intégration interne (par exemple
   « Gitnotate lecture »).
2. Dans ses capacités, cochez seulement « Read content » (ni « Update content », ni « Insert
   content »). Copiez son jeton.
3. Dans Notion, ouvrez la base « Ressources GitHub » en pleine page : ••• → Connexions → ajoutez
   cette intégration.
4. Dans `.env`, ajoutez `NOTION_READONLY_TOKEN=<le jeton>`.

Sans `NOTION_READONLY_TOKEN`, le moteur utilise `NOTION_TOKEN` (celui de `gitnotate.py`) et le
bilan de `sync` affiche une ligne `Conseil`.

## 3. Synchroniser

```powershell
python redecouverte.py sync
```

Le moteur lit toutes les fiches de `DATABASE_ID`, vérifie chaque réponse de Notion, construit le
nouvel index dans un fichier temporaire, le contrôle (intégrité, nombre de fiches, absence de
jeton), puis remplace l'ancien d'un seul coup. **Toute erreur, tout Ctrl-C laisse l'ancien index
intact.** Une seule synchronisation peut tourner à la fois.

**Quand la lancer** : après chaque run de `gitnotate.py`, et après avoir modifié des fiches dans
Notion (Statut, notes…). Jamais pendant un run de `gitnotate.py` : la lecture ne verrait pas les
fiches en cours de création et, avec le même jeton, les deux programmes se partagent la limite de
débit de Notion (environ 3 requêtes par seconde par intégration). `cherche` et `etat` vous
préviennent quand l'index date de plus de 30 jours, ou quand `gitnotate.py` a créé des fiches
depuis la dernière synchronisation (d'après `gitnotate_stats.json`).

**Lire le bilan** (exemple réel, obtenu sur le corpus de test avec un faux Notion) :

```text
Lecture de la base Notion « Ressources GitHub » (lecture seule)…
Synchronisation de l'index de redécouverte
   Base Notion : « Ressources GitHub » 1a2b3c4d… — Notion-Version 2022-06-28, lecture seule (NOTION_READONLY_TOKEN)
   Lecture     : 1 requête, 62 fiches (1 à la corbeille ignorée) — fiches hors corbeille et hors pages archivées
   Versions    : v7.3+ ×16 · v7.2 ×5 · v7.0/v7.1 ×20 · ancienne ×18 · manuelle ×3
   Dépôts      : 51 distincts ; 6 dépôts sur plusieurs fiches (etat --doublons) ; 2 fiches sans dépôt GitHub
   Colonnes    : personnelles indexées : Tags, Notes ; ignorées : Créé le (created_time), Favori (checkbox), Projet lié (relation)
   Anomalies   : 2 (etat --anomalies)
   Différence  : +0 fiche, -1 depuis la synchronisation du 2026-10-12 01:04
   Disparues   : outil-sans-readme
   Index       : …\.gitnotate_index\redecouverte.sqlite (328 Ko) — recherche hors ligne possible
```

- **Lecture** : le nombre de fiches lues doit égaler le nombre de lignes de la base dans Notion (vue
  sans filtre). Les fiches à la corbeille ne sont pas lues ; celles archivées avec la fonction
  « Archiver » récente de Notion ne le sont probablement pas non plus (comportement non vérifié).
- **Versions** : répartition des fiches selon la version de Gitnotate qui les a écrites, reconnue
  d'après leur contenu (préfixe de la Justification, valeurs typiques) : `v7.3+` (v7.3 et v7.4),
  `v7.2`, `v7.0/v7.1`, `ancienne` (versions antérieures, sans Justification), `manuelle` (fiche
  saisie à la main), `indéterminée`.
- **Dépôts** : un même dépôt peut avoir plusieurs fiches (anciens runs) ; elles sont toutes gardées
  et regroupées à l'affichage. `etat --doublons` les liste pour un tri manuel dans Notion.
- **Colonnes** : les colonnes que vous avez ajoutées vous-même, de type texte, sélection, statut,
  URL ou formule, sont « personnelles indexées » : leur contenu est cherchable et affiché « saisi par
  vous ». Seules leurs valeurs sont cherchées, jamais leur nom : chercher « notes » ou « tags » ne
  trouve pas toutes les fiches où ces colonnes sont remplies. Les autres (case à cocher, relation,
  date de création…) sont ignorées. Les colonnes personne, e-mail, téléphone et fichiers ne sont
  jamais conservées.
- **Anomalies** : fiches sans adresse GitHub, colonne d'un type inattendu, valeur illisible,
  texte ressemblant à un jeton (masqué)… Détail : `python redecouverte.py etat --anomalies`.
- **Différence / Disparues** : comparaison avec la synchronisation précédente.

**En cas de code 2, l'ancien index est intact** : la recherche reste possible sur la copie
précédente. Messages possibles :

- `Lecture interrompue (réponse N) : … L'index précédent est conservé.` (réseau, incident Notion,
  fiche reçue deux fois parce que la base a changé pendant la lecture…) : relancez `sync` plus tard ;
- `Une autre synchronisation est en cours ; relancez quand elle sera terminée` ;
- `L'index est ouvert par un autre programme ; fermez-le puis relancez sync. L'ancien index est
  conservé et reste utilisable` (voir la [section 7](#7-windows)) ;
- garde-fou contre une baisse brutale :

  ```text
  21 fiches de l'index précédent sont absentes de la lecture (DATABASE_ID changé ? partage de l'intégration retiré ? fiches supprimées ?). L'ancien index est conservé. Si c'est voulu : python redecouverte.py sync --accepter-baisse
     Absentes : short-video-maker, remotion, piper1-gpl, chatterbox, marimo, evidently, BuildingAI, windows, llama.cpp, aibal …
  ```

  Ce refus se produit quand au moins 10 fiches **et** au moins 10 % des fiches de l'index précédent
  manquent, quand la lecture ne renvoie aucune fiche alors que l'index en contenait, ou quand
  l'index précédent venait d'une autre base. **N'utilisez `--accepter-baisse` qu'après avoir compris
  la baisse** : vérifiez dans Notion que ces fiches ont bien été supprimées, que `DATABASE_ID` est le
  bon et que l'intégration est toujours connectée à la base. Le bilan signale alors
  `Attention : baisse acceptée (--accepter-baisse) : N fiches disparues`.

Un code 1 signale un problème de configuration : jeton ou `DATABASE_ID` manquant ou invalide (le
message rappelle le fichier `.env` attendu), ou base refusée par Notion (HTTP 401 : jeton invalide ;
403 : capacité « Read content » absente ou intégration non connectée ; 404 : base introuvable ou non
partagée ; 400 : ID mal formé ou base devenue multi-sources).

**Capture et rejeu hors ligne.** `python redecouverte.py sync --capture` écrit aussi, après un
remplacement réussi, les fiches lues dans `exports\capture-notion-AAAAMMJJ-HHMMSS.json` (ou dans le
fichier indiqué : un nom seul va dans `exports\`). Cette capture ne contient ni jeton ni colonne de
données personnelles, mais elle contient le texte de vos fiches : gardez-la pour vous. Elle permet
de reconstruire l'index sans réseau ni jeton, avec les mêmes contrôles :

```powershell
python redecouverte.py sync --depuis capture-notion-20261012-010441.json
```

Un nom seul est cherché dans le dossier courant, puis dans `exports\`. `--capture` et `--depuis`
ne s'utilisent pas ensemble (code 1). `--log-level verbose` affiche chaque réponse reçue. Après un
rejeu, `cherche` et `etat` donnent la date à laquelle la capture a lu Notion (`données lues dans
Notion le …`, puis la date du rejeu) : les alertes d'ancienneté (plus de 30 jours) et de fiches créées
depuis par `gitnotate.py` partent de cette date, pas de celle du rejeu.

## 4. Chercher

Écrivez le besoin en phrase, **entre guillemets**, en français ou en anglais. Les mots de la
question (« quels », « outils », « déjà », « enregistrés », « which », « saved »…) sont ignorés.

```powershell
python redecouverte.py cherche "Quels outils déjà enregistrés pourrais-je utiliser pour extraire des données de PDF techniques ?"
python redecouverte.py cherche "Quels dépôts seraient réutilisables dans une application FastAPI de traitement documentaire ?"
python redecouverte.py cherche "automatiser une veille financière" --exclure-statut "Écarté" -n 5
python redecouverte.py cherche --statut "En test" --statut "Utilisé"
python redecouverte.py cherche "application FastAPI de traitement documentaire" --format markdown --sortie resultats.md
```

| Option | Effet | Défaut |
|--------|-------|--------|
| `-n N`, `--nombre N` | dépôts affichés (correspondances fortes et partielles), de 1 à 50 | `REDECOUVERTE_RESULTATS` (10) |
| `--tout` | affiche aussi les correspondances faibles | masquées |
| `--details` | détail du calcul, toutes les fiches du dépôt, chaque champ avec sa fiabilité, la Pertinence avec sa grille | non |
| `--statut S` | garde les dépôts dont au moins une fiche a ce Statut ; répétable (l'un **ou** l'autre) | — |
| `--exclure-statut S` | écarte les dépôts dont une fiche a ce Statut (par exemple « Écarté ») ; répétable | aucune exclusion |
| `--licence L` | licence exacte, ou famille : « Apache » garde Apache-2.0 | — |
| `--categorie C` | texte contenu dans la `Catégorie` | — |
| `--projet P` | texte contenu dans un nom de `Brique pour` | — |
| `--format texte\|markdown\|json` | format de sortie | `texte` |
| `--sortie FICHIER` | écrit les résultats dans un fichier (UTF-8) au lieu de l'écran ; un nom sans dossier va dans `exports\` | écran |
| `--llm`, `--llm-max N`, `--oui`, `--llm-apercu` | avis LLM facultatif ([section 6](#6-avis-llm-facultatif---llm)) | désactivé |
| `--log-level quiet\|normal\|verbose` | verbosité (`verbose` : expressions cherchées et durée) | `LOG_LEVEL` |

- Les filtres se combinent : l'un **ou** l'autre au sein d'une même option répétée, et **et** entre
  options différentes. Les comparaisons ignorent les accents et la casse.
- Le Statut « Écarté » n'est **pas** masqué par défaut : ajoutez `--exclure-statut "Écarté"`.
- Sans besoin mais avec un filtre (`cherche --statut "En test"`), vous obtenez la liste, par nom, de
  tous les dépôts qui passent les filtres (`-n` ne la limite pas). Sans besoin ni filtre, ou avec
  seulement des mots ignorés : code 1, `Aucun mot significatif dans la recherche`.
- `--format markdown` produit un tableau récapitulatif puis le détail de chaque dépôt ;
  `--format json` (format `gitnotate-redecouverte/1`) sert aux scripts : sans `--sortie`, le JSON va
  seul sur la sortie standard et les messages sur la sortie d'erreur.
- Avec `--sortie`, une ligne `Résultats écrits dans …` confirme l'écriture ; le fichier est écrit
  d'un coup (jamais à moitié) et refusé s'il contenait un jeton.

## 5. Lire un résultat

Exemple réel sur le corpus de test (`cherche "Quels outils déjà enregistrés pourrais-je utiliser
pour extraire des données de PDF techniques ?" -n 3`, index reconstruit avec `sync --depuis` ; premier
résultat seulement, lien Notion abrégé) :

```text
Recherche : « Quels outils déjà enregistrés pourrais-je utiliser pour extraire des données de PDF techniques ? »
Concepts  : extraire (+ extraction, extracteur, extract, extracting…) · données (+ data, donnée) · PDF (+
            fichier pdf, pdfs) · techniques (+ technique, technical)
Ignorés   : quels, outils, deja, enregistres, pourrais, je, utiliser, pour, des, de
Index     : 62 fiches, 51 dépôts — données lues dans Notion le 2026-10-11 à 12:00 (aujourd'hui), capture
            capture-corpus.json rejouée le 2026-10-12. Recherche locale : rien n'a été envoyé.

1. docling — docling-project/docling — correspondance forte (83 %)
   Répond à   : extraire (Cas d'usage, Description, Exemple · fiche v7.3+ ; via « Convertir », « convertit »,
                « converter » — et Notes · fiche ancienne)
                PDF (Cas d'usage, Description · fiche v7.3+ — et Notes · fiche ancienne ; Description · fiche
                v7.0/v7.1)
                techniques (Cas d'usage · fiche v7.3+)
   Ne couvre pas : données (notion secondaire)
   D'après la fiche :
     • Cas d'usage [LLM, à vérifier · fiche v7.3+ du 2026-10-11] :
         « • *Convertir* des *PDF* *techniques* en Markdown avant un traitement par LLM
         • *Extraire* les tableaux de documents *PDF* »
     • Description [LLM, à vérifier · fiche v7.3+ du 2026-10-11] :
         « Bibliothèque Python qui *convertit* des documents (*PDF*, DOCX, PPTX, HTML, images) en Markdown ou
         JSON pour l'IA générative, avec analyse de mise en page et de tableaux. »
     • Exemple [README, mot pour mot · fiche v7.3+ du 2026-10-11] :
         « from docling.document_*converter* import DocumentConverter

         *converter* = DocumentConverter()
         result = *converter*.*convert*(source) »
   Établi     : Exemple [README, mot pour mot · fiche v7.3+ du 2026-10-11] : extrait cité ci-dessus
   À vérifier :
     - 3 fiches produites par une première version de Gitnotate (v7.0/v7.1 du 2026-03-08, ancienne du
       2026-01-14 ×2) : description traduite par LLM ; Cas d'usage, Exemple (« pip install docling »),
       Prérequis (« Python recent ») et Type (« ML/AI ») sont des gabarits écrits sans lire le dépôt
       (ignorés). Vérifiez sur GitHub avant de réutiliser.
     - Prérequis : « Non vérifié » par Gitnotate (fiche v7.3+)
   Statut     : Utilisé (fiche du 2026-01-14, et 1 autre fiche) ; À explorer (2 autres fiches)
   Licence    : MIT (GitHub · fiche v7.3+) · Langage : Python · Étoiles : 49 100 au 2026-10-11
   Projets    : Documents et OCR, Applications web (Brique pour · LLM, à vérifier)
   Fiche      : fiche v7.3+ · LLM mistral-small-2603 · profil 2026-10-11/8c41d2 · analysée le 2026-10-11
   GitHub     : https://github.com/docling-project/docling
   Notion     : https://www.notion.so/… (+ 3 autres fiches du même dépôt : --details)
```

**En-tête.**

- `Concepts` : les notions retenues, avec entre parenthèses des formes et synonymes français ou
  anglais du lexique (`redecouverte_lexique.py`, 119 concepts). `(hors lexique)` : mot cherché tel
  quel, avec son singulier, son masculin et son féminin construit par ses suffixes (« interactifs »
  trouve aussi « interactives », « créatif » trouve « créative »). `[contrainte]` : système,
  plateforme, langage de programmation ou déploiement (Windows, Linux, macOS, Android, iOS, Python,
  JavaScript, TypeScript, Docker, en local, hors ligne, GPU, terminal, ligne de commande) : il pèse
  la moitié de la notion principale de l'objet du besoin (la plus lourde de ses notions essentielles
  du lexique ; un mot hors lexique, souvent un verbe comme « installer », n'en est jamais une),
  quelle que soit sa rareté, et ne suffit jamais seul pour une correspondance forte quand le besoin
  nomme aussi son objet (« un OCR pour Windows » est d'abord un OCR). `[contexte]` : mots (3 au plus)
  qui suivent « mes », « mon », « ma », « nos », « notre »,
  « my » ou « our » (poids divisé par deux), sauf si le possessif est suivi de « propre » ou « own » :
  dans « mon propre serveur », « my own MCP server », le serveur est l'objet cherché. `[référence]` : mots (3 au plus)
  qui suivent « alternative », « équivalent », « similaire »…, ou une comparaison : « plus simple
  que », « plus facile que », « plutôt que », « au lieu de », « à la place de », « mieux que »,
  « instead of », « rather than », « simpler than », « easier than », « better than » (poids divisé
  par quatre), jusqu'à une ponctuation ou une préposition (« pour », « avec », « dans », « for »…) :
  dans « un OCR plus simple que Tesseract pour les plans scannés », seul Tesseract est la référence.
  Une notion citée à la fois comme objet et comme référence (« dans le terminal, plus
  simple que la ligne de commande ») garde le rôle le plus fort.
- `Ignorés` : mots de la question, sans contenu, et nombres isolés d'un ou deux chiffres
  (« Eurocode 2 » ne cherche pas « 2 », qui trouverait « Apache-2.0 »).
- `Non pris en compte (négation)` : mots qui suivent « sans », « pas », « aucun », « no »,
  « without »… Ils ne sont pas cherchés ; un dépôt qui les mentionne n'est pas écarté pour autant
  (voir « À vérifier »).
- `Aucune fiche ne mentionne` : mots de votre besoin qu'aucune fiche ne contient, même par un
  concept voisin. `Aucune fiche ne mentionne directement : … (trouvé seulement par un concept
  voisin)` : aucune fiche ne contient le mot ni ses synonymes, mais une notion proche est trouvée
  (« élèves » et « éducative ») ; le résultat le dit dans `Répond à` (`concept voisin « … »`). En
  JSON : `absents_partout` et `trouves_par_voisin`. Les mots sont écrits comme vous les avez tapés,
  sans la majuscule du seul début de phrase (« Gérer les notes » donne « gérer ») ; sigles et
  majuscules en cours de phrase sont gardés.
- `Index` : date de la synchronisation (après un rejeu : date de lecture de la capture, puis date du
  rejeu) ; « Recherche locale : rien n'a été envoyé ». Une ligne `Attention` peut suivre (index
  ancien, fiches créées depuis par `gitnotate.py`).

**Niveau.** L'unité de résultat est le dépôt : les preuves de toutes ses fiches sont réunies, et
chaque extrait reste attaché à sa fiche.

- `correspondance forte` : au moins 60 % du poids des notions essentielles du besoin est couvert, dont
  au moins une trouvée directement (pas seulement par un concept voisin ni par l'avis du LLM). Les
  notions essentielles sont celles du lexique qui ne sont pas génériques (« LLM », « IA »,
  « données », « application »… sont des notions secondaires) et les mots hors lexique, hors
  `[contexte]` et `[référence]`. **Quand le besoin n'a qu'une notion essentielle**, deux règles
  s'ajoutent : les notions `[contexte]` comptent aussi dans la couverture (pour moitié de leur
  poids), et les notions secondaires doivent être présentes. Ainsi, pour « un LLM local », un moteur
  de synthèse vocale qui ne parle que de « local » reste partiel (`Ne couvre pas : LLM (notion
  secondaire)`), et pour « gérer mes commits git depuis le terminal », « terminal » seul ne suffit
  plus. **Une contrainte** (`[contrainte]`) ne compte jamais seule comme notion trouvée directement
  quand le besoin nomme aussi son objet, une notion essentielle du lexique : pour « un OCR pour les
  PC Windows », un dépôt qui ne parle que de Windows reste partiel. Quand le besoin ne nomme, en plus
  de ses contraintes, aucune notion essentielle du lexique (« installer Windows dans un conteneur
  Docker », « tester un logiciel Windows dans Docker »), les contraintes et les mots hors lexique sont
  l'objet, à égalité : la couverture décide, même si une fiche sans rapport contient « installer » ou
  « tester » ;
- `correspondance partielle` : une partie seulement (un concept voisin compte pour moitié) ;
- les correspondances faibles (notions trouvées seulement dans l'avis du LLM, ou seulement des
  notions secondaires) sont masquées ; `--tout` les affiche.

Le pourcentage est le score de classement : la part des notions du besoin trouvées dans le dépôt,
pondérée par leur rareté dans votre base (un mot présent partout compte peu ; une contrainte pèse la
moitié de la notion principale de l'objet, rare ou non), par le champ qui les contient et, pour 30 %,
par la force de la correspondance (BM25). Les fortes viennent d'abord, puis
les partielles, chacune par score décroissant.

**Répond à** : pour chaque notion, les champs et la fiche qui la contiennent ; un champ n'est cité
que si son texte contient réellement le mot trouvé (une colonne personnelle : sa valeur). Le JSON
donne, dans `occurrences`, le mot tel qu'écrit et sa position dans le texte stocké du champ. Le nom
cherché réunit le titre, son découpage CamelCase et `propriétaire/dépôt` : un mot du découpage
(« Paddle » de « PaddleOCR ») est situé dans le titre (`Nom`) ; un mot qui ne vient que de
`propriétaire/dépôt` est cité dans le champ `URL`, tel qu'écrit dans l'adresse (« mannheim » :
`URL`, « Mannheim » dans `https://github.com/UB-Mannheim/tesseract`).
`via « … »` donne les mots trouvés quand ils diffèrent de ceux du besoin. `concept voisin « … »` : correspondance partielle
par un concept proche (OCR et « scanné », PDF et « document »…), qui compte pour moitié.
`Indice faible : … seulement dans l'avis du LLM` : la notion n'apparaît que dans la Justification.
`Ne couvre pas` : notions du besoin absentes de ce dépôt, essentielles ou non ; une notion secondaire
est suivie de `(notion secondaire)`, une notion de contexte de `[contexte]`. Les mots qui suivent
« alternative », « équivalent »… (`[référence]`) n'y figurent jamais : un dépôt n'a pas à les
mentionner.

**D'après la fiche** : jusqu'à 4 extraits **mot pour mot**, chacun précédé de
`Champ [fiabilité · version de la fiche du date d'analyse]` ; les mots trouvés sont entre `*` (deux
notions qui se chevauchent, comme « extracteur web » et « web », sont marquées une seule fois). Le
texte est celui de la fiche, à une normalisation près, faite à la synchronisation : apostrophe
typographique (’) remplacée par l'apostrophe droite ('), espaces et traits d'union insécables
simplifiés, caractères de contrôle (séquences d'échappement du terminal, retour chariot) et marques
de sens d'écriture retirés. Pour retrouver un extrait dans Notion avec Ctrl+F, cherchez un fragment
sans apostrophe.

| Étiquette | Sens |
|-----------|------|
| GitHub | copié de GitHub par Gitnotate (nom, adresse, langage, licence d'une fiche v7.3+, topics, description GitHub d'origine) |
| README, mot pour mot | extrait du README vérifié mot pour mot par Gitnotate (Installation, Exemple, Prérequis des fiches récentes) |
| README, modifié dans Notion — à vérifier | même champ, mais modifié dans Notion (mise en forme, plusieurs segments, mention) : une partie du texte peut venir de vous |
| README, extrait ancien | extrait réel du README par une ancienne version, peut être tronqué |
| LLM, à vérifier | rédigé, traduit ou classé par un LLM (Description, Cas d'usage, Catégorie, Brique pour) |
| avis du LLM, ne prouve rien | corps de la Justification ; compte nettement moins qu'un autre champ dans le classement |
| saisi par vous | colonne personnelle, fiche saisie à la main, Justification sans préfixe Gitnotate, cas d'usage réécrits sur une ancienne fiche, Catégorie, Brique pour ou Licence remplies hors d'une analyse v7.3+ |
| origine inconnue | origine impossible à établir |

Ne sont **jamais** cherchés : les gabarits des anciennes versions, les « Non vérifié », « Non
vérifiée » et « Non renseignée » (une information absente, jamais négative), et le Statut (affiché,
il ne sert qu'aux filtres).

**Établi** : seulement des extraits du README vérifiés mot pour mot, ou des topics GitHub, qui
portent une notion du besoin (2 au plus) ; à défaut, la première ligne de l'Installation de la fiche
principale, si elle est vérifiée mot pour mot. Jamais un texte rédigé par un LLM, ni un champ README
modifié dans Notion. Sinon : `rien de vérifié mot pour mot dans le README` (suivi de
`(Installation modifiée dans Notion : voir À vérifier)` quand c'est la raison). Un extrait déjà cité
dans `D'après la fiche` n'est pas répété : `extrait cité ci-dessus`.

**À vérifier** (liste fermée) :

- version de la fiche non reconnue ;
- fiches produites par une première version de Gitnotate (jusqu'à la v7.2) : la liste des champs
  qui sont des gabarits écrits sans lire le dépôt. Ces versions écrivaient des cas d'usage
  génériques (liste anglaise ou sa traduction), `Installation` « See documentation », `Exemple`
  « See docs » ou une commande `pip install <nom>` / `npm install <nom>` construite d'après le nom,
  `Prérequis` « <langage> recent », et un `Type` heuristique ou « Outils ». Le moteur les ignore. La
  description de ces fiches est une traduction par LLM (ou le texte GitHub d'origine) : elle est
  cherchée, avec l'étiquette correspondante ;
- fiche non notée (v7.4 : le dépôt n'avait ni description, ni topics, ni README exploitable ; ou,
  avec `README_LLM_CHARS=0`, son README n'a pas été transmis au LLM) ;
- champs « Non vérifié » de la fiche principale ;
- négation dans une fiche : `La fiche précise (…) : « … »` (par exemple « ne nécessite pas de
  GPU ») ;
- contrainte matérielle : GPU, CUDA, VRAM, NVIDIA ou carte graphique mentionné dans une fiche du
  dépôt, avec la citation ; une phrase négative, facultative ou qui propose le CPU (« GPU
  facultatif », « GPU optional », « sans GPU ») n'en est pas une (même règle que l'indice GPU de
  `gitnotate.py`) ;
- licence absente, non identifiée par Gitnotate (« Non vérifiée »), ou absente selon GitHub
  (« Non renseignée » d'une fiche v7.3+ : aucune licence déclarée, vérifiez les droits de
  réutilisation) ;
- champ modifié dans Notion (mise en forme, plusieurs segments, mention) : une partie du texte peut
  venir de vous ; un tel champ README n'est plus présenté comme établi ni « mot pour mot » ;
- Pertinence différente de la note écrite dans la Justification, ou posée sur une fiche non notée ;
- texte ressemblant à un jeton, masqué.

**Lignes suivantes** : `Statut` (tous les statuts des fiches du dépôt, ceux que vous avez posés
d'abord) ; `Licence`, `Langage`, `Étoiles` (à la date d'analyse) ; `Projets` (`Brique pour`) ;
`Fiche` (version, modèle, profil et date de la fiche principale : celle de la version de Gitnotate
la plus récente, puis de la date d'analyse la plus récente) ;
`GitHub` ; `Notion` (lien de la fiche principale, et nombre d'autres fiches) ; `Voir aussi` (dépôt
de même nom à une autre adresse : renommé, transféré ou homonyme ? jamais fusionné). Les fiches sans
adresse GitHub (notes, idées) sont listées à part, 3 au plus. Le pied indique les correspondances
faibles masquées, les dépôts au-delà de la limite `-n` et les fiches ou dépôts écartés par les
filtres. Si les filtres écartent tout ce qui correspond au besoin, la ligne principale le dit
(`Aucun résultat ne passe les filtres : N fiches ou dépôts correspondent au besoin mais sont
écartés.`) au lieu de conseiller d'autres termes.

**Versions des fiches** : `fiche v7.3+` (v7.3 et v7.4), `fiche v7.2`, `fiche v7.0/v7.1`, `fiche
ancienne (v7.2 ou antérieure, sans Justification)`, `fiche saisie à la main`, `fiche de version non
reconnue`. Une fiche v7.0/v7.1 n'apporte souvent que son nom, une phrase de description et l'avis
du LLM : elle ressort moins qu'une fiche v7.3+. C'est signalé, jamais compensé.

**Pourquoi les étoiles et la Pertinence ne classent pas** : les étoiles mesurent la popularité, pas
l'adéquation à votre besoin. La Pertinence a été calculée selon des grilles différentes d'une
version à l'autre, avec le profil du moment : ces notes ne se comparent pas entre elles. Elles sont
affichées pour information (`--details` montre la Pertinence de chaque fiche avec sa grille).

**`--details`** ajoute la table des concepts (classe, rôle, nombre de fiches qui les contiennent,
rareté, poids, termes cherchés) et, pour chaque dépôt, le calcul du score et toutes ses fiches
(version, règle de détection, dates de création et de modification, indices de modification,
anomalies, Pertinence avec sa grille, chaque champ avec sa fiabilité et la raison de ce niveau).

## 6. Avis LLM facultatif (`--llm`)

Après la recherche locale, `--llm` demande à un LLM un avis sur les premiers dépôts trouvés
(`--llm-max N`, de 1 à 15 ; défaut `REDECOUVERTE_LLM_MAX`, 8). L'avis ne modifie jamais le
classement local.

- **Ce qui part** : votre recherche et, pour chaque dépôt, son nom, `propriétaire/dépôt`, la
  description et, pour les fiches v7.3+, les cas d'usage et la catégorie, sauf un gabarit, un texte
  saisi par vous ou un champ modifié dans Notion (mise en forme, plusieurs segments, mention) : le
  moteur prend alors le même champ d'une autre fiche du dépôt, ou rien. Une phrase ajoutée en texte
  brut dans le même segment ne se détecte pas et part avec le reste ; `--llm-apercu` montre le texte
  exact.
- **Ce qui ne part jamais** : liens et identifiants Notion, Statut, colonnes personnelles,
  `Brique pour`, Justification.
- **Fournisseurs** : ceux de `LLM_PROVIDERS` qui ont une clé, dans l'ordre (par défaut Mistral, puis
  OpenRouter en secours si le premier ne répond pas). OpenRouter est ignoré avec
  `OPENROUTER_RESPONSE_FORMAT=json_schema`.
- **Confirmation** : un résumé (fournisseur, dépôts, champs, nombre de caractères, confidentialité)
  s'affiche, puis `Envoyer ? Tapez « oui » pour confirmer :`. Toute autre réponse annule (rien n'est
  envoyé). `--oui` confirme sans question ; il est obligatoire hors terminal interactif (sinon :
  `Avis LLM non demandé : entrée non interactive (ajoutez --oui)`).
- **`--llm-apercu`** affiche le texte exact qui serait envoyé et n'envoie rien (code 0), même sans
  clé configurée.
- **Coût** : un appel par recherche (le fournisseur suivant n'est sollicité que si le premier ne
  répond pas ; un appel peut être répété une fois après une erreur 429 ou 5xx), décompté des
  mêmes quotas que `gitnotate.py` (par exemple 50 requêtes par jour sur le palier gratuit
  d'OpenRouter). Aucun avis n'est mis en cache.
- **Confidentialité** : palier gratuit de Mistral, vos requêtes peuvent servir à l'entraînement
  (réglable dans la console Mistral) ; OpenRouter, voir `OPENROUTER_DATA_COLLECTION` et les réglages
  Privacy de votre compte.
- **Lecture** : un bloc séparé `Avis du LLM — <fournisseur>, modèle servi <modèle> — facultatif, non
  vérifié, n'a pas modifié le classement` donne l'ordre proposé (adéquation de 0 à 3) et une raison
  par dépôt, avec son rang local. `(raison non ancrée dans la fiche)` signale une raison qui ne
  reprend aucun mot significatif du texte envoyé pour ce dépôt. Une réponse dont moins de la moitié
  des avis sont valides est rejetée : `Réponse du LLM inexploitable ; classement local conservé`
  (code 2). Sans clé : `Avis LLM impossible (aucune clé configurée) ; résultats locaux ci-dessus`
  (code 2 ; « résultats locaux conservés » avec `--format markdown`, `--format json` ou `--sortie`,
  dont les résultats ne sont pas au-dessus). Les raisons et le nom du modèle renvoyés par le LLM sont
  affichés sans caractère de contrôle.

## 7. Windows

- **OneDrive** : par défaut, l'index est créé dans le dossier du projet (`.gitnotate_index`). Si ce
  dossier est synchronisé par OneDrive, la synchronisation du fichier peut bloquer son remplacement.
  Placez alors le dossier de données hors de OneDrive avec la variable `GITNOTATE_DATA_DIR`, et
  déplacez-y `.env` et `user_profile.json` : `gitnotate.py` et `redecouverte.py` liront tous deux ce
  dossier. Pour la définir durablement (puis ouvrir une nouvelle fenêtre) :

  ```powershell
  [Environment]::SetEnvironmentVariable('GITNOTATE_DATA_DIR', 'C:\Gitnotate-donnees', 'User')
  ```

- **Antivirus, DB Browser for SQLite** : un programme qui garde l'index ouvert empêche son
  remplacement. Le moteur réessaie pendant environ 5 secondes, puis s'arrête (code 2) avec le
  message `L'index est ouvert par un autre programme…` ; l'ancien index reste utilisable. Fermez le
  programme et relancez `sync`.
- **Guillemets** : mettez le besoin entre guillemets doubles ; une apostrophe à l'intérieur ne gêne
  pas (`"un OCR pour l'atelier"`). Sans guillemets, chaque mot devient un argument séparé : un
  besoin de plusieurs mots est refusé (code 1) avec le message `Commande invalide : arguments en trop :
  … Mettez le besoin entre guillemets doubles…`. Un mot seul sans la commande
  (`python redecouverte.py pdf`) est refusé avec le message
  `Commande inconnue « pdf ». Pour chercher : python redecouverte.py cherche "pdf"`. Les commandes
  s'écrivent aussi avec accent ou majuscule (`état`, `Cherche`) ; les options se placent après la
  commande (`python redecouverte.py cherche "pdf" --log-level verbose`).
- **Ctrl-C** : interrompt rapidement, même pendant une requête Notion (le moteur attend la réponse
  par tranches d'une demi-seconde) ; l'ancien index est conservé (code 130).
- **Accents et redirection** : l'affichage dans la console est sûr. Sous PowerShell, n'utilisez pas
  la redirection `> resultats.txt` : Python écrit dans l'encodage ANSI (cp1252) et Windows PowerShell
  5.1 relit cette sortie avec l'encodage de la console (cp850 en français), si bien que toutes les
  lettres accentuées sont corrompues (« dépôts » devient « dÚp¶ts ») ; constat simulé, non vérifié
  sous PowerShell. Sous `cmd.exe`, `>` écrit en cp1252 et seuls les caractères inconnus de cp1252
  deviennent « ? ». Pour garder le texte exact, utilisez `--sortie resultats.txt` ou
  `--format markdown --sortie resultats.md` (UTF-8).
- **Lecteur réseau** (`H:`, `\\serveur\partage`, fréquent en établissement) : le moteur ouvre l'index
  avec un chemin sans résolution des lecteurs et une adresse SQLite sans « autorité »
  (`file:////serveur/partage/…`), refusée sinon par SQLite. Non vérifié sous Windows : si `cherche`
  ou `etat` répondent `Index illisible` juste après un `sync` réussi, placez le dossier de données
  sur un disque local avec `GITNOTATE_DATA_DIR`.
- **Code de sortie** : `$LASTEXITCODE` après la commande (Linux : `echo $?`).

## 8. Fichiers et codes de sortie

```text
<dossier de données>\            dossier du projet, ou GITNOTATE_DATA_DIR
  .gitnotate_index\              créé par sync (jamais par cherche ni etat), ignoré par git
    redecouverte.sqlite          l'index
    redecouverte.sqlite.tmp      index en construction, supprimé à la fin de sync (succès ou échec)
    sync.lock                    fichier de verrou, laissé en place
  exports\                       ignoré par git
    capture-notion-….json        sync --capture
    <fichier> de --sortie        quand le nom est donné sans dossier
```

**Supprimer le dossier `.gitnotate_index` ne fait rien perdre** : il se reconstruit au prochain
`sync` (`Remove-Item -Recurse .gitnotate_index`, Linux : `rm -r .gitnotate_index`). Un index créé
par une autre version du moteur n'est jamais converti : `cherche` et `etat` demandent de relancer
`sync` (c'est le cas d'un index construit avant l'affinage de la pertinence, format 1 : les noms des
colonnes personnelles y étaient indexés ; le format 2 n'indexe que leurs valeurs). Ce `sync` compare
quand même la lecture à la liste des fiches et à la base de l'ancien index : le garde-fou contre une
baisse brutale s'applique (bilan : `index précédent d'un autre format : remplacé après comparaison
des fiches`) ; seul un index illisible est remplacé sans comparaison. Modifier les concepts, mots
vides ou déclencheurs du lexique (`redecouverte_lexique.py`) ne
demande aucune synchronisation : l'index garde le texte des fiches. Exception : les gabarits
`GABARITS_CAS_USAGE_EN` et `GABARITS_CAS_USAGE_FR` sont appliqués à l'indexation (fiabilité des Cas
d'usage, version de la fiche) ; après les avoir modifiés, relancez `sync` (ou `sync --depuis` une
capture).

`python redecouverte.py etat` résume l'index (fichier, date, base, fiches, versions, colonnes,
anomalies, moteur). `--anomalies` détaille les anomalies (`url_absente`, `url_non_github`,
`titre_absent`, `type_inattendu`, `colonne_ambigue`, `valeur_illisible`, `troncature_possible`,
`jeton_masque`) avec le lien de chaque fiche ; `--doublons` liste les dépôts sur plusieurs fiches,
avec la version, la date, le Statut et le lien de chacune ; `--format json` pour un script.

| Code | Signification |
|------|---------------|
| 0 | terminé, même sans résultat ; avis LLM annulé ou non demandé |
| 1 | configuration (jeton, `DATABASE_ID`, base refusée ou introuvable), commande ou option invalide, recherche sans mot significatif, capture introuvable ou illisible, index absent, illisible ou d'une autre version, FTS5 absent |
| 2 | lecture Notion incomplète ou interrompue, baisse brutale refusée, autre synchronisation en cours, index ouvert par un autre programme, construction impossible (l'ancien index est conservé) ; index remplacé mais capture non écrite ; fichier `--sortie` non écrit ; avis LLM demandé impossible ou réponse inexploitable |
| 130 | interruption (Ctrl-C) |

## 9. Valider sur la base réelle et mesurer

La procédure de validation en lecture seule sur votre base est la partie H de
[VALIDATION.md](VALIDATION.md#h-redécouverte-lecture-seule). Elle s'appuie sur le script de mesure
`scripts/evaluer_redecouverte.py`, qui lance des recherches dont vous avez écrit les résultats
attendus **avant** de les voir :

```powershell
python scripts/evaluer_redecouverte.py exports/mes_requetes.json --details
```

Format du fichier (UTF-8) : les clés de dépôt sont `propriétaire/dépôt` en minuscules, telles que
`cherche` les affiche après le nom (`1. docling — docling-project/docling — …`) ; `en_tete` = dépôts
attendus en tête (gain 2), `acceptables` (gain 1), `a_exclure` = intrus ; `options` reprend les
filtres (`statut`, `exclure_statut`, `licence`, `categorie`, `projet`), chacun avec une liste de
valeurs (un texte seul est accepté et mis dans une liste) ; une option inconnue arrête le script
(code 1). Un fichier enregistré avec BOM (PowerShell 5.1, Bloc-notes) est accepté ; une erreur de
syntaxe JSON est signalée avec sa ligne et sa colonne ; un dépôt attendu absent de l'index (faute de
frappe, majuscules) est signalé par une ligne `Attention`.

```json
{"requetes": [
  {"id": "M01", "jeu": "reel", "requete": "extraire des données de PDF techniques", "options": {},
   "en_tete": ["docling-project/docling"], "acceptables": ["paddlepaddle/paddleocr"], "a_exclure": []},
  {"id": "M02", "jeu": "reel", "requete": "", "options": {"statut": ["En test"]},
   "en_tete": ["docling-project/docling"], "acceptables": [], "a_exclure": []}
]}
```

Pour chaque requête, le script affiche nDCG@10 (qualité de l'ordre des 10 premiers), P@5 (part
d'attendus dans les 5 premiers), MRR (1 si un dépôt attendu en tête est premier, 1/2 s'il est
deuxième…), intrus@3 et intrus@5 (nombre d'intrus dans les 3 et 5 premiers), le nombre de
correspondances fortes et les attendus manquants ; `--details` montre les premiers dépôts. Les
moyennes sont données par jeu ; les requêtes avec filtres sont mesurées à part, hors moyenne. Le
script ouvre l'index en lecture seule, sans réseau (code 1 si le fichier ou l'index est illisible).

## 10. Mesures sur le corpus synthétique

**Ce qui a été mesuré.** Le corpus de test (`tests/fixtures/redecouverte/`) contient 63 fiches
synthétiques, écrites pendant la conception : 62 hors corbeille, 51 dépôts, réparties en v7.3+ ×16,
v7.2 ×5, v7.0/v7.1 ×20, ancienne ×18 et manuelle ×3. Les noms de dépôts sont réels, le contenu des
fiches est fabriqué pour les tests. L'index a été reconstruit hors ligne (`sync --depuis` d'une
capture du corpus), puis mesuré avec `scripts/evaluer_redecouverte.py` sur 24 requêtes de référence
et 8 requêtes nouvelles, écrites avec leurs attendus et figées (empreinte SHA-256) avant tout
résultat, puis ajoutées sans changement au fichier de référence (jeu `nouvelles` de
`tests/fixtures/redecouverte/requetes.json`). Moteur 1.0.0, gitnotate 7.4.0, mesures du 2026-10-12,
refaites après l'affinage de la pertinence (noms des colonnes personnelles non indexés, classe
« contrainte », comparaisons « plus simple que », « mon propre », féminins des mots hors lexique,
nombres isolés ignorés, formes « calcul de structures », notion « vie scolaire », affichage des
concepts absents). Entre parenthèses : la valeur avant l'affinage, quand elle diffère. Les
corrections de la seconde revue (un mot hors lexique n'est plus l'objet du besoin, plus de féminin
en « e » ajouté, comparaison arrêtée par une préposition, citation `URL` d'un mot du seul
propriétaire/dépôt) laissent toutes ces mesures inchangées (seuls les scores de N07 bougent, sans
changer les 5 premiers).

| Jeu | Requêtes | nDCG@10 | MRR | P@5 | intrus@3 | intrus@5 | Réussies / partielles / échecs |
|-----|----------|---------|-----|-----|----------|----------|-------------------------------|
| Référence (Q01-Q15, hors Q10 et Q14 filtrées) | 13 | 0,84 (0,83) | 0,92 | 0,82 (0,80) | 0,00 | 0,31 (0,38) | 11 / 2 / 0 |
| Hors échantillon (H01-H10) | 10 | 0,92 | 1,00 | 0,81 | 0,00 | 0,40 | 10 / 0 / 0 |
| Anglais (E01) | 1 | 0,80 | 1,00 | 0,80 | 0,00 | 1,00 | 1 / 0 / 0 |
| **Ensemble de référence** | 24 | **0,87** | **0,96** | **0,81** (0,80) | **0,00** | 0,38 (0,42) | 22 / 2 / 0 |
| **Nouvelles (N01-N08)** | 8 | **0,86** (0,84) | **0,86** (0,85) | **0,73** | **0,25** (0,38) | 0,50 | 5 / 2 / 1 (4 / 2 / 2) |
| Filtrée Q10 (licence MIT), hors moyenne | 1 | 0,90 | 1,00 | 0,80 | 0 | 0 | réussie |
| Filtrée Q14 (statuts), hors moyenne | 1 | 0,97 | 1,00 | 1,00 | 0 | 0 | réussie |

Verdicts : réussie si un dépôt attendu en tête est premier, sans intrus dans les 3 premiers ni
intrus « forte » dans les 5 premiers ; partielle si un dépôt attendu en tête figure dans les 3
premiers, avec au plus un intrus dans les 3 premiers ; échec sinon. Une requête sans réponse
attendue est réussie si aucune correspondance n'est « forte » et qu'aucun intrus n'est dans les 3
premiers, en échec si une correspondance est « forte », partielle sinon. Les listes d'intrus du fichier de référence sont incomplètes : d'après un relevé à part,
fait avant la revue du lot 4, environ 0,42 dépôt hors sujet par requête figure dans les 3 premiers,
et non 0,00.

**Recherches représentatives** (F : correspondance forte, P : partielle ; « intrus » : dépôt hors
sujet listé comme tel ; deux dépôts différents s'appellent tesseract) :

| Recherche | Attendus en tête | 5 premiers obtenus | Verdict |
|-----------|------------------|--------------------|---------|
| Q01 « Quels outils déjà enregistrés pourrais-je utiliser pour extraire des données de PDF techniques ? » | docling, paddleocr, olmocr, dolphin, deepseek-ocr, deepseek_ocr_app | docling (F), paddleocr (F), olmocr (F), dolphin (F), omniparser (intrus, P) | réussie ; deepseek-ocr (fiche v7.0/v7.1 pauvre) absent des 10 premiers |
| Q02 « Quels dépôts seraient réutilisables dans une application FastAPI de traitement documentaire ? » | deepseek_ocr_app, docling, txtai, paddleocr | deepseek_ocr_app (F), docling (F), paddleocr (F), pageindex (F), dolphin (F) | réussie |
| Q03 « Ai-je déjà enregistré un projet intéressant pour automatiser une veille financière ? » | dexter, gpt-researcher, huginn, finrobot | huginn (F), dexter (F), composer-trade-mcp (P), finrobot (P), gpt-researcher (P) | réussie |
| Q04 « Un moteur OCR qui fonctionne sous Windows pour des plans scannés ? » | tesseract (×2), paddleocr, poppler-windows | paddleocr (F), tesseract (P), dolphin (P), deepseek_ocr_app (P), tesseract (P) | réussie ; « Windows » est une contrainte : windows (intrus) n'est plus 5e |
| Q05 « Ai-je quelque chose pour le métré ou la lecture de plans de bâtiment (BIM, IFC) ? » | aucun (rien dans le corpus) | paddleocr (P), open-notebook (P), docling (P) | réussie : aucune « forte » |
| Q09 « Une base vectorielle ou un RAG pour interroger mes supports de cours ? » | ragflow, txtai, open-notebook, pagelm | pageindex (P), ragflow (P), paddleocr (P), buildingai (P), txtai (P) | partielle |
| Q11 « Un agent de code open source auto-hébergeable, alternative à Claude Code ? » | openhands (×2 adresses), opencode | openhands (F), huginn (F, hors sujet), opencode (F), awesome-selfhosted (intrus, P), windows (P) | réussie (huginn hors sujet non listé comme intrus) |
| Q15 « Un outil pour faire un tableau de bord de données en Python sans écrire de front-end ? » | marimo | evidently (F), marimo (P), python (P, hors sujet), fastmcp (P), docling (intrus, P) | partielle ; « Python » est une contrainte : un dépôt qui ne parle que de Python sort après ceux qui parlent de l'objet (avant : datagouv-mcp, paddleocr, olmocr aux rangs 3 à 5) |
| H04 « faire tourner un modèle de langage en local sur mon PC » | llama.cpp | llama.cpp (F), piper1-gpl (P, hors sujet : `Ne couvre pas : modèle de langage (notion secondaire), PC [contexte]`), tesseract (P), awesome-selfhosted (P), huginn (P) | réussie |
| E01 « Which saved tools could extract data from technical PDFs? » | comme Q01 | docling (F), olmocr (F), paddleocr (F), dolphin (F), omniparser (intrus, P) | réussie : mêmes 4 premiers que Q01 |
| N01 « Je dois récupérer les quantités d'un DPGF en PDF pour les reprendre dans un tableur : quel outil ai-je déjà ? » | docling, paddleocr | docling (F), open-notebook (P), pageindex (P), paddleocr (P), dolphin (P) | réussie |
| N02 « offline text-to-speech to narrate my course videos » | piper1-gpl, chatterbox | piper1-gpl (F), chatterbox (F), awesome-selfhosted (P), huginn (P), llama.cpp (P) | réussie ; « offline » est une contrainte : chatterbox (« SoTA open-source TTS », sans « hors ligne ») passe de partielle à forte |
| N03 « Which saved repos help me write my own MCP server in Python? » | fastmcp | fastmcp (F), servers (F), datagouv-mcp (F), composer-trade-mcp (F), awesome-mcp-servers (F) | réussie : « my own » ne met plus « MCP server » en contexte ; les 5 « forte » sont des serveurs MCP (attendu ou acceptables) |
| N04 « Un OCR qui ne nécessite pas de GPU, pour les PC Windows de la salle informatique » | tesseract (×2) | tesseract (F), tesseract (P), deepseek_ocr_app (intrus, P), deepseek-ocr (intrus, P), paddleocr (P) | partielle (nDCG@10 0,95, avant 0,88 avec windows, intrus, 2e) : la négation « pas de GPU » ne déclasse pas les dépôts qui exigent un GPU |
| N05 « Un logiciel de calcul de structures en béton armé selon l'Eurocode 2 » | aucun | aucun résultat (`Aucune fiche ne contient ces concepts : calcul de structures, selon.`) | réussie (avant : paddleocr, dolphin, pagelm par « structurées », evidently par « Apache-2.0 », tous partiels) |
| N06 « Gérer les notes et les absences de mes élèves » | aucun | pagelm (intrus, P) | partielle : aucune « forte » ; pagelm reste visible par « notes structurées » (avant : échec, pagelm « forte », tesseract et docling sans extrait par le nom de colonne « Notes ») |
| N07 « Une interface pour utiliser Git dans le terminal, plus simple que la ligne de commande » | lazygit | lazygit (F), deepseek_ocr_app (P), marimo (P), claude-code-templates (intrus, P), ai-hedge-fund (P) | réussie (avant : partielle, claude-code-templates 2e) |
| N08 « Créer des supports de cours interactifs en Python pour mes étudiants de BTS » | marimo | pagelm (F), open-notebook (F), generative-ai-for-beginners (P), paddleocr (P), pageindex (P) | échec : marimo (fiche v7.0/v7.1 pauvre) 7e ; pagelm trouvé par « ressources interactives » |

**Contrôles de non-invention** (34 recherches, 263 résultats affichés, limite 10) : les 584 extraits
et citations (449 extraits « D'après la fiche », 93 « Établi », 42 citations de négation ou de
contrainte matérielle) se retrouvent tels quels dans le texte Notion d'origine, et le rendu affiché
de chacun des 542 extraits (marques retirées) est identique au texte cité. Chaque notion de
`Répond à` (389 lignes, 612 champs cités) correspond à une occurrence réelle du mot dans le texte
stocké du champ cité ; 10 lignes n'ont pas d'extrait, toutes parce que le mot n'est que dans le nom
du dépôt (le nom n'est jamais cité en extrait). Depuis la seconde revue, un mot venu du seul
`propriétaire/dépôt` est cité dans `URL`, et non plus dans `Nom`, dont le texte ne le contient pas.
Avant l'affinage, une recherche contenant « notes »
ou « tags » citait la colonne « Notes » sans extrait : le mot n'était que dans le nom de la colonne.
Cet invariant est vérifié sur toutes les requêtes du fichier de référence par
`tests/test_redecouverte_affinage.py`. Aucun extrait ne vient d'un gabarit ni d'un « Non vérifié ».
Les 184 résultats qui contiennent une fiche ancienne portent tous l'avertissement « première version
de Gitnotate ». La version détectée correspond à la version attendue pour toutes les fiches
affichées. La fiche non notée du corpus porte la limite « Fiche non notée ».

**Effet de chaque correction** (32 requêtes sans filtre ; chacune retirée seule de l'état final, sauf
la première, mesurée sur l'index du nouveau format comparé à l'ancien, avant les autres corrections) :

| Correction | Requêtes dont une mesure change | Effet |
|------------|---------------------------------|-------|
| Noms des colonnes personnelles non indexés | N06 | tesseract et docling ne sortent plus sur le seul nom de colonne « Notes » |
| Classe « contrainte » | Q04, Q07, N02, N03, N04, N07, N08 | nouvelles : nDCG@10 de 0,81 à 0,86, MRR de 0,74 à 0,86, intrus@3 de 0,375 à 0,25 ; référence : nDCG@10 de 0,835 à 0,836, intrus@3 inchangé (0) |
| « mon propre », « my own » | N03 | fastmcp passe du 3e au 1er rang (MRR de 0,33 à 1) |
| Comparaisons (« plus simple que »…) | aucune mesure | N07 : « simple » n'est plus cherché, omniparser (trouvé par ce seul mot) quitte les 5 premiers, lazygit passe de 70 à 100 % |
| Féminins des mots hors lexique | aucune mesure | N08 : pagelm trouvé par « ressources interactives », de partielle à forte |
| Nombres isolés ignorés | aucune mesure | N05 : evidently n'est plus trouvé par « Apache-2.0 » |
| Formes « calcul de structures » | aucune mesure | N05 : paddleocr, dolphin et pagelm ne sont plus trouvés par « structurées » |
| Notion « vie scolaire » (« absences »…) | N06 | sans elle, pagelm reste « forte » par le seul mot « notes » |

Les concepts gardés en contrainte sont ceux dont la mesure ne dégrade pas la référence : classer
« auto-hébergé » en contrainte améliorait Q11 mais plaçait dexter (intrus) 2e en H10 ; « navigateur »
abaissait H03 (nDCG@10 de 1,00 à 0,99) ; « open source » en contrainte plaçait un intrus dans les 3 premiers de
Q11 ; ces trois-là restent comme avant (« gratuit » et « open source » restent des notions secondaires,
de poids 0,3). Un poids de contrainte fixé à la moitié de sa rareté (et non de la notion principale)
laissait fastmcp 3e en N03 (MRR des nouvelles 0,74 au lieu de 0,86).

**Ce que ces chiffres valent** : ils ont servi à choisir les réglages et à repérer les défauts
décrits ci-dessous ; ils ne mesurent pas la qualité sur votre base réelle (corpus de 62 fiches écrit
pendant la conception, attendus jugés par une seule personne ; sur 8 requêtes nouvelles, une seule
requête déplace le MRR moyen de 0,15). L'avis LLM, l'exécution sous Windows et la console cp1252
n'ont pas été mesurés. La validation sur la base réelle (partie H de
[VALIDATION.md](VALIDATION.md)) reste nécessaire.

## 11. Limites

- **Recherche lexicale** : en dehors du lexique, aucune proximité de sens. Un besoin formulé avec des
  mots absents des fiches et du lexique ne trouve que les formes exactes (signalé par `Aucune fiche
  ne mentionne`). Le lexique a aussi des polysémies : « notes » (des élèves) rejoint « notes
  structurées » (N06 : pagelm reste visible en partielle ; il n'est plus « forte » parce que
  « absences », notion du lexique depuis l'affinage, n'est dans aucune fiche), « tableur » a pour
  voisin « table » (« table des matières »), « DPGF » et « métré » sont une même notion, « français »
  rejoint « données publiques françaises ». Corrigé à la revue : « feed » seul (verbe anglais, « to
  feed an LLM ») n'est plus lu comme « veille » (seuls « rss feed » et « news feed » le sont), et
  « surveillance » n'entre plus dans « veille » par le voisinage avec « monitoring ». Corrigé à
  l'affinage : « calcul de structures » est une forme du lexique (plus de « données structurées »), un
  nombre isolé d'un ou deux chiffres n'est plus cherché, un mot hors lexique au masculin trouve aussi
  son féminin. Le féminin est construit par ses seuls suffixes (if/ive, ier/ière, ien/ienne,
  el/elle, eur/euse) : il peut produire une forme qui n'existe pas (« créateur » donne « créateuse »,
  sans effet puisqu'aucune fiche ne la contient). Aucun « e » n'est ajouté après une consonne : une
  fois les accents retirés, « test » + e rejoindrait le participe « Testé » d'une note personnelle
  (corrigé à la seconde revue) ; en contrepartie, l'anglais « text » ne trouve pas le français
  « texte ».
- **Fiches anciennes pauvres** : une fiche v7.0/v7.1 n'apporte que son nom, une phrase de
  description et l'avis du LLM (qui compte peu) ; elle ressort moins qu'une v7.3+. Signalé, non
  compensé : seule une nouvelle analyse l'enrichirait, ce que le moteur ne fait pas (aucune écriture
  dans Notion).
- **Heuristiques de la phrase** : la négation porte sur les 4 mots de contenu qui suivent et s'arrête
  à une ponctuation ou à un mot de liaison ; elle retire le mot de la recherche sans déclasser les
  dépôts qui le mentionnent (N04 « un OCR qui ne nécessite pas de GPU » : deepseek_ocr_app, qui exige
  un GPU, est 3e, avec la limite `Contrainte matérielle mentionnée`). Le possessif (« mes », « my »…)
  met les 3 mots suivants en contexte, sauf s'il est suivi de « propre » ou « own » ; il reste à tort
  en contexte quand il désigne l'objet cherché sans ce mot (« pour créer mon serveur MCP »). Quand le
  besoin n'a qu'une notion essentielle, les notions de contexte comptent dans la couverture et les
  notions secondaires sont exigées pour « forte ». Avec deux notions essentielles ou plus, « forte »
  ne regarde que celles-ci : une notion secondaire absente (« données ») ne l'empêche pas, mais elle
  est listée dans `Ne couvre pas`. La recherche reste lexicale : pour « un LLM local », gpt-researcher
  (« fondé sur des LLM », « recherches … locales ») sort « forte » avant llama.cpp. Une comparaison
  (« plus simple que la ligne de commande ») met la suite en référence, mais une notion déjà citée
  comme objet (« dans le terminal ») garde son rôle. `--details` montre le rôle et le poids de chaque
  mot.
- **Contraintes** : une contrainte (Windows, Python, Docker, en local, GPU, terminal…) pèse la moitié
  de la notion principale de l'objet, même quand elle est très fréquente : un dépôt qui ne parle que
  de la contrainte sort donc après ceux qui parlent de l'objet, mais avant des correspondances plus
  faibles (Q15 « tableau de bord … en Python » : TheAlgorithms/Python, hors sujet, est 3e). Une fiche
  qui couvre l'objet sans la contrainte peut être « forte » (N02 : chatterbox, dont la fiche ne dit pas
  « hors ligne ») : la contrainte est listée dans `Ne couvre pas`. Une notion générique du lexique
  nommée avec des contraintes reste l'objet : pour « un serveur Windows dans Docker », dockur/windows
  (« Windows inside a Docker container ») n'est que partiel, derrière awesome-selfhosted
  (« servers », forte). Le moteur ne distingue pas « serveur Windows » (une édition de Windows) de
  « un OCR Windows dans Docker », où un dépôt qui ne couvre que Windows et Docker ne doit pas être
  « fort ». « Auto-hébergé » et « navigateur »
  restent des notions ordinaires, « gratuit » et « open source » des notions secondaires (mesures de
  la [section 10](#10-mesures-sur-le-corpus-synthétique)).
- **Requêtes en anglais** : les mots de question anglais courants sont ignorés comme les français
  (E01 donne les mêmes premiers dépôts que Q01) ; le lexique reste centré sur les notions des
  fiches.
- **Modification manuelle** : détectée par la mise en forme, les segments, les mentions, ou au
  niveau de la page ; un champ ainsi modifié n'est jamais présenté comme établi ni envoyé au LLM.
  Une phrase ajoutée sans mise en forme dans un champ produit par Gitnotate ne se détecte pas : elle
  garde l'étiquette de ce champ.
- **Normalisation du texte** : apostrophes, espaces insécables et caractères de contrôle sont
  uniformisés à la synchronisation (voir « D'après la fiche ») ; un extrait peut donc différer de la
  fiche Notion sur ces seuls caractères.
- **Découpage des mots** : `c++`, `c#` et `.net` perdent leur ponctuation ; les noms collés en
  minuscules (`olmocr`) ne sont pas découpés (les noms en CamelCase le sont : `PaddleOCR`) ; les mots
  d'une lettre ne sont pas cherchés.
- **Doublons** : un dépôt renommé dont les deux adresses ont chacune une fiche n'est pas regroupé ;
  `Voir aussi` le signale quand le nom est identique.
- **Notion** : fiches à la corbeille non lues, pages archivées probablement pas non plus (non
  vérifié) ; base multi-sources : arrêt (HTTP 400) ; un texte avec 25 mentions ou plus peut être
  tronqué par Notion (anomalie `troncature_possible`) ; aucun instantané pendant la lecture (une
  fiche supprimée pendant la lecture peut en décaler une autre : relancez `sync`) ; limite de débit
  partagée avec `gitnotate.py` sur le même jeton.
- **Windows** : un index dans OneDrive ou ouvert ailleurs peut bloquer le remplacement (réessais,
  ancien index conservé).
- **Statut « Écarté »** : non masqué par défaut (`--exclure-statut "Écarté"`).
- **Avis LLM** : non déterministe, informatif seulement.
- **Mesures** : faites sur un corpus synthétique de 62 fiches écrit pendant la conception ; elles
  justifient les choix, pas la qualité réelle ([section 10](#10-mesures-sur-le-corpus-synthétique)).
