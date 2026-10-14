"""Áudio Studio · projetos (a lista de edição é a fonte da verdade).

AudioStudio/dados/projetos/<id>/
  projeto.json      pistas -> clipes (fonte, início na fonte, duração, posição,
                    ganho, fades), envelope de volume, marcadores, regiões,
                    cadeia de efeitos do master, alvo de loudness
  fontes/<fid>/     arquivo importado + a16.raw + picos.i8 (ver as_midia)
  transcricao/<fid>.json, sugestoes.json, exportados/

Nada é destrutivo: cortar, apagar e encurtar só mexem nos clipes; o arquivo
importado fica igual. O desfazer mora no navegador (histórico de estados) e o
projeto é salvo sozinho a cada mudança.
"""
import json
import os
import re
import secrets
import shutil
import time

from AudioStudio import as_midia as M
from AudioStudio import as_fila as F

DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dados', 'projetos')
LONGO_S = 3600


class ProjetoError(Exception):
    pass


def _id():
    return secrets.token_hex(5)


def pasta(pid):
    if not re.fullmatch(r'[0-9a-f]{10}', pid or ''):
        raise ProjetoError('Projeto inválido.')
    p = os.path.join(DADOS, pid)
    if not os.path.isdir(p):
        raise ProjetoError('Projeto não encontrado (pode ter sido apagado).')
    return p


def pasta_fonte(pid, fid):
    if not re.fullmatch(r'[0-9a-f]{10}', fid or ''):
        raise ProjetoError('Arquivo inválido.')
    p = os.path.join(pasta(pid), 'fontes', fid)
    if not os.path.isdir(p):
        raise ProjetoError('Arquivo não encontrado neste projeto.')
    return p


def _arq(pid):
    return os.path.join(pasta(pid), 'projeto.json')


def ler(pid):
    with open(_arq(pid), encoding='utf-8') as f:
        return json.load(f)


def _gravar(pid, proj):
    proj['alterado'] = time.strftime('%Y-%m-%d %H:%M:%S')
    caminho = _arq(pid)
    with open(caminho + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(proj, f, ensure_ascii=False)
    os.replace(caminho + '.tmp', caminho)


def nova_pista(nome='Voz', tipo='voz'):
    return {'id': _id(), 'nome': nome, 'tipo': tipo, 'ganho': 0.0, 'pan': 0.0, 'mudo': False, 'solo': False,
            'envelope': [], 'clipes': []}


def criar(nome='Projeto sem nome'):
    pid = _id()
    p = os.path.join(DADOS, pid)
    os.makedirs(os.path.join(p, 'fontes'))
    proj = {'id': pid, 'nome': M.nome_seguro(nome, 'Projeto sem nome'), 'criado': time.strftime('%Y-%m-%d %H:%M'),
            'versao': 1, 'sr': 48000, 'pistas': [nova_pista()], 'marcadores': [], 'regioes': [],
            'master': [], 'loudness': {'ativo': False, 'alvo': -16.0, 'pico': -1.0}, 'ducking': {'ativo': False, 'reducao': 12},
            'idioma': 'auto', 'tags': {}}
    _gravar(pid, proj)
    return publico(pid)


def _fontes(pid):
    base = os.path.join(pasta(pid), 'fontes')
    out = {}
    for fid in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        try:
            info = M.ler_fonte(os.path.join(base, fid))
        except (OSError, ValueError):
            continue
        tr = os.path.join(pasta(pid), 'transcricao', f'{fid}.json')
        info['transcrita'] = os.path.exists(tr)
        info['longa'] = info['duracao'] > LONGO_S
        out[fid] = info
    return out


def publico(pid):
    proj = ler(pid)
    proj['fontes'] = _fontes(pid)
    proj['tarefas'] = [t for t in F.listar(pid) if t['estado'] not in ('pronta', 'cancelada')]
    return proj


def listar():
    if not os.path.isdir(DADOS):
        return []
    out = []
    for pid in os.listdir(DADOS):
        try:
            p = ler(pid)
        except (OSError, ValueError, ProjetoError):
            continue
        dur = 0.0
        for pista in p['pistas']:
            for c in pista['clipes']:
                dur = max(dur, c['pos'] + c['dur'])
        out.append({'id': pid, 'nome': p['nome'], 'criado': p.get('criado'), 'alterado': p.get('alterado'),
                    'duracao': round(dur, 2), 'pistas': len(p['pistas'])})
    return sorted(out, key=lambda x: x.get('alterado') or '', reverse=True)


def apagar(pid):
    p = pasta(pid)
    F.remover_do_projeto(pid)
    shutil.rmtree(p, ignore_errors=True)
    return True


# ------------------------------------------------------------- salvar ---

def _num(v, lo, hi, padrao=0.0):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return padrao
    return max(lo, min(hi, v))


class Conflito(ProjetoError):
    """O projeto mudou no servidor (receita, separação) depois que o editor o abriu."""


def salvar(pid, dados):
    """Grava o estado que veio do editor (validado: só os campos conhecidos)."""
    proj = ler(pid)
    base = dados.get('versao_base')
    if base is not None and int(base) != int(proj.get('versao', 1)):
        raise Conflito('O projeto mudou enquanto você editava (uma receita ou a IA terminou). Recarreguei a versão nova.')
    fontes = _fontes(pid)
    pistas = []
    for p in (dados.get('pistas') or [])[:32]:
        clipes = []
        for c in (p.get('clipes') or [])[:20000]:
            if c.get('fonte') not in fontes:
                continue
            durf = fontes[c['fonte']]['duracao']
            ini = _num(c.get('ini'), 0, durf)
            dur = _num(c.get('dur'), 0.005, durf - ini, 0)
            if dur <= 0.004:
                continue
            clipes.append({'id': str(c.get('id') or _id())[:16], 'fonte': c['fonte'], 'ini': round(ini, 6), 'dur': round(dur, 6),
                           'pos': round(_num(c.get('pos'), 0, 86400 * 2), 6), 'ganho': _num(c.get('ganho'), -60, 24),
                           'fi': _num(c.get('fi'), 0, 60), 'fo': _num(c.get('fo'), 0, 60)})
        env = []
        for ponto in (p.get('envelope') or [])[:5000]:
            if isinstance(ponto, (list, tuple)) and len(ponto) == 2:
                env.append([round(_num(ponto[0], 0, 86400 * 2), 4), round(_num(ponto[1], -60, 12), 2)])
        env.sort()
        pistas.append({'id': str(p.get('id') or _id())[:16], 'nome': M.nome_seguro(p.get('nome'), 'Pista')[:40],
                       'tipo': p.get('tipo') if p.get('tipo') in ('voz', 'musica', 'efeito') else 'voz',
                       'ganho': _num(p.get('ganho'), -60, 12), 'pan': _num(p.get('pan'), -1, 1),
                       'mudo': bool(p.get('mudo')), 'solo': bool(p.get('solo')), 'envelope': env, 'clipes': clipes})
    proj['pistas'] = pistas or [nova_pista()]
    proj['marcadores'] = [{'id': str(m.get('id') or _id())[:16], 't': _num(m.get('t'), 0, 86400 * 2), 'nome': str(m.get('nome') or '')[:60]}
                          for m in (dados.get('marcadores') or [])[:2000]]
    regs = []
    for r in (dados.get('regioes') or [])[:500]:
        a, b = _num(r.get('ini'), 0, 86400 * 2), _num(r.get('fim'), 0, 86400 * 2)
        if b - a > 0.05:
            regs.append({'id': str(r.get('id') or _id())[:16], 'ini': a, 'fim': b, 'nome': M.nome_seguro(r.get('nome'), 'Região')[:60]})
    proj['regioes'] = regs
    from AudioStudio import as_efeitos as E
    proj['master'] = E.validar_cadeia(dados.get('master') or [])
    lo = dados.get('loudness') or {}
    proj['loudness'] = {'ativo': bool(lo.get('ativo')), 'alvo': _num(lo.get('alvo'), -30, -6, -16), 'pico': _num(lo.get('pico'), -6, 0, -1)}
    du = dados.get('ducking') or {}
    proj['ducking'] = {'ativo': bool(du.get('ativo')), 'reducao': _num(du.get('reducao'), 3, 30, 12)}
    proj['sug_estado'] = {str(k)[:40]: v for k, v in list((dados.get('sug_estado') or {}).items())[:50000]
                          if v in ('aceita', 'recusada')}
    if dados.get('nome'):
        proj['nome'] = M.nome_seguro(dados['nome'], proj['nome'])
    if dados.get('idioma') in ('auto', 'pt', 'en', 'es', 'fr', 'it', 'de', 'ja'):
        proj['idioma'] = dados['idioma']
    proj['tags'] = {k: str(v)[:200] for k, v in (dados.get('tags') or {}).items() if k in ('titulo', 'artista', 'album', 'ano', 'genero', 'comentario')}
    proj['versao'] = int(proj.get('versao', 1)) + 1
    _gravar(pid, proj)
    return {'versao': proj['versao'], 'alterado': proj['alterado']}


# ------------------------------------------------------------ importar ---

def importar(pid, origem, nome, pista_id=None, nova=False, tipo='voz', posicao=None):
    """Guarda o arquivo como fonte, põe um clipe na pista e manda preparar."""
    pasta(pid)
    fid = _id()
    pf = os.path.join(pasta(pid), 'fontes', fid)
    try:
        info = M.guardar_fonte(origem, pf, os.path.basename(nome))
    except M.MidiaError:
        shutil.rmtree(pf, ignore_errors=True)
        raise
    proj = ler(pid)
    pista = None
    if not nova:
        pista = next((p for p in proj['pistas'] if p['id'] == pista_id), None)
        if pista is None and pista_id is None:
            pista = next((p for p in proj['pistas'] if not p['clipes']), None)
    if pista is None:
        pista = nova_pista('Música' if tipo == 'musica' else f'Pista {len(proj["pistas"]) + 1}', tipo)
        proj['pistas'].append(pista)
    fim = max([c['pos'] + c['dur'] for c in pista['clipes']] or [0.0])
    pos = fim if posicao is None else max(0.0, float(posicao))
    pista['clipes'].append({'id': _id(), 'fonte': fid, 'ini': 0.0, 'dur': round(info['duracao'], 6), 'pos': round(pos, 6),
                            'ganho': 0.0, 'fi': 0.0, 'fo': 0.0})
    if proj['nome'] == 'Projeto sem nome':
        proj['nome'] = M.nome_seguro(os.path.splitext(os.path.basename(nome))[0], proj['nome'])[:60]
    proj['versao'] = int(proj.get('versao', 1)) + 1
    _gravar(pid, proj)
    longa = info['duracao'] > LONGO_S
    F.adicionar('preparar', pid, {'fonte': fid},
                titulo=f'Preparar "{info["nome"]}"' + (' (modo fila: mais de 1 h)' if longa else ''))
    return {'fonte': fid, 'pista': pista['id'], 'longa': longa}


def caminho_transcricao(pid, fid):
    return os.path.join(pasta(pid), 'transcricao', f'{fid}.json')


def ler_transcricao(pid, fid):
    try:
        with open(caminho_transcricao(pid, fid), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
