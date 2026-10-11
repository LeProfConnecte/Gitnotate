# Valider la v7.3 avant la mise en production

Cette procédure vérifie la v7.3 sur de vraies données, étape par étape, **sans risque pour la base
principale**. Les premiers essais se font sur une page et une base de test ; la base principale
n'est utilisée qu'à la fin, avec quelques fiches seulement.

Rappels :

- Dans Notion, `gitnotate.py` ne fait que lire (GET, et POST de requête sur la base) et créer (des
  fiches ; une base seulement avec `CREATE_DATABASE=true`). Il ne modifie jamais une fiche, ne
  supprime rien et ne change jamais le schéma d'une base existante : il n'envoie que des options de
  sélection déjà présentes (`Langage`, `Statut`, `Type` et colonnes facultatives) et omet les autres
  valeurs, signalées au démarrage (`⚠️  Colonne '…' sans l'option …`) et en fin de run.
- `--dry-run` appelle GitHub et le LLM (le quota est consommé), mais n'écrit rien dans Notion.
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
   `sauvegardes\2026-10-11-avant-v7.3\`.
2. **Nombre de fiches de la base principale** : notez-le. Dans Notion, en bas d'une colonne de la
   vue tableau (sans filtre), le menu Calculer affiche le décompte de toutes les lignes (« Count
   all » dans l'interface anglaise). Vous pouvez aussi compter les lignes
   du CSV exporté (décompressez d'abord l'archive ; si elle contient un fichier qui se termine par
   `_all.csv`, prenez celui-là) :

   ```powershell
   (Import-Csv 'sauvegardes\2026-10-11-avant-v7.3\<fichier>.csv').Count
   ```

3. **Fichiers locaux** : copiez dans le même dossier `.env`, `user_profile.json`,
   `gitnotate_stats.json` et `.gitnotate_state.json` (s'ils existent). Si vous n'utilisez pas git,
   gardez aussi une copie du dossier du projet en v7.2.

L'export n'est qu'une précaution : la v7.3 ne modifie et ne supprime aucune donnée Notion.

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

Vérifiez les faits de chaque dépôt avant le test, en ouvrant dans le navigateur
`https://api.github.com/repos/<propriétaire>/<dépôt>` (lecture publique, sans jeton). Relevez
`license` (`null`, ou son `spdx_id`), `archived`, `pushed_at`, `language` et `topics`. Vous pouvez
ajouter un 6e lien, celui d'un dépôt déjà présent dans la base : il doit être reconnu « Déjà présent ».

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
  ligne `🧠 [<dépôt>] Score LLM: U…·P…·T…·I…·C…·M…·L… = <note> — <justification>`.
- Bilan : `Simulées: 5` (moins si un dépôt est reporté ou en erreur), puis les lignes `Pertinence:`,
  `Catégories:` et `Modèles LLM:`. Si des colonnes de sélection existent, la liste des valeurs non
  écrites faute d'option.
- Code de sortie 0. Le code 2 signale une erreur (par exemple un lien en « GitHub HTTP 404 ») : lisez
  la liste des URL en erreur. Un dépôt « reporté » n'a pas reçu de réponse LLM valide ; un report
  isolé n'est pas bloquant (il sera repris), des reports systématiques le sont.
- Dans Notion : le nombre de fiches de la base de test n'a pas changé.

En simulation, la console ne montre pas la licence ni les extraits de chaque dépôt. Ils sont dans le
cache local du dossier de test, lisible avec cette commande (lecture seule) :

```powershell
python -c "import json,os; d=os.environ.get('GITNOTATE_DATA_DIR','.'); c=json.load(open(os.path.join(d,'.gitnotate_cache.json'),encoding='utf-8')); [print(k, v.get('license_state'), v.get('license_spdx'), v.get('archived'), v.get('pushed_at'), json.dumps(v.get('readme_sections'),ensure_ascii=False)) for k,v in c.items()]"
```

Chaque ligne donne : dépôt, état de la licence (`spdx`, `absente` ou `non_identifiee`), identifiant
SPDX, archivé, date du dernier push, puis les extraits `installation`, `example` et `prerequisites`
(une chaîne vide donnera « Non vérifié » dans la fiche). La catégorie et `Brique pour` de chaque
dépôt ne se voient qu'après l'import de l'étape E ; la simulation n'en donne que le décompte par
catégorie, dans le bilan.

La dernière entrée de `gitnotate_stats.json` (dossier de test, à ouvrir dans le Bloc-notes) doit
indiquer `"version": "7.3.0"`, `"dry_run": true`, `"profile_version": "2026-10-11"`, ainsi que
`scores_distribution`, `categories_count` et `optional_columns`.

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

Pour chaque dépôt, vérifiez aussi :

- **Note** : recalculez-en au moins une à la main avec la formule du README (section « Notation »)
  et les lettres affichées ; vous devez retrouver le même entier.
- **Garde-fous** : si U vaut 2 ou 3, `Brique pour` contient au moins un projet actif du profil
  (« Gitnotate » ou « Automatisations n8n » dans le profil livré ; contrôle possible à l'étape E) ;
  si U et P valent 0, la note ne dépasse pas 2.
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
     `[LLM <modèle> · profil 2026-10-11/<empreinte>] U…·L… = <note> —` ;
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
   - ouvrez 2 ou 3 anciennes fiches : `Pertinence` et `Justification` sont inchangées (ancien
     préfixe, sans le détail `U·P·T·I·C·M·L`) ;
   - contrôle complémentaire (facultatif) : exportez de nouveau la base en CSV, puis comparez les
     deux exports. Aucune ligne `<=` ne doit apparaître (une telle ligne signalerait une ancienne
     fiche modifiée ou disparue) ; les lignes `=>` sont les nouvelles fiches.

     ```powershell
     $avant = Import-Csv 'sauvegardes\2026-10-11-avant-v7.3\<fichier>.csv'
     $apres = Import-Csv 'sauvegardes\2026-10-11-apres-v7.3\<fichier>.csv'
     $avant.Count; $apres.Count
     Compare-Object $avant $apres -Property URL, Pertinence, Justification, Description
     ```

7. Augmentez ensuite le plafond par paliers (par exemple `MAX_NEW_PER_RUN=20`), puis remettez
   `MAX_NEW_PER_RUN=0` (sans limite) dans `.env`. Avant de modifier `.env`, fermez la fenêtre ou
   tapez `Remove-Item Env:MAX_NEW_PER_RUN` (sous Linux `unset MAX_NEW_PER_RUN`) : la variable
   `$env:MAX_NEW_PER_RUN=3` du point 4 reste active dans la fenêtre et l'emporte sur `.env`. Pour
   retrouver les fiches de la v7.3, filtrez ou triez sur `Analysé le`.

## G. Critères d'acceptation et retour arrière

La v7.3 est acceptée si **tous** ces critères sont remplis :

1. `python scripts/check_llm.py` renvoie le code 0.
2. Simulation (D) : code 0, ou code 2 seulement pour une erreur identifiée sur un lien ; profil lu
   depuis le bon fichier, version 2026-10-11, aucune ligne `⚠️  Profil` ; aucune écriture dans
   Notion.
3. Import de test (E) : `Créations` égal au nombre de liens nouveaux (5 au plus) ; second run à
   0 création ; tous les contrôles déterministes de la grille D3 sont exacts sur toutes les fiches
   (Licence, M, L, Dernière MAJ, extraits mot pour mot ou « Non vérifié », `Brique pour` limitée au
   profil, garde-fous, au moins une note recalculée à la main) ; contrôles de jugement plausibles,
   selon vous, sur au moins 4 fiches sur 5 ; aucune commande, compatibilité ou fonctionnalité
   inventée.
4. Base principale (F) : nombre après = nombre avant + `Créations` ; aucune ancienne fiche modifiée ;
   anciennes Justifications intactes.
5. `gitnotate_stats.json` : dernière entrée en version 7.3.0, avec `profile_version`,
   `scores_distribution`, `categories_count` et `optional_columns` cohérents avec le run.

Si un critère n'est pas rempli, arrêtez-vous et notez la sortie de la console (les clés n'y
apparaissent jamais en clair) ainsi que la fiche concernée.

**Retour arrière** :

- **Notion** : rien à restaurer, puisque Gitnotate ne modifie ni ne supprime rien. Supprimez à la
  main, si vous le souhaitez, les fiches de test (sélection des lignes → Supprimer : elles vont dans
  la corbeille Notion) et la page ou la base de test. Vérifiez avant de supprimer qu'il s'agit bien
  de la copie (nom « TEST », ID du `.env` de test). Les colonnes facultatives ajoutées à la main
  peuvent rester : la v7.2 les ignore.
- **Code** : revenez à la v7.2 avec

  ```powershell
  git checkout 47a8f4c -- gitnotate.py
  python gitnotate.py --version
  ```

  `47a8f4c` (« Correctifs minimaux avant le lot 3 ») est le dernier commit en version 7.2.0 ; la
  commande ne remplace que `gitnotate.py` et doit afficher 7.2.0. Le profil v2 peut rester en
  place : la v7.2 ne lit que ses 5 listes historiques. Pour revenir à la v7.3 :
  `git checkout HEAD -- gitnotate.py`. Sans git : reprenez la copie du dossier v7.2 faite à
  l'étape A.
- **Fichiers locaux** : supprimez le cache GitHub écrit par la v7.3 avant le premier run de la v7.2
  (`Remove-Item .gitnotate_cache.json`, sous Linux `rm .gitnotate_cache.json`, dans le dossier de
  données). La v7.2 le relirait pendant 24 heures sans appeler GitHub, mais ce cache garde un README
  déjà nettoyé (blocs de code retirés) : la v7.2 en tirerait une `Installation` moins bonne. Le
  cache est simplement reconstruit au run suivant. Les statistiques écrites par la v7.3 restent
  lisibles par la v7.2. Le dossier de test (`..\gitnotate-test`) peut être supprimé après la
  validation : il contient une copie de vos clés.
