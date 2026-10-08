"""Renderizador dos ícones 3D dos apps do LocalTools (static/localtools/apps/<id>.webp).

Cada ícone é o símbolo Phosphor do app (static/localtools/icons/) virado peça 3D:
mapa de altura com chanfro arredondado e espessura, na cor do grupo, sobre uma
placa de grafite chanfrada. Mesma luz em todos: principal de cima-esquerda,
preenchimento verde-azulado (as luzes do fundo do site), verniz e sombra.

Uso (com o venv do Verto):
  pip install playwright   # só para rasterizar os SVGs, usa o Chrome instalado
  python scripts/icones_3d.py            # todos
  python scripts/icones_3d.py meuapp     # só um (adicione-o em APPS antes)
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

RAIZ = Path(__file__).resolve().parent.parent
SVGS = RAIZ / 'static' / 'localtools' / 'icons'
SAIDA = RAIZ / 'static' / 'localtools' / 'apps'
D = Path('/tmp') / 'localtools-mascaras'
N = 640                     # tamanho de trabalho (sai reduzido, com antisserrilhado)
OUT = 192

GRUPOS = {
    'downloads': '#4ade80', 'imagem': '#f472b6', 'audio': '#fbbf24', 'documentos': '#fb7185',
    'conversao': '#38bdf8', 'privacidade': '#a78bfa', 'texto': '#2dd4bf', 'dev': '#fb923c', 'ajuda': '#e2e8f0',
}
APPS = {  # id: (símbolo, grupo)
    'verto': ('youtube-logo', 'downloads'), 'instasaver': ('camera', 'downloads'), 'vscosaver': ('aperture', 'downloads'),
    'whatssaver': ('chat-circle-dots', 'downloads'), 'automacoes': ('lightning', 'downloads'), 'purpleflix': ('film-reel', 'downloads'),
    'efeitos': ('magic-wand', 'imagem'), 'editor': ('scissors', 'imagem'), 'imagestudio': ('paint-brush', 'imagem'),
    'transparent': ('eraser', 'imagem'), 'matchaeffect': ('leaf', 'imagem'), 'captureocr': ('scan', 'imagem'),
    'social': ('device-mobile', 'imagem'), 'transcribe': ('microphone', 'audio'), 'isolate': ('waveform', 'audio'),
    'smartstudio': ('microphone-stage', 'audio'), 'subtitlelab': ('closed-captioning', 'audio'), 'pdfs': ('file-pdf', 'documentos'),
    'office': ('file-doc', 'documentos'), 'files': ('folders', 'conversao'), 'conversor': ('arrows-clockwise', 'conversao'),
    'compress': ('arrows-in', 'conversao'), 'vetor3d': ('cube', 'conversao'),
    'ghost': ('ghost', 'privacidade'), 'stealth': ('fingerprint', 'privacidade'),
    'censor': ('eye-slash', 'privacidade'), 'textclean': ('git-diff', 'texto'), 'aiguard': ('detective', 'texto'),
    'clean': ('book-open', 'texto'), 'devdata': ('brackets-curly', 'dev'), 'qrcode': ('qr-code', 'dev'),
    'encurtador': ('link-simple', 'dev'), 'tempo': ('clock', 'dev'), 'instructions': ('book-bookmark', 'ajuda'),
}


def hexrgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def norm(v):
    return v / np.linalg.norm(v)


def bevel(d, largura, altura):
    """Perfil arredondado (quarto de círculo) até 'largura' px da borda."""
    t = np.clip(d / largura, 0, 1)
    return altura * np.sqrt(1 - (1 - t) ** 2)


yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
u, v = (xx + 0.5) / N * 2 - 1, (yy + 0.5) / N * 2 - 1
# Squircle (superelipse n=5, como os ícones do iOS), um pouco menor que o quadro
R = 0.965
placa = ((np.abs(u / R) ** 5 + np.abs(v / R) ** 5) <= 1).astype(np.float32)
d_placa = ndi.distance_transform_edt(placa)


def mascaras(simbolos):
    """Rasteriza os SVGs em 1024 px com o Chrome (Playwright)."""
    (D / 'mask').mkdir(parents=True, exist_ok=True)
    faltam = [s for s in simbolos if not (D / 'mask' / f'{s}.png').exists()]
    if not faltam:
        return
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome')
        pg = b.new_page(viewport={'width': 1024, 'height': 1024})
        for s in faltam:
            svg = (SVGS / f'{s}.svg').read_text().replace('<svg ', '<svg width="1024" height="1024" style="display:block;color:#fff" ', 1)
            pg.set_content(f'<html><body style="margin:0;background:transparent">{svg}</body></html>')
            pg.screenshot(path=str(D / 'mask' / f'{s}.png'), omit_background=True, clip={'x': 0, 'y': 0, 'width': 1024, 'height': 1024})
        b.close()


def glyph_mask(simbolo, escala=0.56):
    im = Image.open(D / 'mask' / f'{simbolo}.png').convert('RGBA')
    a = np.asarray(im)[..., 3].astype(np.float32) / 255
    lado = int(N * escala)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((lado, lado), Image.LANCZOS)).astype(np.float32) / 255
    m = np.zeros((N, N), np.float32)
    o = (N - lado) // 2
    m[o:o + lado, o:o + lado] = a
    return m


def sombrear(n, alb, p, ks, L1, c1, L2, c2, amb=0.22):
    V = np.array([0, 0, 1.0])
    d1 = np.clip((n * L1).sum(2), 0, 1)[..., None]
    d2 = np.clip((n * L2).sum(2), 0, 1)[..., None]
    s1 = np.clip((n * norm(L1 + V)).sum(2), 0, 1)[..., None] ** p
    s2 = np.clip((n * norm(L2 + V)).sum(2), 0, 1)[..., None] ** (p * 0.6)
    return alb * (amb + d1 * c1 * 0.85 + d2 * c2) + s1 * ks + s2 * c2 * ks * 0.8


def normais(H):
    gy, gx = np.gradient(H)
    n = np.dstack([-gx, -gy, np.ones_like(H)])
    return n / np.linalg.norm(n, axis=2, keepdims=True)


EXT = 24          # espessura da peça (px no tamanho de trabalho)
DIR = (1.0, 0.18)  # a lateral aparece para baixo e um pouco para a direita


def render(app_id):
    simbolo, grupo = APPS[app_id]
    hue = lin(hexrgb(GRUPOS[grupo]))
    L1, c1 = norm(np.array([-0.5, -0.75, 0.75])), np.array([1.0, 0.98, 0.95]) * 1.05
    L2, c2 = norm(np.array([0.65, 0.55, 0.45])), lin(hexrgb('#5eead4')) * 0.32   # verde-azulado das luzes do site

    g0 = glyph_mask(simbolo, 0.6)
    # a peça sobe meia espessura para o conjunto ficar centrado
    top = ndi.shift(g0, (-EXT * 0.55, -EXT * 0.1), order=1)
    gb = (top > 0.5).astype(np.float32)
    d_g = ndi.distance_transform_edt(gb)

    # ---- placa de grafite chanfrada ----
    t = v[..., None] * 0.5 + 0.5
    graf = lin(hexrgb('#30343d')) * (1 - t) + lin(hexrgb('#121418')) * t
    eco = ndi.gaussian_filter(gb, 40)[..., None]
    alb_placa = graf + hue * eco * 0.14
    n_placa = normais(bevel(d_placa, 34, 30.0))
    col = sombrear(n_placa, alb_placa, 30, 0.12, L1, c1, L2, c2)

    # sombra que a peça projeta na placa + oclusão de contato da base
    base = ndi.shift(top, (EXT * DIR[0], EXT * DIR[1]), order=1)
    sombra = ndi.gaussian_filter(ndi.shift(base, (14, 9), order=1), 13) * 0.7
    contato = ndi.gaussian_filter(base, 4) * 0.45
    col = col * (1 - np.clip(sombra + contato, 0, 0.9))[..., None]
    col = col + hue * ndi.gaussian_filter(ndi.shift(base, (8, 0), order=1), 16)[..., None] * 0.12

    # ---- lateral: camadas da base até o topo, mais escuras embaixo ----
    lado = lin(hue * 0) + hue * 0.30
    for k in range(EXT, 0, -1):
        m = ndi.shift(top, (k * DIR[0], k * DIR[1]), order=1)
        f = k / EXT
        c_k = hue * (0.42 - 0.22 * f) + 0.012
        col = col * (1 - m[..., None]) + c_k * m[..., None]
    # filete de luz na quina entre o topo e a lateral
    quina = np.clip(ndi.shift(top, (1.5, 0.3), order=1) - top, 0, 1)[..., None]
    col = col + quina * (hue * 0.5 + 0.25)

    # ---- topo: chanfro arredondado + leve abaulado, cor do grupo com verniz ----
    h = bevel(d_g, 14, 30.0) + 0.05 * np.minimum(d_g, 70)
    h = ndi.gaussian_filter(h, 1.0)
    n_top = normais(h)
    # cor do grupo saturada; só o alto da peça clareia um pouco (luz do céu)
    alto = np.clip(1 - (yy[..., None] / N - 0.18) / 0.45, 0, 1)
    alb_top = hue * (1 - 0.35 * alto) + (hue * 0.4 + 0.6) * 0.35 * alto
    col_top = sombrear(n_top, alb_top, 80, 0.75, L1, c1, L2, c2, amb=0.3)         + sombrear(n_top, np.zeros(3), 10, 0.10, L1, c1, L2, c2)
    # verniz: reflexo diagonal suave na face de cima
    diag = (u + v)[..., None]
    verniz = np.clip(1 - np.abs(diag + 0.55) / 0.42, 0, 1) ** 1.6 * 0.20
    plano = np.clip(d_g / 14, 0, 1)[..., None]
    col_top = col_top + verniz * plano
    col = col * (1 - top[..., None]) + col_top * top[..., None]

    # filete de luz no alto da placa (vidro)
    borda = np.clip(1 - d_placa / 2.5, 0, 1) * np.clip(-v, 0, 1) * 0.4
    col = col + borda[..., None]
    rgba = np.dstack([srgb(col), ndi.gaussian_filter(placa, 0.7)])
    im = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8))
    return im.resize((OUT, OUT), Image.LANCZOS)


if __name__ == '__main__':
    ids = sys.argv[1:] or list(APPS)
    mascaras(sorted({APPS[i][0] for i in ids}))
    SAIDA.mkdir(parents=True, exist_ok=True)
    for i in ids:
        render(i).save(SAIDA / f'{i}.webp', 'WEBP', quality=90, method=6)
    print(len(ids), 'ícones em', SAIDA)
