@echo off
setlocal
cd /d "%~dp0"
set "GITNOTATE_DATA_DIR=%USERPROFILE%\gitnotate-validation"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [Gitnotate V3] Environnement absent.
  echo Executez d'abord installer_web_v3.cmd dans ce dossier.
  pause
  exit /b 1
)
echo [Gitnotate V3] Catalogue local: %GITNOTATE_DATA_DIR%
echo [Gitnotate V3] Interface: http://127.0.0.1:8765
echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0web_v3.py"
if errorlevel 1 (
  echo ERREUR: verifiez le port 8765 et les dependances.
  pause
)
endlocal
