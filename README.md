# GitNotate

Outil personnel de veille : GitNotate lit les liens GitHub d'une page Notion, récupère pour chaque
dépôt ses métadonnées et son README (API GitHub), demande à un LLM une description française, des
cas d'usage, une catégorie et cinq jugements notés sur des échelles courtes, en déduit une note de
pertinence de 0 à 10 (calcul fait par le script, voir [Notation](#notation)), puis crée une fiche
par dépôt dans une base Notion. Il cherche surtout des dépôts qui pourraient devenir des composants
réutilisables dans vos applications, même sans besoin immédiat. Version 7.4
(`python gitnotate.py --version`). Le moteur `redecouverte.py` retrouve ensuite, hors ligne, les
dépôts déjà enregistrés qui répondent à un besoin (voir
[Retrouver un dépôt déjà enregistré](#retrouver-un-dépôt-déjà-enregistré)).

Avant la première utilisation réelle de la v7.4, suivez [docs/VALIDATION.md](docs/VALIDATION.md)
(essais sur une base de test, sans risque pour la base principale).

## Prérequis

- Python 3.10 ou plus récent (Windows ou Linux).
- Une intégration Notion interne (<https://www.notion.so/my-integrations>) avec les capacités
  « Read content » et « Insert content », **connectée à la page source ET à la base**
  (dans Notion : ••• → Connexions → votre intégration).
- Une base Notion dont les colonnes (nom exact et type) sont vérifiées avant toute écriture :
  `Nom` (Titre), `URL` (URL), `Description`, `Cas d'usage`, `Installation`, `Exemple`, `Prérequis`
  (Texte), `Stars`, `Pertinence` (Nombre), `Langage`, `Statut` (Sélection), `Type` (Sélection
  multiple), `Dernière MAJ`, `Analysé le` (Date) et, facultative, `Justification` (Texte).
  Trois autres colonnes facultatives sont lues depuis la v7.3 : `Licence`, `Catégorie` et
  `Brique pour` (voir [Colonnes facultatives](#colonnes-facultatives)). Une base de la v7.1 ou de
  la v7.2 reste utilisable telle quelle.
- Une clé API Mistral (fournisseur principal). Une clé OpenRouter est facultative (secours).
- Facultatif : un jeton GitHub en lecture seule (sans jeton : 60 requêtes GitHub par heure).
- Pour `redecouverte.py` seulement : SQLite avec le module FTS5 (inclus dans le Python de
  python.org) ; recommandé, une seconde intégration Notion limitée à « Read content »
  (`NOTION_READONLY_TOKEN`, voir [docs/REDECOUVERTE.md](docs/REDECOUVERTE.md)).

## Installation (environnement virtuel)

```powershell
# Windows (PowerShell), dans le dossier du projet
# (si Activate.ps1 est refusé : Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

```bash
# Linux
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
```

**À chaque nouvelle fenêtre de terminal**, placez-vous dans le dossier du projet et réactivez
l'environnement virtuel avant de lancer un script : `.\.venv\Scripts\Activate.ps1` sous Windows
(le préfixe `(.venv)` apparaît alors dans l'invite), `source .venv/bin/activate` sous Linux. Sinon
Python ne trouve pas les dépendances (`ModuleNotFoundError: No module named 'requests'`).

## Configuration

Copiez le modèle en `.env` **dans le dossier du script** (`Copy-Item env.example .env` sous
PowerShell, `cp env.example .env` sous Linux) et renseignez au minimum `NOTION_TOKEN`,
`PARENT_PAGE_ID`, `DATABASE_ID` et `MISTRAL_API_KEY` ; chaque variable y est commentée avec sa valeur
par défaut. Le profil qui sert à noter les dépôts se règle dans `user_profile.json` (ou
`USER_PROFILE_JSON`) : voir [Profil de pertinence](#profil-de-pertinence-user_profilejson). Le
`.env` contient vos secrets : ne le partagez jamais (il est exclu de git).

## Premier lancement

1. `python scripts/check_llm.py` vérifie les clés LLM sans consommer de quota de génération
   (code 0 : au moins une clé, et toutes les clés présentes sont valides ; le modèle Mistral est
   vérifié si `MISTRAL_API_KEY` est renseignée, le modèle OpenRouter si `OPENROUTER_API_KEY` l'est ;
   le quota gratuit OpenRouter est affiché).
2. Pas encore de base ? Avec `CREATE_DATABASE=true`, `python gitnotate.py` crée « Ressources GitHub »
   (avec toutes les colonnes, y compris `Justification` et les trois colonnes facultatives de la
   v7.3) dans la page source, affiche son ID (noté aussi dans `.gitnotate_state.json`)
   et s'arrête sans rien importer. Recopiez l'ID dans `DATABASE_ID` et remettez `CREATE_DATABASE=false`.
3. Simulation limitée à 10 nouvelles fiches : `MAX_NEW_PER_RUN=10` avec `--dry-run`. Écrivez
   `MAX_NEW_PER_RUN=10` dans `.env`, ou bien, pour la seule fenêtre en cours :
   - PowerShell : `$env:MAX_NEW_PER_RUN=10` puis `python gitnotate.py --dry-run` ;
   - Linux : `MAX_NEW_PER_RUN=10 python gitnotate.py --dry-run`.

   Une variable définie dans le terminal prime sur la ligne du `.env`. Au plus 10 dépôts **absents
   de la base** sont simulés : GitHub et le LLM sont appelés (le quota est consommé), mais rien n'est
   écrit dans Notion. N'utilisez pas `--max-repos 10` pour cet essai : `--max-repos` compte aussi les
   dépôts déjà présents dans la base, et ne simulerait rien si les 10 premiers liens de la page y sont
   déjà (cas d'une migration depuis la v7.1). Si aucun lien de la page n'est nouveau, rien n'est
   simulé : ajoutez d'abord un lien neuf à la page pour tester la chaîne LLM.
4. Même réglage sans `--dry-run` (`python gitnotate.py`, ou `MAX_NEW_PER_RUN=10 python gitnotate.py`
   sous Linux) pour un premier import réel limité à 10 fiches.
   Remettez ensuite `MAX_NEW_PER_RUN=0` dans `.env` (sous PowerShell, fermez la fenêtre ou tapez
   `Remove-Item Env:MAX_NEW_PER_RUN`), puis lancez `python gitnotate.py` pour l'import complet.

## Utilisation courante

```text
python gitnotate.py                      import complet
python gitnotate.py --dry-run            simulation, aucune écriture dans Notion
python gitnotate.py --max-repos N        seulement les N premiers dépôts uniques de la page
python gitnotate.py --log-level verbose  détails (quiet = erreurs seulement)
```

Les options priment sur `.env`. Les dépôts déjà présents dans la base sont reconnus, le plus souvent
sans appel GitHub, et ne sont jamais modifiés ; chaque nouvelle fiche reçoit le Statut « À explorer ».
`--max-repos` compte aussi les dépôts déjà présents : pour limiter les **créations** par run,
utilisez `MAX_NEW_PER_RUN`. Le bilan final liste les créations, les dépôts reportés et les URL en
erreur. `gitnotate_stats.json` garde l'historique des 50 derniers runs allés jusqu'au traitement des
dépôts : un run arrêté avant (configuration, aucun fournisseur LLM, base ou page source illisible ou
lue en partie) n'y figure pas ; son code de sortie et sa cause s'affichent seulement dans la console.
Depuis la v7.3, le bilan affiche aussi la répartition des notes (`Pertinence`) et le nombre de fiches
par catégorie, et chaque entrée de `gitnotate_stats.json` contient `profile_version`,
`scores_distribution`, `categories_count` et `optional_columns` (colonnes facultatives trouvées).
Depuis la v7.4, une fiche non notée (voir [Notation](#notation)) s'affiche `∅ non notée (aucune
information)` dans la console et `non notée ×n` dans la ligne `Pertinence:` du bilan ; dans
`scores_distribution`, elle est comptée sous la clé `aucun`.

`SCORE_MIN_THRESHOLD` (0 par défaut, recommandé) écarte, sans fiche, les dépôts dont la note est
inférieure au seuil. Il n'écarte jamais une fiche non notée. Comme un dépôt sans `Brique pour` est
plafonné à 8 (voir [Notation](#notation)), un seuil de 9 ou 10 écarte tous ces dépôts, y compris en
repli lexical.

## Retrouver un dépôt déjà enregistré

`redecouverte.py` cherche, **hors ligne**, parmi les fiches déjà créées dans votre base Notion, les
dépôts qui peuvent répondre à un besoin, même sans projet actif associé. Il ne fait que lire Notion
(deux appels de lecture seulement, vérifiés avant tout envoi) et n'appelle jamais GitHub.

```text
python redecouverte.py sync                                   copie locale des fiches (lecture seule)
python redecouverte.py cherche "extraire des données de PDF"  recherche hors ligne
python redecouverte.py etat                                   état de la copie locale
```

Chaque résultat cite mot pour mot les champs de la fiche qui répondent au besoin, avec leur fiabilité
(README, GitHub, LLM, saisi par vous), la version et la date de la fiche, et signale ce qui est à
vérifier, notamment les champs fabriqués par les premières versions de Gitnotate (jamais pris en
compte par la recherche). Les étoiles, la Pertinence et le Statut n'entrent pas dans le classement.
L'avis d'un LLM est facultatif (`--llm`) et n'envoie rien sans confirmation. La copie locale
(dossier `.gitnotate_index` du dossier de données) est régénérable et ignorée par git ; relancez
`sync` après chaque run de `gitnotate.py`. Mode d'emploi : [docs/REDECOUVERTE.md](docs/REDECOUVERTE.md).

## Profil de pertinence (`user_profile.json`)

Le profil décrit votre contexte, votre matériel, vos domaines et vos projets. Le prompt envoyé au LLM
est construit à partir de lui, et le script s'en sert pour calculer la note. Aucun nom de projet ou
de domaine n'est écrit dans le code : tout vient du profil. Le script cherche le profil dans cet
ordre : la variable `USER_PROFILE_JSON` (objet JSON sur une seule ligne), puis le fichier
`user_profile.json` du dossier de données (dossier du script, ou `GITNOTATE_DATA_DIR`), puis le
profil par défaut intégré au script (format v1).
Au démarrage, il affiche d'où vient le profil, son empreinte, sa version, et le nombre de domaines
et de projets (empreinte fictive dans l'exemple) :

```text
👤 Profil de pertinence : fichier …\user_profile.json (empreinte 1a2b3c)
   • Version du profil : 2026-10-11 — 11 domaine(s), 4 projet(s) dont 2 actif(s)
```

| Clé | Format | Rôle |
|-----|--------|------|
| `languages`, `frameworks`, `infra` | listes de textes | technologies que vous utilisez déjà : le LLM les reçoit comme simple contexte (un autre langage n'est jamais un défaut) ; le score lexical de secours se sert de `frameworks` et `infra` (`languages` n'y sert plus depuis la v7.4) |
| `domains`, `interests` | listes de mots-clés courts (anglais, minuscules) | score lexical de secours ; ils servent de domaines au LLM seulement si `domaines` est absent (profil v1) |
| `profile_version` | texte, par exemple `"2026-10-11"` | version affichée au démarrage et dans la Justification ; `v1` si la clé est absente |
| `contexte` | texte court | qui vous êtes et ce que vous cherchez |
| `environnement` | objet `{materiel, systemes, services, contraintes}`, chacun une liste de textes | sert au critère « compatibilité » |
| `domaines` | liste d'objets `{nom, description}` | vos domaines d'intérêt (critère « potentiel futur ») ; leurs noms peuvent apparaître dans `Brique pour` |
| `projets` | liste d'objets `{nom, statut, description, besoins}`, avec `statut` = `actif` ou `envisagé` | vos projets ; un besoin listé d'un projet actif justifie l'utilité immédiate maximale ; leurs noms peuvent apparaître dans `Brique pour` |
| `exclusions` | liste de textes | sujets écartés : le LLM a pour consigne de mettre alors l'utilité immédiate et le potentiel futur à 0 ; s'il la suit, la note est plafonnée à 2. En repli lexical, seule une exclusion écrite comme un topic GitHub exact (minuscules, chiffres et tirets, par exemple `game-engine`) est appliquée : un dépôt qui porte ce topic voit son score lexical plafonné à 2. Ce n'est pas un filtre du script : la fiche est quand même créée |
| `licences` | objet `{preferees, avec_contraintes}`, identifiants SPDX | critère « licence » (voir [Notation](#notation)) ; `avec_contraintes` est indicatif et n'entre pas encore dans le calcul |
| `ponderations` | objet `{valeur, interet, integration, compatibilite, maturite, licence}`, nombres ≥ 0 | poids des critères ; un poids de 0 retire un critère du calcul |
| `categories` | liste de textes (facultative) | remplace la liste par défaut des catégories proposées au LLM |
| clés commençant par `_` | libre | commentaires : jamais lus, jamais envoyés au LLM |

Liste des catégories par défaut : Agent IA, Assistant de code, MCP/Intégrations, LLM/Inférence,
RAG/Recherche, OCR/Documents, Génération média, Audio/Vidéo, Automatisation/No-code, Web/Frontend,
Backend/API, Données/Analyse, Finance/Trading, Crypto/Web3, DevOps/Self-hosting, BTP/Ingénierie,
Éducation/Cours, Liste/Ressources, Autre.

Le fichier livré (`profile_version` « 2026-10-11 ») contient des points **à vérifier** : la quantité
de VRAM du GPU (8 Go, « à confirmer » dans `environnement.materiel`), les descriptions et besoins des
quatre projets (marqués `_a_valider`), et les exclusions. Il n'exclut que « jeux vidéo et moteurs
de jeu » ; les applications mobiles natives sont seulement suggérées dans `_exclusions_a_valider`,
sans être appliquées. Cette exclusion est une phrase : seul le LLM l'applique, le repli lexical ne
la lit pas (il faudrait ajouter des topics exacts comme `game-engine`).

Le commentaire `_lisez_moi` du fichier livré date de la v7.3 : il indique encore que les 5 listes
historiques, dont `languages`, servent au score lexical de secours. Depuis la v7.4, `languages` n'y
sert plus (voir [Notation](#notation)). Ce commentaire n'est jamais lu par le script ; si vous le
corrigez, l'empreinte du profil change (comme pour toute modification de son contenu).

Un profil sans aucun projet ni domaine affiche au démarrage `⚠️  Profil : ni projet ni domaine :
« Brique pour » restera vide et toute note sera plafonnée à 8`.

**Ajouter un projet** : ajoutez un objet à la liste `projets`, avec une virgule entre deux objets.

```json
{
  "nom": "Nom du projet",
  "statut": "envisagé",
  "description": "ce que fait le projet, en une phrase",
  "besoins": ["besoin concret 1", "besoin concret 2"]
}
```

- `actif` : vous y travaillez. Un dépôt peut alors recevoir l'utilité immédiate 2 ou 3.
  `envisagé` : le projet compte pour le potentiel futur. Tout autre statut donne un avertissement,
  et « envisagé » est retenu.
- Écrivez des besoins courts et concrets : c'est à eux que le LLM compare le dépôt.
- Changez `profile_version` (par exemple pour la date du jour) : vous reconnaîtrez ainsi les fiches
  notées avec ce profil. L'empreinte change de toute façon.
- Si la colonne `Brique pour` est une Sélection multiple, créez dans Notion une option qui porte le
  même nom. Sinon, la valeur est omise et signalée en fin de run.
- Évitez les virgules dans les noms et les noms de plus de 100 caractères : Notion les refuse dans
  une option (un avertissement `⚠️  Profil` s'affiche au démarrage, et la fin de run indique que la
  valeur ne peut pas devenir une option), et la version texte de `Brique pour` sépare les noms par
  « , ». Il en va de même pour les catégories ; `CREATE_DATABASE` ne crée que des options valides,
  sans doublon.

**Ajouter un domaine** : ajoutez `{"nom": "Nom du domaine", "description": "mots-clés qui le
décrivent"}` à la liste `domaines`. Les mêmes règles s'appliquent pour l'option `Brique pour` et les
virgules. Pour que le score lexical de secours le reconnaisse aussi, ajoutez un mot-clé anglais à
`domains` ou `interests`.

**Profil v1 et erreurs** :

- Un profil v1 (seulement les 5 listes historiques) reste accepté. Les domaines sont alors
  `domains` + `interests`, il n'y a aucun projet (l'utilité immédiate ne dépasse donc pas 1), les
  pondérations, licences et catégories sont celles par défaut, et la version vaut « v1 ».
- Une clé du mauvais type (par exemple `projets` qui n'est pas une liste, ou un poids négatif)
  affiche au démarrage une ligne `⚠️  Profil : …` ; seule cette clé prend sa valeur par défaut, et
  le run continue.
- Une erreur de syntaxe JSON (virgule oubliée), ou un fichier enregistré « UTF-8 avec BOM », fait
  ignorer **tout** le fichier : un avertissement `[load_user_profile/file]` s'affiche, et le profil
  par défaut intégré est utilisé (la ligne de démarrage indique « profil par défaut (intégré au
  script) »). Enregistrez le fichier en UTF-8 sans BOM (Bloc-notes : « UTF-8 »).
- Tout changement de contenu du profil (valeurs, clés, commentaires `_`) change l'empreinte ; la
  mise en forme seule (indentation, ordre des clés) ne la change pas. Les fiches déjà créées ne
  sont ni modifiées ni recalculées.

## Notation

La note `Pertinence` (entier de 0 à 10) combine sept critères. Le langage n'en fait jamais partie.

| Lettre | Critère | Échelle | Évalué par | Repères |
|--------|---------|---------|------------|---------|
| U | utilité immédiate | 0-3 | LLM | 3 = répond à un besoin listé d'un projet actif ; 2 = utile à un projet actif, hors besoins listés ; 1 = lien faible ; 0 = aucun |
| P | potentiel futur | 0-3 | LLM | 3 = composant plausible pour un domaine ou un projet envisagé, même sans besoin immédiat ; 2 = utile à un domaine ; 1 = lien faible ; 0 = hors profil ou exclusion |
| T | intérêt | 0-2 | LLM | intérêt technique ou fonctionnel (2 = fort, 1 = moyen, 0 = faible) |
| I | intégration | 0-2 | LLM | 2 = intégrable tel quel (bibliothèque, API, CLI, image Docker, service auto-hébergeable, plugin) ; 1 = avec effort ; 0 = rien à intégrer (cours, liste, article) |
| C | compatibilité | 0-2 | LLM | avec votre environnement, d'après les seuls faits du dépôt ; 0 seulement pour une incompatibilité prouvée (par exemple un GPU de 24 Go exigé) |
| M | maturité | 0-2 | script | archivé : 0 ; dernier push (`pushed_at`) il y a 365 jours au plus : 2 ; 3 ans au plus : 1 ; plus ancien : 0 ; date absente : `?` |
| L | licence | 0-2 | script | identifiant SPDX présent dans `licences.preferees` : 2 ; autre identifiant SPDX reconnu : 1 ; aucune licence : 0 ; licence non identifiée par GitHub (NOASSERTION) ou donnée absente : `?` |

```text
Pertinence = arrondi( 10 × Σ poids × (note / maximum) / Σ poids )
composante « valeur » = max(U, P) / 3   (un dépôt n'est pas pénalisé faute de besoin immédiat)
```

La somme porte sur six composantes : valeur, T, I, C, M et L. Une composante `?` (non vérifiée)
est retirée du numérateur **et** du dénominateur : elle n'apporte ni bonus ni pénalité. Le calcul
se fait en fractions exactes, avec arrondi au demi supérieur (6,5 donne 7). Poids par défaut :
valeur 4, intérêt 1, intégration 2, compatibilité 1, maturité 1, licence 1 (clé `ponderations` du
profil). Exemple avec ces poids : `U0·P2·T1·I1·C2·M?·L?` donne
10 × (4×2/3 + 1×1/2 + 2×1/2 + 1×2/2) / (4+1+2+1) = 10 × 5,167 / 8 = 6,46, soit une note de 6
(M et L, inconnus, sont retirés des deux côtés). Avec les sept lettres connues,
`U2·P3·T1·I2·C2·M2·L2` donne 10 × 9,5 / 10 = 9,5, soit 10.

Garde-fous appliqués par le script :

- U vaut 2 ou plus seulement si `Brique pour` nomme au moins un projet **actif** du profil ; sinon,
  U est ramené à 1 avant le calcul (la Justification affiche la valeur corrigée). Un nom suivi du
  statut recopié du prompt (« Gitnotate (actif) ») est reconnu, et si le LLM cite plus de 3 noms, les
  projets actifs sont gardés en premier.
- Valeur nulle (U = P = 0) : la note ne dépasse pas 2.
- **Plafond sans rattachement (v7.4)** : une note de 9 ou 10 exige que `Brique pour` nomme au moins
  un projet ou un domaine du profil, après validation de la réponse (les noms absents du profil sont
  retirés). Sinon, la note est ramenée à 8, sur toutes les voies : réponse du LLM, repli lexical
  (qui n'établit jamais de brique, donc jamais plus de 8), réponse partielle avec
  `REQUIRE_LLM=false` et traduction seule. Quand le plafond change la note, la Justification garde
  la note calculée : `U0·P3·T2·I2·C2·M2·L2 = 10, plafonnée à 8 (aucune brique du profil) — …`
  (repli lexical : `[LEXICAL · profil …] Note 10, plafonnée à 8 (aucune brique du profil).`). Seule
  compte la réponse validée, jamais le schéma de la base : sans colonne `Brique pour` (ou sans
  l'option voulue), une note de 9 ou 10 reste possible, mais la brique n'apparaît pas dans la fiche.
- La note reste entre 0 et 10. Les poids viennent du profil (nombres ≥ 0) ; si les poids des
  critères présents ont une somme nulle, les poids par défaut sont utilisés.

**Stabilité** : les mêmes jugements donnent toujours la même note (le calcul n'a aucune part de
hasard). Les jugements eux-mêmes viennent du LLM (température 0,1) et peuvent varier d'un modèle à
l'autre, d'autant que `openrouter/free` tire un modèle au hasard. Le détail `U·P·T·I·C·M·L` écrit
dans la Justification montre d'où vient chaque note.

**Neutralité du langage** : le prompt précise qu'un autre langage ou un autre framework n'est jamais
un défaut. Un dépôt en Go, Rust, Java ou C++ utilisable par une CLI, une API, une image Docker ou
comme service est intégrable. Le langage n'entre pas dans le calcul, et la colonne `Langage` reste
une simple information. Depuis la v7.4, le score lexical de secours est lui aussi neutre : le
langage n'y donne ni bonus ni pénalité, et il n'applique plus aucune pénalité codée en dur (jeu,
mobile, blockchain). Sa seule pénalité vient du profil : un topic GitHub égal à une exclusion écrite
comme un topic exact (`game-engine`) plafonne le score lexical à 2 (comparaison exacte : `game-theory`
n'est pas `game`).

**« Non vérifié »** : une information que ni les métadonnées GitHub ni le README ne prouvent est
écrite « Non vérifié » (« Non vérifiée » pour la licence), jamais devinée. Une maturité ou une
licence inconnue est notée `?` et sort du calcul.

**Dépôt sans information : fiche non notée (v7.4)**. Un dépôt sans description, sans topics et sans
README exploitable n'est pas envoyé au LLM et ne reçoit aucune note : une note, une catégorie ou une
description seraient devinées d'après le seul nom. Un README est exploitable si, une fois nettoyé
(balises, images, badges et liens retirés), il contient au moins une ligne avec une lettre ou un
chiffre autre qu'un titre égal au nom du dépôt : pour le dépôt `moi/mon-outil`, un README réduit au
titre `# mon-outil` (ou `# moi/mon-outil`) et à des badges ne l'est pas. Avec `README_LLM_CHARS=0`,
le README n'est pas envoyé au LLM et compte comme absent. La fiche est quand même créée (elle n'est
jamais reportée par le mode reprise, ni écartée par `SCORE_MIN_THRESHOLD`) avec les faits GitHub
(nom, URL, étoiles, licence, dates, extraits du README s'il y en a), `Pertinence` vide,
`Description` et `Cas d'usage` « Non vérifié », ni `Catégorie` ni `Brique pour`, et la Justification
`[NON NOTÉ] Ni description, ni topics, ni README exploitable : Pertinence laissée vide.` (si la base
a la colonne `Justification`) ; avec `README_LLM_CHARS=0` et un README exploitable :
`[NON NOTÉ] Ni description, ni topics ; README non transmis au LLM (README_LLM_CHARS=0) : Pertinence
laissée vide.`. Un README **illisible** (erreur 5xx, délai dépassé, quota GitHub épuisé, contenu
illisible) n'est jamais pris pour un README absent : pour un dépôt sans description ni topics, aucune
fiche n'est créée, l'erreur `README illisible` est comptée (code de sortie 2) et le dépôt est repris
au run suivant ; ce résultat n'est pas mis en cache.

**Repli lexical** : dans trois cas, la note est un score lexical de 0 à 10, calculé localement à
partir des mots-clés du profil : `REQUIRE_LLM=false` sans réponse LLM valide,
`LLM_SCORING_ENABLED=false`, ou `TRANSLATION_ENABLED=false`. La Justification commence alors par
`[LEXICAL · profil …]`, et ni `Catégorie` ni `Brique pour` ne sont écrites. Sans brique, ce score ne
dépasse jamais 8 (voir le plafond ci-dessus).

Les notes de la v7.3 et de la v7.4 suivent la même grille à 7 critères ; la v7.3 n'appliquait pas
encore le plafond de 8 sans `Brique pour`. Elles ne se comparent pas à celles des versions
précédentes, qui suivaient une autre grille. Le préfixe de la Justification permet de distinguer les
fiches ; l'empreinte du profil intègre les règles de notation, si bien qu'un même profil donne une
empreinte différente en v7.3 et en v7.4.

## Contenu des fiches

| Colonne | Valeur écrite (v7.4) |
|---------|----------------------|
| `Nom`, `URL`, `Stars` | nom, adresse et étoiles du dépôt (GitHub) |
| `Description` | description française du LLM (1 à 2 phrases demandées) ; sans LLM, description GitHub d'origine, ou « Non vérifié » si le dépôt n'en a pas ; « Non vérifié » pour une fiche non notée |
| `Cas d'usage` | une puce « • » par cas d'usage du LLM (0 à 3, 200 caractères au plus chacun ; le prompt exige des usages propres au dépôt, tirés de sa description ou de son README) ; « Non vérifié » si la liste est vide, en traduction seule (`LLM_SCORING_ENABLED=false`) ou sans LLM. Plus aucune liste générique |
| `Installation` | extrait mot pour mot du README : premier bloc de code d'une section installation, install, getting started, quick start, setup, démarrage ou mise en route |
| `Exemple` | extrait mot pour mot du README : premier bloc de code d'une section usage, example(s), exemple(s), utilisation ou how to use |
| `Prérequis` | extrait mot pour mot du README : premières lignes de liste d'une section requirements, prerequisites, prérequis, dependencies ou dépendances, sinon son premier bloc de code |
| `Pertinence` | note de 0 à 10 (voir [Notation](#notation)) ; 8 au plus sans `Brique pour` ; vide pour une fiche non notée (dépôt sans description, sans topics et sans README exploitable) |
| `Langage` | Python, JavaScript, TypeScript, Go ou Autre (simple information) |
| `Type` | Agent IA, ML/AI ou Web, seulement d'après des topics GitHub exacts (`agent`, `agents`, `ai-agent`, `ai-agents` ; `machine-learning`, `ai` ; `web`, `frontend`) ; vide sinon |
| `Statut` | « À explorer » |
| `Dernière MAJ` | date du dernier push (`pushed_at`), à défaut `updated_at` |
| `Analysé le` | date du run |
| `Justification` | `[LLM <modèle réellement servi> · profil <version>/<empreinte>] U2·P3·T1·I2·C2·M2·L2 = 10 — <justification>` (faits tirés du dépôt ; 40 mots demandés au LLM, 400 caractères gardés au plus) ; `M?` ou `L?` si la donnée manque ; quand le plafond sans brique change la note : `… = 10, plafonnée à 8 (aucune brique du profil) — <justification>` ; `[LEXICAL · profil <version>/<empreinte>]` en repli lexical, suivi de `Note 10, plafonnée à 8 (aucune brique du profil).` si le plafond a joué ; `[NON NOTÉ] Ni description, ni topics, ni README exploitable : Pertinence laissée vide.` pour une fiche non notée (variante « README non transmis au LLM (README_LLM_CHARS=0) » quand ce réglage a écarté un README exploitable) ; 800 caractères au plus en tout |
| `Licence`, `Catégorie`, `Brique pour` | colonnes facultatives, voir ci-dessous |

`Langage`, `Type` et `Statut` ne reçoivent que des options **déjà présentes** dans la base (celles
d'une base v7.1 : Python, JavaScript, TypeScript, Go, Autre ; Agent IA, ML/AI, Web ; À explorer). La
comparaison ignore les accents et la casse, et le nom exact de l'option existante est envoyé. Si
vous avez renommé ou supprimé une de ces options, une ligne `⚠️  Colonne '…' sans l'option …`
s'affiche au démarrage, la valeur est omise (colonne laissée vide pour `Langage` ou `Statut`), la
fiche est créée quand même, et la valeur figure en fin de run dans `ℹ️  Valeurs non écrites faute
d'option dans la base`. Gitnotate ne crée jamais d'option.

Le LLM indique aussi un type de réutilisation (bibliothèque, service, CLI, API, plugin, modèle,
cours, liste…). Le script le valide, mais la v7.3 ne l'écrit ni dans la fiche ni dans les
statistiques.

Pour `Installation`, `Exemple` et `Prérequis`, le README est lu **en entier**, avant toute
troncature. Les titres sont comparés sans tenir compte des accents ni de la casse, par mots entiers ;
les titres Markdown `#`, les titres soulignés (`===`, `---`) et les titres HTML `<h1>` à `<h6>` sont
reconnus. Une section comprend ses sous-sections. Le script retient, dans l'ordre du README, la
première section qui correspond et qui contient un extrait utilisable (bloc de code, ou liste pour
Prérequis). Le texte placé dans un commentaire HTML `<!-- … -->` est ignoré.
L'extrait fait au plus 5 lignes et 300 caractères (coupé en fin de ligne quand c'est possible), et il est toujours
recopié tel quel : le script vérifie qu'il figure mot pour mot dans le README. Quand il est coupé,
ses dernières lignes inachevées (commande continuée par `\`, `` ` `` ou `^`, ligne finissant par
`|`, `&&` ou `:`, commentaire seul) sont retirées ; s'il ne reste rien, « Non vérifié » est écrit
plutôt qu'une commande incomplète. Une liste de prérequis aérée (lignes vides entre les éléments)
est lue comme une seule liste. Sinon, la colonne reçoit « Non vérifié » : pas de section, section sans bloc de code (pour Installation et Exemple),
ou README absent. Rien n'est plus déduit du langage : fini les « pip install <nom> », « <langage>
recent » et « See documentation ».

## Colonnes facultatives

Si votre base contient ces colonnes (nom exact, accents et majuscules compris), Gitnotate les
remplit. Sinon, il les ignore : une ligne `ℹ️  Colonnes facultatives absentes (ignorées, schéma
inchangé)` s'affiche au démarrage, puis la ligne `• Facultatives:` liste celles qu'il a trouvées,
avec leur type.

| Colonne | Types acceptés | Valeur écrite |
|---------|----------------|---------------|
| `Licence` | Texte ou Sélection | identifiant SPDX donné par GitHub (`license.spdx_id`, par exemple `MIT`, `Apache-2.0`, `GPL-3.0`) ; « Non renseignée » si le dépôt n'a pas de licence ; « Non vérifiée » si GitHub ne l'identifie pas (NOASSERTION) ou si la donnée manque |
| `Catégorie` | Sélection ou Texte | catégorie choisie par le LLM dans la liste du profil (ou la liste par défaut) ; rien si la catégorie est inconnue ou en repli lexical |
| `Brique pour` | Sélection multiple ou Texte | 0 à 3 noms de projets ou de domaines **du profil** (les autres noms proposés par le LLM sont retirés) ; en Texte, noms séparés par « , » ; rien si la liste est vide. Le plafond de 8 dépend des noms validés, pas de cette colonne (voir [Notation](#notation)) |

- **Créez ces colonnes vous-même dans Notion si vous les voulez** : Gitnotate ne modifie jamais le
  schéma d'une base existante. Une colonne d'un autre type (par exemple `Licence` en Sélection
  multiple) donne un avertissement au démarrage et reste ignorée.
- **Sélection et Sélection multiple : créez les options à la main.** Gitnotate n'envoie que des
  options déjà présentes dans la base (comparaison sans accents ni casse ; il envoie le nom exact de
  l'option existante). Une valeur sans option est omise, et la fiche est créée quand même. En fin de
  run, une ligne `ℹ️  Valeurs non écrites faute d'option dans la base` liste ces valeurs
  (« ajoutez l'option … dans Notion »). Options utiles : pour `Licence`, les identifiants SPDX que
  vous attendez, plus « Non renseignée » et « Non vérifiée » ; pour `Catégorie`, les catégories du
  profil ; pour `Brique pour`, les noms des projets et des domaines du profil.
- **Les fiches déjà créées ne sont jamais complétées ni recalculées** : aucune fiche n'est
  modifiée, même après l'ajout d'une colonne ou d'une option. Seules les nouvelles fiches en
  profitent.
- Une base créée par `CREATE_DATABASE=true` (nouvelle base uniquement) reçoit d'emblée ces trois
  colonnes : `Licence` et `Brique pour` en Texte, `Catégorie` en Sélection, avec les catégories du
  profil comme options.

## Codes de sortie

| Code | `gitnotate.py` | `clean_page_duplicates.py` | `scripts/check_llm.py` | `redecouverte.py` |
|------|----------------|----------------------------|------------------------|-------------------|
| 0 | succès, même avec des dépôts reportés | terminé sans problème | clés utilisables | terminé, même sans résultat (et avis LLM annulé, ou non demandé hors terminal sans `--oui`) |
| 1 | configuration (option invalide, page source introuvable…) ou erreur fatale, aucune fiche créée | configuration, page ou journal introuvable | aucune clé, clé refusée, modèle absent, réseau | configuration (jeton, `DATABASE_ID`, base refusée ou introuvable), commande ou option invalide, recherche sans mot significatif, capture introuvable ou illisible, index absent ou illisible, FTS5 absent |
| 2 | au moins une erreur, ou lecture partielle | abandon, lecture partielle ou échec | — | lecture Notion incomplète ou interrompue, baisse brutale refusée, autre synchronisation en cours, index ouvert par un autre programme (dans tous ces cas, l'ancien index est conservé) ; capture ou fichier `--sortie` non écrit ; avis LLM demandé impossible ou réponse inexploitable |
| 130 | interruption (Ctrl-C) | — | — | interruption (Ctrl-C) ; pendant `sync`, l'ancien index est conservé tant que le nouveau ne l'a pas remplacé |

## Sûreté des données

- **`gitnotate.py` ne fait qu'ajouter des fiches** : il ne modifie ni ne supprime jamais rien dans
  Notion. Avec une intégration limitée à Read + Insert, Notion refuserait d'ailleurs toute modification.
- **`redecouverte.py` ne fait que lire** : seuls `GET /v1/databases/{id}` et
  `POST /v1/databases/{id}/query` sont autorisés, vérifiés par une liste blanche avant tout envoi ;
  tout autre appel est bloqué avant le réseau. Il n'écrit que sa copie locale (remplacée d'un bloc,
  l'ancienne est conservée à la moindre erreur) et, sur demande, une capture ou un fichier de
  résultats dans `exports/`. Aucun jeton n'y est écrit ; les colonnes personne, e-mail, téléphone et
  fichiers ne sont jamais conservées.
- **Aucune modification de schéma ni recalcul** : le schéma d'une base existante n'est jamais
  modifié (les colonnes facultatives ne servent que si vous les avez créées, et aucune option de
  sélection n'est créée : `Langage`, `Statut`, `Type` et les colonnes facultatives de sélection ne
  reçoivent que des options déjà présentes dans la base, les autres valeurs sont omises). Les
  fiches existantes ne sont jamais recalculées ni complétées, même quand le profil ou la grille de
  notation change.
- **Aucune base créée implicitement** : `DATABASE_ID` vide ou illisible → arrêt (code 1) avec le code
  HTTP et une piste. `CREATE_DATABASE=true` ne crée qu'une base, jamais en simulation ; une seconde
  création est refusée tant que `.gitnotate_state.json` garde l'ID.
- **Lecture complète ou rien** : si la base ou la page source n'est lue qu'en partie, le run s'arrête
  sans créer de fiche (code 2). Seule exception : un sous-bloc de la page source dont Notion refuse
  durablement le contenu (HTTP 400/403/404, par exemple une copie synchronisée d'une page non partagée
  avec l'intégration) est ignoré avec un avertissement (type et identifiant du bloc) ; les autres liens
  sont traités, `extracted_urls_unique.txt` n'est pas réécrit et le run se termine en code 2.
- **Pas de doublon après une erreur réseau** : une création restée sans réponse (timeout) ou en
  erreur serveur (5xx) n'est jamais renvoyée ; pendant le reste du run, un autre lien vers le même
  dépôt (dépôt renommé ou transféré) n'est pas recréé non plus. Vérifiez dans Notion : si la fiche
  n'existe pas, le dépôt sera repris au run suivant.
- **Le nettoyeur `clean_page_duplicates.py` ne touche que la page source** : il met à la corbeille
  Notion les blocs lien (signet, aperçu, intégration) qui répètent un lien GitHub déjà présent.
  Il simule par défaut ; `--apply` exige de taper exactement « SUPPRIMER n » et il abandonne sans rien
  supprimer au-delà de `CLEANER_MAX_DELETE` suppressions (50). Un journal est écrit dans `journal/`
  **avant** chaque suppression : `--restore <journal>` montre ce qui serait restauré, et
  `--restore <journal> --apply` le remet en place (phrase « RESTAURER n »). Donnez-lui sa propre
  intégration (`NOTION_CLEANER_TOKEN`, capacités Read + Update content).
- **Limites connues** : deux runs lancés en même temps (double lancement, tâche planifiée qui
  chevauche un run manuel) peuvent créer chacun la fiche d'un même dépôt : lancez un seul run à la
  fois. Un dépôt importé sous son ancien nom, puis ajouté à la page sous son nouveau nom, reçoit une
  seconde fiche (la base ne garde pas l'identifiant GitHub du dépôt). Ces doublons se suppriment à la
  main dans Notion.
- **Triez sans supprimer** : pour écarter un dépôt, ajoutez une option « Écarté » à la colonne
  `Statut` (gardez le type Sélection) plutôt que de supprimer la fiche. Une fiche supprimée serait
  recréée au run suivant si son lien est encore sur la page source.

## Fournisseurs LLM et mode reprise

- Ordre par défaut (`LLM_PROVIDERS=mistral,openrouter`) : **Mistral** en direct avec
  `mistral-small-2603` (Mistral Small 4), puis **OpenRouter** `openrouter/free` en secours. Un
  fournisseur sans clé est ignoré ; une réponse vide, tronquée ou invalide fait passer au suivant.
- Chaque fournisseur est testé au démarrage : OpenRouter sans consommer de quota (clé, quota gratuit
  du jour, et existence du modèle dans la liste publique des modèles : un modèle introuvable écarte
  OpenRouter avec la piste `OPENROUTER_MODEL=openrouter/free`), Mistral par une très courte requête.
  En cours de run, il est désactivé si sa clé est refusée, si ses crédits ou son quota sont épuisés,
  ou après `LLM_BREAKER_THRESHOLD` échecs consécutifs (3).
- `openrouter/free` tire au hasard un modèle gratuit à chaque requête ; le modèle réellement servi
  est noté en tête de la Justification (`[LLM <modèle> · profil <version>/<empreinte>]`) et dans les
  statistiques. Quotas gratuits : 20 requêtes/min et 50 requêtes/jour tant que moins de 10 $ de
  crédits ont été achetés (remise à zéro à minuit UTC) ; GitNotate se limite à 18 requêtes/min.
- **Mode reprise** (`REQUIRE_LLM=true`, par défaut), aucune fiche dégradée : sans réponse LLM valide,
  le dépôt est **reporté**. Rien n'est écrit, et comme il reste absent de la base, il est repris
  automatiquement au run suivant. Une réponse est valide si elle contient toutes les clés attendues,
  sans recopie du modèle de réponse du prompt : `description_fr` non vide et en français (une
  description nettement anglaise, sans aucun mot français, est refusée) ; `cas_usage` sous forme de
  liste de textes, ou d'un texte unique découpé aux puces et aux sauts de ligne (une liste vide, un
  texte vide ou `null` sont acceptés et donnent « Non vérifié », comme les cas d'usage de remplissage
  « N/A », « Aucun » ou « Non vérifié ») ; les cinq jugements en entiers dans leur échelle (`"2"`,
  `2.0`, `"2/3"`, `"2 sur 3"` et `"2 (utile…)"` sont acceptés ; un booléen, `2.5`, une autre échelle
  comme `"2/5"` ou une valeur hors échelle ne le sont pas) ; `justification` non vide. Une clé
  accentuée (`catégorie`, `intérêt`) ou des notes regroupées dans un sous-objet (`"notes": {…}`)
  sont ramenées aux clés attendues. Certaines valeurs sont corrigées sans faire rejeter la
  réponse : une catégorie inconnue est laissée vide (`OCR / Documents` vaut `OCR/Documents`), un
  type de réutilisation inconnu devient `inspiration`, les noms de `brique_pour` absents du profil
  sont retirés (3 au plus ; un statut recopié du prompt, comme « Gitnotate (actif) », est ignoré ;
  au-delà de 3 noms, les projets actifs sont gardés en premier), et la justification est tronquée à
  400 caractères. Une réponse invalide fait passer au fournisseur suivant. Si aucun fournisseur n'est disponible au démarrage, le run s'arrête (code 1) avant tout
  appel GitHub, avec la piste qui correspond à la cause (clé refusée, quota épuisé, modèle
  introuvable). `REQUIRE_LLM=false` rétablit l'ancien
  comportement (fiche avec un score lexical calculé localement).
- Le mode reprise ne garantit une fiche entièrement issue du LLM (traduction, cas d'usage, note et
  justification) que si `TRANSLATION_ENABLED=true` et `LLM_SCORING_ENABLED=true` (valeurs par
  défaut). Avec `LLM_SCORING_ENABLED=false`, seule la traduction est exigée : la note est lexicale,
  la Justification ne vient pas du LLM, `Cas d'usage` vaut « Non vérifié », et ni `Catégorie` ni
  `Brique pour` ne sont écrites. La réponse doit tout de même contenir `use_cases_fr` (traduction
  de la liste générique, héritée de la v7.2) non vide et non recopié du gabarit : ce champ n'est
  jamais écrit, mais une réponse qui le laisse vide ou le recopie est refusée (signe d'un modèle qui
  recopie le gabarit), et le dépôt est reporté. Avec `TRANSLATION_ENABLED=false`, aucun LLM n'est
  appelé : les fiches gardent la description GitHub d'origine (en anglais le plus souvent) avec un score lexical,
  et `REQUIRE_LLM` est sans effet.
  Attention : un interrupteur laissé vide (`TRANSLATION_ENABLED=`) vaut **false** (sauf
  `REQUIRE_LLM`, que seule la valeur `false` désactive).

## Confidentialité

- Partent au LLM, pour les dépôts **publics** : nom, langage (« non détecté » s'il manque), topics,
  description, indices calculés par le script (fork, archivé, distribution PyPI, npm ou Docker
  détectée — un lien ou une commande d'installation compte seulement s'il désigne le paquet du
  dépôt ; pour Docker, depuis la v7.4, seule compte une image qui désigne le dépôt : image du même
  nom que le dépôt (`ghcr.io/huginn/huginn` pour huginn/huginn), ou image `<dépôt>-<suffixe>`
  publiée sous le nom du propriétaire (`acme/outil-server` pour acme/outil), citée dans une commande
  `docker run`, `docker create` ou `docker pull`, une adresse de registre, une page ou un badge
  Docker Hub, ou une ligne `image:` ; une image tierce (`docker run postgres`), une image au seul nom
  du propriétaire (`ollama/ollama` pour ollama/ollama-python), `docker compose up` ou `docker build`
  seuls ne comptent pas —, exigence de GPU relevée dans le README, avec la quantité de VRAM quand
  elle est écrite et la phrase source citée ; une phrase négative ou facultative comme « No GPU
  required » ou « Optional: a GPU with 6 GB VRAM » n'est jamais lue comme une exigence), et un
  extrait du README **nettoyé avant d'être tronqué** (`README_LLM_CHARS`, 1 500 caractères). Le
  nettoyage retire les commentaires HTML, les balises, les images, les badges, les URL et les
  définitions de liens, et réduit chaque bloc de code à 3 lignes. Ni les étoiles ni la licence ne
  sont envoyées (pour éviter un biais). Ce contenu est placé entre `<depot>` et `</depot>` ; le prompt le traite
  comme une donnée non fiable (ces balises sont retirées du contenu lui-même, y compris leurs
  variantes accentuées, en pleine chasse ou coupées par un caractère invisible) et interdit d'inventer
  une commande, une compatibilité ou une fonctionnalité. Un dépôt sans description, sans topics et
  sans README exploitable (fiche non notée) n'est pas envoyé du tout.
- Partent aussi, depuis votre profil : `contexte`, `environnement`, les technologies (`languages`,
  `frameworks`, `infra`), les domaines, les projets avec leurs besoins, les exclusions et la liste
  des catégories. Ne partent jamais : les clés commençant par `_`, `profile_version`, `licences` et
  `ponderations` (utilisées seulement par le calcul local).
- Dépôts privés : aucune donnée d'un dépôt privé n'est envoyée au LLM. Avec un jeton GitHub sans
  portée privée (recommandé) ou sans jeton, GitHub répond 404 : le dépôt apparaît en erreur
  « GitHub HTTP 404 » (run en code 2) ; retirez ce lien de la page source.
- Palier gratuit de Mistral : vos requêtes peuvent servir à entraîner ses modèles ; cette utilisation
  se désactive dans les réglages de confidentialité de la console Mistral.
- OpenRouter : vérifiez les réglages **Privacy** de votre compte (entraînement et publication des
  requêtes par les modèles gratuits). `OPENROUTER_DATA_COLLECTION=deny` exclut les fournisseurs qui
  collectent les données (moins de modèles gratuits). Les en-têtes d'attribution, qui rendent
  l'application visible publiquement, ne partent qu'avec `OPENROUTER_ATTRIBUTION=true`.
- Jetons et clés ne sont jamais affichés en clair (au plus leurs 4 premiers et 4 derniers caractères).
- `redecouverte.py` n'envoie rien à un LLM, sauf avec `cherche --llm` : votre recherche et, pour les
  premiers dépôts trouvés (8 par défaut), leur nom, `propriétaire/dépôt`, leur description et, pour les
  fiches v7.3 et suivantes, leurs cas d'usage et leur catégorie ; jamais de lien Notion, de Statut, de
  colonne personnelle, de `Brique pour` ni de Justification. Le résumé de l'envoi s'affiche avant une
  confirmation (« oui ») ; `--llm-apercu` montre le texte exact sans rien envoyer.

## Migration depuis la v7.3

Validez d'abord la v7.4 sur une base de test : [docs/VALIDATION.md](docs/VALIDATION.md).

- **Code** : `gitnotate.py` passe en 7.4.0 (`python gitnotate.py --version`) ; seules les règles de
  notation changent (plafond de 8 sans `Brique pour`, fiche non notée, indice Docker, repli lexical
  neutre : voir [Notation](#notation)). `clean_page_duplicates.py` et `scripts/check_llm.py` sont
  inchangés. Nouveaux fichiers : `redecouverte.py`, `redecouverte_lexique.py`,
  `scripts/evaluer_redecouverte.py` et [docs/REDECOUVERTE.md](docs/REDECOUVERTE.md).
- **`.env`** : aucune nouvelle variable pour `gitnotate.py`. Trois variables facultatives servent à
  `redecouverte.py` : `NOTION_READONLY_TOKEN`, `REDECOUVERTE_RESULTATS` et `REDECOUVERTE_LLM_MAX`
  (section « REDÉCOUVERTE » de `env.example`).
- **`user_profile.json`** : inchangé. Une exclusion n'agit sur le repli lexical que si elle est écrite
  comme un topic GitHub exact (voir [Profil de pertinence](#profil-de-pertinence-user_profilejson)).
- **Base Notion** : rien à changer, schéma inchangé. Une fiche non notée est créée avec `Pertinence`
  vide : triez sur `Pertinence` en sachant que ces fiches n'ont pas été jugées.
- **Anciennes fiches** : jamais modifiées ni recalculées. Une fiche v7.3 notée 9 ou 10 sans
  `Brique pour` garde sa note ; elle aurait 8 en v7.4. L'empreinte du profil change avec la v7.4,
  même si le profil est identique.
- **Cache GitHub** : son format passe de 3 à 5 (le format 5 distingue un README absent d'un README
  illisible) ; les entrées plus anciennes sont relues sur GitHub une fois, quand le dépôt est traité.
  Aucune action n'est nécessaire.
- **Retour à la v7.3** : voir l'étape G de [docs/VALIDATION.md](docs/VALIDATION.md). Aucune donnée
  Notion n'est à restaurer.

## Migration depuis la v7.2

Validez d'abord la version actuelle sur une base de test : [docs/VALIDATION.md](docs/VALIDATION.md).
Les points ci-dessous décrivent le passage à la v7.3 ; ceux de la section précédente s'y ajoutent.

- **Code** : seul `gitnotate.py` change (`python gitnotate.py --version` affiche 7.3.0).
  `scripts/check_llm.py` et `clean_page_duplicates.py` sont inchangés.
- **`.env`** : aucune nouvelle variable, votre `.env` de la v7.2 reste valable. `README_MAX_CHARS`
  limite désormais le README **nettoyé** gardé dans le cache ; Installation, Exemple et Prérequis
  sont extraits du README complet, avant cette limite.
- **`user_profile.json`** : le fichier livré passe au profil v2. Relisez les points à vérifier (VRAM,
  projets, exclusions, voir [Profil de pertinence](#profil-de-pertinence-user_profilejson)). Si vous
  aviez modifié votre `user_profile.json`, mettez votre version de côté avant de récupérer la v7.3 :
  vous pouvez la garder telle quelle (un profil v1 reste accepté) ou reporter vos listes dans le
  nouveau fichier.
- **Base Notion** : rien à changer. Le schéma de la v7.1 et de la v7.2 (avec ou sans
  `Justification`) est accepté tel quel. Si vous avez renommé ou supprimé une option d'origine de
  `Langage`, `Statut` ou `Type`, la valeur correspondante est désormais omise au lieu d'être créée
  par Notion (voir [Contenu des fiches](#contenu-des-fiches)). Vous pouvez ajouter à la main
  `Licence`, `Catégorie` et `Brique pour` (voir [Colonnes facultatives](#colonnes-facultatives)).
- **Anciennes fiches** : jamais modifiées ni recalculées. Leur `Pertinence` suit l'ancienne grille et
  ne se compare pas aux notes de la v7.3. Pour les distinguer, regardez la Justification (v7.3 :
  `profil <version>/<empreinte>]` suivi du détail `U·P·T·I·C·M·L = note`) ou la date `Analysé le`.
- **Nouvelles fiches** : Installation, Exemple et Prérequis sont extraits mot pour mot du README, ou
  valent « Non vérifié » ; les cas d'usage sont propres au dépôt, ou valent « Non vérifié » ;
  `Dernière MAJ` est la date du dernier push ; `Type` vient seulement de topics GitHub exacts (plus
  d'option « Outils » par défaut, la colonne peut rester vide). Un dépôt désactivé par GitHub est
  ignoré (compté dans « Filtrées »), sans appel au LLM.
- **LLM** : mêmes fournisseurs et mêmes modèles, toujours un seul appel par dépôt (le fournisseur
  de secours n'est sollicité que si le premier échoue ou répond mal), mais la réponse attendue suit
  le format v2. Une réponse hors format est refusée : le fournisseur suivant est
  essayé, puis le dépôt est reporté en mode reprise.
- **Cache GitHub** : les entrées écrites par la v7.2 n'ont ni licence, ni `archived`, ni
  `pushed_at` ; elles sont relues sur GitHub quand le dépôt est traité. Aucune action n'est
  nécessaire.
- **Retour à la v7.2** : voir l'étape G de [docs/VALIDATION.md](docs/VALIDATION.md). Aucune donnée
  Notion n'est à restaurer, puisque rien n'y est modifié.

## Migration depuis la v7.1

- `gitnotate_v7.1.py` devient `gitnotate.py` ; `scripts/check_llm.py` remplace `test_key.py`.
- Repartez de `env.example` et recopiez-y vos jetons et ID : un ancien `MISTRAL_MODEL=mistral-small-2503`
  (retiré par Mistral) ou `TRANSLATION_MODEL` resterait prioritaire sur les nouveaux défauts.
  `TRANSLATION_MODEL` (v7.1) est obsolète : supprimez la ligne pour utiliser `openrouter/free` (ou
  écrivez `OPENROUTER_MODEL=openrouter/free`) ; elle est encore lue, avec un avertissement, tout comme
  l'ancien défaut `OPENROUTER_MODEL=openai/gpt-oss-20b:free` et un ancien `MISTRAL_MODEL` de la v7.1.
- `MIN_UPDATE_DAYS` valait 180 dans l'ancien `env.example` (dépôts non mis à jour depuis 180 jours
  ignorés) ; il vaut 0 désormais (filtre désactivé). Recopiez `MIN_UPDATE_DAYS=180` dans votre `.env`
  pour garder ce filtre.
- `DATABASE_ID` est **obligatoire** : la v7.1 créait une nouvelle base quand il était vide ou
  illisible, la v7.2 s'arrête (code 1). `CREATE_DATABASE=true` ne sert qu'à la première installation.
- Nouveaux défauts LLM : Mistral `mistral-small-2603` puis OpenRouter `openrouter/free`, mode reprise
  actif (la v7.1 essayait OpenRouter `openai/gpt-oss-20b:free`, puis Mistral `mistral-small-2503`).
- Régénérez le jeton GitHub en lecture seule (sans portée `repo`) ; un jeton invalide arrête le run.
- Le nettoyeur simule par défaut et ne lit plus `DRY_RUN` (suppression : `--apply` + phrase exacte).
- `gitnotate_stats.json` et `extracted_urls_unique.txt` ne sont plus suivis par git (ce sont des
  fichiers produits par chaque run, désormais ignorés). **Si vous utilisez `git pull`** sur une copie
  qui les contient, copiez-les d'abord ailleurs : git les retirerait de votre dossier. Leur dernière
  version publiée reste récupérable : `git show 4b90d6f:gitnotate_stats.json > gitnotate_stats.json`
  (même commande pour `extracted_urls_unique.txt`).
- Les bases « Ressources GitHub » en double créées par l'ancienne version ne sont jamais supprimées
  par GitNotate : triez-les à la main dans Notion et gardez celle de `DATABASE_ID`.

## Tests

`python -m pip install -r requirements-dev.txt` puis `python -m pytest`. Les tests n'accèdent jamais
au réseau ni à votre `.env` : les API Notion, GitHub, Mistral et OpenRouter sont simulées.
`tests/test_lot3.py` couvre la v7.3 : compatibilité avec le schéma de la v7.1, colonnes facultatives,
absence de toute modification (seulement des lectures et des créations), extraits mot pour mot du
README, métadonnées GitHub absentes, stabilité de la note et validation des réponses du LLM.
`tests/test_lot4_notation.py` couvre les règles de la v7.4 (plafond sans brique, fiche non notée,
indice Docker, repli lexical neutre). `tests/test_redecouverte_sync.py`, `test_redecouverte_fiches.py`
et `test_redecouverte_recherche.py` couvrent `redecouverte.py` sur un corpus synthétique
(`tests/fixtures/redecouverte/`) : liste blanche des appels Notion, pagination, interruption,
conservation de l'index, versions des fiches, extraits mot pour mot, classement et requêtes de
référence. `tests/test_lot4_revue.py` reprend les constats de la revue du lot 4 (citations, niveau
« forte », champs modifiés dans Notion, caractères de contrôle, README illisible, chemins réseau…).
Ces tests ne remplacent pas la validation sur une vraie base de test décrite dans
[docs/VALIDATION.md](docs/VALIDATION.md).
