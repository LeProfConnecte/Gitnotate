@echo off
setlocal
cd /d "%~dp0"
echo [Gitnotate V3] Installation isolee dans .venv ...
py -3.10 -m venv "%~dp0.venv"
if errorlevel 1 (
  echo ERREUR: Python 3.10 n'est pas accessible via py -3.10.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" -r "%~dp0requirements-web.txt"
if errorlevel 1 (
  echo ERREUR: installation des dependances interrompue.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -c "import fastapi, uvicorn, requests, dotenv; print('Dependances V3 OK')"
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo Installation terminee. Double-cliquez sur Gitnotate-V3.cmd.
pause
endlocal
