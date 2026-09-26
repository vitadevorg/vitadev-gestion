@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0work\run_supabase_private.ps1" -Script "%~dp0work\validate_supabase_schema.py"
echo.
echo Copia el resultado en el chat. No se muestran contrasenas.
pause
