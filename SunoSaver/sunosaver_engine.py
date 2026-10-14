"""Motor do SunoSaver: cola um link do Suno (música, link de compartilhamento,
playlist ou perfil) e baixa áudio, vídeo, capa, letra e metadados, sem login.

Como o Suno entrega as coisas (conferido em 2026-10-12, sem login):
- /api/clip/<id> devolve o JSON da música: título, autor, letra
  (metadata.prompt), estilo (metadata.tags), duração, capa e video_url;
- o MP3 antigo (cdn1.suno.ai/<id>.mp3) responde 403 e o áudio novo
  (media_urls, .m4a) vem cifrado. O SunoSaver NÃO mexe nisso;
- o vídeo (cdn1.suno.ai/<id>.mp4) é público e traz o áudio em AAC estéreo
  48 kHz (~190 kbps). O áudio sai dele com "-c:a copy": é o mesmo áudio que o
  Suno publicou, sem recodificar e sem perder nada.

Nada aqui usa créditos nem o limite de downloads da conta: só lê o que o Suno
já deixa público para quem abre o link.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlparse, parse_qs

import requests

API = 'https://studio-api.prod.suno.com/api'
SITE = 'https://suno.com'
UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/130.0.0.0 Safari/537.36')
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
MEDIA_HOSTS = ('cdn1.suno.ai', 'cdn2.suno.ai')
CACHE_DIR = os.path.join(tempfile.gettempdir(), 'sunosaver')
CACHE_TTL = 24 * 3600
PERFIL_PAGINAS_MAX = 60      # ~20 músicas por página
PLAYLIST_PAGINAS_MAX = 60

FORMATOS = {
    # id: (extensão, descrição)
    'm4a': ('m4a', 'Áudio original (AAC, sem recodificar)'),
    'mp3': ('mp3', 'MP3 320 kbps'),
    'wav': ('wav', 'WAV 16 bits (para editar)'),
    'flac': ('flac', 'FLAC (para editar, sem perda)'),
    'mp4': ('mp4', 'Vídeo do Suno'),
    'capa': ('jpg', 'Capa'),
    'letra': ('txt', 'Letra'),
    'lrc': ('lrc', 'Letra sincronizada (LRC)'),
    'srt': ('srt', 'Legenda (SRT)'),
    'vtt': ('vtt', 'Legenda (VTT)'),
    'info': ('json', 'Metadados'),
}
SINCRONIZADOS = ('lrc', 'srt', 'vtt')


class SunoSaverError(Exception):
    pass


# ------------------------------------------------------------------ rede ---

_sessao = None
_sessao_lock = threading.Lock()


def _http():
    global _sessao
    with _sessao_lock:
        if _sessao is None:
            _sessao = requests.Session()
            _sessao.headers.update({'User-Agent': UA, 'Accept': 'application/json, */*',
                                    'Referer': SITE + '/', 'Origin': SITE})
        return _sessao


def _get(url, what='esta música', **kw):
    try:
        r = _http().get(url, timeout=kw.pop('timeout', 20), **kw)
    except requests.RequestException:
        raise SunoSaverError('Sem conexão com o Suno. Confira a internet e tente de novo.')
    if r.status_code in (401, 403):
        raise SunoSaverError(f'O Suno não mostra {what} sem login (é privado). Peça ao autor para deixar público.')
    if r.status_code == 404:
        raise SunoSaverError(f'Não encontrei {what}: o link está errado ou foi apagado.')
    if r.status_code == 429:
        raise SunoSaverError('O Suno limitou as consultas. Espere um minuto e tente de novo.')
    if r.status_code >= 400:
        raise SunoSaverError(f'O Suno respondeu com erro {r.status_code}.')
    return r


def _json(url, what='esta música'):
    try:
        return _get(url, what).json()
    except ValueError:
        raise SunoSaverError('O Suno respondeu num formato inesperado (pode ter mudado). Tente de novo mais tarde.')


def is_media_url(url):
    try:
        p = urlparse(url)
    except ValueError:
        return False
    return p.scheme == 'https' and p.hostname in MEDIA_HOSTS


# ----------------------------------------------------------------- links ---

def _seguir_compartilhamento(codigo):
    """suno.com/s/<código> redireciona para /song/<id>?sh=<código>."""
    try:
        r = _http().get(f'{SITE}/s/{codigo}', allow_redirects=False, timeout=20)
    except requests.RequestException:
        raise SunoSaverError('Sem conexão com o Suno. Confira a internet e tente de novo.')
    destino = r.headers.get('Location', '')
    m = re.search(UUID, destino)
    if not m:
        raise SunoSaverError('Link de compartilhamento inválido ou expirado.')
    return m.group(0)


def _clip_do_hook(hook_id):
    """O hook (vídeo curto) aponta para a música de origem; o id dela vem na página."""
    html = _get(f'{SITE}/hook/{hook_id}', 'este hook').text
    for m in re.finditer(r'clip_id\\?"\s*:\s*\\?"(' + UUID + ')', html):
        return m.group(1)
    ids = [i for i in dict.fromkeys(re.findall(UUID, html)) if i != hook_id]
    for i in ids[:6]:
        try:
            _json(f'{API}/clip/{i}')
            return i
        except SunoSaverError:
            continue
    raise SunoSaverError('Não achei a música deste hook. Abra o hook no Suno e copie o link da música.')


def interpretar(link):
    """Texto colado -> ('musica', id) | ('playlist', id) | ('perfil', handle)."""
    t = (link or '').strip()
    if not t:
        raise SunoSaverError('Cole um link do Suno.')
    if re.fullmatch(UUID, t.lower()):
        return 'musica', t.lower()
    if t.startswith('@'):
        return 'perfil', t[1:]
    if not re.match(r'https?://', t):
        t = 'https://' + t
    p = urlparse(t)
    host = (p.hostname or '').lower()
    if not (host == 'suno.com' or host.endswith('.suno.com') or host.endswith('.suno.ai')):
        raise SunoSaverError('Esse link não é do Suno. Use um link de suno.com (música, compartilhamento, playlist ou perfil).')
    partes = [x for x in p.path.split('/') if x]
    if not partes:
        raise SunoSaverError('Esse link é da página inicial do Suno. Abra a música e use "Copiar link".')
    tipo, resto = partes[0].lower(), partes[1:]
    if tipo == 's' and resto:
        return 'musica', _seguir_compartilhamento(resto[0])
    if tipo in ('song', 'embed', 'clip') and resto and re.fullmatch(UUID, resto[0].lower()):
        return 'musica', resto[0].lower()
    if tipo == 'hook' and resto:
        return 'musica', _clip_do_hook(resto[0])
    if tipo == 'playlist' and resto and re.fullmatch(UUID, resto[0].lower()):
        return 'playlist', resto[0].lower()
    if tipo.startswith('@'):
        return 'perfil', tipo[1:]
    if tipo == 'profile' and resto:
        return 'perfil', resto[0].lstrip('@')
    m = re.search(UUID, p.path.lower())
    if m:
        return 'musica', m.group(0)
    q = parse_qs(p.query)
    if q.get('sh'):
        return 'musica', _seguir_compartilhamento(q['sh'][0])
    raise SunoSaverError('Não reconheci esse link. Funciona com música (suno.com/song/…), compartilhamento (suno.com/s/…), hook, playlist e perfil (suno.com/@nome).')


# ---------------------------------------------------------------- músicas ---

def _limpar_letra(texto):
    return (texto or '').replace('\r\n', '\n').strip()


def _musica(c):
    """JSON do Suno -> o que o front e o download precisam."""
    m = c.get('metadata') or {}
    video = c.get('video_url') or ''
    capa = c.get('image_large_url') or c.get('image_url') or ''
    return {
        'id': c.get('id'),
        'titulo': (c.get('title') or '').strip() or 'Sem título',
        'autor': c.get('display_name') or c.get('handle') or 'Suno',
        'handle': c.get('handle') or '',
        'avatar': c.get('avatar_image_url') or '',
        'capa': capa if is_media_url(capa) else '',
        'video': video if is_media_url(video) else '',
        'duracao': m.get('duration') or 0,
        'letra': _limpar_letra(m.get('prompt')),
        'estilo': (m.get('tags') or '').strip(),
        'estilo_curto': c.get('display_tags') or '',
        'instrumental': bool(m.get('make_instrumental')),
        'modelo': c.get('major_model_version') or c.get('model_name') or '',
        'criado': (c.get('created_at') or '')[:10],
        'publico': bool(c.get('is_public')),
        'pronto': c.get('status') == 'complete',
        'plays': c.get('play_count') or 0,
        'curtidas': c.get('upvote_count') or 0,
        'link': f"{SITE}/song/{c.get('id')}",
        'local': bool(_local_existente(c.get('id') or '')),
    }


def musica(clip_id):
    if not re.fullmatch(UUID, clip_id or ''):
        raise SunoSaverError('Id de música inválido.')
    return _musica(_json(f'{API}/clip/{clip_id}'))


def playlist(pid, pagina=1):
    d = _json(f'{API}/playlist/{pid}/?page={int(pagina)}', 'esta playlist')
    itens = [_musica(x['clip']) for x in d.get('playlist_clips') or [] if x.get('clip')]
    total = d.get('num_total_results') or len(itens)
    return {
        'tipo': 'playlist', 'id': pid, 'nome': d.get('name') or 'Playlist',
        'autor': d.get('user_display_name') or d.get('user_handle') or '',
        'capa': d.get('image_url') or '', 'total': total,
        'pagina': int(pagina), 'musicas': itens,
        'mais': bool(itens) and int(pagina) < PLAYLIST_PAGINAS_MAX and (int(pagina) * 20) < total,
    }


def perfil(handle, pagina=1):
    handle = re.sub(r'[^\w.-]', '', handle or '')
    if not handle:
        raise SunoSaverError('Nome de perfil inválido.')
    d = _json(f'{API}/profiles/{handle}?page={int(pagina)}&clips_sort_by=created_at&playlists_sort_by=created_at', 'este perfil')
    itens = [_musica(c) for c in d.get('clips') or []]
    return {
        'tipo': 'perfil', 'id': handle, 'nome': d.get('display_name') or handle, 'handle': d.get('handle') or handle,
        'avatar': d.get('avatar_image_url') or '', 'bio': d.get('profile_description') or '',
        'total': d.get('num_total_clips') or len(itens), 'pagina': int(pagina), 'musicas': itens,
        'playlists': [{'id': p.get('id'), 'nome': p.get('name'), 'total': p.get('num_total_results'),
                       'capa': p.get('image_url') or ''} for p in (d.get('playlists') or []) if p.get('id')],
        'mais': bool(itens) and int(pagina) < PERFIL_PAGINAS_MAX,
    }


def resolver(link):
    tipo, valor = interpretar(link)
    if tipo == 'musica':
        return {'tipo': 'musica', 'musica': musica(valor)}
    if tipo == 'playlist':
        return playlist(valor)
    return perfil(valor)


# ------------------------------------------------------------- arquivos ---

def _limpar_cache():
    agora = time.time()
    try:
        for nome in os.listdir(CACHE_DIR):
            p = os.path.join(CACHE_DIR, nome)
            if agora - os.path.getmtime(p) > CACHE_TTL:
                shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    except OSError:
        pass


_baixando = {}
_baixando_lock = threading.Lock()


def _baixar_para(url, destino):
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        os.utime(destino)
        return destino
    with _baixando_lock:
        trava = _baixando.setdefault(destino, threading.Lock())
    with trava:
        if os.path.exists(destino) and os.path.getsize(destino) > 0:
            return destino
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        tmp = destino + '.part'
        r = _get(url, 'o arquivo', stream=True, timeout=60)
        with open(tmp, 'wb') as f:
            for bloco in r.iter_content(256 * 1024):
                f.write(bloco)
        os.replace(tmp, destino)
    return destino


def _pasta(clip_id):
    _limpar_cache()
    return os.path.join(CACHE_DIR, clip_id)


EXT_AUDIO = ('.mp3', '.m4a', '.aac', '.wav', '.flac', '.ogg', '.opus', '.webm', '.mp4')


def _local_existente(clip_id):
    pasta = os.path.join(CACHE_DIR, clip_id)
    if not os.path.isdir(pasta):
        return None
    for n in os.listdir(pasta):
        if n.startswith('local.'):
            return os.path.join(pasta, n)
    return None


def _probe(caminho):
    try:
        p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,codec_name',
                            '-of', 'json', caminho], capture_output=True, text=True, timeout=60)
        d = json.loads(p.stdout or '{}')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    audio = [x for x in d.get('streams', []) if x.get('codec_type') == 'audio']
    if not audio:
        return None
    return {'duracao': float((d.get('format') or {}).get('duration') or 0), 'codec': audio[0].get('codec_name')}


ZIP_MAX_MEMBRO = 400 * 1024 * 1024


def _audio_do_zip(caminho, m, destino_dir):
    """Tira de um ZIP (o "Baixar tudo" do usesuno traz áudio, capa, letra e vídeo)
    o áudio desta música: só membros de áudio, sem caminhos (nada é escrito fora
    da pasta temporária), do maior para o menor, o primeiro com a duração certa."""
    import zipfile
    try:
        z = zipfile.ZipFile(caminho)
    except (zipfile.BadZipFile, OSError):
        raise SunoSaverError('Esse ZIP está corrompido.')
    with z:
        membros = [i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(EXT_AUDIO)
                   and 0 < i.file_size <= ZIP_MAX_MEMBRO]
        if not membros:
            raise SunoSaverError('Esse ZIP não tem nenhum arquivo de áudio.')
        # áudio antes de vídeo; dentro de cada tipo, o maior primeiro
        membros.sort(key=lambda i: (i.filename.lower().endswith(('.mp4', '.webm')), -i.file_size))
        for k, i in enumerate(membros):
            ext = os.path.splitext(i.filename)[1].lower()
            alvo = os.path.join(destino_dir, f'membro{k}{ext}')
            with z.open(i) as src, open(alvo, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            info = _probe(alvo)
            if info and (not m.get('duracao') or abs(info['duracao'] - m['duracao']) <= 6):
                return alvo, os.path.basename(i.filename)
    raise SunoSaverError('O áudio desse ZIP não tem a duração desta música: não parece ser ela.')


def receber_arquivo(m, origem, nome='audio'):
    """Guarda o arquivo de áudio desta música que a pessoa baixou e passa a usá-lo
    como fonte. Aceita o ZIP do usesuno. Confere se é áudio e se a duração bate
    com a da música no Suno."""
    if nome.lower().endswith('.zip'):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            audio, nome_audio = _audio_do_zip(origem, m, tmp)
            return receber_arquivo(m, audio, nome_audio)
    info = _probe(origem)
    if not info:
        raise SunoSaverError('Esse arquivo não tem áudio.')
    if m.get('duracao') and abs(info['duracao'] - m['duracao']) > 6:
        raise SunoSaverError(f'Esse arquivo tem {info["duracao"]:.0f} s e a música tem {m["duracao"]:.0f} s: não parece ser ela.')
    pasta = _pasta(m['id'])
    os.makedirs(pasta, exist_ok=True)
    for n in os.listdir(pasta):            # saídas antigas vieram de outra fonte
        if n.startswith('local.') or n.startswith('saida.'):
            os.remove(os.path.join(pasta, n))
    ext = os.path.splitext(nome)[1].lower()
    destino = os.path.join(pasta, 'local' + (ext if ext in EXT_AUDIO else '.audio'))
    shutil.copyfile(origem, destino)
    return destino


def procurar_em_downloads(m, desde):
    """Procura em Downloads um áudio novo (depois de `desde`) com a duração da
    música. Ignora o que ainda está baixando (.crdownload, .part)."""
    from Automacoes.core import pastas
    base = str(pastas.downloads())
    try:
        nomes = os.listdir(base)
    except OSError:
        return None
    candidatos = []
    for n in nomes:
        c = os.path.join(base, n)
        if not n.lower().endswith(EXT_AUDIO + ('.zip',)) or not os.path.isfile(c):
            continue
        try:
            st = os.stat(c)
        except OSError:
            continue
        if st.st_mtime < desde - 2 or st.st_size < 50_000:
            continue
        candidatos.append((st.st_mtime, c, st.st_size))
    for _, c, tam in sorted(candidatos, reverse=True):
        time.sleep(0.3)
        try:
            if os.path.getsize(c) != tam:      # ainda crescendo
                continue
        except OSError:
            continue
        if c.lower().endswith('.zip'):
            try:
                return receber_arquivo(m, c, os.path.basename(c))
            except SunoSaverError:
                continue        # ZIP de outra coisa (ou de outra música)
        info = _probe(c)
        if info and (not m.get('duracao') or abs(info['duracao'] - m['duracao']) <= 6):
            return receber_arquivo(m, c, os.path.basename(c))
    return None


def previa_local(clip_id):
    """O arquivo baixado, para a prévia tocar sem conversão. -> (caminho, mimetype) ou None"""
    local = _local_existente(clip_id)
    if not local:
        return None
    mimes = {'.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.aac': 'audio/aac', '.wav': 'audio/wav', '.flac': 'audio/flac',
             '.ogg': 'audio/ogg', '.opus': 'audio/ogg', '.webm': 'audio/webm', '.mp4': 'video/mp4'}
    return local, mimes.get(os.path.splitext(local)[1].lower(), 'application/octet-stream')


def fonte_audio(m):
    """De onde o áudio sai: o arquivo baixado pela pessoa (se houver) ou o vídeo público."""
    local = _local_existente(m['id'])
    if local:
        return local
    return video_local(m)


def video_local(m):
    if not m['video']:
        if not m['publico']:
            raise SunoSaverError('Música privada: o áudio ainda não chegou. Use "Baixar pelo usesuno" no cartão da música '
                                 '(ou solte o arquivo lá) e tudo fica liberado. Capa, letra e dados já estão disponíveis.')
        raise SunoSaverError('O Suno ainda não publicou o vídeo desta música, que é de onde o áudio sai sem login. '
                             'Abra a música no Suno uma vez (o vídeo é gerado na primeira exibição) e tente de novo.')
    return _baixar_para(m['video'], os.path.join(_pasta(m['id']), 'video.mp4'))


def capa_local(m):
    if not m['capa']:
        raise SunoSaverError('Esta música não tem capa.')
    return _baixar_para(m['capa'], os.path.join(_pasta(m['id']), 'capa.jpg'))


def nome_base(m):
    base = f"{m['autor']} - {m['titulo']}"
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', base).strip(' .')
    return base[:150] or m['id']


def _letra_tag(m):
    return m['letra'] if not m['instrumental'] else ''


def _id3_letra(caminho, letra):
    """Põe a letra no quadro USLT do ID3v2.3 (o campo que os players leem).
    O FFmpeg 6 grava "lyrics" como TXXX, que nenhum player mostra."""
    with open(caminho, 'rb') as f:
        dados = f.read()
    if not letra or dados[:3] != b'ID3' or dados[3] != 3:
        return
    tamanho = 0
    for b in dados[6:10]:
        tamanho = (tamanho << 7) | (b & 0x7f)
    corpo = b'\x01' + b'por' + b'\xff\xfe\x00\x00' + b'\xff\xfe' + letra.encode('utf-16-le')
    quadro = b'USLT' + len(corpo).to_bytes(4, 'big') + b'\x00\x00' + corpo
    novo = tamanho + len(quadro)
    syncsafe = bytes([(novo >> s) & 0x7f for s in (21, 14, 7, 0)])
    with open(caminho, 'wb') as f:
        f.write(dados[:6] + syncsafe + quadro + dados[10:])


def _tags(m, com_letra=True):
    letra = _letra_tag(m) if com_letra else ''
    tags = {
        'title': m['titulo'], 'artist': m['autor'], 'album_artist': m['autor'],
        'genre': m['estilo_curto'] or m['estilo'][:120], 'date': m['criado'][:4],
        'comment': f"Feito no Suno ({m['modelo']}) · {m['link']}", 'lyrics': letra,
    }
    return [x for k, v in tags.items() if v for x in ('-metadata', f'{k}={v}')]


def _ffmpeg(args):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise SunoSaverError('Falta o FFmpeg (rode o INSTALAR.py).')
    p = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *args],
                       capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise SunoSaverError('O FFmpeg não conseguiu montar o arquivo: ' + (p.stderr.strip().splitlines() or ['erro'])[-1])


def gerar(m, formato, palavra_a_palavra=False):
    """Cria (ou reaproveita do cache) o arquivo pedido. Devolve (caminho, nome, mimetype)."""
    if formato not in FORMATOS:
        raise SunoSaverError('Formato desconhecido.')
    ext = FORMATOS[formato][0]
    nome = f'{nome_base(m)}.{ext}'
    pasta = _pasta(m['id'])
    os.makedirs(pasta, exist_ok=True)
    saida = os.path.join(pasta, f'saida.{formato}.{ext}')
    mimes = {'m4a': 'audio/mp4', 'mp3': 'audio/mpeg', 'wav': 'audio/wav', 'flac': 'audio/flac', 'mp4': 'video/mp4',
             'jpg': 'image/jpeg', 'txt': 'text/plain; charset=utf-8', 'json': 'application/json',
             'lrc': 'text/plain; charset=utf-8', 'srt': 'application/x-subrip', 'vtt': 'text/vtt'}

    if formato == 'letra':
        if not m['letra']:
            raise SunoSaverError('Esta música não tem letra (instrumental ou letra escondida pelo autor).')
        with open(saida, 'w', encoding='utf-8') as f:
            f.write(f"{m['titulo']}\n{m['autor']}\n\n{m['letra']}\n")
    elif formato == 'info':
        with open(saida, 'w', encoding='utf-8') as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
    elif formato == 'capa':
        shutil.copyfile(capa_local(m), saida)
    elif formato in SINCRONIZADOS:
        from SunoSaver import sunosaver_letra
        try:
            sunosaver_letra.exportar(m, formato, saida, palavra_a_palavra)
        except sunosaver_letra.LetraError as e:
            raise SunoSaverError(str(e))
    elif not (os.path.exists(saida) and os.path.getsize(saida) > 0):
        if formato == 'mp4' and not m['video']:
            raise SunoSaverError('Esta música não tem o vídeo do Suno.')
        video = video_local(m) if formato == 'mp4' else fonte_audio(m)
        fonte_codec = (_probe(video) or {}).get('codec')
        try:
            capa = capa_local(m)
        except SunoSaverError:
            capa = None
        tmp = saida + '.tmp.' + ext
        if formato == 'mp4':
            _ffmpeg(['-i', video, '-map', '0', '-c', 'copy', *_tags(m), '-movflags', '+faststart', tmp])
        elif formato == 'wav':
            _ffmpeg(['-i', video, '-vn', '-c:a', 'pcm_s16le', tmp])
        else:
            entrada = ['-i', video] + (['-i', capa] if capa else [])
            mapa = ['-map', '0:a'] + (['-map', '1:v', '-disposition:v', 'attached_pic'] if capa else [])
            codec = {'m4a': ['-c:a', 'copy'] if fonte_codec == 'aac' else ['-c:a', 'aac', '-b:a', '256k'],
                     'mp3': ['-c:a', 'libmp3lame', '-b:a', '320k', '-id3v2_version', '3'],
                     'flac': ['-c:a', 'flac']}[formato]
            capa_codec = ['-c:v', 'copy', '-metadata:s:v', 'title=Album cover',
                          '-metadata:s:v', 'comment=Cover (front)'] if capa else []
            _ffmpeg([*entrada, *mapa, '-map_metadata', '-1', *codec, *capa_codec,
                     *_tags(m, com_letra=formato != 'mp3'), tmp])
            if formato == 'mp3':
                _id3_letra(tmp, _letra_tag(m))
        os.replace(tmp, saida)
    return saida, nome, mimes[ext]


def info():
    return {'formatos': [{'id': k, 'ext': v[0], 'nome': v[1]} for k, v in FORMATOS.items()]}
