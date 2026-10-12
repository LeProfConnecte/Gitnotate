# Qualification indépendante du lot 4 (requêtes I01-I26)

> **Corpus synthétique uniquement.** Ces mesures portent sur les 62 fiches fabriquées de
> `tests/fixtures/redecouverte/corpus.json`. Elles ne disent rien de la qualité du moteur sur la base Notion
> réelle de 443 fiches (`31db36ca-5523-811f-8266-c279e8b76c28`), qui n'a pas été lue depuis Claude Code.

## 1. Intégration (2026-10-12)

Pack reçu : `gitnotate_lot4_qualification_passation.zip` (SHA-256 `255bfa04…6d00d`), trois fichiers. Les
empreintes annoncées par `PASSATION_CLAUDE_CODE.md` sont vérifiées, et les deux originaux sont copiés à
l'octet près dans `tests/fixtures/redecouverte/` (fins de ligne protégées par `.gitattributes`, test
`tests/test_qualification_independante.py`) :

| Fichier | SHA-256 des octets | Empreinte des jugements (`--empreinte`) |
|---|---|---|
| `requetes_independantes_lot4.json` (original, 26 requêtes) | `e32f0fc29e75d5db4eef45e2f018ad148004cc941f4a6d5947dfeba6fcb8e6e7` | `5444aa4f44b4a40370238d857396917d11f4f48f6866fa3ee76b97bb466f0b8a` |
| `PROTOCOLE_QUALIFICATION_LOT4.md` (original) | `bbc9aaed67fa0b43bdadd7071182ff41ce1713b49d05aded17ed5d2f4a8f6f0d` | — |
| `requetes_independantes_lot4_derive_aucun_fort.json` (**dérivé, non identique**) | `5874d668cd5fc65040168f3fac26192f7de708fa68e2a60628adfb2ede0011ec` | `fcecaadda3b7e8959b0464c4bd555c83865e6cbe26e001501dada9585d990ee4` |

Le jeu dérivé ne diffère de l'original que par `"aucun_fort": true` sur I01, I02, I03 et I26, les quatre
requêtes sans dépôt en tête ni acceptable, pour que le contrôle automatique de l'évaluateur s'applique
(consigne de la passation). L'empreinte de l'original a été produite avant toute exécution du moteur sur ce
jeu. Aucun jugement, libellé, filtre ni ordre n'a été modifié.

## 2. Résultats initiaux (moteur de `702f6cb`, avant toute correction)

Index reconstruit depuis une capture du corpus (`sync --depuis`, 62 fiches, 51 dépôts), puis
`python scripts/evaluer_redecouverte.py tests/fixtures/redecouverte/requetes_independantes_lot4.json --details`.
Définitions des mesures : `docs/REDECOUVERTE.md` § 9 (P@5 = pertinents parmi les 5 premiers / 5 ; R@5 =
pertinents parmi les 5 premiers / pertinents jugés). Le moteur est identique depuis `16e163f`.

Moyennes (22 requêtes avec des attendus pour nDCG@10, P@5, R@5 et MRR ; 26 pour les intrus) :
nDCG@10 **0,90** · P@5 **0,24** · R@5 **0,92** · MRR **0,87** · intrus@3 **0,38** · intrus@5 **0,58**.
P@5 est mécaniquement bas : 21 requêtes sur 22 n'ont qu'un ou deux dépôts pertinents jugés (maximum
atteignable 0,20 ou 0,40) ; la moyenne des maxima atteignables est 0,26.

Requêtes sans réponse attendue (jeu dérivé) : `aucun_fort non respecté pour 0 requête sur 4`.

| Requête | nDCG@10 | P@5 | R@5 | MRR | intrus@3 | intrus@5 | « forte » | Visibles | 5 premiers (F forte, P partielle) |
|---|---|---|---|---|---|---|---|---|---|
| I01 | — | — | — | — | 1 | 1 | 0 | 1 | caviraoss/pagelm (P) |
| I02 | — | — | — | — | 0 | 0 | 0 | 0 | (aucun) |
| I03 | — | — | — | — | 2 | 2 | 0 | 6 | ohf-voice/piper1-gpl (P), resemble-ai/chatterbox (P), bytedance/dolphin (P), docling-project/docling (P), jesseduffield/lazygit (P) |
| I04 | 0,52 | 0,20 | 0,50 | 0,11 | 0 | 0 | 0 | 36 | caviraoss/pagelm (P), browser-use/browser-use (P), microsoft/generative-ai-for-beginners (P), lfnovo/open-notebook (P), unclecode/crawl4ai (P) |
| I05 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 0 | 1 | 3 | evidentlyai/evidently (F), bytedance/dolphin (P), neuml/txtai (P) |
| I06 | 1,00 | 0,20 | 1,00 | 1,00 | 1 | 2 | 2 | 29 | marimo-team/marimo (F), lfnovo/open-notebook (F), docling-project/docling (P), caviraoss/pagelm (P), thealgorithms/python (P) |
| I07 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 0 | 1 | 11 | microsoft/omniparser (F), browser-use/browser-use (P), virattt/dexter (P), assafelovic/gpt-researcher (P), openhands/openhands (P) |
| I08 | 0,96 | 0,40 | 0,67 | 1,00 | 0 | 0 | 2 | 14 | bytedance/dolphin (F), paddlepaddle/paddleocr (F), docling-project/docling (P), rdumasia303/deepseek_ocr_app (P), vectifyai/pageindex (P) |
| I09 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 0 | 1 | 7 | jesseduffield/lazygit (F), rdumasia303/deepseek_ocr_app (P), marimo-team/marimo (P), davila7/claude-code-templates (P), virattt/ai-hedge-fund (P) |
| I10 | 0,00 | 0,00 | 0,00 | 0,00 | 1 | 1 | 2 | 17 | davila7/claude-code-templates (F), anomalyco/opencode (F), jesseduffield/lazygit (P), ai4finance-foundation/finrobot (P), resemble-ai/chatterbox (P) |
| I11 | 0,94 | 0,40 | 1,00 | 1,00 | 1 | 1 | 3 | 32 | jlowin/fastmcp (F), datagouv/datagouv-mcp (F), invest-composer/composer-trade-mcp (F), modelcontextprotocol/servers (P), punkpeye/awesome-mcp-servers (P) |
| I12 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 0 | 1 | 19 | datagouv/datagouv-mcp (F), virattt/dexter (P), allenai/olmocr (P), modelcontextprotocol/servers (P), punkpeye/awesome-mcp-servers (P) |
| I13 | 1,00 | 0,20 | 1,00 | 1,00 | 1 | 1 | 1 | 11 | davila7/claude-code-templates (F), huginn/huginn (P), openhands/openhands (P), evidentlyai/evidently (P), browser-use/browser-use (P) |
| I14 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 0 | 1 | 8 | huginn/huginn (F), davila7/claude-code-templates (P), evidentlyai/evidently (P), bidingcc/buildingai (P), caviraoss/pagelm (P) |
| I15 | 0,80 | 0,40 | 1,00 | 0,50 | 0 | 0 | 1 | 2 | huginn/huginn (F), rssnext/folo (P) |
| I16 | 0,93 | 0,40 | 1,00 | 1,00 | 0 | 0 | 1 | 11 | neuml/txtai (F), rdumasia303/deepseek_ocr_app (P), paddlepaddle/paddleocr (P), docling-project/docling (P), infiniflow/ragflow (P) |
| I17 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 0 | 1 | 10 | vectifyai/pageindex (F), assafelovic/gpt-researcher (P), docling-project/docling (P), paddlepaddle/paddleocr (P), lfnovo/open-notebook (P) |
| I18 | 1,00 | 0,20 | 1,00 | 1,00 | 1 | 1 | 1 | 7 | remotion-dev/remotion (F), gyoridavid/short-video-maker (P), rdumasia303/deepseek_ocr_app (P), microsoft/omniparser (P), marimo-team/marimo (P) |
| I19 | 0,94 | 0,40 | 1,00 | 1,00 | 0 | 0 | 1 | 10 | gyoridavid/short-video-maker (F), public-apis/public-apis (P), huginn/huginn (P), remotion-dev/remotion (P), invest-composer/composer-trade-mcp (P) |
| I20 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 1 | 1 | 4 | ohf-voice/piper1-gpl (F), huginn/huginn (P), awesome-selfhosted/awesome-selfhosted (P), ggml-org/llama.cpp (P) |
| I21 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 1 | 0 | 28 | thealgorithms/python (P), lfnovo/open-notebook (P), marimo-team/marimo (P), jlowin/fastmcp (P), docling-project/docling (P) |
| I22 | 0,63 | 0,20 | 1,00 | 0,50 | 0 | 0 | 0 | 10 | huginn/huginn (P), awesome-selfhosted/awesome-selfhosted (P), rdumasia303/deepseek_ocr_app (P), anomalyco/opencode (P), firefly-iii/firefly-iii (P) |
| I23 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 0 | 1 | 7 | invest-composer/composer-trade-mcp (F), gyoridavid/short-video-maker (P), modelcontextprotocol/servers (P), punkpeye/awesome-mcp-servers (P), datagouv/datagouv-mcp (P) |
| I24 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 1 | 1 | 12 | firefly-iii/firefly-iii (F), awesome-selfhosted/awesome-selfhosted (P), huginn/huginn (P), virattt/dexter (P), invest-composer/composer-trade-mcp (P) |
| I25 | 1,00 | 0,20 | 1,00 | 1,00 | 0 | 0 | 1 | 1 | evidentlyai/evidently (F) |
| I26 | — | — | — | — | 2 | 3 | 0 | 9 | lfnovo/open-notebook (P), caviraoss/pagelm (P), docling-project/docling (P), vectifyai/pageindex (P), paddlepaddle/paddleocr (P) |

Les dépôts « visibles » sont les correspondances forte et partielle (les faibles sont masquées par défaut).

## 3. Avant et après l'affinage, sur ce jeu

« Avant » : moteur de `a679661` (dernière version vérifiée avant l'affinage), avec son propre index ; « après » :
moteur actuel (identique depuis `16e163f`). Même capture du corpus, mêmes jugements, mêmes définitions (la
fonction `mesurer()` actuelle appliquée aux classements des deux versions).

| Mesure (22 requêtes avec attendus ; intrus sur 26) | Avant | Après |
|---|---|---|
| nDCG@10 | 0,857 | 0,897 |
| MRR | 0,836 | 0,869 |
| P@5 | 0,236 | 0,236 |
| R@5 | 0,917 | 0,917 |
| Attendu en tête au 1er rang | 17 / 22 | 18 / 22 |
| intrus@3 (total / moyenne) | 15 / 0,58 | 10 / 0,38 |
| intrus@5 (total / moyenne) | 19 / 0,73 | 15 / 0,58 |
| Correspondances « forte », toutes requêtes | 24 | 24 |

Seules I25 (« rather than » reconnu comme comparaison : nDCG 0,50 → 1,00) et I04 (nDCG 0,14 → 0,52) changent les
mesures. La baisse des intrus vient surtout des requêtes sans réponse (I01, I02, I26) et de I25.

## 4. Faux positifs non listés (double qualification)

Les listes `a_exclure` ne sont pas exhaustives. Deux analystes ont qualifié **indépendamment** chaque dépôt
visible des 5 premiers rangs (et toute « forte » au-delà) d'après le texte des fiches : pertinent, plausible
ou hors sujet. Accord : 226 éléments sur 230 (98,3 %, kappa de Cohen 0,96) ; les 2 désaccords (I16 ragflow,
I24 awesome-selfhosted) ont été tranchés en relisant les fiches. Ce sont des jugements d'analyste, distincts
des jugements de référence, qui restent inchangés.

| Mesure (26 requêtes) | Avant | Après |
|---|---|---|
| Hors sujet **non listés** dans les 3 premiers | 36 | 35 |
| Hors sujet **non listés** dans les 5 premiers | 71 | 67 |
| Hors sujet, listés ou non, dans les 5 premiers | 89 | 81 |
| « forte » donnée à un dépôt hors sujet | 7 | 5 |
| 1er rang hors sujet | 8 | 5 |
| P@5 selon les analystes (pertinent seul / pertinent ou plausible) | 0,16 / 0,23 | 0,16 / 0,23 |

L'évaluateur ne voit que les intrus listés : dans les 5 premiers, il manque environ 4,5 fois plus de faux
positifs qu'il n'en compte. « forte » hors sujet après l'affinage : I06 open-notebook (nouvelle), I10
claude-code-templates et opencode, I11 datagouv-mcp et composer-trade-mcp. Causes récurrentes : un seul mot
libre suffit pour une correspondance partielle (« modèle », « interface », « long », « texte »,
« implémentation »), homonymies (notebook / Notebook LM, notes, « source » dans « open source », « code » dans
« Claude Code »), contrainte « Python » trouvée par le seul Langage GitHub.

## 5. Les quatre requêtes sans réponse attendue (jeu dérivé `aucun_fort`)

Règle du protocole : aucune correspondance forte sans preuve pertinente. Elle est respectée (0 sur 4, avant
comme après, fiches sans dépôt comprises). Mais **tous** les dépôts encore visibles sont hors sujet :

| Requête | Visibles avant → après | « forte » avant → après | intrus@3 après | Ce qui remonte (après) et pourquoi |
|---|---|---|---|---|
| I01 notes et absences des élèves | 7 → 1 | 0 → 0 | 1 | pagelm (partielle) : homonymie « notes structurées » |
| I02 poutres en béton armé, Eurocode 2 | 2 → 0 | 0 → 0 | 0 | rien (« 2 » n'est plus cherché ; notion génie civil absente du corpus) |
| I03 transcrire les paroles d'une réunion | 6 → 6 | 0 → 0 | 2 | piper1-gpl et chatterbox : synthèse vocale au lieu de reconnaissance ; OCR via « texte » |
| I26 présences et absences à l'école, « pas pour analyser des PDF » | 12 → 9 | 2 → 0 | 2 | 8 outils PDF : la négation n'est pas appliquée (§ 6) |

## 6. Négations et ambiguïtés

| Cas | Traitement | Effet | Gravité |
|---|---|---|---|
| I26 « pas pour analyser des PDF » | **défaut** : « pour » figure dans `FIN_NEGATION` et ferme la négation ouverte par « pas » avant tout mot ; « analyser » et « PDF » restent cherchés (identique avant et après) | 8 outils PDF visibles, dont 2 intrus listés dans les 3 premiers | élevée |
| I17 « sans créer de base vectorielle » | « créer » et « base vectorielle » retirés et affichés | pageindex 1er (forte) ; aucun porteur visible | aucune |
| I20 « hors ligne », « sans service cloud » | « hors ligne » reconnu comme expression (non nié) ; « service », « cloud » retirés | piper 1er (forte) | aucune |
| I25 « rather than watching RSS news feeds » | après : comparaison reconnue (rôle référence) ; avant : non | huginn passe de forte au rang 1 à faible masqué | corrigé par l'affinage |
| Toutes | un mot nié est seulement retiré ; un dépôt qui porte la propriété exclue n'est ni déclassé ni signalé (choix de conception documenté) | limite connue | modérée |

Ambiguïtés : notes (scolaires / documentaires, I01), notebook (Python / Notebook LM, I06 et I04), parole
(reconnaissance / synthèse, I03), texte (format cible / mode texte / OCR, I03), surveillance (dérive ML / flux,
I05 et I25 : correctement départagées après l'affinage), structures (I02 : aucune confusion), « en ligne de
commande » lu comme « en ligne » (site web) avant « ligne de commande » (I13).

## 7. Échecs et régressions qualitatives

Échecs du moteur actuel (attendu en tête absent du 1er rang) : I10 (bat absent : sa fiche ne contient que
« A cat(1) clone with wings. » ; le jugement repose sur une connaissance extérieure à la fiche), I04 (marimo
9e : fiche pauvre, « interactifs » seulement dans la Justification), I15 (folo 2e derrière huginn : fiche
réduite à « Suivez tout au même endroit »), I22 (awesome-selfhosted 2e : « auto-héberger » et « catalogue »
absents du lexique). Les échecs I10 et I15 tiennent au texte des fiches plus qu'au classement.

Régressions qualitatives de l'affinage (sans effet sur les mesures) :
- I06 : open-notebook (à exclure, homonymie « Notebook LM ») passe de partielle à **forte** ;
- I15 : huginn (acceptable) passe de partielle à **forte**, devant l'attendu en tête ;
- les deux atteignent exactement le seuil (couverture = 0,600 = 1,5 / 2,5) : effet du poids fixe des
  contraintes (Python, terminal) et des mots libres ; résultat fragile ;
- I09, I10, I04 : des dépôts trouvés par le seul Langage Python ou par « interface » montent dans les rangs.

## 8. Corrections candidates (non appliquées)

Mesurées sur des copies du code, sans rien modifier dans le dépôt ; à appliquer seulement après accord, dans
un commit séparé, puis à comparer sur les mêmes jeux figés :

| Piste | Effet mesuré sur copie | Risque |
|---|---|---|
| Négation : un mot de `FIN_NEGATION` placé juste après le déclencheur ne la ferme pas (I26) | I26 : « analyser » et « PDF » affichés comme niés, intrus@3 2 → 0 (moyenne du jeu 0,38 → 0,31) ; aucun autre changement sur les 26 + 34 requêtes (contre-vérifié une seconde fois, indépendamment) | faible |
| Seuil « forte » strict (couverture > 0,60) | retire les fortes d'I06 et I15 ; aucun changement sur les 34 requêtes de référence | faible |
| Expressions : une expression plus longue commençant dans la correspondance courante l'emporte (« ligne de commande ») | seule I13 change | faible |
| Sans notion du lexique dans le besoin, « forte » exige tous les essentiels | I10 : les 2 fortes hors sujet deviennent partielles ; rien d'autre ne change | faible |
| Lexique : « code source » / « coloration syntaxique », « narration » / « parlée », « auto-héberger » / « catalogue » | I10 : 17 → 3 visibles ; I20 : preuve réelle ; I22 : 1er rang mais un intrus entre dans les 5 premiers | faible à modéré |

Écartées : pondération des mots libres à 0,75 (régresse H04, Q06, Q09, H02), « un mot libre seul ne suffit
pas » (Q10 perd son attendu, folo et awesome-selfhosted disparaissent), suppression du voisinage Claude Code
(« alternative à Claude Code » ne trouverait plus de concurrents).

## 9. Limites de cette qualification

- Corpus synthétique de 62 fiches : aucune mesure sur la base réelle de 443 fiches (v7.1), qui n'a pas été lue
  depuis Claude Code (aucun jeton en lecture seule dans la session). La validation réelle reste **non réalisée**.
- 21 requêtes sur 22 n'ont qu'un ou deux dépôts pertinents : P@5 est plafonné et peu informatif ; R@5 et MRR
  sont sensibles à une seule requête.
- Les qualifications « hors sujet » sont celles de deux analystes de cette session (accord élevé, mais même
  équipe que le moteur) ; les jugements de référence de I10, I11, I15 et I04 s'appuient en partie sur une
  connaissance des produits réels absente des fiches.
