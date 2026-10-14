"""Áudio Studio · render: a lista de edição vira áudio.

1. Cada pista é mixada em blocos de 10 min (numpy, 48 kHz estéreo): para cada
   clipe, só o trecho necessário da fonte é decodificado (trechos vizinhos da
   mesma fonte numa leitura só), com ganho, fades, um fade de 5 ms em toda
   emenda (corte sem estalo), pan, volume da pista e envelope. Cada bloco vira
   um FLAC 24 bits a -6 dB (sobra para somar sem estourar) e a tarefa pode
   retomar do bloco em que parou.
2. Um grafo do FFmpeg junta as pistas (com ducking: a música abaixa quando há
   voz), aplica a cadeia do master e a loudness em duas passadas e grava uma
   mixagem final em FLAC; dela saem o arquivo no formato pedido e as regiões.
"""
import json
import os
import re
import shutil
import subprocess
import time
import zipfile

import numpy as np

from AudioStudio import as_midia as M
from AudioStudio import as_efeitos as E
from AudioStudio import as_edicao as ED
from AudioStudio import as_projeto as P

SR = 48000
BLOCO_S = 600
MICRO_FADE = 0.005
JUNTAR_GAP = 3.0

FORMATOS = {
    'wav': ('wav', 'audio/wav'), 'flac': ('flac', 'audio/flac'), 'mp3': ('mp3', 'audio/mpeg'),
    'ogg': ('ogg', 'audio/ogg'), 'opus': ('opus', 'audio/ogg'), 'm4a': ('m4a', 'audio/mp4'),
}


class RenderError(Exception):
    pass


# ------------------------------------------------------------ mixagem ---

def _pistas_ativas(proj):
    solo = [p for p in proj['pistas'] if p.get('solo')]
    return [p for p in (solo or proj['pistas']) if not p.get('mudo') and p['clipes']]


def _env(pista, t):
    env = pista.get('envelope') or []
    if not env:
        return None
    xs = np.array([e[0] for e in env], float)
    ys = np.array([e[1] for e in env], float)
    return 10 ** (np.interp(t, xs, ys) / 20)


def mixar_bloco(proj, pista, t0, t1, fontes_pasta):
    """Pista no intervalo [t0, t1) do projeto -> float32 (n, 2)."""
    n = int(round((t1 - t0) * SR))
    buf = np.zeros((n, 2), np.float32)
    pedacos = []
    for c in pista['clipes']:
        x, y = max(t0, c['pos']), min(t1, c['pos'] + c['dur'])
        if y - x > 1e-4:
            pedacos.append((c, x, y))
    # agrupa leituras da mesma fonte que ficam perto (uma decodificação só)
    por_fonte = {}
    for c, x, y in pedacos:
        por_fonte.setdefault(c['fonte'], []).append((c['ini'] + x - c['pos'], c['ini'] + y - c['pos']))
    lidos = {}
    for fid, trechos in por_fonte.items():
        trechos.sort()
        grupos = []
        for a, b in trechos:
            if grupos and a - grupos[-1][1] <= JUNTAR_GAP:
                grupos[-1][1] = max(grupos[-1][1], b)
            else:
                grupos.append([a, b])
        lidos[fid] = []
        for a, b in grupos:
            a0 = max(0.0, a - 0.01)
            dados = M.decodificar(M.arquivo_original(fontes_pasta(fid)), a0, (b - a0) + 0.02, SR, 2, 'f32le')
            lidos[fid].append((a0, dados))
    for c, x, y in pedacos:
        s0 = c['ini'] + (x - c['pos'])
        bloco = next(((a0, d) for a0, d in lidos[c['fonte']] if a0 <= s0 + 1e-6 and a0 + len(d) / SR >= s0), None)
        if bloco is None:
            continue
        a0, dados = bloco
        i0 = int(round((s0 - a0) * SR))
        k = int(round((y - x) * SR))
        trecho = dados[i0:i0 + k]
        k = len(trecho)
        if k == 0:
            continue
        o = int(round((x - t0) * SR))
        k = min(k, n - o)
        trecho = trecho[:k]
        # ganho + fades (o fade pedido ou, no mínimo, 5 ms em cada emenda)
        tc = (x - c['pos']) + np.arange(k) / SR            # tempo desde o início do clipe
        resta = c['dur'] - tc
        fi = max(c.get('fi') or 0.0, MICRO_FADE)
        fo = max(c.get('fo') or 0.0, MICRO_FADE)
        g = np.minimum(1.0, tc / fi) * np.minimum(1.0, np.maximum(0.0, resta) / fo)
        g *= 10 ** ((c.get('ganho') or 0.0) / 20)
        buf[o:o + k] += trecho * g[:, None].astype(np.float32)
    # pista: volume, pan (equilíbrio) e envelope
    ganho = 10 ** ((pista.get('ganho') or 0.0) / 20)
    pan = float(pista.get('pan') or 0.0)
    buf[:, 0] *= ganho * min(1.0, 1 - pan)
    buf[:, 1] *= ganho * min(1.0, 1 + pan)
    env = _env(pista, t0 + np.arange(n) / SR)
    if env is not None:
        buf *= env[:, None].astype(np.float32)
    return buf


def _escrever_flac(caminho, dados):
    import soundfile as sf
    sf.write(caminho, np.clip(dados * 0.5, -1, 1), SR, subtype='PCM_24', format='FLAC')


# --------------------------------------------------------------- FFmpeg ---

def _grafo(proj, entradas, duracao, medir=None):
    """entradas: [(tipo_da_pista, idx_ffmpeg)] -> (filter_complex, rótulo de saída)."""
    partes = []
    vozes, musicas, outros = [], [], []
    for tipo, i in entradas:
        rot = f'p{i}'
        partes.append(f'[{i}:a]volume=2[{rot}]')
        (vozes if tipo == 'voz' else musicas if tipo == 'musica' else outros).append(rot)
    duck = proj.get('ducking') or {}
    mix = []
    if duck.get('ativo') and vozes and musicas:
        if len(vozes) > 1:
            partes.append(''.join(f'[{v}]' for v in vozes) + f'amix=inputs={len(vozes)}:normalize=0[vz0]')
        else:
            partes.append(f'[{vozes[0]}]anull[vz0]')
        partes.append('[vz0]asplit=2[vz][chave]')
        if len(musicas) > 1:
            partes.append(''.join(f'[{m}]' for m in musicas) + f'amix=inputs={len(musicas)}:normalize=0[mu0]')
        else:
            partes.append(f'[{musicas[0]}]anull[mu0]')
        razao = 1 + float(duck.get('reducao', 12)) / 3
        partes.append(f'[mu0][chave]sidechaincompress=threshold=0.02:ratio={razao:.2f}:attack=30:release=450:knee=4[mu]')
        mix = ['vz', 'mu'] + outros
    else:
        mix = vozes + musicas + outros
    if len(mix) > 1:
        partes.append(''.join(f'[{m}]' for m in mix) + f'amix=inputs={len(mix)}:normalize=0:dropout_transition=0[mix]')
    else:
        partes.append(f'[{mix[0]}]anull[mix]')
    cadeia = E.filtros(proj.get('master') or [], duracao)
    cadeia.append('aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo')
    lo = proj.get('loudness') or {}
    if medir == 'loudnorm':
        # medir com o ebur128 é 4× mais rápido que o loudnorm (que roda a 192 kHz)
        cadeia.append('ebur128=peak=true')
    elif isinstance(medir, dict):
        # loudness linear: ganho até o alvo + limitador abaixo do teto de pico
        # (0,5 dB de folga para os picos entre amostras)
        ganho = float(lo.get('alvo', -16)) - medir['I']
        teto = 10 ** ((float(lo.get('pico', -1)) - 0.5) / 20)
        cadeia.append(f'volume={ganho:.3f}dB')
        cadeia.append(f'alimiter=limit={teto:.5f}:attack=3:release=60:level=disabled')
    elif medir == 'pico':
        cadeia.append('volumedetect')
    elif isinstance(medir, (int, float)):
        cadeia.append(f'volume={medir:.3f}dB')
    partes.append('[mix]' + ','.join(cadeia) + '[saida]')
    return ';'.join(partes), '[saida]'


def _ffmpeg(ctx, args, duracao, etapa, p0, p1):
    def ler(linha):
        m = re.match(r'out_time_us=(\d+)', linha)
        if m and duracao > 0:
            ctx.etapa(etapa, p0 + (p1 - p0) * min(1.0, int(m.group(1)) / 1e6 / duracao))
    return ctx.rodar(['ffmpeg', '-hide_banner', '-nostats', '-loglevel', 'info', '-y', '-progress', 'pipe:1', *args], ao_ler=ler)


def _medida_ebur(linhas):
    texto = '\n'.join(linhas)
    i = re.findall(r'I:\s+(-?[\d.]+) LUFS', texto)
    tp = re.findall(r'Peak:\s+(-?[\d.]+|-inf) dBFS', texto)
    if not i:
        raise RenderError('Não consegui medir a loudness.')
    v = float(i[-1])
    if v < -70:
        raise RenderError('O áudio está mudo demais para medir a loudness.')
    return {'I': v, 'TP': float(tp[-1]) if tp and tp[-1] != '-inf' else -99.0}


def _entradas_args(listas):
    args = []
    for lista in listas:
        args += ['-f', 'concat', '-safe', '0', '-i', lista]
    return args


def mixdown(pid, ctx, faixa=None, nome_saida='mix.flac'):
    """Gera a mixagem final (FLAC 48 kHz estéreo) com master e loudness. -> caminho"""
    proj = P.ler(pid)
    pasta = P.pasta(pid)
    trab = os.path.join(pasta, 'render')
    os.makedirs(trab, exist_ok=True)
    pistas = _pistas_ativas(proj)
    if not pistas:
        raise RenderError('Não há nada para exportar (as pistas estão vazias ou mudas).')
    t_ini, t_fim = (faixa if faixa else (0.0, ED.duracao(proj)))
    dur = t_fim - t_ini
    if dur <= 0.01:
        raise RenderError('O projeto está vazio.')
    nb = max(1, int(np.ceil(dur / BLOCO_S)))
    total = len(pistas) * nb
    ctx.blocos(total + 1)
    feitos_ok = set(ctx.t['dados'].get('stems_feitos', []))
    assinatura = json.dumps([proj['pistas'], faixa], sort_keys=True)
    if ctx.t['dados'].get('assinatura') != assinatura:
        feitos_ok = set()     # o projeto mudou desde a última tentativa: refaz tudo
        ctx.t['dados']['assinatura'] = assinatura
        ctx.t['feitos'] = 0
    listas = []
    k = 0
    for pi, pista in enumerate(pistas):
        arqs = []
        for b in range(nb):
            k += 1
            a = t_ini + b * BLOCO_S
            z = min(t_fim, a + BLOCO_S)
            arq = os.path.join(trab, f'{pista["id"]}_{b:04d}.flac')
            arqs.append(arq)
            chave = f'{pista["id"]}:{b}'
            if chave in feitos_ok and os.path.exists(arq):
                continue
            t0 = time.time()
            ctx.etapa(f'Mixando "{pista["nome"]}": bloco {b + 1} de {nb}', (k - 1) / (total + 1))
            dados = mixar_bloco(proj, pista, a, z, lambda fid: P.pasta_fonte(pid, fid))
            _escrever_flac(arq, dados)
            feitos_ok.add(chave)
            ctx.bloco_feito({'stems_feitos': sorted(feitos_ok)}, seg=time.time() - t0)
        lista = os.path.join(trab, f'{pista["id"]}.txt')
        with open(lista, 'w', encoding='utf-8') as f:
            f.writelines(f"file '{x}'\n" for x in arqs)
        listas.append((pista.get('tipo', 'voz'), lista))

    entradas = [(tipo, i) for i, (tipo, _) in enumerate(listas)]
    args_in = _entradas_args([l for _, l in listas])
    saida = os.path.join(trab, nome_saida)
    lo = proj.get('loudness') or {}
    pico = E.pico_alvo(proj.get('master') or [])
    medida = None
    p_mix = len(listas) and (total / (total + 1))
    if lo.get('ativo'):
        g, rot = _grafo(proj, entradas, dur, 'loudnorm')
        linhas = _ffmpeg(ctx, [*args_in, '-filter_complex', g, '-map', rot, '-f', 'null', '-'], dur,
                         'Medindo a loudness', p_mix, p_mix + (1 - p_mix) / 2)
        medida = _medida_ebur(linhas)
    elif pico is not None:
        g, rot = _grafo(proj, entradas, dur, 'pico')
        linhas = _ffmpeg(ctx, [*args_in, '-filter_complex', g, '-map', rot, '-f', 'null', '-'], dur,
                         'Medindo o pico', p_mix, p_mix + (1 - p_mix) / 2)
        mx = next((float(m.group(1)) for l in linhas for m in [re.search(r'max_volume:\s*(-?[\d.]+) dB', l)] if m), 0.0)
        medida = pico - mx
    g, rot = _grafo(proj, entradas, dur, medida)
    _ffmpeg(ctx, [*args_in, '-filter_complex', g, '-map', rot, '-ar', '48000', '-c:a', 'flac', '-sample_fmt', 's32',
                  saida], dur, 'Aplicando os efeitos', p_mix + (1 - p_mix) / 2 if medida is not None else p_mix, 0.98)
    ctx.bloco_feito(seg=None)
    return saida, proj


# ------------------------------------------------------------ exportar ---

def _codec(op):
    f = op.get('formato', 'wav')
    sr = str(int(op.get('sr') or 48000))
    canais = '1' if str(op.get('canais')) == '1' else '2'
    base = ['-ar', sr, '-ac', canais]
    if f == 'wav':
        bits = str(op.get('bits') or '24')
        return base + ['-c:a', {'16': 'pcm_s16le', '24': 'pcm_s24le', '32': 'pcm_f32le'}.get(bits, 'pcm_s24le')]
    if f == 'flac':
        return base + ['-c:a', 'flac', '-sample_fmt', 's16' if str(op.get('bits')) == '16' else 's32']
    kbps = int(op.get('kbps') or {'mp3': 320, 'ogg': 192, 'opus': 128, 'm4a': 256}[f])
    if f == 'mp3':
        return base + ['-c:a', 'libmp3lame', '-b:a', f'{kbps}k', '-id3v2_version', '3']
    if f == 'ogg':
        return base + ['-c:a', 'libvorbis', '-b:a', f'{kbps}k']
    if f == 'opus':
        return ['-ar', '48000', '-ac', canais, '-c:a', 'libopus', '-b:a', f'{kbps}k']
    return base + ['-c:a', 'aac', '-b:a', f'{kbps}k']


def _tags(proj):
    t = proj.get('tags') or {}
    mapa = {'titulo': 'title', 'artista': 'artist', 'album': 'album', 'ano': 'date', 'genero': 'genre', 'comentario': 'comment'}
    out = []
    if not t.get('titulo'):
        out += ['-metadata', f"title={proj['nome']}"]
    for k, v in t.items():
        if v and k in mapa:
            out += ['-metadata', f'{mapa[k]}={v}']
    return out


def _capa(pid):
    c = os.path.join(P.pasta(pid), 'capa.jpg')
    return c if os.path.exists(c) else None


def _codificar(mix, destino, op, proj, pid, ss=None, to=None):
    capa = _capa(pid) if op.get('formato') in ('mp3', 'm4a', 'flac') else None
    args = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y']
    if ss is not None:
        args += ['-ss', f'{ss:.3f}', '-to', f'{to:.3f}']
    args += ['-i', mix]
    if capa:
        args += ['-i', capa, '-map', '0:a', '-map', '1:v', '-c:v', 'copy', '-disposition:v', 'attached_pic']
    args += _codec(op) + _tags(proj) + [destino]
    p = subprocess.run(args, capture_output=True, text=True, timeout=7200)
    if p.returncode != 0:
        raise RenderError('O FFmpeg não conseguiu gerar o arquivo: ' + (p.stderr.strip().splitlines() or ['erro'])[-1])


def exportar(pid, op, ctx):
    """Tarefa da fila. -> {'arquivo', 'bytes'} (um arquivo ou um ZIP com as regiões)."""
    mix, proj = mixdown(pid, ctx)
    fmt = op.get('formato', 'wav')
    if fmt not in FORMATOS:
        raise RenderError('Formato desconhecido.')
    ext = FORMATOS[fmt][0]
    pasta_exp = os.path.join(P.pasta(pid), 'exportados')
    os.makedirs(pasta_exp, exist_ok=True)
    base = M.nome_seguro(proj['nome'], 'audio')
    carimbo = time.strftime('%Y%m%d-%H%M%S')
    ctx.etapa('Gravando o arquivo final', 0.99)
    arquivos = []
    if not op.get('so_regioes'):
        destino = os.path.join(pasta_exp, f'{carimbo}__{base}.{ext}')
        _codificar(mix, destino, op, proj, pid)
        arquivos.append(destino)
    if op.get('regioes') and proj.get('regioes'):
        for i, r in enumerate(sorted(proj['regioes'], key=lambda r: r['ini']), 1):
            destino = os.path.join(pasta_exp, f'{carimbo}__{base} - {i:02d} {M.nome_seguro(r["nome"], "regiao")}.{ext}')
            _codificar(mix, destino, op, proj, pid, r['ini'], r['fim'])
            arquivos.append(destino)
    if not arquivos:
        raise RenderError('Não há regiões marcadas para exportar.')
    if len(arquivos) == 1:
        final = arquivos[0]
    else:
        final = os.path.join(pasta_exp, f'{carimbo}__{base}.zip')
        with zipfile.ZipFile(final, 'w', zipfile.ZIP_STORED) as z:
            for a in arquivos:
                z.write(a, os.path.basename(a).split('__', 1)[1])
        for a in arquivos:
            os.remove(a)
    shutil.rmtree(os.path.join(P.pasta(pid), 'render'), ignore_errors=True)
    return {'arquivo': os.path.basename(final), 'nome': os.path.basename(final).split('__', 1)[1],
            'bytes': os.path.getsize(final)}


def medir(pid, ctx):
    """Tarefa da fila: loudness integrada, LRA, true peak, RMS, pico e piso de ruído
    da mixagem final (o relatório do Audiobook/ACX sai daqui)."""
    mix, proj = mixdown(pid, ctx, nome_saida='medir.flac')
    ctx.etapa('Medindo', 0.99)
    p = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', mix, '-af', 'ebur128=peak=true,astats=measure_overall=all:measure_perchannel=none',
                        '-f', 'null', '-'], capture_output=True, text=True, timeout=7200)
    txt = p.stderr

    def achar(rx, padrao=None):
        m = re.findall(rx, txt)
        return float(m[-1]) if m else padrao
    r = {
        'lufs': achar(r'I:\s+(-?[\d.]+) LUFS'),
        'lra': achar(r'LRA:\s+(-?[\d.]+) LU'),
        'true_peak': achar(r'Peak:\s+(-?[\d.]+) dBFS'),
        'rms': achar(r'RMS level dB:\s*(-?[\d.]+|-inf)'),
        'pico': achar(r'Peak level dB:\s*(-?[\d.]+)'),
        'ruido': achar(r'Noise floor dB:\s*(-?[\d.]+)'),
    }
    r['acx'] = {
        'rms_ok': r['rms'] is not None and -23 <= r['rms'] <= -18,
        'pico_ok': r['pico'] is not None and r['pico'] <= -3,
        'ruido_ok': r['ruido'] is not None and r['ruido'] <= -60,
    }
    shutil.rmtree(os.path.join(P.pasta(pid), 'render'), ignore_errors=True)
    return r


class _CtxSimples:
    """Contexto mínimo para renders curtos fora da fila (prévia fiel)."""

    def __init__(self):
        self.t = {'dados': {}, 'feitos': 0, 'blocos': 0}

    def etapa(self, *_a, **_k):
        pass

    def blocos(self, n):
        self.t['blocos'] = n

    def bloco_feito(self, guardar=None, seg=None):
        if guardar:
            self.t['dados'].update(guardar)

    def checar(self):
        pass

    def rodar(self, cmd, teto_mb=None, ao_ler=None, timeout=None):
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout or 600)
        linhas = (p.stdout + '\n' + p.stderr).splitlines()
        if ao_ler:
            for l in linhas:
                ao_ler(l)
        if p.returncode != 0:
            raise RenderError(next((l for l in reversed(linhas) if l.strip()), 'erro no FFmpeg'))
        return linhas


def previa_fiel(pid, t, dur=10.0):
    """10 s em volta de t com tudo aplicado (efeitos sem prévia no navegador). -> bytes WAV"""
    proj = P.ler(pid)
    total = ED.duracao(proj)
    a = max(0.0, min(t, max(0.0, total - dur)))
    b = min(total, a + dur)
    lo = proj.get('loudness') or {}
    ctx = _CtxSimples()
    pasta = P.pasta(pid)
    trab = os.path.join(pasta, 'render_previa')
    shutil.rmtree(trab, ignore_errors=True)
    os.makedirs(trab)
    listas = []
    for pista in _pistas_ativas(proj):
        dados = mixar_bloco(proj, pista, a, b, lambda fid: P.pasta_fonte(pid, fid))
        arq = os.path.join(trab, f'{pista["id"]}.flac')
        _escrever_flac(arq, dados)
        lista = os.path.join(trab, f'{pista["id"]}.txt')
        with open(lista, 'w') as f:
            f.write(f"file '{arq}'\n")
        listas.append((pista.get('tipo', 'voz'), lista))
    if not listas:
        raise RenderError('Não há nada para ouvir aqui.')
    g, rot = _grafo(proj, [(tp, i) for i, (tp, _) in enumerate(listas)], b - a, None)
    if lo.get('ativo'):
        # numa janela curta a loudness é só aproximada: forma dinâmica do loudnorm
        g = g.replace('[saida]', f"[pre];[pre]loudnorm=I={lo.get('alvo', -16)}:TP={lo.get('pico', -1)}:LRA=11,"
                                 "aresample=48000[saida]")
    saida = os.path.join(trab, 'previa.wav')
    ctx.rodar(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *_entradas_args([l for _, l in listas]),
               '-filter_complex', g, '-map', rot, '-ar', '48000', '-c:a', 'pcm_s16le', saida])
    with open(saida, 'rb') as f:
        dados = f.read()
    shutil.rmtree(trab, ignore_errors=True)
    return dados, a
