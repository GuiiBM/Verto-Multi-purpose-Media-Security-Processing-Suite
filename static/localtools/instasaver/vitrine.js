// InstaSaver · vitrine em 3D: um celular realista (estrutura de metal, vidro,
// câmeras atrás, luz de estúdio) que mostra a mídia escolhida do jeito que ela
// aparece no Instagram: story em tela cheia com as barrinhas, ou post com
// cabeçalho, curtidas e legenda. Vídeos tocam na tela.
//
// A lógica do app (busca, grades, visualizador, downloads, .zip) continua no
// script da página; este módulo lê window.InstaSaver e ouve os eventos insta:*.
// Unidades em metros (o aparelho tem as medidas de um celular de 6,1").

import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const gsap = window.gsap;
const IS = window.InstaSaver;
const $ = (id) => document.getElementById(id);
const vitrine = $('vitrine');
const reduzido = matchMedia('(prefers-reduced-motion: reduce)').matches;

let ok = null;
try { ok = document.createElement('canvas').getContext('webgl2'); } catch {}
if (ok && gsap && IS && vitrine) iniciar();
else { document.body.classList.remove('com-3d'); document.body.classList.add('sem-3d'); }

function iniciar() {
gsap.ticker.lagSmoothing(0);
document.body.classList.add('com-3d');

// ---------- medidas ----------
const W = 0.715, H = 1.47, D = 0.078, R = 0.112;          // corpo
const SW = W - 0.034, SH = H - 0.034, SR = 0.094;          // tela
const ASP = SW / SH;
const CW = 900, CH = Math.round(CW / ASP);                 // canvas da interface

// ---------- renderizador ----------
const gl = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
gl.setPixelRatio(Math.min(devicePixelRatio, 2));
gl.setClearColor(0x000000, 0);
gl.outputColorSpace = THREE.SRGBColorSpace;
gl.toneMapping = THREE.ACESFilmicToneMapping;
gl.toneMappingExposure = 1.0;
gl.domElement.className = 'vit-gl';
gl.domElement.setAttribute('aria-hidden', 'true');
vitrine.prepend(gl.domElement);

const cena = new THREE.Scene();
const pmrem = new THREE.PMREMGenerator(gl);
cena.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
cena.environmentIntensity = 0.85;
const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 50);

// luz de recorte (separa o metal escuro do fundo) e uma luz principal suave
const chave = new THREE.DirectionalLight(0xffffff, 1.6); chave.position.set(2.5, 3, 4); cena.add(chave);
const recorte = new THREE.DirectionalLight(0xc9b2ff, 2.2); recorte.position.set(-3, 1.5, -2.5); cena.add(recorte);
const recorte2 = new THREE.DirectionalLight(0xffc2a8, 1.2); recorte2.position.set(3, -1, -2.5); cena.add(recorte2);

// ---------- o aparelho ----------
function retangulo(w, h, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}
const aparelho = new THREE.Group();
const giro = new THREE.Group(); // recebe os giros (entrada, troca, arrastar)
giro.add(aparelho);
cena.add(giro);

const metal = new THREE.MeshPhysicalMaterial({ color: 0x55545b, metalness: 1, roughness: 0.3, clearcoat: 0.4, clearcoatRoughness: 0.2 });
const bev = 0.012;
const geoCorpo = new THREE.ExtrudeGeometry(retangulo(W - bev * 2, H - bev * 2, R - bev), { depth: D - bev * 2, bevelEnabled: true, bevelSize: bev, bevelThickness: bev, bevelSegments: 6, curveSegments: 32 });
geoCorpo.translate(0, 0, -(D - bev * 2) / 2);
aparelho.add(new THREE.Mesh(geoCorpo, metal));

// frente: vidro preto (a borda da tela) e a ilha da câmera frontal
const vidroFrente = new THREE.Mesh(new THREE.ShapeGeometry(retangulo(W - 0.012, H - 0.012, R - 0.006), 32),
  new THREE.MeshPhysicalMaterial({ color: 0x030304, roughness: 0.04, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.02 }));
vidroFrente.position.z = D / 2 + 0.0004;
aparelho.add(vidroFrente);
const ilha = new THREE.Mesh(new THREE.ShapeGeometry(retangulo(0.19, 0.056, 0.028), 16), new THREE.MeshBasicMaterial({ color: 0x000000 }));
ilha.position.set(0, SH / 2 - 0.05, D / 2 + 0.0016);
aparelho.add(ilha);

// costas: vidro fosco, o módulo das câmeras e o flash
const costas = new THREE.Mesh(new THREE.ShapeGeometry(retangulo(W - 0.012, H - 0.012, R - 0.006), 32),
  new THREE.MeshPhysicalMaterial({ color: 0x2f2a3a, roughness: 0.42, metalness: 0.1, clearcoat: 0.6, clearcoatRoughness: 0.35 }));
costas.position.z = -D / 2 - 0.0004; costas.rotation.y = Math.PI;
aparelho.add(costas);
const modulo = new THREE.Mesh(new THREE.ExtrudeGeometry(retangulo(0.27, 0.27, 0.07), { depth: 0.008, bevelEnabled: true, bevelSize: 0.004, bevelThickness: 0.004, bevelSegments: 4, curveSegments: 24 }),
  new THREE.MeshPhysicalMaterial({ color: 0x2a2633, roughness: 0.25, metalness: 0.2, clearcoat: 1, clearcoatRoughness: 0.1 }));
modulo.position.set(-W / 2 + 0.19, H / 2 - 0.19, -D / 2 - 0.004); modulo.rotation.y = Math.PI;
aparelho.add(modulo);
const lenteMat = new THREE.MeshPhysicalMaterial({ color: 0x050507, roughness: 0.04, metalness: 0.3, clearcoat: 1, clearcoatRoughness: 0 });
const aroLente = new THREE.MeshPhysicalMaterial({ color: 0x77767d, roughness: 0.25, metalness: 1 });
for (const [x, y] of [[-0.058, 0.058], [-0.058, -0.058], [0.058, 0]]) {
  const aro = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.014, 40), aroLente);
  aro.rotation.x = Math.PI / 2; aro.position.set(modulo.position.x - x, modulo.position.y + y, -D / 2 - 0.016);
  const lente = new THREE.Mesh(new THREE.CylinderGeometry(0.038, 0.038, 0.016, 40), lenteMat);
  lente.rotation.x = Math.PI / 2; lente.position.copy(aro.position); lente.position.z -= 0.0015;
  aparelho.add(aro, lente);
}
const flash = new THREE.Mesh(new THREE.CircleGeometry(0.016, 24), new THREE.MeshPhysicalMaterial({ color: 0xf3efe6, roughness: 0.3 }));
flash.position.set(modulo.position.x + 0.058, modulo.position.y + 0.06, -D / 2 - 0.0135); flash.rotation.y = Math.PI;
aparelho.add(flash);
// botões laterais
for (const [x, y, h] of [[-1, 0.33, 0.07], [-1, 0.2, 0.12], [-1, 0.05, 0.12], [1, 0.18, 0.2]]) {
  const b = new THREE.Mesh(new THREE.BoxGeometry(0.008, h, 0.024), metal);
  b.position.set(x * (W / 2 + 0.002), y, 0); aparelho.add(b);
}

// ---------- a tela: mídia real + interface do Instagram desenhada em canvas ----------
const canvasUI = document.createElement('canvas');
canvasUI.width = CW; canvasUI.height = CH;
const ctx = canvasUI.getContext('2d');
const texUI = new THREE.CanvasTexture(canvasUI);
texUI.colorSpace = THREE.SRGBColorSpace; texUI.anisotropy = 8;
const vazio = new THREE.DataTexture(new Uint8Array([0, 0, 0, 255]), 1, 1); vazio.needsUpdate = true;
const matTela = new THREE.ShaderMaterial({
  uniforms: {
    midia: { value: vazio }, temMidia: { value: 0 }, aspMidia: { value: 1 }, rect: { value: new THREE.Vector4(0, 0, 1, 1) },
    ui: { value: texUI }, brilho: { value: 1 }, carregando: { value: 0 }, t: { value: 0 },
    tam: { value: new THREE.Vector2(SW, SH) }, raio: { value: SR },
  },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `varying vec2 vUv;
    uniform sampler2D midia; uniform float temMidia; uniform float aspMidia; uniform vec4 rect;
    uniform sampler2D ui; uniform float brilho; uniform float carregando; uniform float t; uniform vec2 tam; uniform float raio;
    float caixa(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
    void main(){
      vec2 p = (vUv - 0.5) * tam;
      if (caixa(p, tam * 0.5, raio) > 0.0) discard;
      vec2 u = vec2(vUv.x, 1.0 - vUv.y);                 // origem no topo, como o canvas
      vec3 cor = vec3(0.0);
      // a mídia, recortada para cobrir o retângulo dela (object-fit: cover)
      if (u.x >= rect.x && u.x <= rect.z && u.y >= rect.y && u.y <= rect.w) {
        vec2 l = (u - rect.xy) / (rect.zw - rect.xy);
        float aspRect = (rect.z - rect.x) * tam.x / ((rect.w - rect.y) * tam.y);
        vec2 esc = aspMidia > aspRect ? vec2(aspRect / aspMidia, 1.0) : vec2(1.0, aspMidia / aspRect);
        vec2 m = (l - 0.5) * esc + 0.5;
        cor = mix(vec3(0.02), texture2D(midia, vec2(m.x, 1.0 - m.y)).rgb, temMidia);
      }
      vec4 i = texture2D(ui, vUv);
      cor = mix(cor, i.rgb, i.a);
      // carregando: um brilho passando pelos blocos
      float onda = smoothstep(0.18, 0.0, abs(fract(u.y * 0.7 - u.x * 0.4 - t * 0.55) - 0.5));
      cor += vec3(0.012) * onda * carregando;  // linear: pouco aqui já aparece bem
      gl_FragColor = vec4(cor * brilho, 1.0);
      #include <colorspace_fragment>
    }`,
  toneMapped: false,
});
const tela = new THREE.Mesh(new THREE.PlaneGeometry(SW, SH), matTela);
tela.position.z = D / 2 + 0.0012;
aparelho.add(tela);
ilha.renderOrder = 2;

// sombra suave embaixo do aparelho flutuando
const sombraTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'); const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  gr.addColorStop(0, 'rgba(0,0,0,0.6)'); gr.addColorStop(0.55, 'rgba(0,0,0,0.25)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
})();
const sombra = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.1), new THREE.MeshBasicMaterial({ map: sombraTex, transparent: true, depthWrite: false, opacity: 0.75 }));
sombra.rotation.x = -Math.PI / 2; sombra.position.y = -H / 2 - 0.14; sombra.scale.set(1, 0.42, 1);
cena.add(sombra);

// ---------- desenho da interface ----------
const F = IS.fmt;
const BRANCO = '#fff', CINZA = 'rgba(255,255,255,0.62)';
const fonte = (peso, tam) => `${peso} ${tam}px Geist, "Segoe UI", system-ui, sans-serif`;
let imgAvatar = null, imgIcone = null;
const icone = new Image(); icone.src = '/static/localtools/apps/instasaver.webp'; icone.onload = () => { imgIcone = icone; if (!estado.perfil) desenharInicio(); };

function barraStatus(cor = BRANCO) {
  ctx.fillStyle = cor; ctx.font = fonte(600, 34); ctx.textBaseline = 'middle';
  ctx.fillText('9:41', 62, 66);
  // sinal, wi-fi e bateria
  for (let k = 0; k < 4; k++) ctx.fillRect(CW - 236 + k * 13, 76 - 8 - k * 5, 9, 8 + k * 5);
  ctx.lineWidth = 4.5; ctx.strokeStyle = cor; ctx.lineCap = 'round';
  for (const r of [10, 20]) { ctx.beginPath(); ctx.arc(CW - 158, 80, r, -Math.PI * 0.78, -Math.PI * 0.22); ctx.stroke(); }
  ctx.beginPath(); ctx.arc(CW - 158, 80, 2.5, 0, Math.PI * 2); ctx.fill();
  ctx.lineWidth = 3; ctx.strokeStyle = cor; ctx.globalAlpha = 0.55; arredondado(CW - 128, 54, 58, 26, 8); ctx.stroke(); ctx.globalAlpha = 1;
  arredondado(CW - 124, 58, 44, 18, 5); ctx.fill();
}
function arredondado(x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function avatar(x, y, r, anel) {
  if (anel) {
    const g = ctx.createLinearGradient(x - r, y + r, x + r, y - r);
    g.addColorStop(0, '#feda75'); g.addColorStop(0.35, '#fa7e1e'); g.addColorStop(0.6, '#d62976'); g.addColorStop(0.85, '#962fbf'); g.addColorStop(1, '#4f5bd5');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r + 5, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#000'; ctx.beginPath(); ctx.arc(x, y, r + 1.5, 0, Math.PI * 2); ctx.fill();
  }
  ctx.save(); ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.clip();
  if (imgAvatar) ctx.drawImage(imgAvatar, x - r, y - r, r * 2, r * 2); else { ctx.fillStyle = '#2a2730'; ctx.fillRect(x - r, y - r, r * 2, r * 2); }
  ctx.restore();
}
function linhaTexto(txt, x, y, larg, linhas, alt) {
  const palavras = String(txt || '').split(/\s+/); let linha = '', n = 0;
  for (const p of palavras) {
    const t = linha ? linha + ' ' + p : p;
    if (ctx.measureText(t).width > larg && linha) {
      n++; if (n >= linhas) { ctx.fillText(linha.replace(/\s*\S*$/, '') + '…', x, y); return y + alt; }
      ctx.fillText(linha, x, y); y += alt; linha = p;
    } else linha = t;
  }
  if (linha) ctx.fillText(linha, x, y);
  return y + alt;
}
function icCoracao(x, y, s) { ctx.beginPath(); ctx.moveTo(x, y + s * 0.3); ctx.bezierCurveTo(x, y - s * 0.1, x - s * 0.55, y - s * 0.15, x - s * 0.55, y + s * 0.18); ctx.bezierCurveTo(x - s * 0.55, y + s * 0.5, x - s * 0.1, y + s * 0.72, x, y + s * 0.85); ctx.bezierCurveTo(x + s * 0.1, y + s * 0.72, x + s * 0.55, y + s * 0.5, x + s * 0.55, y + s * 0.18); ctx.bezierCurveTo(x + s * 0.55, y - s * 0.15, x, y - s * 0.1, x, y + s * 0.3); ctx.stroke(); }
function icBalao(x, y, s) { ctx.beginPath(); ctx.arc(x, y + s * 0.38, s * 0.44, Math.PI * 0.75, Math.PI * 2.55); ctx.lineTo(x - s * 0.42, y + s * 0.85); ctx.closePath(); ctx.stroke(); }
function icEnviar(x, y, s) { ctx.beginPath(); ctx.moveTo(x - s * 0.5, y); ctx.lineTo(x + s * 0.5, y); ctx.lineTo(x + s * 0.05, y + s * 0.9); ctx.lineTo(x - s * 0.08, y + s * 0.38); ctx.closePath(); ctx.moveTo(x - s * 0.08, y + s * 0.38); ctx.lineTo(x + s * 0.5, y); ctx.stroke(); }
function icSalvar(x, y, s) { ctx.beginPath(); ctx.moveTo(x - s * 0.36, y); ctx.lineTo(x + s * 0.36, y); ctx.lineTo(x + s * 0.36, y + s * 0.9); ctx.lineTo(x, y + s * 0.62); ctx.lineTo(x - s * 0.36, y + s * 0.9); ctx.closePath(); ctx.stroke(); }

function desenharInicio() {
  ctx.clearRect(0, 0, CW, CH);
  const g = ctx.createLinearGradient(0, 0, 0, CH);
  g.addColorStop(0, '#16121d'); g.addColorStop(1, '#0b0a0f');
  ctx.fillStyle = g; ctx.fillRect(0, 0, CW, CH);
  barraStatus();
  const cx = CW / 2, cy = CH * 0.4, r = 120;
  const a = ctx.createLinearGradient(cx - r, cy + r, cx + r, cy - r);
  a.addColorStop(0, '#feda75'); a.addColorStop(0.35, '#fa7e1e'); a.addColorStop(0.6, '#d62976'); a.addColorStop(0.85, '#962fbf'); a.addColorStop(1, '#4f5bd5');
  ctx.strokeStyle = a; ctx.lineWidth = 10; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
  if (imgIcone) ctx.drawImage(imgIcone, cx - r * 0.8, cy - r * 0.8, r * 1.6, r * 1.6);
  ctx.textAlign = 'center'; ctx.fillStyle = BRANCO; ctx.font = fonte(700, 52);
  ctx.fillText('InstaSaver', cx, cy + r + 90);
  ctx.fillStyle = CINZA; ctx.font = fonte(400, 34);
  ctx.fillText('Cole um link na busca', cx, cy + r + 150);
  ctx.fillText('e a mídia aparece aqui.', cx, cy + r + 196);
  ctx.textAlign = 'left';
  matTela.uniforms.temMidia.value = 0; matTela.uniforms.rect.value.set(0, 0, 0, 0);
  texUI.needsUpdate = true;
}
function desenharCarregando(usuario) {
  ctx.clearRect(0, 0, CW, CH);
  ctx.fillStyle = '#0d0c11'; ctx.fillRect(0, 0, CW, CH);
  barraStatus();
  ctx.fillStyle = 'rgba(255,255,255,0.08)';
  ctx.beginPath(); ctx.arc(96, 210, 44, 0, Math.PI * 2); ctx.fill();
  arredondado(162, 186, 260, 22, 11); ctx.fill(); arredondado(162, 222, 160, 18, 9); ctx.fill();
  arredondado(0, 290, CW, CW * 1.1, 0); ctx.fill();
  for (let k = 0; k < 3; k++) { arredondado(48, 290 + CW * 1.1 + 60 + k * 54, CW - 96 - k * 140, 24, 12); ctx.fill(); }
  ctx.fillStyle = CINZA; ctx.font = fonte(500, 34); ctx.textAlign = 'center';
  ctx.fillText(usuario ? `Buscando ${usuario}…` : 'Buscando no Instagram…', CW / 2, CH - 140);
  ctx.textAlign = 'left';
  matTela.uniforms.temMidia.value = 0; matTela.uniforms.rect.value.set(0, 0, 0, 0);
  texUI.needsUpdate = true;
}
function desenharStory(it, total) {
  ctx.clearRect(0, 0, CW, CH);
  const sombraTopo = ctx.createLinearGradient(0, 0, 0, 380);
  sombraTopo.addColorStop(0, 'rgba(0,0,0,0.55)'); sombraTopo.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = sombraTopo; ctx.fillRect(0, 0, CW, 380);
  const sombraBase = ctx.createLinearGradient(0, CH - 300, 0, CH);
  sombraBase.addColorStop(0, 'rgba(0,0,0,0)'); sombraBase.addColorStop(1, 'rgba(0,0,0,0.5)');
  ctx.fillStyle = sombraBase; ctx.fillRect(0, CH - 300, CW, 300);
  barraStatus();
  // barrinhas do story
  const n = Math.min(total, 40), m = 22, gap = 6, w = (CW - m * 2 - gap * (n - 1)) / n;
  for (let k = 0; k < n; k++) {
    ctx.fillStyle = k <= it.i ? BRANCO : 'rgba(255,255,255,0.38)';
    arredondado(m + k * (w + gap), 128, w, 6, 3); ctx.fill();
  }
  avatar(70, 196, 38, false);
  ctx.fillStyle = BRANCO; ctx.font = fonte(650, 32); ctx.textBaseline = 'middle';
  const nome = it.kind === 'destaque' ? (it.titulo || 'Destaque') : IS.state.profile.username;
  ctx.fillText(nome, 124, 196);
  const quando = it.m.taken_at ? (it.kind === 'story' ? F.ago(it.m.taken_at) : new Date(it.m.taken_at * 1000).toLocaleDateString('pt-BR')) : '';
  ctx.fillStyle = CINZA; ctx.font = fonte(400, 30);
  ctx.fillText(quando, 124 + ctx.measureText(nome).width * (32 / 30) + 22, 196);
  ctx.fillStyle = BRANCO; for (const dx of [-14, 0, 14]) { ctx.beginPath(); ctx.arc(CW - 112 + dx, 196, 4.5, 0, Math.PI * 2); ctx.fill(); }
  ctx.lineWidth = 4.5; ctx.strokeStyle = BRANCO; ctx.beginPath(); ctx.moveTo(CW - 66, 182); ctx.lineTo(CW - 40, 208); ctx.moveTo(CW - 40, 182); ctx.lineTo(CW - 66, 208); ctx.stroke();
  // base: caixa de mensagem
  ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,0.7)';
  arredondado(36, CH - 150, CW - 230, 84, 42); ctx.stroke();
  ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.font = fonte(400, 30); ctx.fillText('Enviar mensagem', 72, CH - 108);
  ctx.lineWidth = 4.5; ctx.strokeStyle = BRANCO; icCoracao(CW - 142, CH - 126, 46); icEnviar(CW - 62, CH - 130, 50);
  matTela.uniforms.rect.value.set(0, 0, 1, 1);
  texUI.needsUpdate = true;
}
function desenharPost(it) {
  const p = it.post, u = IS.state.profile.username;
  ctx.clearRect(0, 0, CW, CH);
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, CW, CH);
  barraStatus();
  // cabeçalho "Posts"
  ctx.lineWidth = 5; ctx.strokeStyle = BRANCO; ctx.beginPath(); ctx.moveTo(62, 140); ctx.lineTo(42, 160); ctx.lineTo(62, 180); ctx.stroke();
  ctx.fillStyle = BRANCO; ctx.font = fonte(700, 36); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('Posts', CW / 2, 160); ctx.textAlign = 'left';
  // autor
  avatar(70, 252, 32, IS.state.stories.length > 0);
  ctx.fillStyle = BRANCO; ctx.font = fonte(650, 30); ctx.fillText(u, 120, 252);
  ctx.fillStyle = BRANCO; for (const dx of [-14, 0, 14]) { ctx.beginPath(); ctx.arc(CW - 60 + dx, 252, 4.5, 0, Math.PI * 2); ctx.fill(); }
  // área da mídia (transparente: o shader desenha a foto/vídeo aí)
  const asp = Math.min(1.25, Math.max(0.8, it.aspecto || 0.8));
  const y0 = 304, h = Math.round(CW / asp);
  ctx.clearRect(0, y0, CW, h);
  if (p.media.length > 1) {
    ctx.fillStyle = 'rgba(0,0,0,0.55)'; arredondado(CW - 120, y0 + 26, 92, 50, 25); ctx.fill();
    ctx.fillStyle = BRANCO; ctx.font = fonte(600, 26); ctx.textAlign = 'center'; ctx.fillText(`1/${p.media.length}`, CW - 74, y0 + 52); ctx.textAlign = 'left';
  }
  let y = y0 + h + 42;
  ctx.lineWidth = 4.5; ctx.strokeStyle = BRANCO; ctx.lineJoin = 'round';
  icCoracao(58, y - 4, 48); icBalao(140, y - 4, 48); icEnviar(222, y, 48); icSalvar(CW - 52, y, 48);
  if (p.media.length > 1) for (let k = 0; k < Math.min(p.media.length, 10); k++) {
    ctx.fillStyle = k === 0 ? '#3897f0' : 'rgba(255,255,255,0.35)'; ctx.beginPath(); ctx.arc(CW / 2 - (Math.min(p.media.length, 10) - 1) * 9 + k * 18, y + 16, 5, 0, Math.PI * 2); ctx.fill();
  }
  y += 84;
  ctx.fillStyle = BRANCO; ctx.font = fonte(650, 30);
  if (p.like_count != null) { ctx.fillText(`${F.num(p.like_count)} curtidas`, 36, y); y += 48; }
  if (p.caption) {
    ctx.font = fonte(650, 30); const larg = ctx.measureText(u + ' ').width;
    ctx.fillText(u, 36, y);
    ctx.font = fonte(400, 30); y = linhaTexto(p.caption, 36 + larg, y, CW - 72 - larg, 1, 42);
    ctx.font = fonte(400, 30); ctx.fillStyle = BRANCO;
  }
  if (p.comment_count) { ctx.fillStyle = CINZA; ctx.font = fonte(400, 28); ctx.fillText(`Ver todos os ${F.num(p.comment_count)} comentários`, 36, y); y += 44; }
  if (p.taken_at) { ctx.fillStyle = 'rgba(255,255,255,0.45)'; ctx.font = fonte(400, 24); ctx.fillText(new Date(p.taken_at * 1000).toLocaleDateString('pt-BR', { day: 'numeric', month: 'long' }), 36, y); }
  // barra de navegação do app
  ctx.fillStyle = '#000'; ctx.fillRect(0, CH - 140, CW, 140);
  ctx.strokeStyle = 'rgba(255,255,255,0.12)'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(0, CH - 140); ctx.lineTo(CW, CH - 140); ctx.stroke();
  ctx.strokeStyle = BRANCO; ctx.lineWidth = 4.5;
  const yb = CH - 92, xs = [110, 280, 450, 620, 790];
  ctx.beginPath(); ctx.moveTo(xs[0] - 26, yb + 26); ctx.lineTo(xs[0] - 26, yb - 4); ctx.lineTo(xs[0], yb - 26); ctx.lineTo(xs[0] + 26, yb - 4); ctx.lineTo(xs[0] + 26, yb + 26); ctx.closePath(); ctx.stroke();
  ctx.beginPath(); ctx.arc(xs[1] - 4, yb - 4, 20, 0, Math.PI * 2); ctx.moveTo(xs[1] + 11, yb + 11); ctx.lineTo(xs[1] + 26, yb + 26); ctx.stroke();
  arredondado(xs[2] - 26, yb - 26, 52, 52, 14); ctx.stroke(); ctx.beginPath(); ctx.moveTo(xs[2], yb - 12); ctx.lineTo(xs[2], yb + 12); ctx.moveTo(xs[2] - 12, yb); ctx.lineTo(xs[2] + 12, yb); ctx.stroke();
  arredondado(xs[3] - 26, yb - 26, 52, 52, 14); ctx.stroke(); ctx.beginPath(); ctx.moveTo(xs[3] - 6, yb - 10); ctx.lineTo(xs[3] + 10, yb); ctx.lineTo(xs[3] - 6, yb + 10); ctx.closePath(); ctx.stroke();
  avatar(xs[4], yb, 24, false);
  matTela.uniforms.rect.value.set(0, y0 / CH, 1, (y0 + h) / CH);
  texUI.needsUpdate = true;
}

// ---------- estado e seleção ----------
const estado = { perfil: null, aba: null, itens: [], i: -1, visor: false, som: false };
function itensDaAba(aba) {
  const s = IS.state;
  if (aba === 'stories') return s.stories.map((m, i) => ({ kind: 'story', m, i }));
  if (aba === 'highlights') {
    const hl = s.hlCache.get(s.hlCurrent);
    return hl ? hl.items.map((m, i) => ({ kind: 'destaque', m, i, titulo: hl.title })) : [];
  }
  return s.posts.map((p, i) => ({ kind: 'post', m: p.media[0] || {}, post: p, i }));
}
const GRADE = { stories: 'gridStories', highlights: 'gridHighlight', posts: 'gridPosts' };

const cache = new Map();
const loader = new THREE.TextureLoader();
function textura(url) {
  if (cache.has(url)) return cache.get(url);
  const pr = new Promise((ok) => loader.load(url, (t) => { t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; ok(t); }, undefined, () => ok(null)));
  cache.set(url, pr);
  if (cache.size > 40) cache.delete(cache.keys().next().value);
  return pr;
}

let video = null;
function pararVideo() {
  if (!video) return;
  video.el.pause(); video.el.removeAttribute('src'); video.el.load(); video.tex.dispose(); video = null;
  somDisponivel(false);
}
let seqTroca = 0;
async function mostrar(i, animar = true) {
  const it = estado.itens[i];
  if (!it) { estado.i = -1; vazioDaAba(); return; }
  estado.i = i;
  const minha = ++seqTroca;
  marcarCard();
  atualizarBarra();
  pararVideo();
  const m = it.m;
  const urlImg = m.type === 'video' ? (m.thumb || m.cover) : (m.url || m.thumb);
  const carregar = urlImg ? textura(IS.proxied(urlImg)) : Promise.resolve(null);
  // giro curto: a tela escurece, o conteúdo troca e o aparelho volta
  const fora = animar && !reduzido ? gsap.timeline()
    .to(matTela.uniforms.brilho, { value: 0.18, duration: 0.2, ease: 'power2.in' }, 0)
    .to(troca, { v: 1, duration: 0.24, ease: 'power2.in' }, 0) : null;
  const tex = await carregar;
  if (fora) await fora;
  if (minha !== seqTroca) return;
  const asp = tex && tex.image ? tex.image.width / tex.image.height : (it.kind === 'post' ? 0.8 : 9 / 16);
  it.aspecto = asp;
  matTela.uniforms.midia.value = tex || vazio;
  matTela.uniforms.temMidia.value = tex ? 1 : 0;
  matTela.uniforms.aspMidia.value = asp;
  if (it.kind === 'post') desenharPost(it); else desenharStory(it, estado.itens.length);
  if (m.type === 'video' && m.url) tocar(m, minha);
  if (animar && !reduzido) {
    gsap.timeline().to(troca, { v: 0, duration: 0.6, ease: 'expo.out' }, 0)
      .to(matTela.uniforms.brilho, { value: 1, duration: 0.45, ease: 'power2.out' }, 0.05);
  } else { troca.v = 0; matTela.uniforms.brilho.value = 1; }
  acordar();
}
function tocar(m, minha) {
  const el = document.createElement('video');
  el.muted = !estado.som; el.loop = true; el.playsInline = true; el.preload = 'auto';
  el.src = IS.proxied(m.url);
  el.play().then(() => {
    if (minha !== seqTroca) { el.pause(); return; }
    const t = new THREE.VideoTexture(el); t.colorSpace = THREE.SRGBColorSpace;
    matTela.uniforms.midia.value = t; matTela.uniforms.temMidia.value = 1;
    matTela.uniforms.aspMidia.value = el.videoWidth / el.videoHeight || matTela.uniforms.aspMidia.value;
    video = { el, tex: t };
    somDisponivel(true);
    acordar();
  }).catch(() => {});
}
function vazioDaAba() {
  ctx.clearRect(0, 0, CW, CH); ctx.fillStyle = '#0d0c11'; ctx.fillRect(0, 0, CW, CH); barraStatus();
  ctx.fillStyle = CINZA; ctx.font = fonte(500, 36); ctx.textAlign = 'center';
  const s = IS.state;
  const msg = estado.aba === 'stories' ? ['Sem stories', 'nas últimas 24 horas.'] : estado.aba === 'highlights' ? (s.highlights.length ? ['Escolha um destaque', 'na lista ao lado.'] : ['Nenhum destaque.']) : ['Nenhum post disponível.'];
  msg.forEach((l, k) => ctx.fillText(l, CW / 2, CH * 0.45 + k * 52));
  ctx.textAlign = 'left';
  matTela.uniforms.temMidia.value = 0; matTela.uniforms.rect.value.set(0, 0, 0, 0); texUI.needsUpdate = true;
  atualizarBarra(); marcarCard(); acordar();
}
function marcarCard() {
  document.querySelectorAll('.card.sel').forEach((c) => c.classList.remove('sel'));
  const g = $(GRADE[estado.aba]);
  const el = g && estado.i >= 0 ? g.children[estado.i] : null;
  if (el) { el.classList.add('sel'); el.scrollIntoView({ block: 'nearest', behavior: reduzido ? 'auto' : 'smooth' }); }
}
// a barra segue sempre o mesmo formato, para todo tipo de mídia:
// 1ª linha o tipo, 2ª linha "mídia · quando · números"; contador "n / total";
// e os mesmos três botões no mesmo lugar (Som, Ampliar, Baixar), que só se
// desativam quando não se aplicam, nunca somem
function atualizarBarra() {
  const it = estado.itens[estado.i];
  $('vitBarra').hidden = !estado.perfil;
  $('vitBarra').classList.toggle('vazia', !it);
  const baixar = $('vitBaixar');
  if (!it) {
    $('vitTipo').textContent = { stories: 'Stories', highlights: 'Destaques', posts: 'Posts' }[estado.aba] || '\u00a0';
    $('vitMeta').textContent = '\u00a0';
    $('vitN').textContent = '– / –';
    $('vitAnt').disabled = $('vitProx').disabled = $('vitAmpliar').disabled = true;
    baixar.removeAttribute('href'); baixar.setAttribute('aria-disabled', 'true'); delete baixar.dataset.zip;
    somDisponivel(false);
    return;
  }
  const m = it.m, quando = [], numeros = [];
  const midia = m.type === 'video' ? `Vídeo${m.duration ? ' ' + F.dur(m.duration) : ''}` : 'Foto';
  let tipo, primeiro = midia;
  if (it.kind === 'post') {
    const p = it.post;
    tipo = p.is_reel ? 'Reel' : p.media.length > 1 ? 'Carrossel' : 'Post';
    if (p.media.length > 1) primeiro = `${p.media.length} mídias`;
    if (p.taken_at) quando.push(new Date(p.taken_at * 1000).toLocaleDateString('pt-BR'));
    if (p.like_count != null) numeros.push(`${F.num(p.like_count)} curtidas`);
    if (p.comment_count != null) numeros.push(`${F.num(p.comment_count)} comentários`);
  } else {
    tipo = it.kind === 'story' ? 'Story' : `Destaque · ${it.titulo || 'sem título'}`;
    if (m.taken_at) quando.push(it.kind === 'story' ? `há ${F.ago(m.taken_at)}` : new Date(m.taken_at * 1000).toLocaleDateString('pt-BR'));
  }
  $('vitTipo').textContent = tipo;
  $('vitMeta').textContent = [primeiro, ...quando, ...numeros].join(' · ');
  $('vitTipo').title = tipo; $('vitMeta').title = $('vitMeta').textContent;
  $('vitN').textContent = `${estado.i + 1} / ${estado.itens.length}${it.kind === 'post' && IS.state.nextMaxId ? '+' : ''}`;
  $('vitAnt').disabled = estado.i <= 0;
  $('vitProx').disabled = estado.i >= estado.itens.length - 1;
  $('vitAmpliar').disabled = false;
  // Baixar: a foto, o vídeo ou, no carrossel, todas as mídias num .zip
  baixar.removeAttribute('aria-disabled');
  if (it.kind === 'post' && it.post.media.length > 1) {
    baixar.removeAttribute('href'); baixar.dataset.zip = '1';
    baixar.title = `Baixar as ${it.post.media.length} mídias (.zip)`;
  } else if (m.url) {
    delete baixar.dataset.zip; baixar.href = IS.dlHref(m);
    baixar.title = m.type === 'video' ? 'Baixar o vídeo' : 'Baixar a foto';
  } else { baixar.removeAttribute('href'); baixar.setAttribute('aria-disabled', 'true'); }
  somDisponivel(!!video);
}
function somDisponivel(sim) {
  const b = $('vitSom');
  b.disabled = !sim;
  b.classList.toggle('ligado', sim && estado.som);
  b.setAttribute('aria-pressed', String(sim && estado.som));
  const rot = !sim ? 'Som (só em vídeos)' : estado.som ? 'Tirar o som' : 'Ativar som';
  b.title = rot; b.setAttribute('aria-label', rot);
}
$('vitBaixar').addEventListener('click', async (e) => {
  const b = e.currentTarget;
  if (b.getAttribute('aria-disabled') === 'true') { e.preventDefault(); return; }
  if (!b.dataset.zip) return;
  e.preventDefault();
  const it = estado.itens[estado.i]; if (!it || b.classList.contains('ocupado')) return;
  const p = it.post, u = IS.state.profile.username;
  b.classList.add('ocupado');
  try {
    const res = await fetch('/instasaver/zip', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: `${u}_${p.code || p.id}`, items: p.media.map((x) => ({ url: x.url, filename: x.filename })) }) });
    if (!res.ok) throw new Error();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob()); a.download = `${u}_${p.code || p.id}.zip`;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  } catch { /* o visualizador mostra o erro detalhado; aqui só não trava */ }
  b.classList.remove('ocupado');
});
function abrir() {
  const it = estado.itens[estado.i]; if (!it) return;
  const s = IS.state;
  if (it.kind === 'story') IS.openViewer(IS.storyList(s.stories), estado.i);
  else if (it.kind === 'destaque') IS.openViewer(IS.storyList(s.hlCache.get(s.hlCurrent).items), estado.i);
  else IS.openViewer(IS.postList(), estado.i);
}
function passo(d) {
  const n = estado.i + d;
  if (n < 0 || n >= estado.itens.length) return;
  mostrar(n);
  if (estado.aba === 'posts' && IS.state.nextMaxId && n > estado.itens.length - 4) IS.loadMore();
}
$('vitAnt').addEventListener('click', () => passo(-1));
$('vitProx').addEventListener('click', () => passo(1));
$('vitAmpliar').addEventListener('click', abrir);
$('vitSom').addEventListener('click', () => {
  estado.som = !estado.som;
  if (video) { video.el.muted = !estado.som; if (estado.som) video.el.play().catch(() => {}); }
  somDisponivel(!!video);
});
addEventListener('keydown', (e) => {
  if (estado.visor || !estado.itens.length || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '')) return;
  if (e.key === 'ArrowRight') { passo(1); e.preventDefault(); }
  else if (e.key === 'ArrowLeft') { passo(-1); e.preventDefault(); }
});

// ---------- eventos do app ----------
document.addEventListener('insta:buscando', (e) => {
  pararVideo();
  let u = ''; try { const m = String(e.detail || '').match(/instagram\.com\/(?:stories\/)?([A-Za-z0-9._]+)/); if (m && !['p', 'reel', 'stories', 'highlights'].includes(m[1])) u = '@' + m[1]; } catch {}
  desenharCarregando(u);
  gsap.to(matTela.uniforms.carregando, { value: 1, duration: 0.3 });
  acordar();
});
document.addEventListener('insta:erro', () => {
  gsap.to(matTela.uniforms.carregando, { value: 0, duration: 0.3 });
  if (estado.perfil) mostrar(estado.i, false); else desenharInicio();
});
document.addEventListener('insta:dados', () => {
  gsap.to(matTela.uniforms.carregando, { value: 0, duration: 0.3 });
  estado.perfil = IS.state.profile;
  estado.aba = null;
  const url = estado.perfil.profile_pic;
  imgAvatar = null;
  if (url) { const im = new Image(); im.onload = () => { imgAvatar = im; if (estado.i >= 0) redesenhar(); }; im.src = IS.proxied(url); }
  atualizarBarra();
});
function redesenhar() { const it = estado.itens[estado.i]; if (!it) return; if (it.kind === 'post') desenharPost(it); else desenharStory(it, estado.itens.length); acordar(); }
document.addEventListener('insta:aba', (e) => {
  if (e.detail === estado.aba) return;
  estado.aba = e.detail;
  estado.itens = itensDaAba(estado.aba);
  // o aparelho dá um giro curto ao trocar de aba
  if (!reduzido && estado.perfil) gsap.fromTo(giro.rotation, { y: -0.55 }, { y: 0, duration: 0.9, ease: 'expo.out' });
  mostrar(0, false);
});
document.addEventListener('insta:destaque', () => {
  if (estado.aba !== 'highlights') return;
  estado.itens = itensDaAba('highlights');
  mostrar(0);
});
document.addEventListener('insta:posts', () => {
  if (estado.aba !== 'posts') return;
  estado.itens = itensDaAba('posts');
  atualizarBarra(); marcarCard();
});
document.addEventListener('insta:escolher', (e) => {
  const { grade, i } = e.detail || {};
  if (grade !== GRADE[estado.aba]) return;
  if (i === estado.i) abrir(); else mostrar(i);
});
document.addEventListener('insta:visor', (e) => {
  estado.visor = e.detail;
  if (estado.visor) { if (video) video.el.pause(); dormir(); }
  else { if (video) video.el.play().catch(() => {}); acordar(); }
});

// ---------- câmera, movimento e interação ----------
const troca = { v: 0 };          // 0..1: giro da troca de mídia
const olhar = { x: 0, y: 0 }, olharAlvo = { x: 0, y: 0 };
const arr = { ativo: false, x: 0, base: 0, v: 0 };
let arrasto = 0;                 // giro extra vindo do arrastar (volta sozinho)
const BASE_Y = -0.38;            // três quartos, de leve
function ajustar() {
  const w = vitrine.clientWidth, h = vitrine.clientHeight;
  if (!w || !h) return;
  gl.setSize(w, h, false);
  camera.aspect = w / h;
  // o aparelho fica centrado no espaço acima da barra de informações
  const barra = $('vitBarra');
  const reserva = barra.hidden ? 0 : barra.offsetHeight + 16;
  const util = Math.max(0.35, (h - reserva) / h);
  // enquadra o aparelho inteiro com folga, em qualquer proporção
  const tg = Math.tan(camera.fov * Math.PI / 360);
  const alvoH = H * 1.18 / util, alvoW = W * 1.95;
  const dist = Math.max(alvoH / (2 * tg), alvoW / (2 * tg * camera.aspect));
  camera.position.set(0, 0.04, dist);
  camera.lookAt(0, -0.06, 0);
  camera.setViewOffset(w, h, 0, reserva / 2, w, h);
  camera.updateProjectionMatrix();
  desenhar();
}
const raio = new THREE.Raycaster(), ponto = new THREE.Vector2();
function naTela(e) {
  const r = gl.domElement.getBoundingClientRect();
  ponto.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  raio.setFromCamera(ponto, camera);
  return raio.intersectObject(tela, false).length > 0;
}
gl.domElement.addEventListener('pointerdown', (e) => {
  arr.ativo = true; arr.x = e.clientX; arr.base = arrasto; arr.moveu = false;
  gl.domElement.setPointerCapture(e.pointerId); acordar();
});
gl.domElement.addEventListener('pointermove', (e) => {
  acordar();
  if (e.pointerType !== 'touch') {
    const r = vitrine.getBoundingClientRect();
    olharAlvo.x = ((e.clientX - r.left) / r.width - 0.5) * 2;
    olharAlvo.y = ((e.clientY - r.top) / r.height - 0.5) * 2;
  }
  if (arr.ativo) {
    const dx = e.clientX - arr.x;
    if (Math.abs(dx) > 5) arr.moveu = true;
    arrasto = arr.base + dx * 0.012;
    gl.domElement.style.cursor = 'grabbing';
  } else gl.domElement.style.cursor = naTela(e) && estado.i >= 0 ? 'zoom-in' : 'grab';
});
gl.domElement.addEventListener('pointerup', (e) => {
  arr.ativo = false; gl.domElement.style.cursor = '';
  if (!arr.moveu && naTela(e) && estado.i >= 0) abrir();
  // solta: o aparelho volta para a pose de vitrine, com uma mola
  gsap.to({ v: arrasto }, { v: 0, duration: reduzido ? 0 : 1.4, ease: 'elastic.out(1, 0.55)', onUpdate() { arrasto = this.targets()[0].v; } });
});
gl.domElement.addEventListener('pointerleave', () => { olharAlvo.x = olharAlvo.y = 0; });

// ---------- o quadro ----------
let rodando = false, quieto = 0, acum = 0, visivel = true;
const relogio = new THREE.Clock();
function desenhar() { gl.render(cena, camera); }
function quadro(tempo, deltaMs) {
  const dt = Math.min(0.1, deltaMs / 1000);
  const animando = gsap.isTweening(troca) || gsap.isTweening(giro.rotation) || gsap.isTweening(matTela.uniforms.brilho) || arr.ativo || Math.abs(arrasto) > 0.001;
  // com vídeo tocando, 30 quadros por segundo bastam; parado, o aparelho dorme
  if (!animando && !video && quieto > 6 && matTela.uniforms.carregando.value < 0.01) { dormir(); return; }
  if (!animando && video) { acum += dt; if (acum < 1 / 30) return; acum = 0; }
  quieto += dt;
  const t = relogio.getElapsedTime();
  matTela.uniforms.t.value = t;
  const k = 1 - Math.exp(-dt * 3.5);
  olhar.x += (olharAlvo.x - olhar.x) * k; olhar.y += (olharAlvo.y - olhar.y) * k;
  // flutua de leve; segue o mouse; gira na troca; obedece o arrastar
  const bob = reduzido ? 0 : Math.sin(t * 0.9) * 0.012;
  aparelho.position.y = bob;
  aparelho.rotation.set(0.05 + olhar.y * 0.08, BASE_Y + olhar.x * 0.22 + arrasto - troca.v * 0.55, reduzido ? 0 : Math.sin(t * 0.6) * 0.008);
  sombra.material.opacity = 0.75 - bob * 6;
  desenhar();
}
function acordar() { quieto = 0; if (!rodando && visivel && !estado.visor && !document.hidden) { rodando = true; gsap.ticker.add(quadro); } }
function dormir() { if (rodando) { rodando = false; gsap.ticker.remove(quadro); } }
document.addEventListener('visibilitychange', () => (document.hidden ? dormir() : acordar()));
new IntersectionObserver((es) => { visivel = es[0].isIntersecting; visivel ? acordar() : dormir(); }).observe(vitrine);
const ro = new ResizeObserver(ajustar); ro.observe(vitrine); ro.observe($('vitBarra'));

// ---------- entrada: o aparelho chega de costas e vira para a tela ----------
desenharInicio();
ajustar();
const compilar = gl.compileAsync && gl.extensions.has('KHR_parallel_shader_compile')
  ? gl.compileAsync(cena, camera) : Promise.resolve(gl.compile(cena, camera));
compilar.catch(() => {}).then(() => {
  document.body.classList.add('vitrine-pronta');
  if (reduzido) { acordar(); return; }
  giro.rotation.y = Math.PI * 0.92; giro.position.y = -0.18;
  acordar();
  gsap.to(giro.rotation, { y: 0, duration: 2.2, ease: 'expo.inOut', delay: 0.15 });
  gsap.to(giro.position, { y: 0, duration: 1.8, ease: 'expo.out', delay: 0.15 });
});
if (location.search.includes('debug')) window.__vitrine = { estado, aparelho, giro, camera, gl, matTela };
}
