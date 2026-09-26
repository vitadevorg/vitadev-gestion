@echo off
cd /d "%~dp0"
python src/backend/auth_server.py --create-admin
pause
