"""Áudio Studio · mídia: importar, preparar (em blocos), picos, janelas e espectro.

Uma "fonte" é um arquivo importado. Ao preparar, a fila gera, bloco a bloco:
- a16.raw: o áudio em 16 kHz mono (int16), usado nas análises e na transcrição;
- picos.i8: mínimo e máximo a cada 64 amostras desse áudio (250 por segundo),
  o que o navegador desenha em qualquer zoom sem decodificar nada.
Uma hora de áudio vira 115 MB de a16.raw e 1,8 MB de picos; o preparo de 2 h
levou 11 s nesta máquina.

O navegador toca por "janelas": 20 s do arquivo original, decodificados na hora
pelo FFmpeg em WAV 48 kHz. Assim nada é decodificado inteiro (1 h em float32
seriam ~1,3 GB no navegador) e o som tocado é o do arquivo, não de uma cópia.
"""
import json
import os
import re
import shutil
import subprocess
import time

import numpy as np

SR_ANALISE = 16000
PICOS_BLOCO = 64              # amostras de 16 kHz por pico: 250 picos/s
JANELA_S = 20
SR_SAIDA = 48000


class MidiaError(Exception):
    pass


def ffprobe(caminho):
    try:
        p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                            'format=duration,format_name:stream=codec_type,codec_name,sample_rate,channels:format_tags',
                            '-of', 'json', caminho], capture_output=True, text=True, timeout=60)
        d = json.loads(p.stdout or '{}')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise MidiaError('Não consegui ler esse arquivo.')
    audio = [s for s in d.get('streams', []) if s.get('codec_type') == 'audio']
    video = [s for s in d.get('streams', []) if s.get('codec_type') == 'video' and s.get('codec_name') not in ('mjpeg', 'png')]
    if not audio:
        raise MidiaError('Esse arquivo não tem áudio.')
    dur = float((d.get('format') or {}).get('duration') or 0)
    if dur <= 0:
        raise MidiaError('Não consegui saber a duração desse arquivo.')
    a = audio[0]
    return {'duracao': dur, 'sr': int(a.get('sample_rate') or 48000), 'canais': int(a.get('channels') or 2),
            'codec': a.get('codec_name'), 'video': bool(video),
            'tags': {k.lower(): v for k, v in ((d.get('format') or {}).get('tags') or {}).items()}}


def guardar_fonte(origem, pasta, nome):
    """Copia (ou só extrai o áudio de um vídeo) para a pasta da fonte. -> info"""
    os.makedirs(pasta, exist_ok=True)
    info = ffprobe(origem)
    ext = os.path.splitext(nome)[1].lower() or '.bin'
    if info['video']:
        # vídeo: guarda só a trilha de áudio, sem recodificar (.mka aceita qualquer codec)
        destino = os.path.join(pasta, 'original.mka')
        p = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', origem, '-vn', '-map', '0:a:0',
                            '-c:a', 'copy', destino], capture_output=True, text=True, timeout=1800)
        if p.returncode != 0:
            raise MidiaError('Não consegui separar o áudio desse vídeo.')
    else:
        destino = os.path.join(pasta, 'original' + ext)
        shutil.copyfile(origem, destino)
    info.update({'nome': nome, 'arquivo': os.path.basename(destino), 'bytes': os.path.getsize(destino),
                 'estado': 'preparando', 'pronto_ate': 0.0, 'importada': time.strftime('%Y-%m-%d %H:%M')})
    with open(os.path.join(pasta, 'fonte.json'), 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False)
    return info


def ler_fonte(pasta):
    with open(os.path.join(pasta, 'fonte.json'), encoding='utf-8') as f:
        return json.load(f)


def salvar_fonte(pasta, info):
    with open(os.path.join(pasta, 'fonte.json') + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False)
    os.replace(os.path.join(pasta, 'fonte.json') + '.tmp', os.path.join(pasta, 'fonte.json'))


def arquivo_original(pasta):
    return os.path.join(pasta, ler_fonte(pasta)['arquivo'])


def decodificar(caminho, ini, dur, sr=SR_SAIDA, canais=2, formato='f32le'):
    """Trecho do arquivo como numpy (amostras, canais). Busca exata no FFmpeg."""
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', f'{max(0.0, ini):.6f}', '-t', f'{max(0.001, dur):.6f}',
           '-i', caminho, '-vn', '-ac', str(canais), '-ar', str(sr), '-f', formato, '-']
    p = subprocess.run(cmd, capture_output=True, timeout=600)
    if p.returncode != 0:
        raise MidiaError('O FFmpeg não conseguiu ler esse trecho.')
    dt = np.float32 if formato == 'f32le' else np.int16
    return np.frombuffer(p.stdout, dtype=dt).reshape(-1, canais)


def preparar(pasta, ctx):
    """Tarefa da fila: a16.raw + picos.i8, bloco a bloco (retoma de onde parou)."""
    from AudioStudio.as_fila import BLOCO_S
    info = ler_fonte(pasta)
    orig = arquivo_original(pasta)
    dur = info['duracao']
    n = max(1, int(np.ceil(dur / BLOCO_S)))
    ctx.blocos(n)
    a16 = os.path.join(pasta, 'a16.raw')
    picos = os.path.join(pasta, 'picos.i8')
    feitos = ctx.t['feitos']
    if feitos == 0:
        for c in (a16, picos):
            if os.path.exists(c):
                os.remove(c)
    else:
        # recomeça exatamente no limite do último bloco salvo
        alvo = feitos * BLOCO_S * SR_ANALISE * 2
        with open(a16, 'r+b') as f:
            f.truncate(min(alvo, os.path.getsize(a16)))
        with open(picos, 'r+b') as f:
            f.truncate(min(feitos * BLOCO_S * SR_ANALISE // PICOS_BLOCO * 2, os.path.getsize(picos)))
    for b in range(feitos, n):
        t0 = time.time()
        ini = b * BLOCO_S
        ctx.etapa(f'Preparando o áudio: bloco {b + 1} de {n}', b / n)
        pcm = decodificar(orig, ini, min(BLOCO_S, dur - ini), SR_ANALISE, 1, 's16le')[:, 0]
        if b < n - 1:   # todo bloco tem o tamanho exato (o último é o que sobrar)
            alvo = BLOCO_S * SR_ANALISE
            pcm = np.pad(pcm, (0, max(0, alvo - len(pcm))))[:alvo]
        with open(a16, 'ab') as f:
            f.write(pcm.astype(np.int16).tobytes())
        k = len(pcm) // PICOS_BLOCO
        if k:
            blk = pcm[:k * PICOS_BLOCO].reshape(k, PICOS_BLOCO)
            pk = np.empty((k, 2), np.int8)
            pk[:, 0] = (blk.min(1) >> 8).astype(np.int8)
            pk[:, 1] = (blk.max(1) >> 8).astype(np.int8)
            with open(picos, 'ab') as f:
                f.write(pk.tobytes())
        info['pronto_ate'] = min(dur, (b + 1) * BLOCO_S)
        salvar_fonte(pasta, info)
        ctx.bloco_feito(seg=time.time() - t0)
    info['estado'] = 'pronta'
    info['pronto_ate'] = dur
    salvar_fonte(pasta, info)
    return {'duracao': dur}


def a16(pasta):
    """Áudio de análise como memmap int16 (sem carregar na memória)."""
    caminho = os.path.join(pasta, 'a16.raw')
    if not os.path.exists(caminho) or os.path.getsize(caminho) == 0:
        return np.zeros(0, np.int16)
    return np.memmap(caminho, dtype=np.int16, mode='r')


def picos_bytes(pasta, nivel=0):
    """Nível 0: 250 picos/s. Nível 1: 1/16 disso (para ver horas de uma vez)."""
    caminho = os.path.join(pasta, 'picos.i8')
    if not os.path.exists(caminho):
        return b''
    dados = np.fromfile(caminho, dtype=np.int8).reshape(-1, 2)
    if nivel >= 1 and len(dados):
        f = 16
        k = len(dados) // f
        if k:
            r = dados[:k * f].reshape(k, f, 2)
            dados = np.stack([r[:, :, 0].min(1), r[:, :, 1].max(1)], 1)
    return dados.astype(np.int8).tobytes()


def janela_wav(pasta, ini, dur=JANELA_S):
    """WAV 48 kHz estéreo 16 bits de um trecho do arquivo original (para tocar)."""
    import io
    import wave
    pcm = decodificar(arquivo_original(pasta), ini, dur, SR_SAIDA, 2, 's16le')
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR_SAIDA)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def espectro_png(pasta, ini, dur, largura=1200, altura=200):
    """Espectrograma de um trecho (showspectrumpic do FFmpeg)."""
    dur = max(0.2, min(dur, 1800))
    largura = int(max(200, min(4000, largura)))
    altura = int(max(64, min(800, altura)))
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', f'{max(0, ini):.3f}', '-t', f'{dur:.3f}',
           '-i', arquivo_original(pasta), '-vn', '-ac', '1', '-lavfi',
           f'showspectrumpic=s={largura}x{altura}:legend=0:mode=combined:color=magma:scale=log:fscale=log:drange=90',
           '-frames:v', '1', '-f', 'image2', '-c:v', 'png', '-']
    p = subprocess.run(cmd, capture_output=True, timeout=300)
    if p.returncode != 0 or not p.stdout:
        raise MidiaError('Não consegui desenhar o espectrograma deste trecho.')
    return p.stdout


def nome_seguro(nome, padrao='audio'):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', str(nome or '')).strip()[:120] or padrao


# --------------------------------------------------------------- vídeo ---
# O vídeo do projeto (para exportar MP4 com o áudio novo) fica em
# <projeto>/video.mkv: a imagem e a trilha de áudio original sem recodificar
# (.mkv aceita qualquer codec); a trilha original serve de referência para
# sincronizar o áudio editado.

def guardar_video(origem, pasta_proj, nome):
    """Guarda o vídeo do projeto. -> info"""
    info = ffprobe(origem)
    if not info['video']:
        raise MidiaError('Esse arquivo não tem vídeo.')
    destino = os.path.join(pasta_proj, 'video.mkv')
    tmp = destino + '.tmp.mkv'
    p = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', origem, '-map', '0:v:0', '-map', '0:a:0?',
                        '-c', 'copy', '-sn', '-dn', tmp], capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise MidiaError('Não consegui guardar esse vídeo.')
    os.replace(tmp, destino)
    v = {'nome': nome, 'duracao': info['duracao'], 'bytes': os.path.getsize(destino),
         'guardado': time.strftime('%Y-%m-%d %H:%M')}
    with open(os.path.join(pasta_proj, 'video.json'), 'w', encoding='utf-8') as f:
        json.dump(v, f, ensure_ascii=False)
    return v


def ler_video(pasta_proj):
    try:
        with open(os.path.join(pasta_proj, 'video.json'), encoding='utf-8') as f:
            v = json.load(f)
    except (OSError, ValueError):
        return None
    return v if os.path.exists(os.path.join(pasta_proj, 'video.mkv')) else None


def apagar_video(pasta_proj):
    for n in ('video.mkv', 'video.json'):
        c = os.path.join(pasta_proj, n)
        if os.path.exists(c):
            os.remove(c)
