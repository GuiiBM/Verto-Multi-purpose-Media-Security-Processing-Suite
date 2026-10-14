"""Áudio Studio · sugestões de onde cortar (e de efeito), em tempo da FONTE.

Como as sugestões ficam presas ao tempo do arquivo importado (e não ao da
linha do tempo), continuam valendo depois de outras edições: o editor mostra
cada uma onde aquele trecho estiver agora.

Categorias:
- silencio   pausa longa -> encurtar para uma pausa natural (não some com ela)
- cabeca     começo e fim sem som
- vicio      "hã", "ahn", "hum", "éé", "uh", "um"…        (aceitar-tudo: sim)
- muleta     "tipo", "né", "sabe", "like", "o sea"…        (aceitar-tudo: não)
- gaguejo    palavra repetida em seguida ("eu eu")
- repeticao  frase começada e refeita: fica a última
- respiracao respiração alta entre frases -> abaixa 15 dB (não corta)
- estouro    clipping -> efeito "Recuperar estouro"
- volume     volume muito irregular -> efeito "Nivelar volume da fala"
- trecho     música: melhor trecho de 15/30/60 s (Reels, TikTok, Status)
O nível de "silêncio" sai do próprio arquivo (entre o ruído de fundo e a fala).
"""
import difflib
import json
import os
import re
import time
import unicodedata

import numpy as np

from AudioStudio import as_fila as F
from AudioStudio import as_midia as M
from AudioStudio import as_projeto as P

QUADRO = 0.02                        # 20 ms por medida de energia
N_QUADRO = int(M.SR_ANALISE * QUADRO)

VICIOS = {
    # só formas que não existem como palavra: "a" (artigo) e "e" (conjunção) ficam de fora
    'pt': re.compile(r'^(ah+|a{2,}h*|ãh*|ã{2,}|hã+|ahn+|anh+|hum+|hm+|h?m{2,}|uh+m*|eh+|é{2,}h*|e{2,}h*|éh+|mhm+|aham)$'),
    'en': re.compile(r'^(u+h+m*|u+m+|e+r+m*|a+h+|h+m+|m+h*m+|uh-huh|mm+)$'),
    'es': re.compile(r'^(e+h+|e+m+|m+h*m+|a+h+|ehm+)$'),
}
MULETAS = {
    'pt': {'tipo', 'né', 'ne', 'sabe', 'assim', 'enfim', 'basicamente', 'tá', 'ta', 'entendeu', 'beleza', 'olha', 'então'},
    'en': {'like', 'basically', 'actually', 'literally', 'so', 'right', 'okay', 'well'},
    'es': {'o', 'sea', 'pues', 'bueno', 'este', 'vale', 'digamos'},
}
NOMES = {
    'silencio': 'Pausas longas', 'cabeca': 'Começo e fim sem som', 'vicio': 'Vícios de linguagem',
    'muleta': 'Muletas (tipo, né, sabe…)', 'gaguejo': 'Palavra repetida', 'repeticao': 'Frase refeita',
    'respiracao': 'Respirações altas', 'estouro': 'Estouro (clipping)', 'volume': 'Volume irregular',
    'trecho': 'Melhor trecho (música)',
}


def _sid(fid, cat, ini):
    return f'{cat}-{fid[:4]}-{int(ini * 1000)}'


def _norm(w):
    t = unicodedata.normalize('NFKC', w.lower())
    return re.sub(r"[^\w\-]", '', t)


# ---------------------------------------------------------------- energia ---

def energia(pf, ctx=None):
    """dB por quadro de 20 ms (calculado em blocos e guardado em energia.npy)."""
    cache = os.path.join(pf, 'energia.npy')
    a = M.a16(pf)
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(os.path.join(pf, 'a16.raw')):
        return np.load(cache)
    n = len(a) // N_QUADRO
    out = np.empty(n, np.float32)
    passo = int(F.BLOCO_S / QUADRO)
    for i in range(0, n, passo):
        k = min(passo, n - i)
        blk = np.asarray(a[i * N_QUADRO:(i + k) * N_QUADRO], np.float32).reshape(k, N_QUADRO) / 32768.0
        out[i:i + k] = 10 * np.log10(np.maximum((blk ** 2).mean(1), 1e-10))
        if ctx:
            ctx.etapa('Medindo a energia do áudio', 0.05 + 0.25 * (i + k) / max(1, n))
    np.save(cache, out)
    return out


def niveis(db):
    real = db[db > -85]
    if not len(real):
        return -90.0, -90.0, -90.0
    piso = float(np.percentile(real, 8))
    fala = float(np.percentile(real, 90))
    limiar = piso + 0.38 * (fala - piso)
    return piso, fala, max(limiar, -60.0)


def parece_musica(db, fala):
    """Fala sobe e desce a cada sílaba (variação mediana de ~15 dB em 200 ms e
    ~40% dos quadros bem abaixo do nível da fala); música é sustentada (6 a 10 dB,
    ~18%). Medido em audiolivro, gravação de voz e três músicas."""
    real = db[db > -85]
    if len(real) < 100:
        return False
    quedas = float((real < fala - 15).mean())
    k = len(db) // 10
    modulacao = float(np.median(np.ptp(db[:k * 10].reshape(k, 10), axis=1))) if k else 0.0
    return modulacao < 12 and quedas < 0.3


def _corridas(mask):
    """Trechos True consecutivos -> [(i0, i1)] (i1 exclusivo)."""
    if not len(mask):
        return []
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


# ----------------------------------------------------------- categorias ---

def silencios(fid, db, limiar, palavras, minimo=0.9, manter=0.45):
    baixo = db < limiar
    out = []
    for i0, i1 in _corridas(baixo):
        a, b = i0 * QUADRO, i1 * QUADRO
        if b - a < minimo or i0 == 0 or i1 >= len(db):
            continue
        if palavras and any(w['ini'] < b - 0.05 and w['fim'] > a + 0.05 for w in palavras):
            continue
        conf = min(1.0, 0.55 + (b - a - minimo) / 3)
        out.append({'id': _sid(fid, 'silencio', a), 'cat': 'silencio', 'fonte': fid, 'ini': round(a, 3), 'fim': round(b, 3),
                    'acao': 'encurtar', 'manter': manter, 'conf': round(conf, 2),
                    'motivo': f'Pausa de {b - a:.1f} s: fica com {manter:.2f} s.'})
    return out


def cabeca_cauda(fid, db, limiar, dur, palavras):
    acima = np.where(db >= limiar)[0]
    if not len(acima):
        return []
    ini = acima[0] * QUADRO
    fim = (acima[-1] + 1) * QUADRO
    if palavras:
        ini = min(ini, palavras[0]['ini'])
        fim = max(fim, palavras[-1]['fim'])
    out = []
    if ini > 0.6:
        out.append({'id': _sid(fid, 'cabeca', 0), 'cat': 'cabeca', 'fonte': fid, 'ini': 0.0, 'fim': round(ini - 0.15, 3),
                    'acao': 'cortar', 'conf': 0.9, 'motivo': f'{ini:.1f} s sem som antes do começo.'})
    if dur - fim > 0.8:
        out.append({'id': _sid(fid, 'cabeca', fim), 'cat': 'cabeca', 'fonte': fid, 'ini': round(fim + 0.3, 3),
                    'fim': round(dur, 3), 'acao': 'cortar', 'conf': 0.9, 'motivo': f'{dur - fim:.1f} s sem som no fim.'})
    return out


def vicios(fid, palavras, idioma):
    reg = VICIOS.get(idioma, VICIOS['pt'])
    mul = MULETAS.get(idioma, MULETAS['pt'])
    out = []
    for i, w in enumerate(palavras):
        n = _norm(w['w'])
        if not n:
            continue
        # "é..." com reticências é o "é" de hesitação; sem elas é o verbo
        hesitacao = reg.match(n) or (idioma == 'pt' and n == 'é' and ('...' in w['w'] or '…' in w['w']))
        if hesitacao:
            out.append({'id': _sid(fid, 'vicio', w['ini']), 'cat': 'vicio', 'fonte': fid, 'ini': round(max(0, w['ini'] - 0.03), 3),
                        'fim': round(w['fim'] + 0.03, 3), 'acao': 'cortar', 'conf': 0.9,
                        'texto': w['w'], 'motivo': f'Hesitação "{w["w"].strip()}".'})
        elif n in mul:
            # muleta só quando está "solta" (pausa antes ou depois, ou vírgula)
            antes = w['ini'] - palavras[i - 1]['fim'] if i else 1
            depois = palavras[i + 1]['ini'] - w['fim'] if i + 1 < len(palavras) else 1
            if ',' in w['w'] or antes > 0.25 or depois > 0.25:
                out.append({'id': _sid(fid, 'muleta', w['ini']), 'cat': 'muleta', 'fonte': fid, 'ini': round(w['ini'] - 0.02, 3),
                            'fim': round(w['fim'] + 0.02, 3), 'acao': 'cortar', 'conf': 0.45, 'texto': w['w'],
                            'motivo': f'Muleta "{w["w"].strip(" ,.")}". Ouça antes de cortar.'})
    return out


def gaguejos(fid, palavras):
    out = []
    for a, b in zip(palavras, palavras[1:]):
        na, nb = _norm(a['w']), _norm(b['w'])
        # "não, não" e "Morte! Morte!" são ênfase de propósito; "-se -se" é pedaço de palavra
        if re.search(r'[,;:!?.…]$', a['w'].strip()) or a['w'].strip().startswith('-') or na.startswith('-'):
            continue
        if na and na == nb and b['ini'] - a['fim'] < 0.35 and len(na) <= 12:
            out.append({'id': _sid(fid, 'gaguejo', a['ini']), 'cat': 'gaguejo', 'fonte': fid, 'ini': round(a['ini'], 3),
                        'fim': round(b['ini'], 3), 'acao': 'cortar', 'conf': 0.8, 'texto': f'{a["w"]} {b["w"]}',
                        'motivo': f'"{a["w"].strip()}" repetido.'})
    return out


def _frases(palavras, pausa=0.55):
    frases, atual = [], []
    for i, w in enumerate(palavras):
        atual.append(w)
        prox = palavras[i + 1] if i + 1 < len(palavras) else None
        fim_frase = re.search(r'[.!?…]$', w['w'].strip()) or prox is None or prox['ini'] - w['fim'] > pausa
        if fim_frase:
            frases.append(atual)
            atual = []
    return frases


def repeticoes(fid, palavras):
    """Frase começada e refeita logo depois: corta a primeira tentativa."""
    out = []
    frases = _frases(palavras)
    for i, f in enumerate(frases):
        na = [_norm(w['w']) for w in f if _norm(w['w'])]
        if len(na) < 3:
            continue
        for j in (i + 1, i + 2):
            if j >= len(frases):
                break
            nb = [_norm(w['w']) for w in frases[j] if _norm(w['w'])][:len(na) + 2]
            r = difflib.SequenceMatcher(None, na, nb).ratio()
            if r >= 0.78:
                fim = frases[i + 1][0]['ini'] if j == i + 1 else frases[j][0]['ini']
                texto = ' '.join(w['w'] for w in f)
                out.append({'id': _sid(fid, 'repeticao', f[0]['ini']), 'cat': 'repeticao', 'fonte': fid,
                            'ini': round(f[0]['ini'] - 0.05, 3), 'fim': round(fim - 0.05, 3), 'acao': 'cortar',
                            'conf': round(min(1.0, r), 2), 'texto': texto[:160],
                            'motivo': 'Frase dita de novo logo depois: fica a última versão.'})
                break
    return out


def respiracoes(fid, db, palavras, limiar, fala):
    out = []
    for a, b in zip(palavras, palavras[1:]):
        g0, g1 = a['fim'] + 0.04, b['ini'] - 0.04
        if not 0.18 <= g1 - g0 <= 1.2:
            continue
        seg = db[int(g0 / QUADRO):int(g1 / QUADRO)]
        if not len(seg):
            continue
        pico = float(np.percentile(seg, 85))
        if limiar <= pico <= fala - 6:
            out.append({'id': _sid(fid, 'respiracao', g0), 'cat': 'respiracao', 'fonte': fid, 'ini': round(g0, 3),
                        'fim': round(g1, 3), 'acao': 'reduzir', 'db': -15, 'conf': 0.55,
                        'motivo': 'Respiração alta entre frases: abaixa 15 dB.'})
    return out


def estouros(fid, pf):
    pk = np.fromfile(os.path.join(pf, 'picos.i8'), dtype=np.int8).reshape(-1, 2) if os.path.exists(os.path.join(pf, 'picos.i8')) else None
    if pk is None or not len(pk):
        return []
    clip = (pk[:, 1] >= 126) | (pk[:, 0] <= -127)
    trechos = [(i0 / 250, i1 / 250) for i0, i1 in _corridas(clip) if i1 - i0 >= 2]
    total = sum(b - a for a, b in trechos)
    if total < 0.05:
        return []
    onde = ', '.join(f'{int(a // 60)}:{int(a % 60):02d}' for a, _ in trechos[:5]) + ('…' if len(trechos) > 5 else '')
    return [{'id': _sid(fid, 'estouro', 0), 'cat': 'estouro', 'fonte': fid, 'ini': round(trechos[0][0], 3),
             'fim': round(trechos[0][1], 3), 'acao': 'efeito', 'efeito': {'ef': 'declip', 'p': {}}, 'conf': 0.85,
             'motivo': f'{len(trechos)} trecho(s) estourado(s), {total:.1f} s no total (em {onde}). Aplica "Recuperar estouro".',
             'onde': [[round(a, 2), round(b, 2)] for a, b in trechos[:200]]}]


def volume_irregular(fid, db, limiar):
    jan = int(5 / QUADRO)
    medias = []
    for i in range(0, len(db) - jan, jan):
        seg = db[i:i + jan]
        seg = seg[seg >= limiar]
        if len(seg) > jan * 0.3:
            medias.append(float(np.mean(seg)))
    if len(medias) < 6:
        return []
    med = np.median(medias)
    fora = sum(1 for m in medias if abs(m - med) > 7)
    desvio = float(np.std(medias))
    if desvio < 3.5 and fora < max(2, len(medias) * 0.08):
        return []
    return [{'id': _sid(fid, 'volume', 0), 'cat': 'volume', 'fonte': fid, 'ini': 0.0, 'fim': 0.0, 'acao': 'efeito',
             'efeito': {'ef': 'nivelar', 'p': {'forca': 6 if desvio > 5 else 4}}, 'conf': 0.7,
             'motivo': f'O volume da fala varia muito (desvio de {desvio:.1f} dB entre trechos). Aplica "Nivelar volume da fala".'}]


# ----------------------------------------------------------------- música ---

def _stft_mag(x, n, hop):
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    k = 1 + (len(x) - n) // hop
    idx = np.arange(n)[None, :] + hop * np.arange(k)[:, None]
    jan = np.hanning(n).astype(np.float32)
    out = np.empty((k, n // 2 + 1), np.float32)
    for i in range(0, k, 4000):
        out[i:i + 4000] = np.abs(np.fft.rfft(x[idx[i:i + 4000]] * jan, axis=1))
    return out


def batidas(sinal):
    """Tempo (BPM) e batidas pelo fluxo espectral + autocorrelação."""
    hop, n = 256, 1024
    fps = M.SR_ANALISE / hop
    mag = np.log1p(_stft_mag(sinal, n, hop))
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(1)
    flux = np.concatenate([[0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, mode='same')
    flux = np.maximum(flux, 0)
    if flux.max() <= 0:
        return None, []
    env = flux / flux.max()
    ac = np.correlate(env - env.mean(), env - env.mean(), mode='full')[len(env) - 1:]
    melhor, bpm = -1, 120.0
    for b in np.arange(60, 181, 0.5):
        lag = 60 * fps / b
        i = int(round(lag))
        if i >= len(ac):
            continue
        peso = np.exp(-0.5 * (np.log2(b / 120) / 0.9) ** 2)
        v = ac[i] * peso
        if v > melhor:
            melhor, bpm = v, b
    periodo = 60 * fps / bpm
    p = int(round(periodo))
    fases = [env[f::p].sum() if p > 0 else 0 for f in range(max(1, p))]
    fase = int(np.argmax(fases))
    beats = []
    t = float(fase)
    while t < len(env):
        a, b = int(max(0, t - 0.1 * periodo)), int(min(len(env), t + 0.1 * periodo + 1))
        j = a + int(np.argmax(env[a:b])) if b > a else int(t)
        beats.append(round(j / fps, 3))
        t = j + periodo
    return round(float(bpm), 1), beats


def _croma(sinal):
    n, hop = 4096, 2048
    mag = _stft_mag(sinal, n, hop)
    freqs = np.fft.rfftfreq(n, 1 / M.SR_ANALISE)
    sel = (freqs >= 60) & (freqs <= 5000)
    pc = (np.round(12 * np.log2(freqs[sel] / 440.0) + 69).astype(int)) % 12
    cr = np.zeros((len(mag), 12), np.float32)
    for k in range(12):
        cr[:, k] = mag[:, sel][:, pc == k].sum(1)
    cr /= np.maximum(np.linalg.norm(cr, axis=1, keepdims=True), 1e-9)
    fps = M.SR_ANALISE / hop
    return cr, fps


def melhores_trechos(fid, sinal, db, beats):
    dur = len(sinal) / M.SR_ANALISE
    if dur < 25 or dur > 1200:
        return []
    cr, fps = _croma(sinal)
    # 2 quadros por segundo, suavizados em 1 s
    passo = max(1, int(round(fps / 2)))
    k = len(cr) // passo
    c2 = cr[:k * passo].reshape(k, passo, 12).mean(1)
    c2 = np.array([c2[max(0, i - 1):i + 2].mean(0) for i in range(k)])
    c2 /= np.maximum(np.linalg.norm(c2, axis=1, keepdims=True), 1e-9)
    ssm = c2 @ c2.T
    e = db[:int(len(db) // 25) * 25].reshape(-1, 25).mean(1)   # dB a cada 0,5 s
    e = np.interp(np.arange(k), np.linspace(0, k - 1, len(e)), e) if len(e) else np.zeros(k)
    en = (e - np.percentile(e, 10)) / max(1e-6, np.percentile(e, 95) - np.percentile(e, 10))
    out = []
    for L in (15, 30, 60):
        if dur < L + 8:
            continue
        w = L * 2
        notas = []
        for s in range(0, k - w, 2):
            fora = np.ones(k, bool)
            fora[max(0, s - w // 2):min(k, s + w + w // 2)] = False
            if not fora.any():
                continue
            rep = ssm[s:s + w][:, fora].max(1).mean()
            notas.append((0.6 * rep + 0.4 * float(np.clip(en[s:s + w].mean(), 0, 1)), s))
        if not notas:
            continue
        nota, s = max(notas)
        ini = s / 2
        if beats:   # começa numa batida
            antes = [b for b in beats if b <= ini + 0.3]
            ini = antes[-1] if antes else ini
        fim = min(dur, ini + L)
        out.append({'id': _sid(fid, 'trecho', L), 'cat': 'trecho', 'fonte': fid, 'ini': round(ini, 3), 'fim': round(fim, 3),
                    'acao': 'trecho', 'duracao': L, 'conf': round(float(min(1, nota)), 2),
                    'motivo': f'Melhor trecho de {L} s (a parte que mais se repete e mais forte: o refrão).'})
    return out


# ---------------------------------------------------------------- tarefa ---

def _arq(pid):
    return os.path.join(P.pasta(pid), 'sugestoes.json')


def ler(pid):
    try:
        with open(_arq(pid), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'fontes': {}}


def tarefa(t, ctx):
    pid, fid = t['projeto'], t['args']['fonte']
    pf = P.pasta_fonte(pid, fid)
    info = M.ler_fonte(pf)
    if info.get('estado') != 'pronta':
        raise F.FilaError('O arquivo ainda está sendo preparado.')
    ctx.blocos(4)
    ctx.etapa('Medindo a energia do áudio', 0.05)
    db = energia(pf, ctx)
    piso, fala, limiar = niveis(db)
    ctx.bloco_feito()
    tr = P.ler_transcricao(pid, fid)
    palavras = (tr or {}).get('palavras') or []
    idioma = (tr or {}).get('idioma') or 'pt'
    musica = t['args'].get('musica')
    if musica is None:
        musica = parece_musica(db, fala) and len(palavras) < info['duracao'] * 0.8
    # em música, parte baixinha (introdução, ponte) não é pausa: só silêncio de verdade
    limiar_sil = min(limiar, -45.0) if musica else limiar
    sug = []
    sug += cabeca_cauda(fid, db, limiar_sil, info['duracao'], palavras)
    sug += silencios(fid, db, limiar_sil, palavras, float(t['args'].get('pausa_min', 0.9)) * (2 if musica else 1),
                     float(t['args'].get('pausa_manter', 0.45)))
    sug += estouros(fid, pf)
    if not musica:
        sug += volume_irregular(fid, db, limiar)
    ctx.etapa('Procurando vícios e repetições', 0.5)
    if palavras:
        sug += vicios(fid, palavras, idioma[:2])
        sug += gaguejos(fid, palavras)
        sug += repeticoes(fid, palavras)
        sug += respiracoes(fid, db, palavras, limiar, fala)
    ctx.bloco_feito()
    resultado = {'piso': round(piso, 1), 'fala': round(fala, 1), 'limiar': round(limiar, 1), 'musica': bool(musica)}
    if musica and info['duracao'] <= 1200:
        ctx.etapa('Achando as batidas e o refrão', 0.75)
        sinal = np.asarray(M.a16(pf), np.float32) / 32768.0
        bpm, bts = batidas(sinal)
        resultado.update(bpm=bpm, batidas=bts)
        sug += melhores_trechos(fid, sinal, db, bts)
    ctx.bloco_feito()
    # sugestões que se sobrepõem na mesma categoria viram uma
    sug.sort(key=lambda s: (s['cat'], s['ini']))
    final = []
    for s in sug:
        if final and final[-1]['cat'] == s['cat'] and s['acao'] == 'cortar' and final[-1]['acao'] == 'cortar' \
                and s['ini'] <= final[-1]['fim']:
            final[-1]['fim'] = max(final[-1]['fim'], s['fim'])
            final[-1]['texto'] = (final[-1].get('texto', '') + ' ' + s.get('texto', '')).strip()
            continue
        final.append(s)
    padrao_ok = {'silencio', 'cabeca', 'vicio', 'gaguejo', 'repeticao', 'estouro', 'volume'}
    for s in final:
        s['padrao'] = s['cat'] in padrao_ok
    tudo = ler(pid)
    tudo.setdefault('fontes', {})[fid] = {'sugestoes': final, **resultado, 'transcrita': bool(palavras),
                                          'gerada': time.strftime('%Y-%m-%d %H:%M')}
    with open(_arq(pid) + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(tudo, f, ensure_ascii=False)
    os.replace(_arq(pid) + '.tmp', _arq(pid))
    ctx.bloco_feito()
    contagem = {}
    for s in final:
        contagem[s['cat']] = contagem.get(s['cat'], 0) + 1
    return {'sugestoes': len(final), 'por_categoria': contagem, **{k: v for k, v in resultado.items() if k != 'batidas'}}
