"""Mapa de cortes: o que fica e o que sai do vídeo.

Cada palavra tem início e fim no vídeo original. Os intervalos entre
palavras maiores que o limite do preset viram corte, sempre com uma folga
antes e depois para não comer o começo ou o fim da fala. Palavras marcadas
como removidas (retomada ou à mão, na revisão) também saem.

Como o Whisper às vezes estica uma palavra por cima do silêncio, os tempos
são conferidos antes com o silencedetect do FFmpeg (ajustar_ao_silencio).
"""
import difflib
import re
import unicodedata

CORTE_MINIMO = 0.08   # corte menor que isso não vale um pulo na imagem


# ------------------------------------------------------------ palavras ---

def ajustar_ao_silencio(palavras, silencios, margem=0.02):
    """Puxa para fora do silêncio o começo/fim de palavra que caiu dentro
    dele. Palavra inteira dentro do silêncio e com baixa confiança é
    alucinação: sai."""
    if not silencios:
        return palavras
    out = []
    for w in palavras:
        ini, fim = w['ini'], w['fim']
        dentro = False
        for s0, s1 in silencios:
            if s1 <= ini or s0 >= fim:
                continue
            if s0 <= ini and s1 >= fim:
                dentro = True
                break
            if s0 <= ini < s1 < fim:
                ini = max(ini, s1 - margem)
            if ini < s0 < fim <= s1:
                fim = min(fim, s0 + margem)
        if dentro and w.get('p', 1) < 0.5:
            continue
        out.append({**w, 'ini': round(float(ini), 3), 'fim': round(float(max(fim, ini + 0.04)), 3)})
    return out


def _normalizar(texto):
    texto = unicodedata.normalize('NFD', texto.lower())
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^\w]+', '', texto)


def frases(palavras, pausa=0.35):
    """Índices [(i0, i1)] de cada frase: quebra na pontuação final ou numa pausa."""
    out, ini = [], None
    for i, w in enumerate(palavras):
        if w.get('removida') == 'manual':
            continue
        if ini is None:
            ini = i
        fim_frase = re.search(r'[.!?…]$', w['w'])
        prox = next((p for p in palavras[i + 1:] if p.get('removida') != 'manual'), None)
        if fim_frase or not prox or prox['ini'] - w['fim'] > pausa:
            out.append((ini, i))
            ini = None
    return out


def detectar_retomadas(palavras, pausa=0.35):
    """Quando a pessoa erra e repete a frase, duas frases seguidas muito
    parecidas indicam retomada: fica só a última. Marca as palavras da
    primeira com removida='retomada'. Devolve [(i0, i1, texto, parecida_com)]."""
    achadas = []
    fr = frases(palavras, pausa)
    for (a0, a1), (b0, b1) in zip(fr, fr[1:]):
        a = [_normalizar(palavras[i]['w']) for i in range(a0, a1 + 1)]
        b = [_normalizar(palavras[i]['w']) for i in range(b0, b1 + 1)]
        a, b = [x for x in a if x], [x for x in b if x]
        if len(a) < 2 or len(b) < 2:
            continue
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        cobre = sum(m.size for m in sm.get_matching_blocks()) / len(a)
        # Mesma frase de novo, ou um começo interrompido que a seguinte refaz.
        if sm.ratio() >= 0.6 or (cobre >= 0.8 and a[0] == b[0] and len(a) <= len(b)):
            for i in range(a0, a1 + 1):
                palavras[i]['removida'] = 'retomada'
            achadas.append((a0, a1, ' '.join(palavras[i]['w'] for i in range(a0, a1 + 1)),
                            ' '.join(palavras[i]['w'] for i in range(b0, b1 + 1))))
    return achadas


# ------------------------------------------------------------- trechos ---

def chave_pausa(i, j):
    return f'{i}-{j}'


def calcular(palavras, pausa_max, folga, duracao, mantidas=()):
    """Trechos [(ini, fim)] que ficam e cortes [{ini, fim, motivo, chave}] que saem.

    mantidas: chaves de pausas que o usuário mandou manter na revisão."""
    mantidas = set(mantidas or ())
    vivas = [(i, w) for i, w in enumerate(palavras) if not w.get('removida')]
    if not vivas:
        if any(w.get('removida') for w in palavras):
            return [], [{'ini': 0.0, 'fim': duracao, 'motivo': 'manual', 'chave': None}]
        return [(0.0, duracao)], []

    trechos, cortes = [], []
    i0, w0 = vivas[0]
    removidas_antes = [w for w in palavras[:i0] if w.get('removida')]
    ini = max(0.0, w0['ini'] - folga, max((w['fim'] for w in removidas_antes), default=0.0))
    if ini >= CORTE_MINIMO:
        cortes.append({'ini': 0.0, 'fim': ini, 'motivo': 'inicio', 'chave': None})
    else:
        ini = 0.0
    (ia, wa) = vivas[0]
    for (ib, wb) in vivas[1:]:
        entre = palavras[ia + 1:ib]
        removidas = [w for w in entre if w.get('removida')]
        if removidas:
            fim = min(wa['fim'] + folga, removidas[0]['ini'])
            prox = max(wb['ini'] - folga, removidas[-1]['fim'])
            motivo = 'retomada' if any(w['removida'] == 'retomada' for w in removidas) else 'manual'
            chave = None
        else:
            gap = wb['ini'] - wa['fim']
            chave = chave_pausa(ia, ib)
            if gap <= pausa_max or chave in mantidas:
                ia, wa = ib, wb
                continue
            fim, prox, motivo = wa['fim'] + folga, wb['ini'] - folga, 'pausa'
        if prox - fim >= CORTE_MINIMO:
            trechos.append((ini, fim))
            cortes.append({'ini': round(fim, 3), 'fim': round(prox, 3), 'motivo': motivo, 'chave': chave})
            ini = prox
        ia, wa = ib, wb
    removidas_depois = [w for w in palavras[ia + 1:] if w.get('removida')]
    fim = min(duracao, wa['fim'] + folga, min((w['ini'] for w in removidas_depois), default=duracao))
    if duracao - fim >= CORTE_MINIMO:
        trechos.append((ini, fim))
        cortes.append({'ini': round(fim, 3), 'fim': duracao, 'motivo': 'fim', 'chave': None})
    else:
        trechos.append((ini, duracao))
    return [(round(a, 3), round(b, 3)) for a, b in trechos], cortes


def alinhar_aos_quadros(trechos, fps):
    """Cada borda cai num quadro exato: assim o vídeo (que só tem quadros) e o
    áudio (cortado por amostra) têm exatamente a mesma duração em cada trecho
    e não dessincronizam somando cortes."""
    out = []
    for a, b in trechos:
        qa, qb = round(a * fps), round(b * fps)
        if qb - qa < 1:
            continue
        if out and qa <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], qb))
        else:
            out.append((qa, qb))
    return [(qa / fps, qb / fps) for qa, qb in out]


def duracao_final(trechos):
    return sum(b - a for a, b in trechos)


def tempo_no_video_final(t, trechos):
    """Reposiciona um instante do vídeo original no vídeo cortado,
    descontando tudo o que foi cortado antes dele. É o que mantém a legenda
    sincronizada."""
    acumulado = 0.0
    for a, b in trechos:
        if t < a:
            return acumulado
        if t <= b:
            return acumulado + (t - a)
        acumulado += b - a
    return acumulado


def inicios_no_final(trechos):
    """Onde cada trecho começa no vídeo final."""
    out, acc = [], 0.0
    for a, b in trechos:
        out.append(acc)
        acc += b - a
    return out

