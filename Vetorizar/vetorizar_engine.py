"""Vetorizar 4K · motor do app: projetos, modo automático, fundo por IA e exportação.

Cada imagem enviada vira um projeto em Vetorizar/dados/<id>/ (fora do git):
original, meta.json (análise, opções, paleta, números) e resultado.svg.
O traçado roda aqui mesmo, um por vez (trava), e leva de frações de segundo
a poucos segundos; a remoção de fundo por IA (rembg) roda num processo à
parte com teto de memória, como a fila de IA do Vetor3D, e fica guardada.

Exporta: SVG, PDF e AI (PDF vetorial, que o Illustrator abre), EPS e DXF
(escritos pelo Conversor), PNG e WebP em 4K, 8K ou tamanho livre (o vetor
renderizado), e a paleta (.gpl do GIMP/Inkscape e .txt).
"""
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import zipfile

import numpy as np
from PIL import Image

from Vetorizar import vz_nucleo as N
from Vetorizar.vz_nucleo import VetorizarError

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dados')
MAX_BYTES = 60 * 1024 * 1024
MAX_LADO_ENTRADA = 12000
MAX_LADO_SAIDA = 8192
TAMANHOS = {'4k': 3840, '4k-dci': 4096, '5k': 5120, '8k': 7680}
EXT_OK = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.heif', '.avif')
TETO_IA_MB = 1500

_trava = threading.Lock()


def _pasta(pid):
    if not re.fullmatch(r'[0-9a-f]{12}', pid or ''):
        raise VetorizarError('Projeto inválido.')
    p = os.path.join(DADOS, pid)
    if not os.path.isdir(p):
        raise VetorizarError('Projeto não encontrado (pode ter sido apagado).')
    return p


def _meta(pid):
    with open(os.path.join(_pasta(pid), 'meta.json'), encoding='utf-8') as f:
        return json.load(f)


def _salvar_meta(pid, meta):
    caminho = os.path.join(_pasta(pid), 'meta.json')
    with open(caminho + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.replace(caminho + '.tmp', caminho)


def _original(pid):
    pasta = _pasta(pid)
    for n in os.listdir(pasta):
        if n.startswith('original.'):
            return os.path.join(pasta, n)
    raise VetorizarError('O arquivo original sumiu.')


def _rgba(pid):
    return N.abrir(_original(pid))


def _publico(meta):
    r = meta.get('resultado') or {}
    return {'id': meta['id'], 'nome': meta['nome'], 'largura': meta['info']['largura'], 'altura': meta['info']['altura'],
            'info': meta['info'], 'opcoes': meta.get('opcoes') or {}, 'resultado': r, 'criado': meta.get('criado'),
            'versao': meta.get('versao', 0)}


# --------------------------------------------------------------- projetos ---

def enviar(arquivo):
    if arquivo is None or not arquivo.filename:
        raise VetorizarError('Escolha uma imagem.')
    nome = os.path.basename(arquivo.filename)
    ext = os.path.splitext(nome)[1].lower()
    if ext not in EXT_OK:
        raise VetorizarError('Formato não suportado. Use PNG, JPG, WebP, GIF, BMP, TIFF, HEIC ou AVIF.')
    dados = arquivo.read(MAX_BYTES + 1)
    if len(dados) > MAX_BYTES:
        raise VetorizarError('Imagem grande demais (máximo 60 MB).')
    if ext in ('.heic', '.heif'):
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            pass
    try:
        im = Image.open(io.BytesIO(dados))
        im.load()
    except Exception:
        raise VetorizarError('Não consegui abrir essa imagem.')
    if max(im.size) > MAX_LADO_ENTRADA:
        raise VetorizarError(f'Imagem grande demais ({im.size[0]}×{im.size[1]}). O máximo é {MAX_LADO_ENTRADA} px no lado maior.')
    pid = secrets.token_hex(6)
    pasta = os.path.join(DADOS, pid)
    os.makedirs(pasta)
    caminho = os.path.join(pasta, 'original' + ('.png' if ext in ('.heic', '.heif', '.avif') else ext))
    if ext in ('.heic', '.heif', '.avif'):
        im.save(caminho)
    else:
        with open(caminho, 'wb') as f:
            f.write(dados)
    rgba = N.abrir(caminho)
    info = N.analisar(rgba)
    meta = {'id': pid, 'nome': os.path.splitext(nome)[0][:120] or 'imagem', 'criado': time.strftime('%Y-%m-%d %H:%M'),
            'info': info, 'opcoes': N.normalizar({}), 'resultado': None, 'versao': 0}
    _salvar_meta(pid, meta)
    try:
        return processar(pid, {}, auto=True)
    except VetorizarError as e:
        meta['resultado'] = {'erro': str(e)}
        _salvar_meta(pid, meta)
        return _publico(meta)


def listar():
    if not os.path.isdir(DADOS):
        return []
    out = []
    for pid in os.listdir(DADOS):
        try:
            out.append(_publico(_meta(pid)))
        except (VetorizarError, OSError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda p: p.get('criado') or '', reverse=True)


def projeto(pid):
    return _publico(_meta(pid))


def remover(pid):
    shutil.rmtree(_pasta(pid), ignore_errors=True)
    return True


def renomear(pid, nome):
    meta = _meta(pid)
    meta['nome'] = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', str(nome or '')).strip()[:120] or meta['nome']
    _salvar_meta(pid, meta)
    return _publico(meta)


# --------------------------------------------------------------- fundo IA ---

def _prefixo(teto_mb):
    if sys.platform.startswith('linux') and shutil.which('systemd-run'):
        try:
            if subprocess.run(['systemd-run', '--user', '--scope', '-q', '-p', 'MemoryMax=64M', 'true'],
                              capture_output=True, timeout=10).returncode == 0:
                return ['systemd-run', '--user', '--scope', '-q', '-p', f'MemoryMax={teto_mb}M',
                        '-p', 'MemorySwapMax=0', '-p', 'CPUWeight=20', '--']
        except (OSError, subprocess.TimeoutExpired):
            pass
    return []


def mascara_ia(pid):
    """Máscara do objeto principal (rembg), feita uma vez e guardada."""
    pasta = _pasta(pid)
    saida = os.path.join(pasta, 'mascara_ia.png')
    if os.path.exists(saida):
        return np.asarray(Image.open(saida).convert('L'))
    try:
        import psutil
        if psutil.virtual_memory().available / 2**20 < 900:
            raise VetorizarError('Pouca memória livre agora para tirar o fundo com IA. Feche algumas abas e tente de novo.')
    except ImportError:
        pass
    env = os.environ.copy()
    env['PYTHONPATH'] = RAIZ + os.pathsep + env.get('PYTHONPATH', '')
    p = subprocess.run(_prefixo(TETO_IA_MB) + [sys.executable, '-m', 'Vetorizar.vetorizar_engine', 'mascara',
                                               _original(pid), saida],
                       cwd=RAIZ, env=env, capture_output=True, text=True, timeout=600)
    if p.returncode != 0 or not os.path.exists(saida):
        if p.returncode in (-9, 137):
            raise VetorizarError('Faltou memória para tirar o fundo com IA. Use "Tirar a cor do fundo".')
        if 'No module named' in (p.stderr or ''):
            raise VetorizarError('Falta o rembg para tirar o fundo com IA (rode o INSTALAR.py).')
        raise VetorizarError('A IA não conseguiu separar o fundo desta imagem.')
    return np.asarray(Image.open(saida).convert('L'))


def _worker_mascara(entrada, saida):
    from rembg import remove, new_session
    im = Image.open(entrada).convert('RGBA')
    m = remove(im, session=new_session('u2net'), only_mask=True)
    m.convert('L').save(saida)


# ------------------------------------------------------------- vetorizar ---

def _medir(rgba, info, op, mascara):
    t = time.time()
    r = N.vetorizar(rgba, info, op, mascara)
    h, w = rgba.shape[:2]
    svg = N.montar_svg(r['formas'], w, h)
    fid, de = N.fidelidade(rgba, svg, fundo=N.cor_papel(rgba) if r['tipo'] == 'traco' else None)
    return r, svg, fid, de, round(time.time() - t, 2)


def _candidatos(tipo, op):
    """Combinações que o modo automático testa para cada tipo."""
    base = dict(op)
    if tipo == 'pixel':
        return [dict(base, pixel_estilo='exato')]
    if tipo == 'traco':
        return [dict(base, suavidade=s, detalhe=d) for s, d in ((55, 50), (85, 50), (35, 60), (70, 75))]
    if tipo == 'foto':
        return [dict(base, foto_estilo=e, cores=c, suavidade=55, detalhe=d)
                for e, c, d in (('poster', 12, 50), ('poster', 20, 60), ('detalhado', 32, 70))]
    return [dict(base, suavidade=s, detalhe=d) for s, d in ((55, 50), (80, 50), (35, 55), (60, 75), (70, 30))]


def _nota(fid, nos):
    # fidelidade manda; entre resultados parecidos, menos nós (arquivo mais limpo)
    return fid - nos / 4000


def processar(pid, opcoes, auto=False):
    meta = _meta(pid)
    rgba = _rgba(pid)
    info = meta['info']
    op = N.normalizar(opcoes)
    mascara = mascara_ia(pid) if op['fundo'] == 'ia' else None
    tipo = info['tipo'] if op['tipo'] == 'auto' else op['tipo']
    with _trava:
        if auto:
            testes = []
            for cand in _candidatos(tipo, op):
                try:
                    r, svg, fid, de, seg = _medir(rgba, info, cand, mascara)
                except VetorizarError:
                    continue
                testes.append((_nota(fid, N.contar(r['formas'])['nos']), cand, r, svg, fid, de, seg))
            if not testes:
                raise VetorizarError('Nenhuma combinação deu certo com esta imagem. Tente outro tipo.')
            testes.sort(key=lambda t: -t[0])
            _, op, r, svg, fid, de, seg = testes[0]
            op = N.normalizar(op)
            seg = round(sum(t[6] for t in testes), 2)
            testados = len(testes)
        else:
            r, svg, fid, de, seg = _medir(rgba, info, op, mascara)
            testados = 1
    pasta = _pasta(pid)
    with open(os.path.join(pasta, 'resultado.svg'), 'w', encoding='utf-8') as f:
        f.write(svg)
    with open(os.path.join(pasta, 'formas.json'), 'w', encoding='utf-8') as f:
        json.dump(r['formas'], f)
    op_salvar = dict(op)
    op_salvar['travadas'] = [N.hexa(c) for c in op['travadas']]
    meta['opcoes'] = op_salvar
    meta['versao'] = meta.get('versao', 0) + 1
    meta['resultado'] = {
        'tipo': r['tipo'], 'paleta': r['paleta'], 'fidelidade': fid, 'erro_cor': de, 'segundos': seg,
        'testados': testados, 'bytes': len(svg.encode('utf-8')), 'fundo_removido': bool(r.get('fundo_removido')),
        'pixel': r.get('pixel'), **N.contar(r['formas']),
        'cores_saida': len({tuple(f['cor']) for f in r['formas']}),
    }
    _salvar_meta(pid, meta)
    return _publico(meta)


def svg(pid, contorno=False):
    pasta = _pasta(pid)
    if contorno:
        meta = _meta(pid)
        formas = _formas(pid)
        return N.montar_svg(formas, meta['info']['largura'], meta['info']['altura'], contorno=True)
    caminho = os.path.join(pasta, 'resultado.svg')
    if not os.path.exists(caminho):
        raise VetorizarError('Ainda não vetorizado.')
    with open(caminho, encoding='utf-8') as f:
        return f.read()


def _formas(pid):
    with open(os.path.join(_pasta(pid), 'formas.json'), encoding='utf-8') as f:
        formas = json.load(f)
    # JSON vira listas: volta para tuplas onde o Conversor espera
    for fm in formas:
        fm['cor'] = tuple(fm['cor'])
        if fm['regra'] == 'linha':
            fm['subs'] = [[tuple(p) for p in linha] for linha in fm['subs']]
        else:
            fm['subs'] = [[(c[0],) + tuple(tuple(p) for p in c[1:]) for c in sub] for sub in fm['subs']]
    return formas


# -------------------------------------------------------------- exportar ---

FORMATOS = {
    'svg': ('svg', 'image/svg+xml'), 'pdf': ('pdf', 'application/pdf'), 'ai': ('ai', 'application/postscript'),
    'eps': ('eps', 'application/postscript'), 'dxf': ('dxf', 'application/dxf'),
    'png': ('png', 'image/png'), 'webp': ('webp', 'image/webp'),
    'gpl': ('gpl', 'text/plain; charset=utf-8'), 'txt': ('txt', 'text/plain; charset=utf-8'),
}


def _lado(tamanho):
    if str(tamanho).lower() in TAMANHOS:
        return TAMANHOS[str(tamanho).lower()]
    try:
        v = int(tamanho)
    except (TypeError, ValueError):
        return TAMANHOS['4k']
    return max(64, min(MAX_LADO_SAIDA, v))


def _cor_fundo(valor):
    if not valor or valor == 'transparente':
        return None
    return N._hex_rgb(valor)


def exportar_bytes(pid, formato, tamanho='4k', fundo=None):
    """-> (bytes, nome, mime)"""
    if formato not in FORMATOS:
        raise VetorizarError('Formato desconhecido.')
    meta = _meta(pid)
    w, h = meta['info']['largura'], meta['info']['altura']
    ext, mime = FORMATOS[formato]
    base = re.sub(r'[\\/:*?"<>|]', '', meta['nome']).strip() or 'vetor'
    formas = _formas(pid)
    cor_fundo = _cor_fundo(fundo)
    texto = N.montar_svg(formas, w, h, fundo=cor_fundo)

    if formato == 'svg':
        return texto.encode('utf-8'), f'{base}.svg', mime
    if formato in ('pdf', 'ai'):
        import pymupdf
        doc = pymupdf.open(stream=texto.encode('utf-8'), filetype='svg')
        return doc.convert_to_pdf(), f'{base}.{ext}', ('application/pdf' if formato == 'pdf' else mime)
    if formato == 'eps':
        from Conversor import conversor_engine as CE
        tr = N.para_trace_result(formas, w, h)
        return CE.trace_to_eps(tr).encode('ascii'), f'{base}.eps', mime
    if formato == 'dxf':
        from Conversor import conversor_engine as CE
        import tempfile
        tr = N.para_trace_result(formas, w, h)
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, 'saida.dxf')
            CE.trace_to_dxf(tr, {'dxf_hatch': '1', 'dxf_version': 'R2010'}, caminho)
            with open(caminho, 'rb') as f:
                return f.read(), f'{base}.dxf', mime
    if formato in ('png', 'webp'):
        lado = _lado(tamanho)
        im = N.renderizar(texto, lado, fundo=cor_fundo)
        buf = io.BytesIO()
        if formato == 'png':
            im.save(buf, 'PNG', optimize=False, compress_level=6)
        else:
            im.save(buf, 'WEBP', lossless=True, quality=90, method=4)
        return buf.getvalue(), f'{base} ({im.width}x{im.height}).{ext}', mime
    cores = []
    for f in formas:
        if tuple(f['cor']) not in cores:
            cores.append(tuple(f['cor']))
    if formato == 'gpl':
        linhas = ['GIMP Palette', f'Name: {base}', 'Columns: 8', '#']
        linhas += [f'{r:3d} {g:3d} {b:3d}\t{N.hexa((r, g, b))}' for r, g, b in cores]
        return ('\n'.join(linhas) + '\n').encode('utf-8'), f'{base}.gpl', mime
    return ('\n'.join(N.hexa(c) for c in cores) + '\n').encode('utf-8'), f'{base} (paleta).txt', mime


def exportar_zip(pids, formatos, tamanho='4k', fundo=None):
    buf = io.BytesIO()
    falhas, usados = [], set()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for pid in pids[:100]:
            for f in formatos:
                try:
                    dados, nome, _ = exportar_bytes(pid, f, tamanho, fundo)
                except (VetorizarError, OSError, ValueError) as e:
                    falhas.append(f'{pid} ({f}): {e}')
                    continue
                while nome in usados:
                    raiz, ext = os.path.splitext(nome)
                    nome = f'{raiz} (2){ext}'
                usados.add(nome)
                z.writestr(nome, dados)
        if falhas:
            z.writestr('LEIA - o que faltou.txt', '\n'.join(falhas) + '\n')
    return buf.getvalue()


def original_bytes(pid):
    caminho = _original(pid)
    ext = os.path.splitext(caminho)[1].lower()
    if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
        with open(caminho, 'rb') as f:
            return f.read(), {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                               '.webp': 'image/webp', '.gif': 'image/gif'}[ext]
    buf = io.BytesIO()
    Image.fromarray(N.abrir(caminho), 'RGBA').save(buf, 'PNG')
    return buf.getvalue(), 'image/png'


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'mascara':
        _worker_mascara(sys.argv[2], sys.argv[3])
    else:
        print('uso: python -m Vetorizar.vetorizar_engine mascara <entrada> <saida.png>')
        sys.exit(2)
