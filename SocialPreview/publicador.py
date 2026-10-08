"""Social Preview: contas conectadas e publicação de um post em várias redes de uma vez.

Tudo pelas APIs oficiais, com as credenciais da própria pessoa salvas em
dados/contas.json (fora do git). Cada rede tem uma classe com `testar(conta)`,
que confere o acesso e devolve o perfil (nome, @, foto) usado nas prévias, e
`publicar(conta, item, ctx)`, que posta e devolve o link do post.

A página manda um "plano" (rede, formato, texto e mídias de cada destino) com
as imagens já recortadas no tamanho certo; vídeos sobem uma vez (/social/midia)
e são enquadrados aqui pelo ffmpeg. Cada publicação vira um job em segundo
plano; a página acompanha por /social/publicar/<job>.
"""

import base64
import datetime as dt
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode, urlsplit, parse_qsl

import requests

from . import midia as M
from . import redes as R
from .hospedagem import Hospedagem

_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS_DIR = os.path.join(_DIR, 'dados')
CONTAS_PATH = os.path.join(DADOS_DIR, 'contas.json')
HISTORICO_PATH = os.path.join(DADOS_DIR, 'historico.json')
MIDIAS_DIR = os.path.join(DADOS_DIR, 'midias')
AUDIOS_DIR = os.path.join(DADOS_DIR, 'audios')
JOBS_DIR = os.path.join(DADOS_DIR, 'jobs')

GRAPH = f'https://graph.facebook.com/{R.GRAPH_VERSAO}'
GRAPH_VIDEO = f'https://graph-video.facebook.com/{R.GRAPH_VERSAO}'
GRAPH_IG = f'https://graph.instagram.com/{R.GRAPH_VERSAO}'
THREADS = 'https://graph.threads.net/v1.0'
UA = 'Verto-SocialPreview/1.0'

_lock = threading.RLock()


class PublicarError(Exception):
    pass


# ---------- Armazenamento ----------

def _ler(caminho, padrao):
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return padrao


def _gravar(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, caminho)


def _contas():
    d = _ler(CONTAS_PATH, {})
    d.setdefault('contas', {})
    d.setdefault('config', {'hospedagem': 'auto'})
    return d


def _salvar_conta(rid, conta):
    with _lock:
        d = _contas()
        d['contas'][rid] = conta
        _gravar(CONTAS_PATH, d)


def _agora():
    return dt.datetime.now().isoformat(timespec='seconds')


# ---------- HTTP ----------

def _erro_de(r):
    """Mensagem legível a partir do corpo de erro de cada API."""
    try:
        j = r.json()
    except Exception:
        t = (r.text or '').strip()
        return f'HTTP {r.status_code}' + (f': {t[:200]}' if t else '')
    if isinstance(j, dict):
        e = j.get('error')
        if isinstance(e, dict):
            msg = e.get('error_user_msg') or e.get('message') or e.get('status') or json.dumps(e)[:200]
            if e.get('error_user_title'):
                msg = f"{e['error_user_title']}: {msg}"
            return msg
        if isinstance(e, str):
            return j.get('error_description') or j.get('message') or e
        for k in ('detail', 'description', 'message', 'title'):
            if j.get(k):
                det = j.get(k)
                if j.get('errors') and isinstance(j['errors'], list):
                    extra = '; '.join(str(x.get('message') or x) for x in j['errors'][:3] if isinstance(x, dict))
                    if extra and extra not in det:
                        det = f'{det} ({extra})'
                return str(det)
        if j.get('errors'):
            return '; '.join(str(x.get('message') or x) for x in j['errors'][:3] if isinstance(x, dict)) or str(j['errors'])[:200]
    return f'HTTP {r.status_code}: {str(j)[:200]}'


CONECTAR_S = 20  # se a rede nem responde (bloqueio, DNS), falha logo em vez de esperar o envio inteiro


def _prazo(kw, padrao):
    t = kw.pop('timeout', padrao)
    return t if isinstance(t, tuple) else (CONECTAR_S, t)


_rede_checada = False


def _checar_ipv6():
    """Em redes com IPv6 anunciado mas sem rota (comum em roteador doméstico), cada conexão
    perde o prazo inteiro no IPv6 antes de tentar o IPv4. Testa uma vez e, se o IPv6 não sai,
    usa só IPv4 (o urllib3 consulta allowed_gai_family a cada conexão)."""
    global _rede_checada
    if _rede_checada:
        return
    _rede_checada = True
    import socket
    import urllib3.util.connection as uc
    try:
        s = socket.create_connection(('2606:4700:4700::1111', 443), timeout=2.5)
        s.close()
    except OSError:
        uc.allowed_gai_family = lambda: socket.AF_INET


def _req(metodo, url, ok=(200, 201, 202, 204, 206), **kw):
    _checar_ipv6()
    kw['timeout'] = _prazo(kw, 120)
    h = kw.pop('headers', None) or {}
    h.setdefault('User-Agent', UA)
    try:
        r = requests.request(metodo, url, headers=h, **kw)
    except requests.RequestException as e:
        raise PublicarError(f'Sem conexão com {urlsplit(url).netloc}: {e.__class__.__name__}')
    if r.status_code not in ok:
        raise PublicarError(_erro_de(r))
    return r


def _json(r):
    try:
        return r.json()
    except Exception:
        return {}


def _mime(caminho):
    return mimetypes.guess_type(caminho)[0] or 'application/octet-stream'


def _esperar(funcao, limite, intervalo, msg_tempo):
    fim = time.time() + limite
    while True:
        pronto = funcao()
        if pronto:
            return pronto
        if time.time() > fim:
            raise PublicarError(msg_tempo)
        time.sleep(intervalo)


# ---------- Redes ----------

class Rede:
    id = ''
    campos_obrigatorios = ()

    def testar(self, conta):
        raise NotImplementedError

    def publicar(self, conta, item, ctx):
        raise NotImplementedError

    def renovar(self, conta):
        """Renova o token se precisar; devolve True se a conta mudou."""
        return False


def _dias_desde(iso):
    try:
        return (dt.datetime.now() - dt.datetime.fromisoformat(iso)).days
    except Exception:
        return 999


class Instagram(Rede):
    id = 'instagram'
    campos_obrigatorios = ('token',)

    def _base(self, conta):
        return GRAPH_IG if conta.get('_tipo') == 'ig' else GRAPH

    def testar(self, conta):
        token = conta['token'].strip()
        if token.startswith('IG'):
            j = _json(_req('GET', f'{GRAPH_IG}/me', params={
                'fields': 'user_id,username,name,profile_picture_url,account_type', 'access_token': token}))
            conta['_tipo'] = 'ig'
            conta['_ig_id'] = str(j.get('user_id') or j.get('id'))
            p = j
        else:
            conta['_tipo'] = 'fb'
            campos = 'instagram_business_account{id,username,name,profile_picture_url}'
            p = None
            try:
                j = _json(_req('GET', f'{GRAPH}/me/accounts', params={
                    'fields': f'name,{campos}', 'access_token': token, 'limit': 100}))
                for pg in j.get('data', []):
                    if pg.get('instagram_business_account'):
                        p = pg['instagram_business_account']
                        break
            except PublicarError:
                pass
            if not p:
                j = _json(_req('GET', f'{GRAPH}/me', params={'fields': campos, 'access_token': token}))
                p = j.get('instagram_business_account')
            if not p:
                raise PublicarError('Esse token não dá acesso a nenhuma conta profissional do Instagram ligada a uma Página.')
            conta['_ig_id'] = str(p['id'])
        usuario = p.get('username') or ''
        return {'nome': p.get('name') or usuario, 'usuario': usuario,
                'avatar': p.get('profile_picture_url') or '', 'url': f'https://www.instagram.com/{usuario}/'}

    def renovar(self, conta):
        if conta.get('_tipo') != 'ig' or _dias_desde(conta.get('renovado_em') or conta.get('conectado_em')) < 7:
            return False
        try:
            j = _json(_req('GET', f'{GRAPH_IG}/refresh_access_token', params={
                'grant_type': 'ig_refresh_token', 'access_token': conta['token']}))
        except PublicarError:
            return False
        if j.get('access_token'):
            conta['token'] = j['access_token']
            conta['renovado_em'] = _agora()
            return True
        return False

    def _container(self, conta, params):
        j = _json(_req('POST', f"{self._base(conta)}/{conta['_ig_id']}/media",
                       data={**params, 'access_token': conta['token']}))
        if not j.get('id'):
            raise PublicarError('O Instagram não devolveu o contêiner da mídia.')
        return j['id']

    def _pronto(self, conta, cid, video):
        def ver():
            j = _json(_req('GET', f'{self._base(conta)}/{cid}', params={
                'fields': 'status_code,status', 'access_token': conta['token']}))
            st = j.get('status_code')
            if st in ('FINISHED', 'PUBLISHED'):
                return True
            if st in ('ERROR', 'EXPIRED'):
                raise PublicarError(f"O Instagram recusou a mídia: {j.get('status') or st}")
            return False
        _esperar(ver, 900 if video else 120, 6 if video else 2,
                 'O Instagram demorou demais para processar a mídia.')

    def _publicar(self, conta, cid):
        j = _json(_req('POST', f"{self._base(conta)}/{conta['_ig_id']}/media_publish",
                       data={'creation_id': cid, 'access_token': conta['token']}))
        mid = j.get('id')
        url = ''
        try:
            url = _json(_req('GET', f'{self._base(conta)}/{mid}', params={
                'fields': 'permalink', 'access_token': conta['token']})).get('permalink', '')
        except PublicarError:
            pass
        return mid, url

    def _midia_params(self, m, ctx, item, carrossel=False):
        url = ctx['url_publica'](m['caminho'], m['mime'])
        if m['tipo'] == 'video':
            return {'media_type': 'VIDEO', 'video_url': url, **({'is_carousel_item': 'true'} if carrossel else {})}
        p = {'image_url': url}
        if carrossel:
            p['is_carousel_item'] = 'true'
        if item.get('alt'):
            p['alt_text'] = item['alt'][:1000]
        return p

    def publicar(self, conta, item, ctx):
        fid = item['formato']['id']
        midias = item['midias']
        legenda = item.get('texto', '')
        if fid == 'story':
            urls = []
            for i, m in enumerate(midias, 1):
                ctx['log'](f'Story {i} de {len(midias)}…')
                url = ctx['url_publica'](m['caminho'], m['mime'])
                cid = self._container(conta, {'media_type': 'STORIES',
                                              ('video_url' if m['tipo'] == 'video' else 'image_url'): url})
                self._pronto(conta, cid, m['tipo'] == 'video')
                urls.append(self._publicar(conta, cid)[1])
            return {'url': next((u for u in urls if u), ctx['perfil'].get('url', ''))}
        if fid == 'reels':
            m = midias[0]
            ctx['log']('Enviando o Reels…')
            cid = self._container(conta, {'media_type': 'REELS', 'caption': legenda, 'share_to_feed': 'true',
                                          'video_url': ctx['url_publica'](m['caminho'], m['mime'])})
            ctx['log']('O Instagram está processando o vídeo…')
            self._pronto(conta, cid, True)
            return {'url': self._publicar(conta, cid)[1]}
        if len(midias) == 1:
            p = self._midia_params(midias[0], ctx, item)
            p['caption'] = legenda
            cid = self._container(conta, p)
            self._pronto(conta, cid, False)
            return {'url': self._publicar(conta, cid)[1]}
        filhos = []
        for i, m in enumerate(midias, 1):
            ctx['log'](f'Carrossel: mídia {i} de {len(midias)}…')
            cid = self._container(conta, self._midia_params(m, ctx, item, carrossel=True))
            filhos.append((cid, m['tipo'] == 'video'))
        for cid, video in filhos:
            self._pronto(conta, cid, video)
        cid = self._container(conta, {'media_type': 'CAROUSEL', 'caption': legenda,
                                      'children': ','.join(c for c, _ in filhos)})
        self._pronto(conta, cid, False)
        return {'url': self._publicar(conta, cid)[1]}


class Facebook(Rede):
    id = 'facebook'
    campos_obrigatorios = ('token',)

    def testar(self, conta):
        token = conta['token'].strip()
        if conta.get('app_id') and conta.get('app_secret') and not conta.get('_trocado'):
            try:
                j = _json(_req('GET', f'{GRAPH}/oauth/access_token', params={
                    'grant_type': 'fb_exchange_token', 'client_id': conta['app_id'].strip(),
                    'client_secret': conta['app_secret'].strip(), 'fb_exchange_token': token}))
                if j.get('access_token'):
                    token = j['access_token']
                    conta['token'] = token
                    conta['_trocado'] = True
            except PublicarError:
                pass  # token de Página não precisa de troca
        paginas = []
        try:
            j = _json(_req('GET', f'{GRAPH}/me/accounts', params={
                'fields': 'id,name,access_token,picture{url},link', 'access_token': token, 'limit': 100}))
            paginas = j.get('data', [])
        except PublicarError:
            paginas = []
        if paginas:
            alvo = (conta.get('pagina_id') or '').strip()
            pg = next((p for p in paginas if p['id'] == alvo), None) if alvo else paginas[0]
            if not pg:
                raise PublicarError('O token não dá acesso à Página com esse ID.')
            conta['_pagina'] = {'id': pg['id'], 'token': pg['access_token']}
        else:
            pg = _json(_req('GET', f'{GRAPH}/me', params={'fields': 'id,name,picture{url},link', 'access_token': token}))
            conta['_pagina'] = {'id': pg['id'], 'token': token}
        return {'nome': pg.get('name', ''), 'usuario': pg.get('name', ''),
                'avatar': ((pg.get('picture') or {}).get('data') or {}).get('url', ''),
                'url': pg.get('link') or f"https://www.facebook.com/{pg['id']}",
                'extra': {'paginas': [{'id': p['id'], 'nome': p['name']} for p in paginas]}}

    def publicar(self, conta, item, ctx):
        pg = conta['_pagina']
        pid, tk = pg['id'], pg['token']
        fid = item['formato']['id']
        midias = item['midias']
        texto = item.get('texto', '')

        def foto(m, publicada, extra=None):
            with open(m['caminho'], 'rb') as f:
                return _json(_req('POST', f'{GRAPH}/{pid}/photos',
                                  data={'access_token': tk, 'published': 'true' if publicada else 'false', **(extra or {})},
                                  files={'source': (os.path.basename(m['caminho']), f, m['mime'])}, timeout=300))

        if fid == 'story':
            for i, m in enumerate(midias, 1):
                ctx['log'](f'Story {i} de {len(midias)}…')
                ph = foto(m, False)
                _req('POST', f'{GRAPH}/{pid}/photo_stories', data={'photo_id': ph['id'], 'access_token': tk})
            return {'url': ctx['perfil'].get('url', '')}
        if fid == 'reels':
            m = midias[0]
            tam = os.path.getsize(m['caminho'])
            ini = _json(_req('POST', f'{GRAPH}/{pid}/video_reels', data={'upload_phase': 'start', 'access_token': tk}))
            vid = ini['video_id']
            ctx['log']('Enviando o vídeo…')
            with open(m['caminho'], 'rb') as f:
                _req('POST', ini.get('upload_url') or f'https://rupload.facebook.com/video-upload/{R.GRAPH_VERSAO}/{vid}',
                     headers={'Authorization': f'OAuth {tk}', 'offset': '0', 'file_size': str(tam)},
                     data=f, timeout=1800)
            _req('POST', f'{GRAPH}/{pid}/video_reels', data={
                'upload_phase': 'finish', 'video_id': vid, 'video_state': 'PUBLISHED',
                'description': texto, 'access_token': tk})
            return {'url': f'https://www.facebook.com/reel/{vid}'}
        if not midias:
            dados = {'message': texto, 'access_token': tk}
            if item.get('link'):
                dados['link'] = item['link']
            j = _json(_req('POST', f'{GRAPH}/{pid}/feed', data=dados))
            return {'url': f"https://www.facebook.com/{j.get('id', pid)}"}
        if midias[0]['tipo'] == 'video':
            m = midias[0]
            ctx['log']('Enviando o vídeo…')
            with open(m['caminho'], 'rb') as f:
                j = _json(_req('POST', f'{GRAPH_VIDEO}/{pid}/videos', data={'description': texto, 'access_token': tk},
                               files={'source': (os.path.basename(m['caminho']), f, m['mime'])}, timeout=1800))
            return {'url': f"https://www.facebook.com/{pid}/videos/{j.get('id', '')}"}
        if len(midias) == 1:
            j = foto(midias[0], True, {'message': texto})
            return {'url': f"https://www.facebook.com/{j.get('post_id') or j.get('id')}"}
        ids = []
        for i, m in enumerate(midias, 1):
            ctx['log'](f'Foto {i} de {len(midias)}…')
            ids.append(foto(m, False)['id'])
        dados = {'message': texto, 'access_token': tk}
        for i, fb in enumerate(ids):
            dados[f'attached_media[{i}]'] = json.dumps({'media_fbid': fb})
        j = _json(_req('POST', f'{GRAPH}/{pid}/feed', data=dados))
        return {'url': f"https://www.facebook.com/{j.get('id', pid)}"}


class Threads(Rede):
    id = 'threads'
    campos_obrigatorios = ('token',)

    def testar(self, conta):
        j = _json(_req('GET', f'{THREADS}/me', params={
            'fields': 'id,username,name,threads_profile_picture_url', 'access_token': conta['token'].strip()}))
        conta['_uid'] = j['id']
        u = j.get('username', '')
        return {'nome': j.get('name') or u, 'usuario': u, 'avatar': j.get('threads_profile_picture_url', ''),
                'url': f'https://www.threads.com/@{u}'}

    def renovar(self, conta):
        if _dias_desde(conta.get('renovado_em') or conta.get('conectado_em')) < 7:
            return False
        try:
            j = _json(_req('GET', 'https://graph.threads.net/refresh_access_token', params={
                'grant_type': 'th_refresh_token', 'access_token': conta['token']}))
        except PublicarError:
            return False
        if j.get('access_token'):
            conta['token'] = j['access_token']
            conta['renovado_em'] = _agora()
            return True
        return False

    def _container(self, conta, params):
        j = _json(_req('POST', f"{THREADS}/{conta['_uid']}/threads", data={**params, 'access_token': conta['token']}))
        return j['id']

    def _pronto(self, conta, cid, video):
        def ver():
            j = _json(_req('GET', f'{THREADS}/{cid}', params={'fields': 'status,error_message',
                                                              'access_token': conta['token']}))
            if j.get('status') in ('FINISHED', 'PUBLISHED'):
                return True
            if j.get('status') in ('ERROR', 'EXPIRED'):
                raise PublicarError(f"O Threads recusou a mídia: {j.get('error_message') or j.get('status')}")
            return False
        _esperar(ver, 600 if video else 120, 5 if video else 2, 'O Threads demorou demais para processar a mídia.')

    def _item(self, m, ctx, item, carrossel):
        url = ctx['url_publica'](m['caminho'], m['mime'])
        p = {'media_type': 'VIDEO', 'video_url': url} if m['tipo'] == 'video' else {'media_type': 'IMAGE', 'image_url': url}
        if carrossel:
            p['is_carousel_item'] = 'true'
        if item.get('alt') and m['tipo'] == 'imagem':
            p['alt_text'] = item['alt'][:1000]
        return p

    def publicar(self, conta, item, ctx):
        midias, texto = item['midias'], item.get('texto', '')
        if not midias:
            p = {'media_type': 'TEXT', 'text': texto}
            if item.get('link'):
                p['link_attachment'] = item['link']
            cid = self._container(conta, p)
        elif len(midias) == 1:
            cid = self._container(conta, {**self._item(midias[0], ctx, item, False), 'text': texto})
            self._pronto(conta, cid, midias[0]['tipo'] == 'video')
        else:
            filhos = []
            for i, m in enumerate(midias, 1):
                ctx['log'](f'Carrossel: mídia {i} de {len(midias)}…')
                filhos.append((self._container(conta, self._item(m, ctx, item, True)), m['tipo'] == 'video'))
            for c, v in filhos:
                self._pronto(conta, c, v)
            cid = self._container(conta, {'media_type': 'CAROUSEL', 'text': texto,
                                          'children': ','.join(c for c, _ in filhos)})
            self._pronto(conta, cid, False)
        j = _json(_req('POST', f"{THREADS}/{conta['_uid']}/threads_publish",
                       data={'creation_id': cid, 'access_token': conta['token']}))
        url = ''
        try:
            url = _json(_req('GET', f"{THREADS}/{j['id']}", params={'fields': 'permalink',
                                                                    'access_token': conta['token']})).get('permalink', '')
        except (PublicarError, KeyError):
            pass
        return {'url': url or ctx['perfil'].get('url', '')}


def _pct(s):
    return quote(str(s), safe='-._~')


def oauth1_header(metodo, url, consumer_key, consumer_secret, token, token_secret, params=None):
    """Cabeçalho OAuth 1.0a (HMAC-SHA1). `params` = query string e campos de formulário
    urlencoded; corpo JSON e multipart não entram na assinatura."""
    partes = urlsplit(url)
    base_url = f'{partes.scheme}://{partes.netloc}{partes.path}'
    oauth = {
        'oauth_consumer_key': consumer_key, 'oauth_nonce': secrets.token_hex(16),
        'oauth_signature_method': 'HMAC-SHA1', 'oauth_timestamp': str(int(time.time())),
        'oauth_token': token, 'oauth_version': '1.0',
    }
    todos = list(parse_qsl(partes.query, keep_blank_values=True)) + list((params or {}).items()) + list(oauth.items())
    norm = '&'.join(f'{k}={v}' for k, v in sorted((_pct(k), _pct(v)) for k, v in todos))
    base = '&'.join([metodo.upper(), _pct(base_url), _pct(norm)])
    chave = f'{_pct(consumer_secret)}&{_pct(token_secret)}'
    oauth['oauth_signature'] = base64.b64encode(hmac.new(chave.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return 'OAuth ' + ', '.join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


class X(Rede):
    id = 'x'
    campos_obrigatorios = ('api_key', 'api_secret', 'access_token', 'access_secret')
    API = 'https://api.x.com/2'

    def _auth(self, conta, metodo, url, params=None):
        return {'Authorization': oauth1_header(metodo, url, conta['api_key'].strip(), conta['api_secret'].strip(),
                                               conta['access_token'].strip(), conta['access_secret'].strip(), params)}

    def testar(self, conta):
        url = f'{self.API}/users/me?user.fields=profile_image_url,username,name'
        j = _json(_req('GET', url, headers=self._auth(conta, 'GET', url))).get('data') or {}
        if not j:
            raise PublicarError('A X não devolveu o perfil.')
        u = j.get('username', '')
        return {'nome': j.get('name', u), 'usuario': u,
                'avatar': (j.get('profile_image_url') or '').replace('_normal.', '_200x200.'),
                'url': f'https://x.com/{u}'}

    def _imagem(self, conta, m):
        url = f'{self.API}/media/upload'
        with open(m['caminho'], 'rb') as f:
            j = _json(_req('POST', url, headers=self._auth(conta, 'POST', url),
                           data={'media_category': 'tweet_image'},
                           files={'media': (os.path.basename(m['caminho']), f, m['mime'])}, timeout=300))
        mid = (j.get('data') or {}).get('id')
        if not mid:
            raise PublicarError('A X não devolveu o id da imagem.')
        return mid

    def _video(self, conta, m, ctx):
        tam = os.path.getsize(m['caminho'])
        url = f'{self.API}/media/upload/initialize'
        j = _json(_req('POST', url, headers=self._auth(conta, 'POST', url),
                       json={'media_type': 'video/mp4', 'total_bytes': tam, 'media_category': 'tweet_video'}))
        mid = j['data']['id']
        with open(m['caminho'], 'rb') as f:
            i = 0
            while True:
                bloco = f.read(4 * 1024 * 1024)
                if not bloco:
                    break
                ctx['log'](f'Enviando o vídeo ({min(100, int((i + 1) * 4 * 1024 * 1024 * 100 / tam))}%)…')
                url = f'{self.API}/media/upload/{mid}/append'
                _req('POST', url, headers=self._auth(conta, 'POST', url), data={'segment_index': str(i)},
                     files={'media': ('blob', bloco, 'application/octet-stream')}, timeout=600)
                i += 1
        url = f'{self.API}/media/upload/{mid}/finalize'
        j = _json(_req('POST', url, headers=self._auth(conta, 'POST', url)))
        info = (j.get('data') or {}).get('processing_info')
        while info and info.get('state') in ('pending', 'in_progress'):
            time.sleep(max(1, int(info.get('check_after_secs') or 3)))
            url = f'{self.API}/media/upload?command=STATUS&media_id={mid}'
            info = (_json(_req('GET', url, headers=self._auth(conta, 'GET', url))).get('data') or {}).get('processing_info')
        if info and info.get('state') == 'failed':
            raise PublicarError('A X não conseguiu processar o vídeo: ' + str((info.get('error') or {}).get('message', '')))
        return mid

    def publicar(self, conta, item, ctx):
        ids = []
        for m in item['midias']:
            ids.append(self._video(conta, m, ctx) if m['tipo'] == 'video' else self._imagem(conta, m))
        corpo = {'text': item.get('texto', '')}
        if ids:
            corpo['media'] = {'media_ids': ids}
        url = f'{self.API}/tweets'
        j = _json(_req('POST', url, headers=self._auth(conta, 'POST', url), json=corpo))
        tid = (j.get('data') or {}).get('id', '')
        return {'url': f"https://x.com/{ctx['perfil'].get('usuario') or 'i'}/status/{tid}"}


def _versao_linkedin(meses_atras=1):
    hoje = dt.date.today()
    a, m = hoje.year, hoje.month - meses_atras
    while m <= 0:
        m += 12
        a -= 1
    return f'{a}{m:02d}'


_LITTLE = re.compile(r'([\\|{}@\[\]()<>*_~])')


def little_text(texto):
    """Escapa o texto para o formato "little" do LinkedIn (senão parênteses e @ cortam o post).
    # seguido de palavra continua hashtag; # solto é escapado."""
    t = _LITTLE.sub(r'\\\1', texto)
    return re.sub(r'#(?!\w)', r'\\#', t)


class LinkedIn(Rede):
    id = 'linkedin'
    campos_obrigatorios = ('token',)

    def _h(self, conta, versao=None, extra=None):
        h = {'Authorization': f"Bearer {conta['token'].strip()}", 'X-Restli-Protocol-Version': '2.0.0',
             'LinkedIn-Version': versao or conta.get('_versao') or _versao_linkedin()}
        h.update(extra or {})
        return h

    def _rest(self, conta, metodo, caminho, **kw):
        """Chama /rest com a versão mensal; se ela já tiver saído do ar, tenta as anteriores."""
        ultimo = None
        for atras in (1, 2, 3, 5, 8):
            v = _versao_linkedin(atras)
            try:
                r = _req(metodo, f'https://api.linkedin.com/rest/{caminho}', headers=self._h(conta, v, kw.pop('extra', None)), **kw)
                conta['_versao'] = v
                return r
            except PublicarError as e:
                ultimo = e
                if 'version' not in str(e).lower():
                    raise
        raise ultimo

    def testar(self, conta):
        j = _json(_req('GET', 'https://api.linkedin.com/v2/userinfo',
                       headers={'Authorization': f"Bearer {conta['token'].strip()}"}))
        if not j.get('sub'):
            raise PublicarError('O token precisa dos escopos openid e profile.')
        conta['_autor'] = (conta.get('autor') or '').strip() or f"urn:li:person:{j['sub']}"
        return {'nome': j.get('name', ''), 'usuario': j.get('name', ''), 'avatar': j.get('picture', ''),
                'url': 'https://www.linkedin.com/in/me/'}

    def _imagem(self, conta, m):
        j = _json(self._rest(conta, 'POST', 'images?action=initializeUpload',
                             json={'initializeUploadRequest': {'owner': conta['_autor']}}))['value']
        with open(m['caminho'], 'rb') as f:
            _req('PUT', j['uploadUrl'], data=f, timeout=300,
                 headers={'Authorization': f"Bearer {conta['token'].strip()}", 'Content-Type': 'application/octet-stream'})
        return j['image']

    def _video(self, conta, m, ctx):
        tam = os.path.getsize(m['caminho'])
        j = _json(self._rest(conta, 'POST', 'videos?action=initializeUpload', json={'initializeUploadRequest': {
            'owner': conta['_autor'], 'fileSizeBytes': tam, 'uploadCaptions': False, 'uploadThumbnail': False}}))['value']
        etags = []
        with open(m['caminho'], 'rb') as f:
            partes = j['uploadInstructions']
            for i, p in enumerate(partes, 1):
                ctx['log'](f'Enviando o vídeo (parte {i} de {len(partes)})…')
                f.seek(p['firstByte'])
                bloco = f.read(p['lastByte'] - p['firstByte'] + 1)
                r = _req('PUT', p['uploadUrl'], data=bloco, timeout=900,
                         headers={'Content-Type': 'application/octet-stream'})
                etags.append(r.headers.get('etag', '').strip('"'))
        self._rest(conta, 'POST', 'videos?action=finalizeUpload', json={'finalizeUploadRequest': {
            'video': j['video'], 'uploadToken': j.get('uploadToken', ''), 'uploadedPartIds': etags}})
        return j['video']

    def publicar(self, conta, item, ctx):
        midias = item['midias']
        corpo = {
            'author': conta['_autor'], 'commentary': little_text(item.get('texto', '')), 'visibility': 'PUBLIC',
            'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': [], 'thirdPartyDistributionChannels': []},
            'lifecycleState': 'PUBLISHED', 'isReshareDisabledByAuthor': False,
        }
        alt = (item.get('alt') or '')[:4086]
        video = False
        if len(midias) == 1:
            m = midias[0]
            video = m['tipo'] == 'video'
            urn = self._video(conta, m, ctx) if video else self._imagem(conta, m)
            corpo['content'] = {'media': {'id': urn, **({'title': item.get('titulo') or ''} if video else {'altText': alt})}}
        elif midias:
            imgs = []
            for i, m in enumerate(midias, 1):
                ctx['log'](f'Imagem {i} de {len(midias)}…')
                imgs.append({'id': self._imagem(conta, m), 'altText': alt})
            corpo['content'] = {'multiImage': {'images': imgs}}
        tentativas = 12 if video else 1
        for t in range(tentativas):
            try:
                r = self._rest(conta, 'POST', 'posts', json=corpo)
                break
            except PublicarError:
                if t == tentativas - 1:
                    raise
                ctx['log']('O LinkedIn ainda está processando o vídeo…')
                time.sleep(8)
        urn = r.headers.get('x-restli-id', '')
        return {'url': f'https://www.linkedin.com/feed/update/{urn}/' if urn else ''}


class Bluesky(Rede):
    id = 'bluesky'
    campos_obrigatorios = ('handle', 'senha_app')

    def _sessao(self, conta):
        srv = (conta.get('servidor') or 'https://bsky.social').strip().rstrip('/')
        j = _json(_req('POST', f'{srv}/xrpc/com.atproto.server.createSession', json={
            'identifier': conta['handle'].strip().lstrip('@'), 'password': conta['senha_app'].strip()}))
        pds = srv
        for s in (j.get('didDoc') or {}).get('service', []):
            if s.get('id', '').endswith('atproto_pds') and s.get('serviceEndpoint'):
                pds = s['serviceEndpoint'].rstrip('/')
        return {'jwt': j['accessJwt'], 'did': j['did'], 'handle': j.get('handle', ''), 'pds': pds}

    def testar(self, conta):
        s = self._sessao(conta)
        p = {}
        try:
            p = _json(_req('GET', f"{s['pds']}/xrpc/app.bsky.actor.getProfile", params={'actor': s['did']},
                           headers={'Authorization': f"Bearer {s['jwt']}"}))
        except PublicarError:
            pass
        return {'nome': p.get('displayName') or s['handle'], 'usuario': s['handle'], 'avatar': p.get('avatar', ''),
                'url': f"https://bsky.app/profile/{s['handle']}"}

    def _facetas(self, texto, s):
        b = texto.encode('utf-8')
        out = []

        def faixa(ini, fim):
            return {'byteStart': len(texto[:ini].encode('utf-8')), 'byteEnd': len(texto[:fim].encode('utf-8'))}
        for m in re.finditer(r'https?://[^\s<>"\]\)]+[^\s<>"\]\).,;:!?]', texto):
            out.append({'index': faixa(m.start(), m.end()),
                        'features': [{'$type': 'app.bsky.richtext.facet#link', 'uri': m.group(0)}]})
        for m in re.finditer(r'(?<![\w#])#([^\s#.,;:!?()\[\]{}"\'<>]*[^\d\s#.,;:!?()\[\]{}"\'<>][^\s#.,;:!?()\[\]{}"\'<>]*)', texto):
            if len(m.group(1)) <= 64:
                out.append({'index': faixa(m.start(), m.end()),
                            'features': [{'$type': 'app.bsky.richtext.facet#tag', 'tag': m.group(1)}]})
        for m in re.finditer(r'(?<![\w@])@([a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,})', texto):
            try:
                did = _json(_req('GET', f"{s['pds']}/xrpc/com.atproto.identity.resolveHandle",
                                 params={'handle': m.group(1)}, timeout=15)).get('did')
            except PublicarError:
                did = None
            if did:
                out.append({'index': faixa(m.start(), m.end()),
                            'features': [{'$type': 'app.bsky.richtext.facet#mention', 'did': did}]})
        return out if b else []

    def publicar(self, conta, item, ctx):
        s = self._sessao(conta)
        auth = {'Authorization': f"Bearer {s['jwt']}"}
        texto = item.get('texto', '')
        reg = {'$type': 'app.bsky.feed.post', 'text': texto,
               'createdAt': dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z'), 'langs': ['pt']}
        fac = self._facetas(texto, s)
        if fac:
            reg['facets'] = fac
        if item['midias']:
            imgs = []
            for m in item['midias']:
                with open(m['caminho'], 'rb') as f:
                    blob = _json(_req('POST', f"{s['pds']}/xrpc/com.atproto.repo.uploadBlob", data=f.read(),
                                      headers={**auth, 'Content-Type': m['mime']}))['blob']
                imgs.append({'alt': (item.get('alt') or '')[:2000], 'image': blob,
                             'aspectRatio': {'width': int(m['w']), 'height': int(m['h'])}})
            reg['embed'] = {'$type': 'app.bsky.embed.images', 'images': imgs}
        j = _json(_req('POST', f"{s['pds']}/xrpc/com.atproto.repo.createRecord", headers=auth,
                       json={'repo': s['did'], 'collection': 'app.bsky.feed.post', 'record': reg}))
        rkey = (j.get('uri') or '').rsplit('/', 1)[-1]
        return {'url': f"https://bsky.app/profile/{s['handle']}/post/{rkey}"}


class Mastodon(Rede):
    id = 'mastodon'
    campos_obrigatorios = ('servidor', 'token')

    def _srv(self, conta):
        s = conta['servidor'].strip().rstrip('/')
        return s if s.startswith('http') else 'https://' + s

    def _h(self, conta):
        return {'Authorization': f"Bearer {conta['token'].strip()}"}

    def testar(self, conta):
        srv = self._srv(conta)
        j = _json(_req('GET', f'{srv}/api/v1/accounts/verify_credentials', headers=self._h(conta)))
        limite = 500
        try:
            inst = _json(_req('GET', f'{srv}/api/v2/instance', timeout=20))
            limite = int(((inst.get('configuration') or {}).get('statuses') or {}).get('max_characters') or 500)
        except (PublicarError, ValueError):
            pass
        return {'nome': j.get('display_name') or j.get('username', ''), 'usuario': j.get('acct', ''),
                'avatar': j.get('avatar', ''), 'url': j.get('url', ''), 'extra': {'max_texto': limite}}

    def publicar(self, conta, item, ctx):
        srv = self._srv(conta)
        ids = []
        for i, m in enumerate(item['midias'], 1):
            ctx['log'](f'Mídia {i} de {len(item["midias"])}…')
            with open(m['caminho'], 'rb') as f:
                j = _json(_req('POST', f'{srv}/api/v2/media', headers=self._h(conta), timeout=600,
                               data={'description': (item.get('alt') or '')[:1500]},
                               files={'file': (os.path.basename(m['caminho']), f, m['mime'])}))
            mid = j['id']
            if not j.get('url'):
                def pronto():
                    r = requests.get(f'{srv}/api/v1/media/{mid}', headers=self._h(conta), timeout=(CONECTAR_S, 30))
                    return r.status_code == 200 and _json(r).get('url')
                _esperar(pronto, 600, 3, 'O Mastodon demorou demais para processar a mídia.')
            ids.append(mid)
        dados = [('status', item.get('texto', '')), ('visibility', 'public')] + [('media_ids[]', i) for i in ids]
        j = _json(_req('POST', f'{srv}/api/v1/statuses', data=dados,
                       headers={**self._h(conta), 'Idempotency-Key': uuid.uuid4().hex}))
        return {'url': j.get('url', '')}


class Telegram(Rede):
    id = 'telegram'
    campos_obrigatorios = ('bot_token', 'chat_id')

    def _api(self, conta, metodo):
        return f"https://api.telegram.org/bot{conta['bot_token'].strip()}/{metodo}"

    def _chamar(self, conta, metodo, **kw):
        _checar_ipv6()
        try:
            r = requests.post(self._api(conta, metodo), timeout=_prazo(kw, 300), **kw)
        except requests.RequestException as e:
            raise PublicarError(f'Sem conexão com o Telegram: {e.__class__.__name__}')
        j = _json(r)
        if not j.get('ok'):
            raise PublicarError(j.get('description') or f'HTTP {r.status_code}')
        return j['result']

    def testar(self, conta):
        bot = self._chamar(conta, 'getMe')
        chat = self._chamar(conta, 'getChat', data={'chat_id': conta['chat_id'].strip()})
        u = chat.get('username', '')
        conta['_chat_username'] = u
        return {'nome': chat.get('title') or chat.get('first_name') or u, 'usuario': u or chat.get('title', ''),
                'avatar': '', 'url': f'https://t.me/{u}' if u else '', 'extra': {'bot': bot.get('username', '')}}

    def publicar(self, conta, item, ctx):
        chat = conta['chat_id'].strip()
        midias, texto = item['midias'], item.get('texto', '')
        if not midias:
            res = self._chamar(conta, 'sendMessage', data={'chat_id': chat, 'text': texto})
        elif len(midias) == 1:
            m = midias[0]
            video = m['tipo'] == 'video'
            with open(m['caminho'], 'rb') as f:
                dados = {'chat_id': chat, 'caption': texto}
                if video:
                    dados.update({'supports_streaming': 'true', 'width': int(m['w']), 'height': int(m['h']),
                                  'duration': int(m.get('dur') or 0)})
                res = self._chamar(conta, 'sendVideo' if video else 'sendPhoto', data=dados,
                                   files={'video' if video else 'photo': (os.path.basename(m['caminho']), f, m['mime'])})
        else:
            grupo, arquivos = [], {}
            try:
                for i, m in enumerate(midias):
                    nome = f'f{i}'
                    arquivos[nome] = (os.path.basename(m['caminho']), open(m['caminho'], 'rb'), m['mime'])
                    e = {'type': 'video' if m['tipo'] == 'video' else 'photo', 'media': f'attach://{nome}'}
                    if i == 0 and texto:
                        e['caption'] = texto
                    grupo.append(e)
                res = self._chamar(conta, 'sendMediaGroup', data={'chat_id': chat, 'media': json.dumps(grupo)},
                                   files=arquivos, timeout=900)
            finally:
                for a in arquivos.values():
                    a[1].close()
            res = res[0] if isinstance(res, list) and res else res
        u = conta.get('_chat_username')
        return {'url': f"https://t.me/{u}/{res.get('message_id')}" if u and isinstance(res, dict) else ''}


class Discord(Rede):
    id = 'discord'
    campos_obrigatorios = ('webhook',)

    def testar(self, conta):
        url = conta['webhook'].strip()
        if not re.match(r'https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+', url):
            raise PublicarError('Isso não parece uma URL de webhook do Discord.')
        j = _json(_req('GET', url))
        conta['_guild'], conta['_canal'] = j.get('guild_id', ''), j.get('channel_id', '')
        av = f"https://cdn.discordapp.com/avatars/{j['id']}/{j['avatar']}.png" if j.get('avatar') else ''
        return {'nome': j.get('name', 'Webhook'), 'usuario': j.get('name', ''), 'avatar': av,
                'url': f"https://discord.com/channels/{conta['_guild']}/{conta['_canal']}" if conta['_guild'] else ''}

    def publicar(self, conta, item, ctx):
        anexos, arquivos = [], {}
        try:
            for i, m in enumerate(item['midias']):
                nome = os.path.basename(m['caminho'])
                anexos.append({'id': i, 'filename': nome, **({'description': item['alt'][:1024]} if item.get('alt') else {})})
                arquivos[f'files[{i}]'] = (nome, open(m['caminho'], 'rb'), m['mime'])
            payload = {'content': item.get('texto', ''), 'attachments': anexos}
            j = _json(_req('POST', conta['webhook'].strip() + '?wait=true', timeout=600,
                           data={'payload_json': json.dumps(payload)}, files=arquivos or None))
        finally:
            for a in arquivos.values():
                a[1].close()
        g, c = conta.get('_guild'), j.get('channel_id') or conta.get('_canal')
        return {'url': f"https://discord.com/channels/{g}/{c}/{j.get('id')}" if g and c else ''}


class Pinterest(Rede):
    id = 'pinterest'
    campos_obrigatorios = ('token',)

    def _base(self, conta):
        return 'https://api-sandbox.pinterest.com/v5' if conta.get('sandbox') else 'https://api.pinterest.com/v5'

    def _h(self, conta):
        return {'Authorization': f"Bearer {conta['token'].strip()}"}

    def testar(self, conta):
        b = self._base(conta)
        u = _json(_req('GET', f'{b}/user_account', headers=self._h(conta)))
        pastas = _json(_req('GET', f'{b}/boards', params={'page_size': 100}, headers=self._h(conta))).get('items', [])
        if not pastas:
            raise PublicarError('A conta não tem nenhuma pasta: crie uma no Pinterest primeiro.')
        alvo = (conta.get('pasta') or '').strip()
        if alvo and not any(p['id'] == alvo for p in pastas):
            raise PublicarError('Não achei a pasta com esse ID.')
        conta['_pasta'] = alvo or pastas[0]['id']
        nome = u.get('business_name') or u.get('username', '')
        return {'nome': nome, 'usuario': u.get('username', ''), 'avatar': u.get('profile_image', ''),
                'url': f"https://www.pinterest.com/{u.get('username', '')}/",
                'extra': {'pastas': [{'id': p['id'], 'nome': p['name']} for p in pastas]}}

    def publicar(self, conta, item, ctx):
        m = item['midias'][0]
        with open(m['caminho'], 'rb') as f:
            dados = base64.b64encode(f.read()).decode()
        corpo = {'board_id': (item.get('opcoes') or {}).get('pasta') or conta['_pasta'],
                 'title': (item.get('titulo') or '')[:100], 'description': item.get('texto', '')[:500],
                 'media_source': {'source_type': 'image_base64', 'content_type': 'image/jpeg', 'data': dados}}
        if item.get('link'):
            corpo['link'] = item['link']
        if item.get('alt'):
            corpo['alt_text'] = item['alt'][:500]
        j = _json(_req('POST', f'{self._base(conta)}/pins', headers=self._h(conta), json=corpo))
        return {'url': f"https://www.pinterest.com/pin/{j.get('id')}/"}


_OAUTH_ESTADOS = {}


class YouTube(Rede):
    id = 'youtube'
    campos_obrigatorios = ('client_id', 'client_secret')
    ESCOPOS = 'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly'

    def iniciar_oauth(self, conta, redirect):
        estado = secrets.token_urlsafe(16)
        verificador = secrets.token_urlsafe(48)
        desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).decode().rstrip('=')
        _OAUTH_ESTADOS[estado] = {'verificador': verificador, 'redirect': redirect, 'quando': time.time()}
        return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
            'client_id': conta['client_id'].strip(), 'redirect_uri': redirect, 'response_type': 'code',
            'scope': self.ESCOPOS, 'access_type': 'offline', 'prompt': 'consent', 'state': estado,
            'code_challenge': desafio, 'code_challenge_method': 'S256'})

    def concluir_oauth(self, conta, codigo, estado):
        e = _OAUTH_ESTADOS.pop(estado, None)
        if not e:
            raise PublicarError('Login expirado: tente "Entrar com Google" de novo.')
        j = _json(_req('POST', 'https://oauth2.googleapis.com/token', data={
            'code': codigo, 'client_id': conta['client_id'].strip(), 'client_secret': conta['client_secret'].strip(),
            'redirect_uri': e['redirect'], 'grant_type': 'authorization_code', 'code_verifier': e['verificador']}))
        if not j.get('refresh_token'):
            raise PublicarError('O Google não devolveu o token de renovação.')
        conta['_refresh'] = j['refresh_token']
        conta['_access'] = j['access_token']
        conta['_expira'] = time.time() + int(j.get('expires_in', 3600)) - 60

    def _token(self, conta):
        if not conta.get('_refresh'):
            raise PublicarError('Falta entrar com a conta Google (botão "Entrar com Google").')
        if conta.get('_access') and time.time() < conta.get('_expira', 0):
            return conta['_access']
        j = _json(_req('POST', 'https://oauth2.googleapis.com/token', data={
            'client_id': conta['client_id'].strip(), 'client_secret': conta['client_secret'].strip(),
            'refresh_token': conta['_refresh'], 'grant_type': 'refresh_token'}))
        conta['_access'] = j['access_token']
        conta['_expira'] = time.time() + int(j.get('expires_in', 3600)) - 60
        return conta['_access']

    def testar(self, conta):
        tk = self._token(conta)
        j = _json(_req('GET', 'https://www.googleapis.com/youtube/v3/channels',
                       params={'part': 'snippet', 'mine': 'true'}, headers={'Authorization': f'Bearer {tk}'}))
        if not j.get('items'):
            raise PublicarError('Essa conta Google não tem canal no YouTube.')
        sn = j['items'][0]['snippet']
        return {'nome': sn.get('title', ''), 'usuario': (sn.get('customUrl') or sn.get('title', '')).lstrip('@'),
                'avatar': ((sn.get('thumbnails') or {}).get('default') or {}).get('url', ''),
                'url': f"https://www.youtube.com/channel/{j['items'][0]['id']}"}

    def publicar(self, conta, item, ctx):
        tk = self._token(conta)
        m = item['midias'][0]
        texto = item.get('texto', '')
        titulo = (item.get('titulo') or texto.split('\n', 1)[0] or 'Vídeo')[:100]
        privacidade = (item.get('opcoes') or {}).get('privacidade') or 'public'
        meta = {'snippet': {'title': titulo, 'description': texto[:5000], 'categoryId': '22'},
                'status': {'privacyStatus': privacidade, 'selfDeclaredMadeForKids': False}}
        tam = os.path.getsize(m['caminho'])
        r = _req('POST', 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
                 headers={'Authorization': f'Bearer {tk}', 'Content-Type': 'application/json; charset=UTF-8',
                          'X-Upload-Content-Type': 'video/mp4', 'X-Upload-Content-Length': str(tam)}, json=meta)
        destino = r.headers.get('Location')
        ctx['log']('Enviando o vídeo para o YouTube…')
        with open(m['caminho'], 'rb') as f:
            j = _json(_req('PUT', destino, data=f, timeout=3600,
                           headers={'Authorization': f'Bearer {tk}', 'Content-Type': 'video/mp4'}))
        vid = j.get('id', '')
        url = f'https://youtube.com/shorts/{vid}' if item['formato']['id'] == 'shorts' else f'https://youtu.be/{vid}'
        return {'url': url}


CONECTORES = {c.id: c() for c in (Instagram, Facebook, Threads, X, LinkedIn, Bluesky, Mastodon, Telegram,
                                  Discord, Pinterest, YouTube)}


# ---------- Contas (rotas) ----------

def _publica(rid, conta):
    """O que a página pode ver de uma conta: nunca os segredos."""
    r = R.rede(rid) or {}
    campos = {}
    for c in (r.get('conta') or {}).get('campos', []):
        v = conta.get(c['id'])
        if c['tipo'] == 'password':
            campos[c['id']] = bool(v)
        else:
            campos[c['id']] = v if v not in (None, '') else ''
    return {'conectada': bool(conta.get('perfil')), 'perfil': conta.get('perfil'), 'campos': campos,
            'conectado_em': conta.get('conectado_em'), 'erro': conta.get('erro'),
            'oauth_pronto': bool(conta.get('_refresh')) if rid == 'youtube' else None}


def status():
    d = _contas()
    return {'contas': {rid: _publica(rid, c) for rid, c in d['contas'].items()}, 'config': d['config']}


def salvar(rid, campos):
    if rid not in CONECTORES:
        raise PublicarError('Essa rede não tem publicação direta.')
    rede = R.rede(rid)
    with _lock:
        atual = dict(_contas()['contas'].get(rid) or {})
    nova = dict(atual)
    for c in rede['conta']['campos']:
        v = campos.get(c['id'])
        if c['tipo'] == 'checkbox':
            nova[c['id']] = bool(v)
        elif isinstance(v, str) and (v.strip() or c['tipo'] != 'password'):
            nova[c['id']] = v.strip()
    # Trocou a credencial principal: o que foi derivado dela não vale mais.
    if any(nova.get(k) != atual.get(k) for k in CONECTORES[rid].campos_obrigatorios):
        for k in [k for k in nova if k.startswith('_')]:
            nova.pop(k)
    faltam = [c['rotulo'] for c in rede['conta']['campos']
              if not c.get('opcional') and c['tipo'] != 'checkbox' and not nova.get(c['id'])]
    if faltam:
        raise PublicarError('Preencha: ' + ', '.join(faltam))
    if rid == 'youtube' and not nova.get('_refresh'):
        nova.pop('perfil', None)
        _salvar_conta(rid, nova)
        return {'conta': _publica(rid, nova), 'precisa_oauth': True}
    perfil = CONECTORES[rid].testar(nova)
    nova['perfil'] = perfil
    nova['conectado_em'] = nova.get('conectado_em') or _agora()
    nova.pop('erro', None)
    _salvar_conta(rid, nova)
    return {'conta': _publica(rid, nova)}


def testar(rid):
    with _lock:
        conta = dict(_contas()['contas'].get(rid) or {})
    if not conta:
        raise PublicarError('Conta não conectada.')
    try:
        CONECTORES[rid].renovar(conta)
        conta['perfil'] = CONECTORES[rid].testar(conta)
        conta.pop('erro', None)
    except PublicarError as e:
        conta['erro'] = str(e)
        _salvar_conta(rid, conta)
        raise
    _salvar_conta(rid, conta)
    return {'conta': _publica(rid, conta)}


def desconectar(rid):
    with _lock:
        d = _contas()
        d['contas'].pop(rid, None)
        _gravar(CONTAS_PATH, d)
    return {}


def configurar(cfg):
    with _lock:
        d = _contas()
        if cfg.get('hospedagem') in ('auto', 'tunel', 'litterbox'):
            d['config']['hospedagem'] = cfg['hospedagem']
        _gravar(CONTAS_PATH, d)
        return {'config': d['config']}


def oauth_iniciar(rid, redirect):
    with _lock:
        conta = dict(_contas()['contas'].get(rid) or {})
    if rid != 'youtube' or not conta.get('client_id'):
        raise PublicarError('Salve o ID e a chave do cliente antes de entrar.')
    return CONECTORES[rid].iniciar_oauth(conta, redirect)


def oauth_concluir(rid, codigo, estado):
    with _lock:
        conta = dict(_contas()['contas'].get(rid) or {})
    CONECTORES[rid].concluir_oauth(conta, codigo, estado)
    conta['perfil'] = CONECTORES[rid].testar(conta)
    conta['conectado_em'] = _agora()
    conta.pop('erro', None)
    _salvar_conta(rid, conta)
    return conta['perfil']


# ---------- Mídias enviadas ----------

def _limpar_antigos(pasta, horas=48):
    if not os.path.isdir(pasta):
        return
    limite = time.time() - horas * 3600
    for nome in os.listdir(pasta):
        p = os.path.join(pasta, nome)
        try:
            if os.path.getmtime(p) < limite:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        except OSError:
            pass


def guardar_midia(arquivo):
    """Guarda o vídeo original (o recorte de cada rede é feito na hora de publicar)."""
    os.makedirs(MIDIAS_DIR, exist_ok=True)
    _limpar_antigos(MIDIAS_DIR)
    ext = os.path.splitext(arquivo.filename or '')[1].lower()
    if ext not in ('.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi'):
        ext = '.mp4'
    mid = uuid.uuid4().hex
    caminho = os.path.join(MIDIAS_DIR, mid + ext)
    arquivo.save(caminho)
    try:
        info = M.sondar(caminho)
    except M.MidiaError:
        os.remove(caminho)
        raise
    return {'id': mid, 'info': info}


def _origem(mid):
    if not re.fullmatch(r'[0-9a-f]{32}', mid or ''):
        raise PublicarError('Mídia inválida.')
    for nome in os.listdir(MIDIAS_DIR) if os.path.isdir(MIDIAS_DIR) else []:
        if nome.startswith(mid):
            return os.path.join(MIDIAS_DIR, nome)
    raise PublicarError('O vídeo original não está mais no Verto: adicione-o de novo.')


_render_locks = {}


def renderizar(mid, w, h, enq, max_s=None):
    """Vídeo enquadrado W×H; o mesmo pedido em várias redes é feito uma vez só."""
    origem = _origem(mid)
    chave = hashlib.sha1(json.dumps([mid, w, h, enq, max_s], sort_keys=True).encode()).hexdigest()[:20]
    destino = os.path.join(MIDIAS_DIR, f'{mid}-{chave}.mp4')
    with _lock:
        trava = _render_locks.setdefault(chave, threading.Lock())
    with trava:
        if not os.path.exists(destino):
            tmp = destino[:-4] + '.tmp.mp4'
            M.renderizar_video(origem, tmp, int(w), int(h), enq or {}, max_s)
            os.replace(tmp, destino)
    return destino


def guardar_audio(arquivo):
    """Guarda a música escolhida para as fotos (sobe uma vez; cada rede reaproveita)."""
    os.makedirs(AUDIOS_DIR, exist_ok=True)
    _limpar_antigos(AUDIOS_DIR)
    ext = os.path.splitext(arquivo.filename or '')[1].lower()
    if ext not in ('.mp3', '.m4a', '.aac', '.wav', '.ogg', '.oga', '.opus', '.flac', '.webm', '.mp4'):
        ext = '.mp3'
    aid = uuid.uuid4().hex
    caminho = os.path.join(AUDIOS_DIR, aid + ext)
    arquivo.save(caminho)
    try:
        info = M.sondar_audio(caminho)
    except M.MidiaError:
        os.remove(caminho)
        raise
    return {'id': aid, 'dur': info['dur']}


def _audio(aid):
    if not re.fullmatch(r'[0-9a-f]{32}', aid or ''):
        raise PublicarError('Música inválida.')
    for nome in os.listdir(AUDIOS_DIR) if os.path.isdir(AUDIOS_DIR) else []:
        if nome.startswith(aid):
            return os.path.join(AUDIOS_DIR, nome)
    raise PublicarError('A música não está mais no Verto: escolha-a de novo.')


def analisar(dados):
    try:
        return M.analisar_foco(dados)
    except Exception as e:
        raise PublicarError(f'Não deu para analisar a foto: {e}')


def renderizar_show(fotos, W, H, opcoes, audio_id=None):
    """Vídeo das fotos com música; `fotos` = bytes de cada foto já recortada no tamanho W×H.
    O mesmo pedido (mesmas fotos e opções) é gerado uma vez só."""
    os.makedirs(MIDIAS_DIR, exist_ok=True)
    h = hashlib.sha1(json.dumps([W, H, opcoes, audio_id], sort_keys=True).encode())
    for f in fotos:
        h.update(hashlib.sha1(f).digest())
    chave = h.hexdigest()[:24]
    destino = os.path.join(MIDIAS_DIR, f'show-{chave}.mp4')
    with _lock:
        trava = _render_locks.setdefault(chave, threading.Lock())
    with trava:
        if not os.path.exists(destino):
            pasta = os.path.join(MIDIAS_DIR, f'show-{chave}')
            os.makedirs(pasta, exist_ok=True)
            caminhos = []
            for i, f in enumerate(fotos):
                c = os.path.join(pasta, f'{i:03d}.jpg')
                out, _ = M.ajustar_imagem(f)
                with open(c, 'wb') as fp:
                    fp.write(out)
                caminhos.append(c)
            try:
                tmp = destino[:-4] + '.tmp.mp4'
                M.slideshow(caminhos, tmp, int(W), int(H), opcoes, _audio(audio_id) if audio_id else None)
                os.replace(tmp, destino)
            finally:
                shutil.rmtree(pasta, ignore_errors=True)
    return destino


# ---------- Publicação ----------

_JOBS = {}


def _validar(rede, fmt, item):
    midias = item['midias']
    tipos = {m['tipo'] for m in midias}
    if len(midias) < fmt.get('min_itens', 0):
        raise PublicarError(f"{fmt['nome']} precisa de pelo menos {fmt['min_itens']} mídia.")
    if len(midias) > fmt.get('max_itens', 0):
        raise PublicarError(f"{fmt['nome']} aceita no máximo {fmt['max_itens']} mídias.")
    for t in tipos:
        if t not in fmt['midia']:
            raise PublicarError(f"{fmt['nome']} não aceita {'vídeo' if t == 'video' else 'imagem'}.")
    if len(tipos) > 1 and not fmt.get('mistura') and not fmt.get('cada_item_um_post'):
        raise PublicarError(f"{rede['nome']} não mistura fotos e vídeo no mesmo post.")
    if fmt.get('max_videos') and sum(m['tipo'] == 'video' for m in midias) > fmt['max_videos']:
        raise PublicarError(f"{rede['nome']} aceita só {fmt['max_videos']} vídeo por post.")
    if fmt.get('video_so_carrossel') and len(midias) == 1 and 'video' in tipos:
        raise PublicarError('Vídeo sozinho no Instagram vai como Reels: escolha o formato Reels.')


def _preparar(item, arquivos, pasta):
    rede, fmt = R.rede(item['rede']), R.formato(item['rede'], item['formato'])
    tam = next((t for t in fmt['tamanhos'] if t['ratio'] == item.get('ratio')), fmt['tamanhos'][0])
    max_bytes = None
    if fmt.get('max_kb'):
        max_bytes = fmt['max_kb'] * 1024
    elif fmt.get('max_mb'):
        max_bytes = int(fmt['max_mb'] * 1024 * 1024 * 0.97)
    prontas = []
    for i, m in enumerate(item.get('midias') or []):
        if m['tipo'] == 'imagem':
            dados = arquivos.get(m['arquivo'])
            if dados is None:
                raise PublicarError('Imagem do post não chegou ao Verto.')
            out, mime = M.ajustar_imagem(dados, max_bytes)
            caminho = os.path.join(pasta, f"{item['rede']}-{item['formato']}-{i + 1}.jpg")
            with open(caminho, 'wb') as f:
                f.write(out)
            prontas.append({'tipo': 'imagem', 'caminho': caminho, 'mime': mime, 'w': tam['w'], 'h': tam['h']})
        elif m['tipo'] == 'slideshow':
            fotos = []
            for chave in m.get('fotos') or []:
                if chave not in arquivos:
                    raise PublicarError('Foto do vídeo com música não chegou ao Verto.')
                fotos.append(arquivos[chave])
            opcoes = {**(m.get('opcoes') or {}), 'max_s': (fmt.get('video') or {}).get('max_s')}
            caminho = renderizar_show(fotos, tam['w'], tam['h'], opcoes, m.get('audio_id'))
            info = M.sondar(caminho)
            prontas.append({'tipo': 'video', 'caminho': caminho, 'mime': 'video/mp4', 'w': info['w'], 'h': info['h'],
                            'dur': info['dur']})
        else:
            lim = (fmt.get('video') or {}).get('max_s')
            caminho = renderizar(m['midia_id'], tam['w'], tam['h'], m.get('enquadre') or {}, lim)
            limite_mb = fmt.get('max_mb_video')
            if limite_mb and os.path.getsize(caminho) > limite_mb * 1024 * 1024:
                raise PublicarError(f"O vídeo passou de {limite_mb} MB, o limite do {rede['nome']}.")
            info = M.sondar(caminho)
            prontas.append({'tipo': 'video', 'caminho': caminho, 'mime': 'video/mp4', 'w': info['w'], 'h': info['h'],
                            'dur': info['dur']})
    return rede, fmt, {**item, 'formato': fmt, 'midias': prontas}


def _historico(entrada):
    with _lock:
        h = _ler(HISTORICO_PATH, [])
        h.insert(0, entrada)
        _gravar(HISTORICO_PATH, h[:200])


def historico():
    return {'historico': _ler(HISTORICO_PATH, [])[:50]}


def iniciar(plano, arquivos):
    """plano = {'itens': [{rede, formato, ratio, texto, titulo, link, alt, opcoes, midias: [...]}]}
    arquivos = {nome do campo: bytes} com as imagens já recortadas pela página."""
    itens = plano.get('itens') or []
    if not itens:
        raise PublicarError('Nenhuma rede escolhida.')
    d = _contas()
    for it in itens:
        if it['rede'] not in CONECTORES:
            raise PublicarError(f"{it['rede']}: essa rede é publicada pelo modo assistido.")
        if not (d['contas'].get(it['rede']) or {}).get('perfil'):
            raise PublicarError(f"Conecte a conta do {R.rede(it['rede'])['nome']} antes de publicar.")
    jid = uuid.uuid4().hex[:12]
    pasta = os.path.join(JOBS_DIR, jid)
    os.makedirs(pasta, exist_ok=True)
    _limpar_antigos(JOBS_DIR, 24)
    job = {'id': jid, 'criado': _agora(), 'fim': False, 'itens': [
        {'chave': f"{it['rede']}:{it['formato']}", 'rede': it['rede'], 'formato': it['formato'],
         'estado': 'fila', 'msg': 'Na fila', 'url': ''} for it in itens]}
    _JOBS[jid] = job
    threading.Thread(target=_rodar, args=(job, itens, arquivos, pasta, d['config'].get('hospedagem', 'auto')),
                     daemon=True).start()
    return {'job': jid}


def _rodar(job, itens, arquivos, pasta, metodo):
    _checar_ipv6()
    hosp = Hospedagem(metodo)
    trava_hosp = threading.Lock()

    def um(i, it):
        st = job['itens'][i]

        def log(msg):
            st['msg'] = msg
        try:
            st.update(estado='preparando', msg='Preparando a mídia…')
            rede, fmt, item = _preparar(it, arquivos, pasta)
            _validar(rede, fmt, item)
            with _lock:
                conta = dict(_contas()['contas'][it['rede']])
            con = CONECTORES[it['rede']]
            if con.renovar(conta):
                _salvar_conta(it['rede'], conta)

            def url_publica(caminho, mime):
                with trava_hosp:
                    hosp.log = log
                    return hosp.url(caminho, mime)
            st.update(estado='enviando', msg='Enviando…')
            ctx = {'log': log, 'url_publica': url_publica, 'perfil': conta.get('perfil') or {}}
            res = con.publicar(conta, item, ctx)
            st.update(estado='publicado', msg='Publicado', url=res.get('url', ''))
            _historico({'quando': _agora(), 'rede': it['rede'], 'formato': it['formato'], 'url': st['url'],
                        'texto': (it.get('texto') or '')[:120]})
        except (PublicarError, M.MidiaError) as e:
            st.update(estado='erro', msg=str(e))
        except Exception as e:
            st.update(estado='erro', msg=f'Erro inesperado: {e.__class__.__name__}: {e}')

    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(lambda a: um(*a), enumerate(itens)))
    finally:
        hosp.fechar()
        job['fim'] = True
        shutil.rmtree(pasta, ignore_errors=True)


def acompanhar(jid):
    job = _JOBS.get(jid)
    if not job:
        raise PublicarError('Publicação não encontrada.')
    return {'job': job}
