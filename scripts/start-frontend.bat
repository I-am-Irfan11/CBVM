@echo off
setlocal
call "%~dp0run_frontend.bat"
exit /b %ERRORLEVEL%
