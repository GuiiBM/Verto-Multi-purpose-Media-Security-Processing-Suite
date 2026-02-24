@echo off
title Instalacao de Dependencias
color 0B

REM Ir para a pasta pai
cd /d "%~dp0.."

REM Executar instalador Python universal
python executaveis\INSTALAR.py
if errorlevel 1 (
    python3 executaveis\INSTALAR.py
)

pause