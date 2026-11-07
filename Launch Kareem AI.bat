@echo off
setlocal
cd /d "%~dp0"
if exist "..\.venv-kareem\Scripts\pythonw.exe" (
  start "" "..\.venv-kareem\Scripts\pythonw.exe" bootstrap.py
  exit /b
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -c "import PySide6, httpx, keyring" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
)
start "" ".venv\Scripts\pythonw.exe" bootstrap.py
exit /b
:failed
echo Setup could not finish. Install Python 3.11 or newer, then try again.
pause
