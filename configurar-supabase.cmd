@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configurar-supabase.ps1"
if errorlevel 1 pause
