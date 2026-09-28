"""Motor do app Efeitos.

Aplica efeitos em fotos e vídeos e devolve o arquivo NO MESMO FORMATO do
original, com o nome do efeito entre parênteses: "praia.jpg" -> "praia (Sépia).jpg".

Um efeito é uma função numpy que recebe um quadro (RGB em float 0..1 + alfa
opcional) e devolve outro. Fotos, GIFs animados e vídeos passam pela mesma
função, então a prévia, a foto e o vídeo ficam idênticos:

  - Pillow (+pillow-heif)  lê e grava as fotos no formato original, inclusive
                           animações (GIF/WebP/APNG), EXIF, perfil de cor e DPI
  - FFmpeg                 decodifica o vídeo em quadros crus, que passam pelo
                           efeito e voltam para o FFmpeg no mesmo contêiner, com
                           o áudio original copiado sem recodificar
  - PyMuPDF                rasteriza SVG (que volta como SVG com a imagem embutida)
  - rembg                  opcional: recorte do assunto por IA na Silhueta

Parâmetros que dependem de tamanho (pixel, grão, deslocamento do glitch) são
relativos à imagem, então a prévia reduzida mostra o mesmo resultado do arquivo
final em resolução cheia.
"""

import base64
import hashlib
import io
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np


class EffectError(Exception):
    pass


# ---------------------------------------------------------------------------
# Catálogo de efeitos (a interface é montada a partir daqui)
# ---------------------------------------------------------------------------

GROUPS = [
    ('engracado', '😂', 'Engraçados'),
    ('deformar', '🌀', 'Deformações Divertidas'),
    ('cor', '🎨', 'Filtros de Cor e Época'),
    ('otico', '🎭', 'Distorções e Efeitos Ópticos'),
    ('camera', '📹', 'Câmeras e Visões'),
    ('arte', '🖌️', 'Estilos Artísticos e Gráficos'),
]


def _range(pid, label, lo, hi, default, step=1, unit=''):
    return {'id': pid, 'label': label, 'type': 'range', 'min': lo, 'max': hi,
            'default': default, 'step': step, 'unit': unit}


def _select(pid, label, options, default):
    return {'id': pid, 'label': label, 'type': 'select',
            'options': [{'value': v, 'label': l} for v, l in options], 'default': default}


def _color(pid, label, default):
    return {'id': pid, 'label': label, 'type': 'color', 'default': default}


def _check(pid, label, default):
    return {'id': pid, 'label': label, 'type': 'check', 'default': default}


INTENSITY = _range('intensidade', 'Intensidade', 0, 100, 100, unit='%')

# "label" é o texto que entra no nome do arquivo: "foto (Sépia).jpg"
EFFECTS = [
    {'id': 'sepia', 'group': 'cor', 'icon': '🟤', 'label': 'Sépia',
     'desc': 'Tom marrom-avermelhado que imita o envelhecimento das fotografias do século XIX.',
     'params': [INTENSITY, _range('envelhecer', 'Desbotado', 0, 100, 25, unit='%')]},
    {'id': 'pb', 'group': 'cor', 'icon': '⚫', 'label': 'Preto e Branco',
     'desc': 'Remove toda a cor e destaca contraste, texturas, luzes e sombras.',
     'params': [_range('contraste', 'Contraste', -50, 100, 15, unit='%'),
                _select('filtro', 'Filtro de lente', [
                    ('neutro', 'Neutro'), ('vermelho', 'Vermelho (céu dramático)'),
                    ('amarelo', 'Amarelo (clássico)'), ('verde', 'Verde (vegetação e pele)'),
                    ('azul', 'Azul (clima de névoa)')], 'neutro')]},
    {'id': 'ciano', 'group': 'cor', 'icon': '🔷', 'label': 'Ciano',
     'desc': 'Cianotipia: monocromático azul, frio e melancólico, como os primeiros processos de impressão.',
     'params': [INTENSITY, _range('contraste', 'Contraste', -50, 100, 10, unit='%')]},
    {'id': 'vintage', 'group': 'cor', 'icon': '📼', 'label': 'Vintage',
     'desc': 'Cores lavadas, baixo contraste e granulação das câmeras de filme dos anos 70 a 90.',
     'params': [INTENSITY, _range('grao', 'Granulação', 0, 100, 35, unit='%'),
                _range('vinheta', 'Vinheta', 0, 100, 30, unit='%'),
                _select('tom', 'Tom do filme', [('quente', 'Quente (anos 70)'), ('frio', 'Frio (anos 90)'),
                                                ('rosado', 'Rosado (anos 80)')], 'quente')]},
    {'id': 'duotone', 'group': 'cor', 'icon': '🌗', 'label': 'Duotone',
     'desc': 'Troca as cores por apenas duas tonalidades contrastantes, como em capas de álbuns.',
     'params': [_color('cor1', 'Cor das sombras', '#1f2a8c'), _color('cor2', 'Cor das luzes', '#ffd23f'),
                _range('contraste', 'Contraste', -50, 100, 20, unit='%'), INTENSITY],
     'presets': [['#1f2a8c', '#ffd23f'], ['#2d0b59', '#ff5ca8'], ['#0b3d3a', '#b8ff5c'],
                 ['#3a0c0c', '#ff9f43'], ['#101820', '#34d1ff'], ['#4a0072', '#00f5d4']]},
    {'id': 'negativo', 'group': 'otico', 'icon': '🔄', 'label': 'Negativo',
     'desc': 'Inverte cores e luminosidade: o claro fica escuro e cada cor vira a complementar.',
     'params': [INTENSITY]},
    {'id': 'glitch', 'group': 'otico', 'icon': '📺', 'label': 'Glitch',
     'desc': 'Falhas digitais: faixas horizontais deslocadas, blocos de cor pura e canais RGB separados.',
     'params': [_range('intensidade', 'Intensidade', 0, 100, 55, unit='%'),
                _range('separacao', 'Separação RGB', 0, 100, 50, unit='%'),
                _check('linhas', 'Linhas de varredura', True),
                _range('variacao', 'Variação (sorteio)', 1, 99, 7)]},
    {'id': 'olhodepeixe', 'group': 'otico', 'icon': '🐟', 'label': 'Olho de Peixe',
     'desc': 'Distorção circular ultra-angular de lente esférica, que curva as bordas.',
     'params': [_range('forca', 'Força', 5, 100, 65, unit='%'),
                _select('formato', 'Formato', [('circulo', 'Círculo (bordas escuras)'),
                                               ('cheio', 'Tela cheia')], 'circulo')]},
    {'id': 'espelho', 'group': 'otico', 'icon': '🪞', 'label': 'Espelho',
     'desc': 'Duplica e reflete metade da imagem de forma simétrica.',
     'params': [_select('modo', 'Reflexo', [('esquerda', 'Esquerda → direita'), ('direita', 'Direita → esquerda'),
                                            ('cima', 'Cima → baixo'), ('baixo', 'Baixo → cima'),
                                            ('quadrantes', '4 quadrantes (caleidoscópio)')], 'esquerda')]},
    {'id': 'silhueta', 'group': 'arte', 'icon': '👤', 'label': 'Silhueta',
     'desc': 'Escurece o assunto contra um fundo bem iluminado, destacando só o contorno.',
     'params': [_select('modo', 'Detecção do assunto', [('luz', 'Pela luz (contraluz)'),
                                                         ('ia', 'Recorte por IA (fotos)')], 'luz'),
                _range('limiar', 'Limiar (0 = automático)', 0, 100, 0),
                _range('fundo', 'Clarear o fundo', 0, 100, 45, unit='%')]},
    {'id': 'popart', 'group': 'arte', 'icon': '🟨', 'label': 'Pop Art',
     'desc': 'Cores vibrantes e irreais em quatro quadrantes, imitando a serigrafia de Warhol.',
     'params': [_select('layout', 'Layout', [('quadrantes', '4 quadrantes'), ('unico', 'Imagem única')], 'quadrantes'),
                _range('niveis', 'Níveis de cor', 3, 6, 4),
                _check('contorno', 'Contorno preto', True)]},
    {'id': 'pixelado', 'group': 'arte', 'icon': '👾', 'label': 'Pixelado',
     'desc': 'Reduz a resolução até os pixels aparecerem, como um videogame clássico.',
     'params': [_range('blocos', 'Pixels na largura', 12, 320, 72),
                _select('cores', 'Paleta', [('0', 'Cores originais'), ('32', '32 cores'),
                                            ('16', '16 cores (16 bits)'), ('8', '8 cores (8 bits)'),
                                            ('4', '4 cores (Game Boy)')], '16')]},
    {'id': 'vinheta', 'group': 'arte', 'icon': '🔘', 'label': 'Vinheta',
     'desc': 'Escurece suavemente as bordas e leva o olhar para o centro.',
     'params': [_range('forca', 'Força', 0, 100, 65, unit='%'), _range('tamanho', 'Área clara', 0, 100, 45, unit='%'),
                _range('suavidade', 'Suavidade', 0, 100, 60, unit='%')]},
    {'id': 'granulado', 'group': 'arte', 'icon': '🌫️', 'label': 'Granulado',
     'desc': 'Ruído de filme analógico de ISO alto, com grãos finos ou grossos.',
     'params': [_range('quantidade', 'Quantidade', 0, 100, 40, unit='%'),
                _range('tamanho', 'Tamanho do grão', 1, 100, 25, unit='%'),
                _check('colorido', 'Grão colorido', False)]},
]

EFFECT_BY_ID = {e['id']: e for e in EFFECTS}


def catalog():
    return {
        'groups': [{'id': g, 'icon': i, 'label': l} for g, i, l in GROUPS],
        'effects': EFFECTS,
        'order': COMBINE_ORDER,
        'tones': [t for t in TONE_IDS if t != 'pb'],
        'ffmpeg': bool(shutil.which('ffmpeg') and shutil.which('ffprobe')),
    }


def _clean_params(effect_id, raw):
    """Valida os parâmetros vindos do navegador contra o catálogo."""
    eff = EFFECT_BY_ID.get(effect_id)
    if not eff:
        raise EffectError(f"Efeito desconhecido: {effect_id}")
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for p in eff['params']:
        v = raw.get(p['id'], p['default'])
        if p['type'] == 'range':
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = p['default']
            if v != v:
                v = p['default']
            v = min(p['max'], max(p['min'], v))
        elif p['type'] == 'select':
            if v not in {o['value'] for o in p['options']}:
                v = p['default']
        elif p['type'] == 'color':
            v = str(v or '')
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', v):
                v = p['default']
        elif p['type'] == 'check':
            v = v if isinstance(v, bool) else str(v).lower() in ('1', 'true', 'on', 'sim')
        out[p['id']] = v
    return out


# Ao combinar, os efeitos são aplicados por camada, não na ordem do clique:
# senão um apaga o outro (Pop Art depois da Sépia troca todas as cores, Pixelado
# depois do Granulado borra o grão, Negativo depois do Olho de Peixe deixa as
# bordas da lente brancas...). Rosto -> composição -> recorte e cor -> tom ->
# visões e filme -> deformações e lente -> gravação, falhas e textura por cima.
COMBINE_ORDER = [
    # rosto primeiro, enquanto ainda dá para achá-lo (os óculos entram antes do
    # Cabeção, então inflam junto com a cabeça)
    'thuglife', 'olhosdesenho', 'palhaco', 'cabecao', 'olhudo',
    'espelho', 'caleidoscopio',
    'silhueta', 'negativo', 'cartoon', 'lapis', 'quadrinho', 'popart', 'pixelado', 'matrix',
    'pb', 'ciano', 'duotone', 'sepia',
    'termica', 'visaonoturna', 'raiox', 'neon', 'psicodelico', 'fritado', 'vintage', 'miniatura',
    'redemoinho', 'espelhoparque', 'gelatina', 'derretendo',
    'clones', 'infinito', 'olhodepeixe', 'terremoto', 'anaglifo',
    # a "gravação" e a tela vêm por cima de tudo
    'batata', 'vhs', 'cctv', 'glitch', 'vinheta', 'granulado', 'telarachada',
]
# Filtros de tom: recolorem pela luminosidade, então combinados em sequência só o
# último sobraria. Eles viram um estágio único (ver fx_tons). A ordem acima vale
# também entre eles: frio nas sombras, quente nas luzes.
TONE_IDS = ('pb', 'ciano', 'duotone', 'sepia')


def clean_chain(chain):
    """Lista de {'id', 'params'} -> lista de (id, params validados), sem
    repetidos e na ordem de combinação."""
    if not isinstance(chain, list) or not chain:
        raise EffectError("Escolha pelo menos um efeito.")
    out = {}
    for item in chain:
        if not isinstance(item, dict):
            raise EffectError("Efeito inválido.")
        eid = item.get('id')
        if eid not in out:
            out[eid] = _clean_params(eid, item.get('params'))
    return sorted(out.items(), key=lambda kv: COMBINE_ORDER.index(kv[0]))


def chain_label(chain):
    return ' + '.join(EFFECT_BY_ID[eid]['label'] for eid, _ in chain)


def _compile(chain):
    """Junta os filtros de tom (que ficam vizinhos na ordem de combinação) num
    passo só, para eles se combinarem em vez de um substituir o outro."""
    steps = []
    for eid, params in sorted(chain, key=lambda kv: COMBINE_ORDER.index(kv[0])):
        if eid in TONE_IDS:
            if steps and steps[-1][0] == '_tons':
                steps[-1][1]['members'].append((eid, params))
            else:
                steps.append(('_tons', {'members': [(eid, params)]}))
        elif eid == 'vinheta' and any(e == 'olhodepeixe' and q['formato'] == 'circulo' for e, q in chain):
            steps.append((eid, dict(params, _circulo=True)))
        else:
            steps.append((eid, params))
    return steps


# ---------------------------------------------------------------------------
# Ferramentas de imagem em numpy
# ---------------------------------------------------------------------------

def _hex_rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def _luma(rgb, weights=(0.299, 0.587, 0.114)):
    w = np.asarray(weights, dtype=np.float32)
    return rgb @ (w / w.sum())


def _contrast(x, amount):
    """amount em %: 0 = igual, 100 = dobro, -50 = metade."""
    if not amount:
        return x
    return np.clip((x - 0.5) * (1.0 + amount / 100.0) + 0.5, 0.0, 1.0)


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / max(e1 - e0, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _gradient_map(lum, stops):
    """Mapeia a luminância (0..1) para um degradê de cores [(pos, '#rrggbb'|rgb), ...]
    usando uma tabela de 1024 tons (bem mais rápido que interpolar pixel a pixel)."""
    pos = np.array([s[0] for s in stops], dtype=np.float32)
    cols = np.array([_hex_rgb(c) if isinstance(c, str) else c for _, c in stops], dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, 1024, dtype=np.float32)
    lut = np.stack([np.interp(ramp, pos, cols[:, ch]) for ch in range(3)], axis=-1).astype(np.float32)
    idx = (np.clip(lum, 0.0, 1.0) * 1023.0 + 0.5).astype(np.int32)
    return lut[idx]


def _mix(a, b, t):
    if t >= 1.0:
        return b
    if t <= 0.0:
        return a
    return a + (b - a) * t


def _resize_float(arr, size, resample='bilinear'):
    """Redimensiona um array 2D float com o Pillow (modo 'F')."""
    from PIL import Image
    method = {'bilinear': Image.BILINEAR, 'nearest': Image.NEAREST,
              'box': Image.BOX, 'lanczos': Image.LANCZOS}[resample]
    return np.asarray(Image.fromarray(arr.astype(np.float32)).resize(size, method), dtype=np.float32)


def _rng(ctx, salt=0):
    seed = (int(ctx.get('seed', 0)) * 1_000_003 + int(ctx.get('frame', 0)) * 7919 + salt) & 0xFFFFFFFF
    return np.random.default_rng(seed)


def _cached(ctx, key, build):
    """Cache por arquivo (máscaras de vinheta, mapas do olho de peixe...).
    O primeiro quadro é processado sozinho antes do paralelismo, então não há
    corrida na criação."""
    cache = ctx.setdefault('cache', {})
    if key not in cache:
        cache[key] = build()
    return cache[key]


def _region(ctx, h, w):
    """(linha inicial, altura total, largura total) do quadro a que este pedaço
    pertence. Fora do modo em faixas, o pedaço é o próprio quadro."""
    return ctx.get('region') or (0, h, w)


def _vignette_mask(full_h, full_w, size, softness, y0=0, rows=None, circle=False):
    rows = full_h - y0 if rows is None else rows
    if circle:
        # Depois do Olho de Peixe circular: 1 na borda do círculo, não nos cantos
        ry = rx = min(full_h, full_w) / 2
        norm = 1.0
    else:
        ry, rx = full_h / 2, full_w / 2
        norm = math.sqrt(2)
    y = (np.arange(y0, y0 + rows, dtype=np.float32) - (full_h - 1) / 2) / ry
    x = (np.arange(full_w, dtype=np.float32) - (full_w - 1) / 2) / rx
    d = np.sqrt(x[None, :] ** 2 + y[:, None] ** 2) / norm  # 0 no centro, 1 nos cantos (ou na borda do círculo)
    start = 0.15 + 0.7 * size
    width = 0.1 + 0.9 * softness
    return _smoothstep(start - width * 0.35, start + width * 0.65, d).astype(np.float32)


def _apply_vignette(rgb, ctx, strength, size=0.45, softness=0.6, circle=False):
    if strength <= 0:
        return rgb
    h, w = rgb.shape[:2]
    if ctx.get('region'):
        y0, full_h, full_w = ctx['region']
        mask = _vignette_mask(full_h, full_w, size, softness, y0, h, circle)
    else:
        mask = _cached(ctx, ('vig', h, w, size, softness, circle),
                       lambda: _vignette_mask(h, w, size, softness, circle=circle))
    return rgb * (1.0 - strength * mask)[..., None]


def _interp_var(scale):
    """Fração da variância que sobra ao ampliar ruído branco por 'scale' com
    interpolação bilinear (o ruído ampliado fica mais suave e mais fraco)."""
    if scale <= 1.0:
        return 1.0
    n = max(64, int(scale * 32))
    x = (np.arange(n) + 0.5) / scale - 0.5
    t = x - np.floor(x)
    return float(np.mean((1 - t) ** 2 + t ** 2))


def _grain_noise(h, w, ctx, size, colored, salt):
    """Ruído gaussiano (desvio 1) com grão proporcional ao tamanho do quadro.
    O campo é sorteado em resolução baixa para o quadro inteiro e ampliado só
    nas linhas pedidas, então faixas vizinhas se encaixam sem emenda."""
    from PIL import Image
    y0, full_h, full_w = _region(ctx, h, w)
    cell = max(1.0, (0.6 + size * 3.4) * min(full_h, full_w) / 1000.0)
    gh, gw = max(2, int(math.ceil(full_h / cell))), max(2, int(math.ceil(full_w / cell)))
    chans = 3 if colored else 1

    def build():
        return _rng(ctx, salt).standard_normal((chans, gh, gw)).astype(np.float32)

    # Em faixas, as faixas do mesmo quadro precisam do mesmo campo
    fcache = ctx.get('fcache')
    if fcache is not None:
        key = ('grain', salt, size, chans)
        if key not in fcache:
            fcache[key] = build()
        field = fcache[key]
    else:
        field = build()
    if (gh, gw) == (full_h, full_w):
        return np.moveaxis(field[:, y0:y0 + h], 0, -1)
    box = (0, y0 * gh / full_h, gw, (y0 + h) * gh / full_h)
    planes = [np.asarray(Image.fromarray(field[c]).resize((w, h), Image.BILINEAR, box=box), dtype=np.float32)
              for c in range(chans)]
    norm = 1.0 / math.sqrt(_interp_var(full_h / gh) * _interp_var(full_w / gw))
    return np.stack(planes, axis=-1) * np.float32(norm)


def _apply_grain(rgb, ctx, amount, size=0.25, colored=False, salt=11):
    if amount <= 0:
        return rgb
    h, w = rgb.shape[:2]
    noise = _grain_noise(h, w, ctx, size, colored, salt)
    lum = _luma(rgb)
    # Filme granula mais nos meios-tons do que no preto puro e no branco estourado
    weight = (0.35 + 2.6 * lum * (1.0 - lum))[..., None]
    return np.clip(rgb + noise * (0.12 * amount) * weight, 0.0, 1.0)


def _remap_plan(h, w, map_x, map_y):
    """Pré-calcula índices (int32) e pesos da amostragem bilinear numa imagem
    de origem h x w. Em vídeo o plano é reaproveitado em todos os quadros."""
    x0 = np.floor(map_x)
    y0 = np.floor(map_y)
    fx = (map_x - x0).astype(np.float32).ravel()
    fy = (map_y - y0).astype(np.float32).ravel()
    x0 = x0.astype(np.int32)
    y0 = y0.astype(np.int32)
    x0c, x1c = np.clip(x0, 0, w - 1).ravel(), np.clip(x0 + 1, 0, w - 1).ravel()
    y0c, y1c = (np.clip(y0, 0, h - 1).ravel() * np.int32(w), np.clip(y0 + 1, 0, h - 1).ravel() * np.int32(w))
    idx = (y0c + x0c, y0c + x1c, y1c + x0c, y1c + x1c)
    wts = ((1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy)
    return idx, tuple(wt[:, None] for wt in wts), map_x.shape


def _remap(arr, plan):
    """Amostragem bilinear de arr (H, W, C) segundo o plano; devolve float32
    na escala de arr (0..1 ou 0..255)."""
    idx, wts, shape = plan
    flat = arr.reshape(-1, arr.shape[2])
    out = np.take(flat, idx[0], axis=0) * wts[0]
    for i in (1, 2, 3):
        out += np.take(flat, idx[i], axis=0) * wts[i]
    return out.reshape(shape + (arr.shape[2],))


def _otsu(lum):
    hist, edges = np.histogram(lum, bins=128, range=(0.0, 1.0))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 0.5
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = total - w0
    m0 = np.cumsum(hist * centers)
    mt = m0[-1]
    with np.errstate(divide='ignore', invalid='ignore'):
        between = (mt * w0 / total - m0) ** 2 / (w0 * w1 / total)
    between[~np.isfinite(between)] = 0
    return float(centers[int(np.argmax(between))])


def _to_u8(rgb, alpha=None):
    out = (np.clip(rgb, 0, 1) * 255.0 + 0.5).astype(np.uint8)
    if alpha is not None:
        out = np.dstack([out, (np.clip(alpha, 0, 1) * 255.0 + 0.5).astype(np.uint8)])
    return out


def _from_u8(arr):
    rgb = arr[..., :3].astype(np.float32) / 255.0
    alpha = arr[..., 3].astype(np.float32) / 255.0 if arr.shape[2] == 4 else None
    return rgb, alpha


# ---------------------------------------------------------------------------
# Efeitos: cada um recebe (rgb float32 HxWx3, alfa HxW ou None, params, ctx)
# e devolve (rgb, alfa). Efeitos geométricos transformam o alfa junto.
# Os que mexem na geometria (espelho, glitch, pixelado, pop art) trabalham em
# uint8 por baixo, o que permite aplicá-los em fotos enormes sem cópias em float.
# ---------------------------------------------------------------------------

BW_FILTERS = {
    'neutro': (0.299, 0.587, 0.114),
    'vermelho': (0.80, 0.18, 0.02),
    'amarelo': (0.45, 0.50, 0.05),
    'verde': (0.20, 0.72, 0.08),
    'azul': (0.12, 0.28, 0.60),
}


def _tone_sepia(lum, p):
    fade = p['envelhecer'] / 100.0
    lum = lum * (1.0 - 0.18 * fade) + 0.1 * fade
    return _gradient_map(lum, [(0.0, '#1c0f07'), (0.35, '#6b4428'), (0.65, '#b58a5f'), (1.0, '#fbf0d9')])


def _tone_ciano(lum, p):
    return _gradient_map(_contrast(lum, p['contraste']),
                         [(0.0, '#04142e'), (0.3, '#0d3b73'), (0.62, '#3f7fb5'), (1.0, '#eaf3fa')])


def _tone_duotone(lum, p):
    return _gradient_map(_contrast(lum, p['contraste']), [(0.0, p['cor1']), (1.0, p['cor2'])])


TONE_MAPS = {'sepia': _tone_sepia, 'ciano': _tone_ciano, 'duotone': _tone_duotone}


def _band_range(lum):
    lo, hi = (float(v) for v in np.percentile(lum[::4, ::4], [10, 90]))
    if hi - lo < 0.1:
        mid = (hi + lo) / 2
        lo, hi = mid - 0.05, mid + 0.05
    return lo, hi


def _tone_lum(rgb, p):
    pb = next((q for e, q in p['members'] if e == 'pb'), None)
    return _contrast(_luma(rgb, BW_FILTERS[pb['filtro']]), pb['contraste']) if pb else _luma(rgb)


def _tones_prepare(arr, p, ctx):
    """Para fotos em faixas: a divisão sombras/luzes vem da foto inteira."""
    small = _downscale(np.ascontiguousarray(arr[..., :3]), 1600).astype(np.float32) / 255.0
    return {'band': _band_range(_tone_lum(small, p))}


def fx_tons(rgb, alpha, p, ctx):
    """P&B, Ciano, Duotone e Sépia, sozinhos ou combinados.

    - P&B é a base: seu filtro de lente e contraste definem a luminosidade que os
      outros tons recebem, como uma cópia em sépia feita de um negativo P&B.
    - Dois ou mais tons dividem a imagem por faixa de luz (split toning): o
      primeiro na ordem de combinação fica nas sombras e o último nas luzes, com
      transição suave, então todos continuam visíveis.
    Um tom sozinho dá exatamente o mesmo resultado de antes."""
    members = p['members']
    tints = [(e, q) for e, q in members if e != 'pb']
    lum = _tone_lum(rgb, p)
    base = np.repeat(lum[..., None], 3, axis=2) if len(tints) < len(members) else rgb
    if not tints:
        return base, alpha
    if len(tints) == 1:
        e, q = tints[0]
        return _mix(base, TONE_MAPS[e](lum, q), q['intensidade'] / 100.0), alpha
    n = len(tints)
    # As faixas seguem a luz desta imagem (não valores fixos): numa foto noturna
    # quase tudo é sombra e o tom das luzes sumiria
    if 'band' in (ctx.get('prep') or {}):
        lo, hi = ctx['prep']['band']
    elif ctx.get('video'):
        lo, hi = _cached(ctx, 'tone_band', lambda: _band_range(lum))
    else:
        lo, hi = _band_range(lum)
    band = _smoothstep(lo, hi, lum)
    out = np.zeros_like(base)
    for i, (e, q) in enumerate(tints):
        weight = np.clip(1.0 - np.abs(band - i / (n - 1)) * (n - 1), 0.0, 1.0)[..., None]
        out += weight * _mix(base, TONE_MAPS[e](lum, q), q['intensidade'] / 100.0)
    return out, alpha


VINTAGE_TONES = {
    # (preto levantado, ganho) por canal: sombras lavadas e luzes sem branco puro
    'quente': ((0.09, 0.06, 0.10), (0.86, 0.82, 0.64)),
    'frio': ((0.05, 0.09, 0.12), (0.80, 0.86, 0.84)),
    'rosado': ((0.12, 0.05, 0.10), (0.88, 0.76, 0.78)),
}


def fx_vintage(rgb, alpha, p, ctx):
    lum = _luma(rgb)[..., None]
    out = lum + (rgb - lum) * 0.72                      # cores lavadas
    out = _contrast(out, -22)                           # contraste baixo
    lift, gain = VINTAGE_TONES[p['tom']]
    out = np.asarray(lift, np.float32) + out * np.asarray(gain, np.float32)
    out = _apply_vignette(out, ctx, 0.55 * p['vinheta'] / 100.0, 0.5, 0.7)
    out = _apply_grain(out, ctx, 0.55 * p['grao'] / 100.0, 0.3, False, salt=21)
    return _mix(rgb, np.clip(out, 0, 1), p['intensidade'] / 100.0), alpha


def fx_negativo(rgb, alpha, p, ctx):
    return _mix(rgb, 1.0 - rgb, p['intensidade'] / 100.0), alpha


def _glitch(img, p, ctx, maxv):
    """img (H, W, C): float 0..1 (maxv=1) ou uint8 (maxv=255); o 4º canal,
    se houver, é o alfa. O mesmo sorteio gera o mesmo resultado nos dois."""
    h, w = img.shape[:2]
    a = p['intensidade'] / 100.0
    rng = _rng(ctx, int(p['variacao']) * 131)
    if ctx.get('video'):
        # Em vídeo a falha "pisca": quadros calmos com surtos de distorção
        a *= 1.4 if rng.random() < 0.18 else 0.35 + 0.3 * rng.random()
    out = img.copy()

    def store(view, values):
        view[...] = np.clip(values, 0, maxv) if maxv == 1 else np.clip(values + 0.5, 0, 255).astype(np.uint8)

    # Faixas horizontais cortadas e deslocadas
    for _ in range(int(3 + 22 * a)):
        bh = max(1, int(h * rng.uniform(0.004, 0.06)))
        y = int(rng.integers(0, max(1, h - bh)))
        shift = int(w * rng.uniform(-0.12, 0.12) * a)
        if shift:
            out[y:y + bh] = np.roll(out[y:y + bh], shift, axis=1)

    # Canais RGB deslocados em sentidos opostos
    sep = int(round(w * 0.018 * (p['separacao'] / 100.0) * (0.5 + a)))
    if sep:
        out[..., 0] = np.roll(out[..., 0], -sep, axis=1)
        out[..., 2] = np.roll(out[..., 2], sep, axis=1)
        out[..., 1] = np.roll(out[..., 1], int(sep * 0.35), axis=0)

    # Blocos de cor pura (falha de canal)
    pure = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 1, 1], [1, 0, 1]], dtype=np.float32)
    for _ in range(int(1 + 6 * a)):
        bh = max(1, int(h * rng.uniform(0.01, 0.05)))
        bw = max(1, int(w * rng.uniform(0.08, 0.45)))
        y = int(rng.integers(0, max(1, h - bh)))
        x = int(rng.integers(0, max(1, w - bw)))
        color = pure[rng.integers(0, len(pure))]
        view = out[y:y + bh, x:x + bw, :3]
        lum = _luma(view.astype(np.float32) / maxv)
        store(view, color * (0.25 + 0.75 * lum[..., None]) * maxv)

    # Linhas de varredura
    if p['linhas']:
        step = max(2, h // 360)
        view = out[::step * 2, :, :3]
        store(view, view * (1.0 - 0.22 * min(1.0, a + 0.3)))
    return out


def fx_glitch(rgb, alpha, p, ctx):
    img = rgb if alpha is None else np.dstack([rgb, alpha])
    out = _glitch(img, p, ctx, 1)
    return out[..., :3], (None if alpha is None else out[..., 3])


def _fisheye_maps(h, w, strength, circle, y0=0, rows=None):
    """Plano de amostragem das linhas y0..y0+rows do resultado (quadro h x w)."""
    rows = h - y0 if rows is None else rows
    theta = 0.25 + 1.2 * strength             # meio ângulo de visão, até ~83°
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    radius = min(w, h) / 2.0 if circle else math.hypot(w / 2.0, h / 2.0)
    u = ((np.arange(w, dtype=np.float32) - cx) / radius)[None, :]
    v = ((np.arange(y0, y0 + rows, dtype=np.float32) - cy) / radius)[:, None]
    r = np.sqrt(u * u + v * v)
    # Lente fisheye equidistante: o raio na foto (retilínea) cresce com tan()
    rs = np.tan(np.minimum(r, 1.0) * theta) / math.tan(theta)
    k = np.where(r > 1e-6, rs / np.maximum(r, 1e-6), np.float32(1.0))
    u2, v2 = u * k, v * k
    del rs, k
    if circle:
        # Disco -> quadrado (mapeamento elíptico de Fong): a imagem inteira,
        # inclusive os cantos, é "encaixada" dentro do círculo
        u2, v2 = np.clip(u2, -1, 1), np.clip(v2, -1, 1)
        t = u2 * u2 - v2 * v2
        s2 = 2 * math.sqrt(2)
        sx = 0.5 * np.sqrt(np.maximum(0, 2 + t + s2 * u2)) - 0.5 * np.sqrt(np.maximum(0, 2 + t - s2 * u2))
        sy = 0.5 * np.sqrt(np.maximum(0, 2 - t + s2 * v2)) - 0.5 * np.sqrt(np.maximum(0, 2 - t - s2 * v2))
        map_x = cx + sx * (w / 2.0)
        map_y = cy + sy * (h / 2.0)
        # Borda do círculo antisserrilhada (1,5 px)
        edge = np.clip((1.0 - r) * radius / 1.5, 0, 1).astype(np.float32)
    else:
        map_x = cx + u2 * radius
        map_y = cy + v2 * radius
        edge = None
    map_x, map_y = np.broadcast_arrays(map_x, map_y)
    return _remap_plan(h, w, map_x, map_y), edge


def fx_olhodepeixe(rgb, alpha, p, ctx):
    h, w = rgb.shape[:2]
    circle = p['formato'] == 'circulo'
    strength = p['forca'] / 100.0
    plan, edge = _cached(ctx, ('fish', h, w, strength, circle),
                         lambda: _fisheye_maps(h, w, strength, circle))
    out = _remap(rgb, plan)
    if alpha is not None:
        alpha = _remap(alpha[..., None], plan)[..., 0]
    if edge is not None:
        if alpha is not None:
            alpha = alpha * edge          # fora do círculo fica transparente
        else:
            out = out * edge[..., None]   # sem alfa: bordas pretas, como na lente real
    return out, alpha


def _fisheye_u8(arr, p, rows_per_strip):
    """Olho de peixe numa foto grande: cada faixa do resultado amostra a imagem
    inteira, sem criar mapas nem cópias em float do quadro todo."""
    h, w, c = arr.shape
    circle = p['formato'] == 'circulo'
    strength = p['forca'] / 100.0
    out = np.empty_like(arr)
    for y0 in range(0, h, rows_per_strip):
        rows = min(rows_per_strip, h - y0)
        plan, edge = _fisheye_maps(h, w, strength, circle, y0, rows)
        strip = _remap(arr, plan)
        if edge is not None:
            if c == 4:
                strip[..., 3] *= edge
            else:
                strip *= edge[..., None]
        out[y0:y0 + rows] = np.clip(strip + 0.5, 0, 255).astype(np.uint8)
    return out


def _mirror(arr, mode):
    h, w = arr.shape[:2]
    out = arr.copy()
    hw, hh = w // 2, h // 2
    if mode in ('esquerda', 'quadrantes'):
        out[:, w - hw:] = out[:, :hw][:, ::-1]
    elif mode == 'direita':
        out[:, :hw] = out[:, w - hw:][:, ::-1]
    if mode in ('cima', 'quadrantes'):
        out[h - hh:] = out[:hh][::-1]
    elif mode == 'baixo':
        out[:hh] = out[h - hh:][::-1]
    return out


def fx_espelho(rgb, alpha, p, ctx):
    return _mirror(rgb, p['modo']), (None if alpha is None else _mirror(alpha, p['modo']))


_REMBG = {'session': None, 'lock': threading.Lock(), 'masks': OrderedDict()}


def _subject_mask_ai(rgb):
    """Máscara do assunto principal com rembg (mesmo modelo do app Transparência)."""
    try:
        from rembg import remove, new_session
    except ImportError as e:
        raise EffectError("O modo IA da Silhueta precisa do rembg: pip install rembg") from e
    from PIL import Image
    key = hashlib.md5(np.ascontiguousarray(rgb[::7, ::7]).tobytes()).hexdigest() + str(rgb.shape)
    with _REMBG['lock']:
        cached = _REMBG['masks'].get(key)
        if cached is not None:
            return cached
        if _REMBG['session'] is None:
            _REMBG['session'] = new_session('u2net')
        img = Image.fromarray(_to_u8(rgb))
        mask = remove(img, session=_REMBG['session'], only_mask=True)
        arr = np.asarray(mask.convert('L'), dtype=np.float32) / 255.0
        _REMBG['masks'][key] = arr
        while len(_REMBG['masks']) > 12:
            _REMBG['masks'].popitem(last=False)
        return arr


def _silhouette_mode(p, ctx):
    # A prévia de um vídeo mostra o mesmo modo que o vídeo final vai usar
    if p['modo'] == 'ia' and (ctx.get('video') or ctx.get('video_source')):
        ctx['notes'].add('Em vídeo a Silhueta usa a detecção pela luz (a IA quadro a quadro seria lenta demais).')
        return 'luz'
    return p['modo']


def _silhouette_prepare(arr, p, ctx):
    """Para fotos em faixas: limiar e máscara da IA calculados uma vez, numa
    versão reduzida da foto inteira."""
    small = _downscale(np.ascontiguousarray(arr[..., :3]), 1600)
    rgb = small.astype(np.float32) / 255.0
    prep = {}
    if _silhouette_mode(p, ctx) == 'ia':
        prep['mask'] = _subject_mask_ai(rgb)
    elif p['limiar'] <= 0:
        prep['thr'] = _cached(ctx, 'sil_thr', lambda: _otsu(_luma(rgb))) if ctx.get('video') else _otsu(_luma(rgb))
    return prep


def fx_silhueta(rgb, alpha, p, ctx):
    from PIL import Image
    h, w = rgb.shape[:2]
    lum = _luma(rgb)
    prep = ctx.get('prep') or {}
    if _silhouette_mode(p, ctx) == 'ia':
        if 'mask' in prep:
            y0, full_h, _ = _region(ctx, h, w)
            mh, mw = prep['mask'].shape
            box = (0, y0 * mh / full_h, mw, (y0 + h) * mh / full_h)
            subject = np.asarray(Image.fromarray(prep['mask']).resize((w, h), Image.BILINEAR, box=box),
                                 dtype=np.float32)
        else:
            subject = _subject_mask_ai(rgb)
    else:
        if p['limiar'] > 0:
            thr = p['limiar'] / 100.0
        elif 'thr' in prep:
            thr = prep['thr']
        else:
            # Em vídeo o limiar do primeiro quadro vale para todos (sem piscar)
            thr = _cached(ctx, 'sil_thr', lambda: _otsu(lum)) if ctx.get('video') else _otsu(lum)
        thr = min(0.8, max(0.12, thr))
        subject = 1.0 - _smoothstep(thr - 0.05, thr + 0.05, lum)
    boost = p['fundo'] / 100.0
    # Fundo "estourado": clareia, mas mantém a cor do céu/pôr do sol
    bg = 1.0 - (1.0 - rgb) * (1.0 - 0.75 * boost)
    bl = _luma(bg)[..., None]
    bg = np.clip(bl + (bg - bl) * (1.0 + 0.4 * boost), 0, 1)
    ink = np.array([0.02, 0.02, 0.035], dtype=np.float32)
    out = bg * (1.0 - subject[..., None]) + ink * subject[..., None]
    return out, alpha


POP_PALETTES = [
    ['#141466', '#ff2e88', '#ffd400', '#fff6c2'],
    ['#3b0a57', '#00a8ff', '#7cff4f', '#f6ff9e'],
    ['#082b1a', '#ff6a00', '#ff3cac', '#ffe45c'],
    ['#3d1400', '#8a2be2', '#00e5c7', '#fffb96'],
]


def _dilate(mask, r):
    """Dilatação quadrada (2r+1) de uma máscara booleana, separável em linhas e
    colunas (bem mais rápida que um filtro 2D quando r cresce)."""
    out = mask.copy()
    for s in range(1, r + 1):
        out[s:] |= mask[:-s]
        out[:-s] |= mask[s:]
    rows = out.copy()
    for s in range(1, r + 1):
        out[:, s:] |= rows[:, :-s]
        out[:, :-s] |= rows[:, s:]
    return out


def _poster_strip(rgb_u8, levels, palette, outline, lo, hi, thick):
    """Pôster (serigrafia) de um pedaço uint8 RGB -> uint8 RGB."""
    from PIL import Image, ImageFilter
    lum8 = _to_u8(_luma(rgb_u8.astype(np.float32) / 255.0))
    lum = np.asarray(Image.fromarray(lum8).filter(ImageFilter.MedianFilter(3)), dtype=np.float32) / 255.0
    # Equaliza para distribuir as áreas entre os níveis (serigrafia usa chapadas)
    lum = np.clip((lum - lo) / max(hi - lo, 1e-3), 0, 1)
    idx = np.minimum((lum * levels).astype(np.int32), levels - 1)
    del lum
    cols = _gradient_map(np.linspace(0, 1, levels, dtype=np.float32),
                         [(i / (len(palette) - 1), c) for i, c in enumerate(palette)])
    out = _to_u8(cols)[idx]
    if outline:
        edges = (np.diff(idx, axis=0, append=idx[-1:]) != 0) | (np.diff(idx, axis=1, append=idx[:, -1:]) != 0)
        if thick > 1:
            edges = _dilate(edges, thick)
        out[edges & (idx <= levels // 2)] = 8
    return out


def _poster(rgb_u8, levels, palette, outline, rows_per_strip=None):
    h, w = rgb_u8.shape[:2]
    thick = max(1, min(h, w) // 400)
    lo, hi = np.percentile(_luma(rgb_u8[::3, ::3].astype(np.float32) / 255.0), [3, 97])
    if not rows_per_strip or h <= rows_per_strip:
        return _poster_strip(rgb_u8, levels, palette, outline, lo, hi, thick)
    halo = thick * 2 + 4   # o filtro de mediana e o contorno olham os vizinhos
    out = np.empty((h, w, 3), dtype=np.uint8)
    for y0 in range(0, h, rows_per_strip):
        y1 = min(h, y0 + rows_per_strip)
        a, b = max(0, y0 - halo), min(h, y1 + halo)
        part = _poster_strip(rgb_u8[a:b], levels, palette, outline, lo, hi, thick)
        out[y0:y1] = part[y0 - a:y1 - a]
    return out


def _popart_u8(arr, p, rows_per_strip=None):
    from PIL import Image
    levels = int(p['niveis'])
    h, w, c = arr.shape
    if p['layout'] == 'unico':
        rgb = _poster(arr[..., :3], levels, POP_PALETTES[0], p['contorno'], rows_per_strip)
        return rgb if c == 3 else np.dstack([rgb, arr[..., 3]])
    th, tw = (h + 1) // 2, (w + 1) // 2
    small = np.asarray(Image.fromarray(np.ascontiguousarray(arr[..., :3])).resize((tw, th), Image.LANCZOS))
    out = np.empty((th * 2, tw * 2, c), dtype=np.uint8)
    for i, pal in enumerate(POP_PALETTES):
        y, x = (i // 2) * th, (i % 2) * tw
        out[y:y + th, x:x + tw, :3] = _poster(small, levels, pal, p['contorno'], rows_per_strip)
    if c == 4:
        sa = np.asarray(Image.fromarray(np.ascontiguousarray(arr[..., 3])).resize((tw, th), Image.LANCZOS))
        out[..., 3] = np.tile(sa, (2, 2))
    return out[:h, :w]


def fx_popart(rgb, alpha, p, ctx):
    return _from_u8(_popart_u8(_to_u8(rgb, alpha), p))


def _pixelate_u8(arr, p, ctx):
    from PIL import Image
    h, w, c = arr.shape
    bw = max(1, min(w, int(p['blocos'])))
    bh = max(1, min(h, round(h * bw / w)))
    small_img = Image.fromarray(np.ascontiguousarray(arr[..., :3])).resize((bw, bh), Image.BOX)
    ncolors = int(p['cores'])
    if ncolors:
        # Em vídeo a paleta do primeiro quadro vale para todos (senão as cores piscam)
        def build_palette():
            return small_img.quantize(colors=ncolors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        pal = _cached(ctx, ('pix_pal', ncolors), build_palette) if ctx.get('video') else build_palette()
        small_img = small_img.quantize(palette=pal, dither=Image.Dither.NONE).convert('RGB')
    small = np.asarray(small_img)
    ys = (np.arange(h) * bh // h).astype(np.int32)
    xs = (np.arange(w) * bw // w).astype(np.int32)
    out = np.empty_like(arr)
    out[..., :3] = small[ys][:, xs]
    if c == 4:
        sa = np.asarray(Image.fromarray(np.ascontiguousarray(arr[..., 3])).resize((bw, bh), Image.BOX))
        out[..., 3] = np.where(sa > 127, 255, 0).astype(np.uint8)[ys][:, xs]
    return out


def fx_pixelado(rgb, alpha, p, ctx):
    return _from_u8(_pixelate_u8(_to_u8(rgb, alpha), p, ctx))


def fx_vinheta(rgb, alpha, p, ctx):
    out = _apply_vignette(rgb, ctx, p['forca'] / 100.0, p['tamanho'] / 100.0, p['suavidade'] / 100.0,
                          circle=p.get('_circulo', False))
    return out, alpha


def fx_granulado(rgb, alpha, p, ctx):
    out = _apply_grain(rgb, ctx, p['quantidade'] / 100.0, p['tamanho'] / 100.0, p['colorido'], salt=37)
    return out, alpha


FX = {
    '_tons': fx_tons, 'vintage': fx_vintage, 'negativo': fx_negativo, 'glitch': fx_glitch, 'olhodepeixe': fx_olhodepeixe, 'espelho': fx_espelho,
    'silhueta': fx_silhueta, 'popart': fx_popart, 'pixelado': fx_pixelado, 'vinheta': fx_vinheta,
    'granulado': fx_granulado,
}

# Efeitos extras (engraçados, deformações, câmeras...): trabalham em uint8 e já
# cuidam sozinhos da memória em fotos grandes (ver efeitos_extras.py)
from . import efeitos_extras as _extras  # noqa: E402  (usa os helpers acima)


def _native(fn):
    def fx(rgb, alpha, p, ctx):
        return _from_u8(fn(_to_u8(rgb, alpha), p, ctx))
    return fx


NATIVE_FX = dict(_extras.FX)
EFFECTS.extend(_extras.EFFECTS)
EFFECT_BY_ID.update({e['id']: e for e in _extras.EFFECTS})
FX.update({eid: _native(fn) for eid, fn in NATIVE_FX.items()})
assert set(COMBINE_ORDER) == set(EFFECT_BY_ID) and len(COMBINE_ORDER) == len(EFFECTS)

# Acima disto o quadro é processado em faixas horizontais: um efeito em float32
# chega a ~70 bytes por pixel, e uma foto de 48 MP passaria de 3 GB de RAM.
STRIP_PIXELS = 8_000_000
STRIP_TARGET = 1_500_000   # pixels por faixa


def _sub_ctx(ctx, i):
    """Contexto do i-ésimo efeito da cadeia para ESTE quadro. O cache (máscaras,
    planos, paletas) é compartilhado entre quadros; o resto é novo a cada
    chamada, porque vários quadros são processados ao mesmo tempo."""
    shared = ctx.setdefault('subs', {}).setdefault(i, {'cache': {}})
    return {'cache': shared['cache'], 'frame': ctx.get('frame', 0), 'seed': ctx.get('seed', 0) + i * 17,
            'video': ctx.get('video', False), 'video_source': ctx.get('video_source', False),
            'fps': ctx.get('fps', 30.0), 'faces_hint': ctx.get('faces_hint'),
            'notes': ctx.setdefault('notes', set())}


def _render_strips(arr, chain, ctx):
    h, w, c = arr.shape
    rows = max(16, STRIP_TARGET // max(1, w))
    cur = arr
    for i, (eid, params) in enumerate(chain):
        sub = _sub_ctx(ctx, i)
        if eid == 'espelho':
            cur = _mirror(cur, params['modo'])
        elif eid == 'glitch':
            cur = _glitch(cur, params, sub, 255)
        elif eid == 'pixelado':
            cur = _pixelate_u8(cur, params, sub)
        elif eid == 'popart':
            cur = _popart_u8(cur, params, rows)
        elif eid == 'olhodepeixe':
            cur = _fisheye_u8(cur, params, rows)
        elif eid in NATIVE_FX:
            cur = NATIVE_FX[eid](cur, params, sub)
        else:
            # Efeitos de pixel: cada faixa sabe onde está no quadro (vinheta e
            # grão usam coordenadas globais, então não aparecem emendas)
            sub['fcache'] = {}
            if eid == 'silhueta':
                sub['prep'] = _silhouette_prepare(cur, params, sub)
            elif eid == '_tons':
                sub['prep'] = _tones_prepare(cur, params, sub)
            out = np.empty_like(cur)
            for y0 in range(0, h, rows):
                y1 = min(h, y0 + rows)
                sub['region'] = (y0, h, w)
                rgb, alpha = _from_u8(cur[y0:y1])
                rgb, alpha = FX[eid](rgb, alpha, params, sub)
                out[y0:y1] = _to_u8(rgb, alpha)
            cur = out
    return cur


def render(arr, chain, ctx):
    """Aplica a cadeia de efeitos a um quadro uint8 (H, W, 3 ou 4)."""
    h, w = arr.shape[:2]
    steps = _compile(chain)
    if h * w > STRIP_PIXELS:
        return _render_strips(arr, steps, ctx)
    rgb, alpha = _from_u8(arr)
    for i, (eid, params) in enumerate(steps):
        rgb, alpha = FX[eid](rgb, alpha, params, _sub_ctx(ctx, i))
    return _to_u8(rgb, alpha)


# ---------------------------------------------------------------------------
# Tipos de arquivo
# ---------------------------------------------------------------------------

VIDEO_EXTS = {'mp4', 'm4v', 'mov', 'mkv', 'webm', 'avi', 'wmv', 'asf', 'flv', 'f4v', 'mpg', 'mpeg',
              'm2v', 'vob', '3gp', '3g2', 'ts', 'mts', 'm2ts', 'ogv', 'mxf', 'dv', 'divx', 'rm', 'rmvb'}
SVG_EXTS = {'svg', 'svgz'}
# Formatos que o Pillow lê mas não sabe gravar (ou grava mal): saem em PNG
PIL_FORMAT_FIX = {'MPO': 'JPEG', 'JFIF': 'JPEG'}
AUDIO_ONLY_EXTS = {'mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'oga', 'opus', 'wma', 'aiff', 'aif', 'amr', 'ac3'}


def _split_name(filename):
    name = os.path.basename(filename or '').strip() or 'arquivo'
    base, ext = os.path.splitext(name)
    if not base:
        base, ext = ext, ''
    return base, ext  # ext com ponto e com a caixa original (".JPG" continua ".JPG")


def _safe_base(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', name or '').strip(' .')
    return name[:150] or 'arquivo'


def _downloads_dir():
    d = str(Path.home() / "Downloads")
    os.makedirs(d, exist_ok=True)
    return d


def output_name(original_name, label, ext=None):
    base, orig_ext = _split_name(original_name)
    return f"{_safe_base(base)} ({label}){orig_ext if ext is None else ext}"


def _unique_path(directory, filename):
    """"foto (Sépia).jpg" -> "foto (Sépia) (2).jpg" se já existir; nunca sobrescreve."""
    base, ext = os.path.splitext(filename)
    path = os.path.join(directory, filename)
    n = 2
    while os.path.exists(path):
        path = os.path.join(directory, f"{base} ({n}){ext}")
        n += 1
    return path


def _ffmpeg():
    return shutil.which('ffmpeg')


def _ffprobe():
    return shutil.which('ffprobe')


_HEIF = {'done': False}


def _register_heif():
    if _HEIF['done']:
        return
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        try:
            pillow_heif.register_avif_opener()
        except Exception:
            pass
    except Exception:
        pass
    _HEIF['done'] = True


def _probe_video(path):
    ffprobe = _ffprobe()
    if not ffprobe:
        return None
    try:
        r = subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path],
                           capture_output=True, timeout=60)
        data = json.loads(r.stdout or b'{}')
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None
    streams = data.get('streams') or []
    video = next((s for s in streams if s.get('codec_type') == 'video'
                  and not (s.get('disposition') or {}).get('attached_pic')), None)
    if not video:
        return None
    fmt = data.get('format') or {}

    def rate(text):
        try:
            a, b = str(text).split('/')
            v = float(a) / float(b)
            return v if 0 < v < 1000 else None
        except (ValueError, ZeroDivisionError):
            return None

    fps_text = video.get('avg_frame_rate')
    fps = rate(fps_text)
    if not fps:
        fps_text = video.get('r_frame_rate')
        fps = rate(fps_text)
    if not fps:
        fps_text, fps = '30', 30.0
    rotation = 0
    for sd in video.get('side_data_list') or []:
        if 'rotation' in sd:
            rotation = int(float(sd['rotation']))
    if not rotation and (video.get('tags') or {}).get('rotate'):
        rotation = int(float(video['tags']['rotate']))
    w, h = int(video.get('width') or 0), int(video.get('height') or 0)
    if abs(rotation) % 180 == 90:
        w, h = h, w
    try:
        duration = float(video.get('duration') or fmt.get('duration') or 0)
    except ValueError:
        duration = 0.0
    try:
        nb = int(video.get('nb_frames') or 0)
    except ValueError:
        nb = 0
    if duration > 0:
        nb = int(round(duration * fps)) or nb
    pix = str(video.get('pix_fmt') or '')
    return {
        'width': w, 'height': h, 'fps': fps, 'fps_text': fps_text, 'duration': duration,
        'frames': nb, 'codec': video.get('codec_name') or '', 'pix_fmt': pix,
        'alpha': bool(re.search(r'(yuva|rgba|argb|bgra|abgr|gbrap|ya)', pix)) or
                 (video.get('tags') or {}).get('alpha_mode') == '1',
        'has_audio': any(s.get('codec_type') == 'audio' for s in streams),
        'format_name': fmt.get('format_name') or '',
    }


def detect_kind(path, filename):
    """'image', 'video' ou 'svg', pelo conteúdo (a extensão pode estar errada)."""
    _, ext = _split_name(filename)
    ext = ext.lower().lstrip('.')
    if ext in SVG_EXTS:
        return 'svg'
    with open(path, 'rb') as f:
        head = f.read(512)
    if b'<svg' in head.lower() and ext not in VIDEO_EXTS:
        return 'svg'
    if ext not in VIDEO_EXTS:
        from PIL import Image
        _register_heif()
        try:
            with Image.open(path) as im:
                im.size
            return 'image'
        except Exception:
            pass
    info = _probe_video(path)
    if info and info['width'] and info['height']:
        # Uma imagem que só o FFmpeg abre (ex.: EXR, DPX) tem 1 quadro e sem duração
        still = info['frames'] <= 1 and info['duration'] <= 0.05 and not info['has_audio']
        return 'ffimage' if still else 'video'
    if ext in AUDIO_ONLY_EXTS:
        raise EffectError("Este arquivo é só áudio: os efeitos são para fotos e vídeos.")
    raise EffectError("Formato não reconhecido como foto ou vídeo.")


# ---------------------------------------------------------------------------
# Fotos (Pillow)
# ---------------------------------------------------------------------------

def _frame_to_array(frame):
    has_alpha = frame.mode in ('RGBA', 'LA', 'PA') or (frame.mode == 'P' and 'transparency' in frame.info)
    return np.asarray(frame.convert('RGBA' if has_alpha else 'RGB'))


def _array_to_image(arr):
    from PIL import Image
    return Image.fromarray(np.ascontiguousarray(arr))  # RGB ou RGBA pelo formato do array


def _save_kwargs(img, fmt):
    kw = {}
    info = img.info or {}
    icc = info.get('icc_profile')
    if icc and img.mode not in ('CMYK', 'I', 'I;16', 'F', 'YCbCr', 'LAB'):
        kw['icc_profile'] = icc
    if info.get('dpi'):
        kw['dpi'] = info['dpi']
    try:
        exif = img.getexif()
        if exif:
            exif[0x0112] = 1  # a rotação já foi aplicada nos pixels
            kw['exif'] = exif.tobytes()
    except Exception:
        pass
    if fmt == 'JPEG':
        kw.update(quality=95, subsampling=0, optimize=True)
        if info.get('progressive') or info.get('progression'):
            kw['progressive'] = True
    elif fmt == 'WEBP':
        kw.update(quality=95, method=4)
        if info.get('lossless'):
            kw['lossless'] = True
    elif fmt in ('AVIF', 'HEIF'):
        kw['quality'] = 92
    elif fmt == 'TIFF':
        kw['compression'] = info.get('compression') or 'tiff_lzw'
        if kw['compression'] in ('group3', 'group4', 'tiff_ccitt'):
            kw['compression'] = 'tiff_lzw'  # compressões só de 1 bit
    elif fmt == 'JPEG2000':
        kw = {k: v for k, v in kw.items() if k != 'exif'}
        kw['quality_mode'] = 'dB'
        kw['quality_layers'] = [48]
    elif fmt == 'ICO':
        try:
            kw['sizes'] = sorted(img.ico.sizes())
        except Exception:
            pass
    elif fmt == 'PNG':
        kw['compress_level'] = 6
    if fmt in ('GIF', 'BMP', 'ICO', 'PCX', 'TGA', 'PPM', 'SGI', 'QOI', 'XBM', 'DDS', 'ICNS', 'IM', 'MSP'):
        kw.pop('exif', None)
        kw.pop('icc_profile', None)
    return kw


def _prepare_for_format(im, fmt):
    """Ajusta o modo da imagem ao que o formato de saída aceita."""
    if fmt in ('JPEG', 'PPM', 'PCX', 'EPS', 'PDF', 'MSP', 'IM') and im.mode not in ('RGB', 'L'):
        from PIL import Image
        if im.mode == 'RGBA':
            bg = Image.new('RGB', im.size, (255, 255, 255))
            bg.paste(im, mask=im.getchannel('A'))
            return bg
        return im.convert('RGB')
    if fmt == 'XBM':
        return im.convert('1')
    return im


def _pil_writable(fmt):
    from PIL import Image
    Image.init()
    _register_heif()
    return fmt in Image.SAVE


def process_image(src, original_name, chain, dest_dir, progress=None, seed=0):
    from PIL import Image, ImageOps, ImageSequence
    _register_heif()
    try:
        img = Image.open(src)
        img.load()
    except Exception as e:
        raise EffectError(f"Não foi possível abrir a imagem ({e}).")
    fmt = PIL_FORMAT_FIX.get(img.format, img.format)
    _, ext = _split_name(original_name)
    notes = []
    if not fmt or not _pil_writable(fmt):
        notes.append(f"O formato {img.format or ext.upper()} só pode ser lido, não gravado: o resultado saiu em PNG.")
        fmt, ext = 'PNG', '.png'
    if not ext:
        ext = next((e for e, f in Image.registered_extensions().items() if f == fmt), '.png')

    n_frames = getattr(img, 'n_frames', 1) if getattr(img, 'is_animated', False) else 1
    ctx = {'seed': seed, 'video': n_frames > 1}
    if n_frames > 1:
        # GIF/WebP animado: o tempo de cada quadro vem da duração média
        try:
            durs = [f.info.get('duration', 100) or 100 for f in ImageSequence.Iterator(img)]
            ctx['fps'] = 1000.0 / max(10.0, sum(durs) / len(durs))
        except Exception:
            ctx['fps'] = 10.0
    kwargs = _save_kwargs(img, fmt)
    out_frames = []
    if n_frames > 1:
        durations = []
        for i, frame in enumerate(ImageSequence.Iterator(img)):
            ctx['frame'] = i
            durations.append(frame.info.get('duration', img.info.get('duration', 100)))
            out_frames.append(_array_to_image(render(_frame_to_array(frame), chain, ctx)))
            if progress:
                progress((i + 1) / n_frames)
    else:
        frame = ImageOps.exif_transpose(img)
        out_frames.append(_array_to_image(render(_frame_to_array(frame), chain, ctx)))
        if progress:
            progress(1.0)

    label = chain_label(chain)
    target = _unique_path(dest_dir, output_name(original_name, label, ext))
    tmp = target + '.part'
    try:
        first = _prepare_for_format(out_frames[0], fmt)
        if len(out_frames) > 1 and fmt in ('GIF', 'WEBP', 'PNG', 'TIFF', 'AVIF'):
            rest = [_prepare_for_format(f, fmt) for f in out_frames[1:]]
            extra = {'save_all': True, 'append_images': rest, 'loop': img.info.get('loop', 0)}
            if fmt != 'TIFF':
                extra['duration'] = durations
            if fmt == 'GIF':
                extra['disposal'] = 2
                kwargs.pop('optimize', None)
            first.save(tmp, format=fmt, **kwargs, **extra)
        else:
            first.save(tmp, format=fmt, **kwargs)
        os.replace(tmp, target)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise EffectError(f"Não foi possível gravar em {fmt}: {e}")
    notes.extend(sorted(ctx.get('notes', ())))
    return target, notes


# ---------------------------------------------------------------------------
# SVG (rasterizado com PyMuPDF e embutido de volta num SVG)
# ---------------------------------------------------------------------------

def _svg_raster(src, max_side=2400):
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError as e:
            raise EffectError("Para SVG é preciso o PyMuPDF (pip install PyMuPDF).") from e
    try:
        doc = fitz.open(src, filetype='svg')
        page = doc[0]
        w_pt, h_pt = page.rect.width, page.rect.height
        zoom = max(1.0, min(4.0, max_side / max(w_pt, h_pt, 1)))
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
        doc.close()
    except Exception as e:
        raise EffectError(f"Não foi possível ler o SVG ({e}).")
    return arr, w_pt, h_pt


def process_svg(src, original_name, chain, dest_dir, progress=None, seed=0):
    arr, w_pt, h_pt = _svg_raster(src)
    ctx = {'seed': seed}
    out = _array_to_image(render(arr, chain, ctx))
    buf = io.BytesIO()
    out.save(buf, 'PNG', optimize=True)
    data = base64.b64encode(buf.getvalue()).decode('ascii')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'width="{w_pt:g}" height="{h_pt:g}" viewBox="0 0 {w_pt:g} {h_pt:g}">'
           f'<image width="{w_pt:g}" height="{h_pt:g}" preserveAspectRatio="none" '
           f'href="data:image/png;base64,{data}" xlink:href="data:image/png;base64,{data}"/></svg>')
    _, ext = _split_name(original_name)
    if ext.lower() == '.svgz':
        import gzip
        payload = gzip.compress(svg.encode('utf-8'))
    else:
        payload = svg.encode('utf-8')
    target = _unique_path(dest_dir, output_name(original_name, chain_label(chain), ext or '.svg'))
    with open(target, 'wb') as f:
        f.write(payload)
    if progress:
        progress(1.0)
    return target, ['O SVG saiu com a imagem do efeito embutida (os efeitos trabalham em pixels, então os '
                    'vetores viram imagem na resolução de até 2400 px).'] + sorted(ctx.get('notes', ()))


# ---------------------------------------------------------------------------
# Vídeo (FFmpeg -> quadros crus -> efeito -> FFmpeg)
# ---------------------------------------------------------------------------

_ENCODERS = {'list': None}


def _has_encoder(name):
    if _ENCODERS['list'] is None:
        try:
            r = subprocess.run([_ffmpeg(), '-hide_banner', '-encoders'], capture_output=True, timeout=30)
            _ENCODERS['list'] = {line.split()[1] for line in r.stdout.decode('utf-8', 'ignore').splitlines()
                                 if len(line.split()) > 1 and line.startswith(' ') and line.split()[0][0] in 'VAS'}
        except Exception:
            _ENCODERS['list'] = set()
    return name in _ENCODERS['list']


def _x264(crf='18'):
    return ['-c:v', 'libx264', '-preset', 'medium', '-crf', crf, '-pix_fmt', 'yuv420p']


def _video_codec_candidates(ext, info, alpha):
    """Codecs possíveis para o contêiner, do melhor para o mais compatível."""
    ext = ext.lower()
    codec = info.get('codec', '')
    c = []
    if alpha and ext == 'webm':
        c.append(['-c:v', 'libvpx-vp9', '-crf', '28', '-b:v', '0', '-pix_fmt', 'yuva420p',
                  '-row-mt', '1', '-deadline', 'good', '-cpu-used', '3', '-auto-alt-ref', '0'])
    if alpha and ext in ('mov', 'mkv'):
        c.append(['-c:v', 'prores_ks', '-profile:v', '4444', '-pix_fmt', 'yuva444p10le'])
    if ext in ('mp4', 'm4v', 'mov', 'mkv', '3gp', '3g2', 'ts', 'mts', 'm2ts', 'flv', 'f4v', 'mxf', 'divx'):
        if codec == 'hevc' and ext in ('mp4', 'm4v', 'mov', 'mkv') and _has_encoder('libx265'):
            c.append(['-c:v', 'libx265', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-tag:v', 'hvc1'])
        if codec == 'prores' and ext in ('mov', 'mkv') and _has_encoder('prores_ks'):
            c.append(['-c:v', 'prores_ks', '-profile:v', '3', '-pix_fmt', 'yuv422p10le'])
        if codec in ('vp9', 'av1') and ext == 'mkv':
            c.append(['-c:v', 'libvpx-vp9', '-crf', '30', '-b:v', '0', '-row-mt', '1', '-deadline', 'good',
                      '-cpu-used', '4', '-pix_fmt', 'yuv420p'])
        if ext in ('3gp', '3g2'):
            c.append(['-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.0', '-crf', '20', '-pix_fmt', 'yuv420p'])
        c.append(_x264())
    elif ext == 'webm':
        if codec == 'vp8':
            c.append(['-c:v', 'libvpx', '-crf', '8', '-b:v', '4M', '-pix_fmt', 'yuv420p'])
        c.append(['-c:v', 'libvpx-vp9', '-crf', '30', '-b:v', '0', '-row-mt', '1', '-deadline', 'good',
                  '-cpu-used', '4', '-pix_fmt', 'yuv420p'])
    elif ext in ('avi', 'divx'):
        if codec == 'h264':
            c.append(_x264())
        if _has_encoder('libxvid'):
            c.append(['-c:v', 'libxvid', '-q:v', '3', '-pix_fmt', 'yuv420p'])
        c.append(['-c:v', 'mpeg4', '-q:v', '3', '-pix_fmt', 'yuv420p'])
    elif ext in ('wmv', 'asf'):
        c.append(['-c:v', 'wmv2', '-q:v', '3', '-pix_fmt', 'yuv420p'])
    elif ext in ('mpg', 'mpeg', 'm2v', 'vob'):
        c.append(['-c:v', 'mpeg2video', '-q:v', '2', '-pix_fmt', 'yuv420p'])
    elif ext == 'ogv':
        c.append(['-c:v', 'libtheora', '-q:v', '8', '-pix_fmt', 'yuv420p'])
    elif ext == 'dv':
        c.append(['-c:v', 'dvvideo', '-pix_fmt', 'yuv411p'])
    c.append(_x264())
    c.append(['-c:v', 'mpeg4', '-q:v', '3', '-pix_fmt', 'yuv420p'])
    seen, uniq = set(), []
    for args in c:
        if args[1] in ('libx264', 'libx265', 'libvpx', 'libvpx-vp9', 'libxvid', 'libtheora', 'prores_ks') \
                and not _has_encoder(args[1]):
            continue
        key = tuple(args)
        if key not in seen:
            seen.add(key)
            uniq.append(args)
    return uniq


def _tail(path, fallback):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4000))
            lines = [l for l in f.read().decode('utf-8', 'ignore').splitlines() if l.strip()]
        return lines[-1] if lines else fallback
    except OSError:
        return fallback


def _scale_filter(max_side):
    return (f"scale='if(gt(iw,ih),min({max_side},iw),-2)':"
            f"'if(gt(iw,ih),-2,min({max_side},ih))'")


def _input_args(src, info, keep_alpha, start=None):
    args = ['-hide_banner', '-v', 'error', '-nostdin']
    if keep_alpha and info['codec'] in ('vp9', 'vp8'):
        # O decodificador nativo do VP9 descarta o canal alfa; o libvpx não
        args += ['-c:v', 'libvpx-vp9' if info['codec'] == 'vp9' else 'libvpx']
    if start:
        args += ['-ss', f'{start:.3f}']
    return args + ['-i', src, '-map', '0:v:0']


def _decode_cmd(src, info, keep_alpha):
    """Todos os quadros em RGB(A) cru, a taxa constante (celulares gravam com
    taxa variável; fixar na média mantém o áudio sincronizado)."""
    return [_ffmpeg()] + _input_args(src, info, keep_alpha) + [
        '-vf', f"fps={info['fps_text']}",
        '-f', 'rawvideo', '-pix_fmt', 'rgba' if keep_alpha else 'rgb24', '-']


def video_frame(src, info, max_side=None, at=None):
    """Um quadro do vídeo (para a prévia), já com a rotação aplicada."""
    from PIL import Image
    t = at if at is not None else (min(1.0, info['duration'] * 0.15) if info['duration'] else 0)
    for start in dict.fromkeys((t, 0)):
        cmd = [_ffmpeg()] + _input_args(src, info, info['alpha'], start) + ['-frames:v', '1']
        if max_side:
            cmd += ['-vf', _scale_filter(max_side)]
        cmd += ['-f', 'image2pipe', '-c:v', 'png', '-']
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            continue
        if r.returncode == 0 and r.stdout:
            return _frame_to_array(Image.open(io.BytesIO(r.stdout)))
    raise EffectError("Não foi possível ler um quadro do vídeo.")


def process_video(src, original_name, chain, dest_dir, progress=None, seed=0, cancel=None):
    ffmpeg = _ffmpeg()
    if not ffmpeg or not _ffprobe():
        raise EffectError("Para vídeos é preciso o FFmpeg instalado (o INSTALAR.py cuida disso).")
    info = _probe_video(src)
    if not info:
        raise EffectError("Não foi possível ler o vídeo.")
    _, ext = _split_name(original_name)
    ext_l = ext.lower().lstrip('.') or 'mp4'
    if not ext:
        ext = '.mp4'
    keep_alpha = info['alpha'] and ext_l in ('webm', 'mov', 'mkv')
    w, h = info['width'], info['height']
    chans = 4 if keep_alpha else 3
    frame_bytes = w * h * chans
    total = max(1, info['frames'])

    work = tempfile.mkdtemp(prefix='efeitos_vid_')
    label = chain_label(chain)
    target = _unique_path(dest_dir, output_name(original_name, label, ext))
    notes = []
    try:
        dec_log = os.path.join(work, 'dec.log')
        candidates = _video_codec_candidates(ext_l, info, keep_alpha)
        tmp_video = os.path.join(work, 'video' + ext)
        last_error = 'erro desconhecido do FFmpeg'
        # Primeiro gera só o vídeo com efeito (pipe), depois junta o áudio/legendas
        # originais num segundo passo rápido, sem recodificar o vídeo de novo.
        for attempt, vargs in enumerate(candidates):
            even = [] if vargs[1] in ('prores_ks', 'libx264rgb') else \
                ['-vf', 'crop=trunc(iw/2)*2:trunc(ih/2)*2']
            enc_log = os.path.join(work, f'enc{attempt}.log')
            enc_cmd = [ffmpeg, '-hide_banner', '-v', 'error', '-y', '-f', 'rawvideo',
                       '-pix_fmt', 'rgba' if keep_alpha else 'rgb24', '-s', f'{w}x{h}',
                       '-framerate', info['fps_text'], '-i', '-'] + even + vargs + ['-an', tmp_video]
            with open(dec_log, 'wb') as dlog, open(enc_log, 'wb') as elog:
                dec = subprocess.Popen(_decode_cmd(src, info, keep_alpha), stdout=subprocess.PIPE, stderr=dlog)
                enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stderr=elog)
                ok = _pump_frames(dec, enc, w, h, chans, frame_bytes, chain, seed, total, progress, cancel, notes,
                                  info['fps'])
                try:
                    enc.stdin.close()
                except OSError:
                    pass
                enc.wait()
                dec.stdout.close()
                dec.wait()
            if ok == 'cancel':
                raise EffectError("Cancelado.")
            if ok == 'empty':
                raise EffectError(f"O FFmpeg não conseguiu ler os quadros: {_tail(dec_log, 'vídeo vazio')}")
            if enc.returncode == 0 and os.path.exists(tmp_video) and os.path.getsize(tmp_video) > 0:
                break
            last_error = _tail(enc_log, last_error)
            if os.path.exists(tmp_video):
                os.remove(tmp_video)
        else:
            raise EffectError(f"O FFmpeg não conseguiu gravar o vídeo em {ext_l.upper()}: {last_error}")

        # Junta o áudio (e legendas) do original sem recodificar; se o contêiner
        # recusar a cópia, recodifica só o áudio.
        tmp_final = os.path.join(work, 'final' + ext)
        base_mux = [ffmpeg, '-hide_banner', '-v', 'error', '-y', '-i', tmp_video, '-i', src,
                    '-map', '0:v:0', '-map', '1:a?']
        tries = [
            base_mux + ['-map', '1:s?', '-c', 'copy', '-map_metadata', '1', '-map_chapters', '1'],
            base_mux + ['-c', 'copy', '-map_metadata', '1'],
            base_mux + ['-c:v', 'copy', '-map_metadata', '1'] + _audio_fallback(ext_l),
        ]
        if ext_l in ('mp4', 'm4v', 'mov'):
            tries = [t + ['-movflags', '+faststart'] for t in tries]
        merged = False
        mux_log = os.path.join(work, 'mux.log')
        for t in tries:
            with open(mux_log, 'wb') as mlog:
                r = subprocess.run(t + [tmp_final], stderr=mlog, timeout=3600)
            if r.returncode == 0 and os.path.exists(tmp_final) and os.path.getsize(tmp_final) > 0:
                merged = True
                break
        if not merged:
            tmp_final = tmp_video
            if info['has_audio']:
                notes.append('O áudio original não pôde ser incluído neste formato: o vídeo saiu sem som.')
        shutil.move(tmp_final, target)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return target, notes


def _audio_fallback(ext):
    return {
        'webm': ['-c:a', 'libopus', '-b:a', '160k'],
        'ogv': ['-c:a', 'libvorbis', '-q:a', '5'],
        'avi': ['-c:a', 'libmp3lame', '-b:a', '192k'],
        'wmv': ['-c:a', 'wmav2', '-b:a', '192k'],
        'asf': ['-c:a', 'wmav2', '-b:a', '192k'],
        'mpg': ['-c:a', 'mp2', '-b:a', '224k'],
        'mpeg': ['-c:a', 'mp2', '-b:a', '224k'],
        'vob': ['-c:a', 'ac3', '-b:a', '192k'],
        'flv': ['-c:a', 'aac', '-b:a', '160k', '-ar', '44100'],
    }.get(ext, ['-c:a', 'aac', '-b:a', '192k'])


def _mem_available():
    """Memória livre em bytes (Linux: /proc/meminfo; outros sistemas: 2 GB)."""
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return 2 * 1024 ** 3


def _pump_frames(dec, enc, w, h, chans, frame_bytes, chain, seed, total, progress, cancel, notes, fps=30.0):
    """Lê quadros do decodificador, aplica o efeito em paralelo (numpy libera o
    GIL) e escreve na ordem certa no codificador."""
    ctx = {'seed': seed, 'video': True, 'fps': fps}
    # Cada quadro em processamento chega a ~80 bytes por pixel (float32 +
    # temporários): em 4K são ~660 MB, então o paralelismo depende da RAM livre.
    per_frame = w * h * 80
    budget = max(768 * 1024 ** 2, int(_mem_available() * 0.5))
    workers = max(1, min(6, (os.cpu_count() or 2) - 1, budget // max(1, per_frame)))

    def read_frame():
        buf = bytearray()
        while len(buf) < frame_bytes:
            chunk = dec.stdout.read(frame_bytes - len(buf))
            if not chunk:
                break
            buf += chunk
        if len(buf) < frame_bytes:
            return None
        return np.frombuffer(bytes(buf), dtype=np.uint8).reshape(h, w, chans)

    def job(arr, idx):
        local = dict(ctx)
        local['frame'] = idx
        return render(arr, chain, local)

    def write(arr):
        try:
            enc.stdin.write(np.ascontiguousarray(arr).tobytes())
            return True
        except (BrokenPipeError, OSError):
            return False

    first = read_frame()
    if first is None:
        return 'empty'
    # O primeiro quadro roda sozinho para preencher os caches (máscaras, paletas,
    # limiar da silhueta) que os demais quadros compartilham.
    ctx['frame'] = 0
    if not write(render(first, chain, ctx)):
        return 'encoder'
    done = 1
    pending = deque()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        idx = 1
        eof = False
        while not eof or pending:
            while not eof and len(pending) < workers * 2:
                arr = read_frame()
                if arr is None:
                    eof = True
                    break
                pending.append(pool.submit(job, arr, idx))
                idx += 1
            if not pending:
                break
            if not write(pending.popleft().result()):
                for f in pending:
                    f.cancel()
                return 'encoder'
            done += 1
            if progress and (done % 5 == 0):
                progress(min(0.99, done / total))
            if cancel and cancel():
                for f in pending:
                    f.cancel()
                return 'cancel'
    notes.extend(sorted(ctx.get('notes', ())))
    return 'ok'


# ---------------------------------------------------------------------------
# Arquivos enviados, prévias e tarefas em segundo plano
# ---------------------------------------------------------------------------

_ROOT = os.path.join(tempfile.gettempdir(), 'verto_efeitos')
_SOURCES = {}
_SOURCES_LOCK = threading.Lock()
SOURCE_TTL = 12 * 3600
PREVIEW_SIDE = 900
THUMB_SIDE = 220


def _cleanup_sources():
    now = time.time()
    with _SOURCES_LOCK:
        old = [k for k, s in _SOURCES.items() if now - s['touched'] > SOURCE_TTL and not s.get('busy')]
        for k in old:
            shutil.rmtree(_SOURCES.pop(k)['dir'], ignore_errors=True)


def _source(sid):
    with _SOURCES_LOCK:
        s = _SOURCES.get(sid or '')
        if s:
            s['touched'] = time.time()
    if not s:
        raise EffectError("Arquivo não encontrado: envie-o de novo.")
    return s


def _downscale(arr, max_side):
    h, w = arr.shape[:2]
    if max(h, w) <= max_side:
        return arr
    from PIL import Image
    k = max_side / max(h, w)
    size = (max(1, round(w * k)), max(1, round(h * k)))
    return np.asarray(_array_to_image(arr).resize(size, Image.LANCZOS))


def _load_base(s):
    """Quadro de referência da prévia (reduzido), guardado em memória."""
    if s.get('base') is not None:
        return s['base']
    kind, path = s['kind'], s['path']
    if kind == 'image':
        from PIL import Image, ImageOps
        _register_heif()
        with Image.open(path) as im:
            im.draft('RGB', (PREVIEW_SIDE * 2, PREVIEW_SIDE * 2))
            arr = _frame_to_array(ImageOps.exif_transpose(im))
    elif kind == 'svg':
        arr, _, _ = _svg_raster(path, max_side=PREVIEW_SIDE)
    else:
        arr = video_frame(path, s['info'], max_side=PREVIEW_SIDE)
    s['base'] = _downscale(arr, PREVIEW_SIDE)
    s['thumb'] = _downscale(s['base'], THUMB_SIDE)
    return s['base']


def _encode_preview(arr, quality=86):
    from PIL import Image
    img = _array_to_image(arr)
    buf = io.BytesIO()
    if arr.shape[2] == 4 and arr[..., 3].min() < 255:
        img.save(buf, 'WEBP', quality=quality)
        mime = 'image/webp'
    else:
        img.convert('RGB').save(buf, 'JPEG', quality=quality)
        mime = 'image/jpeg'
    return f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def register_upload(file_storage):
    if not file_storage or not file_storage.filename:
        raise EffectError("Selecione um arquivo.")
    _cleanup_sources()
    os.makedirs(_ROOT, exist_ok=True)
    sid = secrets.token_urlsafe(12)
    d = tempfile.mkdtemp(prefix='src_', dir=_ROOT)
    _, ext = _split_name(file_storage.filename)
    path = os.path.join(d, 'original' + re.sub(r'[^A-Za-z0-9.]', '', ext)[:12])
    file_storage.save(path)
    try:
        if os.path.getsize(path) == 0:
            raise EffectError("O arquivo enviado está vazio.")
        kind = detect_kind(path, file_storage.filename)
        info = _probe_video(path) if kind in ('video', 'ffimage') else None
        if kind == 'ffimage':
            kind = 'video'  # só o FFmpeg abre: segue o caminho do vídeo (1 quadro)
        if kind == 'video' and not _ffmpeg():
            raise EffectError("Para vídeos é preciso o FFmpeg instalado.")
        s = {'id': sid, 'dir': d, 'path': path, 'name': os.path.basename(file_storage.filename),
             'kind': kind, 'info': info, 'touched': time.time(), 'base': None, 'busy': 0}
        with _SOURCES_LOCK:
            _SOURCES[sid] = s
        base = _load_base(s)
    except Exception:
        with _SOURCES_LOCK:
            _SOURCES.pop(sid, None)
        shutil.rmtree(d, ignore_errors=True)
        raise
    h, w = base.shape[:2]
    meta = {'id': sid, 'name': s['name'], 'kind': kind, 'size': os.path.getsize(path),
            'thumb': _encode_preview(s['thumb'], 80), 'preview': _encode_preview(base)}
    if kind == 'video':
        meta.update(width=info['width'], height=info['height'], duration=info['duration'],
                    fps=round(info['fps'], 2), audio=info['has_audio'])
    else:
        from PIL import Image
        if kind == 'image':
            with Image.open(path) as im:
                meta.update(width=im.width, height=im.height, frames=getattr(im, 'n_frames', 1),
                            format=im.format)
        else:
            meta.update(width=w, height=h)
    return meta


def forget_upload(sid):
    with _SOURCES_LOCK:
        s = _SOURCES.get(sid or '')
        if s and not s.get('busy'):
            _SOURCES.pop(sid, None)
            shutil.rmtree(s['dir'], ignore_errors=True)


def preview(sid, chain):
    s = _source(sid)
    chain = clean_chain(chain)
    base = _load_base(s)
    ctx = {'seed': 0, 'video': False, 'video_source': s['kind'] == 'video'}
    return {'image': _encode_preview(render(base.copy(), chain, ctx)),
            'notes': sorted(ctx.get('notes', ()))}


def thumbnails(sid):
    """Miniatura de cada efeito (com os parâmetros padrão) para a galeria."""
    s = _source(sid)
    _load_base(s)
    thumb = s['thumb']
    if 'faces' not in s:
        s['faces'] = _extras.faces_normalized(s['base'])
    out = {}
    for eff in EFFECTS:
        params = _clean_params(eff['id'], {})
        if eff['id'] == 'silhueta':
            params['modo'] = 'luz'  # a IA fica para quando o usuário escolher
        try:
            out[eff['id']] = _encode_preview(render(thumb.copy(), [(eff['id'], params)],
                                                    {'seed': 0, 'faces_hint': s['faces']}), 78)
        except Exception:
            out[eff['id']] = None
    return out


_JOBS = {}
_JOBS_LOCK = threading.Lock()
_OUTPUTS = {}
# Uma renderização por vez: vídeos já usam todos os núcleos
_RUNNER = ThreadPoolExecutor(max_workers=1, thread_name_prefix='efeitos')


def _register_output(path):
    token = secrets.token_urlsafe(16)
    with _JOBS_LOCK:
        _OUTPUTS[token] = path
    return token


def output_path(token):
    with _JOBS_LOCK:
        path = _OUTPUTS.get(token or '')
    return path if path and os.path.isfile(path) else None


def start_job(sid, chains):
    s = _source(sid)
    cleaned = [clean_chain(c) for c in (chains or [])]
    if not cleaned:
        raise EffectError("Escolha pelo menos um efeito.")
    job_id = uuid.uuid4().hex[:16]
    job = {'id': job_id, 'status': 'queued', 'progress': 0.0, 'current': None,
           'outputs': [], 'errors': [], 'total': len(cleaned), 'cancel': False}
    with _JOBS_LOCK:
        _JOBS[job_id] = job
    with _SOURCES_LOCK:
        s['busy'] += 1
    _RUNNER.submit(_run_job, job, s, cleaned)
    return job_id


def cancel_job(job_id):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id or '')
        if job:
            job['cancel'] = True
    return bool(job)


def _run_job(job, s, chains):
    try:
        job['status'] = 'running'
        dest = _downloads_dir()
        n = len(chains)
        for i, chain in enumerate(chains):
            if job['cancel']:
                job['errors'].append({'label': chain_label(chain), 'error': 'Cancelado.'})
                continue
            job['current'] = chain_label(chain)

            def progress(frac, i=i):
                job['progress'] = (i + max(0.0, min(1.0, frac))) / n

            try:
                seed = 0
                if s['kind'] == 'image':
                    path, notes = process_image(s['path'], s['name'], chain, dest, progress, seed)
                elif s['kind'] == 'svg':
                    path, notes = process_svg(s['path'], s['name'], chain, dest, progress, seed)
                else:
                    path, notes = process_video(s['path'], s['name'], chain, dest, progress, seed,
                                                cancel=lambda: job['cancel'])
                job['outputs'].append({
                    'label': chain_label(chain), 'filename': os.path.basename(path),
                    'size': os.path.getsize(path), 'token': _register_output(path), 'notes': notes,
                })
            except EffectError as e:
                job['errors'].append({'label': chain_label(chain), 'error': str(e)})
            except Exception as e:
                job['errors'].append({'label': chain_label(chain), 'error': f'Erro inesperado: {e}'})
            job['progress'] = (i + 1) / n
        job['status'] = 'done' if job['outputs'] else 'error'
        job['current'] = None
    finally:
        with _SOURCES_LOCK:
            s['busy'] = max(0, s['busy'] - 1)
            s['touched'] = time.time()
        _release_memory()


def _release_memory():
    """Fotos grandes deixam centenas de MB livres no heap, que o glibc não
    devolve ao sistema sozinho; malloc_trim devolve (só existe no Linux)."""
    import gc
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except (OSError, AttributeError):
        pass


def job_status(job_id):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id or '')
        if not job:
            return None
        return {k: v for k, v in job.items() if k != 'cancel'}
