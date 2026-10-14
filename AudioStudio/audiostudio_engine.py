"""Áudio Studio · fachada do app (o que as rotas do Flask chamam).

Módulos: as_fila (modo fila), as_midia (preparar, picos, janelas), as_projeto
(lista de edição), as_edicao (cortar/encurtar/recortar), as_analise
(sugestões), as_transcrever (Whisper em blocos), as_efeitos (catálogo),
as_render (mixagem e exportação), as_receitas (receitas e Demucs).
"""
import os
import re
import tempfile
import time

from AudioStudio import as_fila as F
from AudioStudio import as_midia as M
from AudioStudio import as_projeto as P
from AudioStudio import as_efeitos as E
from AudioStudio import as_edicao as ED
from AudioStudio import as_receitas as RC
from AudioStudio import as_tarefas

ProjetoError = P.ProjetoError
MidiaError = M.MidiaError
FilaError = F.FilaError
MAX_UPLOAD = 4 * 1024 ** 3     # 4 GB por arquivo (vídeos longos)


def iniciar():
    as_tarefas.registrar()


# ------------------------------------------------------------- importar ---

def importar_uploads(pid, arquivos, pista=None, nova=False, tipo='voz'):
    if not arquivos:
        raise ProjetoError('Escolha um arquivo de áudio ou vídeo.')
    out = []
    for i, arq in enumerate(arquivos[:20]):
        nome = os.path.basename(arq.filename or 'audio')
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, re.sub(r'[^\w.\- ]', '_', nome) or 'audio')
            arq.save(caminho)
            if os.path.getsize(caminho) > MAX_UPLOAD:
                raise ProjetoError('Arquivo grande demais (máximo 4 GB).')
            out.append(P.importar(pid, caminho, nome, pista_id=pista if i == 0 else None,
                                  nova=nova or i > 0 and bool(pista), tipo=tipo))
    return out


def novo_com_arquivo(arquivo, nome=None, tipo='voz', marcadores=None):
    """Projeto novo com um arquivo (gravação do Smart Studio, lote). Os marcadores
    da gravação ({t, nome} em JSON) viram marcadores do projeto."""
    import json
    if arquivo is None:
        raise ProjetoError('Nenhum arquivo enviado.')
    pr = P.criar(nome or os.path.splitext(os.path.basename(arquivo.filename or 'Gravação'))[0])
    importar_uploads(pr['id'], [arquivo], tipo=tipo)
    if marcadores:
        try:
            lista = json.loads(marcadores)
        except ValueError:
            lista = []
        proj = P.ler(pr['id'])
        proj['marcadores'] = [{'id': P._id(), 't': max(0.0, float(m.get('t') or 0)), 'nome': str(m.get('nome') or '')[:60]}
                              for m in lista[:500] if isinstance(m, dict)]
        P._gravar(pr['id'], proj)
    return pr['id']


def novo_do_suno(clip_id):
    from SunoSaver import sunosaver_engine as S
    m = S.musica(clip_id)
    caminho, nome, _ = S.gerar(m, 'm4a')
    pr = P.criar(f"{m['titulo']}")
    P.importar(pr['id'], caminho, nome, tipo='musica')
    proj = P.ler(pr['id'])
    proj['pistas'][0]['nome'] = 'Música'
    proj['pistas'][0]['tipo'] = 'musica'
    proj['tags'] = {'titulo': m['titulo'], 'artista': m['autor'], 'comentario': m['link']}
    P._gravar(pr['id'], proj)
    return pr['id']


def lote(arquivos, receita, exportar):
    """Uma receita em vários arquivos: um projeto para cada, receita e exportação na fila."""
    if receita not in RC.RECEITAS:
        raise ProjetoError('Escolha uma receita.')
    ids = []
    for arq in arquivos[:50]:
        pid = novo_com_arquivo(arq, tipo='musica' if RC.RECEITAS[receita].get('trecho') else 'voz')
        RC.enfileirar(pid, receita)
        op = dict(RC.RECEITAS[receita].get('exportar') or {})
        op.update({k: v for k, v in (exportar or {}).items() if v not in (None, '')})
        op.setdefault('formato', 'mp3')
        F.adicionar('exportar', pid, op, f'Exportar ({op["formato"].upper()})', unica=False)
        ids.append(pid)
    return ids


# --------------------------------------------------------------- fila ---

def fila():
    nomes = {}
    out = []
    for t in F.listar():
        if t['projeto'] not in nomes:
            try:
                nomes[t['projeto']] = P.ler(t['projeto'])['nome']
            except Exception:  # noqa: BLE001 - projeto apagado
                nomes[t['projeto']] = '(projeto apagado)'
        t['projeto_nome'] = nomes[t['projeto']]
        out.append(t)
    return out


# --------------------------------------------------------- transcrição ---

def transcricao_projeto(pid):
    """Palavras de cada fonte (tempo da fonte) para o painel de texto."""
    proj = P.ler(pid)
    out = {}
    for fid in {c['fonte'] for p in proj['pistas'] for c in p['clipes']}:
        tr = P.ler_transcricao(pid, fid)
        if tr:
            out[fid] = {'idioma': tr.get('idioma'), 'palavras': tr['palavras']}
    return out


def _palavras_no_tempo(pid):
    """Palavras que continuam no projeto, já no tempo da linha do tempo."""
    proj = P.ler(pid)
    out = []
    for pista in proj['pistas']:
        if pista.get('mudo'):
            continue
        for c in pista['clipes']:
            tr = P.ler_transcricao(pid, c['fonte'])
            if not tr:
                continue
            for w in tr['palavras']:
                meio = (w['ini'] + w['fim']) / 2
                if c['ini'] <= meio < c['ini'] + c['dur']:
                    d = c['pos'] - c['ini']
                    out.append({'w': w['w'], 'ini': max(c['pos'], w['ini'] + d), 'fim': min(c['pos'] + c['dur'], w['fim'] + d)})
    out.sort(key=lambda w: w['ini'])
    return out


def _ts(t, sep=','):
    h, r = divmod(max(0.0, t), 3600)
    m, s = divmod(r, 60)
    return f'{int(h):02d}:{int(m):02d}:{s:06.3f}'.replace('.', sep)


def transcricao_texto(pid, formato):
    palavras = _palavras_no_tempo(pid)
    if not palavras:
        raise ProjetoError('Transcreva o áudio primeiro (aba Texto).')
    if formato == 'txt':
        linhas, atual = [], []
        for i, w in enumerate(palavras):
            atual.append(w['w'])
            prox = palavras[i + 1] if i + 1 < len(palavras) else None
            if prox is None or prox['ini'] - w['fim'] > 1.2:
                linhas.append(' '.join(atual))
                atual = []
        return '\n\n'.join(linhas) + '\n'
    # legendas: até 42 caracteres por linha, 2 linhas, 6 s, quebra em pausa ou pontuação
    cues, atual = [], []
    for i, w in enumerate(palavras):
        atual.append(w)
        texto = ' '.join(x['w'] for x in atual)
        prox = palavras[i + 1] if i + 1 < len(palavras) else None
        if prox is None or len(texto) > 70 or atual[-1]['fim'] - atual[0]['ini'] > 6 or prox['ini'] - w['fim'] > 0.7 \
                or re.search(r'[.!?]$', w['w']):
            cues.append((atual[0]['ini'], atual[-1]['fim'], texto))
            atual = []
    def quebra(t):
        if len(t) <= 42:
            return t
        meio = len(t) // 2
        i = t.rfind(' ', 0, meio + 8)
        return t[:i] + '\n' + t[i + 1:] if i > 0 else t
    if formato == 'srt':
        return '\n'.join(f'{n}\n{_ts(a)} --> {_ts(max(b, a + 0.6))}\n{quebra(t)}\n' for n, (a, b, t) in enumerate(cues, 1))
    return 'WEBVTT\n\n' + '\n'.join(f"{_ts(a, '.')} --> {_ts(max(b, a + 0.6), '.')}\n{quebra(t)}\n" for a, b, t in cues)


def caminho_exportado(pid, arquivo):
    if not re.fullmatch(r'[\w\-. ()\[\],&\'!+@#À-ÿ]+', arquivo or '') or '..' in arquivo:
        raise ProjetoError('Arquivo inválido.')
    c = os.path.join(P.pasta(pid), 'exportados', arquivo)
    if not os.path.isfile(c):
        raise ProjetoError('Arquivo não encontrado (pode ter sido apagado).')
    return c, arquivo.split('__', 1)[-1]


def salvar_capa(pid, arquivo):
    from PIL import Image
    try:
        im = Image.open(arquivo.stream).convert('RGB')
    except Exception:
        raise ProjetoError('Não consegui abrir essa imagem.')
    im.thumbnail((1400, 1400))
    im.save(os.path.join(P.pasta(pid), 'capa.jpg'), 'JPEG', quality=90)
    return True


def tem_capa(pid):
    return os.path.exists(os.path.join(P.pasta(pid), 'capa.jpg'))
