"""Motor do InstaSaver: resolve um link do Instagram (story, destaque, perfil,
post ou reel) e lista stories, destaques e posts do perfil dono do link.

Funciona como a versão "privada" de sites tipo SaveClip, só que automática:
lá o usuário abre o view-source da página do Instagram no próprio navegador
logado e cola o HTML; aqui o motor carrega essas mesmas páginas (e as mesmas
consultas GraphQL que a página dispara) com a sessão já logada no navegador
local. Os cookies são lidos pelo mesmo leitor que o yt-dlp usa em
--cookies-from-browser e nada sai da máquina além das requisições ao
Instagram. Só aparece o que a conta logada já pode ver.

Sem sessão não há caminho: o Instagram responde 403/vazio para visitantes
deslogados (inclusive o extrator do yt-dlp), e stories sempre exigem login.
"""
import os
import re
import json
import time
import threading
import concurrent.futures
from datetime import datetime
from http.cookiejar import MozillaCookieJar
from urllib.parse import urlparse

import requests

try:
    # Imita a impressão digital TLS do Chrome; com requests puro o Instagram
    # responde 429 para boa parte das rotas mesmo com sessão válida.
    from curl_cffi import requests as ig_requests
    _IMPERSONATE = {'impersonate': 'chrome'}
except ImportError:
    ig_requests = requests
    _IMPERSONATE = {}

_DIR = os.path.dirname(os.path.abspath(__file__))
IG_APP_ID = '936619743392459'
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')
BROWSERS = ('chrome', 'firefox', 'chromium', 'brave', 'edge', 'opera', 'vivaldi')
MEDIA_HOST_SUFFIXES = ('.cdninstagram.com', '.fbcdn.net')
SESSION_TTL = 15 * 60
TOKEN_TTL = 20 * 60

# doc_id de cada consulta GraphQL que o site do Instagram usa. A Meta troca
# esses números de tempos em tempos; quando uma consulta falha, o motor
# procura os atuais nos scripts do próprio site (_refresh_doc_ids).
DEFAULT_DOC_IDS = {
    'PolarisProfilePageContentQuery': '28036671149327607',
    'PolarisProfilePostsTabContentQuery_connection': '38620137654299531',
    'PolarisProfileStoryHighlightsTrayContentQuery': '26970053832668570',
    'PolarisPostRootQuery': '27830990013244856',
}
_DOC_IDS_FILE = os.path.join(_DIR, '.doc_ids.json')


class InstaSaverError(Exception):
    pass


# ---------------------------------------------------------------- sessão ---

_session_lock = threading.Lock()
_session_cache = {'session': None, 'source': None, 'at': 0}
_tokens = {'lsd': None, 'fb_dtsg': None, 'at': 0}


def _load_cookie_jar():
    """Procura uma sessão do Instagram (cookie sessionid). Ordem: arquivo
    cookies.txt em INSTASAVER_COOKIES, navegador em INSTASAVER_BROWSER, e por
    fim cada navegador suportado até achar um logado."""
    cookies_file = os.environ.get('INSTASAVER_COOKIES')
    if cookies_file and os.path.isfile(cookies_file):
        jar = MozillaCookieJar(cookies_file)
        jar.load(ignore_discard=True, ignore_expires=True)
        if _has_session(jar):
            return jar, f'arquivo {os.path.basename(cookies_file)}'

    from yt_dlp.cookies import extract_cookies_from_browser

    preferred = os.environ.get('INSTASAVER_BROWSER')
    browsers = ([preferred] if preferred else []) + [b for b in BROWSERS if b != preferred]
    for browser in browsers:
        try:
            jar = extract_cookies_from_browser(browser, logger=_SilentLogger())
        except Exception:
            continue
        if _has_session(jar):
            return jar, browser
    return None, None


def _has_session(jar):
    # Cookie presente mas vazio = o Chrome não pôde ser descriptografado
    # (no Linux isso exige o pacote secretstorage).
    return any(c.name == 'sessionid' and c.value and 'instagram.com' in c.domain for c in jar)


class _SilentLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg, only_once=False): pass
    def error(self, msg): pass


def _get_session(force_refresh=False):
    with _session_lock:
        cached = _session_cache['session']
        if cached and not force_refresh and time.time() - _session_cache['at'] < SESSION_TTL:
            return cached

        jar, source = _load_cookie_jar()
        if jar is None:
            raise InstaSaverError(
                'Nenhuma sessão do Instagram encontrada. Faça login em instagram.com '
                'no Chrome ou Firefox deste computador e tente de novo.')

        session = ig_requests.Session(**_IMPERSONATE)
        for cookie in jar:
            if 'instagram.com' in cookie.domain:
                session.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
        if not _IMPERSONATE:
            session.headers['User-Agent'] = USER_AGENT
        _session_cache.update(session=session, source=source, at=time.time())
        _tokens.update(lsd=None, fb_dtsg=None, at=0)
        return session


def _cookie(name):
    cookies = _get_session().cookies
    for cookie in getattr(cookies, 'jar', cookies):  # curl_cffi expõe .jar; requests já é o jar
        if cookie.name == name and 'instagram.com' in cookie.domain:
            return cookie.value
    return None


def session_status():
    try:
        _get_session()
        return {'logged_in': True, 'source': _session_cache['source']}
    except InstaSaverError as e:
        return {'logged_in': False, 'error': str(e)}


def _check_status(resp):
    if resp.status_code == 404:
        raise InstaSaverError('Conteúdo não encontrado (link inválido, removido ou expirado).')
    if resp.status_code == 429:
        raise InstaSaverError('O Instagram limitou as requisições. Espere alguns minutos.')


# ------------------------------------------------------- páginas (view-source) ---

def _page(path, _retry=True):
    """Carrega a página como o navegador faria e devolve o HTML - é o mesmo
    conteúdo que aparece no view-source. Aproveita para guardar os tokens
    (lsd/fb_dtsg) que as consultas GraphQL exigem."""
    session = _get_session()
    try:
        resp = session.get(f'https://www.instagram.com{path}', timeout=25, allow_redirects=True)
    except Exception as e:
        raise InstaSaverError(f'Falha de conexão com o Instagram: {e}')
    _check_status(resp)
    html = resp.text
    if '/accounts/login' in str(resp.url) or 'not-logged-in' in html[:3000]:
        if _retry:
            _get_session(force_refresh=True)  # cookie pode ter sido renovado no navegador
            return _page(path, _retry=False)
        raise InstaSaverError(
            'O Instagram não reconheceu a sessão. Abra instagram.com no navegador, '
            'confirme que está logado e tente de novo.')

    lsd = re.search(r'\["LSD",\[\],\{"token":"([^"]+)"', html)
    dtsg = re.search(r'"DTSGInitialData",\[\],\{"token":"([^"]+)"', html)
    if lsd and dtsg:
        _tokens.update(lsd=lsd.group(1), fb_dtsg=dtsg.group(1), at=time.time())
    _tokens['last_html'] = html
    return html


def _sjs_find(html, key):
    """Procura `key` nos blocos JSON embutidos (<script data-sjs>) da página."""
    for match in re.finditer(r'<script type="application/json"[^>]*data-sjs>(.*?)</script>', html, re.S):
        if key not in match.group(1):
            continue
        try:
            data = json.loads(match.group(1))
        except ValueError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if key in node:
                    return node[key]
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return None


# --------------------------------------------------------------- GraphQL ---

def _load_doc_ids():
    ids = dict(DEFAULT_DOC_IDS)
    try:
        with open(_DOC_IDS_FILE, encoding='utf-8') as f:
            ids.update(json.load(f))
    except (OSError, ValueError):
        pass
    return ids


_doc_ids = _load_doc_ids()


def _refresh_doc_ids():
    """Lê os scripts públicos do site (os mesmos que o navegador baixa) e
    extrai os doc_id atuais de cada consulta. Não usa a conta."""
    html = _tokens.get('last_html') or _page('/')
    scripts = sorted(set(re.findall(
        r'"(https://static\.cdninstagram\.com/rsrc\.php/[^"]+\.js[^"]*)"', html.replace('\\/', '/'))))
    wanted = set(DEFAULT_DOC_IDS)
    found = {}
    anon = ig_requests.Session(**_IMPERSONATE)

    def scan(url):
        try:
            text = anon.get(url, timeout=30).text
        except Exception:
            return {}
        return {m.group(1): m.group(2) for m in re.finditer(
            r'__d\("(\w+)_instagramRelayOperation",\[\],\(function\([^)]*\)\{\w+\.exports="(\d+)"', text)
            if m.group(1) in wanted}

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        futures = [pool.submit(scan, url) for url in scripts]
        for future in concurrent.futures.as_completed(futures):
            found.update(future.result())
            if wanted <= set(found):
                for f in futures:
                    f.cancel()
                break
    if found:
        _doc_ids.update(found)
        try:
            with open(_DOC_IDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(_doc_ids, f, indent=2)
        except OSError:
            pass
    return found


def _gql(name, variables, root, _retry=True):
    """POST /graphql/query igual ao que a página faz; devolve data[root]."""
    if not _tokens.get('lsd') or time.time() - _tokens['at'] > TOKEN_TTL:
        _page('/')
    session = _get_session()
    form = {
        'av': _cookie('ds_user_id') or '0', '__user': '0', '__a': '1', '__comet_req': '7',
        'fb_dtsg': _tokens['fb_dtsg'], 'lsd': _tokens['lsd'],
        'fb_api_caller_class': 'RelayModern', 'fb_api_req_friendly_name': name,
        'variables': json.dumps(variables), 'server_timestamps': 'true', 'doc_id': _doc_ids[name],
    }
    headers = {
        'X-FB-LSD': _tokens['lsd'], 'X-FB-Friendly-Name': name, 'X-IG-App-ID': IG_APP_ID,
        'X-CSRFToken': _cookie('csrftoken') or '', 'X-ASBD-ID': '359341',
        'Origin': 'https://www.instagram.com', 'Referer': 'https://www.instagram.com/',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    try:
        resp = session.post('https://www.instagram.com/graphql/query', data=form,
                            headers=headers, timeout=25, allow_redirects=False)
    except Exception as e:
        raise InstaSaverError(f'Falha de conexão com o Instagram: {e}')
    _check_status(resp)
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if data.get('message') == 'feedback_required' or data.get('spam'):
        raise InstaSaverError('O Instagram pediu uma pausa nesta conta. Espere algumas horas antes de usar de novo.')

    if not isinstance(data.get('data'), dict):
        if _retry:
            # Tokens vencidos ou doc_id trocado pela Meta: renova os dois e tenta de novo.
            _page('/')
            _refresh_doc_ids()
            return _gql(name, variables, root, _retry=False)
        raise InstaSaverError('O Instagram não liberou este conteúdo agora. Tente de novo mais tarde.')
    return data['data'].get(root)


_PV_FALSE = lambda *names: {f'__relay_internal__pv__{n}relayprovider': False for n in names}


# ------------------------------------------------------------ parse link ---

def parse_link(raw):
    """Retorna dict com 'kind' em story|highlight|profile|post e o identificador."""
    text = (raw or '').strip()
    if not text:
        raise InstaSaverError('Cole um link do Instagram.')

    if re.fullmatch(r'@?[\w.]{1,30}', text):
        return {'kind': 'profile', 'username': text.lstrip('@').lower()}

    if not re.match(r'^https?://', text):
        text = 'https://' + text
    parsed = urlparse(text)
    host = parsed.netloc.lower()
    if not (host == 'instagram.com' or host.endswith('.instagram.com') or host == 'instagr.am'):
        raise InstaSaverError('Isso não parece um link do Instagram.')

    parts = [p for p in parsed.path.split('/') if p]
    if not parts:
        raise InstaSaverError('Link sem perfil ou conteúdo.')

    if parts[0] == 'stories' and len(parts) >= 2:
        if parts[1] == 'highlights' and len(parts) >= 3:
            return {'kind': 'highlight', 'highlight_id': parts[2]}
        return {'kind': 'story', 'username': parts[1].lower(),
                'story_pk': parts[2] if len(parts) >= 3 and parts[2].isdigit() else None}
    if parts[0] == 's' and len(parts) >= 2:
        # Link curto de destaque compartilhado (instagram.com/s/<base64>)
        import base64
        try:
            decoded = base64.b64decode(parts[1] + '=' * (-len(parts[1]) % 4)).decode()
            match = re.search(r'highlight:(\d+)', decoded)
            if match:
                return {'kind': 'highlight', 'highlight_id': match.group(1)}
        except Exception:
            pass
        raise InstaSaverError('Não consegui interpretar esse link curto de destaque.')
    if parts[0] in ('p', 'reel', 'reels', 'tv') and len(parts) >= 2:
        return {'kind': 'post', 'shortcode': parts[1]}
    if len(parts) >= 3 and parts[1] in ('p', 'reel', 'tv'):
        return {'kind': 'post', 'shortcode': parts[2]}
    if re.fullmatch(r'[\w.]{1,30}', parts[0]) and parts[0] not in ('explore', 'accounts', 'direct'):
        return {'kind': 'profile', 'username': parts[0].lower()}
    raise InstaSaverError('Tipo de link não suportado.')


# ------------------------------------------------------------ normalização ---

def _best_image(item):
    candidates = (item.get('image_versions2') or {}).get('candidates') or []
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.get('width', 0) * c.get('height', 0)).get('url')


def _best_video(item):
    versions = item.get('video_versions') or []
    if not versions:
        return None
    return max(versions, key=lambda v: v.get('width', 0) * v.get('height', 0)).get('url')


def _stamp(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%Y%m%d_%H%M%S')
    except (TypeError, ValueError):
        return 'sem_data'


def _media_entry(item, username, kind, index=None, taken_at=None):
    taken_at = item.get('taken_at') or taken_at  # itens de carrossel não trazem data própria
    video = _best_video(item)
    image = _best_image(item)
    ext = 'mp4' if video else 'jpg'
    suffix = f'_{index}' if index is not None else ''
    return {
        'id': str(item.get('pk') or item.get('id', '')).split('_')[0],
        'type': 'video' if video else 'image',
        'url': video or image,
        'thumb': image,
        'width': item.get('original_width'),
        'height': item.get('original_height'),
        'duration': item.get('video_duration'),
        'taken_at': taken_at,
        'filename': f"{username}_{kind}_{_stamp(taken_at)}_{item.get('pk', '')}{suffix}.{ext}",
    }


def _normalize_post(item, username):
    caption = (item.get('caption') or {}).get('text') or ''
    children = item.get('carousel_media') or []
    if children:
        media = [_media_entry(c, username, 'post', i + 1, item.get('taken_at')) for i, c in enumerate(children)]
    else:
        media = [_media_entry(item, username, 'reel' if item.get('product_type') == 'clips' else 'post')]
    media = [m for m in media if m['url']]
    return {
        'id': str(item.get('pk')),
        'code': item.get('code'),
        'permalink': f"https://www.instagram.com/p/{item.get('code')}/" if item.get('code') else None,
        'is_reel': item.get('product_type') == 'clips',
        'caption': caption,
        'taken_at': item.get('taken_at'),
        'like_count': item.get('like_count'),
        'comment_count': item.get('comment_count'),
        'play_count': item.get('play_count') or item.get('view_count'),
        'thumb': media[0]['thumb'] if media else None,
        'media': media,
    }


def _normalize_reel_items(items, username, kind):
    out = []
    for item in items or []:
        entry = _media_entry(item, username, kind)
        if entry['url']:
            out.append(entry)
    return out


# --------------------------------------------------------------- consultas ---

def get_profile(username):
    html = _page(f'/{username}/')
    match = re.search(r'"profile_id":"(\d+)"', html) or re.search(r'"props":\{"id":"(\d+)"', html)
    if not match:
        raise InstaSaverError(f'Perfil @{username} não encontrado.')
    user = _gql('PolarisProfilePageContentQuery', {
        'id': match.group(1), 'enable_integrity_filters': True,
        **_PV_FALSE('PolarisCannesGuardianExperienceEnabled', 'PolarisCASB976ProfileEnabled',
                    'PolarisWebSchoolsEnabled', 'PolarisRepostsConsumptionEnabled', 'PolarisShortDramaEnabled'),
    }, 'user')
    if not user:
        raise InstaSaverError(f'Perfil @{username} não encontrado.')
    return {
        'id': str(user.get('pk') or user.get('id')),
        'username': user.get('username') or username,
        'full_name': user.get('full_name'),
        'biography': user.get('biography'),
        'profile_pic': (user.get('hd_profile_pic_url_info') or {}).get('url') or user.get('profile_pic_url'),
        'is_private': bool(user.get('is_private')),
        'is_verified': bool(user.get('is_verified')),
        'followed_by_viewer': bool((user.get('friendship_status') or {}).get('following')),
        'followers': user.get('follower_count'),
        'following': user.get('following_count'),
        'posts_count': user.get('media_count'),
    }


def get_stories(username):
    # A página /stories/<usuário>/ já vem com os stories embutidos no HTML
    # (é exatamente o que o SaveClip pede para copiar do view-source).
    html = _page(f'/stories/{username}/')
    data = _sjs_find(html, 'xdt_api__v1__feed__reels_media') or {}
    for reel in data.get('reels_media') or []:
        if (reel.get('user') or {}).get('username', '').lower() == username.lower():
            return _normalize_reel_items(reel.get('items'), username, 'story')
    return []  # sem stories ativos: o Instagram manda para o perfil


def get_highlights_tray(user_id):
    conn = _gql('PolarisProfileStoryHighlightsTrayContentQuery', {
        'user_id': user_id, 'first': 100, 'after': None, 'before': None, 'last': None,
        'max_highlights_to_fetch_on_pagination': 100,
    }, 'highlights') or {}
    tray = []
    for edge in conn.get('edges') or []:
        h = edge.get('node') or {}
        tray.append({
            'id': str(h.get('id', '')).replace('highlight:', ''),
            'title': h.get('title') or '',
            'cover': ((h.get('cover_media') or {}).get('cropped_image_version') or {}).get('url'),
            'count': h.get('media_count'),
        })
    return tray


def get_highlight(highlight_id):
    html = _page(f'/stories/highlights/{highlight_id}/')
    conn = _sjs_find(html, 'xdt_api__v1__feed__reels_media__connection') or {}
    reel = next((e.get('node') for e in conn.get('edges') or []
                 if str((e.get('node') or {}).get('id', '')).endswith(highlight_id)), None)
    if not reel:
        raise InstaSaverError('Destaque não encontrado ou sem permissão para ver.')
    user = reel.get('user') or {}
    username = user.get('username') or 'instagram'
    return {
        'id': highlight_id,
        'title': reel.get('title') or '',
        'username': username,
        'user_id': str(user.get('pk') or user.get('id') or ''),
        'items': _normalize_reel_items(reel.get('items'), username, 'destaque'),
    }


def get_posts(username, cursor=None):
    conn = _gql('PolarisProfilePostsTabContentQuery_connection', {
        'data': {'count': 12, 'include_reel_media_seen_timestamp': True, 'include_relationship_info': True,
                 'latest_besties_reel_media': True, 'latest_reel_media': True},
        'username': username, 'first': 12, 'after': cursor, 'before': None, 'last': None,
        'include_multi_captions': False,
        **_PV_FALSE('PolarisMultiCaptionCarouselEnabled', 'PolarisShortDramaEnabled',
                    'PolarisReelsRecoDebugOverlayEnabled'),
    }, 'xdt_api__v1__feed__user_timeline_graphql_connection') or {}
    page_info = conn.get('page_info') or {}
    return {
        'items': [_normalize_post(e['node'], username) for e in conn.get('edges') or [] if e.get('node')],
        'next_max_id': page_info.get('end_cursor') if page_info.get('has_next_page') else None,
    }


def get_post(shortcode):
    info = _gql('PolarisPostRootQuery', {
        'shortcode': shortcode,
        **_PV_FALSE('PolarisShortDramaEnabled', 'PolarisMultiCaptionCarouselEnabled'),
    }, 'xdt_api__v1__media__shortcode__web_info') or {}
    items = info.get('items') or []
    if not items:
        raise InstaSaverError('Post não encontrado ou sem permissão para ver.')
    item = items[0]
    username = (item.get('user') or {}).get('username') or 'instagram'
    return username, _normalize_post(item, username)


def _safe(fn, *args):
    """Uma seção que falha (ex.: destaques indisponíveis) não derruba o resto."""
    try:
        return fn(*args), None
    except InstaSaverError as e:
        return None, str(e)


def resolve(link):
    """Ponto de entrada: a partir de qualquer link, devolve o perfil e tudo
    que dá para ver dele, marcando qual conteúdo o link apontava (focus)."""
    target = parse_link(link)
    focus = {'kind': target['kind']}

    if target['kind'] == 'highlight':
        highlight = get_highlight(target['highlight_id'])
        username = highlight['username']
        focus['highlight'] = highlight
    elif target['kind'] == 'post':
        username, post = get_post(target['shortcode'])
        focus['post'] = post
    else:
        username = target['username']
        focus['story_pk'] = target.get('story_pk')

    profile = get_profile(username)
    username = profile['username']
    result = {'profile': profile, 'focus': focus, 'errors': {}}

    if profile['is_private'] and not profile['followed_by_viewer']:
        result['locked'] = True
        result.update(stories=[], highlights=[], posts={'items': [], 'next_max_id': None})
        return result

    for key, fn, args in (
        ('stories', get_stories, (username,)),
        ('highlights', get_highlights_tray, (profile['id'],)),
        ('posts', get_posts, (username,)),
    ):
        value, err = _safe(fn, *args)
        result[key] = value if value is not None else ([] if key != 'posts' else {'items': [], 'next_max_id': None})
        if err:
            result['errors'][key] = err
    return result


# ------------------------------------------------------------------ proxy ---

def is_allowed_media_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or '').lower()
    return parsed.scheme == 'https' and any(host.endswith(s) for s in MEDIA_HOST_SUFFIXES)


def open_media(url, range_header=None):
    """Abre a mídia na CDN (só hosts do Instagram/Facebook) repassando Range
    para o player de vídeo conseguir avançar/voltar."""
    if not is_allowed_media_url(url):
        raise InstaSaverError('URL de mídia não permitida.')
    headers = {'User-Agent': USER_AGENT, 'Referer': 'https://www.instagram.com/'}
    if range_header:
        headers['Range'] = range_header
    resp = requests.get(url, headers=headers, stream=True, timeout=30)
    if resp.status_code >= 400:
        resp.close()
        raise InstaSaverError('Link da mídia expirou - recarregue o perfil.')
    return resp
