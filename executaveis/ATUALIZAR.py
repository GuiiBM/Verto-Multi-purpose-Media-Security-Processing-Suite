#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import platform
import subprocess

def print_colored(text, color="white"):
    colors = {
        "red": "\033[91m",
        "green": "\033[92m", 
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "white": "\033[97m",
        "reset": "\033[0m"
    }
    if platform.system() == "Windows":
        print(text)
    else:
        print(f"{colors.get(color, colors['white'])}{text}{colors['reset']}")

def run_command(cmd, shell=True):
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print_colored("========================================", "yellow")
    print_colored("    Atualizando yt-dlp", "yellow")
    print_colored("========================================", "yellow")
    print_colored("\nIsso resolve problemas de erro 403...\n", "white")
    
    system = platform.system()
    
    # Verificar ambiente virtual
    if not os.path.exists("venv"):
        print_colored("[ERRO] Ambiente virtual não encontrado!", "red")
        print_colored("Execute: python executaveis/INSTALAR.py", "white")
        input("Pressione Enter para sair...")
        sys.exit(1)
    
    # Definir comando pip baseado no sistema
    if system == "Windows":
        pip_cmd = "venv\\Scripts\\pip"
    else:
        pip_cmd = "venv/bin/pip"
    
    # Atualizar yt-dlp
    print_colored("Atualizando yt-dlp...", "white")
    success, output, error = run_command(f"{pip_cmd} install --upgrade yt-dlp")
    
    if success:
        print_colored("\n========================================", "green")
        print_colored("    Atualização Concluída!", "green")
        print_colored("========================================", "green")
    else:
        print_colored(f"\n[ERRO] Falha na atualização: {error}", "red")
    
    input("\nPressione Enter para sair...")

if __name__ == "__main__":
    main()