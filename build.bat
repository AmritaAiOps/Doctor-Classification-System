@echo off
REM One-shot build: frontend -> Python deps -> single-file exe. Run from repo root.
setlocal

echo 1/3 Building frontend...
REM Skip npm install when deps are already present -- saves time on rebuilds.
if not exist frontend\node_modules call npm install --prefix frontend || goto :fail
call npm run build --prefix frontend || goto :fail

echo 2/3 Installing Python + build deps (isolated venv)...
REM Build inside a dedicated venv so PyInstaller only ever sees the app's real
REM dependencies -- not whatever heavy packages (torch, etc.) happen to be in
REM the global environment. Keeps the build fast and the exe small.
if not exist .venv py -3 -m venv .venv || goto :fail
call .venv\Scripts\activate.bat || goto :fail
python -m pip install -r requirements.txt pyinstaller pywebview || goto :fail

echo Closing any running instance so the old exe isn't locked...
taskkill /F /IM HospitalReportAutomation.exe >nul 2>&1

echo 3/3 Packaging single-file exe...
python -m PyInstaller --noconfirm build_exe.spec || goto :fail

echo Done -^> dist\HospitalReportAutomation.exe
echo.
echo Build succeeded.
pause
exit /b 0

:fail
echo BUILD FAILED (see error above).
echo.
pause
exit /b 1
