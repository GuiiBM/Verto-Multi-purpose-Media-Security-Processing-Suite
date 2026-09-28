"""Efeitos extras do app Efeitos: engraçados, deformações, câmeras e mais estilos.

Todos trabalham em uint8 (H, W, 3 ou 4) e devolvem outro array do mesmo tamanho,
então funcionam igual em prévias, fotos, GIFs e vídeos. Três ferramentas cobrem
quase tudo e já respeitam o limite de memória das fotos enormes:

  - by_strips  filtros de pixel, em faixas com margem de vizinhança (desfoque,
               bordas, JPEG) e coordenadas globais (padrões sem emenda)
  - geo_remap  deformações: cada faixa do resultado busca seus pixels de origem
               na imagem inteira (redemoinho, gelatina, derretendo...)
  - paint      desenhos por cima da foto (óculos, olhos, textos), com
               antisserrilhado por supersampling

Os efeitos de rosto usam o YuNet (OpenCV FaceDetectorYN), um detector leve que
devolve a caixa do rosto e 5 pontos: olhos, nariz e cantos da boca. O modelo
(~230 KB, licença MIT) fica em Efeitos/modelos.
"""

import math
import os
import threading
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import efeitos_engine as E


# ---------------------------------------------------------------------------
# Infraestrutura
# ---------------------------------------------------------------------------

def _single(h, w):
    return h * w <= E.STRIP_PIXELS


def _rows(w):
    return max(16, E.STRIP_TARGET // max(1, w))


def _t(ctx):
    """Tempo do quadro em segundos (0 em fotos)."""
    return ctx.get('frame', 0) / max(1e-3, ctx.get('fps', 30.0)) if ctx.get('video') else 0.0


def by_strips(arr, fn, halo=0, align=1):
    """fn(rgb float 0..1 da faixa com margem, (linha inicial, H, W)) -> rgb do mesmo
    tamanho. O alfa é preservado. Fotos pequenas são uma faixa só."""
    h, w, c = arr.shape
    rows = h if _single(h, w) else max(align, _rows(w) // align * align)
    out = np.empty_like(arr)
    for y0 in range(0, h, rows):
        y1 = min(h, y0 + rows)
        a, b = max(0, y0 - halo), min(h, y1 + halo)
        res = fn(arr[a:b, :, :3].astype(np.float32) / 255.0, (a, h, w))
        out[y0:y1, :, :3] = E._to_u8(res[y0 - a:y1 - a])
    if c == 4:
        out[..., 3] = arr[..., 3]
    return out


def _ygrid(region, rows):
    return np.arange(region[0], region[0] + rows, dtype=np.float32)[:, None]


def _xgrid(w):
    return np.arange(w, dtype=np.float32)[None, :]


def geo_remap(arr, coords, ctx=None, key=None):
    """coords(xs (1, W), ys (linhas, 1), W, H) -> (map_x, map_y): de onde vem cada
    pixel do resultado. Amostragem bilinear; fora da imagem repete a borda.
    Com key, o plano fica em cache (deformações que não mudam entre quadros)."""
    h, w, c = arr.shape
    single = _single(h, w)
    rows = h if single else _rows(w)
    out = np.empty_like(arr)
    xs = _xgrid(w)
    for y0 in range(0, h, rows):
        y1 = min(h, y0 + rows)

        def build(y0=y0, y1=y1):
            mx, my = coords(xs, np.arange(y0, y1, dtype=np.float32)[:, None], w, h)
            mx, my = np.broadcast_arrays(np.asarray(mx, np.float32), np.asarray(my, np.float32))
            return E._remap_plan(h, w, mx, my)

        plan = E._cached(ctx, key + (h, w), build) if (key and single and ctx is not None) else build()
        out[y0:y1] = np.clip(E._remap(arr, plan) + 0.5, 0, 255).astype(np.uint8)
    return out


def geo_blend(arr, coords_list, weights):
    """Média ponderada de várias deformações (rastro/fantasma), em faixas."""
    h, w, c = arr.shape
    rows = h if _single(h, w) else _rows(w)
    out = np.empty_like(arr)
    xs = _xgrid(w)
    for y0 in range(0, h, rows):
        y1 = min(h, y0 + rows)
        ys = np.arange(y0, y1, dtype=np.float32)[:, None]
        acc = None
        for coords, wt in zip(coords_list, weights):
            mx, my = np.broadcast_arrays(*[np.asarray(v, np.float32) for v in coords(xs, ys, w, h)])
            part = E._remap(arr, E._remap_plan(h, w, mx, my)) * wt
            acc = part if acc is None else acc + part
        out[y0:y1] = np.clip(acc + 0.5, 0, 255).astype(np.uint8)
    return out


def composite(arr, layer, x, y):
    """Compõe uma camada RGBA (PIL) sobre arr na posição (x, y), com recorte."""
    layer = layer.convert('RGBA')
    h, w = arr.shape[:2]
    x, y = int(round(x)), int(round(y))
    sx0, sy0 = max(0, -x), max(0, -y)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + layer.width), min(h, y + layer.height)
    if x1 <= x0 or y1 <= y0:
        return
    # Em blocos de linhas: numa camada do tamanho da foto (rachaduras numa foto
    # de 45 MP) a conta em float de uma vez passaria de 2 GB
    step = max(1, 2_000_000 // max(1, x1 - x0))
    for r0 in range(y0, y1, step):
        r1 = min(y1, r0 + step)
        src = np.asarray(layer.crop((sx0, sy0 + r0 - y0, sx0 + x1 - x0, sy0 + r1 - y0)), dtype=np.float32) / 255.0
        a = src[..., 3:4]
        if not a.any():
            continue
        region = arr[r0:r1, x0:x1]
        region[..., :3] = np.clip(region[..., :3] * (1 - a) + src[..., :3] * 255 * a + 0.5, 0, 255).astype(np.uint8)
        if arr.shape[2] == 4:
            region[..., 3] = np.maximum(region[..., 3], (a[..., 0] * 255 + 0.5).astype(np.uint8))


def paint(arr, box, painter, ss=3):
    """Desenha numa camada do tamanho de box (x0, y0, x1, y1) e compõe sobre arr.
    painter(layer, draw, T, ss): T(x, y) converte coordenadas da imagem para a
    camada; ss é o fator de supersampling (antisserrilhado)."""
    h, w = arr.shape[:2]
    x0, y0 = max(0, int(math.floor(box[0]))), max(0, int(math.floor(box[1])))
    x1, y1 = min(w, int(math.ceil(box[2]))), min(h, int(math.ceil(box[3])))
    if x1 <= x0 or y1 <= y0:
        return
    bw, bh = x1 - x0, y1 - y0
    while ss > 1 and bw * bh * ss * ss > 24_000_000:
        ss -= 1
    layer = Image.new('RGBA', (bw * ss, bh * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    def T(x, y):
        return ((x - x0) * ss, (y - y0) * ss)

    painter(layer, draw, T, ss)
    if ss > 1:
        layer = layer.convert('RGBa').resize((bw, bh), Image.LANCZOS).convert('RGBA')
    composite(arr, layer, x0, y0)


def soft_spot(arr, cx, cy, radius, color, strength):
    """Mancha de cor com borda gaussiana (bochechas, brilho dos olhos)."""
    h, w = arr.shape[:2]
    r = radius * 2.2
    x0, x1 = max(0, int(cx - r)), min(w, int(cx + r) + 1)
    y0, y1 = max(0, int(cy - r)), min(h, int(cy + r) + 1)
    if x1 <= x0 or y1 <= y0:
        return
    xs = np.arange(x0, x1, dtype=np.float32)[None, :] - cx
    ys = np.arange(y0, y1, dtype=np.float32)[:, None] - cy
    wgt = (np.exp(-(xs * xs + ys * ys) / (2 * (radius * 0.6) ** 2)) * strength)[..., None]
    reg = arr[y0:y1, x0:x1, :3].astype(np.float32)
    arr[y0:y1, x0:x1, :3] = np.clip(reg * (1 - wgt) + np.asarray(color, np.float32) * wgt + 0.5, 0, 255).astype(np.uint8)


def gblur(x, sigma):
    """Desfoque gaussiano de um array float 0..1 (H, W) ou (H, W, 3) pelo Pillow."""
    if sigma < 0.3:
        return x
    img = Image.fromarray((np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(sigma)), dtype=np.float32) / 255.0


def grad_mag(lum):
    gy, gx = np.gradient(lum)
    return np.sqrt(gx * gx + gy * gy)


def yiq(rgb):
    y = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    i = rgb @ np.array([0.596, -0.274, -0.322], np.float32)
    q = rgb @ np.array([0.211, -0.523, 0.312], np.float32)
    return y, i, q


def from_yiq(y, i, q):
    return np.stack([y + 0.956 * i + 0.621 * q, y - 0.272 * i - 0.647 * q, y - 1.106 * i + 1.703 * q], axis=-1)


def hue_rgb(hh):
    """Cor pura do matiz hh (0..1)."""
    hh = (hh % 1.0) * 6.0
    return np.stack([np.clip(np.abs(hh - 3) - 1, 0, 1), np.clip(2 - np.abs(hh - 2), 0, 1),
                     np.clip(2 - np.abs(hh - 4), 0, 1)], axis=-1)


def hue_rotate_u8(arr_rgb, degrees, sat=1.0):
    rgb = arr_rgb.astype(np.float32) / 255.0
    y, i, q = yiq(rgb)
    a = math.radians(degrees)
    i2, q2 = (i * math.cos(a) - q * math.sin(a)) * sat, (i * math.sin(a) + q * math.cos(a)) * sat
    return E._to_u8(from_yiq(y, i2, q2))


def hblur(x, k):
    """Média móvel horizontal (largura k) de um array 2D, com borda repetida."""
    k = int(k)
    if k <= 1:
        return x
    pad = k // 2
    xp = np.pad(x, ((0, 0), (pad, k - 1 - pad)), mode='edge')
    c = np.cumsum(xp, axis=1, dtype=np.float32)
    c = np.concatenate([np.zeros((x.shape[0], 1), np.float32), c], axis=1)
    return (c[:, k:] - c[:, :-k]) / k


def shift_x(x, s):
    """Desloca um array 2D s pixels para a direita (borda repetida)."""
    if s == 0:
        return x
    out = np.empty_like(x)
    if s > 0:
        out[:, s:] = x[:, :-s]
        out[:, :s] = x[:, :1]
    else:
        out[:, :s] = x[:, -s:]
        out[:, s:] = x[:, -1:]
    return out


def dilate(mask, r):
    return E._dilate(mask, r) if r > 0 else mask


def jpeg_crunch(arr, quality, align=16):
    """Passa a imagem por JPEG de qualidade baixa (artefatos de blocos), em faixas
    alinhadas aos blocos do JPEG para não criar emendas."""
    import io
    h, w, c = arr.shape
    rows = h if _single(h, w) else max(align, _rows(w) // align * align)
    out = arr.copy()
    for y0 in range(0, h, rows):
        y1 = min(h, y0 + rows)
        buf = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(arr[y0:y1, :, :3])).save(buf, 'JPEG', quality=int(quality), subsampling=2)
        buf.seek(0)
        out[y0:y1, :, :3] = np.asarray(Image.open(buf).convert('RGB'))
    return out


_FONTS = {}


def font(size, mono=False):
    size = max(6, int(size))
    key = (size, mono)
    if key not in _FONTS:
        names = (['DejaVuSansMono-Bold.ttf', 'consolab.ttf', 'Courier New Bold.ttf', 'courbd.ttf', 'LiberationMono-Bold.ttf']
                 if mono else ['DejaVuSans-Bold.ttf', 'arialbd.ttf', 'Arial Bold.ttf', 'LiberationSans-Bold.ttf'])
        found = None
        for n in names:
            try:
                found = ImageFont.truetype(n, size)
                break
            except OSError:
                continue
        _FONTS[key] = found or ImageFont.load_default(size)
    return _FONTS[key]


def osd_text(arr, text, x, y, size, fill=(255, 255, 255), mono=True, anchor='la', shadow=True, stroke=0):
    """Texto de tela (PLAY, REC, data), com sombra para ler em qualquer fundo."""
    stroke = int(round(stroke))
    f = font(size, mono)
    l, t, r, b = f.getbbox(text, anchor=anchor, stroke_width=stroke)
    pad = max(2, int(size * 0.15))
    box = (x + l - pad, y + t - pad, x + r + pad * 2, y + b + pad * 2)

    def painter(layer, draw, T, ss):
        fs = font(size * ss, mono)
        if shadow:
            off = max(1, size * 0.06) * ss
            px, py = T(x, y)
            draw.text((px + off, py + off), text, font=fs, fill=(0, 0, 0, 170), anchor=anchor)
        draw.text(T(x, y), text, font=fs, fill=tuple(fill) + (255,), anchor=anchor,
                  stroke_width=int(stroke * ss), stroke_fill=(0, 0, 0, 255))

    paint(arr, box, painter, ss=2)


_EMOJI = {}


def emoji_image(ch, size):
    """Emoji colorido como imagem RGBA (Noto Color Emoji no Linux, Segoe no
    Windows, Apple Color Emoji no macOS). None se não houver fonte de emoji."""
    if ch not in _EMOJI:
        img = None
        for name, px in (('NotoColorEmoji.ttf', 109), ('seguiemj.ttf', 96), ('Apple Color Emoji.ttc', 96)):
            try:
                f = ImageFont.truetype(name, px)
            except OSError:
                continue
            try:
                canvas = Image.new('RGBA', (px * 2, px * 2), (0, 0, 0, 0))
                ImageDraw.Draw(canvas).text((px // 2, px // 2), ch, font=f, embedded_color=True)
                bbox = canvas.getbbox()
                if bbox:
                    img = canvas.crop(bbox)
                    break
            except Exception:
                continue
        _EMOJI[ch] = img
    base = _EMOJI[ch]
    if base is None:
        return None
    k = size / max(base.size)
    return base.resize((max(1, round(base.width * k)), max(1, round(base.height * k))), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Rostos (YuNet)
# ---------------------------------------------------------------------------

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modelos', 'face_detection_yunet_2023mar.onnx')
_TLS = threading.local()


def _detector():
    det = getattr(_TLS, 'det', None)
    if det is None:
        import cv2
        try:
            cv2.setLogLevel(2)  # só erros (o OpenCV 5 avisa sobre o backend no stderr)
        except Exception:
            pass
        det = cv2.FaceDetectorYN.create(MODEL_PATH, '', (320, 320), 0.72, 0.3, 50)
        _TLS.det = det
    return det


def _face_from_points(box, pts):
    eyes = sorted([tuple(pts[0]), tuple(pts[1])])
    (ex1, ey1), (ex2, ey2) = eyes
    return {'box': tuple(box), 'eyes': eyes, 'nose': tuple(pts[2]), 'mouth': [tuple(pts[3]), tuple(pts[4])],
            'd': max(2.0, math.hypot(ex2 - ex1, ey2 - ey1)), 'angle': math.atan2(ey2 - ey1, ex2 - ex1)}


def detect_faces(arr):
    """Rostos na imagem (coordenadas em pixels). Detecta numa cópia de até 960 px."""
    h, w = arr.shape[:2]
    det = _detector()
    k = min(1.0, 960.0 / max(h, w))
    img = arr[..., :3]
    if k < 1:
        img = np.asarray(Image.fromarray(np.ascontiguousarray(img)).resize(
            (max(1, round(w * k)), max(1, round(h * k))), Image.BILINEAR))
    bgr = np.ascontiguousarray(img[..., ::-1])
    det.setInputSize((bgr.shape[1], bgr.shape[0]))
    _, res = det.detect(bgr)
    faces = []
    for r in (res if res is not None else []):
        faces.append(_face_from_points(r[:4] / k, (r[4:14].reshape(5, 2) / k)))
    return faces


def faces_normalized(arr):
    """Rostos em coordenadas 0..1 (para as miniaturas, pequenas demais para detectar)."""
    h, w = arr.shape[:2]
    try:
        faces = detect_faces(arr)
    except Exception:
        return []
    out = []
    for f in faces:
        x, y, fw, fh = f['box']
        pts = [f['eyes'][0], f['eyes'][1], f['nose'], f['mouth'][0], f['mouth'][1]]
        out.append(((x / w, y / h, fw / w, fh / h), [(px / w, py / h) for px, py in pts]))
    return out


def find_faces(arr, ctx, label):
    h, w = arr.shape[:2]
    hint = ctx.get('faces_hint')
    if hint is not None and max(h, w) <= 480:
        return [_face_from_points((b[0] * w, b[1] * h, b[2] * w, b[3] * h),
                                  np.array([(px * w, py * h) for px, py in pts])) for b, pts in hint]
    try:
        faces = detect_faces(arr)
    except Exception:
        ctx['notes'].add('Detecção de rostos indisponível: instale o OpenCV (pip install opencv-python-headless).')
        return []
    if not faces:
        ctx['notes'].add(f'{label}: nenhum rosto encontrado' + (' em alguns quadros.' if ctx.get('video') else '.'))
    return faces


# ---------------------------------------------------------------------------
# Engraçados
# ---------------------------------------------------------------------------

def _thug_glasses():
    """Os óculos pixelados do meme "Thug Life / Deal with it" (30 x 7)."""
    g = np.zeros((7, 30), np.uint8)
    g[0, :] = 1
    g[1, 0:2] = g[1, 28:30] = 1
    g[1, 13:17] = 1
    for lx in (2, 17):
        for y in range(1, 6):
            s = max(0, y - 3)
            g[y, lx + s:lx + 11 - s] = 1
        g[1, lx + 2] = g[1, lx + 3] = 2
        g[2, lx + 3] = g[2, lx + 4] = 2
    rgba = np.zeros((7, 30, 4), np.uint8)
    rgba[g == 1] = (8, 8, 8, 255)
    rgba[g == 2] = (255, 255, 255, 255)
    return Image.fromarray(rgba)


_GLASSES = _thug_glasses()


def fx_thuglife(arr, p, ctx):
    arr = arr.copy()
    h, w = arr.shape[:2]
    faces = find_faces(arr, ctx, 'Thug Life')
    t = _t(ctx)
    prog = 1.0
    if ctx.get('video') and p['animar']:
        prog = min(1.0, t / 1.4)
        prog = 1 - (1 - prog) ** 3  # desacelera ao chegar no rosto
    for f in faces:
        s = f['d'] / 15.0 * p['tamanho'] / 100.0
        img = _GLASSES.resize((max(1, round(30 * s)), max(1, round(7 * s))), Image.NEAREST)
        rot = img.rotate(-math.degrees(f['angle']), resample=Image.BICUBIC, expand=True)
        (ex1, ey1), (ex2, ey2) = f['eyes']
        mx, my = (ex1 + ex2) / 2, (ey1 + ey2) / 2
        # a linha dos olhos fica um pouco acima do meio da armação
        off = 0.7 * s
        cx, cy = mx - math.sin(f['angle']) * off, my + math.cos(f['angle']) * off
        cy -= (1 - prog) * (cy + rot.height)
        composite(arr, rot, cx - rot.width / 2, cy - rot.height / 2)
    if p['texto'] and faces and prog >= 1.0:
        size = min(w * 0.11, h * 0.13)
        osd_text(arr, 'THUG LIFE', w / 2, h * 0.93, size, mono=False, anchor='ms', shadow=False,
                 stroke=max(1, size * 0.07))
    return arr


def fx_olhosdesenho(arr, p, ctx):
    arr = arr.copy()
    faces = find_faces(arr, ctx, 'Olhos de Desenho')
    t = _t(ctx)
    rng = np.random.default_rng(int(p['variacao']) * 97)
    for fi, f in enumerate(faces):
        R = f['d'] * 0.36 * p['tamanho'] / 100.0
        eyes = f['eyes']
        xs = [e[0] for e in eyes]
        ys = [e[1] for e in eyes]
        box = (min(xs) - R * 1.3, min(ys) - R * 1.3, max(xs) + R * 1.3, max(ys) + R * 1.3)
        angles = []
        for i in range(2):
            if ctx.get('video'):
                ph = rng.uniform(0, 6.28)
                angles.append(math.pi / 2 + 1.25 * math.sin(6.9 * t + ph) + 0.45 * math.sin(17.0 * t + 2 * ph))
            else:
                angles.append(rng.uniform(0, 2 * math.pi))

        def painter(layer, draw, T, ss, eyes=eyes, R=R, angles=angles):
            lw = max(1, R * 0.11) * ss
            for (ex, ey), phi in zip(eyes, angles):
                cx, cy = T(ex, ey)
                r = R * ss
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255), outline=(10, 10, 10, 255),
                             width=int(lw))
                pr = r * 0.5
                dist = (r - pr - lw) * 0.95
                px, py = cx + dist * math.cos(phi), cy + dist * math.sin(phi)
                draw.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(12, 12, 12, 255))
                hr = pr * 0.22
                hx, hy = px - pr * 0.35, py - pr * 0.35
                draw.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=(255, 255, 255, 235))

        paint(arr, box, painter, ss=3)
    return arr


def fx_palhaco(arr, p, ctx):
    arr = arr.copy()
    faces = find_faces(arr, ctx, 'Nariz de Palhaço')
    for f in faces:
        d = f['d']
        nx, ny = f['nose']
        if p['bochechas']:
            for ex, _ in f['eyes']:
                soft_spot(arr, ex + (ex - nx) * 0.25, ny + d * 0.12, d * 0.34, (255, 80, 110), 0.42)
        r = d * 0.3 * p['tamanho'] / 100.0

        def painter(layer, draw, T, ss, nx=nx, ny=ny, r=r):
            cx, cy = T(nx, ny)
            rr = r * ss
            draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(150, 0, 18, 255))
            ri = rr * 0.9
            ox, oy = cx - rr * 0.05, cy - rr * 0.05
            draw.ellipse((ox - ri, oy - ri, ox + ri, oy + ri), fill=(226, 22, 38, 255))
            hx, hy = cx - rr * 0.38, cy - rr * 0.42
            draw.ellipse((hx - rr * 0.22, hy - rr * 0.14, hx + rr * 0.22, hy + rr * 0.14), fill=(255, 255, 255, 210))

        paint(arr, (nx - r - 2, ny - r - 2, nx + r + 2, ny + r + 2), painter, ss=4)
    return arr


def bulge(arr, cx, cy, R, mag, core=0.55):
    """Lupa local: dentro de core*R tudo fica 'mag' vezes maior (sem distorcer o
    rosto); daí até a borda do círculo a ampliação volta suavemente a 1."""
    h, w = arr.shape[:2]
    x0, x1 = max(0, int(cx - R)), min(w, int(math.ceil(cx + R)) + 1)
    y0, y1 = max(0, int(cy - R)), min(h, int(math.ceil(cy + R)) + 1)
    if x1 <= x0 or y1 <= y0 or R < 2:
        return
    # A origem de cada pixel fica sempre dentro do círculo: basta copiar essa
    # região e escrever o resultado em blocos de linhas (memória limitada).
    src = arr[y0:y1, x0:x1].copy()
    bh, bw = src.shape[:2]
    xs = np.arange(x0, x1, dtype=np.float32)[None, :] - cx
    step = max(1, 1_000_000 // bw)
    for r0 in range(y0, y1, step):
        r1 = min(y1, r0 + step)
        ys = np.arange(r0, r1, dtype=np.float32)[:, None] - cy
        r = np.sqrt(xs * xs + ys * ys) / R
        # k = quanto encolher a distância ao centro para achar o pixel de origem.
        # Crescendo de 1/mag até 1, com a origem sempre andando para fora (sem dobras).
        t = E._smoothstep(core, 1.0, r)
        k = (1.0 / mag + (1.0 - 1.0 / mag) * t).astype(np.float32)
        mx, my = np.broadcast_arrays(cx + xs * k - x0, cy + ys * k - y0)
        arr[r0:r1, x0:x1] = np.clip(E._remap(src, E._remap_plan(bh, bw, mx, my)) + 0.5, 0, 255).astype(np.uint8)


def fx_cabecao(arr, p, ctx):
    arr = arr.copy()
    h, w = arr.shape[:2]
    mag = 1.0 + 1.1 * p['forca'] / 100.0
    k = p['tamanho'] / 100.0
    faces = find_faces(arr, ctx, 'Cabeção') if p['alvo'] == 'rosto' else []
    if not faces:
        bulge(arr, w / 2, h / 2, min(w, h) * 0.42 * k, mag)
        return arr
    for f in faces:
        x, y, fw, fh = f['box']
        # centro um pouco acima do meio do rosto, para o cabelo crescer junto
        bulge(arr, x + fw / 2, y + fh * 0.35, max(fw, fh) * 1.45 * k, mag, core=0.5)
    return arr


def fx_olhudo(arr, p, ctx):
    arr = arr.copy()
    mag = 1.0 + 1.3 * p['forca'] / 100.0
    for f in find_faces(arr, ctx, 'Olhos Esbugalhados'):
        for ex, ey in f['eyes']:
            bulge(arr, ex, ey, f['d'] * 0.5 * p['tamanho'] / 100.0, mag, core=0.4)
    return arr


FRIED_EMOJIS = ['😂', '💯', '🔥', '👌', '😂', '😳']


def fx_fritado(arr, p, ctx):
    h, w = arr.shape[:2]
    f = p['intensidade'] / 100.0
    faces = find_faces(arr, ctx, 'Frito (olhos brilhando)') if p['olhos'] else []
    radius = max(1.0, min(h, w) * 0.0025)
    seed = ctx.get('seed', 0)

    def fry(rgb, region):
        lum = E._luma(rgb)[..., None]
        rgb = lum + (rgb - lum) * (1 + 2.2 * f)
        rgb = E._contrast(rgb, 60 * f)
        rgb = np.clip(rgb * np.array([1 + 0.25 * f, 1 + 0.03 * f, 1 - 0.4 * f], np.float32), 0, 1)
        blur = gblur(rgb, radius)
        rgb = rgb + (1.5 + 2.5 * f) * (rgb - blur)
        rng = np.random.default_rng((seed * 31 + ctx.get('frame', 0) * 7 + region[0]) & 0xFFFFFFFF)
        rgb = rgb + rng.standard_normal(rgb.shape[:2]).astype(np.float32)[..., None] * 0.06 * f
        return np.clip(rgb, 0, 1)

    out = by_strips(arr, fry, halo=int(radius * 3) + 2, align=16)
    out = jpeg_crunch(out, max(4, round(22 - 17 * f)))
    for face in faces:
        d = face['d']
        for ex, ey in face['eyes']:
            soft_spot(out, ex, ey, d * 0.55, (255, 30, 10), 0.85)
            soft_spot(out, ex, ey, d * 0.16, (255, 255, 230), 1.0)

            def painter(layer, draw, T, ss, ex=ex, ey=ey, d=d):
                cx, cy = T(ex, ey)
                for ang in (0, 90, 45, 135):
                    L = d * (1.6 if ang in (0, 90) else 0.9) * ss
                    dx, dy = math.cos(math.radians(ang)) * L, math.sin(math.radians(ang)) * L
                    draw.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=(255, 150, 120, 200),
                              width=max(1, int(d * 0.035 * ss)))

            paint(out, (ex - d * 1.7, ey - d * 1.7, ex + d * 1.7, ey + d * 1.7), painter, ss=2)
    if p['emojis']:
        rng = np.random.default_rng(int(p['intensidade']) * 13 + 5)  # fixo entre quadros do vídeo
        for i in range(3 + int(3 * f)):
            size = min(h, w) * rng.uniform(0.1, 0.18)
            em = emoji_image(FRIED_EMOJIS[i % len(FRIED_EMOJIS)], size)
            if em is None:
                ctx['notes'].add('Frito: nenhuma fonte de emoji colorido encontrada, os emojis ficaram de fora.')
                break
            em = em.rotate(rng.uniform(-25, 25), resample=Image.BICUBIC, expand=True)
            composite(out, em, rng.uniform(0, w - em.width), rng.uniform(0, h - em.height))
    return out


def fx_batata(arr, p, ctx):
    h, w, c = arr.shape
    f = p['intensidade'] / 100.0
    # a foto "encolhe" para ~100-350 px no lado maior, qualquer que seja a resolução
    k = min(1.0, (90 + 260 * (1 - f)) / max(w, h))
    sw, sh = max(8, round(w * k)), max(8, round(h * k))
    img = Image.fromarray(np.ascontiguousarray(arr[..., :3])).resize((sw, sh), Image.BOX)
    small = jpeg_crunch(np.asarray(img).copy(), max(4, round(22 - 16 * f)))
    big = np.asarray(Image.fromarray(small).resize((w, h), Image.BILINEAR))
    out = np.empty_like(arr)
    out[..., :3] = big
    if c == 4:
        out[..., 3] = arr[..., 3]
    seed = ctx.get('seed', 0)

    def potato(rgb, region):
        rgb = rgb * 1.08 + 0.035 * f
        lum = E._luma(rgb)[..., None]
        rgb = lum + (rgb - lum) * (1 - 0.25 * f)
        rgb = rgb * np.array([1.03, 1.02, 0.9], np.float32)
        rng = np.random.default_rng((seed + region[0] * 3 + ctx.get('frame', 0) * 11) & 0xFFFFFFFF)
        return np.clip(rgb + rng.standard_normal(rgb.shape).astype(np.float32) * 0.03 * f, 0, 1)

    return by_strips(out, potato)


def fx_clones(arr, p, ctx):
    h, w, c = arr.shape
    n = int(p['grade'])
    tw, th = (w + n - 1) // n, (h + n - 1) // n
    small = np.asarray(Image.fromarray(np.ascontiguousarray(arr)).resize((tw, th), Image.LANCZOS))
    out = np.empty((th * n, tw * n, c), np.uint8)
    for i in range(n * n):
        tile = small.copy()
        if p['cores'] and i:
            tile[..., :3] = hue_rotate_u8(small[..., :3], i * 360.0 / (n * n), 1.25)
        y, x = (i // n) * th, (i % n) * tw
        out[y:y + th, x:x + tw] = tile
    return np.ascontiguousarray(out[:h, :w])


def fx_infinito(arr, p, ctx):
    h, w, c = arr.shape
    base = Image.fromarray(np.ascontiguousarray(arr))
    f = p['escala'] / 100.0
    sizes = [(w, h)]
    while len(sizes) < 16:
        nw, nh = round(sizes[-1][0] * f), round(sizes[-1][1] * f)
        if min(nw, nh) < 6:
            break
        sizes.append((nw, nh))
    inner = base.resize(sizes[-1], Image.LANCZOS)
    for k in range(len(sizes) - 2, -1, -1):
        lvl = base.resize(sizes[k], Image.LANCZOS) if k else base.copy()
        child = inner.convert('RGBA')
        if p['moldura']:
            bw = max(1, round(min(child.size) * 0.03))
            ImageDraw.Draw(child).rectangle((0, 0, child.width - 1, child.height - 1), outline=(255, 255, 255, 255),
                                            width=bw)
        if p['giro']:
            child = child.rotate(p['giro'], resample=Image.BICUBIC, expand=True)
        lvl.paste(child, ((lvl.width - child.width) // 2, (lvl.height - child.height) // 2), child)
        inner = lvl
    return np.asarray(inner.convert('RGBA' if c == 4 else 'RGB')).copy()


def _cracks(w, h, p):
    """Rachaduras em coordenadas de pixel (listas de polilinhas), a partir do
    ponto de impacto: raios tortos com ramificações e anéis de teia de aranha."""
    rng = np.random.default_rng(int(p['variacao']) * 7919 + 3)
    D = math.hypot(w, h)
    if p['impacto'] == 'centro':
        p0 = (w * rng.uniform(0.45, 0.55), h * rng.uniform(0.42, 0.55))
    elif p['impacto'] == 'canto':
        p0 = (w * rng.uniform(0.74, 0.86), h * rng.uniform(0.7, 0.84))
    else:
        p0 = (w * rng.uniform(0.2, 0.8), h * rng.uniform(0.2, 0.8))
    q = p['quantidade'] / 100.0
    n = int(8 + 18 * q)
    lines, rays = [], []

    def walk(start, ang, length, depth):
        pts = [start]
        x, y = start
        step = D * 0.022
        travelled = 0.0
        while travelled < length:
            ang += rng.normal(0, 0.2)
            x, y = x + step * math.cos(ang), y + step * math.sin(ang)
            pts.append((x, y))
            travelled += step
            if not (-step <= x <= w + step and -step <= y <= h + step):
                break
            if depth < 2 and rng.random() < 0.1:
                walk((x, y), ang + rng.choice([-1, 1]) * rng.uniform(0.35, 0.8), (length - travelled) * 0.5, depth + 1)
        lines.append(pts)
        return pts

    for i in range(n):
        ang = 2 * math.pi * i / n + rng.uniform(-0.2, 0.2)
        rays.append((ang, walk(p0, ang, D * rng.uniform(0.25, 0.9) * (0.6 + 0.6 * q), 0)))
    rays.sort(key=lambda r: r[0])
    for radius in (0.035, 0.075, 0.13)[:1 + int(2 * q + 0.5)]:
        ring = []
        for ang, _ in rays:
            rr = D * radius * rng.uniform(0.8, 1.2)
            ring.append((p0[0] + rr * math.cos(ang), p0[1] + rr * math.sin(ang)))
        for a_, b_ in zip(ring, ring[1:] + ring[:1]):
            if rng.random() > 0.25:
                lines.append([a_, b_])
    for _ in range(40):
        a_ = rng.uniform(0, 2 * math.pi)
        r1, r2 = D * rng.uniform(0, 0.015), D * rng.uniform(0.005, 0.03)
        lines.append([(p0[0] + r1 * math.cos(a_), p0[1] + r1 * math.sin(a_)),
                      (p0[0] + r2 * math.cos(a_ + 0.3), p0[1] + r2 * math.sin(a_ + 0.3))])
    return p0, lines


def fx_telarachada(arr, p, ctx):
    arr = arr.copy()
    h, w = arr.shape[:2]
    # As rachaduras não mudam entre os quadros do vídeo
    p0, lines = E._cached(ctx, ('cracks', w, h, p['impacto'], p['quantidade'], p['variacao']),
                          lambda: _cracks(w, h, p))
    D = math.hypot(w, h)
    soft_spot(arr, p0[0], p0[1], D * 0.02, (235, 240, 245), 0.55)
    lw = max(1.0, D * 0.0012)

    def painter(layer, draw, T, ss):
        for pts in lines:
            tp = [T(x, y) for x, y in pts]
            draw.line([(x + lw * ss, y + lw * ss) for x, y in tp], fill=(0, 0, 0, 120), width=max(1, int(lw * ss)))
        for pts in lines:
            draw.line([T(x, y) for x, y in pts], fill=(245, 250, 255, 215), width=max(1, int(lw * ss)))

    paint(arr, (0, 0, w, h), painter, ss=2)
    return arr


def fx_terremoto(arr, p, ctx):
    h, w = arr.shape[:2]
    f = p['forca'] / 100.0
    amp = min(w, h) * 0.03 * f
    cx, cy = w / 2, h / 2
    if ctx.get('video'):
        rng = E._rng(ctx, 555)
        dx, dy = rng.normal(0, 1) * amp, rng.normal(0, 1) * amp
        th = math.radians(rng.normal(0, 1.4 * f))
        zoom = 1 + 0.07 * f
        cos, sin = math.cos(th), math.sin(th)

        def coords(xs, ys, W, H):
            x, y = (xs - cx) / zoom, (ys - cy) / zoom
            return cx + cos * x + sin * y - dx, cy - sin * x + cos * y - dy

        return geo_remap(arr, coords)
    # Foto: rastro de tremida (cópias deslocadas e levemente giradas)
    copies = [(0, 0, 0.0, 0.4), (amp, -0.6 * amp, 0.6, 0.22), (-0.8 * amp, 0.5 * amp, -0.5, 0.2),
              (0.3 * amp, 0.9 * amp, 0.3, 0.18)]

    def make(dx, dy, deg):
        c_, s_ = math.cos(math.radians(deg * f)), math.sin(math.radians(deg * f))
        zoom = 1 + 0.04 * f

        def coords(xs, ys, W, H):
            x, y = (xs - cx) / zoom, (ys - cy) / zoom
            return cx + c_ * x + s_ * y - dx, cy - s_ * x + c_ * y - dy
        return coords

    return geo_blend(arr, [make(dx, dy, deg) for dx, dy, deg, _ in copies], [c[3] for c in copies])


# ---------------------------------------------------------------------------
# Deformações
# ---------------------------------------------------------------------------

def fx_redemoinho(arr, p, ctx):
    h, w = arr.shape[:2]
    cx, cy = (w - 1) / 2, (h - 1) / 2
    R = max(4.0, p['raio'] / 100.0 * 0.5 * math.hypot(w, h))
    maxang = 2 * math.pi * 1.2 * p['forca'] / 100.0

    def coords(xs, ys, W, H):
        dx, dy = xs - cx, ys - cy
        r = np.sqrt(dx * dx + dy * dy) / R
        ang = maxang * np.clip(1 - r, 0, 1) ** 2
        c_, s_ = np.cos(ang), np.sin(ang)
        return cx + c_ * dx - s_ * dy, cy + s_ * dx + c_ * dy

    return geo_remap(arr, coords, ctx, ('twirl', p['forca'], p['raio']))


def fx_espelhoparque(arr, p, ctx):
    h, w = arr.shape[:2]
    A = 0.65 * p['forca'] / 100.0
    n = p['ondas']
    cx, cy = (w - 1) / 2, (h - 1) / 2
    horiz = p['direcao'] in ('horizontal', 'ambas')
    vert = p['direcao'] in ('vertical', 'ambas')

    def coords(xs, ys, W, H):
        mx = cx + (xs - cx) / (1 + A * np.cos(2 * np.pi * n * ys / H)) if horiz else xs + 0 * ys
        my = cy + (ys - cy) / (1 + A * np.cos(2 * np.pi * n * xs / W)) if vert else ys + 0 * xs
        return mx, my

    return geo_remap(arr, coords, ctx, ('funhouse', A, n, p['direcao']))


def fx_gelatina(arr, p, ctx):
    h, w = arr.shape[:2]
    A = min(h, w) * 0.035 * p['forca'] / 100.0
    n = p['ondas']
    animate = ctx.get('video') and p['animar']
    t = _t(ctx) if animate else 0.0
    wob = 1.0 + (0.35 * math.sin(2 * math.pi * 0.9 * t) if animate else 0.0)

    def coords(xs, ys, W, H):
        return (xs + A * wob * np.sin(2 * np.pi * n * ys / H + 2 * np.pi * 1.4 * t),
                ys + 0.8 * A * wob * np.sin(2 * np.pi * n * xs / W + 2 * np.pi * 1.8 * t + 1.0))

    key = None if animate else ('jelly', A, n)
    return geo_remap(arr, coords, ctx, key)


def fx_derretendo(arr, p, ctx):
    h, w = arr.shape[:2]
    f = p['forca'] / 100.0
    rng = np.random.default_rng(int(p['variacao']) * 131 + 17)
    n = int(p['gotas'])
    centers, widths, depths = rng.uniform(0, 1, n), rng.uniform(0.008, 0.05, n), rng.uniform(0.3, 1.0, n)
    xn = np.arange(w, dtype=np.float32) / max(1, w - 1)
    melt = 0.06 * f + f * 0.55 * np.sum(depths[:, None] * np.exp(-((xn[None, :] - centers[:, None]) / widths[:, None]) ** 2),
                                         axis=0)
    melt = np.minimum(melt, 0.85).astype(np.float32)
    animate = ctx.get('video') and p['animar']
    if animate:
        prog = min(1.0, _t(ctx) / 3.0)
        melt = melt * (prog * prog * (3 - 2 * prog))

    def coords(xs, ys, W, H):
        yn = ys / max(1, H - 1)
        return xs + 0 * ys, (yn - melt[None, :] * yn * yn) * (H - 1)

    key = None if animate else ('melt', f, n, p['variacao'])
    return geo_remap(arr, coords, ctx, key)


def fx_caleidoscopio(arr, p, ctx):
    h, w = arr.shape[:2]
    cx, cy = (w - 1) / 2, (h - 1) / 2
    n = int(p['segmentos'])
    seg = 2 * math.pi / n
    rot = math.radians(p['giro'])
    k = (min(w, h) / math.hypot(w, h)) * 100.0 / p['zoom']

    def coords(xs, ys, W, H):
        dx, dy = xs - cx, ys - cy
        r = np.sqrt(dx * dx + dy * dy) * k
        a = np.mod(np.arctan2(dy, dx) - rot, seg)
        a = np.where(a > seg / 2, seg - a, a) + rot
        return cx + r * np.cos(a), cy + r * np.sin(a)

    return geo_remap(arr, coords, ctx, ('kaleido', n, p['giro'], p['zoom']))


# ---------------------------------------------------------------------------
# Câmeras e visões
# ---------------------------------------------------------------------------

MESES = ['JAN.', 'FEV.', 'MAR.', 'ABR.', 'MAI.', 'JUN.', 'JUL.', 'AGO.', 'SET.', 'OUT.', 'NOV.', 'DEZ.']


def fx_vhs(arr, p, ctx):
    h, w = arr.shape[:2]
    f = p['intensidade'] / 100.0
    seed = ctx.get('seed', 0)
    t = _t(ctx)

    def tape(rgb, region):
        y, i, q = yiq(rgb)
        kc = max(1, int(w * 0.012 * f) + 1)
        s = int(round(w * 0.004 * f))
        i, q = shift_x(hblur(i, kc), s), shift_x(hblur(q, kc), s)
        y = hblur(y, max(1, int(w * 0.0015 * (0.5 + f)))) * 0.9 + 0.045
        out = from_yiq(y, i * (1 - 0.2 * f), q * (1 - 0.2 * f)) * np.array([1.02, 0.98, 1.04], np.float32)
        ys = _ygrid(region, rgb.shape[0])
        out = out * np.where((ys // max(1, h // 240)) % 2 == 1, 1 - 0.08 * f, 1.0)[..., None]
        rng = np.random.default_rng((seed * 7 + ctx.get('frame', 0) * 13 + region[0]) & 0xFFFFFFFF)
        return np.clip(out + rng.standard_normal(rgb.shape[:2]).astype(np.float32)[..., None] * 0.025 * f, 0, 1)

    out = by_strips(arr, tape)
    # Faixa de "tracking": linhas deslocadas e chiado perto do rodapé
    rng = E._rng(ctx, 909)
    bh = max(2, int(h * (0.02 + 0.04 * f)))
    yb = int(h * (0.86 + (0.04 * math.sin(t * 0.8) if ctx.get('video') else 0)) + rng.integers(-2, 3))
    yb = min(max(0, yb), h - bh)
    for yy in range(yb, yb + bh):
        out[yy] = np.roll(out[yy], int(rng.normal(0, w * 0.025 * f)), axis=0)
        noise = (rng.random(w) < 0.25 * f)[:, None] * 170
        out[yy, :, :3] = np.clip(out[yy, :, :3].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    if p['texto']:
        size = max(10, h * 0.055)
        if not ctx.get('video') or t < 4:
            osd_text(out, 'PLAY ►', w * 0.05, h * 0.06, size)
        now = datetime.now()
        secs = int(t)
        osd_text(out, f'AM 12:{secs // 60:02d}:{secs % 60:02d}', w * 0.05, h * 0.8, size)
        osd_text(out, f'{MESES[now.month - 1]} {now.day:02d} {int(p["ano"])}', w * 0.05, h * 0.88, size)
    return out


def fx_cctv(arr, p, ctx):
    h, w, c = arr.shape
    f = p['ruido'] / 100.0
    seed = ctx.get('seed', 0)
    t = _t(ctx)
    src = arr
    if min(w, h) > 200:
        small = Image.fromarray(np.ascontiguousarray(arr[..., :3])).resize((max(1, w // 2), max(1, h // 2)), Image.BILINEAR)
        src = arr.copy()
        src[..., :3] = np.asarray(small.resize((w, h), Image.BILINEAR))

    def cam(rgb, region):
        lum = E._contrast(E._luma(rgb), 25)
        out = E._gradient_map(lum, [(0.0, '#050805'), (1.0, '#dfeedd')])
        rows = rgb.shape[0]
        out = out * (1 - 0.45 * E._vignette_mask(h, w, 0.5, 0.6, region[0], rows))[..., None]
        rng = np.random.default_rng((seed * 5 + ctx.get('frame', 0) * 17 + region[0]) & 0xFFFFFFFF)
        return np.clip(out + rng.standard_normal((rows, w)).astype(np.float32)[..., None] * 0.07 * f, 0, 1)

    out = by_strips(src, cam)
    if p['texto']:
        size = max(10, h * 0.045)
        osd_text(out, f'CAM {int(p["camera"]):02d}', w * 0.04, h * 0.06, size)
        if not ctx.get('video') or int(t * 2) % 2 == 0:
            osd_text(out, '● REC', w * 0.96, h * 0.06, size, fill=(255, 40, 40), anchor='ra')
        now = datetime.now()
        secs = 3 * 3600 + 14 * 60 + 7 + int(t)
        stamp = f'{now:%d-%m-%Y} {secs // 3600:02d}:{secs // 60 % 60:02d}:{secs % 60:02d}'
        osd_text(out, stamp, w * 0.96, h * 0.94, size, anchor='rs')
    return out


def fx_visaonoturna(arr, p, ctx):
    h, w = arr.shape[:2]
    b = p['brilho'] / 100.0
    f = p['ruido'] / 100.0
    seed = ctx.get('seed', 0)
    bino = p['formato'] == 'binoculo'

    def night(rgb, region):
        rows = rgb.shape[0]
        lum = np.clip(E._luma(rgb) * (1 + 1.1 * b), 0, 1) ** 0.85
        rng = np.random.default_rng((seed * 3 + ctx.get('frame', 0) * 19 + region[0]) & 0xFFFFFFFF)
        lum = np.clip(lum + rng.standard_normal((rows, w)).astype(np.float32) * 0.09 * f, 0, 1)
        out = E._gradient_map(lum, [(0.0, '#000a00'), (0.35, '#0b3d0b'), (0.7, '#58c24a'), (1.0, '#d8ffd0')])
        ys = _ygrid(region, rows)
        out = out * np.where(ys % 3 == 0, 0.86, 1.0)[..., None]
        if bino:
            xs = _xgrid(w)
            r = h * 0.46
            m = np.zeros((rows, w), np.float32)
            for cxx in (w / 2 - r * 0.62, w / 2 + r * 0.62):
                d = np.sqrt((xs - cxx) ** 2 + (ys - h / 2) ** 2) / r
                m = np.maximum(m, np.clip((1 - d) * r / max(2.0, h * 0.02), 0, 1))
            out = out * m[..., None]
        else:
            out = out * (1 - 0.7 * E._vignette_mask(h, w, 0.4, 0.8, region[0], rows))[..., None]
        return out

    return by_strips(arr, night)


THERMAL = {
    'ferro': [(0.0, '#000004'), (0.15, '#1b0c5c'), (0.35, '#7a1a8c'), (0.55, '#d6304b'), (0.72, '#f7791a'),
              (0.88, '#fcd23b'), (1.0, '#fffff0')],
    'arcoiris': [(0.0, '#00007a'), (0.2, '#0050ff'), (0.4, '#00e0e0'), (0.55, '#30e030'), (0.7, '#ffff00'),
                 (0.85, '#ff8000'), (1.0, '#ff0000')],
    'branco': [(0.0, '#000000'), (1.0, '#ffffff')],
}


def fx_termica(arr, p, ctx):
    h, w = arr.shape[:2]
    sigma = min(h, w) * 0.006 * p['suavizar'] / 100.0
    stops = THERMAL[p['paleta']]

    def heat(rgb, region):
        lum = gblur(E._luma(rgb), sigma)
        return E._gradient_map(E._contrast(lum, 20), stops)

    return by_strips(arr, heat, halo=int(3 * sigma) + 2)


def fx_raiox(arr, p, ctx):
    h, w = arr.shape[:2]
    b = p['brilho'] / 100.0
    sigma = min(h, w) * 0.006

    def xray(rgb, region):
        inv = E._contrast(1 - E._luma(rgb), 30)
        out = E._gradient_map(inv, [(0.0, '#000000'), (0.45, '#0a2a4a'), (0.8, '#7fcfff'), (1.0, '#ffffff')])
        glow = gblur(out, sigma) * (0.3 + 0.7 * b)
        return 1 - (1 - out) * (1 - glow)

    return by_strips(arr, xray, halo=int(3 * sigma) + 2)


def fx_anaglifo(arr, p, ctx):
    h, w = arr.shape[:2]
    s = max(1, round(w * 0.012 * p['forca'] / 100.0))
    out = arr.copy()
    out[:, :, 0] = shift_x(arr[:, :, 0], -s)
    out[:, :, 1] = shift_x(arr[:, :, 1], s)
    out[:, :, 2] = shift_x(arr[:, :, 2], s)
    return out


ASCII_RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
MATRIX_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ@#$%&*+=<>:;"
_ATLAS = {}


def _atlas(chars, cw, ch):
    key = (chars, cw, ch)
    if key not in _ATLAS:
        f = font(ch * 0.92, mono=True)
        masks = []
        for c in chars:
            img = Image.new('L', (cw, ch), 0)
            ImageDraw.Draw(img).text((cw / 2, ch / 2), c, font=f, fill=255, anchor='mm')
            masks.append(np.asarray(img))
        _ATLAS[key] = np.stack(masks)
    return _ATLAS[key]


def fx_matrix(arr, p, ctx):
    h, w, c = arr.shape
    cw = max(3, round(w / p['colunas']))
    ch = max(5, round(cw * 1.75))
    ncols, nrows = -(-w // cw), -(-h // ch)
    cells = np.asarray(Image.fromarray(np.ascontiguousarray(arr[..., :3])).resize((ncols, nrows), Image.BOX),
                       dtype=np.float32) / 255.0
    lum = E._luma(cells)
    mode = p['modo']
    if mode == 'matrix':
        chars = MATRIX_CHARS
        t = _t(ctx)
        crng = np.random.default_rng(int(ctx.get('seed', 0)) + 4242)
        speed, phase = crng.uniform(4, 12, ncols), crng.uniform(0, nrows * 1.6, ncols)
        rng = np.random.default_rng((int(ctx.get('frame', 0)) // 3 + 77) & 0xFFFFFFFF)
        idx = rng.integers(0, len(chars), (nrows, ncols))
        head = np.mod(phase + speed * t, nrows * 1.6)
        dist = head[None, :] - np.arange(nrows)[:, None]
        trail = np.where((dist >= 0) & (dist < 10), 1.0 + 1.2 * (1 - dist / 10), 1.0)
        bright = np.clip(0.04 + 1.25 * np.clip(E._contrast(lum, 40), 0, 1) ** 1.1 * trail, 0, 1.6)
        color = np.stack([0.1 * bright, bright, 0.35 * bright], axis=-1)
        is_head = (dist >= 0) & (dist < 1)
        color[is_head] = (0.85, 1.0, 0.9)
    else:
        chars = ASCII_RAMP
        idx = np.clip((lum * (len(chars) - 1)).round().astype(np.int32), 0, len(chars) - 1)
        if mode == 'colorido':
            color = np.clip(cells / np.maximum(cells.max(axis=-1, keepdims=True), 0.15) * 1.05, 0, 1)
        else:
            color = np.ones_like(cells)
    atlas = _atlas(chars, cw, ch)
    color8 = (np.clip(color, 0, 1) * 255).astype(np.uint16)
    out = np.empty((h, w, c), np.uint8)
    if c == 4:
        out[..., 3] = 255
    step = max(1, 400_000 // max(1, ncols * cw * ch))
    for r0 in range(0, nrows, step):
        r1 = min(nrows, r0 + step)
        m = atlas[idx[r0:r1]]                                         # (rr, ncols, ch, cw)
        m = m.transpose(0, 2, 1, 3).reshape((r1 - r0) * ch, ncols * cw).astype(np.uint16)
        col = np.repeat(np.repeat(color8[r0:r1], ch, axis=0), cw, axis=1)
        y0, y1 = r0 * ch, min(h, r1 * ch)
        block = (m[..., None] * col // 255).astype(np.uint8)
        out[y0:y1, :, :3] = block[:y1 - y0, :w]
    return out


# ---------------------------------------------------------------------------
# Artísticos
# ---------------------------------------------------------------------------

def fx_quadrinho(arr, p, ctx):
    h, w = arr.shape[:2]
    levels = int(p['cores'])
    pitch = max(3.0, min(h, w) * (0.004 + 0.014 * p['pontos'] / 100.0))
    thick = max(1, min(h, w) // 450)

    def comic(rgb, region):
        rows = rgb.shape[0]
        lum0 = gblur(E._luma(rgb), 1.0)
        lum = E._luma(rgb)[..., None]
        sat = np.clip(lum + (rgb - lum) * 1.4, 0, 1)
        q = np.round(sat * (levels - 1)) / (levels - 1)
        ys, xs = _ygrid(region, rows), _xgrid(w)
        u = (xs + ys) * 0.7071 / pitch
        v = (xs - ys) * 0.7071 / pitch
        dist = np.sqrt((u - np.floor(u) - 0.5) ** 2 + (v - np.floor(v) - 0.5) ** 2)
        rr = 0.6 * np.sqrt(np.clip((0.5 - lum[..., 0]) / 0.5, 0, 1))
        out = q * np.where(dist < rr, 0.45, 1.0)[..., None]
        if p['contorno']:
            edges = dilate(grad_mag(gblur(lum0, 1.0)) > 0.075, thick)
            out[edges] = 0.04
        return out

    return by_strips(arr, comic, halo=thick + 4)


def fx_lapis(arr, p, ctx):
    h, w = arr.shape[:2]
    sigma = min(h, w) * (0.002 + 0.01 * p['traco'] / 100.0)
    paper = np.array([0.985, 0.97, 0.935], np.float32)

    def sketch(rgb, region):
        gray = E._luma(rgb)
        blur = gblur(1 - gray, sigma)
        s = np.clip(gray / np.maximum(1e-3, 1 - blur * 0.985), 0, 1) ** 1.8
        out = s[..., None] * paper
        if p['colorido']:
            col = rgb / np.maximum(rgb.max(axis=-1, keepdims=True), 0.2)
            out = out * (0.55 + 0.45 * col)
        return out

    return by_strips(arr, sketch, halo=int(3 * sigma) + 2)


def fx_cartoon(arr, p, ctx):
    h, w = arr.shape[:2]
    levels = int(p['cores'])
    passes = 1 + int(2 * p['suavizar'] / 100.0)
    # A suavização é proporcional ao tamanho da foto: fixa em pixels, apagaria
    # olhos e boca numa foto pequena e não faria nada numa de 40 MP
    ds = max(1, round(min(h, w) / 500))
    sigma = max(0.8, min(h, w) / 700)
    thick = 1 + round(min(h, w) / 800 * p['contorno'] / 100.0)
    thr = 0.045 + 0.06 * (1 - p['contorno'] / 100.0)

    def toon(rgb, region):
        rows = rgb.shape[0]
        img = Image.fromarray(E._to_u8(rgb))
        small = img.resize((max(1, w // ds), max(1, rows // ds)), Image.BILINEAR) if ds > 1 else img
        for _ in range(passes):
            small = small.filter(ImageFilter.MedianFilter(3))
        smooth = np.asarray(small.resize((w, rows), Image.BILINEAR) if ds > 1 else small, dtype=np.float32) / 255.0
        lum = E._luma(smooth)
        # sombreamento de desenho: a luz vira poucas faixas, a cor (matiz) continua
        ql = gblur((np.floor(lum * levels) + 0.5) / levels, 0.7)
        out = smooth * (ql / np.maximum(lum, 0.03))[..., None]
        l2 = E._luma(out)[..., None]
        out = np.clip(l2 + (out - l2) * 1.3, 0, 1)
        edges = dilate(grad_mag(gblur(E._luma(rgb), sigma)) > thr, thick)
        out[edges] = 0.04
        return out

    halo = int(3 * sigma) + 4 * ds + thick + 4
    halo = -(-halo // ds) * ds  # múltiplo de ds: a grade reduzida de cada faixa coincide com a da foto inteira
    return by_strips(arr, toon, halo=halo, align=max(2, ds))


def fx_neon(arr, p, ctx):
    h, w = arr.shape[:2]
    sigma = min(h, w) * 0.006
    b = p['brilho'] / 100.0
    bg = p['fundo'] / 100.0

    def neon(rgb, region):
        rows = rgb.shape[0]
        e = np.clip((grad_mag(gblur(E._luma(rgb), 1.0)) - 0.025) * 9, 0, 1)
        if p['cores'] == 'arcoiris':
            ys, xs = _ygrid(region, rows), _xgrid(w)
            col = hue_rgb(xs / w * 0.8 + ys / h * 0.5)
        else:
            col = rgb / np.maximum(rgb.max(axis=-1, keepdims=True), 0.05)
            l = E._luma(col)[..., None]
            col = np.clip(l + (col - l) * 1.8, 0, 1)
        lines = e[..., None] * col
        glow = gblur(lines, sigma) * (0.8 + 1.6 * b)
        return 1 - (1 - rgb * bg) * (1 - lines) * (1 - np.clip(glow, 0, 1))

    return by_strips(arr, neon, halo=int(3 * sigma) + 3)


def fx_psicodelico(arr, p, ctx):
    h, w = arr.shape[:2]
    f = p['forca'] / 100.0
    n = p['ondas']
    t = _t(ctx) if (ctx.get('video') and p['animar']) else 0.0
    diag = 0.5 * math.hypot(w, h)

    def trip(rgb, region):
        rows = rgb.shape[0]
        ys, xs = _ygrid(region, rows), _xgrid(w)
        dx, dy = xs - w / 2, ys - h / 2
        a = 2 * np.pi * n * np.sqrt(dx * dx + dy * dy) / diag + 2 * np.arctan2(dy, dx) + 2 * np.pi * 0.5 * t
        y, i, q = yiq(rgb)
        ca, sa = np.cos(a), np.sin(a)
        i2 = (i * ca - q * sa) * (1 + 1.2 * f) + 0.12 * f * ca
        q2 = (i * sa + q * ca) * (1 + 1.2 * f) + 0.12 * f * sa
        return E._mix(rgb, np.clip(from_yiq(y, i2, q2), 0, 1), f)

    return by_strips(arr, trip)


def fx_miniatura(arr, p, ctx):
    h, w = arr.shape[:2]
    sigma = min(h, w) * 0.012 * (0.3 + p['desfoque'] / 100.0)
    yc = h * p['foco'] / 100.0
    band = h * p['faixa'] / 200.0

    def toy(rgb, region):
        rows = rgb.shape[0]
        blur = gblur(rgb, sigma)
        m = E._smoothstep(band, band + 0.22 * h, np.abs(_ygrid(region, rows) - yc))[..., None]
        out = rgb * (1 - m) + blur * m
        lum = E._luma(out)[..., None]
        out = lum + (out - lum) * 1.4
        return np.clip(E._contrast(out, 18) * 1.04, 0, 1)

    return by_strips(arr, toy, halo=int(3 * sigma) + 2)


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

R, S, C = E._range, E._select, E._check
TAMANHO = R('tamanho', 'Tamanho', 50, 200, 100, unit='%')
ANIMAR = C('animar', 'Animar no vídeo', True)
VARIACAO = R('variacao', 'Variação (sorteio)', 1, 99, 7)

EFFECTS = [
    # Engraçados
    {'id': 'thuglife', 'group': 'engracado', 'icon': '🕶️', 'label': 'Thug Life', 'face': True,
     'desc': 'Óculos pixelados do meme em cima dos olhos e o texto THUG LIFE. No vídeo, os óculos descem até o rosto.',
     'params': [TAMANHO, C('texto', 'Texto THUG LIFE', True), C('animar', 'Óculos descendo (vídeo)', True)]},
    {'id': 'olhosdesenho', 'group': 'engracado', 'icon': '👀', 'label': 'Olhos de Desenho', 'face': True,
     'desc': 'Olhos esbugalhados de desenho animado por cima dos olhos. No vídeo, as pupilas ficam balançando.',
     'params': [TAMANHO, VARIACAO]},
    {'id': 'palhaco', 'group': 'engracado', 'icon': '🤡', 'label': 'Nariz de Palhaço', 'face': True,
     'desc': 'Nariz vermelho brilhante e bochechas rosadas, no lugar certo do rosto.',
     'params': [TAMANHO, C('bochechas', 'Bochechas rosadas', True)]},
    {'id': 'cabecao', 'group': 'engracado', 'icon': '🎈', 'label': 'Cabeção', 'face': True,
     'desc': 'Infla a cabeça como uma lupa de parque de diversões. Sem rosto na foto, infla o centro.',
     'params': [R('forca', 'Força', 10, 100, 70, unit='%'), TAMANHO,
                S('alvo', 'Onde', [('rosto', 'No rosto (automático)'), ('centro', 'No centro da imagem')], 'rosto')]},
    {'id': 'olhudo', 'group': 'engracado', 'icon': '😳', 'label': 'Olhos Esbugalhados', 'face': True,
     'desc': 'Aumenta os olhos de verdade, como se a pessoa tivesse levado um susto.',
     'params': [R('forca', 'Força', 10, 100, 75, unit='%'), TAMANHO]},
    {'id': 'fritado', 'group': 'engracado', 'icon': '🍳', 'label': 'Frito', 'face': True,
     'desc': 'O meme "deep fried": cores estouradas, nitidez exagerada, compressão horrível, olhos brilhando e emojis.',
     'params': [R('intensidade', 'Intensidade', 10, 100, 70, unit='%'), C('olhos', 'Olhos brilhando', True),
                C('emojis', 'Emojis', True)]},
    {'id': 'batata', 'group': 'engracado', 'icon': '🥔', 'label': 'Batata',
     'desc': 'Qualidade de foto "tirada com uma batata": borrada, estourada e cheia de artefatos de compressão.',
     'params': [R('intensidade', 'Intensidade', 10, 100, 70, unit='%')]},
    {'id': 'clones', 'group': 'engracado', 'icon': '👯', 'label': 'Clones',
     'desc': 'Repete a imagem numa grade, cada cópia com uma cor diferente.',
     'params': [S('grade', 'Grade', [('2', '2 × 2'), ('3', '3 × 3'), ('4', '4 × 4')], '3'),
                C('cores', 'Cada clone de uma cor', True)]},
    {'id': 'infinito', 'group': 'engracado', 'icon': '♾️', 'label': 'Infinito',
     'desc': 'A foto dentro da foto dentro da foto (efeito Droste), com moldura e giro opcionais.',
     'params': [R('escala', 'Tamanho de cada cópia', 50, 90, 72, unit='%'), R('giro', 'Giro', 0, 45, 0, unit='°'),
                C('moldura', 'Moldura branca', True)]},
    {'id': 'telarachada', 'group': 'engracado', 'icon': '📱', 'label': 'Tela Rachada',
     'desc': 'Pegadinha: parece que a tela do celular quebrou, com rachaduras em teia a partir do impacto.',
     'params': [S('impacto', 'Ponto de impacto', [('canto', 'Canto inferior'), ('centro', 'Centro'),
                                                  ('aleatorio', 'Aleatório')], 'canto'),
                R('quantidade', 'Quantidade de rachaduras', 0, 100, 60, unit='%'), VARIACAO]},
    {'id': 'terremoto', 'group': 'engracado', 'icon': '📳', 'label': 'Terremoto',
     'desc': 'Na foto, rastro de tremida; no vídeo, a câmera chacoalha sem parar.',
     'params': [R('forca', 'Força', 10, 100, 60, unit='%')]},
    # Deformações
    {'id': 'redemoinho', 'group': 'deformar', 'icon': '🌀', 'label': 'Redemoinho',
     'desc': 'Torce a imagem em espiral a partir do centro, como água descendo pelo ralo.',
     'params': [R('forca', 'Força e sentido', -100, 100, 60, unit='%'), R('raio', 'Raio', 10, 100, 60, unit='%')]},
    {'id': 'espelhoparque', 'group': 'deformar', 'icon': '🎪', 'label': 'Espelho de Parque',
     'desc': 'Espelho de parque de diversões: estica e afina partes da imagem em ondas.',
     'params': [R('forca', 'Força', 10, 100, 75, unit='%'), R('ondas', 'Ondas', 1, 4, 2),
                S('direcao', 'Direção', [('horizontal', 'Largura (gordo/magro)'), ('vertical', 'Altura (alto/baixo)'),
                                         ('ambas', 'As duas')], 'horizontal')]},
    {'id': 'gelatina', 'group': 'deformar', 'icon': '🍮', 'label': 'Gelatina',
     'desc': 'Ondula a imagem como gelatina. No vídeo, fica balançando.',
     'params': [R('forca', 'Força', 10, 100, 50, unit='%'), R('ondas', 'Ondas', 1, 10, 3), ANIMAR]},
    {'id': 'derretendo', 'group': 'deformar', 'icon': '🫠', 'label': 'Derretendo',
     'desc': 'A imagem escorre para baixo em gotas. No vídeo, derrete aos poucos.',
     'params': [R('forca', 'Força', 10, 100, 60, unit='%'), R('gotas', 'Gotas', 3, 40, 14), VARIACAO, ANIMAR]},
    {'id': 'caleidoscopio', 'group': 'deformar', 'icon': '🔮', 'label': 'Caleidoscópio',
     'desc': 'Reflete uma fatia da imagem em volta do centro, como um caleidoscópio.',
     'params': [R('segmentos', 'Segmentos', 3, 16, 8), R('giro', 'Giro', 0, 360, 0, unit='°'),
                R('zoom', 'Zoom', 50, 200, 100, unit='%')]},
    # Câmeras e visões
    {'id': 'vhs', 'group': 'camera', 'icon': '⏯️', 'label': 'VHS',
     'desc': 'Fita VHS dos anos 90: cor borrada, linhas, faixa de tracking e PLAY e data na tela.',
     'params': [R('intensidade', 'Intensidade', 0, 100, 70, unit='%'), C('texto', 'PLAY e data na tela', True),
                R('ano', 'Ano da data', 1980, 2005, 1997)]},
    {'id': 'cctv', 'group': 'camera', 'icon': '📹', 'label': 'Câmera de Segurança',
     'desc': 'Imagem granulada de câmera de vigilância, com número da câmera, REC piscando e horário.',
     'params': [C('texto', 'CAM, REC e horário', True), R('camera', 'Número da câmera', 1, 16, 1),
                R('ruido', 'Ruído', 0, 100, 40, unit='%')]},
    {'id': 'visaonoturna', 'group': 'camera', 'icon': '🌙', 'label': 'Visão Noturna',
     'desc': 'Óculos de visão noturna: verde fósforo, chiado e linhas, com opção de binóculo.',
     'params': [R('brilho', 'Amplificação de luz', 0, 100, 60, unit='%'), R('ruido', 'Ruído', 0, 100, 45, unit='%'),
                S('formato', 'Formato', [('tela', 'Tela cheia'), ('binoculo', 'Binóculo')], 'tela')]},
    {'id': 'termica', 'group': 'camera', 'icon': '🌡️', 'label': 'Visão Térmica',
     'desc': 'Câmera térmica: o claro vira "quente" (amarelo e branco) e o escuro vira "frio".',
     'params': [S('paleta', 'Paleta', [('ferro', 'Ferro em brasa'), ('arcoiris', 'Arco-íris'),
                                       ('branco', 'Branco quente')], 'ferro'),
                R('suavizar', 'Suavizar', 0, 100, 40, unit='%')]},
    {'id': 'raiox', 'group': 'camera', 'icon': '🦴', 'label': 'Raio-X',
     'desc': 'Negativo azulado e brilhante, como uma chapa de raio-X.',
     'params': [R('brilho', 'Brilho', 0, 100, 50, unit='%')]},
    {'id': 'anaglifo', 'group': 'camera', 'icon': '🥽', 'label': '3D Anáglifo',
     'desc': 'Separa vermelho e ciano para ver com óculos 3D de papel.',
     'params': [R('forca', 'Profundidade', 10, 100, 50, unit='%')]},
    {'id': 'matrix', 'group': 'camera', 'icon': '💻', 'label': 'Matrix',
     'desc': 'Transforma a imagem em letras: chuva verde do Matrix, ASCII art ou letras coloridas.',
     'params': [S('modo', 'Estilo', [('matrix', 'Matrix (verde)'), ('ascii', 'ASCII (branco)'),
                                     ('colorido', 'Letras coloridas')], 'matrix'),
                R('colunas', 'Letras na largura', 30, 240, 110)]},
    # Artísticos
    {'id': 'quadrinho', 'group': 'arte', 'icon': '💥', 'label': 'Quadrinhos',
     'desc': 'Gibi: cores chapadas, pontilhado de impressão nas sombras e contorno preto.',
     'params': [R('pontos', 'Tamanho do pontilhado', 0, 100, 40, unit='%'), R('cores', 'Níveis de cor', 3, 6, 4),
                C('contorno', 'Contorno preto', True)]},
    {'id': 'lapis', 'group': 'arte', 'icon': '✏️', 'label': 'Desenho a Lápis',
     'desc': 'Esboço a lápis em papel, em cinza ou com lápis de cor.',
     'params': [R('traco', 'Espessura do traço', 0, 100, 45, unit='%'), C('colorido', 'Lápis de cor', False)]},
    {'id': 'cartoon', 'group': 'arte', 'icon': '🎨', 'label': 'Desenho Animado',
     'desc': 'Cores lisas e poucas, com contorno preto, como um desenho animado.',
     'params': [R('cores', 'Níveis de cor', 4, 12, 7), R('contorno', 'Contorno', 0, 100, 50, unit='%'),
                R('suavizar', 'Suavizar', 0, 100, 60, unit='%')]},
    {'id': 'neon', 'group': 'arte', 'icon': '💡', 'label': 'Neon',
     'desc': 'Só os contornos, brilhando como letreiro de neon sobre o escuro.',
     'params': [R('brilho', 'Brilho', 0, 100, 60, unit='%'), R('fundo', 'Fundo visível', 0, 100, 15, unit='%'),
                S('cores', 'Cores', [('original', 'Da foto'), ('arcoiris', 'Arco-íris')], 'original')]},
    {'id': 'psicodelico', 'group': 'arte', 'icon': '🌈', 'label': 'Psicodélico',
     'desc': 'Cores girando em espiral de arco-íris. No vídeo, as cores ficam rodando.',
     'params': [R('forca', 'Força', 0, 100, 70, unit='%'), R('ondas', 'Ondas', 1, 10, 3), ANIMAR]},
    {'id': 'miniatura', 'group': 'arte', 'icon': '🏘️', 'label': 'Miniatura',
     'desc': 'Tilt-shift: desfoca em cima e embaixo e realça as cores, e a cena parece uma maquete.',
     'params': [R('foco', 'Altura do foco', 0, 100, 55, unit='%'), R('faixa', 'Faixa nítida', 5, 50, 18, unit='%'),
                R('desfoque', 'Desfoque', 0, 100, 60, unit='%')]},
]

FX = {
    'thuglife': fx_thuglife, 'olhosdesenho': fx_olhosdesenho, 'palhaco': fx_palhaco, 'cabecao': fx_cabecao,
    'olhudo': fx_olhudo, 'fritado': fx_fritado, 'batata': fx_batata, 'clones': fx_clones, 'infinito': fx_infinito,
    'telarachada': fx_telarachada, 'terremoto': fx_terremoto, 'redemoinho': fx_redemoinho,
    'espelhoparque': fx_espelhoparque, 'gelatina': fx_gelatina, 'derretendo': fx_derretendo,
    'caleidoscopio': fx_caleidoscopio, 'vhs': fx_vhs, 'cctv': fx_cctv, 'visaonoturna': fx_visaonoturna,
    'termica': fx_termica, 'raiox': fx_raiox, 'anaglifo': fx_anaglifo, 'matrix': fx_matrix,
    'quadrinho': fx_quadrinho, 'lapis': fx_lapis, 'cartoon': fx_cartoon, 'neon': fx_neon,
    'psicodelico': fx_psicodelico, 'miniatura': fx_miniatura,
}
