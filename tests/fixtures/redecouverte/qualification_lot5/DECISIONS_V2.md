# Lot 5 — version 2 : règles fixées AVANT toute exécution sur le jeu de validation M01-M30

Écrit avant la livraison du jeu M (rédacteur aveugle distinct, nouvelles fiches P31+). La version 2 a été construite
APRÈS lecture des résultats du jeu N (N05, N03, N32) : ses mesures sur N sont optimistes et ne valent pas validation.
Code figé : VARIANTES_V2_CODE.txt (V2a = parties 2 v2 + 3 + patch 01 ; V2b = parties 1 (composition hors négation)
+ 2 v2 + 3 ; V2c = parties 2 v2 + 3 sans changement sémantique). Comparées à ref (f68b656) et P01 (patch 01 seul,
retenu par les règles de DECISIONS_LOT5.md sur N, sous réserve de la qualification).

R1. Sur M : nDCG@10, MRR et R@5 ≥ ref ; intrus@5 ≤ ref.
R2. Sur M : aucun dépôt « en tête » présent dans les 3 premiers de ref ne sort des 5 premiers ; requêtes dont le
    nDCG@10 baisse de plus de 0,05 pas plus nombreuses que celles où il monte de plus de 0,05.
R3. Exclusions : aucun dépôt jugé pertinent (en tête ou acceptable) déclassé hors des 5 premiers par un état
    « requis », sur M, N et les 82 synthétiques.
R4. Qualification exhaustive en double aveugle des 5 premiers (et de toute « forte ») de chaque variante, sur N et M,
    sans étiquette de variante : part de hors sujet dans les 5 premiers et « forte » non pertinentes ≤ ref.
R5. Choix : V2b si elle satisfait R1-R4 et que son nDCG@10 sur le thème « semantique » de M est ≥ celui de V2a ;
    sinon V2a si elle satisfait R1-R4 ; sinon V2c ; sinon P01 seul s'il satisfait R1 et R4 sur M ; sinon rien.
R6. Après lecture de M, aucun réglage. Une régression attribuable à une sous-partie conduit à la retirer ; la version
    obtenue est alors signalée comme non validée par un jeu indépendant.
