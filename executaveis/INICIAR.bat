@echo off
title YouTube MP4 Downloader
color 0A

REM Ir para a pasta pai
cd /d "%~dp0.."

REM Executar inicializador Python universal
python executaveis\INICIAR.py
if errorlevel 1 (
    python3 executaveis\INICIAR.py
)

pause