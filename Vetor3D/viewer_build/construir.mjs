// Gera os dois visualizadores usados pelo código copia-e-cola do Vetor3D:
//   static/localtools/vetor3d/viewer-embutido.min.js  three.js dentro (funciona offline)
//   static/localtools/vetor3d/viewer-cdn.min.js       three.js do jsDelivr (versão fixa)
//
// Uso (precisa de internet só para instalar):
//   cd /tmp/v3d && npm i three@0.170.0 esbuild
//   node <Verto>/Vetor3D/viewer_build/construir.mjs /tmp/v3d/node_modules
import path from 'node:path';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const nm = path.resolve(process.argv[2] || 'node_modules');
const require = createRequire(path.join(nm, 'x.js'));
const esbuild = require('esbuild');
const aqui = path.dirname(fileURLToPath(import.meta.url));
const saida = path.resolve(aqui, '../../static/localtools/vetor3d');
const entrada = path.join(aqui, 'entrada.js');
const THREE = '0.170.0';
const CDN = `https://cdn.jsdelivr.net/npm/three@${THREE}`;

const versao = JSON.parse(fs.readFileSync(path.join(nm, 'three/package.json'), 'utf8')).version;
if (versao !== THREE) throw new Error(`three ${versao} instalado; o Vetor3D usa ${THREE}`);

const base = { entryPoints: [entrada], bundle: true, minify: true, nodePaths: [nm], target: 'es2020', legalComments: 'none', write: false };

const emb = await esbuild.build({ ...base, format: 'iife' });
let codigoEmb = emb.outputFiles[0].text;
codigoEmb = `/* Vetor3D viewer · three.js r170 (MIT) embutido */\n` + codigoEmb;
fs.writeFileSync(path.join(saida, 'viewer-embutido.min.js'), codigoEmb);

const cdn = await esbuild.build({ ...base, format: 'esm', external: ['three', 'three/addons/*'] });
let codigoCdn = cdn.outputFiles[0].text
  .replace(/(["'])three\1/g, `"${CDN}/+esm"`)
  .replace(/(["'])three\/addons\/([^"']+)\1/g, (_, q, p) => `"${CDN}/examples/jsm/${p}/+esm"`);
if (/["']three(\/|["'])/.test(codigoCdn)) throw new Error('sobrou import "three" sem CDN');
codigoCdn = `/* Vetor3D viewer · three.js r${THREE.split('.')[1]} via jsDelivr */\n` + codigoCdn;
fs.writeFileSync(path.join(saida, 'viewer-cdn.min.js'), codigoCdn);

for (const n of ['viewer-embutido.min.js', 'viewer-cdn.min.js']) {
  const t = fs.readFileSync(path.join(saida, n), 'utf8');
  if (/<\/script/i.test(t)) throw new Error(`${n} contém </script>`);
  console.log(n, (t.length / 1024).toFixed(1), 'KB');
}
