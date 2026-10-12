# Valider la v7.4 avant la mise en production

Cette procédure vérifie la v7.4 sur de vraies données, étape par étape, **sans risque pour la base
principale**. Les premiers essais se font sur une page et une base de test ; la base principale
n'est utilisée qu'à la fin, avec quelques fiches seulement.

Rappels :

- Dans Notion, `gitnotate.py` ne fait que lire (GET, et POST de requête sur la base) et créer (des
  fiches ; une base seulement avec `CREATE_DATABASE=true`). Il ne modifie jamais une fiche, ne
  supprime rien et ne change jamais le schéma d'une base existante : il n'envoie que des options de
  sélection déjà présentes (`Langage`, `Statut`, `Type` et colonnes facultatives) et omet les autres
  valeurs, signalées au démarrage (`⚠️  Colonne '…' sans l'option …`) et en fin de run.
- `--dry-run` appelle GitHub et le LLM (le quota est consommé), mais n'écrit rien dans Notion.
- `redecouverte.py` (partie H) ne fait que lire Notion : deux appels de lecture seulement, vérifiés
  avant tout envoi, et aucune écriture.
- Commandes données pour PowerShell (Windows), avec l'équivalent Linux. Dans chaque nouvelle fenêtre,
  placez-vous dans le dossier du projet et réactivez l'environnement virtuel
  (`.\.venv\Scripts\Activate.ps1`, ou `source .venv/bin/activate` sous Linux).
- Lancez un seul run à la fois, et ne modifiez pas les bases pendant les contrôles.
- Si un contrôle échoue, arrêtez-vous là : ne passez pas à l'étape suivante (voir l'étape G).

| Étape | Ce qu'elle fait | Écrit dans Notion ? |
|-------|-----------------|---------------------|
| 0 | dossier de données de test (`.env` et profil séparés) | non |
| A | sauvegarde : export Notion et copie des fichiers locaux | non |
| B | base de test (copie de la base principale ou nouvelle base) | oui, sur la page de test seulement |
| C | `python scripts/check_llm.py` | non |
| D | simulation `--dry-run` de 5 dépôts choisis, grille de contrôle | non |
| E | import réel de 5 fiches au plus dans la base de test | oui, dans la base de test |
| F | bascule sur la base principale, quelques fiches | oui, quelques fiches neuves |
| G | critères d'acceptation et retour arrière | — |
| H | redécouverte : copie locale et recherches sur la base principale ou une base historique | non (lecture seule) |

## 0. Dossier de données de test (recommandé)

La variable système `GITNOTATE_DATA_DIR` désigne le dossier où Gitnotate lit `.env` et
`user_profile.json`, et où il écrit son cache, ses statistiques et `.gitnotate_state.json`. Avec un
dossier dédié aux essais, votre `.env` principal et le fichier d'état de la base principale ne sont
jamais touchés, et `CREATE_DATABASE` reste possible pour une base de test.

```powershell
# PowerShell, dans le dossier du projet
New-Item -ItemType Directory -Force ..\gitnotate-test
Copy-Item .env ..\gitnotate-test\.env
Copy-Item user_profile.json ..\gitnotate-test\user_profile.json
$env:GITNOTATE_DATA_DIR = (Resolve-Path ..\gitnotate-test).Path
```

```bash
# Linux
mkdir -p ../gitnotate-test && cp .env user_profile.json ../gitnotate-test/
export GITNOTATE_DATA_DIR="$(cd ../gitnotate-test && pwd)"
```

- Le `.env` copié pointe encore vers la page source et la base principales : ne lancez rien avant
  d'y avoir remplacé `PARENT_PAGE_ID` et `DATABASE_ID` à l'étape B (`notepad ..\gitnotate-test\.env`).
- La variable ne vaut que pour la fenêtre en cours. **Redéfinissez-la dans chaque nouvelle fenêtre**,
  sinon le `.env` principal (et donc la base principale) est utilisé.
- Sans `user_profile.json` dans ce dossier, le profil par défaut intégré (v1) est utilisé.
- Vérification à chaque run : la ligne `👤 Profil de pertinence : fichier …` affiche le chemin du
  profil lu, qui doit être celui du dossier de test. La ligne `📋 Réutilisation database …` affiche
  les 8 premiers caractères de `DATABASE_ID`, qui doivent correspondre à la base de test.

## A. Sauvegarde

1. **Export Notion de la base principale** : ouvrez la base en pleine page, puis
   ••• (en haut à droite) → Exporter. Choisissez le format « Markdown & CSV », incluez les
   sous-pages, puis exportez. Faites de même pour la page source des liens. Rangez les archives ZIP
   dans `sauvegardes\` (dossier ignoré par git), par exemple
   `sauvegardes\2026-10-11-avant-v7.4\`.
2. **Nombre de fiches de la base principale** : notez-le. Dans Notion, en bas d'une colonne de la
   vue tableau (sans filtre), le menu Calculer affiche le décompte de toutes les lignes (« Count
   all » dans l'interface anglaise) ; ce calcul est enregistré dans la vue (pas dans les fiches) :
   pour une validation strictement en lecture (partie H), comptez plutôt les lignes
   du CSV exporté (décompressez d'abord l'archive ; si elle contient un fichier qui se termine par
   `_all.csv`, prenez celui-là) :

   ```powershell
   (Import-Csv 'sauvegardes\2026-10-11-avant-v7.4\<fichier>.csv').Count
   ```

3. **Fichiers locaux** : copiez dans le même dossier `.env`, `user_profile.json`,
   `gitnotate_stats.json` et `.gitnotate_state.json` (s'ils existent). Si vous n'utilisez pas git,
   gardez aussi une copie du dossier du projet en v7.3.

L'export n'est qu'une précaution : la v7.4 ne modifie et ne supprime aucune donnée Notion.

## B. Base de test

Créez d'abord dans Notion une **page de test** (par exemple « Gitnotate – TEST »), hors de la page
source principale, et connectez-y l'intégration de Gitnotate (••• → Connexions). Cette page recevra
les 5 liens de l'étape D. Dans le `.env` du dossier de test, mettez `PARENT_PAGE_ID=<id de la page
de test>`. Choisissez ensuite l'une des deux options ci-dessous. **N'utilisez jamais la base
principale pour les premiers essais.**

### Option B1 : copie de la base principale (recommandée)

Elle vérifie la compatibilité avec votre schéma réel et la reconnaissance des fiches existantes.

1. Ouvrez la base principale en pleine page : ••• → Dupliquer. Puis, sur la copie : ••• →
   Déplacer vers → page de test, et renommez-la clairement (« Ressources GitHub – TEST »).
2. Vérifiez sur la copie (••• → Connexions) que l'intégration y a accès.
3. Recopiez l'ID de la copie (les 32 caractères de son URL, avant `?v=`) dans `DATABASE_ID` du
   `.env` de test. Laissez `CREATE_DATABASE=false`.
4. Facultatif, pour tester les colonnes facultatives : ajoutez à la main à la **copie** les colonnes
   `Licence` (Sélection), `Catégorie` (Sélection) et `Brique pour` (Sélection multiple). Créez
   volontairement des options incomplètes : par exemple `MIT`, `Apache-2.0`, « Non renseignée » et
   « Non vérifiée » pour `Licence` ; quelques catégories pour `Catégorie` ; les noms des 4 projets du
   profil pour `Brique pour`. Vous verrez ainsi le signalement des options manquantes en fin de run.
   En type Texte, ces colonnes ne demandent aucune option.

### Option B2 : nouvelle base créée par Gitnotate

Elle vérifie la création d'une base complète (colonnes facultatives comprises), sans vos fiches.

1. Dans le `.env` de test : `DATABASE_ID=` (vide) et `CREATE_DATABASE=true`.
2. Lancez `python gitnotate.py` **sans** `--dry-run` (une simulation ne crée jamais de base). Le
   script crée « Ressources GitHub » dans la page de test, affiche son ID, l'écrit dans le
   `.gitnotate_state.json` du dossier de test, puis s'arrête (code 0) sans rien importer.
3. Recopiez l'ID dans `DATABASE_ID`, puis remettez `CREATE_DATABASE=false`.
4. Contrôle : la nouvelle base contient `Justification`, `Licence` (Texte), `Catégorie` (Sélection,
   avec les catégories du profil comme options) et `Brique pour` (Texte).

## C. Clés LLM

```powershell
python scripts/check_llm.py
$LASTEXITCODE
```

(Linux : `python scripts/check_llm.py; echo $?`.) Le script lit le `.env` du dossier de test et ne
consomme aucun quota de génération. Attendu : code 0, clés masquées, modèle Mistral présent ;
si `OPENROUTER_API_KEY` est renseignée, le quota gratuit OpenRouter du jour s'affiche. Les étapes D
et E envoient chacune une requête LLM par dépôt nouveau, soit une dizaine en tout ; OpenRouter n'est
sollicité que si Mistral échoue ou répond mal.

## D. Simulation sur 5 dépôts choisis

### D1. Choisir les 5 liens

Sur la page de test, collez 5 liens de dépôts **absents de la base de test** (avec l'option B1, un
dépôt déjà présent serait seulement reconnu « Déjà présent ») :

| # | Cas | Comment le trouver |
|---|-----|--------------------|
| 1 | dépôt sans licence | souvent un petit dépôt personnel ou de démonstration ; à vérifier : `"license": null` |
| 2 | dépôt archivé | recherche GitHub avec le filtre `archived:true` (par exemple `archived:true topic:automation`) ; à vérifier : `"archived": true` |
| 3 | dépôt en Go ou en Rust | outil en ligne de commande, API ou service (filtres `language:Go` ou `language:Rust`) ; à vérifier : `"language"` |
| 4 | dépôt de cours | cours ou tutoriel (filtre `topic:course`, ou dépôts « for beginners ») |
| 5 | liste « awesome » | liste de ressources (filtre `topic:awesome-list`) |
| 6 | dépôt vide (v7.4) | dépôt sans description, sans topics, et sans README ou avec un README réduit à son titre (souvent un dépôt tout juste créé) ; à vérifier : `"description": null`, `"topics": []`, et `https://api.github.com/repos/<propriétaire>/<dépôt>/readme` répond 404 (ou le README ne contient que le nom du dépôt et des badges) |
| 7 | image Docker tierce (v7.4) | dépôt dont le README lance seulement l'image d'un autre projet (par exemple `docker run … postgres` ou `redis`), sans image à son propre nom ; à vérifier dans le README |

Vérifiez les faits de chaque dépôt avant le test, en ouvrant dans le navigateur
`https://api.github.com/repos/<propriétaire>/<dépôt>` (lecture publique, sans jeton). Relevez
`license` (`null`, ou son `spdx_id`), `archived`, `pushed_at`, `language` et `topics`. Vous pouvez
ajouter un lien de plus, celui d'un dépôt déjà présent dans la base : il doit être reconnu « Déjà
présent ».

Les cas 6 et 7 vérifient les règles de la v7.4 ; le cas « dépôt sans brique » (note 8 au plus) se
présente de lui-même dès qu'un dépôt n'est rattaché à aucun projet ni domaine du profil. Avec les 7
liens, remplacez 5 par 7 dans `MAX_NEW_PER_RUN` aux étapes D2 et E, et dans les nombres de fiches
attendus.

### D2. Lancer la simulation

```powershell
$env:MAX_NEW_PER_RUN=5
python gitnotate.py --dry-run --log-level verbose
$LASTEXITCODE
```

(Linux : `MAX_NEW_PER_RUN=5 python gitnotate.py --dry-run --log-level verbose; echo $?`.)

À vérifier dans la console :

- `👤 Profil de pertinence : fichier <dossier de test>\user_profile.json (empreinte …)`, puis
  `• Version du profil : 2026-10-11 — 11 domaine(s), 4 projet(s) dont 2 actif(s)` (avec le profil
  livré), et aucune ligne `⚠️  Profil : …`. Si la source affichée est « profil par défaut (intégré
  au script) », le fichier n'a pas été lu (absent, erreur de syntaxe JSON ou BOM) : corrigez-le
  avant d'aller plus loin.
- `📋 Réutilisation database …` avec l'ID de la base de test, `✅ Schema validé`, puis la ligne
  `• Facultatives:` (colonnes trouvées et leur type), ou la ligne `ℹ️  Colonnes facultatives
  absentes (ignorées, schéma inchangé)`.
- `• Scoring: 🧠 LLM v2 — 5 jugements + maturité et licence calculées` et
  `🔍 MODE DRY-RUN activé (aucune écriture dans Notion)`.
- Pour chaque dépôt : une ligne `🔍 DRY-RUN: <dépôt> (… ⭐ | 🧠 <note>/10)` et, en mode verbose, une
  ligne `🧠 [<dépôt>] Score LLM: U…·P…·T…·I…·C…·M…·L… = <note> — <justification>`. Quand le plafond
  sans brique a joué, cette ligne indique `= 9, plafonnée à 8 (aucune brique du profil)` (ou `= 10, …`).
- Pour le dépôt vide (cas 6) : `🔍 DRY-RUN: <dépôt> (… ⭐ | ∅ non notée) (aucune information)`, et
  aucune ligne `Score LLM` (aucune requête LLM n'est envoyée pour lui).
- Bilan : `Simulées: 5` (moins si un dépôt est reporté ou en erreur), puis les lignes `Pertinence:`
  (avec `non notée ×1` pour le cas 6), `Catégories:` et `Modèles LLM:`. Si des colonnes de
  sélection existent, la liste des valeurs non écrites faute d'option.
- Code de sortie 0. Le code 2 signale une erreur (par exemple un lien en « GitHub HTTP 404 ») : lisez
  la liste des URL en erreur. Un dépôt « reporté » n'a pas reçu de réponse LLM valide ; un report
  isolé n'est pas bloquant (il sera repris), des reports systématiques le sont.
- Dans Notion : le nombre de fiches de la base de test n'a pas changé.

En simulation, la console ne montre pas la licence ni les extraits de chaque dépôt. Ils sont dans le
cache local du dossier de test, lisible avec cette commande (lecture seule) :

```powershell
python -c "import json,os; d=os.environ.get('GITNOTATE_DATA_DIR','.'); c=json.load(open(os.path.join(d,'.gitnotate_cache.json'),encoding='utf-8')); [print(k, v.get('license_state'), v.get('license_spdx'), v.get('archived'), v.get('pushed_at'), (v.get('readme_hints') or {}).get('distribution'), json.dumps(v.get('readme_sections'),ensure_ascii=False)) for k,v in c.items()]"
```

Chaque ligne donne : dépôt, état de la licence (`spdx`, `absente` ou `non_identifiee`), identifiant
SPDX, archivé, date du dernier push, distribution détectée (liste parmi `PyPI`, `npm`, `Docker`),
puis les extraits `installation`, `example` et `prerequisites` (une chaîne vide donnera « Non
vérifié » dans la fiche). La catégorie et `Brique pour` de chaque
dépôt ne se voient qu'après l'import de l'étape E ; la simulation n'en donne que le décompte par
catégorie, dans le bilan.

La dernière entrée de `gitnotate_stats.json` (dossier de test, à ouvrir dans le Bloc-notes) doit
indiquer `"version": "7.4.0"`, `"dry_run": true`, `"profile_version": "2026-10-11"`, ainsi que
`scores_distribution` (une fiche non notée y est comptée sous la clé `"aucun"`), `categories_count`
et `optional_columns`.

### D3. Grille de contrôle

**Contrôles déterministes** : ils doivent être exacts, car le script les calcule à partir des faits
GitHub relevés en D1.

| Fait GitHub | Colonne `Licence` | Lettre L |
|-------------|-------------------|----------|
| `"license": null` | « Non renseignée » | `L0` |
| `spdx_id` présent dans `licences.preferees` (MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, MPL-2.0, Unlicense, 0BSD, Zlib, CC0-1.0) | cet identifiant | `L2` |
| autre `spdx_id` (GPL-3.0, AGPL-3.0, CC-BY-4.0…) | cet identifiant | `L1` |
| `"spdx_id": "NOASSERTION"` | « Non vérifiée » | `L?` (exclu du calcul) |

| Fait GitHub | Lettre M |
|-------------|----------|
| `"archived": true` | `M0`, quelle que soit la date |
| `pushed_at` il y a 365 jours au plus | `M2` |
| `pushed_at` il y a 3 ans au plus | `M1` |
| `pushed_at` plus ancien | `M0` |
| `pushed_at` absent | `M?` (exclu du calcul) |

Règles de la v7.4, déterministes elles aussi :

| Situation | Attendu |
|-----------|---------|
| dépôt vide (cas 6) : ni description, ni topics, ni README exploitable | aucune requête LLM pour ce dépôt ; console `∅ non notée (aucune information)` ; bilan `non notée ×1` ; à l'étape E, fiche créée avec `Pertinence` vide, Justification `[NON NOTÉ] Ni description, ni topics, ni README exploitable : Pertinence laissée vide.`, `Description` et `Cas d'usage` « Non vérifié », ni `Catégorie` ni `Brique pour` |
| `Brique pour` vide (aucun projet ni domaine du profil retenu) | note de 8 au plus ; si la note calculée dépassait 8, la Justification (et la ligne `Score LLM` en verbose) indique `= 9, plafonnée à 8 (aucune brique du profil)` ou `= 10, …` |
| note de 9 ou 10 | la réponse du LLM nommait au moins un projet ou un domaine du profil ; il apparaît dans `Brique pour` si la colonne existe (et, en Sélection multiple, si l'option existe) |
| README qui ne lance qu'une image tierce (cas 7) | pas de `Docker` dans la distribution affichée par la commande de lecture du cache ci-dessus |
| README qui cite une image au nom du dépôt (`ghcr.io/<propriétaire>/<dépôt>`, `docker run <propriétaire>/<dépôt>`, page Docker Hub du dépôt) | `Docker` dans la distribution |

Pour chaque dépôt, vérifiez aussi :

- **Note** : recalculez-en au moins une à la main avec la formule du README (section « Notation »)
  et les lettres affichées ; vous devez retrouver le même entier.
- **Garde-fous** : si U vaut 2 ou 3, `Brique pour` contient au moins un projet actif du profil
  (« Gitnotate » ou « Automatisations n8n » dans le profil livré ; contrôle possible à l'étape E) ;
  si U et P valent 0, la note ne dépasse pas 2 ; sans `Brique pour`, la note est de 8 au plus.
- **Installation, Exemple, Prérequis** : soit « Non vérifié », soit un texte retrouvé **mot pour
  mot** dans le README. Cherchez-le avec Ctrl+F dans la vue « Code » du README sur GitHub (la vue
  rendue masque la syntaxe Markdown). Jamais de commande absente du README.
- **Dernière MAJ** (étape E) : la date de `pushed_at`.

**Contrôles de jugement** : ils doivent être plausibles. Ils dépendent du LLM et peuvent varier
d'un run ou d'un modèle à l'autre.

| Dépôt | Attendu plausible |
|-------|-------------------|
| 1. sans licence | `Licence` « Non renseignée » et `L0` (déterministe) ; le reste selon le dépôt |
| 2. archivé | `M0` (déterministe) ; l'indice « archivé » est transmis au LLM, la justification peut le citer |
| 3. Go ou Rust | `Langage` vaut « Go » ou « Autre » ; aucune pénalité pour le langage : si le dépôt fournit une CLI, une API, une image Docker ou un service, I vaut 1 ou 2 ; la justification ne présente pas le langage comme un défaut |
| 4. cours | `Catégorie` probable « Éducation/Cours » ; I à 0 plausible (rien à intégrer) ; Installation et Exemple souvent « Non vérifié » |
| 5. liste awesome | `Catégorie` probable « Liste/Ressources » ; I à 0 plausible ; Installation, Exemple et Prérequis le plus souvent « Non vérifié » |
| 6. dépôt vide | non noté (déterministe, voir ci-dessus) ; rien d'autre n'est jugé |
| 7. image tierce | la justification ne présente pas le dépôt comme distribué en image Docker |
| tous | `Description` en français, 1 à 2 phrases ; `Cas d'usage` propres au dépôt, ou « Non vérifié » ; `Brique pour` limitée aux noms de projets et de domaines du profil ; `Catégorie` prise dans la liste du profil, ou vide |

## E. Import réel limité, sur la base de test

1. Notez le nombre de fiches de la base de test (option B1 : celui de la base copiée ; option B2 :
   0) et l'heure.
2. Lancez l'import dans la **même fenêtre** (`GITNOTATE_DATA_DIR` toujours défini) :

   ```powershell
   $env:MAX_NEW_PER_RUN=5
   python gitnotate.py --log-level verbose
   $LASTEXITCODE
   ```

   (Linux : `MAX_NEW_PER_RUN=5 python gitnotate.py --log-level verbose; echo $?`.)
3. Contrôles :
   - le nombre de fiches vaut l'ancien nombre plus `Créations` (bilan) ;
   - ouvrez chaque nouvelle fiche et appliquez toute la grille D3 : `Licence`, `Catégorie`,
     `Brique pour`, `Installation`, `Exemple`, `Prérequis`, `Cas d'usage`, `Dernière MAJ`,
     `Statut` « À explorer », et la `Justification` qui commence par
     `[LLM <modèle> · profil 2026-10-11/<empreinte>] U…·L… = <note> —` (ou
     `U…·L… = 9, plafonnée à 8 (aucune brique du profil) —` si le plafond a joué) ;
   - dépôt vide (cas 6) : la fiche existe, Notion a accepté la `Pertinence` vide (cellule vide dans
     la vue), et la Justification est `[NON NOTÉ] Ni description, ni topics, ni README exploitable :
     Pertinence laissée vide.` ;
   - avec des colonnes de sélection : les valeurs sans option sont absentes de la fiche et listées
     en fin de run (`ℹ️  Valeurs non écrites faute d'option dans la base`), et la fiche existe quand
     même ;
   - option B1 : triez la copie par « Dernière modification » (voir F3) ; seules les nouvelles
     fiches ont une heure postérieure au début du run.
4. Relancez la même commande : `Créations: 0`, et les 5 dépôts sont « Déjà présent » (aucun
   doublon).

Les éléments déterministes (licence, M, L, dates, extraits) doivent être identiques à ceux de la
simulation : les données GitHub viennent du même cache (24 h). Les jugements du LLM peuvent varier
légèrement entre D et E.

## F. Bascule sur la base principale

1. **Revenez à la configuration principale** : fermez la fenêtre PowerShell et ouvrez-en une
   nouvelle (ou tapez `Remove-Item Env:GITNOTATE_DATA_DIR` et `Remove-Item Env:MAX_NEW_PER_RUN`).
   Sous Linux : `unset GITNOTATE_DATA_DIR`. Recopiez dans le `user_profile.json` du projet les
   corrections faites sur la copie de test, s'il y en a. Facultatif : ajoutez à la main les colonnes
   facultatives à la base principale, avec les options validées à l'étape E.
2. **Vérifiez les capacités de l'intégration** (page des intégrations Notion) : « Read content » et
   « Insert content » seulement, sans « Update content ». Notion refuse alors toute modification,
   même en cas de bug.
3. **Avant le run** : notez le nombre de fiches de la base principale et l'heure. Pour repérer une
   éventuelle modification, triez une vue par « Dernière modification » (type de propriété « Last
   edited time »), du plus récent au plus ancien. Si la base n'a pas de telle propriété, ajoutez-la
   à la main **avant** de noter l'heure : c'est une propriété calculée par Notion, qui ne change le
   contenu d'aucune fiche, et Gitnotate ignore les colonnes qu'il ne connaît pas. Vous pouvez aussi
   vous en passer et comparer deux exports CSV (point 6).
4. **Simulation sur la base principale**, avec un plafond bas :

   ```powershell
   $env:MAX_NEW_PER_RUN=3
   python gitnotate.py --dry-run
   ```

   Contrôlez que `📋 Réutilisation database …` affiche l'ID de la base principale, que le profil lu
   est celui du projet, et que `Simulées` ne dépasse pas 3.
5. **Premier import réel** : même réglage, sans `--dry-run` (`python gitnotate.py`).
6. **Contrôles** :
   - nombre de fiches après le run = nombre avant + `Créations` ;
   - trié par « Dernière modification », seules les nouvelles fiches ont une heure postérieure au
     début du run ;
   - ouvrez 2 ou 3 anciennes fiches : `Pertinence` et `Justification` sont inchangées (préfixe et
     détail d'origine) ;
   - contrôle complémentaire (facultatif) : exportez de nouveau la base en CSV, puis comparez les
     deux exports. Aucune ligne `<=` ne doit apparaître (une telle ligne signalerait une ancienne
     fiche modifiée ou disparue) ; les lignes `=>` sont les nouvelles fiches.

     ```powershell
     $avant = Import-Csv 'sauvegardes\2026-10-11-avant-v7.4\<fichier>.csv'
     $apres = Import-Csv 'sauvegardes\2026-10-11-apres-v7.4\<fichier>.csv'
     $avant.Count; $apres.Count
     Compare-Object $avant $apres -Property URL, Pertinence, Justification, Description
     ```

7. Augmentez ensuite le plafond par paliers (par exemple `MAX_NEW_PER_RUN=20`), puis remettez
   `MAX_NEW_PER_RUN=0` (sans limite) dans `.env`. Avant de modifier `.env`, fermez la fenêtre ou
   tapez `Remove-Item Env:MAX_NEW_PER_RUN` (sous Linux `unset MAX_NEW_PER_RUN`) : la variable
   `$env:MAX_NEW_PER_RUN=3` du point 4 reste active dans la fenêtre et l'emporte sur `.env`. Pour
   retrouver les fiches de la v7.4, filtrez ou triez sur `Analysé le`.

## G. Critères d'acceptation et retour arrière

La v7.4 est acceptée si **tous** ces critères sont remplis :

1. `python scripts/check_llm.py` renvoie le code 0.
2. Simulation (D) : code 0, ou code 2 seulement pour une erreur identifiée sur un lien ; profil lu
   depuis le bon fichier, version 2026-10-11, aucune ligne `⚠️  Profil` ; aucune écriture dans
   Notion.
3. Import de test (E) : `Créations` égal au nombre de liens nouveaux (5 au plus) ; second run à
   0 création ; tous les contrôles déterministes de la grille D3 sont exacts sur toutes les fiches
   (Licence, M, L, Dernière MAJ, extraits mot pour mot ou « Non vérifié », `Brique pour` limitée au
   profil, garde-fous, au moins une note recalculée à la main) ; règles de la v7.4 exactes : aucune
   fiche sans `Brique pour` au-dessus de 8, fiche du dépôt vide non notée (`Pertinence` vide,
   Justification `[NON NOTÉ] …`), pas de `Docker` pour l'image tierce ; contrôles de jugement
   plausibles, selon vous, sur au moins 4 fiches sur 5 ; aucune commande, compatibilité ou
   fonctionnalité inventée.
4. Base principale (F) : nombre après = nombre avant + `Créations` ; aucune ancienne fiche modifiée ;
   anciennes Justifications intactes.
5. `gitnotate_stats.json` : dernière entrée en version 7.4.0, avec `profile_version`,
   `scores_distribution` (clé `"aucun"` pour une fiche non notée), `categories_count` et
   `optional_columns` cohérents avec le run.
6. Redécouverte (partie H, facultative pour accepter `gitnotate.py`) : critères d'acceptation de la partie H.

Si un critère n'est pas rempli, arrêtez-vous et notez la sortie de la console (les clés n'y
apparaissent jamais en clair) ainsi que la fiche concernée.

**Retour arrière** :

- **Notion** : rien à restaurer, puisque Gitnotate ne modifie ni ne supprime rien. Supprimez à la
  main, si vous le souhaitez, les fiches de test (sélection des lignes → Supprimer : elles vont dans
  la corbeille Notion) et la page ou la base de test. Vérifiez avant de supprimer qu'il s'agit bien
  de la copie (nom « TEST », ID du `.env` de test). Les fiches créées par la v7.4, fiches non notées
  comprises, peuvent rester : la v7.3 les reconnaît comme déjà présentes (par leur URL) et ne les
  modifie pas. Les colonnes facultatives ajoutées à la main peuvent rester.
- **Code** : revenez à la v7.3 avec

  ```powershell
  git checkout e55f0fe -- gitnotate.py
  python gitnotate.py --version
  ```

  `e55f0fe` est le dernier commit en version 7.3.0 ; la commande ne remplace que `gitnotate.py` et
  doit afficher 7.3.0. Pour revenir à la v7.4 : `git checkout HEAD -- gitnotate.py`. Sans git :
  reprenez la copie du dossier v7.3 faite à l'étape A. `redecouverte.py` peut rester en place : il
  ne lit que Notion et sa copie locale (essai hors ligne avec la v7.3.0 : synchronisation depuis une
  capture et recherche). Pour remonter jusqu'à la v7.2 : `git checkout 47a8f4c -- gitnotate.py`
  (« Correctifs minimaux avant le lot 3 », dernier commit en version 7.2.0) ; le profil v2 peut
  rester en place, la v7.2 ne lit que ses 5 listes historiques.
- **Fichiers locaux** : pour la v7.3, rien à supprimer : elle ignore les entrées du cache GitHub
  écrites par la v7.4 (format 5) et relit ces dépôts sur GitHub. Pour la v7.2, supprimez le cache
  GitHub avant son premier run (`Remove-Item .gitnotate_cache.json`, sous Linux
  `rm .gitnotate_cache.json`, dans le dossier de données) : la v7.2 le relirait pendant 24 heures
  sans appeler GitHub, mais ce cache garde un README déjà nettoyé (blocs de code retirés), dont elle
  tirerait une `Installation` moins bonne. Le cache est simplement reconstruit au run suivant. Les
  statistiques écrites par la v7.4 restent lisibles par les versions précédentes. Le dossier de test
  (`..\gitnotate-test`) peut être supprimé après la validation : il contient une copie de vos clés.

## H. Redécouverte (lecture seule)

Cette partie valide `redecouverte.py` sur une base réelle, en lecture seule : la base principale
après la sauvegarde de la partie A, ou une base historique remplie par une ancienne version (H0).
Les recherches se font hors ligne, sans quota. Mode d'emploi détaillé :
[REDECOUVERTE.md](REDECOUVERTE.md).

**Rien ne doit changer dans Notion.** `redecouverte.py` n'envoie que deux sortes d'appels de lecture,
et l'intégration n'a que la capacité « Read content ». De votre côté, ne modifiez rien non plus :
n'ajoutez ni propriété, ni calcul (menu Calculer), ni tri ou filtre enregistré, et ne retirez aucun
filtre d'une vue : ce sont des modifications de la base. Les seules actions permises dans Notion
sont la lecture (ouvrir une fiche, Ctrl+F, exporter en CSV), la connexion de l'intégration au début
et son retrait à la fin ; ces deux dernières ne changent que des droits d'accès, pas le contenu.

### H0. Base historique écrite par la v7.0 ou la v7.1 : ce qu'il faut attendre

Une base remplie par la v7.1 (par exemple plusieurs centaines de fiches créées en un seul run) a été
étudiée hors ligne, par simulation : schéma exact de la v7.1, fiches produites par le vrai code de
la v7.1 avec un contenu fabriqué. Ces essais valident la structure, **pas la qualité de la
recherche**, qui reste à mesurer sur la vraie base. À quoi s'attendre :

- **Schéma** : les 15 colonnes de la v7.1 (`Nom`, `URL`, `Description`, `Cas d'usage`,
  `Installation`, `Exemple`, `Prérequis`, `Justification`, `Stars`, `Pertinence`, `Langage`, `Type`,
  `Statut`, `Dernière MAJ`, `Analysé le`) sont acceptées telles quelles. `etat` liste
  `facultatives absentes : Catégorie, Brique pour, Licence` : c'est normal. Les filtres `--licence`,
  `--categorie` et `--projet` n'ont alors rien à filtrer (0 résultat, sans dire que la colonne
  manque) : ne les utilisez pas sur une telle base. Si `URL` a été supprimée ou renommée, la lecture
  est refusée (code 1).
- **Versions** : presque toutes les fiches doivent être `v7.0/v7.1` (Justification préfixée par
  le LLM). `ancienne` ne doit compter que des fiches sans Justification ou dont la Justification a
  été réécrite à la main. Si la colonne `Justification` a été renommée, toutes les fiches passent en
  `ancienne` et l'avis du LLM est indexé comme une note personnelle : arrêtez-vous (critères d'arrêt).
- **Gabarits ignorés** : les `Cas d'usage`, `Exemple`, `Prérequis` et `Type` de ces fiches sont des
  textes types (« Automatisation de tâches via des agents IA », « pip install <nom> »,
  « Python recent »…) : ils ne sont ni indexés ni cités. Un Cas d'usage réellement rédigé par le LLM
  dans une fiche v7.0/v7.1 est ignoré lui aussi (à compter en H6).
- **Ce qui est cherché** : surtout le `Nom` (et `propriétaire/dépôt`), la `Description` traduite,
  l'extrait d'`Installation` (quand ce n'est pas « See documentation ») et la `Justification` (avis
  du LLM, poids faible : une correspondance dans la seule Justification n'est jamais « forte »),
  plus vos colonnes personnelles (Notes…). `Langage` ne connaît que Python, JavaScript, TypeScript,
  Go et Autre (« Autre » n'est pas indexé).
- **Qualité probablement inférieure aux mesures publiées** (section 10 de REDECOUVERTE.md, corpus
  synthétique) : dans ce corpus, les dépôts attendus dont la fiche la plus récente est v7.0/v7.1 sont
  moins bien retrouvés que ceux des fiches v7.3+ (67 % contre 96 % dans les 10 premiers). Sur une
  transformation « tout v7.1 » du même corpus, les verdicts passent de 33/6/1 à 30/7/3 sur 40
  requêtes, et la négation « OCR sans GPU » devient un échec (deux dépôts qui exigent un GPU en
  « forte » aux rangs 2 et 3). Ces chiffres sont synthétiques et ne prédisent rien sur votre base.
- **Justification centrée sur le profil** : l'avis de la v7.1 juge le dépôt par rapport à votre
  profil et cite souvent ses domaines (éducation, finance, automatisation…). Une recherche d'un seul
  mot du profil (« éducation ») peut donc afficher beaucoup de correspondances partielles dues à la
  seule Justification ; avec plusieurs concepts, elles restent faibles et masquées.
- **Doublons** : plusieurs fiches pour un même dépôt sont possibles (run en parallèle, dépôts
  renommés) ; elles sont regroupées à l'affichage et listées par `etat --doublons`, jamais
  supprimées.
- **Taille et durée** : un index de quelques mégaoctets ; la lecture de 443 fiches demande 1 appel
  `GET` et 5 requêtes de 100 fiches.

### Procédure

1. **Intégration en lecture seule.** Sur <https://www.notion.so/my-integrations>, créez une
   intégration interne (par exemple « Gitnotate lecture »), dans l'espace de travail de la base :
   capacités de contenu **« Read content » seulement** (décochez « Update content » et « Insert
   content »), aucun commentaire, « No user information ». Copiez le jeton (`ntn_…`).
2. **Connexion à la bonne base et compte de référence.** Ouvrez la base **en pleine page**, puis
   ••• → Connexions → ajoutez l'intégration. Dans l'adresse, les 32 caractères hexadécimaux avant
   `?v=` sont l'identifiant de la base ; s'ils diffèrent de votre `DATABASE_ID`, vous êtes sur une
   vue liée : ouvrez la base d'origine. Prenez cet identifiant dans l'adresse, jamais dans le menu
   « Copier l'ID de la source de données » (un tel identifiant donne un 404 trompeur). Avant toute
   synchronisation, notez :
   - le nombre de fiches **N_notion**, sans rien modifier : exportez la base en CSV comme en A1
     (••• → Exporter → « Markdown & CSV » : c'est une lecture), depuis une vue existante sans filtre,
     puis `(Import-Csv '<fichier>.csv').Count` (fichier `…_all.csv` s'il existe). N'ajoutez pas de
     calcul et ne retirez pas de filtre pour compter ;
   - le nombre de fiches de cette base dans la corbeille ;
   - l'heure.
3. **Dossier de données dédié, hors du dépôt**, par exemple `C:\gitnotate-validation`, avec un
   `.env` qui contient **seulement** :

   ```
   NOTION_READONLY_TOKEN=ntn_...
   DATABASE_ID=<les 32 caractères hexadécimaux de la base>
   ```

   Ni `NOTION_TOKEN` (jeton qui peut écrire), ni `PARENT_PAGE_ID`, ni clé LLM. Puis, depuis le
   dossier du projet, dans une nouvelle fenêtre :

   ```powershell
   Remove-Item Env:NOTION_TOKEN, Env:NOTION_READONLY_TOKEN, Env:DATABASE_ID -ErrorAction SilentlyContinue
   $env:GITNOTATE_DATA_DIR = "C:\gitnotate-validation"
   python -c "import sqlite3; sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)'); print('FTS5 OK')"
   ```

   (Linux : `unset NOTION_TOKEN NOTION_READONLY_TOKEN DATABASE_ID;
   export GITNOTATE_DATA_DIR=~/gitnotate-validation`, puis la même commande avec `python3`.) Le
   `.env` ne remplace pas une variable déjà définie dans la fenêtre : d'où le `Remove-Item`.
4. **Première lecture, avec capture** :

   ```powershell
   python redecouverte.py sync --capture
   $LASTEXITCODE
   ```

   (Linux : `python3 redecouverte.py sync --capture; echo $?`.) Attendu :
   - code 0 ;
   - `Base Notion : « <titre> » <8 premiers caractères de DATABASE_ID>… — Notion-Version
     2022-06-28, lecture seule (NOTION_READONLY_TOKEN)` ;
   - `Lecture : <⌈N/100⌉> requêtes, N fiches`, avec N = N_notion (hors corbeille) ;
   - `Versions` : répartition plausible au vu de votre historique (base v7.1 : `v7.0/v7.1` pour
     presque toutes les fiches, voir H0 ; les fiches créées aux étapes E et F comptent dans
     `v7.3+`) ;
   - `Colonnes` : vos colonnes personnelles réelles ;
   - `Anomalies : aucune`, ou quelques-unes à expliquer ;
   - une dernière ligne `Capture : …\exports\capture-notion-AAAAMMJJ-HHMMSS.json`.
5. **État de l'index** : `python redecouverte.py etat --anomalies --doublons`. Contrôlez :
   - la ligne `Colonnes` : `facultatives absentes : Catégorie, Brique pour, Licence` est normal pour
     une base v7.1 ;
   - le nombre de dépôts sur plusieurs fiches (à noter, pour un éventuel tri à la main plus tard) ;
   - 5 anomalies et 5 fiches de versions différentes, vérifiées à la main dans Notion (la version
     annoncée doit correspondre à leur Justification) ;
   - aucune anomalie `jeton_masque` inattendue.
6. **Contrôle du contenu (facultatif, hors ligne).** Ouvrez 10 fiches tirées au hasard et notez :
   combien de `Cas d'usage` ne sont pas des textes types (le moteur les ignore, voir H0) ; combien de
   Justifications citent un domaine de votre profil ; combien de descriptions sont restées en anglais
   ou vides. Un outil de comptage sur la capture, qui n'affiche que des nombres, peut être fourni à
   part avec le rapport de qualification ; il n'est pas dans le dépôt et n'est pas nécessaire.
7. **Requêtes écrites avant toute recherche.** Sans lancer `cherche`, de mémoire ou en parcourant
   Notion, écrivez dans `exports\mes_requetes.json` (format : section 9 de REDECOUVERTE.md, clés
   `propriétaire/dépôt` en minuscules) au moins 12 besoins :
   - au moins 10 avec des dépôts attendus, dont les trois de départ (extraire des données de PDF
     techniques, application FastAPI de traitement documentaire, veille financière), 2 négations
     (« un OCR sans GPU »), 1 requête en anglais et 1 requête d'un seul mot de votre profil
     (« éducation ») ;
   - 2 besoins sans réponse attendue dans la base, marqués `"aucun_fort": true`.

   Pistes d'après les seuls noms des dépôts de la page source (contenu des fiches non lu) : PDF
   techniques → docling, olmocr, PaddleOCR, DeepSeek-OCR, deepseek_ocr_app, tesseract ; FastAPI
   documentaire → docling, document-chat-system, pixeltable ; veille financière → FinRobot,
   Finance-Guru, composer-trade-mcp, Folo, worldmonitor, crawl4ai, gpt-crawler ; supports de cours →
   llm-course, Paper2Slides, frontend-slides ; vidéo → short-video-maker, Wan2.2, LTX-Video,
   Paper2Video. Un jeu de requêtes écrit par quelqu'un d'autre s'ajoute tel quel, avec son protocole
   (§ 9 de REDECOUVERTE.md, « Intégrer un jeu de requêtes externe »). Avant toute mesure, notez
   l'empreinte des jugements :

   ```powershell
   python scripts/evaluer_redecouverte.py exports/mes_requetes.json --empreinte
   ```

   Elle doit rester la même jusqu'à la fin : on ne corrige pas un attendu après avoir vu les
   résultats.
8. **Mesure** :

   ```powershell
   python scripts/evaluer_redecouverte.py exports/mes_requetes.json --details > exports\mesures.txt
   ```

   Relevez P@5 (calculée sur 5), R@5, MRR, intrus@3, `forts` et les lignes `aucun_fort non
   respecté`. Pour chaque attendu manquant, notez la cause : fiche pauvre (seulement un nom et une
   phrase), Cas d'usage ignoré, synonyme absent du lexique, mot rare qui l'emporte sur l'objet du
   besoin, bruit de la Justification, fiche absente de la base. Relisez chaque requête, dépôts hors
   sujet non listés compris.
9. **Extraits mot pour mot** : lancez quelques recherches (`python redecouverte.py cherche "…"`) ;
   pour 10 extraits pris au hasard, vérifiez dans la fiche Notion (lien `Notion` du résultat,
   Ctrl+F) qu'ils y figurent mot pour mot. Le moteur uniformise l'apostrophe typographique (’
   devient '), les espaces insécables et les traits d'union insécables, et retire les caractères de
   contrôle : cherchez de préférence un fragment sans apostrophe ni espace insécable.
10. **Rejeu hors ligne** : supprimez la copie locale puis reconstruisez-la depuis la capture de
    l'étape 4, sans réseau ni jeton (vous pouvez couper le Wi-Fi pour le constater) :

    ```powershell
    Remove-Item -Recurse .gitnotate_index
    python redecouverte.py sync --depuis capture-notion-AAAAMMJJ-HHMMSS.json
    ```

    (dans le dossier de données ; Linux : `rm -r .gitnotate_index`). Relancez deux des recherches de
    l'étape 9 : les résultats sont identiques.
11. **Aucune modification dans Notion**, sans rien ajouter à la base : faites une seconde lecture en
    lecture seule (`python redecouverte.py sync --capture`, jamais `--accepter-baisse`), puis
    comparez hors ligne la date de dernière modification de chaque fiche dans les deux captures
    (champ `modifie_le`, copié de Notion) :

    ```powershell
    python -c "import json,sys; a,b=[{p['page_id']:p['modifie_le'] for p in json.load(open(f,encoding='utf-8'))['pages']} for f in sys.argv[1:3]]; print('fiches', len(a), len(b)); print('modifiees', sorted(k for k in a.keys() & b.keys() if a[k] != b[k])); print('disparues', sorted(a.keys() - b.keys())); print('apparues', sorted(b.keys() - a.keys()))" "$env:GITNOTATE_DATA_DIR\exports\capture-notion-PREMIERE.json" "$env:GITNOTATE_DATA_DIR\exports\capture-notion-SECONDE.json"
    ```

    (remplacez `PREMIERE` et `SECONDE` par la date et l'heure des deux captures ; Linux : `python3`
    et `"$GITNOTATE_DATA_DIR/exports/…"`). Attendu : les mêmes nombres de fiches et trois listes vides, sauf pour les fiches que vous
    auriez modifiées vous-même (seuls des identifiants de pages s'affichent). Autre possibilité :
    comparer deux exports CSV, comme en F6.
12. **Fin** : retirez l'intégration de la base (••• → Connexions), puis supprimez l'intégration sur
    <https://www.notion.so/my-integrations> (son jeton cesse de fonctionner) et le `.env` du dossier
    dédié. La capture et l'index restent dans le dossier dédié : ils contiennent vos fiches.
13. **Retour** : pour un compte rendu, transmettez seulement le bilan de `sync`, le résumé de `etat`,
    `mesures.txt`, l'empreinte des jugements et la liste des échecs avec leur cause, **jamais la
    capture**.

**Critères d'arrêt immédiat** (ne pas contourner, ne pas relancer avec un autre jeton) :

- la ligne `Base Notion` n'affiche pas `(NOTION_READONLY_TOKEN)` ;
- code 1 avec HTTP 400 : base passée à plusieurs sources de données, non lisible avec
  Notion-Version 2022-06-28 ; arrêt tant que le produit n'est pas migré ;
- code 1 avec HTTP 404 : vérifiez une fois la connexion de l'intégration et l'identifiant (étape 2),
  puis arrêtez si l'erreur persiste ;
- code 1 avec 401 ou 403 : corrigez une fois le jeton ou la capacité ;
- code 2 (lecture interrompue : autre base, fiche reçue deux fois, curseur, lecture incomplète, 429
  ou erreurs serveur persistants) : relancez une fois ; si l'erreur se répète, arrêtez ;
- N lu différent de N_notion, sans explication par la corbeille ou des pages archivées ;
- `Versions` d'une base v7.1 : plus de 5 % de fiches `indéterminée` ou `manuelle`, ou plus de 10 %
  d'`ancienne` (les règles de détection ne collent pas aux fiches réelles : à corriger avant toute
  mesure) ;
- une anomalie `jeton_masque` inexpliquée, un extrait introuvable mot pour mot ou une fiche modifiée
  dans Notion sans que vous l'ayez fait.

N'utilisez jamais `--accepter-baisse` pendant cette validation et n'ajoutez jamais `NOTION_TOKEN`
au `.env` dédié.

**Critères d'acceptation** :

- toutes les fiches sont indexées (N = N_notion, étape 4) ;
- aucun extrait inventé (étape 9) ;
- aucune modification dans Notion (étape 11) ;
- P@5 supérieure à 0 (au moins un attendu dans les 5 premiers) pour au moins 80 % des besoins qui
  ont des attendus (8 sur 10), et aucune ligne `aucun_fort non respecté` (étape 8) ;
- empreinte des jugements inchangée entre l'étape 7 et la fin ;
- `python -m pytest` vert.

Les filtres `--licence`, `--categorie` et `--projet` sont exclus de l'évaluation d'une base v7.1 :
ses colonnes n'existent pas.

**Réglages éventuels.** Ne modifiez jamais les jugements (`en_tete`, `acceptables`, `a_exclure`,
`aucun_fort`) d'un jeu de requêtes, ni les empreintes figées des jeux du dépôt, ni un seuil de test
pour faire passer un réglage. Ajustez d'abord le lexique (`redecouverte_lexique.py` : formes,
voisins), puis relancez directement `scripts/evaluer_redecouverte.py` (formes, voisins, mots vides
et déclencheurs ne demandent aucune synchronisation ; une modification des gabarits
`GABARITS_CAS_USAGE_EN` ou `GABARITS_CAS_USAGE_FR`, appliqués à l'indexation, exige
`python redecouverte.py sync`, ou `sync --depuis` la capture de l'étape 4) ; ne touchez aux poids et
aux seuils de `redecouverte.py` qu'en dernier, et seulement si les écarts sont nets. Après un
réglage, `python -m pytest` doit rester vert : un écart sur les tests de référence
(`tests/fixtures/redecouverte/requetes.json`, `test_requetes_reference`,
`test_requetes_nouvelles_seuils`) est une régression à analyser ; annulez le réglage, ou documentez
l'écart sans abaisser de seuil ni retoucher d'attendu. Un nouveau jeu s'ajoute sous un nouveau nom
de jeu (§ 9 de REDECOUVERTE.md). La capture reste dans `exports\` (ignoré par git) et n'entre jamais
dans les tests, car elle contient vos fiches ; seuls des cas anonymisés, recopiés à la main, peuvent
y entrer.

**Retour arrière** : rien à restaurer dans Notion. Supprimez le dossier `.gitnotate_index` (et, si
vous le souhaitez, la capture dans `exports\`) ; `redecouverte.py`, `redecouverte_lexique.py` et
`scripts/evaluer_redecouverte.py` peuvent être supprimés : `gitnotate.py` n'en dépend pas.
