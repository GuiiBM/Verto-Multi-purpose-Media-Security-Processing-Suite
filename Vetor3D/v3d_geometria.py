"""Vetor3D · geometria: peças 2D viram sólidos 3D (chanfro ou inflado).

Os dois estilos usam a mesma construção, que aguenta qualquer forma:

1. parede vertical a partir do contorno exato;
2. "curvas de nível" do perfil: a forma é encolhida (buffer negativo) em
   degraus e cada degrau sobe um pouco. A faixa entre dois degraus é
   triangulada (earcut) e cada vértice recebe a altura do seu degrau. Partes
   finas que somem num degrau ficam com o topo naquele nível, e formas que se
   dividem continuam subindo separadas, sem auto-interseção;
3. tampa no último degrau e fundo plano (ou espelhado, no inflado "balão").

Chanfro: degraus até a largura do chanfro (perfil redondo ou reto), limitada
para a forma não mudar de topologia (o topo fica plano em toda a peça).
Inflado: degraus até o raio inscrito da forma, perfil de quarto de círculo:
partes largas estufam mais, partes finas menos, como um ícone 3D.

Tudo em mm. O desenho fica no plano XY e a espessura cresce em +Z (de frente
para a câmera, que é como o glTF/three.js mostram por padrão).
"""
import math

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

import mapbox_earcut as earcut


class GeometriaError(Exception):
    pass


# ---------------------------------------------------------------------------
# Triangulação
# ---------------------------------------------------------------------------

def _aneis(poly):
    """Anéis de um polígono (sem o ponto repetido de fechamento)."""
    ext = np.asarray(poly.exterior.coords)[:-1]
    ints = [np.asarray(r.coords)[:-1] for r in poly.interiors]
    return [ext] + ints


def _earcut(poly):
    """Triângulos (índices) de um polígono com furos + os vértices 2D.

    Usa a triangulação de Delaunay restrita do GEOS (sem pontos novos, respeita
    contornos e furos, triângulos bem proporcionados e robusta com pontos
    colineares). Se ela falhar, cai no earcut."""
    aneis = [a for a in _aneis(poly) if len(a) >= 3]
    if not aneis:
        return np.zeros((0, 2)), np.zeros((0, 3), dtype=np.int64)
    verts = np.vstack(aneis).astype(np.float64)
    try:
        tri = shapely.constrained_delaunay_triangles(poly)
        n = len(tri.geoms)
        if n:
            c = shapely.get_coordinates(tri).reshape(n, 4, 2)[:, :3].reshape(-1, 2)
            indice = {}
            for i, xy in enumerate(map(tuple, verts)):
                indice.setdefault(xy, i)
            tris = np.fromiter((indice[xy] for xy in map(tuple, c)), dtype=np.int64, count=len(c)).reshape(-1, 3)
            return verts, tris
    except (KeyError, shapely.errors.GEOSException, ValueError):
        pass
    fins = np.cumsum([len(a) for a in aneis]).astype(np.uint32)
    idx = earcut.triangulate_float64(verts, fins)
    tris = np.asarray(idx, dtype=np.int64).reshape(-1, 3)
    return verts, tris


def _orientar(verts2, tris, para_cima=True):
    """Garante a ordem anti-horária vista de cima (normal +Z) ou de baixo."""
    if not len(tris):
        return tris
    a, b, c = verts2[tris[:, 0]], verts2[tris[:, 1]], verts2[tris[:, 2]]
    cruz = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    inv = cruz < 0 if para_cima else cruz > 0
    tris = tris.copy()
    tris[inv] = tris[inv][:, [0, 2, 1]]
    return tris


class _Malha:
    """Acumula triângulos com coordenadas 3D; os vértices são soldados no fim
    (as faixas vizinhas compartilham exatamente as mesmas coordenadas)."""

    def __init__(self):
        self.v = []
        self.f = []
        self.n = 0

    def add(self, verts3, tris):
        if not len(tris):
            return
        self.v.append(np.asarray(verts3, dtype=np.float64))
        self.f.append(np.asarray(tris, dtype=np.int64) + self.n)
        self.n += len(verts3)

    def resultado(self):
        if not self.f:
            return np.zeros((0, 3), np.float64), np.zeros((0, 3), np.int64)
        v = np.vstack(self.v)
        f = np.vstack(self.f)
        # soldagem exata (as coordenadas compartilhadas são cópias idênticas)
        _, inv = np.unique(np.round(v, 9), axis=0, return_inverse=True)
        uniq_idx = np.zeros(inv.max() + 1, dtype=np.int64)
        uniq_idx[inv] = np.arange(len(v))
        v2 = v[uniq_idx]
        f2 = inv.reshape(-1)[f]
        ok = (f2[:, 0] != f2[:, 1]) & (f2[:, 1] != f2[:, 2]) & (f2[:, 0] != f2[:, 2])
        f2 = f2[ok]
        return v2, _fechar_frestas(f2)


def _fechar_frestas(f):
    """O earcut descarta triângulos de área zero no plano (um vértice do degrau
    seguinte alinhado com a aresta do degrau atual). Em 3D eles não são nulos:
    viram frestas verticais finíssimas. Aqui as arestas sem par formam laços,
    que são preenchidos no sentido oposto (malha volta a ser fechada)."""
    if not len(f):
        return f
    dirigidas = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    chave = dirigidas[:, 0] * (f.max() + 1) + dirigidas[:, 1]
    reversa = dirigidas[:, 1] * (f.max() + 1) + dirigidas[:, 0]
    sem_par = ~np.isin(chave, reversa)
    if not sem_par.any():
        return f
    # o preenchimento percorre cada aresta solta ao contrário (b -> a)
    prox = {}
    for a, b in dirigidas[sem_par]:
        prox.setdefault(int(b), []).append(int(a))
    novos = []
    while prox:
        inicio = next(iter(prox))
        laco = [inicio]
        atual = inicio
        while True:
            lista = prox.get(atual)
            if not lista:
                break
            seguinte = lista.pop()
            if not lista:
                del prox[atual]
            if seguinte == inicio:
                break
            laco.append(seguinte)
            atual = seguinte
            if len(laco) > 100000:
                break
        if len(laco) >= 3:
            for i in range(1, len(laco) - 1):
                novos.append((laco[0], laco[i], laco[i + 1]))
    if novos:
        f = np.vstack([f, np.asarray(novos, dtype=np.int64)])
    return f


def _tampa(m, poly, z, para_cima):
    verts, tris = _earcut(poly)
    if not len(tris):
        return
    tris = _orientar(verts, tris, para_cima)
    m.add(np.column_stack([verts, np.full(len(verts), z)]), tris)


def _parede(m, poly, z0, z1):
    if z1 - z0 <= 1e-9:
        return
    for anel in _aneis(poly):
        n = len(anel)
        if n < 3:
            continue
        a0 = np.column_stack([anel, np.full(n, z0)])
        a1 = np.column_stack([anel, np.full(n, z1)])
        verts = np.vstack([a0, a1])
        i = np.arange(n)
        j = (i + 1) % n
        tris = np.vstack([np.column_stack([i, j, j + n]), np.column_stack([i, j + n, i + n])])
        m.add(verts, tris)


def _chave(xy):
    return (round(float(xy[0]), 9), round(float(xy[1]), 9))


def _costurar(m, faixa, internos, z_ext, z_int, para_cima):
    """Faixa em anel (um contorno de cada degrau): costura os dois anéis em
    tiras radiais. Cada vértice do anel de dentro é casado com o ponto mais
    próximo do anel de fora (as curvas de nível são offsets, então esse
    casamento anda sempre para a frente). Devolve False se não der certo
    (aí a faixa vai para o earcut)."""
    from shapely.geometry import LineString
    fora = np.asarray(faixa.exterior.coords)[:-1]
    dentro = np.asarray(faixa.interiors[0].coords)[:-1]
    if len(fora) < 3 or len(dentro) < 3:
        return False
    nivel_fora = sum(_chave(xy) in internos for xy in fora[:8]) > min(8, len(fora)) / 2
    nivel_dentro = sum(_chave(xy) in internos for xy in dentro[:8]) > min(8, len(dentro)) / 2
    if nivel_fora == nivel_dentro:
        return False
    # os dois no mesmo sentido (anti-horário)
    if not bool(shapely.is_ccw(shapely.linearrings(fora))):
        fora = fora[::-1]
    if not bool(shapely.is_ccw(shapely.linearrings(dentro))):
        dentro = dentro[::-1]
    linha = LineString(np.vstack([fora, fora[:1]]))
    seg = np.linalg.norm(np.diff(np.vstack([fora, fora[:1]]), axis=0), axis=1)
    total = seg.sum()
    if total <= 0:
        return False
    tf = np.r_[0.0, np.cumsum(seg)[:-1]] / total
    td = shapely.line_locate_point(linha, shapely.points(dentro), normalized=True)
    # começa no vértice de dentro mais perto do início do anel de fora
    k = int(np.argmin(np.minimum(td, 1 - td)))
    dentro = np.roll(dentro, -k, axis=0)
    td = np.roll(td, -k)
    if td[0] > 0.5:
        td[0] -= 1.0
    # desenrola e força monotonia (offset: o casamento só anda para a frente)
    for i in range(1, len(td)):
        while td[i] < td[i - 1] - 0.5:
            td[i] += 1.0
    td = np.maximum.accumulate(td)
    if td[-1] - td[0] > 1.0 + 1e-6:
        return False
    n, mm = len(fora), len(dentro)
    a = np.vstack([fora, fora[:1]])
    b = np.vstack([dentro, dentro[:1]])
    ta = np.r_[tf, 1.0]
    tb = np.r_[td, td[0] + 1.0]
    # anel de fora também começa no mesmo ponto (rotação pelo parâmetro de td[0])
    i = int(np.searchsorted(ta, td[0] % 1.0, side='right')) - 1
    i = max(0, min(n - 1, i))
    ordem_a = [(i + s) % n for s in range(n + 1)]
    ta_rot = np.array([tf[x] for x in ordem_a[:-1]] + [tf[ordem_a[0]]])
    base = ta_rot[0]
    ta_rot = (ta_rot - base) % 1.0
    ta_rot[-1] = 1.0
    tb_rot = tb - tb[0]
    pa = a[ordem_a]
    tris = []
    ia = ib = 0
    while ia < n or ib < mm:
        avanca_a = ib >= mm or (ia < n and ta_rot[ia + 1] <= tb_rot[ib + 1])
        if avanca_a:
            tris.append((('a', ia), ('a', ia + 1), ('b', ib)))
            ia += 1
        else:
            tris.append((('a', ia), ('b', ib + 1), ('b', ib)))
            ib += 1
    pts = {'a': pa, 'b': b}
    t2 = np.array([[pts[r][i_] for r, i_ in t] for t in tris])
    area = (t2[:, 1, 0] - t2[:, 0, 0]) * (t2[:, 2, 1] - t2[:, 0, 1]) - \
           (t2[:, 1, 1] - t2[:, 0, 1]) * (t2[:, 2, 0] - t2[:, 0, 0])
    escala = max(total * total * 1e-12, 1e-18)
    if (area < -escala).any():
        return False
    za = z_int if nivel_fora else z_ext
    zb = z_int if nivel_dentro else z_ext
    verts = np.vstack([np.column_stack([pa, np.full(len(pa), za)]),
                       np.column_stack([b, np.full(len(b), zb)])])
    off = len(pa)
    idx = np.array([[i_ if r == 'a' else i_ + off for r, i_ in t] for t in tris], dtype=np.int64)
    if not para_cima:
        idx = idx[:, [0, 2, 1]]
    m.add(verts, idx)
    return True


def _faixa(m, externo, interno, z_ext, z_int, para_cima=True):
    """Superfície entre o nível 'externo' (altura z_ext) e o 'interno' (z_int),
    que está contido nele. Partes do externo sem interno viram tampa plana."""
    if interno is None or interno.is_empty:
        band = externo
    else:
        band = externo.difference(interno)
    if band.is_empty:
        return
    internos = set()
    if interno is not None and not interno.is_empty:
        for p in shapely.get_parts(interno):
            for anel in _aneis(p):
                for xy in anel:
                    internos.add(_chave(xy))
    for p in shapely.get_parts(band):
        if not isinstance(p, Polygon) or p.area <= 0:
            continue
        if len(p.interiors) == 1 and internos and _costurar(m, p, internos, z_ext, z_int, para_cima):
            continue
        verts, tris = _earcut(p)
        if not len(tris):
            continue
        tris = _orientar(verts, tris, para_cima)
        z = np.array([z_int if _chave(xy) in internos else z_ext for xy in verts])
        m.add(np.column_stack([verts, z]), tris)


# ---------------------------------------------------------------------------
# Perfis
# ---------------------------------------------------------------------------

def _topologia(g):
    partes = [p for p in shapely.get_parts(g) if isinstance(p, Polygon) and not p.is_empty]
    return len(partes), sum(len(p.interiors) for p in partes)


def _encolher(poly, d, arco):
    if d <= 0:
        return poly
    return poly.buffer(-d, quad_segs=arco, join_style='round')


def raio_seguro(poly, d_max, arco=6):
    """Maior encolhimento (<= d_max) que mantém a mesma topologia da forma
    (nenhuma parte some nem se divide, nenhum furo fecha)."""
    alvo = _topologia(poly)
    g = _encolher(poly, d_max, arco)
    if not g.is_empty and _topologia(g) == alvo:
        return d_max
    lo, hi = 0.0, d_max
    for _ in range(12):
        mid = (lo + hi) / 2
        g = _encolher(poly, mid, arco)
        if not g.is_empty and _topologia(g) == alvo:
            lo = mid
        else:
            hi = mid
    return lo * 0.98


def raio_inscrito(poly):
    try:
        linha = shapely.maximum_inscribed_circle(poly, tolerance=max(poly.length * 1e-4, 1e-6))
        return float(linha.length)
    except Exception:
        b = poly.bounds
        return min(b[2] - b[0], b[3] - b[1]) / 2


def _niveis(estilo, poly, p, degraus):
    """Lista [(d, z_relativo)] dos degraus do perfil (d = quanto encolhe)."""
    if estilo == 'inflado':
        R = raio_inscrito(poly)
        if R <= 0:
            return [], 0.0, R
        h = max(0.0, float(p.get('inflado', 0.6))) * R
        n = max(3, degraus)
        niveis = []
        for j in range(1, n + 1):
            t = (math.pi / 2) * j / n
            d = R * (1 - math.cos(t)) * 0.985
            niveis.append((d, h * math.sin(t)))
        return niveis, h, R
    b = float(p.get('chanfro', 0) or 0)
    if b <= 0:
        return [], 0.0, 0.0
    perfil = p.get('perfil', 'redondo')
    if perfil == 'reto':
        return [(b, b)], b, b
    n = max(2, degraus)
    niveis = []
    for j in range(1, n + 1):
        t = (math.pi / 2) * j / n
        niveis.append((b * (1 - math.cos(t)), b * math.sin(t)))
    return niveis, b, b


def solido(poly, p, q):
    """Malha fechada (vértices, faces) de UM polígono com furos.

    p: parâmetros da peça (estilo, altura, chanfro, perfil, lados, inflado,
       fundo, z). q: qualidade (degraus, arco)."""
    poly = orient(poly, 1.0)
    estilo = p.get('estilo', 'chanfro')
    altura = max(0.0, float(p.get('altura', 1.0)))
    z0 = float(p.get('z', 0.0))
    degraus = int(q.get('degraus', 6))
    arco = int(q.get('arco', 4))
    m = _Malha()
    info = {}

    if estilo == 'inflado':
        niveis, h, R = _niveis('inflado', poly, p, degraus)
        info['raio'] = R
        info['raio_seguro'] = raio_seguro(poly, R * 0.95, arco) if R > 0 else 0
        # densifica os anéis (triângulos do tamanho do degrau), no máximo ~400 pontos extras por anel
        seg = max(R * 2.5 / max(degraus, 1), poly.length / int(q.get('pontos', 400)))
        poly = shapely.segmentize(poly, seg)
        duplo = p.get('fundo', 'plano') == 'duplo'
        parede = altura
        if duplo:
            zb, zt = z0 + h, z0 + h + parede
        else:
            zb, zt = z0, z0 + parede
        _parede(m, poly, zb, zt)
        _subir(m, poly, niveis, zt, arco, para_cima=True, seg=seg)
        if duplo:
            _subir(m, poly, niveis, zb, arco, para_cima=False, seg=seg)
        else:
            _tampa(m, poly, zb, para_cima=False)
        info['altura_total'] = parede + h * (2 if duplo else 1)
    else:
        b = float(p.get('chanfro', 0) or 0)
        ambos = p.get('lados', 'topo') == 'ambos'
        b = min(b, altura * (0.49 if ambos else 0.95))
        if b > 0:
            b = raio_seguro(poly, b, arco)
        pp = dict(p, chanfro=b)
        niveis, hb, _ = _niveis('chanfro', poly, pp, degraus)
        seg = max(b * 3, poly.length / int(q.get('pontos', 400))) if b > 0 else 0.0
        if seg > 0:
            poly = shapely.segmentize(poly, seg)
        info['chanfro_usado'] = b
        zb = z0 + (hb if ambos else 0.0)
        zt = z0 + altura - hb
        _parede(m, poly, zb, zt)
        _subir(m, poly, niveis, zt, arco, para_cima=True, seg=seg)
        if ambos:
            _subir(m, poly, niveis, zb, arco, para_cima=False, seg=seg)
        else:
            _tampa(m, poly, zb, para_cima=False)
        info['altura_total'] = altura
    v, f = m.resultado()
    return v, f, info


def _subir(m, poly, niveis, z_base, arco, para_cima, seg=0.0):
    """Faixas do perfil a partir de z_base (para cima ou espelhado para baixo).
    seg: comprimento máximo de aresta dos anéis (densifica para a triangulação
    das faixas ficar proporcional ao degrau)."""
    sinal = 1.0 if para_cima else -1.0
    atual = poly
    z_atual = z_base
    for d, dz in niveis:
        prox = _encolher(poly, d, arco)
        if not prox.is_empty:
            # garante contenção estrita (evita bordas encostadas por arredondamento)
            prox = prox.intersection(atual) if not atual.contains(prox) else prox
            if seg > 0 and not prox.is_empty:
                prox = shapely.segmentize(prox, seg)
        z_prox = z_base + sinal * dz
        if prox.is_empty:
            _faixa(m, atual, None, z_atual, z_atual, para_cima)
            return
        _faixa(m, atual, prox, z_atual, z_prox, para_cima)
        atual = prox
        z_atual = z_prox
    # tampa no último degrau
    for parte in shapely.get_parts(atual):
        if isinstance(parte, Polygon) and parte.area > 0:
            _tampa(m, parte, z_atual, para_cima)


# ---------------------------------------------------------------------------
# Montagem do modelo
# ---------------------------------------------------------------------------

PADRAO_PECA = {
    'estilo': 'chanfro', 'altura': None, 'z': 0.0, 'chanfro': None, 'perfil': 'redondo',
    'lados': 'topo', 'inflado': 0.6, 'fundo': 'plano', 'metal': 0.0, 'rugosidade': 0.45,
}


def parametros_peca(peca, largura):
    """Completa os parâmetros da peça com padrões proporcionais ao tamanho."""
    p = dict(PADRAO_PECA)
    p.update({k: v for k, v in peca.items() if v is not None})
    if p.get('altura') is None:
        p['altura'] = round(largura * (0.012 if p['estilo'] == 'inflado' else 0.05), 2)
    if p.get('chanfro') is None:
        p['chanfro'] = round(largura * 0.008, 2)
    return p


def _chave_grupo(p, cor):
    return (cor, p['estilo'], round(float(p['altura']), 4), round(float(p['z']), 4),
            round(float(p['chanfro']), 4), p['perfil'], p['lados'], round(float(p['inflado']), 4),
            p['fundo'], round(float(p.get('metal', 0)), 3), round(float(p.get('rugosidade', 0.45)), 3))


def preparar(pecas, geoms, config, largura_original, simplificar=0.0):
    """Aplica escala, recorte por ordem de pintura / empilhamento, furos e
    junta peças vizinhas iguais. Devolve a lista de grupos a construir:
    [{ids, nome, cor, params, geom (MultiPolygon)}]."""
    largura = float(config.get('largura') or largura_original or 100)
    s = largura / (largura_original or largura)
    sobre = config.get('sobreposicao', 'recortar')
    unir = config.get('unir_iguais', True)

    itens = []
    for pc in pecas:
        if not pc.get('ativo', True):
            continue
        g = geoms.get(pc['id'])
        if g is None or g.is_empty:
            continue
        if s != 1:
            g = affinity.scale(g, s, s, origin=(0, 0))
        if simplificar > 0:
            g = g.simplify(simplificar, preserve_topology=True)
        g = shapely.make_valid(g)
        itens.append((pc, g))
    if not itens:
        raise GeometriaError('Nenhuma peça ativa: ligue ao menos uma peça na lista.')

    itens.sort(key=lambda t: t[0].get('ordem', 0))
    visiveis = []
    if sobre == 'recortar':
        acima = None
        for pc, g in reversed(itens):
            if pc.get('furo'):
                acima = g if acima is None else unary_union([acima, g])
                continue
            vis = g if acima is None else g.difference(acima)
            acima = g if acima is None else unary_union([acima, g])
            visiveis.append((pc, vis, 0.0))
        visiveis.reverse()
    else:
        # Empilhar: cada peça começa no topo das peças de baixo que ela cobre
        topo = []   # (geom, z_topo)
        cortes = [g for pc, g in itens if pc.get('furo')]
        furos = unary_union(cortes) if cortes else None
        for pc, g in itens:
            if pc.get('furo'):
                continue
            p = parametros_peca(pc, largura)
            base = 0.0
            for gb, zt in topo:
                if gb.intersects(g) and gb.intersection(g).area > 1e-6:
                    base = max(base, zt)
            topo.append((g, base + float(p['altura']) + float(p.get('z', 0))))
            vis = g.difference(furos) if furos is not None else g
            visiveis.append((pc, vis, base))

    grupos = {}
    ordem = []
    for pc, g, base in visiveis:
        g = _limpar(g)
        if g is None:
            continue
        p = parametros_peca(pc, largura)
        p['z'] = float(p.get('z', 0)) + base
        cor = pc.get('cor') or '#9aa1ac'
        chave = _chave_grupo(p, cor) if unir else ('peca', pc['id'])
        if chave not in grupos:
            grupos[chave] = {'ids': [], 'nome': pc.get('nome'), 'cor': cor, 'params': p, 'geoms': []}
            ordem.append(chave)
        grupos[chave]['ids'].append(pc['id'])
        grupos[chave]['geoms'].append(g)

    saida = []
    for chave in ordem:
        gr = grupos[chave]
        g = _limpar(unary_union(gr['geoms'])) if len(gr['geoms']) > 1 else gr['geoms'][0]
        if g is None:
            continue
        if len(gr['ids']) > 1:
            gr['nome'] = f"{gr['nome']} +{len(gr['ids']) - 1}"
        saida.append({'ids': gr['ids'], 'nome': gr['nome'], 'cor': gr['cor'], 'params': gr['params'], 'geom': g})

    base_tipo = config.get('base', 'nenhuma')
    if base_tipo in ('retangulo', 'contorno') and saida:
        tudo = unary_union([gr['geom'] for gr in saida])
        margem = float(config.get('base_margem') or largura * 0.04)
        if base_tipo == 'retangulo':
            x0, y0, x1, y1 = tudo.bounds
            r = float(config.get('base_raio') or 0)
            placa = box(x0 - margem, y0 - margem, x1 + margem, y1 + margem)
            if r > 0:
                r = min(r, (x1 - x0 + 2 * margem) / 2.01, (y1 - y0 + 2 * margem) / 2.01)
                placa = placa.buffer(-r, join_style='mitre').buffer(r, quad_segs=16)
        else:
            placa = tudo.buffer(margem, quad_segs=16)
            placa = unary_union([Polygon(p.exterior) for p in shapely.get_parts(placa)])
        espessura = float(config.get('base_altura') or largura * 0.02)
        pb = dict(PADRAO_PECA, estilo='chanfro', altura=espessura, z=-espessura,
                  chanfro=min(espessura * 0.4, float(config.get('base_chanfro') or espessura * 0.3)),
                  metal=0.0, rugosidade=0.6)
        saida.insert(0, {'ids': [0], 'nome': 'Base', 'cor': config.get('base_cor') or '#2a2d34',
                         'params': pb, 'geom': _limpar(placa)})
    return saida


def _limpar(g):
    if g is None or g.is_empty:
        return None
    partes = [p for p in shapely.get_parts(shapely.make_valid(g)) if isinstance(p, Polygon) and p.area > 1e-9]
    if not partes:
        partes = [p for p in shapely.get_parts(shapely.get_parts(g)) if isinstance(p, Polygon) and p.area > 1e-9]
    if not partes:
        return None
    return MultiPolygon(partes)


def estimar_triangulos(grupos, q):
    """Estimativa rápida para a fila (sem construir nada)."""
    total = 0
    deg = int(q.get('degraus', 6))
    for gr in grupos:
        pts = sum(len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors)
                  for p in shapely.get_parts(gr['geom']))
        niveis = 1 if gr['params'].get('perfil') == 'reto' and gr['params']['estilo'] == 'chanfro' else deg
        lados = 2 if (gr['params'].get('lados') == 'ambos' or gr['params'].get('fundo') == 'duplo') else 1
        total += pts * (2 + 2 * niveis * lados) + pts * 2
    return int(total)


def construir_componente(wkb, params, q):
    """Função de trabalho (roda em outro processo): um polígono -> malha."""
    poly = shapely.from_wkb(wkb)
    v, f, info = solido(poly, params, q)
    return v.astype(np.float64), f.astype(np.int64), info


def receita_componente(poly, params, info, casas=2):
    """Contornos simplificados + parâmetros do ExtrudeGeometry do three.js."""
    def anel(a):
        a = np.asarray(a)[:-1]
        return np.round(a, casas).ravel().tolist()
    poly = orient(poly, 1.0)
    forma = [anel(poly.exterior.coords)] + [anel(r.coords) for r in poly.interiors]
    estilo = params['estilo']
    if estilo == 'inflado':
        R = float(info.get('raio_seguro') or 0)
        h = float(params.get('inflado', 0.6)) * float(info.get('raio') or 0)
        return {'f': forma, 'e': 'i', 'h': round(float(params['altura']), 3), 'bt': round(h, 3),
                'bs': round(R, 3), 'z': round(float(params.get('z', 0)), 3),
                'd': 1 if params.get('fundo') == 'duplo' else 0}
    b = float(info.get('chanfro_usado') or 0)
    return {'f': forma, 'e': 'c', 'h': round(float(params['altura']), 3), 'bt': round(b, 3), 'bs': round(b, 3),
            'z': round(float(params.get('z', 0)), 3), 'r': 1 if params.get('perfil') == 'reto' else 0}
