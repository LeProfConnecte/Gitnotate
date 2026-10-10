# 📘 GitNotate v6.7 - Guide Complet

**GitNotate** est un outil Python d'automatisation de veille technologique. Il extrait des URLs GitHub depuis une page Notion, analyse les dépôts, traduit les descriptions en français avec l'IA, et remplit une base de données Notion structurée.

---

## 🌟 Nouveautés v6.7

| Fonctionnalité | Description | Impact |
|----------------|-------------|--------|
| **Cache GitHub (24h)** | Évite les requêtes API en double pour les repos récemment analysés | ⚡ +50-100% de vitesse |
| **Nettoyage Doublons** | Script dédié pour supprimer les URLs dupliquées dans la page source | 🧹 Base propre |
| **Mode DRY_RUN** | Simulation complète sans aucune écriture dans Notion | 🔍 Tests sécurisés |
| **Filtre Ancienneté** | Ignore automatiquement les projets abandonnés (> X jours sans update) | 📊 Données pertinentes |
| **Détection Langue Auto** | Ne traduit que les contenus en anglais (économie crédits IA) | 💰 -10% coûts |
| **Barre de Progression** | Suivi visuel temps réel avec ETA | 👁️ Monitoring |
| **Stats JSON** | Historique des 50 dernières exécutions sauvegardé | 📈 Analyse perf |

---

## 🛠️ Installation

### 1. Prérequis

- **Python 3.8+** installé ([Télécharger Python](https://www.python.org/downloads/))
- **Compte GitHub** avec Token d'accès personnel
- **Compte Notion** avec Token d'intégration + IDs de page/base
- **Clé API OpenRouter** (Optionnel, pour traduction IA gratuite)

### 2. Installation des dépendances

Créez un dossier projet et installez les bibliothèques requises :

```bash
# Windows PowerShell
cd "C:\Users\VotreNom\Desktop\GitNotate"
pip install requests python-dotenv

# macOS / Linux
cd ~/GitNotate
pip3 install requests python-dotenv

3. Configuration .env

Créez un fichier .env à la racine du projet avec vos clés API :

bash
# ========================================
# TOKENS & CLÉS API
# ========================================

# Token d'intégration Notion (secret_xxxxx...)
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Token GitHub Personnel (ghp_xxxxx...)
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Clé API OpenRouter pour traduction IA (sk-or-v1-xxxxx...)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ========================================
# IDs NOTION
# ========================================

# ID de la PAGE contenant les liens GitHub à analyser
# Exemple : https://www.notion.so/Ma-Page-1cab36ca5523800292cad5f59ab1fc0c
# → PARENT_PAGE_ID = 1cab36ca5523800292cad5f59ab1fc0c
PARENT_PAGE_ID=1cab36ca5523800292cad5f59ab1fc0c

# ID de la BASE DE DONNÉES de destination (laissez vide pour création auto)
# Exemple : https://www.notion.so/2e8b36ca552381888439cb17eff24c83?v=...
# → DATABASE_ID = 2e8b36ca552381888439cb17eff24c83
DATABASE_ID=2e8b36ca-5523-816f-9f08-f2a87c465404

# ========================================
# CONFIGURATION AVANCÉE
# ========================================

# Nombre de threads parallèles (recommandé : 3-5)
MAX_WORKERS=5

# Modèle IA pour traduction (gratuit par défaut)
# Options gratuites : openai/gpt-3.5-turbo, google/gemma-2-9b-it:free
TRANSLATION_MODEL=openai/gpt-3.5-turbo

# Activer la traduction automatique (true/false)
TRANSLATION_ENABLED=true

# Mode simulation : teste sans écrire dans Notion (true/false)
DRY_RUN=false

# Activer le cache GitHub (true/false) - garde les infos 24h
CACHE_ENABLED=true

# Ignorer les repos non mis à jour depuis X jours (0 = désactivé)
# Recommandé : 180 (6 mois) ou 365 (1 an)
MIN_UPDATE_DAYS=180

# Nettoyage auto des doublons dans la DB (true/false)
CLEAN_DUPLICATES=false

🔑 Obtenir vos Tokens
A. Token Notion

    Allez sur https://www.notion.so/my-integrations

    Cliquez sur "+ New integration"

    Donnez un nom (ex: "GitNotate Bot")

    Copiez le Internal Integration Token (commence par secret_...)

    Important : Invitez l'intégration sur votre page source ET votre base de données

        Ouvrez la page/DB dans Notion

        Cliquez sur ⋯ (menu) en haut à droite

        Connections → Connect to → Sélectionnez votre intégration

B. Token GitHub

    Allez sur https://github.com/settings/tokens

    Cliquez sur "Generate new token" → "Classic"

    Cochez au minimum : repo (accès aux dépôts publics)

    Générez et copiez le token (commence par ghp_...)

C. Clé OpenRouter (Traduction IA)

    Créez un compte sur https://openrouter.ai

    Allez dans "Keys" et créez une nouvelle clé

    Copiez la clé (commence par sk-or-v1-...)

    Le tier gratuit offre des modèles comme openai/gpt-3.5-turbo avec limite mensuelle

🚀 Utilisation
1. Analyse et Importation (Principal)

Lance l'analyse des dépôts GitHub et le remplissage de la base Notion.

bash
# Windows PowerShell
python gitnotate_v6.7.py

# macOS / Linux
python3 gitnotate_v6.7.py

🔄 Déroulement du script :

    Validation des tokens (Notion, GitHub, OpenRouter)

    Création/Vérification de la base de données Notion

    Extraction des URLs depuis la page source (PARENT_PAGE_ID)

    Détection des doublons (normalisation des URLs)

    Préchargement des URLs existantes (pour éviter les duplications)

    Traitement parallèle de chaque dépôt :

        Récupération infos GitHub (Stars, Langage, Topics, README)

        Analyse du README pour extraire installation/exemple/prérequis

        Traduction FR via IA (si activé)

        Calcul du score de pertinence (0-10) selon votre profil

        Création de la page dans la base Notion

    Sauvegarde des statistiques (gitnotate_stats.json)

💡 Exemple de sortie :

text
======================================================================
🚀 GITNOTATE v6.7 - OPTIMIZED PRODUCTION EDITION
======================================================================

⚡ Configuration:
 -  Workers: 5
 -  GitHub auth: ✅
 -  Traduction: ✅
 -  Modèle: openai/gpt-3.5-turbo
 -  Cache GitHub: ✅
 -  Dry-run: ❌
 -  Filtre âge: ✅ 180 jours

📋 Database Notion...
✅ Database prête!
 -  ID: 2e8b36ca-5523-816f-9f08-f2a87c465404
 -  URL: https://www.notion.so/2e8b36ca552381888439cb17eff24c83

🔍 Extraction URLs (pagination complète)...
✅ 312 URLs extraites

🔍 Détection des doublons...
  ⚠️  Doublon: https://github.com/browserbase/stagehand
      Identique: https://github.com/browserbase/stagehand
  
📊 Résumé doublons:
  -  URLs totales: 312
  -  URLs uniques: 254
  -  Doublons supprimés: 58

⏳ Préchargement des URLs existantes...
✅ 187 URLs déjà présentes

📊 Traitement de 67 dépôts...

[1/67] ✅ browserbase/stagehand (1234 ⭐ | 🎯 8/10) 🌍 FR
[2/67] ✅ anthropics/claude-mcp (987 ⭐ | 🎯 9/10) 🌍 FR
[3/67] ⏭️ old-project/abandoned - Trop ancien
...

✅ TERMINÉ en 2m 34s
📊 Stats:
  -  Succès: 54
  -  Erreurs: 0
  -  Ignorés (déjà présents): 10
  -  Ignorés (trop anciens): 3
  -  Traduction: 48/54 (88.9%)

2. Nettoyage des Doublons dans la Page Source

Si vous avez collé plusieurs fois les mêmes liens GitHub dans votre page de veille Notion, utilisez le script dédié pour nettoyer les doublons directement dans la page source (pas dans la base de données).
a. Création du script

Créez un fichier clean_page_duplicates.py dans le même dossier que gitnotate_v6.7.py.
b. Test en mode simulation (DRY_RUN)

bash
# Dans .env, configurez :
DRY_RUN=true

# Puis lancez :
python clean_page_duplicates.py

Sortie attendue (simulation) :

text
📂 Dossier : C:\Users\Fabrice\Desktop\GitNotate
📄 Fichier .env : C:\Users\Fabrice\Desktop\GitNotate\.env
✅ .env chargé

======================================================================
🧹 NETTOYEUR DE DOUBLONS - PAGE SOURCE NOTION
======================================================================

🔑 Token : secr...xxxx
📄 Page ID : 1cab36ca5523800292cad5f59ab1fc0c

🔍 MODE DRY-RUN : Simulation (aucune suppression)

📥 Récupération des blocs de la page...
✅ 438 blocs récupérés

🔍 Extraction des URLs GitHub...
✅ 312 URLs GitHub trouvées

🔍 Détection des doublons...

⚠️  URL : https://github.com/browserbase/stagehand
  📌 GARDE : Block abc123def456 (bookmark)
  🗑️  SUPPRIME : 2 bloc(s)

⚠️  URL : https://github.com/anthropics/claude-mcp
  📌 GARDE : Block def789ghi012 (link_preview)
  🗑️  SUPPRIME : 1 bloc(s)

📊 Bilan :
  -  URLs uniques : 254
  -  URLs en doublon : 58
  -  Blocs à supprimer : 58

🔍 MODE DRY-RUN : Aucune suppression effectuée
💡 Pour supprimer : DRY_RUN=false python clean_page_duplicates.py

c. Suppression réelle

Une fois satisfait du résultat de la simulation :

bash
# Dans .env, changez :
DRY_RUN=false

# Puis relancez :
python clean_page_duplicates.py

Le script vous demandera confirmation avant toute suppression :

text
❓ Confirmer la suppression de 58 blocs ? (OUI/non) : OUI

🗑️  Suppression en cours...
  ✅ [1/58] Supprimé : https://github.com/browserbase/stagehand
  ✅ [2/58] Supprimé : https://github.com/anthropics/claude-mcp
  ...
  
✅ TERMINÉ : 58/58 blocs supprimés

🎯 Ce que fait le script :

    ✅ Scanne tous les blocs de votre page source

    ✅ Identifie les URLs GitHub dupliquées (normalisation intelligente)

    ✅ Garde la première occurrence, supprime les autres

    ⚠️ Ne touche pas aux liens dans du texte (nécessite suppression manuelle)

    ✅ Supprime uniquement les blocs de type bookmark, link_preview, embed

⚙️ Personnalisation du Profil Utilisateur

Le score de pertinence (0-10) est calculé en fonction de vos centres d'intérêt. Par défaut, GitNotate utilise un profil "développeur full-stack éducation/automation".
Profil par défaut (dans le code)

python
USER_PROFILE_DEFAULT = {
    "languages": ["Python", "JavaScript", "TypeScript"],
    "frameworks": ["Django", "Next.js", "React", "FastAPI"],
    "domains": ["education", "web-dev", "automation", "ai", "llm"],
    "interests": ["teaching-tools", "document-processing", "translation"]
}

Personnalisation via user_profile.json

Créez un fichier user_profile.json à la racine du projet pour surcharger ces valeurs :

json
{
  "languages": ["Python", "Rust", "Go", "TypeScript"],
  "frameworks": ["FastAPI", "Actix", "Next.js", "Tailwind"],
  "domains": ["ai", "automation", "finance", "crypto", "saas", "devops"],
  "interests": ["trading-bot", "scraping", "workflow", "docker", "monitoring"]
}

📊 Calcul du score :

    +3 points : Si le langage principal correspond

    +4 points max : Si des frameworks correspondants sont détectés (max 4)

    +2 points max : Si des domaines correspondent

    +1 point max : Si des centres d'intérêt sont trouvés

    +1 point : Bonus "éducation" si keywords (education, teaching, student...)

    +1 point : Bonus "automation" si keywords (automation, workflow, scraping...)

    -3 points : Si langage non pertinent (Java, C++, Kotlin) sans domaine correspondant

    -2 points : Si topics non pertinents (game, mobile-app, blockchain)

📊 Structure de la Base Notion

GitNotate crée automatiquement une base de données avec ce schéma :
Propriété	Type	Description	Exemple
Nom	Title	Nom du dépôt GitHub	stagehand
URL	URL	Lien vers le dépôt	https://github.com/browserbase/stagehand
Stars	Number	Nombre d'étoiles	12450
Pertinence	Number	Score /10 calculé selon profil	8
Langage	Select	Langage principal	Python, JavaScript, TypeScript, Go, Autre
Type	Multi-select	Catégories du projet	Agent IA, ML/AI, Web, Outils
Statut	Select	État d'exploration	À explorer, En test, Utilisé
Description	Rich Text	Résumé traduit en FR	"Automatise les tâches web avec l'IA..."
Cas d'usage	Rich Text	Suggestions d'utilisation	"- Scraping intelligent\n- Tests E2E..."
Installation	Rich Text	Commande d'installation	npm install @browserbase/stagehand
Exemple	Rich Text	Code exemple simple	(extrait du README)
Prérequis	Rich Text	Dépendances nécessaires	Node.js 18+, API key
Dernière MAJ	Date	Date du dernier commit	2026-01-10
Analysé le	Date	Date du traitement GitNotate	2026-01-14
❓ Dépannage & FAQ
🔴 Erreur : NOTION_TOKEN manquant

Cause : Le fichier .env n'est pas trouvé ou la variable est vide.

Solution :

    Vérifiez que .env est bien dans le même dossier que gitnotate_v6.7.py

    Sur Windows, le fichier ne doit pas s'appeler .env.txt (extensions masquées)

    Relancez le script depuis le bon dossier :

    bash
    cd "C:\Users\VotreNom\Desktop\GitNotate"
    python gitnotate_v6.7.py

🔴 Erreur 401 / 403 Notion

Cause : Token invalide ou intégration non invitée sur la page/base.

Solution :

    Vérifiez que NOTION_TOKEN commence par secret_

    Important : Invitez l'intégration sur CHAQUE page/base utilisée :

        Ouvrez la page source dans Notion

        Menu ⋯ (en haut à droite) → Connections → Connect to → Sélectionnez votre intégration

        Répétez pour la base de données

🔴 Erreur Rate Limit GitHub

Cause : Limite de requêtes API GitHub atteinte.

Solution :

    Sans token : 60 requêtes/heure (très limité)

    Avec token : 5000 requêtes/heure

    Le script attend automatiquement si la limite est atteinte (message affiché)

    Activez le cache : CACHE_ENABLED=true pour réduire les requêtes

🐌 Script très lent ?

Causes possibles :

    Cache désactivé

    Trop de workers (surcharge)

    Traduction IA activée mais lente

Solutions :

bash
# Configuration optimale dans .env
CACHE_ENABLED=true          # Active le cache 24h
MAX_WORKERS=5               # Équilibre vitesse/stabilité
MIN_UPDATE_DAYS=180         # Ignore les vieux projets (6 mois)
TRANSLATION_ENABLED=true    # Mais utilise détection auto langue

Performances attendues :
Configuration	Vitesse	Commentaire
Baseline (sans cache, sans filtre)	8-10 repos/sec	Première exécution
Avec cache (2ème run même jour)	15-20 repos/sec	+50-100% vitesse
Avec MIN_UPDATE_DAYS=180	12-15 repos/sec	Moins de repos traités
DRY_RUN=true	25-30 repos/sec	Pas d'écriture Notion
🔄 Doublons persistants ?

Si vous voyez toujours des doublons malgré le script :

    Variantes d'URL : Certains repos ont plusieurs URLs valides

        Exemple : github.com/user/repo vs github.com/user/repo/

        Le script normalise ces cas, mais pas les redirections GitHub

    Lancement du nettoyeur :

    bash
    python clean_page_duplicates.py

    Doublons dans le texte : Le script ne peut pas supprimer automatiquement les liens inclus dans des paragraphes. Vous devrez les retirer manuellement.

🛑 Erreur : Schema Database - Propriétés manquantes

Cause : La base de données existante n'a pas toutes les colonnes requises.

Solution 1 (Recommandé) : Laissez GitNotate créer une nouvelle base :

bash
# Dans .env, supprimez ou commentez :
# DATABASE_ID=

Solution 2 : Ajoutez manuellement les colonnes manquantes listées dans l'erreur.
📈 Statistiques et Historique

Chaque exécution sauvegarde des statistiques dans gitnotate_stats.json (historique des 50 dernières runs).

Exemple gitnotate_stats.json :

json
[
  {
    "timestamp": "2026-01-14 20:15:43",
    "duration_seconds": 154,
    "repos_processed": 67,
    "success_count": 54,
    "error_count": 0,
    "skipped_count": 13,
    "translation_success_rate": 88.9,
    "model_used": "openai/gpt-3.5-turbo",
    "dry_run": false
  }
]

🔐 Sécurité & Bonnes Pratiques

    Ne commitez JAMAIS le fichier .env sur GitHub

        Ajoutez .env dans .gitignore

    Tokens à durée limitée :

        Régénérez vos tokens régulièrement

        Utilisez des tokens avec le minimum de permissions nécessaires

    Sauvegarde Notion :

        Notion garde un historique (corbeille), mais faites des exports réguliers

    Test avant production :

        Utilisez toujours DRY_RUN=true avant une première exécution

        Testez sur une page/base Notion de développement

🆕 Changelog
v6.7.0 (2026-01-14)
🚀 Nouvelles Fonctionnalités

    ✅ Cache GitHub intelligent (24h) - Économise 50% des appels API

    ✅ Script dédié clean_page_duplicates.py - Nettoie les doublons dans la page source

    ✅ Mode DRY_RUN - Simulation complète sans écriture

    ✅ Filtre d'ancienneté MIN_UPDATE_DAYS - Ignore les projets abandonnés

    ✅ Détection langue automatique - Économise crédits IA

    ✅ Barre de progression avec ETA

    ✅ Historique stats JSON (50 dernières exécutions)

🔧 Améliorations

    Gestion robuste des rate limits GitHub (wait automatique)

    Validation tokens au démarrage (fail-fast)

    Normalisation URLs GitHub améliorée

    Pool HTTP par thread (meilleure performance)

    Idempotence renforcée (préchargement URLs existantes)

🐛 Corrections

    Fix : Crash si README indisponible

    Fix : Timeout sur repos volumineux

    Fix : Encodage UTF-8 pour caractères spéciaux

📞 Support

    Documentation : Ce guide

    Issues : Consultez les logs d'erreur détaillés dans la console

    Contribution : Projet personnel, suggestions bienvenues

📜 Licence

Projet personnel - Utilisation libre pour vos besoins de veille technologique.

Version : 6.7.0
Date : 14 Janvier 2026
Auteur : LeProfConnecté
Statut : ✅ Production-Ready