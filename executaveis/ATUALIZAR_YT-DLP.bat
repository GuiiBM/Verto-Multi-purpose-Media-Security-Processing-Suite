@echo off
title Atualizacao yt-dlp
color 0E

REM Ir para a pasta pai
cd /d "%~dp0.."

REM Executar atualizador Python universal
python executaveis\ATUALIZAR.py
if errorlevel 1 (
    python3 executaveis\ATUALIZAR.py
)

pause