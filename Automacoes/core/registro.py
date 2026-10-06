"""Histórico das automações: o que foi feito, para onde foi e por que falhou.

Cada entrada é uma linha JSON em dados/registro.jsonl, então o histórico
sobrevive a reinícios do Verto; a interface lê só as entradas novas.
"""
import json
import threading
import time
from collections import deque
from pathlib import Path

LIMITE = 400


class Registro:
    def __init__(self, arquivo: Path):
        self._arquivo = arquivo
        self._lock = threading.Lock()
        self._itens = deque(maxlen=LIMITE)
        self._ultimo_id = 0
        try:
            for linha in arquivo.read_text(encoding='utf-8').splitlines()[-LIMITE:]:
                item = json.loads(linha)
                self._itens.append(item)
                self._ultimo_id = max(self._ultimo_id, item.get('id', 0))
        except (OSError, ValueError):
            pass

    def _adicionar(self, nivel, titulo, detalhes=None, automacao='organizador'):
        with self._lock:
            self._ultimo_id += 1
            item = {'id': self._ultimo_id, 'quando': time.time(), 'nivel': nivel,
                    'automacao': automacao, 'titulo': titulo, 'detalhes': list(detalhes or [])}
            self._itens.append(item)
            try:
                self._arquivo.parent.mkdir(parents=True, exist_ok=True)
                if self._arquivo.exists() and self._arquivo.stat().st_size > 2_000_000:
                    # Mantém o arquivo pequeno: reescreve só o que está na memória.
                    self._arquivo.write_text(''.join(json.dumps(i, ensure_ascii=False) + '\n'
                                                     for i in self._itens), encoding='utf-8')
                else:
                    with open(self._arquivo, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(item, ensure_ascii=False) + '\n')
            except OSError:
                pass
            return item

    def ok(self, titulo, detalhes=None, **kw):
        return self._adicionar('ok', titulo, detalhes, **kw)

    def info(self, titulo, detalhes=None, **kw):
        return self._adicionar('info', titulo, detalhes, **kw)

    def erro(self, titulo, detalhes=None, **kw):
        return self._adicionar('erro', titulo, detalhes, **kw)

    def listar(self, depois_de=0):
        with self._lock:
            return [i for i in self._itens if i['id'] > depois_de]

    def limpar(self):
        with self._lock:
            self._itens.clear()
            try:
                self._arquivo.write_text('', encoding='utf-8')
            except OSError:
                pass
