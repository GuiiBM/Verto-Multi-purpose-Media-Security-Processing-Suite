"""Vetor3D · exportação de arquivos 3D.

Entrada comum: lista de "partes" {nome, ids, cor '#rrggbb', metal, rugosidade,
v (N,3) float, f (M,3) int}. As malhas chegam fechadas (estanques) e em mm.

- GLB: uma malha por cor com material PBR e normais suaves com vinco
  (as quinas continuam vivas); é o formato do preview e do código.
- STL: sólido sem cor (opção de unir tudo num sólido só, para impressão).
- OBJ + MTL (zip), 3MF (objetos por cor com <basematerials>) e PLY (cor por
  vértice).
"""
import io
import json
import struct
import zipfile

import numpy as np
import trimesh

ANGULO_VINCO = 35.0


def _rgb(cor):
    cor = (cor or '#9aa1ac').lstrip('#')
    return tuple(int(cor[i:i + 2], 16) for i in (0, 2, 4))


def _linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def normais_vinco(v, f, angulo_graus=ANGULO_VINCO):
    """Normais suaves com quinas vivas (o "auto smooth" dos programas 3D).

    Os cantos de triângulos vizinhos ligados por uma aresta suave (ângulo
    menor que o vinco) viram o mesmo vértice; a normal dele é a média das
    normais das faces ponderada pelo ângulo do canto. Devolve (v, f, n) com
    vértices duplicados só onde há quina."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    if not len(f):
        return v, f, np.zeros_like(v)
    tri = v[f]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    comp = np.linalg.norm(fn, axis=1, keepdims=True)
    fn = np.divide(fn, comp, out=np.zeros_like(fn), where=comp > 0)
    # ângulo de cada canto
    ang = np.zeros((len(f), 3))
    for k in range(3):
        a = tri[:, (k + 1) % 3] - tri[:, k]
        b = tri[:, (k + 2) % 3] - tri[:, k]
        na = np.linalg.norm(a, axis=1)
        nb = np.linalg.norm(b, axis=1)
        c = np.einsum('ij,ij->i', a, b) / np.maximum(na * nb, 1e-30)
        ang[:, k] = np.arccos(np.clip(c, -1, 1))
    # arestas compartilhadas: (min, max) -> pares de faces
    arestas = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    face_de = np.tile(np.arange(len(f)), 3)
    canto_a = np.repeat([0, 1, 2], len(f))
    canto_b = np.repeat([1, 2, 0], len(f))
    chave = np.sort(arestas, axis=1)
    ordem = np.lexsort((chave[:, 1], chave[:, 0]))
    ch = chave[ordem]
    iguais = np.all(ch[1:] == ch[:-1], axis=1)
    i1 = ordem[:-1][iguais]
    i2 = ordem[1:][iguais]
    f1, f2 = face_de[i1], face_de[i2]
    cosang = np.einsum('ij,ij->i', fn[f1], fn[f2])
    suave = cosang >= np.cos(np.radians(angulo_graus))
    i1, i2, f1, f2 = i1[suave], i2[suave], f1[suave], f2[suave]
    # cantos (face*3+k) que tocam o mesmo vértice dos dois lados da aresta
    va1 = arestas[i1, 0]
    ca1 = f1 * 3 + canto_a[i1]
    cb1 = f1 * 3 + canto_b[i1]
    # na outra face, o vértice va1 pode estar no canto a ou b da aresta
    mesmo = arestas[i2, 0] == va1
    ca2 = np.where(mesmo, f2 * 3 + canto_a[i2], f2 * 3 + canto_b[i2])
    cb2 = np.where(mesmo, f2 * 3 + canto_b[i2], f2 * 3 + canto_a[i2])
    n_cantos = len(f) * 3
    lin = np.r_[ca1, cb1]
    col = np.r_[ca2, cb2]
    g = coo_matrix((np.ones(len(lin), dtype=np.int8), (lin, col)), shape=(n_cantos, n_cantos))
    _, rotulo = connected_components(g, directed=False)
    # vértices novos: um por grupo de cantos (de um mesmo vértice original)
    vert_canto = f.reshape(-1)
    novos, inv = np.unique(rotulo, return_inverse=True)
    pos = np.zeros((len(novos), 3))
    pos[inv] = v[vert_canto]
    nrm = np.zeros((len(novos), 3))
    peso = (ang.reshape(-1)[:, None] * np.repeat(fn, 3, axis=0))
    np.add.at(nrm, inv, peso)
    comp = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = np.divide(nrm, comp, out=np.zeros_like(nrm), where=comp > 0)
    return pos, inv.reshape(-1, 3), nrm


def _malha(parte):
    return trimesh.Trimesh(vertices=parte['v'], faces=parte['f'], process=False, validate=False)


def _nome_no(parte, i):
    ids = '-'.join(str(x) for x in parte.get('ids') or [i])
    return f'peca_{ids}'


def _soldada(p):
    """Malha sem as costuras da textura (vértices duplicados só pelo UV)."""
    if 'uv' not in p:
        return p
    _, inv = np.unique(np.round(np.asarray(p['v']), 6), axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    v = np.zeros((inv.max() + 1, 3))
    v[inv] = p['v']
    f = inv[np.asarray(p['f'])]
    ok = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    q = {k: x for k, x in p.items() if k not in ('uv', 'n', 'textura')}
    q.update(v=v, f=f[ok])
    return q


def _textura(p):
    from PIL import Image
    im = Image.open(p['textura'])
    im.load()
    return im          # JPEG continua JPEG dentro do GLB (bem menor que PNG)


def _cores_vertice(p):
    """Cor de cada vértice amostrada da textura (PLY)."""
    img = np.asarray(_textura(p))
    h, w = img.shape[:2]
    uv = np.asarray(p['uv'])
    x = np.clip((uv[:, 0] * (w - 1)).round().astype(int), 0, w - 1)
    y = np.clip(((1 - uv[:, 1]) * (h - 1)).round().astype(int), 0, h - 1)
    return img[y, x]


def glb(partes, suave=True):
    from trimesh.visual.material import PBRMaterial
    cena = trimesh.Scene()
    for i, p in enumerate(partes):
        if 'uv' in p:
            m = trimesh.Trimesh(vertices=p['v'], faces=p['f'], vertex_normals=p.get('n'), process=False, validate=False)
            mat = PBRMaterial(name='textura', baseColorTexture=_textura(p), baseColorFactor=[1.0, 1.0, 1.0, 1.0],
                              metallicFactor=float(p.get('metal', 0.0)), roughnessFactor=float(p.get('rugosidade', 0.55)),
                              doubleSided=False)
            m.visual = trimesh.visual.TextureVisuals(uv=p['uv'], material=mat)
            nome = _nome_no(p, i)
            cena.add_geometry(m, node_name=nome, geom_name=nome)
            continue
        if suave and len(p['f']):
            v, f, n = normais_vinco(p['v'], p['f'])
            m = trimesh.Trimesh(vertices=v, faces=f, vertex_normals=n, process=False, validate=False)
        else:
            m = _malha(p)
        # glTF guarda a cor base em espaço linear (o hex do desenho é sRGB)
        lin = [_linear(c / 255) for c in _rgb(p.get('cor'))]
        mat = PBRMaterial(name=f'cor_{p.get("cor", "#9aa1ac").lstrip("#")}',
                          baseColorFactor=lin + [1.0],
                          metallicFactor=float(p.get('metal', 0.0)),
                          roughnessFactor=float(p.get('rugosidade', 0.45)),
                          doubleSided=False)
        m.visual = trimesh.visual.TextureVisuals(material=mat)
        nome = _nome_no(p, i)
        cena.add_geometry(m, node_name=nome, geom_name=nome)
    return cena.export(file_type='glb', include_normals=True)


def _unir(partes):
    """União booleana estanque de todas as partes (manifold3d)."""
    import manifold3d as mf
    sol = None
    for p in map(_soldada, partes):
        if not len(p['f']):
            continue
        mesh = mf.Mesh(vert_properties=np.asarray(p['v'], dtype=np.float32),
                       tri_verts=np.asarray(p['f'], dtype=np.uint32))
        m = mf.Manifold(mesh)
        sol = m if sol is None else sol + m
    if sol is None:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    out = sol.to_mesh()
    return np.asarray(out.vert_properties)[:, :3].astype(np.float64), np.asarray(out.tri_verts, dtype=np.int64)


def stl(partes, unir=False):
    if unir:
        v, f = _unir(partes)
    else:
        vs, fs, n = [], [], 0
        for p in map(_soldada, partes):
            vs.append(p['v'])
            fs.append(p['f'] + n)
            n += len(p['v'])
        v, f = np.vstack(vs), np.vstack(fs)
    tri = v[f].astype(np.float32)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    comp = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = np.divide(nrm, comp, out=np.zeros_like(nrm), where=comp > 0)
    reg = np.zeros(len(f), dtype=[('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')])
    reg['n'] = nrm
    reg['v'] = tri
    cab = b'Vetor3D STL (mm)'.ljust(80, b' ')
    return cab + struct.pack('<I', len(f)) + reg.tobytes()


def obj_zip(partes, nome='modelo'):
    obj = io.StringIO()
    mtl = io.StringIO()
    obj.write(f'# Vetor3D (mm)\nmtllib {nome}.mtl\n')
    n = 1
    nt = 1
    feitos = set()
    texturas = {}
    for i, p in enumerate(partes):
        if 'uv' in p:
            mat = f'textura_{i}'
            texturas[f'{nome}_{i}.jpg'] = p['textura']
            mtl.write(f'newmtl {mat}\nKd 1 1 1\nKa 0 0 0\nKs 0.1 0.1 0.1\nNs 40\nd 1\nillum 2\nmap_Kd {nome}_{i}.jpg\n\n')
            obj.write(f'o {_nome_no(p, i)}\nusemtl {mat}\n')
            np.savetxt(obj, p['v'], fmt='v %.5f %.5f %.5f')
            np.savetxt(obj, p['uv'], fmt='vt %.6f %.6f')
            fv = np.asarray(p['f']) + n
            ft = np.asarray(p['f']) + nt
            np.savetxt(obj, np.column_stack([fv[:, 0], ft[:, 0], fv[:, 1], ft[:, 1], fv[:, 2], ft[:, 2]]),
                       fmt='f %d/%d %d/%d %d/%d')
            n += len(p['v'])
            nt += len(p['uv'])
            continue
        cor = p.get('cor') or '#9aa1ac'
        mat = 'cor_' + cor.lstrip('#')
        if mat not in feitos:
            r, g, b = (c / 255 for c in _rgb(cor))
            mtl.write(f'newmtl {mat}\nKd {r:.4f} {g:.4f} {b:.4f}\nKa 0 0 0\nKs 0.2 0.2 0.2\n'
                      f'Ns {max(1, (1 - float(p.get("rugosidade", 0.45))) * 200):.0f}\nd 1\nillum 2\n\n')
            feitos.add(mat)
        obj.write(f'o {_nome_no(p, i)}\nusemtl {mat}\n')
        np.savetxt(obj, p['v'], fmt='v %.5f %.5f %.5f')
        np.savetxt(obj, p['f'] + n, fmt='f %d %d %d')
        n += len(p['v'])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{nome}.obj', obj.getvalue())
        z.writestr(f'{nome}.mtl', mtl.getvalue())
        for arq, origem in texturas.items():
            z.write(origem, arq)
    return buf.getvalue()


def ply(partes):
    vs, fs, cs, n = [], [], [], 0
    for p in partes:
        vs.append(p['v'])
        fs.append(p['f'] + n)
        if 'uv' in p:
            c = _cores_vertice(p)
            cs.append(np.column_stack([c, np.full(len(c), 255)]).astype(np.uint8))
        else:
            cs.append(np.tile(np.array(list(_rgb(p.get('cor'))) + [255], dtype=np.uint8), (len(p['v']), 1)))
        n += len(p['v'])
    m = trimesh.Trimesh(np.vstack(vs), np.vstack(fs), vertex_colors=np.vstack(cs), process=False)
    return m.export(file_type='ply')


def tmf(partes):
    """3MF com um objeto por cor e as cores em <basematerials> (os fatiadores
    mostram as cores e permitem um filamento por objeto)."""
    cores = []
    for p in partes:
        c = (p.get('cor') or '#9aa1ac').upper()
        if c not in cores:
            cores.append(c)
    xml = io.StringIO()
    xml.write('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<model unit="millimeter" xml:lang="pt-BR" '
              'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
              '<metadata name="Application">Vetor3D (LocalTools)</metadata>\n<resources>\n'
              '<basematerials id="1">\n')
    for c in cores:
        xml.write(f'<base name="{c}" displaycolor="{c}FF"/>\n')
    xml.write('</basematerials>\n')
    ids = []
    partes = [_soldada(p) for p in partes]
    for i, p in enumerate(partes):
        oid = i + 2
        ids.append(oid)
        pidx = cores.index((p.get('cor') or '#9aa1ac').upper())
        xml.write(f'<object id="{oid}" name="{_nome_no(p, i)}" type="model" pid="1" pindex="{pidx}">\n<mesh>\n<vertices>\n')
        xml.write(''.join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>\n' for x, y, z in p['v']))
        xml.write('</vertices>\n<triangles>\n')
        xml.write(''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>\n' for a, b, c in p['f']))
        xml.write('</triangles>\n</mesh>\n</object>\n')
    xml.write('</resources>\n<build>\n')
    for oid in ids:
        xml.write(f'<item objectid="{oid}"/>\n')
    xml.write('</build>\n</model>\n')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                   '</Types>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
                   'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr('3D/3dmodel.model', xml.getvalue())
    return buf.getvalue()


FORMATOS = {
    'glb': ('GLB (cores, web)', 'model/gltf-binary'),
    'stl': ('STL (impressão 3D, sem cor)', 'model/stl'),
    'obj': ('OBJ + MTL (zip)', 'application/zip'),
    '3mf': ('3MF (impressão com cores)', 'model/3mf'),
    'ply': ('PLY (cor por vértice)', 'application/octet-stream'),
}


def exportar(partes, formato, unir=False):
    if formato == 'glb':
        return glb(partes), 'glb'
    if formato == 'stl':
        return stl(partes, unir), 'stl'
    if formato == 'obj':
        return obj_zip(partes), 'zip'
    if formato == '3mf':
        return tmf(partes), '3mf'
    if formato == 'ply':
        return ply(partes), 'ply'
    raise ValueError(f'Formato desconhecido: {formato}')


def decimar(partes, fracao):
    """Reduz os triângulos (versão "web otimizada" do código)."""
    if fracao <= 0:
        return partes
    import fast_simplification
    saida = []
    for p in partes:
        if 'uv' in p and 'uvmap' in p and len(p['f']) >= 200:
            from Vetor3D.v3d_volume import costurar_uv
            s = _soldada(p)
            v, f = fast_simplification.simplify(np.asarray(s['v'], dtype=np.float32),
                                                np.asarray(s['f'], dtype=np.int32), target_reduction=fracao)
            V, F, N, UV = costurar_uv(np.asarray(v, dtype=np.float64), np.asarray(f, dtype=np.int64), p['uvmap'])
            saida.append(dict(p, v=V, f=F, n=N, uv=UV))
            continue
        if len(p['f']) < 200 or 'uv' in p:
            saida.append(p)
            continue
        v, f = fast_simplification.simplify(np.asarray(p['v'], dtype=np.float32),
                                            np.asarray(p['f'], dtype=np.int32), target_reduction=fracao)
        saida.append(dict(p, v=np.asarray(v, dtype=np.float64), f=np.asarray(f, dtype=np.int64)))
    return saida


def salvar_partes(caminho, partes, meta=None):
    """Guarda o resultado de uma etapa (para exportar depois sem refazer)."""
    dados = {}
    info = []
    for i, p in enumerate(partes):
        dados[f'v{i}'] = np.asarray(p['v'], dtype=np.float64)
        dados[f'f{i}'] = np.asarray(p['f'], dtype=np.int64)
        for k in ('n', 'uv'):
            if k in p:
                dados[f'{k}{i}'] = np.asarray(p[k], dtype=np.float64)
        info.append({k: v for k, v in p.items() if k not in ('v', 'f', 'n', 'uv')})
    dados['info'] = np.frombuffer(json.dumps({'partes': info, 'meta': meta or {}}).encode(), dtype=np.uint8)
    with open(caminho, 'wb') as fh:
        np.savez_compressed(fh, **dados)


def carregar_partes(caminho):
    with np.load(caminho) as z:
        info = json.loads(bytes(z['info']).decode())
        partes = []
        for i, p in enumerate(info['partes']):
            q = dict(p, v=z[f'v{i}'], f=z[f'f{i}'])
            for k in ('n', 'uv'):
                if f'{k}{i}' in z.files:
                    q[k] = z[f'{k}{i}']
            partes.append(q)
    return partes, info.get('meta', {})
