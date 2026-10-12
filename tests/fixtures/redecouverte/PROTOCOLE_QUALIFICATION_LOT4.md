# Qualification indépendante du moteur de redécouverte — lot 4

## État

- Référence GitHub étudiée : `a679661a2fcadd9ce07cb6d63d947b1740aeb2c8`.
- Jeu de qualification : `requetes_independantes_lot4.json`.
- 26 requêtes écrites à partir des fiches **synthétiques**, avant toute exécution du moteur sur ce nouveau jeu.
- Empreinte SHA-256 du fichier de référence : `e32f0fc29e75d5db4eef45e2f018ad148004cc941f4a6d5947dfeba6fcb8e6e7`.
- Le jeu contient 4 requêtes sans réponse pertinente connue, destinées à mesurer les faux positifs.

## Méthode recommandée

1. Geler ce jeu (ne jamais ajuster ses résultats attendus en fonction de la sortie du moteur).
2. Construire l'index à partir du corpus synthétique existant selon la procédure du dépôt (vérifier le format de capture attendu avant le rejeu).
3. Exécuter `python scripts/evaluer_redecouverte.py <CHEMIN_DU_FICHIER_JSON> --details` avec le même index, avant/après correctifs ; enregistrer les classements et leurs explications.
4. Vérifier le comportement de chaque requête sans réponse attendue : aucune correspondance forte ne doit être affirmée sans preuve pertinente. Les listes `a_exclure` sont des exemples et ne couvrent pas tous les faux positifs.
5. Corriger le nom et le calcul de P@5 : véritable Precision@5 = nombre de dépôts jugés pertinents dans les cinq premiers / 5. L'ancienne formule avec `min(5, nombre de pertinents)` correspond à une précision normalisée, qu'il faut nommer séparément si elle est conservée.
6. Ajouter Recall@5 (pertinents retrouvés dans les cinq premiers / total des pertinents connus), puis recalculer les séries de référence avec les mêmes définitions.
7. Évaluer séparément les contraintes (« sans », « pas », « hors ligne »), les ambiguïtés (notes, structures, monitoring), les contraintes techniques et les requêtes négatives sans candidat.
8. Après réussite sur le corpus synthétique, effectuer une validation en lecture seule sur la véritable base v7.1 de 443 fiches. Ne pas confondre le test synthétique et la validation réelle.

## Données Notion identifiées par lecture seule

Trois bases distinctes ont été identifiées : deux bases de 311 fiches datées du 14 janvier 2026 et une base de 443 fiches datées du 8 mars 2026.

Base de référence probable (v7.1, 443 fiches) : `31db36ca-5523-811f-8266-c279e8b76c28`.
Page : https://app.notion.com/p/31db36ca5523811f8266c279e8b76c28

Cette sélection doit être confrontée au `.env` local. Ne modifier aucune base automatiquement ; ne supprimer ni archiver de fiche.

## Conditions avant fusion

- Tests complets, lint ciblé et comparaisons de classement documentées.
- Régression évitée sur toutes les requêtes existantes ; toute baisse significative doit être explicitée.
- Tests de non-écriture Notion et d'atomicité de l'index maintenus.
- Aucune mesure sur données synthétiques présentée comme une preuve de qualité réelle.
- Validation en lecture seule sur la bonne base de 443 fiches, si l'accès est autorisé et fonctionnel.
- Aucun commit ni push automatique sur `main`.
