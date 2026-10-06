"""Análise do vídeo: ffprobe, áudio para análise, voz isolada e silêncios.

O áudio de análise é 16 kHz mono (o que o Whisper usa). Ele não vai para o
vídeo final: serve para transcrever e achar as pausas. Com o Demucs, a voz é
separada antes, o que ajuda muito com música ou ruído de fundo.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

SR_ANALISE = 16000
FPS_COMUNS = (24, 25, 30, 50, 60)


class AnaliseError(Exception):
    pass


def _fracao(texto):
    try:
        a, b = (texto or '0/1').split('/')
        return float(a) / float(b) if float(b) else 0.0
    except ValueError:
        return 0.0


def sondar(caminho):
    """Duração, tamanho de exibição (já com a rotação do celular), fps e áudio."""
    try:
        saida = subprocess.run(
            ['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(caminho)],
            capture_output=True, text=True, timeout=60)
        dados = json.loads(saida.stdout or '{}')
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        raise AnaliseError(f'Não consegui ler o vídeo: {e}')
    video = next((s for s in dados.get('streams', []) if s.get('codec_type') == 'video'
                  and not (s.get('disposition') or {}).get('attached_pic')), None)
    audio = next((s for s in dados.get('streams', []) if s.get('codec_type') == 'audio'), None)
    if not video:
        raise AnaliseError('O arquivo não tem vídeo.')
    duracao = float((dados.get('format') or {}).get('duration') or video.get('duration') or 0)
    if duracao <= 0:
        raise AnaliseError('Não consegui descobrir a duração do vídeo.')

    rotacao = 0
    for sd in video.get('side_data_list') or []:
        if 'rotation' in sd:
            rotacao = int(round(float(sd['rotation'])))
    rotacao = rotacao or int((video.get('tags') or {}).get('rotate', 0) or 0)
    largura, altura = int(video['width']), int(video['height'])
    if abs(rotacao) % 180 == 90:
        largura, altura = altura, largura

    media, real = _fracao(video.get('avg_frame_rate')), _fracao(video.get('r_frame_rate'))
    base = media or real or 30
    # Celular grava com fps variável: a saída sai a um fps constante comum.
    fps = min(FPS_COMUNS, key=lambda f: abs(f - base)) if 20 <= base <= 65 else 30
    return {
        'duracao': duracao, 'largura': largura, 'altura': altura, 'rotacao': rotacao,
        'fps_origem': round(base, 3), 'fps': fps,
        'fps_variavel': bool(media and real and abs(media - real) / real > 0.01),
        'tem_audio': audio is not None,
        'codec': video.get('codec_name'),
    }


def extrair_audio(caminho, destino_wav: Path):
    """Áudio de análise (16 kHz mono) em WAV e como array float32."""
    proc = subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-i', str(caminho), '-vn', '-ac', '1', '-ar', str(SR_ANALISE),
         '-af', 'aresample=async=1:first_pts=0', '-c:a', 'pcm_s16le', str(destino_wav)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise AnaliseError('Não consegui extrair o áudio: ' + (proc.stderr.strip().splitlines() or ['?'])[-1])
    return ler_wav(destino_wav)


def ler_wav(caminho):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(caminho), '-ac', '1', '-ar', str(SR_ANALISE),
                          '-f', 's16le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def isolar_voz(wav: Path, pasta: Path):
    """Separa a voz com o Demucs (o mesmo modelo do Isolador de Voz). Devolve o
    WAV da voz a 16 kHz, ou levanta AnaliseError."""
    saida = pasta / 'demucs'
    env = dict(os.environ, TORCHAUDIO_BACKEND='soundfile')
    proc = subprocess.run([sys.executable, '-m', 'demucs', '--two-stems', 'vocals', '--mp3', '-o', str(saida), str(wav)],
                          capture_output=True, text=True, env=env)
    voz = next(saida.rglob('vocals.mp3'), None) if saida.exists() else None
    if proc.returncode != 0 or not voz:
        raise AnaliseError('O Demucs não conseguiu separar a voz: ' + (proc.stderr.strip().splitlines() or ['?'])[-1])
    destino = pasta / 'voz16k.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(voz), '-ac', '1', '-ar', str(SR_ANALISE), str(destino)],
                   check=True)
    shutil.rmtree(saida, ignore_errors=True)
    return destino


def limiar_de_silencio(audio):
    """Limiar em dB entre o ruído de fundo e a fala, medido no próprio áudio
    (um valor fixo erra feio entre um quarto silencioso e uma rua)."""
    janela = int(SR_ANALISE * 0.05)
    n = len(audio) // janela
    if n < 4:
        return -40.0
    rms = np.sqrt(np.mean(audio[:n * janela].reshape(n, janela) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    fundo, fala = np.percentile(db, 10), np.percentile(db, 90)
    return float(np.clip(fundo + 0.35 * (fala - fundo), -55, -22))


def silencios(wav: Path, audio, minimo=0.15):
    """Trechos de silêncio pelo filtro silencedetect do FFmpeg."""
    limiar = limiar_de_silencio(audio)
    proc = subprocess.run(['ffmpeg', '-v', 'info', '-nostats', '-i', str(wav), '-af',
                           f'silencedetect=noise={limiar:.1f}dB:d={minimo}', '-f', 'null', '-'],
                          capture_output=True, text=True)
    out, ini = [], None
    for linha in proc.stderr.splitlines():
        m = re.search(r'silence_start: (-?[\d.]+)', linha)
        if m:
            ini = max(0.0, float(m.group(1)))
        m = re.search(r'silence_end: ([\d.]+)', linha)
        if m and ini is not None:
            out.append((ini, float(m.group(1))))
            ini = None
    if ini is not None:
        out.append((ini, len(audio) / SR_ANALISE))
    return out, limiar
