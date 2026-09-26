@echo off
cd /d "%~dp0"
node build.js
if errorlevel 1 exit /b 1
python src/backend/auth_server.py
pause
