"""Encurtador GBM: links curtos que funcionam no mundo todo, sem o Verto ligado.

Os links ficam num banco D1 da Cloudflare e quem redireciona é o código de
cloudflare/worker.js, publicado na conta gratuita do usuário em até três
endereços que servem os mesmos links (o primeiro no ar é o principal):

    https://gbm.pages.dev/<código>          Cloudflare Pages
    https://gbmlinks.pages.dev/<código>     Cloudflare Pages
    https://gbm.gbm.workers.dev/<código>    Cloudflare Workers (ou gbm.gbmlinks.workers.dev)

O Verto só administra: cria, edita e lê as estatísticas pela API da Cloudflare,
com o token salvo em dados/config.json. Uma cópia dos links fica em
dados/backup.json.
"""

import base64
import hashlib
import io
import ipaddress
import json
import os
import re
import secrets
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

import requests
from urllib3 import encode_multipart_formdata
from urllib3.fields import RequestField

_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS_DIR = os.path.join(_DIR, 'dados')
CONFIG_PATH = os.path.join(DADOS_DIR, 'config.json')
BACKUP_PATH = os.path.join(DADOS_DIR, 'backup.json')
WORKER_PATH = os.path.join(_DIR, 'cloudflare', 'worker.js')
SCHEMA_PATH = os.path.join(_DIR, 'cloudflare', 'schema.sql')

API = 'https://api.cloudflare.com/client/v4'
# O nome do projeto Pages é o endereço dos links (<nome>.pages.dev). Se o nome
# já tiver dono no mundo, a Cloudflare cria o projeto com um sufixo aleatório
# (gbm-3xk.pages.dev); o Verto apaga esse e tenta o próximo da lista.
PROJETOS = ('gbm', 'gbmlinks')
# Reserva no Workers: gbm.<subdomínio da conta>.workers.dev. Cada conta tem um só
# subdomínio workers.dev; o Verto tenta gbm e, se tiver dono, gbmlinks.
WORKER_NOME = 'gbm'
SUBDOMINIOS = ('gbm', 'gbmlinks')
CHAVE_WORKER = 'workers'
PERMISSOES = ('"Cloudflare Pages: Edit", "Workers Scripts: Edit", "D1: Edit" '
              'e "Account Settings: Read"')
BANCO_NOME = 'gbm-encurtador'
COMPAT_DATE = '2025-09-01'

# Sem i, l, o, 0 e 1: o código pode ser ditado ou digitado sem confusão.
# 31^6 = 887 milhões de combinações.
ALFABETO = 'abcdefghjkmnpqrstuvwxyz23456789'
TAMANHO_CODIGO = 6
ALIAS_RE = re.compile(r'^[A-Za-z0-9_-]{3,50}$')
PBKDF2_ITERACOES = 10000  # o Worker grátis tem 10 ms de CPU por acesso
MAX_URL = 2048
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

CAMPOS_LINK = ('id, slug, url, titulo, notas, tags, criado_em, atualizado_em, expira_em, '
               'max_cliques, ativo, tipo_redirect, cliques, ultimo_clique, '
               '(senha_hash IS NOT NULL) AS protegido')

_lock = threading.Lock()


class EncurtadorError(Exception):
    def __init__(self, msg, codigos=(), http=None):
        super().__init__(msg)
        self.codigos = set(codigos)
        self.http = http


# ---------- Configuração ----------

_config_cache = {'chave': None, 'cfg': {}}


def _config():
    """Lê dados/config.json (relê só quando o arquivo muda). Devolve uma cópia."""
    try:
        st = os.stat(CONFIG_PATH)
        chave = (CONFIG_PATH, st.st_mtime_ns, st.st_size)
        if _config_cache['chave'] != chave:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                _config_cache.update(chave=chave, cfg=json.load(f))
        cfg = json.loads(json.dumps(_config_cache['cfg']))
    except (OSError, ValueError):
        return {}
    if cfg.get('projeto') and 'projetos' not in cfg:  # formato da primeira versão
        cfg['projetos'] = {cfg['projeto']: f"{cfg['projeto']}.pages.dev"}
    cfg.pop('projeto', None)
    return cfg


def _salvar_config(cfg):
    os.makedirs(DADOS_DIR, exist_ok=True)
    tmp = CONFIG_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    os.chmod(tmp, 0o600)  # o token dá acesso à conta Cloudflare
    os.replace(tmp, CONFIG_PATH)


def _worker_hash():
    with open(WORKER_PATH, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _enderecos(cfg):
    """Endereços que servem os links, na ordem de preferência: gbm.pages.dev,
    gbmlinks.pages.dev e, por último, o reserva no workers.dev."""
    donos = cfg.get('projetos') or {}
    lista = [{'nome': n, 'host': donos[n], 'tipo': 'pages'} for n in PROJETOS if n in donos]
    if cfg.get('worker'):
        lista.append({'nome': CHAVE_WORKER, 'host': cfg['worker']['host'], 'tipo': 'workers'})
    return lista


def _host(cfg, nome):
    return next((e['host'] for e in _enderecos(cfg) if e['nome'] == nome), nome)


def status():
    cfg = _config()
    if not cfg.get('base_url'):
        return {'conectado': False}
    return {
        'conectado': True,
        'base_url': cfg['base_url'],
        'conta': cfg.get('account_name', ''),
        'enderecos': _enderecos(cfg),
        'indisponiveis': cfg.get('motivos', {}),
    }


def desconectar():
    """Esquece o token neste computador. Os links continuam no ar na Cloudflare."""
    try:
        os.remove(CONFIG_PATH)
    except FileNotFoundError:
        pass


# ---------- API da Cloudflare ----------

def _repetir_seguro(method, path):
    # Repetir um pedido que talvez já tenha sido feito só é seguro quando o efeito
    # é o mesmo: leituras, PUT/PATCH/DELETE e publicar de novo. Criar link (consulta
    # D1) e criar projeto só são repetidos quando a Cloudflare nem recebeu o pedido.
    return method in ('GET', 'PUT', 'PATCH', 'DELETE') or path.endswith('/deployments')


def _cf(method, path, token, **kw):
    headers = kw.pop('headers', {})
    headers['Authorization'] = f'Bearer {token}'
    timeout = kw.pop('timeout', 30)
    seguro = _repetir_seguro(method, path)
    for tentativa in range(4):
        ultima = tentativa == 3
        try:
            r = requests.request(method, API + path, headers=headers, timeout=timeout, **kw)
        except requests.ConnectTimeout as e:  # não chegou à Cloudflare: sempre pode repetir
            if ultima:
                raise EncurtadorError(f'Sem conexão com a Cloudflare: {e}')
            time.sleep(2 ** tentativa)
            continue
        except requests.RequestException as e:
            if ultima or not seguro:
                raise EncurtadorError(f'Sem conexão com a Cloudflare: {e}')
            time.sleep(2 ** tentativa)
            continue
        try:
            data = r.json()
        except ValueError:
            data = None
        temporario = r.status_code == 429 or (r.status_code >= 500 and seguro) or (
            data and seguro and 8000000 in {e.get('code') for e in data.get('errors') or []})
        if temporario and not ultima:
            espera = 2 ** tentativa
            try:
                espera = max(espera, min(int(r.headers.get('retry-after', 0)), 20))
            except ValueError:
                pass
            time.sleep(espera)
            continue
        if data is None:
            raise EncurtadorError(f'Resposta inesperada da Cloudflare (HTTP {r.status_code}).', http=r.status_code)
        if not data.get('success'):
            erros = data.get('errors') or []
            codigos = {e.get('code') for e in erros}
            msg = '; '.join(e.get('message', '') for e in erros) or f'HTTP {r.status_code}'
            if r.status_code in (401, 403) or codigos & {9106, 9109, 10000, 10001}:
                raise EncurtadorError(
                    f'O token não tem permissão para isso. Crie um token com as permissões {PERMISSOES}. '
                    f'(Cloudflare: {msg})', codigos, r.status_code)
            raise EncurtadorError(f'Cloudflare: {msg}', codigos, r.status_code)
        return data.get('result')


def _d1_query(cfg, sql, params=None):
    body = {'sql': sql}
    if params:
        body['params'] = list(params)
    res = _cf('POST', f"/accounts/{cfg['account_id']}/d1/database/{cfg['database_id']}/query",
              cfg['token'], json=body)
    return res[-1].get('results', []) if res else []


def _d1_batch(cfg, stmts):
    body = {'batch': [{'sql': s, 'params': list(p)} if p else {'sql': s} for s, p in stmts]}
    res = _cf('POST', f"/accounts/{cfg['account_id']}/d1/database/{cfg['database_id']}/query",
              cfg['token'], json=body)
    return [r.get('results', []) for r in (res or [])]


class _D1:
    """Banco do encurtador. Os testes trocam por um SQLite local com a mesma interface."""

    def __init__(self, cfg):
        self.cfg = cfg

    def query(self, sql, params=()):
        return _d1_query(self.cfg, sql, params)

    def batch(self, stmts):
        return _d1_batch(self.cfg, stmts)


def _db():
    cfg = _config()
    if not cfg.get('base_url'):
        raise EncurtadorError('Conecte sua conta Cloudflare primeiro (é grátis).')
    return _D1(cfg)


def _base_url():
    return _config().get('base_url', '')


def _hosts_curtos():
    hosts = {e['host'] for e in _enderecos(_config())}
    base = urlsplit(_base_url()).hostname
    if base:
        hosts.add(base)
    return hosts


# ---------- Conexão (cria tudo na conta do usuário) ----------

def conectar(token, account_id=''):
    salvo = _config()
    token = (token or '').strip() or salvo.get('token', '')
    if not token:
        raise EncurtadorError('Cole o token da API da Cloudflare.')
    if not account_id and token == salvo.get('token'):
        account_id = salvo.get('account_id', '')

    contas = _cf('GET', '/accounts', token, params={'per_page': 50}) or []
    if account_id:
        conta = next((c for c in contas if c.get('id') == account_id), {'id': account_id, 'name': ''})
    elif len(contas) == 1:
        conta = contas[0]
    elif not contas:
        raise EncurtadorError('O token não dá acesso a nenhuma conta. Confira se ele inclui a sua conta em "Account Resources".')
    else:
        return {'escolher_conta': [{'id': c['id'], 'nome': c.get('name', '')} for c in contas]}
    aid = conta['id']

    # Banco D1: reaproveita se já existir (reconectar não perde links).
    bancos = _cf('GET', f'/accounts/{aid}/d1/database', token, params={'name': BANCO_NOME}) or []
    banco = next((b for b in bancos if b.get('name') == BANCO_NOME), None)
    if not banco:
        try:
            banco = _cf('POST', f'/accounts/{aid}/d1/database', token, json={'name': BANCO_NOME})
        except EncurtadorError:
            # Pode ter sido criado por um pedido anterior que perdeu a resposta.
            bancos = _cf('GET', f'/accounts/{aid}/d1/database', token, params={'name': BANCO_NOME}) or []
            banco = next((b for b in bancos if b.get('name') == BANCO_NOME), None)
            if not banco:
                raise

    cfg = salvo if salvo.get('account_id') in (None, aid) else {}
    if cfg.get('database_id') not in (None, banco['uuid']):
        cfg.pop('projetos', None)
        cfg.pop('worker', None)
    cfg.update({
        'token': token, 'account_id': aid, 'account_name': conta.get('name', ''),
        'database_id': banco['uuid'], 'salt': cfg.get('salt') or secrets.token_hex(16),
    })
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        _d1_query(cfg, f.read())
    _garantir_enderecos(cfg)
    _publicar(cfg, [e['nome'] for e in _enderecos(cfg)])
    # Principal = o primeiro endereço (na ordem de preferência) que recebeu o código.
    versao = _worker_hash()
    publicados = [e for e in _enderecos(cfg) if cfg['versoes'].get(e['nome']) == versao]
    cfg['base_url'] = 'https://' + publicados[0]['host']
    _salvar_config(cfg)
    _saude_cache['ts'] = 0
    return {'conectado': True, 'base_url': cfg['base_url'], 'enderecos': _enderecos(cfg),
            'indisponiveis': cfg.get('motivos', {}), 'online': _online(cfg['base_url'], esperar=45)}


def _config_pages(cfg):
    conf = {
        'compatibility_date': COMPAT_DATE,
        'd1_databases': {'DB': {'id': cfg['database_id']}},
        'env_vars': {'SALT': {'type': 'secret_text', 'value': cfg['salt']}},
    }
    return {'production': conf, 'preview': conf}


def _eh_nosso(proj, cfg):
    """Um projeto é do encurtador se está ligado ao banco do encurtador. Projetos seus
    com o mesmo nome, feitos para outra coisa, nunca são alterados nem apagados."""
    try:
        return proj['deployment_configs']['production']['d1_databases']['DB']['id'] == cfg['database_id']
    except (KeyError, TypeError):
        return False


def _worker_eh_nosso(conf, cfg):
    """Mesma regra para o Worker: só é do encurtador se estiver ligado ao banco dele."""
    for b in (conf or {}).get('bindings') or []:
        if b.get('type') == 'd1' and cfg['database_id'] in (b.get('database_id'), b.get('id')):
            return True
    return False


def _nome_resolve(host):
    # Um endereço pages.dev sem dono não existe no DNS. É só uma pista (pode mudar a
    # qualquer momento); quem decide é a Cloudflare ao criar o projeto.
    try:
        socket.getaddrinfo(host, 443)
        return True
    except (socket.gaierror, UnicodeError):
        return False
    except OSError:
        return False


def _apagar_com_sufixo(cfg, nome):
    """Apaga um projeto do encurtador que ganhou endereço com sufixo (o nome tinha dono)."""
    base = f"/accounts/{cfg['account_id']}/pages/projects/{nome}"
    pendentes = [n for n in cfg.get('pendentes_apagar', []) if n != nome]
    try:
        proj = _cf('GET', base, cfg['token'])
        if _eh_nosso(proj, cfg) and proj.get('subdomain') != f'{nome}.pages.dev':
            _cf('DELETE', base, cfg['token'])
    except EncurtadorError as e:
        if e.http != 404:
            pendentes.append(nome)  # tenta de novo na próxima verificação
    cfg['pendentes_apagar'] = pendentes


def _garantir_enderecos(cfg):
    """Reserva cada endereço livre (Pages e Workers). Todos servem os mesmos links.
    Um tipo com problema (ou sem permissão no token) não impede o outro."""
    motivos = {}
    for tipo, fn, permissao in (('pages', _garantir_pages, 'Cloudflare Pages: Edit'),
                                ('workers', _garantir_worker, 'Workers Scripts: Edit')):
        try:
            fn(cfg, motivos)
        except EncurtadorError as e:
            msg = (f'o token não tem a permissão "{permissao}"' if e.http in (401, 403)
                   else f'não deu para verificar agora ({e})')
            if tipo == 'pages':
                for n in PROJETOS:
                    if n not in (cfg.get('projetos') or {}):
                        motivos.setdefault(f'{n}.pages.dev', msg)
            elif not cfg.get('worker'):
                motivos.setdefault(f'{WORKER_NOME}.{SUBDOMINIOS[0]}.workers.dev', msg)
    for e in _enderecos(cfg):
        motivos.pop(e['host'], None)
    cfg['motivos'] = motivos
    cfg['ultima_reserva'] = int(time.time())
    hosts = ['https://' + e['host'] for e in _enderecos(cfg)]
    if not hosts:
        raise EncurtadorError('Nenhum endereço ficou disponível: ' + '; '.join(
            f'{h} {m}' for h, m in motivos.items()) + '.')
    if cfg.get('base_url') not in hosts:
        cfg['base_url'] = hosts[0]


def _garantir_pages(cfg, motivos):
    """gbm.pages.dev e gbmlinks.pages.dev: reserva os que estiverem livres."""
    base = f"/accounts/{cfg['account_id']}/pages/projects"
    tok = cfg['token']
    for nome in list(cfg.get('pendentes_apagar', [])):
        _apagar_com_sufixo(cfg, nome)
    donos = cfg.setdefault('projetos', {})
    for nome in PROJETOS:
        alvo = f'{nome}.pages.dev'
        try:
            proj = _cf('GET', f'{base}/{nome}', tok)
        except EncurtadorError as e:
            if e.http in (401, 403):
                raise
            if e.http != 404:
                motivos[alvo] = f'não deu para verificar agora ({e})'
                continue  # falha passageira: mantém o que já sabíamos
            proj = None

        if proj is not None:
            if not (nome in donos or _eh_nosso(proj, cfg)):
                motivos[alvo] = f'sua conta já tem um projeto "{nome}" de outro uso (não foi alterado)'
                donos.pop(nome, None)
                continue
            if proj.get('subdomain') != alvo:
                _apagar_com_sufixo(cfg, nome)
                motivos[alvo] = 'é de outra pessoa'
                donos.pop(nome, None)
                continue
            if not _eh_nosso(proj, cfg):
                _cf('PATCH', f'{base}/{nome}', tok, json={'deployment_configs': _config_pages(cfg)})
            donos[nome] = alvo
            continue

        donos.pop(nome, None)  # o projeto foi apagado: recria abaixo, se o nome ainda estiver livre
        if _nome_resolve(alvo):
            motivos[alvo] = 'é de outra pessoa'
            continue
        corpo = {'name': nome, 'production_branch': 'main', 'deployment_configs': _config_pages(cfg)}
        try:
            proj = _cf('POST', base, tok, json=corpo)
        except EncurtadorError as e:
            if e.http in (401, 403):
                raise
            try:  # talvez tenha sido criado e só a resposta se perdeu
                proj = _cf('GET', f'{base}/{nome}', tok)
            except EncurtadorError:
                proj = None
            if not (proj and _eh_nosso(proj, cfg)):
                motivos[alvo] = f'a Cloudflare recusou ({e})'
                continue
        if proj.get('subdomain') == alvo:
            donos[nome] = alvo
        else:
            _apagar_com_sufixo(cfg, nome)
            motivos[alvo] = 'é de outra pessoa'


def _outros_workers(cfg):
    """A conta tem Workers além do encurtador? Na dúvida, responde que sim."""
    try:
        scripts = _cf('GET', f"/accounts/{cfg['account_id']}/workers/scripts", cfg['token']) or []
    except EncurtadorError as e:
        if e.http in (401, 403):
            raise
        return True
    return any(s.get('id') != WORKER_NOME for s in scripts)


def _garantir_worker(cfg, motivos):
    """Reserva no Workers: gbm.gbm.workers.dev, ou gbm.gbmlinks.workers.dev."""
    base = f"/accounts/{cfg['account_id']}/workers"
    tok = cfg['token']
    atual = cfg.get('worker')
    ideal = f'{WORKER_NOME}.{SUBDOMINIOS[0]}.workers.dev'

    # Um Worker "gbm" que não é do encurtador nunca é sobrescrito.
    try:
        conf = _cf('GET', f'{base}/scripts/{WORKER_NOME}/settings', tok)
    except EncurtadorError as e:
        if e.http in (401, 403):
            raise
        if e.http != 404:
            motivos[atual['host'] if atual else ideal] = f'não deu para verificar agora ({e})'
            return  # falha passageira: mantém o que já sabíamos
        conf = None
    if conf is not None and not atual and not _worker_eh_nosso(conf, cfg):
        motivos[ideal] = f'sua conta já tem um Worker "{WORKER_NOME}" de outro uso (não foi alterado)'
        return

    try:
        sub = (_cf('GET', f'{base}/subdomain', tok) or {}).get('subdomain')
    except EncurtadorError as e:
        if e.http in (401, 403):
            raise
        if e.http is None or e.http >= 500 or e.http == 429:
            motivos[atual['host'] if atual else ideal] = f'não deu para verificar agora ({e})'
            return
        sub = None  # a conta ainda não tem subdomínio workers.dev

    if sub not in SUBDOMINIOS:
        if sub and _outros_workers(cfg):
            # Trocar o subdomínio mudaria o endereço dos outros Workers da conta.
            motivos[ideal] = (f'sua conta já usa {sub}.workers.dev em outros Workers; '
                              f'para não quebrá-los, o reserva fica em {WORKER_NOME}.{sub}.workers.dev')
        else:
            for cand in SUBDOMINIOS:
                try:
                    sub = (_cf('PUT', f'{base}/subdomain', tok, json={'subdomain': cand}) or {}).get('subdomain') or cand
                    break
                except EncurtadorError as e:
                    if e.http in (401, 403):
                        raise
                    if e.http is None or e.http >= 500 or e.http == 429:
                        # Falha passageira: não pula para o próximo nome, porque depois
                        # de escolhido o subdomínio não é mais trocado.
                        motivos[f'{WORKER_NOME}.{cand}.workers.dev'] = f'não deu para verificar agora ({e})'
                        return
                    motivos[f'{WORKER_NOME}.{cand}.workers.dev'] = 'é de outra pessoa'
            else:
                if not sub:
                    cfg.pop('worker', None)
                    return
    cfg['worker'] = {'sub': sub, 'host': f'{WORKER_NOME}.{sub}.workers.dev'}


def _bundle(codigo):
    """Monta o "_worker.bundle" igual ao wrangler pages deploy: um corpo multipart com
    o metadata e o módulo. As ligações (D1, SALT) vêm da configuração do projeto."""
    meta = RequestField('metadata', json.dumps({'main_module': '_worker.js'}))
    meta.make_multipart()
    mod = RequestField('_worker.js', codigo, filename='_worker.js')
    mod.make_multipart(content_type='application/javascript+module')
    corpo, _ = encode_multipart_formdata([meta, mod])
    return corpo


def _publicar_pages(cfg, nome, codigo):
    files = {
        'manifest': (None, '{}'),  # nenhum arquivo estático: tudo é servido pelo worker.js
        'branch': (None, 'main'),
        '_worker.bundle': ('_worker.bundle', _bundle(codigo), 'application/octet-stream'),
    }
    path = f"/accounts/{cfg['account_id']}/pages/projects/{nome}/deployments"
    dep = _cf('POST', path, cfg['token'], files=files, timeout=120) or {}
    _esperar_publicacao(cfg, nome, dep.get('id'))


def _publicar_worker(cfg, codigo):
    path = f"/accounts/{cfg['account_id']}/workers/scripts/{WORKER_NOME}"
    # Mesmo formato que o wrangler deploy envia (conferido campo a campo).
    meta = {
        'main_module': 'worker.js',
        'bindings': [
            {'name': 'DB', 'type': 'd1', 'id': cfg['database_id']},
            {'name': 'SALT', 'type': 'secret_text', 'text': cfg['salt']},
        ],
        'compatibility_date': COMPAT_DATE,
        'compatibility_flags': [],
    }
    files = {
        'metadata': (None, json.dumps(meta, separators=(',', ':'))),
        'worker.js': ('worker.js', codigo, 'application/javascript+module'),
    }
    _cf('PUT', path, cfg['token'], files=files, timeout=60)
    _cf('POST', f'{path}/subdomain', cfg['token'], json={'enabled': True, 'previews_enabled': False})


def _publicar(cfg, nomes):
    """Publica o worker.js em cada endereço. Um endereço com problema não impede os outros."""
    with open(WORKER_PATH, 'rb') as f:
        codigo = f.read()
    versao = _worker_hash()
    versoes = cfg.setdefault('versoes', {})
    publicados = cfg.setdefault('publicado_em', {})
    erros = []
    for nome in nomes:
        try:
            if nome == CHAVE_WORKER:
                _publicar_worker(cfg, codigo)
            else:
                _publicar_pages(cfg, nome, codigo)
            versoes[nome] = versao
            publicados[nome] = int(time.time())
        except EncurtadorError as e:
            versoes.pop(nome, None)
            erros.append(f'{_host(cfg, nome)}: {e}')
    if erros and len(erros) == len(nomes):
        raise EncurtadorError('Não deu para publicar o encurtador. ' + '; '.join(erros))
    return erros


def _esperar_publicacao(cfg, nome, dep_id, limite=45):
    """Acompanha a publicação até a Cloudflare confirmar (como o wrangler faz)."""
    if not dep_id:
        return
    path = f"/accounts/{cfg['account_id']}/pages/projects/{nome}/deployments/{dep_id}"
    fim = time.time() + limite
    while time.time() < fim:
        try:
            etapa = (_cf('GET', path, cfg['token']) or {}).get('latest_stage') or {}
        except EncurtadorError:
            return  # sem como confirmar agora; a verificação de saúde confere depois
        if etapa.get('status') == 'failure':
            raise EncurtadorError(f'a Cloudflare recusou a publicação (etapa {etapa.get("name")}).')
        if etapa.get('name') == 'deploy' and etapa.get('status') == 'success':
            return
        time.sleep(1.5)


def _online(base_url, esperar=0):
    # Um endereço novo pode levar alguns minutos para responder no mundo todo.
    fim = time.time() + esperar
    while True:
        try:
            r = requests.get(base_url + '/', timeout=8, headers={'User-Agent': 'Verto-Encurtador/saude'})
            if r.status_code == 200 and 'GBM' in r.text:
                return True
        except requests.RequestException:
            pass
        if time.time() >= fim:
            return False
        time.sleep(3)


# ---------- Saúde: troca automática e autorreparo ----------

SAUDE_INTERVALO = 300            # verifica os endereços no máximo a cada 5 minutos
RESERVA_INTERVALO = 6 * 3600     # tenta de novo um endereço que estava ocupado
REPARO_CARENCIA = 15 * 60        # endereço recém-publicado ainda pode estar propagando
_saude_cache = {'ts': 0, 'res': None}
_saude_lock = threading.Lock()


def saude(forcar=False):
    """Confere cada endereço e conserta sozinho o que der:
    - publica a versão nova do worker.js onde estiver desatualizada;
    - reserva um endereço que estava ocupado, se ficar livre;
    - recria e republica um endereço que saiu do ar ou foi apagado;
    - se o principal estiver fora, os links novos passam a usar o próximo no ar."""
    with _saude_lock:
        cfg = _config()
        if not cfg.get('base_url'):
            return {'conectado': False}
        agora = time.time()
        if not forcar and _saude_cache['res'] and agora - _saude_cache['ts'] < SAUDE_INTERVALO:
            return _saude_cache['res']
        acoes, avisos = [], []

        def tentar(rotulo, fn):
            try:
                return fn()
            except EncurtadorError as e:
                avisos.append(f'{rotulo}: {e}')

        def hosts(nomes):
            return ', '.join(_host(cfg, n) for n in nomes)

        faltando = ([n for n in PROJETOS if n not in (cfg.get('projetos') or {})]
                    + ([] if cfg.get('worker') else [CHAVE_WORKER]))
        if faltando and (forcar or agora - cfg.get('ultima_reserva', 0) > RESERVA_INTERVALO):
            antes = {e['nome'] for e in _enderecos(cfg)}
            tentar('Reservar endereço', lambda: _garantir_enderecos(cfg))
            novos = [e['nome'] for e in _enderecos(cfg) if e['nome'] not in antes]
            if novos:
                tentar('Publicar', lambda: _publicar(cfg, novos))
                acoes.append('Endereço reservado: ' + hosts(novos))

        versao = _worker_hash()
        desatualizados = [e['nome'] for e in _enderecos(cfg) if cfg.get('versoes', {}).get(e['nome']) != versao]
        if desatualizados:
            falhas = tentar('Atualizar', lambda: _publicar(cfg, desatualizados))
            if falhas is not None:
                acoes.append('Encurtador atualizado em ' + hosts(desatualizados))

        def testar():
            return {e['nome']: _online('https://' + e['host']) for e in _enderecos(cfg)}

        no_ar = testar()
        fora = [n for n, ok in no_ar.items() if not ok]
        recentes = {n for n in fora if agora - cfg.get('publicado_em', {}).get(n, 0) < REPARO_CARENCIA}
        reparar = [n for n in fora if n not in recentes]
        # Só conserta quando outro endereço responde (prova de que a internet daqui funciona)
        # ou quando a verificação foi pedida.
        if reparar and (any(no_ar.values()) or forcar):
            tentar('Reparar', lambda: _garantir_enderecos(cfg))
            reparar = [e['nome'] for e in _enderecos(cfg) if e['nome'] in reparar]
            if reparar:
                tentar('Republicar', lambda: _publicar(cfg, reparar))
                acoes.append('Reparado: ' + hosts(reparar))
                no_ar = testar()

        funcionando = [e for e in _enderecos(cfg) if no_ar.get(e['nome'])]
        if funcionando:
            novo = 'https://' + funcionando[0]['host']
            if novo != cfg['base_url']:
                acoes.append(f'Links novos passam a usar {funcionando[0]["host"]}')
                cfg['base_url'] = novo
        _salvar_config(cfg)
        res = {
            'conectado': True, 'base_url': cfg['base_url'],
            'enderecos': [{**e, 'online': no_ar.get(e['nome'], False),
                           'propagando': e['nome'] in recentes} for e in _enderecos(cfg)],
            'indisponiveis': cfg.get('motivos', {}),
            'acoes': acoes, 'avisos': avisos,
            'sem_internet': bool(no_ar) and not any(no_ar.values()) and not recentes,
        }
        _saude_cache.update(ts=time.time(), res=res)
        return res


def atualizar_worker():
    return saude(forcar=True)


# ---------- Validação ----------

def normalizar_url(url):
    url = (url or '').strip()
    if not url:
        raise EncurtadorError('Cole o link que você quer encurtar.')
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', url):
        if re.match(r'^(javascript|data|file|vbscript|blob|about):', url, re.I):
            raise EncurtadorError('Esse tipo de link não pode ser encurtado.')
        url = 'https://' + url
    if len(url) > MAX_URL:
        raise EncurtadorError(f'O link tem mais de {MAX_URL} caracteres.')
    if re.search(r'\s', url):
        raise EncurtadorError('O link tem espaços. Confira se foi colado inteiro.')
    partes = urlsplit(url)
    if partes.scheme.lower() not in ('http', 'https'):
        raise EncurtadorError('Só links http:// ou https:// podem ser encurtados.')
    host = (partes.hostname or '').lower()
    if not host or ('.' not in host and host != 'localhost'):
        raise EncurtadorError('Esse link não parece um endereço válido.')
    if host in _hosts_curtos():
        raise EncurtadorError('Esse já é um link curto do encurtador.')
    return url


def _validar_alias(alias):
    if not ALIAS_RE.match(alias):
        raise EncurtadorError('O apelido precisa ter de 3 a 50 caracteres: letras, números, "-" ou "_".')
    return alias


def _hash_senha(senha):
    sal = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac('sha256', senha.encode('utf-8'), sal, PBKDF2_ITERACOES, 32)
    return f'pbkdf2${PBKDF2_ITERACOES}${base64.b64encode(sal).decode()}${base64.b64encode(h).decode()}'


def _int_ou_none(v, nome, minimo=1):
    if v in (None, '', 0, '0'):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise EncurtadorError(f'Valor inválido para {nome}.')
    if n < minimo:
        raise EncurtadorError(f'Valor inválido para {nome}.')
    return n


def _tags(v):
    if isinstance(v, list):
        v = ','.join(v)
    vistas = []
    for t in (v or '').split(','):
        t = t.strip().lower()
        if t and t not in vistas:
            vistas.append(t[:30])
    return ','.join(vistas) or None


def _codigo():
    return ''.join(secrets.choice(ALFABETO) for _ in range(TAMANHO_CODIGO))


# ---------- Links ----------

def _com_url_curta(link):
    base = _base_url()
    link = dict(link)
    link['curto'] = f"{base}/{link['slug']}"
    # O mesmo link abre em todos os endereços reservados (gbm e gbmlinks).
    link['alternativos'] = [f"https://{h}/{link['slug']}" for h in sorted(_hosts_curtos())
                            if f'https://{h}' != base and not h.startswith(('127.', 'localhost'))]
    link['protegido'] = bool(link.get('protegido'))
    link['ativo'] = bool(link.get('ativo'))
    return link


def criar(dados, buscar_titulo_auto=True):
    url = normalizar_url(dados.get('url'))
    alias = (dados.get('alias') or '').strip()
    if alias:
        _validar_alias(alias)
    titulo = (dados.get('titulo') or '').strip()[:300] or None
    if titulo is None and buscar_titulo_auto:
        titulo = buscar_titulo(url).get('titulo')
    tipo = 301 if str(dados.get('tipo_redirect')) == '301' else 302
    senha = dados.get('senha') or ''
    agora = int(time.time())
    expira = _int_ou_none(dados.get('expira_em'), 'validade')
    if expira and expira <= agora:
        raise EncurtadorError('A data de validade já passou.')
    valores = [
        url, titulo, (dados.get('notas') or '').strip()[:1000] or None, _tags(dados.get('tags')),
        agora, agora, expira, _int_ou_none(dados.get('max_cliques'), 'limite de cliques'),
        _hash_senha(senha) if senha else None, tipo,
    ]
    db = _db()
    sql = ('INSERT OR IGNORE INTO links (slug, url, titulo, notas, tags, criado_em, atualizado_em, '
           'expira_em, max_cliques, senha_hash, tipo_redirect) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) '
           f'RETURNING {CAMPOS_LINK}')
    for tentativa in range(8):
        slug = alias or _codigo() + (secrets.choice(ALFABETO) if tentativa >= 3 else '')
        linhas = db.query(sql, [slug] + valores)
        if linhas:
            return _com_url_curta(linhas[0])
        if alias:
            raise EncurtadorError(f'O apelido "{alias}" já está em uso.')
    raise EncurtadorError('Não foi possível gerar um código livre. Tente de novo.')


def criar_varios(urls, opcoes=None):
    """Encurta uma lista de links (um por linha). Erros de um link não param os outros."""
    opcoes = dict(opcoes or {})
    opcoes.pop('alias', None)
    opcoes.pop('url', None)
    lista = [u.strip() for u in urls if u and u.strip()][:200]
    if not lista:
        raise EncurtadorError('Cole pelo menos um link (um por linha).')

    def um(url):
        try:
            return {'url': url, 'link': criar({**opcoes, 'url': url})}
        except EncurtadorError as e:
            return {'url': url, 'erro': str(e)}

    with ThreadPoolExecutor(max_workers=6) as ex:
        return list(ex.map(um, lista))


def listar():
    db = _db()
    linhas = db.query(f'SELECT {CAMPOS_LINK}, senha_hash FROM links ORDER BY criado_em DESC, id DESC')
    _backup(linhas)
    out = []
    for l in linhas:
        l = dict(l)
        l.pop('senha_hash', None)
        out.append(_com_url_curta(l))
    return out


def _backup(linhas):
    try:
        os.makedirs(DADOS_DIR, exist_ok=True)
        with _lock:
            tmp = BACKUP_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'gerado_em': int(time.time()), 'base_url': _base_url(), 'links': linhas},
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, BACKUP_PATH)
    except OSError:
        pass


def _buscar(db, slug):
    linhas = db.query(f'SELECT {CAMPOS_LINK} FROM links WHERE slug = ?', [slug])
    if not linhas:
        raise EncurtadorError('Link não encontrado.')
    return linhas[0]


def editar(slug, dados):
    db = _db()
    atual = _buscar(db, slug)
    sets, params = [], []

    def put(coluna, valor):
        sets.append(f'{coluna} = ?')
        params.append(valor)

    if 'url' in dados:
        put('url', normalizar_url(dados['url']))
    if 'titulo' in dados:
        put('titulo', (dados['titulo'] or '').strip()[:300] or None)
    if 'notas' in dados:
        put('notas', (dados['notas'] or '').strip()[:1000] or None)
    if 'tags' in dados:
        put('tags', _tags(dados['tags']))
    if 'expira_em' in dados:
        put('expira_em', _int_ou_none(dados['expira_em'], 'validade'))
    if 'max_cliques' in dados:
        put('max_cliques', _int_ou_none(dados['max_cliques'], 'limite de cliques'))
    if 'ativo' in dados:
        put('ativo', 1 if dados['ativo'] else 0)
    if 'tipo_redirect' in dados:
        put('tipo_redirect', 301 if str(dados['tipo_redirect']) == '301' else 302)
    if dados.get('remover_senha'):
        put('senha_hash', None)
    elif dados.get('senha'):
        put('senha_hash', _hash_senha(dados['senha']))
    novo = (dados.get('novo_slug') or '').strip()
    if novo and novo.lower() != atual['slug'].lower():
        _validar_alias(novo)
        if db.query('SELECT 1 AS x FROM links WHERE slug = ?', [novo]):
            raise EncurtadorError(f'O apelido "{novo}" já está em uso.')
        put('slug', novo)
    elif novo:
        put('slug', novo)  # só mudou maiúsculas/minúsculas
    if not sets:
        return _com_url_curta(atual)
    put('atualizado_em', int(time.time()))
    params.append(atual['id'])
    linhas = db.query(f"UPDATE links SET {', '.join(sets)} WHERE id = ? RETURNING {CAMPOS_LINK}", params)
    return _com_url_curta(linhas[0])


def excluir(slug):
    db = _db()
    atual = _buscar(db, slug)
    db.batch([
        ('DELETE FROM cliques WHERE link_id = ?', [atual['id']]),
        ("DELETE FROM tentativas WHERE chave LIKE ?", [f"{atual['id']}:%"]),
        ('DELETE FROM links WHERE id = ?', [atual['id']]),
    ])


def estatisticas(slug, dias=30):
    dias = max(1, min(int(dias or 30), 3650))
    db = _db()
    link = _buscar(db, slug)
    desde = int(time.time()) - dias * 86400
    fuso = f'{time.localtime().tm_gmtoff} seconds'
    lid = link['id']

    def top(coluna):
        return (f"SELECT COALESCE({coluna}, '?') AS nome, COUNT(*) AS n FROM cliques "
                'WHERE link_id = ? AND ts >= ? AND bot = 0 GROUP BY nome ORDER BY n DESC LIMIT 10', [lid, desde])

    res = db.batch([
        ('SELECT COALESCE(SUM(bot = 0), 0) AS cliques, COALESCE(SUM(bot), 0) AS bots, '
         'COUNT(DISTINCT CASE WHEN bot = 0 THEN visitante END) AS unicos '
         'FROM cliques WHERE link_id = ? AND ts >= ?', [lid, desde]),
        ("SELECT date(ts, 'unixepoch', ?) AS dia, SUM(bot = 0) AS cliques, "
         "COUNT(DISTINCT CASE WHEN bot = 0 THEN visitante END) AS unicos "
         "FROM cliques WHERE link_id = ? AND ts >= ? GROUP BY dia ORDER BY dia", [fuso, lid, desde]),
        top('referencia'), top('pais'), top('dispositivo'), top('navegador'), top('so'),
        ('SELECT ts, referencia, dispositivo, navegador, so, pais, bot FROM cliques '
         'WHERE link_id = ? ORDER BY ts DESC LIMIT 25', [lid]),
    ])
    return {
        'link': _com_url_curta(link), 'dias': dias,
        'totais': res[0][0] if res[0] else {'cliques': 0, 'bots': 0, 'unicos': 0},
        'por_dia': res[1], 'referencias': res[2], 'paises': res[3],
        'dispositivos': res[4], 'navegadores': res[5], 'sistemas': res[6], 'recentes': res[7],
    }


# ---------- QR Code ----------

def qr(slug, formato='png'):
    import segno
    link = _buscar(_db(), slug)
    q = segno.make(f"{_base_url()}/{link['slug']}", error='m')
    buf = io.BytesIO()
    if formato == 'svg':
        q.save(buf, kind='svg', scale=10, border=2, dark='#07090e')
        return buf.getvalue(), 'image/svg+xml', f"qr-{link['slug']}.svg"
    q.save(buf, kind='png', scale=12, border=2, dark='#07090e')
    return buf.getvalue(), 'image/png', f"qr-{link['slug']}.png"


# ---------- Título do destino ----------

def _host_publico(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split('%')[0])
        if not ip.is_global:
            return False
    return True


def buscar_titulo(url):
    """Título da página de destino, para a lista ficar legível. Nunca levanta erro."""
    try:
        url = normalizar_url(url)
        sessao = requests.Session()
        for _ in range(5):
            host = urlsplit(url).hostname or ''
            if not _host_publico(host):  # não usar o Verto para sondar a rede local
                return {}
            r = sessao.get(url, headers={'User-Agent': USER_AGENT, 'Accept-Language': 'pt-BR,pt;q=0.9'},
                           timeout=(4, 6), stream=True, allow_redirects=False)
            if r.is_redirect and r.headers.get('location'):
                url = urljoin(url, r.headers['location'])
                r.close()
                continue
            break
        else:
            return {}
        if 'html' not in r.headers.get('content-type', ''):
            r.close()
            return {}
        corpo = b''
        for parte in r.iter_content(65536):
            corpo += parte
            if len(corpo) > 600_000 or b'</head>' in corpo.lower():
                break
        r.close()
        from bs4 import BeautifulSoup
        sopa = BeautifulSoup(corpo, 'html.parser')
        titulo = None
        for sel in (('meta', {'property': 'og:title'}), ('meta', {'name': 'twitter:title'})):
            tag = sopa.find(*sel)
            if tag and tag.get('content'):
                titulo = tag['content']
                break
        if not titulo and sopa.title and sopa.title.string:
            titulo = sopa.title.string
        titulo = re.sub(r'\s+', ' ', titulo or '').strip()[:300] or None
        return {'titulo': titulo} if titulo else {}
    except Exception:
        return {}


# ---------- Exportar / importar ----------

def exportar():
    db = _db()
    linhas = db.query(f'SELECT {CAMPOS_LINK}, senha_hash FROM links ORDER BY id')
    _backup(linhas)
    return {'formato': 'encurtador-gbm', 'versao': 1, 'gerado_em': int(time.time()),
            'base_url': _base_url(), 'links': linhas}


def importar(dados):
    links = dados.get('links') if isinstance(dados, dict) else dados
    if not isinstance(links, list):
        raise EncurtadorError('Arquivo inválido: use um backup exportado pelo Encurtador.')
    db = _db()
    agora = int(time.time())
    stmts, ignorados = [], 0
    for l in links:
        try:
            slug = _validar_alias(str(l.get('slug', ''))) if len(str(l.get('slug', ''))) >= 3 else None
            if not slug:
                raise EncurtadorError('sem código')
            url = normalizar_url(l.get('url'))
        except EncurtadorError:
            ignorados += 1
            continue
        stmts.append((
            'INSERT OR IGNORE INTO links (slug, url, titulo, notas, tags, criado_em, atualizado_em, expira_em, '
            'max_cliques, senha_hash, ativo, tipo_redirect, cliques, ultimo_clique) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [slug, url, l.get('titulo'), l.get('notas'), _tags(l.get('tags')),
             int(l.get('criado_em') or agora), agora, l.get('expira_em'), l.get('max_cliques'),
             l.get('senha_hash'), 0 if l.get('ativo') in (0, False) else 1,
             301 if l.get('tipo_redirect') == 301 else 302, int(l.get('cliques') or 0), l.get('ultimo_clique')]))
    antes = db.query('SELECT COUNT(*) AS n FROM links')[0]['n']
    for i in range(0, len(stmts), 50):
        db.batch(stmts[i:i + 50])
    depois = db.query('SELECT COUNT(*) AS n FROM links')[0]['n']
    novos = depois - antes
    return {'importados': novos, 'ja_existiam': len(stmts) - novos, 'invalidos': ignorados}
