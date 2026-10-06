"""Editor automático de vídeo: trabalhos, revisão e exportação.

Um trabalho passa por: fila -> analisando -> revisao (opcional) -> fila ->
renderizando -> pronto. A análise (transcrição, pausas, retomadas, rostos)
é feita uma vez; a revisão e cada exportação (em qualquer formato) só
refazem o mapa de cortes e o render.

Cada trabalho mora em Automacoes/dados/editor/<id>/ (trabalho.json + áudio de
análise + cópia do vídeo enviado pelo navegador). O resultado vai para
Downloads no padrão do app Efeitos: "gravacao (Reels 9x16).mp4", com a
legenda .srt e o mapa de cortes .cortes.json ao lado (reabre a edição depois).
"""
import copy
import json
import shutil
import threading
import time
import uuid
from pathlib import Path

from ..core import pastas
from ..core.fila import Fila
from . import analise, cortes, enquadramento, legendas, render, transcricao

_DIR = Path(__file__).resolve().parent
PRESETS = json.loads((_DIR / 'presets.json').read_text(encoding='utf-8'))
EXT_VIDEO = {'.mp4', '.mov', '.m4v', '.mkv', '.webm', '.avi', '.3gp'}
VERSAO_MAPA = 1
DIAS_GUARDADOS = 14


class EditorError(Exception):
    pass


class Editor:
    def __init__(self, dados: Path, registro):
        self.dir = dados / 'editor'
        self.registro = registro
        self.fila = Fila(registro)
        self._lock = threading.RLock()
        self._jobs = {}
        self._carregar()

    # ------------------------------------------------------------ opções ---

    def presets_usuario_arquivo(self):
        return self.dir.parent / 'editor_presets.json'

    def presets(self):
        try:
            meus = json.loads(self.presets_usuario_arquivo().read_text(encoding='utf-8'))
        except (OSError, ValueError):
            meus = {}
        return {'padrao': PRESETS['padrao'], 'meus': meus}

    def salvar_preset(self, nome, opcoes, padrao_da_pasta=False):
        nome = (nome or '').strip()[:40]
        if not nome:
            raise EditorError('Dê um nome ao preset.')
        dados = self.presets()['meus']
        dados[nome] = {**self.opcoes(opcoes), 'pasta': bool(padrao_da_pasta)}
        if padrao_da_pasta:
            for k, v in dados.items():
                v['pasta'] = k == nome
        self.presets_usuario_arquivo().parent.mkdir(parents=True, exist_ok=True)
        self.presets_usuario_arquivo().write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
        return dados

    def remover_preset(self, nome):
        dados = self.presets()['meus']
        dados.pop(nome, None)
        self.presets_usuario_arquivo().write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
        return dados

    def opcoes(self, o=None):
        """Completa e valida as opções vindas da tela."""
        base = dict(PRESETS['padrao'])
        base.update({k: v for k, v in (o or {}).items() if k in base})
        if base['intensidade'] not in PRESETS['intensidades']:
            base['intensidade'] = 'dinamico'
        if base['legenda'] not in legendas.ESTILOS:
            base['legenda'] = 'classico'
        if base['enquadramento'] not in enquadramento.MODOS:
            base['enquadramento'] = 'rosto'
        if base['modelo'] not in transcricao.MODELOS:
            base['modelo'] = 'small'
        if base['formato'] not in enquadramento.FORMATOS:
            base['formato'] = 'custom'
            enquadramento.tamanho_saida('custom', base['largura'], base['altura'])   # valida
        for k in ('retomadas', 'tratar_audio', 'isolar_voz', 'revisar'):
            base[k] = bool(base[k])
        base['idioma'] = str(base['idioma'] or 'pt')[:5]
        return base

    # ---------------------------------------------------------- trabalhos ---

    def _carregar(self):
        if not self.dir.is_dir():
            return
        limite = time.time() - DIAS_GUARDADOS * 86400
        for arq in self.dir.glob('*/trabalho.json'):
            try:
                job = json.loads(arq.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if job.get('criado', 0) < limite:
                shutil.rmtree(arq.parent, ignore_errors=True)
                continue
            if job.get('estado') in ('fila', 'analisando', 'renderizando'):
                job['estado'] = 'erro'
                job['erro'] = 'Interrompido: o Verto foi fechado no meio. Clique em “Tentar de novo”.'
            self._jobs[job['id']] = job

    def _salvar(self, job):
        pasta = self.dir / job['id']
        pasta.mkdir(parents=True, exist_ok=True)
        tmp = pasta / 'trabalho.json.tmp'
        tmp.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
        tmp.replace(pasta / 'trabalho.json')

    def _estado(self, job, estado=None, etapa=None, progresso=None, salvar=True):
        with self._lock:
            if estado:
                job['estado'] = estado
            if etapa is not None:
                job['etapa'] = etapa
            if progresso is not None:
                job['progresso'] = round(progresso, 3)
            if salvar:
                self._salvar(job)

    def resumo(self, job):
        return {k: job.get(k) for k in ('id', 'nome', 'estado', 'etapa', 'progresso', 'erro', 'criado', 'saidas',
                                        'opcoes', 'origem')} | {
            'duracao': (job.get('info') or {}).get('duracao'),
            'duracao_final': job.get('duracao_final'),
            'retomadas': len(job.get('retomadas') or []),
        }

    def listar(self):
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: -j['criado'])
            return [self.resumo(j) for j in jobs]

    def obter(self, job_id):
        job = self._jobs.get(job_id)
        if not job:
            raise EditorError('Trabalho não encontrado (pode ter sido removido).')
        return job

    def criar(self, fonte: Path, nome, opcoes, copia, origem='upload', mapa=None, depois=None):
        """Novo trabalho. mapa: um .cortes.json para reabrir uma edição."""
        fonte = Path(fonte)
        if fonte.suffix.lower() not in EXT_VIDEO:
            raise EditorError(f'Formato de vídeo não suportado: {fonte.suffix or "sem extensão"}.')
        job = {
            'id': uuid.uuid4().hex[:12], 'criado': time.time(), 'nome': nome or fonte.name,
            'fonte': str(fonte), 'copia': bool(copia), 'origem': origem, 'opcoes': self.opcoes(opcoes),
            'estado': 'fila', 'etapa': 'Na fila', 'progresso': 0, 'erro': None,
            'palavras': [], 'mantidas': [], 'retomadas': [], 'rostos': None, 'saidas': [],
            'depois': depois,
        }
        if mapa:
            self._aplicar_mapa(job, mapa)
        if copia:
            # Vídeo enviado pelo navegador: a cópia mora na pasta do trabalho
            # e some junto com ele.
            pasta = self.dir / job['id']
            pasta.mkdir(parents=True, exist_ok=True)
            alvo = pasta / ('fonte' + fonte.suffix.lower())
            shutil.move(str(fonte), str(alvo))
            job['fonte'] = str(alvo)
        with self._lock:
            self._jobs[job['id']] = job
            self._salvar(job)
        if mapa:
            self.fila.adicionar(('analisar', job['id']), f'vídeo {job["nome"]}', self._reabrir, job)
        else:
            self.fila.adicionar(('analisar', job['id']), f'vídeo {job["nome"]}', self._analisar, job)
        return self.resumo(job)

    def _aplicar_mapa(self, job, mapa):
        if not isinstance(mapa, dict) or mapa.get('verto') != 'editor' or not isinstance(mapa.get('palavras'), list):
            raise EditorError('Esse arquivo não é um .cortes.json do editor do Verto.')
        job['palavras'] = [{'w': str(w.get('w', '')), 'ini': float(w['ini']), 'fim': float(w['fim']),
                            'p': float(w.get('p', 1)), 'removida': w.get('removida')} for w in mapa['palavras']]
        job['mantidas'] = [str(k) for k in mapa.get('mantidas') or []]
        job['retomadas'] = mapa.get('retomadas') or []
        job['opcoes'] = self.opcoes({**job['opcoes'], **(mapa.get('opcoes') or {}), 'revisar': True})
        job['duracao_mapa'] = mapa.get('duracao')

    def tentar_de_novo(self, job_id):
        job = self.obter(job_id)
        if job['estado'] != 'erro':
            raise EditorError('Esse trabalho não falhou.')
        job['erro'] = None
        analisado = bool(job.get('info')) and job.get('analisado')
        self._estado(job, 'fila', 'Na fila', 0)
        if analisado:
            self.fila.adicionar(('render', job['id']), f'render {job["nome"]}', self._exportar, job)
        else:
            self.fila.adicionar(('analisar', job['id']), f'vídeo {job["nome"]}', self._analisar, job)
        return self.resumo(job)

    def remover(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if job['estado'] in ('analisando', 'renderizando'):
                raise EditorError('Espere terminar a etapa atual antes de remover.')
            self._jobs.pop(job_id, None)
        shutil.rmtree(self.dir / job_id, ignore_errors=True)

    # ----------------------------------------------------------- análise ---

    def _falhar(self, job, e):
        job['erro'] = str(e)
        self._estado(job, 'erro', 'Falhou')
        self.registro.erro(f'Editor: {job["nome"]} falhou', [str(e)], automacao='editor')

    def _analisar(self, job):
        pasta = self.dir / job['id']
        o = job['opcoes']
        try:
            fonte = Path(job['fonte'])
            if not fonte.exists():
                raise EditorError('O vídeo não está mais no lugar.')
            self._estado(job, 'analisando', 'Lendo o vídeo', 0.02)
            info = analise.sondar(fonte)
            job['info'] = info
            palavras, silencios = [], []
            if info['tem_audio']:
                self._estado(job, etapa='Extraindo o áudio', progresso=0.05)
                wav = pasta / 'audio16k.wav'
                audio = analise.extrair_audio(fonte, wav)
                if o['isolar_voz']:
                    self._estado(job, etapa='Separando a voz (Demucs)', progresso=0.08)
                    wav = analise.isolar_voz(wav, pasta)
                    audio = analise.ler_wav(wav)
                self._estado(job, etapa='Achando as pausas', progresso=0.12)
                silencios, _ = analise.silencios(wav, audio)
                self._estado(job, etapa=f'Transcrevendo ({transcricao.MODELOS[o["modelo"]]})', progresso=0.15)
                palavras = transcricao.transcrever(
                    audio, o['modelo'], o['idioma'],
                    progresso=lambda p: self._estado(job, progresso=0.15 + 0.6 * p, salvar=False))
                palavras = cortes.ajustar_ao_silencio(palavras, silencios)
            job['palavras'] = palavras
            job['retomadas'] = []
            if o['retomadas'] and palavras:
                job['retomadas'] = [{'ini': palavras[a]['ini'], 'fim': palavras[b]['fim'], 'texto': t, 'refeita': r}
                                    for a, b, t, r in cortes.detectar_retomadas(palavras)]
            if o['enquadramento'] == 'rosto':
                self._rostos(job, 0.75, 0.2)
            job['analisado'] = True
            self._atualizar_mapa(job)
            if not palavras:
                self.registro.info(f'Editor: {job["nome"]} sem fala reconhecida',
                                   ['Nada para cortar: o vídeo sai inteiro, só no formato e com o áudio tratado.'],
                                   automacao='editor')
            if o['revisar']:
                self._estado(job, 'revisao', 'Pronto para revisar', 1)
            else:
                self._estado(job, 'fila', 'Na fila para exportar', 0)
                self.fila.adicionar(('render', job['id']), f'render {job["nome"]}', self._exportar, job)
        except Exception as e:
            self._falhar(job, e)

    def _reabrir(self, job):
        try:
            self._estado(job, 'analisando', 'Lendo o vídeo', 0.1)
            info = analise.sondar(Path(job['fonte']))
            if job.get('duracao_mapa') and abs(info['duracao'] - float(job['duracao_mapa'])) > 0.5:
                raise EditorError('O vídeo enviado não é o mesmo do .cortes.json (a duração não bate).')
            job['info'] = info
            if job['opcoes']['enquadramento'] == 'rosto':
                self._rostos(job, 0.2, 0.75)
            job['analisado'] = True
            self._atualizar_mapa(job)
            self._estado(job, 'revisao', 'Pronto para revisar', 1)
        except Exception as e:
            self._falhar(job, e)

    def _rostos(self, job, base, peso):
        self._estado(job, etapa='Procurando o rosto', progresso=base)
        job['rostos'] = [list(map(float, r)) for r in enquadramento.detectar_rostos(
            Path(job['fonte']), job['info'], progresso=lambda p: self._estado(job, progresso=base + peso * p, salvar=False))]

    # ----------------------------------------------------------- revisão ---

    def _parametros(self, o):
        i = PRESETS['intensidades'][o['intensidade']]
        return i['pausa'], i['folga'], i['zoom']

    def calcular(self, job, palavras=None, mantidas=None, opcoes=None):
        """Mapa de cortes sem salvar (a tela usa para a prévia)."""
        o = self.opcoes(opcoes or job['opcoes'])
        pausa, folga, _ = self._parametros(o)
        info = job['info']
        palavras = job['palavras'] if palavras is None else palavras
        trechos, cs = cortes.calcular(palavras, pausa, folga, info['duracao'],
                                      job['mantidas'] if mantidas is None else mantidas)
        trechos = cortes.alinhar_aos_quadros(trechos, info['fps'])
        return {'trechos': trechos, 'cortes': cs, 'duracao_final': round(cortes.duracao_final(trechos), 2)}

    def _atualizar_mapa(self, job):
        r = self.calcular(job)
        job['trechos'], job['cortes'], job['duracao_final'] = r['trechos'], r['cortes'], r['duracao_final']

    def detalhes(self, job_id):
        job = self.obter(job_id)
        out = self.resumo(job)
        out.update({k: job.get(k) for k in ('palavras', 'mantidas', 'retomadas', 'trechos', 'cortes', 'info')})
        out['tem_rostos'] = job.get('rostos') is not None
        return out

    def revisar(self, job_id, dados):
        """Aplica o que foi mudado na tela: texto das palavras, palavras
        removidas, pausas mantidas e opções. Devolve o mapa recalculado."""
        job = self.obter(job_id)
        if not job.get('analisado'):
            raise EditorError('A análise ainda não terminou.')
        with self._lock:
            palavras = copy.deepcopy(job['palavras'])
            for ed in dados.get('palavras') or []:
                i = ed.get('i')
                if not isinstance(i, int) or not 0 <= i < len(palavras):
                    continue
                if isinstance(ed.get('w'), str) and ed['w'].strip():
                    palavras[i]['w'] = ed['w'].strip()[:60]
                if 'removida' in ed:
                    palavras[i]['removida'] = ed['removida'] if ed['removida'] in ('manual', 'retomada') else None
            mantidas = [str(k) for k in dados.get('mantidas', job['mantidas'])]
            opcoes = self.opcoes({**job['opcoes'], **(dados.get('opcoes') or {})})
            if dados.get('salvar', True):
                job['palavras'], job['mantidas'], job['opcoes'] = palavras, mantidas, opcoes
                self._atualizar_mapa(job)
                self._salvar(job)
                return {'trechos': job['trechos'], 'cortes': job['cortes'], 'duracao_final': job['duracao_final']}
        return self.calcular(job, palavras, mantidas, opcoes)

    def exportar(self, job_id, dados=None):
        job = self.obter(job_id)
        if job['estado'] in ('fila', 'analisando', 'renderizando'):
            raise EditorError('Esse trabalho já está em andamento.')
        if dados:
            self.revisar(job_id, {**dados, 'salvar': True})
        self._estado(job, 'fila', 'Na fila para exportar', 0)
        self.fila.adicionar(('render', job['id']), f'render {job["nome"]}', self._exportar, job)
        return self.resumo(job)

    # ------------------------------------------------------------ render ---

    def _exportar(self, job):
        pasta = self.dir / job['id']
        o = job['opcoes']
        info = job['info']
        try:
            fonte = Path(job['fonte'])
            if not fonte.exists():
                raise EditorError('O vídeo original não está mais no lugar.')
            self._estado(job, 'renderizando', 'Montando os cortes', 0.01)
            self._atualizar_mapa(job)
            trechos = job['trechos']
            if not trechos:
                raise EditorError('Todos os trechos foram removidos: não sobrou nada para exportar.')
            W, H, rotulo = enquadramento.tamanho_saida(o['formato'], o['largura'], o['altura'])
            _, _, zoom = self._parametros(o)
            if o['enquadramento'] == 'rosto' and job.get('rostos') is None:
                self._rostos(job, 0.02, 0.1)
            rostos = [tuple(r) for r in job.get('rostos') or []]
            cw, ch, planos = enquadramento.planos(trechos, rostos, info, W, H, o['enquadramento'])

            total = cortes.duracao_final(trechos)
            finais = [{'w': w['w'], 'ini': cortes.tempo_no_video_final(w['ini'], trechos),
                       'fim': cortes.tempo_no_video_final(w['fim'], trechos)}
                      for w in job['palavras'] if not w.get('removida')]
            finais = [w for w in finais if w['fim'] > w['ini']]
            ass = legendas.gerar_ass(finais, W, H, o['legenda'], total) if o['legenda'] != 'nenhuma' and finais else None

            medida = None
            if info['tem_audio']:
                self._estado(job, etapa='Cortando o áudio', progresso=0.05)
                render.cortar_audio(fonte, trechos, pasta / 'audio_cortado.wav', info['duracao'])
                if o['tratar_audio']:
                    self._estado(job, etapa='Medindo o volume (-14 LUFS)', progresso=0.1)
                    medida = render.medir_volume(pasta / 'audio_cortado.wav')

            destino = pastas.downloads()
            destino.mkdir(parents=True, exist_ok=True)
            base = Path(job['nome']).stem
            mp4 = _nome_unico(destino, f'{base} ({rotulo})', '.mp4')
            self._estado(job, etapa=f'Renderizando {rotulo}', progresso=0.12)
            render.renderizar(fonte, mp4, pasta, info, trechos, W, H, o['enquadramento'], cw, ch, planos, zoom,
                              ass, medida, o['tratar_audio'], info['tem_audio'],
                              progresso=lambda p: self._estado(job, progresso=0.12 + 0.86 * p, salvar=False))
            srt = mp4.with_suffix('.srt')
            if finais:
                srt.write_text(legendas.gerar_srt(finais, total), encoding='utf-8')
            mapa = mp4.with_name(mp4.stem + '.cortes.json')
            mapa.write_text(json.dumps(self._mapa_para_arquivo(job), ensure_ascii=False, indent=1), encoding='utf-8')
            (pasta / 'audio_cortado.wav').unlink(missing_ok=True)

            saida = {'mp4': str(mp4), 'srt': str(srt) if finais else None, 'mapa': str(mapa),
                     'formato': rotulo, 'quando': time.time()}
            job['saidas'] = (job.get('saidas') or []) + [saida]
            self._estado(job, 'pronto', 'Pronto', 1)
            antes, depois = info['duracao'], total
            n_cortes = len([c for c in job['cortes'] if c['motivo'] in ('pausa', 'retomada', 'manual')])
            self.registro.ok(
                f'Vídeo exportado: {mp4.name} em {_mmss(depois)}',
                [f'{_mmss(antes)} → {_mmss(depois)} ({n_cortes} cortes, {len(job.get("retomadas") or [])} retomada(s))',
                 f'Salvo em {destino}' + (' com a legenda .srt e o .cortes.json' if finais else ' com o .cortes.json')],
                automacao='editor')
            if job.get('depois'):
                # Vídeo da pasta de entrada: sai de lá para não ser processado de novo.
                job['fonte'] = str(_mover_processado(Path(job['fonte']), job['depois']))
                job['depois'] = None
                self._salvar(job)
        except Exception as e:
            self._falhar(job, e)

    def _mapa_para_arquivo(self, job):
        return {
            'verto': 'editor', 'versao': VERSAO_MAPA, 'fonte': job['nome'],
            'duracao': job['info']['duracao'], 'fps': job['info']['fps'], 'opcoes': job['opcoes'],
            'palavras': job['palavras'], 'mantidas': job['mantidas'], 'retomadas': job.get('retomadas') or [],
            'trechos': job['trechos'], 'cortes': job['cortes'],
        }

    # --------------------------------------------------- pasta de entrada ---

    def processar_pasta(self, entrada: Path, opcoes):
        """Cada vídeo da pasta vira um trabalho automático (sem revisão). O
        original vai para Processados/ depois de exportado."""
        if not entrada.is_dir():
            entrada.mkdir(parents=True, exist_ok=True)
            return 0
        em_andamento = {j['fonte'] for j in self._jobs.values() if j['estado'] in ('fila', 'analisando', 'renderizando')}
        n = 0
        for arq in sorted(entrada.iterdir()):
            if arq.is_file() and arq.suffix.lower() in EXT_VIDEO and str(arq) not in em_andamento \
                    and not arq.name.startswith('.') and not arq.name.endswith(('.part', '.crdownload')):
                self.criar(arq, arq.name, {**opcoes, 'revisar': False}, copia=False, origem='pasta',
                           depois=str(entrada / 'Processados'))
                n += 1
        return n


def _nome_unico(pasta, base, ext):
    alvo, n = pasta / f'{base}{ext}', 2
    while alvo.exists():
        alvo = pasta / f'{base} ({n}){ext}'
        n += 1
    return alvo


def _mover_processado(fonte: Path, pasta):
    try:
        destino = Path(pasta)
        destino.mkdir(parents=True, exist_ok=True)
        alvo = _nome_unico(destino, fonte.stem, fonte.suffix)
        shutil.move(str(fonte), str(alvo))
        return alvo
    except OSError:
        return fonte


def _mmss(s):
    s = int(round(s or 0))
    return f'{s // 60}:{s % 60:02d}'
