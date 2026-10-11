# GitNotate

Outil personnel de veille : GitNotate lit les liens GitHub d'une page Notion, récupère pour chaque
dépôt ses métadonnées et le début de son README (API GitHub), demande à un LLM une traduction
française, une note de pertinence de 0 à 10 et une justification, puis crée une fiche par dépôt
dans une base Notion. Version 7.2 (`python gitnotate.py --version`).

## Prérequis

- Python 3.10 ou plus récent (Windows ou Linux).
- Une intégration Notion interne (<https://www.notion.so/my-integrations>) avec les capacités
  « Read content » et « Insert content », **connectée à la page source ET à la base**
  (dans Notion : ••• → Connexions → votre intégration).
- Une base Notion dont les colonnes (nom exact et type) sont vérifiées avant toute écriture :
  `Nom` (Titre), `URL` (URL), `Description`, `Cas d'usage`, `Installation`, `Exemple`, `Prérequis`
  (Texte), `Stars`, `Pertinence` (Nombre), `Langage`, `Statut` (Sélection), `Type` (Sélection
  multiple), `Dernière MAJ`, `Analysé le` (Date) et, facultative, `Justification` (Texte).
- Une clé API Mistral (fournisseur principal). Une clé OpenRouter est facultative (secours).
- Facultatif : un jeton GitHub en lecture seule (sans jeton : 60 requêtes GitHub par heure).

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
`USER_PROFILE_JSON`). Le `.env` contient vos secrets : ne le partagez jamais (il est exclu de git).

## Premier lancement

1. `python scripts/check_llm.py` vérifie les clés LLM sans consommer de quota de génération
   (code 0 : au moins une clé, et toutes les clés présentes sont valides ; le modèle Mistral est
   vérifié si `MISTRAL_API_KEY` est renseignée, le modèle OpenRouter si `OPENROUTER_API_KEY` l'est ;
   le quota gratuit OpenRouter est affiché).
2. Pas encore de base ? Avec `CREATE_DATABASE=true`, `python gitnotate.py` crée « Ressources GitHub »
   (avec toutes les colonnes) dans la page source, affiche son ID (noté aussi dans `.gitnotate_state.json`)
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

## Codes de sortie

| Code | `gitnotate.py` | `clean_page_duplicates.py` | `scripts/check_llm.py` |
|------|----------------|----------------------------|------------------------|
| 0 | succès, même avec des dépôts reportés | terminé sans problème | clés utilisables |
| 1 | configuration (option invalide, page source introuvable…) ou erreur fatale, aucune fiche créée | configuration, page ou journal introuvable | aucune clé, clé refusée, modèle absent, réseau |
| 2 | au moins une erreur, ou lecture partielle | abandon, lecture partielle ou échec | — |
| 130 | interruption (Ctrl-C) | — | — |

## Sûreté des données

- **`gitnotate.py` ne fait qu'ajouter des fiches** : il ne modifie ni ne supprime jamais rien dans
  Notion. Avec une intégration limitée à Read + Insert, Notion refuserait d'ailleurs toute modification.
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
  est noté en tête de la Justification (`[LLM <modèle> · profil <empreinte>]`) et dans les
  statistiques. Quotas gratuits : 20 requêtes/min et 50 requêtes/jour tant que moins de 10 $ de
  crédits ont été achetés (remise à zéro à minuit UTC) ; GitNotate se limite à 18 requêtes/min.
- **Mode reprise** (`REQUIRE_LLM=true`, par défaut), aucune fiche dégradée : sans réponse LLM valide
  (traduction, cas d'usage, note et justification non vides, sans recopie du modèle de réponse du
  prompt), le dépôt est **reporté**, rien n'est écrit, et comme il reste absent de la
  base il est repris automatiquement au run suivant. Si aucun fournisseur n'est disponible au
  démarrage, le run s'arrête (code 1) avant tout appel GitHub, avec la piste qui correspond à la
  cause (clé refusée, quota épuisé, modèle introuvable). `REQUIRE_LLM=false` rétablit l'ancien
  comportement (fiche avec un score lexical calculé localement).
- Le mode reprise ne garantit une fiche entièrement issue du LLM (traduction, cas d'usage, note et
  justification) que si `TRANSLATION_ENABLED=true` et `LLM_SCORING_ENABLED=true` (valeurs par
  défaut). Avec `LLM_SCORING_ENABLED=false`, seule la traduction est exigée : la note est lexicale
  et la Justification ne vient pas du LLM. Avec `TRANSLATION_ENABLED=false`, aucun LLM n'est
  appelé : les fiches restent en anglais avec un score lexical et `REQUIRE_LLM` est sans effet.
  Attention : un interrupteur laissé vide (`TRANSLATION_ENABLED=`) vaut **false** (sauf
  `REQUIRE_LLM`, que seule la valeur `false` désactive).

## Confidentialité

- Partent au LLM : nom, langage, topics, étoiles, description et début du README (`README_LLM_CHARS`,
  1 500 caractères) des dépôts **publics**, et votre profil de pertinence.
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
