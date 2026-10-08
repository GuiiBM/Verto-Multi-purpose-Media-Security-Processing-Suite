"""Vetor3D · processo de trabalho.

Roda como `python -m Vetor3D.v3d_trabalho`, separado do Flask: recebe tarefas
por linhas JSON no stdin e responde (progresso, resultado ou erro) por linhas
JSON no stdout. Assim uma etapa pesada não trava o servidor, cancelar é só
encerrar o processo, e se o sistema matar o processo por falta de memória o
app continua de pé e avisa.

As etapas de alta definição dividem o trabalho por peça entre vários
processos (quantidade decidida pela fila, de acordo com o hardware).
"""
import base64
import gzip
import json
import os
import sys
import time
import traceback

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import numpy as np  # noqa: E402
import shapely  # noqa: E402


def _baixa_prioridade():
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def _contorno_svg(geom, casas=2):
    """MultiPolygon -> atributo 'd' de SVG (y invertido para a tela)."""
    partes = []
    for p in shapely.get_parts(geom):
        for anel in [p.exterior] + list(p.interiors):
            c = np.asarray(anel.coords)
            if len(c) < 3:
                continue
            fmt = f'{{:.{casas}f}}'
            pts = ' '.join(f'{fmt.format(x)} {fmt.format(-y)}' for x, y in c[:-1])
            partes.append(f'M{pts}Z')
    return ''.join(partes)


def leitura(args, progresso):
    from Vetor3D import v3d_importar as I
    progresso('Lendo o arquivo', 0.05)
    d = I.importar(args['arquivo'], tol_frac=args['tol_frac'], opts=args.get('opts') or {},
                   trabalho=args['pasta'])
    progresso('Organizando as peças', 0.7)
    diag = float(np.hypot(d.largura, d.altura)) or 1.0
    geoms = {}
    pecas = []
    for p in d.pecas:
        g = p['geom']
        geoms[str(p['id'])] = shapely.to_wkb(g, hex=True)
        simpl = g.simplify(diag / 2500, preserve_topology=True)
        pts = sum(len(x.exterior.coords) + sum(len(r.coords) for r in x.interiors) for x in shapely.get_parts(g))
        pecas.append({
            'id': p['id'], 'nome': p['nome'], 'camada': p['camada'], 'cor': p['cor'], 'cor_original': p['cor'],
            'furo': bool(p['furo']), 'ativo': bool(p['ativo']), 'ordem': p['ordem'], 'origem': p['origem'],
            'area': round(float(g.area), 3), 'pts': int(pts), 'partes': len(g.geoms), 'papel': p.get('papel'),
            'd': _contorno_svg(simpl), 'caixa': [round(v, 3) for v in g.bounds],
        })
    with open(os.path.join(args['pasta'], 'geom.json'), 'w') as fh:
        json.dump(geoms, fh)
    progresso('Pronto', 1.0)
    return {'pecas': pecas, 'avisos': d.avisos, 'origem': d.origem, 'sem_cor': d.sem_cor,
            'sem_fundo': os.path.exists(os.path.join(args['pasta'], 'sem_fundo.png')),
            'largura': d.largura, 'altura': d.altura, 'info': d.info}


# ---------------------------------------------------------------------------
# Modelo 3D (preview e alta definição)
# ---------------------------------------------------------------------------

def _componente(job):
    from Vetor3D import v3d_geometria as G
    wkb, params, q = job
    return G.construir_componente(wkb, params, q)


def _modelo_volume(args, progresso, peca):
    """Personagem 3D: reconstrução 360° (v3d_reconstrucao) ou volume inflado (v3d_volume)."""
    from Vetor3D import v3d_exportar as E
    from Vetor3D import v3d_volume as VO
    t0 = time.time()
    pasta, nivel = args['pasta'], args['nivel']
    largura = float(args['config'].get('largura') or args['largura_original'] or 100)
    aviso_metodo = None
    if peca.get('metodo', 'reconstrucao') == 'reconstrucao':
        from Vetor3D import v3d_reconstrucao as RC
        try:
            parte, info = RC.construir(pasta, peca, largura, args['q'], lambda e, f: progresso(e, f * 0.92),
                                       orcamento_mb=float(args.get('orcamento_mb') or 1200))
        except RC.ReconstrucaoError as e:
            if 'baixar' not in str(e):
                raise RuntimeError(str(e))
            # sem o modelo (primeira vez sem internet): volume pela silhueta
            aviso_metodo = f'{e} Feito pelo método inflado (silhueta) no lugar.'
            peca = dict(peca, metodo='inflado')
    if peca.get('metodo', 'reconstrucao') != 'reconstrucao':
        try:
            parte, info = VO.construir(pasta, peca, largura, args['q'], progresso)
        except VO.VolumeError as e:
            raise RuntimeError(str(e))
        if aviso_metodo:
            info['aviso'] = aviso_metodo
    # uma textura por nível: o preview exportado depois do HD não pega a textura (e os UVs) do outro
    tex = os.path.join(pasta, f'textura_{nivel}.jpg')
    os.replace(parte['textura'], tex)
    parte['textura'] = tex
    parte.update(ids=[peca['id']], nome=peca.get('nome') or 'Personagem 3D')
    progresso('Gravando o modelo (GLB)', 0.93)
    glb = E.glb([parte])
    with open(os.path.join(pasta, f'{nivel}.glb'), 'wb') as fh:
        fh.write(glb)
    progresso('Gravando o modelo (exportação)', 0.96)
    E.salvar_partes(os.path.join(pasta, f'{nivel}.npz'), [parte], {'nivel': nivel})
    v = parte['v']
    caixa = [round(float(x), 3) for x in list(v.min(axis=0)) + list(v.max(axis=0))]
    # tamanho do código "exato": compressão estimada por uma amostra (o GLB do HD
    # passa de 50 MB; comprimir tudo só para mostrar o número levaria minutos)
    amostra = glb[:4_000_000]
    razao = len(gzip.compress(amostra, 6)) / max(1, len(amostra))
    exato_b64 = int(len(glb) * razao * 4 / 3) if len(glb) > len(amostra) else len(base64.b64encode(gzip.compress(glb, 9)))
    progresso('Pronto', 1.0)
    return {'nivel': nivel, 'triangulos': int(len(parte['f'])), 'vertices': int(len(v)), 'partes': 1,
            'estanques': int(info['estanque']), 'tempo': round(time.time() - t0, 2), 'glb_bytes': len(glb),
            'exato_b64': exato_b64, 'receita_b64': 0, 'caixa': caixa,
            'q': args['q'], 'workers': 1, 'volume': True, 'aviso': info.get('aviso'),
            'fidelidade_silhueta': info.get('fidelidade_silhueta'), 'tempos': info.get('tempos'),
            'previstos': info.get('previstos')}


def modelo(args, progresso):
    from Vetor3D import v3d_exportar as E
    from Vetor3D import v3d_geometria as G
    t0 = time.time()
    pasta = args['pasta']
    nivel = args['nivel']            # 'preview' | 'hd'
    q = args['q']
    vol = [p for p in args['pecas'] if p.get('estilo') == 'volume' and p.get('ativo', True)]
    if vol:
        return _modelo_volume(args, progresso, vol[0])
    workers = max(1, int(args.get('workers', 1)))
    progresso('Preparando o desenho 2D', 0.02)
    with open(os.path.join(pasta, 'geom.json')) as fh:
        geoms = {int(k): shapely.from_wkb(v) for k, v in json.load(fh).items()}
    grupos = G.preparar(args['pecas'], geoms, args['config'], args['largura_original'],
                        simplificar=float(args.get('simplificar') or 0))
    progresso('Preparando o desenho 2D', 0.08)

    jobs = []
    dono = []
    for gi, gr in enumerate(grupos):
        for poly in shapely.get_parts(gr['geom']):
            if poly.area <= 0:
                continue
            jobs.append((shapely.to_wkb(poly), gr['params'], q))
            pts = len(poly.exterior.coords) + sum(len(r.coords) for r in poly.interiors)
            dono.append((gi, poly, pts))
    if not jobs:
        raise RuntimeError('Nada para construir: as peças ativas ficaram vazias.')
    peso_total = float(sum(d[2] for d in dono)) or 1.0
    resultados = [None] * len(jobs)
    feito = 0.0
    rotulo = f'Geometria ({len(jobs)} parte{"s" if len(jobs) != 1 else ""}'
    rotulo += f', {workers} processos)' if workers > 1 else ')'
    progresso(rotulo, 0.1)
    ordem = sorted(range(len(jobs)), key=lambda i: -dono[i][2])
    if workers > 1 and len(jobs) > 1 and peso_total > 6000:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor, as_completed
        ctx = mp.get_context('spawn')
        with ProcessPoolExecutor(max_workers=min(workers, len(jobs)), mp_context=ctx,
                                 initializer=_baixa_prioridade) as ex:
            futs = {ex.submit(_componente, jobs[i]): i for i in ordem}
            for fut in as_completed(futs):
                i = futs[fut]
                resultados[i] = fut.result()
                feito += dono[i][2]
                progresso(rotulo, 0.1 + 0.7 * feito / peso_total)
    else:
        for i in ordem:
            resultados[i] = _componente(jobs[i])
            feito += dono[i][2]
            progresso(rotulo, 0.1 + 0.7 * feito / peso_total)

    progresso('Montagem', 0.82)
    partes = []
    receita = []
    estanques = 0
    for gi, gr in enumerate(grupos):
        vs, fs, n = [], [], 0
        comps = []
        for i, (dg, poly, _) in enumerate(dono):
            if dg != gi:
                continue
            v, f, info = resultados[i]
            if len(f):
                vs.append(v)
                fs.append(f + n)
                n += len(v)
            comps.append(G.receita_componente(poly, gr['params'], info, casas=2 if nivel == 'hd' else 2))
        if not fs:
            continue
        p = gr['params']
        partes.append({'nome': gr['nome'], 'ids': gr['ids'], 'cor': gr['cor'],
                       'metal': float(p.get('metal', 0)), 'rugosidade': float(p.get('rugosidade', 0.45)),
                       'v': np.vstack(vs), 'f': np.vstack(fs)})
        receita.append({'ids': gr['ids'], 'cor': gr['cor'], 'm': round(float(p.get('metal', 0)), 2),
                        'r': round(float(p.get('rugosidade', 0.45)), 2), 'c': comps})

    progresso('Acabamento (verificando a malha)', 0.86)
    import trimesh
    for p in partes:
        m = trimesh.Trimesh(p['v'], p['f'], process=False, validate=False)
        if m.is_watertight:
            estanques += 1
    tri = int(sum(len(p['f']) for p in partes))
    vert = int(sum(len(p['v']) for p in partes))

    progresso('Exportando o preview', 0.9)
    E.salvar_partes(os.path.join(pasta, f'{nivel}.npz'), partes, {'nivel': nivel})
    glb = E.glb(partes)
    with open(os.path.join(pasta, f'{nivel}.glb'), 'wb') as fh:
        fh.write(glb)
    rec = {'v': 1, 'u': 'mm', 'p': receita}
    rec_txt = json.dumps(rec, separators=(',', ':'))
    with open(os.path.join(pasta, f'{nivel}.receita.json'), 'w') as fh:
        fh.write(rec_txt)
    exato_b64 = len(base64.b64encode(gzip.compress(glb, 9)))
    receita_b64 = len(base64.b64encode(gzip.compress(rec_txt.encode(), 9)))
    xs = np.vstack([p['v'] for p in partes])
    caixa = [round(float(v), 3) for v in list(xs.min(axis=0)) + list(xs.max(axis=0))]
    progresso('Pronto', 1.0)
    return {'nivel': nivel, 'triangulos': tri, 'vertices': vert, 'partes': len(partes),
            'estanques': estanques, 'tempo': round(time.time() - t0, 2), 'glb_bytes': len(glb),
            'exato_b64': exato_b64, 'receita_b64': receita_b64, 'caixa': caixa, 'q': q, 'workers': workers}


# ---------------------------------------------------------------------------
# Exportação e código
# ---------------------------------------------------------------------------

def exportar(args, progresso):
    from Vetor3D import v3d_exportar as E
    progresso('Carregando o modelo', 0.1)
    partes, _ = E.carregar_partes(args['npz'])
    progresso(f'Gerando {args["formato"].upper()}', 0.4)
    dados, ext = E.exportar(partes, args['formato'], unir=bool(args.get('unir')))
    destino = args['destino']
    base, _ = os.path.splitext(destino)
    destino = base + '.' + ext
    n = 2
    final = destino
    while os.path.exists(final):
        final = f'{base} ({n}).{ext}'
        n += 1
    with open(final, 'wb') as fh:
        fh.write(dados)
    progresso('Pronto', 1.0)
    return {'caminho': final, 'nome': os.path.basename(final), 'bytes': len(dados)}


def codigo(args, progresso):
    from Vetor3D import v3d_codigo as C
    from Vetor3D import v3d_exportar as E
    pasta = args['pasta']
    nivel = args['nivel']
    op = args['opcoes']
    payload = {}
    progresso('Preparando o modelo', 0.1)
    if op.get('carga', 'exato') == 'exato':
        reducao = float(op.get('reducao') or 0)
        if reducao > 0:
            partes, _ = E.carregar_partes(os.path.join(pasta, f'{nivel}.npz'))
            progresso('Otimizando para a web', 0.3)
            partes = E.decimar(partes, reducao)
            glb = E.glb(partes)
        else:
            with open(os.path.join(pasta, f'{nivel}.glb'), 'rb') as fh:
                glb = fh.read()
            partes = None
        payload['glb'] = base64.b64encode(gzip.compress(glb, 9)).decode('ascii')
        extras = op.get('extras') or []
        if extras:
            if partes is None:
                partes, _ = E.carregar_partes(os.path.join(pasta, f'{nivel}.npz'))
                if reducao > 0:
                    partes = E.decimar(partes, reducao)
            for fmt in extras:
                if fmt in ('stl', 'obj', '3mf', 'ply'):
                    progresso(f'Embutindo {fmt.upper()}', 0.5)
                    dados, _ = E.exportar(partes, fmt)
                    payload[fmt] = base64.b64encode(gzip.compress(dados, 9)).decode('ascii')
    else:
        with open(os.path.join(pasta, f'{nivel}.receita.json')) as fh:
            payload['receita'] = base64.b64encode(gzip.compress(fh.read().encode(), 9)).decode('ascii')
    progresso('Montando o código', 0.8)
    texto, ext = C.gerar(payload, op)
    destino = os.path.join(pasta, f'codigo_{args["tid"]}.{ext}')
    with open(destino, 'w', encoding='utf-8') as fh:
        fh.write(texto)
    progresso('Pronto', 1.0)
    return {'arquivo': destino, 'ext': ext, 'bytes': len(texto.encode('utf-8'))}


FUNCOES = {'leitura': leitura, 'modelo': modelo, 'exportar': exportar, 'codigo': codigo}


class _Falha(Exception):
    pass


def _mensagem(e):
    from Vetor3D.v3d_importar import ImportError3D
    from Vetor3D.v3d_geometria import GeometriaError
    if isinstance(e, (ImportError3D, GeometriaError)):
        return str(e)
    if isinstance(e, MemoryError):
        return 'Faltou memória nesta etapa. Feche outros programas ou use o perfil Econômico.'
    return f'{type(e).__name__}: {e}'


def main():
    _baixa_prioridade()
    # stdout é só do protocolo; qualquer print de biblioteca vai para o stderr
    canal = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1, encoding='utf-8')
    sys.stdout = sys.stderr

    def enviar(obj):
        canal.write(json.dumps(obj, ensure_ascii=False) + '\n')
        canal.flush()

    enviar({'t': 'pronto', 'pid': os.getpid()})
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            msg = json.loads(linha)
        except ValueError:
            continue
        if msg.get('func') == 'sair':
            break
        tid = msg.get('id')
        ultimo = [0.0]

        def progresso(etapa, frac, _tid=tid):
            agora = time.monotonic()
            if frac >= 1.0 or agora - ultimo[0] > 0.15:
                ultimo[0] = agora
                enviar({'t': 'progresso', 'id': _tid, 'etapa': etapa, 'frac': round(float(frac), 4)})

        try:
            res = FUNCOES[msg['func']](msg.get('args') or {}, progresso)
            enviar({'t': 'ok', 'id': tid, 'res': res})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            enviar({'t': 'erro', 'id': tid, 'erro': _mensagem(e)})


if __name__ == '__main__':
    main()
