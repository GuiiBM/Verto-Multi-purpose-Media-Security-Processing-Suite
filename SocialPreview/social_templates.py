import os

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def SOCIAL_HTML():
    """Lê o HTML do disco a cada chamada, para edições aparecerem sem reiniciar o Flask."""
    try:
        with open(os.path.join(_RAIZ, 'templates', 'social.html'), 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return "<h1>Erro ao carregar Social Preview</h1>"
