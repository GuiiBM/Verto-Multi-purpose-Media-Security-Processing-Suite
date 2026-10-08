"""Aplica o visual LocalTools com um "modo" próprio por app.

O comum a todos (base.css + app.css): fundo grafite, fonte Geist, botão de
voltar, marca LOCALTOOLS, ícone 3D do app. A identidade de cada app fica em
static/localtools/modos/<modo>.css (ver docs/REDESIGN.md).

O script é idempotente: página que já tem "lt-body" é pulada.
Uso: python scripts/visual_modos.py [modo ...]
"""
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TRACO = RAIZ / 'static' / 'localtools' / 'traco'


def svg_traco(nome):
    corpo = re.sub(r'^<svg[^>]*>|</svg>$', '', (TRACO / f'{nome}.svg').read_text().strip())
    return f'<svg class="traco" viewBox="0 0 256 256" aria-hidden="true">{corpo}</svg>'


# Ícone de traço de cada ferramenta dos hubs (rota -> símbolo)
ICONES = {
    '/aiguard/detect': 'magnifying-glass', '/aiguard/humanize': 'pencil-line', '/aiguard/plagiarism': 'copy',
    '/captureocr/ocr': 'text-aa', '/captureocr/record': 'video-camera',
    '/devdata/format': 'brackets-angle', '/devdata/mock': 'dice-five', '/devdata/convert': 'swap', '/devdata/encode': 'lock-key',
    '/imagestudio/solo': 'image', '/imagestudio/resize': 'crop', '/imagestudio/filters': 'sliders-horizontal',
    '/imagestudio/favicon': 'app-window',
    '/matchaeffect/ai/add': 'sparkle', '/matchaeffect/ai/remove': 'eraser', '/matchaeffect/ai/video': 'film-strip',
    '/matchaeffect/ai/video/remove': 'film-slate', '/matchaeffect/add': 'plus-circle', '/matchaeffect/remove': 'minus-circle',
    '/matchaeffect/video/add': 'video', '/matchaeffect/video/remove': 'video-camera-slash',
    '/office/convert': 'arrows-left-right', '/office/repair': 'first-aid-kit',
    '/smartstudio/studio': 'microphone-stage', '/smartstudio/editor': 'waveform',
    '/subtitlelab/editor': 'closed-captioning', '/subtitlelab/burn': 'fire',
    '/textclean/diff': 'git-diff', '/textclean/sanitize': 'broom', '/textclean/stats': 'chart-bar',
}

# (fonte, modo, grupo, id do app, nome do app, tipo, rota do hub, título da página)
# tipo: 'principal' (hub ou app de uma página) | 'ferramenta' (página dentro de um hub)
P = []
def hub(pasta, prefixo, modo, grupo, app, nome, rota, ferramentas):
    P.append((f'{pasta}/{prefixo}_hub.html', modo, grupo, app, nome, 'principal', rota, nome))
    for arq, titulo in ferramentas:
        P.append((f'{pasta}/{prefixo}_{arq}.html', modo, grupo, app, nome, 'ferramenta', rota, titulo))

hub('AIGuard', 'aiguard', 'analise', 'texto', 'aiguard', 'AI Guard & Diff', '/aiguard',
    [('detect', 'Detector de IA'), ('humanize', 'Reescritor & Diff'), ('plagiarism', 'Plágio interno')])
hub('CaptureOCR', 'captureocr', 'visor', 'imagem', 'captureocr', 'Capture & OCR', '/captureocr',
    [('ocr', 'OCR local'), ('record', 'Gravador de tela & GIF')])
hub('DevData', 'devdata', 'terminal', 'dev', 'devdata', 'Dev/Data', '/devdata',
    [('format', 'Beautifier / Minifier'), ('mock', 'Dados mock'), ('convert', 'Conversor de formatos'), ('encode', 'Encode / Decode')])
hub('ImageStudio', 'imagestudio', 'mesa-de-luz', 'imagem', 'imagestudio', 'Image Studio', '/imagestudio',
    [('solo', 'Editor individual'), ('resize', 'Crop & Resize'), ('filters', 'Filtros & Marca d’água'), ('favicon', 'Gerador de favicon')])
hub('MatchaEffect', 'matchaeffect', 'matcha', 'imagem', 'matchaeffect', 'Matcha Effect', '/matchaeffect',
    [('ai_add', 'Adicionar com IA'), ('ai_remove', 'Remover com IA'), ('ai_video', 'Vídeo com IA: adicionar'),
     ('ai_video_remove', 'Vídeo com IA: remover'), ('add', 'Adicionar efeito'), ('remove', 'Remover efeito'),
     ('video_add', 'Vídeo: adicionar efeito'), ('video_remove', 'Vídeo: remover efeito')])
hub('Office', 'office', 'pastas', 'documentos', 'office', 'Office', '/office',
    [('convert', 'Converter'), ('repair', 'Reparar e recuperar')])
hub('SmartStudio', 'smartstudio', 'no-ar', 'audio', 'smartstudio', 'Smart Studio', '/smartstudio',
    [('studio', 'Estúdio & teleprompter'), ('editor', 'Editor de corte')])
hub('SubtitleLab', 'subtitlelab', 'legenda', 'audio', 'subtitlelab', 'Subtitle Lab', '/subtitlelab',
    [('editor', 'Transcrição & timeline'), ('burn', 'Burn-in de legenda')])
hub('TextClean', 'textclean', 'diff', 'texto', 'textclean', 'Text Clean & Diff', '/textclean',
    [('diff', 'Text Diff'), ('sanitize', 'Sanitizador'), ('stats', 'Contador estatístico')])
P += [
    ('Encurtador/encurtador.html', 'bilhete', 'dev', 'encurtador', 'Encurtador', 'principal', '/', 'Encurtador'),
    ('templates/censor.html', 'tarja', 'privacidade', 'censor', 'Censor', 'principal', '/', 'Censor'),
    ('templates/clean.html', 'leitura', 'texto', 'clean', 'Clean Reader', 'principal', '/', 'Clean Reader'),
    ('templates/compress.html', 'prensa', 'conversao', 'compress', 'Compressor', 'principal', '/', 'Compressor'),
    ('templates/isolate.html', 'mesa-de-som', 'audio', 'isolate', 'Isolador de Voz', 'principal', '/', 'Isolador de Voz'),
    ('templates/qrcode.html', 'modulos', 'dev', 'qrcode', 'QR Code', 'principal', '/', 'QR Code'),
    ('templates/social.html', 'feed', 'imagem', 'social', 'Social Preview', 'principal', '/', 'Social Preview'),
    ('templates/tempo.html', 'calendario', 'dev', 'tempo', 'Tempo', 'principal', '/', 'Tempo'),
    ('app.py:FILES_HTML', 'fichario', 'conversao', 'files', 'Arquivos', 'principal', '/', 'Arquivos'),
    ('app.py:PURPLEFLIX_HTML', 'cinema', 'downloads', 'purpleflix', 'PurpleFlix', 'principal', '/', 'PurpleFlix'),
    ('app.py:TRANSPARENT_HTML', 'recorte', 'imagem', 'transparent', 'Transparência', 'principal', '/', 'Transparência'),
    ('app.py:TRANSCRIBE_HTML', 'fita', 'audio', 'transcribe', 'Transcrever', 'principal', '/', 'Transcrever'),
    ('app.py:GHOST_HTML', 'nevoa', 'privacidade', 'ghost', 'Ghost Tool', 'principal', '/', 'Ghost Tool'),
    ('app.py:STEALTH_HTML', 'esteganografia', 'privacidade', 'stealth', 'Stealth', 'principal', '/', 'Stealth'),
]

CORES = [('rgba(15, 23, 42', 'rgba(24, 26, 31'), ('rgba(2, 6, 23', 'rgba(12, 13, 16'), ('rgba(10, 15, 30', 'rgba(11, 12, 15'),
         ('#0a0f1e', '#0b0c0f'), ('#0f172a', '#16181c'), ('#020617', '#0c0d10'),
         ("'Inter', sans-serif", 'var(--lt-sans)'), ("'Inter', -apple-system", 'var(--lt-sans), -apple-system')]

VOLTAR = '''<a class="lt-back" href="{href}" title="{titulo}" aria-label="{titulo}">
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M19 12H5M5 12L12 19M5 12L12 5" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
  </a>'''


def sem_emoji(t):
    i = 0
    while i < len(t) and (unicodedata.category(t[i]) in ('So', 'Sk', 'Mn', 'Cf', 'Zs') or t[i] in '️‍'):
        i += 1
    return t[i:]


def cabecalho(modo, grupo, app, nome, tipo, rota, titulo, sub):
    marca = '<div class="topo"><a class="lt-brand" href="/"><span>LOCALTOOLS</span></a></div>'
    p = f'\n    <p class="modo-sub">{sub}</p>' if sub else ''
    if tipo == 'principal':
        return f'''{marca}
  <header class="lt-head modo-cab">
    <span class="lt-key lg" style="--hue: var(--lt-cat-{grupo})"><img src="/static/localtools/apps/{app}.webp" alt="" width="76" height="76"></span>
    <h1 class="modo-titulo">{titulo}</h1>{p}
  </header>'''
    return f'''{marca}
  <header class="modo-cab modo-cab-ferramenta">
    <nav class="modo-trilha" aria-label="Você está em"><a href="{rota}">{nome}</a> / {titulo}</nav>
    <h1 class="modo-titulo">{titulo}</h1>{p}
  </header>'''


def migrar(html, modo, grupo, app, nome, tipo, rota, titulo):
    log = []
    if 'lt-body' in html:
        return html, ['já migrada']
    html = re.sub(r"[ \t]*@import url\('https://fonts\.googleapis\.com[^\n]*\n?", '', html)
    html = re.sub(r'[ \t]*<link[^>]+fonts\.googleapis\.com[^>]*>\n?', '', html)
    html, n = re.subn(r'(<title>[^<]*</title>)', rf'''\1
  <meta name="theme-color" content="#0b0c0f">
  <link rel="icon" type="image/svg+xml" href="/static/localtools/verto.svg">
  <link rel="stylesheet" href="/static/localtools/base.css">
  <link rel="stylesheet" href="/static/localtools/app.css">
  <link rel="stylesheet" href="/static/localtools/modos/{modo}.css">''', html, count=1)
    log.append(f'links {n}')
    for a, b in CORES:
        html = html.replace(a, b)
    m = re.search(r'<body([^>]*)>', html)
    if m:
        attrs = m.group(1)
        if 'class="' in attrs:
            attrs = attrs.replace('class="', f'class="lt-body modo-{modo} ', 1)
        else:
            attrs = f' class="lt-body modo-{modo}"' + attrs
        html = html[:m.start()] + f'<body{attrs}>' + html[m.end():]
    log.append(f'body {1 if m else 0}')
    voltar_href = rota if tipo == 'ferramenta' else '/'
    voltar_tit = f'Voltar para {nome}' if tipo == 'ferramenta' else 'Voltar ao menu'
    html, n = re.subn(r'<(div|a|button) class="back-button"[^>]*>.*?</svg>\s*</\1>',
                      VOLTAR.format(href=voltar_href, titulo=voltar_tit), html, count=1, flags=re.S)
    log.append(f'voltar {n}')
    m = re.search(r'<(div|h1) class="logo"[^>]*>(.*?)</\1>\s*(?:<(div|p) class="tagline"[^>]*>(.*?)</\3>)?', html, re.S)
    if m:
        sub = (m.group(4) or '').strip()
        html = html[:m.start()] + cabecalho(modo, grupo, app, nome, tipo, rota, titulo, sub) + html[m.end():]
        log.append('cabeçalho' + ('' if sub else ' (sem sub)'))
    else:
        log.append('CABEÇALHO NÃO ACHADO')
    # cards dos hubs: link de verdade + ícone de traço
    def card(mo):
        href, miolo = mo.group(1), mo.group(2)
        ic = ICONES.get(href)
        if ic:
            miolo = re.sub(r'<div class="tool-icon">[^<]*</div>', f'<div class="tool-icon">{svg_traco(ic)}</div>', miolo)
        return f'<a class="tool-card" href="{href}">{miolo}</a>'
    html, n = re.subn(r'''<div class="tool-card" onclick="window\.location\.href='([^']+)'">(\s*<div class="tool-icon">.*?</div>\s*<div class="tool-title">.*?</div>\s*<div class="tool-desc">.*?</div>\s*)</div>''',
                      card, html, flags=re.S)
    if n:
        log.append(f'cards {n}')
    cont = [0]
    def limpa(mo):
        novo = sem_emoji(mo.group(2))
        cont[0] += novo != mo.group(2)
        return mo.group(1) + novo + mo.group(3)
    html = re.sub(r'(<button[^>]*>)([^<]+)(</button>)', limpa, html)
    html = re.sub(r'(<div class="group-title">)([^<]+)(</div>)', limpa, html)
    if cont[0]:
        log.append(f'emojis {cont[0]}')
    return html, log


def main(modos):
    app_py = RAIZ / 'app.py'
    for fonte, modo, grupo, app, nome, tipo, rota, titulo in P:
        if modos and modo not in modos:
            continue
        if fonte.startswith('app.py:'):
            const = fonte.split(':', 1)[1]
            s = app_py.read_text(encoding='utf-8')
            a = s.index(f'{const} = """')
            b = s.index('\n"""', a + 20)
            novo, log = migrar(s[a:b], modo, grupo, app, nome, tipo, rota, titulo)
            app_py.write_text(s[:a] + novo + s[b:], encoding='utf-8')
        else:
            p = RAIZ / fonte
            novo, log = migrar(p.read_text(encoding='utf-8'), modo, grupo, app, nome, tipo, rota, titulo)
            p.write_text(novo, encoding='utf-8')
        print(f'{modo:14} {fonte:44} ' + ' | '.join(log))




# ---------------------------------------------------------------- cores ---
# Destaques antigos de cada app -> paleta do modo. Cores com significado
# (vermelho de "provável IA", +/− do diff, Word/Excel/PowerPoint, verdes do
# Matcha) ficam como estão.
RECOR = {
    'tarja': {'#3b82f6': '#7c5ce0', '#6366f1': '#6d4bd8', '#8b5cf6': '#a78bfa', '#60a5fa': '#c4b5fd'},
    'leitura': {'#3b82f6': '#b7802f', '#8b5cf6': '#946422', '#ec4899': '#e9b872', '#60a5fa': '#e9b872'},
    'prensa': {'#22c55e': '#0284c7', '#16a34a': '#075985', '#4ade80': '#38bdf8', '#3b82f6': '#0ea5e9'},
    'mesa-de-som': {'#ec4899': '#b45309', '#db2777': '#a16207', '#8b5cf6': '#92400e', '#7c3aed': '#78350f', '#3b82f6': '#fbbf24'},
    'modulos': {'#22c55e': '#c2410c', '#16a34a': '#9a3412', '#15803d': '#7c2d12', '#4ade80': '#fb923c', '#3b82f6': '#f97316', '#60a5fa': '#fdba74'},
    'feed': {'#3b82f6': '#db2777', '#8b5cf6': '#be185d'},
    'calendario': {'#3b82f6': '#ea580c', '#60a5fa': '#fb923c', '#93c5fd': '#fdba74'},
    'bilhete': {'#4169e1': '#ea580c', '#3159d4': '#c2410c', '#2745a8': '#9a3412', '#a9bdf5': '#fdba74'},
    'fichario': {'#22c55e': '#0284c7', '#16a34a': '#075985', '#15803d': '#0c4a6e', '#4ade80': '#38bdf8', '#3b82f6': '#0ea5e9'},
    'recorte': {'#a855f7': '#db2777', '#9333ea': '#be185d'},
    'fita': {'#22c55e': '#b45309', '#16a34a': '#92400e', '#15803d': '#78350f', '#4ade80': '#fbbf24', '#3b82f6': '#f59e0b'},
    'esteganografia': {'#ef4444': '#7c5ce0', '#dc2626': '#6d4bd8', '#b91c1c': '#5232b5', '#fca5a5': '#c4b5fd'},
    'analise': {'#8b5cf6': '#0f9488', '#3b82f6': '#2dd4bf', '#c4b5fd': '#99f6e4'},
    'visor': {'#f97316': '#db2777', '#f59e0b': '#f472b6', '#ea580c': '#be185d'},
    'terminal': {'#3b82f6': '#ea580c', '#06b6d4': '#fb923c', '#60a5fa': '#fdba74', '#2563eb': '#c2410c', '#a5f3fc': '#fed7aa'},
    'mesa-de-luz': {'#a855f7': '#db2777', '#d8b4fe': '#f9a8d4', '#3b82f6': '#f472b6'},
    'no-ar': {'#d946ef': '#f59e0b', '#6366f1': '#fbbf24'},
    'legenda': {'#10b981': '#ca8a04', '#06b6d4': '#facc15', '#d1fae5': '#fef3c7'},
    'diff': {'#3b82f6': '#2dd4bf', '#14b8a6': '#0f9488'},
}


def _rgb(h):
    return f'{int(h[1:3], 16)}, {int(h[3:5], 16)}, {int(h[5:7], 16)}'


def recolorir(html, mapa):
    n = 0
    for velho, novo in mapa.items():
        for a, b in ((velho, novo), (velho.upper(), novo)):
            n += html.count(a)
            html = html.replace(a, b)
        a, b = f'rgba({_rgb(velho)},', f'rgba({_rgb(novo)},'
        n += html.count(a)
        html = html.replace(a, b)
    return html, n


def cores(modos):
    app_py = RAIZ / 'app.py'
    for fonte, modo, *_ in P:
        if modo not in RECOR or (modos and modo not in modos):
            continue
        if fonte.startswith('app.py:'):
            const = fonte.split(':', 1)[1]
            s = app_py.read_text(encoding='utf-8')
            a = s.index(f'{const} = """'); b = s.index('\n"""', a + 20)
            novo, n = recolorir(s[a:b], RECOR[modo])
            app_py.write_text(s[:a] + novo + s[b:], encoding='utf-8')
        else:
            p = RAIZ / fonte
            novo, n = recolorir(p.read_text(encoding='utf-8'), RECOR[modo])
            p.write_text(novo, encoding='utf-8')
        print(f'cores {modo:14} {fonte:44} {n} trocas')


# -------------------------------------------------------------- emojis ---
_EMO = r'(?:[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\u2190-\u21FF][\uFE0F\u200D]*)+'
# para texto corrido: sem setas e sem \u2713 \u2714 \u2715 \u2716 \u2717 \u2718, que s\u00E3o sinais da interface e n\u00E3o enfeite
_EMO_TEXTO = r'(?:[\U0001F000-\U0001FAFF\u2600-\u2712\u2719-\u27BF\u2B00-\u2BFF\u2300-\u23FF\u2139\u25B6\u25C0][\uFE0F\u200D]*)+'


# emoji que era o ícone inteiro de um elemento -> ícone de traço (static/localtools/traco)
ICONE_EMOJI = {
    '🗎': 'file-pdf', '📝': 'file-doc', '📄': 'file-text', '📃': 'file-txt', '📊': 'file-xls', '📋': 'file-csv',
    '📽️': 'file-ppt', '🖼️': 'file-image', '📷': 'camera', '📸': 'instagram-logo', '🎥': 'video-camera',
    '🎬': 'film-slate', '🐦': 'bird', '👥': 'users-three', '💬': 'chat-circle', '💼': 'briefcase',
    '📱': 'device-mobile', '📲': 'device-mobile-camera', '🔗': 'link', '❤️': 'heart', '🔖': 'bookmark-simple',
    '🔐': 'lock-key', '🛡️': 'shield-check', '📁': 'tray-arrow-up', '🔁': 'arrow-counter-clockwise',
}
_ICONES = {k.replace('\ufe0f', ''): v for k, v in ICONE_EMOJI.items()}


def emojis(modos):
    """Emoji no começo de títulos/rótulos sai (o texto fica); ícone de upload
    que era só um emoji vira o ícone de traço de envio."""
    alvo_upload = svg_traco('tray-arrow-up')
    app_py = RAIZ / 'app.py'
    for fonte, modo, *_ in P + [(f, 'tema-' + t) for f, t in TEMAS] + [(f, 'pdf-papel') for f in PDFS]:
        if modos and modo not in modos:
            continue
        def tratar(html):
            n = [0]
            def tira(mo):
                n[0] += 1
                return mo.group(1)
            html = re.sub(r'(<(?:h[1-4]|label|legend)(?:\s[^>]*)?>)\s*' + _EMO + r'\s*(?=[^\s<\uFE0F\u200D])', tira, html)
            html = re.sub(r'(<(?:div|span) class="(?:[a-z-]*-)?(?:title|label|heading)"[^>]*>)\s*' + _EMO + r'\s*(?=[^\s<\uFE0F\u200D])', tira, html)
            html, k = re.subn(r'(<div class="(?:upload-icon|drop-zone-icon|drop-icon|upload-emoji)">)\s*' + _EMO + r'\s*(</div>)',
                              lambda m: m.group(1) + alvo_upload + m.group(2), html)
            # qualquer outro texto da marcação que comece com emoji (botões, opções,
            # avisos, legendas); <script> e <style> ficam de fora, e setas e ✓/✕ ficam
            trocas = [0]
            partes = re.split(r'(<script\b.*?</script>|<style\b.*?</style>)', html, flags=re.S)
            for i in range(0, len(partes), 2):
                partes[i] = re.sub(r'(>\s*)' + _EMO_TEXTO + r'[ \t]*(?=[^\s<\uFE0F\u200D])', tira, partes[i])
            # textos montados no JS (rótulo de botão devolvido depois do processo,
            # mensagens de status): sai o emoji do começo da string; string que é
            # só o emoji fica (ex.: o estilo "emoji" do Censor)
            for i in range(1, len(partes), 2):
                if partes[i].startswith('<script'):
                    partes[i] = re.sub(r'''([`'"](?:<span>)?)''' + _EMO_TEXTO + r'''(?:[ \t]+|(?=[^`'"\s\uFE0F\u200D]))''', tira, partes[i])
            # elemento que era só um emoji vira o ícone de traço equivalente
            for i in range(0, len(partes), 2):
                def troca(m):
                    nome = _ICONES.get(m.group(3).replace('\ufe0f', ''))
                    if not nome:
                        return m.group(0)
                    trocas[0] += 1
                    return m.group(1) + svg_traco(nome) + m.group(4)
                partes[i] = re.sub(r'(<(\w+)[^>]*>)\s*(' + _EMO_TEXTO + r')\s*(</\2>)', troca, partes[i])
            html = ''.join(partes)
            return html, n[0], k + trocas[0]
        if fonte.startswith('app.py:'):
            const = fonte.split(':', 1)[1]
            s = app_py.read_text(encoding='utf-8')
            a = s.index(f'{const} = """'); b = s.index('\n"""', a + 20)
            novo, n, k = tratar(s[a:b])
            app_py.write_text(s[:a] + novo + s[b:], encoding='utf-8')
        else:
            p = RAIZ / fonte
            novo, n, k = tratar(p.read_text(encoding='utf-8'))
            p.write_text(novo, encoding='utf-8')
        if n or k:
            print(f'emojis {modo:14} {fonte:44} textos {n} | ícones {k}')


# ------------------------------------------------------------- temas ---
# Páginas feitas à mão sobre os componentes lt-* (não passam pelo migrar()):
# ganham só a classe tema-X no body e o CSS do tema no fim do <head>, que se
# soma ao estilo da própria página. "tema-" não casa com body[class*="modo-"],
# então a base neutra do app.css não mexe nos .card e campos delas.
TEMAS = [
    ('app.py:VERTO_HTML', 'player'),
    ('InstaSaver/instasaver.html', 'stories'),
    ('VscoSaver/vscosaver.html', 'filme'),
    ('WhatsSaver/whatssaver.html', 'conversa'),
    ('Conversor/conversor.html', 'planta'),
    ('Efeitos/efeitos.html', 'laboratorio'),
    ('Vetor3D/vetor3d.html', 'maquete'),
    ('Automacoes/automacoes.html', 'fluxo'),
    ('Automacoes/organizador.html', 'fluxo'),
    ('Automacoes/editor.html', 'timeline'),
    ('templates/instructions.html', 'manual'),
]


# ferramentas do PDFs (modo papel, migradas antes por outro script); só passam pelo --emojis
PDFS = ['app.py:PDFS_MERGE_HTML'] + [f'PDFs/pdfs_{n}.html' for n in (
    'split_new', 'convert_final', 'edit', 'compress', 'rotate', 'protect', 'unlock', 'watermark', 'compare', 'repair', 'corrupt')]


def temas():
    app_py = RAIZ / 'app.py'
    for fonte, tema in TEMAS:
        def tratar(html):
            if f'tema-{tema}' in html:
                return html, 'já aplicado'
            html, a = re.subn(r'<body class="lt-body">', f'<body class="lt-body tema-{tema}">', html, count=1)
            html, b = re.subn(r'</head>', f'  <link rel="stylesheet" href="/static/localtools/modos/tema-{tema}.css">\n</head>', html, count=1)
            return html, f'body {a} | css {b}'
        if fonte.startswith('app.py:'):
            const = fonte.split(':', 1)[1]
            s = app_py.read_text(encoding='utf-8')
            a = s.index(f'{const} = """'); b = s.index('\n"""', a + 20)
            novo, log = tratar(s[a:b])
            app_py.write_text(s[:a] + novo + s[b:], encoding='utf-8')
        else:
            p = RAIZ / fonte
            novo, log = tratar(p.read_text(encoding='utf-8'))
            p.write_text(novo, encoding='utf-8')
        print(f'tema {tema:12} {fonte:32} {log}')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--cores' in sys.argv:
        cores(set(args))
    elif '--temas' in sys.argv:
        temas()
    elif '--emojis' in sys.argv:
        emojis(set(args))
    else:
        main(set(args))
