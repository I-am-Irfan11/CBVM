@echo off
setlocal
cd /d "%~dp0.."
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required. Install Python and enable Add Python to PATH.
  exit /b 1
)
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo Node.js 22 LTS or later is required. Restart your terminal after installation.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r backend\requirements-dev.txt
if errorlevel 1 exit /b 1
if not exist ".env" copy /y ".env.example" ".env" >nul
pushd frontend
call npm.cmd ci
set "GATELOG_RESULT=%ERRORLEVEL%"
popd
if not "%GATELOG_RESULT%"=="0" exit /b %GATELOG_RESULT%
echo Setup complete. Run scripts\run_backend.bat and scripts\run_frontend.bat in separate terminals.
