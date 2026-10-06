"""Render: uma única codificação do vídeo final.

Vídeo: um só filter_complex. Os trechos saem com select (um fluxo só, então a
memória não cresce com o número de cortes, como aconteceria com split+trim),
depois vêm enquadramento, zoom alternado e a legenda queimada. Saída em H.264
(CRF 19, yuv420p) com +faststart.

Áudio: cortado por amostra no Python, nas mesmas bordas (já alinhadas ao
quadro), com microfade de 10 ms em cada corte para não estalar. Depois passa
por passa-alta (ronco), compressão leve e loudnorm em duas passadas para -14
LUFS, a referência das redes sociais. Vai para AAC na mesma codificação.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

SR = 48000
FADE = 0.010
ZOOM = 1.08
FILTRO_VOZ = 'highpass=f=80,acompressor=threshold=0.125:ratio=3:attack=10:release=250:makeup=1.6'
ALVO_LUFS = -14


class RenderError(Exception):
    pass


# ----------------------------------------------------------------- áudio ---

def cortar_audio(fonte, trechos, saida_wav: Path, duracao_origem):
    """Lê o áudio do vídeo em fluxo (memória constante) e grava só os trechos."""
    import soundfile as sf
    faixas = [(int(round(a * SR)), int(round(b * SR))) for a, b in trechos]
    nf = int(FADE * SR)
    proc = subprocess.Popen(
        ['ffmpeg', '-v', 'error', '-i', str(fonte), '-vn', '-af', 'aresample=async=1:first_pts=0',
         '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'], stdout=subprocess.PIPE)
    bloco_bytes = SR * 2 * 4
    pos = 0
    with sf.SoundFile(str(saida_wav), 'w', SR, 2, 'FLOAT') as out:
        def escrever(dados, ini):
            fim = ini + len(dados)
            for s, e in faixas:
                a, b = max(s, ini), min(e, fim)
                if a >= b:
                    continue
                parte = dados[a - ini:b - ini]
                idx = np.arange(a, b)
                ganho = np.minimum(np.clip((idx - s) / nf, 0, 1), np.clip((e - idx) / nf, 0, 1))
                out.write(parte * ganho[:, None].astype(np.float32))
        try:
            while True:
                buf = proc.stdout.read(bloco_bytes)
                if not buf:
                    break
                dados = np.frombuffer(buf[:len(buf) // 8 * 8], np.float32).reshape(-1, 2)
                escrever(dados, pos)
                pos += len(dados)
        finally:
            proc.stdout.close()
            proc.wait()
        # Áudio mais curto que o vídeo (ou sem áudio): completa com silêncio.
        total = faixas[-1][1] if faixas else 0
        while pos < total:
            n = min(SR, total - pos)
            escrever(np.zeros((n, 2), np.float32), pos)
            pos += n


def medir_volume(wav: Path):
    """Primeira passada do loudnorm: mede o áudio já tratado."""
    proc = subprocess.run(
        ['ffmpeg', '-v', 'info', '-nostats', '-i', str(wav), '-af',
         f'{FILTRO_VOZ},loudnorm=I={ALVO_LUFS}:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'],
        capture_output=True, text=True)
    m = re.search(r'\{[^{}]*"input_i"[^{}]*\}', proc.stderr, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        if float(d['input_i']) < -70:   # silêncio total: nada a normalizar
            return None
        return d
    except (ValueError, KeyError):
        return None


def filtro_audio(medida, tratar):
    if not tratar:
        return 'anull'
    if not medida:
        return FILTRO_VOZ + f',loudnorm=I={ALVO_LUFS}:TP=-1.5:LRA=11'
    return (FILTRO_VOZ + f",loudnorm=I={ALVO_LUFS}:TP=-1.5:LRA=11:measured_I={medida['input_i']}"
            f":measured_TP={medida['input_tp']}:measured_LRA={medida['input_lra']}"
            f":measured_thresh={medida['input_thresh']}:offset={medida['target_offset']}:linear=true")


# ----------------------------------------------------------------- vídeo ---

def _por_trecho(valores, quadros, fmt='{:.0f}'):
    """Expressão do FFmpeg que vale valores[i] durante o trecho i do vídeo
    final. Usa o número do quadro (n, inteiro e exato) em vez do tempo: com
    30 fps, 2/30 s impresso como 0.0667 cairia um quadro depois.
    Soma de termos gte(n,a)*lt(n,b), sem aninhar ifs."""
    if len(set(valores)) == 1:
        return fmt.format(valores[0])
    termos = []
    for i, v in enumerate(valores):
        cond = f'gte(n,{quadros[i]})' + (f'*lt(n,{quadros[i + 1]})' if i + 1 < len(quadros) else '')
        termos.append(f'{fmt.format(v)}*{cond}')
    return '+'.join(termos)


def montar_filtro(info, trechos, W, H, modo, cw, ch, planos, zoom, legenda):
    fps = info['fps']
    faixas = [(int(round(a * fps)), int(round(b * fps))) for a, b in trechos]
    quadros, acc = [], 0          # quadro em que cada trecho começa no vídeo final
    for qa, qb in faixas:
        quadros.append(acc)
        acc += qb - qa
    # start_time=0: o quadro n é o instante n/fps, o mesmo relógio do áudio cortado.
    sel = '+'.join(f'between(n,{qa},{qb - 1})' for qa, qb in faixas)
    v = [f"[0:v]fps={fps}:start_time=0,select='{sel}',setpts=N/{fps}/TB"]
    if modo == 'desfocado':
        bw, bh = max(2, W // 4 - W // 4 % 2), max(2, H // 4 - H // 4 % 2)
        v.append(f'split=2[fg][bg];[bg]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},'
                 f'boxblur=12:2,scale={W}:{H},setsar=1[bgb];'
                 f'[fg]scale={W}:{H}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1[fgs];'
                 f'[bgb][fgs]overlay=(W-w)/2:(H-h)/2')
    else:
        xs = _por_trecho([p['x'] for p in planos], quadros)
        ys = _por_trecho([p['y'] for p in planos], quadros)
        v.append(f"crop={cw}:{ch}:x='{xs}':y='{ys}',scale={W}:{H}:flags=lanczos,setsar=1")
    if zoom and len(trechos) > 1:
        # Zoom leve alternado (100% / 108%) disfarça o pulo entre os trechos.
        zw, zh = int(W / ZOOM) - int(W / ZOOM) % 2, int(H / ZOOM) - int(H / ZOOM) % 2
        zx = _por_trecho([min(max(p['foco_x'] * W - zw / 2, 0), W - zw) for p in planos], quadros)
        zy = _por_trecho([min(max(p['foco_y'] * H - zh / 2, 0), H - zh) for p in planos], quadros)
        liga = '+'.join(f'between(n,{quadros[i]},{(quadros[i + 1] if i + 1 < len(quadros) else acc) - 1})'
                        for i in range(1, len(trechos), 2))
        v.append(f"split=2[vn][vz];[vz]crop={zw}:{zh}:x='{zx}':y='{zy}',scale={W}:{H}:flags=lanczos,setsar=1[vzz];"
                 f"[vn][vzz]overlay=0:0:enable='{liga}'")
    if legenda:
        v.append('ass=legenda.ass:fontsdir=fontes')
    v.append('format=yuv420p[v]')
    return ','.join(v)


def renderizar(fonte, saida: Path, pasta: Path, info, trechos, W, H, modo, cw, ch, planos, zoom,
               ass_texto, audio_medido, tratar_audio, tem_audio, progresso=None):
    """Roda o FFmpeg com tudo pronto. pasta: diretório de trabalho (legenda,
    fontes e áudio cortado ficam ali)."""
    from .cortes import duracao_final
    if ass_texto:
        (pasta / 'legenda.ass').write_text(ass_texto, encoding='utf-8')
        fontes = pasta / 'fontes'
        if not fontes.exists():
            shutil.copytree(Path(__file__).resolve().parent / 'fontes', fontes)
    filtro = montar_filtro(info, trechos, W, H, modo, cw, ch, planos, zoom, bool(ass_texto))
    cmd = ['ffmpeg', '-v', 'error', '-y', '-nostats', '-progress', 'pipe:1', '-i', str(fonte)]
    if tem_audio:
        cmd += ['-i', 'audio_cortado.wav']
        filtro += f';[1:a]{filtro_audio(audio_medido, tratar_audio)},aresample={SR}[a]'
    (pasta / 'filtro.txt').write_text(filtro, encoding='utf-8')
    cmd += ['-filter_complex_script', 'filtro.txt', '-map', '[v]']
    if tem_audio:
        cmd += ['-map', '[a]', '-c:a', 'aac', '-b:a', '192k', '-ar', str(SR)]
    cmd += ['-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
            '-r', str(info['fps']), '-movflags', '+faststart', str(saida)]
    total = duracao_final(trechos) or 1
    proc = subprocess.Popen(cmd, cwd=str(pasta), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for linha in proc.stdout:
        m = re.match(r'out_time_us=(\d+)', linha)
        if m and progresso:
            progresso(min(1.0, int(m.group(1)) / 1e6 / total))
    erro = proc.stderr.read()
    proc.wait()
    if proc.returncode != 0 or not saida.exists():
        saida.unlink(missing_ok=True)
        raise RenderError('O FFmpeg falhou: ' + (erro.strip().splitlines() or ['erro desconhecido'])[-1])
