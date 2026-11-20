# Gitnotate V3-C : interface Web locale (pilote isolé)

## État et limites

La V3-C remplace le terminal comme interface pour le nouveau catalogue de signets.
Elle **ne remplace pas** le moteur historique redecouverte.py et n'importe
aucune fiche Notion. La recherche V3-C utilise l'index expérimental des signets
créé par catalogue_v3.py.

- Source principale : signets GitHub des pages Notion sélectionnées.
- Recherche : SQLite FTS5, **locale et sans LLM**.
- Enrichissement : GET API GitHub, lot limité à 20 dépôts/action, pas d'IA.
- Ajout/actualisation de sources : GET API Notion avec NOTION_READONLY_TOKEN.
- Configuration fournisseur/modèle/clé : fichier .env privé conservé,
  sans exposition au navigateur. La clé API peut être ajoutée ou remplacée.
- Test de clés/modèles : scripts/check_llm.py (contrôle de clé, sans génération).
- Les modèles configurés ne sont pas encore utilisés pour analyser les résultats
  du catalogue V3. Cette intégration constitue un lot suivant après qualification.
- Aucun endpoint d'écriture dans Notion, aucun déploiement ou accès réseau externe.

Ce pilote se développe depuis feat/v3-catalogue-signets-20261120,
dans sa propre branche feat/v3-interface-web-locale-20261120.
Ne pas fusionner sans le résultat CI et le test de navigation Windows.

## Installation Windows PowerShell (commandes indépendantes)

Le programme historique est dans :
D:\Downloads\Travaux en cours\Gitnotate

Le catalogue des signets de 809 dépôts et l'index des 443 fiches sont dans :
C:\Users\Fabrice\gitnotate-validation

1. Vérifier que le futur worktree est absent :

    Test-Path 'D:\Downloads\Travaux en cours\Gitnotate-V3-WEB-PILOTE'

Lancer la suite **uniquement si False**.

2. Récupérer la branche de test :

    git -C "D:\Downloads\Travaux en cours\Gitnotate" fetch origin "refs/heads/feat/v3-interface-web-locale-20261120:refs/remotes/origin/feat/v3-interface-web-locale-20261120"

3. Créer un worktree de test isolé, sans modifier les autres checkouts :

    git -C "D:\Downloads\Travaux en cours\Gitnotate" worktree add --detach "D:\Downloads\Travaux en cours\Gitnotate-V3-WEB-PILOTE" "origin/feat/v3-interface-web-locale-20261120"

4. Créer un Python 3.10 isolé dans ce nouveau worktree :

    py -3.10 -m venv "D:\Downloads\Travaux en cours\Gitnotate-V3-WEB-PILOTE\.venv"

5. Installer les dépendances applicatives (pas besoin de Node.js) :

    & "D:\Downloads\Travaux en cours\Gitnotate-V3-WEB-PILOTE\.venv\Scripts\python.exe" -m pip install -r "D:\Downloads\Travaux en cours\Gitnotate-V3-WEB-PILOTE\requirements.txt" -r "D:\Downloads\Travaux en cours\Gitnotate-V3-WEB-PILOTE\requirements-web-v3.txt"

6. Double-cliquer ensuite sur :
D:\Downloads\Travaux en cours\Gitnotate-V3-WEB-PILOTE\Gitnotate-V3.cmd

Une fenêtre console démarre le serveur et ouvre :
http://127.0.0.1:8765

Le lanceur configure automatiquement GITNOTATE_DATA_DIR à
%USERPROFILE%\gitnotate-validation. La fenêtre doit rester ouverte pendant
l'utilisation. Ctrl+C dans la console arrête le serveur.

## Navigation

- **Recherche** : besoin en français, sélection de sources (aucune case cochée
  signifie toutes les sources), 5/10/20 résultats avec couverture lexicale
  et niveau de preuve, liens GitHub.
- **Sources Notion** : ajouter une URL de page autorisée, actualiser toutes
  les sources, enrichir 5/10/20 dépôts par appel explicite.
- **Accès GitHub** : ajouter un jeton personnel en lecture seule pour augmenter
  le quota disponible pour les enrichissements.
- **Fournisseurs IA** : choisir Mistral, OpenRouter, OpenAI ou Anthropic, saisir
  l'identifiant du modèle et la clé correspondante, définir le fournisseur
  prioritaire et vérifier les clés.

Attention : les clés API sont stockées en texte clair dans le .env privé.
Le frontend n'obtient **jamais** les valeurs des clés ; seulement un booléen
"configurée". Il faut protéger le dossier Windows et ne pas l'archiver publiquement.

## Sécurité

- Uvicorn écoute uniquement 127.0.0.1, pas 0.0.0.0.
- Host limité à localhost et 127.0.0.1 ; aucune route CORS.
- Token de session anti-CSRF obligatoire sur toute requête POST, origine
  vérifiée, CSP stricte et ressources CSS/JS locales sans CDN.
- Écritures de configuration atomiques, uniquement sur une liste blanche de
  variables provider et GitHub ; jeton Notion historique et autres champs
  préservés. Pas de stockage des secrets dans le code Git.
- Opérations longues (inventaire, enrichissement, configuration) sérialisées.
- Aucune nouvelle route de création/modification Notion.
- Pas de génération LLM dans le serveur V3-C.
- Pas de service Windows installé, pas de port exposé au LAN, pas de VPS.

## Recette manuelle et critères de GO

1. Le lanceur démarre en un double-clic sans PowerShell manuel.
2. La page charge 809 dépôts, 10 enrichis (ou le nombre réel après
   enrichissements), 382 absents des fiches historiques (si données inchangées).
3. La recherche "automatiser une veille financière" renvoie les mêmes résultats
   que la CLI V3 pour le même nombre et la même sélection de sources.
4. Les URL GitHub s'ouvrent ; les textes tiers sont affichés sans HTML exécutable.
5. Un enrichissement volontaire de 5 dépôts réussit ou s'arrête proprement
   sur un quota GitHub, puis l'état est mis à jour sans perte.
6. L'interface sait ajouter une seconde page Notion seulement si
   l'intégration Gitnotate-ReadOnly y est autorisée.
7. La configuration d'un modèle/clé n'écrase pas NOTION_READONLY_TOKEN,
   DATABASE_ID, ni la configuration des autres fournisseurs.
8. Le vieux moteur redecouverte.py etat retrouve toujours les 443 fiches
   sans modification du fichier historique.
9. Les tests Python sous Windows 3.10 et Linux 3.13 sont verts sur la PR.

## Retour arrière

Arrêter la fenêtre console et continuer à utiliser l'installation historique
D:\Downloads\Travaux en cours\Gitnotate.
Aucun changement de branche stable ni de données Notion n'est nécessaire.
Ne pas supprimer le dossier privé gitnotate-validation : il contient les
secrets et les deux catalogues SQLite.
