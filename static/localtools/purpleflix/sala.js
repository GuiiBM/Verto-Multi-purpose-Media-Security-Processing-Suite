// PurpleFlix · sala de cinema em 3D (Three.js + CSS3DRenderer + GSAP).
//
// O site real da PurpleFlix é um <iframe> posto na tela da sala pelo
// CSS3DRenderer, na mesma câmera do WebGL. O canvas WebGL fica por cima e
// "fura" a tela (NoBlending com alfa 0) para o iframe aparecer; o que estiver
// na frente da tela (poltronas, feixe do projetor) é desenhado por cima dele.
//
// Unidades em metros. A tela fica no plano z = 0, virada para +z; a plateia
// sobe em degraus até a parede do fundo (z ≈ 27).

import * as THREE from 'three';
import { CSS3DRenderer, CSS3DObject } from 'three/addons/renderers/CSS3DRenderer.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const gsap = window.gsap;
// as animações seguem o relógio de verdade, mesmo se a máquina engasgar
gsap?.ticker.lagSmoothing(0);
const URL_SITE = 'https://purpleflix3.vercel.app/';
const $ = (id) => document.getElementById(id);
const sala = $('sala');
const reduzido = matchMedia('(prefers-reduced-motion: reduce)').matches;
const celular = () => matchMedia('(max-width: 760px), (pointer: coarse) and (max-width: 1024px)').matches;

// ---------- medidas da sala ----------
const TELA = { w: 12, h: 12 * 9 / 16, y: 4.7 };
const SALA = { meia: 12, fundo: 27, teto: 11.6 };
const FILEIRAS = 12, PASSO_Z = 1.2, PASSO_Y = 0.34, Z0 = 6.8;
const POLTRONA = 0.6, BLOCO = 8.4;

// ---------- o iframe (sempre um só: mover um iframe no DOM recarrega a página) ----------
const moldura = document.createElement('div');
moldura.className = 'tela-site';
const iframe = document.createElement('iframe');
iframe.src = URL_SITE;
iframe.title = 'PurpleFlix';
iframe.allow = 'autoplay; fullscreen; picture-in-picture; encrypted-media';
moldura.appendChild(iframe);

const estado = { carregou: false, modo: 'poltrona', luzes: 1 };
function status(txt, on) {
  $('estado').textContent = txt;
  $('luz').className = 'luz' + (on ? ' on' : '');
}
let aoCarregar = () => {};
iframe.addEventListener('load', () => {
  estado.carregou = true;
  status('Em exibição', true);
  aoCarregar();
});
setTimeout(() => { if (!estado.carregou) status('Está demorando. Confira a internet ou abra em nova aba.'); }, 12000);

// ---------- sem WebGL: a tela em 2D, ainda bonita ----------
function telaCheia() {
  const f = iframe.requestFullscreen || iframe.webkitRequestFullscreen;
  if (!f) return;
  const r = f.call(iframe);
  if (r && r.then) r.then(() => screen.orientation?.lock?.('landscape').catch(() => {})).catch(() => {});
}
function recarregar() { estado.carregou = false; status('Recarregando a sessão…'); iframe.src = URL_SITE; }

// ---------- sem WebGL: a tela em 2D, com a mesma moldura ----------
function semWebGL() {
  document.body.classList.add('sem-3d');
  sala.appendChild(moldura);
  $('veu').classList.add('fora');
  $('assistir').onclick = telaCheia;
  $('cheia').onclick = telaCheia;
  $('recarregar').onclick = recarregar;
  $('luzes').hidden = true;
  status('Preparando a sessão…');
}
let teste = null;
try { teste = document.createElement('canvas').getContext('webgl2'); } catch {}
if (teste && gsap) iniciar3D(); else semWebGL();

function iniciar3D() {

// ---------- renderizadores ----------
const css = new CSS3DRenderer();
css.domElement.className = 'css3d';
sala.appendChild(css.domElement);

const gl = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
gl.setPixelRatio(Math.min(devicePixelRatio, 1.5));
gl.setClearColor(0x050407, 1);
gl.outputColorSpace = THREE.SRGBColorSpace;
gl.toneMapping = THREE.ACESFilmicToneMapping;
gl.toneMappingExposure = 1.05;
gl.domElement.className = 'gl';
sala.appendChild(gl.domElement);

const cena = new THREE.Scene();
cena.fog = new THREE.FogExp2(0x060509, 0.018);
const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 120);
RectAreaLightUniformsLib.init();

// ---------- texturas feitas no canvas (nada vem de fora) ----------
function textura(w, h, desenhar, repetir) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  desenhar(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  if (repetir) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...repetir); }
  return t;
}
const carpete = textura(256, 256, (g, w, h) => {
  g.fillStyle = '#120d19'; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 2600; i++) { g.fillStyle = `rgba(${90 + Math.random() * 60},${50 + Math.random() * 40},${140 + Math.random() * 60},${Math.random() * 0.06})`; g.fillRect(Math.random() * w, Math.random() * h, 1.5, 1.5); }
  g.strokeStyle = 'rgba(176,124,255,0.07)'; g.lineWidth = 2;
  for (let y = 0; y <= h; y += 64) for (let x = 0; x <= w; x += 64) { g.beginPath(); g.arc(x, y, 18, 0, Math.PI * 2); g.stroke(); }
}, [10, 14]);
const tecido = textura(128, 128, (g, w, h) => {
  g.fillStyle = '#16111e'; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 1600; i++) { g.fillStyle = `rgba(255,255,255,${Math.random() * 0.025})`; g.fillRect(Math.random() * w, Math.random() * h, 1, 2); }
}, [1, 3]);
const placaSaida = textura(256, 96, (g, w, h) => {
  g.fillStyle = '#04150b'; g.fillRect(0, 0, w, h);
  g.strokeStyle = '#1f8f52'; g.lineWidth = 4; g.strokeRect(4, 4, w - 8, h - 8);
  g.fillStyle = '#5dffa6'; g.font = '700 46px Geist, Arial, sans-serif'; g.textBaseline = 'middle';
  g.fillText('SAÍDA', 26, h / 2 + 2);
  g.beginPath(); g.moveTo(206, 30); g.lineTo(232, 48); g.lineTo(206, 66); g.lineWidth = 8; g.strokeStyle = '#5dffa6'; g.stroke();
});

// ---------- materiais ----------
const M = {
  parede: new THREE.MeshStandardMaterial({ color: 0x0c0a10, roughness: 0.96 }),
  painel: new THREE.MeshStandardMaterial({ color: 0x1b1424, map: tecido, roughness: 0.92 }),
  teto: new THREE.MeshStandardMaterial({ color: 0x060509, roughness: 1 }),
  carpete: new THREE.MeshStandardMaterial({ color: 0xffffff, map: carpete, roughness: 1 }),
  degrau: new THREE.MeshStandardMaterial({ color: 0x0e0b13, roughness: 0.9 }),
  preto: new THREE.MeshStandardMaterial({ color: 0x030304, roughness: 1 }),
  veludo: new THREE.MeshPhysicalMaterial({ color: 0x3d1260, roughness: 0.82, sheen: 1, sheenColor: new THREE.Color(0xc89bff), sheenRoughness: 0.42 }),
  cortina: new THREE.MeshPhysicalMaterial({ color: 0x2c0b4a, roughness: 0.78, sheen: 1, sheenColor: new THREE.Color(0xd8b0ff), sheenRoughness: 0.35, side: THREE.DoubleSide }),
  braco: new THREE.MeshStandardMaterial({ color: 0x141118, roughness: 0.42, metalness: 0.25 }),
  palco: new THREE.MeshStandardMaterial({ color: 0x0d0a11, roughness: 0.55, metalness: 0.1 }),
  ouro: new THREE.MeshStandardMaterial({ color: 0x8a6a3a, emissive: 0x3a2610, roughness: 0.35, metalness: 0.9 }),
};
function caixa(w, h, d, mat, x, y, z, pai = cena) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z); pai.add(m); return m;
}

// ---------- paredes, teto, chão ----------
caixa(SALA.meia * 2, SALA.teto + 1, 0.4, M.parede, 0, SALA.teto / 2, -0.6);                 // parede da tela
caixa(SALA.meia * 2, SALA.teto + 1, 0.4, M.parede, 0, SALA.teto / 2, SALA.fundo + 0.2);      // fundo
for (const s of [-1, 1]) caixa(0.4, SALA.teto + 1, SALA.fundo + 1, M.parede, s * (SALA.meia + 0.2), SALA.teto / 2, SALA.fundo / 2);
caixa(SALA.meia * 2 + 1, 0.3, SALA.fundo + 1, M.teto, 0, SALA.teto + 0.15, SALA.fundo / 2);
const chao = new THREE.Mesh(new THREE.PlaneGeometry(SALA.meia * 2, SALA.fundo), M.carpete);
chao.rotation.x = -Math.PI / 2; chao.position.set(0, 0, SALA.fundo / 2); cena.add(chao);

// painéis acústicos nas laterais (ritmo vertical) e arandelas entre eles
const arandelas = [];
for (const s of [-1, 1]) {
  for (let z = 3.2, i = 0; z < SALA.fundo - 1; z += 2.05, i++) {
    const p = caixa(0.14, 7.4, 1.82, M.painel, s * (SALA.meia - 0.08), 5.1 + (i % 2) * 0.05, z);
    p.rotation.y = s * 0.004 * (i % 3 - 1);
    if (i % 3 === 1) {
      const a = caixa(0.1, 0.42, 0.22, new THREE.MeshBasicMaterial({ color: 0xffb46b }), s * (SALA.meia - 0.2), 2.6 + (z - Z0) * 0.34 * 0.5, z + 1.03);
      arandelas.push(a);
    }
  }
}
// faixa dourada fina na altura dos painéis (detalhe de sala de luxo)
for (const s of [-1, 1]) caixa(0.04, 0.03, SALA.fundo - 2, M.ouro, s * (SALA.meia - 0.17), 8.86, SALA.fundo / 2 + 1);

// brilho das arandelas lavando a parede (planos aditivos, sem custo de luz)
const lavagem = textura(64, 256, (g, w, h) => {
  const gr = g.createRadialGradient(w / 2, h * 0.5, 2, w / 2, h * 0.5, h * 0.5);
  gr.addColorStop(0, 'rgba(255,190,120,0.9)'); gr.addColorStop(0.35, 'rgba(255,150,80,0.25)'); gr.addColorStop(1, 'rgba(255,140,60,0)');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
});
lavagem.colorSpace = THREE.SRGBColorSpace;
const matLavagem = new THREE.MeshBasicMaterial({ map: lavagem, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.55 });
for (const a of arandelas) {
  const p = new THREE.Mesh(new THREE.PlaneGeometry(1.4, 3.6), matLavagem);
  p.position.copy(a.position); p.position.x += Math.sign(a.position.x) * -0.03; p.position.y += 0.35;
  p.rotation.y = -Math.sign(a.position.x) * Math.PI / 2;
  cena.add(p);
}

// ---------- palco, moldura da tela e a tela ----------
caixa(SALA.meia * 2, 0.7, 2.6, M.palco, 0, 0.35, 1.0);
const fitaPalco = caixa(SALA.meia * 2, 0.025, 0.03, new THREE.MeshBasicMaterial({ color: 0x9b5cff }), 0, 0.69, 2.31);
const m = 0.42; // moldura de veludo preto
caixa(TELA.w + m * 2, m, 0.2, M.preto, 0, TELA.y + TELA.h / 2 + m / 2, -0.12);
caixa(TELA.w + m * 2, m, 0.2, M.preto, 0, TELA.y - TELA.h / 2 - m / 2, -0.12);
for (const s of [-1, 1]) caixa(m, TELA.h, 0.2, M.preto, s * (TELA.w / 2 + m / 2), TELA.y, -0.12);

// o "furo": onde o WebGL escreve alfa 0 e o iframe (atrás do canvas) aparece
const furo = new THREE.Mesh(new THREE.PlaneGeometry(TELA.w, TELA.h),
  new THREE.MeshBasicMaterial({ color: 0x000000, opacity: 0, transparent: true, blending: THREE.NoBlending, depthWrite: true }));
furo.position.set(0, TELA.y, 0);
furo.renderOrder = -1;
cena.add(furo);

// halo da tela na parede, por trás (anel: nada dentro do retângulo da tela)
const halo = new THREE.Mesh(new THREE.PlaneGeometry(TELA.w * 1.9, TELA.h * 2.1), new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  uniforms: { forca: { value: 0 }, cor: { value: new THREE.Color(0x8a5cff) } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
  fragmentShader: `varying vec2 vUv; uniform float forca; uniform vec3 cor;
    void main(){ vec2 p = (vUv - 0.5) * vec2(1.9, 2.1); vec2 d = max(abs(p) - vec2(0.5), 0.0);
      float k = exp(-length(d) * 5.0) * step(0.0001, length(d)); gl_FragColor = vec4(cor * k * forca, 1.0); }`,
}));
halo.position.set(0, TELA.y, -0.38);
cena.add(halo);

// ---------- cortinas de veludo (franzidas; abrir = comprimir as dobras) ----------
function geoCortina(largura, altura, dobras) {
  const g = new THREE.PlaneGeometry(largura, altura, 220, 1);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i) + largura / 2;
    p.setZ(i, 0.2 * Math.sin(x / largura * dobras * Math.PI * 2) + 0.06 * Math.sin(x / largura * dobras * 5.3));
    p.setX(i, x);
  }
  g.computeVertexNormals();
  return g;
}
const cortinas = [];
for (const s of [-1, 1]) {
  const grupo = new THREE.Group();
  grupo.position.set(s * SALA.meia, 0.7, 0.75);
  const pano = new THREE.Mesh(geoCortina(SALA.meia + 0.3, 10.2, 26), M.cortina);
  pano.position.y = 10.2 / 2;
  if (s > 0) pano.scale.x = -1;
  grupo.add(pano);
  grupo.scale.x = 1; // 1 = fechada (cobre até o meio), ~0.47 = aberta
  cena.add(grupo);
  cortinas.push(grupo);
}
// bandô (sanefa) em cima, com o friso dourado
const sanefa = new THREE.Mesh(geoCortina(SALA.meia * 2, 1.5, 60), M.cortina);
sanefa.position.set(-SALA.meia, 10.25, 0.95);
cena.add(sanefa);
caixa(SALA.meia * 2, 0.05, 0.06, M.ouro, 0, 9.5, 1.15);

// ---------- plateia em degraus, com as poltronas ----------
const assentos = [];
for (let r = 0; r < FILEIRAS; r++) {
  const z = Z0 + r * PASSO_Z, h = r * PASSO_Y;
  if (r > 0) caixa(SALA.meia * 2, h, PASSO_Z, M.degrau, 0, h / 2, z);
  for (let x = -BLOCO; x <= BLOCO + 0.001; x += POLTRONA) assentos.push([x, h, z + 0.08, r]);
}
// tapete por cima de cada degrau (a textura do carpete sobe com a plateia)
for (let r = 1; r < FILEIRAS; r++) {
  const t = new THREE.Mesh(new THREE.PlaneGeometry(SALA.meia * 2, PASSO_Z), M.carpete);
  t.rotation.x = -Math.PI / 2; t.position.set(0, r * PASSO_Y + 0.002, Z0 + r * PASSO_Z); cena.add(t);
}
// luzinhas âmbar nos degraus dos dois corredores
const luzDegrau = new THREE.InstancedMesh(new THREE.BoxGeometry(0.34, 0.03, 0.03), new THREE.MeshBasicMaterial({ color: 0xffa94d }), FILEIRAS * 4);
{
  const o = new THREE.Object3D(); let n = 0;
  for (let r = 0; r < FILEIRAS; r++) for (const x of [-9.35, -10.25, 9.35, 10.25]) {
    o.position.set(x, r * PASSO_Y + 0.05, Z0 + r * PASSO_Z - PASSO_Z / 2 + 0.03); o.updateMatrix(); luzDegrau.setMatrixAt(n++, o.matrix);
  }
}
cena.add(luzDegrau);

// a poltrona: assento + encosto em veludo, braços e apoios escuros
function pecas() {
  const vel = [], esc = [];
  const assento = new RoundedBoxGeometry(0.5, 0.17, 0.5, 3, 0.07); assento.translate(0, 0.46, -0.02); vel.push(assento);
  const encosto = new RoundedBoxGeometry(0.52, 0.8, 0.14, 3, 0.07); encosto.rotateX(0.17); encosto.translate(0, 0.9, 0.27); vel.push(encosto);
  const cabeca = new RoundedBoxGeometry(0.46, 0.2, 0.16, 3, 0.07); cabeca.rotateX(0.17); cabeca.translate(0, 1.33, 0.34); vel.push(cabeca);
  for (const s of [-1, 1]) {
    const b = new RoundedBoxGeometry(0.075, 0.07, 0.56, 2, 0.03); b.translate(s * 0.3, 0.68, 0.02); esc.push(b);
    const p = new THREE.BoxGeometry(0.06, 0.64, 0.42); p.translate(s * 0.3, 0.32, 0.05); esc.push(p);
  }
  const juntar = (gs) => mergeGeometries(gs.map((g) => (g.index ? g.toNonIndexed() : g)));
  return [juntar(vel), juntar(esc)];
}
const [geoVel, geoEsc] = pecas();
const poltronas = new THREE.InstancedMesh(geoVel, M.veludo, assentos.length);
const bracos = new THREE.InstancedMesh(geoEsc, M.braco, assentos.length);
{
  const o = new THREE.Object3D(), cor = new THREE.Color();
  assentos.forEach(([x, h, z], i) => {
    o.position.set(x, h, z);
    o.rotation.y = -x * 0.012; // a fileira abraça a tela de leve
    o.updateMatrix();
    poltronas.setMatrixAt(i, o.matrix); bracos.setMatrixAt(i, o.matrix);
    poltronas.setColorAt(i, cor.setHSL(0.76, 0.6, 0.3 + (Math.random() - 0.5) * 0.04));
  });
}
cena.add(poltronas, bracos);

// placas de saída perto do palco
for (const s of [-1, 1]) {
  const p = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.34), new THREE.MeshBasicMaterial({ map: placaSaida }));
  p.position.set(s * (SALA.meia - 0.22), 7.4, 3.1); p.rotation.y = -s * Math.PI / 2; if (s > 0) p.scale.x = -1;
  cena.add(p);
}

// ---------- céu de estrelas no teto (fibra ótica) ----------
const estrelas = (() => {
  const n = 900, pos = new Float32Array(n * 3), fase = new Float32Array(n), tam = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    pos[i * 3] = (Math.random() * 2 - 1) * (SALA.meia - 0.6);
    pos[i * 3 + 1] = SALA.teto - 0.02;
    pos[i * 3 + 2] = 2 + Math.random() * (SALA.fundo - 3);
    fase[i] = Math.random() * 6.28; tam[i] = 0.6 + Math.random() * 1.6;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('fase', new THREE.BufferAttribute(fase, 1));
  g.setAttribute('tam', new THREE.BufferAttribute(tam, 1));
  const mat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { t: { value: 0 }, brilho: { value: 1 }, px: { value: gl.getPixelRatio() } },
    vertexShader: `attribute float fase; attribute float tam; uniform float t; uniform float px; varying float a;
      void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); gl_Position = projectionMatrix * mv;
        a = 0.55 + 0.45 * sin(t * (0.6 + fase * 0.15) + fase); gl_PointSize = tam * px * (26.0 / -mv.z); }`,
    fragmentShader: `uniform float brilho; varying float a; void main(){ float d = length(gl_PointCoord - 0.5);
      float k = smoothstep(0.5, 0.0, d); gl_FragColor = vec4(vec3(1.0, 0.92, 0.85) * k * a * brilho, 1.0); }`,
  });
  const pts = new THREE.Points(g, mat); cena.add(pts); return mat;
})();

// ---------- projetor: a janela da cabine, o feixe e a poeira ----------
// soma só a cor e preserva o alfa: na frente da tela isso vira luz por cima do site
const SO_LUZ = { blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,
  blendSrcAlpha: THREE.ZeroFactor, blendDstAlpha: THREE.OneFactor };
const APICE = new THREE.Vector3(0, 9.4, SALA.fundo - 0.05);
caixa(1.4, 0.8, 0.05, new THREE.MeshBasicMaterial({ color: 0x2a1f3d }), 0, APICE.y, SALA.fundo - 0.02);
// o feixe é feito de fatias de luz suave ao longo do raio (somadas, viram névoa sem arestas)
const feixe = (() => {
  const N = 44;
  const centro = new THREE.Vector3(0, TELA.y, 0.15);
  const mat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide, ...SO_LUZ,
    uniforms: { tempo: { value: 0 }, forca: { value: 0 } },
    vertexShader: `attribute float t; varying vec2 vUv; varying float vt; void main(){ vUv = uv; vt = t;
      gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform float tempo; uniform float forca; varying vec2 vUv; varying float vt;
      void main(){
        vec2 c = abs(vUv - 0.5) * 2.0;
        float borda = (1.0 - smoothstep(0.35, 1.0, c.x)) * (1.0 - smoothstep(0.3, 1.0, c.y));
        float raios = 0.7 + 0.3 * sin(vUv.x * 23.0 + tempo * 0.25 + vt * 9.0) * sin(vUv.x * 7.0 - tempo * 0.17);
        float k = smoothstep(0.0, 0.12, vt) * (1.0 - smoothstep(0.42, 0.72, vt));
        gl_FragColor = vec4(vec3(0.8, 0.74, 1.0) * 0.016 * borda * raios * k * forca, 1.0);
      }`,
  });
  const geo = new THREE.PlaneGeometry(1, 1);
  const ts = new Float32Array(N);
  const malha = new THREE.InstancedMesh(geo, mat, N);
  const o = new THREE.Object3D();
  for (let i = 0; i < N; i++) {
    const t = (i + 0.5) / N; ts[i] = t;
    o.position.copy(APICE).lerp(centro, t);
    o.lookAt(centro);
    o.scale.set(Math.max(0.05, TELA.w * t * 1.1), Math.max(0.03, TELA.h * t * 1.1), 1);
    o.updateMatrix(); malha.setMatrixAt(i, o.matrix);
  }
  geo.setAttribute('t', new THREE.InstancedBufferAttribute(ts, 1));
  malha.frustumCulled = false;
  cena.add(malha);
  return mat;
})();
// brilho da lente na janela da cabine
const lente = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.6), new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, ...SO_LUZ,
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
  fragmentShader: 'varying vec2 vUv; void main(){ float d = length((vUv - 0.5) * vec2(1.5, 1.0)); gl_FragColor = vec4(vec3(0.85, 0.8, 1.0) * exp(-d * 9.0) * 0.9, 1.0); }',
}));
lente.position.set(0, APICE.y, SALA.fundo - 0.08); lente.rotation.y = Math.PI;
cena.add(lente);
const poeira = (() => {
  const n = 420, pos = new Float32Array(n * 3), sem = new Float32Array(n);
  const v = new THREE.Vector3();
  for (let i = 0; i < n; i++) {
    const u = Math.random(), w = Math.random(), t = 0.06 + Math.random() * 0.8;
    v.set((u - 0.5) * TELA.w, TELA.y + (w - 0.5) * TELA.h, 0.15).lerp(APICE, 1 - t);
    pos.set([v.x, v.y, v.z], i * 3); sem[i] = Math.random() * 100;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('sem', new THREE.BufferAttribute(sem, 1));
  const mat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, ...SO_LUZ,
    uniforms: { tempo: { value: 0 }, forca: { value: 0 }, px: { value: gl.getPixelRatio() } },
    vertexShader: `attribute float sem; uniform float tempo; uniform float px; varying float a;
      void main(){ vec3 p = position + vec3(sin(tempo * 0.13 + sem) * 0.25, sin(tempo * 0.09 + sem * 1.7) * 0.3, cos(tempo * 0.11 + sem) * 0.25);
        vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_Position = projectionMatrix * mv;
        a = (0.35 + 0.65 * pow(0.5 + 0.5 * sin(tempo * 0.8 + sem * 3.0), 3.0)) * smoothstep(1.5, 6.0, p.z);
        gl_PointSize = px * (0.8 + fract(sem) * 1.2) * (12.0 / -mv.z); }`,
    fragmentShader: `uniform float forca; varying float a; void main(){ float d = length(gl_PointCoord - 0.5);
      gl_FragColor = vec4(vec3(1.0, 0.95, 0.9) * smoothstep(0.5, 0.0, d) * a * 0.22 * forca, 1.0); }`,
  });
  cena.add(new THREE.Points(g, mat)); return mat;
})();

// ---------- luzes ----------
const ambiente = new THREE.HemisphereLight(0x4a3a70, 0x0a0710, 1.2);
cena.add(ambiente);
const luzTela = new THREE.RectAreaLight(0xc9b8ff, 0, TELA.w, TELA.h);
luzTela.position.set(0, TELA.y, 0.05); luzTela.lookAt(0, TELA.y, 10);
cena.add(luzTela);
// o brilho da tela chegando à plateia (recorta o topo das poltronas quando a sala apaga)
const luzPlateia = new THREE.SpotLight(0xa58bff, 0, 42, 0.95, 1, 1.1);
luzPlateia.position.set(0, TELA.y, 0.6); luzPlateia.target.position.set(0, 1.2, 18);
cena.add(luzPlateia, luzPlateia.target);
const luzCortina = new THREE.SpotLight(0xd9b2ff, 160, 34, 1.05, 1, 1.6);
luzCortina.position.set(0, 10.6, 9); luzCortina.target.position.set(0, 4.4, 0.6);
cena.add(luzCortina, luzCortina.target);
// luz da sala: arandelas quentes nas paredes, focos descendo sobre a plateia
// e a sanca (faixa de luz escondida no alto das paredes laterais)
const arandelasLuz = [], focos = [];
for (const s of [-1, 1]) for (const z of [8, 17]) {
  const p = new THREE.PointLight(0xffaa66, 0, 15, 1.5); p.position.set(s * (SALA.meia - 0.8), 3.4 + (z - Z0) * 0.17, z);
  p.userData.base = 55; cena.add(p); arandelasLuz.push(p);
}
// quatro focos no eixo da sala, da frente para o fundo (mesmo número de luzes de antes: o custo por pixel não sobe)
for (const z of [8.4, 12.6, 16.8, 21]) {
  const f = new THREE.SpotLight(0xffd2a1, 0, 18, 0.66, 0.8, 1.3);
  f.position.set(0, SALA.teto - 0.2, z); f.target.position.set(0, 0, z + 0.6);
  f.userData.base = 95; cena.add(f, f.target); focos.push(f);
}
const sanca = [];
const texSanca = textura(16, 256, (g, w, h) => {
  const gr = g.createLinearGradient(0, 0, 0, h);
  gr.addColorStop(0, 'rgba(255,196,140,0.95)'); gr.addColorStop(0.12, 'rgba(255,170,110,0.45)'); gr.addColorStop(1, 'rgba(255,150,90,0)');
  g.fillStyle = gr; g.fillRect(0, 0, w, h);
});
const matSanca = new THREE.MeshBasicMaterial({ map: texSanca, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 1 });
const matFitaSanca = new THREE.MeshBasicMaterial({ color: 0xffc58f });
for (const s of [-1, 1]) {
  const lav = new THREE.Mesh(new THREE.PlaneGeometry(SALA.fundo - 2.5, 5.2), matSanca);
  lav.position.set(s * (SALA.meia - 0.22), SALA.teto - 2.75, SALA.fundo / 2 + 1);
  lav.rotation.y = -s * Math.PI / 2;
  cena.add(lav); sanca.push(lav);
  caixa(0.05, 0.04, SALA.fundo - 2.5, matFitaSanca, s * (SALA.meia - 0.24), SALA.teto - 0.18, SALA.fundo / 2 + 1);
}
// nível de cada grupo: 1 = sala acesa (intervalo), 0 = sessão
const nivel = { arandelas: 1, sanca: 1, geral: 1, focos: focos.map((f) => ({ v: 1, z: f.position.z })) };
const corArandela = new THREE.Color();
function aplicarLuzes() {
  const a = nivel.arandelas, g = nivel.geral, c = nivel.sanca, escuro = 1 - g;
  arandelasLuz.forEach((p) => (p.intensity = p.userData.base * a));
  focos.forEach((f, i) => (f.intensity = f.userData.base * nivel.focos[i].v));
  arandelas.forEach((m) => m.material.color.copy(corArandela.setRGB(1, 0.7, 0.42).multiplyScalar(0.18 + 0.82 * a)));
  matLavagem.opacity = 0.05 + 0.75 * a;
  matSanca.opacity = c;
  matFitaSanca.color.setRGB(1, 0.77, 0.56).multiplyScalar(0.06 + 0.94 * c);
  ambiente.intensity = 0.07 + 1.1 * g;
  gl.toneMappingExposure = 0.9 + 0.16 * g;
  estrelas.uniforms.brilho.value = 0.45 + 0.95 * escuro;
  luzPlateia.intensity = luzPlateia.userData.base * (1 + 0.7 * escuro);
  luzCortina.intensity = luzCortina.userData.base * (0.3 + 0.7 * g + 0.5 * c);
  halo.material.uniforms.forca.value = halo.userData.base * (0.75 + 0.6 * escuro);
  luzDegrau.material.color.setRGB(1, 0.66, 0.3).multiplyScalar(0.7 + 0.5 * escuro);
}
luzPlateia.userData.base = 0;
luzCortina.userData.base = 160;
halo.userData.base = 0;

// ---------- o site na tela (CSS3D) ----------
const BASE_W = 1600;
const objSite = new CSS3DObject(moldura);
objSite.position.set(0, TELA.y, 0);
cena.add(objSite);
function tamanhoSite(px) {
  const w = Math.max(320, Math.round(px)), h = Math.round(w * 9 / 16);
  moldura.style.width = w + 'px'; moldura.style.height = h + 'px';
  objSite.scale.setScalar(TELA.w / w);
}
tamanhoSite(BASE_W);

// ---------- câmera: entrada, poltrona e "assistir" ----------
const alvo = new THREE.Vector3(0, TELA.y - 0.3, 0);
const cam = { x: 0, y: 8.6, z: SALA.fundo - 1.2, ax: 0, ay: TELA.y, fov: 42 };
const olhar = { x: 0, y: 0 }, olharAlvo = { x: 0, y: 0 };
let movendo = true;
function poseAssento() {
  const asp = innerWidth / Math.max(1, alturaPalco());
  // de pé no alto da plateia: as fileiras descem até o palco e a tela fica no fundo do quadro
  const r = asp < 1 ? 6 : asp < 1.4 ? 9 : 10;
  const z = Z0 + r * PASSO_Z + 0.45, y = r * PASSO_Y + 1.85;
  const dist = z;
  // retrato: a tela ocupa a largura toda; paisagem: ~46%, com a sala em volta
  const larguraVista = asp < 1 ? TELA.w * 1.12 : TELA.w / 0.5;
  const fovV = 2 * Math.atan(Math.tan(Math.atan(larguraVista / 2 / dist)) / asp) * 180 / Math.PI;
  return { x: 0, y, z, ax: 0, ay: TELA.y - (asp < 1 ? 0.6 : 1.25), fov: Math.min(78, Math.max(36, fovV)) };
}
function poseTela() {
  const asp = innerWidth / alturaPalco();
  const fov = 34, t = Math.tan(fov * Math.PI / 360);
  const margem = 0.94;
  const hNec = Math.max(TELA.h / margem, TELA.w / margem / asp);
  const dist = hNec / 2 / t;
  return { x: 0, y: TELA.y, z: dist, ax: 0, ay: TELA.y, fov };
}
function alturaPalco() { return sala.clientHeight || innerHeight; }

function aplicarCamera() {
  camera.fov = cam.fov;
  camera.position.set(cam.x + olhar.x * 0.45, cam.y + olhar.y * 0.18, cam.z);
  alvo.set(cam.ax + olhar.x * 0.9, cam.ay + olhar.y * 0.35, 0);
  camera.lookAt(alvo);
  camera.updateProjectionMatrix();
}
function ajustar() {
  const w = sala.clientWidth, h = sala.clientHeight;
  gl.setSize(w, h, false); css.setSize(w, h);
  camera.aspect = w / h;
  if (!movendo) {
    Object.assign(cam, estado.modo === 'tela' ? poseTela() : poseAssento());
    if (estado.modo === 'tela') nitido();
  }
  aplicarCamera();
  desenhar();
}
// no modo "assistir" o iframe ganha o tamanho exato em pixels que ocupa na tela:
// a página fica nítida e o site se ajusta a essa largura
function nitido(p = cam) {
  const t = Math.tan(p.fov * Math.PI / 360);
  const pxPorMetro = alturaPalco() / (2 * p.z * t);
  tamanhoSite(TELA.w * pxPorMetro);
}

// ---------- animações ----------
let rodando = false, quieto = 0, acumulado = 0;
const relogio = new THREE.Clock();
function desenhar() { gl.render(cena, camera); css.render(cena, camera); }
// roda no ticker do GSAP: as animações e o desenho acontecem no mesmo quadro
function quadro(tempo, deltaMs) {
  const dt = Math.min(0.1, deltaMs / 1000);
  const animando = movendo || tlLuzes?.isActive() || gsap.isTweening(cortinas[0].scale);
  // parado há bastante tempo, sem nada animando: 30 quadros por segundo bastam para a poeira
  if (!animando && quieto > 10) { acumulado += dt; if (acumulado < 1 / 30) return; acumulado = 0; }
  medir(deltaMs, animando);
  const t = relogio.getElapsedTime();
  if (!reduzido) { estrelas.uniforms.t.value = t; feixe.uniforms.tempo.value = t; poeira.uniforms.tempo.value = t; }
  luzTela.intensity = luzTela.userData.base * (0.94 + 0.06 * Math.sin(t * 1.3) * Math.sin(t * 0.7));
  // a cabeça segue o mouse com amortecimento (não depende da taxa de quadros)
  const k = 1 - Math.exp(-dt * 3.4);
  olhar.x += (olharAlvo.x - olhar.x) * k;
  olhar.y += (olharAlvo.y - olhar.y) * k;
  quieto += dt;
  aplicarLuzes();
  aplicarCamera();
  desenhar();
}
luzTela.userData.base = 0;
// qualidade adaptativa: se os quadros ficam pesados, a resolução do WebGL baixa um degrau
let somaMs = 0, nQuadros = 0;
function medir(ms, animando) {
  if (!(ms > 0) || ms > 250) return;
  somaMs += ms; nQuadros++;
  if (nQuadros < 90) return;
  const media = somaMs / nQuadros; somaMs = 0; nQuadros = 0;
  const dpr = gl.getPixelRatio();
  if (media > 21 && dpr > 1) { gl.setPixelRatio(Math.max(1, dpr - 0.25)); ajustar(); }
  else if (media > 30 && dpr > 0.75) { gl.setPixelRatio(0.75); ajustar(); }
}
function ligar() { if (!rodando) { rodando = true; gsap.ticker.add(quadro); } }
function desligar() { if (rodando) { rodando = false; gsap.ticker.remove(quadro); } }
document.addEventListener('visibilitychange', () => (document.hidden ? desligar() : estado.modo === 'poltrona' && ligar()));

addEventListener('pointermove', (e) => {
  if (reduzido || estado.modo !== 'poltrona' || e.pointerType === 'touch') return;
  quieto = 0;
  olharAlvo.x = (e.clientX / innerWidth - 0.5) * 2;
  olharAlvo.y = -(e.clientY / innerHeight - 0.5) * 2;
});

// luzes da sala, em sequência de cinema. Apagar: arandelas, depois os focos
// fileira por fileira da frente para o fundo, por último a sanca. Acender: o inverso.
let tlLuzes = null;
function luzes(alvo) {
  estado.luzes = alvo;
  document.body.classList.toggle('sala-escura', alvo < 0.5);
  tlLuzes?.kill();
  const d = reduzido ? 0 : 1;
  const ordem = [...nivel.focos].sort((p, q) => (alvo < 0.5 ? p.z - q.z : q.z - p.z));
  tlLuzes = gsap.timeline({ onStart: ligar, onComplete: () => { if (estado.modo === 'tela' && !movendo) { aplicarLuzes(); desenhar(); desligar(); } } });
  if (alvo < 0.5) {
    tlLuzes.to(nivel, { arandelas: 0, duration: 1.1 * d, ease: 'power2.in' }, 0)
      .to(ordem, { v: 0, duration: 0.8 * d, ease: 'power2.inOut', stagger: 0.2 * d }, 0.35 * d)
      .to(nivel, { sanca: 0, duration: 1.3 * d, ease: 'power2.inOut' }, 1.2 * d)
      .to(nivel, { geral: 0, duration: 2.4 * d, ease: 'power1.inOut' }, 0);
  } else {
    tlLuzes.to(nivel, { sanca: 1, duration: 1.1 * d, ease: 'power2.out' }, 0)
      .to(ordem, { v: 1, duration: 0.7 * d, ease: 'power2.out', stagger: 0.16 * d }, 0.3 * d)
      .to(nivel, { arandelas: 1, duration: 1 * d, ease: 'power2.out' }, 1.0 * d)
      .to(nivel, { geral: 1, duration: 2.0 * d, ease: 'power1.inOut' }, 0);
  }
  $('luzes').setAttribute('aria-pressed', String(alvo < 0.5));
  $('luzes').querySelector('span').textContent = alvo < 0.5 ? 'Acender luzes' : 'Apagar luzes';
}

let cortinasAbertas = false;
aoCarregar = () => abrirCortinas();
function abrirCortinas() {
  if (cortinasAbertas || !cortinas.length) return;
  cortinasAbertas = true;
  const dur = reduzido ? 0 : 3.4;
  cortinas.forEach((c, i) => gsap.to(c.scale, { x: 0.47, duration: dur, ease: 'power2.inOut', delay: reduzido ? 0 : 0.15 * i }));
  // a luz retangular da tela fica fraca (forte, ela marca diagonais duras nas cortinas); quem ilumina a plateia é o foco roxo
  gsap.to(luzTela.userData, { base: 1.6, duration: dur + 0.6, ease: 'power2.inOut' });
  gsap.to(luzPlateia.userData, { base: 85, duration: dur + 0.6, ease: 'power2.inOut' });
  gsap.to(halo.userData, { base: 0.55, duration: dur + 0.6, ease: 'power2.inOut' });
  gsap.to(feixe.uniforms.forca, { value: 1, duration: dur, ease: 'power1.inOut', delay: reduzido ? 0 : 0.6 });
  gsap.to(poeira.uniforms.forca, { value: 1, duration: dur, ease: 'power1.inOut', delay: reduzido ? 0 : 0.8 });
  gsap.to(luzCortina.userData, { base: 22, duration: dur, ease: 'power2.inOut' });
  gsap.to(fitaPalco.material.color, { r: 0.45, g: 0.25, b: 0.9, duration: dur });
}

function irPara(pose, dur, depois) {
  movendo = true; ligar();
  gsap.to(cam, { ...pose, duration: reduzido ? 0 : dur, ease: 'power3.inOut', overwrite: true,
    onComplete: () => { movendo = false; depois && depois(); } });
}

function assistir() {
  if (celular()) { telaCheia(); return; }
  estado.modo = 'tela';
  document.body.classList.add('assistindo');
  olharAlvo.x = olharAlvo.y = 0;
  luzes(0);
  gsap.to(feixe.uniforms.forca, { value: 0.3, duration: 1.6 });
  gsap.to(poeira.uniforms.forca, { value: 0, duration: 1.2 });
  gsap.to(halo.userData, { base: 0.22, duration: 1.6 });
  const pose = poseTela();
  // a página ganha o tamanho final já no começo do voo (o site se ajusta enquanto a câmera ainda está longe)
  nitido(pose);
  irPara(pose, 2.2, () => { aplicarCamera(); desenhar(); desligar(); });
  $('assistir').querySelector('span').textContent = 'Voltar à poltrona';
}
function voltar() {
  estado.modo = 'poltrona';
  document.body.classList.remove('assistindo');
  tamanhoSite(BASE_W);
  luzes(1);
  gsap.to([feixe.uniforms.forca, poeira.uniforms.forca], { value: 1, duration: 1.6 });
  gsap.to(halo.userData, { base: 0.55, duration: 1.6 });
  irPara(poseAssento(), 2, null);
  $('assistir').querySelector('span').textContent = 'Assistir';
}

// ---------- botões ----------
$('assistir').onclick = () => (estado.modo === 'tela' ? voltar() : assistir());
$('cheia').onclick = telaCheia;
$('recarregar').onclick = recarregar;
$('luzes').onclick = () => luzes(estado.luzes > 0.5 ? 0 : 1);
addEventListener('keydown', (e) => { if (e.key === 'Escape' && estado.modo === 'tela' && !document.fullscreenElement) voltar(); });

// ---------- começo: véu, voo pela sala e as cortinas ----------
new ResizeObserver(ajustar).observe(sala);
ajustar();
status('Preparando a sala…');
aplicarLuzes();
// compila os shaders antes de começar (sem isso a entrada engasga no primeiro segundo)
const compilar = gl.compileAsync && gl.extensions.has('KHR_parallel_shader_compile')
  ? gl.compileAsync(cena, camera) : Promise.resolve(gl.compile(cena, camera));
compilar.catch(() => {}).then(() => {
  desenhar();
  ligar();
  requestAnimationFrame(() => {
    $('veu').classList.add('fora');
    irPara(poseAssento(), 4.2, () => { if (!estado.carregou) abrirCortinas(); });
  });
});
if (location.search.includes('debug')) window.__sala = { cortinas, cam, estado, gl, luzTela, luzPlateia, luzCortina, ambiente, focos, halo, nivel, desenhar };
// sem internet o site nunca carrega: as cortinas abrem mesmo assim, depois de um tempo
setTimeout(abrirCortinas, reduzido ? 0 : 5000);
}
