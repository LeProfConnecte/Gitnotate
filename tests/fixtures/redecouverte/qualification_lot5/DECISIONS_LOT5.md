# Lot 5 — règles de décision fixées AVANT toute exécution sur le jeu indépendant N01-N40

Écrit le 2026-10-25, après les mesures synthétiques (82 requêtes déjà utilisées : non-régression seulement) et avant
d'avoir lu ou exécuté `jeu_independant/requetes_independantes_lot5.json` (sha256 691bb8b3…d1d8) et son supplément de
30 fiches (sha256 ff3e03dd…98b8). Code figé : `VARIANTES_CODE.txt` (empreintes), branche locale `lot5-essai` 8e3308b.

## Variantes mesurées (même index : 62 fiches synthétiques + 30 fiches du supplément)
ref (f68b656) · P01, P02, P03 (patches de l'archive) · L1 (recherche de code sémantique : notion voisine +
composition) · L2 (identifiants selon leur rôle) · L23 (L2 + exclusions requis/non requis/inconnu) · L12 · L123.

## Règles
1. Partie 1 contre patch 01. Retenir L1 si, sur N01-N40 : nDCG@10 et R@5 ≥ ref ; aucun dépôt « en tête » présent
   dans les 5 premiers de ref n'en sort ; sur les requêtes documents/PDF du thème « semantique », aucun outil de
   code ne monte au-dessus de sa place dans ref. Entre L1 et P01 : préférer celui qui ne dégrade aucune requête
   documents/PDF ; à égalité, celui qui a le meilleur nDCG@10 sur les requêtes « code ». Si les deux régressent :
   rejeter les deux.
2. Partie 2. Retenir si, sur N01-N40 : nDCG@10, MRR et R@5 ≥ ref ; aucune requête où un dépôt « en tête » sort
   des 5 premiers par rapport à ref sans gain compensateur sur la même requête ; « forte » injustifiées (double
   qualification aveugle) pas plus nombreuses que dans ref.
3. Partie 3. Retenir si aucun dépôt jugé pertinent (en tête ou acceptable) n'est déclassé hors des 5 premiers par
   un état « requis », sur N01-N40 comme sur les 82 synthétiques ; intrus@5 des requêtes d'exclusion ≤ ref.
4. Global : qualification exhaustive des 5 premiers (pertinent / plausible / hors sujet) en double aveugle, sans
   étiquette de variante ; la part de hors sujet dans les 5 premiers et le nombre de « forte » injustifiées de la
   version retenue ne doivent pas dépasser ceux de ref.
5. Régression : retirer uniquement la partie responsable, sans réglage sur N01-N40. Toute modification faite après
   lecture des résultats est signalée comme telle et ne compte pas comme validée par ce jeu.
6. V01-V22 et S01-S10 (base réelle de 443 fiches) : non rejouables ici, la capture n'a pas été fournie ; commandes
   de reproduction locale dans le rapport. Les mesures de l'archive restent celles de ChatGPT, non vérifiées ici.
