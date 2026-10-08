"""Vetor3D · modelos de IA: o que existe, o que cabe e o download.

Dois motores para o personagem 3D:
- maximo (Hunyuan3D-2 mini, ~4,3 GB): forma 3D muito mais fiel; precisa de
  ~6 GB de RAM no total e espaço em disco;
- leve (TripoSR, ~1,7 GB): roda em qualquer máquina; também é a reserva
  quando o máximo não cabe (disco, RAM) ou falha.

Usado pelo instalador (`python -m Vetor3D.v3d_modelos --instalar`) e pelo app
(primeira geração sem o modelo). Antes de baixar, verifica o espaço livre e o
que já está no cache do Hugging Face (arquivos completos não são baixados de
novo; downloads interrompidos continuam de onde pararam; arquivos que mudaram
no servidor são atualizados) e mostra velocidade e tempo estimado.
"""
import os
import shutil
import sys
import threading
import time

GB = 1024 ** 3
MB = 1024 ** 2
FOLGA_DISCO = 1.5 * GB        # o que sempre fica livre no disco depois dos downloads

MOTORES = {
    'leve': {
        'nome': 'TripoSR (motor leve)',
        'arquivos': [('stabilityai/TripoSR', 'config.yaml'), ('stabilityai/TripoSR', 'model.ckpt'),
                     ('facebook/dino-vitb16', 'config.json')],
        'tamanho': 1.68 * GB,
    },
    'maximo': {
        'nome': 'Hunyuan3D-2 mini (máxima qualidade)',
        'arquivos': [('tencent/Hunyuan3D-2mini', f) for f in (
            'hunyuan3d-dit-v2-mini-turbo/config.yaml', 'hunyuan3d-dit-v2-mini-turbo/model.fp16.safetensors',
            'hunyuan3d-vae-v2-mini-turbo/config.yaml', 'hunyuan3d-vae-v2-mini-turbo/model.fp16.safetensors')],
        'tamanho': 4.23 * GB,
    },
}


def pasta_cache():
    try:
        from huggingface_hub import constants
        return constants.HF_HUB_CACHE
    except Exception:  # noqa: BLE001
        return os.path.join(os.path.expanduser('~'), '.cache', 'huggingface', 'hub')


def espaco_livre():
    p = pasta_cache()
    while p and not os.path.exists(p):
        p = os.path.dirname(p)
    return shutil.disk_usage(p or os.path.expanduser('~')).free


def _local(repo, arquivo):
    try:
        from huggingface_hub import try_to_load_from_cache
        p = try_to_load_from_cache(repo, arquivo)
        return p if isinstance(p, str) and os.path.exists(p) else None
    except Exception:  # noqa: BLE001
        return None


def _remoto(repo, arquivo):
    """(tamanho, etag) no servidor, ou None sem internet."""
    try:
        from huggingface_hub import get_hf_file_metadata, hf_hub_url
        meta = get_hf_file_metadata(hf_hub_url(repo, arquivo), timeout=15)
        return meta.size, meta.etag
    except Exception:  # noqa: BLE001
        return None


def estado(motor, consultar_servidor=False):
    """O que já está baixado do motor e o que falta (bytes)."""
    info = MOTORES[motor]
    faltam, presentes, atualizar = [], [], []
    falta_bytes = 0
    for repo, arq in info['arquivos']:
        p = _local(repo, arq)
        rem = _remoto(repo, arq) if consultar_servidor else None
        if p is None:
            faltam.append((repo, arq))
            falta_bytes += rem[0] if rem and rem[0] else (info['tamanho'] if arq.endswith(('.ckpt', '.safetensors')) else 0)
            continue
        tam = os.path.getsize(p)
        if rem and rem[0] and rem[0] != tam:
            atualizar.append((repo, arq))
            falta_bytes += rem[0]
        else:
            presentes.append((repo, arq))
    return {'motor': motor, 'nome': info['nome'], 'completo': not faltam and not atualizar,
            'faltam': faltam, 'atualizar': atualizar, 'presentes': presentes, 'falta_bytes': int(falta_bytes)}


def plano(consultar_servidor=True):
    """Decide o que baixar pelo espaço livre. Volta lista de motores a baixar
    e as mensagens para mostrar."""
    from Vetor3D import v3d_hunyuan as H
    livre = espaco_livre()
    msgs = [f'Espaço livre no disco: {livre / GB:.1f} GB (pasta de modelos: {pasta_cache()})']
    baixar = []
    disponivel = livre - FOLGA_DISCO
    for motor in ('leve', 'maximo'):
        e = estado(motor, consultar_servidor)
        if e['completo']:
            msgs.append(f'✓ {e["nome"]}: já baixado e atualizado')
            continue
        if motor == 'maximo' and not H.adequado():
            msgs.append(f'– {e["nome"]}: este computador tem menos de {H.RAM_MINIMA_GB:.0f} GB de RAM; '
                        'fica só o motor leve')
            continue
        precisa = e['falta_bytes']
        if precisa > disponivel:
            msgs.append(f'– {e["nome"]}: precisa de {precisa / GB:.1f} GB e há {max(0, disponivel) / GB:.1f} GB '
                        f'(deixando {FOLGA_DISCO / GB:.1f} GB de folga). Não baixado agora; o app usa o outro motor '
                        'e tenta de novo quando houver espaço.')
            continue
        disponivel -= precisa
        acao = 'atualizar' if e['atualizar'] and not e['faltam'] else ('completar' if e['presentes'] else 'baixar')
        msgs.append(f'↓ {e["nome"]}: {acao} {precisa / GB:.2f} GB')
        baixar.append(e)
    return baixar, msgs


def _fmt_tempo(s):
    if s is None:
        return '…'
    s = int(s)
    return f'{s // 3600}h{(s % 3600) // 60:02d}min' if s >= 3600 else (f'{s // 60}min{s % 60:02d}s' if s >= 60 else f'{s}s')


def baixar(e, avisar=print):
    """Baixa o que falta de um motor, com velocidade e tempo estimado. A
    medida é o espaço em disco consumido (vale para qualquer formato de cache,
    inclusive downloads retomados)."""
    from huggingface_hub import hf_hub_download
    alvo = max(1, e['falta_bytes'])
    livre0 = espaco_livre()
    erro = []
    pronto = threading.Event()

    def trabalho():
        try:
            for repo, arq in e['faltam'] + e['atualizar']:
                hf_hub_download(repo, arq, force_download=(repo, arq) in e['atualizar'])
        except Exception as ex:  # noqa: BLE001
            erro.append(ex)
        finally:
            pronto.set()
    threading.Thread(target=trabalho, daemon=True).start()
    t0 = time.time()
    vel = None
    while not pronto.wait(1.0):
        feito = max(0, livre0 - espaco_livre())
        agora = time.time()
        # média desde o início: o cache grava em rajadas, e janelas curtas
        # davam estimativas absurdas ("falta 200 h" num instante, "4 min" no outro)
        if agora - t0 >= 5 and feito >= 0.03 * alvo:
            vel = feito / (agora - t0)
        falta = max(0, alvo - feito)
        eta = falta / vel if vel and vel > 1024 else None
        avisar({'motor': e['motor'], 'nome': e['nome'], 'feito': feito, 'total': alvo,
                'frac': min(0.99, feito / alvo), 'velocidade': vel, 'eta': eta})
    if erro:
        raise erro[0]
    avisar({'motor': e['motor'], 'nome': e['nome'], 'feito': alvo, 'total': alvo, 'frac': 1.0,
            'velocidade': vel, 'eta': 0})


def instalar():
    """Passo do instalador: verifica, decide e baixa, mostrando o progresso."""
    print('Modelos de IA do Vetor3D (personagem 3D)')
    try:
        lista, msgs = plano(consultar_servidor=True)
    except Exception as ex:  # noqa: BLE001
        print(f'  Não foi possível verificar os modelos ({type(ex).__name__}); o app baixa na primeira vez.')
        return 0
    for m in msgs:
        print('  ' + m)
    for e in lista:
        ultimo = [0.0]

        def mostrar(p, e=e):
            agora = time.time()
            if p['frac'] < 1.0 and agora - ultimo[0] < 1.0:
                return
            ultimo[0] = agora
            barra = int(p['frac'] * 30)
            vel = f'{p["velocidade"] / MB:.1f} MB/s' if p['velocidade'] else '…'
            sys.stdout.write(f'\r  [{"█" * barra}{"░" * (30 - barra)}] {p["frac"] * 100:5.1f}%  '
                             f'{p["feito"] / GB:.2f}/{p["total"] / GB:.2f} GB  {vel}  falta {_fmt_tempo(p["eta"])}   ')
            sys.stdout.flush()
        print(f'  {e["nome"]}:')
        try:
            baixar(e, mostrar)
            print('\n  ✓ concluído')
        except Exception as ex:  # noqa: BLE001
            print(f'\n  [AVISO] Não foi possível baixar ({type(ex).__name__}). O app tenta de novo quando precisar.')
    return 0


if __name__ == '__main__':
    if '--instalar' in sys.argv:
        sys.exit(instalar())
    lista, msgs = plano(consultar_servidor='--servidor' in sys.argv)
    print('\n'.join(msgs))
