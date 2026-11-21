# Gitnotate V3-C : interface Web locale

Cette V3 est un pilote isole au-dessus du catalogue V3-A/B.
Elle ne modifie ni la branche stable, ni l'index historique des 443 fiches,
ni la base Notion.

## Fonctionnalites

- Recherche locale sur les signets avec resultats en cartes.
- Provenance Notion, date du controle GitHub et niveau de preuve.
- Filtres : tous / GitHub consulte / signets seuls / absents de l'historique.
- Choix des sources, ajout et actualisation explicites des pages Notion.
- Enrichissement cible : jusqu'a cinq depots choisis parmi les resultats.
- Aucun LLM, aucune facture de generation dans ce pilote.
- Aucun build Node, aucun service Cloud ; HTML/CSS/JS servis par FastAPI.

Le nombre de notions lexicales couvertes n'est PAS une note de pertinence.

## Installation Windows PowerShell 5.1

Dossiers existants a conserver :

    D:\Downloads\Travaux en cours\Gitnotate
    C:\Users\Fabrice\gitnotate-validation
    D:\Downloads\Travaux en cours\Gitnotate-V3-PILOTE

Ne pas actualiser la branche stable pour installer ce pilote.

1. Verifier l'absence du nouveau dossier :

    Test-Path 'D:\Downloads\Travaux en cours\Gitnotate-V3-WEB'

   Attendu : False. Si True, ne pas ecraser le dossier.

2. Recuperer la branche :

    git -C 'D:\Downloads\Travaux en cours\Gitnotate' fetch origin 'refs/heads/feat/v3-web-local-20261120:refs/remotes/origin/feat/v3-web-local-20261120'

3. Creer le worktree isole :

    git -C 'D:\Downloads\Travaux en cours\Gitnotate' worktree add --detach 'D:\Downloads\Travaux en cours\Gitnotate-V3-WEB' 'origin/feat/v3-web-local-20261120'

4. Installer les dependances dans le worktree uniquement :

    & 'D:\Downloads\Travaux en cours\Gitnotate-V3-WEB\installer_web_v3.cmd'

5. Lancer l'application :

    & 'D:\Downloads\Travaux en cours\Gitnotate-V3-WEB\Gitnotate-V3.cmd'

   Adresse : http://127.0.0.1:8765
   Le navigateur s'ouvre automatiquement et le dossier de donnees
   C:\Users\Fabrice\gitnotate-validation est defini par le lanceur.

Arret : Ctrl+C ou fermeture du terminal. Aucun service permanent.

## Protection des donnees

- Serveur lie uniquement a 127.0.0.1, non expose au reseau local.
- Hote, origine et jeton anti-CSRF controles pour les requetes mutantes.
- CSP et affichage des donnees de depots en texte brut (pas de HTML injecte).
- Les cles Notion/GitHub restent dans le fichier prive cote Python et
  ne sont jamais exposees par les endpoints HTTP.
- Aucune requete externe au demarrage ; la recherche reste hors ligne.
- Synchronisation Notion : GET et uniquement apres demande explicite.
- Enrichissement GitHub : GET et uniquement apres confirmation explicite,
  sur un depot valide et appartenant aux pages indexees.
- Les erreurs de pagination/quota conservent l'ancien catalogue local.
- Le moteur et l'index de redecouverte des 443 fiches restent inchanges.

## Validations avant fusion

- Tests unitaires et suite complete sous Windows Python 3.10 et Linux 3.13.
- Ouvrir l'interface sur le PC Windows, verifier le nombre de signets,
  les fiches historiques et les descriptions GitHub.
- Recherche "automatiser une veille financiere" et validation des filtres.
- Enrichir un depot non analyse depuis sa carte.
- Verifier que son statut change sans appel IA ni ecriture Notion.
- Confirmer que redecouverte.py etat conserve l'index historique.

## Limites fonctionnelles explicites

- Avis IA et gestion des cles/modeles depuis le navigateur : a integrer
  seulement apres qualification de l'interface.
- Recherche V3-B encore lexicale et exploratoire (pas de note semantique).
- Filtres appliques aux 50 premiers resultats charges.
- L'utilisateur doit donner l'acces aux autres pages Notion via
  l'integration Gitnotate-ReadOnly.
