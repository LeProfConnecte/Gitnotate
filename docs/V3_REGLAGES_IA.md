# Gitnotate V3 — réglages IA dans l'interface Web locale

Statut : fonctionnalité en PR isolée, non fusionnée. Elle s'ajoute à la V3 stable,
sans changement de schéma Notion, d'index historique ni de moteur de classement.

## Pourquoi

L'ancien lanceur Tkinter V2 était nécessaire pour modifier Mistral, OpenRouter,
OpenAI et Anthropic. Ce lot permet de choisir fournisseur, identifiant de
modèle et clé API directement dans la V3 web sur http://127.0.0.1:8765.

## Parcours

1. Ouvrir « Réglages IA » dans la navigation de Gitnotate V3.
2. Choisir Mistral, OpenRouter, OpenAI ou Anthropic.
3. Saisir l'identifiant exact du modèle dans le champ libre. Le bouton
   « Tester la connexion et lister les modèles » charge des suggestions via
   l'API du fournisseur ; aucune génération n'est lancée.
4. Saisir une NOUVELLE clé API dans le champ masqué (ou le laisser vide pour
   conserver la clé actuellement enregistrée).
5. Enregistrer explicitement ; les autres clés, tokens Notion et paramètres
   sont laissés intacts.
6. Arrêter et relancer le serveur Gitnotate-V3.cmd pour appliquer les
   modèles et clés au moteur IA déjà chargé en mémoire.

Un bouton distinct « Effacer la clé » demande une confirmation et vide
UNIQUEMENT la clé du fournisseur choisi dans le fichier privé. Il ne
révoque PAS la clé sur le site du fournisseur.

La liste de modèles et la vérification de clé sont facultatives et peuvent
être lancées AVANT l'enregistrement pour éviter de sauvegarder une clé
invalide. Un modèle trouvé dans la liste n'est PAS une garantie de quota,
crédits disponibles, compatibilité avec tous les paramètres de génération,
ni coût nul de futures générations.

## Limites et sécurité

- Les clés sont enregistrées EN TEXTE CLAIR dans le fichier privé
  GITNOTATE_DATA_DIR/.env. Cela suit le contrat déjà utilisé par la V2.
  Le fichier doit rester dans le profil utilisateur Windows, avec des ACL
  privées. Ce lot n'introduit pas de coffre-fort chiffré (DPAPI/Keyring).
- Aucune clé n'est renvoyée par les API HTTP : seule une présence booléenne
  est affichée. Pas de suffixe ni de préfixe de clé, pas de stockage
  localStorage/sessionStorage ou copie dans les sources de page.
- L'API de configuration ne modifie que les huit variables connues :
  MISTRAL_API_KEY/MODEL, OPENROUTER_API_KEY/MODEL,
  OPENAI_API_KEY/MODEL et ANTHROPIC_API_KEY/MODEL.
- Les autres lignes du .env, commentaires et jetons Notion sont conservés ;
  doublon de variable ou format invalide : arrêt sans mutation.
- Les écritures sont atomiques (fichier temporaire privé dans le même
  répertoire et os.replace) : en cas d'échec l'ancien .env est préservé.
  Pas de sauvegarde en clair supplémentaire laissée par le programme.
- Serveur strictement local (127.0.0.1), contrôle Host, Origin et CSRF
  conservés. L'édition est bloquée durant une requête IA en cours.
- Les tests de connexion font uniquement les GET fixes vers :
    OpenAI : https://api.openai.com/v1/models
    Anthropic : https://api.anthropic.com/v1/models
    Mistral : https://api.mistral.ai/v1/models
    OpenRouter : https://openrouter.ai/api/v1/key pour vérifier la clé,
                 puis https://openrouter.ai/api/v1/models pour le modèle.
  Aucune redirection automatique avec en-tête de clé. Aucun appel POST
  de génération. Les requêtes n'utilisent pas de proxy implicite.
- Un changement de clé/modèle demande le redémarrage du serveur, sans
  modifier automatiquement l'ordre LLM_PROVIDERS utilisé pour de futurs
  imports. L'interface web choisit explicitement un fournisseur pour l'avis.
- Ne jamais partager un extrait du .env, des clés ni un journal contenant
  des en-têtes Authorization/x-api-key.
- Une personne ou un logiciel malveillant contrôlant déjà la session
  Windows peut lire le fichier en clair : ce lot ne résout pas une
  compromission de l'ordinateur.

## Validation avant toute fusion

1. Tests pytest sous Windows Python 3.10 et Linux Python 3.13.
2. Test simulé de sauvegarde/erreur : le token Notion et les variables
   non IA conservent leur valeur exacte, aucune clé renvoyée par l'API.
3. Test des requêtes GET sans génération, refus d'une clé invalide,
   d'une redirection HTTP et des requêtes cross-origin / sans CSRF.
4. Pilote natif Windows dans un worktree isolé : ouverture de l'interface,
   sélection fournisseur/modèle, sauvegarde en .env privé, redémarrage
   et lecture du modèle dans le panneau « Comparer avec une IA ».
5. Vérifier 809 signets et 443 fiches historiques inchangés (ou leurs
   totaux légitimement mis à jour depuis), et aucune écriture Notion.

## Retour arrière

Quitter le serveur pilote, relancer le serveur de la branche stable.
Les réglages .env enregistrés via l'interface persistent dans le dossier
privé : si besoin, modifier le modèle/clé de retour via l'ancien lanceur V2
ou noter les anciennes valeurs de modèles avant essai. Aucune commande
de suppression de données ni reset Git destructif n'est nécessaire.
