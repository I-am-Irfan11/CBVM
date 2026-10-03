@echo off
setlocal
cd /d "%~dp0.."
if not exist "test-results" mkdir test-results
set "GATELOG_TEST_TEMP=..\test-results\pytest-%RANDOM%-%RANDOM%"
pushd backend
"..\.venv\Scripts\python.exe" -B -m pytest -q -p no:cacheprovider --basetemp=%GATELOG_TEST_TEMP%
set "GATELOG_RESULT=%ERRORLEVEL%"
popd
exit /b %GATELOG_RESULT%
