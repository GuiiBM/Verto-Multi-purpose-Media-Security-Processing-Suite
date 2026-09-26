import os

_DIR = os.path.dirname(os.path.abspath(__file__))


def _load(filename):
    """Lê o HTML do disco a cada chamada, para edições aparecerem sem
    reiniciar o Flask (mesmo padrão dos outros módulos)."""
    try:
        with open(os.path.join(_DIR, filename), 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return f"<h1>Error loading {filename}</h1>"


def CONVERSOR_HTML(): return _load('conversor.html')
