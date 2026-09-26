"""Motor do WhatsSaver: conecta ao WhatsApp como aparelho vinculado (igual ao
WhatsApp Web) e mostra, conversa por conversa, todas as fotos e vídeos -
inclusive os enviados como arquivo/documento - direto dos servidores do
WhatsApp, sem depender do que o celular baixou ou não.

A conexão fica numa ponte em Node.js (bridge/bridge.mjs, com a biblioteca
Baileys), porque é ela que fala o protocolo do WhatsApp Web, inclusive os dois
pedidos que fazem a diferença aqui: buscar no celular mensagens mais antigas
de uma conversa e pedir o reenvio de uma mídia que já saiu do servidor.
O Python abre a ponte, conversa com ela por stdin/stdout (um JSON por linha)
e guarda um índice num SQLite em dados/: conversas, contatos e as mídias (a
miniatura que vem na mensagem + o necessário para baixar depois).

Nada é salvo no computador sem pedir, como no InstaSaver: ver uma mídia só a
baixa para um cache temporário do sistema (whatssaver_cache, limpo sozinho);
o botão de download entrega o arquivo ao navegador e "baixar tudo" monta um
.zip em streaming. O download e a conferência de cada arquivo estão em
whatssaver_media.py.
"""
import os
import re
import json
import time
import uuid
import base64
import shutil
import sqlite3
import hashlib
import platform
import tarfile
import zipfile
import tempfile
import threading
import subprocess
import traceback
import mimetypes
import unicodedata
import urllib.request
from collections import deque, Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path

from . import whatssaver_media as wmedia

_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_DIR = os.path.join(_DIR, 'bridge')
RUNTIME_DIR = os.path.join(BRIDGE_DIR, 'runtime')  # Node portátil, quando o sistema não tem um
DATA_DIR = os.path.join(_DIR, 'dados')             # sessão do WhatsApp + índice (fica fora do git)
DB_PATH = os.path.join(DATA_DIR, 'whatssaver.db')
AVATAR_DIR = os.path.join(DATA_DIR, 'avatares')
CACHE_DIR = os.path.join(tempfile.gettempdir(), 'whatssaver_cache')
CACHE_MAX = int(os.environ.get('WHATSSAVER_CACHE_MB') or 4096) * 1024 * 1024
CACHE_TTL = 24 * 3600
SCHEMA_VERSION = 2

NODE_MIN_MAJOR = 20
NODE_DIST = 'https://nodejs.org/dist/latest-v24.x/'
ZIP_WORKERS = 4
PREFETCH_WORKERS = 6
PREFETCH_MAX_BYTES = 25 * 1024 * 1024  # fotos maiores só quando abertas
ZIP_KEEP = 3600           # um .zip pronto fica disponível por 1 h
HISTORY_BATCH = 50        # o celular entrega no máximo 50 mensagens por pedido
HISTORY_WAIT = 40         # segundos esperando o celular responder cada lote
HISTORY_MAX_ROUNDS = 2000
ON_DEMAND = 6             # proto.HistorySync.HistorySyncType.ON_DEMAND
MIME_EXT = {
    'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif', 'image/heic': 'heic',
    'image/heif': 'heif', 'image/avif': 'avif', 'image/tiff': 'tif', 'image/bmp': 'bmp',
    'video/mp4': 'mp4', 'video/quicktime': 'mov', 'video/3gpp': '3gp', 'video/x-matroska': 'mkv',
    'video/webm': 'webm', 'video/x-msvideo': 'avi', 'video/mpeg': 'mpg',
}
# Formatos que o navegador não abre: a prévia é convertida para JPEG.
CONVERT_PREVIEW = {'heic', 'heif', 'tif', 'tiff'}
_NO_WINDOW = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


class WhatsSaverError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def _log_error(what):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, 'engine.log'), 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now():%Y-%m-%d %H:%M:%S}] {what}\n{traceback.format_exc()}\n')
    except OSError:
        pass


# =============================================================== instalação ===

_node_found = {}


def _node_version(exe):
    try:
        out = subprocess.run([exe, '--version'], capture_output=True, text=True, timeout=15, **_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r'v?(\d+)\.\d+', (out or '').strip())
    return (int(m.group(1)), out.strip()) if m else None


def _portable_nodes():
    if not os.path.isdir(RUNTIME_DIR):
        return []
    found = []
    for name in sorted(os.listdir(RUNTIME_DIR), reverse=True):
        exe = (os.path.join(RUNTIME_DIR, name, 'node.exe') if os.name == 'nt'
               else os.path.join(RUNTIME_DIR, name, 'bin', 'node'))
        if os.path.isfile(exe):
            found.append(exe)
    return found


def find_node():
    """Node >= 20: o de WHATSSAVER_NODE, o do sistema ou o portátil em bridge/runtime."""
    if _node_found.get('exe') and os.path.isfile(_node_found['exe']):
        return _node_found['exe'], _node_found['version']
    for exe in [os.environ.get('WHATSSAVER_NODE'), shutil.which('node')] + _portable_nodes():
        if not exe:
            continue
        v = _node_version(exe)
        if v and v[0] >= NODE_MIN_MAJOR:
            _node_found.update(exe=exe, version=v[1])
            return exe, v[1]
    return None, None


def deps_installed():
    return os.path.isfile(os.path.join(BRIDGE_DIR, 'node_modules', 'baileys', 'package.json'))


def _node_asset():
    system, machine = platform.system(), platform.machine().lower()
    arm = machine in ('arm64', 'aarch64')
    if system == 'Windows':
        return 'win-arm64.zip' if arm else 'win-x64.zip'
    if system == 'Darwin':
        return 'darwin-arm64.tar.gz' if arm else 'darwin-x64.tar.gz'
    if system == 'Linux':
        return 'linux-arm64.tar.xz' if arm else 'linux-x64.tar.xz'
    raise WhatsSaverError(f'Não há Node.js portátil para {system}: instale o Node.js 20 ou mais novo.')


def download_node(log=print):
    """Baixa o Node.js oficial (LTS 24) para bridge/runtime, conferindo o SHA-256."""
    suffix = _node_asset()
    with urllib.request.urlopen(NODE_DIST + 'SHASUMS256.txt', timeout=30) as resp:
        sums = resp.read().decode()
    for line in sums.splitlines():
        digest, _, name = line.strip().partition('  ')
        if name.startswith('node-v') and name.endswith('-' + suffix):
            break
    else:
        raise WhatsSaverError('Não achei o Node.js para este sistema no site oficial.')

    os.makedirs(RUNTIME_DIR, exist_ok=True)
    archive = os.path.join(RUNTIME_DIR, name)
    log(f'Baixando {name}...')
    sha = hashlib.sha256()
    with urllib.request.urlopen(NODE_DIST + name, timeout=60) as resp, open(archive + '.part', 'wb') as out:
        total, done, shown = int(resp.headers.get('Content-Length') or 0), 0, 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if total and done * 4 // total > shown:
                shown = done * 4 // total
                log(f'  {shown * 25}%')
    if sha.hexdigest() != digest:
        os.remove(archive + '.part')
        raise WhatsSaverError('O download do Node.js veio corrompido. Tente de novo.')
    os.replace(archive + '.part', archive)

    log('Extraindo o Node.js...')
    try:
        if name.endswith('.zip'):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(RUNTIME_DIR)
        else:
            with tarfile.open(archive) as tar:
                tar.extractall(RUNTIME_DIR, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
    finally:
        os.remove(archive)
    _node_found.clear()


def _npm_command(node):
    """O npm que acompanha o próprio Node (vale também para o portátil)."""
    base = os.path.dirname(node)
    for cli in (os.path.join(base, 'node_modules', 'npm', 'bin', 'npm-cli.js'),
                os.path.join(base, '..', 'lib', 'node_modules', 'npm', 'bin', 'npm-cli.js')):
        if os.path.isfile(cli):
            return [node, os.path.normpath(cli)]
    npm = shutil.which('npm')
    if npm:
        return [npm]
    raise WhatsSaverError('Não achei o npm junto do Node.js.')


def install_components(log=print):
    """Deixa o WhatsSaver pronto: Node.js (baixa um portátil se faltar) e as
    bibliotecas da ponte (npm install). Usado pelo botão do app e pelo INSTALAR.py."""
    node, version = find_node()
    if not node:
        log(f'Node.js {NODE_MIN_MAJOR}+ não encontrado: baixando uma cópia só para o WhatsSaver...')
        download_node(log)
        node, version = find_node()
        if not node:
            raise WhatsSaverError('Não consegui preparar o Node.js.')
    log(f'Node.js {version} ok. Instalando a biblioteca do WhatsApp (Baileys)...')
    env = dict(os.environ, PATH=os.path.dirname(node) + os.pathsep + os.environ.get('PATH', ''))
    proc = subprocess.Popen(_npm_command(node) + ['install', '--omit=dev', '--no-audit', '--no-fund', '--loglevel=error'],
                            cwd=BRIDGE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8', errors='replace', env=env, **_NO_WINDOW)
    for line in proc.stdout:
        if line.strip():
            log('  ' + line.rstrip())
    if proc.wait() != 0 or not deps_installed():
        raise WhatsSaverError('A instalação das bibliotecas falhou (npm install). Veja as mensagens acima.')
    log('Pronto! Componentes do WhatsSaver instalados.')


_setup = {'running': False, 'log': deque(maxlen=80), 'error': None}
_setup_lock = threading.Lock()


def start_install():
    with _setup_lock:
        if _setup['running']:
            return
        _setup.update(running=True, error=None)
        _setup['log'].clear()

    def run():
        try:
            install_components(_setup['log'].append)
        except Exception as e:
            _setup['error'] = str(e)
            _log_error('install')
        finally:
            _setup['running'] = False

    threading.Thread(target=run, daemon=True, name='whatssaver-install').start()


def setup_info():
    node, version = find_node()
    return {'node': version, 'deps': deps_installed(), 'installing': _setup['running'],
            'log': list(_setup['log']), 'error': _setup['error'],
            'ready': bool(node) and deps_installed() and not _setup['running']}


# ==================================================================== ponte ===

class _Bridge:
    """Processo Node com a conexão do WhatsApp. Nasce na primeira chamada e
    morre junto com o Flask (quando o stdin fecha, a ponte fecha)."""

    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.pending = {}
        self.seq = 0
        self.state = {'status': 'stopped'}
        self.opened = threading.Condition()

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def ensure(self):
        with self.lock:
            if self.running():
                return
            node, _ = find_node()
            if not node or not deps_installed():
                raise WhatsSaverError('Os componentes do WhatsSaver ainda não foram instalados.', 'setup')
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(os.path.join(DATA_DIR, 'bridge-stderr.log'), 'ab') as err:
                self.proc = subprocess.Popen(
                    [node, 'bridge.mjs'], cwd=BRIDGE_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=err, env=dict(os.environ, WHATSSAVER_DATA=DATA_DIR), **_NO_WINDOW)
            self.pending = {}
            self._set_state({'status': 'starting'})
            threading.Thread(target=self._read, args=(self.proc, self.pending), daemon=True,
                             name='whatssaver-bridge').start()

    def _set_state(self, state):
        with self.opened:
            self.state = state
            self.opened.notify_all()

    def _read(self, proc, pending):
        for raw in proc.stdout:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if 'id' in msg:
                slot = pending.pop(msg['id'], None)
                if slot:
                    slot[1] = msg
                    slot[0].set()
                continue
            try:
                if msg.get('ev') == 'state':
                    state = {k: msg.get(k) for k in ('status', 'qr', 'pairingCode', 'me', 'error')}
                    store.on_state(state)
                    self._set_state(state)
                elif msg.get('ev'):
                    store.apply(msg)
            except Exception:
                _log_error(f'evento {msg.get("ev")}')
        with self.lock:
            if self.proc is proc:
                self._set_state({'status': 'stopped',
                                 'error': 'A ponte com o WhatsApp fechou. Recarregue a página para reabrir.'})
        for slot in list(pending.values()):
            slot[1] = {'ok': False, 'error': 'A conexão com o WhatsApp caiu.', 'code': 'bridge_closed'}
            slot[0].set()
        pending.clear()

    def call(self, cmd, timeout=30, **args):
        self.ensure()
        done = threading.Event()
        slot = [done, None]
        with self.write_lock:
            self.seq += 1
            mid = self.seq
            pending = self.pending
            pending[mid] = slot
            try:
                self.proc.stdin.write((json.dumps({'id': mid, 'cmd': cmd, **args}) + '\n').encode())
                self.proc.stdin.flush()
            except (OSError, ValueError, AttributeError):
                pending.pop(mid, None)
                raise WhatsSaverError('A ponte com o WhatsApp não está respondendo.', 'bridge_closed')
        if not done.wait(timeout):
            pending.pop(mid, None)
            raise WhatsSaverError('O WhatsApp demorou demais para responder.', 'timeout')
        res = slot[1]
        if not res.get('ok'):
            raise WhatsSaverError(res.get('error') or 'Erro na ponte com o WhatsApp.', res.get('code'))
        return res.get('data') or {}

    def is_open(self):
        return self.running() and self.state.get('status') == 'open'

    def wait_open(self, timeout):
        """Espera a conexão abrir enquanto ela ainda está tentando (não fica
        esperando se o usuário desconectou ou precisa escanear o QR)."""
        end = time.time() + timeout
        with self.opened:
            while not self.is_open():
                if self.state.get('status') not in ('starting', 'connecting', 'reconnecting'):
                    return False
                left = end - time.time()
                if left <= 0:
                    return False
                self.opened.wait(min(left, 2))
        return True

    def stop(self):
        proc = self.proc
        if proc and proc.poll() is None:
            try:
                proc.stdin.close()  # a ponte salva a sessão e sai sozinha
                proc.wait(5)
            except Exception:
                proc.kill()


# ============================================================ utilidades ===

def _fold(text):
    return unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower()


def _user(jid):
    return (jid or '').split('@')[0].split(':')[0]


def _is_pn(jid):
    return (jid or '').endswith('@s.whatsapp.net')


def format_number(jid):
    digits = _user(jid)
    if not _is_pn(jid) or not digits.isdigit():
        return ''
    if digits.startswith('55') and len(digits) in (12, 13):
        return f'+55 {digits[2:4]} {digits[4:-4]}-{digits[-4:]}'
    return '+' + digits


def _safe_name(name, limit=80):
    name = unicodedata.normalize('NFC', name or '')
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip().strip('.')
    return name[:limit].rstrip(' .') or 'Conversa'


def _ext(row):
    name_ext = os.path.splitext(row['file_name'] or '')[1].lstrip('.').lower()
    if name_ext and len(name_ext) <= 5:
        return name_ext
    mime = (row['mimetype'] or '').split(';')[0].strip().lower()
    if mime in MIME_EXT:
        return MIME_EXT[mime]
    guessed = mimetypes.guess_extension(mime) if mime else None
    return guessed.lstrip('.') if guessed else ('jpg' if row['kind'] == 'image' else 'mp4')


def _file_name(row):
    ts = row['ts'] or 0
    stamp = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H.%M.%S') if ts else 'sem data'
    ext = _ext(row)
    if row['as_file'] and row['file_name']:
        return f'{stamp} {_safe_name(os.path.splitext(row["file_name"])[0], 100)}.{ext}'
    prefix = 'GIF' if row['variant'] == 'gif' else 'IMG' if row['kind'] == 'image' else 'VID'
    return f'{stamp} {prefix}-{_safe_name(row["id"][-6:], 12)}.{ext}'


def _qr_image(text):
    """QR como data URI (SVG pelo segno; PNG pelo qrcode se o segno faltar)."""
    try:
        import segno
        return segno.make(text, error='l').svg_data_uri(scale=6, border=2, dark='#0b141a', light='#ffffff')
    except ImportError:
        pass
    try:
        import io
        import qrcode
        buf = io.BytesIO()
        qrcode.make(text, border=2).save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return None


# ================================================================== banco ===

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    jid TEXT PRIMARY KEY,
    name TEXT,
    is_group INTEGER NOT NULL DEFAULT 0,
    last_ts INTEGER NOT NULL DEFAULT 0,
    oldest_ts INTEGER,
    oldest_key TEXT,
    history_end INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS contacts (
    jid TEXT PRIMARY KEY, name TEXT, notify TEXT, verified TEXT
);
CREATE TABLE IF NOT EXISTS lid_map (lid TEXT PRIMARY KEY, pn TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS media (
    chat TEXT NOT NULL,
    id TEXT NOT NULL,
    from_me INTEGER NOT NULL DEFAULT 0,
    sender TEXT,
    push_name TEXT,
    ts INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL,
    as_file INTEGER NOT NULL DEFAULT 0,
    variant TEXT,
    mimetype TEXT,
    file_name TEXT,
    size INTEGER,
    width INTEGER,
    height INTEGER,
    seconds INTEGER,
    caption TEXT,
    thumb BLOB,
    payload TEXT NOT NULL,
    error TEXT,
    error_code TEXT,
    PRIMARY KEY (chat, id)
);
CREATE INDEX IF NOT EXISTS media_chat_ts ON media (chat, ts DESC);
"""

MEDIA_COLUMNS = ('chat, id, from_me, sender, push_name, ts, kind, as_file, variant, mimetype, file_name, size, '
                 'width, height, seconds, caption, error, error_code, thumb IS NOT NULL AS has_thumb')


class _Store:
    """Índice local: conversas, contatos e mídias. Só a thread da ponte e os
    downloads escrevem (sob self.lock); as rotas do Flask só leem."""

    def __init__(self):
        self.lock = threading.RLock()
        self.lid = {}
        self.me = None
        self.ready = False
        self.sync = {'active': False, 'progress': None, 'last': 0, 'media': 0, 'chunks': 0}

    # ---- conexão ----
    def _connect(self):
        c = sqlite3.connect(DB_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def db(self):
        if not self.ready:
            with self.lock:
                if not self.ready:
                    os.makedirs(DATA_DIR, exist_ok=True)
                    with closing(self._connect()) as c:
                        c.execute('PRAGMA journal_mode=WAL')
                        if c.execute('PRAGMA user_version').fetchone()[0] < SCHEMA_VERSION:
                            # A 1ª versão guardava os arquivos numa pasta; o índice é refeito pelo celular.
                            c.executescript('DROP TABLE IF EXISTS media; DROP TABLE IF EXISTS chats; '
                                            'DROP TABLE IF EXISTS contacts; DROP TABLE IF EXISTS lid_map; '
                                            'DROP TABLE IF EXISTS saved;')
                            c.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
                        c.executescript(SCHEMA)
                        self.lid = {r['lid']: r['pn'] for r in c.execute('SELECT lid, pn FROM lid_map')}
                        # Antes essas mídias eram marcadas como "corrompidas"; o motivo real é outro.
                        c.execute("UPDATE media SET error_code = 'phone_only', error = ? WHERE error_code = 'corrupt'",
                                  (wmedia.PHONE_ONLY,))
                        c.commit()
                    self.ready = True
        return closing(self._connect())

    def canon(self, jid):
        """Mesma conversa pode chegar pelo número ou pelo LID (id anônimo do
        WhatsApp); quando o par é conhecido, tudo fica no número."""
        return self.lid.get(jid, jid) if jid else jid

    def wipe(self):
        """Apaga o índice (conversas, contatos, mídias) e o cache."""
        with self.lock:
            if os.path.exists(DB_PATH):
                with self.db() as c:
                    with c:
                        for table in ('media', 'chats', 'contacts', 'lid_map'):
                            c.execute(f'DELETE FROM {table}')
                    c.execute('VACUUM')
            self.lid = {}
            self.me = None
            self.sync = {'active': False, 'progress': None, 'last': 0, 'media': 0, 'chunks': 0}
            shutil.rmtree(AVATAR_DIR, ignore_errors=True)
            cache.clear()

    # ---- eventos da ponte ----
    def on_state(self, state):
        if state.get('status') == 'logged_out':
            # Desconectado (aqui ou pelo celular): outra conta pode entrar depois.
            zips.cancel_all()
            history.stop()
            prefetch.stop()
            self.wipe()
            return
        me = state.get('me')
        self.me = me
        if me and me.get('lid') and me.get('id'):
            self.apply({'ev': 'mappings', 'mappings': [{'lid': me['lid'], 'pn': me['id']}]})

    def apply(self, msg):
        ev = msg.get('ev')
        if ev not in ('history', 'messages', 'contacts', 'chats', 'mappings', 'deleted', 'history_status'):
            return
        media_by_chat = {}
        with self.lock, self.db() as c:
            with c:
                self._mappings(c, msg.get('mappings'))
                if ev in ('history', 'contacts'):
                    self._contacts(c, msg.get('contacts'))
                if ev in ('history', 'chats'):
                    self._chats(c, msg.get('chats'))
                if ev in ('history', 'messages'):
                    self._bounds(c, msg.get('bounds'))
                    media_by_chat = self._media(c, msg.get('media'))
                if ev == 'deleted':
                    for d in msg.get('items') or []:
                        c.execute('DELETE FROM media WHERE chat = ? AND id = ?', (self.canon(d.get('chat')), d.get('id')))
        if ev == 'history':
            if msg.get('syncType') == ON_DEMAND:
                history.on_demand(msg.get('bounds') or [], media_by_chat)
            else:
                s = self.sync
                s.update(active=True, last=time.time(), chunks=s['chunks'] + 1,
                         media=s['media'] + sum(media_by_chat.values()))
                if msg.get('progress') is not None:
                    s['progress'] = msg['progress']
                if msg.get('progress') == 100:
                    s['active'] = False
        elif ev == 'history_status' and msg.get('status') == 'complete' and msg.get('syncType') != ON_DEMAND:
            self.sync['active'] = False

    def _mappings(self, c, items):
        for m in items or []:
            lid, pn = m.get('lid'), m.get('pn')
            if not lid or not pn or lid == pn or not lid.endswith('lid') or pn.endswith('lid'):
                continue
            if self.lid.get(lid) == pn:
                continue
            c.execute('INSERT OR REPLACE INTO lid_map (lid, pn) VALUES (?, ?)', (lid, pn))
            self.lid[lid] = pn
            self._merge(c, lid, pn)

    def _merge(self, c, old, new):
        row = c.execute('SELECT * FROM chats WHERE jid = ?', (old,)).fetchone()
        if row:
            c.execute('INSERT INTO chats (jid) VALUES (?) ON CONFLICT(jid) DO NOTHING', (new,))
            older = 'oldest_ts IS NULL OR (:ts IS NOT NULL AND :ts < oldest_ts)'
            c.execute(f'''UPDATE chats SET name = COALESCE(name, :name), is_group = MAX(is_group, :grp),
                              last_ts = MAX(last_ts, :last),
                              oldest_key = CASE WHEN {older} THEN :key ELSE oldest_key END,
                              oldest_ts = CASE WHEN {older} THEN :ts ELSE oldest_ts END,
                              history_end = MIN(history_end, :end)
                          WHERE jid = :jid''',
                      {'name': row['name'], 'grp': row['is_group'], 'last': row['last_ts'],
                       'key': row['oldest_key'], 'ts': row['oldest_ts'], 'end': row['history_end'], 'jid': new})
            c.execute('DELETE FROM chats WHERE jid = ?', (old,))
        c.execute('UPDATE OR IGNORE media SET chat = ? WHERE chat = ?', (new, old))
        c.execute('DELETE FROM media WHERE chat = ?', (old,))
        c.execute('UPDATE media SET sender = ? WHERE sender = ?', (new, old))
        ct = c.execute('SELECT name, notify, verified FROM contacts WHERE jid = ?', (old,)).fetchone()
        if ct:
            self._upsert_contact(c, new, ct['name'], ct['notify'], ct['verified'])

    def _upsert_contact(self, c, jid, name, notify, verified):
        c.execute('''INSERT INTO contacts (jid, name, notify, verified) VALUES (?, ?, ?, ?)
                     ON CONFLICT(jid) DO UPDATE SET name = COALESCE(excluded.name, contacts.name),
                         notify = COALESCE(excluded.notify, contacts.notify),
                         verified = COALESCE(excluded.verified, contacts.verified)''',
                  (jid, name or None, notify or None, verified or None))

    def _contacts(self, c, items):
        for ct in items or []:
            if ct.get('lid') and ct.get('pn'):
                self._mappings(c, [{'lid': ct['lid'], 'pn': ct['pn']}])
            if ct.get('name') or ct.get('notify') or ct.get('verified'):
                self._upsert_contact(c, self.canon(ct['jid']), ct.get('name'), ct.get('notify'), ct.get('verified'))

    def _chats(self, c, items):
        for ch in items or []:
            if ch.get('lid') and ch.get('pn'):
                self._mappings(c, [{'lid': ch['lid'], 'pn': ch['pn']}])
            jid = self.canon(ch['jid'])
            c.execute('''INSERT INTO chats (jid, name, is_group, last_ts) VALUES (?, ?, ?, ?)
                         ON CONFLICT(jid) DO UPDATE SET name = COALESCE(excluded.name, chats.name),
                             is_group = MAX(chats.is_group, excluded.is_group),
                             last_ts = MAX(chats.last_ts, excluded.last_ts)''',
                      (jid, ch.get('name'), int(bool(ch.get('group')) or jid.endswith('@g.us')), ch.get('ts') or 0))

    def _bounds(self, c, items):
        for b in items or []:
            jid = self.canon(b['jid'])
            oldest = b.get('oldest') or {}
            c.execute('''INSERT INTO chats (jid, is_group, last_ts, oldest_ts, oldest_key) VALUES (?, ?, ?, ?, ?)
                         ON CONFLICT(jid) DO UPDATE SET last_ts = MAX(chats.last_ts, excluded.last_ts),
                             oldest_key = CASE WHEN excluded.oldest_ts IS NOT NULL AND
                                 (chats.oldest_ts IS NULL OR excluded.oldest_ts < chats.oldest_ts)
                                 THEN excluded.oldest_key ELSE chats.oldest_key END,
                             oldest_ts = CASE WHEN excluded.oldest_ts IS NOT NULL AND
                                 (chats.oldest_ts IS NULL OR excluded.oldest_ts < chats.oldest_ts)
                                 THEN excluded.oldest_ts ELSE chats.oldest_ts END''',
                      (jid, int(jid.endswith('@g.us')), b.get('newest') or 0, oldest.get('ts'),
                       json.dumps(oldest['key']) if oldest.get('key') else None))

    def _media(self, c, items):
        per_chat = {}
        rows = []
        for m in items or []:
            chat = self.canon(m['chat'])
            sender = self.canon(m.get('sender'))
            variant = 'gif' if m.get('gif') else 'ptv' if m.get('ptv') else None
            rows.append((chat, m['id'], int(bool(m.get('fromMe'))), sender, m.get('pushName'), m.get('ts') or 0,
                         m['kind'], int(bool(m.get('asFile'))), variant, m.get('mimetype'), m.get('fileName'),
                         m.get('size'), m.get('width'), m.get('height'), m.get('seconds'), m.get('caption'),
                         base64.b64decode(m['thumb']) if m.get('thumb') else None, json.dumps(m['payload'])))
            per_chat[chat] = per_chat.get(chat, 0) + 1
            if sender and m.get('pushName'):
                self._upsert_contact(c, sender, None, m['pushName'], None)
        # Mensagem repetida mantém os dados de download que já temos (podem ter
        # vindo de um reenvio do celular, mais novos que os da mensagem).
        c.executemany('''INSERT INTO media (chat, id, from_me, sender, push_name, ts, kind, as_file, variant, mimetype,
                             file_name, size, width, height, seconds, caption, thumb, payload)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                         ON CONFLICT(chat, id) DO UPDATE SET thumb = COALESCE(media.thumb, excluded.thumb),
                             caption = COALESCE(media.caption, excluded.caption),
                             push_name = COALESCE(excluded.push_name, media.push_name)''', rows)
        # Toda mídia precisa de uma conversa, senão não aparece na lista.
        c.executemany('INSERT INTO chats (jid, is_group) VALUES (?, ?) ON CONFLICT(jid) DO NOTHING',
                      [(jid, int(jid.endswith('@g.us'))) for jid in per_chat])
        return per_chat

    # ---- nomes ----
    def _name(self, jid, chat_name=None, contact_name=None, notify=None, verified=None, is_group=False):
        me = self.me or {}
        if jid and jid in (me.get('id'), me.get('lid')):
            return 'Você'
        if is_group:
            return chat_name or contact_name or 'Grupo sem nome'
        return contact_name or chat_name or notify or verified or format_number(jid) or 'Contato sem nome'

    def _chat_dict(self, r):
        jid = r['jid']
        return {
            'jid': jid,
            'name': self._name(jid, r['chat_name'], r['contact_name'], r['notify'], r['verified'], bool(r['is_group'])),
            'number': format_number(jid),
            'group': bool(r['is_group']),
            'last_ts': r['last_ts'] or r['last_media'] or 0,
            'total': r['total'], 'photos': r['photos'], 'videos': r['videos'], 'files': r['files'],
            'failed': r['failed'], 'phone_only': r['phone_only'], 'last_media': r['last_media'],
            'oldest_ts': r['oldest_ts'], 'history_end': bool(r['history_end']),
        }

    _CHAT_SQL = '''
        SELECT ch.jid, ch.name AS chat_name, ch.is_group, ch.last_ts, ch.oldest_ts, ch.history_end,
               ct.name AS contact_name, ct.notify, ct.verified,
               COUNT(m.id) AS total,
               COALESCE(SUM(m.kind = 'image' AND m.as_file = 0), 0) AS photos,
               COALESCE(SUM(m.kind = 'video' AND m.as_file = 0), 0) AS videos,
               COALESCE(SUM(m.as_file = 1), 0) AS files,
               COALESCE(SUM(m.error IS NOT NULL), 0) AS failed,
               COALESCE(SUM(m.error_code = 'phone_only'), 0) AS phone_only,
               MAX(m.ts) AS last_media
        FROM chats ch
        LEFT JOIN contacts ct ON ct.jid = ch.jid
        LEFT JOIN media m ON m.chat = ch.jid
    '''

    # ---- consultas ----
    def list_chats(self, query='', scope='media'):
        with self.db() as c:
            rows = c.execute(self._CHAT_SQL + ' GROUP BY ch.jid').fetchall()
        chats = [self._chat_dict(r) for r in rows]
        if scope == 'media':
            chats = [x for x in chats if x['total']]
        elif scope == 'groups':
            chats = [x for x in chats if x['group']]
        elif scope == 'contacts':
            chats = [x for x in chats if not x['group']]
        q = _fold(query).strip()
        if q:
            digits = re.sub(r'\D', '', q)
            chats = [x for x in chats if q in _fold(x['name']) or (digits and digits in x['jid'])]
        chats.sort(key=lambda x: x['last_ts'] or 0, reverse=True)
        return chats

    def chat(self, jid):
        with self.db() as c:
            r = c.execute(self._CHAT_SQL + ' WHERE ch.jid = ? GROUP BY ch.jid', (jid,)).fetchone()
            if not r:
                raise WhatsSaverError('Conversa não encontrada.')
            info = self._chat_dict(r)
            who = c.execute('''SELECT COALESCE(SUM(from_me = 1), 0) AS mine, COALESCE(SUM(from_me = 0), 0) AS theirs
                               FROM media WHERE chat = ?''', (jid,)).fetchone()
        info.update(mine=who['mine'], theirs=who['theirs'])
        return info

    def _filters(self, jid, kind='all', who='all'):
        where, params = ['chat = ?'], [jid]
        where += {'photo': ["kind = 'image'", 'as_file = 0'], 'video': ["kind = 'video'", 'as_file = 0'],
                  'file': ['as_file = 1']}.get(kind, [])
        where += {'me': ['from_me = 1'], 'them': ['from_me = 0']}.get(who, [])
        return ' AND '.join(where), params

    def list_media(self, jid, kind='all', who='all', offset=0, limit=120):
        where, params = self._filters(jid, kind, who)
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        with self.db() as c:
            total = c.execute(f'SELECT COUNT(*) FROM media WHERE {where}', params).fetchone()[0]
            rows = c.execute(f'SELECT {MEDIA_COLUMNS} FROM media WHERE {where} ORDER BY ts DESC, id LIMIT ? OFFSET ?',
                             params + [limit, offset]).fetchall()
            senders = {r['sender'] for r in rows if r['sender']}
            names = {}
            if senders:
                marks = ','.join('?' * len(senders))
                for ct in c.execute(f'SELECT jid, name, notify, verified FROM contacts WHERE jid IN ({marks})', list(senders)):
                    names[ct['jid']] = ct['name'] or ct['notify'] or ct['verified']
        items = [self._item(r, names) for r in rows]
        return {'items': items, 'total': total, 'offset': offset,
                'next': offset + len(items) if offset + len(items) < total else None}

    def _item(self, r, names):
        sender = None
        if not r['from_me'] and r['sender']:
            sender = names.get(r['sender']) or r['push_name'] or format_number(r['sender']) or None
        return {
            'id': r['id'], 'ts': r['ts'], 'kind': r['kind'], 'as_file': bool(r['as_file']), 'variant': r['variant'],
            'mimetype': r['mimetype'], 'file_name': r['file_name'], 'ext': _ext(r), 'size': r['size'],
            'width': r['width'], 'height': r['height'], 'seconds': r['seconds'], 'caption': r['caption'],
            'from_me': bool(r['from_me']), 'sender': sender, 'thumb': bool(r['has_thumb']),
            'name': _file_name(r), 'cached': cache.has(r['chat'], r['id'], _ext(r)),
            'error': r['error'], 'error_code': r['error_code'],
        }

    def ids(self, jid, kind='all', who='all'):
        where, params = self._filters(jid, kind, who)
        with self.db() as c:
            return [r[0] for r in c.execute(f'SELECT id FROM media WHERE {where} ORDER BY ts, id', params)]

    def row(self, jid, mid):
        with self.db() as c:
            return c.execute('SELECT * FROM media WHERE chat = ? AND id = ?', (jid, mid)).fetchone()

    def chat_row(self, jid):
        with self.db() as c:
            return c.execute('SELECT * FROM chats WHERE jid = ?', (jid,)).fetchone()

    def set_history_end(self, jid):
        with self.lock, self.db() as c, c:
            c.execute('UPDATE chats SET history_end = 1 WHERE jid = ?', (jid,))

    def set_error(self, jid, mid, message, code):
        with self.lock, self.db() as c, c:
            c.execute('UPDATE media SET error = ?, error_code = ? WHERE chat = ? AND id = ?', (message, code, jid, mid))

    def media_ok(self, jid, mid, refreshed):
        """Limpa o erro e, se o celular reenviou, guarda o endereço novo."""
        with self.lock, self.db() as c, c:
            if refreshed:
                r = c.execute('SELECT payload FROM media WHERE chat = ? AND id = ?', (jid, mid)).fetchone()
                if r:
                    payload = json.loads(r['payload'])
                    payload['media'].update({k: v for k, v in refreshed.items() if v})
                    c.execute('UPDATE media SET payload = ? WHERE chat = ? AND id = ?', (json.dumps(payload), jid, mid))
            c.execute('UPDATE media SET error = NULL, error_code = NULL WHERE chat = ? AND id = ?', (jid, mid))

    def prefetch_ids(self, jid):
        """Fotos da conversa que ainda não estão no cache, das mais novas para as mais antigas."""
        with self.db() as c:
            rows = c.execute('''SELECT id, kind, mimetype, file_name, error_code FROM media
                                WHERE chat = ? AND kind = 'image' AND (size IS NULL OR size <= ?)
                                  AND (error_code IS NULL OR error_code != 'phone_only')
                                ORDER BY ts DESC, id''', (jid, PREFETCH_MAX_BYTES)).fetchall()
        return [r['id'] for r in rows if not cache.has(jid, r['id'], _ext(r))]

    def stats(self):
        with self.db() as c:
            r = c.execute('SELECT COUNT(*) AS media, COUNT(DISTINCT chat) AS chats FROM media').fetchone()
        return dict(r)

    def chat_name(self, jid):
        with self.db() as c:
            r = c.execute(self._CHAT_SQL + ' WHERE ch.jid = ? GROUP BY ch.jid', (jid,)).fetchone()
        return self._chat_dict(r)['name'] if r else (format_number(jid) or 'WhatsApp')


# ================================================================== cache ===

class _Cache:
    """Mídias já baixadas e conferidas, num diretório temporário do sistema.
    Serve o visualizador (inclusive os saltos no vídeo), o botão de download e
    o .zip; some sozinho (24 h ou acima do limite, o que foi usado há mais
    tempo sai primeiro). Arquivos de um .zip em preparo não são apagados."""

    def __init__(self):
        self.pinned = Counter()
        self.lock = threading.Lock()
        self.pruned_at = 0

    @staticmethod
    def base(jid, mid):
        return os.path.join(CACHE_DIR, hashlib.sha1(f'{jid}/{mid}'.encode()).hexdigest())

    def path(self, jid, mid, ext):
        return f'{self.base(jid, mid)}.{ext}'

    def has(self, jid, mid, ext):
        return os.path.isfile(self.path(jid, mid, ext))

    def thumb_path(self, jid, mid):
        return self.base(jid, mid) + '.thumb.jpg'

    @staticmethod
    def touch(path):
        try:
            os.utime(path)
        except OSError:
            pass

    def pin(self, path):
        with self.lock:
            self.pinned[path] += 1

    def unpin(self, path):
        with self.lock:
            self.pinned[path] -= 1
            if self.pinned[path] <= 0:
                del self.pinned[path]

    def prune(self, force=False):
        if not force and time.time() - self.pruned_at < 60:
            return
        self.pruned_at = time.time()
        try:
            entries = []
            for name in os.listdir(CACHE_DIR):
                full = os.path.join(CACHE_DIR, name)
                st = os.stat(full)
                entries.append((st.st_mtime, st.st_size, full))
        except OSError:
            return
        total = sum(e[1] for e in entries)
        now = time.time()
        with self.lock:
            pinned = set(self.pinned)
        for mtime, size, full in sorted(entries):
            stale = now - mtime > CACHE_TTL
            leftover = full.endswith(('.enc', '.part')) and now - mtime > 3600
            if full in pinned or not (stale or leftover or total > CACHE_MAX):
                continue
            try:
                os.remove(full)
                total -= size
            except OSError:
                pass

    def clear(self):
        shutil.rmtree(CACHE_DIR, ignore_errors=True)


def _make_thumb(src, out, kind):
    """Miniatura boa a partir do arquivo (a que vem na mensagem é pequena e borrada)."""
    if kind == 'image':
        try:
            from PIL import Image, ImageOps
            _register_heif()
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((480, 480))
                im.convert('RGB').save(out, 'JPEG', quality=82)
        except Exception:
            pass
        return
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return
    for seek in (['-ss', '0.5'], []):
        try:
            subprocess.run([ffmpeg, '-nostdin', '-y', '-loglevel', 'error', *seek, '-i', src, '-frames:v', '1',
                            '-vf', 'scale=480:480:force_original_aspect_ratio=decrease', out],
                           capture_output=True, timeout=60, **_NO_WINDOW)
        except (OSError, subprocess.SubprocessError):
            return
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            return


def _register_heif():
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        return True
    except ImportError:
        return False


def ensure_media(jid, mid, cancel=None, allow_reupload=True):
    """Garante a mídia baixada e conferida no cache. Devolve (linha, caminho).
    Sem `allow_reupload`, desiste em vez de pedir o reenvio ao celular."""
    row = store.row(jid, mid)
    if not row:
        raise WhatsSaverError('Mídia não encontrada (a conversa pode ter sido atualizada).', 'not_found')
    dest = cache.path(jid, mid, _ext(row))
    with wmedia.item_lock(dest):
        if os.path.isfile(dest):
            cache.touch(dest)
            return row, dest
        os.makedirs(CACHE_DIR, exist_ok=True)
        payload = json.loads(row['payload'])

        def reupload():
            if not allow_reupload:
                raise wmedia.MediaError('Precisa pedir ao celular.', 'needs_phone')
            if not bridge.is_open() and not bridge.wait_open(30):
                raise wmedia.MediaError('O arquivo saiu do servidor do WhatsApp e, para pedir o reenvio ao celular, '
                                        'o WhatsSaver precisa estar conectado.', 'offline')
            try:
                return bridge.call('reupload', timeout=90, key=payload['key'], mediaKey=payload['media']['mediaKey'])
            except WhatsSaverError as e:
                raise wmedia.MediaError(str(e), e.code or 'reupload_failed')

        try:
            refreshed = wmedia.fetch(payload, dest, reupload, cancel)
        except wmedia.MediaError as e:
            if e.code not in ('cancelled', 'needs_phone'):
                store.set_error(jid, mid, str(e), e.code)
            raise WhatsSaverError(str(e), e.code)
        except Exception as e:
            _log_error('fetch')
            raise WhatsSaverError(f'Erro inesperado ao baixar: {e}', 'error')
        store.media_ok(jid, mid, refreshed)
        _make_thumb(dest, cache.thumb_path(jid, mid), row['kind'])
    cache.prune()
    return row, dest


def _preview(path):
    """HEIC/TIFF viram JPEG para o navegador conseguir mostrar."""
    ext = os.path.splitext(path)[1].lstrip('.').lower()
    if ext not in CONVERT_PREVIEW:
        return path, None
    out = path + '.preview.jpg'
    if os.path.isfile(out):
        return out, 'image/jpeg'
    if not _register_heif() and ext in ('heic', 'heif'):
        return path, None
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((2560, 2560))
            im.convert('RGB').save(out, 'JPEG', quality=88)
        return out, 'image/jpeg'
    except Exception:
        return path, None


# ==================================================================== zip ===

class _Sink:
    """Destino do zipfile que só acumula bytes, para o .zip sair em streaming."""

    def __init__(self):
        self.parts = []

    def write(self, data):
        self.parts.append(bytes(data))
        return len(data)

    def flush(self):
        pass

    def take(self):
        data = b''.join(self.parts)
        self.parts.clear()
        return data


def _missing_report(errors):
    """Texto do LEIA que vai no .zip: o que faltou, agrupado pelo motivo."""
    def line(row, message=None):
        when = datetime.fromtimestamp(row['ts']).strftime('%d/%m/%Y %H:%M') if row and row['ts'] else '?'
        what = (row['file_name'] or ('foto' if row['kind'] == 'image' else 'vídeo')) if row else '?'
        return f'{when}  {what}' + (f': {message}' if message else '')

    errors = sorted(errors, key=lambda e: e[0]['ts'] if e[0] else 0)
    phone = [e for e in errors if e[2] == 'phone_only']
    other = [e for e in errors if e[2] != 'phone_only']
    out = []
    if phone:
        out += [f'{len(phone)} mídia(s) antiga(s) que estão só no celular', '',
                'O arquivo original já saiu do servidor do WhatsApp. O WhatsSaver pediu ao celular',
                'para reenviar e ele reenviou, mas protegido com uma chave nova que o WhatsApp não',
                'repassa para aparelhos conectados (acontece com mídias antigas depois que o WhatsApp',
                'mudou o jeito de identificar as conversas). Não é arquivo estragado: ele existe no celular.',
                '',
                'Como salvar essas pelo celular:',
                '  * Abra a foto ou o vídeo no WhatsApp do celular e toque em Compartilhar ou Salvar.',
                '  * Ou exporte a conversa: no celular, abra a conversa > Mais > Exportar conversa > Incluir mídia.',
                '  * No Android, os arquivos também ficam em Android/media/com.whatsapp/WhatsApp/Media',
                '    (dá para copiar pelo cabo USB).',
                '',
                'Datas dessas mídias:', ''] + [line(e[0]) for e in phone] + ['']
    if other:
        out += [f'{len(other)} mídia(s) que não puderam ser baixadas por outros motivos:', '']
        out += [line(e[0], e[1]) for e in other] + ['']
    return '\n'.join(out)


class _ZipJobs:
    """'Baixar tudo': baixa e confere as mídias em paralelo (a página acompanha
    o progresso) e depois entrega um .zip montado em streaming a partir do cache."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs = {}

    def start(self, jid, ids, label):
        self._cleanup()
        if not ids:
            raise WhatsSaverError('Nada para baixar com esses filtros.')
        job = {'id': uuid.uuid4().hex[:12], 'jid': jid, 'ids': ids, 'label': label, 'state': 'preparing',
               'total': len(ids), 'done': 0, 'failed': 0, 'bytes': 0, 'errors': [], 'files': {},
               'cancel': threading.Event(), 'created': time.time()}
        with self.lock:
            self.jobs[job['id']] = job
        threading.Thread(target=self._run, args=(job,), daemon=True, name='whatssaver-zip').start()
        return self.status(job['id'])

    def _one(self, job, mid):
        if job['cancel'].is_set():
            return
        row = store.row(job['jid'], mid)
        try:
            if row and row['error_code'] == 'phone_only' and not cache.has(job['jid'], mid, _ext(row)):
                # O celular já mostrou que não entrega essa: pedir de novo só atrasa o .zip.
                raise WhatsSaverError(row['error'], 'phone_only')
            row, path = ensure_media(job['jid'], mid, job['cancel'])
        except WhatsSaverError as e:
            if e.code == 'cancelled':
                return
            with self.lock:
                job['failed'] += 1
                job['errors'].append((row, str(e), e.code))
            return
        cache.pin(path)
        with self.lock:
            job['files'][mid] = (path, row)
            job['done'] += 1
            job['bytes'] += os.path.getsize(path)

    def _run(self, job):
        try:
            with ThreadPoolExecutor(ZIP_WORKERS) as pool:
                list(pool.map(lambda mid: self._one(job, mid), job['ids']))
            job['state'] = 'cancelled' if job['cancel'].is_set() else 'ready' if job['files'] else 'failed'
        except Exception:
            _log_error('zip')
            job['state'] = 'failed'
        job['finished'] = time.time()
        if job['state'] != 'ready':
            self._release(job)

    def _release(self, job):
        files, job['files'] = job['files'], {}
        for path, _ in files.values():
            cache.unpin(path)

    def _cleanup(self):
        now = time.time()
        with self.lock:
            old = [j for j in self.jobs.values() if j['state'] != 'preparing' and now - j.get('finished', now) > ZIP_KEEP]
            for j in old:
                self.jobs.pop(j['id'], None)
        for j in old:
            self._release(j)

    def status(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            raise WhatsSaverError('Esse .zip não existe mais. Peça de novo.', 'gone')
        with self.lock:
            return {'id': job['id'], 'jid': job['jid'], 'state': job['state'], 'total': job['total'],
                    'done': job['done'], 'failed': job['failed'], 'bytes': job['bytes'],
                    'last_error': job['errors'][-1][1] if job['errors'] else None,
                    'phone_only': sum(1 for e in job['errors'] if e[2] == 'phone_only'),
                    'filename': job['label'] + '.zip'}

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if job:
            job['cancel'].set()
            if job['state'] == 'ready':
                job['state'] = 'cancelled'
                self._release(job)

    def cancel_all(self):
        for job_id in list(self.jobs):
            self.cancel(job_id)

    def stream(self, job_id):
        """(gerador de bytes do .zip, nome do arquivo)."""
        job = self.jobs.get(job_id)
        if not job or job['state'] != 'ready':
            raise WhatsSaverError('Esse .zip não está pronto (ou já expirou).', 'not_ready')
        files = sorted(job['files'].values(), key=lambda f: (f[1]['ts'], f[1]['id']))  # ordem cronológica
        errors = list(job['errors'])

        def generate():
            sink = _Sink()
            used = set()
            with zipfile.ZipFile(sink, 'w', zipfile.ZIP_STORED, allowZip64=True) as zf:
                for path, row in files:
                    name = _file_name(row)
                    base, ext = os.path.splitext(name)
                    n = 1
                    while name in used:
                        n += 1
                        name = f'{base} ({n}){ext}'
                    used.add(name)
                    stamp = datetime.fromtimestamp(row['ts'] or time.time()).timetuple()[:6]
                    info = zipfile.ZipInfo(name, date_time=max(stamp, (1980, 1, 1, 0, 0, 0)))
                    with open(path, 'rb') as src, zf.open(info, 'w', force_zip64=True) as dst:
                        while True:
                            chunk = src.read(1 << 20)
                            if not chunk:
                                break
                            dst.write(chunk)
                            data = sink.take()
                            if data:
                                yield data
                if errors:
                    zf.writestr('LEIA - itens que faltaram.txt', _missing_report(errors))
            data = sink.take()
            if data:
                yield data

        return generate(), job['label'] + '.zip'


# ======================================================== histórico antigo ===

class _History:
    """Pede ao celular, em lotes de 50, as mensagens anteriores à mais antiga
    que já conhecemos de uma conversa. Uma conversa por vez: a resposta do
    celular não diz com certeza a qual pedido pertence."""

    def __init__(self):
        self.lock = threading.Lock()
        self.job = None
        self.thread = None

    def start(self, jid):
        with self.lock:
            if self.job and self.job['running']:
                if self.job['chat'] == jid:
                    return self.status()
                # Abriu outra conversa: a busca passa para ela.
                self._stop_locked()
                if self.thread:
                    self.thread.join(5)
            row = store.chat_row(jid)
            self.job = {'chat': jid, 'running': True, 'stop': False, 'waiter': None, 'rounds': 0, 'messages': 0,
                        'media': 0, 'oldest_ts': row['oldest_ts'] if row else None, 'status': 'running', 'message': None}
            self.thread = threading.Thread(target=self._run, args=(self.job,), daemon=True, name='whatssaver-history')
            self.thread.start()
        return self.status()

    def _stop_locked(self):
        job = self.job
        if job and job['running']:
            job['stop'] = True
            if job['waiter']:
                job['waiter']['event'].set()

    def stop(self):
        with self.lock:
            self._stop_locked()
        return self.status()

    def status(self):
        job = self.job
        return {k: v for k, v in job.items() if k not in ('stop', 'waiter')} if job else None

    def on_demand(self, bounds, media_by_chat):
        w = self.job and self.job['waiter']
        if w:
            w['bounds'] = bounds
            w['media'] = media_by_chat
            w['event'].set()

    def _run(self, job):
        jid = job['chat']
        try:
            for _ in range(HISTORY_MAX_ROUNDS):
                if job['stop']:
                    break
                row = store.chat_row(jid)
                if not row or not row['oldest_key']:
                    job.update(status='error', message='Ainda não conheço nenhuma mensagem dessa conversa. '
                               'Espere a sincronização com o celular terminar e tente de novo.')
                    break
                before = row['oldest_ts']
                waiter = job['waiter'] = {'event': threading.Event(), 'bounds': None, 'media': {}}
                bridge.call('fetch_history', key=json.loads(row['oldest_key']), ts=before, count=HISTORY_BATCH)
                answered = waiter['event'].wait(HISTORY_WAIT)
                job['waiter'] = None
                if job['stop']:
                    break
                if not answered:
                    job.update(status='timeout', message=(
                        'O celular não respondeu. Ele precisa estar ligado, com internet e com o WhatsApp '
                        'funcionando. Se a busca já vinha trazendo mensagens, talvez o começo da conversa '
                        'já tenha sido alcançado.'))
                    break
                got = sum(b.get('count') or 0 for b in waiter['bounds'] or [] if store.canon(b.get('jid')) == jid)
                row = store.chat_row(jid)
                after = row['oldest_ts'] if row else None
                job['rounds'] += 1
                job['messages'] += got
                job['media'] += waiter['media'].get(jid, 0)
                if not got or after is None or (before is not None and after >= before):
                    store.set_history_end(jid)
                    job.update(status='done', message='Chegou ao começo da conversa: não há mensagens mais antigas no celular.')
                    break
                job['oldest_ts'] = after
                time.sleep(0.2)
            else:
                job.update(status='stopped', message='Pausei depois de muitos lotes. Clique de novo para continuar.')
            if job['stop']:
                job.update(status='stopped', message='Busca interrompida.')
        except WhatsSaverError as e:
            job.update(status='error', message=str(e))
        except Exception as e:
            job.update(status='error', message=f'Erro inesperado: {e}')
            _log_error('history')
        finally:
            job['waiter'] = None
            job['running'] = False


class _Prefetch:
    """Ao abrir uma conversa, traz as fotos dela para o cache (das mais novas
    para as mais antigas) e gera miniaturas nítidas; a página troca cada card
    assim que a foto chega. Só uma conversa por vez, e sem pedir reenvio ao
    celular: o que depende disso fica para quando a foto for aberta."""

    def __init__(self):
        self.lock = threading.Lock()
        self.job = None

    def start(self, jid):
        with self.lock:
            job = self.job
            if job and job['jid'] == jid and job['running']:
                return self.status(jid)
            if job:
                job['cancel'].set()
            ids = store.prefetch_ids(jid)
            job = self.job = {'jid': jid, 'total': len(ids), 'done': 0, 'skipped': 0, 'phone_only': 0,
                              'ready': [], 'marked': [], 'running': bool(ids), 'cancel': threading.Event()}
            if ids:
                threading.Thread(target=self._run, args=(job, ids), daemon=True, name='whatssaver-prefetch').start()
        return self.status(jid)

    def _one(self, job, mid):
        if job['cancel'].is_set():
            return
        try:
            # Só o que já está no servidor. O que precisaria de reenvio fica para
            # quando a foto for aberta - aí o reenvio é tentado de verdade.
            ensure_media(job['jid'], mid, job['cancel'], allow_reupload=False)
        except WhatsSaverError as e:
            with self.lock:
                job['skipped'] += 1
                if e.code == 'phone_only':
                    job['phone_only'] += 1
                    job['marked'].append(mid)
                    store.set_error(job['jid'], mid, wmedia.PHONE_ONLY, 'phone_only')
            return
        with self.lock:
            job['done'] += 1
            job['ready'].append(mid)

    def _run(self, job, ids):
        try:
            with ThreadPoolExecutor(PREFETCH_WORKERS) as pool:
                list(pool.map(lambda mid: self._one(job, mid), ids))
        except Exception:
            _log_error('prefetch')
        job['running'] = False

    def stop(self):
        job = self.job
        if job:
            job['cancel'].set()

    def status(self, jid, since=0, mark_since=0):
        job = self.job
        if not job or job['jid'] != jid:
            return {'running': False, 'total': 0, 'done': 0, 'skipped': 0, 'phone_only': 0,
                    'ready': [], 'phone': [], 'next': 0, 'mark_next': 0}
        with self.lock:
            return {'running': job['running'] and not job['cancel'].is_set(), 'total': job['total'],
                    'done': job['done'], 'skipped': job['skipped'], 'phone_only': job['phone_only'],
                    'ready': job['ready'][since:], 'next': len(job['ready']),
                    'phone': job['marked'][mark_since:], 'mark_next': len(job['marked'])}


bridge = _Bridge()
store = _Store()
cache = _Cache()
zips = _ZipJobs()
history = _History()
prefetch = _Prefetch()


# ============================================================ API do Flask ===

_qr_cache = {}


def status():
    setup = setup_info()
    result = {'setup': setup}
    if not setup['ready']:
        result['state'] = {'status': 'setup'}
        return result
    try:
        bridge.ensure()
    except (WhatsSaverError, OSError) as e:
        result['state'] = {'status': 'error', 'error': str(e)}
        return result
    state = dict(bridge.state)
    qr = state.pop('qr', None)
    if qr:
        if qr not in _qr_cache:
            _qr_cache.clear()
            _qr_cache[qr] = _qr_image(qr)
        state['qr_image'] = _qr_cache[qr]
    result['state'] = state
    sync = dict(store.sync)
    if sync['active'] and time.time() - sync['last'] > 90:
        sync['active'] = False  # nenhum lote novo faz tempo: o celular terminou de mandar
    result['sync'] = sync
    result['stats'] = store.stats()
    result['history'] = history.status()
    return result


def connect():
    return bridge.call('connect')


def pair(phone):
    return bridge.call('pair_code', timeout=40, phone=phone)


def logout():
    """Desconecta o aparelho e apaga o índice local e o cache."""
    zips.cancel_all()
    history.stop()
    prefetch.stop()
    try:
        bridge.call('logout', timeout=20)
    except WhatsSaverError:
        shutil.rmtree(os.path.join(DATA_DIR, 'auth'), ignore_errors=True)
    store.wipe()


def list_chats(query='', scope='media'):
    return store.list_chats(query, scope)


def chat_info(jid):
    info = store.chat(jid)
    job = history.status()
    info['history'] = job if job and job['chat'] == jid else None
    return info


def list_media(jid, kind='all', who='all', offset=0, limit=120):
    return store.list_media(jid, kind, who, offset, limit)


def history_start(jid):
    return history.start(jid)


def history_stop():
    return history.stop()


def thumb(jid, mid):
    """Miniatura boa (se a mídia já foi vista) ou a pequena que vem na mensagem."""
    hq = cache.thumb_path(jid, mid)
    if os.path.isfile(hq):
        return hq, None
    with store.db() as c:
        r = c.execute('SELECT thumb FROM media WHERE chat = ? AND id = ?', (jid, mid)).fetchone()
    return None, (r['thumb'] if r else None)


def prepare(jid, mid):
    """Baixa e confere a mídia (no cache) para ver ou baixar."""
    row, path = ensure_media(jid, mid)
    return {'name': _file_name(row), 'size': os.path.getsize(path), 'kind': row['kind']}


def media_file(jid, mid, preview=False):
    """(caminho, mimetype, nome para salvar) da mídia, baixando se preciso."""
    row, path = ensure_media(jid, mid)
    mime = row['mimetype']
    serve = path
    if preview and row['kind'] == 'image':
        serve, converted = _preview(path)
        mime = converted or mime
    mime = (mime or mimetypes.guess_type(path)[0] or 'application/octet-stream').split(';')[0]
    if row['as_file'] and mime in ('application/octet-stream', 'binary/octet-stream'):
        mime = mimetypes.guess_type(_file_name(row))[0] or mime
    return serve, mime, _file_name(row)


ZIP_LABELS = {'all': 'tudo', 'photo': 'fotos', 'video': 'vídeos', 'file': 'enviados como arquivo'}


def prefetch_start(jid):
    return prefetch.start(jid)


def prefetch_status(jid, since=0, mark_since=0):
    return prefetch.status(jid, since, mark_since)


def zip_start(jid, ids=None, kind='all', who='all'):
    chat = _safe_name(store.chat_name(jid), 60)
    if ids:
        ids = [str(i) for i in ids]
        what = '1 item' if len(ids) == 1 else f'{len(ids)} itens'
    else:
        ids = store.ids(jid, kind, who)
        what = ZIP_LABELS.get(kind, kind)
    return zips.start(jid, ids, f'{chat} - {what}')


def zip_status(job_id):
    return zips.status(job_id)


def zip_cancel(job_id):
    zips.cancel(job_id)


def zip_stream(job_id):
    return zips.stream(job_id)


_avatar_gate = threading.Semaphore(2)


def _fresh(path, max_age=86400):
    return os.path.isfile(path) and time.time() - os.path.getmtime(path) < max_age


def avatar(jid):
    """Foto de perfil (cache de um dia). None quando não tem ou é privada."""
    h = hashlib.sha1(jid.encode()).hexdigest()
    path = os.path.join(AVATAR_DIR, h + '.jpg')
    missing = path + '.none'
    if _fresh(path):
        return path
    if _fresh(missing) or not bridge.is_open():
        return path if os.path.isfile(path) else None
    with _avatar_gate:
        try:
            url = bridge.call('avatar', timeout=15, jid=jid).get('url')
            os.makedirs(AVATAR_DIR, exist_ok=True)
            if not url:
                Path(missing).touch()
                return None
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = resp.read()
            with open(path, 'wb') as f:
                f.write(data)
            return path
        except (WhatsSaverError, OSError):
            return path if os.path.isfile(path) else None
