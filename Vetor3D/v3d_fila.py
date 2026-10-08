"""Vetor3D · filas de espera e processos de trabalho.

Três filas:
- leve: leitura do arquivo, preview 3D, exportação e código (um processo,
  sempre pronto, para o preview responder rápido);
- pesada: alta definição (até N processos simultâneos, N pelo perfil de
  hardware; cada um ainda divide as peças entre vários núcleos);
- ia: personagem 3D (rede de reconstrução). Uma tarefa por vez, na ordem em
  que foram pedidas, cada uma num processo novo que termina no fim (a memória
  volta inteira para o sistema) e com um TETO RÍGIDO de memória (cgroup via
  systemd-run, no Linux): se a etapa passar do teto, só ela é encerrada,
  nunca o computador trava; a fila tenta de novo sozinha em modo de pouca
  memória (mesma qualidade, fatias menores, mais tempo).

Antes de começar uma etapa a fila estima a memória e só libera se couber
(senão a tarefa fica "aguardando memória" e tenta de novo sozinha). Tarefas
podem ser pausadas (o processo é congelado), retomadas, canceladas (o processo
é encerrado com os filhos) e reordenadas. Se o sistema matar um processo por
falta de memória, a tarefa vira erro com explicação e o processo renasce.
"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid

import shutil

import psutil

from Vetor3D import v3d_hardware as HW

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASSES = {'leitura': 'leve', 'preview': 'leve', 'exportar': 'leve', 'codigo': 'leve', 'hd': 'pesada'}
MARGEM_SISTEMA_MB = 700   # o que fica livre para o sistema, o navegador e o servidor
CRITICO_MB = 260          # abaixo disso de RAM livre o vigia encerra a etapa de IA
TENTATIVAS_IA = 3
PRIORIDADE = {'leitura': 0, 'preview': 1, 'codigo': 2, 'exportar': 2, 'hd': 5}
OCIOSO_MAX = 180          # s até um processo pesado parado ser encerrado (libera RAM)
GUARDAR_FINALIZADAS = 40


class Trabalhador:
    """Um processo `python -m Vetor3D.v3d_trabalho` e a thread que lê as
    respostas dele."""

    def __init__(self, fila, classe, log_path):
        self.fila = fila
        self.classe = classe
        self.prefixo = []           # ex.: systemd-run com teto de memória (fila de IA)
        self.limite_mb = None
        self.motivo = None          # por que o processo foi encerrado (vigia)
        self.log_path = log_path
        self.proc = None
        self.tarefa = None
        self.ocioso_desde = time.time()
        self.pronto = threading.Event()
        self._lock = threading.Lock()

    def vivo(self):
        return self.proc is not None and self.proc.poll() is None

    def garantir(self):
        with self._lock:
            if self.vivo():
                return
            self.pronto.clear()
            log = open(self.log_path, 'a', buffering=1, encoding='utf-8')
            env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', MALLOC_ARENA_MAX='2')
            self.proc = subprocess.Popen(
                list(self.prefixo) + [sys.executable, '-m', 'Vetor3D.v3d_trabalho'], cwd=RAIZ, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
                encoding='utf-8', bufsize=1)
            threading.Thread(target=self._ler, args=(self.proc,), daemon=True,
                             name=f'v3d-leitor-{self.classe}').start()

    def _ler(self, proc):
        for linha in proc.stdout:
            try:
                msg = json.loads(linha)
            except ValueError:
                continue
            if msg.get('t') == 'pronto':
                self.pronto.set()
                continue
            self.fila._mensagem(self, msg)
        # saiu do laço: o processo terminou
        self.fila._processo_morreu(self, proc)

    def enviar(self, tarefa):
        self.garantir()
        self.tarefa = tarefa
        cmd = {'id': tarefa['id'], 'func': tarefa['func'], 'args': tarefa['args']}
        try:
            self.proc.stdin.write(json.dumps(cmd, ensure_ascii=False) + '\n')
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self.fila._processo_morreu(self, self.proc)

    def arvore(self):
        if not self.vivo():
            return []
        try:
            p = psutil.Process(self.proc.pid)
            return [p] + p.children(recursive=True)
        except psutil.Error:
            return []

    def memoria_mb(self):
        """Memória própria (anônima) do processo e filhos. O RSS inclui arquivos
        mapeados (pesos da rede), que o sistema pode descartar a qualquer hora."""
        total = 0
        for p in self.arvore():
            try:
                with open(f'/proc/{p.pid}/status') as fh:
                    for linha in fh:
                        if linha.startswith('RssAnon:'):
                            total += int(linha.split()[1]) * 1024
                            break
            except (OSError, ValueError):
                try:
                    total += p.memory_info().rss
                except psutil.Error:
                    pass
        return total / HW.MB

    def uso_real(self):
        """Uso de verdade agora: memória própria (sem os pesos mapeados do disco),
        o que o teto do cgroup está contando, o limite e a CPU (% de um núcleo)."""
        procs = self.arvore()
        if not procs:
            return None
        cpu = 0.0
        vistos = getattr(self, '_ps', {})
        novos = {}
        for p in procs:
            q = vistos.get(p.pid) or p
            try:
                cpu += q.cpu_percent(None)
            except psutil.Error:
                pass
            novos[p.pid] = q
        self._ps = novos
        uso = {'mem_mb': round(self.memoria_mb()), 'cpu': round(cpu)}
        try:
            with open(f'/proc/{procs[-1].pid}/cgroup') as fh:
                caminho = fh.read().strip().split('\n')[-1].split(':', 2)[2]
            base = '/sys/fs/cgroup' + caminho
            with open(base + '/memory.current') as fh:
                uso['cgroup_mb'] = round(int(fh.read()) / HW.MB)
            with open(base + '/memory.max') as fh:
                v = fh.read().strip()
                uso['limite_mb'] = None if v == 'max' else round(int(v) / HW.MB)
        except (OSError, ValueError, IndexError):
            pass
        return uso

    def suspender(self, sim):
        for p in self.arvore():
            try:
                p.suspend() if sim else p.resume()
            except psutil.Error:
                pass

    def matar(self):
        procs = self.arvore()
        for p in reversed(procs):
            try:
                p.kill()
            except psutil.Error:
                pass
        if self.proc is not None:
            try:
                self.proc.wait(timeout=5)
            except Exception:
                pass

    def encerrar(self):
        if self.vivo():
            try:
                self.proc.stdin.write('{"func": "sair"}\n')
                self.proc.stdin.flush()
                self.proc.wait(timeout=3)
            except Exception:
                self.matar()


class Fila:
    def __init__(self, pasta):
        self.pasta = pasta
        os.makedirs(pasta, exist_ok=True)
        self.log = os.path.join(pasta, 'trabalho.log')
        self.tarefas = {}
        self.sequencia = 0
        self.lock = threading.RLock()
        self.leves = [Trabalhador(self, 'leve', self.log)]
        self.pesados = []
        self.ias = [Trabalhador(self, 'ia', self.log)]
        self._cgroup = None
        self.ao_terminar = {}       # tipo -> callback(tarefa)
        self.vazao = {}             # triângulos por segundo e por processo (medido)
        self._thread = None
        self._parar = threading.Event()
        self._evento = threading.Event()

    # ------------------------------------------------------------------ API
    def iniciar(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._laco, daemon=True, name='v3d-fila')
        self._thread.start()
        # aquece o processo leve (imports de numpy/shapely/trimesh) para o
        # primeiro preview sair rápido
        threading.Thread(target=self.leves[0].garantir, daemon=True).start()

    def adicionar(self, tipo, projeto, rotulo, func, args, estimativa_mb=200.0, triangulos=0, extra=None,
                  classe=None, previsto_s=None, minimo_mb=None):
        with self.lock:
            self.sequencia += 1
            tid = uuid.uuid4().hex[:12]
            t = {
                'id': tid, 'tipo': tipo, 'classe': classe or CLASSES[tipo], 'projeto': projeto, 'rotulo': rotulo,
                'previsto_s': previsto_s, 'minimo_mb': minimo_mb, 'tentativa': 1,
                'func': func, 'args': args, 'estado': 'fila', 'etapa': 'Na fila', 'progresso': 0.0,
                'etapas': [], 'criado': time.time(), 'inicio': None, 'fim': None, 'erro': None,
                'resultado': None, 'estimativa_mb': float(estimativa_mb), 'triangulos': int(triangulos),
                'ordem': self.sequencia, 'pausado': False, 'mensagem': None, 'eta': None,
                'extra': extra or {},
            }
            if 'workers' in args:
                t['workers'] = args['workers']
            self.tarefas[tid] = t
        self._acordar()
        return tid

    def obter(self, tid):
        with self.lock:
            t = self.tarefas.get(tid)
            return self._publica(t) if t else None

    def listar(self, projeto=None):
        with self.lock:
            ts = [t for t in self.tarefas.values() if projeto is None or t['projeto'] == projeto]
            ativas = [t for t in ts if t['estado'] in ('fila', 'aguardando_memoria', 'rodando', 'pausado')]
            fim = [t for t in ts if t not in ativas]
            ativas.sort(key=lambda t: (t['estado'] != 'rodando', self._chave(t)))
            fim.sort(key=lambda t: -(t['fim'] or 0))
            pos = 0
            saida = []
            uso = {id(w.tarefa): w for w in self._todos() if w.tarefa is not None}
            for t in ativas:
                pt = self._publica(t)
                w = uso.get(id(t))
                if w is not None and t['estado'] == 'rodando':
                    pt['uso_real'] = w.uso_real()
                if t['estado'] != 'rodando':
                    pos += 1
                    pt['posicao'] = pos
                saida.append(pt)
            return saida + [self._publica(t) for t in fim[:GUARDAR_FINALIZADAS]]

    def cancelar(self, tid):
        with self.lock:
            t = self.tarefas.get(tid)
            if not t or t['estado'] in ('pronto', 'erro', 'cancelado'):
                return False
            rodando = t['estado'] in ('rodando',) or (t['estado'] == 'pausado' and t.get('inicio'))
            t['estado'] = 'cancelado'
            t['etapa'] = 'Cancelado'
            t['fim'] = time.time()
            if rodando:
                for w in self._todos():
                    if w.tarefa is t:
                        w.tarefa = None
                        w.matar()
        self._acordar()
        return True

    def cancelar_projeto(self, projeto, tipos=None):
        with self.lock:
            ids = [t['id'] for t in self.tarefas.values() if t['projeto'] == projeto
                   and (tipos is None or t['tipo'] in tipos)
                   and t['estado'] in ('fila', 'aguardando_memoria', 'rodando', 'pausado')]
        for tid in ids:
            self.cancelar(tid)

    def pausar(self, tid, sim=True):
        with self.lock:
            t = self.tarefas.get(tid)
            if not t:
                return False
            if sim and t['estado'] in ('fila', 'aguardando_memoria'):
                t['pausado'] = True
                t['estado'] = 'pausado'
                t['etapa'] = 'Pausada na fila'
            elif sim and t['estado'] == 'rodando':
                for w in self._todos():
                    if w.tarefa is t:
                        w.suspender(True)
                t['pausado'] = True
                t['estado'] = 'pausado'
                t['pausa_inicio'] = time.time()
            elif not sim and t['estado'] == 'pausado':
                t['pausado'] = False
                if t.get('inicio'):
                    for w in self._todos():
                        if w.tarefa is t:
                            w.suspender(False)
                    t['estado'] = 'rodando'
                    if t.get('pausa_inicio'):
                        t['inicio'] += time.time() - t.pop('pausa_inicio')
                else:
                    t['estado'] = 'fila'
                    t['etapa'] = 'Na fila'
            else:
                return False
        self._acordar()
        return True

    def mover(self, tid, direcao):
        """Sobe (-1) ou desce (+1) uma tarefa entre as que esperam na mesma classe."""
        with self.lock:
            t = self.tarefas.get(tid)
            if not t or t['estado'] not in ('fila', 'aguardando_memoria', 'pausado') or t.get('inicio'):
                return False
            fila = sorted([x for x in self.tarefas.values() if x['classe'] == t['classe']
                           and x['estado'] in ('fila', 'aguardando_memoria', 'pausado') and not x.get('inicio')],
                          key=self._chave)
            i = fila.index(t)
            j = i + (1 if direcao > 0 else -1)
            if j < 0 or j >= len(fila) or (t['classe'] != 'ia' and PRIORIDADE[fila[j]['tipo']] != PRIORIDADE[t['tipo']]):
                return False
            t['ordem'], fila[j]['ordem'] = fila[j]['ordem'], t['ordem']
        return True

    def limpar(self, cancelar_pendentes=False):
        canceladas = 0
        if cancelar_pendentes:
            with self.lock:
                ids = [t['id'] for t in self.tarefas.values()
                       if t['estado'] in ('fila', 'aguardando_memoria', 'rodando', 'pausado')]
            for tid in ids:
                canceladas += bool(self.cancelar(tid))
        with self.lock:
            fim = [tid for tid, t in self.tarefas.items() if t['estado'] in ('pronto', 'erro', 'cancelado')]
            for tid in fim:
                self.tarefas.pop(tid, None)
        self._acordar()
        return {'removidas': len(fim), 'canceladas': canceladas}

    def forcar(self, tid):
        """Roda mesmo sem memória folgada (o usuário assume o risco)."""
        with self.lock:
            t = self.tarefas.get(tid)
            if not t or t['estado'] != 'aguardando_memoria':
                return False
            t['forcar'] = True
            t['estado'] = 'fila'
        self._acordar()
        return True

    def resumo(self):
        with self.lock:
            ativas = [t for t in self.tarefas.values() if t['estado'] in ('rodando', 'pausado')]
            espera = [t for t in self.tarefas.values() if t['estado'] in ('fila', 'aguardando_memoria')]
            mem = sum(w.memoria_mb() for w in self._todos() if w.vivo())
            return {
                'rodando': len([t for t in ativas if t['estado'] == 'rodando']),
                'pausadas': len([t for t in ativas if t['estado'] == 'pausado']),
                'esperando': len(espera),
                'processos': len([w for w in self._todos() if w.vivo()]),
                'teto_ia': bool(self._teto_disponivel()),
                'memoria_mb': round(mem),
            }

    def encerrar(self):
        self._parar.set()
        for w in self._todos():
            try:
                w.encerrar()
            except Exception:
                pass

    # ------------------------------------------------------------ internos
    def _todos(self):
        return self.leves + self.pesados + self.ias

    @staticmethod
    def _chave(t):
        # a fila de IA é estritamente na ordem do pedido; as outras, por prioridade
        if t['classe'] == 'ia':
            return (3, t['ordem'])
        return (PRIORIDADE[t['tipo']], t['ordem'])

    def _teto_disponivel(self):
        """systemd-run --user --scope funciona aqui? (teto rígido de memória)"""
        if self._cgroup is None:
            ok = False
            if sys.platform.startswith('linux') and shutil.which('systemd-run'):
                try:
                    r = subprocess.run(['systemd-run', '--user', '--scope', '-q', '-p', 'MemoryMax=64M', 'true'],
                                       capture_output=True, timeout=10)
                    ok = r.returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    ok = False
            self._cgroup = ok
        return self._cgroup

    def _publica(self, t):
        pub = {k: v for k, v in t.items() if k not in ('args', 'func')}
        pub['decorrido'] = round(((t['fim'] or time.time()) - t['inicio']), 1) if t['inicio'] else None
        return pub

    def _acordar(self):
        self._evento.set()

    def _mensagem(self, w, msg):
        with self.lock:
            t = self.tarefas.get(msg.get('id'))
            if t is None or t['estado'] == 'cancelado':
                return
            if msg['t'] == 'progresso':
                frac = float(msg.get('frac', 0))
                etapa = msg.get('etapa') or t['etapa']
                if not t['etapas'] or t['etapas'][-1]['nome'] != etapa:
                    if t['etapas']:
                        t['etapas'][-1]['fim'] = time.time()
                    t['etapas'].append({'nome': etapa, 'inicio': time.time(), 'fim': None})
                t['etapa'] = etapa
                t['progresso'] = max(t['progresso'], frac)
                dec = time.time() - (t['inicio'] or time.time())
                if 0.04 < t['progresso'] < 1 and dec > 1:
                    t['eta'] = round(dec / t['progresso'] * (1 - t['progresso']), 1)
                return
            if t['etapas'] and t['etapas'][-1]['fim'] is None:
                t['etapas'][-1]['fim'] = time.time()
            t['fim'] = time.time()
            w.tarefa = None
            w.ocioso_desde = time.time()
            if w.classe == 'ia':
                # processo novo a cada tarefa de IA: a memória volta toda ao sistema
                threading.Thread(target=w.encerrar, daemon=True).start()
            if msg['t'] != 'ok' and t['classe'] == 'ia' and 'memória' in (msg.get('erro') or '') \
                    and t['tentativa'] < TENTATIVAS_IA:
                self._de_novo(t, 'A etapa passou do limite de memória; recomeçando em modo de pouca memória '
                                 '(mesma qualidade, mais tempo).')
                self._acordar()
                return
            if msg['t'] == 'ok':
                t['estado'] = 'pronto'
                t['progresso'] = 1.0
                t['etapa'] = 'Pronto'
                t['eta'] = 0
                t['resultado'] = msg.get('res')
                res = t['resultado'] or {}
                if res.get('triangulos') and res.get('tempo'):
                    por_proc = res['triangulos'] / max(0.05, res['tempo']) / max(1, res.get('workers', 1)) ** 0.8
                    antigo = self.vazao.get(t['tipo'])
                    self.vazao[t['tipo']] = por_proc if antigo is None else antigo * 0.6 + por_proc * 0.4
            else:
                t['estado'] = 'erro'
                t['erro'] = msg.get('erro') or 'Erro desconhecido.'
                t['etapa'] = 'Erro'
            cb = self.ao_terminar.get(t['tipo'])
        if cb:
            try:
                cb(self._publica(t) | {'resultado': t['resultado'], 'args': t['args']})
            except Exception:
                import traceback
                traceback.print_exc()
        self._acordar()

    def _processo_morreu(self, w, proc):
        with self.lock:
            if proc is not w.proc:
                return
            t = w.tarefa
            w.tarefa = None
            if t is not None and t['estado'] in ('rodando', 'pausado'):
                codigo = proc.poll()
                t['estado'] = 'erro'
                t['fim'] = time.time()
                t['etapa'] = 'Erro'
                if codigo in (-9, 137) and t['classe'] == 'ia' and t['tentativa'] < TENTATIVAS_IA:
                    self._de_novo(t, w.motivo or 'A etapa passou do limite de memória; recomeçando em modo de '
                                                  'pouca memória (mesma qualidade, mais tempo).')
                elif codigo in (-9, 137):
                    t['erro'] = ('O processo foi encerrado por falta de memória, mesmo no modo de pouca memória. '
                                 'Feche outros programas (navegador com muitas abas, editores) e peça de novo.')
                else:
                    t['erro'] = f'O processo de trabalho parou inesperadamente (código {codigo}).'
            w.motivo = None
        self._acordar()

    def _de_novo(self, t, mensagem):
        """Volta a tarefa de IA para o começo da fila, com menos memória por fatia."""
        t['tentativa'] += 1
        t['estado'] = 'fila'
        t['etapa'] = 'Na fila'
        t['erro'] = None
        t['fim'] = None
        t['inicio'] = None
        t['progresso'] = 0.0
        t['etapas'] = []
        t['mensagem'] = f'Tentativa {t["tentativa"]} de {TENTATIVAS_IA}: {mensagem}'
        t['args']['pouca_memoria'] = t['tentativa'] - 1
        t['ordem'] = min([x['ordem'] for x in self.tarefas.values() if x['classe'] == 'ia'] + [t['ordem']]) - 1

    def _admitir_ia(self, t):
        """Teto de memória da etapa de IA pela RAM livre agora. Se nem o mínimo
        cabe, espera (com aviso) em vez de arriscar travar o computador."""
        livre = HW.ram_livre() / HW.MB
        for w in self.leves + self.pesados:
            if w.tarefa is not None:
                livre -= max(0.0, w.tarefa['estimativa_mb'] - w.memoria_mb())
        teto = min(livre - MARGEM_SISTEMA_MB, psutil.virtual_memory().total / HW.MB * 0.75)
        minimo = float(t.get('minimo_mb') or 1400)
        reducao = 0.6 ** int(t['args'].get('pouca_memoria') or 0)
        if teto < minimo and not t.get('forcar'):
            t['mensagem'] = (f'Aguardando memória livre: esta etapa precisa de ~{minimo:.0f} MB e agora há '
                             f'{max(0, livre - MARGEM_SISTEMA_MB):.0f} MB (fora a folga que fica para o sistema e os '
                             'outros programas). Ela começa sozinha assim que liberar; para começar já, feche '
                             'programas ou use "Rodar assim mesmo" (com teto de memória: se faltar, só ela para, '
                             'o computador não trava).')
            return False
        teto = max(teto, minimo)
        t['args']['limite_mb'] = round(teto)
        # o que o processo ainda pode usar além da base (~900 MB: python, rede, textura)
        t['args']['orcamento_mb'] = round(max(150.0, (teto - 900) * reducao))
        t['estimativa_mb'] = round(teto)
        return True

    def _ias_alvo(self):
        """Quantas etapas de IA ao mesmo tempo: 2 só com memória livre para as
        duas (com folga) e 8+ núcleos lógicos; senão 1."""
        livre = HW.ram_livre() / HW.MB - MARGEM_SISTEMA_MB
        ocupadas = [w for w in self.ias if w.tarefa is not None]
        if (os.cpu_count() or 2) >= 8 and livre >= 2 * 2400 + sum(w.tarefa['estimativa_mb'] for w in ocupadas):
            return 2
        return max(1, len(ocupadas))

    def _pesados_alvo(self):
        return HW.perfil_ativo()['hd_simultaneos']

    def _proxima(self, classe):
        cand = [t for t in self.tarefas.values() if t['classe'] == classe
                and t['estado'] in ('fila', 'aguardando_memoria') and not t['pausado']]
        cand.sort(key=self._chave)
        return cand

    def _admitir(self, t):
        """Decide se a tarefa cabe na memória agora (ajustando os processos)."""
        if t.get('forcar'):
            return True
        reservado = 0.0
        for w in self._todos():
            if w.tarefa is not None:
                # o que a etapa em curso ainda deve crescer
                reservado += max(0.0, w.tarefa['estimativa_mb'] - w.memoria_mb())
        if t['tipo'] == 'hd':
            pedidos = int(t['args'].get('workers_pedidos') or t['args'].get('workers') or 1)
            w = HW.workers_agora(pedidos)
            vivo = any(x.vivo() and x.tarefa is None for x in self.pesados)
            while w >= 1:
                est = HW.estimar_mb(t['triangulos'], w, vivo)
                ok, livre = HW.admitir(est, reservado)
                if ok:
                    t['args']['workers'] = w
                    t['workers'] = w
                    t['estimativa_mb'] = est
                    return True
                w -= 1
            t['mensagem'] = (f'Aguardando memória: precisa de ~{HW.estimar_mb(t["triangulos"], 1, vivo):.0f} MB '
                             f'e há {livre:.0f} MB livres. Feche programas, reduza a qualidade ou use '
                             '"Rodar assim mesmo".')
            return False
        ok, livre = HW.admitir(t['estimativa_mb'], reservado, fracao=0.8)
        if not ok:
            t['mensagem'] = f'Aguardando memória (~{t["estimativa_mb"]:.0f} MB, livres {livre:.0f} MB).'
        return ok

    def _estimar_eta_fila(self):
        # fila de IA: começa quando as da frente terminarem (tempo previsto de cada uma)
        agora = time.time()
        livre_em = agora
        for t in sorted([x for x in self.tarefas.values() if x['classe'] == 'ia'
                         and x['estado'] in ('rodando', 'pausado', 'fila', 'aguardando_memoria')], key=lambda x: (
                             x['estado'] not in ('rodando', 'pausado'), self._chave(x))):
            prev = float(t.get('previsto_s') or 0)
            if t['estado'] in ('rodando', 'pausado') and t.get('inicio'):
                falta = t.get('eta')
                if falta is None:
                    falta = max(5.0, prev - (agora - t['inicio']))
                livre_em = agora + falta
                continue
            t['inicio_previsto'] = round(livre_em - agora, 1)
            t['eta'] = round(livre_em - agora + prev, 1) if prev else None
            livre_em += prev
        for t in self.tarefas.values():
            if t['classe'] == 'ia':
                continue
            if t['estado'] in ('fila', 'aguardando_memoria') and t['triangulos']:
                v = self.vazao.get(t['tipo']) or self.vazao.get('preview')
                if v:
                    w = max(1, t['args'].get('workers') or 1)
                    t['eta'] = round(t['triangulos'] / (v * w ** 0.8) + 2, 1)

    def _laco(self):
        while not self._parar.is_set():
            self._evento.wait(0.4)
            self._evento.clear()
            try:
                self._vigiar()
                self._agendar()
            except Exception:
                import traceback
                traceback.print_exc()

    def _vigiar(self):
        """Segunda proteção (além do teto do cgroup): se a RAM livre do sistema
        chega ao nível crítico, a etapa de IA é encerrada antes de o computador
        começar a travar, e volta para a fila em modo de pouca memória."""
        if HW.ram_livre() / HW.MB >= CRITICO_MB:
            return
        with self.lock:
            alvo = [w for w in self.ias if w.tarefa is not None and w.vivo()]
            if not alvo:
                return
            w = alvo[0]
            w.motivo = ('A memória do computador quase acabou; a etapa foi interrompida para não travar o '
                        'sistema e recomeça em modo de pouca memória (mesma qualidade, mais tempo).')
        w.matar()

    def _agendar(self):
        with self.lock:
            # ajusta a quantidade de processos pesados ao perfil
            alvo = self._pesados_alvo()
            while len(self.pesados) < alvo:
                self.pesados.append(Trabalhador(self, 'pesada', self.log))
            # faixa de IA: uma etapa por vez; duas (de imagens diferentes) só se a
            # memória livre comporta as duas e há núcleos para dividir
            while len(self.ias) < self._ias_alvo():
                self.ias.append(Trabalhador(self, 'ia', self.log))
            for classe, lista in (('ia', self.ias), ('leve', self.leves), ('pesada', self.pesados[:alvo])):
                livres = [w for w in lista if w.tarefa is None and not (classe == 'ia' and w.vivo())]
                if classe == 'ia':
                    livres = livres[:max(0, self._ias_alvo() - sum(1 for w in lista if w.tarefa is not None))]
                if not livres:
                    continue
                em_curso = {w.tarefa['projeto'] for w in lista if w.tarefa is not None}
                for t in self._proxima(classe):
                    if not livres:
                        break
                    if classe == 'ia':
                        if t['projeto'] in em_curso:
                            continue                      # mesma imagem: espera a anterior (usa o cache dela)
                        if not self._admitir_ia(t):
                            t['estado'] = 'aguardando_memoria'
                            t['etapa'] = 'Aguardando memória'
                            break
                        w = livres[0]
                        w.limite_mb = t['args']['limite_mb']
                        # teto rígido + limite macio (o sistema recupera memória da
                        # própria etapa antes de mexer nos outros programas) e
                        # prioridade baixa de CPU e disco: o PC continua livre
                        w.prefixo = (['systemd-run', '--user', '--scope', '-q',
                                      '-p', f'MemoryMax={w.limite_mb}M', '-p', f'MemoryHigh={int(w.limite_mb * 0.9)}M',
                                      '-p', 'MemorySwapMax=0', '-p', 'CPUWeight=20', '-p', 'IOWeight=20', '--']
                                     if self._teto_disponivel() else [])
                        em_curso.add(t['projeto'])
                    elif not self._admitir(t):
                        t['estado'] = 'aguardando_memoria'
                        t['etapa'] = 'Aguardando memória'
                        # tarefas leves seguintes podem caber; pesadas esperam a vez
                        if classe == 'pesada':
                            break
                        continue
                    w = livres.pop(0)
                    t['estado'] = 'rodando'
                    t['inicio'] = time.time()
                    t['etapa'] = 'Iniciando'
                    t['mensagem'] = None
                    w.enviar(t)
            # encerra processos pesados ociosos há muito tempo
            agora = time.time()
            for w in self.pesados:
                if w.tarefa is None and w.vivo() and agora - w.ocioso_desde > OCIOSO_MAX:
                    w.encerrar()
            self._estimar_eta_fila()
            # limpa finalizadas antigas
            fim = sorted([t for t in self.tarefas.values() if t['estado'] in ('pronto', 'erro', 'cancelado')],
                         key=lambda t: -(t['fim'] or 0))
            for t in fim[GUARDAR_FINALIZADAS * 3:]:
                self.tarefas.pop(t['id'], None)
