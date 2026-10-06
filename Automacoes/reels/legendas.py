"""Legendas: blocos de 2 a 4 palavras, a palavra falada em destaque.

O .ass é queimado no vídeo (filtro ass do FFmpeg/libass) e um .srt sai
separado. Os tempos já estão no vídeo cortado (cortes.tempo_no_video_final).
A fonte Montserrat ExtraBold (OFL) vem em fontes/, então a legenda sai igual
em qualquer computador.
"""
import re

FONTE = 'Montserrat ExtraBold'

# Cores do ASS são &HAABBGGRR (alfa, azul, verde, vermelho).
ESTILOS = {
    'classico': {'nome': 'Clássico', 'desc': 'Branca com contorno, palavra falada em amarelo',
                 'cor': '&H00FFFFFF', 'destaque': '&H0000D7FF', 'contorno': '&H00000000', 'fundo': '&H64000000',
                 'borda': 1, 'esp_contorno': 0.075, 'sombra': 0.03, 'tamanho': 0.068, 'maiusculas': True, 'escala': 108},
    'caixa': {'nome': 'Caixa', 'desc': 'Texto sobre uma faixa escura, palavra falada em verde',
              'cor': '&H00FFFFFF', 'destaque': '&H0066FF33', 'contorno': '&H50000000', 'fundo': '&H50000000',
              'borda': 3, 'esp_contorno': 0.16, 'sombra': 0, 'tamanho': 0.06, 'maiusculas': False, 'escala': 100},
    'minimal': {'nome': 'Minimal', 'desc': 'Menor e discreta, sem destaque',
                'cor': '&H00FFFFFF', 'destaque': None, 'contorno': '&H00000000', 'fundo': '&H80000000',
                'borda': 1, 'esp_contorno': 0.045, 'sombra': 0.02, 'tamanho': 0.05, 'maiusculas': False, 'escala': 100},
    'nenhuma': {'nome': 'Sem legenda', 'desc': 'Só o .srt separado'},
}


def margem_inferior(W, H):
    """Distância da legenda até a borda de baixo. No vertical (Reels/Stories)
    o Instagram cobre ~25% de baixo com descrição e botões."""
    r = H / W
    if r >= 1.6:
        return int(H * 0.30)
    if r >= 1.15:
        return int(H * 0.14)
    if r >= 0.9:
        return int(H * 0.12)
    return int(H * 0.09)


def blocos(palavras, minimo=2, maximo=4, max_letras=24, pausa=0.6):
    """Agrupa palavras {'w', 'ini', 'fim'} (tempo final) em blocos de legenda,
    quebrando na pontuação, numa pausa ou quando a linha fica longa."""
    out, atual = [], []
    for i, w in enumerate(palavras):
        atual.append(w)
        prox = palavras[i + 1] if i + 1 < len(palavras) else None
        letras = sum(len(x['w']) + 1 for x in atual)
        pontuacao = re.search(r'[.!?…,;:]$', w['w'])
        quebra = (prox is None or len(atual) >= maximo or letras >= max_letras
                  or (prox and prox['ini'] - w['fim'] > pausa)
                  or (pontuacao and len(atual) >= minimo)
                  or (re.search(r'[.!?…]$', w['w'])))
        if quebra:
            out.append(atual)
            atual = []
    return out


def _tempo_ass(t):
    cs = max(0, int(round(t * 100)))
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'


def _tempo_srt(t):
    ms = max(0, int(round(t * 1000)))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


def _escapar(texto):
    return texto.replace('\\', '⧵').replace('{', '(').replace('}', ')').replace('\n', ' ')


def _intervalos(grupos, total):
    """(ini, fim) de cada bloco: fica na tela até o próximo começar (no máximo
    0,4 s depois da última palavra), sem sobrepor."""
    out = []
    for k, g in enumerate(grupos):
        ini = g[0]['ini']
        fim = g[-1]['fim'] + 0.4
        if k + 1 < len(grupos):
            fim = min(fim, grupos[k + 1][0]['ini'])
        out.append((ini, max(min(fim, total), ini + 0.2)))
    return out


def gerar_ass(palavras, W, H, estilo, total):
    e = ESTILOS.get(estilo) or ESTILOS['classico']
    base = min(W, H)
    tam = int(base * e['tamanho'])
    ml = int(W * 0.08)
    cabecalho = (
        '[Script Info]\nScriptType: v4.00+\n'
        f'PlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n'
        '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
        'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
        'Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f"Style: Verto,{FONTE},{tam},{e['cor']},&H000000FF,{e['contorno']},{e['fundo']},0,0,0,0,100,100,1,0,"
        f"{e['borda']},{round(tam * e['esp_contorno'], 1)},{round(tam * e['sombra'], 1)},2,{ml},{ml},{margem_inferior(W, H)},1\n\n"
        '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    linhas = []
    grupos = blocos(palavras)
    for g, (ini, fim) in zip(grupos, _intervalos(grupos, total)):
        textos = [_escapar(w['w'].upper() if e['maiusculas'] else w['w']) for w in g]
        if not e['destaque']:
            linhas.append(f'Dialogue: 0,{_tempo_ass(ini)},{_tempo_ass(fim)},Verto,,0,0,0,,{" ".join(textos)}')
            continue
        # Um evento por palavra: o bloco inteiro, com a palavra da vez em destaque.
        for j, w in enumerate(g):
            a = ini if j == 0 else w['ini']
            b = g[j + 1]['ini'] if j + 1 < len(g) else fim
            if b - a < 0.01:
                continue
            partes = [(f"{{\\c{e['destaque']}\\fscx{e['escala']}\\fscy{e['escala']}}}{t}{{\\r}}" if k == j else t)
                      for k, t in enumerate(textos)]
            linhas.append(f'Dialogue: 0,{_tempo_ass(a)},{_tempo_ass(b)},Verto,,0,0,0,,{" ".join(partes)}')
    return cabecalho + '\n'.join(linhas) + '\n'


def gerar_srt(palavras, total):
    grupos = blocos(palavras)
    out = []
    for n, (g, (ini, fim)) in enumerate(zip(grupos, _intervalos(grupos, total)), 1):
        out.append(f"{n}\n{_tempo_srt(ini)} --> {_tempo_srt(fim)}\n{' '.join(w['w'] for w in g)}\n")
    return '\n'.join(out)
