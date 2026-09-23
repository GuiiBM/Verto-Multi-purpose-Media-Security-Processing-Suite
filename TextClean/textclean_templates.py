import os

_DIR = os.path.dirname(os.path.abspath(__file__))


def _load(filename):
    """Lê o HTML do disco a cada chamada (sem cache em constante de módulo) -
    assim uma edição no arquivo aparece no próximo request, sem precisar
    reiniciar o servidor Flask (que só recarrega automaticamente por mudança
    em arquivos .py, não nesses templates HTML carregados como string)."""
    try:
        with open(os.path.join(_DIR, filename), 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return f"<h1>Error loading {filename}</h1>"


def TEXTCLEAN_HUB_HTML(): return _load('textclean_hub.html')
def TEXTCLEAN_DIFF_HTML(): return _load('textclean_diff.html')
def TEXTCLEAN_SANITIZE_HTML(): return _load('textclean_sanitize.html')
def TEXTCLEAN_STATS_HTML(): return _load('textclean_stats.html')
