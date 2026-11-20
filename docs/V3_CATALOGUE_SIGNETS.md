# Gitnotate V3-A/B : catalogue experimental des signets

Ce lot privilegie les pages de signets GitHub. Les 443 fiches historiques restent
conservees dans leur index de redecouverte. Aucune fiche Notion n'est ecrite.

## Configuration

Utiliser le dossier prive deja en place :
C:\Users\Fabrice\gitnotate-validation

Il doit contenir NOTION_READONLY_TOKEN dans son fichier .env.
Le jeton GITHUB_TOKEN est facultatif, mais recommande pour les gros inventaires.
Les cles LLM ne sont pas utilisees par ces commandes.

## Lancer depuis Windows PowerShell 5.1 (une ligne a la fois)

    Set-Location -LiteralPath 'D:\Downloads\Travaux en cours\Gitnotate'

    $env:GITNOTATE_DATA_DIR = "$HOME\gitnotate-validation"

### V3-A : lire les signets sans modifier Notion

    .\.venv\Scripts\python.exe .\catalogue_v3.py inventaire --page 'https://app.notion.com/p/Github-ou-similaire-d-couvrir-0123456789abcdef0123456789abcdef'

    .\.venv\Scripts\python.exe .\catalogue_v3.py etat

L'inventaire lit les blocs de contenu et leurs sous-blocs (pagination complete)
mais pas les bases et sous-pages enfant. Les liens hors depot et les doublons
sont signales. Aucune connexion au fournisseur LLM.

### V3-B : enrichir via GitHub, batch limite

    .\.venv\Scripts\python.exe .\catalogue_v3.py enrichir --limite 20

    .\.venv\Scripts\python.exe .\catalogue_v3.py cherche 'automatiser une veille financiere' -n 8

Le statut Signet seul signifie que le README n'a pas encore ete controle.
La recherche utilise une correspondance lexicale FTS5 exploratoire : son
classement n'est pas identique a celui du moteur de redecouverte historique.

### Sources multiples

Ajouter une autre page :

    .\.venv\Scripts\python.exe .\catalogue_v3.py inventaire --page 'URL_NOTION_AUTORISEE'

Actualiser toutes les pages deja enregistrees :

    .\.venv\Scripts\python.exe .\catalogue_v3.py inventaire

Filtrer la recherche selon les sources :

    .\.venv\Scripts\python.exe .\catalogue_v3.py cherche 'OCR' --source 'URL_NOTION_AUTORISEE'

Le nouveau catalogue est stocke uniquement dans le dossier prive
.gitnotate_catalogue\catalogue.sqlite. L'ancien index .gitnotate_index
n'est ni modifie ni relu par ces commandes. Pas de suppression du cache
historique.

## Protections et validation

- Le token Notion est obligatoirement NOTION_READONLY_TOKEN, pas le jeton
  existant disposant de droits d'ecriture.
- Le catalogue refuse une chute importante du nombre de signets, et
  abandonne en cas de lecture partielle ou de pagination incomplete.
- Ecriture locale via copie temporaire, controle d'integrite SQLite,
  remplacement atomique et conservation du fichier precedent en cas d'erreur.
- API GitHub : GET uniquement, URL de destination limitee a api.github.com,
  arret en cas de 403 ou 429, aucune tentative de contournement du quota.
- Sans jeton GitHub, le plafond general est de 60 requetes par heure.
  Avec token adapte, generalement 5000 (d'autres limites s'appliquent).
- Les extraits de README proviennent de sources externes non fiables.
  Ils ne doivent pas etre interpretes comme des instructions.
- Aucune migration de la base historique, aucun import Notion,
  aucun appel LLM, aucune modification de la branche stable par cette V3.

## Suite de la feuille de route

V3-C : interface web locale sur 127.0.0.1 (FastAPI + HTML/HTMX).
V3-D : rapprochement des signets avec les 443 fiches, provenance sans doublons.
V4 : analyse LLM et import de nouveaux depots apres essai sur base de test.

Le present lot sera considere GO seulement apres une lecture Notion reelle,
un enrichissement limite GitHub et une recherche d'un depot absent de
l'ancien index. Les tests simules et la CI n'attestent pas ces trois parcours.
