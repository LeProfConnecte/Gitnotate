# Gitnotate V3-D — avis IA dans l'interface web

**État : pilote séparé, aucune fusion automatique.** La branche V3-D se fonde
sur la V3-C et ne change ni l'index historique des 443 fiches, ni l'inventaire
des signets, ni les droits Notion.

## Parcours utilisateur

1. Lancer l'interface locale sur http://127.0.0.1:8765.
2. Décrire son besoin et effectuer la **recherche locale**, sans appel LLM.
3. Pour les dépôts "Signet seul", utiliser d'abord **Enrichir ce dépôt** :
   cela interroge GitHub uniquement après confirmation.
4. Cocher de 1 à 5 dépôts avec des métadonnées GitHub réellement récupérées.
5. Choisir un fournisseur parmi Mistral, OpenRouter, OpenAI ou Anthropic.
   Le modèle affiché est celui de la configuration privée.
6. Cliquer sur **Préparer l'avis IA**. Un aperçu exact du message système et
   du contenu utilisateur apparaît. Rien n'est encore envoyé.
7. Lire l'avertissement relatif aux données et coûts, cocher le consentement
   et cliquer sur **Confirmer et envoyer à l'IA**.
8. Lire le résultat dans un panneau **distinct**, avec adéquation 0 à 3,
   verdict, contraintes explicites satisfaites / non satisfaites / inconnues,
   constats individuels et extraits littéraux retrouvés. La citation retrouvée
   ne constitue pas une validation sémantique de l'affirmation.
   Le classement SQLite ne change jamais.

Si aucun candidat n'est convaincant, le panneau l'indique explicitement.

## Configuration des modèles et des clés

Les clés ne sont pas saisies dans le navigateur dans ce lot : les fournisseurs
sont ceux déjà définis dans le fichier privé du pilote :

    C:\Users\Fabrice\gitnotate-validation\.env

La configuration peut être modifiée avec le lanceur Windows V2 préexistant,
puis le serveur V3 doit être **redémarré** pour la relire.

> **Mise à jour (lot V3, PR #9) :** les fournisseurs, modèles et clés peuvent
> désormais être configurés directement depuis « Réglages IA » dans Gitnotate V3
> (voir `docs/V3_REGLAGES_IA.md`). Un redémarrage du serveur reste nécessaire
> pour appliquer les nouveaux réglages aux avis IA. Le lanceur V2 demeure une
> solution de retour arrière.
Seuls les identifiants de fournisseurs et les noms de modèles sont renvoyés
au navigateur. Les clés ne sont jamais affichées ou transmises.

Le choix d'un fournisseur est manuel pour chaque requête. **Pas de fallback
silencieux** vers un autre fournisseur pouvant être plus cher.

## Garanties de confidentialité

- Recherche locale : 0 appel IA.
- Aperçu : 0 appel IA, durée de validité limitée à 5 minutes.
- Appel IA : 1 action de consentement explicite, jeton d'aperçu utilisable
  **une seule fois**. Un appel peut toutefois être retenté une fois par le
  moteur en cas de réponse HTTP 429/5xx ; consulter les éventuels coûts.
- Les seules données envoyées : besoin exprimé, identifiant public GitHub,
  description, topics et extrait de README (maximum 2500 caractères/dépôt).
- Ne jamais transmettre l'URL de la page Notion, les notes personnelles,
  la classification historique, le jeton Notion, ni aucune clé API.
- Les README sont traités comme **des données non fiables** dans le prompt.
  Ce garde-fou n'annule pas totalement le risque d'injection de prompt.
- L'avis IA reste **en mémoire de la page ouverte** : aucun enregistrement dans
  l'index ou la base Notion, aucun changement du tri local.
- Les exigences explicites du besoin (open source, local, gratuit, sans
  abonnement, autonome) sont signalées dans l'aperçu exact. Pour chaque
  candidat, le modèle doit les classer comme satisfaites, non satisfaites ou
  non vérifiées, avec extrait littéral obligatoire si un statut est affirmé.
- Chaque affirmation factuelle du panneau contient son propre extrait
  littéral de 12 à 180 caractères présent dans les données du **bon**
  dépôt. Le serveur valide la présence de cet extrait, pas sa portée
  sémantique : une affirmation incohérente peut toujours passer.
- Une exigence obligatoire non satisfaite plafonne l'avis à 1/3, et une
  exigence non vérifiée empêche un verdict de parfaite adéquation (3/3).
  Une licence SPDX seule n'établit pas que le moteur principal est ouvert.
  Si le README indique explicitement un moteur central privé alors que
  l'utilisateur exige open source ou autonomie, le serveur impose un
  verdict conservateur de dépendance propriétaire (0-1/3), en affichant
  la correction. Ce contrôle est limité aux formulations explicites.
- Si le modèle invente une citation ou omet des contraintes, l'avis est
  rejeté ; l'appel API peut néanmoins avoir été facturé.
- Le serveur Web reste lié à 127.0.0.1. Les appels POST exigent la validation
  Origin et le jeton anti-CSRF. Les données dynamiques sont affichées en
  texte brut dans le navigateur.

## Installation dans un nouveau worktree Windows

N'utilisez pas la branche stable, ni le worktree V3-C déjà opérationnel.
Depuis PowerShell 5.1 (une seule ligne à la fois) :

    Test-Path 'D:\Downloads\Travaux en cours\Gitnotate-V3-IA-PILOTE'

Attendu False, sinon STOP.

    git -C 'D:\Downloads\Travaux en cours\Gitnotate' fetch origin 'refs/heads/feat/v3-ai-review-20261121:refs/remotes/origin/feat/v3-ai-review-20261121'

    git -C 'D:\Downloads\Travaux en cours\Gitnotate' worktree add --detach 'D:\Downloads\Travaux en cours\Gitnotate-V3-IA-PILOTE' 'origin/feat/v3-ai-review-20261121'

    & 'D:\Downloads\Travaux en cours\Gitnotate-V3-IA-PILOTE\installer_web_v3.cmd'

Arrêter l'ancien serveur V3-C en appuyant sur Ctrl+C dans sa fenêtre :
les deux pilotes utilisent le même port 8765.

    & 'D:\Downloads\Travaux en cours\Gitnotate-V3-IA-PILOTE\Gitnotate-V3.cmd'

Ne lancer aucun import Notion. Les versions V3-C et stable sont conservées.
Revenir à V3-C revient à fermer le serveur V3-D et à relancer l'ancien
Gitnotate-V3.cmd du worktree précédent.

## Critères du GO local

- CI Linux Python 3.13 et Windows Python 3.10 : suite complète PASS.
- Recherche locale et enrichissement ciblé inchangés.
- Affichage des clés : les quatre fournisseurs sans exposer les secrets.
- Aucun fournisseur appelé lors d'une recherche ou d'un aperçu.
- Premier avis réel sur 1 à 2 dépôts, à budget contrôlé et seulement après
  consentement visible. Vérification manuelle des preuves et de l'absence de
  changement des index après l'appel.
- L'index historique 443 fiches et le catalogue 809 dépôts doivent être
  retrouvés (sous réserve des évolutions réellement effectuées par l'usager).
- PR V3-C et V3-B encore isolées : aucune fusion sans GO spécifique.

## Limites

- Le modèle ne connaît que les métadonnées GitHub et l'extrait README
  transmis, pas l'intégralité du dépôt.
- Les sources sont le cache GitHub local, qui peut devenir ancien.
- Il n'existe aucune notation universelle de pertinence : les 0-3 sont
  des avis indicatifs, non des probabilités.
- L'enregistrement des clés et l'édition du modèle directement dans le
  navigateur restent hors du présent lot V3-D. Le lanceur V2 servait à cela ;
  depuis le lot V3 de la PR #9, « Réglages IA » le permet (redémarrage requis).
