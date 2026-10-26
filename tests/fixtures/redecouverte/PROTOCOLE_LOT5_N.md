# Protocole du jeu indépendant, lot 5

## Conditions de rédaction

- Un seul rédacteur, indépendant du moteur. Il n'a lu aucun fichier du dépôt Gitnotate (code, tests, documentation, lexique, jeux existants). Il n'a exécuté aucun moteur de recherche et n'a vu aucun résultat.
- Seule source lue : `entrees/CORPUS_62_LISIBLE.md`, le texte intégral des 62 fiches existantes.
- Seul outil exécuté : `outils/supplement_vers_capture.py`, pour valider la forme du supplément. Sa sortie a été supprimée aussitôt. L'outil a répondu « 30 fiches ajoutées à 62 ».
- Ordre de travail : fiches supplémentaires d'abord, puis requêtes, puis jugements. Les jugements portent sur le corpus combiné (62 fiches existantes et 30 fiches fictives).

## Fiches supplémentaires (`supplement_fiches.json`)

- 30 fiches fictives, de P01 à P30. Leurs dépôts s'appellent `synth-<organisation>/<nom>`.
- Elles sont écrites dans le style des fiches v7.3+ : description en français, cas d'usage concrets, installation plausible, prérequis tels qu'un README les donnerait, justification courte. Les catégories et les valeurs « Brique pour » sont reprises de l'en-tête du corpus.
- Elles couvrent :
  - l'écosystème n8n et Zapier : modèles, supervision, nœud communautaire, plateforme alternative, moteur en code, migration, intégration Zapier, mentions en passant ;
  - Docker et Kubernetes : tableau de bord, outil livré uniquement en image Docker, outil explicitement sans Docker, opérateur ;
  - FastAPI : gabarit, framework concurrent ;
  - React : bibliothèque de composants, alternative sans React ;
  - Claude Code : skills, hooks, agent concurrent ;
  - Tesseract, technologie choisie en plus : prétraitement, outil qui s'appuie sur lui ;
  - la recherche sémantique : 2 outils sur le code, 2 outils sur des documents ou des PDF ;
  - le matériel : GPU NVIDIA requis, CPU explicite, GPU facultatif, rien n'est dit (prérequis vides) ;
  - quelques thèmes du profil : Notion, IFC et métré, transcription.
- L'identifiant technique apparaît à des endroits variés : nom, description, cas d'usage, prérequis, installation, justification. Chaque fiche décrit honnêtement ce que ferait un tel dépôt. Aucune n'a été taillée contre un algorithme particulier.

## Requêtes et jugements (`requetes_independantes_lot5.json`)

- 40 besoins, de N01 à N40, formulés comme l'utilisateur les écrirait, en français ou en anglais.
- Chaque requête reçoit trois niveaux de jugement :
  - `en_tete` (gain 2) : le dépôt répond directement au besoin, d'après le texte de sa fiche ;
  - `acceptables` (gain 1) : réponse partielle, brique à assembler, ou réponse plausible dont un critère n'est pas documenté ;
  - `a_exclure` : un appariement naïf de mots pourrait proposer le dépôt, mais sa fiche contredit le besoin (outil qui exige ce que la requête exclut, extension de l'outil que la requête veut remplacer, traitement inverse de celui demandé, etc.).
- Règle sur l'information inconnue : une fiche qui ne dit rien d'une contrainte (matériel, Docker…) n'est jamais classée `a_exclure` pour cette contrainte. Elle reste `acceptables` si elle répond au reste du besoin.
- « Facultatif » ou « conseillé » ne vaut pas « requis ». Un GPU facultatif est compatible avec « sans GPU ». Un GPU seulement conseillé n'est classé dans aucune liste.
- Un dépôt hors sujet mais sans contradiction n'est classé dans aucune liste (gain 0).
- `aucun_fort: true` signifie qu'aucun dépôt du corpus combiné ne répond. Les listes `en_tete` et `acceptables` sont alors vides.
- Chaque dépôt jugé a une raison d'une phrase, qui contient au moins une courte citation verbatim de sa fiche entre « ». Une vérification automatique a confirmé :
  - que toutes les citations figurent dans le texte des fiches concernées ;
  - que toutes les clés de dépôt existent ;
  - que les trois listes ne se recoupent pas.
- Les clés sont celles des titres « ## » du corpus, en minuscules. Les fiches sans dépôt sont ignorées.

## Répartition

| Thème | Nombre | fr | en | Rôles |
|---|---|---|---|---|
| identifiants (n8n, Zapier) | 10 | 5 | 5 | cible 3 · contexte 3 · reference 2 · exclusion 2 |
| technologies (Docker, Kubernetes, FastAPI, React, Claude Code, Tesseract) | 10 | 5 | 5 | cible 5 · reference 3 · contexte 1 · exclusion 1 |
| semantique (code ou documents) | 6 | 3 | 3 | contexte 1 · aucun rôle 5 |
| exclusions (sans GPU, sans Docker, sans Kubernetes, pas pour / not for) | 6 | 3 | 3 | exclusion 4 · aucun rôle 2 |
| sans_reponse | 4 | 2 | 2 | aucun rôle |
| generique (OCR, enseignement, finance, vidéo) | 4 | 2 | 2 | aucun rôle |
| **Total** | **40** | **20** | **20** | cible 8 · contexte 5 · reference 5 · exclusion 7 · aucun rôle 15 |

Pour n8n et Zapier, chaque rôle compte au moins une requête en français et une en anglais.

## Limites

- **Fiches fictives.** Les 30 fiches supplémentaires décrivent des dépôts inventés. Elles sont plausibles, mais plus nettes que les fiches réelles, qui sont souvent lacunaires ou génériques. Les mesures obtenues sur elles peuvent donc être optimistes.
- **Un seul rédacteur.** Aucun accord inter-annotateurs n'a été mesuré. La frontière entre `acceptables` et neutre, et entre neutre et `a_exclure`, reste un jugement personnel.
- **Biais de construction.** Le même rédacteur a écrit les fiches et les requêtes : le vocabulaire des requêtes peut être plus proche de celui des fiches qu'il ne le serait en usage réel. Les formulations ont été variées pour limiter cet effet.
- **Jugements sur le texte seul.** Les fiches existantes ont été jugées sur leur seul texte, sans connaissance extérieure des projets. Par exemple, une fiche Tesseract qui ne dit rien du matériel est traitée comme « inconnu ».
- **Rôle unique.** Le champ `role_identifiant` retient un seul rôle par requête, même quand deux technologies y jouent des rôles différents.
- **Petit échantillon.** Avec 4 à 10 requêtes par thème, les écarts d'un thème à l'autre restent indicatifs.
