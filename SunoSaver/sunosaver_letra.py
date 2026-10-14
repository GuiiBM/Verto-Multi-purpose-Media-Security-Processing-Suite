"""SunoSaver · letra sincronizada (LRC, SRT, VTT) feita na própria máquina.

O Suno já dá a letra exata; falta só o tempo de cada linha. Sem login, a
letra sincronizada oficial não vem, então:
1. (modo "preciso") o Demucs isola a voz, porque o reconhecimento erra muito
   com a música por baixo;
2. o faster-whisper marca o tempo de cada palavra que ouviu;
3. as palavras ouvidas são alinhadas à letra conhecida (mesma ordem) e as que
   ele não ouviu ganham o tempo por interpolação entre as vizinhas.

Cada etapa pesada roda num processo próprio, um por vez, com teto rígido de
memória (systemd-run, como a fila de IA do Vetor3D) e prioridade baixa: se
passar do teto, só a etapa é encerrada e o PC não trava. O resultado fica em
SunoSaver/dados/letras/<id>.json e serve para os três formatos.
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dados', 'letras')
TETO_DEMUCS_MB = 1900      # em pedaços de 45 s o pico medido foi ~1,5 GB (a música inteira passa de 1,7 GB)
PEDACO_S = 45
TETO_WHISPER_MB = 2200
MODELO_WHISPER = 'small'
# Quanto cada etapa precisa de RAM livre para começar (medido nesta máquina)
# e o que fica para o sistema, o navegador e o servidor.
PRECISA_MB = {'demucs': 1600, 'small': 1300, 'base': 700}
MARGEM_MB = 450


class LetraError(Exception):
    pass


# ------------------------------------------------------------ processos ---

_cgroup = {'ok': None}


def _prefixo(teto_mb):
    if _cgroup['ok'] is None:
        ok = False
        if sys.platform.startswith('linux') and shutil.which('systemd-run'):
            try:
                ok = subprocess.run(['systemd-run', '--user', '--scope', '-q', '-p', 'MemoryMax=64M', 'true'],
                                    capture_output=True, timeout=10).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                ok = False
        _cgroup['ok'] = ok
    if not _cgroup['ok']:
        return ['nice', '-n', '15'] if shutil.which('nice') else []
    return ['systemd-run', '--user', '--scope', '-q', '-p', f'MemoryMax={teto_mb}M',
            '-p', f'MemoryHigh={int(teto_mb * 0.9)}M', '-p', 'MemorySwapMax=0',
            '-p', 'CPUWeight=20', '-p', 'IOWeight=20', '--']


def _livre_mb():
    try:
        import psutil
        return psutil.virtual_memory().available / 2**20
    except ImportError:
        return 1e9


def _teto(etapa, maximo):
    return int(max(PRECISA_MB[etapa], min(maximo, _livre_mb() - MARGEM_MB)))


def _rodar(cmd, teto_mb, ao_ler=None):
    env = os.environ.copy()
    env['TORCHAUDIO_BACKEND'] = 'soundfile'
    env['PYTHONPATH'] = RAIZ + os.pathsep + env.get('PYTHONPATH', '')
    p = subprocess.Popen(_prefixo(teto_mb) + cmd, cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1)
    _trabalho['proc'] = p
    ultimas = []
    buf = ''
    while True:
        c = p.stdout.read(1)
        if not c:
            break
        if c in '\r\n':
            if buf.strip():
                ultimas = (ultimas + [buf.strip()])[-12:]
                if ao_ler:
                    ao_ler(buf.strip())
            buf = ''
        else:
            buf += c
    p.wait()
    _trabalho['proc'] = None
    if _trabalho.get('cancelar'):
        raise LetraError('Cancelado.')
    if p.returncode in (-9, 137) or (p.returncode and any('Killed' in u or 'MemoryError' in u for u in ultimas)):
        raise MemoryError()
    if p.returncode != 0:
        raise LetraError('Falhou: ' + (ultimas[-1] if ultimas else f'código {p.returncode}'))


# -------------------------------------------------------------- trabalho ---

_trabalho = {'id': None, 'estado': 'livre', 'etapa': '', 'progresso': 0.0, 'erro': None,
             'proc': None, 'cancelar': False, 'inicio': None}
_lock = threading.Lock()


def _caminho(clip_id):
    return os.path.join(DADOS, f'{clip_id}.json')


def pronta(clip_id):
    return os.path.exists(_caminho(clip_id))


def carregar(clip_id):
    try:
        with open(_caminho(clip_id), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def estado(clip_id=None):
    t = {k: v for k, v in _trabalho.items() if k not in ('proc', 'cancelar')}
    t['decorrido'] = round(time.time() - t['inicio'], 1) if t['inicio'] and t['estado'] == 'rodando' else None
    if clip_id:
        s = carregar(clip_id)
        t['pronta'] = bool(s)
        if s:
            t['resumo'] = {'cobertura': s.get('cobertura'), 'modo': s.get('modo'), 'aviso': s.get('aviso'),
                           'linhas': len(s.get('linhas', []))}
    return t


def cancelar():
    _trabalho['cancelar'] = True
    p = _trabalho.get('proc')
    if p and p.poll() is None:
        p.kill()
    return estado()


def iniciar(m, video, modo='rapido'):
    if not m.get('letra') or m.get('instrumental'):
        raise LetraError('Esta música não tem letra para sincronizar.')
    with _lock:
        if _trabalho['estado'] == 'rodando':
            if _trabalho['id'] == m['id']:
                return estado(m['id'])
            raise LetraError('Já estou sincronizando outra música. Espere terminar (uma por vez, para não pesar no PC).')
        _trabalho.update(id=m['id'], estado='rodando', etapa='Preparando', progresso=0.0, erro=None,
                         cancelar=False, inicio=time.time())
    threading.Thread(target=_executar, args=(m, video, modo), daemon=True).start()
    return estado(m['id'])


def _executar(m, video, modo):
    pasta = os.path.dirname(video)
    try:
        audio = os.path.join(pasta, 'audio.wav')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', video, '-vn',
                        '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', audio], check=True, timeout=300)
        voz, aviso = audio, None
        if modo == 'preciso':
            if _livre_mb() - MARGEM_MB < PRECISA_MB['demucs']:
                modo, aviso = 'rapido', 'Pouca memória livre para separar a voz: usei a música inteira (menos preciso).'
            else:
                try:
                    voz = _isolar_voz(audio, pasta)
                except MemoryError:
                    modo, aviso = 'rapido', 'Faltou memória para separar a voz: usei a música inteira (menos preciso).'
        palavras = _transcrever(voz, pasta, m['letra'])
        resultado = alinhar(m['letra'], palavras)
        resultado.update(modo=modo, aviso=aviso, id=m['id'], titulo=m['titulo'], autor=m['autor'],
                         duracao=m.get('duracao'), criado=time.strftime('%Y-%m-%d %H:%M'))
        os.makedirs(DADOS, exist_ok=True)
        with open(_caminho(m['id']), 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=1)
        _trabalho.update(estado='pronto', etapa='Pronto', progresso=1.0)
    except MemoryError:
        _trabalho.update(estado='erro', erro='Faltou memória para reconhecer a voz. Feche programas pesados e tente de novo.')
    except LetraError as e:
        _trabalho.update(estado='erro' if str(e) != 'Cancelado.' else 'livre', erro=str(e))
    except Exception as e:  # noqa: BLE001 - a mensagem vai para a tela
        _trabalho.update(estado='erro', erro=f'Erro inesperado: {e}')


def _isolar_voz(audio, pasta):
    """Demucs em pedaços de 45 s, todos no mesmo processo (o modelo carrega uma
    vez): a música inteira de uma vez passa de 1,7 GB; em pedaços fica ~1,5 GB."""
    _trabalho.update(etapa='Separando a voz da música', progresso=0.02)
    pedacos = os.path.join(pasta, 'pedacos')
    saida = os.path.join(pasta, 'demucs')
    shutil.rmtree(pedacos, ignore_errors=True)
    shutil.rmtree(saida, ignore_errors=True)
    os.makedirs(pedacos)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', audio, '-f', 'segment',
                    '-segment_time', str(PEDACO_S), '-c', 'copy', os.path.join(pedacos, 'p%03d.wav')],
                   check=True, timeout=120)
    nomes = sorted(os.listdir(pedacos))
    feitos = {'n': 0}

    def ler(linha):
        if linha.startswith('Separating track'):
            feitos['n'] += 1
        m = re.search(r'(\d{1,3})%\|', linha)
        frac = int(m.group(1)) / 100 if m else 0
        _trabalho['progresso'] = 0.02 + 0.48 * (max(0, feitos['n'] - 1) + frac) / len(nomes)

    _rodar([sys.executable, '-m', 'demucs', '--two-stems', 'vocals', '--mp3', '-o', saida,
            *[os.path.join(pedacos, n) for n in nomes]], _teto('demucs', TETO_DEMUCS_MB), ler)
    vozes = [os.path.join(saida, 'htdemucs', os.path.splitext(n)[0], 'vocals.mp3') for n in nomes]
    if not all(os.path.exists(v) for v in vozes):
        raise LetraError('O Demucs não gerou a voz isolada.')
    lista = os.path.join(pasta, 'vozes.txt')
    with open(lista, 'w', encoding='utf-8') as f:
        f.writelines(f"file '{v}'\n" for v in vozes)
    voz = os.path.join(pasta, 'voz.wav')
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0',
                    '-i', lista, '-ac', '1', '-ar', '16000', voz], check=True, timeout=120)
    shutil.rmtree(pedacos, ignore_errors=True)
    return voz


def _transcrever(audio, pasta, letra):
    _trabalho.update(etapa='Marcando o tempo de cada palavra',
                     progresso=max(_trabalho['progresso'], 0.5 if audio.endswith('voz.wav') else 0.05))
    inicio = _trabalho['progresso']
    saida = os.path.join(pasta, 'palavras.json')
    letra_path = os.path.join(pasta, 'letra.txt')
    with open(letra_path, 'w', encoding='utf-8') as f:
        f.write(letra)

    def ler(linha):
        if linha.startswith('PROGRESSO '):
            try:
                _trabalho['progresso'] = inicio + (0.98 - inicio) * float(linha.split()[1])
            except ValueError:
                pass

    livre = _livre_mb() - MARGEM_MB
    modelo = MODELO_WHISPER if livre >= PRECISA_MB[MODELO_WHISPER] else 'base'
    if livre < PRECISA_MB['base']:
        raise LetraError('Pouca memória livre agora para reconhecer a voz. Feche algumas abas ou programas e tente de novo.')
    _rodar([sys.executable, '-m', 'SunoSaver.sunosaver_letra', 'transcrever', audio, saida, modelo, letra_path],
           _teto(modelo, TETO_WHISPER_MB), ler)
    with open(saida, encoding='utf-8') as f:
        return json.load(f)


def _worker_transcrever(audio, saida, modelo, letra_path=None):
    """Roda dentro do processo com teto: decodifica e chama o faster-whisper.

    Diferente da transcrição de vídeos (Automacoes/reels/transcricao.py), aqui
    o filtro de voz (VAD) e o descarte de "silêncio" ficam desligados: em
    música eles jogam fora o canto suave sobre o instrumento. Palavras
    inventadas nos trechos instrumentais não atrapalham, porque o alinhamento
    só aproveita o que bate com a letra. A própria letra entra como contexto.
    """
    import numpy as np
    from Automacoes.reels import transcricao
    raw = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', audio, '-ac', '1', '-ar', '16000',
                          '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    sinal = np.frombuffer(raw, dtype=np.float32)
    contexto = None
    if letra_path:
        with open(letra_path, encoding='utf-8') as f:
            contexto = ' '.join(ln['texto'] for ln in _linhas(f.read()))[:600] or None
    m = transcricao._modelo(modelo)
    duracao = len(sinal) / 16000 or 1
    segmentos, _ = m.transcribe(sinal, language=None, word_timestamps=True, vad_filter=False,
                                condition_on_previous_text=False, initial_prompt=contexto, beam_size=5)
    palavras = []
    for seg in segmentos:
        print(f'PROGRESSO {min(1.0, seg.end / duracao):.3f}', flush=True)
        for w in seg.words or []:
            t = w.word.strip()
            if t and w.end > w.start:
                palavras.append({'w': t, 'ini': round(float(w.start), 3), 'fim': round(float(w.end), 3),
                                 'p': round(float(w.probability), 3)})
    with open(saida, 'w', encoding='utf-8') as f:
        json.dump(palavras, f, ensure_ascii=False)


# ------------------------------------------------------------- alinhamento ---

def _norm(t):
    t = unicodedata.normalize('NFD', t.lower())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return re.sub(r"[^\w]", '', t)


CREDITO = re.compile(r'rights reserved|copyright|©|℗|produced by|lyrics by|written by|prod\.|all rights', re.I)


def _tem_texto(linha):
    """Tem letra de verdade (qualquer alfabeto)? Letras estilizadas do bloco
    matemático (𝙞𝙌𝙎…) são assinatura, não canto."""
    return any(unicodedata.category(c).startswith('L') and not 0x1D400 <= ord(c) <= 0x1D7FF for c in linha)


def _linhas(letra):
    """Letra do Suno -> linhas cantadas. [Verse], [Chorus]... viram seções.
    Antes do primeiro cabeçalho, linhas de crédito (direitos, produção, a
    assinatura do autor) não são cantadas e ficam de fora."""
    brutas = letra.split('\n')
    primeiro = next((i for i, b in enumerate(brutas) if re.fullmatch(r'\s*\[[^\]]*\]\s*', b)), None)
    if primeiro:
        brutas = [b for i, b in enumerate(brutas)
                  if i >= primeiro or not (CREDITO.search(b) or not _tem_texto(b))]
    linhas, secao = [], ''
    for bruta in brutas:
        s = bruta.strip()
        if not s:
            continue
        cab = re.fullmatch(r'\[([^\]]*)\]', s)
        if cab:
            secao = cab.group(1).strip()
            continue
        texto = re.sub(r'\[[^\]]*\]', '', s).strip()
        if not texto:
            continue
        palavras = [w for w in (_norm(x) for x in re.split(r"[\s\-–—/]+", texto)) if w]
        if palavras:
            linhas.append({'texto': texto, 'secao': secao, 'palavras': palavras})
    return linhas


def _parecido(a, b):
    if a == b:
        return True
    if len(a) < 3 or len(b) < 3:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


def alinhar(letra, ouvidas):
    linhas = _linhas(letra)
    if not linhas:
        raise LetraError('A letra desta música está vazia.')
    L = [(i, w) for i, ln in enumerate(linhas) for w in ln['palavras']]
    A = []
    for o in ouvidas:
        for w in re.split(r"[\s\-–—/]+", o['w']):
            n = _norm(w)
            if n:
                A.append({'w': n, 'ini': o['ini'], 'fim': o['fim']})
    if not A:
        raise LetraError('Não consegui ouvir a voz desta música para marcar o tempo.')

    # 1) trechos idênticos na mesma ordem; 2) dentro dos buracos, palavras parecidas
    par = [None] * len(L)
    sm = difflib.SequenceMatcher(None, [w for _, w in L], [a['w'] for a in A], autojunk=False)
    for bl in sm.get_matching_blocks():
        for k in range(bl.size):
            par[bl.a + k] = bl.b + k
    anc = [(i, j) for i, j in enumerate(par) if j is not None]
    limites = [(-1, -1)] + anc + [(len(L), len(A))]
    for (i0, j0), (i1, j1) in zip(limites, limites[1:]):
        j = j0 + 1
        for i in range(i0 + 1, i1):
            for jj in range(j, min(j1, j + 6)):
                if _parecido(L[i][1], A[jj]['w']):
                    par[i], j = jj, jj + 1
                    break

    casadas = sum(1 for p in par if p is not None)
    tempos = [None] * len(L)
    for i, j in enumerate(par):
        if j is not None:
            tempos[i] = [A[j]['ini'], A[j]['fim']]
    # interpolação das que não foram ouvidas, pelo tamanho da palavra
    conhecidos = [i for i, t in enumerate(tempos) if t]
    if not conhecidos:
        raise LetraError('A voz reconhecida não bate com a letra (a letra pode ser de outra versão).')
    for a, b in zip([None] + conhecidos, conhecidos + [None]):
        ini = a + 1 if a is not None else 0
        fim = b if b is not None else len(L)
        if ini >= fim:
            continue
        t0 = tempos[a][1] if a is not None else max(0.0, tempos[b][0] - 0.35 * (fim - ini))
        t1 = tempos[b][0] if b is not None else tempos[a][1] + 0.35 * (fim - ini)
        pesos = [len(L[k][1]) + 1 for k in range(ini, fim)]
        total, acc = sum(pesos), 0
        for k, peso in zip(range(ini, fim), pesos):
            s = t0 + (t1 - t0) * acc / total
            acc += peso
            tempos[k] = [s, t0 + (t1 - t0) * acc / total]

    saida, k = [], 0
    for ln in linhas:
        n = len(ln['palavras'])
        ts = tempos[k:k + n]
        palavras = [{'w': w, 'ini': round(t[0], 2), 'fim': round(t[1], 2)}
                    for w, t in zip(ln['texto'].split(), _distribuir(ln['texto'].split(), ts))]
        saida.append({'texto': ln['texto'], 'secao': ln['secao'], 'ini': round(ts[0][0], 2),
                      'fim': round(ts[-1][1], 2), 'palavras': palavras,
                      'ouvida': any(par[k + x] is not None for x in range(n))})
        k += n
    for a, b in zip(saida, saida[1:]):   # sem sobreposição e sempre em ordem
        if b['ini'] < a['ini']:
            b['ini'] = a['ini'] + 0.01
        a['fim'] = min(a['fim'], b['ini'])
    return {'linhas': saida, 'cobertura': round(100 * casadas / len(L))}


def _distribuir(textos, tempos):
    """As palavras do texto original (com pontuação) recebem os tempos das
    palavras normalizadas; quando a contagem difere, reparte o intervalo."""
    if len(textos) == len(tempos):
        return tempos
    t0, t1 = tempos[0][0], tempos[-1][1]
    passo = (t1 - t0) / max(1, len(textos))
    return [[t0 + passo * i, t0 + passo * (i + 1)] for i in range(len(textos))]


# --------------------------------------------------------------- exportar ---

def _ts(seg, sep=','):
    seg = max(0.0, seg)
    h, r = divmod(seg, 3600)
    mi, s = divmod(r, 60)
    return f'{int(h):02d}:{int(mi):02d}:{s:06.3f}'.replace('.', sep)


def _lrc_ts(seg):
    mi, s = divmod(max(0.0, seg), 60)
    return f'{int(mi):02d}:{s:05.2f}'


def texto(s, formato, palavra_a_palavra=False):
    linhas = s['linhas']
    if formato == 'lrc':
        dur = s.get('duracao') or 0
        out = [f"[ti:{s.get('titulo', '')}]", f"[ar:{s.get('autor', '')}]", '[re:SunoSaver]']
        if dur:
            out.append(f'[length:{_lrc_ts(dur)[:5]}]')
        for ln in linhas:
            if palavra_a_palavra:
                corpo = ' '.join(f"<{_lrc_ts(p['ini'])}>{p['w']}" for p in ln['palavras'])
            else:
                corpo = ln['texto']
            out.append(f"[{_lrc_ts(ln['ini'])}]{corpo}")
        return '\n'.join(out) + '\n'
    cues = []
    for i, ln in enumerate(linhas):
        fim = max(ln['fim'], ln['ini'] + 0.8)
        if i + 1 < len(linhas):
            fim = min(fim + 0.4, linhas[i + 1]['ini'])
        cues.append((ln['ini'], fim, ln['texto']))
    if formato == 'srt':
        return '\n'.join(f'{n}\n{_ts(a)} --> {_ts(b)}\n{t}\n' for n, (a, b, t) in enumerate(cues, 1))
    return 'WEBVTT\n\n' + '\n'.join(f"{_ts(a, '.')} --> {_ts(b, '.')}\n{t}\n" for a, b, t in cues)


def exportar(m, formato, saida, palavra_a_palavra=False):
    s = carregar(m['id'])
    if not s:
        raise LetraError('Sincronize a letra primeiro (botão "Sincronizar letra").')
    with open(saida, 'w', encoding='utf-8') as f:
        f.write(texto(s, formato, palavra_a_palavra))


if __name__ == '__main__':
    if len(sys.argv) in (5, 6) and sys.argv[1] == 'transcrever':
        _worker_transcrever(*sys.argv[2:])
    else:
        print('uso: python -m SunoSaver.sunosaver_letra transcrever <audio> <saida.json> <modelo>')
        sys.exit(2)
