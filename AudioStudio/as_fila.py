"""Áudio Studio · fila de tarefas em blocos (o "modo fila").

Tudo que demora passa por aqui: preparar um arquivo (prévia, picos, áudio de
análise), transcrever, analisar, separar voz, aplicar receita e exportar.
Uma tarefa por vez, na ordem; cada tarefa anda em blocos (~10 min de áudio)
e o estado vai para o disco depois de cada bloco, então:
- pausar e cancelar valem no fim do bloco atual (cancelar também encerra o
  processo que estiver rodando);
- se o Verto fechar, a tarefa volta do bloco em que parou;
- o tempo estimado sai da média por bloco.

Etapas pesadas (Whisper, Demucs) rodam num processo à parte com teto rígido
de memória (systemd-run), como a fila de IA do Vetor3D: se passar do teto, só
o processo é encerrado e o PC continua livre.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dados')
ESTADO = os.path.join(DADOS, 'fila.json')
BLOCO_S = 600          # 10 min de áudio por bloco
SOBRA_S = 2            # sobreposição entre blocos (palavra cortada ao meio)
MARGEM_MB = 450        # o que fica livre para o sistema, o navegador e o servidor


class Cancelada(Exception):
    pass


class FilaError(Exception):
    pass


_trabalhos = {}        # tipo -> função(tarefa, ctx)
_lock = threading.RLock()
_tarefas = []
_acordar = threading.Event()
_thread = None
_proc = {'p': None}


def registrar(tipo, funcao):
    _trabalhos[tipo] = funcao


def _salvar():
    os.makedirs(DADOS, exist_ok=True)
    with open(ESTADO + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(_tarefas, f, ensure_ascii=False)
    os.replace(ESTADO + '.tmp', ESTADO)


def _carregar():
    global _tarefas
    try:
        with open(ESTADO, encoding='utf-8') as f:
            _tarefas = json.load(f)
    except (OSError, ValueError):
        _tarefas = []
    for t in _tarefas:
        if t['estado'] == 'rodando':
            t['estado'] = 'esperando'      # o Verto fechou no meio: continua do bloco salvo
            t['etapa'] = 'Retomando de onde parou'


def iniciar():
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return
        _carregar()
        _thread = threading.Thread(target=_laco, name='audiostudio-fila', daemon=True)
        _thread.start()


def adicionar(tipo, projeto, args=None, titulo='', unica=True):
    """Põe uma tarefa no fim da fila. `unica`: não duplica a mesma tarefa pendente."""
    iniciar()
    with _lock:
        if unica:
            for t in _tarefas:
                if t['tipo'] == tipo and t['projeto'] == projeto and t['estado'] in ('esperando', 'rodando', 'pausada') \
                        and t.get('args') == (args or {}):
                    return t
        t = {'id': uuid.uuid4().hex[:10], 'tipo': tipo, 'projeto': projeto, 'args': args or {}, 'titulo': titulo or tipo,
             'estado': 'esperando', 'etapa': 'Na fila', 'progresso': 0.0, 'blocos': 0, 'feitos': 0, 'dados': {},
             'criada': time.time(), 'inicio': None, 'fim': None, 'erro': None, 'seg_bloco': None,
             'pausar': False, 'cancelar': False, 'resultado': None}
        _tarefas.append(t)
        _salvar()
    _acordar.set()
    return t


def listar(projeto=None):
    with _lock:
        ts = [dict(t) for t in _tarefas if projeto is None or t['projeto'] == projeto]
    pendentes = 0.0
    for t in ts:   # tempo estimado: o que falta desta + o das que estão antes
        resto = None
        if t['seg_bloco'] and t['blocos']:
            resto = t['seg_bloco'] * max(0, t['blocos'] - t['feitos'])
        if t['estado'] in ('esperando', 'rodando'):
            t['eta'] = round(pendentes + (resto or 0)) if resto is not None else None
            pendentes += resto or 0
        else:
            t['eta'] = None
        t.pop('pausar', None)
        t.pop('cancelar', None)
    return ts


def tarefa(tid):
    with _lock:
        for t in _tarefas:
            if t['id'] == tid:
                return t
    raise FilaError('Tarefa não encontrada.')


def acao(tid, qual):
    with _lock:
        t = tarefa(tid)
        if qual == 'pausar' and t['estado'] in ('esperando', 'rodando'):
            if t['estado'] == 'esperando':
                t['estado'], t['etapa'] = 'pausada', 'Pausada'
            else:
                t['pausar'] = True
                t['etapa'] = 'Pausa no fim deste bloco…'
        elif qual == 'retomar' and t['estado'] in ('pausada', 'erro', 'cancelada'):
            t.update(estado='esperando', etapa='Na fila', pausar=False, cancelar=False, erro=None)
        elif qual == 'cancelar' and t['estado'] in ('esperando', 'rodando', 'pausada'):
            if t['estado'] == 'rodando':
                t['cancelar'] = True
                p = _proc['p']
                if p and p.poll() is None:
                    p.kill()
            else:
                t['estado'], t['etapa'] = 'cancelada', 'Cancelada'
        elif qual in ('subir', 'descer'):
            i = _tarefas.index(t)
            j = i - 1 if qual == 'subir' else i + 1
            if 0 <= j < len(_tarefas):
                _tarefas[i], _tarefas[j] = _tarefas[j], _tarefas[i]
        elif qual == 'remover' and t['estado'] not in ('rodando',):
            _tarefas.remove(t)
        _salvar()
    _acordar.set()
    return listar()


def limpar_prontas():
    with _lock:
        _tarefas[:] = [t for t in _tarefas if t['estado'] not in ('pronta', 'cancelada')]
        _salvar()
    return listar()


def remover_do_projeto(projeto):
    with _lock:
        for t in _tarefas:
            if t['projeto'] == projeto and t['estado'] == 'rodando':
                t['cancelar'] = True
                p = _proc['p']
                if p and p.poll() is None:
                    p.kill()
        _tarefas[:] = [t for t in _tarefas if t['projeto'] != projeto or t['estado'] == 'rodando']
        _salvar()


class Contexto:
    """O que uma tarefa usa para andar: blocos, progresso, pausa e processos."""

    def __init__(self, t):
        self.t = t

    def etapa(self, texto, progresso=None):
        with _lock:
            self.t['etapa'] = texto
            if progresso is not None:
                self.t['progresso'] = max(0.0, min(1.0, progresso))

    def blocos(self, total):
        with _lock:
            self.t['blocos'] = int(total)
            _salvar()

    def bloco_feito(self, guardar=None, seg=None):
        """Marca um bloco pronto, salva o estado e respeita pausa/cancelamento."""
        with _lock:
            self.t['feitos'] += 1
            if guardar:
                self.t['dados'].update(guardar)
            if seg is not None:
                n = self.t['feitos']
                media = self.t['seg_bloco']
                self.t['seg_bloco'] = seg if media is None else (media * (n - 1) + seg) / n
            if self.t['blocos']:
                self.t['progresso'] = self.t['feitos'] / self.t['blocos']
            _salvar()
        self.checar()

    def checar(self):
        if self.t.get('cancelar'):
            raise Cancelada()
        if self.t.get('pausar'):
            raise _Pausa()

    def rodar(self, cmd, teto_mb=None, ao_ler=None, timeout=None):
        """Roda um processo (com teto de memória se pedido) e devolve a saída."""
        env = os.environ.copy()
        env['PYTHONPATH'] = RAIZ + os.pathsep + env.get('PYTHONPATH', '')
        env['TORCHAUDIO_BACKEND'] = 'soundfile'
        p = subprocess.Popen(prefixo(teto_mb) + cmd, cwd=RAIZ, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
        _proc['p'] = p
        linhas = []
        inicio = time.time()
        try:
            for linha in p.stdout:
                linha = linha.rstrip()
                linhas = (linhas + [linha])[-30:]
                if ao_ler:
                    ao_ler(linha)
                if timeout and time.time() - inicio > timeout:
                    p.kill()
            p.wait()
        finally:
            _proc['p'] = None
        if self.t.get('cancelar'):
            raise Cancelada()
        if p.returncode in (-9, 137):
            raise MemoryError()
        if p.returncode != 0:
            raise FilaError(next((l for l in reversed(linhas) if l.strip()), f'código {p.returncode}'))
        return linhas


class _Pausa(Exception):
    pass


_cgroup = {'ok': None}


def prefixo(teto_mb):
    if not teto_mb:
        return ['nice', '-n', '10'] if shutil.which('nice') else []
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
    return ['systemd-run', '--user', '--scope', '-q', '-p', f'MemoryMax={int(teto_mb)}M',
            '-p', f'MemoryHigh={int(teto_mb * 0.9)}M', '-p', 'MemorySwapMax=0',
            '-p', 'CPUWeight=20', '-p', 'IOWeight=20', '--']


def ram_livre_mb():
    try:
        import psutil
        return psutil.virtual_memory().available / 2**20
    except ImportError:
        return 1e9


def _proxima():
    with _lock:
        for t in _tarefas:
            if t['estado'] == 'esperando':
                return t
    return None


def _laco():
    while True:
        t = _proxima()
        if t is None:
            _acordar.wait(5)
            _acordar.clear()
            continue
        funcao = _trabalhos.get(t['tipo'])
        with _lock:
            t.update(estado='rodando', inicio=t['inicio'] or time.time(), erro=None, pausar=False)
            if t['etapa'] in ('Na fila', 'Retomando de onde parou'):
                t['etapa'] = 'Começando'
            _salvar()
        try:
            if funcao is None:
                raise FilaError(f'Tipo de tarefa desconhecido: {t["tipo"]}')
            resultado = funcao(t, Contexto(t))
            with _lock:
                t.update(estado='pronta', etapa='Pronta', progresso=1.0, fim=time.time(), resultado=resultado)
        except _Pausa:
            with _lock:
                t.update(estado='pausada', etapa='Pausada', pausar=False)
        except Cancelada:
            with _lock:
                t.update(estado='cancelada', etapa='Cancelada', cancelar=False, fim=time.time())
        except MemoryError:
            with _lock:
                t.update(estado='erro', etapa='Erro', erro='Faltou memória. Feche programas pesados e clique em Retomar.')
        except Exception as e:  # noqa: BLE001 - a mensagem vai para a tela
            with _lock:
                t.update(estado='erro', etapa='Erro', erro=str(e) or e.__class__.__name__)
        with _lock:
            _salvar()
