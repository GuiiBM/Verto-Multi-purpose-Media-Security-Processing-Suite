"""Vetor3D · modo "personagem 3D": reconstrução 360° fiel ao desenho.

Duas fontes, cada uma no que faz melhor:

- O DESENHO manda na forma vista de frente. A silhueta do modelo, vista da
  câmera, coincide com a do desenho (um "cone" que sai da câmera e passa pelo
  contorno da imagem limita o volume), e a frente recebe a imagem original
  em alta resolução como textura.
- A REDE de reconstrução (TripoSR, Stability AI + Tripo AI, licença MIT,
  ~1,7 GB baixados uma vez) dá o volume que a imagem não mostra: costas,
  lados, o que está na frente ou atrás de quê.

Etapas:
1. Imagem: recorte centralizado (85% de ocupação). A rede recebe 512 px; o
   resto do processo usa a imagem em alta (até 4096 px).
2. Rede: triplano (cache por imagem no projeto).
3. Corpo: densidade da rede numa grade de 256³ convertida em distância
   assinada; perto da superfície a distância vem do campo contínuo (sem
   degraus de voxel). Também em cache.
4. Mapas 2D (grade de 512): onde a rede cobre a imagem, frente/fundo do corpo
   em cada pixel e uma DEFORMAÇÃO que leva a silhueta da rede para a do
   desenho (Newton sobre as distâncias assinadas 2D): o corpo é puxado para
   o contorno do desenho em vez de cortado (sem paredes retas). Partes que a
   rede perdeu (cauda, antena, pontas) viram tubos redondos com a espessura
   da largura da parte no desenho, a frente alinhada ao corpo vizinho.
5. Campo e malha: campo = mín(cone do desenho, máx(corpo deformado,
   preenchimento)) com uniões e cortes suaves, numa grade fina (até ~1000
   voxels no lado maior) processada em fatias com orçamento de memória e
   pulando colunas fora da silhueta; marching cubes por fatia, costura
   exata, peças soltas removidas, suavização Taubin (não encolhe).
6. Textura: atlas UV por projeção em ilhas; frente = imagem original
   projetada pela câmera da rede onde a superfície é visível (teste de
   profundidade); costas/lados = cor de base da frente (sem os traços) levada
   ao ponto escondido mais próximo em 3D, combinada com a cor da rede (ajustada
   à paleta). Assada em blocos (4096 px no HD sem estourar a memória).

Saída: uma "parte" (v, f, n, uv, textura) em mm, como o v3d_volume.
"""
import gc
import hashlib
import json
import os
import time

import numpy as np

REPO = 'stabilityai/TripoSR'
LADO_ENTRADA = 512
OCUPACAO = 0.85
DIST_CAMERA = 1.9
FOV_GRAUS = 40.0
LIMIAR = 25.0
GRADE_2D = 512
GRADE_CORPO = 256
PROFUNDIDADE_MAX = 2.5   # meia-profundidade máxima em relação ao raio local no desenho
VERSAO_CORPO = 5          # muda quando o cálculo do corpo muda (invalida o cache)

# Qualidade de cada nível. Não depende do perfil de hardware: máquina fraca
# demora mais (fatias menores), mas o resultado é o mesmo.
QUALIDADE = {
    'preview': {'N': 420, 'tex': 2048, 'quad': 2048, 'tri_max': 900_000, 'taubin': 10},
    'hd': {'N': 1000, 'tex': 4096, 'quad': 4096, 'tri_max': 3_000_000, 'taubin': 24},
}

# Custo de cada etapa nesta classe de máquina (s), ajustado pelo ritmo medido
# (arquivo de ritmo no cache do usuário). Usado no progresso e no tempo estimado.
CUSTO_BASE = {
    'imagem': 3.0, 'modelo': 9.0, 'rede': 32.0, 'corpo': 80.0, 'mapas': 14.0,
    'rede_max': 440.0, 'corpo_max': 90.0, 'download_bps': 5 * 1024 * 1024,
    'campo_voxel': 0.75e-6, 'malha_tri': 5e-6, 'uv_tri': 4e-6, 'textura_texel': 3.2e-6,
    'textura_base': 8.0, 'saida_tri': 6e-6,
}
_RITMO = os.path.join(os.path.expanduser('~'), '.cache', 'verto', 'vetor3d_ritmo.json')


class ReconstrucaoError(Exception):
    pass


def ritmo():
    try:
        with open(_RITMO, encoding='utf-8') as fh:
            r = json.load(fh)
        return {k: float(v) for k, v in r.items() if isinstance(v, (int, float)) and 0.1 < float(v) < 20}
    except (OSError, ValueError):
        return {}


def registrar_ritmo(medido, previsto):
    """Guarda quanto cada etapa demorou em relação ao previsto (média móvel)."""
    r = ritmo()
    for k, seg in medido.items():
        p = previsto.get(k)
        # etapas que vieram do cache (previsão fixa curta) não dizem nada do ritmo
        if not p or p <= 2.0 or seg <= 0:
            continue
        fator = max(0.2, min(10.0, seg / p * r.get(k, 1.0)))
        r[k] = fator if k not in r else r[k] * 0.6 + fator * 0.4
    try:
        os.makedirs(os.path.dirname(_RITMO), exist_ok=True)
        with open(_RITMO + '.tmp', 'w', encoding='utf-8') as fh:
            json.dump(r, fh)
        os.replace(_RITMO + '.tmp', _RITMO)
    except OSError:
        pass


def plano_etapas(pasta, nivel, largura_px=None, altura_px=None, motor='leve', baixar_bytes=0):
    """Etapas e segundos previstos. Rápido (sem rede): serve para o tempo
    estimado da fila antes de a etapa começar."""
    q = QUALIDADE[nivel]
    r = ritmo()
    c = lambda k, v: v * r.get(k, 1.0)
    import glob
    tem_rede = bool(glob.glob(os.path.join(pasta, 'triplano_*.pt')))
    tem_corpo = bool(glob.glob(os.path.join(pasta, f'corpo_v{VERSAO_CORPO}_*.npz')))
    asp = 1.0
    if largura_px and altura_px:
        asp = min(largura_px, altura_px) / max(largura_px, altura_px)
    n = q['N']
    voxels = n * (n * asp) * (n * 0.45) * 0.6            # colunas fora da silhueta são puladas
    tris = min(q['tri_max'], 2.6 * n * n * (0.5 + asp))
    texels = q['tex'] ** 2 * 0.5
    if motor == 'maximo':
        tem_max = bool(glob.glob(os.path.join(pasta, 'hunyuan_*.npz')))
        tem_cmax = bool(glob.glob(os.path.join(pasta, f'corpo_hy_v*.{VERSAO_CORPO}_*.npz')))
        inicio = [
            ('imagem', 'Preparando a imagem', c('imagem', CUSTO_BASE['imagem'])),
            ('modelo', 'Baixando o modelo de máxima qualidade' if baixar_bytes else 'Verificando o modelo de IA',
             baixar_bytes / CUSTO_BASE['download_bps'] if baixar_bytes else 1.0),
            ('rede_max', 'IA gerando a forma 3D (máxima qualidade)', c('rede_max', CUSTO_BASE['rede_max']) if not tem_max else 1.0),
            ('corpo_max', 'Preparando o corpo 3D', c('corpo_max', CUSTO_BASE['corpo_max']) if not tem_cmax else 2.0),
        ]
    else:
        inicio = [
            ('imagem', 'Preparando a imagem', c('imagem', CUSTO_BASE['imagem'])),
            ('modelo', 'Carregando o modelo de reconstrução 3D', c('modelo', CUSTO_BASE['modelo'])),
            ('rede', 'Reconstruindo o volume (rede neural)', c('rede', CUSTO_BASE['rede']) if not tem_rede else 1.0),
            ('corpo', 'Calculando o corpo 3D', c('corpo', CUSTO_BASE['corpo']) if not tem_corpo else 2.0),
        ]
    etapas = inicio + [
        ('mapas', 'Ajustando o corpo à silhueta do desenho', c('mapas', CUSTO_BASE['mapas'])),
        ('campo', 'Esculpindo a superfície em alta resolução', c('campo', voxels * CUSTO_BASE['campo_voxel'])),
        ('malha', 'Acabamento da malha', c('malha', tris * CUSTO_BASE['malha_tri'])),
        ('uv', 'Abrindo a malha em UV', c('uv', tris * CUSTO_BASE['uv_tri'])),
        ('textura', 'Pintando a textura', c('textura', CUSTO_BASE['textura_base'] + texels * CUSTO_BASE['textura_texel'])),
        ('saida', 'Gravando o modelo', c('saida', tris * CUSTO_BASE['saida_tri'])),
    ]
    return etapas


class Plano:
    """Progresso por etapas com peso pelo tempo previsto de cada uma (a barra
    e o "falta ~" ficam proporcionais ao tempo de verdade)."""

    def __init__(self, progresso, etapas, inicio=0.0, fim=1.0):
        self.p = progresso
        self.etapas = etapas
        self.inicio, self.fim = inicio, fim
        self.prev = {k: max(0.05, s) for k, _, s in etapas}
        self.rot = {k: r for k, r, _ in etapas}
        tot = sum(self.prev.values())
        acc = 0.0
        self.base = {}
        for k, _, _ in etapas:
            self.base[k] = acc / tot
            acc += self.prev[k]
        self.tot = tot
        self.atual = None
        self.t0 = None
        self.medido = {}

    def __call__(self, chave, frac=0.0, rotulo=None):
        agora = time.time()
        if chave not in self.base:            # etapa fora do plano (ex.: troca de motor no meio)
            self.p(rotulo or chave, self.ultimo if hasattr(self, 'ultimo') else self.inicio)
            return
        if chave != self.atual:
            if self.atual is not None:
                self.medido[self.atual] = self.medido.get(self.atual, 0.0) + agora - self.t0
            self.atual, self.t0 = chave, agora
        f = self.base[chave] + self.prev[chave] / self.tot * min(1.0, max(0.0, frac))
        self.ultimo = self.inicio + (self.fim - self.inicio) * f
        self.p(rotulo or self.rot[chave], self.ultimo)

    def encerrar(self):
        if self.atual is not None:
            self.medido[self.atual] = self.medido.get(self.atual, 0.0) + time.time() - self.t0
            self.atual = None
        return self.medido


# ---------------------------------------------------------------------------
# Rasterizador (numpy): usado para a visibilidade e para assar a textura
# ---------------------------------------------------------------------------

def rasterizar(xy, tri, largura, altura, z=None, lote=600_000):
    """Preenche os pixels cujo centro cai dentro de cada triângulo.

    xy: (N, 2) posição dos vértices em pixels; tri: (M, 3).
    Com z, guarda só o triângulo mais próximo (menor z) de cada pixel.
    Volta (id do triângulo por pixel, -1 = vazio) e baricêntricas (H, W, 3).
    """
    xy = np.asarray(xy, np.float64)
    tri = np.asarray(tri, np.int64)
    ids = np.full(altura * largura, -1, np.int32 if len(tri) < 2 ** 31 - 1 else np.int64)
    bar = np.zeros((altura * largura, 3), np.float32)
    prof = np.full(altura * largura, np.inf, np.float32) if z is not None else None
    a, b, c = xy[tri[:, 0]], xy[tri[:, 1]], xy[tri[:, 2]]
    x0 = np.clip(np.ceil(np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0]) - 0.5), 0, largura - 1).astype(np.int64)
    x1 = np.clip(np.floor(np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0]) - 0.5), -1, largura - 1).astype(np.int64)
    y0 = np.clip(np.ceil(np.minimum(np.minimum(a[:, 1], b[:, 1]), c[:, 1]) - 0.5), 0, altura - 1).astype(np.int64)
    y1 = np.clip(np.floor(np.maximum(np.maximum(a[:, 1], b[:, 1]), c[:, 1]) - 0.5), -1, altura - 1).astype(np.int64)
    bw = np.maximum(x1 - x0 + 1, 0)
    bh = np.maximum(y1 - y0 + 1, 0)
    n = bw * bh
    den = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    validos = np.flatnonzero((n > 0) & (np.abs(den) > 1e-12))
    acum = np.cumsum(n[validos])
    inicio = 0
    while inicio < len(validos):
        base = acum[inicio - 1] if inicio else 0
        fim = int(np.searchsorted(acum, base + lote, side='right'))
        fim = max(fim, inicio + 1)
        sel = validos[inicio:fim]
        inicio = fim
        cont = n[sel]
        t = np.repeat(sel, cont)
        k = np.arange(int(cont.sum())) - np.repeat(np.cumsum(cont) - cont, cont)
        px = x0[t] + k % bw[t]
        py = y0[t] + k // bw[t]
        cx = px + 0.5
        cy = py + 0.5
        d = den[t]
        l0 = ((b[t, 1] - c[t, 1]) * (cx - c[t, 0]) + (c[t, 0] - b[t, 0]) * (cy - c[t, 1])) / d
        l1 = ((c[t, 1] - a[t, 1]) * (cx - c[t, 0]) + (a[t, 0] - c[t, 0]) * (cy - c[t, 1])) / d
        l2 = 1 - l0 - l1
        dentro = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        t, px, py, l0, l1, l2 = t[dentro], px[dentro], py[dentro], l0[dentro], l1[dentro], l2[dentro]
        pix = py * largura + px
        if z is None:
            ids[pix] = t
            bar[pix] = np.column_stack([l0, l1, l2])
            continue
        zz = (l0 * z[tri[t, 0]] + l1 * z[tri[t, 1]] + l2 * z[tri[t, 2]]).astype(np.float32)
        ordem = np.lexsort((zz, pix))
        pix, zz, t = pix[ordem], zz[ordem], t[ordem]
        prim = np.ones(len(pix), bool)
        prim[1:] = pix[1:] != pix[:-1]
        pix, zz, t = pix[prim], zz[prim], t[prim]
        l = np.column_stack([l0, l1, l2])[ordem][prim]
        melhor = zz < prof[pix]
        pix, zz, t, l = pix[melhor], zz[melhor], t[melhor], l[melhor]
        prof[pix] = zz
        ids[pix] = t
        bar[pix] = l
    ids = ids.reshape(altura, largura)
    bar = bar.reshape(altura, largura, 3)
    if z is None:
        return ids, bar
    return ids, bar, prof.reshape(altura, largura)


# ---------------------------------------------------------------------------
# Entrada e rede
# ---------------------------------------------------------------------------

def preparar_entrada(rgba, lado_max=4096):
    """Recorta, centraliza num quadrado com 85% de ocupação e devolve a
    entrada da rede (512 px, fundo cinza) e o quadrado em alta (até lado_max)."""
    from PIL import Image
    alfa = rgba[..., 3]
    ys, xs = np.nonzero(alfa > 0)
    if len(ys) < 100:
        raise ReconstrucaoError('A silhueta está vazia.')
    rec = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    lado = max(rec.shape[:2])
    total = int(lado / OCUPACAO)
    quad = np.zeros((total, total, 4), np.uint8)
    oy = (total - rec.shape[0]) // 2
    ox = (total - rec.shape[1]) // 2
    quad[oy:oy + rec.shape[0], ox:ox + rec.shape[1]] = rec
    pequeno = np.asarray(Image.fromarray(quad).resize((LADO_ENTRADA, LADO_ENTRADA), Image.LANCZOS)).astype(np.float32) / 255
    if total > lado_max:
        quad = np.asarray(Image.fromarray(quad).resize((lado_max, lado_max), Image.LANCZOS))
    a = pequeno[..., 3:4]
    entrada = pequeno[..., :3] * a + 0.5 * (1 - a)
    return entrada.astype(np.float32), quad


def _carregar_arquivos():
    from huggingface_hub import hf_hub_download
    try:
        hf_hub_download(REPO, 'config.yaml')
        hf_hub_download(REPO, 'model.ckpt')
        hf_hub_download('facebook/dino-vitb16', 'config.json')
    except Exception as e:  # noqa: BLE001
        raise ReconstrucaoError('Não foi possível baixar o modelo de reconstrução 3D (precisa de internet só na '
                                f'primeira vez): {type(e).__name__}') from e


def _carregar_modelo(avisar):
    import torch
    from Vetor3D.triposr.system import TSR
    _carregar_arquivos()
    torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
    modelo = TSR.from_pretrained(REPO, 'config.yaml', 'model.ckpt')
    modelo.eval()
    return modelo


def _liberar():
    """Coleta o lixo e devolve ao sistema a memória livre do alocador do C
    (sem isso, centenas de MB ficam presas no processo depois de cada etapa)."""
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except (OSError, AttributeError):
        pass


def _rodar_rede(entrada, cache, threads=None):
    """Processo filho: carrega a rede inteira, gera o triplano e sai (a memória
    da rede volta toda para o sistema quando o processo termina)."""
    import torch
    modelo = _carregar_modelo(lambda r: None)
    if threads:
        torch.set_num_threads(int(threads))
    with torch.no_grad():
        codigo = modelo([entrada], device='cpu')[0].contiguous()
    torch.save(codigo, cache + '.tmp')
    os.replace(cache + '.tmp', cache)


def _esperar(proc, plano, chave, previsto):
    """Espera o processo filho, com o progresso andando pelo tempo previsto."""
    t0 = time.time()
    while proc.is_alive():
        proc.join(0.5)
        plano(chave, min(0.95, (time.time() - t0) / max(1.0, previsto)))
    if proc.exitcode != 0:
        if proc.exitcode in (-9, 137):
            raise MemoryError('A rede de reconstrução foi encerrada por falta de memória.')
        raise ReconstrucaoError(f'A rede de reconstrução parou (código {proc.exitcode}).')


def _decodificador():
    """Só o decodificador da rede (0,2 MB) e o renderizador: é o que as
    etapas seguintes usam, sem montar a rede inteira (~1,7 GB)."""
    import torch
    from huggingface_hub import hf_hub_download
    from Vetor3D.triposr.models.network_utils import NeRFMLP
    from Vetor3D.triposr.models.nerf_renderer import TriplaneNeRFRenderer
    from Vetor3D.triposr.system import _ler_config
    cfg = _ler_config(hf_hub_download(REPO, 'config.yaml'))
    dec = NeRFMLP(cfg['decoder'])
    ren = TriplaneNeRFRenderer(cfg['renderer'])
    ckpt = torch.load(hf_hub_download(REPO, 'model.ckpt'), map_location='cpu', mmap=True, weights_only=True)
    dec.load_state_dict({k[len('decoder.'):]: v.clone() for k, v in ckpt.items() if k.startswith('decoder.')})
    del ckpt
    dec.eval()
    ren.eval()
    return dec, ren


def triplano(pasta, entrada, plano, previsto_rede=40.0):
    """Triplano da imagem (cache por imagem no projeto). A rede roda num
    processo filho. Volta (triplano, decodificador, renderizador, chave)."""
    import multiprocessing as mp
    import torch
    chave = hashlib.sha1(np.ascontiguousarray((entrada * 255).astype(np.uint8)).tobytes()).hexdigest()[:16]
    cache = os.path.join(pasta, f'triplano_{chave}.pt')
    plano('modelo')
    try:
        from huggingface_hub import try_to_load_from_cache
        if not isinstance(try_to_load_from_cache(REPO, 'model.ckpt'), str):
            plano('modelo', 0.05, 'Baixando o modelo de reconstrução 3D (1,7 GB, só na primeira vez)')
        _carregar_arquivos()
    except ReconstrucaoError:
        raise
    plano('rede')
    if not os.path.exists(cache):
        torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
        proc = mp.get_context('spawn').Process(target=_rodar_rede, args=(entrada, cache, threads_livres()), daemon=True)
        proc.start()
        _esperar(proc, plano, 'rede', previsto_rede)
    codigo = torch.load(cache, map_location='cpu', weights_only=True)
    dec, ren = _decodificador()
    _liberar()
    return codigo, dec, ren, chave


def _consultar(decodificador, renderizador, codigo, pts, campo, lote=131072):
    """Densidade ('density_act') ou cor ('color') em pontos (N, 3) do espaço da rede."""
    import torch
    saida = []
    with torch.no_grad():
        for i in range(0, len(pts), lote):
            p = torch.from_numpy(np.ascontiguousarray(pts[i:i + lote], dtype=np.float32))
            saida.append(renderizador.query_triplane(decodificador, p, codigo)[campo].numpy())
    if not saida:
        return np.zeros((0, 1 if campo == 'density_act' else 3), np.float32)
    return np.concatenate(saida, axis=0)


def _grade(decodificador, renderizador, codigo, lo, hi, res, progresso=None, frac=(0, 1)):
    """Densidade numa grade (nx, ny, nz) entre lo e hi, com passo igual nos 3 eixos."""
    passo = float((hi - lo).max()) / (res - 1)
    n = np.maximum(2, np.ceil((hi - lo) / passo).astype(int) + 1)
    xs = lo[0] + np.arange(n[0]) * passo
    ys = lo[1] + np.arange(n[1]) * passo
    zs = lo[2] + np.arange(n[2]) * passo
    dens = np.empty((n[0], n[1], n[2]), np.float32)
    yy, zz = np.meshgrid(ys, zs, indexing='ij')
    fatia = np.column_stack([np.zeros(yy.size), yy.ravel(), zz.ravel()]).astype(np.float32)
    passo_fatias = max(1, 400_000 // max(1, fatia.shape[0]))
    for i in range(0, n[0], passo_fatias):
        blocos = []
        for x in xs[i:i + passo_fatias]:
            f = fatia.copy()
            f[:, 0] = x
            blocos.append(f)
        val = _consultar(decodificador, renderizador, codigo, np.concatenate(blocos), 'density_act')
        dens[i:i + len(blocos)] = val.reshape(len(blocos), n[1], n[2])
        if progresso:
            progresso('Extraindo a superfície', frac[0] + (frac[1] - frac[0]) * min(1, (i + passo_fatias) / n[0]))
    return dens, passo


# ---------------------------------------------------------------------------
# Corpo da rede como distância assinada (com cache)
# ---------------------------------------------------------------------------

def arredondar(sdf, passo, raio_rel=0.012):
    """Deixa o corpo "certinho e redondo": fechamento morfológico (fecha fendas,
    furos e túneis menores que ~1,2% do tamanho do objeto), preenche cavidades
    fechadas por dentro e suaviza. Fora das áreas que mudaram, mantém a
    distância contínua original (os detalhes reais ficam)."""
    from scipy import ndimage as ndi
    occ0 = sdf > 0
    if not occ0.any():
        return sdf
    ext = np.ptp(np.argwhere(occ0), axis=0).max() + 1
    r = max(1.5, raio_rel * ext)
    # espessura mínima: placas e fios mais finos que ~4 voxels são engrossados
    # 1 voxel (a amostragem suave do campo final "come" um pouco das placas
    # finas e abria furinhos nos pontos mais finos)
    bola = ndi.generate_binary_structure(3, 1)
    fino = occ0 & ~ndi.binary_opening(occ0, structure=bola, iterations=2)
    occ = occ0 | ndi.binary_dilation(fino, structure=bola) if fino.any() else occ0
    del fino
    fora = ndi.distance_transform_edt(~occ)
    dil = fora <= r
    del fora
    fech = ndi.distance_transform_edt(dil) > r
    del dil
    fech |= occ
    fech = ndi.binary_fill_holes(fech)
    mudou = fech & ~occ0
    if mudou.any():
        novo = ndi.distance_transform_edt(fech).astype(np.float32)
        novo -= ndi.distance_transform_edt(~fech).astype(np.float32)
        novo = (novo - 0.5 * np.sign(novo)) * passo
        perto = ndi.binary_dilation(mudou, iterations=2)
        sdf = np.where(perto, np.maximum(sdf, novo), sdf).astype(np.float32)
        del novo, perto
    # (sem suavizar o campo aqui: suavizar afina placas finas até furar; a
    # malha final já é suavizada pelo Taubin, que não abre furos)
    return sdf


def corpo(pasta, chave, codigo, decodificador, renderizador, plano):
    """Distância assinada (mundo, positiva dentro) do volume da rede numa grade
    256³ do cubo inteiro. Volta (sdf float32, lo, passo)."""
    from scipy import ndimage as ndi
    cache = os.path.join(pasta, f'corpo_v{VERSAO_CORPO}_{chave}.npz')
    plano('corpo')
    if os.path.exists(cache):
        try:
            with np.load(cache) as z:
                return z['sdf'].astype(np.float32), z['lo'].astype(np.float64), float(z['passo'])
        except Exception:  # noqa: BLE001
            pass
    raio = float(renderizador.cfg.radius)
    lo = np.full(3, -raio)
    hi = np.full(3, raio)
    dens, passo = _grade(decodificador, renderizador, codigo, lo, hi, GRADE_CORPO,
                         lambda e, f: plano('corpo', 0.6 * f), (0, 1))
    lv = ndi.gaussian_filter(np.log(np.maximum(dens, 1e-6)), 1.0) - np.float32(np.log(LIMIAR))
    del dens
    plano('corpo', 0.65)
    occ = lv > 0
    sdf = ndi.distance_transform_edt(occ).astype(np.float32)
    sdf -= ndi.distance_transform_edt(~occ).astype(np.float32)
    sdf -= 0.5 * np.sign(lv)
    del occ
    plano('corpo', 0.85)
    # perto da superfície a distância vem do campo contínuo (sem degraus de voxel)
    gm = np.zeros_like(lv)
    for g in np.gradient(lv):
        gm += g * g
    np.sqrt(gm, out=gm)
    perto = np.clip(lv / np.maximum(gm, 1e-3), -3, 3)
    del gm
    peso = np.clip(1.5 - np.abs(sdf) / 2, 0, 1)
    sdf = ((peso * perto + (1 - peso) * sdf) * passo).astype(np.float32)
    del perto, peso, lv
    plano('corpo', 0.95)
    sdf = arredondar(sdf, passo)
    try:
        np.savez(cache + '.tmp.npz', sdf=sdf.astype(np.float16), lo=lo, passo=passo)
        os.replace(cache + '.tmp.npz', cache)
    except OSError:
        pass
    return sdf, lo, passo


# ---------------------------------------------------------------------------
# Corpo pelo motor de máxima qualidade (Hunyuan3D-2 mini)
# ---------------------------------------------------------------------------

def threads_livres():
    """Núcleos para a IA conforme o uso do PC agora: com outros programas
    ocupando a CPU, usa menos (o computador continua livre para o resto)."""
    n = os.cpu_count() or 2
    try:
        import psutil
        uso = psutil.cpu_percent(interval=0.5)
    except Exception:  # noqa: BLE001
        uso = 0.0
    return max(2, min(n - 1, int(round(n * (1 - uso / 100.0)))))


def _chave_arquivo(caminho):
    h = hashlib.sha1()
    with open(caminho, 'rb') as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()[:16]


def _sdf_de_logits(L, passo):
    """Logits do Hunyuan (só calculados perto da superfície; NaN no resto) ->
    distância assinada (positiva dentro), em unidades do espaço do modelo."""
    from scipy import ndimage as ndi
    nan = np.isnan(L)
    if nan.any():
        _, idx = ndi.distance_transform_edt(nan, return_indices=True)
        L = L[tuple(idx)]
        del idx
    lv = ndi.gaussian_filter(L.astype(np.float32), 0.7)
    del L
    occ = lv > 0
    sdf = ndi.distance_transform_edt(occ).astype(np.float32)
    sdf -= ndi.distance_transform_edt(~occ).astype(np.float32)
    sdf -= 0.5 * np.sign(lv)
    del occ
    gm = np.zeros_like(lv)
    for g in np.gradient(lv):
        gm += g * g
    np.sqrt(gm, out=gm)
    perto = np.clip(lv / np.maximum(gm, 1e-3), -3, 3)
    del gm
    peso = np.clip(1.5 - np.abs(sdf) / 2, 0, 1)
    return ((peso * perto + (1 - peso) * sdf) * passo).astype(np.float32)


def corpo_hunyuan(pasta, quad, plano, previsto_rede=440.0):
    """Corpo pelo Hunyuan3D, já no referencial da câmera do pipeline (x para a
    câmera, y direita, z cima) e alinhado ao contorno do desenho. Volta (sdf,
    lo, passo, câmera ortográfica)."""
    import multiprocessing as mp
    from Vetor3D import v3d_hunyuan as H
    S = quad.shape[0]
    png = os.path.join(pasta, 'sem_fundo.png')
    chave = _chave_arquivo(png)
    cache = os.path.join(pasta, f'corpo_hy_v{H.VERSAO}.{VERSAO_CORPO}_{chave}.npz')
    plano('corpo_max')
    if os.path.exists(cache):
        try:
            with np.load(cache) as z:
                return (z['sdf'].astype(np.float32), z['lo'].astype(np.float64), float(z['passo']),
                        Camera(S, float(z['D']), float(z['tg'])))
        except Exception:  # noqa: BLE001
            pass
    logits = os.path.join(pasta, f'hunyuan_{chave}.npz')
    if not os.path.exists(logits):
        arq = os.path.join(pasta, 'hunyuan_progresso.json')
        try:
            os.remove(arq)
        except OSError:
            pass
        proc = mp.get_context('spawn').Process(target=H.gerar, args=(png, logits, arq, threads_livres()),
                                               daemon=True)
        proc.start()
        # leitura ~33%, difusão ~59% (5 passos), volume ~8% do tempo da etapa
        faixas = {'imagem': (0.0, 0.01), 'leitura': (0.01, 0.33), 'difusao': (0.33, 0.92), 'volume': (0.92, 1.0)}
        rotulos = {'imagem': 'Preparando a imagem para a IA', 'leitura': 'IA lendo a imagem (máxima qualidade)',
                   'difusao': 'IA gerando a forma 3D', 'volume': 'IA extraindo o volume 3D'}
        t_et, ult = time.time(), None
        while proc.is_alive():
            proc.join(1.0)
            try:
                with open(arq) as fh:
                    st = json.load(fh)
            except (OSError, ValueError):
                continue
            et = st.get('etapa')
            if et not in faixas:
                continue
            if (et, st.get('frac')) != ult:
                ult, t_et = (et, st.get('frac')), time.time()
            a, b = faixas[et]
            if et == 'difusao':
                passo_i = round(float(st.get('frac', 0)) * H.PASSOS)
                a = a + (b - a) * passo_i / H.PASSOS
                b = a + (faixas['difusao'][1] - faixas['difusao'][0]) / H.PASSOS
                rot = f'{rotulos[et]} (passo {passo_i + 1} de {H.PASSOS})'
            else:
                rot = rotulos[et]
            dentro = min(0.95, (time.time() - t_et) / max(1.0, (b - a) * previsto_rede))
            plano('rede_max', a + (b - a) * dentro, rot)
        if proc.exitcode != 0:
            if proc.exitcode in (-9, 137):
                raise MemoryError('A IA de máxima qualidade foi encerrada por falta de memória.')
            raise ReconstrucaoError(f'A IA de máxima qualidade parou (código {proc.exitcode}).')
    plano('corpo_max', 0.05)
    with np.load(logits) as z:
        L = z['logits'].astype(np.float32)
        lim = float(z['limite'])
    n = L.shape[0]
    passo = 2 * lim / (n - 1)
    sdf_h = _sdf_de_logits(L, passo)
    del L
    _liberar()
    plano('corpo_max', 0.7)
    # referencial do Hunyuan (x direita, y cima, z para a câmera) -> do pipeline
    sdf = np.ascontiguousarray(sdf_h.transpose(2, 0, 1))
    del sdf_h
    lo = np.full(3, -lim)
    # câmera e posição: a silhueta do volume casa com a do desenho
    if not (sdf > 0).any():
        raise ReconstrucaoError('A IA de máxima qualidade não gerou volume para esta imagem.')
    Rm, centro, esc, D, dy, dz, iou_aj = _alinhar_persp(sdf, lo, passo, quad[..., 3] > 127)
    # volume na pose encontrada, centrado na origem e deslocado no plano da
    # imagem; câmera em +x à distância D ('esc' px por unidade na profundidade 0)
    pts = np.argwhere(sdf > 0)
    meia = float(np.linalg.norm((pts * passo + lo) - centro, axis=1).max()) + 4 * passo
    del pts
    desloc = np.array([0.0, dy, dz])
    sdf, lo = _girar(sdf, lo, passo, Rm, centro, desloc, meia)
    _liberar()
    # arredondar já na pose final (girar reamostra e podia reabrir furinhos)
    plano('corpo_max', 0.85, 'Fechando furos e arredondando o corpo')
    sdf = arredondar(sdf, passo)
    _liberar()
    tg = S / (2 * esc * D)
    cam = Camera(S, D, tg)
    try:
        np.savez(cache + '.tmp.npz', sdf=sdf.astype(np.float16), lo=lo, passo=passo, D=D, tg=tg)
        os.replace(cache + '.tmp.npz', cache)
    except OSError:
        pass
    plano('corpo_max', 1.0)
    return sdf, lo, passo, cam


def _alinhar(proj, lo_y, lo_z, passo, mask):
    """Escala e posição (px por unidade, deslocamentos no mundo) que levam a
    silhueta frontal do volume (proj[y, z]) à do desenho (mask[py, px]),
    maximizando a sobreposição das silhuetas inteiras (os extremos, como a
    ponta de uma cauda, não puxam o ajuste como na caixa envolvente)."""
    from scipy import ndimage as ndi
    from scipy.optimize import minimize
    S = mask.shape[0]
    R_ = 384
    f = R_ / S
    m = ndi.zoom(mask.astype(np.float32), f, order=1) > 0.5
    alvo = ndi.gaussian_filter(m.astype(np.float32), 1.5)
    jy, jz = np.nonzero(proj)
    y0, y1 = lo_y + jy.min() * passo, lo_y + jy.max() * passo
    z0, z1 = lo_z + jz.min() * passo, lo_z + jz.max() * passo
    cy, cz = (y0 + y1) / 2, (z0 + z1) / 2
    ys, xs = np.nonzero(m)
    s0 = 0.5 * ((xs.max() - xs.min()) / (y1 - y0) + (ys.max() - ys.min()) / (z1 - z0))
    u0, v0 = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    fonte = ndi.gaussian_filter(proj.astype(np.float32), 1.0)
    vv, uu = np.mgrid[0:R_, 0:R_].astype(np.float32) + 0.5

    def amostra(x):
        s_, u_, v_ = np.exp(x[0]) * s0, x[1], x[2]
        y = (uu - u_) / s_ + cy
        z = -(vv - v_) / s_ + cz
        return ndi.map_coordinates(fonte, [(y - lo_y) / passo, (z - lo_z) / passo], order=1, cval=0.0)

    def custo(x):
        return float(np.mean((amostra(x) - alvo) ** 2))
    melhor = None
    for ds in (-0.08, 0.0, 0.08):
        r = minimize(custo, np.array([ds, u0, v0]), method='Powell',
                     options={'xtol': 1e-3, 'ftol': 1e-6, 'maxiter': 400})
        if melhor is None or r.fun < melhor.fun:
            melhor = r
    x = melhor.x
    ren = amostra(x) > 0.5
    iou = float((ren & m).sum() / max(1, (ren | m).sum()))
    s_px = np.exp(x[0]) * s0 / f              # px do quadrado por unidade
    u_px, v_px = x[1] / f, x[2] / f
    dy = -cy + (u_px - S / 2) / s_px
    dz = -cz + (S / 2 - v_px) / s_px
    return s_px, dy, dz, iou


def _rot(giro, incl, rolagem):
    """Rotação da cena: giro em torno do eixo vertical (z), inclinação em torno
    de y (para cima/baixo) e rolagem em torno do eixo da câmera (x)."""
    a, b, c = giro, incl, rolagem
    Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    Ry = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(c), -np.sin(c)], [0, np.sin(c), np.cos(c)]])
    return Rx @ Ry @ Rz


def _alinhar_persp(sdf, lo, passo, mask):
    """Pose da câmera que faz a silhueta do volume coincidir com a do desenho.

    A IA gera o objeto na orientação "natural" dele, não necessariamente na
    da imagem (um bicho de perfil pode sair de frente): primeiro uma busca
    ampla do ângulo de vista (giro e inclinação), depois um refino com
    perspectiva (desenhos exageram o que aponta para quem olha), rotação fina,
    escala e posição, maximizando a sobreposição das silhuetas inteiras.
    Volta (R, centro, px por unidade, distância D, dy, dz, IoU)."""
    from scipy import ndimage as ndi
    from scipy.optimize import minimize
    S = mask.shape[0]
    todos = (np.argwhere(sdf > 0) * passo + lo).astype(np.float32)
    centro = todos.mean(axis=0)
    todos -= centro
    rng = np.random.default_rng(0)

    def preparar(R_):
        f = R_ / S
        m = ndi.zoom(mask.astype(np.float32), f, order=1) > 0.5
        return m, ndi.gaussian_filter(m.astype(np.float32), 1.2), f

    def imagem(pts, Rm, s_, dy, dz, inv, R_, raio):
        P = pts @ Rm.T.astype(np.float32)
        k = s_ / (1 - P[:, 0] * inv)
        u = np.round(R_ / 2 + (P[:, 1] + dy) * k).astype(np.int64)
        v = np.round(R_ / 2 - (P[:, 2] + dz) * k).astype(np.int64)
        ok = (u >= 0) & (u < R_) & (v >= 0) & (v < R_)
        im = np.bincount(v[ok] * R_ + u[ok], minlength=R_ * R_).reshape(R_, R_) > 0
        return ndi.binary_dilation(im, iterations=raio) if raio else im

    # 1) busca ampla do ângulo de vista (ortográfica, escala e posição pelos momentos)
    m1, _, f1 = preparar(160)
    pts1 = todos[rng.choice(len(todos), min(len(todos), 250_000), replace=False)]
    ys, xs = np.nonzero(m1)
    cm = np.array([xs.mean(), ys.mean()])
    cands = []
    for giro in np.radians(np.arange(0, 360, 15)):
        for incl in np.radians((-30, -15, 0, 15, 30)):
            Rm = _rot(giro, incl, 0.0)
            P = pts1 @ Rm.T.astype(np.float32)
            ext_y, ext_z = np.ptp(P[:, 1]), np.ptp(P[:, 2])
            s_ = 0.5 * ((xs.max() - xs.min()) / max(ext_y, 1e-6) + (ys.max() - ys.min()) / max(ext_z, 1e-6))
            dy = (cm[0] - 80) / s_ - float(P[:, 1].mean())
            dz = (80 - cm[1]) / s_ - float(P[:, 2].mean())
            im = imagem(pts1, Rm, s_, dy, dz, 0.0, 160, max(1, int(round(s_ * passo * 0.6))))
            iou = (im & m1).sum() / max(1, (im | m1).sum())
            cands.append((iou, giro, incl, s_ / f1, dy, dz))
    cands.sort(key=lambda c: -c[0])

    # 2) refino: rápido nas 5 melhores (a ordem da busca grossa é ruidosa) e
    # completo só na vencedora, com perspectiva, rotação fina, escala e posição
    def refinar(cand, R_, n_pts, iters, invs):
        _, giro, incl, s_px, dy0, dz0 = cand
        mm, alvo_, ff = preparar(R_)
        p_ = todos if len(todos) <= n_pts else todos[rng.choice(len(todos), n_pts, replace=False)]
        s0 = s_px * ff
        raio = max(1, int(round(s0 * passo * 0.6)))

        def custo(x):
            Rm = _rot(giro + x[4], incl + x[5], x[6])
            im = imagem(p_, Rm, np.exp(x[0]) * s0, x[1], x[2], x[3], R_, raio)
            return float(np.mean((ndi.gaussian_filter(im.astype(np.float32), 1.2) - alvo_) ** 2))
        best = None
        for inv in invs:
            r = minimize(custo, np.array([0.0, dy0, dz0, inv, 0.0, 0.0, 0.0]), method='Powell',
                         bounds=[(-0.4, 0.4), (-1.5, 1.5), (-1.5, 1.5), (0.0, 1.0), (-0.25, 0.25), (-0.25, 0.25), (-0.2, 0.2)],
                         options={'xtol': 2e-3, 'ftol': 1e-6, 'maxiter': iters})
            if best is None or r.fun < best.fun:
                best = r
        x = best.x
        Rm = _rot(giro + x[4], incl + x[5], x[6])
        im = imagem(p_, Rm, np.exp(x[0]) * s0, x[1], x[2], x[3], R_, raio)
        iou = float((im & mm).sum() / max(1, (im | mm).sum()))
        return iou, x, giro, incl, s0, ff
    rapidos = [(refinar(c, 160, 150_000, 300, (0.25,)), c) for c in cands[:5]]
    _, venc = max(rapidos, key=lambda t: t[0][0])
    iou, x, giro, incl, s0, f = refinar(venc, 256, 400_000, 1200, (0.1, 0.45))
    Rm = _rot(giro + x[4], incl + x[5], x[6])
    D = 1.0 / max(x[3], 1e-3)
    return Rm, centro.astype(np.float64), np.exp(x[0]) * s0 / f, D, float(x[1]), float(x[2]), iou


def _girar(sdf, lo, passo, Rm, centro, desloc, meia):
    """Reamostra o volume na pose encontrada: valor em q = Rm (p - centro) + desloc,
    numa grade cúbica de meia-largura 'meia' em torno de desloc (em fatias)."""
    from scipy import ndimage as ndi
    n = int(np.ceil(2 * meia / passo)) + 1
    lo_n = np.asarray(desloc, np.float64) - meia
    out = np.empty((n, n, n), np.float32)
    J, K = np.meshgrid(np.arange(n), np.arange(n), indexing='ij')
    Ri = Rm.T
    for i in range(n):
        q = np.stack([np.full(J.shape, lo_n[0] + i * passo), lo_n[1] + J * passo, lo_n[2] + K * passo], -1).reshape(-1, 3)
        p = (q - desloc) @ Ri.T + centro
        idx = ((p - lo) / passo).T
        out[i] = ndi.map_coordinates(sdf, idx, order=1, mode='constant', cval=float(-3 * passo)).reshape(J.shape)
    return out, lo_n


def escolher_motor(preferencia, avisar=None):
    """'maximo' (Hunyuan3D) quando o computador comporta e o modelo está (ou
    cabe ser) baixado; senão 'leve' (TripoSR). Volta (motor, aviso)."""
    from Vetor3D import v3d_hunyuan as H
    from Vetor3D import v3d_modelos as MD
    if preferencia == 'leve':
        return 'leve', None
    if not H.adequado():
        return 'leve', ('Este computador tem menos de 6 GB de RAM: usado o motor leve (TripoSR).'
                        if preferencia == 'maximo' else None)
    if H.caminhos() is not None:
        return 'maximo', None
    e = MD.estado('maximo')
    if e['falta_bytes'] + MD.FOLGA_DISCO > MD.espaco_livre():
        return 'leve', (f'Sem espaço em disco para o motor de máxima qualidade ({e["falta_bytes"] / MD.GB:.1f} GB): '
                        'usado o motor leve (TripoSR).')
    return 'baixar', None


# ---------------------------------------------------------------------------
# Geometria fiel ao desenho
# ---------------------------------------------------------------------------

class Camera:
    """Câmera em +x olhando a origem, +y à direita, +z para cima. Pixel
    (px, py) do quadrado de lado S. Padrão: a do TripoSR (perspectiva, 40°).
    O Hunyuan3D foi treinado com vista ortográfica: câmera bem longe (D grande)
    com campo estreito, que dá a mesma projeção."""

    def __init__(self, S, D=DIST_CAMERA, tg=None):
        self.S = S
        self.D = float(D)
        self.tg = float(tg) if tg is not None else np.tan(np.radians(FOV_GRAUS) / 2)

    def pixel(self, x, y, z):
        d = self.D - x
        k = 1.0 / (self.tg * d)
        return (y * k + 1) * (self.S / 2), (1 - z * k) * (self.S / 2), d

    def ponto(self, px, py, d):
        u = px / self.S * 2 - 1
        v = 1 - py / self.S * 2
        return self.D - d, u * self.tg * d, v * self.tg * d

    def px_mundo(self, d):
        """Tamanho de um pixel do quadrado (em unidades do mundo) na profundidade d."""
        return 2 * self.tg * d / self.S


def _amostra3(campo, lo, passo, x, y, z, ordem=1):
    """Amostra a grade 3D. ordem=3 espera os coeficientes de spline (sem dobras
    entre as células da grade grossa: a superfície fina fica lisa)."""
    from scipy import ndimage as ndi
    idx = np.empty((3, len(x)), np.float32)
    idx[0] = (x - lo[0]) / passo
    idx[1] = (y - lo[1]) / passo
    idx[2] = (z - lo[2]) / passo
    return ndi.map_coordinates(campo, idx, order=ordem, mode='nearest', output=np.float32, prefilter=False)


def _amostra2(img, linhas, colunas, ordem=1):
    """Amostra um mapa 2D. ordem=3 espera coeficientes de spline (spline_filter):
    sem as dobras da bilinear a cada pixel da grade."""
    from scipy import ndimage as ndi
    idx = np.empty((2, len(linhas)), np.float32)
    idx[0] = linhas
    idx[1] = colunas
    return ndi.map_coordinates(img, idx, order=ordem, mode='nearest', output=np.float32, prefilter=False)


def _harmonica(val, conhecido, regiao):
    """Laplace com valores fixos onde é conhecido (interpolação suave)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    G = val.shape[0]
    alvo = regiao & ~conhecido
    if not alvo.any() or not conhecido.any():
        return val
    ys, xs = np.nonzero(alvo)
    idx = -np.ones(val.shape, np.int64)
    idx[ys, xs] = np.arange(len(ys))
    lin, col, coef = [np.arange(len(ys))], [np.arange(len(ys))], [np.zeros(len(ys))]
    b = np.zeros(len(ys))
    for oy, ox in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        yy = np.clip(ys + oy, 0, G - 1)
        xx = np.clip(xs + ox, 0, G - 1)
        dentro = (ys + oy >= 0) & (ys + oy < G) & (xs + ox >= 0) & (xs + ox < G)
        viz_alvo = dentro & alvo[yy, xx]
        viz_fixo = dentro & conhecido[yy, xx]
        coef[0] = coef[0] + (viz_alvo | viz_fixo)
        sel = np.flatnonzero(viz_alvo)
        lin.append(sel)
        col.append(idx[yy[sel], xx[sel]])
        coef.append(-np.ones(len(sel)))
        b += np.where(viz_fixo, val[yy, xx], 0)
    coef[0] = np.maximum(coef[0], 1)
    A = coo_matrix((np.concatenate(coef), (np.concatenate(lin), np.concatenate(col))),
                   shape=(len(ys), len(ys))).tocsr()
    out = val.copy()
    out[ys, xs] = spsolve(A, b)
    return out


def mapas(sdf, lo, passo, quad, cam, plano):
    """Mapas 2D (grade G) que guiam o campo final: deformação da silhueta da
    rede para a do desenho e o preenchimento das partes que a rede perdeu."""
    from PIL import Image
    from scipy import ndimage as ndi
    G = GRADE_2D
    S = cam.S
    plano('mapas', 0.0)
    mask = quad[..., 3] > 127
    mask_g = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((G, G), Image.BILINEAR)) > 127
    # frente e fundo do corpo em cada pixel (marcha de raios no campo do corpo)
    occx = np.nonzero((sdf > 0).any(axis=(1, 2)))[0]
    if len(occx) == 0:
        raise ReconstrucaoError('A rede não encontrou um objeto nesta imagem. Confira se o fundo foi removido.')
    x_lo = lo[0] + (occx.min() - 2) * passo
    x_hi = lo[0] + (occx.max() + 2) * passo
    dmin, dmax = cam.D - x_hi, cam.D - x_lo
    ds = np.arange(dmin, dmax, passo / 2, dtype=np.float32)
    frente = np.full((G, G), np.nan, np.float32)
    tras = np.full((G, G), np.nan, np.float32)
    centros = (np.arange(G) + 0.5) * S / G
    for i0 in range(0, G, 16):
        py = np.repeat(centros[i0:i0 + 16], G)
        px = np.tile(centros, len(py) // G)
        n = len(px)
        X, Y, Z = cam.ponto(px[:, None], py[:, None], ds[None, :])
        val = _amostra3(sdf, lo, passo, np.broadcast_to(X, (n, len(ds))).ravel(), Y.ravel(), Z.ravel()).reshape(n, len(ds))
        dentro = val > 0
        tem = dentro.any(axis=1)
        pri = np.argmax(dentro, axis=1)
        ult = len(ds) - 1 - np.argmax(dentro[:, ::-1], axis=1)
        ar = np.arange(n)
        dd = ds[1] - ds[0]
        v0, v1 = val[ar, np.maximum(pri - 1, 0)], val[ar, pri]
        fp = ds[pri] - dd * np.clip(v1 / np.maximum(v1 - v0, 1e-9), 0, 1)
        w0, w1 = val[ar, ult], val[ar, np.minimum(ult + 1, len(ds) - 1)]
        bp = ds[ult] + dd * np.clip(w0 / np.maximum(w0 - w1, 1e-9), 0, 1)
        frente[i0:i0 + 16] = np.where(tem, fp, np.nan).reshape(-1, G)
        tras[i0:i0 + 16] = np.where(tem, bp, np.nan).reshape(-1, G)
        plano('mapas', 0.6 * (i0 + 16) / G)
    cob = ~np.isnan(frente)

    # deformação: para cada pixel do desenho, o ponto da silhueta da rede com a
    # mesma distância até a borda (Newton); saltos curtos (sem pular de parte)
    sd_d = ndi.gaussian_filter((ndi.distance_transform_edt(mask_g) - ndi.distance_transform_edt(~mask_g)).astype(np.float32), 1.0)
    sd_t = ndi.gaussian_filter((ndi.distance_transform_edt(cob) - ndi.distance_transform_edt(~cob)).astype(np.float32), 1.0)
    gy, gx = np.gradient(sd_t)
    gyy, gxx = np.mgrid[0:G, 0:G].astype(np.float32)
    qy, qx = gyy.copy(), gxx.copy()
    for _ in range(6):
        st = ndi.map_coordinates(sd_t, [qy, qx], order=1, mode='nearest')
        ny = ndi.map_coordinates(gy, [qy, qx], order=1, mode='nearest')
        nx = ndi.map_coordinates(gx, [qy, qx], order=1, mode='nearest')
        n2 = np.maximum(nx * nx + ny * ny, 0.25)
        passo_n = np.clip((st - sd_d) / n2, -4, 4)
        qy -= passo_n * ny
        qx -= passo_n * nx
    resid = np.abs(ndi.map_coordinates(sd_t, [qy, qx], order=1, mode='nearest') - sd_d)
    valido = ((resid < 1.5) & (np.hypot(qy - gyy, qx - gxx) < 15) & (sd_t > -15)
              & (ndi.map_coordinates(cob.astype(np.float32), [qy, qx], order=1) > 0.3))
    pv = np.maximum(ndi.gaussian_filter(valido.astype(np.float32), 3), 1e-3)
    dy = np.where(valido, ndi.gaussian_filter(np.where(valido, qy - gyy, 0), 3) / pv, 0).astype(np.float32)
    dx = np.where(valido, ndi.gaussian_filter(np.where(valido, qx - gxx, 0), 3) / pv, 0).astype(np.float32)
    plano('mapas', 0.75)

    # partes sem correspondência: tubo redondo pela largura da parte no
    # desenho, frente alinhada à frente (harmônica) do corpo vizinho
    # vazios preenchidos pelo vizinho válido ANTES de interpolar (misturar com
    # 0 criava profundidades falsas na borda da cobertura)
    _, (iy, ix) = ndi.distance_transform_edt(~cob, return_indices=True)
    fw = ndi.map_coordinates(frente[iy, ix], [qy, qx], order=1)
    bw = ndi.map_coordinates(tras[iy, ix], [qy, qx], order=1)
    del iy, ix
    cob_q = ndi.map_coordinates(cob.astype(np.float32), [qy, qx], order=1)
    corpo_ok = valido & mask_g & (bw > fw) & (cob_q > 0.99)
    if not corpo_ok.any():
        raise ReconstrucaoError('A reconstrução não correspondeu ao desenho. Confira se o fundo foi removido.')
    regiao = mask_g | ndi.binary_dilation(mask_g, iterations=2)
    fh = _harmonica(np.where(corpo_ok, fw, 0), corpo_ok, regiao)
    bh = _harmonica(np.where(corpo_ok, bw, 0), corpo_ok, regiao)
    falta = mask_g & ~corpo_ok
    w_fill = np.clip(ndi.gaussian_filter(ndi.binary_dilation(falta, iterations=3).astype(np.float32), 1.5) * 2, 0, 1)
    e = ndi.distance_transform_edt(mask_g).astype(np.float32)
    pxm = (2 * cam.tg * (fh + bh) / 2 / G).astype(np.float32)
    rloc = np.maximum(e, ndi.maximum_filter(e, size=61))
    redondo = np.sqrt(np.maximum(2 * rloc * e - e * e, 0)) * pxm
    raio = rloc * pxm
    meia = np.maximum((bh - fh) / 2, 0.35 * raio)
    tau = np.minimum(redondo, meia).astype(np.float32)
    centro = (fh + np.minimum(raio, meia)).astype(np.float32)
    meio = np.where(corpo_ok, (fw + bw) / 2, centro).astype(np.float32)
    # a marcha de raios tem ruído de um pixel da grade; no HD (2 voxels por
    # pixel) isso virava fileiras de calombos: suaviza dentro da silhueta
    def suave(m, sig=1.5):
        w = ndi.gaussian_filter(regiao.astype(np.float32), sig)
        return (ndi.gaussian_filter(np.where(regiao, m, 0).astype(np.float32), sig) / np.maximum(w, 1e-3)).astype(np.float32)
    meio = suave(meio)
    centro = suave(centro)
    # fora da região os mapas de profundidade seguem o vizinho (sem salto a 0)
    _, (ry, rx) = ndi.distance_transform_edt(~regiao, return_indices=True)
    meio = meio[ry, rx]
    centro = centro[ry, rx]
    tau = np.where(mask_g, suave(tau), 0).astype(np.float32)
    # furos que atravessam o corpo (vistos da câmera), fechados por todos os
    # lados, pequenos, num lugar onde o desenho é sólido: não existem no
    # personagem -> recebem uma membrana com a profundidade do corpo em volta
    buraco = ndi.binary_fill_holes(cob) & ~cob
    b_w = np.zeros((G, G), np.float32)
    b_tau = np.zeros((G, G), np.float32)
    b_centro = np.zeros((G, G), np.float32)
    if buraco.any():
        rot_b, n_b = ndi.label(buraco)
        area = ndi.sum(buraco, rot_b, np.arange(1, n_b + 1))
        no_desenho = ndi.mean(mask_g.astype(np.float32), rot_b, np.arange(1, n_b + 1))
        ok = np.flatnonzero((area <= 0.006 * max(1, cob.sum())) & (no_desenho > 0.5)) + 1
        tapar = np.isin(rot_b, ok)
        if tapar.any():
            reg_b = ndi.binary_dilation(tapar, iterations=2)
            _, (iy2, ix2) = ndi.distance_transform_edt(~cob, return_indices=True)
            fr, tr = frente[iy2, ix2], tras[iy2, ix2]
            cb = _harmonica(np.where(cob, (fr + tr) / 2, 0), cob & reg_b, reg_b | tapar)
            tb = _harmonica(np.where(cob, (tr - fr) / 2, 0), cob & reg_b, reg_b | tapar)
            b_centro = np.where(reg_b, cb, 0).astype(np.float32)
            b_tau = np.where(reg_b, np.maximum(tb, 0) * 0.8, 0).astype(np.float32)
            b_w = np.clip(ndi.gaussian_filter(ndi.binary_dilation(tapar, iterations=2).astype(np.float32), 1.0) * 2, 0, 1).astype(np.float32)
    # espessura local do desenho: raio do maior disco dentro da silhueta que
    # contém o pixel (ponta fina = raio pequeno, tronco = raio grande)
    tl = np.zeros((G, G), np.float32)
    for r in np.geomspace(1, 160, 24):
        nucleo = e >= r
        if not nucleo.any():
            break
        coberto = ndi.distance_transform_edt(~nucleo) <= r
        tl = np.where(coberto & mask_g, np.float32(r), tl)
    tl = ndi.gaussian_filter(np.maximum(tl, 1.0), 2.0)              # sem degraus
    tl = (tl * (2 * cam.tg * meio / G)).astype(np.float32)
    plano('mapas', 1.0)
    return {'dx': dx, 'dy': dy, 'tau': tau, 'centro': centro, 'w': w_fill.astype(np.float32), 'meio': meio, 'tl': tl,
            'b_w': b_w, 'b_tau': b_tau, 'b_centro': b_centro, 'furos': int(b_w.sum() > 0),
            'dmin': float(min(dmin, np.nanmin(np.where(falta, centro - tau, np.nan)) if falta.any() else dmin)),
            'dmax': float(max(dmax, np.nanmax(np.where(falta, centro + tau, np.nan)) if falta.any() else dmax)),
            'falta': float(falta.sum() / max(1, mask_g.sum())), 'mask_g': mask_g}


def _msd(quad):
    """Distância assinada (px do quadrado) até o contorno do desenho."""
    from scipy import ndimage as ndi
    mask = quad[..., 3] > 127
    msd = ndi.distance_transform_edt(mask).astype(np.float32)
    msd -= ndi.distance_transform_edt(~mask).astype(np.float32)
    msd -= 0.5 * np.sign(msd)
    # a borda em pixels é uma escadinha (forte nas diagonais): suavizada, o
    # contorno fica subpixel e as paredes não ganham listras
    return ndi.gaussian_filter(msd, 1.5)


def campo_malha(sdf, lo, passo, quad, cam, mp, N, orcamento_mb, plano, limitar=True, contorno=True):
    """Campo final numa grade fina, em fatias (memória limitada), e marching
    cubes por fatia com costura exata. Volta (vértices, faces) no mundo."""
    from skimage.measure import marching_cubes
    G = GRADE_2D
    S = cam.S
    msd = _msd(quad)
    # amostragem por B-spline cúbica APROXIMANTE (sem pré-filtro): suave como a
    # cúbica (a bilinear deixava uma dobra a cada célula da grade, que virava
    # listras no HD) e sem as oscilações da cúbica interpolante perto de saltos
    coef = sdf
    sp = mp
    msd_c = msd
    plano('campo', 0.01)
    mask = quad[..., 3] > 127
    ys, xs = np.nonzero(mask)
    py0, py1, px0, px1 = ys.min() - 3, ys.max() + 3, xs.min() - 3, xs.max() + 3
    dmin, dmax = mp['dmin'] - 2 * passo, mp['dmax'] + 2 * passo
    ext = lambda p, d: (p / S * 2 - 1) * cam.tg * d
    ylo = min(ext(px0, dmin), ext(px0, dmax))
    yhi = max(ext(px1, dmin), ext(px1, dmax))
    zlo = min(-ext(py1, dmin), -ext(py1, dmax))
    zhi = max(-ext(py0, dmin), -ext(py0, dmax))
    h = max(yhi - ylo, zhi - zlo) / N
    xg = np.arange(cam.D - dmax, cam.D - dmin + h, h, dtype=np.float64)
    yg = np.arange(ylo, yhi + h, h, dtype=np.float64)
    zg = np.arange(zlo, zhi + h, h, dtype=np.float64)
    nx, ny, nz = len(xg), len(yg), len(zg)
    k = np.float32(1.5 * h)
    esc = G / S
    # ~110 bytes por voxel avaliado; a fatia cabe no orçamento
    por_fatia = max(nx * ny * 2, int(orcamento_mb * 0.45 * 1024 * 1024 / 110))
    linhas = max(2, por_fatia // (nx * ny))
    # coluna (y, z) só é avaliada se a silhueta (com folga) passa por ela
    folga = 4 + h / cam.px_mundo(dmin)
    verts, faces, nv = [], [], 0
    feitos = 0
    for z0 in range(0, nz - 1, linhas):
        zz = zg[z0:z0 + linhas + 1]
        Yc, Zc = np.meshgrid(yg, zz, indexing='xy')          # (nz_f, ny)
        ativo = np.zeros(Yc.shape, bool)
        for d in (dmin, (dmin + dmax) / 2, dmax):
            pxc, pyc, _ = cam.pixel(np.full(Yc.shape, cam.D - d), Yc, Zc)
            ativo |= _amostra2(msd, (pyc - 0.5).ravel(), (pxc - 0.5).ravel()).reshape(Yc.shape) > -folga
        f = np.full((len(zz), ny, nx), -h, np.float32)
        iz, iy = np.nonzero(ativo)
        if len(iz):
            for c0 in range(0, len(iz), max(1, por_fatia // nx)):
                cz, cy = iz[c0:c0 + por_fatia // nx], iy[c0:c0 + por_fatia // nx]
                n = len(cz)
                X = np.broadcast_to(xg[None, :], (n, nx)).ravel()
                Y = np.repeat(yg[cy], nx)
                Z = np.repeat(zz[cz], nx)
                px, py, d = cam.pixel(X, Y, Z)
                px = px.astype(np.float32)
                py = py.astype(np.float32)
                d = d.astype(np.float32)
                lin, col = py - 0.5, px - 0.5
                f_cone = _amostra2(msd_c, lin, col, 3) * (2 * cam.tg * d / S)
                if not contorno:
                    # "forma da IA": o volume da rede manda; o contorno só limita
                    # com folga larga (corta restos longe do desenho)
                    f_cone = f_cone + 0.06 * S * (2 * cam.tg * d / S)
                lg, cg = py * esc - 0.5, px * esc - 0.5
                if contorno:
                    qpx = px + _amostra2(sp['dx'], lg, cg, 3) / esc
                    qpy = py + _amostra2(sp['dy'], lg, cg, 3) / esc
                else:
                    qpx, qpy = px, py
                Xq, Yq, Zq = cam.ponto(qpx, qpy, d)
                f_rede = _amostra3(coef, lo, passo, X, Yq, Zq, ordem=3)
                del Xq, Yq, Zq, qpx, qpy
                f_fill = (_amostra2(sp['tau'], lg, cg, 3) - np.abs(d - _amostra2(sp['centro'], lg, cg, 3))
                          - (1 - _amostra2(sp['w'], lg, cg, 3)) * 10.0)
                meio = _amostra2(sp['meio'], lg, cg, 3)
                if contorno:
                    a = np.maximum(f_rede, f_fill)
                    hh = np.maximum(k - np.abs(f_rede - f_fill), 0)
                    a += hh * hh / (4 * k)                            # união suave
                else:
                    a = f_rede
                    if mp['furos']:
                        f_b = (_amostra2(sp['b_tau'], lg, cg, 3) - np.abs(d - _amostra2(sp['b_centro'], lg, cg, 3))
                               - (1 - _amostra2(sp['b_w'], lg, cg, 3)) * 10.0)
                        hh = np.maximum(k - np.abs(a - f_b), 0)
                        a = np.maximum(a, f_b) + hh * hh / (4 * k)
                # nada fica muito mais fundo do que largo no desenho: uma ponta
                # fina encostada num corpo fundo não vira um feixe em profundidade
                # (o motor máximo tem profundidade confiável: sem esse limite)
                if limitar:
                    f_lim = PROFUNDIDADE_MAX * _amostra2(sp['tl'], lg, cg, 3) - np.abs(d - meio)
                    hh = np.maximum(k - np.abs(a - f_lim), 0)
                    a = np.minimum(a, f_lim) - hh * hh / (4 * k)
                else:
                    f_lim = None
                if contorno:
                    a = np.maximum(a, 1.2 * h - np.abs(d - meio))
                hh = np.maximum(k - np.abs(a - f_cone), 0)
                val = np.minimum(a, f_cone) - hh * hh / (4 * k)       # corte suave pelo cone
                f[cz, cy, :] = val.reshape(n, nx)
                del px, py, d, f_cone, f_rede, f_fill, f_lim, meio, a, hh, val, X, Y, Z
        feitos += len(zz) - 1
        if f.max() > 0 and f.min() < 0:
            # vértices no espaço de índices (o plano compartilhado entre fatias
            # tem índice inteiro exato nas duas: a costura não depende do float32)
            vv, ff, _, _ = marching_cubes(f, 0.0, allow_degenerate=False)
            vv = vv.astype(np.float64)
            vv[:, 0] += z0
            verts.append(vv)
            faces.append(ff.astype(np.int64) + nv)
            nv += len(vv)
        del f
        plano('campo', feitos / max(1, nz - 1))
    if not faces:
        raise ReconstrucaoError('Nada foi gerado: a silhueta está vazia.')
    V = np.vstack(verts)
    F = np.vstack(faces)
    del verts, faces
    # costura das fatias pelos índices; depois índice -> mundo (x, y, z)
    q = np.round(V * 4096).astype(np.int64)
    _, idx, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    V = V[idx]
    F = inv.reshape(-1)[F]
    V = np.column_stack([xg[0] + V[:, 2] * h, yg[0] + V[:, 1] * h, zg[0] + V[:, 0] * h])
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    return V, F, h, (nx * ny * nz)


def normais_vertice(V, F):
    """Normais suaves (média ponderada pela área das faces)."""
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for i in range(3):
        np.add.at(N, F[:, i], fn)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return N


def acabar_malha(V, F, tri_max, taubin, plano):
    """Peças soltas fora, suavização Taubin e (se passar do limite) redução.
    Volta (V, F, estanque) em arrays, sem os caches pesados do trimesh."""
    import trimesh
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    plano('malha', 0.05)
    # peças soltas (bolhas do campo) fora, sem criar um objeto por peça
    nv = len(V)
    g = coo_matrix((np.ones(2 * len(F), np.int8), (np.concatenate([F[:, 0], F[:, 1]]),
                                                    np.concatenate([F[:, 1], F[:, 2]]))), shape=(nv, nv))
    n_comp, rot = connected_components(g, directed=False)
    del g
    if n_comp > 1:
        cf = rot[F[:, 0]]
        tam = np.bincount(cf, minlength=n_comp)
        F = F[tam[cf] >= 0.002 * tam.max()]
        usados = np.unique(F)
        novo = np.full(nv, -1, np.int64)
        novo[usados] = np.arange(len(usados))
        V = V[usados]
        F = novo[F]
        del cf, tam, usados, novo
    del rot
    _liberar()
    m = trimesh.Trimesh(V, F, process=False, validate=False)
    del V, F
    plano('malha', 0.3)
    if m.volume < 0:
        m.invert()
    trimesh.smoothing.filter_taubin(m, lamb=0.5, nu=-0.53, iterations=taubin)
    plano('malha', 0.75)
    V = np.array(m.vertices, dtype=np.float64)
    F = np.array(m.faces, dtype=np.int64)
    del m
    _liberar()
    if len(F) > tri_max:
        import fast_simplification
        vv, ff = fast_simplification.simplify(V.astype(np.float32), F.astype(np.int32),
                                              target_reduction=1 - tri_max / len(F))
        V, F = vv.astype(np.float64), ff.astype(np.int64)
        _liberar()
    # estanque (fechada): nenhuma aresta de borda (usada por uma face só)
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    _, cont = np.unique(e[:, 0] * (len(V) + 1) + e[:, 1], return_counts=True)
    estanque = bool((cont >= 2).all())
    del e, cont
    plano('malha', 1.0)
    return V, F, estanque


# ---------------------------------------------------------------------------
# Câmera da entrada, amostragem e atlas UV
# ---------------------------------------------------------------------------

def projetar(p_rede, lado, cam=None):
    """Ponto no espaço da cena -> pixel (x, y) num quadrado de 'lado' px e
    profundidade, pela câmera da cena (padrão: a do TripoSR)."""
    D = cam.D if cam is not None else DIST_CAMERA
    t = cam.tg if cam is not None else np.tan(np.radians(FOV_GRAUS) / 2)
    d = D - p_rede[:, 0]
    u = p_rede[:, 1] / (d * t)
    v = p_rede[:, 2] / (d * t)
    return np.column_stack([(u + 1) / 2 * lado, (1 - v) / 2 * lado]), d


def _amostrar(img, xy):
    """Bilinear de img (H, W, C) float em posições de pixel (centro = +0.5)."""
    h, w = img.shape[:2]
    x = np.clip(xy[:, 0] - 0.5, 0, w - 1)
    y = np.clip(xy[:, 1] - 0.5, 0, h - 1)
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0)[:, None]
    fy = (y - y0)[:, None]
    return ((img[y0, x0] * (1 - fx) + img[y0, x1] * fx) * (1 - fy)
            + (img[y1, x0] * (1 - fx) + img[y1, x1] * fx) * fy)


def _ajuste_cor(origem, alvo, peso):
    """Afim 3x4 (mínimos quadrados ponderados, com regularização para a
    identidade) que leva a cor da rede para a paleta da imagem."""
    X = np.column_stack([origem, np.ones(len(origem))])
    W = peso[:, None]
    lam = 0.05 * max(1.0, float(peso.sum())) * 0.01
    A = X.T @ (X * W) + lam * np.eye(4)
    B = X.T @ (alvo * W) + lam * np.vstack([np.eye(3), np.zeros((1, 3))])
    return np.linalg.solve(A, B)


def _vizinhos(F):
    """Para cada face, as faces que dividem uma aresta com ela (-1 = nenhuma)."""
    M = len(F)
    e = np.sort(np.stack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1).reshape(-1, 2), axis=1)
    chave = e[:, 0].astype(np.int64) * (int(F.max()) + 1) + e[:, 1]
    ordem = np.argsort(chave, kind='stable')
    ck = chave[ordem]
    par = np.flatnonzero(ck[1:] == ck[:-1])
    a, b = ordem[par], ordem[par + 1]          # meias-arestas (face*3 + lado)
    viz = np.full(M * 3, -1, np.int64)
    viz[a] = b // 3
    viz[b] = a // 3
    return viz.reshape(M, 3)


def abrir_uv(V, F, lado, pad=3):
    """Atlas UV por projeção (como o "Smart UV Project" do Blender): cada face
    vai para o eixo (±x, ±y, ±z) mais alinhado à sua normal, faces vizinhas
    do mesmo eixo formam uma ilha, cada ilha é projetada no seu plano (sem
    distorção acima de ~55°) e as ilhas são empacotadas em prateleiras com
    a mesma densidade de texels. Segundos, mesmo com centenas de milhares de
    faces (o xatlas leva vários minutos nesse tamanho).
    Volta (vmap, faces novas, uv em [0, 1])."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    V = np.asarray(V, np.float64)
    F = np.asarray(F, np.int64)
    M = len(F)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    eixo = np.argmax(np.abs(fn), axis=1)
    rot = eixo * 2 + (fn[np.arange(M), eixo] >= 0)
    viz = _vizinhos(F)
    dirs = np.array([[-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0], [0, 0, -1], [0, 0, 1]], np.float64)
    # faces isoladas no rótulo errado viram ilhas de 1 triângulo: adota o do vizinho
    for _ in range(3):
        rv = np.where(viz >= 0, rot[np.maximum(viz, 0)], -1)
        sozinha = (rv != rot[:, None]).all(axis=1)
        cand = rv[sozinha, 0]
        ok = (cand >= 0) & (np.einsum('ij,ij->i', fn[sozinha], dirs[np.maximum(cand, 0)]) > 0.35)
        idx = np.flatnonzero(sozinha)[ok]
        if not len(idx):
            break
        rot[idx] = cand[ok]
    # ilhas grandes e recortadas (a frente inteira do personagem) desperdiçam
    # o retângulo que as envolve: corta numa grade no plano de projeção
    planos = np.array([[1, 2], [0, 2], [0, 1]])
    cent = V[F].mean(axis=1)
    e_f = rot // 2
    c2 = np.column_stack([cent[np.arange(M), planos[e_f, 0]], cent[np.arange(M), planos[e_f, 1]]])
    area_f = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    celula = np.sqrt(max(float(area_f.sum()), 1e-12) / 90)
    cel = np.floor(c2 / celula).astype(np.int64)
    grupo = (rot.astype(np.int64) * 1_000_003 + cel[:, 0]) * 1_000_003 + cel[:, 1]
    mesmo = (viz >= 0) & (grupo[np.maximum(viz, 0)] == grupo[:, None])
    i, k = np.nonzero(mesmo)
    g = coo_matrix((np.ones(len(i), np.int8), (i, viz[i, k])), shape=(M, M))
    n_ilhas, ilha = connected_components(g, directed=False)

    # vértices separados por ilha
    chave = ilha[:, None].astype(np.int64) * len(V) + F
    uniq, inv = np.unique(chave.reshape(-1), return_inverse=True)
    vmap = uniq % len(V)
    ilha_v = uniq // len(V)
    Fn = inv.reshape(-1, 3)
    eixo_ilha = np.zeros(n_ilhas, np.int64)
    eixo_ilha[ilha] = rot // 2
    ev = eixo_ilha[ilha_v]
    p2 = np.column_stack([V[vmap, planos[ev, 0]], V[vmap, planos[ev, 1]]])
    lo = np.full((n_ilhas, 2), np.inf)
    hi = np.full((n_ilhas, 2), -np.inf)
    np.minimum.at(lo, ilha_v, p2)
    np.maximum.at(hi, ilha_v, p2)
    tam = hi - lo
    # ilhas largas deitadas: prateleiras mais cheias
    deitar = tam[:, 1] > tam[:, 0]
    tam_e = np.where(deitar[:, None], tam[:, ::-1], tam)

    ordem = np.argsort(-tam_e[:, 1])

    def empacotar(esc):
        wpx = np.ceil(tam_e[:, 0] * esc).astype(np.int64) + 2 * pad + 1
        hpx = np.ceil(tam_e[:, 1] * esc).astype(np.int64) + 2 * pad + 1
        pos = np.zeros((n_ilhas, 2), np.int64)
        x = y = alt = 0
        for j in ordem:
            if x + wpx[j] > lado:
                y += alt
                x = alt = 0
            pos[j] = (x, y)
            x += wpx[j]
            alt = max(alt, hpx[j])
            if y + alt > lado:
                return None
        return pos

    # maior escala que ainda cabe (busca binária): mais texels por mm
    area = float(np.sum((tam_e[:, 0] + 1e-9) * (tam_e[:, 1] + 1e-9)))
    alto = (lado - 2 * pad) / np.sqrt(max(area, 1e-12))
    baixo = 0.0
    pos = None
    for _ in range(22):
        meio = (baixo + alto) / 2
        p = empacotar(meio)
        if p is None:
            alto = meio
        else:
            baixo, pos = meio, p
    if pos is None:
        raise ReconstrucaoError('Não foi possível montar o atlas da textura.')
    esc = baixo
    loc = p2 - lo[ilha_v]
    d = deitar[ilha_v]
    loc = np.where(d[:, None], loc[:, ::-1], loc)
    uv = (loc * esc + pos[ilha_v] + pad + 0.5) / lado
    return vmap, Fn, uv


# ---------------------------------------------------------------------------
# Textura (em blocos: 4096 px sem estourar a memória)
# ---------------------------------------------------------------------------

def registrar_desenho(modelo, desenho, iteracoes=(80, 60, 45, 30)):
    """Deslocamento suave u (2, G, G) que leva cada pixel da silhueta do
    MODELO ao ponto correspondente do DESENHO (desenho(x + u) ~ modelo(x)).

    É o que faz "o desenho se adaptar ao 3D": quando a forma 3D difere um
    pouco do desenho, cada traço vai para o lugar certo do corpo, sem
    distorcer nem se perder. Registro elástico tipo "demons" em várias
    escalas, sobre as distâncias assinadas (limitadas) das duas silhuetas."""
    from scipy import ndimage as ndi
    G = modelo.shape[0]

    def sd(m, K):
        d = ndi.distance_transform_edt(m) - ndi.distance_transform_edt(~m)
        return np.clip(d / K, -1, 1).astype(np.float32)
    u = np.zeros((2, 8, 8), np.float32)
    for nivel, its in zip((64, 128, 256, G), iteracoes):
        nivel = min(nivel, G)
        if u.shape[1] != nivel:
            f = nivel / u.shape[1]
            u = np.stack([ndi.zoom(u[i], f, order=1) * f for i in range(2)])
        z = nivel / G
        mm = ndi.zoom(modelo.astype(np.float32), z, order=1) > 0.5
        dd = ndi.zoom(desenho.astype(np.float32), z, order=1) > 0.5
        K = max(3.0, 0.04 * nivel)
        M_ = sd(mm, K)
        D_ = sd(dd, K)
        yy, xx = np.mgrid[0:nivel, 0:nivel].astype(np.float32)
        sig = max(1.0, nivel / 96)
        for _ in range(its):
            Dw = ndi.map_coordinates(D_, [yy + u[0], xx + u[1]], order=1, mode='nearest')
            dif = Dw - M_
            gy, gx = np.gradient(Dw)
            den = gx * gx + gy * gy + dif * dif / (K * K) + 1e-6
            u[0] -= np.clip(dif * gy / den, -2, 2)
            u[1] -= np.clip(dif * gx / den, -2, 2)
            u[0] = ndi.gaussian_filter(u[0], sig)
            u[1] = ndi.gaussian_filter(u[1], sig)
    final = ndi.map_coordinates(desenho.astype(np.float32), [np.mgrid[0:G, 0:G][0] + u[0], np.mgrid[0:G, 0:G][1] + u[1]],
                                order=1, mode='constant') > 0.5
    iou = float((final & modelo).sum() / max(1, (final | modelo).sum()))
    return u, iou


def _cor_base_pequena(quad, lado=1024):
    """Cores de preenchimento da imagem, sem traços finos nem hachuras
    (fechamento morfológico tira o que é escuro e fino; mediana limpa).
    Volta a imagem reduzida (float32) e a escala para o quadrado."""
    from scipy import ndimage as ndi
    from PIL import Image
    S = quad.shape[0]
    red = min(1.0, lado / S)
    t = max(8, round(S * red))
    rgb = np.asarray(Image.fromarray(quad).resize((t, t), Image.LANCZOS))[..., :3].astype(np.float32) / 255
    k = max(3, int(round(t * 0.012)) | 1)
    fech = np.stack([ndi.grey_closing(rgb[..., c], size=(k, k)) for c in range(3)], -1)
    fech = np.stack([ndi.median_filter(fech[..., c], size=k) for c in range(3)], -1)
    return fech.astype(np.float32), t / S


def _amostrar_u8(img, xy):
    """Bilinear de uma imagem uint8 (H, W, C) em posições de pixel; volta float32 0..1."""
    h, w = img.shape[:2]
    x = np.clip(xy[:, 0] - 0.5, 0, w - 1)
    y = np.clip(xy[:, 1] - 0.5, 0, h - 1)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0).astype(np.float32)[:, None]
    fy = (y - y0).astype(np.float32)[:, None]
    g = lambda yy, xx: img[yy, xx].astype(np.float32)
    return (((g(y0, x0) * (1 - fx) + g(y0, x1) * fx) * (1 - fy) + (g(y1, x0) * (1 - fx) + g(y1, x1) * fx) * fy)
            / 255).astype(np.float32)


def assar_textura(Vm, Fm, codigo, decodificador, renderizador, quad, lado_tex, plano, cam=None, adaptar=False):
    """Atlas UV + textura. Volta (V, F, N, UV, imagem RGB uint8, cobertura da frente)."""
    from scipy.spatial import cKDTree
    plano('uv', 0.05)
    Nm = normais_vertice(Vm, Fm)
    vmap, F, uv = abrir_uv(Vm, Fm, lado_tex)
    V = Vm[vmap]
    N = Nm[vmap]
    del vmap, Nm
    _liberar()
    plano('uv', 1.0)

    plano('textura', 0.0, 'Pintando a textura: visibilidade')
    S = quad.shape[0]
    lado_vis = 2048
    xy_cam, d_cam = projetar(Vm, lado_vis, cam)
    _, _, zbuf = rasterizar(xy_cam, Fm, lado_vis, lado_vis, z=d_cam)
    del xy_cam, d_cam
    _liberar()
    # o desenho se adapta à forma 3D: deslocamento da silhueta do modelo
    # (vista da câmera) para a do desenho, aplicado a cada amostra da frente
    from scipy import ndimage as ndi
    G2 = 512
    sil_modelo = ndi.zoom(np.isfinite(zbuf).astype(np.float32), G2 / lado_vis, order=1) > 0.5
    sil_desenho = ndi.zoom((quad[..., 3] > 127).astype(np.float32), G2 / quad.shape[0], order=1) > 0.5
    if adaptar:
        plano('textura', 0.01, 'Adaptando o desenho à forma 3D')
        desl, ajuste = registrar_desenho(sil_modelo, sil_desenho)
    else:
        desl, ajuste = None, None

    def adaptado(xy):
        if desl is None:
            return xy
        e = G2 / quad.shape[0]
        lin, col = xy[:, 1] * e - 0.5, xy[:, 0] * e - 0.5
        dy = ndi.map_coordinates(desl[0], [lin, col], order=1, mode='nearest')
        dx = ndi.map_coordinates(desl[1], [lin, col], order=1, mode='nearest')
        return np.column_stack([xy[:, 0] + dx / e, xy[:, 1] + dy / e])
    ids, bar = rasterizar(uv * lado_tex, F, lado_tex, lado_tex)
    ids = ids[::-1].reshape(-1)                         # v do glTF cresce para cima
    bar = bar[::-1].reshape(-1, 3)
    cheio = np.flatnonzero(ids >= 0)
    n_tex = len(cheio)
    base_p, esc_b = _cor_base_pequena(quad)
    lum_w = np.array([0.299, 0.587, 0.114], np.float32)
    tamanho = float(np.ptp(Vm, axis=0).max())
    BL = 250_000
    tol = 0.012 * float(np.ptp(Vm, axis=0).max()) / 0.8     # relativo ao tamanho do objeto

    def pontos(sel):
        t = ids[sel]
        b = bar[sel].astype(np.float64)
        P = V[F[t, 0]] * b[:, :1] + V[F[t, 1]] * b[:, 1:2] + V[F[t, 2]] * b[:, 2:3]
        Nn = N[F[t, 0]] * b[:, :1] + N[F[t, 1]] * b[:, 1:2] + N[F[t, 2]] * b[:, 2:3]
        Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-9)
        return P, Nn

    # 1ª passada: peso da frente, cor da imagem, cor da rede; amostra de referência
    peso_t = np.zeros(n_tex, np.float16)
    img_t = np.zeros((n_tex, 3), np.uint8)
    rede_t = np.zeros((n_tex, 3), np.uint8)
    ref_P, ref_base, ref_img, ref_rede = [], [], [], []
    rng = np.random.default_rng(0)
    for i in range(0, n_tex, BL):
        sel = cheio[i:i + BL]
        P, Nn = pontos(sel)
        xy_q, d_t = projetar(P, S, cam)
        xy_v = xy_q * (lado_vis / S)
        xi = np.clip(xy_v[:, 0].astype(int), 0, lado_vis - 1)
        yi = np.clip(xy_v[:, 1].astype(int), 0, lado_vis - 1)
        z_viz = zbuf[yi, xi]
        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            z_viz = np.minimum(z_viz, zbuf[np.clip(yi + ddy, 0, lado_vis - 1), np.clip(xi + ddx, 0, lado_vis - 1)])
        visivel = d_t <= z_viz + tol
        vis = np.column_stack([(cam.D if cam is not None else DIST_CAMERA) - P[:, 0], -P[:, 1], -P[:, 2]])
        vis /= np.linalg.norm(vis, axis=1, keepdims=True)
        cos = np.sum(Nn * vis, axis=1)
        xy_a = adaptado(xy_q)
        am = _amostrar_u8(quad, xy_a)
        p = np.clip((cos - 0.08) / 0.30, 0, 1) * visivel * np.clip((am[:, 3] - 0.5) / 0.4, 0, 1)
        p = p * p * (3 - 2 * p)
        cr = _consultar(decodificador, renderizador, codigo, P, 'color') if codigo is not None else None
        peso_t[i:i + BL] = p
        img_t[i:i + BL] = np.clip(am[:, :3] * 255 + 0.5, 0, 255)
        if cr is not None:
            rede_t[i:i + BL] = np.clip(cr * 255 + 0.5, 0, 255)
        r = np.flatnonzero(p > 0.85)
        if len(r):
            r = r[rng.random(len(r)) < min(1.0, 300_000 / max(1, n_tex))]
            ref_P.append(P[r].astype(np.float32))
            ref_base.append(_amostrar(base_p, xy_a[r] * esc_b).astype(np.float32))
            ref_img.append(am[r, :3])
            if cr is not None:
                ref_rede.append(cr[r].astype(np.float32))
        plano('textura', 0.45 * min(1.0, (i + BL) / max(1, n_tex)), 'Pintando a textura: frente')
    cobertura = float(peso_t.astype(np.float32).mean()) if n_tex else 0.0

    # cor da rede ajustada à paleta da imagem; base da frente levada às costas
    M = None
    arvore = None
    if ref_P and sum(len(x) for x in ref_P) > 500:
        ref_P = np.concatenate(ref_P)
        ref_base = np.concatenate(ref_base)
        ref_img = np.concatenate(ref_img)
        if ref_rede:
            ref_rede = np.concatenate(ref_rede)
            M = _ajuste_cor(ref_rede.astype(np.float64), ref_img.astype(np.float64), np.ones(len(ref_rede)))
            ref_rede_aj = np.clip(np.column_stack([ref_rede, np.ones(len(ref_rede))]) @ M, 0, 1).astype(np.float32)
            ref_lum = ref_rede_aj @ lum_w
        arvore = cKDTree(ref_P)
        # cor dominante do corpo (proteção para áreas escuras finas, ver abaixo)
        lum_base = ref_base @ lum_w
        dominante = np.median(ref_base[lum_base >= np.median(lum_base)], axis=0)

    # 2ª passada: cor final
    tex = np.zeros((lado_tex * lado_tex, 3), np.uint8)
    for i in range(0, n_tex, BL):
        sel = cheio[i:i + BL]
        p = peso_t[i:i + BL].astype(np.float32)[:, None]
        ci = img_t[i:i + BL].astype(np.float32) / 255
        cr = rede_t[i:i + BL].astype(np.float32) / 255
        esc = np.flatnonzero(p[:, 0] < 0.999)
        cor = ci.copy()
        if len(esc) and codigo is None and arvore is not None:
            # sem a cor da rede (motor de máxima qualidade: só forma): as costas
            # recebem a cor de base da frente levada ao ponto mais próximo; onde
            # ela é escura num personagem claro (o miolo preto de uma orelha
            # fina "vazando" para trás), puxa para a cor dominante do corpo
            P, _ = pontos(sel[esc])
            dist, viz = arvore.query(P.astype(np.float32), k=8, workers=-1)
            w = (1.0 / np.maximum(dist, 1e-6) ** 2).astype(np.float32)
            prop = np.einsum('nk,nkc->nc', w, ref_base[viz]) / w.sum(axis=1, keepdims=True)
            lp = prop @ lum_w
            ld = float(dominante @ lum_w)
            puxa = np.clip((0.3 - lp) / 0.3, 0, 1) * 0.75 * (ld > 0.5)
            # a cor da frente só vale perto de onde ela é vista: as costas de uma
            # cabeça não herdam o olho preto do outro lado (parecia um buraco)
            longe = np.clip((dist.mean(axis=1) - 0.02 * tamanho) / (0.04 * tamanho), 0, 1)
            puxa = np.maximum(puxa, longe)[:, None]
            c_r = prop * (1 - puxa) + dominante[None, :] * puxa
            cor[esc] = ci[esc] * p[esc] + c_r * (1 - p[esc])
        elif len(esc):
            c_r = cr[esc]
            if M is not None:
                c_r = np.clip(np.column_stack([c_r, np.ones(len(c_r))]) @ M, 0, 1).astype(np.float32)
            if arvore is not None:
                P, _ = pontos(sel[esc])
                dist, viz = arvore.query(P.astype(np.float32), k=8, workers=-1)
                w = (1.0 / np.maximum(dist, 1e-6) ** 2).astype(np.float32)
                ws = w.sum(axis=1, keepdims=True)
                prop = np.einsum('nk,nkc->nc', w, ref_base[viz]) / ws
                lum = c_r @ lum_w
                lum_viz = np.einsum('nk,nk->n', w, ref_lum[viz]) / ws[:, 0]
                relevo = np.clip(lum / np.maximum(lum_viz, 0.05), 0.75, 1.15)[:, None]
                escondida = np.clip(prop * (0.35 + 0.65 * relevo), 0, 1)
                # onde a cor levada da frente discorda muito da reconstrução
                # (o miolo preto da orelha indo para trás dela), vale a rede
                confia = (0.85 - 0.6 * np.clip((np.abs(escondida @ lum_w - lum) - 0.2) / 0.35, 0, 1))[:, None]
                c_r = confia * escondida + (1 - confia) * c_r
            cor[esc] = ci[esc] * p[esc] + c_r * (1 - p[esc])
        tex[sel] = np.clip(cor * 255 + 0.5, 0, 255).astype(np.uint8)
        plano('textura', 0.45 + 0.5 * min(1.0, (i + BL) / max(1, n_tex)), 'Pintando a textura: costas e lados')
    # sangria: texels vazios recebem a cor do vizinho preenchido (sem costura no mipmap)
    vazio = np.ones(lado_tex * lado_tex, bool)
    vazio[cheio] = False
    vazio = vazio.reshape(lado_tex, lado_tex)
    tex = tex.reshape(lado_tex, lado_tex, 3)
    for _ in range(6):
        if not vazio.any():
            break
        soma = np.zeros(tex.shape, np.float32)
        cont = np.zeros(vazio.shape, np.float32)
        for ddy, ddx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ok = np.roll(~vazio, (ddy, ddx), axis=(0, 1))
            soma += np.roll(tex, (ddy, ddx), axis=(0, 1)) * ok[..., None]
            cont += ok
        novo = vazio & (cont > 0)
        tex[novo] = (soma[novo] / cont[novo][:, None]).astype(np.uint8)
        vazio &= ~novo
    if vazio.any():
        tex[vazio] = tex[~vazio].reshape(-1, 3)[::97].mean(axis=0).astype(np.uint8)
    plano('textura', 1.0)
    return V, F, N, uv.astype(np.float64), tex, cobertura, ajuste


# ---------------------------------------------------------------------------
# Etapa completa
# ---------------------------------------------------------------------------

def construir(pasta, peca, largura_mm, q, progresso=lambda e, f: None, orcamento_mb=1200):
    """Personagem 3D fiel ao desenho. q['nivel'] = 'preview' ou 'hd'."""
    from PIL import Image
    nivel = q.get('nivel', 'preview') if q.get('nivel') in QUALIDADE else 'preview'
    Q = QUALIDADE[nivel]
    caminho = os.path.join(pasta, 'sem_fundo.png')
    if not os.path.exists(caminho):
        raise ReconstrucaoError('A imagem sem fundo não foi encontrada: reprocesse a imagem.')
    t0 = time.time()
    rgba = np.asarray(Image.open(caminho).convert('RGBA'))
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    dims = ((xs.max() - xs.min() + 1) if len(xs) else None, (ys.max() - ys.min() + 1) if len(ys) else None)
    motor, aviso = escolher_motor(peca.get('motor', 'auto'))
    baixar = 0
    if motor == 'baixar':
        from Vetor3D import v3d_modelos as MD
        baixar = MD.estado('maximo')['falta_bytes']
    etapas = plano_etapas(pasta, nivel, *dims, motor='leve' if motor == 'leve' else 'maximo', baixar_bytes=baixar)
    plano = Plano(progresso, etapas)
    plano('imagem')
    entrada, quad = preparar_entrada(rgba, Q['quad'])
    del rgba

    if motor == 'baixar':
        from Vetor3D import v3d_modelos as MD

        def mostrar(pr):
            falta = f' · falta ~{MD._fmt_tempo(pr["eta"])}' if pr.get('eta') else ''
            vel = f' · {pr["velocidade"] / MD.MB:.1f} MB/s' if pr.get('velocidade') else ''
            plano('modelo', pr['frac'], f'Baixando o modelo de máxima qualidade: {pr["feito"] / MD.GB:.2f} de '
                                        f'{pr["total"] / MD.GB:.2f} GB{vel}{falta}')
        plano('modelo')
        try:
            MD.baixar(MD.estado('maximo'), mostrar)
            motor = 'maximo'
        except Exception as ex:  # noqa: BLE001
            motor, aviso = 'leve', f'Não foi possível baixar o motor de máxima qualidade ({type(ex).__name__}): usado o leve.'
    codigo = decodificador = renderizador = None
    if motor == 'maximo':
        plano('modelo', 1.0)
        try:
            sdf, lo, passo, cam = corpo_hunyuan(pasta, quad, plano)
        except MemoryError:
            raise
        except Exception as ex:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            motor, aviso = 'leve', f'O motor de máxima qualidade falhou ({type(ex).__name__}): usado o leve.'
    if motor == 'leve':
        cam = Camera(quad.shape[0])
        codigo, decodificador, renderizador, chave = triplano(pasta, entrada, plano)
        sdf, lo, passo = corpo(pasta, chave, codigo, decodificador, renderizador, plano)
    mp = mapas(sdf, lo, passo, quad, cam, plano)
    _liberar()
    # padrão: a forma 3D da IA fica limpa e o DESENHO se adapta a ela; "exato"
    # deforma o 3D até o contorno do desenho. O motor leve sempre usa o exato
    # (o corpo do TripoSR sozinho é grosseiro demais para valer como forma).
    contorno = peca.get('contorno', 'ia') == 'exato' or motor == 'leve'
    # resolução que dá ~o limite de triângulos direto (sem a redução pesada
    # depois): área da superfície estimada pelos voxels de borda do corpo
    borda = (sdf > 0) & ~np.all([np.roll(sdf > 0, d, a) for a in range(3) for d in (1, -1)], axis=0)
    area = float(borda.sum()) * passo * passo * 1.6
    del borda
    ext_img = 2 * cam.tg * cam.D                            # largura da imagem no mundo
    ys_m, xs_m = np.nonzero(quad[..., 3] > 127)
    lado_obj = max(np.ptp(xs_m), np.ptp(ys_m)) / quad.shape[0] * ext_img
    n_grade = Q['N']
    tri_est = 2.2 * area / (lado_obj / n_grade) ** 2
    if tri_est > Q['tri_max'] * 1.15:
        n_grade = max(200, int(n_grade * np.sqrt(Q['tri_max'] * 1.1 / tri_est)))
    V, F, h, voxels = campo_malha(sdf, lo, passo, quad, cam, mp, n_grade, orcamento_mb, plano,
                                  limitar=motor == 'leve', contorno=contorno)
    del sdf
    _liberar()
    V, F, estanque = acabar_malha(V, F, Q['tri_max'], Q['taubin'], plano)

    # espessura: estica/achata só a profundidade (eixo da câmera)
    esp = float(peca.get('espessura', 1.0) or 1.0)
    if abs(esp - 1.0) > 1e-3:
        cx = float(np.median(V[:, 0]))
        V[:, 0] = cx + (V[:, 0] - cx) * esp

    # fidelidade: silhueta vista da câmera contra o desenho
    S = quad.shape[0]
    red = min(1.0, 1024 / S)
    xy_c, d_c = projetar(V, round(S * red), cam)
    ids_c, _, _ = rasterizar(xy_c, F, round(S * red), round(S * red), z=d_c)
    alvo = np.asarray(Image.fromarray(quad[..., 3]).resize((round(S * red),) * 2, Image.BILINEAR)) > 127
    ren = ids_c >= 0
    iou = float((ren & alvo).sum() / max(1, (ren | alvo).sum()))
    del ids_c, xy_c, d_c
    _liberar()

    V, F, N, UV, img, cobertura, ajuste_tex = assar_textura(V, F, codigo, decodificador, renderizador, quad, Q['tex'],
                                                             plano, cam, adaptar=not contorno)
    plano('saida', 0.1)
    tex = os.path.join(pasta, 'textura.jpg')
    Image.fromarray(img).save(tex, quality=93)

    # espaço da rede -> Vetor3D (x direita, y cima, z para o observador), em mm
    X = np.column_stack([V[:, 1], V[:, 2], V[:, 0]])
    Nx = np.column_stack([N[:, 1], N[:, 2], N[:, 0]])
    lo3, hi3 = X.min(axis=0), X.max(axis=0)
    mm = float(largura_mm) / max(1e-9, hi3[0] - lo3[0])
    Vmm = (X - (lo3 + hi3) / 2) * mm
    # a troca de eixos (y, z, x) é uma rotação: a orientação das faces se mantém
    media = img.reshape(-1, 3)[::97].mean(axis=0)
    cor = '#%02x%02x%02x' % tuple(int(c) for c in media)
    parte = {'v': Vmm, 'f': F, 'n': Nx, 'uv': UV, 'textura': tex, 'cor': cor,
             'metal': float(peca.get('metal', 0.0)), 'rugosidade': float(peca.get('rugosidade', 0.55))}
    medido = plano.encerrar()
    previsto = {k: s for k, _, s in etapas}
    info = {'estanque': estanque, 'grade': [int(n_grade)], 'voxels': int(voxels), 'aviso': aviso,
            'metodo': 'reconstrucao', 'motor': motor, 'desenho_adaptado': ajuste_tex, 'fidelidade_silhueta': round(iou, 4), 'cobertura_frente': round(cobertura, 3),
            'partes_preenchidas': round(mp['falta'], 3), 'tempo': round(time.time() - t0, 1),
            'tempos': {k: round(v, 2) for k, v in medido.items()},
            'previstos': {k: round(v, 2) for k, v in previsto.items()}}
    del decodificador, renderizador, codigo
    gc.collect()
    return parte, info
