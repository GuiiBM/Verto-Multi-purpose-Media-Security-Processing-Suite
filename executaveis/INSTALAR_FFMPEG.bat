@echo off
title Instalacao FFmpeg
color 0C
echo.
echo ========================================
echo    Instalando FFmpeg para Alta Qualidade
echo ========================================
echo.
echo FFmpeg e necessario para combinar video e audio
echo em alta qualidade (1080p, 720p, etc.)
echo.
echo Instalando via pip...
pip install ffmpeg-python
echo.
echo Tentando instalar ffmpeg binario...
pip install ffmpeg
echo.
echo ========================================
echo    Instalacao Concluida!
echo ========================================
echo.
echo Agora voce pode baixar videos em alta qualidade!
echo Execute INICIAR.bat para testar.
echo.
pause