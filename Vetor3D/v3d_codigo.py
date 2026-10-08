"""Vetor3D · código copia-e-cola.

Monta o código que mostra (e gera) o modelo 3D em qualquer site: um trecho
HTML universal (qualquer página, WordPress, Netlify, Webflow...), uma página
completa (index.html para o Netlify Drop), um componente React/Next.js, um
arquivo PHP, um módulo Python e um script Node.js.

payload: {'glb': b64gz, 'stl'|'obj'|'3mf'|'ply': b64gz} (modelo exato) ou
         {'receita': b64gz} (contornos + parâmetros, reconstruído no navegador)
opcoes:  carga, three ('cdn'|'embutido'), alvo, proporcao, autoRotacao, pan,
         verniz, fundo, botaoBaixar, nome
"""
import json
import os
import re
import secrets

PASTA_VIEWER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'static', 'localtools', 'vetor3d')
EXT = {'html': 'html', 'pagina': 'html', 'react': 'jsx', 'php': 'php', 'python': 'py', 'node': 'cjs'}
TIPOS = {'glb': ('model/gltf-binary', 'glb'), 'stl': ('model/stl', 'stl'), 'obj': ('application/zip', 'zip'),
         '3mf': ('model/3mf', '3mf'), 'ply': ('application/octet-stream', 'ply')}


def _viewer(three):
    nome = 'viewer-cdn.min.js' if three == 'cdn' else 'viewer-embutido.min.js'
    caminho = os.path.join(PASTA_VIEWER, nome)
    if not os.path.isfile(caminho):
        raise RuntimeError(f'{nome} não encontrado: rode Vetor3D/viewer_build/construir.mjs.')
    with open(caminho, encoding='utf-8') as fh:
        return fh.read().strip()


def tamanho_viewer(three):
    try:
        return len(_viewer(three).encode('utf-8'))
    except RuntimeError:
        return 0


def _slug(nome):
    s = re.sub(r'[^A-Za-z0-9_-]+', '_', nome or 'modelo').strip('_')
    return (s or 'modelo')[:60]


def _tag_viewer(three):
    codigo = _viewer(three)
    if three == 'cdn':
        return f'<script type="module">{codigo}</script>'
    return f'<script>{codigo}</script>'


def _opcoes_embed(op):
    return {'autoRotacao': op['autoRotacao'], 'pan': op['pan'], 'verniz': op['verniz'],
            'botaoBaixar': op['botaoBaixar'], 'nome': _slug(op['nome']), 'vista': 'iso'}


def _div(id_, op):
    fundo = f'background:{op["fundo"]};' if op.get('fundo') else ''
    return (f'<div id="{id_}" class="v3d-modelo" style="position:relative;width:100%;'
            f'aspect-ratio:{op["proporcao"]};max-height:85vh;overflow:hidden;border-radius:14px;{fundo}"></div>')


def _iniciar(id_, dados_js, op):
    return ('<script>\n(function () {\n'
            f'  var el = document.getElementById("{id_}");\n'
            f'  var dados = {dados_js};\n'
            f'  var opcoes = {json.dumps(_opcoes_embed(op), ensure_ascii=False)};\n'
            '  function iniciar() { window.Vetor3DViewer.iniciarEmbed(el, dados, opcoes); }\n'
            '  if (window.Vetor3DViewer) iniciar();\n'
            '  else window.addEventListener("vetor3d:pronto", iniciar, { once: true });\n'
            '})();\n</script>')


def _cabecalho_html(op, exato):
    modo = 'modelo exato embutido' if exato else 'receita leve (reconstruído no navegador)'
    three = 'three.js via CDN (jsDelivr)' if op['three'] == 'cdn' else 'three.js embutido (funciona offline)'
    return (f'<!-- Modelo 3D "{op["nome"]}" · gerado pelo Vetor3D (LocalTools) · {modo} · {three}\n'
            '     Cole em qualquer página: HTML, WordPress (bloco "HTML personalizado"), Netlify, Webflow (Embed)...\n'
            '     Ocupa 100% da largura de onde for colado. Arraste para girar 360°, role ou pince para zoom. -->')


def _trecho(id_, dados_js, op, exato):
    return '\n'.join([_cabecalho_html(op, exato), _div(id_, op), _tag_viewer(op['three']),
                      _iniciar(id_, dados_js, op)])


def _pagina(corpo, op):
    titulo = (op['nome'] or 'Modelo 3D').replace('<', '').replace('>', '')
    return ('<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{titulo} · 3D</title>\n'
            '<style>html,body{margin:0;min-height:100%;background:#0b0c0f;color:#e2e8f0;'
            'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}'
            'main{max-width:960px;margin:0 auto;padding:24px 16px}'
            'h1{font-size:clamp(20px,4vw,30px);margin:0 0 16px}</style>\n'
            f'</head>\n<body>\n<main>\n<h1>{titulo}</h1>\n{corpo}\n</main>\n</body>\n</html>\n')


def _react(dados, op, exato):
    viewer = _viewer(op['three'])
    modulo = 'true' if op['three'] == 'cdn' else 'false'
    nome = re.sub(r'[^A-Za-z0-9]', '', _slug(op['nome']).title()) or 'Modelo'
    if nome[0].isdigit():
        nome = 'M' + nome
    fundo = f", background: '{op['fundo']}'" if op.get('fundo') else ''
    proporcao = op['proporcao'].replace('/', ' / ')
    return f"""'use client';
/**
 * Modelo 3D "{op['nome']}" · gerado pelo Vetor3D (LocalTools)
 * Componente React / Next.js sem dependências: cole este arquivo no projeto e use
 *   import {nome}3D from './Modelo3D';   // salve este arquivo como Modelo3D.jsx
 *   <{nome}3D />            // ocupa 100% da largura do pai, proporção {op['proporcao']}
 * Arraste para girar 360°, role ou pince para zoom.
 */
import {{ useEffect, useRef }} from 'react';

const VIEWER = {json.dumps(viewer)};
const MODULO = {modulo};
const DADOS = {json.dumps(dados)};
const OPCOES = {json.dumps(_opcoes_embed(op), ensure_ascii=False)};

function carregarViewer() {{
  if (window.Vetor3DViewer) return Promise.resolve(window.Vetor3DViewer);
  if (!window.__vetor3dCarregando) {{
    window.__vetor3dCarregando = new Promise((ok) => {{
      window.addEventListener('vetor3d:pronto', () => ok(window.Vetor3DViewer), {{ once: true }});
      const s = document.createElement('script');
      if (MODULO) s.type = 'module';
      s.textContent = VIEWER;
      document.head.appendChild(s);
    }});
  }}
  return window.__vetor3dCarregando;
}}

export default function {nome}3D({{ className, style }}) {{
  const ref = useRef(null);
  useEffect(() => {{
    let api = null;
    let vivo = true;
    carregarViewer().then((V) => {{
      if (vivo && ref.current) api = V.iniciarEmbed(ref.current, DADOS, OPCOES);
    }});
    return () => {{
      vivo = false;
      if (api) api.destruir();
    }};
  }}, []);
  return (
    <div
      ref={{ref}}
      className={{className}}
      style={{{{ position: 'relative', width: '100%', aspectRatio: '{proporcao}', maxHeight: '85vh',
        overflow: 'hidden', borderRadius: 14{fundo}, ...style }}}}
    />
  );
}}
"""


def _php(dados, op, exato):
    id_ = 'v3d-' + secrets.token_hex(3)
    fn = 'v3d_' + id_[4:] + '_dados'
    slug = _slug(op['nome'])
    linhas = ',\n'.join(f"        '{k}' => '{v}'" for k, v in dados.items())
    tipos = ', '.join(f"'{k}' => array('{t}', '{e}')" for k, (t, e) in TIPOS.items())
    viewer = _viewer(op['three'])
    tag_ini = '<script type="module">' if op['three'] == 'cdn' else '<script>'
    outros = [k for k in dados if k != 'glb']
    tambem = f'  (também: {", ".join(outros)})' if exato and outros else ''
    baixar = ('Este código usa a receita leve: use o botão GLB/STL do visualizador para baixar.'
              if not exato else 'Formato não incluído neste código.')
    return f"""<?php
/**
 * Modelo 3D "{op['nome']}" · gerado pelo Vetor3D (LocalTools)
 *
 * Como usar:
 *   1. Salve este arquivo como modelo3d.php no seu site (qualquer hospedagem com PHP).
 *   2. Para mostrar o modelo numa página:  <?php include __DIR__ . '/modelo3d.php'; ?>
 *      (ou abra o arquivo direto no navegador)
 *   3. Para baixar o arquivo 3D: modelo3d.php?baixar=glb{tambem}
 * Arraste para girar 360°, role ou pince para zoom. Ocupa 100% da largura de onde for incluído.
 */
if (!function_exists('{fn}')) {{
    function {fn}() {{
        return array(
{linhas}
        );
    }}
}}
if (isset($_GET['baixar']) && realpath($_SERVER['SCRIPT_FILENAME']) === __FILE__) {{
    $v3d = {fn}();
    $tipos = array({tipos});
    $fmt = (string) $_GET['baixar'];
    if (isset($v3d[$fmt]) && isset($tipos[$fmt])) {{
        header('Content-Type: ' . $tipos[$fmt][0]);
        header('Content-Disposition: attachment; filename="{slug}.' . $tipos[$fmt][1] . '"');
        echo gzdecode(base64_decode($v3d[$fmt]));
        exit;
    }}
    http_response_code(404);
    header('Content-Type: text/plain; charset=utf-8');
    echo '{baixar}';
    exit;
}}
?>
{_cabecalho_html(op, exato)}
{_div(id_, op)}
{tag_ini}<?php echo <<<'V3DVIEWER'
{viewer}
V3DVIEWER;
?></script>
{_iniciar(id_, "<?php echo json_encode(" + fn + "()); ?>", op)}
"""


def _python(dados, op, exato):
    id_ = 'v3d-' + secrets.token_hex(3)
    slug = _slug(op['nome'])
    trecho = _trecho(id_, '__V3D_DADOS__', op, exato)
    pagina = _pagina('__V3D_TRECHO__', op)
    arquivos = ',\n'.join(f'    {json.dumps(k)}: {json.dumps(v)}' for k, v in dados.items())
    extras = ' (e os extras)' if exato else ''
    outros = [k for k in dados if k != 'glb']
    lista = ', ' + ', '.join(outros) if exato and outros else ''
    return f'''"""Modelo 3D "{op['nome']}" · gerado pelo Vetor3D (LocalTools)

Só usa a biblioteca padrão do Python 3. Como usar:
  Gerar os arquivos:  python modelo3d.py        -> cria {slug}.glb{extras} e {slug}.html
  Flask:      from modelo3d import html
              @app.route("/3d")
              def modelo(): return html(pagina=True)
  Django:     return HttpResponse(html(pagina=True))
  FastAPI:    return HTMLResponse(html(pagina=True))
  Streamlit:  streamlit.components.v1.html(html(), height=600)
  Templates:  passe html() para o template e use {{{{ trecho|safe }}}} (Jinja/Django)
Arraste para girar 360°, role ou pince para zoom. Ocupa 100% da largura de onde for colado.
"""
import base64
import gzip
import json
import sys

NOME = {json.dumps(slug)}
EXATO = {exato}
ARQUIVOS = {{
{arquivos}
}}
EXTENSOES = {json.dumps({k: e for k, (_, e) in TIPOS.items()})}
_TRECHO = {json.dumps(trecho, ensure_ascii=False)}
_PAGINA = {json.dumps(pagina, ensure_ascii=False)}


def html(pagina=False):
    """Trecho HTML do visualizador (ou a página completa)."""
    trecho = _TRECHO.replace("__V3D_DADOS__", json.dumps(ARQUIVOS), 1)
    return _PAGINA.replace("__V3D_TRECHO__", trecho, 1) if pagina else trecho


def dados(formato="glb"):
    """Bytes do arquivo 3D embutido (glb{lista})."""
    if not EXATO:
        raise RuntimeError("Este código usa a receita leve: o arquivo é gerado pelo botão do visualizador.")
    if formato not in ARQUIVOS:
        raise KeyError("Formato não incluído: " + formato)
    return gzip.decompress(base64.b64decode(ARQUIVOS[formato]))


def salvar(formato="glb", caminho=None):
    caminho = caminho or NOME + "." + EXTENSOES[formato]
    with open(caminho, "wb") as fh:
        fh.write(dados(formato))
    return caminho


if __name__ == "__main__":
    if EXATO:
        for fmt in ARQUIVOS:
            print("gravado:", salvar(fmt))
    with open(NOME + ".html", "w", encoding="utf-8") as fh:
        fh.write(html(pagina=True))
    print("gravado:", NOME + ".html")
    sys.exit(0)
'''


def _node(dados, op, exato):
    id_ = 'v3d-' + secrets.token_hex(3)
    slug = _slug(op['nome'])
    trecho = _trecho(id_, '__V3D_DADOS__', op, exato)
    pagina = _pagina('__V3D_TRECHO__', op)
    extras = ' (e os extras)' if exato else ''
    return f"""// Modelo 3D "{op['nome']}" · gerado pelo Vetor3D (LocalTools) · Node.js, sem dependências
//
//   node modelo3d.cjs                      -> grava {slug}.glb{extras} e {slug}.html
//   const {{ html, salvar }} = require('./modelo3d.cjs')   (ESM: import m from './modelo3d.cjs')
//   Express:  app.get('/3d', (req, res) => res.send(html({{ pagina: true }})))
//   Netlify Functions: return {{ statusCode: 200, headers: {{ 'content-type': 'text/html' }}, body: html({{ pagina: true }}) }}
// Arraste para girar 360°, role ou pince para zoom. Ocupa 100% da largura de onde for colado.
'use strict';
const fs = require('fs');
const zlib = require('zlib');

const NOME = {json.dumps(slug)};
const EXATO = {'true' if exato else 'false'};
const ARQUIVOS = {json.dumps(dados, indent=2)};
const EXTENSOES = {json.dumps({k: e for k, (_, e) in TIPOS.items()})};
const TRECHO = {json.dumps(trecho, ensure_ascii=False)};
const PAGINA = {json.dumps(pagina, ensure_ascii=False)};

function html(op = {{}}) {{
  const trecho = TRECHO.replace('__V3D_DADOS__', () => JSON.stringify(ARQUIVOS));
  return op.pagina ? PAGINA.replace('__V3D_TRECHO__', () => trecho) : trecho;
}}

function dados(formato = 'glb') {{
  if (!EXATO) throw new Error('Este código usa a receita leve: o arquivo é gerado pelo botão do visualizador.');
  if (!ARQUIVOS[formato]) throw new Error('Formato não incluído: ' + formato);
  return zlib.gunzipSync(Buffer.from(ARQUIVOS[formato], 'base64'));
}}

function salvar(formato = 'glb', caminho) {{
  caminho = caminho || NOME + '.' + EXTENSOES[formato];
  fs.writeFileSync(caminho, dados(formato));
  return caminho;
}}

module.exports = {{ html, dados, salvar, ARQUIVOS }};

if (require.main === module) {{
  if (EXATO) for (const fmt of Object.keys(ARQUIVOS)) console.log('gravado:', salvar(fmt));
  fs.writeFileSync(NOME + '.html', html({{ pagina: true }}));
  console.log('gravado:', NOME + '.html');
}}
"""


def gerar(payload, op):
    """Devolve (texto, extensão)."""
    exato = 'glb' in payload
    dados = {k: v for k, v in payload.items() if k in ('glb', 'receita', 'stl', 'obj', '3mf', 'ply')}
    alvo = op.get('alvo', 'html')
    if alvo in ('html', 'pagina'):
        id_ = 'v3d-' + secrets.token_hex(3)
        trecho = _trecho(id_, json.dumps(dados), op, exato)
        texto = _pagina(trecho, op) if alvo == 'pagina' else trecho + '\n'
    elif alvo == 'react':
        texto = _react(dados, op, exato)
    elif alvo == 'php':
        texto = _php(dados, op, exato)
    elif alvo == 'python':
        texto = _python(dados, op, exato)
    elif alvo == 'node':
        texto = _node(dados, op, exato)
    else:
        raise ValueError('Alvo inválido.')
    return texto, EXT[alvo]
