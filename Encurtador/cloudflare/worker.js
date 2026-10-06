// Encurtador GBM — código que atende os links curtos.
//
// O mesmo arquivo é publicado como _worker.js nos projetos Cloudflare Pages
// (gbm.pages.dev, gbmlinks.pages.dev) e como o Worker "gbm" (gbm.gbm.workers.dev),
// todos ligados ao mesmo banco: qualquer endereço abre qualquer link. Roda na rede da Cloudflare, então os links funcionam no mundo todo mesmo com o
// computador desligado. O Verto cria/edita os links direto no banco D1 (API da
// Cloudflare); este Worker só lê o link, redireciona e registra o clique.
//
// Bindings: DB (D1) e SALT (segredo para o hash anônimo de visitante).
// Rotas: /<código> redireciona · /<código>+ mostra para onde o link leva.

const BOT_RE = /bot\b|bot\/|crawl|spider|slurp|facebookexternalhit|facebookcatalog|meta-externalagent|whatsapp|telegram|discord|slack|twitter|linkedin|embedly|preview|pinterest|skype|vkshare|redditbot|applebot|bingpreview|headless|python-requests|python-urllib|aiohttp|curl\/|wget|go-http-client|okhttp|axios|node-fetch|undici|lighthouse|pagespeed|monitor|uptime/i;

const MAX_TENTATIVAS = 5;          // senhas erradas por IP e link...
const JANELA_TENTATIVAS = 15 * 60; // ...a cada 15 minutos

export default {
  async fetch(request, env, ctx) {
    try {
      return await atender(request, env, ctx);
    } catch {
      // Nunca mostra o erro genérico da Cloudflare para quem clicou.
      return indisponivel();
    }
  },
};

async function atender(request, env, ctx) {
  const url = new URL(request.url);
  let caminho;
  try {
    caminho = decodeURIComponent(url.pathname.slice(1));
  } catch {
    return pagina(404, 'Link não encontrado', 'O endereço está incompleto ou foi digitado errado.');
  }
  caminho = caminho.replace(/\/+$/, '');

  if (caminho === '') return pagina(200, 'GBM Links', 'Este é o encurtador de links da GBM. Para abrir um link, use o endereço completo que você recebeu.');
  if (caminho === 'robots.txt') return new Response('User-agent: *\nAllow: /\n', { headers: { 'content-type': 'text/plain; charset=utf-8' } });
  if (caminho === 'favicon.ico' || caminho === 'favicon.svg') return new Response(FAVICON, { headers: { 'content-type': 'image/svg+xml', 'cache-control': 'public, max-age=604800' } });

  const previa = caminho.endsWith('+');
  const slug = previa ? caminho.slice(0, -1) : caminho;
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(slug)) return pagina(404, 'Link não encontrado', 'Confira se o endereço foi copiado inteiro.');

  const link = await comRepeticao(() => env.DB.prepare(
    'SELECT id, slug, url, titulo, expira_em, max_cliques, senha_hash, ativo, tipo_redirect, cliques FROM links WHERE slug = ?1'
  ).bind(slug).first());

  if (!link) return pagina(404, 'Link não encontrado', 'Este link curto não existe ou foi excluído.');
  if (!link.ativo) return pagina(410, 'Link pausado', 'O dono deste link o desativou por enquanto.');
  const agora = Math.floor(Date.now() / 1000);
  if ((link.expira_em && agora >= link.expira_em) || (link.max_cliques && link.cliques >= link.max_cliques)) {
    return pagina(410, 'Link expirado', 'Este link curto chegou ao fim da validade.');
  }

  if (previa) return paginaPrevia(link, url.origin);

  if (link.senha_hash) {
    const ip = request.headers.get('cf-connecting-ip') || '';
    const chave = `${link.id}:${ip}`;
    if (request.method !== 'POST') return paginaSenha(link.slug, '');
    if (await bloqueado(env, chave, agora).catch(() => false)) {
      return paginaSenha(link.slug, 'Muitas tentativas erradas. Espere 15 minutos e tente de novo.', 429);
    }
    const form = await request.formData().catch(() => null);
    const senha = form ? String(form.get('senha') || '') : '';
    if (!(await senhaConfere(senha, link.senha_hash))) {
      await registrarErro(env, chave, agora).catch(() => {});
      return paginaSenha(link.slug, 'Senha incorreta.', 403);
    }
  }

  ctx.waitUntil(registrarClique(request, env, link, agora).catch(() => {}));
  return new Response(null, {
    status: link.tipo_redirect === 301 ? 301 : 302,
    headers: {
      location: link.url,
      // 302 não fica em cache: o clique sempre passa por aqui (estatística) e
      // mudar o destino no Verto vale na hora para todo mundo.
      'cache-control': link.tipo_redirect === 301 ? 'public, max-age=86400' : 'private, no-store',
      'x-robots-tag': 'noindex',
    },
  });
}

// Uma falha passageira do banco ganha uma segunda chance antes de virar erro.
async function comRepeticao(fn) {
  try {
    return await fn();
  } catch {
    await new Promise((r) => setTimeout(r, 200));
    return await fn();
  }
}

function indisponivel() {
  const r = pagina(503, 'Volte em instantes', 'O link está certo, mas o encurtador não conseguiu responder agora. Tente de novo em alguns segundos.');
  r.headers.set('retry-after', '10');
  return r;
}

// ---------- Cliques ----------

async function registrarClique(request, env, link, agora) {
  const ua = request.headers.get('user-agent') || '';
  const bot = request.method === 'HEAD' || !ua || BOT_RE.test(ua) ? 1 : 0;
  const ip = request.headers.get('cf-connecting-ip') || '';
  const dia = new Date(agora * 1000).toISOString().slice(0, 10);
  // Sem guardar IP: um hash que muda todo dia só serve para contar visitantes únicos.
  const visitante = (await sha256Hex(`${ip}|${ua}|${dia}|${env.SALT || ''}`)).slice(0, 16);
  const pais = (request.cf && request.cf.country) || null;

  const stmts = [
    env.DB.prepare(
      'INSERT INTO cliques (link_id, ts, referencia, dispositivo, navegador, so, pais, visitante, bot) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)'
    ).bind(link.id, agora, referencia(request), dispositivo(ua), navegador(ua), sistema(ua), pais, visitante, bot),
  ];
  // Robôs de prévia (WhatsApp, Telegram...) "abrem" o link só de colá-lo numa conversa:
  // ficam registrados, mas não contam como clique nem gastam o limite de cliques.
  if (!bot) stmts.push(env.DB.prepare('UPDATE links SET cliques = cliques + 1, ultimo_clique = ?1 WHERE id = ?2').bind(agora, link.id));
  await env.DB.batch(stmts);
}

function referencia(request) {
  const ref = request.headers.get('referer');
  if (!ref) return 'direto';
  try {
    return new URL(ref).hostname.replace(/^www\./, '') || 'direto';
  } catch {
    return 'direto';
  }
}

function dispositivo(ua) {
  if (/iPad|Tablet|PlayBook|Silk|Kindle/i.test(ua) || (/Android/i.test(ua) && !/Mobile/i.test(ua))) return 'tablet';
  if (/Mobi|iPhone|iPod|Android|Windows Phone/i.test(ua)) return 'celular';
  return 'computador';
}

function navegador(ua) {
  const regras = [
    [/Instagram/i, 'Instagram'], [/FBAN|FBAV|FB_IAB/i, 'Facebook'], [/TikTok|BytedanceWebview/i, 'TikTok'],
    [/Edg(e|A|iOS)?\//, 'Edge'], [/OPR\/|Opera/, 'Opera'], [/SamsungBrowser/, 'Samsung Internet'],
    [/Firefox\/|FxiOS/, 'Firefox'], [/CriOS|Chrome\//, 'Chrome'], [/Safari\//, 'Safari'],
  ];
  for (const [re, nome] of regras) if (re.test(ua)) return nome;
  return 'outro';
}

function sistema(ua) {
  const regras = [
    [/Windows/, 'Windows'], [/Android/, 'Android'], [/iPhone|iPad|iPod/, 'iOS'],
    [/CrOS/, 'ChromeOS'], [/Mac OS X|Macintosh/, 'macOS'], [/Linux/, 'Linux'],
  ];
  for (const [re, nome] of regras) if (re.test(ua)) return nome;
  return 'outro';
}

// ---------- Senha ----------
// Formato gerado pelo Verto: pbkdf2$<iterações>$<sal base64>$<hash base64>

async function senhaConfere(senha, guardado) {
  const partes = String(guardado).split('$');
  if (partes.length !== 4 || partes[0] !== 'pbkdf2') return false;
  const iteracoes = parseInt(partes[1], 10);
  const sal = b64ParaBytes(partes[2]);
  const esperado = b64ParaBytes(partes[3]);
  const chave = await crypto.subtle.importKey('raw', new TextEncoder().encode(senha), 'PBKDF2', false, ['deriveBits']);
  const bits = new Uint8Array(await crypto.subtle.deriveBits(
    { name: 'PBKDF2', hash: 'SHA-256', salt: sal, iterations: iteracoes }, chave, esperado.length * 8));
  if (bits.length !== esperado.length) return false;
  let dif = 0;
  for (let i = 0; i < bits.length; i++) dif |= bits[i] ^ esperado[i];
  return dif === 0;
}

async function bloqueado(env, chave, agora) {
  const t = await env.DB.prepare('SELECT n, inicio FROM tentativas WHERE chave = ?1').bind(chave).first();
  return !!t && agora - t.inicio < JANELA_TENTATIVAS && t.n >= MAX_TENTATIVAS;
}

async function registrarErro(env, chave, agora) {
  await env.DB.prepare(
    `INSERT INTO tentativas (chave, n, inicio) VALUES (?1, 1, ?2)
     ON CONFLICT(chave) DO UPDATE SET
       n = CASE WHEN ?2 - inicio >= ?3 THEN 1 ELSE n + 1 END,
       inicio = CASE WHEN ?2 - inicio >= ?3 THEN ?2 ELSE inicio END`
  ).bind(chave, agora, JANELA_TENTATIVAS).run();
}

// ---------- Utilitários ----------

async function sha256Hex(texto) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(texto));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function b64ParaBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

// ---------- Páginas (identidade GBM) ----------

const FAVICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#07090e"/><path d="M27 37l10-10M24 31l-4 4a6 6 0 008.5 8.5l4-4M40 33l4-4a6 6 0 00-8.5-8.5l-4 4" stroke="#4169e1" stroke-width="5" fill="none" stroke-linecap="round"/></svg>';

const CSS = `
:root{--bg:#07090e;--surface:#0f131c;--line:rgba(190,210,240,.12);--text:#eef2f8;--muted:#9aa4b5;--cobalt:#4169e1;--cobalt-btn:#3159d4;--bronze:#d8bd8a}
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px 16px;background:var(--bg);background-image:radial-gradient(at 20% 0%,rgba(65,105,225,.14),transparent 55%),radial-gradient(at 90% 100%,rgba(216,189,138,.07),transparent 50%);color:var(--text);font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{width:100%;max-width:520px;background:var(--surface);border:1px solid var(--line);border-radius:22px;padding:36px 28px;text-align:center;box-shadow:0 30px 80px rgba(0,0,0,.45)}
.marca{display:inline-flex;align-items:center;gap:10px;font-weight:900;letter-spacing:.14em;font-size:13px;color:var(--muted);text-transform:uppercase;margin-bottom:22px}
.marca b{background:linear-gradient(180deg,#fff 0%,#e2e6ec 32%,#9ca3af 54%,#f4f5f7 100%);-webkit-background-clip:text;background-clip:text;color:transparent;font-size:18px;letter-spacing:.08em}
h1{font-size:clamp(1.5rem,1.2rem + 1.5vw,2rem);line-height:1.2;margin-bottom:10px}
p{color:var(--muted)}
.destino{margin:22px 0;padding:14px 16px;border-radius:12px;background:#151a26;border:1px solid var(--line);text-align:left;word-break:break-all;font-size:14px}
.destino small{display:block;color:var(--muted);font-size:12px;margin-bottom:4px}
.destino strong{color:var(--bronze);font-size:16px;word-break:break-word}
.btn{display:inline-flex;align-items:center;justify-content:center;width:100%;min-height:48px;padding:12px 18px;margin-top:8px;border:0;border-radius:12px;background:var(--cobalt-btn);color:#fff;font-family:inherit;font-weight:700;font-size:15px;text-decoration:none;cursor:pointer}
.btn:hover{background:#2745a8}
input{width:100%;min-height:48px;margin-top:18px;padding:12px 14px;border-radius:12px;border:1px solid var(--line);background:#151a26;color:var(--text);font-family:inherit;font-size:16px}
input:focus{outline:2px solid var(--cobalt);outline-offset:1px}
.erro{margin-top:14px;color:#fca5a5;font-size:14px}
`;

function html(status, titulo, corpo) {
  return new Response(
    `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><meta name="color-scheme" content="dark"><title>${esc(titulo)} · GBM Links</title><link rel="icon" href="/favicon.svg" type="image/svg+xml"><style>${CSS}</style></head><body><main><div class="marca"><b>GBM</b> Links</div>${corpo}</main></body></html>`,
    { status, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'x-robots-tag': 'noindex' } }
  );
}

function pagina(status, titulo, texto) {
  return html(status, titulo, `<h1>${esc(titulo)}</h1><p>${esc(texto)}</p>`);
}

function paginaPrevia(link, origem) {
  let dominio = '';
  try { dominio = new URL(link.url).hostname.replace(/^www\./, ''); } catch {}
  const aviso = link.senha_hash ? '<p>Este link é protegido por senha.</p>' : '';
  return html(200, 'Para onde este link leva', `<h1>Para onde este link leva</h1>
<p>${esc(origem.replace(/^https?:\/\//, ''))}/${esc(link.slug)}</p>
<div class="destino"><small>Destino</small><strong>${esc(dominio)}</strong>${link.titulo ? `<br>${esc(link.titulo)}` : ''}<br><span style="color:#9aa4b5">${esc(link.url)}</span></div>
${aviso}<a class="btn" href="/${encodeURIComponent(link.slug)}" rel="noreferrer">Continuar</a>`);
}

function paginaSenha(slug, erro, status = 200) {
  return html(status, 'Link protegido', `<h1>Link protegido</h1><p>Digite a senha para continuar.</p>
<form method="post" action="/${encodeURIComponent(slug)}"><input type="password" name="senha" autocomplete="current-password" aria-label="Senha" required autofocus><button class="btn" type="submit">Abrir link</button></form>
${erro ? `<p class="erro" role="alert">${esc(erro)}</p>` : ''}`);
}
