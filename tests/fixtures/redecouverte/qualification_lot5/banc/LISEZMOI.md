# Banc d'états indépendant (lot 5)

Mesure de la lecture des exclusions, hors du classement : pour un champ de fiche qui cite une technologie, l'état
lu par le moteur (requis, non requis, mention) ; pour une requête, le rôle de chaque technologie citée (cherche,
exclu, reference, neutre). Méthode et résultats : `docs/QUALIFICATION_LOT5.md` § 6, « Banc indépendant ».

## Protocole

1. Rédaction et étiquetage par des agents sans accès à aucun fichier ni programme (ni le moteur, ni les tests, ni
   les revues), d'après le seul `GUIDE.md`. Chaque lot est rédigé par un agent, puis étiqueté à nouveau par un
   second agent qui ne voit pas les étiquettes du premier. Seuls les éléments où les deux s'accordent sont gardés
   (`brut_*.json` conserve tout, rédaction et contre-étiquetage).
2. Premier jeu (lots F1 à F4, Q1) : 415 champs et 149 requêtes, coupés en deux moitiés par l'empreinte de
   l'identifiant (SHA-256 pair : `banc_dev.json`, impair : `banc_t1.json`). La moitié dev a servi à corriger le
   moteur ; t1 a été mesurée une fois sur toutes les versions avant d'être regardée, puis a servi à son tour.
3. Second jeu (lots G1 à G4, Q2), rédigé par d'autres agents sur d'autres domaines : 360 champs et 139 requêtes
   (`banc_t2.json`). Mesuré une seule fois, code figé (c3f4747 de la branche d'essai) ; il n'a servi à aucune
   correction.

## Fichiers et empreintes (SHA-256)

| Fichier | Contenu | Empreinte |
|---|---|---|
| `brut_t1.json` | lots F1-F4, Q1 : rédaction et contre-étiquetage | `0fc60fe0…ae245` |
| `banc_dev.json` | 204 champs, 80 requêtes | `9617afeb…a6bc7` |
| `banc_t1.json` | 211 champs, 69 requêtes | `9ec79918…10f6e` |
| `brut_t2.json` | lots G1-G4, Q2 : rédaction et contre-étiquetage | `3fecd992…fbe6c` |
| `banc_t2.json` | 360 champs, 139 requêtes | `3ca7bfa4…1a3e7` |
| `versions/` | code des versions mesurées, en patchs enchaînés | ci-dessous |

`tests/test_redecouverte_banc.py` vérifie ces empreintes, l'absence de recouvrement entre les parties, et fige les
mesures du code (exacts, faux « requis », « requis » justes et trouvés ; rôles justes).

## Versions mesurées

Les versions du tableau (`docs/QUALIFICATION_LOT5.md` § 6) sont des commits d'une branche d'essai locale, non
publiée. Leur code (`redecouverte.py`, `redecouverte_lexique.py`) est conservé dans `versions/` sous forme de patchs
unifiés enchaînés : `1_fe9fdeb.patch` s'applique à `f68b656`, chacun des suivants à la version précédente, et
`6_c3f4747.patch` donne le code de cette branche. `test_versions_du_banc_reproductibles` refait la chaîne et
vérifie l'empreinte de chaque version (16 premiers caractères du SHA-256 des deux fichiers, comme pour
`../variantes/`).

| Version | Étape | Empreinte |
|---|---|---|
| fe9fdeb | corrections de la troisième revue | `dba417ef5c615e10` |
| de04315 | quatrième revue et jugements complémentaires | `392a52be81aa256c` |
| d4ffc83 | cinquième revue | `6fecb28fd86c551c` |
| f8ae513 | sixième revue | `8f26f81fea7e68ba` |
| eb8106f | banc, partie dev | `923d79cd8a75a4a8` |
| c3f4747 | banc, parties dev et t1 (code final) | `18b9cf152f2ed425` |

Remesurer une version : dans une copie de travail de cette branche (`git -c core.autocrlf=false worktree add
../version HEAD`), remplacer les deux fichiers par ceux de la version (patchs appliqués dans l'ordre à ceux de
`f68b656`, par exemple avec `appliquer_patch` de `tests/redecouverte_outils.py`), puis lancer
`python -m pytest tests/test_redecouverte_banc.py -k mesures` : l'assertion qui échoue affiche, à gauche, les
mesures de la version (exacts, faux « requis », « requis » justes, « requis » trouvés ; rôles justes, rôles).
