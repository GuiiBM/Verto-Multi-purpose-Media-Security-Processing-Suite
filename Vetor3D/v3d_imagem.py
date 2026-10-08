"""Vetor3D · imagem (PNG, JPG, WEBP...) -> fundo transparente -> peças 2D.

1. Fundo: usa a transparência que a imagem já tem; sem transparência, o fundo
   é a área ligada às bordas com a cor da borda (preenchimento a partir das
   bordas); para fotos há a opção por IA (rembg). O resultado também é salvo
   como PNG sem fundo.
2. Modo "desenho" (arte de linha, quadrinho, logo com contorno): a tinta escura
   vira uma peça e cada área fechada vira uma região que pode ser pintada (a
   cor original entra quando a área é colorida). Áreas minúsculas, como os
   vãos de uma hachura, ficam na tinta.
   Modo "cores": a imagem sem fundo é vetorizada por cor (Conversor).
3. Os contornos saem de uma máscara levemente suavizada (marching squares com
   precisão de subpixel), então as curvas ficam lisas no 3D.

Coordenadas de saída em mm (y para cima), sem centralizar.
"""
import os

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon


class ImagemError(Exception):
    pass


LADO_MAX = 2200     # lado maior de trabalho (px)
LADO_MIN = 1100     # imagens pequenas são ampliadas (contornos mais lisos)


def _abrir(caminho):
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    try:
        im = Image.open(caminho)
        im = ImageOps.exif_transpose(im)
    except Exception as e:
        raise ImagemError(f'Não foi possível abrir a imagem ({e}).')
    dpi = im.info.get('dpi', (96, 96))[0] or 96
    try:
        dpi = float(dpi)
    except (TypeError, ValueError):
        dpi = 96.0
    if dpi < 30 or dpi > 1200:
        dpi = 96.0
    im = im.convert('RGBA')
    w, h = im.size
    lado = max(w, h)
    escala = 1.0
    if lado > LADO_MAX:
        escala = LADO_MAX / lado
    elif lado < LADO_MIN:
        escala = LADO_MIN / lado
    if escala != 1.0:
        im = im.resize((max(1, round(w * escala)), max(1, round(h * escala))), Image.LANCZOS)
    return im, dpi, escala


def _rotulos(mask, conectividade=1):
    from scipy import ndimage as ndi
    estrutura = ndi.generate_binary_structure(2, conectividade)
    return ndi.label(mask, structure=estrutura)


def _fundo(rgba, modo):
    """Máscara do fundo (True = fundo)."""
    from scipy import ndimage as ndi
    alfa = rgba[..., 3]
    h, w = alfa.shape
    if modo == 'nenhum':
        return np.zeros((h, w), bool), 'mantido'
    if modo == 'ia':
        try:
            from rembg import new_session, remove
            from PIL import Image
            sessao = new_session('u2net')
            out = remove(Image.fromarray(rgba), session=sessao)
            a = np.asarray(out.convert('RGBA'))[..., 3]
            return a < 128, 'ia'
        except Exception as e:
            raise ImagemError(f'A remoção de fundo por IA falhou ({e}). Use o modo Automático.')
    if (alfa < 128).mean() > 0.01:
        return alfa < 128, 'transparencia'
    # sem transparência: cor dominante na borda, ligada às bordas
    rgb = rgba[..., :3].astype(np.int16)
    borda = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    cor = np.median(borda, axis=0)
    parecido = np.abs(rgb - cor).max(axis=2) <= 32
    rot, n = _rotulos(parecido)
    ids_borda = np.unique(np.concatenate([rot[0], rot[-1], rot[:, 0], rot[:, -1]]))
    ids_borda = ids_borda[ids_borda > 0]
    fundo = np.isin(rot, ids_borda)
    # suaviza a borda do recorte (antisserrilhado da imagem original)
    fundo = ndi.binary_opening(fundo, iterations=1)
    return fundo, 'borda'


def _otsu(valores):
    hist, borda = np.histogram(valores, bins=256, range=(0, 256))
    total = hist.sum()
    if total == 0:
        return 128
    soma = np.dot(np.arange(256), hist)
    peso_b = soma_b = 0.0
    melhor, limiar = -1.0, 128
    for t in range(256):
        peso_b += hist[t]
        if peso_b == 0:
            continue
        peso_f = total - peso_b
        if peso_f == 0:
            break
        soma_b += t * hist[t]
        mb = soma_b / peso_b
        mf = (soma - soma_b) / peso_f
        v = peso_b * peso_f * (mb - mf) ** 2
        if v > melhor:
            melhor, limiar = v, t
    return limiar


def _contornos(mask, deslocamento=(0, 0), simpl=0.35, area_min=2.0):
    """Máscara booleana -> MultiPolygon (px, y para baixo), contornos lisos."""
    from scipy.ndimage import gaussian_filter
    from skimage.measure import find_contours
    m = np.pad(mask, 3).astype(np.float32)
    m = gaussian_filter(m, 0.85)
    aneis = []
    ox, oy = deslocamento
    for c in find_contours(m, 0.5):
        if len(c) < 4:
            continue
        xy = np.column_stack([c[:, 1] - 3 + ox, c[:, 0] - 3 + oy])
        p = Polygon(xy)
        if not p.is_valid:
            p = shapely.make_valid(p)
            p = max((g for g in shapely.get_parts(p) if isinstance(g, Polygon)), key=lambda g: g.area, default=None)
            if p is None:
                continue
        if p.area < area_min:
            continue
        if simpl > 0:
            p = p.simplify(simpl, preserve_topology=True)
        aneis.append(Polygon(p.exterior))
    if not aneis:
        return None
    # contornos de uma máscara não se cruzam: aninhamento decide casca/furo
    aneis.sort(key=lambda p: -p.area)
    arvore = shapely.STRtree(aneis)
    profundidade = [0] * len(aneis)
    pai = [-1] * len(aneis)
    for i, p in enumerate(aneis):
        rp = p.representative_point()
        donos = [j for j in arvore.query(rp, predicate='within') if j != i and aneis[j].area > p.area]
        profundidade[i] = len(donos)
        if donos:
            pai[i] = min(donos, key=lambda j: aneis[j].area)
    furos = {}
    for i, d in enumerate(profundidade):
        if d % 2 == 1 and pai[i] >= 0:
            furos.setdefault(pai[i], []).append(aneis[i].exterior.coords)
    cascas = []
    for i, d in enumerate(profundidade):
        if d % 2 == 0:
            q = Polygon(aneis[i].exterior.coords, furos.get(i, []))
            if not q.is_valid:
                q = shapely.make_valid(q)
            cascas.extend(g for g in shapely.get_parts(q) if isinstance(g, Polygon) and g.area > 0)
    if not cascas:
        return None
    return MultiPolygon(cascas)


def _hex(rgb):
    return '#%02x%02x%02x' % tuple(int(max(0, min(255, round(v)))) for v in rgb)


def _decidir_modo(rgba, frente):
    rgb = rgba[..., :3][frente].astype(np.float32) / 255
    if len(rgb) < 100:
        return 'cores'
    amostra = rgb[:: max(1, len(rgb) // 200000)]
    mx, mn = amostra.max(axis=1), amostra.min(axis=1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    lum = amostra @ np.array([0.299, 0.587, 0.114])
    escuro = (lum < 0.35).mean()
    # arte de linha: tinta escura em boa quantidade (mas não tudo) e pouca cor,
    # ou desenho colorido com contorno escuro bem marcado
    if 0.02 < escuro < 0.65 and (np.median(sat) < 0.2 or escuro > 0.08):
        return 'desenho'
    return 'cores'


def ler(caminho, opts, pasta):
    """Devolve dict com: modo, pecas [{nome, camada, cor, geom(mm), origem, papel}],
    avisos, png_sem_fundo (caminho) e, no modo cores, o PNG a vetorizar."""
    from PIL import Image
    from scipy import ndimage as ndi
    opts = opts or {}
    avisos = []
    im, dpi, escala = _abrir(caminho)
    rgba = np.asarray(im).copy()
    h, w = rgba.shape[:2]
    fundo, origem_fundo = _fundo(rgba, opts.get('fundo', 'auto'))
    frente = ~fundo
    # remove sujeirinhas soltas da frente
    rot, n = _rotulos(frente, 2)
    if n:
        tam = ndi.sum(frente, rot, index=np.arange(1, n + 1))
        minimo = max(25, frente.sum() * 0.00005)
        pequenos = np.flatnonzero(tam < minimo) + 1
        if len(pequenos):
            frente &= ~np.isin(rot, pequenos)
    if frente.sum() < 50:
        raise ImagemError('Depois de tirar o fundo não sobrou nada da imagem. Tente o fundo "Manter" ou "IA".')
    # PNG sem fundo (na resolução de trabalho)
    saida = rgba.copy()
    borda_suave = rgba[..., 3] if origem_fundo == 'transparencia' else 255
    saida[..., 3] = np.where(frente, borda_suave, 0).astype(np.uint8)
    png = os.path.join(pasta, 'sem_fundo.png')
    Image.fromarray(saida).save(png, optimize=True)
    nomes_fundo = {'transparencia': 'a transparência da imagem', 'borda': 'a cor das bordas',
                   'ia': 'IA (rembg)', 'mantido': 'nada (fundo mantido)'}
    avisos.append(f'Fundo removido usando {nomes_fundo[origem_fundo]}. O PNG sem fundo pode ser baixado.')

    modo = opts.get('modo_imagem', 'auto')
    if modo not in ('desenho', 'cores', 'volume'):
        modo = _decidir_modo(rgba, frente)
    k = 25.4 / dpi / escala      # mm por pixel de trabalho

    if modo == 'volume':
        # personagem 3D: uma peça só (a silhueta); o volume é feito na etapa 3D
        from shapely import affinity
        g = _contornos(frente)
        if g is None:
            raise ImagemError('Não encontrei a silhueta da imagem.')
        g = affinity.scale(g, k, -k, origin=(0, 0))
        avisos.append('Modo personagem 3D: de frente o modelo segue o contorno do desenho e usa a própria imagem como '
                      'textura; uma IA de reconstrução dá o volume que a imagem não mostra (costas, lados). Na primeira '
                      'vez o modelo (1,7 GB) é baixado.')
        return {'modo': 'volume', 'avisos': avisos, 'png_sem_fundo': png,
                'pecas': [{'nome': 'Personagem 3D', 'camada': 'volume', 'cor': '#cbd5e1', 'geom': g,
                           'origem': 'volume', 'papel': 'volume'}]}

    if modo == 'cores':
        return {'modo': 'cores', 'pecas': [], 'avisos': avisos, 'png_sem_fundo': png, 'vetorizar': png}

    # ---- desenho: tinta + regiões fechadas ----
    branco = np.array([255, 255, 255], np.float32)
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = rgba[..., :3].astype(np.float32) * a + branco * (1 - a)   # sobre branco
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    limiar = float(np.clip(_otsu(lum[frente]), 70, 190))
    tinta = frente & (lum < limiar)
    # fecha frestas de 1-2 px no traço (senão a região "vaza" para fora)
    fechar = int(opts.get('fechar', max(1, round(min(h, w) / 900))))
    tinta_f = ndi.binary_closing(tinta, iterations=fechar) & frente if fechar > 0 else tinta
    vazio = frente & ~tinta_f
    rot, n = _rotulos(vazio, 1)
    pecas = []
    regioes = np.zeros((h, w), bool)
    if n:
        tam = ndi.sum(vazio, rot, index=np.arange(1, n + 1))
        area_min = max(120.0, frente.sum() * float(opts.get('detalhe', 0.0004)))
        ids = [i + 1 for i in np.argsort(-tam) if tam[i] >= area_min][:500]
        caixas = ndi.find_objects(rot)
        for num, i in enumerate(ids, 1):
            sl = caixas[i - 1]
            y0, y1 = max(0, sl[0].start - 3), min(h, sl[0].stop + 3)
            x0, x1 = max(0, sl[1].start - 3), min(w, sl[1].stop + 3)
            m = rot[y0:y1, x0:x1] == i
            regioes[y0:y1, x0:x1] |= m
            # um pouco maior: entra embaixo da tinta (sem frestas entre as peças)
            md = ndi.binary_dilation(m, iterations=2)
            g = _contornos(md, (x0, y0))
            if g is None:
                continue
            cores = rgb[y0:y1, x0:x1][m]
            med = np.median(cores, axis=0)
            cor = None if med.min() > 222 or (med.max() - med.min() < 18 and med.min() > 200) else _hex(med)
            pecas.append({'nome': f'Região {num}', 'camada': 'regioes', 'cor': cor, 'geom': g,
                          'origem': 'regiao', 'papel': 'regiao'})
        descartadas = n - len(pecas)
        if descartadas > 0:
            avisos.append(f'{descartadas} área(s) muito pequenas (vãos de hachura, pontos) ficaram junto da tinta.')
    corpo = frente & ~regioes
    g_tinta = _contornos(corpo)
    if g_tinta is not None:
        pecas.append({'nome': 'Traço (tinta)', 'camada': 'tinta', 'cor': '#15171b', 'geom': g_tinta,
                      'origem': 'tinta', 'papel': 'tinta'})
    if not pecas:
        raise ImagemError('Não encontrei formas na imagem.')
    # px (y para baixo) -> mm (y para cima)
    from shapely import affinity
    for p in pecas:
        p['geom'] = affinity.scale(p['geom'], k, -k, origin=(0, 0))
    avisos.append(f'Desenho separado em traço + {len(pecas) - 1} região(ões) fechada(s): clique nelas para pintar.')
    return {'modo': 'desenho', 'pecas': pecas, 'avisos': avisos, 'png_sem_fundo': png}
