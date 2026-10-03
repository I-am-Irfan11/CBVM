@echo off
setlocal
cd /d "%~dp0..\frontend"
if not exist "node_modules" (
  echo Run scripts\setup.bat first.
  exit /b 1
)
call npm.cmd run dev
