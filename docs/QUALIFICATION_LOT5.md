# Redécouverte — lot 5 : précision, identifiants techniques et exclusions

Référence figée : `f68b656`. Toutes les mesures sont hors ligne, sur des fiches synthétiques ou fictives : elles ne
prouvent rien sur les 443 fiches réelles (§ 9). Aucune écriture dans Notion, aucun changement de schéma, d'index
(FORMAT_INDEX 2, aucune resynchronisation nécessaire) ni de seuil ; `main` inchangée.

## 1. Point de départ et reproduction de l'archive

- HEAD local et distant = `f68b656`. Archive `Gitnotate_lot5_precision_20261025.zip` (sha256 `0080845f…b499`) :
  les 8 fichiers correspondent à son manifeste ; les trois patches s'appliquent sur un checkout LF.
- **82 requêtes synthétiques sans filtre** (32 historiques, I01-I26, K01-K24) : les chiffres de
  `MESURES_ABLATIONS.json` sont reproduits à l'identique (référence : nDCG@10 0,8755, MRR 0,8979, P@5 0,4225, R@5
  0,8104, intrus@3 0,2683, intrus@5 0,5244 ; patch 02 : seul K18 change, nDCG@10 0,8763 ; patch 01 : aucun
  changement).
- **V15, V17 et S01-S10 ne sont pas rejouables ici** : la capture des 443 fiches réelles (sha256 `ce394c08…c3af`)
  n'a pas été transmise, ni le fichier V01-V22. Le mécanisme décrit par le rapport est confirmé sur le code : « n8n »
  était une forme du concept `workflow` (V17) et « recherche de code sémantique » ne contient pas l'expression
  « recherche sémantique » (V15). Commandes de reproduction locale : § 9. Le jeu V01-V22 a inspiré les corrections de
  l'archive : il ne certifie plus un gain indépendant.

## 2. Protocole

1. **Jeu N01-N40** (indépendant) : un rédacteur aveugle (sans accès au moteur, au lexique ni aux jeux existants) a
   écrit 30 fiches fictives « synth-… » (`lot5_supplement_N.json`) et 40 besoins jugés d'après le seul texte des
   fiches (20 FR, 20 EN : identifiants n8n/Zapier selon les quatre rôles, autres technologies, recherche sémantique
   code/documents, exclusions, 4 sans réponse, 4 génériques). Figé (sha256) avant toute exécution.
2. **Règles de décision** écrites et figées avant d'exécuter N (`DECISIONS_LOT5.md`, sha256 `32c78ef6…9e9f`).
3. Variantes mesurées sur le même index (62 + 30 fiches) : référence, patches 01/02/03, et les trois parties du
   lot 5 seules et combinées.
4. **Qualification exhaustive** : deux analystes aveugles (ni rang, ni niveau, ni variante) jugent pertinent /
   plausible / hors sujet chaque dépôt présent dans les 5 premiers ou en « forte » d'une variante (N : 217 couples,
   accord 98,6 %, kappa 0,973). Une « forte » est justifiée si le dépôt est jugé pertinent.
5. Les corrections inspirées par N forment une **version 2**, signalée comme post-hoc. Nouvelles règles figées
   (`DECISIONS_V2.md`, sha256 `fcc1d2a8…cbd3`), puis **jeu de validation M01-M30** par un second rédacteur aveugle
   (21 nouvelles fiches, `lot5_supplement_M.json`), exécuté une seule fois, code figé.

## 3. Ce qui a été construit

- **Partie 1 — recherche de code sémantique.** Notion `recherche_code`, voisine de `recherche_semantique` (formes
  « recherche de code sémantique », « semantic code search » ; dans les fiches, aussi « recherche sémantique dans le
  code », « semantic search over code »…), et composition : « recherche sémantique » + le mot « code » dans le même
  segment du besoin (une virgule ou une parenthèse les sépare), à six mots au plus → recherche de code (« une
  recherche sémantique dans mon code source »). Version 2 : un « code » placé après une négation ne compose pas
  (« … PDFs, not for source code »).
- **Partie 2 — identifiants selon leur rôle** (`IDENTIFIANTS`). n8n, Zapier, React, Kubernetes deviennent des
  notions à part. Produit **cible** (« workflows pour n8n ») : notion essentielle ; **environnement** (préposition
  « avec / sur / dans / en / with / on / in / using », ou possessif) : contrainte de rôle normal ; **à remplacer**
  (« alternative à n8n ») : sa catégorie, nom compris, et exclusion implicite ; **exclu** (« sans n8n ») : jamais
  cherché. Plateformes (Docker, Kubernetes, Windows, Linux, macOS, GPU) : contraintes inchangées, seule l'exclusion
  change.
- **Partie 3 — exclusions.** Trois états lus dans la fiche, jamais déduits de l'absence d'information : requis
  (Prérequis, exigence écrite, « pour n8n », « workflows n8n »), non requis (nié, facultatif, « alternative à … »),
  inconnu. Seul « requis » retire la « forte » et place le dépôt après les autres partielles. L'avis du LLM
  (Justification) est affiché, jamais compté comme preuve. La pénalité de négation du lot 4 n'est pas réintroduite :
  un mot nié reste retiré de la recherche sans déclasser les fiches qui le mentionnent. Portée : la liaison juste
  après le déclencheur ne ferme plus la négation devant un identifiant (« pas avec Docker », « not for Windows ») ;
  « avec ou sans GPU » est indifférent ; « pas à pas » n'est plus une négation.

## 4. Jeu N (indépendant) : résultats et décisions de la première passe

| Variante | nDCG@10 | MRR | R@5 | intrus@3 | intrus@5 | premiers attendus | hors sujet @5 (A/B) | « forte » non pertinentes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Référence f68b656 | 0,870 | 0,894 | 0,775 | 0,500 | 0,750 | 30 | 118 / 115 | 58 |
| Patch 01 | 0,876 | 0,899 | 0,775 | 0,475 | 0,775 | 30 | 117 / 114 | 61 |
| Partie 1 (L1) | 0,873 | 0,899 | 0,775 | 0,450 | 0,750 | 30 | 117 / 114 | 55 |
| Partie 2 (L2) | 0,857 | 0,882 | 0,775 | 0,500 | 0,750 | 29 | — | — |
| Parties 2+3 (L23) | 0,859 | 0,882 | 0,775 | 0,400 | 0,625 | 29 | — | — |
| Parties 1+2+3 (L123) | 0,861 | 0,887 | 0,775 | 0,350 | 0,625 | 29 | 116 / 113 | 43 |

Décisions selon les règles figées :

- **Patch 01 rejeté.** Il améliore N22 (« Semantic code search across several of my repositories… », nDCG@10
  0,59 → 0,80), mais en rendant `recherche_semantique` synonyme de la recherche de code, il donne une « forte » aux
  outils de documents pour une requête sur le code (txtai, pdfseek) : 61 « forte » non pertinentes contre 58
  (règle 4). Son léger recul sur les PDF signalé par l'archive (S07) relève du même mécanisme : une forme plus
  spécifique placée parmi les synonymes du concept général.
- **Patches 02 et 03 non retenus**, comme l'archive le proposait déjà (« hypothèse n8n », « combinaison
  exploratoire ») : sur N, P02 baisse R@5 (0,775 → 0,768) et P@5 et monte intrus@5 (0,750 → 0,775) ; P03, malgré
  un nDCG@10 de 0,876, baisse R@5 (0,768) et monte intrus@5 (0,800) et le nombre de « forte » (règles 1 et 4).
- **Partie 1 rejetée** dans sa première forme : N32 (« Semantic search for my lesson notes and PDFs, not for source
  code ») — le défaut connu « not for X » laisse « code » positif, la composition le transforme en recherche de
  code et place un outil de code en tête (règle 1).
- **Partie 2 rejetée** : nDCG@10 et MRR sous la référence, un premier attendu perdu. Cause principale : N05
  (« Une alternative no-code à n8n et à Zapier… », nDCG@10 0,91 → 0,45) ; la catégorie remplaçait le produit sans
  son nom, et une fiche « alternative à n8n et Zapier » perdait son meilleur indice. Aussi N03 et N10 (produit après
  un possessif : contexte qui sortait de la couverture).
- **Partie 3** : satisfait sa règle (intrus@5 3 → 0 sur N07, 1 → 0 sur N16 et N29, aucun dépôt pertinent marqué
  « requis »), mais elle n'avait été mesurée qu'au-dessus de la partie 2 : non retenue seule.

## 5. Version 2 (corrections post-hoc d'après N) et validation sur M

Corrections, chacune motivée par une requête de N (donc non validées par N) : en rôle référence, la catégorie garde
le nom du produit et le produit devient une exclusion implicite (N05) ; un produit après un possessif est une
contrainte de rôle normal (N03, N10) ; la composition ignore un « code » placé après une négation (N32). V2a = parties
2 v2 + 3 + patch 01 ; V2b = parties 1 v2 + 2 v2 + 3 ; V2c = parties 2 v2 + 3 seules.

Sur N (optimiste, post-hoc) : V2b nDCG@10 0,885, MRR 0,921, R@5 0,803, intrus@5 0,575, 31 premiers attendus ; 112
hors sujet dans les 5 premiers (A) et 41 « forte » non pertinentes, contre 118 et 58 pour la référence.

**Jeu M (validation, exécuté une fois, code et règles figés) :**

| Variante | nDCG@10 | MRR | R@5 | intrus@3 | intrus@5 | premiers attendus | nDCG@10 sémantique |
|---|---:|---:|---:|---:|---:|---:|---:|
| Référence f68b656 | 0,791 | 0,795 | 0,698 | 0,567 | 0,667 | 19 | 0,705 |
| Patch 01 | 0,793 | 0,795 | 0,690 | 0,633 | 0,700 | 19 | 0,715 |
| V2a | 0,805 | 0,814 | 0,703 | 0,400 | 0,533 | 20 | 0,708 |
| **V2b (retenue)** | **0,818** | **0,847** | **0,710** | **0,367** | **0,533** | **21** | **0,764** |
| V2c | 0,803 | 0,813 | 0,710 | 0,333 | 0,500 | 20 | 0,698 |

Qualification exhaustive de M en double aveugle (176 couples, accord 98,9 %, kappa 0,976 ; analystes A / B) :

| Variante | pertinents @5 | pertinents ou plausibles @5 | hors sujet @5 | 1er rang hors sujet | « forte » | « forte » non pertinentes |
|---|---:|---:|---:|---:|---:|---:|
| Référence f68b656 | 0,193 | 0,340 / 0,353 | 95 / 93 | 8 / 7 | 82 | 54 |
| Patch 01 | 0,193 | 0,333 / 0,347 | 96 / 94 | 8 / 7 | 85 | 57 |
| V2a | 0,200 | 0,340 / 0,353 | 95 / 93 | 7 / 6 | 79 | 51 |
| **V2b (retenue)** | **0,207** | **0,347 / 0,360** | **94 / 92** | **6 / 5** | **74** | **46** |
| V2c | 0,200 | 0,347 / 0,360 | 94 / 92 | 7 / 6 | 76 | 48 |

Décision (règle R5 de `DECISIONS_V2.md`) : **V2b retenue**. Elle satisfait R1 (nDCG@10, MRR, R@5 au-dessus de la
référence, intrus@5 en dessous), R2, R3 et R4 (moins de hors sujet et de « forte » non pertinentes que la référence,
sur M comme sur N), et son nDCG@10 sur le thème sémantique de M (0,764) dépasse celui de V2a (0,708). Le patch 01
échoue de nouveau seul : R@5 en baisse, intrus@5 en hausse, 3 « forte » non pertinentes de plus.

Requêtes de M modifiées par V2b (par rapport à la référence) : gains nets M08 (« … mais pas en React », nDCG@10
0,65 → 0,98, intrus@5 2 → 0), M13 (recherche de code « not for PDFs », MRR 0,08 → 1,0, mais un intrus de plus
dans les 5 premiers), M09, M17, M18, M19, M22 (un intrus de moins chacun) ; pertes mineures M05 et M10 (un intrus de
plus ; M10 nDCG@10 0,98 → 0,94). Aucune requête ne perd plus de 0,05 de nDCG@10 ; aucun dépôt « en tête » des
3 premiers de la référence ne sort des 5 premiers ; aucun dépôt jugé pertinent n'est marqué « requis » (M, N et les
82 synthétiques). Défaut antérieur révélé par M, identique avec la référence : M23 (« … charpente métallique selon
l'Eurocode 3 ») et M24 (emploi du temps scolaire), sans réponse attendue, reçoivent des « forte » (un outil
Eurocode 2 : « 3 » est un nombre isolé ignoré et « Eurocode » une forme du concept calcul de structure).

## 6. Revue de code contradictoire et corrections après validation

Une revue indépendante du diff (sans les conclusions de ce rapport) a relevé 3 défauts bloquants, 8 importants et
8 mineurs, tous reproduits par exécution ; aucun ne touche la lecture seule ni l'injection FTS5. Corrigés, chacun
avec un test (`tests/test_redecouverte_lot5.py`, « Revue contradictoire du lot 5 ») :

- **B1** une négation débordait sur la technologie qui suit « sous / en / via / using / into » (« sans GPU sous
  Windows » excluait Windows) : une préposition referme la négation ; elle se referme aussi après la technologie
  exclue (M5 : « pas avec Docker en Python » cherche Python) ; « without GPU or Docker » exclut les deux, « sans
  GPU et avec Docker » garde Docker.
- **B2** « Docker n'est pas requis », « GPU non nécessaire », « isn't required » étaient lus « requis » : négation
  après la mention.
- **B3** une ligne de Prérequis coupée aux parenthèses et deux-points (« - GPU NVIDIA (optionnel) », « Docker: not
  required ») et le premier élément d'une énumération (« Windows, macOS ou Linux ») : négation, souplesse et
  alternatives se lisent dans l'élément de liste ; « 3.10 ou plus récent » n'est pas une alternative ; le point
  d'un numéro de version ne coupe plus une proposition.
- **I1** « uniquement utilisé pour les tests », « only needed for development », « si nécessaire » ; **I2** exclure
  Docker excluait tout conteneur ; **I3** « no-code », « sans code » et une négation portant sur un autre nom
  rendaient un produit « non requis » ; **I4** un mot souple ou « CPU » visant un autre élément (« Requires an NVIDIA
  GPU and optionally Docker », « no CPU fallback ») ; **I5** composition bloquée par une négation déjà fermée,
  appliquée hors du segment ou à un autre sens de « code » ; **I6** « un tutoriel sur React », « on » pronom
  français ; **I7** « sans GPU » masquait la limite matérielle sans preuve (et « cartes graphiques » manquait) ;
  **I8** liste filtrée « sans n8n » : états non calculés.
- Mineurs : « nœud » (M1), « comme n8n » (M2), dépôt qui porte le nom du produit (M3), verbes « nécessite /
  require » du cadre de question (M8), `source` dans le JSON et en-têtes (M7), tests M6 qui testaient à vide.

Écartés après mesure : chercher « recherche sémantique » près de « code » (NEAR, I5c) faisait perdre la première
place à l'outil de code attendu dans N22 et M13 ; remplacé par les formes de `FORMES_FICHES`, cherchées dans les
fiches mais jamais reconnues dans la requête (« le Code de l'urbanisme » ne compose plus). Ajouter un nom composé
(Claude Code) à sa catégorie déjà demandée en rôle normal dégradait Q11 : le nom n'est ajouté que si la catégorie
reste en rôle référence.

Mesures après ces corrections : **identiques à V2b** sur les 82 synthétiques, N et M (nDCG@10, MRR, P@5, R@5,
intrus, « forte », premiers attendus). Les rangs changent dans N05 (à partir du 5e), M20 (au 10e) et N07, où
inbox-parser (« Déclencher un workflow n8n, Make ou Zapier par webhook »), qui n'est plus lu à tort comme dépendant
de n8n, monte du 8e au 2e rang (taskweave reste 1er) ; ces dépôts ne sont pas jugés pour ces requêtes, d'où des
mesures inchangées. Ces corrections sont postérieures à M : elles sont validées par leurs tests et par l'absence de
changement des mesures, pas par un nouveau jeu indépendant. La qualification complémentaire (ci-dessous) a montré
après coup qu'inbox-parser, entré au 5e rang de N05, est hors sujet pour les deux analystes : un hors sujet de plus
dans les 5 premiers de N (112 → 113 pour l'analyste A).

### Seconde revue contradictoire

Une seconde revue indépendante (lecture du diff, scénarios rejoués) a relevé 47 constats ; 42 confirmés (4
bloquants), 5 écartés après vérification (#10 possessif entre liaison et technologie, #11 « Docker not required »
dans la requête, #28 état « contradictoire », #32 « sans n8n » seul en ligne de commande, #45 « forte » sur une
seule contrainte : comportements voulus ou hors du lot). Principe retenu côté fiches : **« requis » n'est retenu que
sur une tournure sans ambiguïté ; dans le doute, « mention »**, qui ne change pas le classement. Corrigés, chacun
avec un test (`tests/test_redecouverte_revue2.py`, 153 cas ; mutations des correctifs principaux toutes détectées) :

- **Fiches** : groupe de la mention borné par la virgule (« GPU NVIDIA obligatoire, Docker facultatif ») mais pas
  par la coordination (« GPU et Docker facultatifs », « Docker and a GPU are optional ») ; « Neither … nor » ;
  négation sans mot d'exigence (« GPU : non », « none », « n'est pas un prérequis », « not supported », « non pris
  en charge », « incompatible ») ; « ne … que », « required only for » ; exigence qui gouverne un autre membre
  (« Requires Python 3.10 and supports GPU ») ; listes de plateformes (« Windows, macOS, Linux », « Windows et
  Linux ») ; « substitute », « remplacement », migration (« importez vos workflows Zapier ») ; la marque NVIDIA
  seule n'est plus une forme du GPU exclu ; CPU possible (« CPU inference supported », « mode CPU ») et négation
  autour de « CPU » ; « comme » / « like » réservés aux produits ; disjonctions de versions ou de marques (« CUDA
  11.8 ou 12.1 », « NVIDIA or AMD GPU ») ; noms ambigus (« à la demande », « tout le nécessaire », « your automation
  needs ») ; « Windows only for now » ; titre seul (jamais le propriétaire `owner/repo` ; « zapier-alternative »,
  « gpu-free-ocr ») ; adresses et chemins (« git clone https://…/zapier-app-starter.git ») ; citation de la phrase
  entière jusqu'à 220 caractères ; limite matérielle masquée seulement par une preuve d'un champ factuel.
- **Requête** : une technologie à la fois demandée et niée n'est pas exclue (« a React web app, not React
  Native ») ; l'exclusion demande que la négation touche la technologie, des mots d'usage seuls pouvant les séparer
  (« I'm not sure whether to use n8n » ne l'exclut plus ; « sans passer par n8n », « without installing Docker »
  l'excluent toujours) ; « pas que », « not only » ne nient rien ; une préposition ne referme la négation que devant
  une technologie (« sans passer via un service cloud » nie de nouveau « service » et « cloud ») ; produit avant
  « alternatives », après « comme », « like », « similar to », « remplacer » : à remplacer ; « code » en référence,
  quantité (« quelques lignes de code ») ou autre sens (liste élargie, « Code » avec majuscule) ne compose pas ;
  « not with Docker or Kubernetes » exclut les deux ; sujet d'un cours cité plus tôt dans le segment ; « ne …
  plus », « no longer » ; « on » pronom seulement devant un verbe.
- **Documentation et tests** : #39 (K18), #40 (N07), #41 (segment), #42-#44 (tests à vide), #46 (règles de
  décision, empreintes du code des variantes et jugements versionnés dans `tests/fixtures/redecouverte/
  qualification_lot5/`, colonnes de qualification recalculées par `tests/test_qualification_lot5.py`).

Ajustement fait **après avoir vu N et M** : la première version de la règle « la négation touche la technologie »
supprimait l'exclusion de N07 (« sans passer par n8n »), M17 (« without installing Docker »), M18 (« sans être
obligé de passer par Docker ») et M19 (« without needing Kubernetes ») ; la liste fermée `VERBES_EXCLUSION` (mots
d'usage permis entre le déclencheur et la technologie) rétablit le comportement de V2b sur ces quatre requêtes.

Mesures après la seconde revue (00bd67a ; les 82 synthétiques sont inchangés ; mesures finales à la fin du § 6) :

| Jeu | Version | nDCG@10 | MRR | R@5 | intrus@3 | intrus@5 | premiers | hors sujet @5 (A/B) | « forte » | « forte » non pertinentes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| N | f68b656 | 0,870 | 0,894 | 0,775 | 0,500 | 0,750 | 30 | 118 / 115 | 92 | 58 |
| N | V2b | 0,885 | 0,921 | 0,803 | 0,325 | 0,575 | 31 | 112 / 109 | 76 | 41 |
| N | seconde revue | 0,888 | 0,921 | 0,817 | 0,300 | 0,500 | 31 | 111 / 108 | 75 | 40 |
| M | f68b656 | 0,791 | 0,795 | 0,698 | 0,567 | 0,667 | 19 | 95 / 93 | 82 | 54 |
| M | V2b | 0,818 | 0,847 | 0,710 | 0,367 | 0,533 | 21 | 94 / 92 | 74 | 46 |
| M | seconde revue | 0,818 | 0,847 | 0,710 | 0,300 | 0,467 | 21 | 94 / 92 | 71 | 43 |

Requêtes modifiées par rapport à V2b (première et seconde revue) : N18 (« similar to Claude Code » : Claude Code
devient la référence ; les outils pour Claude Code sortent des 5 premiers ; nDCG@10 0,81 → 0,91), M07 (« Something
to replace FastAPI » : les deux gabarits FastAPI, à exclure, sortent des visibles ; intrus@5 2 → 0, mais quatre
dépôts hors sujet les remplacent dans les 5 premiers), N05 et N07 (inbox-parser : n8n « mention » au lieu de
« requis », 19e → 5e et 8e → 2e ; zap2n8n : Zapier « mention »), N28, M21 et M22 (whisper-batch, « GPU NVIDIA
facultatif (CUDA) : fonctionne aussi sur CPU » : « non requis » au lieu de « contradictoire », rangs inchangés), M08
(vue-dash-components : avis du LLM « non utilisable dans une application React » lu « mention » au lieu de « non
requis »), M20 (rangs 10 et 11 échangés). Les 9 couples entrés dans les 5 premiers sans
avoir été jugés (dont inbox-parser pour N05, depuis la première revue) ont été qualifiés par deux nouveaux
analystes aveugles, avec la même consigne : accord 9 / 9. **M n'est plus un jeu de validation indépendant** pour
ces corrections : elles sont postérieures à son exécution et l'une d'elles (`VERBES_EXCLUSION`) a été ajustée après
lecture de ses résultats (règle R6 de `DECISIONS_V2.md`).

### Troisième revue contradictoire

Une troisième revue (quatre axes : faux « requis » des fiches, requête, classement et sorties, cohérence docs /
tests ; chaque constat rejoué par un vérificateur chargé de le réfuter) a confirmé 34 constats, dont plusieurs
**régressions introduites par les corrections de la seconde revue** : « ne … plus » de mémoire (« je ne me souviens
plus du nom de l'outil d'OCR » ne cherchait plus rien), « I'd like a React library » lu comme « like React »
(référence), « migrating to n8n » et « Comme n8n est installé… » lus comme des produits à remplacer, « je n'ai
jamais utilisé n8n » et « je ne connais pas n8n » qui excluaient n8n, « with code examples » et « I want to code a
semantic search » qui composaient une recherche de code. Corrigés, chacun avec un test
(`tests/test_redecouverte_revue3.py`, 113 cas ; 30 mutations des nouvelles gardes, toutes détectées) :

- **Fiches** (faux « requis », ou faux « non requis » qui fabriquait un « contradictoire ») : facultatif qui vise
  une version, un modèle, une quantité ou la valeur qui suit (« Requires Docker (Compose v2 recommended) », « - CUDA
  11.8+ (12.1 recommended) », « (recommended: 24+) ») ; facultatif après une virgule (« - Docker, optional ») ;
  élément conditionnel ou de bénéfice (« - If you have an NVIDIA GPU, install CUDA », « - NVIDIA GPU (for faster
  inference) », « - For GPU acceleration: CUDA ») ; double négation (« Ne fonctionne pas sans GPU ») ; élément
  sous « - Optional: » ; « Zapier-like », « n8n-style » ; intégration proposée (« Also ships an n8n node »,
  « wrappers for React, Vue and Angular ») ; « GPU and CPU supported » ; usage annexe sans « only » ; virgule
  d'Oxford ; variante niée (« Docker Desktop n'est pas nécessaire ») ; « dépend de votre GPU » ; deux formes d'un
  même identifiant (« GPU with CUDA (optional) ») ; ligne de commande (« pip install zapier-alternative »).
- **Requête** : négations contractées (« don't », « doesn't », « can't », « cannot ») et « neither … nor » ; mot
  d'usage suivi d'une liaison (« without depending on n8n », « without relying on Docker ») ; interdiction dans
  l'explication (« sans Docker : les conteneurs sont interdits », « because Docker is not allowed ») ; plus les
  régressions ci-dessus.
- **Classement et sorties** : « no-code » ne nie plus les mots qui suivent dans le score (une alternative no-code
  à n8n perdait la notion workflow : régression du lot 5, n8n et Zapier n'étant plus des formes de workflow) ; à
  état égal, la ligne Exclusion cite le champ qui décrit la technologie avant le titre, et le titre seul ne masque
  plus la limite matérielle ; la citation porte la date de la fiche citée.
- **Documentation et tests** : variantes versionnées sous forme de patchs reproductibles
  (`qualification_lot5/variantes/`, empreintes recalculées par `tests/test_qualification_lot5.py`, méthode dans
  `LISEZMOI.md`) ; intrus@3 et P@5 figés ; la fenêtre où un « facultatif » placé après la mention est lu passe de
  6 à 10 mots (`_APRES_SOUPLE`, sous réserve des mots qui le reportent sur une version ou une quantité).

Mesures changées par la troisième revue (fe9fdeb ; les 82 synthétiques sont inchangés) : N08 (« without depending
on n8n or Zapier » exclut désormais les deux : les gabarits n8n et n8n-nodes-pdfgen sortent des 5 premiers,
intrus@3 1 → 0, intrus@5 2 → 0 ; pdfcraft et docling y entrent) ; N11 et N30 (flowpilot entre au 5e rang) ;
M09 (« Self-hosted workflow automation that doesn't rely on Docker — containers aren't allowed ») : Docker, qui était
cherché comme contrainte, est exclu ; flowpilot, que cette contrainte remontait par accident, passe du 2e au 6e
rang, et quatre dépôts liés à n8n et inbox-parser occupent les 5 premiers (nDCG@10 0,351 → 0,252, R@5 0,333 →
0) : la
règle R2 de `DECISIONS_V2.md` (aucun dépôt « en tête » des 3 premiers de la référence ne sort des 5 premiers) **n'est
plus tenue sur M09** ; M14 (un dépôt hors sujet remplace opencode au 5e rang). Soit, sur N, intrus@3 0,300 → 0,275
et intrus@5 0,500 → 0,450 ; sur M, nDCG@10 0,818 → 0,814, MRR 0,847 → 0,835, R@5 0,710 → 0,698 (le niveau de
f68b656), « forte » 71 → 68. Les 7 couples entrés ainsi dans les 5 premiers sans jugement ont été qualifiés par
deux analystes aveugles, avec la même consigne (`*_complement2.json`) : accord 5 / 7 (les deux désaccords, M09,
opposent « plausible » et « hors sujet »).

### Quatrième revue contradictoire

La quatrième revue, centrée sur les régressions des corrections de la troisième, a confirmé 36 constats sur 40 ;
presque tous étaient de telles régressions (par exemple « You can run it without a GPU » lu comme une exigence,
« Docker is completely optional » ou « - An NVIDIA GPU (RTX 3060 or newer) is recommended » lus « requis », « I can't
find the n8n workflow I saved » qui ne cherchait plus rien, « une alternative à Zapier car le cloud est interdit »
qui excluait Zapier). Constat de méthode : chaque règle ajoutée pour un cas cassait des tournures voisines. La
lecture des fiches a donc été réécrite d'un seul tenant sur un principe plus strict : **une règle étroite pour
« requis » ou « non requis », tout le reste en « mention »** :

- double négation limitée au verbe juste avant « sans » (« Ne fonctionne pas sans GPU », « won't work without ») ;
- facultatif reporté sur une version, une quantité ou un modèle seulement (« (Compose v2 recommended) », « (16 GB
  recommended) »), et plus sur un adverbe, un adjectif ou une parenthèse refermée (« Docker is completely optional »,
  « - An NVIDIA GPU (RTX 3060 or newer) is recommended ») ; « optional: » suivi d'une phrase reste facultatif ;
- négation : « No NVIDIA GPU required », « Does not require a dedicated GPU » ; un autre nom entre la négation et
  l'exigence est l'objet nié (« aucune clé d'API nécessaire », « no other dependency needed ») ; une autre marque
  non prise en charge ne nie pas le GPU (« NVIDIA GPU (AMD GPUs are not supported) ») ;
- CPU possible resserré (« an NVIDIA GPU and a CPU with AVX2 » n'en est pas un) ; « ou équivalent » est une
  alternative ; une condition en tête ne vaut que pour un élément de liste ; fonction conditionnelle (« GPU
  acceleration requires CUDA ») ; bénéfice ou usage annexe d'un autre membre ou coordonné (« for training and
  inference ») ; « (preferred) », « de préférence », « nice to have » ; exemple fourni (« Un exemple de workflow
  n8n est fourni ») ; lignes de commande resserrées (« - helm 3+ and a running Kubernetes cluster » reste une
  exigence) ; ligne de continuation d'un élément de liste ;
- requête : mémoire et indifférence (« I can't find… », « je ne retrouve plus le dépôt n8n », « doesn't matter if
  it's React or Vue », « ça ne me dérange pas d'utiliser Docker ») ; interdiction seulement quand la technologie en
  est le sujet ; « Comme Zapier, mais open source » ; « without installation on Windows » n'exclut pas Windows ;
  « semantic search on my codebase » ; verbe de qualité (« qui ne plante jamais sous Windows ») ; « I haven't used
  n8n » ;
- coût : les bornes de phrase et de groupe sont calculées une fois par texte (une fiche de 90 000 caractères qui
  cite 1 200 fois Docker : 0,4 s au lieu de plusieurs secondes, coût quadratique signalé par la revue).

Tests : `tests/test_redecouverte_revue4.py` (123 cas). Ces corrections ne changent aucune mesure sur les 82
synthétiques, N ni M. Plusieurs des règles de requête ajoutées ici étaient trop larges : la cinquième revue les a
resserrées.

Limite côté gitnotate.py, non corrigée ici (hors du moteur de redécouverte et du périmètre du lot) : une section
de README « Optional dependencies » remplit la colonne Prérequis sans son titre ; le moteur lit l'élément parent
« - Optional: » d'une liste imbriquée, pas un titre de section qui n'est pas conservé.

### Cinquième revue contradictoire

La cinquième revue (mêmes quatre axes, vérificateur chargé de réfuter chaque constat) a confirmé 33 constats sur 34,
dont 5 bloquants après vérification. Presque tous sont des régressions de la quatrième revue, côté requête surtout : la règle
« mémoire ou indifférence » regardait trois mots autour de la négation, « sans » / « without » compris, si bien que
« Find a web scraper without Docker », « Trouve un OCR sans Docker », « retrouver un OCR sans Docker »
**cherchaient Docker au lieu de l'exclure** et plaçaient en « forte » le dépôt qui l'exige. Le constat de méthode
de la quatrième revue vaut toujours : chaque règle ajoutée pour un cas en cassait de voisins. Les règles ont donc
été rendues étroites et ancrées sur la syntaxe :

- **Requête** : la mémoire, l'indifférence et la qualité ne se lisent que sur le verbe que la négation régit
  (entre « ne » et « pas », ou juste après « can't », « don't »), jamais sur « sans » / « without » ; « sais »,
  « arrive » ne valent mémoire que devant un interrogatif ou un verbe de mémoire (« je ne sais pas quel outil
  n8n », « je n'arrive pas à retrouver… » ; « je n'arrive pas à installer Docker » exclut Docker) ; « vois »,
  « figure » retirés ; l'indifférence rend la technologie indifférente (ni cherchée ni exclue) au lieu de la
  chercher (« I don't care about React, I need a Vue component library » ne favorise plus React) ; le verbe régi
  n'est plus une notion du besoin (« retrouve », « dérange ») ; « no GPU installed », « Aucun GPU installé »
  excluent de nouveau le GPU (le participe d'expérience n'est lu que juste après la négation) ; adverbes admis
  avant « interdit » / « autorisé » (« Docker n'est malheureusement pas autorisé », « Docker n'est plus
  autorisé ») ; exception « système » réservée aux mots d'installation (« without relying on Windows » exclut
  Windows) ; « Comme n8n a déjà un nœud HTTP… » en tête de segment est causal, et un produit à la fois cible et
  référence n'est pas exclu ; permission (« I'm not allowed to install Docker », « je n'ai pas le droit
  d'installer Docker ») ; « n'ai » n'est plus lu « AI » (défaut antérieur au lot 5).
- **Fiches** : adverbes entre la négation et l'exigence (« no longer required », « pas vraiment nécessaire ») ;
  double négation jusqu'à trois mots (« You can't run the app without Docker », « doesn't work properly without a
  GPU », « It is not possible to run this model without a GPU ») ; un facultatif dans une parenthèse ouverte vise
  l'autre nom qui le précède (« Requires Docker (Compose plugin recommended) », « - NVIDIA GPU (RTX series
  recommended) ») ; « RTX 3060 or equivalent » n'est pas une alternative ; « A GPU is required: without a GPU,
  … » reste requis ; un verbe d'exigence ne laisse plus passer la négation d'un autre nom (« no cloud: requires an
  NVIDIA GPU ») ; exception (« Aucune dépendance sauf Docker »), affiliation (« not affiliated with n8n GmbH »,
  « non officiel ») et version niée (« Docker 20.10+ (older versions are not supported) ») ne nient pas la
  technologie ; « Runs on GPU and CPU » ; usages annexes coordonnés (« for development and testing ») ;
  intégration offerte (« Ships with an n8n community node ») ; « The backend requires Docker » ; collection
  d'exemples de workflows n8n ; « pour n8n, prêts à importer » n'est pas une liste ; « Docker and Docker Compose
  (optional) » vaut pour les deux.
- **Classement et sorties** : le motif d'énumération revenait en arrière de façon exponentielle (8 s pour une liste
  de 7 technologies après la technologie exclue, défaut présent depuis la seconde revue) : motif sans ambiguïté, en
  temps linéaire ; « No coding required », « sans programmation », « non officiel » ne nient plus la suite dans le
  score ; à état égal, la preuve de la fiche principale est citée ; une même phrase n'est citée qu'une fois (À
  vérifier, Exclusion).
- **Documentation et tests** : `docs/REDECOUVERTE.md` décrit les règles de requête ; les mutations survivantes
  signalées (6 gardes sans test) ont chacune un cas ; l'attribution des changements de mesure à la troisième revue
  est corrigée ci-dessus.

Écarté : le coût encore quadratique d'un texte de plusieurs dizaines de milliers de caractères sans aucune
ponctuation (entrées artificielles ; un docker-compose réaliste collé dans une note reste sous 0,03 s).

Tests : `tests/test_redecouverte_revue5.py` (224 cas ; plus de 150 échouent sur le code de la quatrième revue). Ces
corrections ne changent ni les mesures ni les rangs sur les 82 synthétiques, N et M ; seul l'état d'exclusion de
fastapi-starter dans M09 passe de « contradictoire » à « non requis » (« Docker et Docker Compose (facultatifs…) »).
Cinq revues ont donc été nécessaires, et chacune a trouvé des régressions de la précédente : il faut s'attendre à
d'autres tournures mal lues sur les 443 fiches réelles (§ 9, § 10).

### Sixième revue contradictoire

La sixième revue, centrée sur les corrections de la cinquième, a confirmé 33 constats sur 33 (dont 6 bloquants), et
de nouveau surtout des régressions de la revue précédente : « Does not require any GPU » et « No longer requires
Docker » lus « requis » (la cinquième revue avait cessé de tenir les verbes d'exigence pour neutres), « Pas de cloud
: fonctionne sans GPU » lu « requis », « - NVIDIA GPU (used if available) » lu « requis », « I don't mind Docker and
I want a self-hosted OCR » qui ne cherchait plus l'OCR, « I can no longer find the n8n workflow… » qui excluait n8n,
« une alternative à Zapier, Zapier est trop cher » qui cherchait Zapier, « Comme n8n devient trop cher, je cherche
une alternative » lu comme une cause. Les corrections (`tests/test_redecouverte_revue6.py`, 139 cas, dont 91 états de
champ et 44 requêtes ; tous lus correctement par le code final, contre 27 et 14 par celui de la cinquième revue, 60
et 23 par celui de la quatrième, 34 et 9 par celui de la troisième) reprennent les prototypes vérifiés des relecteurs
: « : » et tiret long bornent la négation qui précède, une négation de nom ou « not only » ne fait pas une double
négation, l'indifférence ne vise que les technologies, adverbes avant le verbe de mémoire, capacité sans mémoire qui
ne nie plus la tâche, produit à remplacer renommé qui reste à remplacer, exception « système » sauf après un mot de
dépendance, « Comme » causal seulement en tête d'une requête sans remplacement, citation Markdown sur une ligne.

Constat de méthode : de la troisième à la sixième revue, chaque série de corrections a cassé autant de tournures
voisines qu'elle en réparait, et aucune revue ne mesurait l'effet d'ensemble. La suite a donc été conduite sur un
banc indépendant, jugé avant toute exécution.

### Banc indépendant

Protocole (`tests/fixtures/redecouverte/qualification_lot5/banc/`, `LISEZMOI.md`, `GUIDE.md`) : des agents sans accès
à aucun fichier ni programme ont rédigé des champs de fiche réalistes (Prérequis recopiés de README, Descriptions
rédigées par LLM, Installation, Exemple, Notes, Cas d'usage ; français et anglais) et des requêtes, chacun étiqueté
par son rédacteur puis, à l'aveugle, par un second analyste. Seuls les éléments où les deux s'accordent sont gardés :
775 champs sur 775 et 288 requêtes sur 290. Cet accord complet sur les champs dit aussi que les rédacteurs ont écrit
des cas nets : les fiches réelles, plus ambiguës, peuvent être moins bien lues. Premier jeu coupé en deux moitiés :
dev (204 champs, 80 requêtes), qui a servi à corriger, et t1 (211 champs, 69 requêtes), mesurée une fois avant d'être
regardée, puis utilisée elle aussi. Second jeu t2 (360 champs, 139 requêtes), rédigé par d'autres agents sur d'autres
domaines, mesuré une seule fois, code figé : c'est la mesure finale. Mesure : état du champ calculé comme pour une
recherche qui exclut la technologie (_preuves_exclusions, etat_exclusion) ; rôle de chaque technologie de la requête.
Les versions du tableau sont des commits d'une branche d'essai non publiée : leur code est conservé en patchs
enchaînés (`banc/versions/`, empreintes vérifiées par les tests) et chaque ligne se remesure avec
`tests/test_redecouverte_banc.py` (`banc/LISEZMOI.md`).

| Version | t1 : champs exacts | t1 : précision / rappel de « requis » | t1 : faux « requis » | t1 : rôles justes | t2 : champs exacts | t2 : précision / rappel de « requis » | t2 : faux « requis » | t2 : rôles justes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fe9fdeb (3e revue) | 69,7 % | 0,68 / 0,62 | 21 | 82,1 % | 70,8 % | 0,68 / 0,58 | 33 | 73,3 % |
| de04315 (4e revue) | 72,0 % | 0,75 / 0,64 | 16 | 82,1 % | 72,5 % | 0,72 / 0,58 | 27 | 72,7 % |
| d4ffc83 (5e revue) | 73,5 % | 0,74 / 0,66 | 17 | 86,3 % | 72,5 % | 0,70 / 0,60 | 31 | 75,6 % |
| f8ae513 (6e revue) | 74,4 % | 0,73 / 0,67 | 18 | 87,4 % | 72,5 % | 0,71 / 0,60 | 30 | 75,6 % |
| eb8106f (banc, dev) | 79,1 % | 0,79 / 0,75 | 15 | 88,4 % | 79,2 % | 0,76 / 0,75 | 29 | 78,4 % |
| **finale** (banc, dev + t1) | (91,5 %, corrigé sur t1) | (0,96 / 0,89) | (3) | (97,9 %) | **81,1 %** | **0,78 / 0,77** | **27** | **83,5 %** |

Lecture : de la troisième à la sixième revue, l'exactitude n'a presque pas bougé (t2 : 70,8 % → 72,5 %) ; les
corrections guidées par le banc l'ont portée à 81,1 % sur t2, avec un rappel de « requis » de 0,58 à 0,77 (plus de
dépôts qui exigent la technologie exclue sont déclassés). Sur la moitié dev, utilisée pour corriger, la version
finale atteint 94,1 % : l'écart avec t2 mesure le sur-ajustement. Le nombre de faux « requis » n'a presque pas
baissé (t2 : 27 sur 360, 7,5 % des champs) : environ un « requis » sur cinq déclasse à tort un bon dépôt. C'est le
risque principal du lot (§ 10, § 11).

Corrections guidées par le banc : élément de Prérequis requis seulement s'il a la technologie pour tête et que rien
ne le borne (« - Tested on… », « - On Linux, also install… », « for the real-time transcription mode », « - One of:
») ; exigence ou restriction d'une partie (« La variante 32B demande un GPU », « L'intégration au menu contextuel
n'est disponible que sous Windows ») en « mention » ; « Prérequis : … » dans une Description, « construit avec React
», « Bibliothèque de composants React », « Application native macOS », « Conçu pour Linux » en « requis » ; négation
restée ouverte, code entre accents graves et champ Exemple jamais une exigence ; usages annexes restreints en « non
requis » ; côté requête, indifférence sans négation (« peu importe », « ça m'est égal », « whether or not », « … ou
pas », « or anything else »), segment d'indifférence qui vaut pour le précédent, « évite d'installer », « nothing
that needs », « X-free », « isn't an option », « replacement for », « moved off », « stop paying for ». Faux « requis
» restants sur t1 : deux exigences restreintes à un composant ou à un mode (« - React 18 (only if you use the
optional `<Viewer />` component) », « - Accès à un cluster Kubernetes (uniquement pour le mode distribué) »), la
famille la plus fréquente sur t2, et « - VRAM: none (CPU-only build of llama.cpp) ».

Erreurs restantes sur t2 (analysées après la mesure, non corrigées pour garder t2 indépendant) : faux « requis »
surtout d'une exigence restreinte à un module ou une fonction, dite après coup (« - CUDA (only for the dense depth
module) », « - FastAPI + uvicorn (for the web UI only) », « La surveillance des dossiers en temps réel ne fonctionne
que sous Windows »), d'une intégration offerte (« a Claude Code integration is offered alongside the main CLI »),
d'une migration ou d'une conversion (« Migrer progressivement des workflows n8n vers Temporal »), d'une négation non
lue (« Kubernetes inutile pour un usage perso », « React is only a devDependency ») ; côté requête, une plateforme à
remplacer (« a lightweight Kubernetes alternative ») n'est pas reconnue, ni « get off Zapier », « anything but
FastAPI », « FastAPI is overkill », les mentions en passant (« je suis tombé dessus en regardant une vidéo sur Zapier
») et « MacBook », « Apple Silicon Macs » pour macOS.

### Mesures finales

| Jeu | Version | nDCG@10 | MRR | R@5 | intrus@3 | intrus@5 | premiers | hors sujet @5 (A/B) | « forte » | « forte » non pertinentes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| N | f68b656 | 0,870 | 0,894 | 0,775 | 0,500 | 0,750 | 30 | 118 / 115 | 92 | 58 |
| N | V2b | 0,885 | 0,921 | 0,803 | 0,325 | 0,575 | 31 | 112 / 109 | 76 | 41 |
| N | **finale** | **0,888** | **0,921** | **0,817** | **0,275** | **0,450** | **31** | **110 / 107** | **75** | **40** |
| M | f68b656 | 0,791 | 0,795 | 0,698 | 0,567 | 0,667 | 19 | 95 / 93 | 82 | 54 |
| M | V2b | 0,818 | 0,847 | 0,710 | 0,367 | 0,533 | 21 | 94 / 92 | 74 | 46 |
| M | **finale** | **0,814** | **0,835** | **0,698** | **0,300** | **0,467** | **21** | **95 / 93** | **68** | **41** |

Sur M, la version finale reste au-dessus de la référence en nDCG@10 et en MRR, avec moins d'intrus, de « forte » et
de « forte » non pertinentes ; elle revient au niveau de la référence en R@5 et en hors sujet dans les 5 premiers
(M09, ci-dessus). Les corrections de la sixième revue et du banc ne changent ni ces mesures ni ces colonnes (dans
M07, des dépôts au-delà du 8e rang reculent d'un rang). M n'est plus un jeu de validation indépendant pour les
corrections des revues 2 à 6 et du banc (règle R6) :
ces chiffres décrivent le code final sur M, ils ne le valident pas. P@5 : N 0,350, M 0,304 (figés dans
`tests/test_qualification_lot5.py`). Accord des analystes sur l'ensemble des couples qualifiés : N 222 / 225, M
180 / 184.

## 7. Non-régression sur les 82 requêtes synthétiques

| | nDCG@10 | MRR | P@5 | R@5 | intrus@3 | intrus@5 | forte / requête | premiers attendus |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Référence f68b656 | 0,8755 | 0,8979 | 0,4225 | 0,8104 | 0,2683 | 0,5244 | 1,256 | 58 |
| V2b | 0,8766 | 0,8979 | 0,4254 | 0,8133 | 0,2561 | 0,5122 | 1,220 | 58 |
| **finale** | **0,8766** | **0,8979** | **0,4254** | **0,8133** | **0,2561** | **0,5122** | **1,220** | **58** |

Les corrections des revues 2 à 6 et du banc ne changent aucun des 82 classements de V2b (même rang, même niveau,
mêmes états d'exclusion pour chaque dépôt visible).

Requêtes modifiées : Q02 (FastAPI devenu contrainte : les dépôts pertinents remontent, nDCG@10 0,872 → 0,881),
N04 (« ne nécessite pas de GPU » : deepseek_ocr_app, dont les Prérequis citent un GPU NVIDIA, passe de la 3e à la
11e place ; P@5 0,6 → 0,8), K18 (« flux de travail » : une fiche dont seul le `Brique pour` cite n8n n'y répond
plus que par le concept voisin « automatisation », en partielle — datagouv-mcp passe de « forte » au 4e rang à
partielle au 8e ; nDCG@10 0,906 → 0,965), K11 (deepseek_ocr_app sort des 5 premiers, remplacé par olmocr, dont seule la Justification
dit qu'il exige un GPU : intrus inchangés), I18, K02, K23 (ordre ou dépôts non pertinents sortis des visibles).

## 8. Contrôles

- Tests : 2 564 réussis, 4 xfail (défauts encore connus) sous Python 3.13 et 3.10 (avant le lot 5 : 1 660 et 11),
  dont les cas des revues 2 à 6 (`tests/test_redecouverte_revue2.py` à `revue6.py`) et le banc
  (`tests/test_redecouverte_banc.py`) ; Ruff (E9, F63, F7, F82, F401, F811, F841, B) sans constat. Temps de
  recherche inchangé (corpus de 5 000 fiches : 0,15 à 1,2 s par requête, comme avant la cinquième revue).
- Lecture seule : aucune ligne du diff ne touche `_appel_notion`, `_LECTURES_AUTORISEES`, le réseau ni l'écriture ;
  tests de la garde Notion inchangés et verts. Expressions FTS : les termes ajoutés viennent du lexique et du
  tokenizer, toujours entre guillemets.
- Citations : chaque ligne `Exclusion` cite le champ et le texte stocké de la fiche (test d'affichage texte,
  Markdown et JSON).
- Réversible : FORMAT_INDEX, Notion-Version et le schéma inchangés ; revenir à `f68b656` suffit, sans
  resynchroniser.

## 9. Ce qu'il reste à vérifier sur la base réelle (lecture seule)

Sur votre poste, avec l'index des 443 fiches déjà construit (inutile de resynchroniser : le format d'index ne
change pas) :

```text
git checkout f68b656
python scripts\evaluer_redecouverte.py <chemin>\V01-V22.json --details > avant_V.txt
python scripts\evaluer_redecouverte.py <chemin>\SONDES_EXPLORATOIRES.json --details > avant_S.txt
git checkout claude/amazing-dijkstra-w25nu2
python scripts\evaluer_redecouverte.py <chemin>\V01-V22.json --details > apres_V.txt
python scripts\evaluer_redecouverte.py <chemin>\SONDES_EXPLORATOIRES.json --details > apres_S.txt
```

Points à regarder : V15 (SeaGOAT : la composition doit le trouver pour « recherche sémantique … code »), V17
(n8n-workflows), S03 (FlowMetr doit rester devant n8n-workflows : n8n est une contrainte après « avec »), S04
(activepieces : n8n est à remplacer), S07 (PDF : SeaGOAT ne doit plus y gagner de rang), et les lignes `Exclusion`
de vos propres requêtes « sans … ».

Lignes `Exclusion` : le banc (§ 6) estime qu'environ un « requis » sur cinq est faux. Sur une dizaine de vos
requêtes « sans Docker », « sans GPU », « pas sous Windows », « sans n8n », « alternative à Zapier », relever pour
chaque dépôt déclassé (« requis ») si le texte cité exige vraiment la technologie : une exigence restreinte à un
module ou une option, une intégration offerte, une migration sont les faux « requis » attendus. Si plus d'un
déclassement sur quatre est faux, garder `f68b656` pour les exclusions (§ 11).

## 10. Limites

- Jeux N et M : fiches fictives écrites par des rédacteurs automatiques, un seul rédacteur par jeu ; N a servi à
  corriger la version 2 et ne vaut plus validation ; M est petit (30 requêtes). Rien ne remplace la mesure réelle.
- Preuves d'exclusion lues par règles : une exigence formulée autrement (« à installer au préalable ») n'est pas
  vue ; une « alternative à n8n » qui dépend quand même de n8n ne serait pas déclassée ; une fiche qui écrit
  « semantic search across your source code » n'est trouvée que par la notion voisine.
- Rôles : « Our Zapier bill keeps growing. What could replace it » (N06) n'est pas reconnu comme référence ; un nom
  de produit à remplacer n'est pas ajouté à sa catégorie quand celle-ci est aussi demandée pour elle-même ;
  « remplacer », « migrer » restent cherchés comme mots libres.
- Listes fermées : mots d'usage qui gardent l'exclusion (`VERBES_EXCLUSION` : « sans devoir recompiler Docker »
  n'exclut pas Docker), autres sens de « code », marques de référence, verbes et adjectifs d'exigence. Une
  exigence formulée autrement est lue « mention » : le dépôt n'est alors pas déclassé, mais rien n'est affirmé.
- Défaut connu conservé : « pas pour analyser des PDF », « not for PDF analysis » (I26) ; correction générale
  rejetée au lot 4.
- Négations de la requête lues sur le verbe régi par listes fermées (`VERBES_SANS_NEGATION`, `VERBES_CAPACITE`,
  `VERBES_INDIFFERENCE`, `VERBES_QUALITE`) : une autre tournure de mémoire ou d'indifférence est lue comme une
  négation ordinaire ; « I'm not able to install Docker » laisse Docker seulement non cherché.
- Fiches, défauts antérieurs conservés : « Without a GPU, it won't run » (« sans » en tête, négation après la
  virgule) est lu « non requis » ; « - GPU (NVIDIA recommended) » lit le facultatif sur le GPU ; adverbes,
  exceptions et affiliations en listes fermées (`_ADVERBES`, `_EXCEPTIONS`, `_AFFILIATION`).
- Coût : une colonne personnelle de dizaines de milliers de caractères sans ponctuation qui cite des centaines de
  fois la technologie exclue reste lente (coût quadratique, entrées artificielles).
- `gitnotate.py` : une section de README « Optional dependencies » remplit la colonne Prérequis sans son titre ; le
  moteur ne peut pas lire ce facultatif.
- Lecture des exclusions mesurée sur le seul banc t2 (360 champs, 139 requêtes, rédigés par des agents) : 81,1 %
  de champs exacts, précision de « requis » 0,78 (27 faux « requis », 7,5 % des champs), rappel 0,77 ; 83,5 % des
  rôles de requête justes. Écart dev / t2 (94,1 % / 81,1 %) : les règles de champ restent ajustées à des tournures
  vues. Les erreurs de t2 (§ 6) ne sont pas corrigées : exigence restreinte à un module ou une fonction et dite
  après coup, intégration offerte, migration ou conversion, option, « inutile pour », « only a devDependency »,
  « se passer de » ; côté requête, plateforme à remplacer, « get off », « anything but », « overkill », « is
  fine », « whatever's simpler », « m'importe peu », mentions en passant, « MacBook » et « Apple Silicon » pour
  macOS.
- Méthode : six revues contradictoires successives n'ont pas convergé (chaque série de corrections cassait des
  tournures voisines) ; les règles ajoutées sont nombreuses et locales (listes fermées, fenêtres de mots). Une
  tournure nouvelle a une chance sur cinq environ d'être mal lue ; une erreur de lecture ne retire jamais un dépôt
  de la liste, elle le déclasse après les autres partielles ou le laisse à son rang.

## 11. Avis pour la revue de fusion

Avis : **la branche peut passer en revue de fusion, pas être fusionnée sans la vérification du § 9.**

- Acquis, mesurés sur des jeux qui n'ont pas servi à corriger : N (première passe), M (validation de V2b, une
  seule exécution), t1 (première mesure), t2 (mesure finale). Sur N et M, moins d'intrus et de « forte » non
  pertinentes à nDCG@10 égal ou meilleur ; recherche de code sémantique trouvée sans gain de rang sur les requêtes
  PDF ; identifiants n8n, Zapier, React, Kubernetes lus selon leur rôle ; 82 requêtes synthétiques sans
  régression. La pénalité de négation du lot 4 n'est pas réintroduite.
- Risque principal : un faux « requis » déclasse un bon dépôt (précision 0,78 sur t2). Le dépôt reste visible et la
  ligne `Exclusion` cite le texte qui a décidé, donc l'erreur se voit et se vérifie ; mais le lot n'a pas atteint
  la précision qu'une lecture par règles laissait espérer, et les corrections après M ne sont validées que par t2.
- Conditions : rejouer le § 9 sur les 443 fiches (V01-V22, sondes S01-S10, lignes `Exclusion`) ; examiner en
  revue de code les fonctions de lecture d'exigence (`sorte_mention` et ses aides, `analyser_requete`), les plus
  longues du lot. Si la vérification réelle dément le banc, deux replis réversibles sans resynchronisation :
  revenir à `f68b656`, ou garder les parties 1 et 2 et ne retenir de la partie 3 que l'affichage des preuves
  (sans déclassement).
- Patches de l'archive : 01 rejeté (aucun effet mesuré), 02 et 03 non retenus tels quels (§ 4) ; aucun n'est
  appliqué automatiquement.
