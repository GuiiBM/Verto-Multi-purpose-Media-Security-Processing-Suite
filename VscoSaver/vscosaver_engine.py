"""Motor do VscoSaver: resolve um link do VSCO (perfil, galeria, foto, vídeo,
coleção ou space) e lista galeria, coleção e spaces do perfil dono do link.

É o InstaSaver do VSCO, com uma diferença boa: o VSCO é público, então não
precisa de login nem de cookies do navegador. A página do perfil já traz um
token de visitante (__PRELOADED_STATE__) e com ele o motor chama a mesma API
que o site usa (/api/2.0, /api/3.0 e /grpc).

Tudo passa pelo curl_cffi imitando o Chrome: com requests puro o Cloudflare
do VSCO responde 403 para tudo, inclusive para as imagens. Vídeos novos são
HLS (.m3u8 no Mux, sem .mp4 pronto): o ffmpeg junta os pedaços num .mp4 sem
recodificar, guardado num cache temporário para o player conseguir avançar.
"""
import os
import re
import json
import time
import hashlib
import tempfile
import threading
import subprocess
from datetime import datetime
from urllib.parse import urlparse

try:
    from curl_cffi import requests as vsco_requests
except ImportError:
    vsco_requests = None

ROOT = 'https://vsco.co'
# Token de visitante que o site embute em toda página de perfil. O motor usa o
# que vier na página; este só entra se a página mudar de formato.
DEFAULT_TOKEN = '7356455548d0a1d886db010883388d08be84d0c9'
GALLERY_PAGE = 14      # o site pede 14 por vez; acima disso o Cloudflare responde 403
COLLECTION_PAGE = 20
THUMB_WIDTH = 480
MEDIA_HOST_SUFFIXES = ('.vsco.co', '.mux.com')
RESERVED_PATHS = {'feed', 'discover', 'search', 'studio', 'user', 'api', 'grpc', 'login',
                  'signup', 'join', 'subscribe', 'store', 'about', 'settings', 'account'}
HLS_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'vscosaver_videos')
HLS_CACHE_TTL = 24 * 3600


class VscoSaverError(Exception):
    pass


# ---------------------------------------------------------------- sessão ---

_session_lock = threading.Lock()
_session = None
_token = {'value': None}


def _http():
    """Sessão única (o curl_cffi usa um handle por thread, então é segura
    para as várias requisições simultâneas do Flask)."""
    global _session
    if vsco_requests is None:
        raise VscoSaverError(
            'Falta o pacote curl_cffi (pip install curl_cffi): sem ele o VSCO bloqueia as requisições.')
    with _session_lock:
        if _session is None:
            _session = vsco_requests.Session(impersonate='chrome')
        return _session


def _check_status(resp, what='Conteúdo'):
    if resp.status_code == 404:
        raise VscoSaverError(f'{what} não encontrado (link inválido ou removido).')
    if resp.status_code == 429:
        raise VscoSaverError('O VSCO limitou as requisições. Espere um ou dois minutos e tente de novo.')
    if resp.status_code == 403:
        raise VscoSaverError('O VSCO bloqueou a requisição. Tente de novo em alguns minutos.')
    if resp.status_code >= 400:
        raise VscoSaverError(f'O VSCO respondeu com erro {resp.status_code}.')


def _state(path, what='Perfil'):
    """Carrega a página e devolve o JSON de __PRELOADED_STATE__ - o mesmo
    que o site usa para desenhar a página. Aproveita para guardar o token."""
    try:
        resp = _http().get(ROOT + path, timeout=25)
    except VscoSaverError:
        raise
    except Exception as e:
        raise VscoSaverError(f'Falha de conexão com o VSCO: {e}')
    _check_status(resp, what)
    html = resp.text
    start = html.find('__PRELOADED_STATE__ = ')
    end = html.find('</script>', start)
    if start < 0 or end < 0:
        raise VscoSaverError('O VSCO mudou o formato da página; não consegui ler o conteúdo.')
    raw = html[start + len('__PRELOADED_STATE__ = '):end].strip().rstrip(';')
    try:
        data = json.loads(raw.replace('":undefined', '":null'))
    except ValueError:
        raise VscoSaverError('O VSCO mudou o formato da página; não consegui ler o conteúdo.')
    tkn = ((data.get('users') or {}).get('currentUser') or {}).get('tkn')
    if tkn:
        _token['value'] = tkn
    return data


def _api(path, params=None, referer=None, _retry=True):
    """GET na API do VSCO com o token de visitante, igual ao que a página faz."""
    headers = {
        'Authorization': 'Bearer ' + (_token['value'] or DEFAULT_TOKEN),
        'X-Client-Platform': 'web', 'X-Client-Build': '1', 'Accept': 'application/json',
        'Referer': referer or ROOT + '/',
    }
    try:
        resp = _http().get(ROOT + path, params=params, headers=headers, timeout=25)
    except VscoSaverError:
        raise
    except Exception as e:
        raise VscoSaverError(f'Falha de conexão com o VSCO: {e}')
    if resp.status_code == 401 and _retry:
        _token['value'] = None  # token vencido: a próxima página traz outro
        _state('/vsco/gallery')
        return _api(path, params, referer, _retry=False)
    _check_status(resp)
    try:
        return resp.json()
    except ValueError:
        raise VscoSaverError('O VSCO devolveu uma resposta inesperada. Tente de novo.')


# ------------------------------------------------------------ parse link ---

def parse_link(raw):
    """Retorna dict com 'kind' em profile|media|video|collection|spaces|space."""
    text = (raw or '').strip()
    if not text:
        raise VscoSaverError('Cole um link do VSCO.')

    if re.fullmatch(r'@?[\w-]{1,50}', text):
        return {'kind': 'profile', 'username': text.lstrip('@').lower()}

    if not re.match(r'^https?://', text):
        text = 'https://' + text
    parsed = urlparse(text)
    host = (parsed.hostname or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    parts = [p for p in parsed.path.split('/') if p]

    # Endereço antigo de perfil: usuario.vsco.co
    if host.endswith('.vsco.co') and host.count('.') == 2 and host.split('.')[0] not in ('i', 'im', 'img'):
        parts = [host.split('.')[0]] + parts
    elif host != 'vsco.co':
        raise VscoSaverError('Isso não parece um link do VSCO.')

    if not parts:
        raise VscoSaverError('Link sem perfil ou conteúdo.')
    if parts[0] == 'spaces' and len(parts) >= 2:
        return {'kind': 'space', 'space_id': parts[1]}
    if parts[0].lower() in RESERVED_PATHS or not re.fullmatch(r'[\w.-]{1,50}', parts[0]):
        raise VscoSaverError('Tipo de link não suportado.')

    username = parts[0].lower()
    section = parts[1].lower() if len(parts) >= 2 else ''
    if section == 'media' and len(parts) >= 3:
        return {'kind': 'media', 'username': username, 'media_id': parts[2]}
    if section == 'video' and len(parts) >= 3:
        return {'kind': 'video', 'username': username, 'media_id': parts[2]}
    if section == 'collection':
        return {'kind': 'collection', 'username': username}
    if section == 'spaces':
        return {'kind': 'spaces', 'username': username}
    return {'kind': 'profile', 'username': username}  # /gallery, /images/1, /journal... abrem o perfil


# ------------------------------------------------------------ normalização ---

def _snake(d):
    """A página usa camelCase e a API snake_case; o motor lê tudo em snake."""
    return {re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower(): v for k, v in (d or {}).items()}


def _https(url):
    if not url:
        return None
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('http://'):
        return 'https://' + url[7:]
    return url if url.startswith('https://') else 'https://' + url


def _ms(value):
    """Datas do VSCO vêm em ms, ou como {sec, ns} nos spaces. Devolve segundos."""
    if isinstance(value, dict):
        return value.get('sec') or None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value // 1000 if value > 10 ** 11 else value


def _stamp(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%Y%m%d_%H%M%S')
    except (TypeError, ValueError):
        return 'sem_data'


def _with_query(url, query):
    return url + ('&' if '?' in url else '?') + query


def _entry(raw, username, kind):
    """Normaliza foto, vídeo antigo (mp4) ou vídeo novo (HLS) num formato só."""
    m = _snake(raw)
    media_id = str(m.get('_id') or m.get('id') or '')
    taken_at = _ms(m.get('upload_date') or m.get('created_date') or m.get('capture_date'))
    playback = m.get('playback_url')
    if playback:  # vídeo novo, hospedado no Mux
        poster = _https(m.get('poster_url'))
        url, thumb, ext, media_type = playback, poster and _with_query(poster, f'width={THUMB_WIDTH}'), 'mp4', 'video'
    else:
        image = _https(m.get('responsive_url'))
        video = _https(m.get('video_url')) if m.get('is_video') else None
        url = video or image
        thumb = image and _with_query(image, f'w={THUMB_WIDTH}')
        ext = (os.path.splitext(urlparse(url or '').path)[1].lstrip('.') or 'jpg').lower()
        media_type = 'video' if video else 'image'
    meta = _snake(m.get('image_meta'))
    preset = _snake(m.get('preset'))
    camera = ' '.join(x for x in (meta.get('make'), meta.get('model')) if x)
    owner = m.get('perma_subdomain') or m.get('domain') or username
    return {
        'id': media_id,
        'type': media_type,
        'hls': bool(playback),
        'url': url,
        'thumb': thumb,
        'width': m.get('width') or m.get('width_px'),
        'height': m.get('height') or m.get('height_px'),
        'duration': m.get('duration_sec'),
        'taken_at': taken_at,
        'caption': m.get('description') or '',
        'owner': owner,
        'preset': preset.get('short_name'),
        'camera': camera,
        'exif': {k: meta.get(k) for k in ('iso', 'shutter_speed', 'aperture') if meta.get(k)},
        'permalink': (f'https://vsco.co/{owner}/video/{media_id}' if playback else
                      _https(m.get('permalink')) or f'https://vsco.co/{owner}/media/{media_id}'),
        'filename': f'{owner}_{kind}_{_stamp(taken_at)}_{media_id}.{ext}',
    }


def _keep(items):
    return [e for e in items if e['url']]


# --------------------------------------------------------------- consultas ---

def _site_from_state(data, username):
    node = ((data.get('sites') or {}).get('siteByUsername') or {}).get(username) or {}
    if node.get('error') == 'site_not_found' or not node.get('site'):
        raise VscoSaverError(f'Perfil {username} não encontrado no VSCO.')
    return _snake(node['site'])


def get_profile(username):
    site = _site_from_state(_state(f'/{username}/gallery', f'Perfil {username}'), username)
    pic_id = site.get('profile_image_id')
    avatar = _https(site.get('profile_image') or site.get('responsive_url'))
    return {
        'id': str(site.get('id')),
        'user_id': str(site.get('user_id') or ''),
        'username': site.get('subdomain') or username,
        'name': site.get('name') if site.get('name') and site.get('name').lower() != username else '',
        'description': site.get('description') or '',
        'external_link': site.get('external_link') or '',
        'avatar': avatar,
        # Sem parâmetros, i.vsco.co devolve a foto original em vez do recorte 300x300.
        'avatar_full': f'https://i.vsco.co/{pic_id}' if pic_id else avatar,
        'collection_id': site.get('site_collection_id') if site.get('has_collection') else None,
    }


def get_gallery(site_id, username, cursor=None):
    params = {'site_id': site_id, 'limit': GALLERY_PAGE}
    if cursor:
        params['cursor'] = cursor
    data = _api('/api/3.0/medias/profile', params, referer=f'{ROOT}/{username}/gallery')
    items = [_entry(m.get(m.get('type')) or {}, username, 'galeria') for m in data.get('media') or []]
    return {'items': _keep(items), 'next_cursor': data.get('next_cursor')}


def get_collection(collection_id, username, page=1):
    data = _api(f'/api/2.0/collections/{collection_id}/medias', {'page': page, 'size': COLLECTION_PAGE},
                referer=f'{ROOT}/{username}/collection/1')
    medias = data.get('medias') or []
    items = _keep([_entry(m, username, 'colecao') for m in medias])
    total = data.get('count')
    more = len(medias) >= COLLECTION_PAGE and (not total or page * COLLECTION_PAGE < total)
    return {'items': items, 'total': total, 'next_page': page + 1 if more else None}


def _space_summary(space):
    cover = _snake(space.get('coverImage') or (space.get('highlightImagesList') or [{}])[0])
    cover_url = _https(cover.get('responsive_url'))
    return {
        'id': space.get('id'),
        'title': space.get('title') or '',
        'description': space.get('description') or '',
        'cover': cover_url and _with_query(cover_url, 'w=300'),
    }


def get_spaces(user_id, username):
    data = _api(f'/grpc/spaces/user/{user_id}', referer=f'{ROOT}/{username}/spaces')
    return [_space_summary(s.get('space') or {}) for s in data.get('spacesWithRoleList') or [] if s.get('space')]


def get_space(space_id, cursor=None):
    params = {'cursor': cursor} if cursor else None
    data = _api(f'/grpc/spaces/{space_id}/posts', params, referer=f'{ROOT}/spaces/{space_id}')
    items = []
    for post in data.get('postsList') or []:
        media = post.get('image') or post.get('video')
        if not media:
            continue
        owner = (post.get('userInfo') or {}).get('domain') or 'vsco'
        entry = _entry(media, owner, 'space')
        entry['caption'] = post.get('caption') or entry['caption']
        entry['taken_at'] = _ms(post.get('createdTimestamp')) or entry['taken_at']
        items.append(entry)
    page = data.get('cursor') or {}
    next_cursor = None if page.get('atEnd') else (page.get('postcursorcontext') or {}).get('postId')
    return {'items': _keep(items), 'next_cursor': next_cursor}


def get_space_info(space_id):
    data = _state(f'/spaces/{space_id}', 'Space')
    entities = data.get('entities') or {}
    space = (entities.get('spaces') or {}).get(space_id)
    if not space:
        raise VscoSaverError('Space não encontrado.')
    owner_node = (entities.get('spaceUsers') or {}).get(str(space.get('ownerUserId'))) or {}
    owner = ((space.get('ownerUserInfo') or owner_node.get('userInfo') or {}).get('domain'))
    if not owner:
        raise VscoSaverError('Não consegui descobrir o dono deste space.')
    return owner.lower(), _space_summary(space)


def get_single(username, media_id, kind):
    """Foto (/media/<id>) ou vídeo (/video/<id>) avulso: lê da própria página."""
    data = _state(f'/{username}/{kind}/{media_id}', 'Foto' if kind == 'media' else 'Vídeo')
    node = ((data.get('medias') or {}).get('byId') or {}).get(media_id) or {}
    media = node.get('media')
    if not media:
        raise VscoSaverError('Foto ou vídeo não encontrado.')
    entry = _entry(media, username, 'galeria')
    if not entry['url']:
        raise VscoSaverError('Esse conteúdo não tem mídia disponível para baixar.')
    return entry


def _safe(fn, *args):
    """Uma seção que falha (ex.: spaces fora do ar) não derruba o resto."""
    try:
        return fn(*args), None
    except VscoSaverError as e:
        return None, str(e)


def resolve(link):
    """Ponto de entrada: a partir de qualquer link, devolve o perfil e tudo
    que dá para ver dele, marcando qual conteúdo o link apontava (focus)."""
    target = parse_link(link)
    focus = {'kind': target['kind']}

    if target['kind'] == 'space':
        username, space = get_space_info(target['space_id'])
        focus['space'] = space
    else:
        username = target['username']
        if target['kind'] in ('media', 'video'):
            focus['media'] = get_single(username, target['media_id'], target['kind'])

    profile = get_profile(username)
    result = {'profile': profile, 'focus': focus, 'errors': {}}
    empty = {'gallery': {'items': [], 'next_cursor': None},
             'collection': {'items': [], 'total': 0, 'next_page': None}, 'spaces': []}

    sections = [('gallery', get_gallery, (profile['id'], profile['username']))]
    if profile['collection_id']:
        sections.append(('collection', get_collection, (profile['collection_id'], profile['username'])))
    if profile['user_id']:
        sections.append(('spaces', get_spaces, (profile['user_id'], profile['username'])))
    for key, fn, args in sections:
        value, err = _safe(fn, *args)
        if err:
            result['errors'][key] = err
        result[key] = value
    for key, value in empty.items():
        if result.get(key) is None:
            result[key] = value
    return result


# ------------------------------------------------------------------ proxy ---

def is_allowed_media_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https':
        return False
    if host == 'vsco.co':  # só o pôster dos vídeos passa pelo próprio site
        return parsed.path.startswith('/api/1.0/videos/')
    return any(host.endswith(s) for s in MEDIA_HOST_SUFFIXES)


def is_hls(url):
    return urlparse(url).path.endswith('.m3u8')


def fetch_media(url, range_header=None):
    """Busca a mídia na CDN do VSCO (só hosts permitidos) repassando Range
    para o player de vídeo conseguir avançar/voltar."""
    if not is_allowed_media_url(url):
        raise VscoSaverError('URL de mídia não permitida.')
    headers = {'Referer': ROOT + '/'}
    if range_header:
        headers['Range'] = range_header
    try:
        resp = _http().get(url, headers=headers, timeout=60, allow_redirects=True)
    except Exception as e:
        raise VscoSaverError(f'Falha ao buscar a mídia: {e}')
    if resp.status_code >= 400:
        raise VscoSaverError('A mídia não está mais disponível - busque o perfil de novo.')
    return resp


_hls_locks = {}
_hls_locks_guard = threading.Lock()


def _prune_hls_cache():
    try:
        for name in os.listdir(HLS_CACHE_DIR):
            full = os.path.join(HLS_CACHE_DIR, name)
            if time.time() - os.path.getmtime(full) > HLS_CACHE_TTL:
                os.remove(full)
    except OSError:
        pass


def hls_to_mp4(url):
    """Junta o vídeo HLS num .mp4 (cópia direta dos pedaços, sem perder
    qualidade) e devolve o caminho. Fica em cache: o player pede o arquivo
    várias vezes (Range) e o download/zip reaproveita o mesmo arquivo."""
    if not is_allowed_media_url(url) or not is_hls(url):
        raise VscoSaverError('URL de vídeo não permitida.')
    key = hashlib.sha1(urlparse(url).path.encode()).hexdigest()[:20]
    path = os.path.join(HLS_CACHE_DIR, key + '.mp4')
    with _hls_locks_guard:
        lock = _hls_locks.setdefault(key, threading.Lock())
    with lock:
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
        os.makedirs(HLS_CACHE_DIR, exist_ok=True)
        _prune_hls_cache()
        partial = path + '.part.mp4'
        try:
            proc = subprocess.run(
                ['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-i', url,
                 '-c', 'copy', '-movflags', '+faststart', partial],
                capture_output=True, text=True, timeout=600)
        except FileNotFoundError:
            raise VscoSaverError('ffmpeg não encontrado - ele é necessário para juntar os vídeos do VSCO.')
        except subprocess.TimeoutExpired:
            raise VscoSaverError('O vídeo demorou demais para baixar. Tente de novo.')
        if proc.returncode != 0 or not os.path.isfile(partial):
            detail = (proc.stderr or '').strip().splitlines()
            raise VscoSaverError('Falha ao juntar o vídeo: ' + (detail[-1] if detail else 'erro do ffmpeg'))
        os.replace(partial, path)
        return path
