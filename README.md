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

## Configuration

Copiez le modèle en `.env` **dans le dossier du script** (`Copy-Item env.example .env` sous
PowerShell, `cp env.example .env` sous Linux) et renseignez au minimum `NOTION_TOKEN`,
`PARENT_PAGE_ID`, `DATABASE_ID` et `MISTRAL_API_KEY` ; chaque variable y est commentée avec sa valeur
par défaut. Le profil qui sert à noter les dépôts se règle dans `user_profile.json` (ou
`USER_PROFILE_JSON`). Le `.env` contient vos secrets : ne le partagez jamais (il est exclu de git).

## Premier lancement

1. `python scripts/check_llm.py` vérifie les clés LLM sans consommer de quota de génération
   (code 0 : clés valides et modèle Mistral disponible ; le quota gratuit OpenRouter est affiché).
2. Pas encore de base ? Avec `CREATE_DATABASE=true`, `python gitnotate.py` crée « Ressources GitHub »
   (avec toutes les colonnes) dans la page source, affiche son ID (noté aussi dans `.gitnotate_state.json`)
   et s'arrête sans rien importer. Recopiez l'ID dans `DATABASE_ID` et remettez `CREATE_DATABASE=false`.
3. `python gitnotate.py --dry-run --max-repos 10` simule 10 dépôts : GitHub et le LLM sont appelés
   (le quota est consommé), mais rien n'est écrit dans Notion.
4. `python gitnotate.py --max-repos 10` pour un premier import réel limité, puis `python gitnotate.py`.

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
erreur ; l'historique des 50 derniers runs est dans `gitnotate_stats.json`.

## Codes de sortie

| Code | `gitnotate.py` | `clean_page_duplicates.py` | `scripts/check_llm.py` |
|------|----------------|----------------------------|------------------------|
| 0 | succès, même avec des dépôts reportés | terminé sans problème | clés utilisables |
| 1 | configuration ou erreur fatale, aucune fiche créée | configuration, page ou journal introuvable | clé absente ou refusée, modèle absent, réseau |
| 2 | au moins une erreur, ou lecture partielle | abandon, lecture partielle ou échec | — |
| 130 | interruption (Ctrl-C) | — | — |

## Sûreté des données

- **`gitnotate.py` ne fait qu'ajouter des fiches** : il ne modifie ni ne supprime jamais rien dans
  Notion. Avec une intégration limitée à Read + Insert, Notion refuserait d'ailleurs toute modification.
- **Aucune base créée implicitement** : `DATABASE_ID` vide ou illisible → arrêt (code 1) avec le code
  HTTP et une piste. `CREATE_DATABASE=true` ne crée qu'une base, jamais en simulation ; une seconde
  création est refusée tant que `.gitnotate_state.json` garde l'ID.
- **Lecture complète ou rien** : si la base ou la page source n'est lue qu'en partie, le run s'arrête
  sans créer de fiche (code 2). Une création restée sans réponse (timeout) n'est jamais renvoyée,
  pour éviter un doublon ; si elle n'a pas abouti, le dépôt sera repris au run suivant.
- **Le nettoyeur `clean_page_duplicates.py` ne touche que la page source** : il met à la corbeille
  Notion les blocs lien (signet, aperçu, intégration) qui répètent un lien GitHub déjà présent.
  Il simule par défaut ; `--apply` exige de taper exactement « SUPPRIMER n » et il abandonne sans rien
  supprimer au-delà de `CLEANER_MAX_DELETE` suppressions (50). Un journal est écrit dans `journal/`
  **avant** chaque suppression : `--restore <journal>` montre ce qui serait restauré, et
  `--restore <journal> --apply` le remet en place (phrase « RESTAURER n »). Donnez-lui sa propre
  intégration (`NOTION_CLEANER_TOKEN`, capacités Read + Update content).
- **Triez sans supprimer** : pour écarter un dépôt, ajoutez une option « Écarté » à la colonne
  `Statut` (gardez le type Sélection) plutôt que de supprimer la fiche. Une fiche supprimée serait
  recréée au run suivant si son lien est encore sur la page source.

## Fournisseurs LLM et mode reprise

- Ordre par défaut (`LLM_PROVIDERS=mistral,openrouter`) : **Mistral** en direct avec
  `mistral-small-2603` (Mistral Small 4), puis **OpenRouter** `openrouter/free` en secours. Un
  fournisseur sans clé est ignoré ; une réponse vide, tronquée ou invalide fait passer au suivant.
- Chaque fournisseur est testé au démarrage (OpenRouter sans consommer de quota, Mistral par une très
  courte requête). En cours de run, il est désactivé si sa clé est refusée, si ses crédits ou son
  quota sont épuisés, ou après `LLM_BREAKER_THRESHOLD` échecs consécutifs (3).
- `openrouter/free` tire au hasard un modèle gratuit à chaque requête ; le modèle réellement servi
  est noté en tête de la Justification (`[LLM <modèle> · profil <empreinte>]`) et dans les
  statistiques. Quotas gratuits : 20 requêtes/min et 50 requêtes/jour tant que moins de 10 $ de
  crédits ont été achetés (remise à zéro à minuit UTC) ; GitNotate se limite à 18 requêtes/min.
- **Mode reprise** (`REQUIRE_LLM=true`, par défaut), aucune fiche dégradée : sans réponse LLM valide
  (traduction et note), le dépôt est **reporté**, rien n'est écrit, et comme il reste absent de la
  base il est repris automatiquement au run suivant. Si aucun fournisseur n'est disponible au
  démarrage, le run s'arrête (code 1) avant tout appel GitHub. `REQUIRE_LLM=false` rétablit l'ancien
  comportement (fiche avec un score lexical calculé localement).

## Confidentialité

- Partent au LLM : nom, langage, topics, étoiles, description et début du README (`README_LLM_CHARS`,
  1 500 caractères) des dépôts **publics**, et votre profil de pertinence. Les dépôts privés sont ignorés.
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
  (retiré par Mistral) ou `TRANSLATION_MODEL` resterait prioritaire sur les nouveaux défauts
  (`TRANSLATION_MODEL` est remplacée par `OPENROUTER_MODEL`, encore lue avec un avertissement).
- `DATABASE_ID` est **obligatoire** : la v7.1 créait une nouvelle base quand il était vide ou
  illisible, la v7.2 s'arrête (code 1). `CREATE_DATABASE=true` ne sert qu'à la première installation.
- Nouveaux défauts LLM : Mistral `mistral-small-2603` puis OpenRouter `openrouter/free`, mode reprise
  actif (la v7.1 essayait OpenRouter `openai/gpt-oss-20b:free`, puis Mistral `mistral-small-2503`).
- Régénérez le jeton GitHub en lecture seule (sans portée `repo`) ; un jeton invalide arrête le run.
- Le nettoyeur simule par défaut et ne lit plus `DRY_RUN` (suppression : `--apply` + phrase exacte).
- Les bases « Ressources GitHub » en double créées par l'ancienne version ne sont jamais supprimées
  par GitNotate : triez-les à la main dans Notion et gardez celle de `DATABASE_ID`.

## Tests

`python -m pip install -r requirements-dev.txt` puis `python -m pytest`. Les tests n'accèdent jamais
au réseau ni à votre `.env` : les API Notion, GitHub, Mistral et OpenRouter sont simulées.
