# Variantes mesurées au lot 5

Chaque variante du moteur mesurée dans docs/QUALIFICATION_LOT5.md (§ 4 et § 5) est conservée ici sous forme d'un
patch unifié contre la référence `f68b656` (fichiers `redecouverte.py` et `redecouverte_lexique.py`).

Empreinte d'une variante (`VARIANTES_CODE.txt`, `VARIANTES_V2_CODE.txt`) : les 16 premiers caractères hexadécimaux
du SHA-256 de la concaténation `redecouverte.py` puis `redecouverte_lexique.py` (octets bruts). `ref` est
`f68b656` lui-même (7ab3cbe5c216055c).

Reproduire une variante :

```text
git -c core.autocrlf=false worktree add ../variante f68b656
cd ../variante
git apply <chemin>/tests/fixtures/redecouverte/qualification_lot5/variantes/V2b.patch
python -c "import hashlib; print(hashlib.sha256(open('redecouverte.py','rb').read() + open('redecouverte_lexique.py','rb').read()).hexdigest()[:16])"
```

`core.autocrlf=false` : sous Windows, Git convertit par défaut les fins de ligne en CRLF, et l'empreinte (calculée sur
les octets LF du dépôt) ne correspond plus ; les patchs sont protégés par `.gitattributes` (`-text`).

| Variante | Contenu | Empreinte |
|---|---|---|
| P01, P02, P03 | patches 01, 02 et 03 de l'archive, appliqués seuls | 452204c4…, 8118d03a…, 7f6c2b75… |
| L1, L2 | partie 1 (recherche de code) ; partie 2 (identifiants selon leur rôle) | 45d2b369…, c7301895… |
| L23, L12, L123 | parties 2+3, 1+2, 1+2+3 (conflits de fusion résolus à la main) | 8ab930f1…, 7e0e0049…, 6620b473… |
| V2a, V2b, V2c | version 2 : parties 2 v2 + 3 + patch 01 ; parties 1 v2 + 2 v2 + 3 (retenue) ; parties 2 v2 + 3 | 1d99d630…, ba64acba…, 11634cbf… |

`tests/test_qualification_lot5.py` applique chaque patch à `f68b656` (lu par git) et vérifie l'empreinte ; le test
est sauté hors d'un dépôt git qui contient ce commit.
