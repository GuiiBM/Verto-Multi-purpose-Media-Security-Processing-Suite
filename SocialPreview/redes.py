"""Catálogo das redes do Social Preview: formatos, tamanhos, limites e como conectar.

É a fonte única: a página lê este catálogo (GET /social/catalogo) para desenhar
as prévias e validar o post, e o publicador usa os mesmos limites. Tamanhos e
regras conferidos na documentação oficial de cada API (out/2026):

- Instagram: imagem só JPEG, 4:5 a 1.91:1, 320–1440 px de largura, 8 MB;
  legenda 2200 caracteres, 30 hashtags, 20 menções; carrossel até 10;
  Reels 3 s–15 min; Story em vídeo até 60 s. A grade do perfil corta em 3:4.
- Threads: texto 500 (emoji conta pelos bytes UTF-8), carrossel 2–20, 8 MB.
- X: até 4 imagens ou 1 vídeo; texto 280 com peso (CJK/emoji contam 2, link 23).
- LinkedIn: multi-imagem orgânico até 20; texto 3000.
- Bluesky: até 4 imagens de no máximo 1 MB cada; texto 300 grafemas.
"""

GRAPH_VERSAO = 'v25.0'

# Zonas que a interface do app cobre (fração da altura/largura da tela 9:16).
ZONAS_STORY = {'topo': 0.13, 'base': 0.18}
ZONAS_REELS = {'topo': 0.10, 'base': 0.33, 'direita': 0.15}
ZONAS_TIKTOK = {'topo': 0.10, 'base': 0.26, 'direita': 0.15}
ZONAS_SHORTS = {'topo': 0.10, 'base': 0.25, 'direita': 0.15}
ZONAS_STATUS = {'topo': 0.10, 'base': 0.15}

V916 = {'ratio': '9:16', 'w': 1080, 'h': 1920}


def _t(ratio, w, h):
    return {'ratio': ratio, 'w': w, 'h': h}


REDES = [
    {
        'id': 'instagram', 'nome': 'Instagram', 'marca': 'instagram', 'cor': '#e1306c', 'api': True,
        'texto': {'max': 2200, 'hashtags': 30, 'mencoes': 20},
        'url_publica': True,
        'formatos': [
            {'id': 'feed', 'nome': 'Feed', 'tela': 'ig-feed', 'midia': ['imagem', 'video'],
             'tamanhos': [_t('4:5', 1080, 1350), _t('1:1', 1080, 1080), _t('1.91:1', 1080, 566)],
             'min_itens': 1, 'max_itens': 10, 'mistura': True, 'video_so_carrossel': True,
             'grade': '3:4', 'jpeg': True, 'max_mb': 8,
             'nota': 'No carrossel todas as fotos usam o formato da primeira. A grade do perfil mostra o centro em 3:4.'},
            {'id': 'story', 'nome': 'Story', 'tela': 'ig-story', 'midia': ['imagem', 'video'],
             'tamanhos': [V916], 'min_itens': 1, 'max_itens': 10, 'cada_item_um_post': True,
             'zonas': ZONAS_STORY, 'sem_texto': True, 'video': {'max_s': 60}, 'jpeg': True, 'max_mb': 8,
             'nota': 'Cada mídia vira um story. Pela API não dá para pôr figurinhas, link nem enquete.'},
            {'id': 'reels', 'nome': 'Reels', 'tela': 'ig-reels', 'midia': ['video'],
             'tamanhos': [V916], 'min_itens': 1, 'max_itens': 1, 'zonas': ZONAS_REELS,
             'video': {'min_s': 3, 'max_s': 900}},
        ],
        'conta': {
            'link': 'https://developers.facebook.com/apps',
            'campos': [
                {'id': 'token', 'rotulo': 'Token de acesso', 'tipo': 'password',
                 'dica': 'Token do Instagram (começa com IG…) ou token de Página do Facebook ligada à conta.'},
            ],
            'passos': [
                'A conta do Instagram precisa ser Profissional (Criador ou Empresa): Configurações → Tipo de conta.',
                'Em developers.facebook.com/apps crie um app do tipo "Empresa" e adicione o caso de uso "Instagram" → "API com login do Instagram".',
                'Em "Gerar tokens de acesso", adicione a sua conta e clique em "Gerar token" (permissões instagram_business_basic e instagram_business_content_publish).',
                'Cole o token aqui. Ele vale 60 dias e o Verto renova sozinho enquanto estiver em uso.',
            ],
            'aviso': 'O Instagram só aceita mídia por endereço público: na hora de postar, o Verto expõe só aquele arquivo por alguns minutos (veja "Hospedagem temporária").',
        },
    },
    {
        'id': 'facebook', 'nome': 'Facebook', 'marca': 'facebook', 'cor': '#1877f2', 'api': True,
        'texto': {'max': 63206},
        'formatos': [
            {'id': 'feed', 'nome': 'Feed', 'tela': 'fb-feed', 'midia': ['imagem', 'video'],
             'tamanhos': [_t('4:5', 1080, 1350), _t('1:1', 1080, 1080), _t('1.91:1', 1200, 630), _t('16:9', 1280, 720)],
             'min_itens': 0, 'max_itens': 10, 'mistura': False, 'max_videos': 1},
            {'id': 'story', 'nome': 'Story', 'tela': 'fb-story', 'midia': ['imagem'],
             'tamanhos': [V916], 'min_itens': 1, 'max_itens': 10, 'cada_item_um_post': True,
             'zonas': ZONAS_STORY, 'sem_texto': True},
            {'id': 'reels', 'nome': 'Reels', 'tela': 'fb-reels', 'midia': ['video'],
             'tamanhos': [V916], 'min_itens': 1, 'max_itens': 1, 'zonas': ZONAS_REELS,
             'video': {'min_s': 3, 'max_s': 90}},
        ],
        'conta': {
            'link': 'https://developers.facebook.com/tools/explorer/',
            'campos': [
                {'id': 'token', 'rotulo': 'Token da Página (ou do usuário)', 'tipo': 'password',
                 'dica': 'Com pages_manage_posts, pages_read_engagement e pages_show_list.'},
                {'id': 'pagina_id', 'rotulo': 'ID da Página', 'tipo': 'text', 'opcional': True,
                 'dica': 'Só se o token der acesso a mais de uma Página.'},
                {'id': 'app_id', 'rotulo': 'ID do app', 'tipo': 'text', 'opcional': True,
                 'dica': 'Com ID e chave secreta o Verto troca o token por um que não vence.'},
                {'id': 'app_secret', 'rotulo': 'Chave secreta do app', 'tipo': 'password', 'opcional': True},
            ],
            'passos': [
                'Publicação pela API só existe para Páginas (perfil pessoal não tem API de postagem).',
                'Abra o Explorador da Graph API, escolha o seu app e, em "Usuário ou Página", selecione a sua Página.',
                'Marque pages_manage_posts, pages_read_engagement e pages_show_list e clique em "Gerar token de acesso".',
                'Cole o token aqui. Se informar o ID e a chave do app, o Verto troca por um token de Página sem validade.',
            ],
        },
    },
    {
        'id': 'threads', 'nome': 'Threads', 'marca': 'threads', 'cor': '#eef0f3', 'api': True,
        'texto': {'max': 500, 'unidade': 'threads'},
        'url_publica': True,
        'formatos': [
            {'id': 'post', 'nome': 'Post', 'tela': 'threads', 'midia': ['imagem', 'video'],
             'tamanhos': [_t('4:5', 1080, 1350), _t('1:1', 1080, 1080), _t('3:4', 1080, 1440), _t('16:9', 1440, 810)],
             'min_itens': 0, 'max_itens': 20, 'mistura': True, 'max_mb': 8, 'video': {'max_s': 300}},
        ],
        'conta': {
            'link': 'https://developers.facebook.com/apps',
            'campos': [
                {'id': 'token', 'rotulo': 'Token do Threads', 'tipo': 'password',
                 'dica': 'Com threads_basic e threads_content_publish.'},
            ],
            'passos': [
                'Em developers.facebook.com/apps crie um app com o caso de uso "Acessar a API do Threads".',
                'Em Casos de uso → Threads → Configurações, adicione a sua conta como testadora e aceite o convite no Threads (Configurações → Conta → Permissões do site).',
                'No "Gerador de tokens de usuário" gere o token com threads_basic e threads_content_publish.',
                'Cole aqui. O token vale 60 dias e o Verto renova sozinho enquanto estiver em uso.',
            ],
            'aviso': 'Como no Instagram, a mídia é buscada por endereço público temporário.',
        },
    },
    {
        'id': 'x', 'nome': 'X', 'marca': 'x', 'cor': '#e7e9ea', 'api': True,
        'texto': {'max': 280, 'unidade': 'x'},
        'formatos': [
            {'id': 'post', 'nome': 'Post', 'tela': 'x', 'midia': ['imagem', 'video'],
             'tamanhos': [_t('16:9', 1600, 900), _t('1:1', 1200, 1200), _t('4:5', 1080, 1350)],
             'min_itens': 0, 'max_itens': 4, 'mistura': False, 'max_videos': 1, 'max_mb': 5,
             'video': {'max_s': 140}},
        ],
        'conta': {
            'link': 'https://console.x.com',
            'campos': [
                {'id': 'api_key', 'rotulo': 'API Key (Consumer Key)', 'tipo': 'password'},
                {'id': 'api_secret', 'rotulo': 'API Key Secret', 'tipo': 'password'},
                {'id': 'access_token', 'rotulo': 'Access Token', 'tipo': 'password'},
                {'id': 'access_secret', 'rotulo': 'Access Token Secret', 'tipo': 'password'},
            ],
            'passos': [
                'No console de desenvolvedor da X (console.x.com) crie um app.',
                'Em "User authentication settings", defina as permissões como "Read and write".',
                'Em "Keys and tokens", copie a API Key e a API Key Secret e gere o "Access Token and Secret" (gere depois de mudar para Read and write, senão o token sai só leitura).',
                'Cole as quatro chaves aqui.',
            ],
            'aviso': 'A API da X é paga por uso: cada post consome créditos pré-pagos da sua conta de desenvolvedor.',
        },
    },
    {
        'id': 'linkedin', 'nome': 'LinkedIn', 'marca': 'linkedin', 'cor': '#0a66c2', 'api': True,
        'texto': {'max': 3000},
        'formatos': [
            {'id': 'post', 'nome': 'Post', 'tela': 'linkedin', 'midia': ['imagem', 'video'],
             'tamanhos': [_t('1.91:1', 1200, 627), _t('1:1', 1080, 1080), _t('4:5', 1080, 1350), _t('16:9', 1920, 1080)],
             'min_itens': 0, 'max_itens': 20, 'mistura': False, 'max_videos': 1},
        ],
        'conta': {
            'link': 'https://www.linkedin.com/developers/tools/oauth/token-generator',
            'campos': [
                {'id': 'token', 'rotulo': 'Token de acesso', 'tipo': 'password',
                 'dica': 'Com openid, profile e w_member_social.'},
                {'id': 'autor', 'rotulo': 'Publicar como (URN)', 'tipo': 'text', 'opcional': True,
                 'dica': 'Vazio = o seu perfil. Para uma Página: urn:li:organization:123 (precisa de w_organization_social).'},
            ],
            'passos': [
                'Em linkedin.com/developers/apps crie um app (ele pede uma Página de empresa associada).',
                'Na aba "Products", adicione "Share on LinkedIn" e "Sign In with LinkedIn using OpenID Connect".',
                'No "OAuth Token Generator" escolha o app, marque openid, profile e w_member_social e gere o token.',
                'Cole aqui. O token vale 60 dias; depois é só gerar outro.',
            ],
        },
    },
    {
        'id': 'bluesky', 'nome': 'Bluesky', 'marca': 'bluesky', 'cor': '#1185fe', 'api': True,
        'texto': {'max': 300, 'unidade': 'grafemas'},
        'formatos': [
            {'id': 'post', 'nome': 'Post', 'tela': 'bluesky', 'midia': ['imagem'],
             'tamanhos': [_t('4:5', 1080, 1350), _t('1:1', 1080, 1080), _t('16:9', 1600, 900), _t('3:4', 1080, 1440)],
             'min_itens': 0, 'max_itens': 4, 'max_kb': 976},
        ],
        'conta': {
            'link': 'https://bsky.app/settings/app-passwords',
            'campos': [
                {'id': 'handle', 'rotulo': 'Usuário', 'tipo': 'text', 'dica': 'Ex.: voce.bsky.social'},
                {'id': 'senha_app', 'rotulo': 'Senha de app', 'tipo': 'password',
                 'dica': 'Nunca a senha principal.'},
                {'id': 'servidor', 'rotulo': 'Servidor', 'tipo': 'url', 'opcional': True,
                 'dica': 'Vazio = https://bsky.social'},
            ],
            'passos': [
                'No Bluesky: Configurações → Privacidade e segurança → Senhas de app → Adicionar senha de app.',
                'Cole aqui o seu usuário e a senha de app gerada (formato xxxx-xxxx-xxxx-xxxx).',
            ],
        },
    },
    {
        'id': 'mastodon', 'nome': 'Mastodon', 'marca': 'mastodon', 'cor': '#6364ff', 'api': True,
        'texto': {'max': 500},
        'formatos': [
            {'id': 'post', 'nome': 'Post', 'tela': 'mastodon', 'midia': ['imagem', 'video'],
             'tamanhos': [_t('16:9', 1600, 900), _t('1:1', 1080, 1080), _t('4:5', 1080, 1350)],
             'min_itens': 0, 'max_itens': 4, 'mistura': False, 'max_videos': 1, 'max_mb': 16},
        ],
        'conta': {
            'link': '',
            'campos': [
                {'id': 'servidor', 'rotulo': 'Servidor', 'tipo': 'url', 'dica': 'Ex.: https://mastodon.social'},
                {'id': 'token', 'rotulo': 'Token de acesso', 'tipo': 'password'},
            ],
            'passos': [
                'No seu servidor: Preferências → Desenvolvimento → Nova aplicação.',
                'Marque os escopos read:accounts, write:statuses e write:media e salve.',
                'Abra a aplicação criada e copie "Seu token de acesso".',
            ],
        },
    },
    {
        'id': 'telegram', 'nome': 'Telegram', 'marca': 'telegram', 'cor': '#26a5e4', 'api': True,
        'texto': {'max': 1024, 'max_sem_midia': 4096},
        'formatos': [
            {'id': 'canal', 'nome': 'Canal', 'tela': 'telegram', 'midia': ['imagem', 'video'],
             'tamanhos': [_t('4:5', 1080, 1350), _t('1:1', 1080, 1080), _t('16:9', 1280, 720)],
             'min_itens': 0, 'max_itens': 10, 'mistura': True, 'max_mb': 10, 'max_mb_video': 50},
        ],
        'conta': {
            'link': 'https://t.me/BotFather',
            'campos': [
                {'id': 'bot_token', 'rotulo': 'Token do bot', 'tipo': 'password'},
                {'id': 'chat_id', 'rotulo': 'Canal ou grupo', 'tipo': 'text',
                 'dica': '@nomedocanal ou o ID numérico (-100…).'},
            ],
            'passos': [
                'Fale com o @BotFather, mande /newbot e copie o token.',
                'Adicione o bot como administrador do canal (ou grupo) com permissão de publicar.',
                'Informe o @ do canal (ou o ID numérico, para canais privados).',
            ],
        },
    },
    {
        'id': 'discord', 'nome': 'Discord', 'marca': 'discord', 'cor': '#5865f2', 'api': True,
        'texto': {'max': 2000},
        'formatos': [
            {'id': 'canal', 'nome': 'Canal', 'tela': 'discord', 'midia': ['imagem', 'video'],
             'tamanhos': [_t('16:9', 1600, 900), _t('1:1', 1080, 1080), _t('4:5', 1080, 1350)],
             'min_itens': 0, 'max_itens': 10, 'mistura': True, 'max_mb': 10, 'max_mb_video': 10},
        ],
        'conta': {
            'link': '',
            'campos': [
                {'id': 'webhook', 'rotulo': 'URL do webhook', 'tipo': 'password',
                 'dica': 'https://discord.com/api/webhooks/…'},
            ],
            'passos': [
                'No canal: Editar canal → Integrações → Webhooks → Novo webhook.',
                'Dê um nome e uma foto (é como o post vai aparecer) e clique em "Copiar URL do webhook".',
            ],
        },
    },
    {
        'id': 'pinterest', 'nome': 'Pinterest', 'marca': 'pinterest', 'cor': '#e60023', 'api': True,
        'texto': {'max': 500, 'titulo': 100},
        'formatos': [
            {'id': 'pin', 'nome': 'Pin', 'tela': 'pinterest', 'midia': ['imagem'],
             'tamanhos': [_t('2:3', 1000, 1500), _t('1:1', 1000, 1000), _t('9:16', 1080, 1920)],
             'min_itens': 1, 'max_itens': 1, 'max_mb': 20},
        ],
        'conta': {
            'link': 'https://developers.pinterest.com/apps/',
            'campos': [
                {'id': 'token', 'rotulo': 'Token de acesso', 'tipo': 'password',
                 'dica': 'Com boards:read, pins:write e user_accounts:read.'},
                {'id': 'pasta', 'rotulo': 'ID da pasta', 'tipo': 'text', 'opcional': True,
                 'dica': 'Vazio = a primeira pasta. Ao testar, o Verto lista as suas pastas.'},
                {'id': 'sandbox', 'rotulo': 'App em acesso de teste (sandbox)', 'tipo': 'checkbox', 'opcional': True},
            ],
            'passos': [
                'Em developers.pinterest.com/apps conecte um app à sua conta (empresa).',
                'Gere um token com boards:read, pins:write e user_accounts:read.',
                'Apps em "Trial access" só criam pins no sandbox: marque a opção até o Pinterest aprovar o acesso padrão.',
            ],
        },
    },
    {
        'id': 'youtube', 'nome': 'YouTube', 'marca': 'youtube', 'cor': '#ff0033', 'api': True,
        'texto': {'max': 5000, 'titulo': 100},
        'oauth': True,
        'formatos': [
            {'id': 'shorts', 'nome': 'Shorts', 'tela': 'yt-shorts', 'midia': ['video'],
             'tamanhos': [V916], 'min_itens': 1, 'max_itens': 1, 'zonas': ZONAS_SHORTS,
             'video': {'max_s': 180}},
            {'id': 'video', 'nome': 'Vídeo', 'tela': 'yt-video', 'midia': ['video'],
             'tamanhos': [_t('16:9', 1920, 1080)], 'min_itens': 1, 'max_itens': 1},
        ],
        'conta': {
            'link': 'https://console.cloud.google.com/apis/credentials',
            'campos': [
                {'id': 'client_id', 'rotulo': 'ID do cliente OAuth', 'tipo': 'text'},
                {'id': 'client_secret', 'rotulo': 'Chave secreta do cliente', 'tipo': 'password'},
            ],
            'passos': [
                'No Google Cloud crie um projeto e ative a "YouTube Data API v3".',
                'Configure a tela de consentimento OAuth (externo, modo de teste) e adicione o seu e-mail como usuário de teste.',
                'Em Credenciais → Criar credenciais → ID do cliente OAuth, escolha "App para computador".',
                'Cole o ID e a chave aqui, salve e clique em "Entrar com Google".',
            ],
            'aviso': 'Enquanto o projeto não passar pela auditoria do Google, os vídeos enviados pela API ficam privados.',
        },
    },
    {
        'id': 'tiktok', 'nome': 'TikTok', 'marca': 'tiktok', 'cor': '#ff0050', 'api': False,
        'texto': {'max': 4000},
        'abrir': 'https://www.tiktok.com/tiktokstudio/upload',
        'formatos': [
            {'id': 'video', 'nome': 'Vídeo', 'tela': 'tiktok', 'midia': ['video'],
             'tamanhos': [V916], 'min_itens': 1, 'max_itens': 1, 'zonas': ZONAS_TIKTOK},
            {'id': 'fotos', 'nome': 'Fotos', 'tela': 'tiktok', 'midia': ['imagem'],
             'tamanhos': [V916], 'min_itens': 1, 'max_itens': 35, 'zonas': ZONAS_TIKTOK},
        ],
        'assistido': 'A API do TikTok só publica para apps auditados pelo TikTok. O Verto prepara o arquivo no formato certo, copia a legenda e abre o TikTok Studio.',
    },
    {
        'id': 'whatsapp', 'nome': 'Status do WhatsApp', 'marca': 'whatsapp', 'cor': '#25d366', 'api': False,
        'texto': {'max': 700},
        'abrir': 'https://web.whatsapp.com/',
        'formatos': [
            {'id': 'status', 'nome': 'Status', 'tela': 'wa-status', 'midia': ['imagem', 'video'],
             'tamanhos': [V916], 'min_itens': 1, 'max_itens': 10, 'cada_item_um_post': True,
             'zonas': ZONAS_STATUS, 'video': {'max_s': 60}},
        ],
        'assistido': 'O WhatsApp não tem API para status de conta pessoal. O Verto prepara os arquivos em 9:16, copia a legenda e abre o WhatsApp Web.',
    },
    {
        'id': 'link', 'nome': 'Prévia de link', 'marca': None, 'cor': '#9aa1ac', 'api': False,
        'texto': {'max': 200, 'titulo': 70},
        'formatos': [
            {'id': 'og', 'nome': 'Open Graph', 'tela': 'og', 'midia': ['imagem'],
             'tamanhos': [_t('1.91:1', 1200, 630)], 'min_itens': 1, 'max_itens': 1},
        ],
        'assistido': 'É a imagem que aparece quando alguém compartilha o link do seu site. O Verto gera a imagem 1200×630 e as meta tags para colar no <head>.',
    },
]

POR_ID = {r['id']: r for r in REDES}


def rede(rid):
    return POR_ID.get(rid)


def formato(rid, fid):
    r = POR_ID.get(rid)
    if not r:
        return None
    return next((f for f in r['formatos'] if f['id'] == fid), None)


def catalogo():
    """Versão para a página: sem nada que dependa do servidor."""
    return {'redes': REDES}
