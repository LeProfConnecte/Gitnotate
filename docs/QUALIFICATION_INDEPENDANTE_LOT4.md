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
