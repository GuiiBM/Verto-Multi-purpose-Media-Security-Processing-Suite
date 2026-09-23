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


def MATCHAEFFECT_HUB_HTML(): return _load('matchaeffect_hub.html')
def MATCHAEFFECT_ADD_HTML(): return _load('matchaeffect_add.html')
def MATCHAEFFECT_REMOVE_HTML(): return _load('matchaeffect_remove.html')
def MATCHAEFFECT_VIDEO_ADD_HTML(): return _load('matchaeffect_video_add.html')
def MATCHAEFFECT_VIDEO_REMOVE_HTML(): return _load('matchaeffect_video_remove.html')
def MATCHAEFFECT_AI_ADD_HTML(): return _load('matchaeffect_ai_add.html')
def MATCHAEFFECT_AI_REMOVE_HTML(): return _load('matchaeffect_ai_remove.html')
def MATCHAEFFECT_AI_VIDEO_HTML(): return _load('matchaeffect_ai_video.html')
def MATCHAEFFECT_AI_VIDEO_REMOVE_HTML(): return _load('matchaeffect_ai_video_remove.html')
