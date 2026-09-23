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


def IMAGESTUDIO_HUB_HTML(): return _load('imagestudio_hub.html')
def IMAGESTUDIO_SOLO_HTML(): return _load('imagestudio_solo.html')
def IMAGESTUDIO_RESIZE_HTML(): return _load('imagestudio_resize.html')
def IMAGESTUDIO_FILTERS_HTML(): return _load('imagestudio_filters.html')
def IMAGESTUDIO_FAVICON_HTML(): return _load('imagestudio_favicon.html')
