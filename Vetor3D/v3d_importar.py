"""Vetor3D · importação: SVG, DXF, PDF/AI, EPS e imagens viram peças 2D.

Todo formato é reduzido ao mesmo modelo: uma lista de "itens" (preenchimento
ou traço, com cor, camada e regra de preenchimento) feitos de caminhos do ezdxf
(retas e Béziers). Só depois que a caixa do desenho é conhecida as curvas são
achatadas, com uma tolerância proporcional ao tamanho (é isso que define a
alta definição).

Desenhos só de linhas (DXF em preto e branco, SVG/PDF só com contorno) não têm
preenchimento: as linhas são unidas num arranjo plano e cada região fechada
vira uma peça que o usuário pode pintar. Coordenadas finais em mm, y para
cima, centradas na origem.
"""
import math
import os
import re
import shutil
import subprocess
import tempfile

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPolygon, Polygon, Point
from shapely.ops import polygonize_full, unary_union

from ezdxf import path as ezpath
from ezdxf.math import Vec2

EXT_VETOR = ('svg', 'svgz', 'dxf', 'pdf', 'ai', 'eps', 'ps')
EXT_IMAGEM = ('png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tif', 'tiff')
EXTENSOES = EXT_VETOR + EXT_IMAGEM

PX_MM = 25.4 / 96.0
PT_MM = 25.4 / 72.0


class ImportError3D(Exception):
    pass


# ---------------------------------------------------------------------------
# Modelo comum
# ---------------------------------------------------------------------------

class Item:
    """Um elemento do desenho: preenchimento ('fill') ou traço ('line')."""

    __slots__ = ('tipo', 'cor', 'camada', 'regra', 'largura', 'paths', 'nome', 'fundo')

    def __init__(self, tipo, paths, cor=None, camada='0', regra='nonzero', largura=0.0, nome=None):
        self.tipo = tipo
        self.paths = [p for p in paths if len(p)]
        self.cor = cor
        self.camada = camada or '0'
        self.regra = regra
        self.largura = largura
        self.nome = nome
        self.fundo = False


class Desenho:
    def __init__(self, pecas, avisos, origem, sem_cor, largura, altura, info=None):
        self.pecas = pecas          # [{id, nome, camada, cor, geom, furo, ativo, ordem, origem}]
        self.avisos = avisos
        self.origem = origem
        self.sem_cor = sem_cor
        self.largura = largura
        self.altura = altura
        self.info = info or {}


def _hex(rgb):
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb[:3])
    return f'#{r:02x}{g:02x}{b:02x}'


def _quase_branco(cor):
    if not cor:
        return False
    r, g, b = int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)
    return min(r, g, b) >= 245


def _quase_preto(cor):
    if not cor:
        return False
    r, g, b = int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)
    return max(r, g, b) <= 24


# ---------------------------------------------------------------------------
# Leitores
# ---------------------------------------------------------------------------

def _ler_svg(caminho, avisos):
    from svgelements import (SVG, Arc, Close, CubicBezier, Line, Move, Path, QuadraticBezier,
                             Shape, Text)
    try:
        svg = SVG.parse(caminho, reify=True, ppi=96.0)
    except Exception as e:
        raise ImportError3D(f'Não foi possível ler o SVG ({e}).')
    itens = []
    textos = 0
    gradientes = 0
    for el in svg.elements():
        if isinstance(el, Text):
            textos += 1
            continue
        if not isinstance(el, Shape):
            continue
        vals = getattr(el, 'values', {}) or {}
        if vals.get('display') == 'none' or vals.get('visibility') == 'hidden':
            continue
        try:
            # abs() aplica a transformação que sobrou (grupos rotacionados etc.)
            p = abs(Path(el))
        except Exception:
            continue
        subs = []
        cur = None
        start = None
        for seg in p:
            if isinstance(seg, Move):
                if cur is not None and len(cur):
                    subs.append(cur)
                cur = ezpath.Path(Vec2(seg.end.x, seg.end.y))
                start = seg.end
            elif cur is None:
                continue
            elif isinstance(seg, Close):
                cur.close()
            elif isinstance(seg, Line):
                cur.line_to(Vec2(seg.end.x, seg.end.y))
            elif isinstance(seg, QuadraticBezier):
                cur.curve3_to(Vec2(seg.end.x, seg.end.y), Vec2(seg.control.x, seg.control.y))
            elif isinstance(seg, CubicBezier):
                cur.curve4_to(Vec2(seg.end.x, seg.end.y), Vec2(seg.control1.x, seg.control1.y),
                              Vec2(seg.control2.x, seg.control2.y))
            elif isinstance(seg, Arc):
                for c in seg.as_cubic_curves():
                    cur.curve4_to(Vec2(c.end.x, c.end.y), Vec2(c.control1.x, c.control1.y),
                                  Vec2(c.control2.x, c.control2.y))
        if cur is not None and len(cur):
            subs.append(cur)
        if not subs:
            continue
        # SVG: y para baixo e px (96 ppi) -> mm com y para cima
        subs = [s.transform(_matriz_escala(PX_MM, -PX_MM)) for s in subs]
        nome = vals.get('id') or None
        fill_raw = str(vals.get('fill', '')).strip()
        tem_fill = el.fill is not None and el.fill.value is not None
        cor_fill = el.fill.hexrgb if tem_fill else None
        if fill_raw.startswith('url('):
            # Degradê: o 3D precisa de uma cor sólida, o usuário escolhe
            gradientes += 1
            tem_fill = True
            cor_fill = None
        regra = 'evenodd' if str(vals.get('fill-rule', '')).strip() == 'evenodd' else 'nonzero'
        if tem_fill:
            itens.append(Item('fill', subs, cor_fill, vals.get('class') or 'svg', regra, nome=nome))
        tem_stroke = el.stroke is not None and el.stroke.value is not None
        if tem_stroke:
            try:
                w = float(el.implicit_stroke_width or el.stroke_width or 1.0)
            except Exception:
                w = 1.0
            if w > 0:
                itens.append(Item('line', subs, el.stroke.hexrgb, vals.get('class') or 'svg',
                                  largura=w * PX_MM, nome=nome))
    if textos:
        avisos.append(f'{textos} texto(s) do SVG foram ignorados: converta os textos em curvas '
                      '(no Inkscape: Caminho → Objeto para caminho) e envie de novo.')
    if gradientes:
        avisos.append(f'{gradientes} forma(s) com degradê ficaram sem cor: escolha uma cor sólida para elas.')
    return itens


def _matriz_escala(sx, sy):
    from ezdxf.math import Matrix44
    return Matrix44.scale(sx, sy, 1)


_INSUNITS_MM = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 8: 0.0000254, 9: 0.0254, 10: 914.4,
                13: 0.001, 14: 100.0}


def _ler_dxf(caminho, avisos):
    import ezdxf
    from ezdxf import colors as ezcolors
    from ezdxf import recover
    from ezdxf.disassemble import recursive_decompose
    try:
        doc, auditor = recover.readfile(caminho)
    except Exception as e:
        raise ImportError3D(f'Não foi possível ler o DXF ({e}).')
    unidades = doc.header.get('$INSUNITS', 0)
    k = _INSUNITS_MM.get(unidades, 1.0)
    if unidades not in _INSUNITS_MM:
        avisos.append('O DXF não informa a unidade: considerado em milímetros.')
    msp = doc.modelspace()

    def cor_de(e):
        try:
            if e.dxf.hasattr('true_color'):
                return _hex(ezcolors.int2rgb(e.dxf.true_color))
        except Exception:
            pass
        aci = e.dxf.get('color', 256)
        camada = e.dxf.get('layer', '0')
        if aci in (256, 0):
            try:
                lay = doc.layers.get(camada)
                if lay.dxf.hasattr('true_color'):
                    return _hex(ezcolors.int2rgb(lay.dxf.true_color))
                aci = abs(lay.color)
            except Exception:
                aci = 7
        if aci == 7 or aci <= 0 or aci > 255:
            return None   # preto/branco: "sem cor"
        return _hex(ezcolors.aci2rgb(aci))

    itens = []
    ignorados = {}
    textos = 0
    escala = _matriz_escala(k, k)
    for e in recursive_decompose(msp):
        t = e.dxftype()
        camada = e.dxf.get('layer', '0')
        try:
            if t == 'HATCH' or t == 'MPOLYGON':
                if t == 'HATCH' and not e.dxf.get('solid_fill', 1):
                    # hachura de padrão (linhas): só o contorno interessa
                    pass
                paths = list(ezpath.from_hatch(e))
                regra = 'evenodd'
                itens.append(Item('fill', [p.transform(escala) for p in paths], cor_de(e), camada, regra))
                continue
            if t in ('SOLID', 'TRACE', '3DFACE'):
                p = ezpath.make_path(e)
                itens.append(Item('fill', [p.transform(escala)], cor_de(e), camada))
                continue
            if t in ('TEXT', 'MTEXT', 'ATTRIB'):
                from ezdxf.addons import text2path
                paths = text2path.make_paths_from_entity(e)
                if paths:
                    textos += 1
                    itens.append(Item('fill', [p.transform(escala) for p in paths], cor_de(e), camada, 'nonzero'))
                continue
            if t in ('LINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'LWPOLYLINE', 'POLYLINE', 'SPLINE', 'HELIX'):
                p = ezpath.make_path(e)
                if len(p):
                    subs = list(p.sub_paths())
                    itens.append(Item('line', [s.transform(escala) for s in subs], cor_de(e), camada,
                                      largura=0.0))
                continue
        except Exception:
            pass
        ignorados[t] = ignorados.get(t, 0) + 1
    ign = {k_: v for k_, v in ignorados.items() if k_ not in ('POINT', 'DIMENSION', 'VIEWPORT', 'INSERT')}
    if ign:
        lista = ', '.join(f'{v} {k_}' for k_, v in sorted(ign.items()))
        avisos.append(f'Entidades ignoradas: {lista}.')
    if textos:
        avisos.append(f'{textos} texto(s) do DXF viraram curvas com a fonte disponível nesta máquina.')
    return itens


def _ler_pdf(caminho, avisos, pagina=0):
    import pymupdf
    try:
        doc = pymupdf.open(caminho)
    except Exception as e:
        raise ImportError3D(f'Não foi possível abrir o arquivo ({e}). Se for um .ai antigo, '
                            'salve-o no Illustrator com "Criar arquivo compatível com PDF".')
    if doc.needs_pass:
        raise ImportError3D('O PDF está protegido por senha. Desbloqueie no app PDFs primeiro.')
    if not len(doc):
        raise ImportError3D('O arquivo não tem nenhuma página.')
    if len(doc) > 1:
        avisos.append(f'O arquivo tem {len(doc)} páginas: foi usada a página {pagina + 1}.')
    page = doc[min(pagina, len(doc) - 1)]
    x0, y0 = page.rect.x0, page.rect.y0
    H = page.rect.height

    def V(pt):
        return Vec2((pt.x - x0) * PT_MM, (H - (pt.y - y0)) * PT_MM)

    itens = []
    for d in page.get_drawings():
        paths = []
        cur = None
        path = None
        for item in d['items']:
            op = item[0]
            if op in ('l', 'c'):
                a = item[1]
                if path is None or cur is None or abs(cur.x - a.x) > 1e-3 or abs(cur.y - a.y) > 1e-3:
                    path = ezpath.Path(V(a))
                    paths.append(path)
                if op == 'l':
                    path.line_to(V(item[2]))
                    cur = item[2]
                else:
                    path.curve4_to(V(item[4]), V(item[2]), V(item[3]))
                    cur = item[4]
            elif op == 're':
                r = item[1]
                p = ezpath.Path(V(r.tl))
                for q in (r.tr, r.br, r.bl):
                    p.line_to(V(q))
                p.close()
                paths.append(p)
                path, cur = None, None
            elif op == 'qu':
                q = item[1]
                p = ezpath.Path(V(q.ul))
                for pt in (q.ur, q.lr, q.ll):
                    p.line_to(V(pt))
                p.close()
                paths.append(p)
                path, cur = None, None
        if d.get('closePath') and path is not None and len(path):
            path.close()
        paths = [p for p in paths if len(p)]
        if not paths:
            continue
        tipo = d.get('type') or ''
        layer = d.get('layer') or 'pdf'
        if 'f' in tipo and d.get('fill') is not None:
            regra = 'evenodd' if d.get('even_odd') else 'nonzero'
            itens.append(Item('fill', paths, _hex([c * 255 for c in d['fill']]), layer, regra))
        if 's' in tipo and d.get('color') is not None:
            w = (d.get('width') or 1.0) * PT_MM
            itens.append(Item('line', paths, _hex([c * 255 for c in d['color']]), layer, largura=w))
    doc.close()
    if not itens:
        raise ImportError3D('O arquivo não tem vetores (pode ser uma imagem dentro do PDF). '
                            'Envie a imagem para ser vetorizada.')
    return itens


def _ler_eps(caminho, avisos, trabalho):
    gs = shutil.which('gs') or shutil.which('gswin64c') or shutil.which('gswin32c')
    if not gs:
        raise ImportError3D('Para abrir EPS/PS é preciso o Ghostscript (gs) instalado.')
    saida = os.path.join(trabalho, 'eps.pdf')
    r = subprocess.run([gs, '-q', '-dNOPAUSE', '-dBATCH', '-dSAFER', '-dEPSCrop', '-sDEVICE=pdfwrite',
                        f'-sOutputFile={saida}', caminho], capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not os.path.exists(saida):
        raise ImportError3D('O Ghostscript não conseguiu ler o EPS: ' + (r.stderr or '').strip()[:200])
    return _ler_pdf(saida, avisos)


def _ler_imagem(caminho, avisos, opts):
    from Conversor import conversor_engine as conv
    cores = int(opts.get('cores_imagem') or 8)
    try:
        tr = conv.trace_image(caminho, {'trace_mode': 'color', 'colors': max(2, min(16, cores)),
                                        'turdsize': opts.get('ruido', 4)})
    except conv.ConversionError as e:
        raise ImportError3D(str(e))
    k = 25.4 / (tr.dpi or 96)
    itens = []
    for camada in tr.layers:
        if camada['kind'] != 'fill':
            continue
        paths = []
        for sub in camada['curves']:
            p = None
            for cmd in sub:
                if cmd[0] == 'M':
                    p = ezpath.Path(Vec2(cmd[1][0] * k, -cmd[1][1] * k))
                elif cmd[0] == 'L' and p is not None:
                    p.line_to(Vec2(cmd[1][0] * k, -cmd[1][1] * k))
                elif cmd[0] == 'C' and p is not None:
                    c1, c2, e = cmd[1], cmd[2], cmd[3]
                    p.curve4_to(Vec2(e[0] * k, -e[1] * k), Vec2(c1[0] * k, -c1[1] * k), Vec2(c2[0] * k, -c2[1] * k))
            if p is not None and len(p):
                p.close()
                paths.append(p)
        if paths:
            itens.append(Item('fill', paths, _hex(camada['color']), camada['name'], 'evenodd'))
    avisos.append(f'Imagem vetorizada em {len(itens)} cor(es). Para curvas perfeitas, prefira o vetor original (SVG/DXF/PDF).')
    return itens


# ---------------------------------------------------------------------------
# Achatamento e geometria 2D
# ---------------------------------------------------------------------------

def _caixa(itens):
    xs, ys = [], []
    for it in itens:
        for p in it.paths:
            bb = ezpath.bbox([p], fast=False)
            if bb.has_data:
                xs += [bb.extmin.x, bb.extmax.x]
                ys += [bb.extmin.y, bb.extmax.y]
    if not xs:
        raise ImportError3D('Nenhuma forma foi encontrada no arquivo.')
    return min(xs), min(ys), max(xs), max(ys)


def _pontos(path, tol):
    pts = np.array([(v.x, v.y) for v in path.flattening(tol, segments=4)], dtype=np.float64)
    if len(pts) > 1:
        d = np.r_[True, np.any(np.abs(np.diff(pts, axis=0)) > tol * 1e-3, axis=1)]
        pts = pts[d]
    return pts


def _winding(anel, pts):
    """Número de voltas de um anel fechado (N,2) em torno de cada ponto (M,2)."""
    a = anel
    b = np.roll(anel, -1, axis=0)
    px = pts[:, 0][:, None]
    py = pts[:, 1][:, None]
    ax, ay, bx, by = a[:, 0][None], a[:, 1][None], b[:, 0][None], b[:, 1][None]
    lado = (bx - ax) * (py - ay) - (px - ax) * (by - ay)
    sobe = (ay <= py) & (by > py) & (lado > 0)
    desce = (ay > py) & (by <= py) & (lado < 0)
    return sobe.sum(axis=1) - desce.sum(axis=1)


def _preencher(aneis, regra):
    """Região preenchida por um conjunto de anéis com regra nonzero/evenodd
    (a mesma semântica do SVG/PDF), inclusive com anéis que se cruzam."""
    aneis = [a for a in aneis if len(a) >= 3]
    if not aneis:
        return None
    if len(aneis) == 1:
        g = shapely.make_valid(Polygon(aneis[0]))
        return _so_poligonos(g)
    linhas = [LineString(np.vstack([a, a[:1]])) for a in aneis]
    escala = max(float(np.ptp(np.vstack(aneis), axis=0).max()), 1e-9)
    faces, _, _, _ = polygonize_full(shapely.union_all(linhas, grid_size=escala * 1e-7))
    faces = [f for f in shapely.get_parts(faces) if f.area > 0]
    if not faces:
        return None
    pts = np.array([f.representative_point().coords[0] for f in faces])
    w = np.zeros(len(faces), dtype=np.int64)
    for a in aneis:
        mn, mx = a.min(axis=0), a.max(axis=0)
        dentro = (pts[:, 0] >= mn[0]) & (pts[:, 0] <= mx[0]) & (pts[:, 1] >= mn[1]) & (pts[:, 1] <= mx[1])
        if dentro.any():
            w[dentro] += _winding(a, pts[dentro])
    cheio = (w % 2 == 1) if regra == 'evenodd' else (w != 0)
    sel = [f for f, c in zip(faces, cheio) if c]
    if not sel:
        return None
    return _so_poligonos(unary_union(sel))


def _so_poligonos(g):
    if g is None or g.is_empty:
        return None
    partes = [p for p in shapely.get_parts(g) if isinstance(p, Polygon) and p.area > 0]
    if not partes:
        # coleções (make_valid) podem ter polígonos aninhados
        partes = [p for p in shapely.get_parts(shapely.get_parts(g)) if isinstance(p, Polygon) and p.area > 0]
    if not partes:
        return None
    return MultiPolygon(partes) if len(partes) > 1 else MultiPolygon([partes[0]])


def _soldar_pontas(linhas, gap):
    """Une pontas de linhas abertas que quase se tocam (desenho de CAD costuma
    ter frestas minúsculas que impediriam a região de fechar)."""
    if gap <= 0 or not linhas:
        return linhas
    from scipy.spatial import cKDTree
    pontas = []
    for i, l in enumerate(linhas):
        if len(l) >= 2 and np.linalg.norm(l[0] - l[-1]) > gap:
            pontas.append((i, 0))
            pontas.append((i, -1))
    if len(pontas) < 2:
        return linhas
    xy = np.array([linhas[i][j] for i, j in pontas])
    arvore = cKDTree(xy)
    pares = arvore.query_pairs(gap)
    pai = list(range(len(pontas)))

    def raiz(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a

    for a, b in pares:
        pai[raiz(a)] = raiz(b)
    grupos = {}
    for idx in range(len(pontas)):
        grupos.setdefault(raiz(idx), []).append(idx)
    linhas = [l.copy() for l in linhas]
    sozinhas = []
    for membros in grupos.values():
        if len(membros) < 2:
            sozinhas.append(membros[0])
            continue
        c = xy[membros].mean(axis=0)
        for m in membros:
            i, j = pontas[m]
            linhas[i][j] = c
    if sozinhas:
        # Junção em "T" com fresta: a ponta encosta no meio de outra linha
        geoms = [LineString(l) for l in linhas]
        arvore = shapely.STRtree(geoms)
        for m in sozinhas:
            i, j = pontas[m]
            pt = Point(linhas[i][j])
            for k in arvore.query(pt.buffer(gap)):
                if k == i:
                    continue
                d = geoms[k].distance(pt)
                if 0 < d <= gap:
                    alvo = geoms[k].interpolate(geoms[k].project(pt))
                    linhas[i][j] = (alvo.x, alvo.y)
                    break
    return linhas


def _regioes(linhas_info, gap, avisos):
    """Arranjo plano das linhas soltas -> faces fechadas com nível de
    aninhamento (par = sólido, ímpar = furo) e cor/camada por votação das
    linhas que formam a borda."""
    if not linhas_info:
        return []
    linhas = _soldar_pontas([l for l, _, _ in linhas_info], gap)
    geoms = []
    tags = []
    for l, (_, cor, camada) in zip(linhas, linhas_info):
        if len(l) >= 2:
            geoms.append(LineString(l))
            tags.append((cor, camada))
    if not geoms:
        return []
    # A grade de precisão faz pontas que diferem por erro de arredondamento
    # (1e-15) se encontrarem na hora de cortar as linhas nos cruzamentos
    noded = shapely.union_all(geoms, grid_size=gap / 20)
    faces, cortes, pontas, invalidas = polygonize_full(noded)
    faces = [f for f in shapely.get_parts(faces) if f.area > gap * gap]
    n_pontas = len(shapely.get_parts(pontas))
    if n_pontas:
        avisos.append(f'{n_pontas} linha(s) não fecham nenhuma região e foram ignoradas.')
    if not faces:
        return []
    arvore = shapely.STRtree(geoms)
    cheias = [Polygon(f.exterior) for f in faces]
    arv_cheias = shapely.STRtree(cheias)
    saida = []
    for i, f in enumerate(faces):
        rp = f.representative_point()
        cand = arv_cheias.query(rp, predicate='within')
        nivel = sum(1 for j in cand if j != i)
        # votação da cor: pontos ao longo da borda externa
        ext = f.exterior
        votos = {}
        for t in np.linspace(0, 1, 9)[:-1]:
            pt = ext.interpolate(t, normalized=True)
            idx = arvore.nearest(pt)
            chave = tags[int(idx)]
            votos[chave] = votos.get(chave, 0) + 1
        cor, camada = max(votos.items(), key=lambda kv: kv[1])[0]
        saida.append({'geom': MultiPolygon([f]), 'nivel': nivel, 'cor': cor, 'camada': camada})
    return saida


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def _de_pecas_prontas(pecas_in, avisos, origem, info):
    """Peças que já chegam como polígonos em mm (imagem em modo desenho)."""
    from shapely import affinity
    x0, y0, x1, y1 = shapely.union_all([p['geom'].envelope for p in pecas_in]).bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    pecas = []
    for i, p in enumerate(pecas_in):
        g = _so_poligonos(affinity.translate(p['geom'], -cx, -cy))
        if g is None:
            continue
        pecas.append({'id': len(pecas) + 1, 'nome': p['nome'], 'camada': p['camada'], 'cor': p['cor'], 'geom': g,
                      'furo': False, 'ativo': True, 'ordem': len(pecas), 'origem': p['origem'],
                      'papel': p.get('papel')})
    if not pecas:
        raise ImportError3D('Nenhuma forma foi encontrada na imagem.')
    sem_cor = all(p['cor'] is None for p in pecas if p.get('papel') not in ('tinta', 'volume'))
    if sem_cor:
        avisos.insert(0, 'As regiões do desenho não têm cor: clique nelas para pintar (ou use "Colorir sem cor").')
    return Desenho(pecas, avisos, origem, sem_cor, x1 - x0, y1 - y0, dict(info, itens=len(pecas)))


def importar(caminho, tol_frac=1 / 9000, opts=None, trabalho=None):
    """Lê o arquivo e devolve um Desenho com as peças em mm.

    opts: tracos ('auto'|'area'|'regioes'), gap (fração da diagonal para soldar
    pontas), cores_imagem (int), pagina (int)."""
    opts = opts or {}
    ext = os.path.splitext(caminho)[1].lower().lstrip('.')
    avisos = []
    trabalho = trabalho or tempfile.mkdtemp(prefix='v3d_imp_')
    if ext in ('svg', 'svgz'):
        itens = _ler_svg(caminho, avisos)
        origem = 'svg'
    elif ext == 'dxf':
        itens = _ler_dxf(caminho, avisos)
        origem = 'dxf'
    elif ext in ('pdf', 'ai'):
        itens = _ler_pdf(caminho, avisos, int(opts.get('pagina') or 0))
        origem = ext
    elif ext in ('eps', 'ps'):
        itens = _ler_eps(caminho, avisos, trabalho)
        origem = 'eps'
    elif ext in EXT_IMAGEM:
        from Vetor3D import v3d_imagem
        try:
            res = v3d_imagem.ler(caminho, opts, trabalho)
        except v3d_imagem.ImagemError as e:
            raise ImportError3D(str(e))
        avisos.extend(res['avisos'])
        origem = 'imagem'
        if res['modo'] in ('desenho', 'volume'):
            return _de_pecas_prontas(res['pecas'], avisos, origem, {'modo_imagem': res['modo']})
        itens = _ler_imagem(res['vetorizar'], avisos, opts)
    else:
        raise ImportError3D(f'Formato .{ext} não suportado. Use SVG, DXF, PDF, AI, EPS ou imagem.')
    itens = [it for it in itens if it.paths]
    if not itens:
        raise ImportError3D('Nenhuma forma foi encontrada no arquivo.')

    x0, y0, x1, y1 = _caixa(itens)
    diag = math.hypot(x1 - x0, y1 - y0) or 1.0
    tol = diag * float(tol_frac)
    gap = diag * float(opts.get('gap', 1 / 2000))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    tem_fill = any(it.tipo == 'fill' for it in itens)
    modo_tracos = opts.get('tracos', 'auto')
    if modo_tracos == 'auto':
        # Desenho só de linhas (CAD, line-art): as linhas delimitam regiões.
        # Com preenchimentos, o traço é parte da arte: vira faixa com a largura dele.
        # No DXF não existe "largura de traço": linha é sempre contorno de região.
        modo_tracos = 'regioes' if (origem == 'dxf' or not tem_fill) else 'area'

    pecas = []
    linhas_regiao = []
    ordem = 0
    for it in itens:
        if it.tipo == 'fill':
            aneis = []
            for p in it.paths:
                pts = _pontos(p, tol)
                if len(pts) >= 3:
                    aneis.append(pts - (cx, cy))
            g = _preencher(aneis, it.regra)
            if g is None:
                continue
            pecas.append({'nome': it.nome, 'camada': it.camada, 'cor': it.cor, 'geom': g,
                          'furo': False, 'ativo': True, 'ordem': ordem, 'origem': 'preenchimento'})
            ordem += 1
        else:
            polis = []
            for p in it.paths:
                pts = _pontos(p, tol)
                if len(pts) >= 2:
                    if p.is_closed and np.linalg.norm(pts[0] - pts[-1]) > tol * 1e-3:
                        pts = np.vstack([pts, pts[:1]])
                    polis.append(pts - (cx, cy))
            if modo_tracos == 'regioes':
                for pts in polis:
                    linhas_regiao.append((pts, it.cor, it.camada))
            else:
                w = it.largura if it.largura > 0 else diag / 400
                partes = [LineString(pts).buffer(w / 2, quad_segs=8, cap_style='round', join_style='round')
                          for pts in polis]
                g = _so_poligonos(unary_union(partes)) if partes else None
                if g is None:
                    continue
                pecas.append({'nome': it.nome, 'camada': it.camada, 'cor': it.cor, 'geom': g,
                              'furo': False, 'ativo': True, 'ordem': ordem, 'origem': 'traco'})
                ordem += 1

    regs = _regioes(linhas_regiao, gap, avisos)
    if regs:
        # As regiões ficam por baixo dos preenchimentos (hachuras do DXF, por exemplo)
        for p in pecas:
            p['ordem'] += len(regs)
        regs.sort(key=lambda r: -r['geom'].area)
        for i, r in enumerate(regs):
            # A cor de um traço preto/branco é "tinta de desenho", não a cor da peça
            cor = None if (r['cor'] is None or _quase_branco(r['cor']) or _quase_preto(r['cor'])) else r['cor']
            pecas.insert(i, {'nome': None, 'camada': r['camada'], 'cor': cor, 'geom': r['geom'],
                             'furo': r['nivel'] % 2 == 1, 'ativo': True, 'ordem': i, 'origem': 'regiao'})

    if not pecas:
        raise ImportError3D('As formas do arquivo não fecham nenhuma área (linhas abertas). '
                            'Feche os contornos no editor ou envie com preenchimento.')

    # Fundo: primeira forma branca cobrindo quase todo o desenho (retângulo de
    # fundo de SVG/PDF). Fica desligada, mas o usuário pode ligar de volta.
    area_total = (x1 - x0) * (y1 - y0)
    for p in sorted(pecas, key=lambda q: q['ordem'])[:2]:
        if p['origem'] == 'preenchimento' and _quase_branco(p['cor']) and p['geom'].envelope.area >= area_total * 0.95 \
                and len(pecas) > 1:
            p['ativo'] = False
            p['nome'] = 'Fundo'
            avisos.append('O fundo branco do desenho foi desligado (pode ser ligado na lista de peças).')
            break

    for i, p in enumerate(sorted(pecas, key=lambda q: q['ordem'])):
        p['ordem'] = i
        p['id'] = i + 1
        if not p['nome']:
            p['nome'] = f"{'Região' if p['origem'] == 'regiao' else 'Forma'} {i + 1}"
    pecas.sort(key=lambda q: q['ordem'])

    sem_cor = all(p['cor'] is None for p in pecas if p['ativo'])
    if sem_cor:
        avisos.insert(0, 'Este desenho não tem cores (preto e branco): clique nas regiões para pintar.')
    elif any(p['cor'] is None for p in pecas if p['ativo']):
        avisos.append('Algumas peças estão sem cor: escolha uma cor para elas.')
    info = {'itens': len(itens), 'tolerancia_mm': tol, 'modo_tracos': modo_tracos}
    return Desenho(pecas, avisos, origem, sem_cor, x1 - x0, y1 - y0, info)
