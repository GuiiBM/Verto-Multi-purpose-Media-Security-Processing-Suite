#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import platform
import subprocess
import urllib.request
import zipfile
import tarfile
import shutil
import time

def format_eta(seconds):
    seconds = max(0, int(seconds))
    horas, resto = divmod(seconds, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas}h{minutos:02d}m{segundos:02d}s"
    if minutos:
        return f"{minutos}m{segundos:02d}s"
    return f"{segundos}s"

def print_progress_bar(current, total, start_time, prefix="Progresso geral", bar_length=30):
    fraction = min(current / total, 1.0) if total else 1.0
    filled = int(bar_length * fraction)
    bar = "█" * filled + "░" * (bar_length - filled)
    elapsed = time.time() - start_time
    if current > 0:
        eta_text = format_eta((elapsed / current) * (total - current))
    else:
        eta_text = "calculando..."
    percent = int(fraction * 100)
    line = f"\r{prefix}: |{bar}| {percent}% ({current}/{total}) - Tempo restante estimado: {eta_text}   "
    sys.stdout.write(line)
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")

def make_download_progress_hook(start_time, label="Baixando"):
    def hook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        elapsed = time.time() - start_time
        bar_length = 30

        if total_size > 0:
            fraction = min(downloaded / total_size, 1.0)
            filled = int(bar_length * fraction)
            bar = "█" * filled + "░" * (bar_length - filled)
            percent = int(fraction * 100)
            speed = downloaded / elapsed if elapsed > 0 else 0
            remaining = (total_size - downloaded) / speed if speed > 0 else 0
            eta_text = format_eta(remaining)
            speed_mb = speed / (1024 * 1024)
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            line = (f"\r{label}: |{bar}| {percent}% "
                     f"({downloaded_mb:.1f}/{total_mb:.1f} MB) - "
                     f"{speed_mb:.1f} MB/s - ETA: {eta_text}   ")
        else:
            downloaded_mb = downloaded / (1024 * 1024)
            line = f"\r{label}: {downloaded_mb:.1f} MB baixados...   "

        sys.stdout.write(line)
        sys.stdout.flush()
    return hook

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
    print_colored("    LocalTools - Instalação Completa", "blue")
    print_colored("========================================", "blue")
    
    system = platform.system()
    print_colored(f"Sistema detectado: {system}", "green")
    
    # [1/6] Verificar Python
    print_colored("\n[1/6] Verificando Python...", "yellow")
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
    
    # [2/6] Criar ambiente virtual
    print_colored("\n[2/6] Criando ambiente virtual...", "yellow")
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
    
    # [3/6] Atualizar pip
    print_colored("\n[3/6] Atualizando pip...", "yellow")
    run_command(f"{python_venv} -m pip install --upgrade pip --quiet")

    # [4/6] Instalar dependências Python
    print_colored("\n[4/6] Instalando dependências Python...", "yellow")
    
    packages = [
        "Flask>=2.3.3",
        "yt-dlp>=2026.8.19",
        "yt-dlp-ejs>=0.8.0",
        "PyPDF2",
        "Pillow",
        "pikepdf",
        "reportlab",
        "PyMuPDF",
        "rembg[cpu]",
        "numpy",
        "qrcode[pil]>=7.4.2",
        "segno>=1.6.0",
        "moviepy",
        "SpeechRecognition",
        "pycryptodome",
        "readability-lxml",
        "beautifulsoup4",
        "requests",
        "html2text",
        "ebooklib",
        "lxml",
        "demucs",
        "soundfile",
        "python-docx",
        "python-pptx",
        "openpyxl"
    ]
    
    total_etapas = len(packages) + 3  # pacotes + FFmpeg + LibreOffice + runtime JS (Deno)
    etapa_atual = 0
    inicio_instalacao = time.time()

    for i, package in enumerate(packages, 1):
        print_colored(f"  [{i}/{len(packages)}] Instalando {package.split('>=')[0]}...", "white")
        success, _, _ = run_command(f'{pip_cmd} install "{package}" --quiet')
        if not success:
            print_colored(f"  [AVISO] Falha ao instalar {package}", "yellow")
        else:
            print_colored(f"  ✓ {package.split('>=')[0]} instalado", "green")
        etapa_atual += 1
        print_progress_bar(etapa_atual, total_etapas, inicio_instalacao)

    print_colored("Dependências Python instaladas!", "green")
    
    # [5/7] Instalar FFmpeg
    print_colored("\n[5/7] Instalando FFmpeg...", "yellow")
    
    if system == "Windows":
        # Windows - baixar FFmpeg
        try:
            print_colored("Baixando FFmpeg para Windows...", "white")
            url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            urllib.request.urlretrieve(
                url, "ffmpeg.zip",
                reporthook=make_download_progress_hook(time.time(), "  Download FFmpeg")
            )
            print()
            
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

    etapa_atual += 1
    print_progress_bar(etapa_atual, total_etapas, inicio_instalacao)

    # [6/7] Instalar LibreOffice (motor de conversão do app Office)
    print_colored("\n[6/7] Instalando LibreOffice...", "yellow")

    if shutil.which("soffice") or shutil.which("libreoffice"):
        print_colored("LibreOffice já está instalado!", "green")
    elif system == "Windows":
        print_colored("[AVISO] Baixe e instale o LibreOffice manualmente em:", "yellow")
        print_colored("        https://www.libreoffice.org/download/download/", "white")
        print_colored("        (necessário para o app Office converter/reparar arquivos)", "yellow")
    else:
        print_colored("Instalando LibreOffice...", "white")
        if shutil.which("apt"):
            success, _, _ = run_command("sudo apt update && sudo apt install -y libreoffice")
        elif shutil.which("yum"):
            success, _, _ = run_command("sudo yum install -y libreoffice")
        elif shutil.which("dnf"):
            success, _, _ = run_command("sudo dnf install -y libreoffice")
        elif shutil.which("pacman"):
            success, _, _ = run_command("sudo pacman -S --noconfirm libreoffice-fresh")
        else:
            print_colored("[AVISO] Instale o LibreOffice manualmente", "yellow")
            success = False

        if success and (shutil.which("soffice") or shutil.which("libreoffice")):
            print_colored("LibreOffice instalado com sucesso!", "green")
        else:
            print_colored("[AVISO] LibreOffice não foi instalado (app Office ficará indisponível)", "yellow")

    etapa_atual += 1
    print_progress_bar(etapa_atual, total_etapas, inicio_instalacao)

    # [7/7] Instalar runtime JavaScript (Deno) - o YouTube passou a exigir a
    # resolução de um desafio em JavaScript para liberar os formatos de
    # vídeo/áudio, então o downloader do Verto não funciona sem um runtime
    # JS disponível (deno, node, bun ou quickjs).
    print_colored("\n[7/7] Instalando runtime JavaScript (necessário para o YouTube)...", "yellow")

    if shutil.which("deno") or shutil.which("node") or shutil.which("bun") or shutil.which("quickjs"):
        print_colored("Runtime JavaScript já está instalado!", "green")
    else:
        deno_bin = "deno.exe" if system == "Windows" else "deno"
        try:
            if system == "Windows":
                asset = "deno-x86_64-pc-windows-msvc.zip"
            elif system == "Darwin":
                asset = "deno-aarch64-apple-darwin.zip" if platform.machine() == "arm64" else "deno-x86_64-apple-darwin.zip"
            else:
                asset = "deno-aarch64-unknown-linux-gnu.zip" if platform.machine() in ("aarch64", "arm64") else "deno-x86_64-unknown-linux-gnu.zip"

            print_colored(f"Baixando Deno ({asset})...", "white")
            url = f"https://github.com/denoland/deno/releases/latest/download/{asset}"
            urllib.request.urlretrieve(
                url, "deno.zip",
                reporthook=make_download_progress_hook(time.time(), "  Download Deno")
            )
            print()

            with zipfile.ZipFile("deno.zip", 'r') as zip_ref:
                zip_ref.extractall(".")
            os.remove("deno.zip")

            if system != "Windows" and os.path.exists(deno_bin):
                os.chmod(deno_bin, 0o755)

            if os.path.exists(deno_bin):
                print_colored("Deno instalado com sucesso!", "green")
            else:
                print_colored("[AVISO] Deno não foi instalado", "yellow")
        except Exception as e:
            print_colored(f"[AVISO] Erro ao instalar Deno: {e}", "yellow")
            print_colored("        O downloader de YouTube pode falhar sem um runtime JS.", "yellow")
            print_colored("        Instale manualmente em: https://deno.com/", "white")

    etapa_atual += 1
    print_progress_bar(etapa_atual, total_etapas, inicio_instalacao)
    print_colored(f"Tempo total de instalação: {format_eta(time.time() - inicio_instalacao)}", "white")

    # Limpar arquivos residuais (ex.: "=2.3.3") que podem sobrar de instalações antigas
    for item in os.listdir("."):
        if os.path.isfile(item) and re.fullmatch(r"=[\d.]+", item):
            os.remove(item)

    print_colored("\n========================================", "green")
    print_colored("    INSTALAÇÃO CONCLUÍDA COM SUCESSO!", "green")
    print_colored("========================================", "green")
    print_colored("\nTodas as dependências foram instaladas!", "white")
    print_colored("Verto está pronto para uso.", "white")

    # Efeito Matcha por IA (opcional) - Stable Diffusion + ControlNet não
    # entram na instalação padrão (são vários GB extras e, sem GPU NVIDIA,
    # cada imagem pode levar minutos para gerar), então perguntamos aqui em
    # vez de instalar automaticamente para todo mundo.
    print_colored("\n----------------------------------------", "blue")
    print_colored("Efeito Matcha por IA (opcional)", "blue")
    print_colored("----------------------------------------", "blue")
    print_colored("O app Matcha Effect tem um modo de IA generativa real (Stable", "white")
    print_colored("Diffusion + ControlNet), além do filtro rápido de cor. Esse modo", "white")
    print_colored("exige vários GB extras de download (PyTorch + modelos) e, sem", "white")
    print_colored("GPU NVIDIA, cada imagem pode levar alguns minutos para gerar.", "white")

    resposta = input("\nInstalar as dependências do Efeito Matcha por IA agora? [s/N]: ").strip().lower()
    ai_req_path = os.path.join("MatchaEffect", "requirements_ai.txt")
    if resposta in ("s", "sim", "y", "yes"):
        if os.path.exists(ai_req_path):
            print_colored("\nInstalando dependências de IA do Matcha Effect (pode demorar bastante)...", "yellow")
            success, _, _ = run_command(f'{pip_cmd} install -r "{ai_req_path}"')
            if success:
                print_colored("Dependências de IA do Matcha Effect instaladas com sucesso!", "green")
            else:
                print_colored("[AVISO] Falha ao instalar as dependências de IA do Matcha Effect.", "yellow")
                print_colored(f"        Rode manualmente depois: {pip_cmd} install -r {ai_req_path}", "white")
        else:
            print_colored(f"[AVISO] Arquivo {ai_req_path} não encontrado.", "yellow")
    else:
        print_colored("\nOk, pulando por enquanto. Para instalar depois, rode:", "white")
        print_colored(f"  {pip_cmd} install -r {ai_req_path}", "white")

    if system == "Windows":
        print_colored("\nPróximo passo: Execute python executaveis\\INICIAR.py", "white")
    else:
        print_colored("\nPróximo passo: Execute python3 executaveis/INICIAR.py", "white")

    input("\nPressione Enter para sair...")

if __name__ == "__main__":
    main()