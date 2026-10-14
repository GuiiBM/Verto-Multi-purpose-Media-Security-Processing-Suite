"""Vetorizar 4K · núcleo: detectar o tipo, preparar a imagem, traçar e medir.

Tipos e caminhos:
- pixel art: acha a grade do "pixel" (mesmo ampliada e com JPEG por cima),
  reduz à grade real e
    * exato: cada célula vira quadrado; células vizinhas da mesma cor viram um
      polígono só (contorno pelas arestas das células, sem nenhuma curva);
    * suave: amplia a grade com EPX (Scale2x) duas vezes, que arredonda as
      diagonais, e traça em curvas;
- logo / ilustração: amplia se for pequena, suaviza sem borrar as bordas,
  reduz a uma paleta em Lab (cores da marca podem ser travadas), limpa o
  serrilhado e traça cada cor em curvas (vtracer, empilhado);
- traço (desenho, escaneado): binariza com limiar adaptativo e traça com o
  potrace do Conversor (contorno ou linha central);
- foto: pôster (paleta de N cores, editável) ou detalhado (vtracer livre).

Saída comum: "formas" na ordem de desenho, cada uma com cor, regra de
preenchimento e subcaminhos em comandos M/L/C (o formato do TraceResult do
Conversor, que escreve EPS e DXF), em coordenadas da imagem original.
"""
import io
import math
import re

import numpy as np
from PIL import Image, ImageFilter

TRABALHO_MAX = 2400        # lado máximo em que o traçado acontece
TRABALHO_MIN = 1000        # imagens menores são ampliadas até aqui (curvas mais lisas)
GRADE_MAX = 512            # pixel art: lado máximo da grade real


class VetorizarError(Exception):
    pass


# ------------------------------------------------------------------ imagem ---

def abrir(caminho):
    """-> RGBA uint8 (H, W, 4), já com a orientação do EXIF."""
    from PIL import ImageOps
    try:
        im = Image.open(caminho)
        im = ImageOps.exif_transpose(im)
    except Exception:
        raise VetorizarError('Não consegui abrir essa imagem. Use PNG, JPG, WebP, GIF, BMP ou TIFF.')
    if getattr(im, 'n_frames', 1) > 1:
        im.seek(0)
    return np.asarray(im.convert('RGBA')).copy()


def _opaco(rgba):
    return rgba[..., 3] >= 128


def _achatar(rgba, fundo=(255, 255, 255)):
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3] * a + np.array(fundo, np.float32) * (1 - a)).astype(np.uint8)


def _lab(rgb):
    from skimage.color import rgb2lab
    return rgb2lab(np.asarray(rgb, np.uint8).reshape(-1, 1, 3)).reshape(-1, 3)


def _rgb_de_lab(lab):
    from skimage.color import lab2rgb
    return np.clip(np.round(lab2rgb(np.asarray(lab, float).reshape(-1, 1, 3)).reshape(-1, 3) * 255), 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ análise ---

def grade_pixel(rgba):
    """Tamanho da célula (s), deslocamento (ox, oy) e a nota da grade.

    Usa a intensidade das bordas por coluna/linha (não a contagem): o JPEG cria
    bordinhas fracas perto das bordas de verdade, que pesam pouco aqui. Uma
    grade s vale quando a maior parte da energia cai exatamente nas linhas da
    grade e quase toda cai a no máximo 1 px delas. s=1 = sem grade."""
    import cv2
    # mediana tira o ruído e os blocos 8×8 do JPEG; bordas fracas não contam
    rgb = cv2.medianBlur(np.ascontiguousarray(_achatar(rgba)), 3).astype(np.float32)
    h, w = rgb.shape[:2]
    dx = np.abs(rgb[:, 1:] - rgb[:, :-1]).sum(2)
    dy = np.abs(rgb[1:] - rgb[:-1]).sum(2)
    ex = np.where(dx > 70, dx, 0).sum(0)   # borda entre a coluna x e x+1
    ey = np.where(dy > 70, dy, 0).sum(1)
    if ex.sum() <= 0 or ey.sum() <= 0:
        return 1, 0, 0, 0.0

    def nota(e, s):
        pos = np.arange(1, len(e) + 1)
        tot = e.sum()
        melhor = (0.0, 0.0, 0)
        for o in range(s):
            r = (pos - o) % s
            exato = e[r == 0].sum() / tot
            perto = e[(r == 0) | (r == 1) | (r == s - 1)].sum() / tot if s >= 4 else exato
            if exato > melhor[0]:
                melhor = (exato, perto, o)
        return melhor

    achado = (1, 0, 0, 0.0)
    for s in range(2, max(3, min(64, w // 6, h // 6) + 1)):
        exx, px_, ox = nota(ex, s)
        exy, py_, oy = nota(ey, s)
        if min(exx, exy) >= 0.55 and min(px_, py_) >= 0.85:
            achado = (s, ox, oy, float(min(px_, py_)))
    return achado


def _cores_dominantes(rgb, opaco):
    """Quantas cores (caixas de 3 bits por canal) cobrem 95% da imagem, depois
    de um filtro que tira o ruído do JPEG sem borrar as bordas. Medido: logos e
    ilustrações 4 a 20; foto de rosto 56."""
    import cv2
    liso = cv2.bilateralFilter(np.ascontiguousarray(rgb), 7, 35, 7)
    px = liso[opaco] if opaco.any() else liso.reshape(-1, 3)
    if len(px) > 300000:
        px = px[np.random.default_rng(0).choice(len(px), 300000, replace=False)]
    chaves = (px[:, 0] >> 5).astype(np.int32) << 6 | (px[:, 1] >> 5).astype(np.int32) << 3 | (px[:, 2] >> 5)
    cont = np.sort(np.bincount(chaves, minlength=512))[::-1]
    return int(np.searchsorted(np.cumsum(cont), 0.95 * len(px)) + 1)


def analisar(rgba):
    h, w = rgba.shape[:2]
    opaco = _opaco(rgba)
    rgb = _achatar(rgba)
    s, ox, oy, nota = grade_pixel(rgba)
    exatas = len(np.unique(rgb[opaco].reshape(-1, 3), axis=0)) if opaco.any() else 1
    k98 = _cores_dominantes(rgb, opaco)
    cinza = np.asarray(Image.fromarray(rgb).convert('L'), np.float32)
    hsv = np.asarray(Image.fromarray(rgb).convert('HSV'), np.float32)
    sat = float(hsv[..., 1][opaco].mean() / 255) if opaco.any() else 0.0
    meios = float(((cinza > 70) & (cinza < 185))[opaco].mean()) if opaco.any() else 0.0
    info = {'largura': w, 'altura': h, 'grade': int(s), 'grade_x': int(ox), 'grade_y': int(oy),
            'cores': k98, 'transparente': bool((~opaco).mean() > 0.01)}
    if s >= 2 and w // s >= 6 and h // s >= 6 and w // s <= GRADE_MAX and h // s <= GRADE_MAX:
        return {**info, 'tipo': 'pixel', 'motivo': f'Pixel art ampliada {s}×: cada "pixel" tem {s}×{s} px ({w // s}×{h // s} células).'}
    if max(w, h) <= 256 and exatas <= 64:
        info['grade'] = 1
        return {**info, 'tipo': 'pixel', 'motivo': f'Pixel art no tamanho real ({w}×{h}, {exatas} cores).'}
    if sat < 0.12 and meios < 0.14:
        return {**info, 'tipo': 'traco', 'motivo': 'Desenho a traço: quase só preto e branco.'}
    if k98 <= 28:
        return {**info, 'tipo': 'logo', 'motivo': 'Logo ou ilustração: poucas cores dominantes e áreas lisas.'}
    return {**info, 'tipo': 'foto', 'motivo': 'Foto ou imagem com muitos tons.'}


# ----------------------------------------------------------- paleta (Lab) ---

def kmeans_lab(px_rgb, k, travadas=()):
    """Paleta de k cores em Lab. Cores travadas (marca) entram fixas."""
    from scipy.cluster.vq import kmeans2
    lab = _lab(px_rgb)
    trav = _lab(np.array(travadas, np.uint8)) if len(travadas) else np.zeros((0, 3))
    k_livre = max(0, k - len(trav))
    if k_livre:
        rng = np.random.default_rng(7)
        cent, _ = kmeans2(lab, k_livre, minit='++', iter=25, seed=rng)
        cent = np.vstack([trav, cent]) if len(trav) else cent
    else:
        cent = trav
    for _ in range(6):   # refina com as travadas paradas
        d = ((lab[:, None, :] - cent[None]) ** 2).sum(2)
        lab_idx = d.argmin(1)
        for c in range(len(trav), len(cent)):
            sel = lab_idx == c
            if sel.any():
                cent[c] = lab[sel].mean(0)
    return cent


def paleta_auto(px_rgb, travadas=(), maximo=24, alvo=5.0):
    """Menor paleta cujo erro médio fica abaixo de `alvo` (ΔE), ou a partir da
    qual mais uma cor quase não ajuda; no fim, junta cores quase iguais
    (o JPEG divide um azul liso em dois tons)."""
    lab = _lab(px_rgb)
    melhor, erro_ant = None, None
    for k in list(range(max(2, len(travadas)), 13)) + [16, 20, 24]:
        if k > maximo:
            break
        cent = kmeans_lab(px_rgb, k, travadas)
        erro = np.sqrt(((lab[:, None, :] - cent[None]) ** 2).sum(2).min(1)).mean()
        if erro_ant is not None and erro > 0.88 * erro_ant and erro < 2 * alvo:
            break
        melhor, erro_ant = cent, erro
        if erro < alvo:
            break
    return juntar_proximas(melhor, len(travadas))


def juntar_proximas(cent, n_fixas=0, limite=12.0):
    cent = [c for c in cent]
    mudou = True
    while mudou and len(cent) > 2:
        mudou = False
        for i in range(len(cent)):
            for j in range(max(i + 1, n_fixas), len(cent)):
                if np.sqrt(((cent[i] - cent[j]) ** 2).sum()) < limite:
                    del cent[j]
                    mudou = True
                    break
            if mudou:
                break
    return np.array(cent)


def _amostra_lisa(rgb, opaco, n=40000):
    """Pixels de áreas lisas (fora das faixas de antisserrilhado das bordas)."""
    from scipy.ndimage import maximum_filter, minimum_filter
    cinza = np.asarray(Image.fromarray(rgb).convert('L'))
    liso = (maximum_filter(cinza, 5).astype(int) - minimum_filter(cinza, 5)) < 18
    sel = liso & opaco
    if sel.sum() < 400:
        sel = opaco
    px = rgb[sel]
    if len(px) > n:
        px = px[np.random.default_rng(1).choice(len(px), n, replace=False)]
    return px


def indexar(rgb, cent_lab):
    """Cada pixel -> índice da cor mais próxima (em blocos, para caber na memória)."""
    h, w = rgb.shape[:2]
    lab = _lab(rgb.reshape(-1, 3))
    out = np.empty(len(lab), np.int32)
    for i in range(0, len(lab), 250000):
        d = ((lab[i:i + 250000, None, :] - cent_lab[None]) ** 2).sum(2)
        out[i:i + 250000] = d.argmin(1)
    return out.reshape(h, w)


def resumo_paleta(idx, cent_lab, transparente=None):
    cores = _rgb_de_lab(cent_lab)
    vis = idx[~transparente] if transparente is not None else idx.ravel()
    cont = np.bincount(vis, minlength=len(cores)) if vis.size else np.zeros(len(cores))
    total = max(1, vis.size)
    return [{'i': i, 'hex': '#%02x%02x%02x' % tuple(int(v) for v in cores[i]), 'pct': round(100 * cont[i] / total, 2)}
            for i in range(len(cores))]


# ------------------------------------------------------- pixel art: grade ---

def ruido_celulas(rgba, s):
    """Variação média dentro das células: ~0 numa pixel art limpa (PNG), alta
    quando o JPEG ou um redimensionamento sujaram as cores."""
    if s <= 1:
        return 0.0
    h, w = rgba.shape[:2]
    gh, gw = h // s, w // s
    b = rgba[:gh * s, :gw * s, :3].reshape(gh, s, gw, s, 3).astype(np.float32)
    return float(b.std(axis=(1, 3)).mean())


def reduzir_grade(rgba, s, ox, oy):
    """Uma amostra por célula: a mediana do miolo (longe das bordas borradas)."""
    if s <= 1:
        return rgba.copy()
    h, w = rgba.shape[:2]
    gw, gh = (w - ox) // s, (h - oy) // s
    m = max(0, s // 4)
    blocos = rgba[oy:oy + gh * s, ox:ox + gw * s].reshape(gh, s, gw, s, 4)
    miolo = blocos[:, m:s - m, :, m:s - m, :] if s - 2 * m >= 1 else blocos
    return np.median(miolo.reshape(gh, miolo.shape[1], gw, miolo.shape[3], 4), axis=(1, 3)).astype(np.uint8)


def paleta_pixel(grade, sujo):
    """Paleta da pixel art. Limpa (PNG): as cores exatas, sem juntar nada.
    Suja (JPEG): junta cores próximas e depois funde as raras que só aparecem
    na fronteira entre duas cores (sangria de cor do JPEG)."""
    opaco = _opaco(grade)
    px = grade[..., :3][opaco]
    if not len(px):
        raise VetorizarError('A imagem está toda transparente.')
    unicas, cont = np.unique(px.reshape(-1, 3), axis=0, return_counts=True)
    ordem = np.argsort(-cont)
    lab = _lab(unicas[ordem])
    cont = cont[ordem]
    limite = 20.0 if sujo else 1.0
    cent, peso = [], []
    for i in range(len(lab)):
        if cent:
            d = np.sqrt(((np.array(cent) - lab[i]) ** 2).sum(1))
            j = int(d.argmin())
            if d[j] <= limite:
                peso[j] += cont[i]
                continue
        if len(cent) < 64:
            cent.append(lab[i]); peso.append(cont[i])
    return np.array(cent)


def fundir_sangria(idx, cent, transp, limite=45.0, raro=0.08):
    """Pixel art suja: cor rara (< 8% das células) que encosta numa cor vizinha
    maior e parecida (até `limite` ΔE) é sangria do JPEG e vira essa vizinha."""
    from scipy.ndimage import binary_dilation
    total = max(1, (~transp).sum())
    cont = np.bincount(idx[~transp], minlength=len(cent))
    for c in np.argsort(cont):
        if cont[c] == 0 or cont[c] / total >= raro:
            continue
        mask = (idx == c) & ~transp
        viz = idx[binary_dilation(mask) & ~mask & ~transp]
        viz = [v for v in np.unique(viz) if cont[v] > cont[c]]
        if not viz:
            continue
        d = [np.sqrt(((cent[v] - cent[c]) ** 2).sum()) for v in viz]
        j = int(np.argmin(d))
        if d[j] < limite:
            idx[mask] = viz[j]
            cont[viz[j]] += cont[c]
            cont[c] = 0
    return idx


def _arredondar_mapa(g, sigma):
    """Cada cor vira uma máscara borrada e cada pixel fica com a mais forte:
    os degraus longos viram rampas sem mexer nas manchas grandes."""
    from scipy.ndimage import gaussian_filter
    melhor = np.full(g.shape, -1.0, np.float32)
    out = g.copy()
    for c in np.unique(g):
        f = gaussian_filter((g == c).astype(np.float32), sigma)
        troca = f > melhor
        melhor[troca], out[troca] = f[troca], c
    return out


def _epx(idx):
    """Scale2x (EPX) num mapa de índices: dobra o tamanho arredondando as diagonais."""
    p = np.pad(idx, 1, mode='edge')
    P = p[1:-1, 1:-1]
    A, B, C, D = p[:-2, 1:-1], p[1:-1, 2:], p[1:-1, :-2], p[2:, 1:-1]   # cima, direita, esquerda, baixo
    e0 = np.where((C == A) & (C != D) & (A != B), A, P)
    e1 = np.where((A == B) & (A != C) & (B != D), B, P)
    e2 = np.where((D == C) & (D != B) & (C != A), C, P)
    e3 = np.where((B == D) & (B != A) & (D != C), D, P)
    h, w = idx.shape
    out = np.empty((h * 2, w * 2), idx.dtype)
    out[0::2, 0::2], out[0::2, 1::2], out[1::2, 0::2], out[1::2, 1::2] = e0, e1, e2, e3
    return out


def contornos_retos(mask):
    """Laços pelas arestas das células (sentido horário em y para baixo; buracos
    saem no sentido contrário, então a regra nonzero preenche certo)."""
    h, w = mask.shape
    p = np.pad(mask, 1)
    m = p[1:-1, 1:-1]
    saidas = {}

    def add(ys, xs, dx0, dy0, dx1, dy1):
        for y, x in zip(ys.tolist(), xs.tolist()):
            saidas.setdefault((x + dx0, y + dy0), []).append((x + dx1, y + dy1))

    ys, xs = np.nonzero(m & ~p[:-2, 1:-1]); add(ys, xs, 0, 0, 1, 0)       # topo: esquerda -> direita
    ys, xs = np.nonzero(m & ~p[1:-1, 2:]); add(ys, xs, 1, 0, 1, 1)        # direita: cima -> baixo
    ys, xs = np.nonzero(m & ~p[2:, 1:-1]); add(ys, xs, 1, 1, 0, 1)        # baixo: direita -> esquerda
    ys, xs = np.nonzero(m & ~p[1:-1, :-2]); add(ys, xs, 0, 1, 0, 0)       # esquerda: baixo -> cima

    lacos = []
    while saidas:
        ini = next(iter(saidas))
        laco, atual, dir_ant = [ini], ini, None
        while True:
            opcoes = saidas.get(atual)
            if not opcoes:
                break
            if len(opcoes) == 1 or dir_ant is None:
                prox = opcoes[0]
            else:
                # vértice com duas saídas (células na diagonal): vira à direita,
                # o que mantém cada mancha no seu próprio laço
                def giro(q):
                    d = (q[0] - atual[0], q[1] - atual[1])
                    return dir_ant[0] * d[1] - dir_ant[1] * d[0]
                prox = max(opcoes, key=giro)
            opcoes.remove(prox)
            if not opcoes:
                del saidas[atual]
            dir_ant = (prox[0] - atual[0], prox[1] - atual[1])
            atual = prox
            if atual == ini:
                break
            laco.append(atual)
        # tira vértices no meio de retas
        simp = [pt for i, pt in enumerate(laco)
                if (laco[i - 1][0] - pt[0]) * (laco[(i + 1) % len(laco)][1] - pt[1])
                != (laco[i - 1][1] - pt[1]) * (laco[(i + 1) % len(laco)][0] - pt[0])]
        if len(simp) >= 3:
            lacos.append(simp)
    return lacos


def tracar_pixel_exato(idx, cores, transp, s, ox, oy):
    formas = []
    ordem = np.argsort(-np.bincount(idx[~transp], minlength=len(cores)))
    for c in ordem:
        mask = (idx == c) & ~transp
        if not mask.any():
            continue
        subs = []
        for laco in contornos_retos(mask):
            pts = [(x * s + ox, y * s + oy) for x, y in laco]
            subs.append([('M', pts[0])] + [('L', q) for q in pts[1:]])
        formas.append({'cor': tuple(int(v) for v in cores[c]), 'regra': 'nonzero', 'subs': subs, 'idx': int(c)})
    return formas


# --------------------------------------------------------------- traçado ---

def _params_vtracer(suavidade, detalhe, escala):
    """suavidade 0..100 (cantos vivos -> curvas soltas); detalhe 0..100 (limpa -> tudo)."""
    return dict(
        mode='spline',
        corner_threshold=int(30 + 0.9 * suavidade),
        length_threshold=round(3.5 + 0.06 * suavidade, 2),
        splice_threshold=int(30 + 0.4 * suavidade),
        filter_speckle=max(1, int(round((14 - 0.13 * detalhe) * max(1.0, escala) ** 0.5))),
        max_iterations=10,
        path_precision=3,
    )


def _vtracer(rgba, cores_livres=False, precisao=6, diferenca=16, **par):
    import vtracer
    buf = io.BytesIO()
    Image.fromarray(rgba, 'RGBA').save(buf, 'PNG')
    if cores_livres:
        cp, ld = precisao, diferenca
    else:
        cp, ld = 8, 1   # a imagem já vem com a paleta exata: não juntar nada
    return vtracer.convert_raw_image_to_svg(buf.getvalue(), img_format='png', colormode='color',
                                            hierarchical='stacked', color_precision=cp,
                                            layer_difference=ld, **par)


def _svg_para_formas(svg, k=1.0, dx=0.0, dy=0.0):
    """SVG do vtracer -> formas (aplica translate e a escala de volta)."""
    from svgelements import SVG, Path, Move, Line, CubicBezier, QuadraticBezier, Close, Arc
    doc = SVG.parse(io.StringIO(svg), reify=True)
    formas = []
    for el in doc.elements():
        if not isinstance(el, Path) or el.fill is None or el.fill.value is None:
            continue
        cor = (el.fill.red, el.fill.green, el.fill.blue)
        T = lambda p: (p.x * k + dx, p.y * k + dy)
        subs, atual = [], None
        for seg in el:
            if isinstance(seg, Move):
                atual = [('M', T(seg.end))]
                subs.append(atual)
            elif isinstance(seg, Close):
                atual = None
            elif atual is None:
                continue
            elif isinstance(seg, Line):
                atual.append(('L', T(seg.end)))
            elif isinstance(seg, CubicBezier):
                atual.append(('C', T(seg.control1), T(seg.control2), T(seg.end)))
            elif isinstance(seg, QuadraticBezier):
                s0, c, e = seg.start, seg.control, seg.end
                c1 = (s0.x + 2 / 3 * (c.x - s0.x), s0.y + 2 / 3 * (c.y - s0.y))
                c2 = (e.x + 2 / 3 * (c.x - e.x), e.y + 2 / 3 * (c.y - e.y))
                atual.append(('C', (c1[0] * k + dx, c1[1] * k + dy), (c2[0] * k + dx, c2[1] * k + dy), T(e)))
            elif isinstance(seg, Arc):
                for cb in seg.as_cubic_curves():
                    atual.append(('C', T(cb.control1), T(cb.control2), T(cb.end)))
        subs = [s for s in subs if len(s) > 2]
        if subs:
            formas.append({'cor': cor, 'regra': 'nonzero', 'subs': subs})
    return formas


def _mapa_para_rgba(idx, cores, transp):
    out = np.zeros(idx.shape + (4,), np.uint8)
    out[..., :3] = np.asarray(cores, np.uint8)[idx]
    out[..., 3] = np.where(transp, 0, 255)
    return out


def _escala_trabalho(w, h):
    lado = max(w, h)
    if lado > TRABALHO_MAX:
        return TRABALHO_MAX / lado
    if lado < TRABALHO_MIN:
        return min(4.0, TRABALHO_MIN / lado)
    return 1.0


def _redimensionar(rgba, k):
    if k == 1.0:
        return rgba
    h, w = rgba.shape[:2]
    novo = (max(1, round(w * k)), max(1, round(h * k)))
    return np.asarray(Image.fromarray(rgba, 'RGBA').resize(novo, Image.LANCZOS if k < 1 else Image.BICUBIC))


def _limpar_bordas(rgb):
    """Suaviza o ruído (JPEG, escaneado) sem borrar as bordas das cores."""
    import cv2
    return cv2.bilateralFilter(np.ascontiguousarray(rgb), 7, 35, 7)


def _moda(idx, tamanho):
    if tamanho < 3:
        return idx
    n = int(idx.max()) + 1
    if n <= 255:
        return np.asarray(Image.fromarray(idx.astype(np.uint8), 'L').filter(ImageFilter.ModeFilter(tamanho))).astype(np.int32)
    return idx


def fundo_da_borda(idx, transp):
    """Cor que ocupa a maior parte da borda da imagem (o fundo), ou None."""
    borda = np.concatenate([idx[0], idx[-1], idx[:, 0], idx[:, -1]])
    tb = np.concatenate([transp[0], transp[-1], transp[:, 0], transp[:, -1]])
    borda = borda[~tb]
    if not len(borda):
        return None
    c = np.bincount(borda).argmax()
    return int(c) if (borda == c).mean() > 0.6 else None


def mascara_fundo(idx, transp, f=None, pela_transparencia=False):
    """Só as manchas da cor de fundo que tocam a borda (o branco de dentro do
    desenho continua). `pela_transparencia`: também as que encostam numa área
    já transparente (sobra do recorte da IA, que tem borda macia)."""
    from scipy.ndimage import label, binary_dilation
    f = fundo_da_borda(idx, transp) if f is None else f
    if f is None:
        return None
    rot, _ = label((idx == f) & ~transp)
    ids = np.unique(np.concatenate([rot[0], rot[-1], rot[:, 0], rot[:, -1]]))
    if pela_transparencia and transp.any():
        anel = binary_dilation(transp, iterations=2) & ~transp
        ids = np.unique(np.concatenate([ids, rot[anel]]))
    ids = ids[ids > 0]
    return np.isin(rot, ids) if len(ids) else None


def aplicar_mapa(idx, cent_lab, mapa):
    """Edições da paleta: juntar (i -> j), trocar a cor, apagar (vira transparente)."""
    idx = idx.copy()
    cent = cent_lab.copy()
    apagar = np.zeros(len(cent), bool)
    for chave, acao in (mapa or {}).items():
        try:
            i = int(chave)
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(cent):
            continue
        if acao.get('para') is not None and 0 <= int(acao['para']) < len(cent) and int(acao['para']) != i:
            idx[idx == i] = int(acao['para'])
        if acao.get('hex'):
            h = acao['hex'].lstrip('#')
            if re.fullmatch(r'[0-9a-fA-F]{6}', h):
                cent[i] = _lab(np.array([[int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)]], np.uint8))[0]
        if acao.get('apagar'):
            apagar[i] = True
    return idx, cent, apagar


def _bordas_por_vizinhanca(rgb, idx, cent, opaco, janela=7):
    """Pixel de borda (mistura de duas cores, antisserrilhado ou JPEG) só pode
    virar uma cor que existe em área lisa por perto. Sem isso, a mistura de
    amarelo com azul vira um filete branco ou verde entre as duas."""
    from scipy.ndimage import maximum_filter, minimum_filter
    cinza = np.asarray(Image.fromarray(rgb).convert('L'))
    liso = ((maximum_filter(cinza, 3).astype(int) - minimum_filter(cinza, 3)) < 14) & opaco
    borda = ~liso & opaco
    if not borda.any() or len(cent) > 40:
        return idx
    lab = _lab(rgb[borda])
    melhor_d = np.full(len(lab), np.inf)
    melhor_c = idx[borda].copy()
    for c in range(len(cent)):
        perto = maximum_filter((idx == c) & liso, size=janela)[borda]
        if not perto.any():
            continue
        d = ((lab - cent[c]) ** 2).sum(1)
        d[~perto] = np.inf
        troca = d < melhor_d
        melhor_d[troca], melhor_c[troca] = d[troca], c
    out = idx.copy()
    out[borda] = melhor_c
    return out


def preparar_cores(rgba, k_cores, travadas, detalhe, mascara_ia=None):
    """Logo/ilustração/pôster: escala de trabalho, limpeza e mapa de índices."""
    h, w = rgba.shape[:2]
    k = _escala_trabalho(w, h)
    trab = _redimensionar(rgba, k)
    if mascara_ia is not None:
        m = np.asarray(Image.fromarray(mascara_ia).resize((trab.shape[1], trab.shape[0]), Image.BILINEAR))
        trab = trab.copy()
        trab[..., 3] = np.minimum(trab[..., 3], m)
    transp = ~_opaco(trab)
    rgb = _limpar_bordas(_achatar(trab))
    px = _amostra_lisa(rgb, ~transp)
    cent = kmeans_lab(px, int(k_cores), travadas) if k_cores else paleta_auto(px, travadas)
    idx = indexar(rgb, cent)
    idx = _bordas_por_vizinhanca(rgb, idx, cent, ~transp)
    # o filtro de moda some com o serrilhado e os pontinhos; menos forte quando o
    # usuário pede mais detalhe
    idx = _moda(idx, 5 if detalhe < 70 else 3)
    return {'k': k, 'idx': idx, 'cent': cent, 'transp': transp}


def _separar_fundo(idx, transp, cores, w, h, k=1.0, dx=0.0, dy=0.0):
    """O fundo que cobre a borda vira um retângulo exato (o traçado em curvas
    arredondaria os cantos da imagem); o resto é traçado por cima dele."""
    m = mascara_fundo(idx, transp)
    if m is None or m.mean() < 0.03:
        return None, transp
    f = fundo_da_borda(idx, transp)
    hh, ww = idx.shape
    x0, y0, x1, y1 = dx, dy, ww * k + dx, hh * k + dy
    ret = [[('M', (x0, y0)), ('L', (x1, y0)), ('L', (x1, y1)), ('L', (x0, y1))]]
    forma = {'cor': tuple(int(v) for v in cores[f]), 'regra': 'nonzero', 'subs': ret, 'idx': int(f), 'fundo': True}
    return forma, transp | m


def tracar_cores(prep, cent, idx, transp, suavidade, detalhe):
    cores = _rgb_de_lab(cent)
    h, w = idx.shape
    fundo, transp = _separar_fundo(idx, transp, cores, w, h, 1 / prep['k'])
    rgba = _mapa_para_rgba(idx, cores, transp)
    par = _params_vtracer(suavidade, detalhe, prep['k'])
    svg = _vtracer(rgba, **par)
    formas = ([fundo] if fundo else []) + _svg_para_formas(svg, 1 / prep['k'])
    return encaixar_na_paleta(formas, cores, cent)


def encaixar_na_paleta(formas, cores, cent):
    """O vtracer faz média de cor ao juntar manchinhas (sai #d9281d em vez de
    #da281d): cada forma volta para a cor mais próxima da paleta, que é exata
    (inclusive as cores travadas da marca) e liga a forma ao índice dela."""
    for f in formas:
        if f.get('fundo'):
            continue
        lab = _lab(np.array([f['cor']], np.uint8))[0]
        i = int(np.sqrt(((cent - lab) ** 2).sum(1)).argmin())
        f['cor'] = tuple(int(v) for v in cores[i])
        f['idx'] = i
    return formas


def tracar_traco(rgba, modo, detalhe, suavidade):
    import cv2
    from Conversor import conversor_engine as CE
    h, w = rgba.shape[:2]
    k = _escala_trabalho(w, h)
    k = min(k, 2400 / max(w, h))
    trab = _redimensionar(rgba, k)
    cinza = cv2.cvtColor(_achatar(trab), cv2.COLOR_RGB2GRAY)
    cinza = cv2.bilateralFilter(cinza, 7, 30, 7)
    otsu, _ = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bloco = max(31, (min(cinza.shape) // 8) | 1)
    adapt = cv2.adaptiveThreshold(cinza, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, bloco, 12)
    # adaptativo só onde o papel tem sombra (variação grande no fundo)
    fundo = cv2.GaussianBlur(cinza, (0, 0), max(5, min(cinza.shape) / 30))
    tinta = (adapt == 0) if fundo.std() > 18 else (cinza < otsu)
    tinta &= _opaco(trab)
    opts = {'despeckle': int(max(0, 30 - 0.28 * detalhe) * max(1, k) ** 0.5), 'smooth': round(0.6 + suavidade / 150, 3),
            'optimize': 0.2}
    if modo == 'centro':
        linhas = CE._centerline(tinta, opts)
        return [{'cor': (0, 0, 0), 'regra': 'linha', 'subs': [[(x / k, y / k) for x, y in l] for l in linhas],
                 'espessura': _espessura(tinta) / k}]
    subs = CE._scale_cmds(CE._potrace_curves(tinta, opts), 1 / k)
    return [{'cor': (0, 0, 0), 'regra': 'evenodd', 'subs': subs}] if subs else []


def _espessura(tinta):
    from scipy.ndimage import distance_transform_edt
    from skimage.morphology import skeletonize
    esq = skeletonize(tinta)
    return float(np.median(distance_transform_edt(tinta)[esq]) * 2) if esq.any() else 2.0


# ---------------------------------------------------------------- SVG ---

def _n(v):
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def caminho_d(subs):
    d = []
    for cmds in subs:
        for c in cmds:
            if c[0] == 'M':
                d.append(f'M{_n(c[1][0])} {_n(c[1][1])}')
            elif c[0] == 'L':
                d.append(f'L{_n(c[1][0])} {_n(c[1][1])}')
            else:
                d.append('C' + ' '.join(f'{_n(p[0])} {_n(p[1])}' for p in c[1:]))
        d.append('Z')
    return ''.join(d)


def hexa(cor):
    return '#%02x%02x%02x' % tuple(int(v) for v in cor)


def montar_svg(formas, w, h, fundo=None, contorno=False):
    """fundo: cor de fundo (None = transparente). contorno: mostra só as linhas (inspeção)."""
    partes = ['<?xml version="1.0" encoding="UTF-8"?>',
              f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{w}" height="{h}" viewBox="0 0 {w} {h}">']
    if fundo is not None:
        partes.append(f'<rect width="{w}" height="{h}" fill="{hexa(fundo)}"/>')
    for f in formas:
        cor = hexa(f['cor'])
        if f['regra'] == 'linha':
            esp = _n(f.get('espessura', 2))
            for linha in f['subs']:
                pts = ' '.join(f'{_n(x)},{_n(y)}' for x, y in linha)
                partes.append(f'<polyline points="{pts}" fill="none" stroke="{cor}" stroke-width="{esp}" '
                              'stroke-linecap="round" stroke-linejoin="round"/>')
            continue
        regra = ' fill-rule="evenodd"' if f['regra'] == 'evenodd' else ''
        if contorno:
            # traço de "caneta de plotter": magenta sobre um contorno escuro, visível em qualquer cor
            d = caminho_d(f['subs'])
            partes.append(f'<path d="{d}" fill="none" stroke="#1b1f24" stroke-opacity=".5" stroke-width="3" vector-effect="non-scaling-stroke"/>')
            partes.append(f'<path d="{d}" fill="none" stroke="#ff2d87" stroke-width="1.2" vector-effect="non-scaling-stroke"/>')
        else:
            partes.append(f'<path d="{caminho_d(f["subs"])}" fill="{cor}"{regra}/>')
    partes.append('</svg>')
    return '\n'.join(partes)


def contar(formas):
    nos = sum(len(c) for f in formas for c in f['subs'])
    return {'formas': len(formas), 'caminhos': sum(len(f['subs']) for f in formas), 'nos': nos}


# ----------------------------------------------------------- render/medir ---

def renderizar(svg, lado, fundo=None):
    """SVG -> PIL RGBA com o lado maior = `lado` px (PyMuPDF; mesmo motor do PDF)."""
    import pymupdf
    doc = pymupdf.open(stream=svg.encode('utf-8'), filetype='svg')
    pg = doc[0]
    z = lado / max(pg.rect.width, pg.rect.height)
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=fundo is None)
    modo = 'RGBA' if pix.alpha else 'RGB'
    im = Image.frombytes(modo, (pix.width, pix.height), pix.samples)
    if fundo is not None and modo == 'RGB':
        return im.convert('RGBA')
    return im


def cor_papel(rgba):
    """Cor típica do fundo claro (papel) de um desenho escaneado."""
    rgb = _achatar(rgba)
    cinza = rgb.mean(2)
    claro = cinza > np.percentile(cinza, 40)
    return tuple(int(v) for v in np.median(rgb[claro], axis=0)) if claro.any() else (255, 255, 255)


def fidelidade(rgba, svg, lado=700, fundo=None):
    """0-100: estrutura (SSIM) + cor (ΔE médio), comparando no mesmo tamanho.
    `fundo`: cor sob o vetor na comparação (o papel, num escaneado)."""
    from skimage.metrics import structural_similarity
    from skimage.color import rgb2lab
    h, w = rgba.shape[:2]
    k = min(1.0, lado / max(w, h))
    alvo = (max(1, round(w * k)), max(1, round(h * k)))
    orig = _achatar(np.asarray(Image.fromarray(rgba, 'RGBA').resize(alvo, Image.LANCZOS)))
    rend = renderizar(svg, max(alvo))
    rend = np.asarray(rend.resize(alvo, Image.LANCZOS))
    rend = _achatar(rend, fundo or (255, 255, 255)) if rend.shape[2] == 4 else rend
    s = structural_similarity(orig, rend, channel_axis=2, data_range=255)
    de = float(np.linalg.norm(rgb2lab(orig) - rgb2lab(rend), axis=2).mean())
    return float(round(100 * (0.6 * max(0.0, s) + 0.4 * max(0.0, 1 - de / 25)), 1)), round(de, 2)


# --------------------------------------------------- exportar (Conversor) ---

def para_trace_result(formas, w, h, dpi=96):
    """Formas -> TraceResult do Conversor (EPS e DXF)."""
    from Conversor import conversor_engine as CE
    camadas = []
    for i, f in enumerate(formas):
        nome = f'COR_{i + 1}_{hexa(f["cor"])[1:].upper()}'
        if f['regra'] == 'linha':
            camadas.append({'name': nome, 'color': f['cor'], 'kind': 'line', 'curves': f['subs']})
        else:
            camadas.append({'name': nome, 'color': f['cor'], 'kind': 'fill', 'curves': f['subs']})
    return CE.TraceResult(w, h, dpi, camadas)


# ------------------------------------------------------------- orquestração ---

PADRAO = {
    'tipo': 'auto',            # auto | pixel | logo | traco | foto
    'pixel_estilo': 'exato',   # exato | suave
    'foto_estilo': 'poster',   # poster | detalhado
    'traco_modo': 'contorno',  # contorno | centro
    'cores': 0,                # 0 = automático
    'suavidade': 55,           # 0..100
    'detalhe': 50,             # 0..100
    'fundo': 'manter',         # manter | remover | ia
    'travadas': [],            # cores da marca ['#rrggbb']
    'mapa': {},                # edições da paleta {i: {para|hex|apagar}}
}


def _hex_rgb(h):
    h = str(h).lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) if re.fullmatch(r'[0-9a-fA-F]{6}', h) else None


def normalizar(op):
    o = dict(PADRAO)
    o.update({k: v for k, v in (op or {}).items() if k in PADRAO})
    for k in ('suavidade', 'detalhe'):
        try:
            o[k] = max(0, min(100, int(o[k])))
        except (TypeError, ValueError):
            o[k] = PADRAO[k]
    try:
        o['cores'] = max(0, min(64, int(o['cores'])))
    except (TypeError, ValueError):
        o['cores'] = 0
    o['travadas'] = [t for t in (_hex_rgb(x) for x in (o['travadas'] or [])[:16]) if t]
    if not isinstance(o['mapa'], dict):
        o['mapa'] = {}
    return o


def _pixel(rgba, info, o, mascara_ia):
    s = max(1, info['grade'])
    ox, oy = info['grade_x'], info['grade_y']
    h, w = rgba.shape[:2]
    # completa as células cortadas nas bordas (repete a borda) para a grade cobrir tudo
    pl, pt = (s - ox) % s, (s - oy) % s
    pr, pb = (-(w + pl)) % s, (-(h + pt)) % s
    if mascara_ia is not None:
        rgba = rgba.copy()
        rgba[..., 3] = np.minimum(rgba[..., 3], mascara_ia)
    cheia = np.pad(rgba, ((pt, pb), (pl, pr), (0, 0)), mode='edge') if (pl or pt or pr or pb) else rgba
    grade = reduzir_grade(cheia, s, 0, 0)
    sujo = ruido_celulas(cheia, s) > 2.5 or (s == 1 and _cores_dominantes(_achatar(rgba), _opaco(rgba)) > 24)
    cent = paleta_pixel(grade, sujo)
    if o['travadas']:
        trav = _lab(np.array(o['travadas'], np.uint8))
        for t in trav:   # a cor da paleta mais parecida vira a cor da marca
            i = np.sqrt(((cent - t) ** 2).sum(1)).argmin()
            if np.sqrt(((cent[i] - t) ** 2).sum()) < 20:
                cent[i] = t
    transp = ~_opaco(grade)
    idx = indexar(grade[..., :3], cent)
    if sujo:
        idx = fundir_sangria(idx, cent, transp)
    return grade, cent, idx, transp, (s, -pl, -pt)


def vetorizar(rgba, info, op, mascara_ia=None):
    """-> {'formas', 'paleta', 'tipo', 'fundo'(rgb|None), 'pixel'(dados da grade)}"""
    o = normalizar(op)
    tipo = info['tipo'] if o['tipo'] == 'auto' else o['tipo']
    if tipo not in ('pixel', 'logo', 'traco', 'foto'):
        tipo = 'logo'
    h, w = rgba.shape[:2]
    res = {'tipo': tipo, 'paleta': [], 'fundo_removido': None}
    f_original = None

    if tipo == 'traco':
        trab = rgba
        if mascara_ia is not None:
            trab = rgba.copy()
            trab[..., 3] = np.minimum(trab[..., 3], mascara_ia)
        res['formas'] = tracar_traco(trab, o['traco_modo'], o['detalhe'], o['suavidade'])
        if not res['formas'] or not any(f['subs'] for f in res['formas']):
            raise VetorizarError('Não achei traços nesta imagem. Tente o tipo "Logo / ilustração".')
        return res

    if tipo == 'pixel':
        if info['grade'] < 1 or max(w, h) // max(1, info['grade']) > GRADE_MAX:
            raise VetorizarError('A grade desta imagem é grande demais para pixel art. Use "Logo / ilustração".')
        grade, cent, idx, transp, (s, ox, oy) = _pixel(rgba, info, o, mascara_ia)
    else:
        k_cores = o['cores'] or ((32 if o['foto_estilo'] == 'detalhado' else 12) if tipo == 'foto' else 0)
        prep = preparar_cores(rgba, k_cores, o['travadas'], o['detalhe'], mascara_ia)
        cent, idx, transp = prep['cent'], prep['idx'], prep['transp']

    if mascara_ia is not None:
        # a cor que dominava a borda antes do recorte (o fundo de verdade)
        borda_rgb = np.concatenate([rgba[0, :, :3], rgba[-1, :, :3], rgba[:, 0, :3], rgba[:, -1, :3]])
        f_original = int(np.bincount(indexar(borda_rgb.reshape(1, -1, 3), cent).ravel()).argmax())
    res['paleta'] = resumo_paleta(idx, cent, transp)
    idx, cent, apagar = aplicar_mapa(idx, cent, o['mapa'])
    finais = _rgb_de_lab(cent)
    for item in res['paleta']:
        acao = (o['mapa'] or {}).get(str(item['i'])) or {}
        item['hex_final'] = hexa(finais[item['i']])
        item['apagada'] = bool(apagar[item['i']])
        if acao.get('para') is not None:
            item['juntada_em'] = int(acao['para'])
    if o['fundo'] == 'ia' and mascara_ia is not None and f_original is not None:
        m = mascara_fundo(idx, transp, f_original, pela_transparencia=True)
        if m is not None:
            transp = transp | m
    transp = transp | apagar[idx]
    if o['fundo'] == 'remover':
        m = mascara_fundo(idx, transp)
        if m is not None:
            transp = transp | m
            res['fundo_removido'] = True
    if transp.all():
        raise VetorizarError('Sobrou só fundo: todas as cores foram apagadas.')

    if tipo == 'pixel':
        if o['pixel_estilo'] == 'suave':
            g, fator = idx.copy(), 1
            g[transp] = len(cent)            # transparente vira uma "cor" a mais, para o EPX respeitar a borda
            while max(g.shape) * 2 <= 1024 and fator < 8:
                g, fator = _epx(g), fator * 2
            ampl = max(1, int(np.ceil(1000 / max(g.shape))))
            if ampl > 1:
                g = np.repeat(np.repeat(g, ampl, 0), ampl, 1)
            # arredonda na resolução final: some com os degraus que o EPX deixa
            g = _arredondar_mapa(g, sigma=max(1.0, 0.45 * ampl * fator / 2 + 0.6 * ampl))
            t2 = g == len(cent)
            g = np.where(t2, 0, g)
            cores = _rgb_de_lab(cent)
            esc = s / (fator * ampl)
            fundo, t2 = _separar_fundo(g, t2, cores, g.shape[1], g.shape[0], esc, ox, oy)
            rgba2 = _mapa_para_rgba(g, cores, t2)
            par = _params_vtracer(max(o['suavidade'], 70), o['detalhe'], 1.0)
            par['filter_speckle'] = max(1, ampl * fator // 4)
            formas = ([fundo] if fundo else []) + _svg_para_formas(_vtracer(rgba2, **par), esc, ox, oy)
            res['formas'] = encaixar_na_paleta(formas, cores, cent)
        else:
            res['formas'] = tracar_pixel_exato(idx, _rgb_de_lab(cent), transp, s, ox, oy)
        res['pixel'] = {'s': s, 'celulas': [int(idx.shape[1]), int(idx.shape[0])]}
    else:
        res['formas'] = tracar_cores(prep, cent, idx, transp, o['suavidade'], o['detalhe'])
    if not res['formas']:
        raise VetorizarError('Não sobrou nenhuma forma. Diminua a limpeza (mais detalhe) ou mude o tipo.')
    return res
