@echo off
REM One-shot build: frontend -> Python deps -> single-file exe. Run from repo root.
setlocal

echo 1/3 Building frontend...
call npm install --prefix frontend || goto :fail
call npm run build --prefix frontend || goto :fail

echo 2/3 Installing Python + build deps...
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
