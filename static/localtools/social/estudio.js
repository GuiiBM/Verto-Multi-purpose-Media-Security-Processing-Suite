/* Social Preview · estúdio: um post, cada rede no formato certo, publicado direto.
 *
 * O catálogo (formatos, tamanhos, limites) vem de /social/catalogo (SocialPreview/redes.py).
 * Cada mídia guarda um enquadramento POR REDE e formato (chave "rede:formato:proporção"):
 * nasce automático (foco no rosto ou no assunto, analisado em /social/foco) e cada rede pode
 * ser ajustada à mão no editor. A conta de recorte é a mesma de SocialPreview/midia.py
 * (`recorte` e `geometria`): a prévia mostra exatamente o arquivo que sai.
 * Com uma música, as fotos viram vídeo (slideshow) nas redes que aceitam vídeo.
 */
(() => {
  'use strict';

  // ---------- utilidades ----------
  const $ = (s, el = document) => el.querySelector(s);
  const SVGNS = 'http://www.w3.org/2000/svg';

  function el(tag, props, ...filhos) {
    const e = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v == null || v === false) continue;
        if (k === 'class') e.className = v;
        else if (k === 'style' && typeof v === 'object') {
          for (const [p, val] of Object.entries(v)) {
            if (p.includes('-')) e.style.setProperty(p, val);
            else e.style[p] = val;
          }
        } else if (k === 'dataset') Object.assign(e.dataset, v);
        else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
        else if (k in e && typeof v !== 'string') e[k] = v;
        else e.setAttribute(k, v === true ? '' : v);
      }
    }
    for (const f of filhos.flat(Infinity)) {
      if (f == null || f === false) continue;
      e.append(f instanceof Node ? f : document.createTextNode(String(f)));
    }
    return e;
  }

  // replaceChildren transforma null em texto "null" e array em "[object …]": achata e filtra antes.
  function trocar(alvo, ...filhos) {
    alvo.replaceChildren(...filhos.flat(Infinity).filter((f) => f != null && f !== false));
  }

  const ICONES = {
    coracao: 'M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.2a4.3 4.3 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z',
    comentario: 'M20.5 11.6a8.4 8.4 0 0 1-12.3 7.4L3.5 20.4l1.4-4.5a8.4 8.4 0 1 1 15.6-4.3z',
    enviar: 'M21.5 3 9.8 14.3M21.5 3l-6.7 18-5-6.7L3 9.6z',
    salvar: 'M6.5 3.5h11v17l-5.5-4.2-5.5 4.2z',
    repost: 'M17 2.5l3.5 3.5L17 9.5M3.5 11V9a3 3 0 0 1 3-3h14M7 21.5 3.5 18 7 14.5M20.5 13v2a3 3 0 0 1-3 3h-14',
    compartilhar: 'M12 3.5v11M7.5 8 12 3.5 16.5 8M5 13.5v6h14v-6',
    mais: 'M5 12h.01M12 12h.01M19 12h.01',
    curtir: 'M7.5 10.5v9h-3v-9zM7.5 10.5l3.8-6.6a1.8 1.8 0 0 1 3.3 1.3l-.9 4.3h5.2a2 2 0 0 1 2 2.4l-1.3 6.2a2 2 0 0 1-2 1.4H7.5',
    descurtir: 'M16.5 13.5v-9h3v9zM16.5 13.5l-3.8 6.6a1.8 1.8 0 0 1-3.3-1.3l.9-4.3H5.1a2 2 0 0 1-2-2.4l1.3-6.2a2 2 0 0 1 2-1.4h10.1',
    globo: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.8 3.2 2.8 14.8 0 18M12 3c-2.8 3.2-2.8 14.8 0 18',
    musica: 'M9 18V5.5l11-2v12.5M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
    adicionar: 'M12 5v14M5 12h14',
    olho: 'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 9.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6z',
    grafico: 'M5 20V11M12 20V4.5M19 20v-6.5',
    play: 'M8 5.5v13l10.5-6.5z',
    pausa: 'M8 5.5v13M16 5.5v13',
    fechar: 'M6 6l12 12M18 6 6 18',
    esq: 'M14.5 6 8.5 12l6 6',
    dir: 'M9.5 6l6 6-6 6',
    camera: 'M4 8h3.5L9 5.5h6L16.5 8H20v11H4zM12 10.5a3.2 3.2 0 1 0 0 6.4 3.2 3.2 0 0 0 0-6.4z',
    lupa: 'M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM15.3 15.3 20 20',
    remix: 'M4 7h11l-3-3M20 17H9l3 3',
    centro: 'M12 3v4M12 17v4M3 12h4M17 12h4M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z',
    menos: 'M5 12h14',
    lapis: 'M4 20h4L19.5 8.5a2.8 2.8 0 0 0-4-4L4 16zM13.5 6.5l4 4',
    magica: 'M5 19 15 9M13.5 4.5v3M12 6h3M18.5 9.5v3M17 11h3M7.5 3.5v2M6.5 4.5h2',
  };

  function ico(nome, cls, preenchido) {
    const s = document.createElementNS(SVGNS, 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('aria-hidden', 'true');
    s.setAttribute('class', 'sp-ico' + (cls ? ' ' + cls : ''));
    const p = document.createElementNS(SVGNS, 'path');
    p.setAttribute('d', ICONES[nome] || '');
    if (preenchido) p.setAttribute('fill', 'currentColor');
    else {
      p.setAttribute('fill', 'none');
      p.setAttribute('stroke', 'currentColor');
      p.setAttribute('stroke-width', nome === 'mais' ? '3' : '1.7');
      p.setAttribute('stroke-linecap', 'round');
      p.setAttribute('stroke-linejoin', 'round');
    }
    s.append(p);
    return s;
  }

  function marca(id, cls) {
    const m = (window.SP_MARCAS || {})[id];
    if (!m) return el('span', { class: 'sp-marca sp-marca--vazia ' + (cls || '') }, ico('globo'));
    const s = document.createElementNS(SVGNS, 'svg');
    s.setAttribute('viewBox', m.vb);
    s.setAttribute('aria-hidden', 'true');
    s.setAttribute('class', 'sp-marca ' + (cls || ''));
    const p = document.createElementNS(SVGNS, 'path');
    p.setAttribute('d', m.d);
    p.setAttribute('fill', 'currentColor');
    s.append(p);
    return s;
  }

  const LS = 'sp-estudio-v3';
  function lerLS() { try { return JSON.parse(localStorage.getItem(LS) || '{}'); } catch { return {}; } }
  function gravarLS() {
    try {
      const redes = {};
      for (const [k, v] of Object.entries(S.redes)) {
        redes[k] = { ativa: v.ativa, textoProprio: v.textoProprio, texto: v.textoProprio ? v.texto : null };
      }
      const show = { durFoto: S.show.durFoto, transicao: S.show.transicao, movimento: S.show.movimento, volume: S.show.volume, fade: S.show.fade };
      localStorage.setItem(LS, JSON.stringify({ texto: S.texto, link: S.link, titulo: S.titulo, alt: S.alt, zonas: S.zonas,
        tercos: S.tercos, selecaoManual: S.selecaoManual, redes, show }));
    } catch { /* sem armazenamento: segue sem lembrar */ }
  }

  function aviso(msg, tipo) {
    const a = $('#sp-aviso');
    a.textContent = msg;
    a.className = 'sp-aviso visivel' + (tipo ? ' ' + tipo : '');
    clearTimeout(aviso.t);
    aviso.t = setTimeout(() => { a.className = 'sp-aviso'; }, tipo === 'erro' ? 6000 : 4200);
  }

  async function api(url, opts) {
    const r = await fetch(url, opts);
    const j = await r.json().catch(() => ({ success: false, error: `HTTP ${r.status}` }));
    if (!j.success) throw new Error(j.error || 'Falhou');
    return j;
  }

  const fmtDur = (s) => { s = Math.round(s || 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const fmtSeg = (s) => `${(Math.round(s * 10) / 10).toLocaleString('pt-BR')} s`;
  const ratioNum = (r) => { const [a, b] = String(r).split(':').map(Number); return a / b; };
  const ratioTxt = (r) => r.replace(':', '∶');
  const limitar = (v, a, b) => Math.min(b, Math.max(a, v));

  // ---------- estado ----------
  const S = {
    cat: null, porId: {}, contas: {}, config: {},
    midias: [], texto: '', link: '', titulo: '', alt: '',
    redes: {}, zonas: true, tercos: false, selecaoManual: false, idx: {}, vivos: [], shows: [],
    show: { ativo: false, audio: null, inicio: 0, durFoto: 3, transicao: 'esmaecer', movimento: true, volume: 1, fade: true },
    slide: 0, tocando: false,
  };
  let seq = 0;

  const rede = (id) => S.porId[id];
  const conta = (id) => S.contas[id] || null;
  const perfil = (id) => (conta(id) && conta(id).perfil) || null;
  const formatoDe = (r) => r.formatos.find((f) => f.id === S.redes[r.id].formato) || r.formatos[0];
  const tamanhoDe = (r, f) => f.tamanhos.find((t) => t.ratio === S.redes[r.id].ratio) || f.tamanhos[0];

  // ---------- geometria (mesma conta de SocialPreview/midia.py) ----------
  function recorte(w, h, W, H, e) {
    const zoom = Math.max(1, Number(e.zoom) || 1);
    const s = Math.max(W / w, H / h) * zoom;
    const cw = Math.min(w, W / s), ch = Math.min(h, H / s);
    const x = Math.min(Math.max((e.x ?? 0.5) * w - cw / 2, 0), w - cw);
    const y = Math.min(Math.max((e.y ?? 0.5) * h - ch / 2, 0), h - ch);
    return [x, y, cw, ch];
  }

  function geometria(w, h, W, H, e) {
    if (!e.modo || e.modo === 'preencher') {
      const [x, y, cw, ch] = recorte(w, h, W, H, e);
      return { tipo: 'recorte', x, y, cw, ch };
    }
    let s = Math.min(W / w, H / h), px = 0.5, py = 0.5;
    if (e.modo === 'livre') {
      s *= limitar(Number(e.escala) || 1, 0.15, 4);
      px = e.px ?? 0.5; py = e.py ?? 0.5;
    }
    const fw = w * s, fh = h * s;
    return { tipo: 'livre', left: px * W - fw / 2, top: py * H - fh / 2, fw, fh };
  }

  const MODOS = [
    ['preencher', 'Cortar', 'A foto cobre o quadro; você escolhe a parte que aparece.'],
    ['encaixar', 'Encaixar', 'A foto inteira, centralizada; o resto é preenchido.'],
    ['livre', 'Preenchimento automático', 'Você põe a foto onde e do tamanho que quiser; o resto é preenchido.'],
  ];
  const FUNDOS = [['desfoque', 'Desfoque'], ['cor', 'Cor da foto'], ['espelho', 'Espelho'], ['bordas', 'Esticar bordas'], ['preto', 'Preto'], ['branco', 'Branco']];

  function corFundo(e, m) {
    const f = e.fundo || 'desfoque';
    if (f === 'cor') return m.cor || '#202020';
    if (f === 'preto') return '#000000';
    if (f === 'branco') return '#ffffff';
    return /^#[0-9a-f]{6}$/i.test(f) ? f : '#000000';
  }

  function pintarFundo(ctx, src, m, W, H, g, e) {
    const f = e.fundo || 'desfoque';
    const w = m.w, h = m.h;
    if (f === 'desfoque') {
      ctx.save();
      ctx.filter = `blur(${Math.max(4, Math.round(W / 27))}px) brightness(0.94)`;
      const s = Math.max(W / w, H / h) * 1.08;
      ctx.drawImage(src, (W - w * s) / 2, (H - h * s) / 2, w * s, h * s);
      ctx.restore();
    } else if (f === 'espelho') {
      const nl = Math.ceil(Math.max(0, g.left) / g.fw), nr = Math.ceil(Math.max(0, W - g.left - g.fw) / g.fw);
      const nt = Math.ceil(Math.max(0, g.top) / g.fh), nb = Math.ceil(Math.max(0, H - g.top - g.fh) / g.fh);
      for (let j = -nt; j <= nb; j++) {
        for (let i = -nl; i <= nr; i++) {
          if (!i && !j) continue;
          const fx = i % 2 !== 0, fy = j % 2 !== 0;
          ctx.save();
          ctx.translate(g.left + i * g.fw + (fx ? g.fw : 0), g.top + j * g.fh + (fy ? g.fh : 0));
          ctx.scale(fx ? -1 : 1, fy ? -1 : 1);
          ctx.drawImage(src, 0, 0, g.fw, g.fh);
          ctx.restore();
        }
      }
    } else if (f === 'bordas') {
      const L = g.left, T = g.top, Rr = g.left + g.fw, B = g.top + g.fh;
      if (L > 0) ctx.drawImage(src, 0, 0, 1, h, 0, T, L, g.fh);
      if (Rr < W) ctx.drawImage(src, w - 1, 0, 1, h, Rr, T, W - Rr, g.fh);
      if (T > 0) ctx.drawImage(src, 0, 0, w, 1, L, 0, g.fw, T);
      if (B < H) ctx.drawImage(src, 0, h - 1, w, 1, L, B, g.fw, H - B);
      if (L > 0 && T > 0) ctx.drawImage(src, 0, 0, 1, 1, 0, 0, L, T);
      if (Rr < W && T > 0) ctx.drawImage(src, w - 1, 0, 1, 1, Rr, 0, W - Rr, T);
      if (L > 0 && B < H) ctx.drawImage(src, 0, h - 1, 1, 1, 0, B, L, H - B);
      if (Rr < W && B < H) ctx.drawImage(src, w - 1, h - 1, 1, 1, Rr, B, W - Rr, H - B);
    } else {
      ctx.fillStyle = corFundo(e, m);
      ctx.fillRect(0, 0, W, H);
    }
  }

  function desenhar(ctx, m, W, H, e) {
    const src = m.fonte;
    ctx.clearRect(0, 0, W, H);
    const g = geometria(m.w, m.h, W, H, e);
    if (g.tipo === 'recorte') {
      ctx.drawImage(src, g.x, g.y, g.cw, g.ch, 0, 0, W, H);
      return;
    }
    pintarFundo(ctx, src, m, W, H, g, e);
    ctx.drawImage(src, g.left, g.top, g.fw, g.fh);
  }

  // ---------- enquadramento automático ----------
  // Corta em volta do rosto/assunto quando a proporção deixa; quando cortar perderia demais
  // (paisagem num 9:16) ou deixaria o assunto de fora, põe a foto inteira e preenche o resto.
  function autoEnq(m, ratio, f) {
    const R = ratioNum(ratio), asp = m.w / m.h;
    const an = m.analise || {};
    const foco = an.foco || { x0: 0.25, y0: 0.25, x1: 0.75, y1: 0.75 };
    const rostos = an.rostos || [];
    const k = Math.min(asp / R, R / asp);
    const cw = asp > R ? R / asp : 1, ch = asp > R ? 1 : asp / R;
    const cabe = foco.x1 - foco.x0 <= cw * 1.04 && foco.y1 - foco.y0 <= ch * 1.04;
    // com rosto, cortar em volta dele funciona mesmo com muita diferença (como seguir o rosto num 9:16)
    const limite = rostos.length ? 0.3 : R < 0.7 ? 0.55 : 0.45;
    if (k >= 0.92 || (cabe && k >= limite)) {
      let cx = (foco.x0 + foco.x1) / 2, cy = (foco.y0 + foco.y1) / 2;
      if (rostos.length && ch < 1) {
        // o rosto fica a ~38% do topo (mesma regra do app Automações), espaço para o texto embaixo
        const ry = (Math.min(...rostos.map((r) => r.y0)) + Math.max(...rostos.map((r) => r.y1))) / 2;
        cy = ry + ch * (0.5 - 0.38);
      }
      const e = { modo: 'preencher', x: cx, y: cy, zoom: 1, fundo: 'desfoque', auto: true,
        motivo: k >= 0.92 ? 'a proporção da foto já combina: preenche o quadro'
          : rostos.length ? `cortado em volta ${rostos.length > 1 ? 'dos rostos' : 'do rosto'}` : 'cortado em volta do assunto principal' };
      normalizar(m, ratio, e);
      return e;
    }
    const z = (f && f.zonas) || {};
    const fhN = Math.min(R / asp, 1), fwN = Math.min(asp / R, 1);
    let py = (z.topo || z.base) ? ((z.topo || 0) + (1 - (z.base || 0))) / 2 : 0.5;
    py = limitar(py, fhN / 2, 1 - fhN / 2);
    const px = limitar(0.5, fwN / 2, 1 - fwN / 2);
    return { modo: 'livre', escala: 1, px, py, fundo: 'desfoque', auto: true,
      motivo: cabe ? `a foto é bem ${asp > R ? 'mais larga' : 'mais alta'} que ${ratio}: inteira, com o fundo preenchido`
        : 'cortar deixaria o assunto de fora: foto inteira, com o fundo preenchido' };
  }

  function enq(m, ctx) {
    if (!m.enq[ctx.k]) m.enq[ctx.k] = autoEnq(m, ctx.t.ratio, ctx.f);
    return m.enq[ctx.k];
  }

  function normalizar(m, ratio, e) {
    if (e.modo && e.modo !== 'preencher') return;
    const R = ratioNum(ratio);
    const [x, y, cw, ch] = recorte(m.w, m.h, R * 1000, 1000, e);
    e.x = (x + cw / 2) / m.w;
    e.y = (y + ch / 2) / m.h;
  }

  function reautomatizar(m) {
    for (const k of Object.keys(m.enq)) if (m.enq[k].auto) delete m.enq[k];
  }

  // ---------- desenho na prévia ----------
  const PREV_W = 640;

  function pintarCanvas(cv, m, ctx) {
    const R = ratioNum(ctx.t.ratio);
    const W = Number(cv.dataset.larg) || PREV_W, H = Math.round(W / R);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    desenhar(cv.getContext('2d'), m, W, H, enq(m, ctx));
  }

  // O arquivo que vai ser postado, desenhado num canvas (foto e vídeo: a mesma conta).
  // No vídeo, passar o mouse toca e o canvas acompanha quadro a quadro.
  function postado(m, ctx, opts = {}) {
    const cv = el('canvas', { class: 'sp-post' + (opts.cobrir ? ' cobrir' : ''), dataset: { larg: String(opts.larg || PREV_W) } });
    pintarCanvas(cv, m, ctx);
    S.vivos.push({ m, k: ctx.k, ctx, el: cv });
    if (m.tipo !== 'video') return cv;
    const caixa = el('div', { class: 'sp-post-mini' + (opts.cobrir ? ' cobrir' : '') }, cv, el('span', { class: 'sp-play' }, ico('play', '', true)));
    let raf = 0;
    const laco = () => { pintarCanvas(cv, m, ctx); raf = requestAnimationFrame(laco); };
    caixa.addEventListener('pointerenter', () => { caixa.classList.add('tocando'); m.fonte.play().catch(() => {}); laco(); });
    caixa.addEventListener('pointerleave', () => { caixa.classList.remove('tocando'); m.fonte.pause(); cancelAnimationFrame(raf); pintarCanvas(cv, m, ctx); });
    return caixa;
  }

  function atualizarVivos(m, k) {
    S.vivos = S.vivos.filter((v) => v.el.isConnected);
    for (const v of S.vivos) if (v.m === m && v.k === k) pintarCanvas(v.el, m, v.ctx);
  }

  // Rótulo "automático/ajustado" e avisos do cartão: redesenha quando o gesto termina
  // (redesenhar no meio do arrasto trocaria o elemento e perderia o ponteiro).
  function gestoTerminou(ctx) {
    if (!S.editor) agendarTela(ctx.r);
  }

  // Arrastar, roda e duplo clique: reenquadra a mídia só nesta rede.
  // `qual()` devolve a foto do quadro (no vídeo com música ela muda a cada slide).
  function interacao(alvo, qual, ctx) {
    alvo.classList.add('sp-arrastavel');
    let ini = null;
    alvo.addEventListener('pointerdown', (ev) => {
      if (ev.button !== 0 || ev.target.closest('button, .sp-ctl, a')) return;
      const m = qual();
      if (!m) return;
      const e = enq(m, ctx);
      if (e.modo === 'encaixar') Object.assign(e, { modo: 'livre', escala: 1, px: 0.5, py: 0.5 });
      ini = { x: ev.clientX, y: ev.clientY, e: { ...e }, m };
      alvo.setPointerCapture(ev.pointerId);
      alvo.classList.add('arrastando');
    });
    alvo.addEventListener('pointermove', (ev) => {
      if (!ini) return;
      const { m } = ini;
      const r = alvo.getBoundingClientRect();
      const R = ratioNum(ctx.t.ratio);
      const dispW = R > r.width / r.height ? r.height * R : r.width;
      const dispH = dispW / R;
      const e = enq(m, ctx);
      e.auto = false;
      if (e.modo === 'livre') {
        e.px = ini.e.px + (ev.clientX - ini.x) / dispW;
        e.py = ini.e.py + (ev.clientY - ini.y) / dispH;
      } else {
        const [, , cw, ch] = recorte(m.w, m.h, R * 1000, 1000, ini.e);
        e.x = ini.e.x - ((ev.clientX - ini.x) * cw) / dispW / m.w;
        e.y = ini.e.y - ((ev.clientY - ini.y) * ch) / dispH / m.h;
        normalizar(m, ctx.t.ratio, e);
      }
      atualizarVivos(m, ctx.k);
    });
    const fim = () => { if (ini) { ini = null; alvo.classList.remove('arrastando'); if (S.editor) renderEditorLado(); gestoTerminou(ctx); } };
    alvo.addEventListener('pointerup', fim);
    alvo.addEventListener('pointercancel', fim);
    alvo.addEventListener('wheel', (ev) => {
      const m = qual();
      if (!m) return;
      const e = enq(m, ctx);
      ev.preventDefault();
      e.auto = false;
      const fator = Math.exp(-ev.deltaY * 0.0015);
      if (e.modo === 'encaixar') Object.assign(e, { modo: 'livre', escala: 1, px: 0.5, py: 0.5 });
      if (e.modo === 'livre') e.escala = limitar((e.escala || 1) * fator, 0.15, 4);
      else { e.zoom = limitar(e.zoom * fator, 1, 5); normalizar(m, ctx.t.ratio, e); }
      atualizarVivos(m, ctx.k);
      if (S.editor) renderEditorLado();
      gestoTerminou(ctx);
    }, { passive: false });
    alvo.addEventListener('dblclick', () => {
      const m = qual();
      if (!m) return;
      m.enq[ctx.k] = autoEnq(m, ctx.t.ratio, ctx.f);
      atualizarVivos(m, ctx.k);
      if (S.editor) renderEditorLado();
      gestoTerminou(ctx);
    });
  }

  // Quadro de uma mídia na proporção do formato (ou o vídeo com música, que troca de foto).
  function quadro(m, ctx, opts = {}) {
    const q = el('div', { class: 'sp-quadro' + (opts.classe ? ' ' + opts.classe : ''), style: { aspectRatio: String(ratioNum(ctx.t.ratio)) } });
    if (!m) {
      q.append(el('div', { class: 'sp-vazio' }, ico('camera'), el('span', null, opts.vazio || 'Sem mídia')));
      return q;
    }
    if (m.tipo === 'slideshow') {
      const cena = el('div', { class: 'sp-cena' });
      const reg = { cena, ctx, larg: opts.larg };
      S.shows.push(reg);
      pintarSlide(reg);
      q.append(cena,
        el('button', { type: 'button', class: 'sp-ctl-show', title: S.tocando ? 'Parar' : 'Ouvir com as fotos', onclick: () => alternarShow() },
          ico(S.tocando ? 'pausa' : 'play', '', !S.tocando), el('span', null, `♫ ${fmtSeg(duracoesShow(m.fotos.length).total)}`)));
      interacao(q, () => m.fotos[Math.min(S.slide, m.fotos.length - 1)], ctx);
    } else {
      q.append(postado(m, ctx, { larg: opts.larg }));
      interacao(q, () => m, ctx);
    }
    if (!opts.semEditar) {
      q.append(el('div', { class: 'sp-ctl' }, el('button', { type: 'button', onclick: () => abrirEditor(ctx.r.id, m.tipo === 'slideshow' ? S.slide : ctx.midias.indexOf(m)) }, ico('lapis'), 'Editar')));
    }
    return q;
  }

  function pintarSlide(reg) {
    const show = midiaShow();
    if (!show) return;
    const i = Math.min(S.slide, show.fotos.length - 1);
    const foto = show.fotos[i];
    const cv = postado(foto, reg.ctx, { larg: reg.larg });
    if (S.tocando) {
      cv.classList.add('entra');
      if (S.show.movimento) cv.classList.add(i % 2 ? 'kb-sai' : 'kb-entra');
      cv.style.setProperty('--d', `${duracoesShow(show.fotos.length).d}s`);
    }
    trocar(reg.cena, cv);
  }

  function atualizarShows() {
    S.shows = S.shows.filter((r) => r.cena.isConnected);
    for (const r of S.shows) pintarSlide(r);
  }

  function carrossel(ctx, opts = {}) {
    const { midias, chave } = ctx;
    const n = midias.length;
    const i = Math.min(S.idx[chave] || 0, Math.max(0, n - 1));
    const q = quadro(midias[i], ctx, { vazio: opts.vazio });
    if (n > 1) {
      const ir = (d) => { S.idx[chave] = (i + d + n) % n; renderTela(ctx.r); };
      if (i > 0) q.append(el('button', { type: 'button', class: 'sp-seta esq', 'aria-label': 'Anterior', onclick: () => ir(-1) }, ico('esq')));
      if (i < n - 1) q.append(el('button', { type: 'button', class: 'sp-seta dir', 'aria-label': 'Próxima', onclick: () => ir(1) }, ico('dir')));
      if (opts.contador !== false) q.append(el('span', { class: 'sp-contador' }, `${i + 1}/${n}`));
    }
    const pontos = n > 1 ? el('div', { class: 'sp-pontos' }, midias.map((_, k) => el('i', { class: k === i ? 'on' : '' }))) : null;
    return { q, pontos, i };
  }

  // Várias fotos, como o X, o Bluesky e o Facebook mostram (corte central de cada arquivo).
  function grade(ctx, estilo) {
    const { midias } = ctx;
    const n = midias.length;
    if (n <= 1) return quadro(midias[0], ctx, { vazio: 'Só texto' });
    const vis = midias.slice(0, estilo === 'fb' ? 5 : 4);
    const g = el('div', { class: `sp-grade sp-grade--${estilo} n${vis.length}` });
    vis.forEach((m, k) => {
      const cel = el('div', { class: 'sp-cel-grade' }, postado(m, ctx, { cobrir: true }));
      if (k === vis.length - 1 && n > vis.length) cel.append(el('span', { class: 'sp-mais-n' }, `+${n - vis.length}`));
      cel.append(el('div', { class: 'sp-ctl' }, el('button', { type: 'button', 'aria-label': 'Editar', onclick: () => abrirEditor(ctx.r.id, k) }, ico('lapis'))));
      interacao(cel, () => m, ctx);
      g.append(cel);
    });
    return g;
  }

  // ---------- texto ----------
  const RE_TOKEN = /(https?:\/\/[^\s]+)|(#[\p{L}\p{N}_]+)|(@[\w.]+)/gu;

  function textoRico(texto) {
    const frag = document.createDocumentFragment();
    let ult = 0;
    for (const mt of texto.matchAll(RE_TOKEN)) {
      if (mt.index > ult) frag.append(texto.slice(ult, mt.index));
      frag.append(el('span', { class: 'sp-tok' }, mt[0]));
      ult = mt.index + mt[0].length;
    }
    frag.append(texto.slice(ult));
    return frag;
  }

  function legenda(texto, linhas, opts = {}) {
    const corpo = el('div', { class: 'sp-leg', style: { '-webkit-line-clamp': String(linhas) } },
      opts.prefixo ? el('b', null, opts.prefixo + ' ') : null, textoRico(texto));
    const caixa = el('div', { class: 'sp-leg-caixa' + (opts.classe ? ' ' + opts.classe : '') }, corpo);
    if (!texto) return caixa;
    requestAnimationFrame(() => {
      if (corpo.scrollHeight > corpo.clientHeight + 2) {
        caixa.append(el('button', { type: 'button', class: 'sp-ver-mais', onclick: (ev) => { corpo.classList.add('aberta'); ev.currentTarget.remove(); } },
          opts.mais || 'mais'));
      }
    });
    return caixa;
  }

  const LINK_NO_TEXTO = new Set(['x', 'threads', 'bluesky', 'mastodon', 'telegram', 'discord', 'linkedin', 'facebook', 'youtube', 'whatsapp']);

  function textoFinal(r, f) {
    if (f.sem_texto) return '';
    const st = S.redes[r.id];
    let t = (st.textoProprio ? st.texto : S.texto) || '';
    if (S.link && LINK_NO_TEXTO.has(r.id) && !t.includes(S.link)) t = t ? `${t.trimEnd()}\n\n${S.link}` : S.link;
    return t;
  }

  const SEG = typeof Intl !== 'undefined' && Intl.Segmenter ? new Intl.Segmenter('pt', { granularity: 'grapheme' }) : null;
  const grafemas = (t) => (SEG ? [...SEG.segment(t)].map((s) => s.segment) : Array.from(t));
  const EMOJI = /\p{Extended_Pictographic}/u;

  function pesoX(t) {
    // twitter-text v3: link = 23; emoji = 2; latim/pontuação comum = 1; o resto (CJK…) = 2.
    let n = 0;
    const semLinks = t.replace(/https?:\/\/[^\s]+/g, () => { n += 23; return ''; });
    for (const g of grafemas(semLinks)) {
      if (EMOJI.test(g)) { n += 2; continue; }
      for (const c of g) {
        const cp = c.codePointAt(0);
        n += (cp <= 4351 || (cp >= 8192 && cp <= 8205) || (cp >= 8208 && cp <= 8223) || (cp >= 8242 && cp <= 8247)) ? 1 : 2;
      }
    }
    return n;
  }

  function contar(r, t) {
    const u = r.texto.unidade;
    if (u === 'x') return pesoX(t);
    if (u === 'grafemas') return grafemas(t).length;
    if (u === 'threads') return grafemas(t).reduce((n, g) => n + (EMOJI.test(g) ? new TextEncoder().encode(g).length : 1), 0);
    if (r.id === 'mastodon') return Array.from(t.replace(/https?:\/\/[^\s]+/g, 'x'.repeat(23))).length;
    return Array.from(t).length;
  }

  function limiteTexto(r, midias) {
    if (r.id === 'mastodon') return (perfil('mastodon') && perfil('mastodon').extra && perfil('mastodon').extra.max_texto) || r.texto.max;
    if (r.id === 'telegram' && !midias.length) return r.texto.max_sem_midia;
    return r.texto.max;
  }

  const hashtags = (t) => (t.match(/(^|[^\w&])#[\p{L}\p{N}_]+/gu) || []).length;
  const mencoes = (t) => (t.match(/(^|[^\w])@[\w.]+/g) || []).length;

  // ---------- fotos com música ----------
  const T_TRANSICAO = 0.6;

  // Mesma conta de SocialPreview/midia.py (duracoes_show).
  function duracoesShow(n, maxS) {
    const t = S.show.transicao !== 'corte' && n > 1 ? T_TRANSICAO : 0;
    let d = Math.max(1, Number(S.show.durFoto) || 3);
    let total = n * d - (n - 1) * t;
    if (maxS && total > maxS) { d = Math.max(t + 0.5, (maxS + (n - 1) * t) / n); total = n * d - (n - 1) * t; }
    return { d, t, total };
  }

  const fotos = () => S.midias.filter((m) => m.tipo === 'imagem');
  const showLigado = () => S.show.ativo && S.show.audio && fotos().length > 0;

  // A "mídia" vídeo-com-música: as fotos, na ordem, viram um vídeo só.
  const SHOW = {
    id: 'show', tipo: 'slideshow',
    get fotos() { return fotos(); },
    get w() { return (fotos()[0] || {}).w || 1080; },
    get h() { return (fotos()[0] || {}).h || 1920; },
    get dur() { return duracoesShow(fotos().length).total; },
  };
  const midiaShow = () => (showLigado() ? SHOW : null);

  function opcoesShow() {
    return { dur_foto: S.show.durFoto, transicao: S.show.transicao, movimento: S.show.movimento,
      inicio: S.show.inicio, volume: S.show.volume, fade: S.show.fade };
  }

  // ---------- regras por formato ----------
  // Vídeo com música só onde um vídeo sozinho é um post válido (o Feed do Instagram não é: vai como Reels).
  const aceitaShow = (f) => f.midia.includes('video') && !f.video_so_carrossel;

  function midiasPara(r, f) {
    if (showLigado() && aceitaShow(f)) return [SHOW];
    let lista = S.midias.filter((m) => f.midia.includes(m.tipo));
    if (!f.mistura && !f.cada_item_um_post && lista.length) {
      const t0 = lista[0].tipo;
      lista = lista.filter((m) => m.tipo === t0);
    }
    if (f.max_videos && lista.length && lista[0].tipo === 'video') lista = lista.slice(0, f.max_videos);
    if (f.video_so_carrossel && lista.length === 1 && lista[0].tipo === 'video') lista = [];
    return lista.slice(0, f.max_itens);
  }

  function avisos(r, f) {
    const lista = midiasPara(r, f);
    const out = [];
    const show = lista[0] && lista[0].tipo === 'slideshow';
    if (show) {
      const { total, d } = duracoesShow(fotos().length, (f.video || {}).max_s);
      const livre = duracoesShow(fotos().length).total;
      out.push({ nivel: 'info', msg: `Vídeo com música: ${fotos().length} foto${fotos().length > 1 ? 's' : ''}, ${fmtSeg(total)}.` });
      if (total < livre - 0.05) out.push({ nivel: 'aviso', msg: `O formato aceita até ${fmtDur(f.video.max_s)}: cada foto fica ${fmtSeg(d)}.` });
      if (f.video && f.video.min_s && total < f.video.min_s) out.push({ nivel: 'erro', msg: `O vídeo precisa ter pelo menos ${f.video.min_s} s: aumente o tempo de cada foto.` });
      if (S.midias.some((m) => m.tipo === 'video')) out.push({ nivel: 'aviso', msg: 'No vídeo com música só entram as fotos.' });
    } else if (showLigado() && !aceitaShow(f)) {
      out.push({ nivel: 'info', msg: f.video_so_carrossel ? `No ${f.nome} vão as fotos; o vídeo com música vai em Reels.` : `${f.nome} não aceita vídeo: vão as fotos, sem música.` });
    }
    const fora = show ? 0 : S.midias.length - lista.length;
    if (lista.length < (f.min_itens || 0)) {
      const so = f.midia.length === 1 ? (f.midia[0] === 'video' ? 'um vídeo' : 'uma foto') : 'uma foto ou vídeo';
      let msg = `${f.nome} precisa de ${so}.`;
      if (f.video_so_carrossel && S.midias.length === 1 && S.midias[0].tipo === 'video') msg = 'Vídeo sozinho no Instagram vai como Reels: escolha Reels.';
      if (f.midia.length === 1 && f.midia[0] === 'video' && fotos().length && !showLigado()) msg += ' Ou adicione uma música para as fotos virarem vídeo.';
      out.push({ nivel: 'erro', msg });
    } else if (fora > 0 && S.midias.length) {
      const motivo = !f.midia.includes('video') && S.midias.some((m) => m.tipo === 'video') ? ' (não aceita vídeo)'
        : !f.midia.includes('imagem') && S.midias.some((m) => m.tipo === 'imagem') ? ' (não aceita foto)'
          : f.max_itens < S.midias.length ? ` (máximo ${f.max_itens})` : ' (não mistura foto e vídeo)';
      out.push({ nivel: 'aviso', msg: `${fora === 1 ? '1 mídia fica' : fora + ' mídias ficam'} de fora${motivo}.` });
    }
    for (const m of lista) {
      if (m.tipo !== 'video' || !f.video) continue;
      if (f.video.max_s && m.dur > f.video.max_s + 0.5) out.push({ nivel: 'aviso', msg: `O vídeo será cortado em ${fmtDur(f.video.max_s)} (limite do formato).` });
      if (f.video.min_s && m.dur < f.video.min_s) out.push({ nivel: 'erro', msg: `O vídeo precisa ter pelo menos ${f.video.min_s} s.` });
    }
    if (!f.sem_texto) {
      const t = textoFinal(r, f);
      const lim = limiteTexto(r, lista);
      const n = contar(r, t);
      if (n > lim) out.push({ nivel: 'erro', msg: `Texto com ${n} de ${lim}${r.texto.unidade === 'x' ? ' (peso da X)' : ''}: corte ${n - lim}.` });
      if (r.texto.hashtags && hashtags(t) > r.texto.hashtags) out.push({ nivel: 'erro', msg: `Máximo de ${r.texto.hashtags} hashtags.` });
      if (r.texto.mencoes && mencoes(t) > r.texto.mencoes) out.push({ nivel: 'erro', msg: `Máximo de ${r.texto.mencoes} menções.` });
      if (!t.trim() && !lista.length) out.push({ nivel: 'erro', msg: 'Post vazio: escreva um texto ou adicione mídia.' });
      if (r.id === 'instagram' && S.link) out.push({ nivel: 'info', msg: 'Link em legenda do Instagram não é clicável: ele fica de fora (use o link da bio).' });
    }
    if (r.texto.titulo && !S.titulo.trim() && r.id !== 'link') out.push({ nivel: 'info', msg: 'Sem título: vai a primeira linha do texto.' });
    if (r.api && !(perfil(r.id))) out.push({ nivel: 'info', msg: 'Conta não conectada: vai pelo modo assistido (arquivo + texto copiado).' });
    if (f.nota && lista.length > 1) out.push({ nivel: 'info', msg: f.nota });
    return out;
  }

  // Escolhe sozinho o formato e a proporção que combinam com a mídia (até a pessoa escolher outro).
  function autoAjustar(r) {
    const st = S.redes[r.id];
    const efetivas = showLigado() ? [SHOW] : S.midias;
    const asp = efetivas.length ? efetivas[0].w / efetivas[0].h : null;
    if (!st.fmtManual) {
      const tipos = new Set(efetivas.map((m) => (m.tipo === 'slideshow' ? 'video' : m.tipo)));
      let cand = r.formatos.filter((f) => midiasPara(r, f).length >= (f.min_itens || 0) && (efetivas.length === 0 || midiasPara(r, f).length));
      if (!cand.length) cand = r.formatos.filter((f) => (f.min_itens || 0) === 0);
      if (!cand.length) cand = r.formatos.slice();
      const semStory = cand.filter((f) => !f.cada_item_um_post);
      if (semStory.length) cand = semStory;
      if (tipos.size === 1 && tipos.has('video')) {
        const soVideo = cand.filter((f) => f.midia.length === 1 && f.midia[0] === 'video');
        if (soVideo.length) cand = soVideo;
      }
      if (asp && cand.length > 1) {
        const dist = (f) => Math.min(...f.tamanhos.map((t) => Math.abs(Math.log(ratioNum(t.ratio) / asp))));
        cand.sort((a, b) => dist(a) - dist(b) + (r.formatos.indexOf(a) - r.formatos.indexOf(b)) * 0.001);
      }
      st.formato = cand[0].id;
    }
    const f = formatoDe(r);
    if (!st.ratioManual || !f.tamanhos.some((t) => t.ratio === st.ratio)) {
      st.ratioManual = false;
      let melhor = f.tamanhos[0];
      if (asp) {
        for (const t of f.tamanhos) {
          if (Math.abs(Math.log(ratioNum(t.ratio) / asp)) < Math.abs(Math.log(ratioNum(melhor.ratio) / asp)) - 0.02) melhor = t;
        }
      }
      st.ratio = melhor.ratio;
    }
  }

  // ---------- telas (simulação de cada app) ----------
  function avatar(p, cls) {
    const nome = (p && (p.nome || p.usuario)) || 'Você';
    const ini = nome.replace(/^@/, '').charAt(0).toUpperCase() || 'V';
    return el('span', { class: 'sp-av ' + (cls || '') },
      p && p.avatar ? el('img', { src: p.avatar, alt: '', referrerpolicy: 'no-referrer', loading: 'lazy' }) : ini);
  }
  const usuario = (p, pad) => (p && p.usuario) || pad || 'seu.perfil';
  const nomeExib = (p, pad) => (p && p.nome) || pad || 'Seu perfil';
  const nomeMusica = (p) => (showLigado() ? S.show.audio.nome.replace(/\.[^.]+$/, '') : `${usuario(p)} · Áudio original`);

  function zonas(f) {
    if (!f.zonas || !S.zonas) return null;
    const z = f.zonas;
    return el('div', { class: 'sp-zonas', 'aria-hidden': 'true' },
      z.topo ? el('i', { class: 'z-topo', style: { height: z.topo * 100 + '%' } }) : null,
      z.base ? el('i', { class: 'z-base', style: { height: z.base * 100 + '%' } }) : null,
      z.direita ? el('i', { class: 'z-dir', style: { width: z.direita * 100 + '%', bottom: (z.base || 0) * 100 + '%', top: (z.topo || 0) * 100 + '%' } }) : null);
  }

  function telaVertical(ctx, extras) {
    const { midias, f } = ctx;
    const n = midias.length;
    const i = Math.min(S.idx[ctx.chave] || 0, Math.max(0, n - 1));
    const q = quadro(midias[i], ctx, { classe: 'sp-quadro-cheio', vazio: f.midia.includes('video') && f.midia.length === 1 ? 'Adicione um vídeo (ou fotos + música)' : 'Adicione mídia' });
    if (n > 1) {
      const ir = (d) => { S.idx[ctx.chave] = (i + d + n) % n; renderTela(ctx.r); };
      q.append(el('button', { type: 'button', class: 'sp-toque esq', 'aria-label': 'Anterior', onclick: () => ir(-1) }),
        el('button', { type: 'button', class: 'sp-toque dir', 'aria-label': 'Próxima', onclick: () => ir(1) }));
    }
    return el('div', { class: 'sp-vert' }, q, zonas(f), extras({ i, n }));
  }

  function barrasStory(n, i) {
    return el('div', { class: 'sp-barras' }, Array.from({ length: Math.max(1, n) }, (_, k) => el('i', { class: k < i ? 'cheia' : k === i ? 'atual' : '' })));
  }

  const TELAS = {
    'ig-feed'(ctx) {
      const p = ctx.perfil;
      const { q, pontos } = carrossel(ctx, { vazio: 'Adicione fotos' });
      const raiz = el('div', { class: 'ig' },
        el('div', { class: 'ig-cab' }, avatar(p, 'anel'), el('b', null, usuario(p)), el('span', { class: 'sp-flex' }), ico('mais')),
        q,
        el('div', { class: 'ig-acoes' }, ico('coracao'), ico('comentario'), ico('enviar'), el('span', { class: 'sp-flex' }, pontos), ico('salvar')),
        el('div', { class: 'ig-curt' }, '1.024 curtidas'),
        legenda(ctx.texto, 2, { prefixo: usuario(p), mais: 'mais' }),
        el('div', { class: 'ig-tempo' }, 'Agora'));
      if (ctx.f.grade && ctx.midias.length && ctx.midias[0].tipo !== 'slideshow') {
        const tile = el('div', { class: 'ig-tile' }, postado(ctx.midias[0], ctx, { cobrir: true }));
        raiz.append(el('div', { class: 'ig-grade' },
          el('div', { class: 'ig-grade-rot' }, 'Na grade do perfil (corte 3:4)'),
          el('div', { class: 'ig-grade-tiles' }, tile, el('div', { class: 'ig-tile vazio' }), el('div', { class: 'ig-tile vazio' }))));
      }
      return raiz;
    },
    'ig-story'(ctx) {
      const p = ctx.perfil;
      return telaVertical(ctx, ({ i, n }) => [
        el('div', { class: 'sv-topo' }, barrasStory(n, i),
          el('div', { class: 'sv-quem' }, avatar(p), el('b', null, usuario(p)), el('span', { class: 'sv-tempo' }, 'agora'), el('span', { class: 'sp-flex' }), ico('mais'), ico('fechar')),
          showLigado() ? el('div', { class: 'sv-musica' }, ico('musica'), nomeMusica(p)) : null),
        el('div', { class: 'sv-base' }, el('span', { class: 'sv-msg' }, 'Enviar mensagem'), ico('coracao'), ico('enviar')),
      ]);
    },
    'fb-story'(ctx) {
      const p = ctx.perfil;
      return telaVertical(ctx, ({ i, n }) => [
        el('div', { class: 'sv-topo' }, barrasStory(n, i),
          el('div', { class: 'sv-quem' }, avatar(p), el('b', null, nomeExib(p)), el('span', { class: 'sv-tempo' }, 'Agora'), el('span', { class: 'sp-flex' }), ico('mais'), ico('fechar'))),
        el('div', { class: 'sv-base' }, el('span', { class: 'sv-msg' }, 'Responder…'), ico('curtir'), ico('coracao')),
      ]);
    },
    'wa-status'(ctx) {
      const p = ctx.perfil;
      return telaVertical(ctx, ({ i, n }) => [
        el('div', { class: 'sv-topo' }, barrasStory(n, i),
          el('div', { class: 'sv-quem' }, avatar(p), el('div', null, el('b', null, 'Meu status'), el('div', { class: 'sv-tempo' }, 'agora mesmo')))),
        ctx.texto ? el('div', { class: 'wa-leg' }, textoRico(ctx.texto)) : null,
        el('div', { class: 'sv-base wa' }, el('span', { class: 'sv-msg' }, 'Responder')),
      ]);
    },
    'ig-reels'(ctx) { return reels(ctx, 'ig'); },
    'fb-reels'(ctx) { return reels(ctx, 'fb'); },
    'yt-shorts'(ctx) { return reels(ctx, 'yt'); },
    tiktok(ctx) { return reels(ctx, 'tt'); },
    'fb-feed'(ctx) {
      const p = ctx.perfil;
      return el('div', { class: 'fb' },
        el('div', { class: 'fb-cab' }, avatar(p), el('div', null, el('b', null, nomeExib(p, 'Sua Página')), el('div', { class: 'fb-sub' }, 'Agora · ', ico('globo'))), el('span', { class: 'sp-flex' }), ico('mais')),
        ctx.texto ? legenda(ctx.texto, 5, { mais: 'Ver mais', classe: 'fb-txt' }) : null,
        grade(ctx, 'fb'),
        el('div', { class: 'fb-num' }, el('span', null, '87'), el('span', null, '12 comentários')),
        el('div', { class: 'fb-acoes' }, el('span', null, ico('curtir'), 'Curtir'), el('span', null, ico('comentario'), 'Comentar'), el('span', null, ico('compartilhar'), 'Compartilhar')));
    },
    threads(ctx) {
      const p = ctx.perfil;
      const { midias } = ctx;
      let media = null;
      if (midias.length === 1) media = quadro(midias[0], ctx, { classe: 'th-um' });
      else if (midias.length > 1) {
        media = el('div', { class: 'th-faixa' }, midias.map((m) => {
          const q = quadro(m, ctx, { classe: 'th-item' });
          q.style.width = `${Math.round(210 * ratioNum(ctx.t.ratio))}px`;
          return q;
        }));
      }
      return el('div', { class: 'th' },
        el('div', { class: 'th-col' }, avatar(p), el('i', { class: 'th-linha' })),
        el('div', { class: 'th-corpo' },
          el('div', { class: 'th-cab' }, el('b', null, usuario(p)), el('span', { class: 'th-tempo' }, 'agora'), el('span', { class: 'sp-flex' }), ico('mais')),
          ctx.texto ? el('div', { class: 'th-txt' }, textoRico(ctx.texto)) : null,
          media,
          el('div', { class: 'th-acoes' }, ico('coracao'), ico('comentario'), ico('repost'), ico('enviar'))));
    },
    x(ctx) {
      const p = ctx.perfil;
      return el('div', { class: 'xx' },
        avatar(p),
        el('div', { class: 'xx-corpo' },
          el('div', { class: 'xx-cab' }, el('b', null, nomeExib(p)), el('span', { class: 'xx-at' }, `@${usuario(p, 'seuperfil')} · agora`), el('span', { class: 'sp-flex' }), ico('mais')),
          ctx.texto ? el('div', { class: 'xx-txt' }, textoRico(ctx.texto)) : null,
          ctx.midias.length ? el('div', { class: 'xx-midia' }, grade(ctx, 'x')) : null,
          el('div', { class: 'xx-acoes' }, ico('comentario'), ico('repost'), ico('coracao'), ico('grafico'), el('span', null, ico('salvar'), ico('compartilhar')))));
    },
    linkedin(ctx) {
      const p = ctx.perfil;
      return el('div', { class: 'li' },
        el('div', { class: 'li-cab' }, avatar(p), el('div', null, el('b', null, nomeExib(p)), el('div', { class: 'li-sub' }, 'Seu título profissional'), el('div', { class: 'li-sub' }, 'Agora · ', ico('globo'))), el('span', { class: 'sp-flex' }), el('span', { class: 'li-seguir' }, '+ Seguir')),
        ctx.texto ? legenda(ctx.texto, 3, { mais: '…mais', classe: 'li-txt' }) : null,
        grade(ctx, 'fb'),
        el('div', { class: 'li-num' }, '64 · 9 comentários'),
        el('div', { class: 'li-acoes' }, el('span', null, ico('curtir'), 'Gostei'), el('span', null, ico('comentario'), 'Comentar'), el('span', null, ico('repost'), 'Compartilhar'), el('span', null, ico('enviar'), 'Enviar')));
    },
    bluesky(ctx) {
      const p = ctx.perfil;
      return el('div', { class: 'bs' },
        avatar(p),
        el('div', { class: 'xx-corpo' },
          el('div', { class: 'xx-cab' }, el('b', null, nomeExib(p)), el('span', { class: 'xx-at' }, `@${usuario(p, 'voce.bsky.social')} · agora`)),
          ctx.texto ? el('div', { class: 'xx-txt' }, textoRico(ctx.texto)) : null,
          ctx.midias.length ? el('div', { class: 'xx-midia' }, grade(ctx, 'x')) : null,
          el('div', { class: 'xx-acoes' }, ico('comentario'), ico('repost'), ico('coracao'), ico('mais'))));
    },
    mastodon(ctx) {
      const p = ctx.perfil;
      return el('div', { class: 'ma' },
        el('div', { class: 'ma-cab' }, avatar(p), el('div', null, el('b', null, nomeExib(p)), el('div', { class: 'ma-at' }, `@${usuario(p, 'voce@mastodon.social')}`)), el('span', { class: 'sp-flex' }), el('span', { class: 'ma-at' }, 'agora')),
        ctx.texto ? el('div', { class: 'ma-txt' }, textoRico(ctx.texto)) : null,
        ctx.midias.length ? el('div', { class: 'ma-midia' }, grade(ctx, 'x')) : null,
        el('div', { class: 'xx-acoes' }, ico('comentario'), ico('repost'), ico('coracao'), ico('salvar'), ico('mais')));
    },
    telegram(ctx) {
      const p = ctx.perfil;
      return el('div', { class: 'tg' },
        el('div', { class: 'tg-cab' }, avatar(p), el('div', null, el('b', null, nomeExib(p, 'Seu canal')), el('div', { class: 'tg-sub' }, '1.204 inscritos'))),
        el('div', { class: 'tg-chat' },
          el('div', { class: 'tg-bolha' },
            ctx.midias.length ? grade(ctx, 'fb') : null,
            ctx.texto ? el('div', { class: 'tg-txt' }, textoRico(ctx.texto)) : null,
            el('div', { class: 'tg-pe' }, ico('olho'), '1', el('span', null, '12:00')))));
    },
    discord(ctx) {
      const p = ctx.perfil;
      return el('div', { class: 'dc' },
        avatar(p),
        el('div', { class: 'dc-corpo' },
          el('div', { class: 'dc-cab' }, el('b', null, nomeExib(p, 'Webhook')), el('span', { class: 'dc-app' }, 'APP'), el('span', { class: 'dc-hora' }, 'Hoje às 12:00')),
          ctx.texto ? el('div', { class: 'dc-txt' }, textoRico(ctx.texto)) : null,
          ctx.midias.length ? el('div', { class: 'dc-midia' }, grade(ctx, 'x')) : null));
    },
    pinterest(ctx) {
      const p = ctx.perfil;
      const titulo = S.titulo || (S.texto.split('\n')[0] || '').slice(0, 100);
      const q = quadro(ctx.midias[0], ctx, { classe: 'pi-img', vazio: 'Adicione uma foto' });
      q.append(el('span', { class: 'pi-salvar' }, 'Salvar'));
      return el('div', { class: 'pi' },
        el('div', { class: 'pi-col' }, q,
          titulo ? el('b', { class: 'pi-tit' }, titulo) : null,
          el('div', { class: 'pi-quem' }, avatar(p), el('span', null, nomeExib(p)))),
        el('div', { class: 'pi-col fant' }, el('i', { style: { aspectRatio: '3/4' } }), el('i', { style: { aspectRatio: '1/1' } })));
    },
    'yt-video'(ctx) {
      const p = ctx.perfil;
      const titulo = S.titulo || (S.texto.split('\n')[0] || 'Título do vídeo').slice(0, 100);
      const q = quadro(ctx.midias[0], ctx, { vazio: 'Adicione um vídeo (ou fotos + música)' });
      if (ctx.midias[0]) q.append(el('span', { class: 'yt-dur' }, fmtDur(ctx.midias[0].dur)));
      return el('div', { class: 'yt' }, q,
        el('div', { class: 'yt-info' }, avatar(p), el('div', null, el('b', { class: 'yt-tit' }, titulo), el('div', { class: 'yt-sub' }, `${nomeExib(p, 'Seu canal')} · 0 visualizações · agora`)), ico('mais')));
    },
    og(ctx) {
      const titulo = S.titulo || (S.texto.split('\n')[0] || 'Título da página').slice(0, 70);
      let dominio = 'seusite.com.br';
      try { if (S.link) dominio = new URL(S.link).hostname.replace(/^www\./, ''); } catch { /* link incompleto */ }
      return el('div', { class: 'og' },
        quadro(ctx.midias[0], ctx, { vazio: 'Adicione a imagem do link' }),
        el('div', { class: 'og-txt' }, el('div', { class: 'og-dom' }, dominio.toUpperCase()), el('b', null, titulo),
          el('div', { class: 'og-desc' }, (S.texto || 'Descrição que aparece quando o link é compartilhado.').slice(0, 200))));
    },
  };

  function reels(ctx, estilo) {
    const p = ctx.perfil;
    const lado = {
      ig: [['coracao', '1,2 mil'], ['comentario', '48'], ['repost', ''], ['enviar', '31'], ['mais', '']],
      fb: [['curtir', '1,2 mil'], ['comentario', '48'], ['compartilhar', '31'], ['mais', '']],
      yt: [['curtir', '1,2 mil'], ['descurtir', 'Não gostei'], ['comentario', '48'], ['compartilhar', 'Compartilhar'], ['remix', 'Remix']],
      tt: [['coracao', '1,2 mil'], ['comentario', '48'], ['salvar', '96'], ['compartilhar', '31']],
    }[estilo];
    return telaVertical(ctx, ({ i, n }) => [
      estilo === 'tt' ? el('div', { class: 'rv-abas' }, el('span', null, 'Seguindo'), el('b', null, 'Para você'), ico('lupa')) : null,
      estilo === 'yt' ? el('div', { class: 'rv-abas yt' }, ico('lupa'), ico('mais')) : null,
      el('div', { class: 'rv-lado' },
        estilo === 'tt' ? el('span', { class: 'rv-av' }, avatar(p), el('i', null, '+')) : null,
        lado.map(([ic, num]) => el('span', { class: 'rv-acao' }, ico(ic, '', ic === 'coracao' && estilo === 'tt'), num ? el('small', null, num) : null))),
      el('div', { class: 'rv-base' },
        el('div', { class: 'rv-quem' }, estilo === 'tt' ? null : avatar(p), el('b', null, estilo === 'tt' ? '@' + usuario(p) : usuario(p)),
          estilo === 'tt' ? null : el('span', { class: 'rv-seguir' }, estilo === 'yt' ? 'Inscrever-se' : 'Seguir')),
        ctx.texto ? legenda(ctx.texto, estilo === 'ig' ? 1 : 2, { mais: 'mais', classe: 'rv-leg' }) : null,
        estilo === 'yt' && !showLigado() ? null : el('div', { class: 'rv-audio' }, ico('musica'), nomeMusica(p)),
        n > 1 ? el('div', { class: 'sp-pontos claro' }, Array.from({ length: n }, (_, k) => el('i', { class: k === i ? 'on' : '' }))) : null),
    ]);
  }

  // ---------- cartões da prévia ----------
  function contexto(r) {
    const f = formatoDe(r);
    const t = tamanhoDe(r, f);
    const midias = midiasPara(r, f);
    return { r, f, t, midias, texto: textoFinal(r, f), perfil: perfil(r.id), chave: `${r.id}:${f.id}`, k: `${r.id}:${f.id}:${t.ratio}` };
  }

  // As fotos (reais) que aparecem nesta rede: no vídeo com música, as do slideshow.
  const fotosDoCtx = (ctx) => ctx.midias.flatMap((m) => (m.tipo === 'slideshow' ? m.fotos : [m]));

  function estadoEnq(ctx) {
    const ms = fotosDoCtx(ctx);
    if (!ms.length) return null;
    const es = ms.map((m) => enq(m, ctx));
    if (es.some((e) => !e.auto)) return { auto: false, txt: 'ajustado à mão' };
    const motivos = [...new Set(es.map((e) => e.motivo))];
    return { auto: true, txt: 'automático', motivo: motivos.length === 1 ? motivos[0] : 'cada foto no seu melhor enquadramento' };
  }

  function tela(r) {
    const st = S.redes[r.id];
    const ctx = contexto(r);
    const { f, t } = ctx;
    const p = ctx.perfil;
    const est = estadoEnq(ctx);
    const cab = el('header', { class: 'sp-tela-cab' },
      el('div', { class: 'sp-tela-id' },
        el('span', { class: 'sp-tela-marca', style: { '--cor': r.cor } }, marca(r.marca || r.id)),
        el('div', { class: 'sp-tela-nome' }, el('b', null, r.nome),
          el('div', { class: 'sp-tela-conta' }, r.api ? (p ? `@${p.usuario || p.nome}` : 'sem conta conectada') : 'modo assistido')),
        est ? el('button', { type: 'button', class: 'sp-editar', onclick: () => abrirEditor(r.id, 0), title: 'Ajustar o enquadramento só desta rede' }, ico('lapis'), 'Editar') : null),
      el('div', { class: 'sp-tela-opcoes' },
        r.formatos.length > 1 ? el('div', { class: 'sp-seg', role: 'group', 'aria-label': 'Formato' },
          r.formatos.map((fo) => el('button', { type: 'button', 'aria-pressed': String(fo.id === f.id),
            onclick: () => { st.formato = fo.id; st.fmtManual = true; st.ratioManual = false; autoAjustar(r); renderTela(r); atualizarResumo(); } }, fo.nome))) : null,
        f.tamanhos.length > 1 ? el('div', { class: 'sp-seg mini', role: 'group', 'aria-label': 'Proporção' },
          f.tamanhos.map((tt) => el('button', { type: 'button', 'aria-pressed': String(tt.ratio === t.ratio), title: `${tt.w}×${tt.h} px`,
            onclick: () => { st.ratio = tt.ratio; st.ratioManual = true; renderTela(r); } }, ratioTxt(tt.ratio)))) : null));

    const tipoTela = f.tela;
    const vertical = (f.tamanhos.length === 1 && f.tamanhos[0].ratio === '9:16') || ['ig-story', 'fb-story', 'ig-reels', 'fb-reels', 'yt-shorts', 'tiktok', 'wa-status'].includes(tipoTela);
    const celular = el('div', { class: `sp-celular sp-t-${tipoTela}${vertical ? ' vertical' : ''}` }, (TELAS[tipoTela] || TELAS.x)(ctx));

    const lista = avisos(r, f);
    if (est && est.auto && est.motivo) lista.unshift({ nivel: 'auto', msg: `Automático: ${est.motivo}.` });
    const pe = el('footer', { class: 'sp-tela-pe' });
    const medidas = el('div', { class: 'sp-medidas' }, el('span', null, `${t.w}×${t.h}`), el('span', null, ratioTxt(t.ratio)));
    if (est) medidas.append(el('span', { class: 'sp-estado-enq' + (est.auto ? ' auto' : '') }, est.txt));
    if (!f.sem_texto) {
      const n = contar(r, ctx.texto), lim = limiteTexto(r, ctx.midias);
      medidas.append(el('span', { class: n > lim ? 'passou' : '' }, `${n.toLocaleString('pt-BR')}/${lim.toLocaleString('pt-BR')}`));
      if (r.texto.hashtags) medidas.append(el('span', { class: hashtags(ctx.texto) > r.texto.hashtags ? 'passou' : '' }, `# ${hashtags(ctx.texto)}/${r.texto.hashtags}`));
    }
    pe.append(medidas);
    if (lista.length) pe.append(el('ul', { class: 'sp-avisos' }, lista.map((a) => el('li', { class: a.nivel }, a.msg))));
    if (!f.sem_texto && r.id !== 'link') {
      if (st.textoProprio) {
        const ta = el('textarea', { class: 'sp-proprio', rows: 4, 'aria-label': `Texto só para ${r.nome}` });
        ta.value = st.texto ?? S.texto;
        ta.addEventListener('input', () => { st.texto = ta.value; gravarLS(); agendarTela(r); });
        pe.append(ta, el('button', { type: 'button', class: 'sp-linkbtn', onclick: () => { st.textoProprio = false; st.texto = null; gravarLS(); renderTela(r); atualizarResumo(); } }, 'Voltar ao texto geral'));
      } else {
        pe.append(el('button', { type: 'button', class: 'sp-linkbtn', onclick: () => { st.textoProprio = true; st.texto = S.texto; gravarLS(); renderTela(r); } }, `Texto só para ${r.nome}`));
      }
    }
    return el('article', { class: 'sp-tela preview-card', dataset: { rede: r.id, k: ctx.k }, style: { '--cor': r.cor } }, cab, celular, pe);
  }

  function renderTela(r) {
    const velho = document.querySelector(`.sp-tela[data-rede="${r.id}"]`);
    if (!velho) return;
    const foco = document.activeElement && velho.contains(document.activeElement) && document.activeElement.classList.contains('sp-proprio');
    const pos = foco ? document.activeElement.selectionStart : null;
    const novo = tela(r);
    velho.replaceWith(novo);
    if (foco) { const ta = novo.querySelector('.sp-proprio'); ta.focus(); ta.setSelectionRange(pos, pos); }
  }

  const pendentes = new Set();
  function agendarTela(r) {
    pendentes.add(r.id);
    clearTimeout(agendarTela.t);
    agendarTela.t = setTimeout(() => {
      for (const id of pendentes) renderTela(rede(id));
      pendentes.clear();
      atualizarResumo();
    }, 140);
  }

  function ativas() { return S.cat.redes.filter((r) => S.redes[r.id].ativa); }

  function renderTelas() {
    S.vivos = [];
    S.shows = [];
    const lista = ativas();
    const caixa = $('#sp-telas');
    if (!lista.length) trocar(caixa, el('div', { class: 'sp-nada' }, 'Ligue pelo menos uma rede em "Onde publicar".'));
    else trocar(caixa, ...lista.map(tela));
    atualizarResumo();
  }

  let temporizadorTexto = null;
  function textoMudou() {
    clearTimeout(temporizadorTexto);
    temporizadorTexto = setTimeout(() => { renderTelas(); gravarLS(); }, 160);
  }

  // ---------- editor de enquadramento (uma rede) ----------
  function abrirEditor(rid, idx) {
    const r = rede(rid);
    const ctx = contexto(r);
    const lista = fotosDoCtx(ctx);
    if (!lista.length) { aviso('Adicione uma foto ou vídeo primeiro.'); return; }
    S.editor = { rid, idx: limitar(idx || 0, 0, lista.length - 1) };
    renderEditor();
    const d = $('#sp-editor');
    if (!d.open) d.showModal();
  }

  function editorCtx() {
    const r = rede(S.editor.rid);
    const ctx = contexto(r);
    const lista = fotosDoCtx(ctx);
    S.editor.idx = limitar(S.editor.idx, 0, lista.length - 1);
    return { r, ctx, lista, m: lista[S.editor.idx] };
  }

  function renderEditor() {
    const { r, ctx, lista, m } = editorCtx();
    const R = ratioNum(ctx.t.ratio);
    const altMax = Math.max(260, Math.min(window.innerHeight * 0.66, 720));
    const larg = Math.round(Math.min(620, altMax * R, window.innerWidth - 80));
    const q = el('div', { class: 'sp-quadro sp-ed-quadro', style: { aspectRatio: String(R), width: `${larg}px` } },
      postado(m, ctx, { larg: Math.min(1600, larg * 2) }), zonas(ctx.f),
      S.tercos ? el('div', { class: 'sp-tercos', 'aria-hidden': 'true' }, el('i'), el('i'), el('i'), el('i')) : null);
    interacao(q, () => editorCtx().m, ctx);
    trocar($('#sp-ed-titulo'),
      el('span', { class: 'sp-tela-marca', style: { '--cor': r.cor } }, marca(r.marca || r.id)),
      el('span', null, el('b', null, `${r.nome} · ${ctx.f.nome}`), el('small', null, `${ratioTxt(ctx.t.ratio)} · ${ctx.t.w}×${ctx.t.h} px · o ajuste vale só aqui`)));
    trocar($('#sp-ed-palco'), q,
      lista.length > 1 ? el('div', { class: 'sp-ed-fotos' }, lista.map((mm, i) => {
        const cv = el('canvas', { width: 96, height: 96 });
        desenhar(cv.getContext('2d'), mm, 96, 96, { modo: 'preencher', x: 0.5, y: 0.5, zoom: 1 });
        return el('button', { type: 'button', 'aria-pressed': String(i === S.editor.idx), 'aria-label': `Foto ${i + 1}`,
          onclick: () => { S.editor.idx = i; renderEditor(); } }, cv, enq(mm, ctx).auto ? null : el('i', { class: 'sp-ed-feito' }));
      })) : null);
    renderEditorLado();
  }

  function renderEditorLado() {
    if (!S.editor) return;
    const { r, ctx, lista, m } = editorCtx();
    const e = enq(m, ctx);
    const mudar = (fn) => { fn(e); e.auto = false; atualizarVivos(m, ctx.k); renderEditorLado(); };
    const modo = e.modo || 'preencher';
    const slider = modo === 'preencher'
      ? el('label', { class: 'sp-ed-campo' }, el('span', null, 'Aproximar', el('small', null, `${Math.round(e.zoom * 100)}%`)),
        el('input', { type: 'range', min: '1', max: '5', step: '0.01', value: String(e.zoom || 1),
          oninput: (ev) => { e.zoom = Number(ev.target.value); e.auto = false; normalizar(m, ctx.t.ratio, e); atualizarVivos(m, ctx.k); ev.target.previousElementSibling.lastChild.textContent = `${Math.round(e.zoom * 100)}%`; } }))
      : modo === 'livre'
        ? el('label', { class: 'sp-ed-campo' }, el('span', null, 'Tamanho da foto', el('small', null, `${Math.round((e.escala || 1) * 100)}%`)),
          el('input', { type: 'range', min: '0.15', max: '3', step: '0.01', value: String(e.escala || 1),
            oninput: (ev) => { e.escala = Number(ev.target.value); e.auto = false; atualizarVivos(m, ctx.k); ev.target.previousElementSibling.lastChild.textContent = `${Math.round(e.escala * 100)}%`; } }))
        : null;
    const alinhar = modo === 'livre' ? el('div', { class: 'sp-ed-campo' }, el('span', null, 'Posição'),
      el('div', { class: 'sp-ed-alinha' },
        [['Topo', { py: 'topo' }], ['Centro', { px: 0.5, py: 0.5 }], ['Base', { py: 'base' }], ['Esquerda', { px: 'esq' }], ['Direita', { px: 'dir' }]].map(([rot, v]) =>
          el('button', { type: 'button', onclick: () => mudar((x) => {
            const g = geometria(m.w, m.h, ratioNum(ctx.t.ratio), 1, x);
            const fwN = g.fw / ratioNum(ctx.t.ratio), fhN = g.fh;
            const z = ctx.f.zonas || {};
            if (v.py === 'topo') x.py = (z.topo || 0) + fhN / 2;
            else if (v.py === 'base') x.py = 1 - (z.base || 0) - fhN / 2;
            else if (v.py != null) x.py = v.py;
            if (v.px === 'esq') x.px = fwN / 2;
            else if (v.px === 'dir') x.px = 1 - fwN / 2;
            else if (v.px != null) x.px = v.px;
          }) }, rot)))) : null;
    const fundo = modo !== 'preencher' ? el('div', { class: 'sp-ed-campo' }, el('span', null, 'O resto do quadro'),
      el('div', { class: 'sp-ed-fundos' },
        FUNDOS.map(([v, rot]) => el('button', { type: 'button', 'aria-pressed': String((e.fundo || 'desfoque') === v), onclick: () => mudar((x) => { x.fundo = v; }) },
          el('i', { class: `sw sw-${v}`, style: v === 'cor' ? { background: m.cor || '#333' } : null }), rot)),
        el('label', { class: 'sp-ed-cor' }, el('input', { type: 'color', value: /^#/.test(e.fundo || '') ? e.fundo : (m.cor || '#222222'),
          oninput: (ev) => { e.fundo = ev.target.value; e.auto = false; atualizarVivos(m, ctx.k); },
          onchange: () => renderEditorLado() }), 'Outra cor'))) : null;

    trocar($('#sp-ed-lado'),
      el('div', { class: 'sp-ed-estado' + (e.auto ? ' auto' : '') }, ico(e.auto ? 'magica' : 'lapis'),
        el('span', null, e.auto ? `Automático: ${e.motivo}.` : 'Ajustado à mão nesta rede.')),
      el('div', { class: 'sp-ed-campo' }, el('span', null, 'Como a foto entra'),
        el('div', { class: 'sp-ed-modos' }, MODOS.map(([v, rot, desc]) => el('button', { type: 'button', 'aria-pressed': String(modo === v),
          onclick: () => mudar((x) => {
            if (v === 'livre' && x.modo !== 'livre') Object.assign(x, { escala: x.modo === 'encaixar' ? 1 : 0.8, px: 0.5, py: 0.5 });
            if (v === 'preencher' && x.zoom == null) Object.assign(x, { x: 0.5, y: 0.5, zoom: 1 });
            x.modo = v;
            if (v === 'preencher') normalizar(m, ctx.t.ratio, x);
          }) }, el('b', null, rot), el('small', null, desc))))),
      slider, alinhar, fundo,
      el('p', { class: 'sp-dica-p' }, modo === 'preencher' ? 'Arraste a foto para escolher a parte que aparece; a roda do mouse aproxima.'
        : modo === 'livre' ? 'Arraste a foto para onde quiser; a roda do mouse muda o tamanho.' : 'Arraste para soltar a foto da posição central.'),
      el('div', { class: 'sp-ed-ver' },
        el('label', { class: 'sp-chave' }, el('input', { type: 'checkbox', checked: S.zonas, onchange: (ev) => { S.zonas = ev.target.checked; $('#sp-zonas').checked = S.zonas; gravarLS(); renderEditor(); renderTelas(); } }), 'Zonas da interface'),
        el('label', { class: 'sp-chave' }, el('input', { type: 'checkbox', checked: S.tercos, onchange: (ev) => { S.tercos = ev.target.checked; gravarLS(); renderEditor(); } }), 'Grade dos terços')),
      el('div', { class: 'sp-ed-acoes' },
        el('button', { type: 'button', class: 'btn-secondary sp-btn-mini', onclick: () => { m.enq[ctx.k] = autoEnq(m, ctx.t.ratio, ctx.f); atualizarVivos(m, ctx.k); renderEditor(); } }, ico('magica'), 'Automático'),
        lista.length > 1 ? el('button', { type: 'button', class: 'btn-secondary sp-btn-mini', onclick: () => {
          for (const mm of lista) {
            if (mm === m) continue;
            const alvo = enq(mm, ctx);
            Object.assign(alvo, { modo: e.modo, fundo: e.fundo, zoom: e.zoom, escala: e.escala, px: e.px, py: e.py, auto: false });
            if (alvo.modo === 'preencher') normalizar(mm, ctx.t.ratio, alvo);
            atualizarVivos(mm, ctx.k);
          }
          renderEditor();
          aviso('Mesmo ajuste nas outras fotos desta rede.');
        } }, 'Usar nas outras fotos') : null,
        el('button', { type: 'button', class: 'btn-secondary sp-btn-mini', onclick: () => {
          let n = 0;
          for (const r2 of ativas()) {
            const c2 = contexto(r2);
            if (c2.k === ctx.k || !fotosDoCtx(c2).includes(m)) continue;
            const alvo = { ...e, auto: false };
            if (alvo.modo === 'preencher') normalizar(m, c2.t.ratio, alvo);
            m.enq[c2.k] = alvo;
            n++;
          }
          renderTelas();
          aviso(n ? `Ajuste copiado para ${n} rede${n > 1 ? 's' : ''}.` : 'Nenhuma outra rede usa esta foto.');
        } }, 'Copiar para as outras redes')),
      el('button', { type: 'button', class: 'btn-primary sp-btn', onclick: () => $('#sp-editor').close() }, 'Concluir'));
  }

  // ---------- composição ----------
  function renderRedes() {
    trocar($('#sp-redes'), ...S.cat.redes.map((r) => {
      const st = S.redes[r.id];
      const p = perfil(r.id);
      return el('button', { type: 'button', class: 'sp-rede', 'aria-pressed': String(st.ativa), style: { '--cor': r.cor },
        title: r.api ? (p ? `Conectado como ${p.nome || p.usuario}` : 'Sem conta conectada') : 'Modo assistido',
        onclick: () => { st.ativa = !st.ativa; S.selecaoManual = true; gravarLS(); renderRedes(); renderTelas(); } },
      el('span', { class: 'sp-rede-ic' }, marca(r.marca || r.id)),
      el('span', { class: 'sp-rede-nome' }, r.nome),
      el('i', { class: 'sp-ponto ' + (r.api ? (p ? 'on' : 'off') : 'assist') }));
    }));
  }

  function renderTiras() {
    trocar($('#sp-tiras'), ...S.midias.map((m, i) => {
      const cv = el('canvas', { width: 120, height: 120 });
      desenhar(cv.getContext('2d'), m, 120, 120, { x: 0.5, y: 0.5, zoom: 1, modo: 'preencher' });
      const mover = (d) => { const j = i + d; if (j < 0 || j >= S.midias.length) return; [S.midias[i], S.midias[j]] = [S.midias[j], S.midias[i]]; mudouMidia(); };
      const li = el('li', { class: 'sp-tira', draggable: 'true', title: `${m.nome} · ${m.w}×${m.h}` },
        cv,
        m.tipo === 'video' ? el('span', { class: 'sp-tira-dur' }, fmtDur(m.dur)) : null,
        (m.envio && m.envio.estado === 'enviando') || m.analisando ? el('span', { class: 'sp-tira-env', title: m.analisando ? 'Procurando o rosto/assunto…' : 'Enviando…' }) : null,
        el('div', { class: 'sp-tira-acoes' },
          i > 0 ? el('button', { type: 'button', 'aria-label': 'Mover para trás', onclick: () => mover(-1) }, ico('esq')) : null,
          el('button', { type: 'button', 'aria-label': 'Remover', onclick: () => { URL.revokeObjectURL(m.url); S.midias.splice(i, 1); mudouMidia(); } }, ico('fechar')),
          i < S.midias.length - 1 ? el('button', { type: 'button', 'aria-label': 'Mover para frente', onclick: () => mover(1) }, ico('dir')) : null));
      li.addEventListener('dragstart', (ev) => { ev.dataTransfer.setData('text/sp-idx', String(i)); li.classList.add('arrastando'); });
      li.addEventListener('dragend', () => li.classList.remove('arrastando'));
      li.addEventListener('dragover', (ev) => { if (ev.dataTransfer.types.includes('text/sp-idx')) { ev.preventDefault(); li.classList.add('alvo'); } });
      li.addEventListener('dragleave', () => li.classList.remove('alvo'));
      li.addEventListener('drop', (ev) => {
        ev.preventDefault();
        li.classList.remove('alvo');
        const de = Number(ev.dataTransfer.getData('text/sp-idx'));
        if (Number.isNaN(de) || de === i) return;
        const [x] = S.midias.splice(de, 1);
        S.midias.splice(i, 0, x);
        mudouMidia();
      });
      return li;
    }));
    const nv = S.midias.filter((m) => m.tipo === 'video').length;
    $('#sp-midia-info').textContent = S.midias.length
      ? `${S.midias.length - nv} foto${S.midias.length - nv === 1 ? '' : 's'} · ${nv} vídeo${nv === 1 ? '' : 's'}`
      : 'fotos e vídeos';
  }

  function mudouMidia() {
    for (const r of S.cat.redes) autoAjustar(r);
    renderTiras();
    renderMusica();
    renderTelas();
  }

  // Cor média (para "Cor da foto") enquanto a análise do Verto não chega.
  function corMedia(m) {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 8;
    const c = cv.getContext('2d');
    c.drawImage(m.fonte, 0, 0, 8, 8);
    const d = c.getImageData(0, 0, 8, 8).data;
    let r = 0, g = 0, b = 0;
    for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; }
    const n = d.length / 4;
    return '#' + [r, g, b].map((v) => Math.round((v / n) * 0.8).toString(16).padStart(2, '0')).join('');
  }

  async function analisar(m) {
    const cv = document.createElement('canvas');
    const k = Math.min(1, 640 / Math.max(m.w, m.h));
    cv.width = Math.round(m.w * k); cv.height = Math.round(m.h * k);
    cv.getContext('2d').drawImage(m.fonte, 0, 0, cv.width, cv.height);
    const blob = await new Promise((ok) => cv.toBlob(ok, 'image/jpeg', 0.85));
    const fd = new FormData();
    fd.append('imagem', blob, 'foco.jpg');
    m.analisando = true;
    try {
      const j = await api('/social/foco', { method: 'POST', body: fd });
      m.analise = { foco: j.foco, rostos: j.rostos || [] };
      if (j.cor) m.cor = j.cor;
      reautomatizar(m);
    } catch { /* sem análise: o automático usa o centro */ }
    m.analisando = false;
    renderTiras();
    if (S.midias.includes(m)) renderTelas();
  }

  async function carregar(arquivo) {
    const tipo = arquivo.type.startsWith('video/') ? 'video' : arquivo.type.startsWith('image/') ? 'imagem' : null;
    if (!tipo) throw new Error(`${arquivo.name}: formato não suportado.`);
    const url = URL.createObjectURL(arquivo);
    const m = { id: 'm' + (++seq), tipo, nome: arquivo.name, url, arquivo, enq: {}, w: 0, h: 0, dur: 0 };
    if (tipo === 'imagem') {
      const img = new Image();
      img.src = url;
      try { await img.decode(); } catch { URL.revokeObjectURL(url); throw new Error(`${arquivo.name}: o navegador não abre esse formato (HEIC? converta antes no Image Studio).`); }
      m.fonte = img; m.w = img.naturalWidth; m.h = img.naturalHeight;
    } else {
      const v = el('video', { src: url, muted: true, playsInline: true, preload: 'auto', loop: true });
      v.muted = true;
      await new Promise((ok, erro) => { v.onloadeddata = ok; v.onerror = () => erro(new Error(`${arquivo.name}: o navegador não abre esse vídeo.`)); });
      m.w = v.videoWidth; m.h = v.videoHeight; m.dur = v.duration;
      await new Promise((ok) => { v.onseeked = ok; v.currentTime = Math.min(0.5, m.dur / 3); setTimeout(ok, 1500); });
      m.fonte = v;
      enviarVideo(m);
    }
    m.cor = corMedia(m);
    return m;
  }

  async function adicionar(arquivos) {
    const primeira = S.midias.length === 0;
    const lista = [...arquivos];
    const novas = [];
    for (const a of lista) {
      if (S.midias.length >= 35) { aviso('Máximo de 35 mídias.', 'erro'); break; }
      try { const m = await carregar(a); S.midias.push(m); novas.push(m); } catch (e) { aviso(e.message, 'erro'); }
    }
    if (!novas.length) return;
    if (primeira) {
      // Primeira foto: tudo no automático, em todas as redes (a não ser que a pessoa já tenha escolhido as dela).
      for (const r of S.cat.redes) {
        const st = S.redes[r.id];
        st.fmtManual = false; st.ratioManual = false;
        if (!S.selecaoManual) st.ativa = true;
      }
      renderRedes();
    }
    mudouMidia();
    if (primeira) aviso(`Pronto: ${ativas().length} redes configuradas automaticamente. Use "Editar" em qualquer uma para ajustar só ela.`);
    novas.forEach((m) => analisar(m));
  }

  function enviarVideo(m) {
    if (m.envio) return m.envio.promessa;
    const fd = new FormData();
    fd.append('arquivo', m.arquivo, m.nome);
    m.envio = { estado: 'enviando' };
    m.envio.promessa = api('/social/midia', { method: 'POST', body: fd })
      .then((j) => { m.servidorId = j.id; m.envio.estado = 'ok'; renderTiras(); return j.id; })
      .catch((e) => { m.envio = null; renderTiras(); throw e; });
    return m.envio.promessa;
  }

  // ---------- música ----------
  async function escolherMusica(arquivo) {
    if (!arquivo) return;
    pararShow();
    const url = URL.createObjectURL(arquivo);
    const el_ = new Audio(url);
    el_.preload = 'auto';
    const dur = await new Promise((ok, erro) => {
      el_.onloadedmetadata = () => ok(el_.duration);
      el_.onerror = () => erro(new Error('O navegador não abre esse áudio.'));
    }).catch((e) => { aviso(e.message, 'erro'); return null; });
    if (!dur) { URL.revokeObjectURL(url); return; }
    if (S.show.audio) URL.revokeObjectURL(S.show.audio.url);
    S.show.audio = { arquivo, url, nome: arquivo.name, dur, el: el_, picos: null };
    S.show.inicio = 0;
    S.show.ativo = true;
    enviarAudio();
    picosAudio(arquivo).then((p) => { if (S.show.audio && S.show.audio.arquivo === arquivo) { S.show.audio.picos = p; desenharOnda(); } });
    mudouMidia();
    if (!fotos().length) aviso('Música pronta: adicione fotos para virarem vídeo.');
  }

  function enviarAudio() {
    const a = S.show.audio;
    if (!a) return Promise.reject(new Error('Sem música.'));
    if (a.envio) return a.envio;
    const fd = new FormData();
    fd.append('arquivo', a.arquivo, a.nome);
    a.envio = api('/social/audio', { method: 'POST', body: fd }).then((j) => { a.id = j.id; return j.id; })
      .catch((e) => { a.envio = null; throw e; });
    return a.envio;
  }

  async function picosAudio(arquivo) {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ac = new Ctx();
      const buf = await ac.decodeAudioData(await arquivo.arrayBuffer());
      const dados = buf.getChannelData(0);
      const n = 400, passo = Math.floor(dados.length / n);
      const picos = [];
      for (let i = 0; i < n; i++) {
        let mx = 0;
        for (let j = i * passo; j < (i + 1) * passo; j += 16) mx = Math.max(mx, Math.abs(dados[j] || 0));
        picos.push(mx);
      }
      ac.close();
      const topo = Math.max(...picos) || 1;
      return picos.map((p) => p / topo);
    } catch { return null; }
  }

  function desenharOnda() {
    const cv = $('#sp-onda');
    const a = S.show.audio;
    if (!cv || !a) return;
    const W = cv.width = cv.clientWidth * 2, H = cv.height = 112;
    const c = cv.getContext('2d');
    c.clearRect(0, 0, W, H);
    const total = duracoesShow(Math.max(1, fotos().length)).total;
    const x0 = (S.show.inicio / a.dur) * W, x1 = Math.min(W, ((S.show.inicio + total) / a.dur) * W);
    const picos = a.picos || Array.from({ length: 200 }, (_, i) => 0.35 + 0.25 * Math.sin(i / 3));
    const bw = W / picos.length;
    picos.forEach((p, i) => {
      const x = i * bw, alt = Math.max(3, p * (H - 16));
      c.fillStyle = x >= x0 && x <= x1 ? '#f472b6' : 'rgba(255,255,255,.22)';
      c.fillRect(x, (H - alt) / 2, Math.max(1, bw - 1.5), alt);
    });
    c.strokeStyle = '#f9a8d4'; c.lineWidth = 3;
    c.strokeRect(x0 + 1.5, 1.5, Math.max(4, x1 - x0 - 3), H - 3);
    if (S.tocando) {
      const t = a.el.currentTime;
      const xp = (t / a.dur) * W;
      c.fillStyle = '#fff'; c.fillRect(xp - 1, 0, 2, H);
    }
  }

  function renderMusica() {
    const caixa = $('#sp-musica');
    const a = S.show.audio;
    const n = fotos().length;
    $('#sp-musica-info').textContent = a ? (S.show.ativo ? `vídeo de ${fmtSeg(duracoesShow(Math.max(1, n)).total)}` : 'desligada') : 'fotos viram vídeo';
    if (!a) {
      trocar(caixa, el('label', { class: 'sp-drop sp-drop-musica' },
        el('input', { type: 'file', accept: 'audio/*,.mp3,.m4a,.aac,.wav,.ogg,.opus,.flac', onchange: (ev) => { escolherMusica(ev.target.files[0]); ev.target.value = ''; } }),
        ico('musica'), el('span', null, el('b', null, 'Adicionar música'), ' e as fotos viram vídeo')));
      return;
    }
    const { d, total } = duracoesShow(Math.max(1, n));
    const onda = el('canvas', { id: 'sp-onda', class: 'sp-onda', 'aria-label': 'Trecho da música: arraste para escolher onde começa' });
    let arrasto = null;
    const posicionar = (ev) => {
      const r = onda.getBoundingClientRect();
      const t = ((ev.clientX - r.left) / r.width) * a.dur - (arrasto ? arrasto.off : total / 2);
      S.show.inicio = limitar(t, 0, Math.max(0, a.dur - total));
      desenharOnda();
      $('#sp-mus-ini').textContent = `começa em ${fmtDur(S.show.inicio)}`;
    };
    onda.addEventListener('pointerdown', (ev) => {
      const r = onda.getBoundingClientRect();
      const t = ((ev.clientX - r.left) / r.width) * a.dur;
      arrasto = { off: t >= S.show.inicio && t <= S.show.inicio + total ? t - S.show.inicio : total / 2 };
      onda.setPointerCapture(ev.pointerId);
      posicionar(ev);
    });
    onda.addEventListener('pointermove', (ev) => { if (arrasto) posicionar(ev); });
    onda.addEventListener('pointerup', () => { arrasto = null; if (S.tocando) tocarShow(); });
    const op = (rot, ctl) => el('label', { class: 'sp-mus-op' }, el('span', null, rot), ctl);
    const atualizar = () => { gravarLS(); for (const r of S.cat.redes) autoAjustar(r); renderMusica(); renderTelas(); };
    trocar(caixa,
      el('div', { class: 'sp-mus-cab' },
        el('button', { type: 'button', class: 'sp-mus-play', 'aria-label': S.tocando ? 'Parar' : 'Ouvir com as fotos', onclick: alternarShow }, ico(S.tocando ? 'pausa' : 'play', '', !S.tocando)),
        el('div', { class: 'sp-mus-nome' }, el('b', null, a.nome), el('small', null, `${fmtDur(a.dur)} · `, el('span', { id: 'sp-mus-ini' }, `começa em ${fmtDur(S.show.inicio)}`))),
        el('button', { type: 'button', class: 'sp-mus-tirar', 'aria-label': 'Tirar a música', onclick: () => { pararShow(); URL.revokeObjectURL(a.url); S.show.audio = null; S.show.ativo = false; mudouMidia(); } }, ico('fechar'))),
      onda,
      el('label', { class: 'sp-chave' }, el('input', { type: 'checkbox', checked: S.show.ativo, onchange: (ev) => { S.show.ativo = ev.target.checked; pararShow(); mudouMidia(); } }),
        'Fotos viram vídeo com esta música'),
      S.show.ativo ? el('div', { class: 'sp-mus-ops' },
        op(`Cada foto: ${fmtSeg(d)}`, el('input', { type: 'range', min: '1', max: '10', step: '0.5', value: String(S.show.durFoto),
          oninput: (ev) => { S.show.durFoto = Number(ev.target.value); ev.target.previousElementSibling.textContent = `Cada foto: ${fmtSeg(duracoesShow(Math.max(1, n)).d)}`; desenharOnda(); },
          onchange: atualizar })),
        op('Transição', el('select', { onchange: (ev) => { S.show.transicao = ev.target.value; atualizar(); } },
          [['esmaecer', 'Esmaecer'], ['dissolver', 'Dissolver'], ['deslizar', 'Deslizar'], ['zoom', 'Zoom'], ['corte', 'Corte seco']].map(([v, t]) =>
            el('option', { value: v, selected: S.show.transicao === v }, t)))),
        op(`Volume: ${Math.round(S.show.volume * 100)}%`, el('input', { type: 'range', min: '0', max: '1.5', step: '0.05', value: String(S.show.volume),
          oninput: (ev) => { S.show.volume = Number(ev.target.value); ev.target.previousElementSibling.textContent = `Volume: ${Math.round(S.show.volume * 100)}%`; a.el.volume = Math.min(1, S.show.volume); },
          onchange: () => gravarLS() })),
        el('label', { class: 'sp-chave' }, el('input', { type: 'checkbox', checked: S.show.movimento, onchange: (ev) => { S.show.movimento = ev.target.checked; gravarLS(); } }), 'Movimento suave (zoom lento)'),
        el('label', { class: 'sp-chave' }, el('input', { type: 'checkbox', checked: S.show.fade, onchange: (ev) => { S.show.fade = ev.target.checked; gravarLS(); } }), 'Música entra e sai suave'),
        el('p', { class: 'sp-dica-p' }, n ? `${n} foto${n > 1 ? 's' : ''} → vídeo de ${fmtSeg(total)}. Redes que não aceitam vídeo (Bluesky, Pinterest) recebem as fotos.` : 'Adicione fotos para montar o vídeo.'),
      ) : null);
    requestAnimationFrame(desenharOnda);
  }

  function alternarShow() { if (S.tocando) pararShow(); else tocarShow(); }

  function tocarShow() {
    const a = S.show.audio;
    if (!a || !fotos().length) { aviso('Adicione fotos e uma música.'); return; }
    if (!S.show.ativo) { S.show.ativo = true; mudouMidia(); }
    const { d, t, total } = duracoesShow(fotos().length);
    a.el.currentTime = S.show.inicio;
    a.el.volume = Math.min(1, S.show.volume);
    a.el.play().catch(() => {});
    const eraTocando = S.tocando;
    S.tocando = true;
    S.slide = 0;
    if (!eraTocando) { renderMusica(); renderTelas(); } else atualizarShows();
    cancelAnimationFrame(tocarShow.raf);
    const laco = () => {
      const tt = a.el.currentTime - S.show.inicio;
      if (tt >= total || a.el.paused) { pararShow(); return; }
      const i = Math.min(fotos().length - 1, Math.floor(tt / Math.max(0.5, d - t)));
      if (i !== S.slide) { S.slide = i; atualizarShows(); }
      desenharOnda();
      tocarShow.raf = requestAnimationFrame(laco);
    };
    tocarShow.raf = requestAnimationFrame(laco);
  }

  function pararShow() {
    cancelAnimationFrame(tocarShow.raf);
    if (S.show.audio) S.show.audio.el.pause();
    if (!S.tocando) return;
    S.tocando = false;
    S.slide = 0;
    renderMusica();
    renderTelas();
  }

  // ---------- arquivos finais ----------
  async function imagemFinal(m, ctx) {
    const cv = document.createElement('canvas');
    cv.width = ctx.t.w; cv.height = ctx.t.h;
    desenhar(cv.getContext('2d'), m, ctx.t.w, ctx.t.h, enq(m, ctx));
    return new Promise((ok) => cv.toBlob(ok, 'image/jpeg', 0.92));
  }

  const enqVideo = (m, ctx) => ({ ...enq(m, ctx), cor: m.cor });

  async function videoFinal(m, ctx) {
    const id = m.servidorId || await enviarVideo(m);
    const r = await fetch('/social/render-video', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ midia_id: id, w: ctx.t.w, h: ctx.t.h, enquadre: enqVideo(m, ctx), max_s: (ctx.f.video || {}).max_s || null }) });
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || 'Falha ao gerar o vídeo.'); }
    return r.blob();
  }

  async function showFinal(ctx) {
    const audioId = S.show.audio.id || await enviarAudio();
    const fd = new FormData();
    let i = 0;
    for (const m of fotos()) fd.append(`f${i++}`, await imagemFinal(m, ctx), 'foto.jpg');
    fd.append('dados', JSON.stringify({ w: ctx.t.w, h: ctx.t.h, audio_id: audioId, opcoes: { ...opcoesShow(), max_s: (ctx.f.video || {}).max_s || null } }));
    const r = await fetch('/social/render-slideshow', { method: 'POST', body: fd });
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || 'Falha ao gerar o vídeo com música.'); }
    return r.blob();
  }

  const nomeArq = (ctx, i, ext) => `${ctx.r.id}-${ctx.f.id}-${ctx.t.ratio.replace(':', 'x')}-${ctx.t.w}x${ctx.t.h}${i != null ? '-' + (i + 1) : ''}.${ext}`;

  async function arquivosDe(r) {
    const ctx = contexto(r);
    const out = [];
    for (const [i, m] of ctx.midias.entries()) {
      const multi = ctx.midias.length > 1 ? i : null;
      if (m.tipo === 'imagem') out.push({ nome: nomeArq(ctx, multi, 'jpg'), blob: await imagemFinal(m, ctx) });
      else if (m.tipo === 'slideshow') out.push({ nome: nomeArq(ctx, null, 'mp4'), blob: await showFinal(ctx) });
      else out.push({ nome: nomeArq(ctx, multi, 'mp4'), blob: await videoFinal(m, ctx) });
    }
    return out;
  }

  function baixarBlob(blob, nome) {
    const a = el('a', { href: URL.createObjectURL(blob), download: nome });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }

  function metaTags() {
    const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    const tit = S.titulo || (S.texto.split('\n')[0] || '');
    const desc = S.texto.slice(0, 200);
    return [
      `<meta property="og:type" content="website">`,
      `<meta property="og:title" content="${esc(tit)}">`,
      `<meta property="og:description" content="${esc(desc)}">`,
      S.link ? `<meta property="og:url" content="${esc(S.link)}">` : null,
      `<meta property="og:image" content="https://SEU-SITE/og-1200x630.jpg">`,
      `<meta property="og:image:width" content="1200">`,
      `<meta property="og:image:height" content="630">`,
      S.alt ? `<meta property="og:image:alt" content="${esc(S.alt)}">` : null,
      `<meta name="twitter:card" content="summary_large_image">`,
    ].filter(Boolean).join('\n');
  }

  async function baixarTudo() {
    const lista = ativas();
    if (!lista.length) { aviso('Ligue pelo menos uma rede.', 'erro'); return; }
    if (typeof JSZip === 'undefined') { aviso('Sem internet para carregar o compactador (JSZip).', 'erro'); return; }
    const btn = $('#sp-baixar');
    btn.disabled = true;
    try {
      const zip = new JSZip();
      const textos = [];
      for (const r of lista) {
        btn.textContent = `Gerando ${r.nome}…`;
        const ctx = contexto(r);
        for (const a of await arquivosDe(r)) zip.file(`${r.id}/${a.nome}`, a.blob);
        if (!ctx.f.sem_texto) textos.push(`### ${r.nome} · ${ctx.f.nome} ${ctx.t.ratio}\n${S.titulo && r.texto.titulo ? 'Título: ' + S.titulo + '\n' : ''}${ctx.texto}\n`);
        if (r.id === 'link') zip.file('link/meta-tags.html', metaTags() + '\n');
      }
      zip.file('textos.txt', textos.join('\n'));
      baixarBlob(await zip.generateAsync({ type: 'blob' }), 'social-preview.zip');
    } catch (e) {
      aviso(e.message, 'erro');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Baixar arquivos';
    }
  }

  // ---------- publicar ----------
  const ABRIR = {
    instagram: 'https://www.instagram.com/', facebook: 'https://www.facebook.com/', threads: 'https://www.threads.com/',
    x: 'https://x.com/compose/post', linkedin: 'https://www.linkedin.com/feed/', bluesky: 'https://bsky.app/',
    mastodon: 'https://mastodon.social/', telegram: 'https://web.telegram.org/', discord: 'https://discord.com/app',
    pinterest: 'https://www.pinterest.com/pin-creation-tool/', youtube: 'https://studio.youtube.com/',
  };

  function atualizarResumo() {
    const lista = ativas();
    let erros = 0, diretas = 0, assist = 0;
    for (const r of lista) {
      const f = formatoDe(r);
      if (avisos(r, f).some((a) => a.nivel === 'erro')) erros++;
      else if (r.api && perfil(r.id)) diretas++;
      else assist++;
    }
    const partes = [];
    if (diretas) partes.push(`${diretas} direto`);
    if (assist) partes.push(`${assist} assistido`);
    if (erros) partes.push(`${erros} com erro`);
    $('#sp-resumo').textContent = lista.length ? `${lista.length} rede${lista.length > 1 ? 's' : ''} · ${partes.join(' · ')}` : 'Escolha as redes';
    $('#sp-publicar').disabled = !lista.length;
  }

  const descMidias = (ctx) => (ctx.midias[0] && ctx.midias[0].tipo === 'slideshow'
    ? `vídeo com música (${fotos().length} fotos)`
    : ctx.midias.length ? ctx.midias.length + (ctx.midias.length > 1 ? ' mídias' : ' mídia') : 'só texto');

  function abrirPublicar() {
    pararShow();
    const itens = ativas().map((r) => {
      const ctx = contexto(r);
      const erros = avisos(r, ctx.f).filter((a) => a.nivel === 'erro');
      return { r, ctx, erros, direto: r.api && !!perfil(r.id), marcado: !erros.length };
    });
    const corpo = $('#sp-pub');
    const diretos = itens.filter((i) => i.direto && !i.erros.length);
    const linha = (it) => {
      const { r, ctx } = it;
      const sub = `${ctx.f.nome} · ${ctx.t.ratio} · ${descMidias(ctx)}`;
      const li = el('li', { class: 'sp-pub-item', dataset: { chave: `${r.id}:${ctx.f.id}` }, style: { '--cor': r.cor } },
        el('span', { class: 'sp-tela-marca' }, marca(r.marca || r.id)),
        el('div', { class: 'sp-pub-info' }, el('b', null, r.nome), el('small', null, sub),
          el('div', { class: 'sp-pub-msg' }, it.erros.length ? it.erros[0].msg : it.direto ? `Publica em @${perfil(r.id).usuario || perfil(r.id).nome}` : r.assistido || 'Sem conta conectada: baixe o arquivo, copie o texto e poste pelo site.')),
        el('div', { class: 'sp-pub-lado' }));
      const lado = li.querySelector('.sp-pub-lado');
      if (it.erros.length) lado.append(el('span', { class: 'sp-estado erro' }, 'Corrija antes'));
      else if (it.direto) {
        const cb = el('input', { type: 'checkbox', 'aria-label': `Publicar no ${r.nome}` });
        cb.checked = true;
        cb.addEventListener('change', () => { it.marcado = cb.checked; atualizarBotao(); });
        lado.append(el('label', { class: 'sp-chave' }, cb, 'Publicar'));
      } else {
        trocar(lado,
          el('button', { type: 'button', class: 'btn-secondary sp-btn-mini', onclick: async (ev) => {
            const b = ev.currentTarget; b.disabled = true; b.textContent = 'Gerando…';
            try {
              const arqs = await arquivosDe(r);
              if (r.id === 'link') arqs.push({ nome: 'meta-tags.html', blob: new Blob([metaTags()], { type: 'text/html' }) });
              if (arqs.length === 1) baixarBlob(arqs[0].blob, arqs[0].nome);
              else if (arqs.length) { const z = new JSZip(); arqs.forEach((a) => z.file(a.nome, a.blob)); baixarBlob(await z.generateAsync({ type: 'blob' }), `${r.id}.zip`); }
            } catch (e) { aviso(e.message, 'erro'); }
            b.disabled = false; b.textContent = 'Baixar';
          } }, 'Baixar'),
          r.id === 'link'
            ? el('button', { type: 'button', class: 'btn-secondary sp-btn-mini', onclick: () => copiar(metaTags(), 'Meta tags copiadas.') }, 'Copiar meta tags')
            : (ctx.f.sem_texto ? null : el('button', { type: 'button', class: 'btn-secondary sp-btn-mini', onclick: () => copiar(ctx.texto, 'Texto copiado.') }, 'Copiar texto')),
          (r.abrir || ABRIR[r.id]) ? el('a', { class: 'btn-secondary sp-btn-mini', href: r.abrir || ABRIR[r.id], target: '_blank', rel: 'noopener' }, 'Abrir') : null);
      }
      return li;
    };
    const btn = el('button', { type: 'button', class: 'btn-primary sp-btn', id: 'sp-pub-ir' });
    function atualizarBotao() {
      const n = diretos.filter((i) => i.marcado).length;
      btn.textContent = n ? `Publicar agora em ${n} rede${n > 1 ? 's' : ''}` : 'Nada para publicar direto';
      btn.disabled = !n;
    }
    atualizarBotao();
    btn.addEventListener('click', () => publicar(diretos.filter((i) => i.marcado), btn));
    const diretosLista = itens.filter((i) => i.direto || i.erros.length);
    const assistLista = itens.filter((i) => !i.direto && !i.erros.length);
    trocar(corpo,
      diretosLista.length ? el('h3', null, 'Publicação direta') : null,
      diretosLista.length ? el('ul', { class: 'sp-pub-lista' }, diretosLista.map(linha)) : null,
      assistLista.length ? el('h3', null, 'Modo assistido') : null,
      assistLista.length ? el('p', { class: 'sp-dica-p' }, 'Sem API aberta (ou sem conta conectada): o Verto gera o arquivo no formato certo e copia o texto; você só cola e posta.') : null,
      assistLista.length ? el('ul', { class: 'sp-pub-lista' }, assistLista.map(linha)) : null,
      el('div', { class: 'sp-pub-pe' }, el('button', { type: 'button', class: 'sp-linkbtn', onclick: () => { $('#sp-dlg-publicar').close(); abrirContas(); } }, 'Conectar mais contas'), btn));
    $('#sp-dlg-publicar').showModal();
  }

  function copiar(texto, msg) {
    navigator.clipboard.writeText(texto).then(() => aviso(msg), () => aviso('Não deu para copiar.', 'erro'));
  }

  function marcarItem(chave, estado, msg, url) {
    const li = document.querySelector(`.sp-pub-item[data-chave="${chave}"]`);
    if (!li) return;
    li.querySelector('.sp-pub-msg').textContent = msg;
    const rotulo = { fila: 'Na fila', preparando: 'Preparando', enviando: 'Enviando', publicado: 'Publicado', erro: 'Erro' }[estado] || estado;
    trocar(li.querySelector('.sp-pub-lado'), el('span', { class: `sp-estado ${estado}` }, rotulo),
      url ? el('a', { class: 'btn-secondary sp-btn-mini', href: url, target: '_blank', rel: 'noopener' }, 'Abrir post') : null);
  }

  async function publicar(itens, btn) {
    btn.disabled = true;
    btn.textContent = 'Preparando…';
    try {
      const fd = new FormData();
      const feitos = new Map();
      const imagem = async (m, ctx) => {
        const chave = `${m.id}|${ctx.t.w}x${ctx.t.h}|${JSON.stringify(enq(m, ctx))}`;
        if (!feitos.has(chave)) {
          const nome = 'f' + feitos.size;
          fd.append(nome, await imagemFinal(m, ctx), nome + '.jpg');
          feitos.set(chave, nome);
        }
        return feitos.get(chave);
      };
      const plano = { itens: [] };
      for (const { r, ctx } of itens) {
        marcarItem(`${r.id}:${ctx.f.id}`, 'preparando', 'Gerando os arquivos no formato certo…');
        const midias = [];
        for (const m of ctx.midias) {
          if (m.tipo === 'imagem') midias.push({ tipo: 'imagem', arquivo: await imagem(m, ctx) });
          else if (m.tipo === 'slideshow') {
            const keys = [];
            for (const foto of fotos()) keys.push(await imagem(foto, ctx));
            midias.push({ tipo: 'slideshow', fotos: keys, audio_id: S.show.audio.id || await enviarAudio(), opcoes: opcoesShow() });
          } else {
            const id = m.servidorId || await enviarVideo(m);
            midias.push({ tipo: 'video', midia_id: id, enquadre: enqVideo(m, ctx) });
          }
        }
        plano.itens.push({ rede: r.id, formato: ctx.f.id, ratio: ctx.t.ratio, texto: ctx.texto, titulo: S.titulo,
          link: S.link, alt: S.alt, opcoes: {}, midias });
      }
      fd.append('plano', JSON.stringify(plano));
      btn.textContent = 'Publicando…';
      const { job } = await api('/social/publicar', { method: 'POST', body: fd });
      let fim = false;
      while (!fim) {
        await new Promise((ok) => setTimeout(ok, 1500));
        const j = (await api(`/social/publicar/${job}`)).job;
        for (const it of j.itens) marcarItem(it.chave, it.estado, it.msg, it.url);
        fim = j.fim;
      }
      const j = (await api(`/social/publicar/${job}`)).job;
      const ok = j.itens.filter((i) => i.estado === 'publicado').length;
      btn.textContent = ok === j.itens.length ? 'Tudo publicado' : `${ok} de ${j.itens.length} publicados`;
      aviso(ok === j.itens.length ? 'Publicado em todas as redes.' : 'Algumas redes deram erro: veja a mensagem de cada uma.', ok === j.itens.length ? '' : 'erro');
    } catch (e) {
      aviso(e.message, 'erro');
      btn.disabled = false;
      btn.textContent = 'Tentar de novo';
    }
  }

  // ---------- contas ----------
  let contaAberta = null;

  async function recarregarContas() {
    const j = await api('/social/contas');
    S.contas = j.contas || {};
    S.config = j.config || {};
  }

  function abrirContas(rid) {
    const apis = S.cat.redes.filter((r) => r.api);
    contaAberta = rid || contaAberta || (apis.find((r) => !perfil(r.id)) || apis[0]).id;
    renderContas();
    if (!$('#sp-contas').open) $('#sp-contas').showModal();
  }

  function renderContas() {
    const apis = S.cat.redes.filter((r) => r.api);
    trocar($('#sp-contas-lista'), ...apis.map((r) => {
      const p = perfil(r.id);
      const c = conta(r.id);
      return el('button', { type: 'button', class: 'sp-conta-bt', 'aria-current': String(r.id === contaAberta), style: { '--cor': r.cor },
        onclick: () => { contaAberta = r.id; renderContas(); } },
      el('span', { class: 'sp-tela-marca' }, marca(r.marca || r.id)),
      el('span', { class: 'sp-conta-bt-txt' }, el('b', null, r.nome), el('small', null, p ? `@${p.usuario || p.nome}` : c && c.erro ? 'com erro' : 'conectar')),
      el('i', { class: 'sp-ponto ' + (p ? (c.erro ? 'erro' : 'on') : 'off') }));
    }));
    trocar($('#sp-contas-form'), formConta(rede(contaAberta)));
    const h = S.config.hospedagem || 'auto';
    const op = (v, tit, desc) => el('label', { class: 'sp-radio' },
      el('input', { type: 'radio', name: 'sp-hosp', value: v, checked: h === v, onchange: async () => {
        try { S.config = (await api('/social/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hospedagem: v }) })).config; aviso('Salvo.'); } catch (e) { aviso(e.message, 'erro'); }
      } }), el('span', null, el('b', null, tit), el('small', null, desc)));
    trocar($('#sp-hosp'),
      el('h3', null, 'Hospedagem temporária (Instagram e Threads)'),
      el('p', { class: 'sp-dica-p' }, 'Essas duas APIs não recebem o arquivo: buscam a mídia por um endereço público. O Verto só expõe o arquivo do post, durante a publicação.'),
      el('div', { class: 'sp-radios' },
        op('auto', 'Automático', 'Túnel; se não abrir, Litterbox.'),
        op('tunel', 'Túnel da Cloudflare', 'Servidor só com os arquivos do post, fechado no fim. Baixa o cloudflared na 1ª vez.'),
        op('litterbox', 'Litterbox', 'Envia para litterbox.catbox.moe, que apaga em 1 hora.')));
  }

  function formConta(r) {
    const c = conta(r.id);
    const p = perfil(r.id);
    const campos = {};
    const form = el('form', { class: 'sp-form', onsubmit: async (ev) => {
      ev.preventDefault();
      const dados = {};
      for (const [k, inp] of Object.entries(campos)) dados[k] = inp.type === 'checkbox' ? inp.checked : inp.value;
      const b = form.querySelector('[type=submit]');
      b.disabled = true; b.textContent = 'Testando…';
      try {
        const j = await api(`/social/contas/${r.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ campos: dados }) });
        await recarregarContas();
        if (j.precisa_oauth) aviso('Salvo. Agora clique em "Entrar com Google".');
        else aviso(`${r.nome} conectado.`);
        renderContas(); renderRedes(); renderTelas();
      } catch (e) {
        aviso(e.message, 'erro');
        b.disabled = false; b.textContent = 'Salvar e testar';
      }
    } });
    const cab = el('div', { class: 'sp-form-cab', style: { '--cor': r.cor } },
      el('span', { class: 'sp-tela-marca grande' }, marca(r.marca || r.id)),
      el('div', null, el('h3', null, r.nome),
        p ? el('div', { class: 'sp-conectado' }, avatar(p), el('span', null, 'Conectado como ', el('b', null, p.nome || p.usuario), p.url ? [' · ', el('a', { href: p.url, target: '_blank', rel: 'noopener' }, 'ver perfil')] : null))
          : el('div', { class: 'sp-dica-p' }, 'Ainda não conectado.')));
    form.append(cab);
    if (c && c.erro) form.append(el('div', { class: 'sp-erro-caixa' }, c.erro));
    form.append(el('ol', { class: 'sp-passos' }, r.conta.passos.map((t) => el('li', null, t))));
    if (r.conta.link) form.append(el('a', { class: 'sp-linkbtn', href: r.conta.link, target: '_blank', rel: 'noopener' }, `Abrir ${new URL(r.conta.link).hostname.replace(/^www\./, '')} ↗`));
    if (r.conta.aviso) form.append(el('p', { class: 'sp-dica-p destaque' }, r.conta.aviso));
    const grupo = el('div', { class: 'sp-campos' });
    for (const cp of r.conta.campos) {
      const salvo = c && c.campos ? c.campos[cp.id] : null;
      let inp;
      if (cp.tipo === 'checkbox') {
        inp = el('input', { type: 'checkbox' });
        inp.checked = !!salvo;
        grupo.append(el('label', { class: 'sp-chave' }, inp, cp.rotulo));
      } else {
        inp = el('input', { type: cp.tipo === 'password' ? 'password' : cp.tipo === 'url' ? 'url' : 'text', autocomplete: 'off', spellcheck: 'false',
          placeholder: cp.tipo === 'password' && salvo ? '•••••• salvo (deixe vazio para manter)' : (cp.dica || '') });
        if (cp.tipo !== 'password' && typeof salvo === 'string') inp.value = salvo;
        grupo.append(el('label', { class: 'sp-campo' }, el('span', null, cp.rotulo, cp.opcional ? el('small', null, ' opcional') : null), inp,
          cp.dica && cp.tipo !== 'password' ? null : cp.dica ? el('small', null, cp.dica) : null));
      }
      campos[cp.id] = inp;
    }
    const extra = p && p.extra;
    if (extra && extra.paginas && extra.paginas.length > 1 && campos.pagina_id) grupo.append(seletor('Página', extra.paginas, campos.pagina_id));
    if (extra && extra.pastas && campos.pasta) grupo.append(seletor('Pasta', extra.pastas, campos.pasta));
    form.append(grupo);
    const acoes = el('div', { class: 'sp-form-acoes' }, el('button', { type: 'submit', class: 'btn-primary sp-btn' }, 'Salvar e testar'));
    if (r.oauth && c) {
      acoes.append(el('button', { type: 'button', class: 'btn-secondary sp-btn', onclick: () => entrarOauth(r) }, c.oauth_pronto ? 'Entrar de novo com Google' : 'Entrar com Google'));
    }
    if (c) {
      if (p) acoes.append(el('button', { type: 'button', class: 'btn-secondary sp-btn', onclick: async (ev) => {
        const b = ev.currentTarget; b.disabled = true;
        try { await api(`/social/contas/${r.id}/testar`, { method: 'POST' }); aviso('Conexão ok.'); } catch (e) { aviso(e.message, 'erro'); }
        await recarregarContas(); renderContas(); renderRedes(); renderTelas();
      } }, 'Testar de novo'));
      acoes.append(el('button', { type: 'button', class: 'sp-linkbtn perigo', onclick: async () => {
        if (!confirm(`Desconectar ${r.nome} e apagar as credenciais salvas?`)) return;
        await api(`/social/contas/${r.id}`, { method: 'DELETE' });
        await recarregarContas(); renderContas(); renderRedes(); renderTelas();
      } }, 'Desconectar'));
    }
    form.append(acoes);
    return form;
  }

  function seletor(rotulo, itens, inp) {
    const sel = el('select', { onchange: () => { inp.value = sel.value; } },
      el('option', { value: '' }, '(padrão: a primeira)'), itens.map((i) => el('option', { value: i.id }, i.nome)));
    sel.value = inp.value || '';
    return el('label', { class: 'sp-campo' }, el('span', null, rotulo), sel);
  }

  function entrarOauth(r) {
    const w = window.open(`/social/oauth/${r.id}/iniciar`, 'sp-oauth', 'width=520,height=680');
    if (!w) { aviso('O navegador bloqueou a janela de login.', 'erro'); return; }
    const ouvir = async (ev) => {
      if (!ev.data || ev.data.socialOauth !== r.id) return;
      window.removeEventListener('message', ouvir);
      await recarregarContas();
      renderContas(); renderRedes(); renderTelas();
      aviso(ev.data.ok ? `${r.nome} conectado.` : 'Login não concluído.', ev.data.ok ? '' : 'erro');
    };
    window.addEventListener('message', ouvir);
  }

  // ---------- início ----------
  async function iniciar() {
    let cat;
    try {
      [cat] = await Promise.all([api('/social/catalogo'), recarregarContas()]);
    } catch (e) {
      trocar($('#sp-telas'), el('div', { class: 'sp-nada' }, `Não deu para falar com o Verto: ${e.message}`));
      return;
    }
    S.cat = cat;
    for (const r of cat.redes) S.porId[r.id] = r;
    const salvo = lerLS();
    S.selecaoManual = !!salvo.selecaoManual;
    for (const r of cat.redes) {
      const sv = (salvo.redes || {})[r.id] || {};
      S.redes[r.id] = {
        ativa: S.selecaoManual && sv.ativa != null ? sv.ativa : true,
        formato: r.formatos[0].id, fmtManual: false, ratio: null, ratioManual: false,
        textoProprio: !!sv.textoProprio, texto: sv.texto ?? null,
      };
      autoAjustar(r);
    }
    Object.assign(S.show, salvo.show || {});
    S.texto = salvo.texto || '';
    S.link = salvo.link || '';
    S.titulo = salvo.titulo || '';
    S.alt = salvo.alt || '';
    S.zonas = salvo.zonas !== false;
    S.tercos = !!salvo.tercos;
    $('#sp-texto').value = S.texto;
    $('#sp-link').value = S.link;
    $('#sp-titulo').value = S.titulo;
    $('#sp-alt').value = S.alt;
    $('#sp-zonas').checked = S.zonas;

    $('#sp-texto').addEventListener('input', (e) => { S.texto = e.target.value; atualizarInfoTexto(); textoMudou(); });
    $('#sp-link').addEventListener('input', (e) => { S.link = e.target.value.trim(); textoMudou(); });
    $('#sp-titulo').addEventListener('input', (e) => { S.titulo = e.target.value; textoMudou(); });
    $('#sp-alt').addEventListener('input', (e) => { S.alt = e.target.value; gravarLS(); });
    $('#sp-zonas').addEventListener('change', (e) => { S.zonas = e.target.checked; gravarLS(); renderTelas(); });
    $('#sp-arquivos').addEventListener('change', (e) => { adicionar(e.target.files); e.target.value = ''; });
    const drop = $('#sp-drop');
    ['dragenter', 'dragover'].forEach((t) => drop.addEventListener(t, (e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); drop.classList.add('sobre'); } }));
    ['dragleave', 'drop'].forEach((t) => drop.addEventListener(t, () => drop.classList.remove('sobre')));
    drop.addEventListener('drop', (e) => {
      if (!e.dataTransfer.files.length) return;
      e.preventDefault();
      const arqs = [...e.dataTransfer.files];
      const audio = arqs.find((a) => a.type.startsWith('audio/'));
      if (audio) escolherMusica(audio);
      adicionar(arqs.filter((a) => !a.type.startsWith('audio/')));
    });
    document.addEventListener('paste', (e) => {
      if (e.target.closest && e.target.closest('input, textarea')) return;
      const arqs = [...(e.clipboardData || {}).files || []];
      if (arqs.length) adicionar(arqs);
    });
    $('#sp-abrir-contas').addEventListener('click', () => abrirContas());
    $('#sp-baixar').addEventListener('click', baixarTudo);
    $('#sp-publicar').addEventListener('click', abrirPublicar);
    document.querySelectorAll('dialog [data-fechar]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));
    document.querySelectorAll('dialog').forEach((d) => d.addEventListener('click', (e) => { if (e.target === d) d.close(); }));
    $('#sp-editor').addEventListener('close', () => { S.editor = null; renderTelas(); });
    document.addEventListener('visibilitychange', () => { if (document.hidden) pararShow(); });

    atualizarInfoTexto();
    renderRedes();
    renderTiras();
    renderMusica();
    renderTelas();
  }

  function atualizarInfoTexto() {
    const n = Array.from(S.texto).length;
    $('#sp-texto-info').textContent = n ? `${n} caracteres · ${hashtags(S.texto)} hashtags` : '';
  }

  window.SocialPreview = { estado: S, recorte, geometria, autoEnq, duracoesShow };
  iniciar();
})();
