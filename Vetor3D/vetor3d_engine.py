"""Vetor3D · motor usado pelas rotas do app.py.

Um "projeto" é um arquivo enviado (SVG, DXF, PDF/AI, EPS ou imagem) com as
peças lidas dele e os parâmetros 3D de cada peça. O projeto fica salvo em
tempfile/verto_vetor3d/<id>/ (projeto.json + geometria + resultados), então
sobrevive a um recarregamento da página ou do servidor.

Cada etapa pesada vira uma tarefa na fila (v3d_fila): leitura -> preview 3D
-> alta definição -> exportação/código. Os resultados finais vão para a pasta
Downloads, sem sobrescrever nada.
"""
import json
import math
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
from pathlib import Path

from Vetor3D import v3d_hardware as HW
from Vetor3D.v3d_fila import Fila
from Vetor3D.v3d_importar import EXT_IMAGEM, EXTENSOES


class Vetor3DError(Exception):
    pass


_ROOT = os.path.join(tempfile.gettempdir(), 'verto_vetor3d')
TTL_PROJETO = 3 * 24 * 3600
_FILA = Fila(_ROOT)
_PROJ = {}
_LOCK = threading.RLock()
_OUTPUTS = {}
_INICIADO = {'ok': False}

PADRAO_CONFIG = {
    'largura': None, 'sobreposicao': 'recortar', 'unir_iguais': True,
    'base': 'nenhuma', 'base_altura': None, 'base_margem': None, 'base_raio': None, 'base_cor': '#2a2d34',
    'auto_preview': True,
}
CAMPOS_PECA = {
    'nome': str, 'cor': 'cor', 'ativo': bool, 'furo': bool, 'estilo': ('chanfro', 'inflado', 'volume'),
    'profundidade': float, 'volume': float, 'detalhe': float, 'traco': float, 'costas': ('lisa', 'imagem'),
    'altura': float, 'z': float, 'chanfro': float, 'perfil': ('redondo', 'reto'), 'lados': ('topo', 'ambos'),
    'inflado': float, 'fundo': ('plano', 'duplo'), 'metal': float, 'rugosidade': float,
    'metodo': ('reconstrucao', 'inflado'), 'espessura': float,
    'motor': ('auto', 'maximo', 'leve'), 'contorno': ('exato', 'ia'),
}
CAMPOS_CONFIG = {
    'largura': float, 'sobreposicao': ('recortar', 'empilhar'), 'unir_iguais': bool,
    'base': ('nenhuma', 'retangulo', 'contorno'), 'base_altura': float, 'base_margem': float,
    'base_raio': float, 'base_cor': 'cor', 'auto_preview': bool,
}
NOMES_ARQUIVO = {'preview.glb', 'hd.glb', 'preview.receita.json', 'hd.receita.json', 'sem_fundo.png'}


# ---------------------------------------------------------------------------
# Infra
# ---------------------------------------------------------------------------

def _downloads_dir():
    d = str(Path.home() / 'Downloads')
    os.makedirs(d, exist_ok=True)
    return d


def _nome_seguro(nome):
    nome = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', nome or '').strip(' .')
    return nome[:120] or 'modelo'


def _pasta(pid):
    if not re.fullmatch(r'[a-f0-9]{12}', pid or ''):
        raise Vetor3DError('Projeto inválido.')
    return os.path.join(_ROOT, pid)


def _salvar(proj):
    pasta = _pasta(proj['id'])
    os.makedirs(pasta, exist_ok=True)
    tmp = os.path.join(pasta, 'projeto.json.tmp')
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(proj, fh, ensure_ascii=False)
    os.replace(tmp, os.path.join(pasta, 'projeto.json'))


def _garantir():
    """Inicia a fila e carrega os projetos salvos (só no processo que atende
    requisições, não no processo vigia do modo debug do Flask)."""
    if _INICIADO['ok']:
        return
    with _LOCK:
        if _INICIADO['ok']:
            return
        os.makedirs(_ROOT, exist_ok=True)
        agora = time.time()
        for nome in os.listdir(_ROOT):
            pasta = os.path.join(_ROOT, nome)
            arq = os.path.join(pasta, 'projeto.json')
            if not os.path.isdir(pasta) or not re.fullmatch(r'[a-f0-9]{12}', nome):
                continue
            if not os.path.exists(arq) or agora - os.path.getmtime(arq) > TTL_PROJETO:
                shutil.rmtree(pasta, ignore_errors=True)
                continue
            try:
                with open(arq, encoding='utf-8') as fh:
                    proj = json.load(fh)
            except (OSError, ValueError):
                continue
            if proj.get('estado') == 'lendo':
                proj['estado'] = 'erro'
                proj['erro'] = 'A leitura foi interrompida (o servidor reiniciou). Envie o arquivo de novo.'
            proj['tarefas'] = {}
            _PROJ[proj['id']] = proj
        _FILA.ao_terminar = {'leitura': _fim_leitura, 'preview': _fim_modelo, 'hd': _fim_modelo}
        _FILA.iniciar()
        _INICIADO['ok'] = True


def _projeto(pid):
    _garantir()
    with _LOCK:
        proj = _PROJ.get(pid)
    if not proj:
        raise Vetor3DError('Projeto não encontrado (pode ter expirado). Envie o arquivo de novo.')
    return proj


def _limpar_valor(tipo, valor):
    if tipo == 'cor':
        if valor in (None, '', 'none'):
            return None
        valor = str(valor).strip().lower()
        if re.fullmatch(r'#[0-9a-f]{6}', valor):
            return valor
        if re.fullmatch(r'#[0-9a-f]{3}', valor):
            return '#' + ''.join(c * 2 for c in valor[1:])
        raise Vetor3DError(f'Cor inválida: {valor}')
    if tipo is bool:
        return bool(valor)
    if tipo is float:
        try:
            v = float(valor)
        except (TypeError, ValueError):
            raise Vetor3DError(f'Valor numérico inválido: {valor}')
        if not math.isfinite(v):
            raise Vetor3DError('Valor numérico inválido.')
        return v
    if tipo is str:
        return str(valor)[:80]
    if isinstance(tipo, tuple):
        if valor not in tipo:
            raise Vetor3DError(f'Opção inválida: {valor}')
        return valor
    return valor


def _padroes_peca(largura):
    return {'estilo': 'chanfro', 'altura': round(largura * 0.05, 2), 'z': 0.0,
            'chanfro': round(largura * 0.008, 2), 'perfil': 'redondo', 'lados': 'topo',
            'inflado': 0.6, 'fundo': 'plano', 'metal': 0.0, 'rugosidade': 0.45}


# ---------------------------------------------------------------------------
# Projetos
# ---------------------------------------------------------------------------

def formatos():
    from Vetor3D import v3d_codigo
    return {'entrada': list(EXTENSOES), 'imagem': list(EXT_IMAGEM),
            'ghostscript': bool(shutil.which('gs') or shutil.which('gswin64c')),
            'viewer': {'cdn': v3d_codigo.tamanho_viewer('cdn'), 'embutido': v3d_codigo.tamanho_viewer('embutido')}}


def enviar(file_storage, opcoes=None):
    _garantir()
    if not file_storage or not file_storage.filename:
        raise Vetor3DError('Selecione um arquivo.')
    nome_orig = os.path.basename(file_storage.filename)
    base, ext = os.path.splitext(nome_orig)
    ext = ext.lower().lstrip('.')
    if ext not in EXTENSOES:
        raise Vetor3DError(f'Formato .{ext or "?"} não suportado. Use SVG, DXF, PDF, AI, EPS ou imagem (PNG/JPG).')
    if ext in ('eps', 'ps') and not formatos()['ghostscript']:
        raise Vetor3DError('Para EPS/PS é preciso o Ghostscript instalado.')
    pid = secrets.token_hex(6)
    pasta = _pasta(pid)
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, f'original.{ext}')
    file_storage.save(caminho)
    tam = os.path.getsize(caminho)
    if tam == 0:
        shutil.rmtree(pasta, ignore_errors=True)
        raise Vetor3DError('O arquivo enviado está vazio.')
    imp = _opcoes_importacao(opcoes)
    proj = {
        'id': pid, 'nome': _nome_seguro(base), 'ext': ext, 'arquivo': caminho, 'tamanho': tam,
        'criado': time.time(), 'estado': 'lendo', 'erro': None, 'pecas': [], 'avisos': [],
        'config': dict(PADRAO_CONFIG), 'resultados': {}, 'tarefas': {}, 'versao': 0,
        'origem': ext, 'sem_cor': False, 'largura_original': None, 'altura_original': None,
        'importacao': imp,
    }
    with _LOCK:
        _PROJ[pid] = proj
    _ler(proj)
    return publico(proj)


def _opcoes_importacao(opcoes):
    opcoes = opcoes or {}
    imp = {}
    if opcoes.get('cores_imagem'):
        imp['cores_imagem'] = max(2, min(16, int(opcoes['cores_imagem'])))
    if opcoes.get('tracos') in ('auto', 'area', 'regioes'):
        imp['tracos'] = opcoes['tracos']
    if opcoes.get('fundo') in ('auto', 'ia', 'nenhum'):
        imp['fundo'] = opcoes['fundo']
    if opcoes.get('modo_imagem') in ('auto', 'desenho', 'cores', 'volume'):
        imp['modo_imagem'] = opcoes['modo_imagem']
    if opcoes.get('detalhe'):
        imp['detalhe'] = max(0.00002, min(0.01, float(opcoes['detalhe'])))
    return imp


def _ler(proj):
    """Põe a leitura do arquivo na fila (envio ou reprocessamento)."""
    perfil = HW.perfil_ativo()
    ext = proj['ext']
    est = 40 + proj['tamanho'] / HW.MB * (60 if ext in EXT_IMAGEM else 25) + (300 if proj['importacao'].get('fundo') == 'ia' else 0)
    tid = _FILA.adicionar('leitura', proj['id'], f'Leitura · {proj["nome"]}', 'leitura',
                          {'arquivo': proj['arquivo'], 'pasta': _pasta(proj['id']), 'tol_frac': perfil['tol_hd'],
                           'opts': proj['importacao']}, estimativa_mb=est)
    with _LOCK:
        proj['tarefas'] = {'leitura': tid}
        _salvar(proj)


def reler(pid, opcoes):
    """Lê o arquivo de novo com outras opções (fundo, modo da imagem...)."""
    proj = _projeto(pid)
    _FILA.cancelar_projeto(pid)
    with _LOCK:
        proj['importacao'] = _opcoes_importacao(opcoes)
        proj.update({'estado': 'lendo', 'erro': None, 'pecas': [], 'avisos': [], 'resultados': {}})
        proj['versao'] += 1
        for nome in ('geom.json', 'preview.glb', 'hd.glb', 'preview.npz', 'hd.npz', 'sem_fundo.png', 'textura.jpg',
                     'textura_preview.jpg', 'textura_hd.jpg'):
            try:
                os.remove(os.path.join(_pasta(pid), nome))
            except OSError:
                pass
    _ler(proj)
    return publico(proj)


def _fim_leitura(t):
    with _LOCK:
        proj = _PROJ.get(t['projeto'])
        if not proj:
            return
        if t['estado'] != 'pronto':
            proj['estado'] = 'erro'
            proj['erro'] = t.get('erro') or 'Não foi possível ler o arquivo.'
            _salvar(proj)
            return
        r = t['resultado']
        largura = float(r['largura']) or 100.0
        proj.update({'estado': 'pronto', 'erro': None, 'avisos': r['avisos'], 'origem': r['origem'],
                     'sem_cor': r['sem_cor'], 'largura_original': largura,
                     'altura_original': float(r['altura']), 'info': r.get('info', {})})
        proj['sem_fundo'] = bool(r.get('sem_fundo'))
        if r['origem'] == 'imagem' and largura > 200:
            largura_cfg = 150.0     # imagem sem DPI real: um tamanho de peça razoável
        else:
            largura_cfg = largura
        proj['config']['largura'] = round(largura_cfg, 2)
        padrao = _padroes_peca(largura_cfg)
        proj['pecas'] = []
        for p in r['pecas']:
            q = dict(padrao, **p)
            if p.get('papel') == 'regiao':
                # no desenho, o traço fica um pouco acima das áreas pintadas
                q['altura'] = round(largura_cfg * 0.035, 2)
            if p.get('papel') == 'volume':
                q.update(estilo='volume', metodo='reconstrucao', motor='auto', contorno='ia', espessura=1.0,
                         profundidade=0.45, volume=1.0,
                         detalhe=0.6, traco=0.5, costas='lisa', rugosidade=0.55)
            proj['pecas'].append(q)
        proj['versao'] += 1
        _salvar(proj)
    if proj['config'].get('auto_preview', True):
        try:
            gerar(proj['id'], 'preview')
        except Vetor3DError:
            pass


def _fim_modelo(t):
    with _LOCK:
        proj = _PROJ.get(t['projeto'])
        if not proj or t['estado'] != 'pronto':
            return
        nivel = t['args']['nivel']
        res = dict(t['resultado'])
        res['versao'] = t['args'].get('versao')
        res['quando'] = time.time()
        res['ajuste'] = t['extra'].get('ajuste')
        proj['resultados'][nivel] = res
        _salvar(proj)
    if res.get('tempos') and res.get('previstos'):
        from Vetor3D import v3d_reconstrucao as RC
        RC.registrar_ritmo(res['tempos'], res['previstos'])


def publico(proj):
    res = {}
    for nivel, r in (proj.get('resultados') or {}).items():
        res[nivel] = dict(r, desatualizado=r.get('versao') != proj['versao'],
                          url=f'/vetor3d/arquivo/{proj["id"]}/{nivel}.glb?v={int(r.get("quando", 0))}')
    tarefas = {}
    for k, tid in (proj.get('tarefas') or {}).items():
        t = _FILA.obter(tid)
        if t:
            tarefas[k] = t
    return {
        'id': proj['id'], 'nome': proj['nome'], 'ext': proj['ext'], 'estado': proj['estado'],
        'erro': proj.get('erro'), 'pecas': proj['pecas'], 'config': proj['config'],
        'avisos': proj.get('avisos', []), 'origem': proj.get('origem'), 'sem_cor': proj.get('sem_cor'),
        'largura_original': proj.get('largura_original'), 'altura_original': proj.get('altura_original'),
        'resultados': res, 'tarefas': tarefas, 'versao': proj['versao'], 'criado': proj['criado'],
        'importacao': proj.get('importacao', {}), 'imagem': proj['ext'] in EXT_IMAGEM,
        'sem_fundo': f'/vetor3d/arquivo/{proj["id"]}/sem_fundo.png' if proj.get('sem_fundo') else None,
    }


def projeto(pid):
    return publico(_projeto(pid))


def listar():
    _garantir()
    with _LOCK:
        ps = sorted(_PROJ.values(), key=lambda p: -p['criado'])
        return [{'id': p['id'], 'nome': p['nome'], 'ext': p['ext'], 'estado': p['estado'],
                 'pecas': len(p['pecas']), 'tem_hd': 'hd' in (p.get('resultados') or {}),
                 'tem_preview': 'preview' in (p.get('resultados') or {})} for p in ps]


def remover(pid):
    proj = _projeto(pid)
    _FILA.cancelar_projeto(proj['id'])
    with _LOCK:
        _PROJ.pop(pid, None)
    shutil.rmtree(_pasta(pid), ignore_errors=True)
    return True


def atualizar(pid, dados):
    proj = _projeto(pid)
    if proj['estado'] != 'pronto':
        raise Vetor3DError('O arquivo ainda está sendo lido.')
    dados = dados or {}
    with _LOCK:
        mudou = False
        cfg = dados.get('config') or {}
        largura_antiga = float(proj['config'].get('largura') or proj['largura_original'] or 100)
        for k, v in cfg.items():
            if k in CAMPOS_CONFIG:
                v = None if v is None or v == '' else _limpar_valor(CAMPOS_CONFIG[k], v)
                if k == 'largura' and v is not None:
                    v = max(1.0, min(5000.0, v))
                if proj['config'].get(k) != v:
                    proj['config'][k] = v
                    mudou = True
        nova = float(proj['config'].get('largura') or largura_antiga)
        if cfg.get('largura') and dados.get('escalar', True) and abs(nova - largura_antiga) > 1e-6:
            # medidas acompanham a nova largura (mesma proporção da peça)
            r = nova / largura_antiga
            for p in proj['pecas']:
                for k in ('altura', 'z', 'chanfro'):
                    p[k] = round(float(p.get(k) or 0) * r, 3)
            for k in ('base_altura', 'base_margem', 'base_raio'):
                if proj['config'].get(k):
                    proj['config'][k] = round(proj['config'][k] * r, 3)
        por_id = {p['id']: p for p in proj['pecas']}
        for alt in dados.get('pecas') or []:
            alvos = alt.get('ids') or [alt.get('id')]
            for pid_ in alvos:
                p = por_id.get(pid_)
                if not p:
                    continue
                for k, v in alt.items():
                    if k in CAMPOS_PECA:
                        v = _limpar_valor(CAMPOS_PECA[k], v)
                        if k in ('altura', 'chanfro', 'metal', 'rugosidade') and v is not None:
                            v = max(0.0, v)
                        if k in ('metal', 'rugosidade'):
                            v = min(1.0, v)
                        if k == 'inflado':
                            v = max(0.05, min(3.0, v))
                        if k in ('profundidade', 'volume', 'detalhe', 'traco'):
                            v = max(0.0, min(3.0, v))
                        if k == 'espessura':
                            v = max(0.3, min(3.0, v))
                        if k == 'estilo' and v == 'volume' and not (proj['ext'] in EXT_IMAGEM):
                            raise Vetor3DError('O modo personagem 3D (volume) é só para imagens.')
                        if p.get(k) != v:
                            p[k] = v
                            mudou = True
        if mudou:
            proj['versao'] += 1
            proj['sem_cor'] = all(p.get('cor') is None for p in proj['pecas'] if p.get('ativo', True))
            _salvar(proj)
    if mudou and proj['config'].get('auto_preview', True) and dados.get('preview', True):
        gerar(pid, 'preview')
    return publico(proj)


def _volume(proj):
    return any(p.get('estilo') == 'volume' and p.get('ativo', True) for p in proj['pecas'])


def _estimativa(proj, perfil, nivel, degraus, simplificar_frac=0.0):
    if _volume(proj):
        return int(perfil[f'vol_tri_{nivel}'] * 1.3)
    pts = sum(p.get('pts', 0) for p in proj['pecas'] if p.get('ativo', True) and not p.get('furo'))
    if nivel == 'preview':
        pts *= math.sqrt(perfil['tol_hd'] / perfil['tol_preview'])
    elif simplificar_frac > 0:
        pts *= min(1.0, math.sqrt(perfil['tol_hd'] / simplificar_frac))
    lados = 2 if any(p.get('lados') == 'ambos' or p.get('fundo') == 'duplo'
                     for p in proj['pecas'] if p.get('ativo', True)) else 1
    return int(pts * (4 + 2 * degraus * lados))


def gerar(pid, nivel):
    proj = _projeto(pid)
    if proj['estado'] != 'pronto':
        raise Vetor3DError('O arquivo ainda está sendo lido.')
    if nivel not in ('preview', 'hd'):
        raise Vetor3DError('Qualidade inválida.')
    perfil = HW.perfil_ativo()
    degraus = perfil[f'degraus_{nivel}']
    arco = perfil[f'arco_{nivel}']
    largura = float(proj['config'].get('largura') or proj['largura_original'] or 100)
    escala = largura / float(proj['largura_original'] or largura)
    diag = math.hypot(proj['largura_original'] or 1, proj['altura_original'] or 1) * escala
    simplificar = diag * perfil['tol_preview'] if nivel == 'preview' else 0.0
    est = _estimativa(proj, perfil, nivel, degraus)
    ajuste = None
    if nivel == 'hd' and est > perfil['max_triangulos'] and not _volume(proj):
        # A máquina não comporta: reduz degraus e depois resolução das curvas
        while est > perfil['max_triangulos'] and degraus > 6:
            degraus -= 4
            est = _estimativa(proj, perfil, nivel, degraus)
        if est > perfil['max_triangulos']:
            f = est / perfil['max_triangulos']
            frac = perfil['tol_hd'] * f * f
            simplificar = diag * frac
            est = _estimativa(proj, perfil, nivel, degraus, frac)
        ajuste = (f'Qualidade ajustada ao perfil {perfil["nome"]}: limite de '
                  f'{perfil["max_triangulos"] / 1e6:.1f} milhões de triângulos.')
    workers = perfil['workers'] if nivel == 'hd' else 1
    tipo = 'hd' if nivel == 'hd' else 'preview'
    if nivel == 'preview':
        _FILA.cancelar_projeto(pid, tipos=('preview',))
    args = {
        'pasta': _pasta(pid), 'nivel': nivel,
        'q': {'degraus': degraus, 'arco': arco, 'pontos': perfil[f'pontos_{nivel}'],
              'vol_res': perfil[f'vol_res_{nivel}'], 'vol_tri': perfil[f'vol_tri_{nivel}']},
        'workers': workers, 'workers_pedidos': workers, 'pecas': proj['pecas'], 'config': proj['config'],
        'largura_original': proj['largura_original'], 'simplificar': simplificar, 'versao': proj['versao'],
    }
    rotulo = f'{"Alta definição" if nivel == "hd" else "Preview 3D"} · {proj["nome"]}'
    est_mb = HW.estimar_mb(est, workers) if nivel == 'hd' else 20 + est * HW.BYTES_POR_TRIANGULO / HW.MB
    classe = previsto = minimo = None
    if _volume(proj):
        r = perfil[f'vol_res_{nivel}']
        import glob
        vol = next(p for p in proj['pecas'] if p.get('estilo') == 'volume' and p.get('ativo', True))
        if vol.get('metodo', 'reconstrucao') == 'reconstrucao':
            from Vetor3D import v3d_reconstrucao as RC
            # fila de IA: uma por vez, na ordem, processo novo com teto de
            # memória; a qualidade é a do nível (não do perfil de hardware)
            classe = 'ia'
            args['q'] = {'nivel': nivel}
            dims = None
            try:
                from PIL import Image
                with Image.open(os.path.join(_pasta(pid), 'sem_fundo.png')) as im:
                    caixa = im.getchannel('A').getbbox() if 'A' in im.getbands() else None
                    if caixa:
                        dims = (caixa[2] - caixa[0], caixa[3] - caixa[1])
            except Exception:  # noqa: BLE001
                dims = None
            motor, _ = RC.escolher_motor(vol.get('motor', 'auto'))
            baixar = 0
            if motor == 'baixar':
                from Vetor3D import v3d_modelos as MD
                baixar = MD.estado('maximo')['falta_bytes']
            etapas = RC.plano_etapas(_pasta(pid), nivel, *(dims or (None, None)),
                                     motor='leve' if motor == 'leve' else 'maximo', baixar_bytes=baixar)
            previsto = round(sum(seg for _, _, seg in etapas) + 6, 1)       # + abrir o processo
            # mínimo de memória para a etapa começar (abaixo disso, espera); o
            # motor máximo usa os pesos direto do disco e cabe em pouca RAM
            minimo = 2300 if nivel == 'hd' else 1400
            est = RC.QUALIDADE[nivel]['tri_max']
            est_mb = minimo
        else:
            # grade do campo 3D + modelo de profundidade (~900 MB, só enquanto não há cache no projeto)
            modelo_ia = 0 if glob.glob(os.path.join(_pasta(pid), 'profundidade_*.npy')) else 900
            est_mb = 60 + r * r * 0.7 * r * 0.6 * 4 * 2.5 / HW.MB + modelo_ia + est * HW.BYTES_POR_TRIANGULO / HW.MB
    tid = _FILA.adicionar(tipo, pid, rotulo, 'modelo', args, estimativa_mb=est_mb, triangulos=est,
                          extra={'ajuste': ajuste, 'nivel': nivel}, classe=classe, previsto_s=previsto,
                          minimo_mb=minimo)
    with _LOCK:
        proj['tarefas'][nivel] = tid
    return {'tarefa': tid, 'triangulos_estimados': est, 'ajuste': ajuste}


def _nivel_disponivel(proj, nivel):
    if nivel not in ('preview', 'hd'):
        raise Vetor3DError('Escolha preview ou alta definição.')
    if nivel not in (proj.get('resultados') or {}) or not os.path.exists(os.path.join(_pasta(proj['id']), f'{nivel}.npz')):
        raise Vetor3DError('Gere esse modelo antes de exportar.' if nivel == 'preview'
                           else 'Gere a alta definição antes (botão "Alta definição").')


def exportar(pid, nivel, formato, unir=False):
    proj = _projeto(pid)
    _nivel_disponivel(proj, nivel)
    if formato not in ('glb', 'stl', 'obj', '3mf', 'ply'):
        raise Vetor3DError('Formato inválido.')
    rotulo = 'HD' if nivel == 'hd' else 'Preview'
    destino = os.path.join(_downloads_dir(), f'{proj["nome"]} (3D {rotulo}).{formato}')
    tri = proj['resultados'][nivel].get('triangulos', 0)
    tid = _FILA.adicionar('exportar', pid, f'Exportar {formato.upper()} · {proj["nome"]}', 'exportar',
                          {'npz': os.path.join(_pasta(pid), f'{nivel}.npz'), 'formato': formato,
                           'unir': bool(unir), 'destino': destino},
                          estimativa_mb=30 + tri * 400 / HW.MB)
    return {'tarefa': tid}


def codigo(pid, nivel, opcoes):
    proj = _projeto(pid)
    _nivel_disponivel(proj, nivel)
    op = opcoes or {}
    if op.get('carga') == 'receita' and not proj['resultados'][nivel].get('receita_b64'):
        raise Vetor3DError('A receita leve não serve para o personagem 3D (volume com textura): use "Exato".')
    limpo = {
        'carga': op.get('carga') if op.get('carga') in ('exato', 'receita') else 'exato',
        'three': op.get('three') if op.get('three') in ('cdn', 'embutido') else 'cdn',
        'alvo': op.get('alvo') if op.get('alvo') in ('html', 'pagina', 'react', 'php', 'python', 'node') else 'html',
        'reducao': max(0.0, min(0.9, float(op.get('reducao') or 0))),
        'extras': [x for x in (op.get('extras') or []) if x in ('stl', 'obj', '3mf', 'ply')],
        'proporcao': op.get('proporcao') if re.fullmatch(r'\d{1,2}/\d{1,2}', str(op.get('proporcao') or '')) else '1/1',
        'autoRotacao': bool(op.get('autoRotacao', True)),
        'fundo': _limpar_valor('cor', op.get('fundo')) if op.get('fundo') else None,
        'botaoBaixar': bool(op.get('botaoBaixar', True)),
        'pan': bool(op.get('pan', False)),
        'verniz': max(0.0, min(1.0, float(op.get('verniz', 0.35) or 0))),
        'nome': proj['nome'],
    }
    tri = proj['resultados'][nivel].get('triangulos', 0)
    tid = _FILA.adicionar('codigo', pid, f'Código {limpo["alvo"].upper()} · {proj["nome"]}', 'codigo',
                          {'pasta': _pasta(pid), 'nivel': nivel, 'opcoes': limpo, 'tid': secrets.token_hex(4)},
                          estimativa_mb=30 + tri * 300 / HW.MB)
    return {'tarefa': tid}


# ---------------------------------------------------------------------------
# Tarefas, arquivos e hardware
# ---------------------------------------------------------------------------

def _registrar_saida(caminho):
    with _LOCK:
        for tok, p in _OUTPUTS.items():
            if p == caminho:
                return tok
        tok = secrets.token_urlsafe(16)
        _OUTPUTS[tok] = caminho
        return tok


def tarefa(tid):
    _garantir()
    t = _FILA.obter(tid)
    if not t:
        raise Vetor3DError('Tarefa não encontrada.')
    if t['estado'] == 'pronto' and t['tipo'] == 'exportar' and t.get('resultado'):
        t['resultado'] = dict(t['resultado'], token=_registrar_saida(t['resultado']['caminho']))
        t['resultado'].pop('caminho', None)
    if t['estado'] == 'pronto' and t['tipo'] == 'codigo' and t.get('resultado'):
        t['resultado'] = {k: v for k, v in t['resultado'].items() if k != 'arquivo'}
    return t


def codigo_texto(tid):
    _garantir()
    t = _FILA.obter(tid)
    if not t or t['tipo'] != 'codigo' or t['estado'] != 'pronto':
        raise Vetor3DError('O código ainda não está pronto.')
    caminho = t['resultado']['arquivo']
    if not caminho.startswith(_ROOT + os.sep) or not os.path.isfile(caminho):
        raise Vetor3DError('O código expirou: gere de novo.')
    with open(caminho, encoding='utf-8') as fh:
        return fh.read(), t['resultado']['ext']


def fila(projeto_id=None):
    _garantir()
    return _FILA.listar(projeto_id)


def limpar_fila(cancelar_pendentes=False):
    """Tira da lista as etapas terminadas (prontas, com erro ou canceladas) e,
    se pedido, cancela as que ainda esperam ou estão rodando."""
    _garantir()
    return _FILA.limpar(cancelar_pendentes)


def acao_tarefa(tid, acao):
    _garantir()
    ok = {
        'cancelar': lambda: _FILA.cancelar(tid),
        'pausar': lambda: _FILA.pausar(tid, True),
        'retomar': lambda: _FILA.pausar(tid, False),
        'subir': lambda: _FILA.mover(tid, -1),
        'descer': lambda: _FILA.mover(tid, +1),
        'forcar': lambda: _FILA.forcar(tid),
    }.get(acao, lambda: False)()
    return bool(ok)


def hardware():
    _garantir()
    snap = HW.snapshot()
    snap['fila'] = _FILA.resumo()
    return snap


def preferencias(modo=None, nucleos=None):
    pref = HW.definir_preferencia(modo, nucleos)
    return {'preferencia': pref, 'perfil': HW.snapshot()['perfil']}


def arquivo(pid, nome):
    _projeto(pid)
    if nome not in NOMES_ARQUIVO:
        raise Vetor3DError('Arquivo inválido.')
    caminho = os.path.join(_pasta(pid), nome)
    if not os.path.isfile(caminho):
        raise Vetor3DError('Arquivo ainda não gerado.')
    return caminho


def original(pid):
    proj = _projeto(pid)
    return proj['arquivo'], f'{proj["nome"]}.{proj["ext"]}'


def output_path(token):
    with _LOCK:
        caminho = _OUTPUTS.get(token or '')
    return caminho if caminho and os.path.isfile(caminho) else None


def encerrar():
    if _INICIADO['ok']:
        _FILA.encerrar()
