"""Mídia do Social Preview: enquadra vídeos com o ffmpeg e ajusta imagens ao limite de cada rede.

O enquadramento usa a mesma conta da página (static/localtools/social/estudio.js,
funções `recorte` e `geometria`): em "preencher" o ponto (x, y) é o centro do
recorte em fração da mídia original e `zoom` aproxima; em "encaixar" e "livre"
(preenchimento automático) a mídia fica inteira, no tamanho e posição pedidos,
e o resto do quadro é preenchido (desfoque, cor da foto, espelho, bordas
esticadas, preto, branco ou uma cor). Assim o vídeo enviado é exatamente o que
a prévia mostrou.
"""

import io
import json
import os
import re
import shutil
import subprocess

from PIL import Image, ImageOps

FFMPEG = shutil.which('ffmpeg') or 'ffmpeg'
FFPROBE = shutil.which('ffprobe') or 'ffprobe'


class MidiaError(Exception):
    pass


def sondar(caminho):
    """Largura, altura, duração, fps e se tem áudio (já com a rotação aplicada)."""
    try:
        out = subprocess.run(
            [FFPROBE, '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', caminho],
            capture_output=True, text=True, timeout=60).stdout
        d = json.loads(out or '{}')
    except Exception as e:
        raise MidiaError(f'Não deu para ler o vídeo: {e}')
    video = next((s for s in d.get('streams', []) if s.get('codec_type') == 'video'), None)
    if not video:
        raise MidiaError('O arquivo não tem faixa de vídeo.')
    w, h = int(video.get('width') or 0), int(video.get('height') or 0)
    rot = 0
    for sd in video.get('side_data_list', []) or []:
        if 'rotation' in sd:
            rot = int(sd['rotation'])
    rot = int((video.get('tags') or {}).get('rotate', rot) or 0)
    if abs(rot) % 180 == 90:
        w, h = h, w
    fps = 30.0
    try:
        n, dd = (video.get('avg_frame_rate') or '30/1').split('/')
        fps = float(n) / float(dd) if float(dd) else 30.0
    except Exception:
        pass
    dur = float((d.get('format') or {}).get('duration') or video.get('duration') or 0)
    audio = any(s.get('codec_type') == 'audio' for s in d.get('streams', []))
    return {'w': w, 'h': h, 'dur': dur, 'fps': fps, 'audio': audio}


def recorte(w, h, W, H, enq):
    """Retângulo (x, y, largura, altura) da mídia original que vira a saída W×H."""
    zoom = max(1.0, float(enq.get('zoom') or 1))
    s = max(W / w, H / h) * zoom
    cw, ch = min(w, W / s), min(h, H / s)
    x = min(max(float(enq.get('x', 0.5)) * w - cw / 2, 0), w - cw)
    y = min(max(float(enq.get('y', 0.5)) * h - ch / 2, 0), h - ch)
    return x, y, cw, ch


def _par(n):
    return max(2, int(round(n / 2)) * 2)


def _pari(n):
    """Inteiro par (pode ser negativo): o 4:2:0 não aceita deslocamento ímpar."""
    return int(round(n / 2)) * 2


def geometria(w, h, W, H, enq):
    """Onde a mídia fica na saída. Mesma conta de estudio.js (`geometria`).

    preencher: recorte (x, y, cw, ch) da original que cobre o quadro.
    encaixar:  mídia inteira, centralizada; o resto é fundo.
    livre:     "preenchimento automático": tamanho (escala sobre o encaixe) e posição
               (px, py = centro da mídia em fração do quadro) livres; o resto é fundo.
    """
    modo = enq.get('modo') or 'preencher'
    if modo == 'preencher':
        return ('recorte',) + recorte(w, h, W, H, enq)
    s = min(W / w, H / h)
    if modo == 'livre':
        s *= min(4.0, max(0.15, float(enq.get('escala') or 1)))
        px, py = float(enq.get('px', 0.5)), float(enq.get('py', 0.5))
    else:
        px = py = 0.5
    fw, fh = w * s, h * s
    return ('livre', px * W - fw / 2, py * H - fh / 2, fw, fh)


CORES = {'preto': '#000000', 'branco': '#ffffff'}


def _cor(enq):
    f = enq.get('fundo') or 'desfoque'
    if f == 'cor':
        c = enq.get('cor') or '#000000'
    else:
        c = CORES.get(f, f)
    return c if re.fullmatch(r'#[0-9a-fA-F]{6}', c or '') else '#000000'


def _grafo_video(w, h, W, H, enq, fps):
    """filter_complex que leva [0:v] a [v] W×H no enquadramento pedido."""
    geo = geometria(w, h, W, H, enq)
    fim = f'setsar=1,fps={fps:.3f},format=yuv420p[v]'
    if geo[0] == 'recorte':
        _, x, y, cw, ch = geo
        return f'[0:v]crop={int(cw)}:{int(ch)}:{int(x)}:{int(y)},scale={W}:{H}:flags=lanczos,{fim}'
    _, left, top, fw, fh = geo
    fw, fh, left, top = _par(fw), _par(fh), _pari(left), _pari(top)
    fundo = enq.get('fundo') or 'desfoque'
    if fundo == 'espelho':
        # Ladrilhos espelhados em volta da mídia (cada vizinho virado), depois o recorte do quadro.
        import math
        nl, nr = math.ceil(max(0, left) / fw), math.ceil(max(0, W - left - fw) / fw)
        nt, nb = math.ceil(max(0, top) / fh), math.ceil(max(0, H - top - fh) / fh)
        cols, linhas = list(range(-nl, nr + 1)), list(range(-nt, nb + 1))
        n = len(cols) * len(linhas)
        partes = [f'[0:v]scale={fw}:{fh},setsar=1,split={n}' + ''.join(f'[t{k}]' for k in range(n))]
        k, nomes_linhas = 0, []
        for j in linhas:
            nomes = []
            for i in cols:
                flt = ','.join(x for x in ('hflip' if i % 2 else '', 'vflip' if j % 2 else '') if x) or 'null'
                partes.append(f'[t{k}]{flt}[c{k}]')
                nomes.append(f'[c{k}]')
                k += 1
            nome = f'[l{len(nomes_linhas)}]'
            partes.append(''.join(nomes) + (f'hstack=inputs={len(nomes)}' if len(nomes) > 1 else 'null') + nome)
            nomes_linhas.append(nome)
        partes.append(''.join(nomes_linhas) + (f'vstack=inputs={len(nomes_linhas)}' if len(nomes_linhas) > 1 else 'null')
                      + f',crop={W}:{H}:{nl * fw - left}:{nt * fh - top},{fim}')
        return ';'.join(partes)
    if fundo == 'bordas':
        # Só a parte visível da mídia, no lugar, e as bordas esticadas até a beira (fillborders=smear).
        vx0, vy0 = max(0, left), max(0, top)
        vx1, vy1 = min(W, left + fw), min(H, top + fh)
        if vx1 - vx0 >= 2 and vy1 - vy0 >= 2:
            return (f'[0:v]scale={fw}:{fh},crop={vx1 - vx0}:{vy1 - vy0}:{vx0 - left}:{vy0 - top},'
                    f'pad={W}:{H}:{vx0}:{vy0},fillborders=left={vx0}:right={W - vx1}:top={vy0}:bottom={H - vy1}:mode=smear,{fim}')
        fundo = 'desfoque'
    frente = f'[0:v]scale={fw}:{fh},setsar=1[fr]'
    if fundo == 'desfoque':
        atras = (f'[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},'
                 f'boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.06,setsar=1[bg]')
    else:
        atras = f'color=c={_cor(enq)}:s={W}x{H}:r={fps:.3f}[bg]'
    return f'{frente};{atras};[bg][fr]overlay={left}:{top}:shortest=1,{fim}'


def _codificar(fps):
    gop = int(round(fps * 2))
    return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-maxrate', '20M', '-bufsize', '20M',
            '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-g', str(gop), '-keyint_min', str(gop),
            '-sc_threshold', '0', '-movflags', '+faststart']


def _rodar(cmd, destino):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 30)
    if r.returncode != 0 or not os.path.exists(destino):
        raise MidiaError('O ffmpeg não conseguiu gerar o vídeo: ' + (r.stderr or '').strip()[-300:])
    return destino


def renderizar_video(origem, destino, W, H, enq=None, max_s=None, progresso=None):
    """Gera um MP4 H.264/AAC W×H no enquadramento pedido, dentro das regras do Instagram
    (23–60 fps, GOP fechado, 4:2:0, AAC 48 kHz, até 25 Mbps), que também servem para as outras redes."""
    enq = enq or {}
    info = sondar(origem)
    w, h = info['w'], info['h']
    if not w or not h:
        raise MidiaError('Vídeo sem dimensões.')
    W, H = _par(W), _par(H)
    fps = info['fps']
    fps_saida = fps if 23 <= fps <= 60 else (30 if fps < 23 else 60)
    cmd = [FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', origem]
    if max_s:
        cmd += ['-t', str(max_s)]
    cmd += ['-filter_complex', _grafo_video(w, h, W, H, enq, fps_saida), '-map', '[v]']
    if info['audio']:
        cmd += ['-map', '0:a:0', '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2']
    return _rodar(cmd + _codificar(fps_saida) + [destino], destino)


# ---------- Fotos com música (slideshow) ----------

TRANSICOES = {'corte': None, 'esmaecer': 'fade', 'deslizar': 'slideleft', 'zoom': 'zoomin', 'dissolver': 'dissolve'}
T_TRANSICAO = 0.6
FPS_SHOW = 30


def duracoes_show(n, dur_foto, transicao, max_s=None):
    """(duração de cada foto, total) com a sobreposição das transições; encolhe para caber no limite."""
    t = T_TRANSICAO if TRANSICOES.get(transicao) and n > 1 else 0.0
    d = max(1.0, float(dur_foto or 3))
    total = n * d - (n - 1) * t
    if max_s and total > max_s:
        d = max(t + 0.5, (max_s + (n - 1) * t) / n)
        total = n * d - (n - 1) * t
    return d, t, total


def slideshow(fotos, destino, W, H, opcoes=None, audio=None):
    """Vídeo W×H com as fotos (já recortadas pela página no tamanho certo), transições,
    movimento suave opcional (zoom lento, alternando aproximar/afastar) e música."""
    o = opcoes or {}
    if not fotos:
        raise MidiaError('Nenhuma foto para o vídeo.')
    W, H = _par(W), _par(H)
    n = len(fotos)
    d, t, total = duracoes_show(n, o.get('dur_foto'), o.get('transicao'), o.get('max_s'))
    quadros = int(round(d * FPS_SHOW))
    cmd = [FFMPEG, '-y', '-hide_banner', '-loglevel', 'error']
    for f in fotos:
        cmd += ['-loop', '1', '-framerate', str(FPS_SHOW), '-t', f'{d:.3f}', '-i', f]
    partes = []
    for i in range(n):
        if o.get('movimento'):
            # zoompan treme em imagem do tamanho final: aumenta 2× antes e reduz no fim.
            z = f"1+0.07*on/{quadros}" if i % 2 == 0 else f"1.07-0.07*on/{quadros}"
            partes.append(f"[{i}:v]scale={W * 2}:{H * 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                          f":d=1:s={W}x{H}:fps={FPS_SHOW},setsar=1,format=yuv420p[s{i}]")
        else:
            partes.append(f'[{i}:v]scale={W}:{H},setsar=1,fps={FPS_SHOW},format=yuv420p[s{i}]')
    efeito = TRANSICOES.get(o.get('transicao'))
    if n == 1:
        partes.append('[s0]null[v]')
    elif efeito:
        atual = '[s0]'
        for i in range(1, n):
            saida = '[v]' if i == n - 1 else f'[x{i}]'
            partes.append(f'{atual}[s{i}]xfade=transition={efeito}:duration={t}:offset={i * (d - t):.3f}{saida}')
            atual = saida
    else:
        partes.append(''.join(f'[s{i}]' for i in range(n)) + f'concat=n={n}:v=1:a=0[v]')
    mapa = ['-map', '[v]']
    if audio:
        ini = max(0.0, float(o.get('inicio') or 0))
        cmd += ['-stream_loop', '-1', '-ss', f'{ini:.3f}', '-i', audio]
        vol = min(2.0, max(0.0, float(o.get('volume', 1))))
        af = f'[{n}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={vol:.2f}'
        if o.get('fade', True):
            af += f',afade=t=in:st=0:d=0.4,afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5'
        partes.append(af + ',aresample=48000[a]')
        mapa += ['-map', '[a]', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2']
    cmd += ['-filter_complex', ';'.join(partes)] + mapa + ['-t', f'{total:.3f}'] + _codificar(FPS_SHOW) + [destino]
    return _rodar(cmd, destino)


def sondar_audio(caminho):
    try:
        out = subprocess.run([FFPROBE, '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', caminho],
                             capture_output=True, text=True, timeout=60).stdout
        d = json.loads(out or '{}')
    except Exception as e:
        raise MidiaError(f'Não deu para ler o áudio: {e}')
    if not any(s.get('codec_type') == 'audio' for s in d.get('streams', [])):
        raise MidiaError('O arquivo não tem áudio.')
    return {'dur': float((d.get('format') or {}).get('duration') or 0)}


# ---------- Foco automático (rosto ou o que mais chama atenção) ----------

MODELO_ROSTO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'Efeitos', 'modelos', 'face_detection_yunet_2023mar.onnx')


def analisar_foco(dados):
    """Caixa (0..1) do que precisa aparecer: os rostos (YuNet, o mesmo do app Efeitos) com
    folga para cabeça e ombros; sem rosto, a região de mais detalhe e cor (bordas + saturação)."""
    import numpy as np
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(dados))).convert('RGB')
    img.thumbnail((640, 640))
    w, h = img.size
    arr = np.asarray(img)
    rostos = []
    try:
        import cv2
        try:
            cv2.setLogLevel(2)
        except Exception:
            pass
        if os.path.exists(MODELO_ROSTO):
            det = cv2.FaceDetectorYN.create(MODELO_ROSTO, '', (w, h), 0.7, 0.3, 50)
            _, faces = det.detect(np.ascontiguousarray(arr[..., ::-1]))
            for f in (faces if faces is not None else []):
                x, y, fw, fh = [float(v) for v in f[:4]]
                if fw * fh > 0.0004 * w * h:
                    rostos.append({'x0': x / w, 'y0': y / h, 'x1': (x + fw) / w, 'y1': (y + fh) / h})
    except Exception:
        rostos = []
    if rostos:
        x0 = min(r['x0'] for r in rostos); x1 = max(r['x1'] for r in rostos)
        y0 = min(r['y0'] for r in rostos); y1 = max(r['y1'] for r in rostos)
        lw, lh = x1 - x0, y1 - y0
        foco = {'x0': max(0, x0 - lw * 0.35), 'x1': min(1, x1 + lw * 0.35),
                'y0': max(0, y0 - lh * 0.45), 'y1': min(1, y1 + lh * 0.9)}
    else:
        cinza = arr.mean(axis=2)
        gx = np.abs(np.diff(cinza, axis=1))[:-1, :]
        gy = np.abs(np.diff(cinza, axis=0))[:, :-1]
        mx, mn = arr.max(axis=2).astype(float), arr.min(axis=2).astype(float)
        sat = ((mx - mn) / (mx + 1))[:-1, :-1] * 60
        energia = gx + gy + sat
        yy, xx = np.mgrid[0:energia.shape[0], 0:energia.shape[1]]
        # leve preferência pelo centro, como o olho faz
        energia = energia * (1.15 - 0.3 * (np.abs(xx / energia.shape[1] - 0.5) + np.abs(yy / energia.shape[0] - 0.5)))
        corte = np.percentile(energia, 85)
        ys, xs = np.nonzero(energia >= corte)
        if len(xs) < 20:
            foco = {'x0': 0.3, 'y0': 0.3, 'x1': 0.7, 'y1': 0.7}
        else:
            pesos = energia[ys, xs]
            cx, cy = float((xs * pesos).sum() / pesos.sum()), float((ys * pesos).sum() / pesos.sum())
            sx, sy = float(np.sqrt(((xs - cx) ** 2 * pesos).sum() / pesos.sum())), float(np.sqrt(((ys - cy) ** 2 * pesos).sum() / pesos.sum()))
            ew, eh = energia.shape[1], energia.shape[0]
            foco = {'x0': max(0, (cx - 1.1 * sx) / ew), 'x1': min(1, (cx + 1.1 * sx) / ew),
                    'y0': max(0, (cy - 1.1 * sy) / eh), 'y1': min(1, (cy + 1.1 * sy) / eh)}
    media = arr.reshape(-1, 3).mean(axis=0)
    cor = '#%02x%02x%02x' % tuple(int(v * 0.8) for v in media)  # um tom mais escuro destaca a foto
    return {'foco': foco, 'rostos': rostos, 'cor': cor}


def capa_video(origem, destino, segundo=0.0):

    subprocess.run([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-ss', str(segundo), '-i', origem,
                    '-frames:v', '1', '-q:v', '3', destino], capture_output=True, timeout=120)
    return destino if os.path.exists(destino) else None


def ajustar_imagem(dados, max_bytes=None, max_lado=None, jpeg=True):
    """Re-encoda a imagem que a página gerou: JPEG sRGB e, se preciso, menor até caber no limite."""
    img = Image.open(io.BytesIO(dados))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ('RGB', 'L'):
        fundo = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGBA')
            fundo.paste(img, mask=img.split()[-1])
            img = fundo
        else:
            img = img.convert('RGB')
    if max_lado and max(img.size) > max_lado:
        img.thumbnail((max_lado, max_lado), Image.LANCZOS)
    if not jpeg and (not max_bytes or len(dados) <= max_bytes):
        return dados, 'image/jpeg' if dados[:3] == b'\xff\xd8\xff' else 'image/png'
    qualidade = 92
    while True:
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=qualidade, optimize=True, progressive=False, subsampling='4:2:0')
        out = buf.getvalue()
        if not max_bytes or len(out) <= max_bytes:
            return out, 'image/jpeg'
        if qualidade > 60:
            qualidade -= 8
        else:
            img = img.resize((int(img.width * 0.85), int(img.height * 0.85)), Image.LANCZOS)
            qualidade = 82
            if min(img.size) < 200:
                return out, 'image/jpeg'
