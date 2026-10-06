"""Automações do Verto: tarefas que rodam sozinhas em segundo plano.

Organizador do InstaSaver: quando o InstaSaver/VscoSaver
entregam um download (que continua indo para Downloads), confere a pasta e
leva o arquivo para Documentos/Instagram/<Perfil>/<Stories|Destaques|...>.
Nada fica olhando a pasta sem motivo: a conferência acontece quando as rotas
de download avisam (avisar_download), quando o Verto liga e quando se clica
em "Organizar agora".

Editor automático de vídeo (reels/): transcreve, corta pausas e retomadas,
legenda e enquadra; os trabalhos rodam numa fila própria, para um render
longo não atrasar o organizador.

Peças comuns (em core/), pensadas para as próximas automações também:
vigia de pasta, fila com um único worker e registro do que foi feito.
Configuração e histórico ficam em Automacoes/dados/ (fora do git).
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from .core import pastas
from .core.fila import Fila
from .core.registro import Registro
from .core.vigia import Vigia, baixando
from .instasaver import nomes
from .instasaver.organizador import Organizador, send2trash
from .reels import enquadramento, legendas, transcricao
from .reels.editor import Editor, EditorError, PRESETS as PRESETS_EDITOR

_DIR = Path(__file__).resolve().parent
DADOS = _DIR / 'dados'
_CONFIG = DADOS / 'config.json'
_PADRAO = {'vigia_ativo': True, 'entrada': '', 'destino': '', 'editor_entrada': ''}


class AutomacoesError(Exception):
    pass


registro = Registro(DADOS / 'registro.jsonl')
_lock = threading.Lock()
_rt = {'fila': None, 'vigia': None, 'org': None, 'editor': None}


# ------------------------------------------------------------ configuração ---

def _config():
    try:
        dados = json.loads(_CONFIG.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        dados = {}
    return {**_PADRAO, **{k: v for k, v in dados.items() if k in _PADRAO}}


def _gravar_config(cfg):
    DADOS.mkdir(parents=True, exist_ok=True)
    _CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')


def entrada_padrao():
    return pastas.downloads()


def destino_padrao():
    return pastas.documentos() / 'Instagram'


def entrada():
    valor = _config()['entrada']
    return Path(valor).expanduser() if valor else entrada_padrao()


def destino():
    valor = _config()['destino']
    return Path(valor).expanduser() if valor else destino_padrao()


def organizador():
    """Organizador do destino atual (refeito se o destino mudar)."""
    alvo = destino()
    org = _rt['org']
    if org is None or org.destino != alvo:
        org = _rt['org'] = Organizador(alvo, registro)
    return org


# ------------------------------------------------------------------ início ---

def iniciar():
    """Liga a fila e o vigia uma vez por processo (o app.py chama no processo
    que atende as páginas, não no observador do modo debug)."""
    with _lock:
        if _rt['fila']:
            return
        _rt['fila'] = Fila(registro)
        org = organizador()
        try:
            org.limpar_temporarios()
            org.sincronizar()
        except OSError as e:
            registro.erro(f'Não consegui ler a pasta de destino: {e}')
        _rt['editor'] = Editor(DADOS, registro)
        # A pasta de entrada do editor também só é olhada quando pedem: aqui,
        # ao ligar o Verto (se ela existir), e no botão "Processar pasta".
        if editor_entrada().is_dir():
            try:
                _rt['editor'].processar_pasta(editor_entrada(), _opcoes_da_pasta())
            except Exception as e:
                registro.erro(f'Editor: não consegui ler a pasta de entrada: {e}', automacao='editor')
        _rt['vigia'] = Vigia(
            obter_pasta=lambda: entrada() if _config()['vigia_ativo'] else None,
            filtro=lambda p: organizador().eh_candidato(p),
            ao_chegar=_enfileirar,
            combina=lambda p, nome: nomes.sem_sufixo_duplicado(p.name) == nomes.sem_sufixo_duplicado(nome),
        )
    # Uma conferência ao ligar: pega o que chegou com o Verto desligado.
    _rt['vigia'].avisar()


def avisar_download(nome=None):
    """Chamado pelas rotas de download do InstaSaver/VscoSaver quando terminam
    de entregar o arquivo: o navegador grava em Downloads logo em seguida."""
    if not _config()['vigia_ativo']:
        return
    iniciar()
    _rt['vigia'].avisar(nome)


def _enfileirar(caminhos):
    fila = _rt['fila']
    soltos = [p for p in caminhos if p.suffix.lower() != '.zip']
    if soltos:
        fila.adicionar(('soltos', tuple(map(str, soltos))),
                       f"{len(soltos)} {'arquivo' if len(soltos) == 1 else 'arquivos'} de {soltos[0].parent.name}",
                       lambda: organizador().organizar_arquivos(soltos))
    for z in caminhos:
        if z.suffix.lower() == '.zip':
            fila.adicionar(('zip', str(z)), f'ZIP {z.name}', lambda z=z: organizador().organizar_zip(z))


def _candidatos():
    pasta = entrada()
    if not pasta.is_dir():
        return []
    org = organizador()
    out = []
    for p in sorted(pasta.iterdir()):
        try:
            if p.is_file() and not baixando(p) and org.eh_candidato(p):
                out.append(p)
        except OSError:
            continue
    return out


# ------------------------------------------------------------------- tela ---

def estado(depois_de=0, verificar=False):
    """Lido pela tela a cada poucos segundos: só memória. A pasta de entrada só
    é lida quando verificar=True (ao abrir a página e depois de uma ação)."""
    iniciar()
    cfg = _config()
    org = organizador()
    candidatos = _candidatos() if verificar else None
    return {
        'config': {
            'vigia_ativo': cfg['vigia_ativo'],
            'entrada': str(entrada()), 'destino': str(destino()),
            'entrada_padrao': str(entrada_padrao()), 'destino_padrao': str(destino_padrao()),
            'perfis_arquivo': str(org.arquivo_perfis),
        },
        'fila': _rt['fila'].estado(),
        'esperando': None if candidatos is None else {
            'arquivos': sum(1 for p in candidatos if p.suffix.lower() != '.zip'),
            'zips': sum(1 for p in candidatos if p.suffix.lower() == '.zip'),
        },
        'perfis': len(org.ler_perfis()),
        'lixeira': bool(send2trash),
        'registro': registro.listar(depois_de),
    }


def salvar_config(dados):
    cfg = _config()
    if 'vigia_ativo' in dados:
        cfg['vigia_ativo'] = bool(dados['vigia_ativo'])
    for chave in ('entrada', 'destino'):
        if chave not in dados:
            continue
        valor = (dados[chave] or '').strip()
        if valor:
            caminho = Path(valor).expanduser()
            if not caminho.is_absolute():
                raise AutomacoesError(f'Use o caminho completo da pasta ({chave}).')
            if chave == 'entrada' and not caminho.is_dir():
                raise AutomacoesError(f'A pasta de entrada não existe: {caminho}')
            if chave == 'destino' and not caminho.parent.is_dir():
                raise AutomacoesError(f'A pasta onde o destino seria criado não existe: {caminho.parent}')
        cfg[chave] = valor
    ent = Path(cfg['entrada']).expanduser() if cfg['entrada'] else entrada_padrao()
    des = Path(cfg['destino']).expanduser() if cfg['destino'] else destino_padrao()
    if ent.resolve() == des.resolve():
        raise AutomacoesError('A entrada e o destino precisam ser pastas diferentes.')
    _gravar_config(cfg)
    if cfg['vigia_ativo'] and 'vigia_ativo' in dados and _rt['vigia']:
        _rt['vigia'].esquecer()   # religado: reavalia o que já estava na pasta
        _rt['vigia'].avisar()
    return {'config': estado()['config']}


def organizar_agora():
    iniciar()
    candidatos = _candidatos()
    if _rt['vigia']:
        for p in candidatos:
            _rt['vigia'].esquecer(p)
    _enfileirar(candidatos)
    return {'enfileirados': len(candidatos)}


def previa_importacao():
    org = organizador()
    perfis, mapa = org.ler_perfis(), org.mapa()
    out = []
    for item in org.pastas_para_importar(entrada()):
        dono = item['dono']
        if dono in mapa:
            vai_para = mapa[dono].name
        elif dono in perfis:
            vai_para = perfis[dono]
        elif item['nome_proprio']:
            vai_para = nomes.limpar_nome(item['pasta'].name) or nomes.nome_da_pasta(dono)
        else:
            vai_para = nomes.nome_da_pasta(dono)
        out.append({'pasta': item['pasta'].name, 'dono': dono, 'outros': item['outros'],
                    'arquivos': item['arquivos'], 'sem_arroba': item['sem_arroba'], 'vai_para': vai_para})
    return {'pastas': out, 'destino': str(destino())}


def importar(escolhidas=None):
    iniciar()
    org = organizador()
    itens = org.pastas_para_importar(entrada())
    if escolhidas is not None:
        itens = [i for i in itens if i['pasta'].name in set(escolhidas)]
    for item in itens:
        _rt['fila'].adicionar(('importar', str(item['pasta'])), f'pasta {item["pasta"].name}',
                              lambda item=item: organizador().importar_pasta(item))
    return {'enfileirados': len(itens)}


def perfis_texto():
    org = organizador()
    return {'texto': org.texto_perfis(), 'arquivo': str(org.arquivo_perfis)}


def salvar_perfis(texto):
    if not isinstance(texto, str):
        raise AutomacoesError('Texto inválido.')
    return {'mudancas': organizador().salvar_texto_perfis(texto)}


def limpar_registro():
    registro.limpar()
    return {}


def abrir_pasta(qual):
    """Abre a pasta no gerenciador de arquivos deste computador."""
    caminho = {'entrada': entrada(), 'destino': destino()}.get(qual)
    if caminho is None:
        raise AutomacoesError('Pasta desconhecida.')
    caminho.mkdir(parents=True, exist_ok=True)
    _abrir(caminho)
    return {}


def _abrir(caminho):
    try:
        if os.name == 'nt':
            os.startfile(str(caminho))
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(caminho)])
        else:
            subprocess.Popen(['xdg-open', str(caminho)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        raise AutomacoesError(f'Não consegui abrir a pasta: {e}')


# ------------------------------------------------------- editor de vídeo ---

def editor():
    iniciar()
    return _rt['editor']


def editor_entrada():
    valor = _config()['editor_entrada']
    return Path(valor).expanduser() if valor else pastas.documentos() / 'Verto Editor' / 'Entrada'


def _opcoes_da_pasta():
    """O preset marcado como "da pasta" (ou o padrão), sempre sem revisão."""
    meus = (_rt['editor'] or editor()).presets()['meus']
    escolhido = next((v for v in meus.values() if v.get('pasta')), None)
    return {**(escolhido or PRESETS_EDITOR['padrao']), 'revisar': False}


def _editor(fn):
    """Traduz os erros do editor para o padrão das rotas."""
    try:
        return fn()
    except (EditorError, ValueError) as e:
        raise AutomacoesError(str(e))


def editor_estado():
    ed = editor()
    return {
        'trabalhos': ed.listar(),
        'fila': ed.fila.estado(),
        'presets': ed.presets(),
        'entrada': str(editor_entrada()),
        'downloads': str(pastas.downloads()),
        'catalogo': {
            'formatos': {k: {'largura': w, 'altura': h, 'nome': n} for k, (w, h, n) in enquadramento.FORMATOS.items()},
            'intensidades': PRESETS_EDITOR['intensidades'],
            'legendas': {k: {'nome': v['nome'], 'desc': v['desc']} for k, v in legendas.ESTILOS.items()},
            'enquadramentos': enquadramento.MODOS,
            'modelos': transcricao.MODELOS,
        },
    }


def editor_enviar(arquivo, opcoes, mapa_bytes=None):
    """Vídeo vindo do navegador (e, para reabrir, o .cortes.json)."""
    ed = editor()
    if not arquivo or not arquivo.filename:
        raise AutomacoesError('Escolha um vídeo.')
    nome = Path(arquivo.filename).name
    tmp = ed.dir / '_envios' / f'{int(time.time() * 1000)}{Path(nome).suffix.lower()}'
    tmp.parent.mkdir(parents=True, exist_ok=True)
    arquivo.save(str(tmp))
    try:
        mapa = json.loads(mapa_bytes.decode('utf-8')) if mapa_bytes else None
    except ValueError:
        tmp.unlink(missing_ok=True)
        raise AutomacoesError('O .cortes.json está corrompido.')
    try:
        return {'trabalho': _editor(lambda: ed.criar(tmp, nome, opcoes, copia=True, mapa=mapa))}
    finally:
        tmp.unlink(missing_ok=True)


def editor_local(caminho, opcoes):
    """Vídeo que já está neste computador: não precisa copiar (bom para arquivos grandes)."""
    p = Path((caminho or '').strip().strip('"')).expanduser()
    if not p.is_file():
        raise AutomacoesError(f'Arquivo não encontrado: {p}')
    return {'trabalho': _editor(lambda: editor().criar(p, p.name, opcoes, copia=False, origem='local'))}


def editor_detalhes(job_id):
    return {'trabalho': _editor(lambda: editor().detalhes(job_id))}


def editor_revisar(job_id, dados):
    return {'mapa': _editor(lambda: editor().revisar(job_id, dados or {}))}


def editor_exportar(job_id, dados):
    return {'trabalho': _editor(lambda: editor().exportar(job_id, dados or None))}


def editor_tentar(job_id):
    return {'trabalho': _editor(lambda: editor().tentar_de_novo(job_id))}


def editor_remover(job_id):
    _editor(lambda: editor().remover(job_id))
    return {}


def editor_arquivo(job_id, qual, n=0):
    """Caminho do vídeo original ou de uma saída, para a tela tocar/baixar."""
    job = _editor(lambda: editor().obter(job_id))
    if qual == 'fonte':
        caminho = Path(job['fonte'])
    else:
        saidas = job.get('saidas') or []
        if not 0 <= n < len(saidas):
            raise AutomacoesError('Essa exportação não existe.')
        caminho = Path(saidas[n]['mp4'])
    if not caminho.is_file():
        raise AutomacoesError('O arquivo não está mais no lugar.')
    return caminho


def editor_preset(dados):
    ed = editor()
    if dados.get('remover'):
        return {'meus': ed.remover_preset(dados['remover'])}
    return {'meus': _editor(lambda: ed.salvar_preset(dados.get('nome'), dados.get('opcoes'), dados.get('pasta')))}


def editor_processar_pasta():
    entrada = editor_entrada()
    n = _editor(lambda: editor().processar_pasta(entrada, _opcoes_da_pasta()))
    return {'enfileirados': n, 'entrada': str(entrada)}


def editor_abrir_entrada():
    p = editor_entrada()
    p.mkdir(parents=True, exist_ok=True)
    _abrir(p)
    return {}
