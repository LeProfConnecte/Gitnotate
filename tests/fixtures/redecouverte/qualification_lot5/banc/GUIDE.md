# Guide d'étiquetage du banc d'états (rédacteurs et analystes)

Texte remis tel quel aux rédacteurs et aux analystes, qui n'avaient accès à aucun fichier ni programme.

## Champs de fiche

Contexte : un outil personnel retrouve des dépôts GitHub enregistrés dans des fiches (Notion). Chaque fiche a des champs : Description (souvent rédigée en français par un LLM, 1 à 3 phrases), Cas d'usage, Installation, Exemple, Prérequis (souvent recopié mot pour mot d'un README anglais, en liste à puces « - … », une technologie ou une condition par ligne), Notes (saisies par l'utilisateur, français ou anglais). L'utilisateur peut chercher un dépôt SANS une technologie (« un OCR sans GPU », « des workflows sans n8n », « an OCR without Docker »). Pour chaque champ qui cite la technologie, on veut savoir ce qu'il en dit.
Technologies (clé : formes qui la désignent dans un texte) : gpu (GPU, CUDA, VRAM, carte graphique, graphics card, NVIDIA RTX, GeForce ; pas « NVIDIA » seul ni une clé d'API NVIDIA) ; docker (Docker, docker compose, Dockerfile ; pas Podman) ; kubernetes (Kubernetes) ; windows ; linux ; macos (macOS) ; n8n ; zapier ; react (React ; « React Native » est une variante) ; fastapi (FastAPI) ; claude_code (Claude Code).
Étiquette, pour TOUT le texte du champ et la technologie indiquée (si plusieurs mentions, ce que le texte dit au total) :
- requis : le texte dit clairement que le projet a besoin de cette technologie pour fonctionner normalement : prérequis ou exigence écrite, « ne fonctionne pas sans », élément d'une liste de prérequis qui est la technologie elle-même (« - NVIDIA GPU with 8 GB VRAM », « - Docker 24+ ») ; pour un produit (n8n, Zapier, React, FastAPI, Claude Code) : le dépôt est fait pour lui ou en dépend (nœud n8n, workflows n8n, composants React, plugin pour Claude Code, gabarit FastAPI).
- non_requis : le texte dit clairement qu'elle n'est pas nécessaire : absente ou explicitement non requise, facultative, seulement recommandée, un autre chemin normal existe (le CPU pour un GPU), seulement pour les tests ou le développement, ou le dépôt est une alternative à ce produit.
- mention : le texte cite la technologie sans trancher : une option parmi d'autres équivalentes (« Windows, macOS ou Linux », « Docker ou Podman », « Docker ou pip »), une intégration proposée en plus du produit principal, une exigence qui ne vaut que pour une fonction, un mode ou une version secondaire (« l'accélération GPU nécessite CUDA », « le mode hors ligne nécessite un GPU »), une variante qui n'est pas la technologie (« Docker Desktop n'est pas nécessaire »), une image ou une commande citée sans dire si elle est exigée, ou une phrase vraiment ambiguë.
En cas de doute entre requis et mention : mention. Entre non_requis et mention : mention. Ne te demande pas ce qu'un programme lirait : juge comme un lecteur humain attentif.

## Requêtes

Contexte : un outil personnel retrouve des dépôts GitHub enregistrés dans des fiches. L'utilisateur tape un besoin en français ou en anglais (« un OCR pour factures scannées sans GPU », « I can't find the n8n workflow I saved to sync my CRM »). Technologies reconnues (clés) : gpu (GPU, CUDA…), docker, kubernetes, windows, linux, macos, n8n, zapier, react, fastapi, claude_code (Claude Code).
Pour chaque technologie citée dans la requête, son rôle :
- cherche : l'utilisateur veut des dépôts qui la concernent, comme objet (« des workflows n8n », « a React component library ») ou comme environnement (« un OCR sous Docker », « workflows running on n8n », « je ne retrouve plus le dépôt n8n » : il cherche bien un dépôt n8n).
- exclu : il veut des dépôts qui ne l'utilisent pas ou ne l'exigent pas (« sans Docker », « I don't want n8n », « Docker n'est pas autorisé chez nous », « no GPU on my laptop »).
- reference : c'est le produit qu'il veut remplacer (« une alternative à Zapier », « something like n8n but open source », « remplacer Zapier »).
- neutre : ni l'un ni l'autre (indifférent : « peu importe React ou Vue », « I don't mind Docker » ; ou citée sans rapport avec ce qu'il cherche).
Et les termes clés : 1 à 3 mots ou expressions de la requête (recopiés tels quels) qui désignent ce qu'il cherche et doivent rester cherchés (« OCR », « factures », « workflow », « component library »), hors technologies.

## Consigne commune

N'ouvre AUCUN fichier : ni le dépôt Gitnotate, ni /tmp, ni le dossier lot5, ni aucun code ou test. Écris de mémoire, d'après ta connaissance des README, fiches et requêtes réelles. Ne lance aucun programme.
