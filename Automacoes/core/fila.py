"""Fila de tarefas com um único worker em thread.

Soltar 40 arquivos de uma vez vira 40 tarefas processadas em ordem, uma por
vez, sem disputar disco/CPU entre si nem com o Whisper ou o FFmpeg de outros
apps. A mesma chave (ex.: o caminho do ZIP) não entra duas vezes na fila.
"""
import queue
import threading
import traceback


class Fila:
    def __init__(self, registro):
        self._registro = registro
        self._q = queue.Queue()
        self._lock = threading.Lock()
        self._chaves = set()
        self._atual = None
        self._thread = threading.Thread(target=self._rodar, name='verto-automacoes-fila', daemon=True)
        self._thread.start()

    def adicionar(self, chave, descricao, funcao, *args):
        with self._lock:
            if chave in self._chaves:
                return False
            self._chaves.add(chave)
        self._q.put((chave, descricao, funcao, args))
        return True

    def estado(self):
        with self._lock:
            return {'atual': self._atual, 'na_fila': max(0, len(self._chaves) - (1 if self._atual else 0))}

    def _rodar(self):
        while True:
            chave, descricao, funcao, args = self._q.get()
            with self._lock:
                self._atual = descricao
            try:
                funcao(*args)
            except Exception as e:
                self._registro.erro(f'Falha em {descricao}: {e}', [traceback.format_exc(limit=3)])
            finally:
                with self._lock:
                    self._atual = None
                    self._chaves.discard(chave)
                self._q.task_done()
