@echo off
setlocal
cd /d "%~dp0.."
if not exist "test-results" mkdir test-results
pushd backend
"..\.venv\Scripts\python.exe" -m pytest -q --basetemp=..\test-results\pytest
set "GATELOG_RESULT=%ERRORLEVEL%"
popd
exit /b %GATELOG_RESULT%
