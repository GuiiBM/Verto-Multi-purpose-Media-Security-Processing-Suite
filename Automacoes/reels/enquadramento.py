"""Formato de saída e enquadramento (seguir o rosto, centro ou fundo desfocado).

Seguir o rosto quadro a quadro treme. Em vez disso, o detector YuNet (o
mesmo do app Efeitos) olha alguns quadros por segundo e cada trecho do vídeo
ganha UMA posição de corte, a mediana das posições do rosto nele: a imagem
fica parada dentro do trecho e só muda no corte, onde o pulo já existe.
"""
import subprocess
from pathlib import Path

import numpy as np

MODELO_ROSTO = Path(__file__).resolve().parent.parent.parent / 'Efeitos' / 'modelos' / 'face_detection_yunet_2023mar.onnx'

FORMATOS = {
    '9x16': (1080, 1920, 'Reels 9x16'),
    '4x5': (1080, 1350, 'Feed 4x5'),
    '1x1': (1080, 1080, 'Quadrado 1x1'),
    '16x9': (1920, 1080, 'YouTube 16x9'),
}
MODOS = {'rosto': 'Seguir o rosto', 'centro': 'Centro', 'desfocado': 'Fundo desfocado'}
ALTURA_DO_ROSTO = 0.38   # o rosto fica a 38% do topo: espaço para a legenda embaixo
AMOSTRAS_POR_SEGUNDO = 3


def tamanho_saida(formato, largura=None, altura=None):
    if formato in FORMATOS:
        return FORMATOS[formato]
    try:
        w, h = int(largura), int(altura)
    except (TypeError, ValueError):
        raise ValueError('Informe largura e altura do formato personalizado.')
    if not (240 <= w <= 4096 and 240 <= h <= 4096):
        raise ValueError('O formato personalizado precisa ter entre 240 e 4096 px de cada lado.')
    w, h = w - w % 2, h - h % 2
    return w, h, f'{w}x{h}'


def janela(info, W, H):
    """Maior retângulo com a proporção de saída que cabe no vídeo original."""
    sw, sh = info['largura'], info['altura']
    if sw / sh > W / H:
        ch = sh
        cw = ch * W / H
    else:
        cw = sw
        ch = cw * H / W
    cw, ch = int(cw) - int(cw) % 2, int(ch) - int(ch) % 2
    return cw, ch


def detectar_rostos(caminho, info, progresso=None):
    """[(t, cx, cy, lado)] em coordenadas 0..1 do quadro (já girado como o
    FFmpeg mostra, igual ao render)."""
    import cv2
    if not MODELO_ROSTO.exists():
        return []
    larg = 480
    alt = int(round(info['altura'] * larg / info['largura'] / 2) * 2)
    proc = subprocess.Popen(
        ['ffmpeg', '-v', 'error', '-i', str(caminho), '-an', '-vf',
         f'fps={AMOSTRAS_POR_SEGUNDO},scale={larg}:{alt}', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
        stdout=subprocess.PIPE)
    det = cv2.FaceDetectorYN.create(str(MODELO_ROSTO), '', (larg, alt), 0.6, 0.3, 50)
    tam = larg * alt * 3
    out, n = [], 0
    total = max(1, int(info['duracao'] * AMOSTRAS_POR_SEGUNDO))
    try:
        while True:
            buf = proc.stdout.read(tam)
            if len(buf) < tam:
                break
            quadro = np.frombuffer(buf, np.uint8).reshape(alt, larg, 3)
            _, faces = det.detect(quadro)
            if faces is not None and len(faces):
                # O maior rosto (pela área e confiança) é quem está falando.
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3] * f[14])[:4]
                out.append((n / AMOSTRAS_POR_SEGUNDO, (x + w / 2) / larg, (y + h / 2) / alt, max(w / larg, h / alt)))
            n += 1
            if progresso and n % 15 == 0:
                progresso(min(1.0, n / total))
    finally:
        proc.stdout.close()
        proc.wait()
    return out


def planos(trechos, rostos, info, W, H, modo):
    """Uma posição de corte por trecho: [{x, y}] em pixels do original, mais o
    centro do rosto já em coordenadas da saída (para o zoom mirar nele)."""
    cw, ch = janela(info, W, H)
    sw, sh = info['largura'], info['altura']
    geral = None
    if modo == 'rosto' and rostos:
        geral = (float(np.median([r[1] for r in rostos])), float(np.median([r[2] for r in rostos])))
    out = []
    for a, b in trechos:
        cx, cy = 0.5, 0.5
        if modo == 'rosto' and rostos:
            dentro = [r for r in rostos if a - 0.2 <= r[0] <= b + 0.2]
            if dentro:
                cx, cy = float(np.median([r[1] for r in dentro])), float(np.median([r[2] for r in dentro]))
            else:
                cx, cy = geral
        px, py = cx * sw, cy * sh
        x = int(np.clip(px - cw / 2, 0, sw - cw))
        y = int(np.clip(py - (ALTURA_DO_ROSTO * ch if modo == 'rosto' and rostos else ch / 2), 0, sh - ch))
        x, y = x - x % 2, y - y % 2
        out.append({'x': x, 'y': y,
                    'foco_x': float(np.clip((px - x) / cw, 0, 1)) if modo == 'rosto' else 0.5,
                    'foco_y': float(np.clip((py - y) / ch, 0, 1)) if modo == 'rosto' else 0.5})
    return cw, ch, out
