/* Vetor3D · visualizador 3D (three.js)
 *
 * O mesmo código roda na página do app e dentro do código copia-e-cola que o
 * app gera, então o preview e o site final mostram o modelo do mesmo jeito.
 *
 * - qualidade adaptada ao aparelho (núcleos, memória, GPU, tela);
 * - desenha só quando algo muda e só enquanto está visível na tela;
 * - giro 360° (arrastar), zoom (roda / pinça), pan opcional, responsivo;
 * - modelo "exato" (GLB comprimido) ou "receita" (contornos reconstruídos aqui);
 * - gera o arquivo no navegador (GLB / STL) para o botão "Baixar".
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { mergeGeometries, mergeVertices, toCreasedNormals } from 'three/addons/utils/BufferGeometryUtils.js';

const VINCO = (35 * Math.PI) / 180;

/* ---------- Aparelho ---------- */
export function nivelAparelho() {
  let pontos = 0;
  const nucleos = navigator.hardwareConcurrency || 4;
  const memoria = navigator.deviceMemory || 4;
  const movel = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '');
  if (nucleos >= 8) pontos += 2; else if (nucleos >= 4) pontos += 1;
  if (memoria >= 8) pontos += 2; else if (memoria >= 4) pontos += 1;
  if (movel) pontos -= 1;
  try {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl2') || c.getContext('webgl');
    if (!gl) return 'nenhum';
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    const nome = ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : '';
    if (/RTX|GTX|Radeon RX|Radeon Pro|Apple M\d|Arc A/i.test(nome)) pontos += 2;
    if (/SwiftShader|llvmpipe|Software|Mali-4|Adreno \(TM\) [3-5]/i.test(nome)) pontos -= 3;
    const perda = gl.getExtension('WEBGL_lose_context');
    if (perda) perda.loseContext();
  } catch (e) { /* segue com o que deu para medir */ }
  return pontos >= 4 ? 'alto' : pontos >= 2 ? 'medio' : 'baixo';
}

/* ---------- Dados ---------- */
export async function decodificar(b64) {
  const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  if (typeof DecompressionStream === 'undefined') throw new Error('Navegador sem DecompressionStream');
  const fluxo = new Blob([bin]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Response(fluxo).arrayBuffer();
}

export function carregarGLB(buffer) {
  return new Promise((ok, falha) => new GLTFLoader().parse(buffer, '', (g) => ok(g.scene), falha));
}

function pontos(plano) {
  const out = [];
  for (let i = 0; i < plano.length; i += 2) out.push(new THREE.Vector2(plano[i], plano[i + 1]));
  return out;
}

/* Receita: contornos (mm) + parâmetros por parte -> malhas com ExtrudeGeometry */
export function construirReceita(rec, nivel = 'medio') {
  const seg = nivel === 'alto' ? { c: 8, i: 14 } : nivel === 'medio' ? { c: 6, i: 10 } : { c: 4, i: 7 };
  const grupo = new THREE.Group();
  for (const p of rec.p) {
    const geos = [];
    for (const c of p.c) {
      const forma = new THREE.Shape(pontos(c.f[0]));
      for (const furo of c.f.slice(1)) forma.holes.push(new THREE.Path(pontos(furo)));
      let g;
      if (c.e === 'c') {
        const b = c.bt || 0;
        if (b > 0) {
          g = new THREE.ExtrudeGeometry(forma, {
            depth: Math.max(c.h - 2 * b, 1e-4), bevelEnabled: true, bevelThickness: b, bevelSize: b,
            bevelOffset: -b, bevelSegments: c.r ? 1 : seg.c, curveSegments: 1, steps: 1,
          });
          g.translate(0, 0, b + (c.z || 0));
        } else {
          g = new THREE.ExtrudeGeometry(forma, { depth: Math.max(c.h, 1e-4), bevelEnabled: false, curveSegments: 1 });
          g.translate(0, 0, c.z || 0);
        }
      } else {
        const h = c.bt || 0;
        const bs = c.bs || 0;
        g = new THREE.ExtrudeGeometry(forma, {
          depth: Math.max(c.h, 1e-4), bevelEnabled: h > 0 && bs > 0, bevelThickness: h, bevelSize: bs,
          bevelOffset: -bs, bevelSegments: seg.i, curveSegments: 1, steps: 1,
        });
        if (c.d) {
          g.translate(0, 0, h + (c.z || 0));
        } else {
          // fundo plano: achata a metade de baixo do "balão"
          const pos = g.attributes.position;
          for (let i = 0; i < pos.count; i++) if (pos.getZ(i) < 0) pos.setZ(i, 0);
          g.translate(0, 0, c.z || 0);
        }
      }
      g.deleteAttribute('uv');
      geos.push(g);
    }
    if (!geos.length) continue;
    let geo = geos.length > 1 ? mergeGeometries(geos) : geos[0];
    geo.deleteAttribute('normal');
    geo = toCreasedNormals(mergeVertices(geo, 1e-4), VINCO);
    const mat = new THREE.MeshStandardMaterial({ color: p.cor, metalness: p.m || 0, roughness: p.r ?? 0.45 });
    const malha = new THREE.Mesh(geo, mat);
    malha.name = 'peca_' + p.ids.join('-');
    grupo.add(malha);
  }
  return grupo;
}

/* ---------- Arquivos gerados no navegador ---------- */
export function exportarSTL(objeto) {
  objeto.updateMatrixWorld(true);
  const tris = [];
  const v = new THREE.Vector3();
  objeto.traverse((m) => {
    if (!m.isMesh) return;
    const g = m.geometry;
    const pos = g.attributes.position;
    const idx = g.index;
    const n = idx ? idx.count : pos.count;
    for (let i = 0; i < n; i++) {
      v.fromBufferAttribute(pos, idx ? idx.getX(i) : i).applyMatrix4(m.matrixWorld);
      tris.push(v.x, v.y, v.z);
    }
  });
  const nt = tris.length / 9;
  const buf = new ArrayBuffer(84 + nt * 50);
  const dv = new DataView(buf);
  const cab = 'Vetor3D STL (mm)';
  for (let i = 0; i < cab.length; i++) dv.setUint8(i, cab.charCodeAt(i));
  dv.setUint32(80, nt, true);
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), nrm = new THREE.Vector3();
  let o = 84;
  for (let t = 0; t < nt; t++) {
    a.fromArray(tris, t * 9); b.fromArray(tris, t * 9 + 3); c.fromArray(tris, t * 9 + 6);
    nrm.subVectors(c, b).cross(b.clone().sub(a)).normalize().negate();
    for (const p of [nrm, a, b, c]) { dv.setFloat32(o, p.x, true); dv.setFloat32(o + 4, p.y, true); dv.setFloat32(o + 8, p.z, true); o += 12; }
    dv.setUint16(o, 0, true); o += 2;
  }
  return buf;
}

export async function exportarGLB(objeto) {
  const { GLTFExporter } = await import('three/addons/exporters/GLTFExporter.js');
  return new GLTFExporter().parseAsync(objeto, { binary: true });
}

/* ---------- Visualizador ---------- */
const DIRECOES = {
  frente: [0, 0, 1], iso: [0.5, 0.32, 1], lado: [1, 0.05, 0.02], topo: [0, 1, 0.02], costas: [0, 0, -1],
};

export function montar(el, opcoes = {}) {
  const op = Object.assign({ fundo: null, autoRotacao: false, pan: false, verniz: 0.35, qualidade: 'auto', capturavel: false }, opcoes);
  const nivel = op.qualidade === 'auto' ? nivelAparelho() : op.qualidade;
  if (nivel === 'nenhum') throw new Error('WebGL indisponível');
  const reduzido = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const renderer = new THREE.WebGLRenderer({
    antialias: nivel !== 'baixo', alpha: true, preserveDrawingBuffer: !!op.capturavel,
    powerPreference: nivel === 'alto' ? 'high-performance' : 'default',
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, nivel === 'alto' ? 2 : nivel === 'medio' ? 1.5 : 1));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = nivel === 'alto';
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const canvas = renderer.domElement;
  canvas.style.cssText = 'display:block;width:100%;height:100%;touch-action:none;outline:none;cursor:grab';
  canvas.setAttribute('aria-label', 'Modelo 3D: arraste para girar, role ou pince para aproximar');
  canvas.setAttribute('role', 'img');
  if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
  el.appendChild(canvas);

  const cena = new THREE.Scene();
  if (op.fundo) cena.background = new THREE.Color(op.fundo);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const ambiente = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  cena.environment = ambiente;
  cena.environmentIntensity = 0.85;
  const luz = new THREE.DirectionalLight(0xffffff, 1.5);
  luz.castShadow = renderer.shadowMap.enabled;
  luz.shadow.mapSize.set(2048, 2048);
  luz.shadow.bias = -0.0004;
  luz.shadow.normalBias = 0.02;
  const contra = new THREE.DirectionalLight(0xbfd9ff, 0.45);
  cena.add(luz, luz.target, contra, new THREE.HemisphereLight(0xffffff, 0x334155, 0.35));

  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 10000);
  const controles = new OrbitControls(camera, canvas);
  controles.enableDamping = true;
  controles.dampingFactor = 0.08;
  controles.rotateSpeed = 0.9;
  controles.enablePan = !!op.pan;
  controles.screenSpacePanning = true;
  controles.autoRotate = !!op.autoRotacao && !reduzido;
  controles.autoRotateSpeed = 1.6;
  controles.touches = { ONE: THREE.TOUCH.ROTATE, TWO: op.pan ? THREE.TOUCH.DOLLY_PAN : THREE.TOUCH.DOLLY_ROTATE };

  const raiz = new THREE.Group();
  cena.add(raiz);
  let modelo = null;
  let raio = 1;
  let precisa = true;
  let visivel = true;
  const marcar = () => { precisa = true; };
  controles.addEventListener('change', marcar);
  controles.addEventListener('start', () => { canvas.style.cursor = 'grabbing'; });
  controles.addEventListener('end', () => { canvas.style.cursor = 'grab'; });

  function quadro() {
    const mudou = controles.update();
    if (mudou || precisa) {
      renderer.render(cena, camera);
      precisa = false;
    }
  }
  function ligarLaco() {
    renderer.setAnimationLoop(visivel && !document.hidden ? quadro : null);
  }
  const io = 'IntersectionObserver' in window ? new IntersectionObserver((es) => {
    visivel = es.some((e) => e.isIntersecting);
    ligarLaco();
  }) : null;
  if (io) io.observe(el);
  const aoVisibilidade = () => ligarLaco();
  document.addEventListener('visibilitychange', aoVisibilidade);

  function ajustar() {
    const w = Math.max(1, el.clientWidth);
    const h = Math.max(1, el.clientHeight || w);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    precisa = true;
  }
  const ro = 'ResizeObserver' in window ? new ResizeObserver(ajustar) : null;
  if (ro) ro.observe(el); else window.addEventListener('resize', ajustar);
  ajustar();
  ligarLaco();

  function descartar(obj) {
    obj.traverse((m) => {
      if (m.geometry) m.geometry.dispose();
      if (m.material) (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => x.dispose());
    });
  }

  function enquadrar(vista = 'iso') {
    const d = new THREE.Vector3().fromArray(DIRECOES[vista] || DIRECOES.iso).normalize();
    const fov = THREE.MathUtils.degToRad(camera.fov);
    const fovH = 2 * Math.atan(Math.tan(fov / 2) * camera.aspect);
    const dist = (raio / Math.sin(Math.min(fov, fovH) / 2)) * 1.04;
    camera.position.copy(d.multiplyScalar(dist));
    camera.near = Math.max(raio / 200, 0.01);
    camera.far = raio * 200;
    camera.updateProjectionMatrix();
    controles.target.set(0, 0, 0);
    controles.update();
    precisa = true;
  }

  const api = {
    nivel,
    renderer,
    camera,
    controles,
    get modelo() { return modelo; },
    carregar(obj, { reenquadrar } = {}) {
      const primeiro = !modelo;
      const raioAntigo = raio;
      if (modelo) { raiz.remove(modelo); descartar(modelo); }
      modelo = obj;
      obj.traverse((m) => {
        if (!m.isMesh) return;
        const antigo = m.material;
        if (nivel !== 'baixo' && antigo && !antigo.isMeshPhysicalMaterial) {
          m.material = new THREE.MeshPhysicalMaterial({
            color: antigo.color, metalness: antigo.metalness ?? 0, roughness: antigo.roughness ?? 0.45,
            map: antigo.map || null, vertexColors: !!antigo.vertexColors,
            clearcoat: antigo.map ? op.verniz * 0.4 : op.verniz, clearcoatRoughness: 0.28,
          });
          antigo.dispose();
        }
        m.castShadow = m.receiveShadow = renderer.shadowMap.enabled;
      });
      const caixa = new THREE.Box3().setFromObject(obj);
      const centro = caixa.getCenter(new THREE.Vector3());
      obj.position.sub(centro);
      raiz.add(obj);
      raio = Math.max(caixa.getSize(new THREE.Vector3()).length() / 2, 1e-3);
      luz.position.set(raio * 1.2, raio * 1.8, raio * 2.4);
      contra.position.set(-raio * 2, -raio * 0.6, -raio * 1.5);
      const sc = luz.shadow.camera;
      sc.left = sc.bottom = -raio * 1.3;
      sc.right = sc.top = raio * 1.3;
      sc.near = raio * 0.1;
      sc.far = raio * 8;
      sc.updateProjectionMatrix();
      controles.minDistance = raio * 0.4;
      controles.maxDistance = raio * 12;
      // modelo novo ou de tamanho bem diferente: enquadra de novo; senão mantém a câmera
      if (primeiro || reenquadrar || Math.abs(Math.log(raio / raioAntigo)) > 0.35) enquadrar(op.vista || 'iso');
      precisa = true;
      return api;
    },
    enquadrar,
    limpar() {
      if (modelo) { raiz.remove(modelo); descartar(modelo); }
      modelo = null;
      precisa = true;
    },
    definirCores(mapa) {
      if (!modelo) return;
      modelo.traverse((m) => {
        if (!m.isMesh) return;
        const ids = idsDe(m);
        const cor = ids.map((i) => mapa[i]).find(Boolean);
        if (cor && !m.material.map) m.material.color.set(cor);
      });
      precisa = true;
    },
    destacar(ids) {
      const alvo = new Set((ids || []).map(Number));
      if (!modelo) return;
      modelo.traverse((m) => {
        if (!m.isMesh || !m.material.emissive) return;
        const sel = idsDe(m).some((i) => alvo.has(i));
        m.material.emissive.setHex(sel ? 0x2a2a2a : 0x000000);
      });
      precisa = true;
    },
    autoRotacao(sim) { controles.autoRotate = !!sim && !reduzido; precisa = true; },
    wireframe(sim) {
      if (!modelo) return;
      modelo.traverse((m) => { if (m.isMesh) m.material.wireframe = !!sim; });
      precisa = true;
    },
    capturar() { renderer.render(cena, camera); return canvas.toDataURL('image/png'); },
    estatisticas() {
      let tri = 0, malhas = 0;
      if (modelo) modelo.traverse((m) => {
        if (!m.isMesh) return;
        malhas++;
        const g = m.geometry;
        tri += (g.index ? g.index.count : g.attributes.position.count) / 3;
      });
      return { triangulos: Math.round(tri), malhas, nivel };
    },
    aoTocar(cb) {
      let ini = null;
      const ray = new THREE.Raycaster();
      const pd = (e) => { ini = { x: e.clientX, y: e.clientY, t: performance.now() }; };
      const pu = (e) => {
        if (!ini || !modelo) return;
        const mov = Math.hypot(e.clientX - ini.x, e.clientY - ini.y);
        if (mov > 5 || performance.now() - ini.t > 600) return;
        const r = canvas.getBoundingClientRect();
        ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
        const hit = ray.intersectObject(modelo, true)[0];
        if (!hit) { cb(null, e); return; }
        const local = modelo.worldToLocal(hit.point.clone());
        cb({ ids: idsDe(hit.object), x: local.x, y: local.y, z: local.z }, e);
      };
      canvas.addEventListener('pointerdown', pd);
      canvas.addEventListener('pointerup', pu);
    },
    pedirQuadro() { precisa = true; },
    destruir() {
      renderer.setAnimationLoop(null);
      if (io) io.disconnect();
      if (ro) ro.disconnect(); else window.removeEventListener('resize', ajustar);
      document.removeEventListener('visibilitychange', aoVisibilidade);
      controles.dispose();
      if (modelo) descartar(modelo);
      ambiente.dispose();
      pmrem.dispose();
      renderer.dispose();
      canvas.remove();
    },
  };
  return api;
}

function idsDe(obj) {
  for (let o = obj; o; o = o.parent) {
    const m = /peca_([\d-]+)/.exec(o.name || '');
    if (m) return m[1].split('-').map(Number);
  }
  return [];
}

/* ---------- Embed (código copia-e-cola) ---------- */
const CSS_EMBED = `
.v3d-ui{position:absolute;inset:auto 10px 10px auto;display:flex;gap:6px;z-index:2}
.v3d-ui button{font:600 12px/1 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:8px 11px;border-radius:9px;border:1px solid rgba(255,255,255,.18);background:rgba(15,17,21,.72);color:#f1f5f9;cursor:pointer;backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
.v3d-ui button:hover{background:rgba(30,34,41,.9)}
.v3d-ui button:focus-visible{outline:2px solid #38bdf8;outline-offset:2px}
.v3d-dica{position:absolute;left:50%;bottom:12px;transform:translateX(-50%);font:500 12px/1.3 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#e2e8f0;background:rgba(15,17,21,.6);padding:6px 10px;border-radius:999px;pointer-events:none;transition:opacity .4s;white-space:nowrap;z-index:1}
.v3d-msg{position:absolute;inset:0;display:grid;place-items:center;font:500 13px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#94a3b8;text-align:center;padding:16px}
@media (max-width:480px){.v3d-ui button{padding:7px 9px}.v3d-dica{font-size:11px}}
@media (prefers-reduced-motion:reduce){.v3d-dica{transition:none}}`;

function estiloEmbed() {
  if (document.getElementById('v3d-estilo')) return;
  const s = document.createElement('style');
  s.id = 'v3d-estilo';
  s.textContent = CSS_EMBED;
  document.head.appendChild(s);
}

function baixarBlob(dados, nome, tipo) {
  const url = URL.createObjectURL(new Blob([dados], { type: tipo || 'application/octet-stream' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

const EXT_EXTRA = { stl: ['stl', 'model/stl'], obj: ['zip', 'application/zip'], '3mf': ['3mf', 'model/3mf'], ply: ['ply', 'application/octet-stream'] };

export function iniciarEmbed(el, dados, opcoes = {}) {
  estiloEmbed();
  let api = null;
  let vivo = true;
  let io = null;
  const criados = [];
  const msg = document.createElement('div');
  criados.push(msg);
  msg.className = 'v3d-msg';
  msg.textContent = 'Carregando modelo 3D…';
  el.appendChild(msg);
  const nome = (opcoes.nome || 'modelo').replace(/[^\w\-]+/g, '_');

  async function comecar() {
    try {
      api = montar(el, opcoes);
      let obj;
      let glb = null;
      if (dados.glb) {
        glb = await decodificar(dados.glb);
        obj = await carregarGLB(glb.slice(0));
      } else {
        const texto = new TextDecoder().decode(await decodificar(dados.receita));
        obj = construirReceita(JSON.parse(texto), api.nivel);
      }
      if (!vivo) { api.destruir(); return; }
      api.carregar(obj);
      msg.remove();
      const dica = document.createElement('div');
      criados.push(dica);
      dica.className = 'v3d-dica';
      dica.textContent = 'Arraste para girar · role ou pince para zoom';
      el.appendChild(dica);
      const sumir = () => { dica.style.opacity = '0'; setTimeout(() => dica.remove(), 500); };
      api.renderer.domElement.addEventListener('pointerdown', sumir, { once: true });
      api.renderer.domElement.addEventListener('wheel', sumir, { once: true, passive: true });
      if (opcoes.botaoBaixar !== false) {
        const ui = document.createElement('div');
        criados.push(ui);
        ui.className = 'v3d-ui';
        const botao = (rotulo, titulo, acao) => {
          const b = document.createElement('button');
          b.type = 'button';
          b.textContent = rotulo;
          b.title = titulo;
          b.addEventListener('click', acao);
          ui.appendChild(b);
        };
        botao('GLB', 'Baixar o modelo 3D (GLB, com cores)', async () => {
          baixarBlob(glb || await exportarGLB(api.modelo), `${nome}.glb`, 'model/gltf-binary');
        });
        if (!dados.stl) botao('STL', 'Baixar para impressão 3D (STL)', () => baixarBlob(exportarSTL(api.modelo), `${nome}.stl`, 'model/stl'));
        for (const [fmt, [ext, tipo]] of Object.entries(EXT_EXTRA)) {
          if (!dados[fmt]) continue;
          botao(fmt.toUpperCase(), `Baixar ${fmt.toUpperCase()}`, async () => baixarBlob(await decodificar(dados[fmt]), `${nome}.${ext}`, tipo));
        }
        el.appendChild(ui);
      }
    } catch (e) {
      msg.textContent = /WebGL/.test(String(e)) ? 'Este navegador não consegue mostrar 3D (WebGL desligado).' : 'Não foi possível abrir o modelo 3D.';
      if (window.console) console.error('[Vetor3D]', e);
    }
  }

  if ('IntersectionObserver' in window) {
    io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { io.disconnect(); comecar(); }
    }, { rootMargin: '300px' });
    io.observe(el);
  } else {
    comecar();
  }
  return {
    destruir() {
      vivo = false;
      if (io) io.disconnect();
      if (api) api.destruir();
      criados.forEach((x) => x.remove());
    },
  };
}
