"""Pastas do usuário (Downloads e Documentos) no idioma do sistema.

No Linux em português elas se chamam "Downloads" e "Documentos" e o nome real
fica em ~/.config/user-dirs.dirs; no Windows a pasta Documentos pode estar
redirecionada (OneDrive), então o caminho vem da própria API do sistema.
"""
import os
import re
from pathlib import Path


def _xdg(chave):
    try:
        texto = (Path.home() / '.config' / 'user-dirs.dirs').read_text(encoding='utf-8')
    except OSError:
        return None
    m = re.search(rf'^XDG_{chave}_DIR="([^"]+)"', texto, re.M)
    if not m:
        return None
    caminho = Path(m.group(1).replace('$HOME', str(Path.home())))
    return caminho if caminho != Path.home() else None


def _windows_documentos():
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        # CSIDL_PERSONAL = 5 (Documentos), SHGFP_TYPE_CURRENT = 0
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
            return Path(buf.value)
    except Exception:
        pass
    return None


def downloads():
    return (_xdg('DOWNLOAD') if os.name != 'nt' else None) or Path.home() / 'Downloads'


def documentos():
    if os.name == 'nt':
        return _windows_documentos() or Path.home() / 'Documents'
    achada = _xdg('DOCUMENTS')
    if achada:
        return achada
    for nome in ('Documentos', 'Documents'):
        if (Path.home() / nome).is_dir():
            return Path.home() / nome
    return Path.home() / 'Documents'
