"""Vetor3D · leitura do hardware e perfis de processamento.

O que define o "peso" de um modelo 3D é a quantidade de triângulos (resolução
das curvas, degraus do chanfro e do inflado). Aqui o app lê a máquina (CPU,
RAM, temperatura e GPU), escolhe um perfil e decide, antes de cada etapa, se
ela cabe na memória livre naquele momento. O painel da página consulta
snapshot() a cada ~1,5 s.

O processamento geométrico é feito na CPU (shapely/earcut/numpy); a GPU é
usada pelo navegador para desenhar o preview, então ela só aparece como
informação.
"""
import os
import shutil
import subprocess
import tempfile
import time

import psutil

MB = 1024 ** 2
GB = 1024 ** 3

# Perfis: o que cada um permite. Tolerâncias são frações da diagonal do desenho.
PERFIS = {
    'economico': {
        'nome': 'Econômico', 'workers': 1, 'hd_simultaneos': 1,
        'tol_hd': 1 / 4000, 'tol_preview': 1 / 900,
        'degraus_hd': 10, 'degraus_preview': 4, 'arco_hd': 8, 'arco_preview': 3,
        'pontos_hd': 200, 'pontos_preview': 60,
        'vol_res_hd': 380, 'vol_res_preview': 220, 'vol_tri_hd': 250_000, 'vol_tri_preview': 80_000,
        'max_triangulos': 1_500_000,
    },
    'equilibrado': {
        'nome': 'Equilibrado', 'workers': 3, 'hd_simultaneos': 1,
        'tol_hd': 1 / 9000, 'tol_preview': 1 / 1200,
        'degraus_hd': 18, 'degraus_preview': 5, 'arco_hd': 12, 'arco_preview': 3,
        'pontos_hd': 400, 'pontos_preview': 80,
        'vol_res_hd': 520, 'vol_res_preview': 260, 'vol_tri_hd': 500_000, 'vol_tri_preview': 120_000,
        'max_triangulos': 4_000_000,
    },
    'alto': {
        'nome': 'Alto', 'workers': 6, 'hd_simultaneos': 2,
        'tol_hd': 1 / 16000, 'tol_preview': 1 / 1500,
        'degraus_hd': 28, 'degraus_preview': 6, 'arco_hd': 16, 'arco_preview': 4,
        'pontos_hd': 600, 'pontos_preview': 100,
        'vol_res_hd': 720, 'vol_res_preview': 300, 'vol_tri_hd': 1_000_000, 'vol_tri_preview': 160_000,
        'max_triangulos': 9_000_000,
    },
    'ultra': {
        'nome': 'Ultra', 'workers': 12, 'hd_simultaneos': 3,
        'tol_hd': 1 / 30000, 'tol_preview': 1 / 1800,
        'degraus_hd': 40, 'degraus_preview': 6, 'arco_hd': 24, 'arco_preview': 4,
        'pontos_hd': 900, 'pontos_preview': 120,
        'vol_res_hd': 960, 'vol_res_preview': 340, 'vol_tri_hd': 2_000_000, 'vol_tri_preview': 200_000,
        'max_triangulos': 20_000_000,
    },
}
ORDEM = ['economico', 'equilibrado', 'alto', 'ultra']

# Escolha do usuário: 'auto' (pelo hardware), 'economico' ou 'maximo'
_preferencia = {'modo': 'auto', 'nucleos': None}
_cache_estatico = {}
_ultimo_cpu = {'t': 0.0, 'valor': None}


def _nucleos():
    return psutil.cpu_count(logical=False) or psutil.cpu_count() or 2


def _logicos():
    return psutil.cpu_count() or 2


def perfil_automatico():
    """Perfil pelo hardware fixo (núcleos físicos e RAM total)."""
    n = _nucleos()
    ram = psutil.virtual_memory().total / GB
    if n >= 12 and ram >= 30:
        return 'ultra'
    if n >= 6 and ram >= 14:
        return 'alto'
    if n >= 4 and ram >= 6:
        return 'equilibrado'
    return 'economico'


def definir_preferencia(modo=None, nucleos=None):
    if modo in ('auto', 'economico', 'maximo'):
        _preferencia['modo'] = modo
    if nucleos is not None:
        try:
            nucleos = int(nucleos)
        except (TypeError, ValueError):
            nucleos = None
        _preferencia['nucleos'] = max(1, min(_logicos(), nucleos)) if nucleos else None
    return dict(_preferencia)


def perfil_ativo():
    """Perfil em uso, já com a preferência do usuário aplicada."""
    chave = perfil_automatico()
    modo = _preferencia['modo']
    if modo == 'economico':
        chave = 'economico'
    elif modo == 'maximo':
        # Um degrau acima do automático: mais qualidade, mais tempo e memória
        chave = ORDEM[min(len(ORDEM) - 1, ORDEM.index(chave) + 1)]
    p = dict(PERFIS[chave])
    p['chave'] = chave
    p['modo'] = modo
    teto = _preferencia['nucleos'] or max(1, _logicos() - 1)
    p['workers'] = max(1, min(p['workers'], teto))
    return p


def _temperatura_cpu():
    try:
        sensores = psutil.sensors_temperatures()
    except Exception:
        return None
    for nome in ('k10temp', 'coretemp', 'zenpower', 'cpu_thermal', 'acpitz'):
        lista = sensores.get(nome)
        if lista:
            # Tctl/Package é o valor que o firmware usa para estrangular a CPU
            prefer = [s for s in lista if s.label in ('Tctl', 'Tdie') or s.label.startswith('Package')]
            return round((prefer or lista)[0].current, 1)
    return None


def temperaturas():
    """Temperaturas reais dos sensores: CPU, GPU e disco (°C), quando existem."""
    try:
        sensores = psutil.sensors_temperatures()
    except Exception:
        return {}
    saida = {'cpu': _temperatura_cpu()}
    for nome in ('amdgpu', 'nouveau', 'radeon', 'i915', 'nvidia'):
        if sensores.get(nome):
            saida['gpu'] = round(sensores[nome][0].current, 1)
            break
    for nome in ('nvme', 'drivetemp'):
        if sensores.get(nome):
            saida['disco'] = round(max(x.current for x in sensores[nome]), 1)
            break
    return saida


_troca = {'t': None, 'sin': 0, 'sout': 0, 'taxa': 0.0}


def troca_swap():
    """Quanto o sistema está trocando com o swap agora (MB/s, entrada + saída).
    É isso que mostra quando a memória acabou de verdade e o PC fica lento."""
    try:
        sw = psutil.swap_memory()
    except Exception:
        return None
    agora = time.monotonic()
    if _troca['t'] is not None and agora - _troca['t'] >= 0.8:
        dt = agora - _troca['t']
        _troca['taxa'] = max(0, (sw.sin - _troca['sin']) + (sw.sout - _troca['sout'])) / dt / MB
    if _troca['t'] is None or agora - _troca['t'] >= 0.8:
        _troca.update(t=agora, sin=sw.sin, sout=sw.sout)
    return round(_troca['taxa'], 2)


def _gpu():
    """Nome da GPU e uso (quando o driver expõe). Só informativo."""
    if 'gpu' in _cache_estatico:
        info = dict(_cache_estatico['gpu'])
    else:
        info = {'nome': None, 'fabricante': None, 'cuda': False, 'sysfs': None}
        fabricantes = {'0x1002': 'AMD', '0x10de': 'NVIDIA', '0x8086': 'Intel'}
        base = '/sys/class/drm'
        if os.path.isdir(base):
            for card in sorted(os.listdir(base)):
                if not card.startswith('card') or '-' in card:
                    continue
                try:
                    with open(os.path.join(base, card, 'device', 'vendor')) as f:
                        vid = f.read().strip()
                except OSError:
                    continue
                info['fabricante'] = fabricantes.get(vid, vid)
                info['sysfs'] = os.path.join(base, card, 'device')
                break
        if shutil.which('lspci'):
            try:
                out = subprocess.run(['lspci', '-vmm'], capture_output=True, text=True, timeout=3).stdout
                for bloco in out.split('\n\n'):
                    campos = dict(l.split(':\t', 1) for l in bloco.splitlines() if ':\t' in l)
                    if 'VGA' in campos.get('Class', '') or '3D controller' in campos.get('Class', ''):
                        marca = campos.get('Vendor', '').split(',')[0].replace('Advanced Micro Devices', 'AMD')
                        info['nome'] = f"{marca} {campos.get('Device', '')}".strip()
                        break
            except Exception:
                pass
        try:
            import importlib.util
            if importlib.util.find_spec('torch') is not None and shutil.which('nvidia-smi'):
                import torch
                info['cuda'] = bool(torch.cuda.is_available())
                if info['cuda']:
                    info['nome'] = torch.cuda.get_device_name(0)
        except Exception:
            pass
        _cache_estatico['gpu'] = dict(info)
    sysfs = info.pop('sysfs', None)

    def ler(nome):
        if not sysfs:
            return None
        try:
            with open(os.path.join(sysfs, nome)) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None
    info['uso'] = ler('gpu_busy_percent')
    info['vram_usada'] = ler('mem_info_vram_used')
    info['vram_total'] = ler('mem_info_vram_total')
    return info


def _nome_cpu():
    if 'cpu' not in _cache_estatico:
        nome = None
        try:
            with open('/proc/cpuinfo') as f:
                for linha in f:
                    if linha.startswith('model name'):
                        nome = linha.split(':', 1)[1].strip()
                        break
        except OSError:
            pass
        if not nome:
            import platform
            nome = platform.processor() or platform.machine()
        _cache_estatico['cpu'] = nome
    return _cache_estatico['cpu']


def uso_cpu():
    """Uso total recente (%) sem bloquear: psutil mede desde a última chamada."""
    agora = time.monotonic()
    if _ultimo_cpu['valor'] is None or agora - _ultimo_cpu['t'] > 0.5:
        _ultimo_cpu['valor'] = psutil.cpu_percent(interval=None)
        _ultimo_cpu['t'] = agora
    return _ultimo_cpu['valor']


def ram_livre():
    return psutil.virtual_memory().available


def snapshot():
    """Tudo o que o painel de hardware mostra."""
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    try:
        freq = psutil.cpu_freq()
    except Exception:
        freq = None
    try:
        carga = [round(x, 2) for x in os.getloadavg()]
    except (AttributeError, OSError):
        carga = None
    try:
        disco = shutil.disk_usage(tempfile.gettempdir()).free
    except OSError:
        disco = None
    p = perfil_ativo()
    return {
        'cpu': {
            'nome': _nome_cpu(),
            'fisicos': _nucleos(),
            'logicos': _logicos(),
            'uso': uso_cpu(),
            'por_nucleo': psutil.cpu_percent(interval=None, percpu=True),
            'mhz': round(freq.current) if freq else None,
            'mhz_max': round(freq.max) if freq and freq.max else None,
            'carga': carga,
            'temperatura': _temperatura_cpu(),
        },
        'ram': {'total': vm.total, 'livre': vm.available, 'uso': vm.percent,
                'em_uso': vm.total - vm.available,
                'cache': getattr(vm, 'cached', 0) + getattr(vm, 'buffers', 0),
                'disponivel': vm.available},
        'swap': {'total': sw.total, 'usado': sw.used, 'uso': sw.percent, 'troca_mb_s': troca_swap()},
        'temperaturas': temperaturas(),
        'gpu': _gpu(),
        'disco_tmp_livre': disco,
        'perfil': {
            'chave': p['chave'], 'nome': p['nome'], 'modo': p['modo'],
            'automatico': PERFIS[perfil_automatico()]['nome'],
            'workers': p['workers'], 'hd_simultaneos': p['hd_simultaneos'],
            'degraus_hd': p['degraus_hd'], 'max_triangulos': p['max_triangulos'],
            'nucleos_limite': _preferencia['nucleos'],
        },
    }


def workers_agora(pedidos):
    """Quantos processos usar na próxima etapa, olhando o estado atual: CPU
    muito quente ou já ocupada por outros programas reduz o paralelismo."""
    w = max(1, int(pedidos))
    temp = _temperatura_cpu()
    if temp is not None and temp >= 90:
        w = max(1, w // 2)
    if uso_cpu() >= 85:
        w = max(1, w - 1)
    return w


# Base de um processo de trabalho (Python + numpy + shapely + trimesh)
MB_POR_PROCESSO = 150
# Pico de memória por triângulo (numpy, shapely, trimesh e o GLB juntos)
BYTES_POR_TRIANGULO = 260
# Etapas pequenas sempre podem rodar (o sistema dá conta de liberar isso)
MB_SEMPRE = 64


def estimar_mb(triangulos, workers, processo_vivo=False):
    """Memória que a etapa ainda vai pedir: o processo de trabalho (se ainda
    não existe), os processos extras de cada núcleo e os dados da malha."""
    base = 0 if processo_vivo else MB_POR_PROCESSO
    filhos = MB_POR_PROCESSO * workers if workers > 1 else 0
    return base + filhos + triangulos * BYTES_POR_TRIANGULO / MB


def admitir(estimativa_mb, reservado_mb=0.0, fracao=0.7):
    """A etapa cabe na RAM livre agora? (deixa 30% de folga para o sistema e
    o navegador; o que etapas em andamento ainda vão pedir é descontado)."""
    livre_mb = ram_livre() / MB
    if estimativa_mb + reservado_mb <= MB_SEMPRE:
        return True, livre_mb
    return estimativa_mb + reservado_mb <= livre_mb * fracao, livre_mb
