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
| H | redécouverte : copie locale et recherches sur la base principale | non (lecture seule) |

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
   all » dans l'interface anglaise). Vous pouvez aussi compter les lignes
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
6. Redécouverte (partie H, facultative pour accepter `gitnotate.py`) : critères de l'étape H9.

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

Cette partie valide `redecouverte.py` sur la **base principale**, en lecture seule, après la
sauvegarde de la partie A. Rien n'est écrit dans Notion ; les recherches se font hors ligne, sans
quota. Mode d'emploi détaillé : [REDECOUVERTE.md](REDECOUVERTE.md).

1. **Intégration en lecture seule** : créez-la avec la seule capacité « Read content », connectez-la
   à la base principale (••• → Connexions) et écrivez `NOTION_READONLY_TOKEN=<jeton>` dans le `.env`
   principal (configuration principale : nouvelle fenêtre, ou `Remove-Item Env:GITNOTATE_DATA_DIR`).
   Vérifiez FTS5 avec la commande de la section 2 de REDECOUVERTE.md.
2. **Première synchronisation, avec capture** :

   ```powershell
   python redecouverte.py sync --capture
   $LASTEXITCODE
   ```

   (Linux : `python redecouverte.py sync --capture; echo $?`.) Attendu : code 0 ; la ligne
   `Base Notion` affiche le titre de la base principale, les 8 premiers caractères de son
   `DATABASE_ID` et `(NOTION_READONLY_TOKEN)` ; le nombre de fiches de la ligne `Lecture` égale le
   nombre de lignes de la base noté en A2 (plus les fiches créées depuis), hors corbeille ; une ligne
   `Capture : …\exports\capture-notion-AAAAMMJJ-HHMMSS.json` termine le bilan.
3. **État de l'index** : `python redecouverte.py etat --anomalies --doublons`. Contrôlez :
   - la ligne `Versions` : répartition plausible au vu de votre historique (les fiches créées aux
     étapes E et F comptent dans `v7.3+`) ; ouvrez 5 fiches de versions différentes (liens de
     `--doublons`, ou `--details` d'une recherche) et vérifiez que la version annoncée correspond à
     leur Justification ;
   - le nombre de dépôts sur plusieurs fiches (à noter, pour un éventuel tri à la main dans Notion) ;
   - 5 anomalies vérifiées à la main dans Notion ;
   - aucune anomalie `jeton_masque` inattendue.
4. **Avant toute recherche**, écrivez pour 10 besoins (dont les trois de départ : extraire des
   données de PDF techniques, application FastAPI de traitement documentaire, veille financière) la
   liste des dépôts que vous attendez, de mémoire ou en parcourant Notion, sans lancer `cherche`.
   Pistes d'après les seuls noms des dépôts de la page source (contenu des fiches non lu) : PDF
   techniques → docling, olmocr, PaddleOCR, DeepSeek-OCR, deepseek_ocr_app, tesseract ; FastAPI
   documentaire → docling, document-chat-system, pixeltable ; veille financière → FinRobot,
   Finance-Guru, composer-trade-mcp, Folo, worldmonitor, crawl4ai, gpt-crawler ; supports de cours →
   llm-course, Paper2Slides, frontend-slides ; vidéo → short-video-maker, Wan2.2, LTX-Video,
   Paper2Video.
5. **Mesure** : recopiez ces attentes dans `exports\mes_requetes.json` (format : section 9 de
   REDECOUVERTE.md ; clés `propriétaire/dépôt` en minuscules), puis :

   ```powershell
   python scripts/evaluer_redecouverte.py exports/mes_requetes.json --details
   ```

   Pour chaque attendu manquant, notez la cause : fiche ancienne pauvre (seulement un nom et une
   phrase), synonyme absent du lexique, mot rare qui l'emporte sur l'objet du besoin, fiche absente
   de la base.
6. **Extraits mot pour mot** : lancez quelques recherches (`python redecouverte.py cherche "…"`) ;
   pour 10 extraits pris au hasard, vérifiez dans la fiche Notion (lien `Notion` du résultat,
   Ctrl+F) qu'ils y figurent mot pour mot. Le moteur uniformise l'apostrophe typographique (’
   devient '), les espaces insécables et les traits d'union insécables, et retire les caractères de
   contrôle : cherchez de préférence un fragment sans apostrophe ni espace insécable.
7. **Aucune modification dans Notion** : triez une vue par « Dernière modification » (voir F3) :
   aucune fiche n'a une heure postérieure au début de la synchronisation, à part celles que vous
   auriez modifiées vous-même. Vous pouvez aussi comparer deux exports CSV (F6).
8. **Rejeu hors ligne** : supprimez la copie locale puis reconstruisez-la depuis la capture de
   l'étape 2, sans réseau ni jeton (vous pouvez couper le Wi-Fi pour le constater) :

   ```powershell
   Remove-Item -Recurse .gitnotate_index
   python redecouverte.py sync --depuis capture-notion-AAAAMMJJ-HHMMSS.json
   ```

   (dans le dossier de données ; Linux : `rm -r .gitnotate_index`). Relancez deux des recherches de
   l'étape 6 : les résultats sont identiques.
9. **Critères d'acceptation** : toutes les fiches sont indexées (étape 2) ; aucun extrait inventé
   (étape 6) ; aucune modification dans Notion (étape 7) ; au moins un attendu dans les 5 premiers
   (P@5 supérieur à 0) pour 8 besoins sur 10 (étape 5) ; `python -m pytest` vert.
10. **Réglages éventuels** : ajustez d'abord le lexique (`redecouverte_lexique.py` : formes, voisins),
    puis relancez directement `scripts/evaluer_redecouverte.py` (formes, voisins, mots vides et
    déclencheurs ne demandent aucune synchronisation ; une modification des gabarits
    `GABARITS_CAS_USAGE_EN` ou `GABARITS_CAS_USAGE_FR`, appliqués à l'indexation, exige
    `python redecouverte.py sync`, ou `sync --depuis` la capture de l'étape 2) ; ne touchez aux poids et
    aux seuils de `redecouverte.py` qu'en dernier, et seulement si les écarts sont nets.
    `python -m pytest` doit rester vert, à une exception près : les tests de référence
    (`tests/fixtures/redecouverte/requetes.json`, `test_requetes_reference`) peuvent légitimement
    changer de résultat ; relisez alors chaque écart avant d'adapter l'attendu. La capture
    reste dans `exports\` (ignoré par git) et n'entre jamais dans les tests, car elle contient vos
    fiches ; seuls des cas anonymisés, recopiés à la main, peuvent y entrer.

**Retour arrière** : rien à restaurer dans Notion. Supprimez le dossier `.gitnotate_index` (et, si
vous le souhaitez, la capture dans `exports\`) ; `redecouverte.py`, `redecouverte_lexique.py` et
`scripts/evaluer_redecouverte.py` peuvent être supprimés : `gitnotate.py` n'en dépend pas.
