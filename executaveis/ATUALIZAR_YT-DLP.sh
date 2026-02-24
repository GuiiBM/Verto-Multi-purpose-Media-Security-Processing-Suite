#!/bin/bash

# Ir para a pasta pai
cd "$(dirname "$0")/.."

# Executar atualizador Python universal
if command -v python3 &> /dev/null; then
    python3 executaveis/ATUALIZAR.py
elif command -v python &> /dev/null; then
    python executaveis/ATUALIZAR.py
else
    echo "[ERRO] Python não encontrado!"
    echo "Instale Python: sudo apt install python3"
    read -p "Pressione Enter para sair..."
fi