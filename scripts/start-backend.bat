@echo off
setlocal
call "%~dp0run_backend.bat"
exit /b %ERRORLEVEL%
