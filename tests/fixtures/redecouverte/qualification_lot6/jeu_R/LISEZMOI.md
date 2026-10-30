# Jeu R (lot 6) — corpus historique de non-régression

Ce dossier contient 11 fichiers historiques figés et ce `LISEZMOI.md`. Seul ce `LISEZMOI.md` est de la documentation
ajoutée après coup : il n'appartient à aucun gel et peut être corrigé. Les 11 autres fichiers sont conservés à
l'octet près (`.gitattributes` : `-text`) et contrôlés par `tests/test_lot6_jeu_r.py`.

## Statut : jeu consommé, non indépendant

Le jeu R (besoins R01-R48, 24 fiches fictives) a été écrit le 2026-10-27 pour juger une variante du moteur (la « v2 »
du lot 6, qui ignorait « partir » dans « à partir de »). Il a servi à cette décision : la v2 a été **refusée** (deux
régressions confirmées, R06 et R10, aucune amélioration confirmée) et n'est pas intégrée. Le moteur stable reste
celui de `9aa4c6e`.

Ses résultats sont donc connus de l'équipe du moteur. Le jeu R est désormais un **corpus historique de
non-régression** du moteur stable, et **pas** un jeu de validation indépendante :

- il ne doit pas servir à valider, choisir ou régler une nouvelle variante du moteur ou du lexique ;
- un gain mesuré sur R n'est pas une preuve d'amélioration ; une nouvelle variante demande un nouveau jeu,
  figé avant toute exécution (même démarche que les lots 4, 5 et 6).

## Contenu et gels

| Fichier | Rôle | Gel |
|---|---|---|
| `supplement_R.json` | 24 fiches fictives v7.3+ (format `gitnotate-lot6-supplement/1`) | 1 |
| `requetes_R.json` | 48 besoins, jugements et rôles des technologies du juge W2 | 2 |
| `DECISIONS_LOT6_R.md` | règles de décision écrites avant toute exécution du moteur | 2 |
| `contre_R.json` | contre-jugement du juge X | 3 |
| `A_QUALIFIER_R.json` | couples à qualifier (5 premiers et « forte » des deux versions) | 4 |
| `analyste_A.json`, `analyste_B.json` | qualifications à l'aveugle (251 couples chacune) | 4 |
| `EMPREINTES_GEL1.sha256` à `EMPREINTES_GEL4.sha256` | empreintes datées des gels (UTC, 2026-10-27) | — |

Les gels ont été écrits sur la copie de travail du jeu (`sorties/…`, `consignes/…`, `journaux/…`) : leurs chemins ne
sont pas ceux de ce dossier, et ils citent aussi des fichiers non versionnés ici (consignes, transcripts, capture),
conservés dans l'archive source. Le test compare les empreintes par nom de fichier.

## Provenance

- Branche source : `lot6-essai` (locale, jamais publiée), commit d'ajout
  `db3e4948190a52a943217b1e6fae05da1d19b3ff`, tête `2822cc1a1674a7007251436d95f0b4bbc202812b`.
- Archive source : `archive_lot6_v2_20261027.zip`, SHA-256
  `8b27fc4178c574805887a00bad17150a221628328dfcfce240d29b9c7d4a9ced` ; son `MANIFESTE.sha256` a pour SHA-256
  `a1f64cbdb21f146ebe29e409a2e962516bc25ad9bffc1273e5d36da0e75e819f`. Les 11 fichiers sont repris de
  `code/tests/fixtures/redecouverte/qualification_lot6/jeu_R/` et sont identiques à l'octet à ceux de `jeu_R/` dans
  la même archive et aux objets de `lot6-essai`.
- Protocole : `PROTOCOLE_R.md`, SHA-256 `69c88b5fdc4d0b9d3a05b63e4795129df7bb14bed66fe4563bc9eb76de1c3d9a`
  (épinglé dans `jeu_R/EMPREINTES_COMPLEMENT.sha256` de l'archive). Il n'est **pas** versionné ici : il cite des
  identifiants de sessions de travail. Il reste dans l'archive, avec ses notes, les consignes et les transcripts.

## Ce que vérifie le test

Index : corpus synthétique, suppléments N et M du lot 5 et fiches de `supplement_R.json`. Les valeurs attendues sont
celles du moteur stable `9aa4c6e` (calculées le 2026-10-27, `jeu_R/valeurs_test_ref.json` de l'archive) : nDCG@10,
MRR, P@5, R@5, intrus@3 et intrus@5 selon W2 et selon X, violations « aucun_fort », décomptes de la qualification
à l'aveugle (A et B) et lecture des rôles des technologies. Les valeurs de la v2 refusée n'y figurent qu'en
commentaire historique.

## Réviser une baseline

Un écart sur ce jeu signale un changement de comportement du moteur : c'est un échec à expliquer, pas une valeur à
recopier. Une valeur attendue ne peut être révisée qu'aux conditions suivantes, toutes remplies :

1. le changement du moteur est voulu, décidé et validé ailleurs que sur R (jeu nouveau, figé avant exécution) ;
2. l'écart est expliqué besoin par besoin, et tout couple nouveau des 5 premiers ou en « forte » est qualifié à
   l'aveugle par deux analystes isolés avant d'être compté (le test échoue par `KeyError` sur un couple non qualifié) ;
3. la révision ne touche que les valeurs attendues du test, dans un commit distinct qui en donne la raison ;
   les 11 fichiers figés, leurs gels et les jugements ne sont jamais modifiés.
