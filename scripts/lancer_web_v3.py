#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lanceur Gitnotate V3-C : ouverture uniquement sur 127.0.0.1.

Ne démarre rien sur le réseau local ni sur Internet. N'installe aucune dépendance.
"""
from __future__ import annotations
import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = Path.home() / "gitnotate-validation"

def main() -> int:
    if not os.environ.get("GITNOTATE_DATA_DIR"):
        if not DEFAULT_DATA.is_dir():
            print("STOP : dossier privé Gitnotate absent : " + str(DEFAULT_DATA))
            return 2
        os.environ["GITNOTATE_DATA_DIR"] = str(DEFAULT_DATA)
    try:
        import uvicorn
    except ImportError:
        print("STOP : FastAPI/Uvicorn non installés dans cet environnement virtuel.")
        print("Installez requirements-web-v3.txt puis relancez le lanceur.")
        return 2
    address = "http://127.0.0.1:8765"
    print("Gitnotate V3-C — interface web locale")
    print("Catalogue privé : " + os.environ["GITNOTATE_DATA_DIR"])
    print("Accès : " + address)
    print("Aucun accès depuis le réseau local. Fermez cette fenêtre pour arrêter le serveur.")
    threading.Timer(1.2, lambda: webbrowser.open(address)).start()
    try:
        uvicorn.run("web_v3:app", app_dir=str(ROOT), host="127.0.0.1", port=8765,
                    reload=False, workers=1, log_level="warning", access_log=False,
                    proxy_headers=False)
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print("STOP : impossible de démarrer le serveur local (" + type(exc).__name__ + ")")
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
