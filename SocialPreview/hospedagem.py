"""Endereço público temporário para a mídia que o Instagram e o Threads buscam pela internet.

Essas duas APIs não aceitam o arquivo enviado: pedem um `image_url`/`video_url`
público que o servidor da Meta baixa. O Verto roda só no computador, então:

- "tunel" (padrão): sobe um servidorzinho próprio, numa porta aleatória, que só
  entrega os arquivos deste post em /m/<token aleatório>/<nome> — nunca o Verto —
  e o expõe por um túnel rápido da Cloudflare (cloudflared, sem conta). O túnel
  e o servidor são encerrados no fim da publicação.
- "litterbox": envia o arquivo para litterbox.catbox.moe, que apaga em 1 hora.

Com "auto", tenta o túnel e, se falhar, o Litterbox.
"""

import http.server
import os
import platform
import re
import secrets
import shutil
import socketserver
import stat
import subprocess
import threading
import time

import requests

_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(_DIR, 'dados', 'bin')

LITTERBOX = 'https://litterbox.catbox.moe/resources/internals/api.php'
UA = 'Verto-SocialPreview/1.0'


class HospedagemError(Exception):
    pass


def _nome_binario():
    sistema = platform.system().lower()
    maq = platform.machine().lower()
    arq = 'arm64' if maq in ('arm64', 'aarch64') else ('386' if maq in ('i386', 'i686', 'x86') else 'amd64')
    if sistema == 'windows':
        return f'cloudflared-windows-{arq}.exe', 'cloudflared.exe'
    if sistema == 'darwin':
        return f'cloudflared-darwin-{arq}.tgz', 'cloudflared'
    return f'cloudflared-linux-{arq}', 'cloudflared'


def cloudflared(baixar=True):
    """Caminho do cloudflared: o do sistema ou o baixado para SocialPreview/dados/bin."""
    achado = shutil.which('cloudflared')
    if achado:
        return achado
    remoto, local = _nome_binario()
    destino = os.path.join(BIN_DIR, local)
    if os.path.exists(destino):
        return destino
    if not baixar:
        return None
    os.makedirs(BIN_DIR, exist_ok=True)
    url = f'https://github.com/cloudflare/cloudflared/releases/latest/download/{remoto}'
    tmp = destino + '.part'
    with requests.get(url, stream=True, timeout=60, headers={'User-Agent': UA}) as r:
        if r.status_code != 200:
            raise HospedagemError(f'Não deu para baixar o cloudflared ({r.status_code}).')
        with open(tmp, 'wb') as f:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)
    if remoto.endswith('.tgz'):
        import tarfile
        with tarfile.open(tmp) as t:
            membro = next(m for m in t.getmembers() if m.name.endswith('cloudflared'))
            with t.extractfile(membro) as src, open(destino, 'wb') as dst:
                shutil.copyfileobj(src, dst)
        os.remove(tmp)
    else:
        os.replace(tmp, destino)
    os.chmod(destino, os.stat(destino).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return destino


class _Servidor(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _handler(arquivos):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _achar(self):
            m = re.fullmatch(r'/m/([A-Za-z0-9_-]{20,})/[^/]+', self.path.split('?')[0])
            return arquivos.get(m.group(1)) if m else None

        def _enviar(self, corpo):
            item = self._achar()
            if not item:
                self.send_error(404)
                return
            caminho, mime = item
            tam = os.path.getsize(caminho)
            ini, fim = 0, tam - 1
            faixa = self.headers.get('Range')
            m = re.match(r'bytes=(\d*)-(\d*)', faixa or '')
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    ini = int(m.group(1))
                    fim = int(m.group(2)) if m.group(2) else tam - 1
                else:
                    ini = max(0, tam - int(m.group(2)))
                fim = min(fim, tam - 1)
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {ini}-{fim}/{tam}')
            else:
                self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(fim - ini + 1))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if not corpo:
                return
            with open(caminho, 'rb') as f:
                f.seek(ini)
                falta = fim - ini + 1
                while falta > 0:
                    bloco = f.read(min(1 << 16, falta))
                    if not bloco:
                        break
                    self.wfile.write(bloco)
                    falta -= len(bloco)

        def do_GET(self):
            self._enviar(True)

        def do_HEAD(self):
            self._enviar(False)
    return H


class Tunel:
    """Servidor só com os arquivos deste post + túnel rápido da Cloudflare."""

    def __init__(self, log=None):
        self.log = log or (lambda m: None)
        self.arquivos = {}
        self.servidor = None
        self.proc = None
        self.base = None

    def abrir(self):
        if self.base:
            return
        binario = cloudflared()
        self.servidor = _Servidor(('127.0.0.1', 0), _handler(self.arquivos))
        porta = self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.log('Abrindo o túnel temporário…')
        self.proc = subprocess.Popen(
            [binario, 'tunnel', '--no-autoupdate', '--url', f'http://127.0.0.1:{porta}'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        achado = {}

        def ler():
            for linha in self.proc.stdout:
                m = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', linha)
                if m and 'url' not in achado:
                    achado['url'] = m.group(0)
        threading.Thread(target=ler, daemon=True).start()
        limite = time.time() + 40
        while 'url' not in achado and time.time() < limite and self.proc.poll() is None:
            time.sleep(0.25)
        if 'url' not in achado:
            self.fechar()
            raise HospedagemError('O túnel da Cloudflare não respondeu.')
        self.base = achado['url']
        # O nome novo leva alguns segundos para valer no DNS: só segue quando o túnel
        # responde de fora (um 404 do nosso servidor já prova que chegou até aqui).
        limite = time.time() + 60
        while time.time() < limite:
            try:
                r = requests.get(self.base + '/m/teste-de-conexao-verto/x', timeout=8, headers={'User-Agent': UA})
                if r.status_code == 404:
                    return
            except requests.RequestException:
                pass
            time.sleep(1.5)
        self.fechar()
        raise HospedagemError('O túnel abriu mas não ficou acessível pela internet.')

    def publicar(self, caminho, mime):
        self.abrir()
        token = secrets.token_urlsafe(24)
        self.arquivos[token] = (caminho, mime)
        nome = os.path.basename(caminho)
        return f'{self.base}/m/{token}/{nome}'

    def fechar(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self.servidor:
            self.servidor.shutdown()
            self.servidor.server_close()
        self.servidor = None
        self.base = None
        self.arquivos.clear()


class Litterbox:
    def __init__(self, log=None):
        self.log = log or (lambda m: None)

    def publicar(self, caminho, mime):
        self.log('Enviando a mídia para o Litterbox (apaga em 1 h)…')
        erro = ''
        for tentativa in range(3):  # o serviço às vezes devolve 500 passageiro
            try:
                with open(caminho, 'rb') as f:
                    r = requests.post(LITTERBOX, data={'reqtype': 'fileupload', 'time': '1h'},
                                      files={'fileToUpload': (os.path.basename(caminho), f, mime)},
                                      timeout=(20, 300), headers={'User-Agent': UA})
                url = (r.text or '').strip()
                if r.status_code == 200 and url.startswith('https://'):
                    return url
                erro = f'HTTP {r.status_code}'
            except requests.RequestException as e:
                erro = e.__class__.__name__
            time.sleep(2 * (tentativa + 1))
        raise HospedagemError(f'O Litterbox não aceitou o arquivo ({erro}).')

    def fechar(self):
        pass


class Hospedagem:
    """Escolhe o método na primeira mídia e mantém até `fechar()`."""

    def __init__(self, metodo='auto', log=None):
        self.metodo = metodo or 'auto'
        self.log = log or (lambda m: None)
        self.atual = None

    def url(self, caminho, mime):
        if self.atual is None:
            if self.metodo in ('auto', 'tunel'):
                t = Tunel(self.log)
                try:
                    t.abrir()
                    self.atual = t
                except Exception as e:
                    if self.metodo == 'tunel':
                        raise HospedagemError(f'Túnel indisponível: {e}')
                    self.log(f'Túnel indisponível ({e}); usando o Litterbox.')
                    self.atual = Litterbox(self.log)
            else:
                self.atual = Litterbox(self.log)
        return self.atual.publicar(caminho, mime)

    def fechar(self):
        if self.atual:
            self.atual.fechar()
        self.atual = None
