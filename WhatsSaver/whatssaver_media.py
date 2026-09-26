"""Download e descriptografia das mídias do WhatsApp, com conferência.

Cada mídia fica no servidor do WhatsApp criptografada com AES-256-CBC. A
chave sai da mediaKey da mensagem por HKDF-SHA256, com um rótulo por tipo
("WhatsApp Image Keys", "WhatsApp Video Keys"...), e o arquivo baixado é
[conteúdo criptografado][10 bytes de MAC].

Antes de entregar qualquer coisa, o MAC é conferido. Mídia antiga às vezes
volta do servidor com "200 OK" mas com um conteúdo que não é mais o original:
sem a conferência isso vira arquivo corrompido (era o "bad decrypt" da versão
anterior, que só pedia reenvio em 404/410). Aqui, qualquer resposta que não
confere faz o motor pedir ao celular para reenviar a mídia, como o WhatsApp
Web faz.
"""
import base64
import hashlib
import hmac
import os
import threading
from urllib.parse import urlparse

import requests

try:
    from Crypto.Cipher import AES
except ImportError:  # pycryptodome (está no requirements.txt)
    AES = None

HKDF_INFO = {
    'image': b'WhatsApp Image Keys',
    'video': b'WhatsApp Video Keys',
    'document': b'WhatsApp Document Keys',
    'audio': b'WhatsApp Audio Keys',
}
MESSAGE_KIND = {'imageMessage': 'image', 'videoMessage': 'video', 'documentMessage': 'document'}
MAC_LEN = 10
CHUNK = 1 << 20          # múltiplo de 16, o bloco do AES
TIMEOUT = (15, 60)       # conexão, e no máximo 1 min sem receber nada
DEFAULT_HOST = 'mmg.whatsapp.net'
HEADERS = {'Origin': 'https://web.whatsapp.com', 'Referer': 'https://web.whatsapp.com/'}


PHONE_ONLY = ('Arquivo antigo que o WhatsApp não libera mais para aparelhos conectados: o celular reenviou, '
              'mas protegido com uma chave que só ele tem. A mídia continua no celular.')


class MediaError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _hkdf(key, length, info):
    prk = hmac.new(b'\0' * 32, key, hashlib.sha256).digest()
    out, block, n = b'', b'', 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([n]), hashlib.sha256).digest()
        out += block
        n += 1
    return out[:length]


def media_keys(media_key, kind):
    """(iv, chave do AES, chave do MAC) da mídia."""
    expanded = _hkdf(media_key, 112, HKDF_INFO[kind])
    return expanded[:16], expanded[16:48], expanded[48:80]


def media_url(media):
    direct = media.get('directPath')
    url = media.get('url') or ''
    if direct:
        host = urlparse(url).hostname if url.startswith('https://') else None
        return f'https://{host or DEFAULT_HOST}{direct}'
    return url or None


def _b64(value):
    return base64.b64decode(value) if value else None


def download(url, dest, cancel=None):
    """Baixa o arquivo criptografado. Devolve o SHA-256 dele."""
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=TIMEOUT) as resp:
            if resp.status_code in (403, 404, 410):
                raise MediaError('O servidor do WhatsApp não tem mais esse arquivo.', 'gone')
            if resp.status_code >= 400:
                raise MediaError(f'O servidor do WhatsApp respondeu com erro {resp.status_code}.', 'http')
            sha = hashlib.sha256()
            with open(dest, 'wb') as out:
                for chunk in resp.iter_content(CHUNK):
                    if cancel is not None and cancel.is_set():
                        raise MediaError('Cancelado.', 'cancelled')
                    out.write(chunk)
                    sha.update(chunk)
            return sha.digest()
    except requests.Timeout:
        raise MediaError('O download travou (o servidor parou de responder). Tente de novo.', 'stalled')
    except requests.RequestException as e:
        raise MediaError(f'Falha de conexão com o servidor do WhatsApp: {e}', 'network')


def _mac_ok(path, iv, mac_key):
    size = os.path.getsize(path)
    if size <= MAC_LEN or (size - MAC_LEN) % 16:
        return False
    h = hmac.new(mac_key, iv, hashlib.sha256)
    with open(path, 'rb') as f:
        left = size - MAC_LEN
        while left:
            chunk = f.read(min(CHUNK, left))
            h.update(chunk)
            left -= len(chunk)
        mac = f.read(MAC_LEN)
    return hmac.compare_digest(h.digest()[:MAC_LEN], mac)


def decrypt(enc_path, out_path, media_key, kind):
    """Confere o MAC e descriptografa. Se o rótulo esperado não confere, tenta
    os outros: quem decide o rótulo é o aparelho que enviou. Devolve o rótulo usado."""
    for label in [kind] + [k for k in HKDF_INFO if k != kind]:
        iv, cipher_key, mac_key = media_keys(media_key, label)
        if _mac_ok(enc_path, iv, mac_key):
            break
    else:
        raise MediaError('O arquivo baixado não confere com a chave da mensagem.', 'bad_mac')
    if AES is None:
        raise MediaError('Falta o pacote pycryptodome (pip install pycryptodome).', 'setup')
    aes = AES.new(cipher_key, AES.MODE_CBC, iv)
    with open(enc_path, 'rb') as src, open(out_path, 'wb') as dst:
        left = os.path.getsize(enc_path) - MAC_LEN
        while left:
            chunk = src.read(min(CHUNK, left))
            left -= len(chunk)
            plain = aes.decrypt(chunk)
            if not left:  # último pedaço: tira o preenchimento PKCS#7
                pad = plain[-1]
                if not 1 <= pad <= 16 or plain[-pad:] != bytes([pad]) * pad:
                    raise MediaError('O arquivo baixado veio corrompido.', 'bad_padding')
                plain = plain[:-pad]
            dst.write(plain)
    return label


def fetch(payload, dest, reupload, cancel=None):
    """Baixa, confere e descriptografa a mídia para `dest`.

    `reupload()` pede ao celular para mandar a mídia de novo ao servidor e
    devolve os campos novos ({directPath, url}); é chamado uma vez, se o
    servidor não tiver mais o arquivo ou se o que veio não conferir.
    Devolve esses campos novos (para guardar) ou None."""
    media = dict(payload['media'])
    kind = MESSAGE_KIND.get(payload.get('type'), 'image')
    media_key = _b64(media['mediaKey'])
    enc_sha = _b64(media.get('fileEncSha256'))
    enc, part = dest + '.enc', dest + '.part'
    refreshed = None
    try:
        for attempt in range(2):
            url, got_sha = media_url(media), None
            if url:
                try:
                    got_sha = download(url, enc, cancel)
                    decrypt(enc, part, media_key, kind)
                    os.replace(part, dest)
                    return refreshed
                except MediaError as e:
                    if e.code == 'bad_mac' and enc_sha and got_sha == enc_sha:
                        # O arquivo é o original e mesmo assim não confere: reenviar não resolve.
                        raise MediaError('A chave desta mídia não confere com o arquivo (mensagem danificada).', 'bad_key')
                    if e.code not in ('gone', 'bad_mac', 'bad_padding'):
                        raise
            if attempt == 0:
                refreshed = reupload()
                media.update(refreshed)
        # O celular reenviou, mas cifrado com uma chave nova que ele não informa.
        # Acontece com mídia antiga (conversas que o WhatsApp migrou para o
        # endereçamento por LID): o arquivo existe, mas só o celular abre.
        raise MediaError(PHONE_ONLY, 'phone_only')
    finally:
        for leftover in (enc, part):
            try:
                os.remove(leftover)
            except OSError:
                pass


_locks = {}
_locks_guard = threading.Lock()


def item_lock(key):
    """Um lock por mídia: visualizador, botão e .zip pedindo a mesma mídia ao
    mesmo tempo baixam uma vez só."""
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())
