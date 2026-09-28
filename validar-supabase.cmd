@echo off
cd /d "%~dp0"
if not exist "work\run_supabase_private.ps1" goto missing
if not exist "work\validate_supabase_schema.py" goto missing
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0work\run_supabase_private.ps1" -Script "%~dp0work\validate_supabase_schema.py"
echo.
echo Copia el resultado en el chat. No se muestran contrasenas.
pause
exit /b
:missing
echo Faltan los scripts privados de validacion en work\ (no se versionan).
echo Pedilos al responsable de la migracion a Supabase.
pause
exit /b 1
