#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import platform
import subprocess
import urllib.request
import zipfile
import tarfile
import shutil

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
    
    print_colored("\n========================================", "blue")
    print_colored("    Verto - Instalação Completa", "blue")
    print_colored("========================================", "blue")
    
    system = platform.system()
    print_colored(f"Sistema detectado: {system}", "green")
    
    # [1/5] Verificar Python
    print_colored("\n[1/5] Verificando Python...", "yellow")
    python_cmd = "python" if system == "Windows" else "python3"
    
    success, output, _ = run_command(f"{python_cmd} --version")
    if not success:
        print_colored("[ERRO] Python não encontrado!", "red")
        if system == "Windows":
            print_colored("Instale Python em: https://python.org", "white")
        else:
            print_colored("Instale: sudo apt install python3 python3-pip", "white")
        input("Pressione Enter para sair...")
        sys.exit(1)
    
    version = output.strip().split()[1]
    print_colored(f"Python {version} encontrado!", "green")
    
    # [2/5] Criar ambiente virtual
    print_colored("\n[2/5] Criando ambiente virtual...", "yellow")
    if os.path.exists("venv"):
        shutil.rmtree("venv")
    
    success, _, error = run_command(f"{python_cmd} -m venv venv")
    if not success:
        print_colored("[ERRO] Falha ao criar ambiente virtual", "red")
        if system != "Windows":
            print_colored("Instale: sudo apt install python3-venv", "white")
        input("Pressione Enter para sair...")
        sys.exit(1)
    
    # Ativar ambiente virtual
    if system == "Windows":
        pip_cmd = "venv\\Scripts\\pip"
        python_venv = "venv\\Scripts\\python"
    else:
        pip_cmd = "venv/bin/pip"
        python_venv = "venv/bin/python"
    
    # [3/5] Atualizar pip
    print_colored("\n[3/5] Atualizando pip...", "yellow")
    run_command(f"{python_venv} -m pip install --upgrade pip --quiet")
    
    # [4/8] Instalar dependências Python
    print_colored("\n[4/8] Instalando dependências Python...", "yellow")
    
    packages = [
        "Flask>=2.3.3",
        "yt-dlp>=2024.1.0",
        "PyPDF2",
        "Pillow",
        "pikepdf",
        "reportlab",
        "PyMuPDF",
        "rembg",
        "numpy"
    ]
    
    for i, package in enumerate(packages, 1):
        print_colored(f"  [{i}/{len(packages)}] Instalando {package.split('>=')[0]}...", "white")
        success, _, _ = run_command(f"{pip_cmd} install {package} --quiet")
        if not success:
            print_colored(f"  [AVISO] Falha ao instalar {package}", "yellow")
        else:
            print_colored(f"  ✓ {package.split('>=')[0]} instalado", "green")
    
    print_colored("\nDependências Python instaladas!", "green")
    
    # [5/8] Instalar FFmpeg
    print_colored("\n[5/8] Instalando FFmpeg...", "yellow")
    
    if system == "Windows":
        # Windows - baixar FFmpeg
        try:
            print_colored("Baixando FFmpeg para Windows...", "white")
            url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            urllib.request.urlretrieve(url, "ffmpeg.zip")
            
            with zipfile.ZipFile("ffmpeg.zip", 'r') as zip_ref:
                zip_ref.extractall(".")
            
            # Encontrar e copiar ffmpeg.exe
            for root, dirs, files in os.walk("."):
                if "ffmpeg.exe" in files:
                    shutil.copy(os.path.join(root, "ffmpeg.exe"), "ffmpeg.exe")
                    break
            
            # Limpar arquivos temporários
            os.remove("ffmpeg.zip")
            for item in os.listdir("."):
                if item.startswith("ffmpeg-master-latest"):
                    shutil.rmtree(item)
            
            if os.path.exists("ffmpeg.exe"):
                print_colored("FFmpeg instalado com sucesso!", "green")
            else:
                print_colored("[AVISO] FFmpeg não foi instalado", "yellow")
        except Exception as e:
            print_colored(f"[AVISO] Erro ao instalar FFmpeg: {e}", "yellow")
    
    else:
        # Linux - usar gerenciador de pacotes
        if shutil.which("ffmpeg"):
            print_colored("FFmpeg já está instalado!", "green")
        else:
            print_colored("Instalando FFmpeg...", "white")
            if shutil.which("apt"):
                success, _, _ = run_command("sudo apt update && sudo apt install -y ffmpeg")
            elif shutil.which("yum"):
                success, _, _ = run_command("sudo yum install -y ffmpeg")
            elif shutil.which("dnf"):
                success, _, _ = run_command("sudo dnf install -y ffmpeg")
            elif shutil.which("pacman"):
                success, _, _ = run_command("sudo pacman -S --noconfirm ffmpeg")
            else:
                print_colored("[AVISO] Instale FFmpeg manualmente", "yellow")
                success = False
            
            if success and shutil.which("ffmpeg"):
                print_colored("FFmpeg instalado com sucesso!", "green")
            else:
                print_colored("[AVISO] FFmpeg não foi instalado", "yellow")
    
    print_colored("\n========================================", "green")
    print_colored("    INSTALAÇÃO CONCLUÍDA COM SUCESSO!", "green")
    print_colored("========================================", "green")
    print_colored("\nTodas as dependências foram instaladas!", "white")
    print_colored("Verto está pronto para uso.", "white")
    
    if system == "Windows":
        print_colored("\nPróximo passo: Execute python executaveis\\INICIAR.py", "white")
    else:
        print_colored("\nPróximo passo: Execute python3 executaveis/INICIAR.py", "white")
    
    input("\nPressione Enter para sair...")

if __name__ == "__main__":
    main()