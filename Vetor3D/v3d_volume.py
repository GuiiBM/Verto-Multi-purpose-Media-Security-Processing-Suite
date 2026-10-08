"""Vetor3D · modo "personagem 3D": imagem sem fundo -> volume fechado, 360°.

Não é extrusão: a silhueta ganha corpo de verdade.

1. Inflação: resolve a equação de Poisson (Δu = -1 dentro da silhueta, u = 0
   na borda) e usa sqrt(2u) como meia-espessura. Partes finas (braços, cauda,
   orelhas) ficam roliças, com seção redonda; partes largas são limitadas pela
   "profundidade" escolhida (tronco achatado como um corpo, não um balão).
2. Profundidade por IA (Depth Anything V2 Small, local, ~100 MB, baixado uma
   vez): desloca cada parte para a frente ou para trás (o braço na frente do
   corpo, a luneta apontando para a câmera) e acrescenta o relevo fino.
3. O traço do desenho vira um sulco leve (contorno marcado no volume).
4. Superfície: campo F(x,y,z) = min(frente - z, z - costas), malha por
   marching cubes (fechada por construção), suavizada (Taubin) e reduzida.
5. Textura: atlas com a imagem na frente e uma versão lisa (borrada) nas
   costas, para não ter "rosto nas costas".

Saída: uma "parte" com v, f, n (normais), uv e o caminho da textura, em mm.
"""
import os

import numpy as np

_PIPE = {}


class VolumeError(Exception):
    pass


def profundidade(rgb, cache):
    """Mapa de profundidade relativa (maior = mais perto), mesmo tamanho da
    imagem. Volta None se o modelo não estiver disponível (sem internet na
    primeira vez, ou transformers/torch ausentes)."""
    if cache and os.path.exists(cache):
        try:
            d = np.load(cache)
            if d.shape == rgb.shape[:2]:
                return d
        except Exception:
            pass
    try:
        from PIL import Image
        if 'pipe' not in _PIPE:
            import torch
            from transformers import pipeline
            torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
            _PIPE['pipe'] = pipeline('depth-estimation', model='depth-anything/Depth-Anything-V2-Small-hf',
                                     device='cpu')
        out = _PIPE['pipe'](Image.fromarray(rgb))
        d = out['predicted_depth']
        d = d.detach().cpu().numpy() if hasattr(d, 'detach') else np.asarray(d)
        d = np.squeeze(d).astype(np.float32)
        if d.shape != rgb.shape[:2]:
            from scipy.ndimage import zoom
            d = zoom(d, (rgb.shape[0] / d.shape[0], rgb.shape[1] / d.shape[1]), order=1)
        if cache:
            np.save(cache, d)
        return d
    except Exception:
        return None
    finally:
        # ~900 MB: não fica preso no processo (o resultado já está em cache no projeto)
        if _PIPE:
            _PIPE.clear()
            import gc
            gc.collect()


def _poisson(mask):
    """u com Δu = -1 dentro da máscara e u = 0 fora (grade em pixels)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    h, w = mask.shape
    idx = -np.ones((h, w), np.int64)
    ys, xs = np.nonzero(mask)
    n = len(ys)
    idx[ys, xs] = np.arange(n)
    lin = [np.arange(n)]
    col = [np.arange(n)]
    val = [np.full(n, 4.0)]
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        yy, xx = ys + dy, xs + dx
        ok = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < w)
        viz = np.full(n, -1, np.int64)
        viz[ok] = idx[yy[ok], xx[ok]]
        sel = viz >= 0
        lin.append(np.flatnonzero(sel))
        col.append(viz[sel])
        val.append(np.full(sel.sum(), -1.0))
    A = coo_matrix((np.concatenate(val), (np.concatenate(lin), np.concatenate(col))), shape=(n, n)).tocsr()
    u = spsolve(A, np.ones(n))
    out = np.zeros((h, w), np.float32)
    out[ys, xs] = np.maximum(u, 0)
    return out


def _preencher_bordas(rgba):
    """Pixels transparentes recebem a cor do pixel visível mais próximo
    (a textura não fica com halo branco/preto na borda da silhueta)."""
    from scipy.ndimage import distance_transform_edt
    vis = rgba[..., 3] > 127
    if vis.all():
        return rgba[..., :3].copy()
    _, (iy, ix) = distance_transform_edt(~vis, return_indices=True)
    return rgba[iy, ix, :3]


def costurar_uv(v, f, uvmap):
    """Malha soldada (mm) -> vértices separados por lado (frente usa a metade
    esquerda do atlas, costas a direita), com normais suaves e UV."""
    import trimesh
    m = trimesh.Trimesh(v, f, process=False)
    vn = m.vertex_normals
    lado = (m.face_normals[:, 2] < 0).astype(np.int64)          # 1 = costas
    chave = np.asarray(f) * 2 + lado[:, None]
    uniq, inv = np.unique(chave.reshape(-1), return_inverse=True)
    vid = uniq // 2
    lado_v = uniq % 2
    V = np.asarray(v)[vid]
    N = vn[vid]
    F2 = inv.reshape(-1, 3)
    px = V[:, 0] / uvmap['mm'] + uvmap['cx']
    py = -V[:, 1] / uvmap['mm'] + uvmap['cy']
    u = np.clip(px / uvmap['gw'], 0, 1) * 0.5 + 0.5 * lado_v
    vv = 1 - np.clip(py / uvmap['gh'], 0, 1)
    return V, F2, N, np.column_stack([u, vv])


def construir(pasta, peca, largura_mm, q, progresso=lambda e, f: None):
    from PIL import Image, ImageFilter
    from scipy import ndimage as ndi
    from skimage.measure import marching_cubes
    import trimesh

    caminho = os.path.join(pasta, 'sem_fundo.png')
    if not os.path.exists(caminho):
        raise VolumeError('A imagem sem fundo não foi encontrada: reprocesse a imagem.')
    progresso('Preparando a silhueta', 0.03)
    rgba = np.asarray(Image.open(caminho).convert('RGBA'))
    vis = rgba[..., 3] > 127
    ys, xs = np.nonzero(vis)
    if len(ys) < 100:
        raise VolumeError('A silhueta está vazia.')
    pad = 4
    y0, y1 = max(0, ys.min() - pad), min(rgba.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(rgba.shape[1], xs.max() + pad + 1)
    rgba = rgba[y0:y1, x0:x1]
    H, W = rgba.shape[:2]
    rgb = _preencher_bordas(rgba)

    # grade de trabalho
    res = int(q.get('vol_res', 400))
    esc = min(1.0, res / max(H, W))
    gh, gw = max(8, round(H * esc)), max(8, round(W * esc))
    alfa = np.asarray(Image.fromarray(rgba[..., 3]).resize((gw, gh), Image.BILINEAR)).astype(np.float32) / 255
    mask = alfa > 0.5
    mask = ndi.binary_opening(mask, iterations=1) | (alfa > 0.85)
    rot, n = ndi.label(mask)
    if n > 1:   # some com sujeira solta
        tam = ndi.sum(mask, rot, np.arange(1, n + 1))
        mask = np.isin(rot, np.flatnonzero(tam >= max(20, tam.max() * 0.002)) + 1)

    # 1) inflação (Poisson em no máximo ~360 px, depois ampliada)
    progresso('Calculando o volume (Poisson)', 0.1)
    ep = min(1.0, 360 / max(gh, gw))
    if ep < 1:
        mp = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(
            (max(4, round(gw * ep)), max(4, round(gh * ep))), Image.BILINEAR)) > 127
        u = _poisson(mp)
        r = np.sqrt(2 * u) / ep
        r = np.asarray(Image.fromarray(r).resize((gw, gh), Image.BILINEAR))
    else:
        r = np.sqrt(2 * _poisson(mask))
    r = np.where(mask, r, 0)
    r = ndi.gaussian_filter(r, 0.8) * mask
    larg_px = max(gw, 1)
    prof = float(peca.get('profundidade', 0.45))        # espessura máxima / largura
    T = max(1.0, prof * larg_px / 2)                    # meia-espessura máxima (px)
    k = float(peca.get('volume', 1.0))
    meia = T * np.tanh(k * r / T)                       # finos redondos, largos limitados

    # 2) profundidade por IA
    progresso('Profundidade por IA (Depth Anything)', 0.25)
    centro = np.zeros_like(meia)
    detalhe_rel = np.zeros_like(meia)
    aviso = None
    alfa_d = float(peca.get('detalhe', 0.6))
    if alfa_d > 0:
        d = profundidade(rgb, os.path.join(pasta, f'profundidade_{x0}_{y0}_{W}x{H}.npy'))
        if d is None:
            aviso = ('Sem o modelo de profundidade (precisa de internet só na primeira vez): '
                     'o volume foi feito só pela silhueta.')
        else:
            dg = np.asarray(Image.fromarray(d.astype(np.float32)).resize((gw, gh), Image.BILINEAR))
            vals = dg[mask]
            p5, p95 = np.percentile(vals, 5), np.percentile(vals, 95)
            dn = np.clip((dg - p5) / max(p95 - p5, 1e-6), 0, 1)
            med = np.median(dn[mask])
            grande = ndi.gaussian_filter(dn, max(2, larg_px / 60))
            centro = alfa_d * 0.9 * T * (grande - med)
            detalhe_rel = alfa_d * 0.35 * T * (dn - grande)

    # 3) traço como sulco
    sulco = np.zeros_like(meia)
    beta = float(peca.get('traco', 0.5))
    if beta > 0:
        lum = (rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32))
        lum_g = np.asarray(Image.fromarray(lum).resize((gw, gh), Image.BILINEAR))
        tinta = np.clip((150 - lum_g) / 90, 0, 1)
        tinta = ndi.gaussian_filter(tinta, 0.7)
        borda = np.clip(ndi.distance_transform_edt(mask) / 3, 0, 1)   # não fura a silhueta
        sulco = beta * max(0.6, larg_px / 260) * tinta * borda

    costas_razao = 0.85
    frente = centro + meia + detalhe_rel * mask - sulco
    costas = centro - meia * costas_razao
    # suaviza o encontro na borda (frente e costas se juntam exatamente)
    frente = np.where(mask, np.maximum(frente, costas + 0.05 * meia), 0)
    fora = ndi.distance_transform_edt(~mask).astype(np.float32)
    dentro = ndi.distance_transform_edt(mask).astype(np.float32)
    borda_c = np.where(mask, centro, ndi.grey_dilation(centro, size=3))
    frente = np.where(mask, frente, borda_c - fora)
    costas = np.where(mask, costas, borda_c + fora)

    # 4) campo e marching cubes
    progresso('Gerando a superfície (marching cubes)', 0.45)
    zmin = float(np.floor(costas[mask].min() - 2))
    zmax = float(np.ceil(frente[mask].max() + 2))
    passo = max(0.5, (zmax - zmin) / max(16, int(q.get('vol_res', 400) * 0.6)))
    zs = np.arange(zmin, zmax + passo, passo, dtype=np.float32)
    nz = len(zs)
    F = np.empty((nz, gh, gw), np.float32)
    for i, z in enumerate(zs):
        np.minimum(frente - z, z - costas, out=F[i])
    F = np.pad(F, 1, constant_values=-1.0)
    v, f, _, _ = marching_cubes(F, level=0.0, allow_degenerate=False)
    del F
    # (z, y, x) -> (x, y, z) em px da grade
    v = np.column_stack([v[:, 2] - 1, v[:, 1] - 1, (v[:, 0] - 1) * passo + zmin])
    m = trimesh.Trimesh(v, f[:, ::-1], process=True)
    if m.volume < 0:
        m.invert()
    progresso('Suavizando a malha', 0.62)
    trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=-0.53, iterations=8)
    alvo = int(q.get('vol_tri', 200000))
    if len(m.faces) > alvo:
        progresso(f'Reduzindo para {alvo // 1000} mil triângulos', 0.72)
        import fast_simplification
        vv, ff = fast_simplification.simplify(m.vertices.astype(np.float32), m.faces.astype(np.int32),
                                              target_reduction=1 - alvo / len(m.faces))
        m = trimesh.Trimesh(vv.astype(np.float64), ff.astype(np.int64), process=True)
        trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=-0.53, iterations=3)
    estanque = bool(m.is_watertight)

    # 5) textura: frente (imagem) | costas (lisa)
    progresso('Montando a textura', 0.82)
    tw = min(2048, max(512, W))
    th = max(1, round(H * tw / W))
    frente_img = Image.fromarray(rgb).resize((tw, th), Image.LANCZOS)
    if peca.get('costas', 'lisa') == 'imagem':
        costas_img = frente_img
    else:
        costas_img = frente_img.filter(ImageFilter.GaussianBlur(max(6, tw / 90)))
        costas_img = Image.fromarray((np.asarray(costas_img).astype(np.float32) * 0.82).astype(np.uint8))
    atlas = Image.new('RGB', (tw * 2, th))
    atlas.paste(frente_img, (0, 0))
    atlas.paste(costas_img, (tw, 0))
    tex = os.path.join(pasta, 'textura.jpg')
    atlas.save(tex, quality=90)

    # px da grade -> mm (centro da caixa da silhueta = origem, y para cima)
    mm = float(largura_mm) / max(1, (xs.max() - xs.min() + 1) * esc)
    cx = ((xs.min() + xs.max()) / 2 - x0) * esc
    cy = ((ys.min() + ys.max()) / 2 - y0) * esc
    Vmm = np.column_stack([(m.vertices[:, 0] - cx) * mm, -(m.vertices[:, 1] - cy) * mm, m.vertices[:, 2] * mm])
    uvmap = {'mm': mm, 'cx': float(cx), 'cy': float(cy), 'gw': int(gw), 'gh': int(gh)}
    V, F2, N, UV = costurar_uv(Vmm, m.faces[:, ::-1], uvmap)   # o espelho em y inverte a orientação
    media = np.asarray(frente_img).reshape(-1, 3)[::97].mean(axis=0)
    cor = '#%02x%02x%02x' % tuple(int(c) for c in media)
    parte = {'v': V, 'f': F2, 'n': N, 'uv': UV, 'uvmap': uvmap, 'textura': tex, 'cor': cor,
             'metal': float(peca.get('metal', 0.0)), 'rugosidade': float(peca.get('rugosidade', 0.55))}
    info = {'estanque': estanque, 'grade': [gw, gh, nz], 'aviso': aviso}
    return parte, info
