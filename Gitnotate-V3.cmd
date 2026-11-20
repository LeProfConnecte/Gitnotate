@echo off
setlocal
title Gitnotate V3 - Interface locale
set "GITNOTATE_DATA_DIR=%USERPROFILE%\gitnotate-validation"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Environnement Python V3 introuvable.
  echo Creez un environnement Python 3.10 isole dans le dossier V3.
  echo Consultez docs\V3_INTERFACE_WEB_LOCALE.md
  pause
  exit /b 2
)
"%PYTHON%" "%~dp0scripts\lancer_web_v3.py"
if errorlevel 1 pause
endlocal
