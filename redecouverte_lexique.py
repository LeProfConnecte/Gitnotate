# -*- coding: utf-8 -*-
"""Données du moteur de redécouverte (redecouverte.py) : aucune fonction, aucune entrée-sortie.

Gabarits de cas d'usage des versions 7.2 et antérieures (spécification du lot 4, annexe C) : textes de
remplissage que ces versions écrivaient sans lire le dépôt (liste générique anglaise, ou sa traduction
par le LLM). Les lignes sont comparées après repli (gitnotate._fold), puces et ponctuation finale
retirées ; les expressions françaises sont compilées une fois par le moteur.

Le lexique de la recherche (concepts, mots vides, déclencheurs de négation…) sera ajouté ici avec la
commande « cherche ».
"""

GABARITS_CAS_USAGE_EN = frozenset({
    'task automation via ai agents', 'multi-agent orchestration', 'agent integration',
    'model fine-tuning', 'production deployment', 'ml experimentation',
    'web app development', 'ui prototyping', 'tech stack integration',
    'development integration', 'testing', 'business adaptation'})

GABARITS_CAS_USAGE_FR = (
    r"^automatisation (de |des )?taches? (via|par|avec|grace a) (des |les )?agents?",
    r"^orchestration multi-?agents?$",
    r"^integration (d'|des |de l')agents?$",
    r"^(ajustement fin|affinage|fine-?tuning|reglage fin) (du |des |de |de la )?modeles?$",
    r"^deploiement en production$",
    r"^experimentation (en )?(ml|apprentissage automatique|machine learning)$",
    r"^developpement d'applications? web$",
    r"^prototypage (d'|de l'|des )?(interfaces?|ui)( utilisateurs?)?$",
    r"^integration (a|dans|de) (la |une )?(stack|pile) (technique|technologique)$",
    r"^integration (du|au|dans le|en|pour le) developpement$",
    r"^tests?$",
    r"^adaptation (commerciale|metier|aux besoins (metier|de l'entreprise)|business)$",
)
