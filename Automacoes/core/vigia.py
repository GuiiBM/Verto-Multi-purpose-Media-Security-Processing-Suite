"""Vigia de pasta sob demanda: só olha a pasta quando alguém pede.

Não há varredura periódica: a thread fica parada num threading.Event (sem
gastar CPU) até o código avisar que um download vai chegar, por exemplo
quando a rota do InstaSaver termina de entregar um arquivo ao navegador. Aí
ela confere a pasta algumas vezes, com intervalos crescentes, até o arquivo
esperado aparecer completo (o navegador ainda precisa renomear o
.crdownload/.part), entrega o que ficou pronto e volta a dormir.

Um arquivo só é entregue quando o tamanho e a data ficam iguais entre duas
conferências e não há um .crdownload/.part ao lado.
"""
import threading
import time
from pathlib import Path

PARCIAIS = ('.crdownload', '.part', '.tmp', '.download', '.partial')
INTERVALOS = (1, 1, 2, 2, 3, 5, 5, 10)   # segundos entre conferências; depois, sempre o último
ESPERA_MAX = 5 * 60                       # desiste de um download esperado depois disso


def baixando(caminho: Path):
    nome = caminho.name.lower()
    if nome.endswith(PARCIAIS) or nome.startswith('.'):
        return True
    return any(caminho.with_name(caminho.name + s).exists() for s in ('.part', '.crdownload'))


class Vigia:
    def __init__(self, obter_pasta, filtro, ao_chegar, combina=None):
        """obter_pasta() -> Path ou None (pausado); filtro(Path) -> bool;
        ao_chegar(lista de Path) recebe de uma vez tudo o que ficou pronto;
        combina(Path, nome esperado) -> bool diz se o arquivo é o esperado."""
        self._obter_pasta = obter_pasta
        self._filtro = filtro
        self._ao_chegar = ao_chegar
        self._combina = combina or (lambda p, nome: p.name == nome)
        self._lock = threading.Lock()
        self._acordar = threading.Event()
        self._esperados = {}   # nome -> até quando esperar
        self._entregues = {}   # caminho -> assinatura já entregue (não entrega duas vezes)
        self._thread = threading.Thread(target=self._rodar, name='verto-automacoes-vigia', daemon=True)
        self._thread.start()

    def avisar(self, nome=None):
        """Um download vai chegar (nome = o nome que o navegador vai dar, se
        souber). Sem nome, é só um pedido de conferência (ex.: ao ligar o Verto)."""
        if nome:
            with self._lock:
                self._esperados[nome] = time.time() + ESPERA_MAX
        self._acordar.set()

    def esquecer(self, caminho=None):
        """Permite entregar de novo o que já foi entregue (ex.: tentar outra vez
        um ZIP que falhou)."""
        with self._lock:
            if caminho is None:
                self._entregues.clear()
            else:
                self._entregues.pop(Path(caminho), None)

    def _rodar(self):
        while True:
            self._acordar.wait()
            self._acordar.clear()
            try:
                self._sessao()
            except Exception:
                pass

    def _sessao(self):
        """Confere pelo menos duas vezes (para saber se o tamanho parou de mudar)
        e continua só enquanto há download esperado ou arquivo pela metade."""
        vistos, passo, fim = {}, 0, time.time() + ESPERA_MAX
        while True:
            pasta = self._obter_pasta()
            if not pasta or not pasta.is_dir():
                with self._lock:
                    self._esperados.clear()
                return
            prontos, mudando = self._conferir(pasta, vistos)
            with self._lock:
                agora = time.time()
                for nome in [n for n, ate in self._esperados.items()
                             if ate < agora or any(self._combina(p, n) for p in prontos)]:
                    del self._esperados[nome]
                continuar = bool(self._esperados) or mudando or passo == 0
            if prontos:
                self._ao_chegar(sorted(prontos))
            if not continuar or time.time() > fim:
                return
            # Novo aviso no meio da espera recomeça os intervalos curtos.
            if self._acordar.wait(INTERVALOS[min(passo, len(INTERVALOS) - 1)]):
                self._acordar.clear()
                passo, fim = 0, time.time() + ESPERA_MAX
            else:
                passo += 1

    def _conferir(self, pasta, vistos):
        prontos, mudando = [], False
        for caminho in pasta.iterdir():
            try:
                if not caminho.is_file() or baixando(caminho) or not self._filtro(caminho):
                    continue
                st = caminho.stat()
            except OSError:
                continue
            assinatura = (st.st_size, st.st_mtime)
            with self._lock:
                if self._entregues.get(caminho) == assinatura:
                    continue
            if st.st_size > 0 and vistos.get(caminho) == assinatura:
                prontos.append(caminho)
                with self._lock:
                    if len(self._entregues) > 2000:
                        self._entregues.clear()
                    self._entregues[caminho] = assinatura
            else:
                vistos[caminho] = assinatura
                mudando = True
        return prontos, mudando
