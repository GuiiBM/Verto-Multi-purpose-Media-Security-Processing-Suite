"""Vetor3D · motor de máxima qualidade: Hunyuan3D-2 mini (Tencent).

Gera a FORMA 3D a partir da imagem com muito mais fidelidade que o TripoSR
(é o melhor modelo aberto de imagem para forma 3D que cabe num computador
sem placa de vídeo). O resto do pipeline (silhueta exata do desenho,
textura, malha final) é o mesmo do v3d_reconstrucao: este módulo só troca a
fonte do "corpo".

Pensado para rodar no processador com pouca memória:
- os pesos (fp16, 3,8 GB) ficam no disco, mapeados (mmap): o sistema lê só o
  que precisa e pode descartar a qualquer momento;
- as redes são montadas sem alocar memória (dispositivo "meta") e cada camada
  linear converte o seu peso para fp32 só na hora do cálculo;
- tudo roda num processo filho, que termina no fim e devolve a memória;
- o progresso de cada passo vai para um arquivo (a fila mostra quanto falta).

Licença: Tencent Hunyuan 3D 2.0 Community License (vale fora da UE, Reino
Unido e Coreia do Sul); o texto está em Vetor3D/hy3dgen/LICENSE.
"""
import json
import os
import struct
import time

import numpy as np

REPO = 'tencent/Hunyuan3D-2mini'
PASTA_DIT = 'hunyuan3d-dit-v2-mini-turbo'
PASTA_VAE = 'hunyuan3d-vae-v2-mini-turbo'
ARQUIVOS = [f'{PASTA_DIT}/config.yaml', f'{PASTA_DIT}/model.fp16.safetensors',
            f'{PASTA_VAE}/config.yaml', f'{PASTA_VAE}/model.fp16.safetensors']
TAMANHO_GB = 4.3
RAM_MINIMA_GB = 6.0          # máquinas com menos RAM total usam o motor leve (TripoSR)
PASSOS = 5                   # difusão "turbo" (destilada para poucos passos)
RESOLUCAO = 256              # grade do volume (octree)
VERSAO = 1


class HunyuanError(Exception):
    pass


# ---------------------------------------------------------------------------
# Disponibilidade
# ---------------------------------------------------------------------------

def caminhos():
    """Arquivos do modelo já baixados (None se falta algum)."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None
    saida = {}
    for f in ARQUIVOS:
        p = try_to_load_from_cache(REPO, f)
        if not isinstance(p, str) or not os.path.exists(p):
            return None
        saida[f] = p
    return saida


def adequado():
    """O computador comporta o motor de máxima qualidade? (RAM total)"""
    try:
        import psutil
        return psutil.virtual_memory().total / 1024 ** 3 >= RAM_MINIMA_GB
    except Exception:  # noqa: BLE001
        return True


def disponivel():
    return adequado() and caminhos() is not None


# ---------------------------------------------------------------------------
# Pesos mapeados do disco
# ---------------------------------------------------------------------------

def _safetensors_mmap(caminho, prefixo=None):
    """Lê um .safetensors sem copiar: cada tensor aponta para o arquivo mapeado."""
    import torch
    with open(caminho, 'rb') as fh:
        n = struct.unpack('<Q', fh.read(8))[0]
        cab = json.loads(fh.read(n))
    cab.pop('__metadata__', None)
    mm = np.memmap(caminho, dtype=np.uint8, mode='r', offset=8 + n)
    tipos = {'F16': np.float16, 'F32': np.float32, 'BF16': np.uint16}
    saida = {}
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')          # tensor somente leitura (não é escrito)
        for nome, info in cab.items():
            if prefixo is not None:
                if not nome.startswith(prefixo + '.'):
                    continue
                chave = nome[len(prefixo) + 1:]
            else:
                chave = nome
            a, b = info['data_offsets']
            arr = mm[a:b].view(tipos[info['dtype']]).reshape(info['shape'])
            t = torch.from_numpy(arr)
            if info['dtype'] == 'BF16':
                t = t.view(torch.bfloat16)
            saida[chave] = t
    return saida


def _preparar_cpu(modulo):
    """Camadas lineares: peso fp16 do disco, convertido para fp32 só na hora.
    Demais parâmetros (normas, embeddings, convolução) viram fp32 de vez
    (são pequenos)."""
    import torch
    from torch import nn
    for m in modulo.modules():
        if isinstance(m, nn.Linear):
            continue
        for nome, p in list(m.named_parameters(recurse=False)):
            if p.dtype != torch.float32:
                setattr(m, nome, nn.Parameter(p.detach().float(), requires_grad=False))
    return modulo


def _linear_fp32():
    import torch.nn.functional as F
    from torch import nn

    def forward(self, x):
        w = self.weight if self.weight.dtype == x.dtype else self.weight.to(x.dtype)
        b = self.bias
        if b is not None and b.dtype != x.dtype:
            b = b.to(x.dtype)
        return F.linear(x, w, b)
    nn.Linear.forward = forward


def _renomear_dinov2(sd, chaves):
    """Pesos salvos com o DINOv2 do transformers 4.x -> nomes do 5.x."""
    chaves = set(chaves)
    if all(k in chaves for k in sd):
        return sd
    trocas = [('.encoder.layer.', '.layers.'), ('.attention.attention.query.', '.attention.q_proj.'),
              ('.attention.attention.key.', '.attention.k_proj.'), ('.attention.attention.value.', '.attention.v_proj.'),
              ('.attention.output.dense.', '.attention.o_proj.'), ('.layer_scale1.lambda1', '.layer_scale1.lambda1'),
              ('.mlp.weights_in.', '.mlp.weights_in.'), ('.mlp.weights_out.', '.mlp.weights_out.')]
    novo = {}
    for k, v in sd.items():
        n = k
        if n not in chaves:
            for a, b in trocas:
                n = n.replace(a, b)
        novo[n if n in chaves else k] = v
    return novo


def _carregar(modulo, sd, nome, opcionais=()):
    faltam, sobram = modulo.load_state_dict(sd, strict=False, assign=True)
    faltam = [k for k in faltam if not k.endswith('frequencies') and not k.startswith(tuple(opcionais))]
    if faltam:
        raise HunyuanError(f'Pesos que não casaram em {nome}: {faltam[:4]}…')


# ---------------------------------------------------------------------------
# Processo filho: imagem -> volume (logits) na grade do Hunyuan
# ---------------------------------------------------------------------------

def _progresso(arq, etapa, frac):
    try:
        with open(arq + '.tmp', 'w') as fh:
            json.dump({'etapa': etapa, 'frac': frac, 't': time.time()}, fh)
        os.replace(arq + '.tmp', arq)
    except OSError:
        pass


def gerar(rgba_png, saida_npz, arq_progresso, threads=None):
    """Roda no processo filho. Salva logits (float16) da grade RESOLUCAO³+1
    no espaço do Hunyuan ([-1.01, 1.01]³)."""
    import torch
    import yaml
    torch.set_num_threads(max(1, int(threads or (os.cpu_count() or 2) - 1)))
    _linear_fp32()
    arqs = caminhos()
    if arqs is None:
        raise HunyuanError('O modelo Hunyuan3D não está baixado.')
    with open(arqs[f'{PASTA_DIT}/config.yaml'], encoding='utf-8') as fh:
        cfg = yaml.safe_load(fh)
    with open(arqs[f'{PASTA_VAE}/config.yaml'], encoding='utf-8') as fh:
        cfg_vae = yaml.safe_load(fh)
    pesos = arqs[f'{PASTA_DIT}/model.fp16.safetensors']

    cache_lat = saida_npz + '.latentes.npy'
    lat = None
    if os.path.exists(cache_lat):
        try:
            lat = torch.from_numpy(np.load(cache_lat)).float()
        except Exception:  # noqa: BLE001
            lat = None
    if lat is None:
        lat = _difusao(cfg, cfg_vae, pesos, rgba_png, arq_progresso)
        np.save(cache_lat + '.tmp.npy', lat.numpy())
        os.replace(cache_lat + '.tmp.npy', cache_lat)
    _volume(cfg_vae, arqs, lat, saida_npz, arq_progresso)


def _difusao(cfg, cfg_vae, pesos, rgba_png, arq_progresso):
    import gc
    import torch
    from PIL import Image
    # 1) imagem -> entrada (fundo branco, 85% de ocupação, 1022 px)
    _progresso(arq_progresso, 'imagem', 0.0)
    from Vetor3D.hy3dgen.shapegen.preprocessors import ImageProcessorV2
    proc = ImageProcessorV2(**cfg['image_processor']['params'])
    ent = proc(Image.open(rgba_png).convert('RGBA'))

    # 2) leitura da imagem pelo DINOv2-giant
    _progresso(arq_progresso, 'leitura', 0.0)
    from Vetor3D.hy3dgen.shapegen.models.conditioner import SingleImageEncoder
    with torch.device('meta'):
        cond_mod = SingleImageEncoder(**cfg['conditioner']['params'])
    sd = _safetensors_mmap(pesos, 'conditioner')
    sd = _renomear_dinov2(sd, cond_mod.state_dict().keys())
    _carregar(cond_mod, sd, 'leitor de imagem')
    _preparar_cpu(cond_mod).eval()
    with torch.no_grad():
        cond = cond_mod(image=ent['image'].float(), mask=ent['mask'].float())
    cond = {k: v.float() for k, v in cond.items()}
    del cond_mod, sd
    gc.collect()

    # 3) difusão (5 passos, orientação embutida)
    from Vetor3D.hy3dgen.shapegen.models.denoisers.hunyuan3ddit import Hunyuan3DDiT
    from Vetor3D.hy3dgen.shapegen.schedulers import ConsistencyFlowMatchEulerDiscreteScheduler
    with torch.device('meta'):
        dit = Hunyuan3DDiT(**cfg['model']['params'])
    _carregar(dit, _safetensors_mmap(pesos, 'model'), 'difusão')
    _preparar_cpu(dit).eval()
    agendador = ConsistencyFlowMatchEulerDiscreteScheduler(**cfg['scheduler']['params'])
    sigmas = np.linspace(0, 1, PASSOS)
    agendador.set_timesteps(sigmas=sigmas, device='cpu')
    tempos = agendador.timesteps
    n_lat = int(cfg_vae['params']['num_latents'])
    g = torch.Generator().manual_seed(12345)
    lat = torch.randn((1, n_lat, int(cfg_vae['params']['embed_dim'])), generator=g, dtype=torch.float32)
    guia = torch.tensor([5.0], dtype=torch.float32)
    with torch.no_grad():
        for i, t in enumerate(tempos):
            _progresso(arq_progresso, 'difusao', i / len(tempos))
            ts = t.expand(1).to(torch.float32) / agendador.config.num_train_timesteps
            ruido = dit(lat, ts, cond, guidance=guia)
            lat = agendador.step(ruido, t, lat).prev_sample
    del dit, cond
    gc.collect()
    return lat


def _volume(cfg_vae, arqs, lat, saida_npz, arq_progresso):
    import torch
    # 4) volume (decodificador rápido FlashVDM, só refina perto da superfície)
    _progresso(arq_progresso, 'volume', 0.0)
    from Vetor3D.hy3dgen.shapegen.models.autoencoders.model import ShapeVAE
    from Vetor3D.hy3dgen.shapegen.models.autoencoders.attention_blocks import FourierEmbedder
    p_vae = dict(cfg_vae['params'])
    with torch.device('meta'):
        vae = ShapeVAE(**p_vae)
    _carregar(vae, _safetensors_mmap(arqs[f'{PASTA_VAE}/model.fp16.safetensors']), 'decodificador',
              opcionais=('encoder.', 'pre_kl.'))       # o codificador só serve para treino
    fe = FourierEmbedder(num_freqs=p_vae.get('num_freqs', 8), include_pi=p_vae.get('include_pi', True))
    for m in vae.modules():
        if hasattr(m, 'fourier_embedder'):
            m.fourier_embedder = fe
    _preparar_cpu(vae).eval()
    # o decodificador de geometria é chamado milhares de vezes: fp32 de vez (é pequeno)
    vae.geo_decoder.float()
    vae.enable_flashvdm_decoder(enabled=True, adaptive_kv_selection=True, topk_mode='mean', mc_algo='mc')
    with torch.no_grad():
        lat = vae(lat / vae.scale_factor)
        _progresso(arq_progresso, 'volume', 0.1)
        grade = vae.volume_decoder(lat, vae.geo_decoder, bounds=1.01, num_chunks=8000,
                                   octree_resolution=RESOLUCAO, mc_level=0.0, enable_pbar=False)
    g = grade[0].float().numpy()
    np.savez_compressed(saida_npz + '.tmp.npz', logits=np.nan_to_num(g, nan=np.nan).astype(np.float16),
                        limite=1.01, versao=VERSAO)
    os.replace(saida_npz + '.tmp.npz', saida_npz)
    _progresso(arq_progresso, 'fim', 1.0)
