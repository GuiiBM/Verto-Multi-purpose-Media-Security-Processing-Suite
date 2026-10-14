"""Áudio Studio · receitas automáticas e separação de voz (Demucs).

Uma receita é: quais sugestões aceitar + a cadeia de efeitos do master + a
loudness final. A rota põe na fila, em ordem: transcrever (se a receita usa a
fala), analisar e só então a tarefa "receita", que aplica tudo de uma vez no
projeto (o editor recarrega e dá para desfazer).

Separar (Karaokê / Isolar voz): Demucs em pedaços de 45 s num processo só, com
teto de memória (a música inteira de uma vez passa de 1,7 GB nesta máquina; em
pedaços o pico medido foi ~1,5 GB). O resultado vira uma fonte nova e os
clipes passam a usá-la, no mesmo lugar.
"""
import os
import shutil
import subprocess
import sys
import time

import numpy as np

from AudioStudio import as_fila as F
from AudioStudio import as_midia as M
from AudioStudio import as_projeto as P
from AudioStudio import as_edicao as ED
from AudioStudio import as_efeitos as E


def _fx(ef, **p):
    return {'ef': ef, 'ativo': True, 'p': p}


RECEITAS = {
    'podcast': {
        'nome': 'Podcast / voz', 'desc': 'Tira ruído, vícios, frases refeitas e pausas longas; voz clara, comprimida e em −16 LUFS.',
        'fala': True, 'cats': ['cabeca', 'silencio', 'vicio', 'gaguejo', 'repeticao', 'estouro'], 'manter': 0.4,
        'master': [_fx('ruido', nivel='medio'), _fx('passa_alta', freq=80), _fx('eq_preset', preset='voz'),
                   _fx('deesser', intensidade=0.35), _fx('compressor', limiar=-22, razao=3, ataque=10, liberacao=180, ganho=4),
                   _fx('limitador', teto=-1)],
        'loudness': (-16, -1)},
    'celular': {
        'nome': 'Gravação de celular', 'desc': 'Tira zumbido, ruído e estalos, nivela o volume da fala e corta começo e fim mortos.',
        'fala': False, 'cats': ['cabeca', 'estouro'],
        'master': [_fx('eq_preset', preset='zumbido60'), _fx('ruido', nivel='leve'), _fx('declick'), _fx('passa_alta', freq=90),
                   _fx('nivelar', forca=5), _fx('limitador', teto=-1)],
        'loudness': (-16, -1)},
    'aula': {
        'nome': 'Aula / palestra', 'desc': 'Encurta as pausas sem dó, nivela, deixa em mono e −18 LUFS (bom para MP3 leve).',
        'fala': False, 'cats': ['cabeca', 'silencio'], 'manter': 0.3, 'pausa_min': 0.6,
        'master': [_fx('ruido', nivel='leve'), _fx('passa_alta', freq=80), _fx('nivelar', forca=6), _fx('mono'),
                   _fx('limitador', teto=-1)],
        'loudness': (-18, -1), 'exportar': {'formato': 'mp3', 'kbps': 64, 'canais': 1, 'sr': 44100}},
    'audiobook': {
        'nome': 'Audiobook (ACX)', 'desc': 'Limpa, tira tropeços e repetições, abaixa respirações e mira o padrão ACX (RMS −18 a −23, pico −3 dB). Mede no fim.',
        'fala': True, 'cats': ['cabeca', 'vicio', 'gaguejo', 'repeticao', 'respiracao', 'estouro'],
        'master': [_fx('ruido', nivel='medio'), _fx('passa_alta', freq=80), _fx('eq_preset', preset='voz'),
                   _fx('compressor', limiar=-24, razao=2.5, ataque=15, liberacao=220, ganho=3), _fx('gate', limiar=-62),
                   _fx('limitador', teto=-3.5)],
        'loudness': (-20, -3.5), 'medir': True},
    'reels15': {'nome': 'Música para Status (15 s)', 'desc': 'Fica com o melhor trecho de 15 s, com fade, em −14 LUFS.',
                'trecho': 15, 'master': [_fx('limitador', teto=-1)], 'loudness': (-14, -1)},
    'reels30': {'nome': 'Música para Reels (30 s)', 'desc': 'Fica com o melhor trecho de 30 s (o refrão), com fade, em −14 LUFS.',
                'trecho': 30, 'master': [_fx('limitador', teto=-1)], 'loudness': (-14, -1)},
    'reels60': {'nome': 'Música para TikTok (60 s)', 'desc': 'Fica com o melhor trecho de 60 s, com fade, em −14 LUFS.',
                'trecho': 60, 'master': [_fx('limitador', teto=-1)], 'loudness': (-14, -1)},
    'karaoke': {'nome': 'Karaokê (tirar a voz)', 'desc': 'Separa a voz com IA (Demucs) e fica só com o instrumental.',
                'separar': 'no_vocals', 'master': [], 'loudness': (-14, -1)},
    'isolar': {'nome': 'Isolar a voz', 'desc': 'Separa a voz com IA (Demucs) e tira a música e o ruído de fundo.',
               'separar': 'vocals', 'master': [_fx('limitador', teto=-1)], 'loudness': (-16, -1)},
}


def lista():
    return [{'id': k, 'nome': v['nome'], 'desc': v['desc'], 'fala': bool(v.get('fala')),
             'ia': bool(v.get('separar'))} for k, v in RECEITAS.items()]


def _fontes_do_projeto(proj, tipos=None):
    out = []
    for p in proj['pistas']:
        if tipos and p.get('tipo') not in tipos:
            continue
        for c in p['clipes']:
            if c['fonte'] not in out:
                out.append(c['fonte'])
    return out


def _fontes_alvo(proj, r):
    """Receita de fala mexe só nas pistas de voz (a trilha de música não perde as
    pausas dela); receita de música, só nas de música. Sem pista do tipo certo,
    vale para todas."""
    if r.get('trecho') or r.get('separar'):
        return _fontes_do_projeto(proj, {'musica'}) or _fontes_do_projeto(proj)
    return _fontes_do_projeto(proj, {'voz'}) or _fontes_do_projeto(proj)


def enfileirar(pid, rid, modelo='base'):
    """Põe na fila tudo que a receita precisa, na ordem certa."""
    if rid not in RECEITAS:
        raise P.ProjetoError('Receita desconhecida.')
    r = RECEITAS[rid]
    proj = P.ler(pid)
    fontes = _fontes_alvo(proj, r)
    if not fontes:
        raise P.ProjetoError('Importe um áudio antes de usar uma receita.')
    tarefas = []
    if r.get('separar'):
        for fid in fontes:
            tarefas.append(F.adicionar('separar', pid, {'fonte': fid, 'parte': r['separar']},
                                       f'{r["nome"]}: separar com IA'))
    else:
        for fid in fontes:
            if r.get('fala') and not os.path.exists(P.caminho_transcricao(pid, fid)):
                tarefas.append(F.adicionar('transcrever', pid, {'fonte': fid, 'modelo': modelo}, 'Transcrever (para a receita)'))
            tarefas.append(F.adicionar('analisar', pid, {'fonte': fid, 'musica': True if r.get('trecho') else None,
                                                         'pausa_min': r.get('pausa_min', 0.9), 'pausa_manter': r.get('manter', 0.45)},
                                       'Analisar (para a receita)', unica=False))
    tarefas.append(F.adicionar('receita', pid, {'receita': rid}, f'Receita: {r["nome"]}', unica=False))
    if r.get('medir'):
        tarefas.append(F.adicionar('medir', pid, {}, 'Medir (relatório ACX)', unica=False))
    return tarefas


def aplicar_sugestoes(proj, sugestoes, ids=None, cats=None, manter=None):
    """Aplica sugestões (as escolhidas por id ou por categoria) na lista de edição.
    -> (segundos cortados, efeitos sugeridos)"""
    cortes = {}
    reduzir = {}
    efeitos = []
    for s in sugestoes:
        if ids is not None and s['id'] not in ids:
            continue
        if cats is not None and s['cat'] not in cats:
            continue
        fid = s['fonte']
        if s['acao'] == 'cortar':
            cortes.setdefault(fid, []).append((s['ini'], s['fim']))
        elif s['acao'] == 'encurtar':
            cortes.setdefault(fid, []).extend(ED.encurtar_trechos([(s['ini'], s['fim'])], manter if manter is not None else s.get('manter', 0.45)))
        elif s['acao'] == 'reduzir':
            reduzir.setdefault(fid, []).append((s['ini'], s['fim'], s.get('db', -15)))
        elif s['acao'] == 'efeito' and s.get('efeito'):
            efeitos.append(s['efeito'])
    for fid, rs in reduzir.items():
        ED.reduzir_trechos(proj, fid, rs)
    total = 0.0
    for fid, cs in cortes.items():
        rem = ED.cortar_fonte(proj, fid, cs, ripple=True)
        total += max(rem.values() or [0])
    return total, efeitos


def tarefa(t, ctx):
    from AudioStudio import as_analise as A
    pid = t['projeto']
    r = RECEITAS[t['args']['receita']]
    ctx.blocos(2)
    ctx.etapa('Aplicando a receita', 0.2)
    proj = P.ler(pid)
    sug = A.ler(pid).get('fontes', {})
    cortado = 0.0
    efeitos_extra = []
    if r.get('trecho'):
        melhor = None
        for fid in _fontes_alvo(proj, r):
            for s in (sug.get(fid) or {}).get('sugestoes', []):
                if s['cat'] == 'trecho' and s.get('duracao') == r['trecho']:
                    if melhor is None or s['conf'] > melhor[1]['conf']:
                        melhor = (fid, s)
        if melhor is None:
            raise F.FilaError(f'A música é curta demais para um trecho de {r["trecho"]} s (ou não pareceu música).')
        fid, s = melhor
        a = ED.fonte_para_projeto(proj, fid, s['ini'])
        if a is None:
            raise F.FilaError('O trecho escolhido não está mais no projeto (foi cortado).')
        ED.recortar(proj, a, a + (s['fim'] - s['ini']))
    elif r.get('cats'):
        for fid in _fontes_alvo(proj, r):
            lista_s = (sug.get(fid) or {}).get('sugestoes', [])
            c, ef = aplicar_sugestoes(proj, lista_s, cats=set(r['cats']), manter=r.get('manter'))
            cortado += c
            efeitos_extra += ef
    master = [dict(x) for x in r['master']]
    for ef in efeitos_extra:   # efeito sugerido (recuperar estouro) entra no começo da cadeia
        if not any(m['ef'] == ef['ef'] for m in master):
            master.insert(0, {'ef': ef['ef'], 'ativo': True, 'p': ef.get('p', {})})
    proj['master'] = E.validar_cadeia(master)
    alvo, pico = r['loudness']
    proj['loudness'] = {'ativo': True, 'alvo': alvo, 'pico': pico}
    if r.get('exportar'):
        proj['exportar_padrao'] = r['exportar']
    proj['versao'] = int(proj.get('versao', 1)) + 1
    P._gravar(pid, proj)
    ctx.bloco_feito()
    ctx.bloco_feito()
    return {'receita': t['args']['receita'], 'cortado': round(cortado, 1), 'duracao': round(ED.duracao(proj), 1)}


# ---------------------------------------------------------------- Demucs ---

PEDACO_S = 45
TETO_DEMUCS_MB = 1900
PRECISA_DEMUCS_MB = 1600


def separar(t, ctx):
    pid, fid, parte = t['projeto'], t['args']['fonte'], t['args'].get('parte', 'vocals')
    pf = P.pasta_fonte(pid, fid)
    info = M.ler_fonte(pf)
    if F.ram_livre_mb() - F.MARGEM_MB < PRECISA_DEMUCS_MB:
        raise MemoryError()
    trab = os.path.join(P.pasta(pid), 'separar', fid)
    pedacos = os.path.join(trab, 'pedacos')
    saida = os.path.join(trab, 'demucs')
    shutil.rmtree(trab, ignore_errors=True)
    os.makedirs(pedacos)
    ctx.blocos(3)
    ctx.etapa('Cortando em pedaços para a IA', 0.02)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', M.arquivo_original(pf), '-vn', '-ac', '2',
                    '-ar', '44100', '-f', 'segment', '-segment_time', str(PEDACO_S), '-c:a', 'pcm_s16le',
                    os.path.join(pedacos, 'p%04d.wav')], check=True, timeout=3600)
    nomes = sorted(os.listdir(pedacos))
    feitos = {'n': 0}

    def ler(linha):
        import re
        if linha.startswith('Separating track'):
            feitos['n'] += 1
        m = re.search(r'(\d{1,3})%\|', linha)
        frac = int(m.group(1)) / 100 if m else 0
        ctx.etapa(f'Separando com IA: pedaço {max(1, feitos["n"])} de {len(nomes)}',
                  0.05 + 0.85 * (max(0, feitos['n'] - 1) + frac) / len(nomes))
    ctx.rodar([sys.executable, '-m', 'demucs', '--two-stems', 'vocals', '--mp3', '-o', saida,
               *[os.path.join(pedacos, n) for n in nomes]], teto_mb=TETO_DEMUCS_MB, ao_ler=ler)
    ctx.bloco_feito()
    partes = [os.path.join(saida, 'htdemucs', os.path.splitext(n)[0], f'{parte}.mp3') for n in nomes]
    if not all(os.path.exists(x) for x in partes):
        raise F.FilaError('A IA não gerou todas as partes.')
    lista = os.path.join(trab, 'lista.txt')
    with open(lista, 'w', encoding='utf-8') as f:
        f.writelines(f"file '{x}'\n" for x in partes)
    nova = os.path.join(trab, 'resultado.flac')
    ctx.etapa('Juntando o resultado', 0.92)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lista,
                    '-t', f'{info["duracao"]:.3f}', '-c:a', 'flac', nova], check=True, timeout=3600)
    rotulo = 'voz' if parte == 'vocals' else 'instrumental'
    base, _ = os.path.splitext(info['nome'])
    nfid = P._id()
    npf = os.path.join(P.pasta(pid), 'fontes', nfid)
    M.guardar_fonte(nova, npf, f'{base} ({rotulo}).flac')
    M.preparar(npf, _CtxMudo())
    shutil.rmtree(trab, ignore_errors=True)
    proj = P.ler(pid)
    for pista in proj['pistas']:
        for c in pista['clipes']:
            if c['fonte'] == fid:
                c['fonte'] = nfid
    proj['versao'] = int(proj.get('versao', 1)) + 1
    P._gravar(pid, proj)
    ctx.bloco_feito()
    ctx.bloco_feito()
    return {'fonte': nfid, 'parte': rotulo}


class _CtxMudo:
    def __init__(self):
        self.t = {'feitos': 0, 'dados': {}}

    def blocos(self, n):
        pass

    def etapa(self, *a, **k):
        pass

    def bloco_feito(self, *a, **k):
        self.t['feitos'] += 1

    def checar(self):
        pass
