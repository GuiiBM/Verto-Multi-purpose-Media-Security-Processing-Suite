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

def porta_ocupada(porta=5000):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def verto_respondendo(porta=5000):
    """A porta está ocupada pelo próprio Verto (aberto em outro terminal)?"""
    from urllib.request import urlopen
    try:
        with urlopen(f"http://127.0.0.1:{porta}/automacoes/estado", timeout=2) as r:
            return b'"success"' in r.read(2000)
    except Exception:
        return False


def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print_colored("========================================", "green")
    print_colored("    YouTube MP4 Downloader v1.0", "green")
    print_colored("========================================", "green")
    
    system = platform.system()
    print_colored(f"\nSistema: {system}", "white")
    print_colored(f"Pasta atual: {os.getcwd()}", "white")
    
    # Verificar se app.py existe
    if not os.path.exists("app.py"):
        print_colored("\n[ERRO] app.py não encontrado nesta pasta!", "red")
        input("Pressione Enter para sair...")
        sys.exit(1)
    
    # Verificar ambiente virtual
    if not os.path.exists("venv"):
        print_colored("\n[ERRO] Ambiente virtual não encontrado!", "red")
        print_colored("Execute: python executaveis/INSTALAR.py", "white")
        input("Pressione Enter para sair...")
        sys.exit(1)
    
    # Definir comandos baseado no sistema
    if system == "Windows":
        python_cmd = "venv\\Scripts\\python"
        pip_cmd = "venv\\Scripts\\pip"
    else:
        python_cmd = "venv/bin/python"
        pip_cmd = "venv/bin/pip"
    
    # Verificar Flask
    print_colored("\nVerificando Flask...", "white")
    success, _, _ = run_command(f"{pip_cmd} show flask")
    if not success:
        print_colored("[ERRO] Flask não encontrado!", "red")
        print_colored("Execute: python executaveis/INSTALAR.py", "white")
        input("Pressione Enter para sair...")
        sys.exit(1)
    
    # Verificar yt-dlp
    print_colored("Verificando yt-dlp...", "white")
    success, _, _ = run_command(f"{pip_cmd} show yt-dlp")
    if not success:
        print_colored("[ERRO] yt-dlp não encontrado!", "red")
        print_colored("Execute: python executaveis/INSTALAR.py", "white")
        input("Pressione Enter para sair...")
        sys.exit(1)
    
    # Porta 5000 ocupada: se for o Verto, é só abrir; senão, explica como liberar.
    if porta_ocupada():
        if verto_respondendo():
            print_colored("\nO Verto já está rodando (em outro terminal ou janela).", "green")
            print_colored("    ACESSE: http://localhost:5000", "yellow")
            try:
                import webbrowser
                webbrowser.open("http://localhost:5000")
            except Exception:
                pass
            print_colored("\nPara reiniciar, feche a outra janela (Ctrl+C nela) e rode o INICIAR de novo.", "white")
        else:
            print_colored("\n[ERRO] A porta 5000 está sendo usada por outro programa.", "red")
            if system == "Windows":
                print_colored("Descubra qual: netstat -ano | findstr :5000  (e feche pelo Gerenciador de Tarefas)", "white")
            else:
                print_colored("Descubra qual: ss -ltnp | grep :5000  (ou: lsof -i :5000) e feche o programa.", "white")
        input("Pressione Enter para sair...")
        sys.exit(0)

    print_colored("\nTudo OK! Iniciando servidor...", "green")
    print_colored("\n========================================", "yellow")
    print_colored("    ACESSE: http://localhost:5000", "yellow")
    print_colored("========================================", "yellow")
    print_colored("\nPressione Ctrl+C para parar\n", "white")
    
    # Iniciar aplicação
    try:
        subprocess.run([python_cmd, "app.py"])
    except KeyboardInterrupt:
        print_colored("\n\nServidor parado.", "white")
    except Exception as e:
        print_colored(f"\n[ERRO] {e}", "red")
    
    input("Pressione Enter para sair...")

if __name__ == "__main__":
    main()