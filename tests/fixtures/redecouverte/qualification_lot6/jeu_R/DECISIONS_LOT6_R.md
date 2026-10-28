# Jeu R — règles de décision (écrites avant toute exécution du moteur sur le jeu R)

Objet : dire si la v2 peut être proposée à la revue de fusion (GO), ne le peut pas (NO GO), ou seulement sous réserve de
la comparaison externe sur les 443 fiches réelles (GO CONDITIONNEL). Versions comparées : `9aa4c6e` (référence) et la
v2 (`lot6-essai`). Ce fichier est figé avec les besoins de W2 (gel 2) ; il n'est pas modifié après exécution.

Définitions :
- « besoin concerné » : besoin dont l'analyse diffère entre les deux versions (concepts, ignorés, exclusions) ; les
  autres sont des « besoins témoins » ;
- qualification : étiquettes à l'aveugle de A et de B sur les 5 premiers visibles et les « forte » ; un couple est
  « confirmé » quand A et B donnent la même étiquette ;
- pour un besoin concerné, Δpert = (pertinents dans les 5 premiers v2) − (même chose 9aa4c6e), Δhs de même pour les
  hors sujet, calculés séparément selon A et selon B ;
- amélioration confirmée : Δpert > 0 ou Δhs < 0 selon A et selon B, sans dégradation chez l'un ni l'autre ;
  régression confirmée : Δpert < 0 ou Δhs > 0 selon A et selon B, sans amélioration chez l'un ni l'autre.

Règles :
1. Non-régression mécanique : tout besoin témoin a les mêmes 10 premiers (clés et niveaux) avec les deux versions.
   Une différence est un défaut : NO GO.
2. Suite complète verte sous Python 3.13 et 3.10 dans un clone git, sans désélection ni saut inattendu ; Ruff sans
   constat (sélection du projet). Sinon : NO GO.
3. Régressions confirmées strictement plus nombreuses que les améliorations confirmées : NO GO.
4. Mesures automatiques (jugements de W2 et, à part, de X) : la baisse de nDCG@10 moyen ou la hausse d'intrus@5 moyen
   de la v2 sur l'ensemble du jeu, pour l'un des deux juges, au-delà de 0,02, ou une violation « aucun_fort » de plus
   qu'avec `9aa4c6e` : GO CONDITIONNEL au mieux (avec explication besoin par besoin).
5. Rôles des technologies (lecture du moteur contre W2 et contre X) : un rôle juste de moins qu'avec `9aa4c6e` pour
   l'un des deux juges : GO CONDITIONNEL au mieux.
6. Sinon : GO pour la revue de fusion. Dans tous les cas, la comparaison externe sur les 443 fiches réelles reste à
   faire avant la fusion, et la publication de la branche demande une autorisation distincte.

Les désaccords A/B ne sont pas arbitrés pour la décision (ils comptent ni comme amélioration ni comme régression) ;
leur nombre et le kappa sont publiés.
