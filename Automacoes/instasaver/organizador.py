"""Organizador do InstaSaver: tira de Downloads o que o InstaSaver/VscoSaver
baixou e guarda em Documentos/Instagram/<Perfil>/<Stories|Destaques|...>.

Regras:
- Só mexe no que é reconhecidamente do InstaSaver/VscoSaver (nome no padrão
  usuario_tipo_data_hora_id, ou ZIP com esse conteúdo). O resto de Downloads
  nunca é tocado.
- O nome da pasta de cada @ vem de perfis.txt (no destino). @ novo ganha um
  nome limpo e uma linha nova no arquivo.
- Cada pasta de perfil tem um .verto_perfil com os @ dela: renomear a pasta
  pelo Explorer atualiza o perfis.txt, e mudar o nome no perfis.txt renomeia
  a pasta.
- Nada é sobrescrito: arquivo com o mesmo nome e o mesmo SHA-256 é cópia e é
  descartado; com conteúdo diferente vira "nome (2).ext".
- O ZIP só é apagado (para a lixeira, se possível) depois de conferir que todo
  arquivo dele chegou ao destino. Se algo falhar, ele fica intacto.
"""
import hashlib
import os
import shutil
import threading
import time
import zipfile
from collections import Counter, OrderedDict
from pathlib import Path

from . import nomes

PERFIS = 'perfis.txt'
MARCADOR = '.verto_perfil'
TMP_PREFIXO = '.verto_tmp_'
LIMITE_ZIP = 5 * 1024 ** 3
NIVEIS_ZIP = 2

CABECALHO = """# Organizador do InstaSaver (Verto)
# Cada linha: @perfil = Nome da pasta
# Mude o nome depois do "=" para renomear a pasta (vale na próxima organização).
# Vários @ podem apontar para a mesma pasta (ex.: o Instagram e o VSCO da mesma pessoa).
# Perfis novos entram sozinhos no fim do arquivo.
"""

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


class Resultado:
    """Contagem de uma tarefa, para o registro: "5 de @x → X/Stories"."""

    def __init__(self):
        self.destinos = Counter()   # (handle ou None, pasta relativa) -> quantos
        self.duplicados = 0
        self.erros = []

    def movido(self, handle, pasta_rel, novo):
        if novo:
            self.destinos[(handle, pasta_rel)] += 1
        else:
            self.duplicados += 1

    @property
    def total(self):
        return sum(self.destinos.values()) + self.duplicados

    def linhas(self):
        out = []
        for (handle, rel), n in sorted(self.destinos.items(), key=lambda kv: -kv[1]):
            quem = f'@{handle}' if handle else 'sem @'
            out.append(f"{n} {'arquivo' if n == 1 else 'arquivos'} de {quem} → {rel}")
        if self.duplicados:
            out.append(f"{self.duplicados} {'cópia idêntica descartada' if self.duplicados == 1 else 'cópias idênticas descartadas'}")
        return out + self.erros


class Organizador:
    def __init__(self, destino: Path, registro):
        self.destino = Path(destino)
        self.registro = registro
        self._lock = threading.RLock()   # perfis.txt e marcadores: worker x tela
        self._zips_vistos = {}

    # ------------------------------------------------------------ perfis.txt ---

    @property
    def arquivo_perfis(self):
        return self.destino / PERFIS

    def ler_perfis(self):
        perfis = OrderedDict()
        try:
            linhas = self.arquivo_perfis.read_text(encoding='utf-8').splitlines()
        except OSError:
            return perfis
        for linha in linhas:
            par = _ler_linha(linha)
            if par:
                perfis[par[0]] = par[1]
        return perfis

    def texto_perfis(self):
        try:
            return self.arquivo_perfis.read_text(encoding='utf-8')
        except OSError:
            return CABECALHO

    def salvar_texto_perfis(self, texto):
        with self._lock:
            self.destino.mkdir(parents=True, exist_ok=True)
            _gravar_atomico(self.arquivo_perfis, texto if texto.endswith('\n') else texto + '\n')
            return self.sincronizar()

    def _atualizar_perfis(self, mudancas):
        """Troca/acrescenta linhas "@h = Nome" sem mexer nas outras nem nos comentários."""
        if not mudancas:
            return
        with self._lock:
            restantes = dict(mudancas)
            linhas = self.texto_perfis().splitlines()
            for i, linha in enumerate(linhas):
                par = _ler_linha(linha)
                if par and par[0] in restantes:
                    linhas[i] = f'@{par[0]} = {restantes.pop(par[0])}'
            linhas += [f'@{h} = {n}' for h, n in restantes.items()]
            self.destino.mkdir(parents=True, exist_ok=True)
            _gravar_atomico(self.arquivo_perfis, '\n'.join(linhas) + '\n')

    # ------------------------------------------------------------ marcadores ---

    def _pastas_de_perfil(self):
        if not self.destino.is_dir():
            return []
        return [p for p in self.destino.iterdir()
                if p.is_dir() and not p.name.startswith(('.', '_')) and (p / MARCADOR).is_file()]

    def mapa(self):
        """@ -> pasta, lido dos marcadores (vale mesmo com a pasta renomeada)."""
        out = {}
        for pasta in self._pastas_de_perfil():
            for h in _ler_marcador(pasta)[0]:
                out[h] = pasta
        return out

    def sincronizar(self):
        """Acerta perfis.txt e pastas nos dois sentidos. Devolve as mudanças feitas."""
        with self._lock:
            perfis = self.ler_perfis()
            mudancas, feito = {}, []
            for pasta in self._pastas_de_perfil():
                handles, sinc = _ler_marcador(pasta)
                if not handles:
                    continue
                atual = pasta.name
                if sinc != atual:
                    # Renomeada pelo Explorer/gerenciador: a pasta manda.
                    for h in handles:
                        if perfis.get(h) != atual:
                            mudancas[h] = atual
                    _gravar_marcador(pasta, handles, atual)
                    feito.append(f'Pasta renomeada para "{atual}": perfis.txt atualizado')
                    continue
                for h in handles:
                    if h not in perfis:
                        mudancas[h] = atual
                pedidos = OrderedDict((h, perfis[h]) for h in handles if h in perfis)
                nomes_pedidos = set(pedidos.values())
                if not nomes_pedidos or nomes_pedidos == {atual}:
                    continue
                if atual in nomes_pedidos:
                    # Parte dos @ ganhou outro nome no perfis.txt: eles saem
                    # desta pasta e levam os arquivos deles para a pasta nova.
                    ficam = {h for h in handles if perfis.get(h, atual) == atual}
                    _gravar_marcador(pasta, ficam, atual)
                    feito += self._separar(pasta, handles - ficam, perfis)
                    continue
                alvo_pedido = next(iter(pedidos.values()))
                ficam = {h for h in handles if perfis.get(h, alvo_pedido) == alvo_pedido}
                nova = self._renomear_pasta(pasta, alvo_pedido, ficam)
                if nova.name != alvo_pedido:
                    for h in ficam:
                        mudancas[h] = nova.name
                feito.append(f'"{atual}" → "{nova.name}" (pedido no perfis.txt)')
                feito += self._separar(nova, handles - ficam, perfis)
            self._atualizar_perfis(mudancas)
            if feito:
                self.registro.info('Pastas e perfis.txt sincronizados', feito)
            return feito

    def _separar(self, pasta, saem, perfis):
        if not saem:
            return []
        mapa, movidos = {}, Counter()
        for arq in sorted(a for a in pasta.rglob('*') if a.is_file()):
            info = nomes.ler_arquivo(arq.name)
            if info and info['user'] in saem:
                nova = self.pasta_do_perfil(info['user'], mapa, perfis)
                mover(arq, nova / arq.parent.relative_to(pasta))
                movidos[info['user']] += 1
        _apagar_vazias(pasta)
        return [f'@{h} saiu de "{pasta.name}" e levou {movidos[h]} arquivo(s) para "{perfis.get(h)}"'
                for h in sorted(saem)]

    def _renomear_pasta(self, pasta, nome_pedido, handles):
        nome = nomes.limpar_nome(nome_pedido) or pasta.name
        alvo = self.destino / nome
        if alvo == pasta:
            return pasta
        if not alvo.exists() or _mesma_pasta(alvo, pasta):
            pasta.rename(alvo)
        else:
            # Já existe uma pasta com esse nome: junta as duas sem perder nada.
            for arq in sorted(pasta.rglob('*')):
                if arq.is_file() and arq.name != MARCADOR:
                    rel = arq.parent.relative_to(pasta)
                    mover(arq, alvo / rel)
            handles = set(handles) | _ler_marcador(alvo)[0]
            _apagar_vazias(pasta, incluir_raiz=True, ignorar=(MARCADOR,))
        _gravar_marcador(alvo, handles, alvo.name)
        return alvo

    def pasta_do_perfil(self, handle, mapa, perfis):
        """Pasta do @ (cria se preciso), já marcada e registrada no perfis.txt."""
        if handle in mapa and mapa[handle].is_dir():
            return mapa[handle]
        pedido = perfis.get(handle)
        nome = nomes.limpar_nome(pedido) if pedido else ''
        explicito = bool(nome)
        nome = nome or nomes.nome_da_pasta(handle)
        pasta = self.destino / nome
        dono = _ler_marcador(pasta)[0] if pasta.is_dir() else set()
        if dono and handle not in dono and not explicito:
            # Nome automático igual ao de outro perfil (ex.: @gbm.clicks e @gbm_clicks).
            pasta = self.destino / nomes.limpar_nome(f'{nome} ({handle})')
            dono = _ler_marcador(pasta)[0] if pasta.is_dir() else set()
        pasta.mkdir(parents=True, exist_ok=True)
        _gravar_marcador(pasta, dono | {handle}, pasta.name)
        mapa[handle] = pasta
        if perfis.get(handle) != pasta.name:
            perfis[handle] = pasta.name
            self._atualizar_perfis({handle: pasta.name})
        return pasta

    def _rel(self, pasta):
        try:
            return str(pasta.relative_to(self.destino))
        except ValueError:
            return str(pasta)

    # ------------------------------------------------------- reconhecimento ---

    def eh_candidato(self, caminho: Path):
        """O vigia só entrega o que este filtro aceita."""
        if caminho.suffix.lower() != '.zip':
            return nomes.ler_arquivo(caminho.name) is not None
        # Abrir cada ZIP de Downloads a cada varredura seria desperdício: guarda
        # a resposta até o arquivo mudar.
        try:
            st = caminho.stat()
        except OSError:
            return False
        chave = (str(caminho), st.st_size, st.st_mtime)
        if chave not in self._zips_vistos:
            if len(self._zips_vistos) > 500:
                self._zips_vistos.clear()
            self._zips_vistos[chave] = eh_zip_reconhecido(caminho)
        return self._zips_vistos[chave]

    def pastas_para_importar(self, entrada: Path):
        """Pastas já separadas à mão em Downloads (ex.: "andre_bronca_", "Fiote"):
        a maioria dos arquivos precisa ser do InstaSaver/VscoSaver."""
        out = []
        if not entrada.is_dir():
            return out
        for pasta in sorted(entrada.iterdir(), key=lambda p: p.name.lower()):
            if not pasta.is_dir() or pasta.name.startswith('.') or _mesma_pasta(pasta, self.destino) \
                    or _dentro(self.destino, pasta):
                continue
            arquivos = [a for a in pasta.rglob('*') if a.is_file()]
            infos = [nomes.ler_arquivo(a.name) for a in arquivos]
            reconhecidos = [i for i in infos if i]
            if not reconhecidos or len(reconhecidos) * 2 < len(arquivos):
                continue
            contagem = Counter(i['user'] for i in reconhecidos)
            # O dono é o @ que dá nome à pasta (em "m.d_amaral_" o VSCO da
            # pessoa pode ter mais arquivos); sem nenhum, o mais frequente.
            pelo_nome = [h for h, _ in contagem.most_common() if nomes.mesmo_perfil(pasta.name, h)]
            dono = (pelo_nome or [contagem.most_common(1)[0][0]])[0]
            out.append({
                'pasta': pasta, 'dono': dono, 'outros': [h for h in contagem if h != dono],
                'arquivos': len(arquivos), 'sem_arroba': len(arquivos) - len(reconhecidos),
                'nome_proprio': not pelo_nome,
            })
        return out

    # -------------------------------------------------------------- tarefas ---

    def organizar_arquivos(self, caminhos):
        """Arquivos soltos (uma tarefa só para um lote, um registro só)."""
        with self._lock:
            self.sincronizar()
            perfis, mapa, res = self.ler_perfis(), self.mapa(), Resultado()
            for caminho in caminhos:
                caminho = Path(caminho)
                info = nomes.ler_arquivo(caminho.name)
                if not info or not caminho.is_file():
                    continue
                try:
                    pasta = self.pasta_do_perfil(info['user'], mapa, perfis) / nomes.TIPOS[info['tipo']]
                    _, novo = mover(caminho, pasta, nomes.sem_sufixo_duplicado(caminho.name))
                    res.movido(info['user'], self._rel(pasta), novo)
                except OSError as e:
                    res.erros.append(f'{caminho.name}: {e}')
        if res.total or res.erros:
            titulo = f"{res.total} {'arquivo organizado' if res.total == 1 else 'arquivos organizados'}"
            (self.registro.erro if res.erros else self.registro.ok)(titulo, res.linhas())
        return res

    def organizar_zip(self, caminho):
        caminho = Path(caminho)
        if not caminho.is_file():
            return None
        info_zip = nomes.ler_zip(caminho.name)
        with self._lock:
            self.sincronizar()
            perfis, mapa, res = self.ler_perfis(), self.mapa(), Resultado()
            self.destino.mkdir(parents=True, exist_ok=True)
            tmp = self.destino / f'{TMP_PREFIXO}{int(time.time() * 1000)}'
            try:
                tmp.mkdir()
                itens, esperados = extrair_seguro(caminho, tmp)
                tratados = 0
                for extraido, original in itens:
                    info = nomes.ler_arquivo(extraido.name)
                    handle = info['user'] if info else None
                    if not handle:
                        handle = next((nomes.handle_de_pasta(p) for p in Path(original).parts[:-1]
                                       if nomes.handle_de_pasta(p)), None)
                    if not handle and info_zip:
                        handle = info_zip['user']
                    if info_zip and info_zip['tipo'] == 'colecao':
                        handle = info_zip['user']   # na coleção, o nome é do autor original
                    tipo = info['tipo'] if info else None
                    if handle:
                        pasta = self.pasta_do_perfil(handle, mapa, perfis) / nomes.TIPOS.get(tipo, nomes.SEM_TIPO)
                        if info_zip and info_zip['titulo'] and tipo == info_zip['tipo']:
                            pasta = pasta / (nomes.limpar_nome(info_zip['titulo']) or '')
                    else:
                        pasta = self.destino / nomes.REVISAR / (nomes.limpar_nome(caminho.stem) or 'zip')
                    nome = nomes.sem_sufixo_duplicado(extraido.name) if info else extraido.name
                    _, novo = mover(extraido, pasta, nome)
                    res.movido(handle, self._rel(pasta), novo)
                    tratados += 1
                if tratados != esperados:
                    raise RuntimeError(f'só {tratados} de {esperados} arquivos chegaram ao destino')
                apagado = _apagar(caminho)
            except Exception as e:
                self.registro.erro(f'ZIP {caminho.name} não foi organizado: {e}',
                                   res.linhas() + ['O ZIP ficou intacto em ' + str(caminho.parent)])
                return res
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        self.registro.ok(f'ZIP {caminho.name}: {res.total} {"arquivo" if res.total == 1 else "arquivos"}',
                         res.linhas() + [apagado])
        return res

    def importar_pasta(self, item):
        """Move uma pasta já separada à mão, respeitando o que a pessoa fez:
        nome próprio da pasta vira o nome do perfil, subpastas criadas por ela
        (ex.: "niver dela <3") continuam como subpastas, e @ de outra rede
        guardados junto (ex.: o VSCO da mesma pessoa) apontam para a mesma pasta."""
        pasta, dono = Path(item['pasta']), item['dono']
        with self._lock:
            self.sincronizar()
            perfis, mapa, res = self.ler_perfis(), self.mapa(), Resultado()
            if item['nome_proprio'] and dono not in perfis and dono not in mapa:
                perfis[dono] = nomes.limpar_nome(pasta.name) or nomes.nome_da_pasta(dono)
                self._atualizar_perfis({dono: perfis[dono]})
            pasta_dono = self.pasta_do_perfil(dono, mapa, perfis)
            juntos = {h: pasta_dono.name for h in item['outros'] if h not in perfis and h not in mapa}
            perfis.update(juntos)
            self._atualizar_perfis(juntos)
            for arq in sorted(a for a in pasta.rglob('*') if a.is_file()):
                info = nomes.ler_arquivo(arq.name)
                handle = info['user'] if info else dono
                tipo = info['tipo'] if info else None
                subpastas = []
                for parte in arq.parent.relative_to(pasta).parts:
                    z = nomes.ler_zip(parte + '.zip')
                    if z:
                        if z['titulo']:
                            subpastas.append(z['titulo'])
                    elif not any(nomes.mesmo_perfil(parte, h) for h in (dono, *item['outros'])):
                        subpastas.append(parte)
                try:
                    destino = self.pasta_do_perfil(handle, mapa, perfis) / nomes.TIPOS.get(tipo, nomes.SEM_TIPO)
                    for s in subpastas:
                        destino = destino / (nomes.limpar_nome(s) or '_')
                    _, novo = mover(arq, destino, nomes.sem_sufixo_duplicado(arq.name) if info else arq.name)
                    res.movido(handle if info else None, self._rel(destino), novo)
                except OSError as e:
                    res.erros.append(f'{arq.name}: {e}')
            _apagar_vazias(pasta, incluir_raiz=True)
        sobrou = ' (alguns arquivos ficaram na pasta original)' if pasta.exists() else ''
        (self.registro.erro if res.erros else self.registro.ok)(
            f'Pasta "{pasta.name}" importada: {res.total} arquivos{sobrou}', res.linhas())
        return res

    def limpar_temporarios(self):
        if self.destino.is_dir():
            for p in self.destino.glob(TMP_PREFIXO + '*'):
                shutil.rmtree(p, ignore_errors=True)


# ----------------------------------------------------------------- ZIP ---

def eh_zip_reconhecido(caminho: Path):
    """ZIP com nome do InstaSaver/VscoSaver, ou cujo conteúdo é todo deles
    (o ZIP de um carrossel se chama usuario_<código>.zip). ZIPs de outras
    coisas em Downloads nunca entram."""
    if nomes.ler_zip(caminho.name):
        return True
    try:
        with zipfile.ZipFile(caminho) as z:
            membros = [Path(i.filename).name for i in z.infolist() if not i.is_dir()]
    except (OSError, zipfile.BadZipFile):
        return False
    membros = [m for m in membros if m and not m.startswith('.')]
    return bool(membros) and all(nomes.ler_arquivo(m) for m in membros)


def extrair_seguro(zip_path, destino: Path, limite=LIMITE_ZIP, nivel=1):
    """Extrai achatando as pastas internas (um arquivo por item, sem caminho,
    o que também bloqueia ../ e caminhos absolutos). Confere a integridade,
    limita o tamanho total e abre ZIPs dentro de ZIPs até 2 níveis.
    Devolve ([(arquivo extraído, caminho original no ZIP)], quantos arquivos
    o ZIP tinha, contando os de dentro dos ZIPs internos)."""
    with zipfile.ZipFile(zip_path) as z:
        ruim = z.testzip()
        if ruim is not None:
            raise ValueError(f'ZIP corrompido (falhou em {ruim})')
        membros = [i for i in z.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in membros)
        if total > limite:
            raise ValueError(f'ZIP grande demais ({total / 1024 ** 3:.1f} GB)')
        livre = shutil.disk_usage(destino).free
        if total > livre * 0.9:
            raise ValueError(f'Espaço em disco insuficiente para extrair ({total / 1024 ** 2:.0f} MB)')
        # Ocultos e restos do macOS (__MACOSX/._foto.jpg) não são conteúdo.
        validos = [i for i in membros if '__MACOSX' not in i.filename
                   and not Path(i.filename.replace('\\', '/')).name.startswith('.')]
        saida, esperados = [], len(validos)
        for info in validos:
            nome = Path(info.filename.replace('\\', '/')).name
            alvo, n = destino / nome, 2
            while alvo.exists():
                alvo = destino / f'{Path(nome).stem} ({n}){Path(nome).suffix}'
                n += 1
            with z.open(info) as src, open(alvo, 'wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            if alvo.suffix.lower() == '.zip' and nivel < NIVEIS_ZIP and zipfile.is_zipfile(alvo):
                interno = destino / f'{alvo.stem}_zip{n}'
                interno.mkdir()
                itens, qtd = extrair_seguro(alvo, interno, limite - total, nivel + 1)
                alvo.unlink()
                saida += [(a, f'{info.filename}/{o}') for a, o in itens]
                esperados += qtd - 1   # o ZIP interno vira o conteúdo dele
                continue
            saida.append((alvo, info.filename))
    return saida, esperados


# ------------------------------------------------------------- arquivos ---

def mover(origem: Path, pasta: Path, nome=None):
    """Move sem sobrescrever. Devolve (caminho final, True se era novo).
    Mesmo nome e mesmo conteúdo = cópia: o de origem é descartado."""
    pasta.mkdir(parents=True, exist_ok=True)
    nome = nome or origem.name
    stem, ext = os.path.splitext(nome)
    alvo, n = pasta / nome, 2
    while alvo.exists():
        if alvo.is_file() and _iguais(origem, alvo):
            origem.unlink()
            return alvo, False
        alvo = pasta / f'{stem} ({n}){ext}'
        n += 1
    shutil.move(str(origem), str(alvo))
    return alvo, True


def _iguais(a: Path, b: Path):
    if a.stat().st_size != b.stat().st_size:
        return False
    return _sha256(a) == _sha256(b)


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloco)
    return h.hexdigest()


def _apagar(caminho: Path):
    if send2trash:
        try:
            send2trash(str(caminho))
            return 'ZIP enviado para a lixeira'
        except Exception:
            pass
    caminho.unlink()
    return 'ZIP apagado'


def _apagar_vazias(raiz: Path, incluir_raiz=False, ignorar=()):
    for pasta in sorted((p for p in raiz.rglob('*') if p.is_dir()), key=lambda p: -len(p.parts)):
        _rmdir_se_vazia(pasta, ignorar)
    if incluir_raiz:
        _rmdir_se_vazia(raiz, ignorar)


def _rmdir_se_vazia(pasta, ignorar):
    try:
        for resto in pasta.iterdir():
            if resto.name not in ignorar:
                return
            resto.unlink()
        pasta.rmdir()
    except OSError:
        pass


def _mesma_pasta(a: Path, b: Path):
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def _dentro(filho: Path, pai: Path):
    try:
        filho.resolve().relative_to(pai.resolve())
        return True
    except ValueError:
        return False


def _gravar_atomico(caminho: Path, texto):
    tmp = caminho.with_name(caminho.name + '.tmp')
    tmp.write_text(texto, encoding='utf-8')
    os.replace(tmp, caminho)


def _ler_linha(linha):
    """'@perfil = Nome' -> ('perfil', 'Nome'). Comentário e linha vazia -> None."""
    linha = linha.split('←')[0].strip()
    if not linha or linha.startswith('#') or '=' not in linha:
        return None
    handle, nome = (s.strip() for s in linha.split('=', 1))
    m = nomes.RE_HANDLE.fullmatch(handle)
    if not m or not nome:
        return None
    return m.group(1).lower(), nome


def _ler_marcador(pasta: Path):
    """.verto_perfil -> ({@ da pasta}, nome que a pasta tinha na última sincronização)."""
    handles, nome = set(), None
    try:
        linhas = (pasta / MARCADOR).read_text(encoding='utf-8').splitlines()
    except OSError:
        return handles, nome
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith('@'):
            handles.add(linha[1:].lower())
        elif linha.startswith('nome ='):
            nome = linha.split('=', 1)[1].strip()
    return handles, nome


def _gravar_marcador(pasta: Path, handles, nome):
    texto = ('# Criado pelo Verto (Automações > Organizador do InstaSaver). Não apague:\n'
             '# é por ele que o app reconhece este perfil mesmo com a pasta renomeada.\n'
             + ''.join(f'@{h}\n' for h in sorted(handles)) + f'nome = {nome}\n')
    caminho = pasta / MARCADOR
    try:
        if caminho.read_text(encoding='utf-8') == texto:
            return
    except OSError:
        pass
    if os.name == 'nt' and caminho.exists():
        _ocultar(caminho, False)   # o Windows não deixa gravar por cima de arquivo oculto
    caminho.write_text(texto, encoding='utf-8')
    if os.name == 'nt':
        _ocultar(caminho, True)


def _ocultar(caminho, ocultar):
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(caminho), 0x2 if ocultar else 0x80)
    except Exception:
        pass
