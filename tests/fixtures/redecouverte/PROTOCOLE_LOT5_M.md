# Protocole du jeu de validation M (lot 5)

## Méthode
- Rédacteur indépendant : aucun fichier du dépôt Gitnotate (code, tests, lexique, docs), aucun jeu antérieur (jeu_independant, mesures_N, dev) n'a été lu ; aucun moteur n'a été exécuté. Seule source : `entrees/CORPUS_92_LISIBLE.md`.
- Étape 1 : rédaction de 21 fiches fictives nouvelles (P31 à P51, dépôts `synth-…`), au style des fiches v7.3+ du corpus, sans viser un algorithme. Forme validée par `outils/supplement_vers_capture.py` (sortie temporaire supprimée).
- Étape 2 : rédaction de 30 besoins (M01 à M30), puis jugement de chaque besoin contre le corpus combiné (92 fiches + 21) d'après le seul texte des fiches, avant toute exécution.
- Étape 3 : relecture manuelle de chaque jugement contre les fiches existantes, puis contrôle automatique (script passé par stdin, sans fichier) : clés existantes, citations retrouvées mot pour mot, listes disjointes, raison pour chaque dépôt jugé, cohérence de `aucun_fort` avec le thème.

## Règles de jugement
- `en_tete` (gain 2) : répond directement au besoin, contraintes comprises.
- `acceptables` (gain 1) : répond en partie (besoin voisin, intégration à faire soi-même, ou contrainte non documentée).
- `a_exclure` : rapprochement lexical tentant mais contraire au besoin (autre rôle de la technologie, autre type de contenu, contrainte violée).
- Fiche non citée : sans rapport, gain 0, sans pénalité particulière.
- Rôle d'une technologie nommée : cible (l'outil est fait pour elle), environnement (l'utilisateur l'a déjà), référence (à remplacer : les outils qui en dépendent sont à exclure), exclusion (à éviter).
- Contraintes : « requis » écrit dans la fiche → `a_exclure` si la demande l'exclut ; « facultatif » ou « inutile » → compatible ; non mentionné → information inconnue, jamais traitée comme une incompatibilité (au mieux `acceptables` quand une autre fiche l'affirme explicitement).
- `aucun_fort: true` seulement si aucune fiche ne répond ; `en_tete` et `acceptables` sont alors vides.
- Clés : `proprietaire/nom` en minuscules, tirées des titres `##` ; fiches sans dépôt et titre à trois segments ignorés ; plusieurs fiches d'une même clé sont jugées ensemble.
- Chaque raison contient une citation verbatim courte entre « ».

## Répartition
| Thème | Nombre | FR | EN |
|---|---|---|---|
| roles | 9 | 5 | 4 |
| semantique | 6 (dont 2 avec négation) | 3 | 3 |
| exclusions | 6 | 3 | 3 |
| sans_reponse | 3 | 1 | 2 |
| generique | 6 | 3 | 3 |
| Total | 30 | 15 | 15 |

Rôles dans le thème roles : cible 2, environnement 3, reference 2, exclusion 2. Sur l'ensemble des 30 : cible 2, environnement 4, reference 3, exclusion 8, null 13.

## Limites
- Un seul rédacteur : pas d'accord inter-annotateurs ; la frontière en_tete / acceptables reste un jugement.
- Les fiches fictives sont écrites par le même rédacteur que les requêtes : risque de formulations proches ; atténué en paraphrasant les besoins et en jugeant aussi les 92 fiches existantes.
- Les jugements reposent sur le texte des fiches et non sur les dépôts réels ; une fiche pauvre (README non vérifié) est jugée sur ce qu'elle dit.
- Les listes `a_exclure` ne sont pas exhaustives : elles retiennent les rapprochements naïfs les plus probables.
- Deux fiches nouvelles ne sont jugées dans aucune requête ; elles servent de distracteurs.
