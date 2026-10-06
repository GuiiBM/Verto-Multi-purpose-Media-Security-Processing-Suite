"""Reconhece os arquivos e ZIPs que o InstaSaver e o VscoSaver geram e
transforma um @ em nome de pasta.

Os nomes seguem o que os motores gravam (InstaSaver/_media_entry e
VscoSaver/_entry), conferidos com downloads reais:

  lis.guadix_story_20261003_224902_4000179235016517858.mp4
  lis.guadix_post_20260109_180735_3806522414008439347_3.jpg   (_3 = item do carrossel)
  ittmarjorie_story_20261003_215000_4000149513750788629_capa.jpg
  marianna_oribe_destaque_20260814_182959_3963810056923269345.mp4
  gabinutri.f_reel_20240630_120009_3401910820965818492.mp4
  isaturny__story_20260930_203844_3997939333221117231.jpg   (@ "isaturny_" termina em _)
  mariholiverr_galeria_20250520_171739_682ce36244391e2acc000001.jpg   (VSCO)
  lis.guadix_perfil.jpg

e os ZIPs: usuario_stories.zip, usuario_destaque_<título>.zip, usuario_posts.zip,
usuario_<código do post>.zip, usuario_galeria.zip, usuario_colecao.zip e
usuario_space_<título>.zip, com " (1)" no fim quando o navegador já tinha um igual.
"""
import os
import re

# Tipo no nome do arquivo -> subpasta dentro da pasta do perfil.
TIPOS = {
    'story': 'Stories',
    'destaque': 'Destaques',
    'post': 'Posts',
    'reel': 'Reels',
    'perfil': 'Fotos de Perfil',
    'galeria': 'VSCO',
    'colecao': os.path.join('VSCO', 'Coleção'),
    'space': os.path.join('VSCO', 'Spaces'),
}
SEM_TIPO = 'Outros'          # arquivo sem tipo reconhecível, mas de perfil conhecido
REVISAR = '_Revisar'         # arquivo sem @ reconhecível: nunca se perde, fica aqui

EXT_MIDIA = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.gif', '.mp4', '.mov', '.m4v', '.webm'}

# @ do Instagram: letras, números, ponto e sublinhado, até 30 caracteres (o
# VSCO também aceita hífen). Não guloso, para "isaturny__story" dar "isaturny_".
_USER = r'(?P<user>[A-Za-z0-9._-]{1,30}?)'
_DUP = r'(?: ?\(\d+\))?'     # " (1)" que o navegador acrescenta

# O nome tem que ser exatamente o que os apps gravam: item do carrossel (_2),
# capa (_capa) ou quadro salvo (_quadro_0m12s) e o " (1)" do navegador. Assim
# "x_story_... (Vintage).jpg" do Efeitos ou "(Reels 9x16).mp4" do editor de
# vídeo ficam em Downloads, onde você está trabalhando com eles.
RE_MIDIA = re.compile(_USER + r'_(?P<tipo>story|destaque|post|reel|galeria|colecao|space)_'
                      r'(?:\d{8}_\d{6}|sem_data)_[0-9A-Za-z]+(?:_\d{1,3})?(?:_capa|_quadro_\d+m\d{2}s)?' + _DUP, re.I)
RE_PERFIL = re.compile(_USER + r'_perfil' + _DUP, re.I)
RE_ZIP = re.compile(_USER + r'_(?:(?P<lista>stories|posts|galeria|colecao)|(?P<tipo>destaque|space)_(?P<titulo>.*?))'
                    + _DUP, re.I)
RE_HANDLE = re.compile(r'@?([A-Za-z0-9._-]{1,30})')
_LISTA_TIPO = {'stories': 'story', 'posts': 'post', 'galeria': 'galeria', 'colecao': 'colecao'}

RESERVADOS = {"CON", "PRN", "AUX", "NUL",
              *(f"COM{i}" for i in range(1, 10)),
              *(f"LPT{i}" for i in range(1, 10))}


def ler_arquivo(nome):
    """{'user', 'tipo'} de um arquivo do InstaSaver/VscoSaver, ou None."""
    base, ext = os.path.splitext(os.path.basename(nome))
    if ext.lower() not in EXT_MIDIA:
        return None
    m = RE_MIDIA.fullmatch(base)
    if m:
        return {'user': m['user'].lower(), 'tipo': m['tipo'].lower()}
    m = RE_PERFIL.fullmatch(base)
    if m:
        return {'user': m['user'].lower(), 'tipo': 'perfil'}
    return None


def ler_zip(nome):
    """{'user', 'tipo', 'titulo'} de um ZIP do InstaSaver/VscoSaver, ou None.
    O ZIP de um post (usuario_<código>.zip) não tem marca no nome: é
    reconhecido pelo conteúdo (ver organizador.eh_zip_reconhecido)."""
    base, ext = os.path.splitext(os.path.basename(nome))
    if ext.lower() != '.zip':
        return None
    m = RE_ZIP.fullmatch(base)
    if not m:
        return None
    tipo = _LISTA_TIPO[m['lista'].lower()] if m['lista'] else m['tipo'].lower()
    return {'user': m['user'].lower(), 'tipo': tipo, 'titulo': titulo_legivel(m['titulo'] or '')}


def titulo_legivel(texto):
    """'Viagem_à_praia_' -> 'Viagem à praia'. Título feito só de emoji (que o
    navegador troca por _) não tem o que aproveitar e volta vazio."""
    texto = re.sub(r'[_\s]+', ' ', texto).strip(' .-')
    return texto if any(c.isalnum() for c in texto) else ''


def sem_sufixo_duplicado(nome):
    """'x (1).mp4' -> 'x.mp4': o " (1)" é do navegador, não do arquivo. Sem ele,
    a cópia repetida é reconhecida pelo hash e descartada no destino."""
    base, ext = os.path.splitext(nome)
    return re.sub(r' ?\(\d+\)$', '', base) + ext


def handle_de_pasta(nome):
    """Uma pasta "@usuario" dentro do ZIP indica o perfil."""
    if not nome.startswith('@'):
        return None
    m = RE_HANDLE.fullmatch(nome)
    return m.group(1).lower() if m else None


def mesmo_perfil(nome_pasta, handle):
    """A pasta foi nomeada pelo próprio @ (ex.: "andre_bronca_" para @andre_bronca)?"""
    a, b = nome_pasta.strip().lstrip('@').lower(), handle.lower()
    return a in (b, b + '_') or a.rstrip('_.') == b.rstrip('_.')


def nome_da_pasta(handle: str) -> str:
    """@gbm.clicks -> Gbm Clicks, @maria_silva.foto -> Maria Silva Foto,
    @__joao__ -> Joao, @studio.42 -> Studio 42."""
    h = handle.strip().lstrip("@").lower()
    partes = [p for p in re.split(r"[._\-\s]+", h) if p]
    nome = " ".join(p.capitalize() for p in partes)
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", nome).strip(" .")
    if not nome or nome.upper() in RESERVADOS:
        nome = "Perfil " + "".join(partes)
    return nome[:60]


def limpar_nome(nome: str) -> str:
    """Nome escolhido pelo usuário (perfis.txt ou subpasta): só tira o que o
    sistema atual não aceita, para "niver dela <3" continuar igual no Linux."""
    proibidos = r'[<>:"/\\|?*\x00-\x1f]' if os.name == 'nt' else r'[/\x00]'
    nome = re.sub(proibidos, '', nome or '').strip(' .' if os.name == 'nt' else ' ')
    if not nome or nome in ('.', '..') or nome.upper() in RESERVADOS:
        return ''
    return nome[:80]
