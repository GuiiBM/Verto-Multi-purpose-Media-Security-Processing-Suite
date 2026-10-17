/* Áudio Studio · editor (linha do tempo, reprodução, sugestões, texto, efeitos, exportar, fila).
 *
 * A lista de edição (S.proj.pistas -> clipes) é a fonte da verdade. Toda edição:
 * muda S.proj, empilha no histórico (desfazer), redesenha e salva sozinha.
 * O áudio nunca é decodificado inteiro: a onda vem dos picos (250 por segundo,
 * gerados no servidor) e o som vem de "janelas" de 20 s do arquivo original,
 * decodificadas pelo navegador só quando vão tocar.
 */
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const uid = () => Math.random().toString(16).slice(2, 12).padEnd(10, '0');
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lin = (db) => Math.pow(10, db / 20);
  const API = '/audiostudio';

  function fmt(t, ms = true) {
    t = Math.max(0, t || 0);
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    const ss = ms ? s.toFixed(3).padStart(6, '0') : String(Math.floor(s)).padStart(2, '0');
    return (h ? `${h}:${String(m).padStart(2, '0')}` : String(m).padStart(2, '0')) + ':' + ss;
  }
  function fmtCurto(t) { t = Math.max(0, t || 0); const m = Math.floor(t / 60), s = Math.floor(t % 60); return `${m}:${String(s).padStart(2, '0')}`; }
  function fmtEta(s) { if (s == null) return ''; s = Math.round(s); if (s < 60) return `~${s} s`; if (s < 3600) return `~${Math.round(s / 60)} min`; return `~${(s / 3600).toFixed(1)} h`; }

  let toastT;
  function toast(msg, erro = false) {
    const t = $('#toast'); t.textContent = msg; t.classList.toggle('erro', erro); t.classList.add('on');
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('on'), erro ? 6500 : 3200);
  }
  async function api(url, opts = {}) {
    const r = await fetch(url, opts);
    let d;
    try { d = await r.json(); } catch { d = { success: false, error: `Erro ${r.status}` }; }
    if (!d.success) { const e = new Error(d.error || 'Falhou.'); e.conflito = d.conflito; e.status = r.status; throw e; }
    return d;
  }
  const json = (url, corpo, metodo = 'POST') => api(url, { method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo || {}) });

  // ======================================================================
  // Estado
  // ======================================================================
  const REGUA = 34, ALT = 96, ZONA_NOVA = 34, MICRO = 0.005;
  const COR_TIPO = { voz: '#fbbf24', musica: '#60a5fa', efeito: '#c084fc' };
  const COR_CAT = { silencio: '#94a3b8', cabeca: '#64748b', vicio: '#fb923c', muleta: '#fde047', gaguejo: '#f472b6', repeticao: '#c084fc',
    respiracao: '#38bdf8', estouro: '#f87171', volume: '#a3e635', trecho: '#4ade80' };
  const S = {
    proj: null, catalogo: null, picos: {}, sug: { fontes: {} }, transcr: {}, tarefas: [],
    zoom: 60, scroll: 0, agulha: 0, ferramenta: 'selecionar',
    sel: { pista: null, clipe: null, faixa: null, faixaPistas: null, marcador: null, regiao: null, sug: null },
    espectro: {}, hist: [], histI: -1, sujo: false, laco: false, copiado: null,
  };

  // ======================================================================
  // Edição (mesmas regras de AudioStudio/as_edicao.py)
  // ======================================================================
  function subtrair(ini, fim, cortes) {
    let ped = [[ini, fim]];
    for (const [a, b] of cortes) {
      const novo = [];
      for (const [x, y] of ped) {
        if (b <= x || a >= y) { novo.push([x, y]); continue; }
        if (a > x) novo.push([x, a]);
        if (b < y) novo.push([b, y]);
      }
      ped = novo;
    }
    return ped.filter(([x, y]) => y - x > 0.004);
  }
  function normalizar(cortes) {
    const cs = cortes.filter(([a, b]) => b - a > 0.004).map(([a, b]) => [+a, +b]).sort((p, q) => p[0] - q[0]);
    const out = [];
    for (const [a, b] of cs) { if (out.length && a <= out[out.length - 1][1] + 1e-6) out[out.length - 1][1] = Math.max(out[out.length - 1][1], b); else out.push([a, b]); }
    return out;
  }
  function moverEnvelope(env, buracos) {
    return (env || []).filter(([t]) => !buracos.some(([a, b]) => a < t && t < b))
      .map(([t, db]) => [Math.max(0, t - buracos.filter(([, b]) => b <= t).reduce((s, [a, b]) => s + b - a, 0)), db]);
  }
  function aplicarRipple(pista, buracos) {
    buracos = normalizar(buracos);
    for (const c of pista.clipes) c.pos = Math.max(0, c.pos - buracos.filter(([, b]) => b <= c.pos + 1e-6).reduce((s, [a, b]) => s + b - a, 0));
    pista.envelope = moverEnvelope(pista.envelope, buracos);
  }
  /** Tira trechos (tempo da FONTE) de todo clipe daquela fonte. */
  function cortarFonte(proj, fid, cortes, ripple = true) {
    cortes = normalizar(cortes);
    for (const pista of proj.pistas) {
      const novos = [], buracos = [];
      for (const c of [...pista.clipes].sort((a, b) => a.pos - b.pos)) {
        if (c.fonte !== fid) { novos.push(c); continue; }
        const ini = c.ini, fim = c.ini + c.dur;
        for (const [a, b] of cortes) { const x = Math.max(a, ini), y = Math.min(b, fim); if (y > x) buracos.push([c.pos + x - ini, c.pos + y - ini]); }
        subtrair(ini, fim, cortes).forEach(([x, y], k) => {
          const n = { ...c, id: k === 0 ? c.id : uid(), ini: x, dur: y - x, pos: c.pos + (x - ini) };
          if (x > ini) n.fi = 0; if (y < fim) n.fo = 0;
          novos.push(n);
        });
      }
      pista.clipes = novos;
      if (ripple && buracos.length) aplicarRipple(pista, buracos);
      pista.clipes.sort((a, b) => a.pos - b.pos);
    }
  }
  /** Tira trechos (tempo do PROJETO) das pistas escolhidas. */
  function cortarTempo(proj, faixas, pistaIds, ripple = true) {
    faixas = normalizar(faixas);
    for (const pista of proj.pistas) {
      if (pistaIds && !pistaIds.includes(pista.id)) continue;
      const novos = [];
      for (const c of pista.clipes) {
        const fim = c.pos + c.dur;
        subtrair(c.pos, fim, faixas).forEach(([x, y], k) => {
          const n = { ...c, id: k === 0 ? c.id : uid(), ini: c.ini + (x - c.pos), dur: y - x, pos: x };
          if (x > c.pos) n.fi = 0; if (y < fim) n.fo = 0;
          novos.push(n);
        });
      }
      pista.clipes = novos;
      if (ripple) aplicarRipple(pista, faixas);
      else pista.envelope = pista.envelope || [];
      pista.clipes.sort((a, b) => a.pos - b.pos);
    }
    if (ripple && (!pistaIds || pistaIds.length === proj.pistas.length)) {
      proj.marcadores = proj.marcadores.filter((m) => !faixas.some(([a, b]) => a < m.t && m.t < b))
        .map((m) => ({ ...m, t: m.t - faixas.filter(([, b]) => b <= m.t).reduce((s, [a, b]) => s + b - a, 0) }));
    }
  }
  function dividir(proj, t, pistaIds) {
    let n = 0;
    for (const pista of proj.pistas) {
      if (pistaIds && !pistaIds.includes(pista.id)) continue;
      const novos = [];
      for (const c of pista.clipes) {
        if (t > c.pos + 0.004 && t < c.pos + c.dur - 0.004) {
          const d = t - c.pos;
          novos.push({ ...c, dur: d, fo: 0 }, { ...c, id: uid(), ini: c.ini + d, dur: c.dur - d, pos: t, fi: 0 });
          n++;
        } else novos.push(c);
      }
      pista.clipes = novos;
    }
    return n;
  }
  function encurtarTrechos(trechos, manter) {
    return trechos.filter(([a, b]) => b - a > manter + 0.05).map(([a, b]) => [a + manter / 2, b - manter / 2]);
  }
  function reduzirTrechos(proj, fid, trechos) {
    for (const pista of proj.pistas) {
      const novos = [];
      for (const c of pista.clipes) {
        if (c.fonte !== fid) { novos.push(c); continue; }
        const ini = c.ini, fim = c.ini + c.dur;
        const lims = [ini, ...[...new Set(trechos.flatMap(([a, b]) => [a, b]).filter((x) => x > ini && x < fim))].sort((a, b) => a - b), fim];
        for (let k = 0; k < lims.length - 1; k++) {
          const x = lims[k], y = lims[k + 1];
          if (y - x <= 0.004) continue;
          const n = { ...c, id: k === 0 ? c.id : uid(), ini: x, dur: y - x, pos: c.pos + (x - ini), fi: x === ini ? c.fi : 0, fo: y === fim ? c.fo : 0 };
          const meio = (x + y) / 2;
          const t = trechos.find(([a, b]) => a <= meio && meio <= b);
          if (t) n.ganho = Math.max(-60, (c.ganho || 0) + t[2]);
          novos.push(n);
        }
      }
      pista.clipes = novos.sort((a, b) => a.pos - b.pos);
    }
  }
  function recortar(proj, a, b, fi = 0.3, fo = 1.5) {
    for (const pista of proj.pistas) {
      const novos = [];
      for (const c of pista.clipes) {
        const x = Math.max(a, c.pos), y = Math.min(b, c.pos + c.dur);
        if (y - x <= 0.004) continue;
        novos.push({ ...c, ini: c.ini + (x - c.pos), dur: y - x, pos: x - a, fi: 0, fo: 0 });
      }
      if (novos.length) {
        novos.sort((p, q) => p.pos - q.pos);
        if (novos[0].pos < 0.01) novos[0].fi = fi;
        const fim = Math.max(...novos.map((c) => c.pos + c.dur));
        novos.forEach((c) => { if (Math.abs(c.pos + c.dur - fim) < 0.01) c.fo = Math.min(fo, c.dur / 2); });
      }
      pista.clipes = novos;
      pista.envelope = (pista.envelope || []).filter(([t]) => a <= t && t <= b).map(([t, db]) => [t - a, db]);
    }
    proj.marcadores = proj.marcadores.filter((m) => a <= m.t && m.t <= b).map((m) => ({ ...m, t: m.t - a }));
    proj.regioes = [];
  }
  function duracao(proj = S.proj) {
    let d = 0;
    for (const p of proj.pistas) for (const c of p.clipes) d = Math.max(d, c.pos + c.dur);
    return d;
  }
  /** Instante da fonte -> instantes no projeto (pode aparecer em mais de um clipe). */
  function fonteParaProjeto(fid, t, proj = S.proj) {
    for (const p of proj.pistas) for (const c of p.clipes) if (c.fonte === fid && c.ini - 1e-6 <= t && t <= c.ini + c.dur + 1e-6) return c.pos + (t - c.ini);
    return null;
  }
  /** Trecho da fonte -> pedaços visíveis no projeto [{pista, x0, x1}] */
  function trechoNoProjeto(fid, a, b, proj = S.proj) {
    const out = [];
    proj.pistas.forEach((p, pi) => p.clipes.forEach((c) => {
      if (c.fonte !== fid) return;
      const x = Math.max(a, c.ini), y = Math.min(b, c.ini + c.dur);
      if (y > x) out.push({ pi, t0: c.pos + x - c.ini, t1: c.pos + y - c.ini });
    }));
    return out;
  }

  // ======================================================================
  // Histórico e salvamento
  // ======================================================================
  const CAMPOS = ['nome', 'pistas', 'marcadores', 'regioes', 'master', 'loudness', 'ducking', 'tags', 'idioma', 'sug_estado'];
  function instantaneo() { const o = {}; CAMPOS.forEach((k) => { o[k] = S.proj[k]; }); return JSON.stringify(o); }
  function iniciarHistorico() { S.hist = [instantaneo()]; S.histI = 0; atualizarBotoesHist(); }
  function confirmar(rotulo) {
    const snap = instantaneo();
    if (S.hist[S.histI] === snap) return;
    S.hist = S.hist.slice(0, S.histI + 1); S.hist.push(snap);
    if (S.hist.length > 200) S.hist.shift();
    S.histI = S.hist.length - 1;
    atualizarBotoesHist(); agendarSalvar(); redesenhar(true); desenharCabecas(); desenharInspetor();
    if (Toca.ativo) Toca.reiniciar();
    if (rotulo) $('#salvo').textContent = rotulo;
    painelAtual() === 'sugestoes' && desenharSugestoes();
    painelAtual() === 'texto' && marcarPalavrasCortadas();
  }
  function restaurar(snap) {
    const o = JSON.parse(snap); CAMPOS.forEach((k) => { S.proj[k] = o[k]; });
    S.sel.clipe = null; agendarSalvar(); redesenhar(true); desenharCabecas(); desenharInspetor(); renderPainel();
    if (Toca.ativo) Toca.reiniciar();
  }
  function desfazer() { if (S.histI > 0) { S.histI--; restaurar(S.hist[S.histI]); atualizarBotoesHist(); } }
  function refazer() { if (S.histI < S.hist.length - 1) { S.histI++; restaurar(S.hist[S.histI]); atualizarBotoesHist(); } }
  function atualizarBotoesHist() { $('#desfazer').disabled = S.histI <= 0; $('#refazer').disabled = S.histI >= S.hist.length - 1; }

  let salvarT = null, salvando = false;
  function agendarSalvar() {
    S.sujo = true; $('#salvo').textContent = 'Salvando…';
    clearTimeout(salvarT); salvarT = setTimeout(salvar, 700);
  }
  async function salvar() {
    if (!S.proj || salvando) { if (salvando) agendarSalvar(); return; }
    salvando = true;
    const corpo = JSON.parse(instantaneo()); corpo.versao_base = S.proj.versao;
    try {
      const d = await json(`${API}/projeto/${S.proj.id}`, corpo, 'PUT');
      S.proj.versao = d.versao; S.sujo = false; $('#salvo').textContent = 'Salvo';
    } catch (e) {
      if (e.conflito) { toast(e.message); await recarregarProjeto(true); }
      else { $('#salvo').textContent = 'Não salvou'; toast(`Não consegui salvar: ${e.message}`, true); }
    } finally { salvando = false; }
  }

  // ======================================================================
  // Carregar projeto
  // ======================================================================
  async function abrirProjeto(pid) {
    const d = await api(`${API}/projeto/${pid}`);
    S.proj = d.projeto; S.proj.sug_estado = S.proj.sug_estado || {};
    S.fontes = d.projeto.fontes; S.picos = {}; S.espectro = {};
    S.sel = { pista: S.proj.pistas[0]?.id || null, clipe: null, faixa: null, faixaPistas: null, marcador: null, regiao: null, sug: null };
    S.agulha = 0; S.scroll = 0;
    history.replaceState(null, '', `?projeto=${pid}`);
    $('#inicio').hidden = true; $('#editor').hidden = false;
    $('#nomeProjeto').value = S.proj.nome;
    document.title = `${S.proj.nome} · Áudio Studio`;
    iniciarHistorico();
    await Promise.all([carregarPicosTodos(), carregarSugestoes(), carregarTranscricao()]);
    redimensionar(); caber(); desenharCabecas(); desenharInspetor(); renderPainel(); avisoLongo();
    $('#salvo').textContent = 'Salvo';
  }
  async function recarregarProjeto(manterVista = false) {
    if (!S.proj) return;
    const d = await api(`${API}/projeto/${S.proj.id}`);
    const vista = { scroll: S.scroll, zoom: S.zoom, agulha: S.agulha };
    const antes = S.proj.versao;
    S.proj = d.projeto; S.proj.sug_estado = S.proj.sug_estado || {}; S.fontes = d.projeto.fontes;
    if (S.proj.versao !== antes) {     // mudou no servidor: entra no histórico (dá para desfazer)
      const snap = instantaneo(); S.hist = S.hist.slice(0, S.histI + 1); S.hist.push(snap); S.histI = S.hist.length - 1; atualizarBotoesHist();
    }
    if (manterVista) Object.assign(S, vista);
    await Promise.all([carregarPicosTodos(), carregarSugestoes(), carregarTranscricao()]);
    redimensionar(); desenharCabecas(); desenharInspetor(); renderPainel(); avisoLongo();
  }
  async function carregarPicosTodos() {
    const fids = Object.keys(S.fontes);
    await Promise.all(fids.map((fid) => carregarPicos(fid)));
  }
  async function carregarPicos(fid) {
    const f = S.fontes[fid]; if (!f) return;
    const at = S.picos[fid];
    if (at && at.ate >= f.pronto_ate && f.estado === 'pronta') return;
    const [r0, r1] = await Promise.all([0, 1].map((n) => fetch(`${API}/projeto/${S.proj.id}/fonte/${fid}/picos?nivel=${n}`).then((r) => r.arrayBuffer())));
    S.picos[fid] = { l0: new Int8Array(r0), l1: new Int8Array(r1), ate: f.pronto_ate };
  }
  async function carregarSugestoes() { try { S.sug = await api(`${API}/projeto/${S.proj.id}/sugestoes`); } catch { S.sug = { fontes: {} }; } }
  async function carregarTranscricao() { try { S.transcr = (await api(`${API}/projeto/${S.proj.id}/transcricao`)).fontes; } catch { S.transcr = {}; } }
  function avisoLongo() {
    const longas = Object.values(S.fontes).filter((f) => f.longa);
    const prep = Object.values(S.fontes).filter((f) => f.estado !== 'pronta');
    const el = $('#avisoLongo');
    if (!longas.length && !prep.length) { el.hidden = true; return; }
    const partes = [];
    if (longas.length) partes.push(`<b>Modo fila:</b> ${longas.map((f) => `"${esc(f.nome)}" (${fmtCurto(f.duracao)})`).join(', ')} passa${longas.length > 1 ? 'm' : ''} de 1 hora, então preparo, transcrição, análise e exportação andam em blocos de 10 minutos na aba Fila. Dá para editar e ouvir o que já está pronto enquanto o resto processa.`);
    if (prep.length) partes.push(`Preparando ${prep.map((f) => `"${esc(f.nome)}": ${Math.round(100 * (f.pronto_ate || 0) / f.duracao)}%`).join(', ')}.`);
    el.innerHTML = partes.join(' '); el.hidden = false;
  }

  // ======================================================================
  // Linha do tempo: desenho
  // ======================================================================
  const tela = $('#tela'), wrap = $('#telaWrap');
  const g = tela.getContext('2d');
  const base = document.createElement('canvas'), gb = base.getContext('2d');
  let W = 800, H = 300, dpr = 1, baseOk = false;
  const tx = (t) => (t - S.scroll) * S.zoom;
  const xt = (x) => S.scroll + x / S.zoom;

  function redimensionar() {
    if (!S.proj) return;
    dpr = window.devicePixelRatio || 1;
    W = Math.max(200, wrap.clientWidth);
    H = REGUA + S.proj.pistas.length * ALT + ZONA_NOVA;
    for (const c of [tela, base]) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
    tela.style.height = `${H}px`;
    $('#vazioEditor').hidden = duracao() > 0;
    redesenhar(true);
  }
  window.addEventListener('resize', () => { redimensionar(); });

  let rafPend = false;
  function redesenhar(tudo = false) {
    if (tudo) baseOk = false;
    if (rafPend) return;
    rafPend = true;
    requestAnimationFrame(() => { rafPend = false; desenhar(); });
  }
  function desenhar() {
    if (!S.proj) return;
    if (!baseOk) { desenharBase(); baseOk = true; }
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, tela.width, tela.height);
    g.drawImage(base, 0, 0);
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    // agulha
    const x = tx(S.agulha);
    if (x >= -2 && x <= W + 2) {
      g.fillStyle = '#fbbf24';
      g.fillRect(Math.round(x) - 0.5, REGUA - 2, 1.5, H - REGUA - ZONA_NOVA + 2);
      g.beginPath(); g.moveTo(x - 6, 0); g.lineTo(x + 6, 0); g.lineTo(x + 6, 8); g.lineTo(x, 15); g.lineTo(x - 6, 8); g.closePath(); g.fill();
    }
    atualizarRelogio();
  }

  function passoRegua() {
    const alvo = 90 / S.zoom;   // segundos a cada ~90 px
    const passos = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
    return passos.find((p) => p >= alvo) || 3600;
  }
  function batidasProjeto() {
    const out = [];
    for (const [fid, info] of Object.entries(S.sug.fontes || {})) {
      if (!info.batidas) continue;
      for (const b of info.batidas) { const t = fonteParaProjeto(fid, b); if (t != null) out.push(t); }
    }
    return out;
  }
  function desenharBase() {
    const c = gb;
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, base.width, base.height); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    const t0 = xt(0), t1 = xt(W);
    // pistas
    S.proj.pistas.forEach((p, i) => {
      const y = REGUA + i * ALT;
      c.fillStyle = i % 2 ? '#101215' : '#0d0f12';
      c.fillRect(0, y, W, ALT);
      if (p.id === S.sel.pista) { c.fillStyle = 'rgba(251,191,36,0.04)'; c.fillRect(0, y, W, ALT); }
      c.fillStyle = 'rgba(255,255,255,0.06)'; c.fillRect(0, y + ALT - 1, W, 1);
      for (const cl of p.clipes) {
        if (cl.pos + cl.dur < t0 || cl.pos > t1) continue;
        desenharClipe(c, p, cl, y);
      }
      if (S.ferramenta === 'envelope' || (p.envelope && p.envelope.length)) desenharEnvelope(c, p, y);
    });
    // zona para nova pista
    const yz = REGUA + S.proj.pistas.length * ALT;
    c.fillStyle = 'rgba(255,255,255,0.02)'; c.fillRect(0, yz, W, ZONA_NOVA);
    c.fillStyle = 'rgba(255,255,255,0.28)'; c.font = '12px Geist, sans-serif'; c.textBaseline = 'middle';
    c.fillText('Solte um arquivo aqui para criar uma pista nova', 12, yz + ZONA_NOVA / 2);
    // sugestões (etiquetas)
    desenharEtiquetas(c, t0, t1);
    // seleção de tempo
    if (S.sel.faixa) {
      const [a, b] = S.sel.faixa;
      const xa = tx(a), xb = tx(b);
      const ids = S.sel.faixaPistas;
      S.proj.pistas.forEach((p, i) => {
        if (ids && !ids.includes(p.id)) return;
        c.fillStyle = 'rgba(251,191,36,0.16)'; c.fillRect(xa, REGUA + i * ALT, xb - xa, ALT);
      });
      c.fillStyle = 'rgba(251,191,36,0.85)'; c.fillRect(xa, REGUA, 1, H - REGUA - ZONA_NOVA); c.fillRect(xb - 1, REGUA, 1, H - REGUA - ZONA_NOVA);
    }
    // marcadores (linha fina nas pistas)
    for (const m of S.proj.marcadores) {
      const x = tx(m.t); if (x < -1 || x > W + 1) continue;
      c.fillStyle = m.id === S.sel.marcador ? 'rgba(96,165,250,0.95)' : 'rgba(96,165,250,0.45)';
      c.fillRect(Math.round(x), REGUA, 1, H - REGUA - ZONA_NOVA);
    }
    desenharRegua(c, t0, t1);
  }

  function desenharRegua(c, t0, t1) {
    c.fillStyle = '#15130f'; c.fillRect(0, 0, W, REGUA);
    // perfurações da fita
    c.fillStyle = 'rgba(251,191,36,0.10)';
    const passoF = 12, off = (-(S.scroll * S.zoom) % passoF + passoF) % passoF;
    for (let x = off; x < W; x += passoF) c.fillRect(x, 3, 5, 3);
    // regiões
    for (const r of S.proj.regioes) {
      const xa = tx(r.ini), xb = tx(r.fim); if (xb < 0 || xa > W) continue;
      c.fillStyle = r.id === S.sel.regiao ? 'rgba(74,222,128,0.5)' : 'rgba(74,222,128,0.26)';
      c.fillRect(xa, 0, xb - xa, 11);
      c.fillStyle = '#bbf7d0'; c.font = '600 9.5px Geist, sans-serif'; c.textBaseline = 'middle';
      c.save(); c.beginPath(); c.rect(xa, 0, xb - xa, 11); c.clip(); c.fillText(r.nome, xa + 4, 6); c.restore();
    }
    // batidas
    const bts = batidasProjeto();
    if (bts.length && S.zoom * 0.25 > 4) {
      c.fillStyle = 'rgba(96,165,250,0.5)';
      for (const b of bts) { const x = tx(b); if (x >= 0 && x <= W) c.fillRect(Math.round(x), REGUA - 6, 1, 6); }
    }
    // marcas de tempo
    const p = passoRegua();
    c.fillStyle = 'rgba(255,255,255,0.55)'; c.font = '10.5px "Geist Mono", monospace'; c.textBaseline = 'alphabetic';
    for (let t = Math.floor(t0 / p) * p; t <= t1 + p; t += p) {
      const x = tx(t);
      c.fillStyle = 'rgba(255,255,255,0.35)'; c.fillRect(Math.round(x), REGUA - 10, 1, 10);
      for (let k = 1; k < 5; k++) { const xs = tx(t + (p * k) / 5); c.fillStyle = 'rgba(255,255,255,0.13)'; c.fillRect(Math.round(xs), REGUA - 5, 1, 5); }
      c.fillStyle = 'rgba(255,255,255,0.6)';
      const rot = p < 1 ? fmt(t).replace(/0+$/, '').replace(/\.$/, '') : fmtCurto(t);
      c.fillText(rot, x + 3, REGUA - 12);
    }
    // marcadores (cabeça na régua)
    for (const m of S.proj.marcadores) {
      const x = tx(m.t); if (x < -10 || x > W + 10) continue;
      c.fillStyle = m.id === S.sel.marcador ? '#93c5fd' : '#60a5fa';
      c.beginPath(); c.moveTo(x - 5, 18); c.lineTo(x + 5, 18); c.lineTo(x, 26); c.closePath(); c.fill();
      if (m.nome) { c.font = '10px Geist, sans-serif'; c.fillText(m.nome, x + 7, 25); }
    }
    if (S.sel.faixa) {
      const [a, b] = S.sel.faixa;
      c.fillStyle = 'rgba(251,191,36,0.35)'; c.fillRect(tx(a), REGUA - 4, tx(b) - tx(a), 4);
    }
    c.fillStyle = 'rgba(255,255,255,0.1)'; c.fillRect(0, REGUA - 1, W, 1);
  }

  function ganhoEm(cl, tc) {
    const fi = Math.max(cl.fi || 0, MICRO), fo = Math.max(cl.fo || 0, MICRO);
    return Math.min(1, tc / fi) * Math.min(1, Math.max(0, cl.dur - tc) / fo);
  }

  function desenharClipe(c, p, cl, y) {
    const x0 = tx(cl.pos), x1 = tx(cl.pos + cl.dur);
    const cor = COR_TIPO[p.tipo] || COR_TIPO.voz;
    const sel = cl.id === S.sel.clipe;
    const fonte = S.fontes[cl.fonte];
    const yi = y + 4, h = ALT - 9;
    c.save();
    c.beginPath(); c.rect(Math.max(-2, x0), yi, Math.min(W + 4, x1) - Math.max(-2, x0), h); c.clip();
    c.fillStyle = sel ? 'rgba(251,191,36,0.20)' : `${cor}1f`;
    c.fillRect(x0, yi, x1 - x0, h);
    // onda ou espectro
    if (S.espectro[p.id]) desenharEspectro(c, cl, x0, x1, yi + 14, h - 14);
    else desenharOnda(c, cl, x0, x1, yi + 14, h - 16, cor, fonte, p);
    // fades
    c.fillStyle = 'rgba(0,0,0,0.38)';
    if (cl.fi > 0) { c.beginPath(); c.moveTo(x0, yi + 13); c.lineTo(x0 + cl.fi * S.zoom, yi + 13); c.lineTo(x0, yi + h); c.closePath(); c.fill(); }
    if (cl.fo > 0) { c.beginPath(); c.moveTo(x1, yi + 13); c.lineTo(x1 - cl.fo * S.zoom, yi + 13); c.lineTo(x1, yi + h); c.closePath(); c.fill(); }
    // título do clipe
    c.fillStyle = sel ? 'rgba(251,191,36,0.9)' : `${cor}cc`;
    c.fillRect(x0, yi, x1 - x0, 13);
    c.fillStyle = '#16120a'; c.font = '600 10.5px Geist, sans-serif'; c.textBaseline = 'middle';
    const nome = (fonte ? fonte.nome : '?') + (cl.ganho ? `  ${cl.ganho > 0 ? '+' : ''}${cl.ganho.toFixed(1)} dB` : '');
    if (x1 - x0 > 30) c.fillText(nome, Math.max(x0, 0) + 5, yi + 7);
    // alças de fade
    if (sel) {
      c.fillStyle = '#fff';
      c.fillRect(x0 + cl.fi * S.zoom - 3, yi + 14, 6, 6);
      c.fillRect(x1 - cl.fo * S.zoom - 3, yi + 14, 6, 6);
    }
    c.restore();
    c.strokeStyle = sel ? '#fbbf24' : `${cor}66`; c.lineWidth = sel ? 1.5 : 1;
    c.strokeRect(x0 + 0.5, yi + 0.5, x1 - x0 - 1, h - 1);
    // ainda preparando
    if (fonte && fonte.estado !== 'pronta') {
      const xp = tx(cl.pos + Math.max(0, (fonte.pronto_ate || 0) - cl.ini));
      c.save(); c.beginPath(); c.rect(Math.max(xp, x0), yi + 13, x1 - Math.max(xp, x0), h - 13); c.clip();
      c.fillStyle = 'rgba(255,255,255,0.05)';
      for (let k = Math.floor(Math.max(xp, x0) / 10) * 10 - 100; k < x1; k += 10) { c.beginPath(); c.moveTo(k, yi + h); c.lineTo(k + 60, yi + 13); c.lineTo(k + 64, yi + 13); c.lineTo(k + 4, yi + h); c.fill(); }
      c.restore();
    }
  }

  function desenharOnda(c, cl, x0, x1, yt, h, cor, fonte, pista) {
    const pk = S.picos[cl.fonte];
    if (!pk || !pk.l0.length) return;
    const meio = yt + h / 2, amp = h / 2 - 1;
    const xa = Math.max(0, Math.floor(x0)), xb = Math.min(W, Math.ceil(x1));
    const porPx = 250 / S.zoom;     // picos de nível 0 por pixel
    const usar1 = porPx >= 32;
    const arr = usar1 ? pk.l1 : pk.l0, taxa = usar1 ? 250 / 16 : 250;
    const n = arr.length / 2;
    const ganho = lin((cl.ganho || 0) + (pista.ganho || 0));
    c.fillStyle = `${cor}d9`;
    if (porPx < 1) {   // zoom alto: linha ligando os picos
      c.beginPath();
      for (let x = xa; x <= xb; x++) {
        const tsrc = cl.ini + (xt(x) - cl.pos);
        const i = Math.floor(tsrc * taxa);
        if (i < 0 || i >= n) continue;
        const v = Math.max(Math.abs(arr[2 * i]), Math.abs(arr[2 * i + 1])) / 128 * ganho * ganhoEm(cl, tsrc - cl.ini);
        c.rect(x, meio - Math.min(1, v) * amp, 1, Math.max(1, 2 * Math.min(1, v) * amp));
      }
      c.fill();
      return;
    }
    c.beginPath();
    for (let x = xa; x < xb; x++) {
      const ta = cl.ini + (xt(x) - cl.pos), tb = cl.ini + (xt(x + 1) - cl.pos);
      let i0 = Math.floor(ta * taxa), i1 = Math.max(i0 + 1, Math.floor(tb * taxa));
      if (i1 <= 0 || i0 >= n) continue;
      i0 = Math.max(0, i0); i1 = Math.min(n, i1);
      let mn = 127, mx = -128;
      for (let i = i0; i < i1; i++) { const a = arr[2 * i], b = arr[2 * i + 1]; if (a < mn) mn = a; if (b > mx) mx = b; }
      const gf = ganho * ganhoEm(cl, (ta + tb) / 2 - cl.ini);
      const top = meio - Math.min(1, (mx / 128) * gf) * amp, bot = meio - Math.max(-1, (mn / 128) * gf) * amp;
      c.rect(x, top, 1, Math.max(1, bot - top));
    }
    c.fill();
  }

  function desenharEspectro(c, cl, x0, x1, yt, h) {
    const xa = Math.max(0, x0), xb = Math.min(W, x1);
    if (xb - xa < 4) return;
    const ta = cl.ini + (xt(xa) - cl.pos), tb = cl.ini + (xt(xb) - cl.pos);
    const larg = Math.round(xb - xa);
    const chave = `${cl.fonte}:${ta.toFixed(2)}:${tb.toFixed(2)}:${larg}`;
    const cache = S.espectro._img || (S.espectro._img = {});
    const img = cache[chave];
    if (img && img.complete && img.naturalWidth) { c.drawImage(img, xa, yt, xb - xa, h); return; }
    if (!img) {
      const im = new Image();
      im.onload = () => redesenhar(true);
      im.src = `${API}/projeto/${S.proj.id}/fonte/${cl.fonte}/espectro?ini=${ta.toFixed(3)}&dur=${(tb - ta).toFixed(3)}&w=${larg}&h=${Math.round(h * 2)}`;
      cache[chave] = im;
      const chaves = Object.keys(cache); if (chaves.length > 60) delete cache[chaves[0]];
    }
    c.fillStyle = 'rgba(255,255,255,0.3)'; c.font = '11px Geist, sans-serif'; c.fillText('Desenhando o espectro…', xa + 8, yt + h / 2);
  }

  function envDb(p, t) {
    const e = p.envelope || [];
    if (!e.length) return 0;
    if (t <= e[0][0]) return e[0][1];
    if (t >= e[e.length - 1][0]) return e[e.length - 1][1];
    for (let i = 1; i < e.length; i++) if (t <= e[i][0]) { const [a, da] = e[i - 1], [b, db] = e[i]; return da + (db - da) * (t - a) / (b - a || 1); }
    return 0;
  }
  const dbY = (db, y) => y + 14 + (1 - (clamp(db, -40, 12) + 40) / 52) * (ALT - 24);
  const yDb = (yy, y) => clamp(-40 + (1 - (yy - y - 14) / (ALT - 24)) * 52, -40, 12);
  function desenharEnvelope(c, p, y) {
    const e = p.envelope || [];
    c.strokeStyle = S.ferramenta === 'envelope' ? '#60a5fa' : 'rgba(96,165,250,0.55)'; c.lineWidth = 1.5;
    c.beginPath();
    c.moveTo(0, dbY(envDb(p, xt(0)), y));
    for (const [t, db] of e) { const x = tx(t); if (x > -50 && x < W + 50) c.lineTo(x, dbY(db, y)); }
    c.lineTo(W, dbY(envDb(p, xt(W)), y));
    c.stroke();
    if (S.ferramenta === 'envelope') {
      c.fillStyle = '#93c5fd';
      for (const [t, db] of e) { const x = tx(t); if (x > -5 && x < W + 5) { c.beginPath(); c.arc(x, dbY(db, y), 4, 0, 7); c.fill(); } }
      c.fillStyle = 'rgba(147,197,253,0.6)'; c.font = '10px Geist, sans-serif'; c.fillText('0 dB', 4, dbY(0, y) - 4);
    }
  }

  // etiquetas das sugestões ainda abertas
  function sugestoesAbertas() {
    const out = [];
    for (const [fid, info] of Object.entries(S.sug.fontes || {})) {
      for (const s of info.sugestoes || []) {
        if (S.proj.sug_estado[s.id]) continue;
        if (!S.fontes[fid]) continue;
        out.push(s);
      }
    }
    return out;
  }
  let etiquetas = [];
  function desenharEtiquetas(c, t0, t1) {
    etiquetas = [];
    for (const s of sugestoesAbertas()) {
      if (s.acao === 'efeito' || (s.fim - s.ini) <= 0) continue;
      for (const pc of trechoNoProjeto(s.fonte, s.ini, s.fim)) {
        if (pc.t1 < t0 || pc.t0 > t1) continue;
        const xa = tx(pc.t0), xb = Math.max(tx(pc.t1), xa + 3), y = REGUA + pc.pi * ALT + ALT - 18;
        const cor = COR_CAT[s.cat] || '#fff';
        c.fillStyle = s.id === S.sel.sug ? `${cor}aa` : `${cor}40`;
        c.fillRect(xa, REGUA + pc.pi * ALT + 17, xb - xa, ALT - 26);
        c.fillStyle = cor; c.fillRect(xa, y, xb - xa, 10);
        etiquetas.push({ s, xa, xb, y0: REGUA + pc.pi * ALT + 17, y1: y + 10 });
      }
    }
  }

  // ======================================================================
  // Cabeças das pistas (DOM)
  // ======================================================================
  function desenharCabecas() {
    if (!S.proj) return;
    const el = $('#cabecas');
    el.innerHTML = `<div class="cab-regua">Pistas</div>` + S.proj.pistas.map((p) => `
      <div class="cab${p.id === S.sel.pista ? ' sel' : ''}" data-p="${p.id}" style="height:${ALT}px">
        <div class="cab-l1">
          <input class="cab-nome" value="${esc(p.nome)}" aria-label="Nome da pista" data-campo="nome">
          <button class="cab-bt m" data-bt="mudo" aria-pressed="${!!p.mudo}" title="Mudo">M</button>
          <button class="cab-bt s" data-bt="solo" aria-pressed="${!!p.solo}" title="Solo">S</button>
          <button class="cab-bt e" data-bt="espectro" aria-pressed="${!!S.espectro[p.id]}" title="Espectrograma">≋</button>
        </div>
        <div class="cab-l2">
          <label>Vol ${p.ganho > 0 ? '+' : ''}${(+p.ganho).toFixed(1)} dB<input type="range" min="-30" max="12" step="0.5" value="${p.ganho}" data-campo="ganho" aria-label="Volume da pista"></label>
          <label>Pan ${p.pan === 0 ? 'C' : p.pan < 0 ? `E${Math.round(-p.pan * 100)}` : `D${Math.round(p.pan * 100)}`}<input type="range" min="-1" max="1" step="0.05" value="${p.pan}" data-campo="pan" aria-label="Pan da pista"></label>
        </div>
        <div class="linha" style="gap:4px">
          <select class="cab-tipo" data-campo="tipo" aria-label="Tipo da pista"><option value="voz"${p.tipo === 'voz' ? ' selected' : ''}>Voz</option><option value="musica"${p.tipo === 'musica' ? ' selected' : ''}>Música</option><option value="efeito"${p.tipo === 'efeito' ? ' selected' : ''}>Efeitos</option></select>
          ${S.proj.pistas.length > 1 ? `<button class="cab-bt" data-bt="apagar" title="Apagar pista" aria-label="Apagar pista">✕</button>` : ''}
        </div>
      </div>`).join('') + `<div class="cab-nova" style="height:${ZONA_NOVA}px"><button class="btn ghost xs" id="novaPista" type="button">+ Pista</button></div>`;
  }
  $('#cabecas').addEventListener('click', (e) => {
    const cab = e.target.closest('.cab');
    if (e.target.id === 'novaPista') { S.proj.pistas.push({ id: uid(), nome: `Pista ${S.proj.pistas.length + 1}`, tipo: 'voz', ganho: 0, pan: 0, mudo: false, solo: false, envelope: [], clipes: [] }); redimensionar(); confirmar(); return; }
    if (!cab) return;
    const p = S.proj.pistas.find((x) => x.id === cab.dataset.p);
    const bt = e.target.closest('[data-bt]');
    if (bt) {
      const k = bt.dataset.bt;
      if (k === 'espectro') { S.espectro[p.id] = !S.espectro[p.id]; desenharCabecas(); redesenhar(true); return; }
      if (k === 'apagar') {
        if (p.clipes.length && !confirm(`Apagar a pista "${p.nome}" e os ${p.clipes.length} clipe(s) dela?`)) return;
        S.proj.pistas = S.proj.pistas.filter((x) => x !== p); S.sel.pista = S.proj.pistas[0].id; redimensionar(); confirmar(); return;
      }
      p[k] = !p[k]; confirmar(); Toca.atualizarMix(); return;
    }
    if (!e.target.matches('input, select')) { S.sel.pista = p.id; desenharCabecas(); redesenhar(true); }
  });
  $('#cabecas').addEventListener('input', (e) => {
    const cab = e.target.closest('.cab'); if (!cab) return;
    const p = S.proj.pistas.find((x) => x.id === cab.dataset.p); const k = e.target.dataset.campo;
    if (k === 'ganho' || k === 'pan') { p[k] = +e.target.value; e.target.parentElement.firstChild.textContent = k === 'ganho' ? `Vol ${p.ganho > 0 ? '+' : ''}${p.ganho.toFixed(1)} dB` : `Pan ${p.pan === 0 ? 'C' : p.pan < 0 ? `E${Math.round(-p.pan * 100)}` : `D${Math.round(p.pan * 100)}`}`; Toca.atualizarMix(); redesenhar(true); }
  });
  $('#cabecas').addEventListener('change', (e) => {
    const cab = e.target.closest('.cab'); if (!cab) return;
    const p = S.proj.pistas.find((x) => x.id === cab.dataset.p); const k = e.target.dataset.campo;
    if (k === 'nome') p.nome = e.target.value.trim().slice(0, 40) || p.nome;
    else if (k === 'tipo') p.tipo = e.target.value;
    else if (k) p[k] = +e.target.value;
    confirmar();
  });

  // ======================================================================
  // Interação na linha do tempo
  // ======================================================================
  function pistaEm(y) { const i = Math.floor((y - REGUA) / ALT); return i >= 0 && i < S.proj.pistas.length ? i : -1; }
  function clipeEm(x, y) {
    const i = pistaEm(y); if (i < 0) return null;
    const t = xt(x), p = S.proj.pistas[i];
    for (let k = p.clipes.length - 1; k >= 0; k--) { const c = p.clipes[k]; if (t >= c.pos && t <= c.pos + c.dur) return { p, c, i }; }
    return null;
  }
  function pontosImã(excluir) {
    const pts = [0, S.agulha];
    for (const p of S.proj.pistas) for (const c of p.clipes) if (c !== excluir) pts.push(c.pos, c.pos + c.dur);
    S.proj.marcadores.forEach((m) => pts.push(m.t));
    S.proj.regioes.forEach((r) => pts.push(r.ini, r.fim));
    batidasProjeto().forEach((b) => pts.push(b));
    for (const [fid, tr] of Object.entries(S.transcr || {})) {
      if (S.zoom < 40) break;
      for (const w of tr.palavras) { const a = fonteParaProjeto(fid, w.ini); if (a != null) pts.push(a); }
    }
    return pts;
  }
  function imã(t, excluir, pts) {
    if (!$('#optIma').checked) return t;
    const lim = 8 / S.zoom;
    let melhor = t, d = lim;
    for (const p of pts || pontosImã(excluir)) { const dd = Math.abs(p - t); if (dd < d) { d = dd; melhor = p; } }
    return melhor;
  }

  let arr = null;
  wrap.addEventListener('pointerdown', (e) => {
    if (!S.proj || e.button === 2) return;
    wrap.focus({ preventScroll: true });
    const r = tela.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top, t = xt(x);
    // régua
    if (y < REGUA) {
      const mk = S.proj.marcadores.find((m) => Math.abs(tx(m.t) - x) < 6 && y > 16);
      if (mk) { S.sel.marcador = mk.id; arr = { tipo: 'marcador', m: mk }; redesenhar(true); desenharInspetor(); }
      else {
        const rg = S.proj.regioes.find((g2) => y <= 11 && x >= tx(g2.ini) && x <= tx(g2.fim));
        if (rg) { S.sel.regiao = rg.id; S.sel.faixa = [rg.ini, rg.fim]; S.sel.faixaPistas = null; desenharInspetor(); redesenhar(true); return; }
        S.sel.marcador = null; S.sel.regiao = null;
        arr = { tipo: 'regua', t0: t, moveu: false };
        Toca.buscar(Math.max(0, t));
      }
      wrap.setPointerCapture(e.pointerId); return;
    }
    const i = pistaEm(y);
    // envelope
    if (S.ferramenta === 'envelope' && i >= 0) {
      const p = S.proj.pistas[i]; const yb = REGUA + i * ALT;
      p.envelope = p.envelope || [];
      let k = p.envelope.findIndex(([tt, db]) => Math.abs(tx(tt) - x) < 7 && Math.abs(dbY(db, yb) - y) < 7);
      if (k < 0) { p.envelope.push([Math.max(0, t), yDb(y, yb)]); p.envelope.sort((a, b) => a[0] - b[0]); k = p.envelope.findIndex(([tt]) => tt === Math.max(0, t)); }
      if (e.detail === 2) { p.envelope.splice(k, 1); confirmar(); return; }
      arr = { tipo: 'env', p, k, yb }; S.sel.pista = p.id; wrap.setPointerCapture(e.pointerId); redesenhar(true); return;
    }
    // etiqueta de sugestão
    const et = etiquetas.find((q) => x >= q.xa && x <= q.xb && y >= q.y1 - 10 && y <= q.y1);
    if (et) { focarSugestao(et.s.id); return; }
    const hit = clipeEm(x, y);
    if (S.ferramenta === 'navalha') {
      if (hit) { const tt = imã(t, null); dividir(S.proj, tt, [hit.p.id]); confirmar('Dividido'); }
      return;
    }
    if (hit) {
      // título do clipe = mover; bordas = aparar; alças = fades; na onda = selecionar um trecho
      const { p, c } = hit;
      const x0 = tx(c.pos), x1 = tx(c.pos + c.dur), yi = REGUA + hit.i * ALT + 4;
      let modo = null;
      if (S.sel.clipe === c.id && y > yi + 12 && y < yi + 24 && Math.abs(x - (x0 + c.fi * S.zoom)) < 7) modo = 'fi';
      else if (S.sel.clipe === c.id && y > yi + 12 && y < yi + 24 && Math.abs(x - (x1 - c.fo * S.zoom)) < 7) modo = 'fo';
      else if (x - x0 < 7 && x1 - x0 > 20) modo = 'ini';
      else if (x1 - x < 7 && x1 - x0 > 20) modo = 'fim';
      else if (y <= yi + 13) modo = 'mover';
      S.sel.pista = p.id; S.sel.clipe = c.id; S.sel.marcador = null; S.sel.regiao = null;
      if (modo) {
        S.sel.faixa = null;
        arr = { tipo: modo, p, c, t0: t, orig: { ...c }, pi: hit.i, moveu: false, pts: pontosImã(c) };
        wrap.setPointerCapture(e.pointerId);
        desenharCabecas(); desenharInspetor(); redesenhar(true);
        return;
      }
    } else {
      S.sel.clipe = null;
    }
    // seleção de tempo (na onda ou no vazio)
    S.sel.marcador = null; S.sel.regiao = null;
    if (i >= 0) S.sel.pista = S.proj.pistas[i].id;
    const tt = imã(t, null);
    arr = { tipo: 'faixa', t0: tt, i0: i, moveu: false };
    if (e.shiftKey && S.sel.faixa) arr.t0 = Math.abs(S.sel.faixa[0] - t) > Math.abs(S.sel.faixa[1] - t) ? S.sel.faixa[0] : S.sel.faixa[1];
    wrap.setPointerCapture(e.pointerId);
    desenharCabecas(); desenharInspetor();
  });
  wrap.addEventListener('pointermove', (e) => {
    const r = tela.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top, t = xt(x);
    if (!arr) { cursor(x, y); return; }
    arr.moveu = true;
    const a = arr;
    if (a.tipo === 'regua') {
      if (Math.abs(t - a.t0) * S.zoom > 4) { const tt = imã(t, null); S.sel.faixa = [Math.min(a.t0, tt), Math.max(a.t0, tt)]; S.sel.faixaPistas = null; redesenhar(true); }
      Toca.buscar(Math.max(0, t));
    } else if (a.tipo === 'marcador') { a.m.t = Math.max(0, imã(t, null)); redesenhar(true); }
    else if (a.tipo === 'env') {
      const pt = a.p.envelope[a.k]; if (!pt) return;
      pt[0] = Math.max(0, t); pt[1] = Math.round(yDb(y, a.yb) * 2) / 2; a.p.envelope.sort((p1, p2) => p1[0] - p2[0]); a.k = a.p.envelope.indexOf(pt); redesenhar(true);
    } else if (a.tipo === 'faixa') {
      const tt = imã(t, null);
      if (Math.abs(tt - a.t0) * S.zoom > 3) {
        S.sel.faixa = [Math.max(0, Math.min(a.t0, tt)), Math.max(a.t0, tt)];
        const i1 = clamp(pistaEm(y), 0, S.proj.pistas.length - 1);
        const lo = Math.min(a.i0 < 0 ? i1 : a.i0, i1), hi = Math.max(a.i0 < 0 ? i1 : a.i0, i1);
        S.sel.faixaPistas = S.proj.pistas.slice(lo, hi + 1).map((p) => p.id);
        redesenhar(true);
      }
    } else if (a.c) {
      const c = a.c, o = a.orig, dt = t - a.t0, fonte = S.fontes[c.fonte];
      if (a.tipo === 'mover') {
        let pos = Math.max(0, o.pos + dt);
        const s1 = imã(pos, c, a.pts), s2 = imã(pos + o.dur, c, a.pts) - o.dur;
        pos = Math.abs(s1 - pos) <= Math.abs(s2 - pos) ? s1 : Math.max(0, s2);
        c.pos = pos;
        const i = pistaEm(y);
        if (i >= 0 && i !== a.pi) { const de = S.proj.pistas[a.pi], para = S.proj.pistas[i]; de.clipes = de.clipes.filter((x2) => x2 !== c); para.clipes.push(c); a.pi = i; a.p = para; S.sel.pista = para.id; desenharCabecas(); }
      } else if (a.tipo === 'ini') {
        let novo = imã(o.pos + dt, c, a.pts) - o.pos;
        novo = clamp(novo, -o.ini, o.dur - 0.02);
        c.pos = o.pos + novo; c.ini = o.ini + novo; c.dur = o.dur - novo; c.fi = Math.min(c.fi, c.dur);
      } else if (a.tipo === 'fim') {
        let fim = imã(o.pos + o.dur + dt, c, a.pts);
        c.dur = clamp(fim - o.pos, 0.02, (fonte ? fonte.duracao : o.ini + o.dur) - o.ini); c.fo = Math.min(c.fo, c.dur);
      } else if (a.tipo === 'fi') c.fi = clamp(o.fi + dt, 0, c.dur - (c.fo || 0));
      else if (a.tipo === 'fo') c.fo = clamp(o.fo - dt, 0, c.dur - (c.fi || 0));
      redesenhar(true);
    }
  });
  function soltarArrasto() {
    const a = arr; arr = null;
    if (!a) return;
    if (a.tipo === 'regua') { if (!a.moveu || !S.sel.faixa) S.sel.faixa = S.sel.faixa && a.moveu ? S.sel.faixa : null; desenharInspetor(); redesenhar(true); }
    else if (a.tipo === 'faixa') {
      if (!a.moveu || !S.sel.faixa || S.sel.faixa[1] - S.sel.faixa[0] < 0.01) { S.sel.faixa = null; Toca.buscar(a.t0); }
      else S.sel.clipe = null;     // selecionou um trecho: o inspetor mostra o trecho
      desenharInspetor(); redesenhar(true);
    }
    else if (a.tipo === 'marcador') { confirmar(); desenharInspetor(); }
    else if (a.tipo === 'env') confirmar();
    else if (a.c && a.moveu) confirmar();
    else if (a.c && !a.moveu) Toca.buscar(Math.max(0, a.t0));   // clique simples num clipe: a agulha vai até ali
  }
  wrap.addEventListener('pointerup', soltarArrasto);
  wrap.addEventListener('pointercancel', soltarArrasto);
  wrap.addEventListener('dblclick', (e) => {
    const r = tela.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top;
    if (y < REGUA) {
      const mk = S.proj.marcadores.find((m) => Math.abs(tx(m.t) - x) < 6);
      if (mk) { const n = prompt('Nome do marcador:', mk.nome || ''); if (n != null) { mk.nome = n.slice(0, 60); confirmar(); } return; }
      const rg = S.proj.regioes.find((g2) => x >= tx(g2.ini) && x <= tx(g2.fim));
      if (rg) { const n = prompt('Nome da região:', rg.nome || ''); if (n != null) { rg.nome = n.slice(0, 60) || rg.nome; confirmar(); } }
    }
  });
  function cursor(x, y) {
    let c = 'default';
    if (y < REGUA) c = 'pointer';
    else if (S.ferramenta === 'navalha') c = 'crosshair';
    else if (S.ferramenta === 'envelope') c = 'cell';
    else {
      const hit = clipeEm(x, y);
      if (hit) {
        const x0 = tx(hit.c.pos), x1 = tx(hit.c.pos + hit.c.dur), yi = REGUA + hit.i * ALT + 4;
        c = (x - x0 < 7 || x1 - x < 7) ? 'ew-resize' : y <= yi + 13 ? 'grab' : 'text';
      } else c = 'text';
      if (etiquetas.some((q) => x >= q.xa && x <= q.xb && y >= q.y1 - 10 && y <= q.y1)) c = 'pointer';
    }
    wrap.style.cursor = c;
  }
  wrap.addEventListener('wheel', (e) => {
    if (!S.proj) return;
    e.preventDefault();
    const r = tela.getBoundingClientRect(); const x = e.clientX - r.left;
    if (e.ctrlKey || e.metaKey) { zoomEm(e.deltaY < 0 ? 1.2 : 1 / 1.2, x); return; }
    const d = (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY);
    rolarPara(S.scroll + d / S.zoom);
  }, { passive: false });

  // zoom e rolagem
  const ZMIN = 0.02, ZMAX = 48000;
  function zoomSlider() { $('#zoom').value = Math.round(1000 * Math.log(S.zoom / ZMIN) / Math.log(ZMAX / ZMIN)); }
  function zoomEm(f, x = W / 2) {
    const t = xt(x);
    S.zoom = clamp(S.zoom * f, ZMIN, ZMAX);
    S.scroll = Math.max(0, t - x / S.zoom);
    zoomSlider(); atualizarRolagem(); redesenhar(true);
  }
  $('#zoom').addEventListener('input', () => { const v = +$('#zoom').value / 1000; const x = tx(S.agulha) >= 0 && tx(S.agulha) <= W ? tx(S.agulha) : W / 2; const t = xt(x); S.zoom = ZMIN * Math.pow(ZMAX / ZMIN, v); S.scroll = Math.max(0, t - x / S.zoom); atualizarRolagem(); redesenhar(true); });
  $('#zMais').addEventListener('click', () => zoomEm(1.6, tx(S.agulha)));
  $('#zMenos').addEventListener('click', () => zoomEm(1 / 1.6, tx(S.agulha)));
  $('#zCaber').addEventListener('click', caber);
  function caber() { const d = Math.max(5, duracao() * 1.03); S.zoom = clamp(W / d, ZMIN, ZMAX); S.scroll = 0; zoomSlider(); atualizarRolagem(); redesenhar(true); }
  function rolarPara(s) { S.scroll = clamp(s, 0, Math.max(0, duracao() + 30 - W / S.zoom)); atualizarRolagem(); redesenhar(true); }
  function atualizarRolagem() { const max = Math.max(0.0001, duracao() + 30 - W / S.zoom); $('#rolagem').value = Math.round(1000 * S.scroll / max); $('#rolagem').disabled = max <= 0.001; }
  $('#rolagem').addEventListener('input', () => { const max = Math.max(0, duracao() + 30 - W / S.zoom); S.scroll = max * $('#rolagem').value / 1000; redesenhar(true); });

  // ferramentas
  function ferramenta(v) { S.ferramenta = v; $$('#ferramenta button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === v))); redesenhar(true); }
  $('#ferramenta').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) ferramenta(b.dataset.v); });

  // ======================================================================
  // Ações (teclado e inspetor)
  // ======================================================================
  function clipeSel() { for (const p of S.proj.pistas) for (const c of p.clipes) if (c.id === S.sel.clipe) return { p, c }; return null; }
  const ripple = () => $('#optRipple').checked;
  function apagarSelecao() {
    if (S.sel.marcador) { S.proj.marcadores = S.proj.marcadores.filter((m) => m.id !== S.sel.marcador); S.sel.marcador = null; confirmar(); return; }
    if (S.sel.regiao && !S.sel.faixa) { S.proj.regioes = S.proj.regioes.filter((r) => r.id !== S.sel.regiao); S.sel.regiao = null; confirmar(); return; }
    if (S.sel.faixa) {
      cortarTempo(S.proj, [S.sel.faixa], S.sel.faixaPistas, ripple());
      S.agulha = S.sel.faixa[0]; S.sel.faixa = null; confirmar('Trecho apagado'); return;
    }
    const cs = clipeSel(); if (!cs) return;
    if (ripple()) cortarTempo(S.proj, [[cs.c.pos, cs.c.pos + cs.c.dur]], [cs.p.id], true);
    else cs.p.clipes = cs.p.clipes.filter((c) => c !== cs.c);
    S.sel.clipe = null; confirmar('Clipe apagado');
  }
  function dividirAqui() {
    if (S.sel.faixa) { const ids = S.sel.faixaPistas; dividir(S.proj, S.sel.faixa[0], ids); dividir(S.proj, S.sel.faixa[1], ids); confirmar('Dividido'); return; }
    const ids = S.sel.clipe ? [clipeSel()?.p.id] : null;
    if (dividir(S.proj, S.agulha, ids)) confirmar('Dividido'); else toast('A agulha não está sobre nenhum clipe.');
  }
  function ficarSo() {
    if (!S.sel.faixa) { toast('Selecione um trecho arrastando na linha do tempo.'); return; }
    recortar(S.proj, S.sel.faixa[0], S.sel.faixa[1], 0, 0); S.sel.faixa = null; S.agulha = 0; confirmar('Recortado'); caber();
  }
  function marcar() { S.proj.marcadores.push({ id: uid(), t: S.agulha, nome: '' }); confirmar('Marcador'); }
  function criarRegiao() {
    if (!S.sel.faixa) { toast('Selecione um trecho para virar região.'); return; }
    const n = S.proj.regioes.length + 1;
    S.proj.regioes.push({ id: uid(), ini: S.sel.faixa[0], fim: S.sel.faixa[1], nome: `Região ${n}` }); confirmar('Região criada');
  }
  function duplicar() {
    const cs = clipeSel(); if (!cs) return;
    const n = { ...cs.c, id: uid(), pos: cs.c.pos + cs.c.dur };
    cs.p.clipes.push(n); S.sel.clipe = n.id; confirmar('Duplicado');
  }
  function colar() {
    if (!S.copiado) return;
    const p = S.proj.pistas.find((x) => x.id === S.sel.pista) || S.proj.pistas[0];
    const n = { ...S.copiado, id: uid(), pos: S.agulha }; p.clipes.push(n); S.sel.clipe = n.id; confirmar('Colado');
  }

  document.addEventListener('keydown', (e) => {
    if ($('#editor').hidden || !S.proj) return;
    if (e.target.matches('input, textarea, select') && !(e.target.type === 'range' || e.target.type === 'checkbox')) return;
    const k = e.key.toLowerCase(), ctrl = e.ctrlKey || e.metaKey;
    if (k === ' ') { e.preventDefault(); Toca.alternar(); }
    else if (ctrl && k === 'z') { e.preventDefault(); e.shiftKey ? refazer() : desfazer(); }
    else if (ctrl && k === 'y') { e.preventDefault(); refazer(); }
    else if (ctrl && k === 'c') { const cs = clipeSel(); if (cs) { S.copiado = { ...cs.c }; toast('Clipe copiado.'); } }
    else if (ctrl && k === 'v') { e.preventDefault(); colar(); }
    else if (ctrl && k === 'd') { e.preventDefault(); duplicar(); }
    else if (ctrl && k === 's') { e.preventDefault(); salvar(); }
    else if (ctrl) return;
    else if (k === 'delete' || k === 'backspace') { e.preventDefault(); apagarSelecao(); }
    else if (k === 's') dividirAqui();
    else if (k === 't') ficarSo();
    else if (k === 'm') marcar();
    else if (k === 'r') criarRegiao();
    else if (k === 'l') { S.laco = !S.laco; toast(S.laco ? 'Laço ligado: toca a seleção repetindo.' : 'Laço desligado.'); }
    else if (k === 'v') ferramenta('selecionar');
    else if (k === 'c') ferramenta('navalha');
    else if (k === 'e') ferramenta('envelope');
    else if (k === 'home') Toca.buscar(0);
    else if (k === 'end') Toca.buscar(duracao());
    else if (k === 'arrowleft') Toca.buscar(Math.max(0, S.agulha - (e.shiftKey ? 10 : 1)));
    else if (k === 'arrowright') Toca.buscar(S.agulha + (e.shiftKey ? 10 : 1));
    else if (k === 'escape') { S.sel.faixa = null; S.sel.clipe = null; desenharInspetor(); redesenhar(true); }
    else if (k === '+' || k === '=') zoomEm(1.4, tx(S.agulha));
    else if (k === '-') zoomEm(1 / 1.4, tx(S.agulha));
    else return;
  });

  function desenharInspetor() {
    const el = $('#inspetor');
    if (!S.proj) { el.hidden = true; return; }
    const cs = clipeSel();
    if (S.sel.faixa) {
      const [a, b] = S.sel.faixa;
      el.innerHTML = `<b>Trecho ${fmt(a)} – ${fmt(b)}</b><span class="faint">${(b - a).toFixed(3)} s${S.sel.faixaPistas && S.sel.faixaPistas.length < S.proj.pistas.length ? ` · ${S.sel.faixaPistas.length} pista(s)` : ' · todas as pistas'}</span>
        <button class="btn ghost xs" data-a="tocar">▶ Ouvir</button><button class="btn ghost xs" data-a="apagar">Apagar</button>
        <button class="btn ghost xs" data-a="ficar">Ficar só com isso</button><button class="btn ghost xs" data-a="silenciar">Silenciar</button>
        <button class="btn ghost xs" data-a="dividir">Dividir nas bordas</button><button class="btn ghost xs" data-a="regiao">Criar região</button>`;
    } else if (cs) {
      const f = S.fontes[cs.c.fonte] || {};
      el.innerHTML = `<b title="${esc(f.nome)}">${esc((f.nome || '').slice(0, 40))}</b>
        <span class="faint mono">${fmt(cs.c.pos)} · ${cs.c.dur.toFixed(2)} s</span>
        <label>Ganho <input type="range" min="-30" max="18" step="0.5" value="${cs.c.ganho || 0}" data-c="ganho"> <output class="mono">${(cs.c.ganho || 0).toFixed(1)} dB</output></label>
        <label>Fade entrada <input class="num" type="number" min="0" step="0.05" value="${(+cs.c.fi || 0).toFixed(2)}" data-c="fi"> s</label>
        <label>Fade saída <input class="num" type="number" min="0" step="0.05" value="${(+cs.c.fo || 0).toFixed(2)}" data-c="fo"> s</label>
        <button class="btn ghost xs" data-a="dividir">Dividir na agulha</button><button class="btn ghost xs" data-a="duplicar">Duplicar</button>
        <button class="btn ghost xs" data-a="apagar">Apagar</button>
        <button class="btn ghost xs" data-a="isolar" title="Separa a voz com IA (Demucs)">Isolar voz (IA)</button>
        <button class="btn ghost xs" data-a="karaoke" title="Tira a voz com IA (Demucs)">Tirar voz (IA)</button>`;
    } else if (S.sel.marcador) {
      const m = S.proj.marcadores.find((x) => x.id === S.sel.marcador);
      el.innerHTML = m ? `<b>Marcador</b><span class="mono faint">${fmt(m.t)}</span><label>Nome <input type="text" value="${esc(m.nome)}" data-m="nome" style="width:200px"></label><button class="btn ghost xs" data-a="apagar">Apagar</button>` : '';
    } else {
      el.innerHTML = `<span class="faint">Clique num clipe para ajustar ganho e fades; arraste no vazio para selecionar um trecho; <kbd>S</kbd> divide, <kbd>Delete</kbd> apaga, <kbd>?</kbd> mostra todos os atalhos.</span>`;
    }
    el.hidden = false;
  }
  $('#inspetor').addEventListener('input', (e) => {
    const cs = clipeSel(); const k = e.target.dataset.c;
    if (cs && k) { cs.c[k] = Math.max(k === 'ganho' ? -30 : 0, +e.target.value || 0); if (k === 'ganho') e.target.nextElementSibling.textContent = `${cs.c.ganho.toFixed(1)} dB`; redesenhar(true); }
    if (e.target.dataset.m === 'nome') { const m = S.proj.marcadores.find((x) => x.id === S.sel.marcador); if (m) m.nome = e.target.value.slice(0, 60); }
  });
  $('#inspetor').addEventListener('change', (e) => { if (e.target.dataset.c || e.target.dataset.m) confirmar(); });
  $('#inspetor').addEventListener('click', (e) => {
    const a = e.target.closest('[data-a]')?.dataset.a; if (!a) return;
    if (a === 'apagar') apagarSelecao();
    else if (a === 'dividir') dividirAqui();
    else if (a === 'duplicar') duplicar();
    else if (a === 'ficar') ficarSo();
    else if (a === 'regiao') criarRegiao();
    else if (a === 'tocar') { Toca.tocarTrecho(S.proj, S.sel.faixa[0], S.sel.faixa[1]); }
    else if (a === 'silenciar') {
      const [x, y] = S.sel.faixa; const ids = S.sel.faixaPistas;
      dividir(S.proj, x, ids); dividir(S.proj, y, ids);
      for (const p of S.proj.pistas) { if (ids && !ids.includes(p.id)) continue; for (const c of p.clipes) if (c.pos >= x - 1e-4 && c.pos + c.dur <= y + 1e-4) c.ganho = -60; }
      confirmar('Silenciado');
    } else if (a === 'isolar' || a === 'karaoke') {
      const cs = clipeSel(); if (!cs) return;
      json(`${API}/projeto/${S.proj.id}/separar`, { fonte: cs.c.fonte, parte: a === 'isolar' ? 'vocals' : 'no_vocals' })
        .then(() => { toast('Na fila: a IA leva alguns minutos (aba Fila).'); abrirAba('fila'); Fila.atualizar(); })
        .catch((err) => toast(err.message, true));
    }
  });

  // ======================================================================
  // Reprodução (Web Audio, janelas de 20 s)
  // ======================================================================
  const Toca = (() => {
    const JAN = 20;
    let ctx = null, entrada = null, saida = null, cadeia = [], pistasNos = {};
    const cache = new Map();
    let sessao = null;
    function garantir() {
      if (ctx) return;
      ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000, latencyHint: 'interactive' });
      entrada = ctx.createGain(); saida = ctx.createGain(); saida.connect(ctx.destination);
      montarCadeia();
    }
    function janela(fid, k) {
      const chave = `${S.proj.id}:${fid}:${k}`;
      if (cache.has(chave)) { const v = cache.get(chave); cache.delete(chave); cache.set(chave, v); return v; }
      const p = fetch(`${API}/projeto/${S.proj.id}/fonte/${fid}/janela?ini=${k * JAN}&dur=${JAN + 0.05}`)
        .then((r) => { if (!r.ok) throw new Error('janela'); return r.arrayBuffer(); })
        .then((b) => ctx.decodeAudioData(b))
        .catch(() => { cache.delete(chave); return null; });
      cache.set(chave, p);
      while (cache.size > 36) cache.delete(cache.keys().next().value);
      return p;
    }
    // efeitos com prévia: o mesmo catálogo, aproximado com nós do Web Audio
    function nosEfeito(item) {
      const p = item.p || {};
      const bq = (type, f, gain = 0, Q = 0.9) => { const n = ctx.createBiquadFilter(); n.type = type; n.frequency.value = f; n.gain.value = gain; n.Q.value = Q; return n; };
      switch (item.ef) {
        case 'ganho': { const n = ctx.createGain(); n.gain.value = lin(p.db || 0); return [n]; }
        case 'passa_alta': return [bq('highpass', p.freq || 80, 0, 0.707)];
        case 'passa_baixa': return [bq('lowpass', p.freq || 12000, 0, 0.707)];
        case 'eq': return [bq('lowshelf', 100, p.graves || 0), bq('peaking', 1000, p.medios || 0, 1), bq('peaking', 3500, p.presenca || 0, 1.2), bq('highshelf', 10000, p.agudos || 0)];
        case 'eq_preset': {
          const P = { voz: [bq('highpass', 80, 0, 0.7), bq('peaking', 250, -2.5, 1.1), bq('peaking', 3200, 3, 1.2), bq('highshelf', 10000, 2)],
            radio: [bq('highpass', 110, 0, 0.7), bq('lowshelf', 140, 3), bq('peaking', 2500, 4, 1)], telefone: [bq('highpass', 320, 0, 0.7), bq('lowpass', 3300, 0, 0.7), bq('peaking', 1500, 4, 1)],
            graves: [bq('lowshelf', 110, 6)], brilho: [bq('highshelf', 7000, 5)], abafado: [bq('peaking', 400, -4, 1), bq('peaking', 4000, 2.5, 1.4)],
            zumbido60: [60, 120, 180, 240, 300].map((f) => bq('notch', f, 0, 30)), zumbido50: [50, 100, 150, 200, 250].map((f) => bq('notch', f, 0, 30)) };
          return P[p.preset] || P.voz;
        }
        case 'compressor': { const n = ctx.createDynamicsCompressor(); n.threshold.value = p.limiar ?? -20; n.ratio.value = p.razao ?? 3; n.attack.value = (p.ataque ?? 15) / 1000; n.release.value = (p.liberacao ?? 200) / 1000; n.knee.value = 6; const m = ctx.createGain(); m.gain.value = lin(p.ganho ?? 3); return [n, m]; }
        case 'limitador': { const n = ctx.createDynamicsCompressor(); n.threshold.value = p.teto ?? -1; n.ratio.value = 20; n.attack.value = 0.002; n.release.value = 0.06; n.knee.value = 0; return [n]; }
        case 'mono': { const sp = ctx.createChannelSplitter(2), mg = ctx.createChannelMerger(2), a = ctx.createGain(); a.gain.value = 0.5; sp.connect(a, 0); sp.connect(a, 1); a.connect(mg, 0, 0); a.connect(mg, 0, 1); return [{ entrada: sp, saida: mg }]; }
        default: return [];
      }
    }
    function montarCadeia() {
      if (!ctx) return;
      try { entrada.disconnect(); } catch { /* sem ligações ainda */ }
      cadeia.forEach((n) => { try { (n.saida || n).disconnect(); } catch { /* idem */ } });
      cadeia = [];
      let atual = entrada;
      if (!$('#optBypass').checked) {
        for (const item of S.proj.master || []) {
          if (item.ativo === false) continue;
          for (const n of nosEfeito(item)) { atual.connect(n.entrada || n); atual = n.saida || n; cadeia.push(n); }
        }
      }
      atual.connect(saida);
    }
    function nosPista(p) {
      let n = pistasNos[p.id];
      if (!n) {
        n = { env: ctx.createGain(), vol: ctx.createGain(), pan: ctx.createStereoPanner() };
        n.env.connect(n.vol); n.vol.connect(n.pan); n.pan.connect(entrada);
        pistasNos[p.id] = n;
      }
      return n;
    }
    function atualizarMix() {
      if (!ctx || !S.proj) return;
      const solo = S.proj.pistas.some((p) => p.solo);
      for (const p of S.proj.pistas) {
        const n = nosPista(p);
        const ouvir = !p.mudo && (!solo || p.solo);
        n.vol.gain.setTargetAtTime(ouvir ? lin(p.ganho || 0) : 0, ctx.currentTime, 0.01);
        n.pan.pan.setTargetAtTime(p.pan || 0, ctx.currentTime, 0.01);
      }
    }
    function pecas(proj, t0, t1) {
      const out = [];
      for (const p of proj.pistas) {
        for (const c of p.clipes) {
          const a = Math.max(t0, c.pos), b = Math.min(t1, c.pos + c.dur);
          if (b - a <= 0.001) continue;
          let s = c.ini + (a - c.pos);
          const sFim = c.ini + (b - c.pos);
          while (s < sFim - 1e-6) {
            const k = Math.floor(s / JAN + 1e-9);
            const e = Math.min(sFim, (k + 1) * JAN);
            out.push({ p, c, k, s0: s, s1: e, t: c.pos + (s - c.ini) });
            s = e;
          }
        }
      }
      return out.sort((x, y) => x.t - y.t);
    }
    function agendarEnvelope(proj, t0, c0) {
      for (const p of proj.pistas) {
        const n = nosPista(p); const gp = n.env.gain;
        gp.cancelScheduledValues(0);
        gp.setValueAtTime(lin(envDb(p, t0)), c0);
        for (const [t, db] of p.envelope || []) if (t > t0) gp.linearRampToValueAtTime(lin(db), c0 + (t - t0));
      }
    }
    async function tocar(proj, t0, t1 = Infinity, aoAcabar) {
      garantir();
      await ctx.resume();
      parar(false);
      montarCadeia(); atualizarMix();
      const fim = Math.min(t1, duracao(proj));
      if (t0 >= fim - 0.01) t0 = 0;
      const lista = pecas(proj, t0, fim);
      // carrega o começo antes de soltar o som (sem buraco nos primeiros segundos)
      await Promise.all(lista.filter((q) => q.t < t0 + 2).map((q) => janela(q.c.fonte, q.k)));
      const c0 = ctx.currentTime + 0.06;
      const s = { proj, t0, fim, c0, lista, i: 0, fontes: [], timer: null, aoAcabar };
      sessao = s;
      agendarEnvelope(proj, t0, c0);
      const passo = async () => {
        if (sessao !== s) return;
        const agora = s.t0 + (ctx.currentTime - s.c0);
        while (s.i < s.lista.length && s.lista[s.i].t < agora + 2.5) {
          const q = s.lista[s.i++];
          janela(q.c.fonte, q.k + 1);     // pré-carrega a próxima janela
          const buf = await janela(q.c.fonte, q.k);
          if (sessao !== s || !buf) continue;
          let quando = s.c0 + (q.t - s.t0), off = q.s0 - q.k * JAN, dur = q.s1 - q.s0;
          const atraso = ctx.currentTime + 0.01 - quando;
          if (atraso > 0) { quando += atraso; off += atraso; dur -= atraso; if (dur <= 0.005) continue; }
          const src = ctx.createBufferSource(); src.buffer = buf;
          const gn = ctx.createGain();
          const tc0 = q.s0 - q.c.ini + (q.s0 - q.k * JAN === off ? 0 : off - (q.s0 - q.k * JAN));
          const gc = lin(q.c.ganho || 0);
          const pts = [tc0, Math.max(q.c.fi, MICRO), q.c.dur - Math.max(q.c.fo, MICRO), tc0 + dur].filter((v) => v >= tc0 && v <= tc0 + dur).sort((a, b) => a - b);
          gn.gain.setValueAtTime(ganhoEm(q.c, tc0) * gc, quando);
          for (const v of pts) gn.gain.linearRampToValueAtTime(ganhoEm(q.c, v) * gc, quando + (v - tc0));
          src.connect(gn); gn.connect(nosPista(q.p).env);
          src.start(quando, Math.max(0, off), Math.max(0.001, dur));
          s.fontes.push(src);
          src.onended = () => { const i = s.fontes.indexOf(src); if (i >= 0) s.fontes.splice(i, 1); };
        }
        if (agora >= s.fim) {
          if (S.laco && S.sel.faixa && proj === S.proj) { tocar(proj, S.sel.faixa[0], S.sel.faixa[1]); return; }
          parar(true); if (s.aoAcabar) s.aoAcabar(); return;
        }
        s.timer = setTimeout(passo, 100);
      };
      passo();
      document.body.classList.add('tocando');
      loop();
    }
    function parar(manterAgulha = true) {
      if (!sessao) return;
      const s = sessao; sessao = null;
      clearTimeout(s.timer);
      for (const f of s.fontes) { try { f.stop(); } catch { /* já parou */ } }
      if (manterAgulha && s.proj === S.proj && ctx) S.agulha = Math.min(s.fim, s.t0 + (ctx.currentTime - s.c0));
      document.body.classList.remove('tocando');
      redesenhar();
    }
    function posicao() { return sessao && ctx ? sessao.t0 + (ctx.currentTime - sessao.c0) : S.agulha; }
    function loop() {
      if (!sessao) return;
      if (sessao.proj === S.proj) {
        const t = posicao();
        if (t >= 0) {
          S.agulha = Math.min(t, sessao.fim);
          if ($('#optSeguir').checked && !arr && (tx(S.agulha) > W - 40 || tx(S.agulha) < 0)) rolarPara(S.agulha - 30 / S.zoom);
          redesenhar(); Texto.realcar();
        }
      }
      requestAnimationFrame(loop);
    }
    return {
      get ativo() { return !!sessao; },
      alternar() { if (sessao) parar(true); else if (S.proj) tocar(S.proj, S.sel.faixa && S.laco ? S.sel.faixa[0] : S.agulha, S.sel.faixa && S.laco ? S.sel.faixa[1] : Infinity); },
      buscar(t) { S.agulha = Math.max(0, t); if (sessao && sessao.proj === S.proj) tocar(S.proj, S.agulha); else redesenhar(); Texto.realcar(); },
      reiniciar() { if (sessao && sessao.proj === S.proj) tocar(S.proj, posicao()); },
      tocarTrecho(proj, a, b, aoAcabar) { tocar(proj, Math.max(0, a), b, aoAcabar); },
      parar, atualizarMix() { if (ctx) atualizarMix(); }, montarCadeia() { if (ctx) montarCadeia(); },
      async tocarWav(buf) { garantir(); await ctx.resume(); parar(false); const b = await ctx.decodeAudioData(buf); const src = ctx.createBufferSource(); src.buffer = b; src.connect(ctx.destination); src.start(); return src; },
    };
  })();
  $('#tPlay').addEventListener('click', () => Toca.alternar());
  $('#tInicio').addEventListener('click', () => Toca.buscar(0));
  $('#tFim').addEventListener('click', () => Toca.buscar(duracao()));
  $('#optBypass').addEventListener('change', () => Toca.montarCadeia());
  function atualizarRelogio() { $('#tAgora').textContent = fmt(S.agulha); $('#tTotal').textContent = `/ ${fmt(duracao(), false)}`; }

  // ======================================================================
  // Importar
  // ======================================================================
  let destinoImport = { modo: 'fim' };
  $('#btnImportar').addEventListener('click', (e) => { e.stopPropagation(); const p = $('#popImportar'); p.hidden = !p.hidden; $('#btnImportar').setAttribute('aria-expanded', String(!p.hidden)); });
  document.addEventListener('click', () => { $('#popImportar').hidden = true; });
  $('#popImportar').addEventListener('click', (e) => { const b = e.target.closest('[data-imp]'); if (!b) return; destinoImport = { modo: b.dataset.imp }; $('#arqImportar').click(); });
  $('#arqImportar').addEventListener('change', (e) => { importar([...e.target.files], destinoImport); e.target.value = ''; });
  async function importar(arquivos, destino) {
    if (!arquivos.length || !S.proj) return;
    await salvar();
    const fd = new FormData(); arquivos.forEach((f) => fd.append('file', f));
    if (destino.modo === 'fim' || destino.modo === 'pista') { fd.append('pista', destino.pista || S.sel.pista || ''); }
    else { fd.append('nova', '1'); fd.append('tipo', destino.modo); }
    $('#salvo').textContent = `Enviando ${arquivos.length} arquivo(s)…`;
    try {
      await api(`${API}/projeto/${S.proj.id}/importar`, { method: 'POST', body: fd });
      toast('Importado. Preparando a onda…');
      await recarregarProjeto(true); caber(); Fila.atualizar();
    } catch (err) { toast(err.message, true); $('#salvo').textContent = 'Salvo'; }
  }
  ['dragenter', 'dragover'].forEach((ev) => wrap.addEventListener(ev, (e) => { if (e.dataTransfer?.types?.includes('Files')) { e.preventDefault(); wrap.style.boxShadow = 'inset 0 0 0 2px var(--acc)'; } }));
  ['dragleave', 'drop'].forEach((ev) => wrap.addEventListener(ev, () => { wrap.style.boxShadow = ''; }));
  wrap.addEventListener('drop', (e) => {
    e.preventDefault();
    const fs = [...e.dataTransfer.files]; if (!fs.length) return;
    const r = tela.getBoundingClientRect(); const i = pistaEm(e.clientY - r.top);
    importar(fs, i >= 0 ? { modo: 'pista', pista: S.proj.pistas[i].id } : { modo: 'voz' });
  });

  // ======================================================================
  // Painéis
  // ======================================================================
  function painelAtual() { return $('.abas [aria-selected="true"]')?.dataset.aba; }
  function abrirAba(nome) {
    $$('.abas button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.aba === nome)));
    $$('.aba').forEach((a) => { a.hidden = a.id !== `aba-${nome}`; });
    renderPainel();
  }
  $('.abas').addEventListener('click', (e) => { const b = e.target.closest('[data-aba]'); if (b) abrirAba(b.dataset.aba); });
  function renderPainel() {
    const a = painelAtual();
    if (a === 'sugestoes') desenharSugestoes();
    else if (a === 'receitas') desenharReceitas();
    else if (a === 'texto') Texto.desenhar();
    else if (a === 'efeitos') desenharEfeitos();
    else if (a === 'exportar') desenharExportar();
    else if (a === 'fila') Fila.desenhar($('#aba-fila'), S.proj?.id);
  }
  function fontesDoProjeto() { const out = []; for (const p of S.proj.pistas) for (const c of p.clipes) if (!out.includes(c.fonte)) out.push(c.fonte); return out; }
  function tarefasPendentes(tipos) { return S.tarefas.filter((t) => t.projeto === S.proj?.id && (!tipos || tipos.includes(t.tipo)) && ['esperando', 'rodando', 'pausada'].includes(t.estado)); }

  // ---------------- Sugestões ----------------
  function aplicarSugestao(s, proj = S.proj) {
    if (s.acao === 'cortar') cortarFonte(proj, s.fonte, [[s.ini, s.fim]], true);
    else if (s.acao === 'encurtar') cortarFonte(proj, s.fonte, encurtarTrechos([[s.ini, s.fim]], s.manter ?? 0.45), true);
    else if (s.acao === 'reduzir') reduzirTrechos(proj, s.fonte, [[s.ini, s.fim, s.db ?? -15]]);
    else if (s.acao === 'efeito' && s.efeito) { if (!proj.master.some((m) => m.ef === s.efeito.ef)) proj.master.unshift({ id: uid(), ef: s.efeito.ef, ativo: true, p: { ...(s.efeito.p || {}) } }); }
    else if (s.acao === 'trecho') { const a = fonteParaProjeto(s.fonte, s.ini, proj); if (a != null) recortar(proj, a, a + (s.fim - s.ini)); }
  }
  function aceitar(ids) {
    const lista = sugestoesAbertas().filter((s) => ids.includes(s.id));
    // cortes da mesma fonte de uma vez (mais rápido e sem erro de posição)
    const porFonte = {};
    for (const s of lista) {
      if (s.acao === 'cortar') (porFonte[s.fonte] = porFonte[s.fonte] || []).push([s.ini, s.fim]);
      else if (s.acao === 'encurtar') (porFonte[s.fonte] = porFonte[s.fonte] || []).push(...encurtarTrechos([[s.ini, s.fim]], s.manter ?? 0.45));
      else aplicarSugestao(s);
      S.proj.sug_estado[s.id] = 'aceita';
    }
    for (const [fid, cs] of Object.entries(porFonte)) cortarFonte(S.proj, fid, cs, true);
    confirmar(lista.length > 1 ? `${lista.length} sugestões aceitas` : 'Sugestão aceita');
  }
  function recusar(ids) { ids.forEach((id) => { S.proj.sug_estado[id] = 'recusada'; }); confirmar(); }
  function focarSugestao(id) {
    S.sel.sug = id; abrirAba('sugestoes');
    const s = sugestoesAbertas().find((x) => x.id === id); if (!s) return;
    const t = fonteParaProjeto(s.fonte, s.ini); if (t != null) { S.agulha = t; if (tx(t) < 0 || tx(t) > W) rolarPara(t - 2); }
    redesenhar(true);
    requestAnimationFrame(() => { const el = $(`.sug[data-id="${CSS.escape(id)}"]`); if (el) { el.closest('details').open = true; el.scrollIntoView({ block: 'nearest' }); } });
  }
  function ouvirSugestao(s, depois) {
    const a = fonteParaProjeto(s.fonte, s.ini); if (a == null) return;
    const b = fonteParaProjeto(s.fonte, Math.min(s.fim, s.ini + 30)) ?? a + (s.fim - s.ini);
    if (!depois) { Toca.tocarTrecho(S.proj, a - 1.5, b + 1.5); return; }
    const copia = JSON.parse(JSON.stringify({ pistas: S.proj.pistas, marcadores: S.proj.marcadores, regioes: S.proj.regioes, master: S.proj.master }));
    aplicarSugestao(s, copia);
    Toca.tocarTrecho(copia, Math.max(0, a - 1.5), a + 1.5 + (s.acao === 'reduzir' ? (s.fim - s.ini) : 0.6));
  }
  function desenharSugestoes() {
    const el = $('#aba-sugestoes'); if (!S.proj) return;
    const fontes = fontesDoProjeto();
    const pend = tarefasPendentes(['analisar', 'transcrever']);
    const temTr = fontes.some((f) => S.fontes[f]?.transcrita);
    const abertas = sugestoesAbertas();
    const nomes = S.catalogo?.categorias || {};
    const grupos = {};
    for (const s of abertas) (grupos[s.cat] = grupos[s.cat] || []).push(s);
    const analisadas = fontes.filter((f) => S.sug.fontes?.[f]);
    el.innerHTML = `
      <div class="campo"><div class="rot">Analisar ${fontes.length > 1 ? `os ${fontes.length} arquivos` : 'o áudio'}</div>
        <label class="chk"><input type="checkbox" id="anFala" ${temTr ? 'checked disabled' : 'checked'}> Incluir a fala (vícios, frases refeitas, respirações)${temTr ? ' · já transcrito' : ''}</label>
        <div class="grade2" style="margin-top:6px">
          <label class="faint" style="font-size:12px">Reconhecimento<select id="anModelo"><option value="base">Rápido (base)</option><option value="small">Preciso (small, ~3× mais lento)</option></select></label>
          <label class="faint" style="font-size:12px">É música?<select id="anMusica"><option value="">Descobrir sozinho</option><option value="1">Sim (batidas e refrão)</option><option value="0">Não</option></select></label>
          <label class="faint" style="font-size:12px">Pausa a partir de<select id="anPausa"><option value="0.6">0,6 s</option><option value="0.9" selected>0,9 s</option><option value="1.5">1,5 s</option><option value="2.5">2,5 s</option></select></label>
          <label class="faint" style="font-size:12px">Deixar a pausa com<select id="anManter"><option value="0.25">0,25 s</option><option value="0.45" selected>0,45 s</option><option value="0.7">0,7 s</option></select></label>
        </div>
        <button class="btn full" id="btnAnalisar" style="margin-top:8px" ${pend.length ? 'disabled' : ''}>${pend.length ? `Analisando… (${pend.length} na fila)` : analisadas.length ? 'Analisar de novo' : 'Analisar'}</button>
        <p class="nota">A transcrição roda na sua máquina (faster-whisper): 10 min de fala levam ~2 min no modo rápido.</p>
      </div>
      ${abertas.length ? `<div class="linha" style="justify-content:space-between;margin:12px 0 8px"><b style="font-size:13px">${abertas.length} sugestão(ões)</b>
        <button class="btn sm" id="aceitarRecomendadas" title="Aceita todas as categorias marcadas como seguras">Aceitar as recomendadas</button></div>` : analisadas.length ? '<p class="nota">Nada para sugerir agora. 🎉</p>' : ''}
      ${Object.entries(grupos).map(([cat, ss]) => `
        <details class="grupo-sug"${ss.some((s) => s.id === S.sel.sug) ? ' open' : ''}>
          <summary><i style="background:${COR_CAT[cat]}"></i>${esc(nomes[cat] || cat)} <span class="n">${ss.length}</span><span class="espaco"></span>
            <button class="btn ghost xs" data-todas="${cat}">Aceitar todas</button><button class="btn ghost xs" data-ignorar="${cat}" title="Recusar todas desta categoria">✕</button></summary>
          ${ss.slice(0, 400).map((s) => {
            const t = fonteParaProjeto(s.fonte, s.ini);
            return `<div class="sug${s.id === S.sel.sug ? ' foco' : ''}" data-id="${esc(s.id)}">
              <span class="t" data-ir="${esc(s.id)}" title="Ir até lá">${t != null ? fmtCurto(t) : '–'}</span>
              <span class="txt">${s.texto ? `<q>${esc(s.texto.slice(0, 90))}</q>` : ''}<small>${esc(s.motivo)}</small></span>
              <span class="bts">${s.acao !== 'efeito' ? `<button class="btn ghost" data-ouvir="${esc(s.id)}" title="Ouvir como está">▶</button>${s.acao !== 'trecho' ? `<button class="btn ghost" data-depois="${esc(s.id)}" title="Ouvir como fica">▶✂</button>` : ''}` : ''}
                <button class="btn" data-aceitar="${esc(s.id)}">${s.acao === 'trecho' ? 'Usar' : s.acao === 'efeito' ? 'Aplicar' : 'Aceitar'}</button><button class="btn ghost" data-recusar="${esc(s.id)}" aria-label="Recusar">✕</button></span>
            </div>`;
          }).join('')}${ss.length > 400 ? `<p class="nota" style="padding:0 10px 8px">+${ss.length - 400} (aceite as primeiras para ver o resto)</p>` : ''}
        </details>`).join('')}
      ${analisadas.some((f) => S.sug.fontes[f].bpm) ? `<p class="nota">Música: ${analisadas.filter((f) => S.sug.fontes[f].bpm).map((f) => `${Math.round(S.sug.fontes[f].bpm)} BPM`).join(', ')}. As batidas aparecem na régua e o imã encaixa nelas.</p>` : ''}`;
  }
  $('#aba-sugestoes').addEventListener('click', async (e) => {
    const b = e.target.closest('button, [data-ir]'); if (!b) return;
    if (b.closest('summary')) e.preventDefault();
    const d = b.dataset;
    const achar = (id) => sugestoesAbertas().find((s) => s.id === id);
    if (b.id === 'btnAnalisar') {
      await salvar();
      try {
        const mus = $('#anMusica').value;
        await json(`${API}/projeto/${S.proj.id}/analisar`, { transcrever: $('#anFala').checked, modelo: $('#anModelo').value,
          musica: mus === '' ? null : mus === '1', pausa_min: +$('#anPausa').value, pausa_manter: +$('#anManter').value });
        toast('Na fila. As sugestões aparecem aqui quando terminar.'); Fila.atualizar();
      } catch (err) { toast(err.message, true); }
    } else if (b.id === 'aceitarRecomendadas') aceitar(sugestoesAbertas().filter((s) => s.padrao).map((s) => s.id));
    else if (d.todas) aceitar(sugestoesAbertas().filter((s) => s.cat === d.todas).map((s) => s.id));
    else if (d.ignorar) recusar(sugestoesAbertas().filter((s) => s.cat === d.ignorar).map((s) => s.id));
    else if (d.aceitar) { const s = achar(d.aceitar); if (s) { if (s.acao === 'trecho') { aplicarSugestao(s); S.proj.sug_estado[s.id] = 'aceita'; confirmar('Trecho escolhido'); caber(); } else aceitar([s.id]); } }
    else if (d.recusar) recusar([d.recusar]);
    else if (d.ouvir) { const s = achar(d.ouvir); if (s) ouvirSugestao(s, false); }
    else if (d.depois) { const s = achar(d.depois); if (s) ouvirSugestao(s, true); }
    else if (d.ir) focarSugestao(d.ir);
  });

  // ---------------- Receitas ----------------
  function desenharReceitas() {
    const el = $('#aba-receitas'); const rs = S.catalogo?.receitas || [];
    el.innerHTML = `<p class="nota" style="margin-top:0">Uma receita faz a edição inteira de uma vez: analisa, corta o que precisa, monta os efeitos e a loudness. Dá para desfazer (<kbd>Ctrl</kbd>+<kbd>Z</kbd>) e ajustar depois.</p>
      ${rs.map((r) => `<div class="receita"><b>${esc(r.nome)}${r.fala ? '<span class="etq">transcreve</span>' : ''}${r.ia ? '<span class="etq">IA</span>' : ''}</b>
        <p>${esc(r.desc)}</p><button class="btn sm" data-receita="${r.id}">Aplicar</button></div>`).join('')}
      <div class="campo" style="margin-top:10px"><label for="recModelo">Reconhecimento da fala</label><select id="recModelo"><option value="base">Rápido (base)</option><option value="small">Preciso (small)</option></select></div>`;
  }
  $('#aba-receitas').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-receita]'); if (!b) return;
    await salvar();
    try {
      const d = await json(`${API}/projeto/${S.proj.id}/receita`, { receita: b.dataset.receita, modelo: $('#recModelo').value });
      toast(`Na fila (${d.tarefas.length} etapa(s)). O projeto se atualiza sozinho quando terminar.`); abrirAba('fila'); Fila.atualizar();
    } catch (err) { toast(err.message, true); }
  });

  // ---------------- Texto ----------------
  const Texto = (() => {
    let mapa = [];    // palavras em ordem: {fid, i, w, el}
    let ultimo = null;
    function vicios() {
      const s = new Set();
      for (const info of Object.values(S.sug.fontes || {})) for (const x of info.sugestoes || []) if (x.cat === 'vicio' || x.cat === 'muleta') s.add(`${x.fonte}:${x.ini}`);
      return s;
    }
    function desenhar() {
      const el = $('#aba-texto'); if (!S.proj) return;
      const fontes = fontesDoProjeto();
      const transcritas = fontes.filter((f) => S.transcr[f]);
      const pend = tarefasPendentes(['transcrever']);
      if (!transcritas.length) {
        el.innerHTML = `<p class="nota" style="margin-top:0">Transcreva para editar pelo texto: apagar palavras apaga o áudio delas (como no Descript). Também sai a legenda (SRT/VTT).</p>
          <div class="campo"><label for="trModelo">Reconhecimento</label><select id="trModelo"><option value="base">Rápido (base)</option><option value="small">Preciso (small)</option></select></div>
          <button class="btn full" id="btnTranscrever" ${pend.length || !fontes.length ? 'disabled' : ''}>${pend.length ? 'Transcrevendo… (aba Fila)' : 'Transcrever'}</button>`;
        return;
      }
      const vic = vicios();
      mapa = [];
      let html = `<input type="search" class="texto-busca" id="buscaTexto" placeholder="Buscar no texto…" aria-label="Buscar no texto">
        <div class="linha" style="margin-bottom:8px;gap:6px"><a class="btn ghost xs" href="${API}/projeto/${S.proj.id}/transcricao.txt">TXT</a><a class="btn ghost xs" href="${API}/projeto/${S.proj.id}/transcricao.srt">SRT</a><a class="btn ghost xs" href="${API}/projeto/${S.proj.id}/transcricao.vtt">VTT</a>
        <label class="chk" style="margin-left:auto"><input type="checkbox" id="mostrarCortadas" checked> mostrar cortadas</label></div><div class="transcricao" id="transcricao">`;
      for (const fid of transcritas) {
        const ws = S.transcr[fid].palavras;
        if (transcritas.length > 1) html += `<h3>${esc(S.fontes[fid]?.nome || '')}</h3>`;
        html += '<p>';
        ws.forEach((w, i) => {
          if (i > 0 && w.ini - ws[i - 1].fim > 1.2) html += '</p><p>';
          const k = mapa.length;
          mapa.push({ fid, i, w });
          html += `<span class="w${vic.has(`${fid}:${Math.round(Math.max(0, w.ini - 0.03) * 1000) / 1000}`) ? ' vicio' : ''}" data-k="${k}">${esc(w.w)}</span> `;
        });
        html += '</p>';
      }
      html += '</div><div class="barra-sel" id="barraSel" hidden></div>';
      el.innerHTML = html;
      mapa.forEach((m, k) => { m.el = el.querySelector(`.w[data-k="${k}"]`); });
      marcarPalavrasCortadas();
    }
    function noProjeto(m) { const meio = (m.w.ini + m.w.fim) / 2; return fonteParaProjeto(m.fid, meio); }
    function marcar() { for (const m of mapa) if (m.el) m.el.classList.toggle('cortada', noProjeto(m) == null); }
    function realcar() {
      if (painelAtual() !== 'texto' || !mapa.length) return;
      let achado = null;
      for (const p of S.proj.pistas) for (const c of p.clipes) {
        if (S.agulha >= c.pos && S.agulha <= c.pos + c.dur) {
          const ts = c.ini + (S.agulha - c.pos);
          const ws = S.transcr[c.fonte]?.palavras; if (!ws) continue;
          let lo = 0, hi = ws.length - 1;
          while (lo <= hi) { const mid = (lo + hi) >> 1; if (ws[mid].fim < ts) lo = mid + 1; else hi = mid - 1; }
          if (ws[lo] && ws[lo].ini <= ts + 0.05) achado = mapa.find((m) => m.fid === c.fonte && m.i === lo);
        }
      }
      if (achado !== ultimo) {
        ultimo?.el?.classList.remove('agora');
        if (achado?.el) { achado.el.classList.add('agora'); if (Toca.ativo) achado.el.scrollIntoView({ block: 'nearest' }); }
        ultimo = achado;
      }
    }
    function selecionadas() {
      const sel = window.getSelection(); if (!sel || sel.isCollapsed) return [];
      const r = sel.getRangeAt(0);
      return mapa.filter((m) => m.el && r.intersectsNode(m.el) && !m.el.classList.contains('cortada'));
    }
    function cortesDe(ms) {
      const out = [];
      const porFonte = {};
      ms.forEach((m) => (porFonte[m.fid] = porFonte[m.fid] || []).push(m));
      for (const [fid, lista] of Object.entries(porFonte)) {
        const ws = S.transcr[fid].palavras;
        lista.sort((a, b) => a.i - b.i);
        let grupo = [lista[0]];
        const fechar = () => {
          const a = grupo[0], b = grupo[grupo.length - 1];
          const prox = ws[b.i + 1];
          const fim = prox ? Math.min(prox.ini - 0.04, b.w.fim + 0.25) : b.w.fim + 0.15;
          out.push([fid, [Math.max(0, a.w.ini - 0.02), Math.max(fim, b.w.fim)]]);
        };
        for (let k = 1; k < lista.length; k++) { if (lista[k].i === grupo[grupo.length - 1].i + 1) grupo.push(lista[k]); else { fechar(); grupo = [lista[k]]; } }
        fechar();
      }
      return out;
    }
    return { desenhar, realcar, marcar, selecionadas, cortesDe };
  })();
  function marcarPalavrasCortadas() { Texto.marcar(); }
  $('#aba-texto').addEventListener('click', async (e) => {
    if (e.target.id === 'btnTranscrever') {
      await salvar();
      try { await json(`${API}/projeto/${S.proj.id}/transcrever`, { modelo: $('#trModelo').value }); toast('Na fila. O texto aparece aqui quando terminar.'); Fila.atualizar(); Texto.desenhar(); }
      catch (err) { toast(err.message, true); }
      return;
    }
    const w = e.target.closest('.w');
    if (w && window.getSelection().isCollapsed) {   // clique numa palavra: a agulha vai até ela
      const item = mapaPalavra(+w.dataset.k);
      if (item) { const tt = fonteParaProjeto(item.fid, item.w.ini); if (tt != null) { Toca.buscar(tt); if (tx(tt) < 0 || tx(tt) > W) rolarPara(tt - 2); } }
    }
    const a = e.target.closest('[data-tx]')?.dataset.tx;
    if (a) {
      const ms = Texto.selecionadas();
      if (!ms.length) return;
      if (a === 'apagar') {
        for (const [fid, c] of Texto.cortesDe(ms)) cortarFonte(S.proj, fid, [c], true);
        window.getSelection().removeAllRanges(); $('#barraSel').hidden = true; confirmar(`${ms.length} palavra(s) apagada(s)`);
      } else if (a === 'ouvir') {
        const t0 = fonteParaProjeto(ms[0].fid, ms[0].w.ini), t1 = fonteParaProjeto(ms[ms.length - 1].fid, ms[ms.length - 1].w.fim);
        if (t0 != null) Toca.tocarTrecho(S.proj, t0 - 0.3, (t1 ?? t0 + 3) + 0.3);
      }
    }
  });
  function mapaPalavra(k) {
    const el = $(`#aba-texto .w[data-k="${k}"]`); if (!el) return null;
    let n = 0;
    for (const fid of fontesDoProjeto().filter((f) => S.transcr[f])) {
      const ws = S.transcr[fid].palavras;
      if (k < n + ws.length) return { fid, i: k - n, w: ws[k - n] };
      n += ws.length;
    }
    return null;
  }
  document.addEventListener('selectionchange', () => {
    const bar = $('#barraSel'); if (!bar || painelAtual() !== 'texto') return;
    const ms = Texto.selecionadas();
    if (!ms.length) { bar.hidden = true; return; }
    bar.innerHTML = `<b style="font-size:12.5px">${ms.length} palavra(s)</b><button class="btn ghost xs" data-tx="ouvir">▶ Ouvir</button><button class="btn xs" data-tx="apagar">Apagar do áudio</button>`;
    bar.hidden = false;
  });
  $('#aba-texto').addEventListener('input', (e) => {
    if (e.target.id === 'mostrarCortadas') { $$('#transcricao .w.cortada').forEach((w) => { w.style.display = e.target.checked ? '' : 'none'; }); }
    if (e.target.id !== 'buscaTexto') return;
    const q = e.target.value.trim().toLowerCase();
    let primeiro = null;
    $$('#transcricao .w').forEach((w) => { const ok = q.length > 1 && w.textContent.toLowerCase().includes(q); w.classList.toggle('achada', ok); if (ok && !primeiro) primeiro = w; });
    primeiro?.scrollIntoView({ block: 'center' });
  });
  $('#aba-texto').addEventListener('change', (e) => { if (e.target.id === 'mostrarCortadas') e.target.dispatchEvent(new Event('input', { bubbles: true })); });

  // ---------------- Efeitos ----------------
  const ALVOS = [[-14, 'Spotify, YouTube, Reels (−14)'], [-16, 'Podcast, Apple (−16)'], [-18, 'Aula, voz (−18)'], [-20, 'Audiobook ACX (−20)'], [-23, 'TV e rádio (−23)']];
  function desenharEfeitos() {
    const el = $('#aba-efeitos'); const cat = S.catalogo?.efeitos || []; const porId = Object.fromEntries(cat.map((e) => [e.id, e]));
    const grupos = {}; cat.forEach((e) => (grupos[e.grupo] = grupos[e.grupo] || []).push(e));
    const lo = S.proj.loudness || {}; const du = S.proj.ducking || {};
    const temMusicaVoz = S.proj.pistas.some((p) => p.tipo === 'musica') && S.proj.pistas.some((p) => p.tipo === 'voz');
    el.innerHTML = `
      <div class="linha" style="justify-content:space-between;margin-bottom:8px"><b style="font-size:13px">Cadeia do master</b>
        <button class="btn ghost xs" id="previaFiel" title="10 s a partir da agulha, renderizados com tudo (inclusive os efeitos sem prévia ao vivo)">▶ Prévia fiel (10 s)</button></div>
      ${(S.proj.master || []).map((m, i) => {
        const e = porId[m.ef]; if (!e) return '';
        return `<div class="efx${m.ativo === false ? ' off' : ''}" data-i="${i}">
          <div class="efx-h"><input type="checkbox" data-on ${m.ativo !== false ? 'checked' : ''} aria-label="Ligar ${esc(e.nome)}"><b>${esc(e.nome)}</b>
            ${e.previa ? '<span class="etq ao-vivo">ao vivo</span>' : '<span class="etq" title="Ouça com a Prévia fiel">no arquivo</span>'}
            <button class="btn ghost xs" data-mv="-1" aria-label="Subir">▲</button><button class="btn ghost xs" data-mv="1" aria-label="Descer">▼</button><button class="btn ghost xs" data-rm aria-label="Tirar">✕</button></div>
          ${e.p.length ? `<div class="efx-b">${e.p.map((p) => p.opcoes
            ? `<div class="param"><span>${esc(p.nome)}</span><select data-p="${p.id}">${p.opcoes.map(([v, n]) => `<option value="${v}"${m.p[p.id] === v ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select><span></span></div>`
            : `<div class="param"><span>${esc(p.nome)}</span><input type="range" min="${p.min}" max="${p.max}" step="${p.passo}" value="${m.p[p.id] ?? p.padrao}" data-p="${p.id}"><output>${m.p[p.id] ?? p.padrao}${p.un ? ` ${p.un}` : ''}</output></div>`).join('')}</div>` : ''}
        </div>`;
      }).join('') || '<p class="nota" style="margin-top:0">Nenhum efeito ainda.</p>'}
      <select id="addEfeito" aria-label="Adicionar efeito"><option value="">+ Adicionar efeito…</option>${Object.entries(grupos).map(([g2, es]) => `<optgroup label="${esc(g2)}">${es.map((e) => `<option value="${e.id}">${esc(e.nome)}</option>`).join('')}</optgroup>`).join('')}</select>
      ${S.catalogo && !S.catalogo.rnnoise ? '<p class="nota">Redução de ruído "Forte" usa o modo FFT reforçado (o modelo RNNoise não está instalado).</p>' : ''}
      <h3>Volume final (loudness)</h3>
      <label class="chk"><input type="checkbox" id="loAtivo" ${lo.ativo ? 'checked' : ''}> Ajustar a loudness no arquivo final</label>
      <div class="grade2" style="margin-top:6px"><select id="loAlvo" aria-label="Alvo">${ALVOS.map(([v, n]) => `<option value="${v}"${+lo.alvo === v ? ' selected' : ''}>${n}</option>`).join('')}${ALVOS.some(([v]) => v === +lo.alvo) ? '' : `<option value="${lo.alvo}" selected>${lo.alvo} LUFS</option>`}</select>
        <label class="faint" style="font-size:12px;display:flex;align-items:center;gap:6px">Pico máx. <input type="number" id="loPico" min="-6" max="0" step="0.5" value="${lo.pico ?? -1}" style="width:70px"> dB</label></div>
      <button class="btn ghost sm" id="medirAgora" style="margin-top:8px">Medir agora</button>
      <div id="medidas"></div>
      <h3>Ducking</h3>
      <label class="chk"><input type="checkbox" id="duAtivo" ${du.ativo ? 'checked' : ''} ${temMusicaVoz ? '' : 'disabled'}> Abaixar a música quando houver voz</label>
      ${temMusicaVoz ? `<div class="param" style="margin-top:6px"><span>Redução</span><input type="range" id="duReducao" min="3" max="30" step="1" value="${du.reducao ?? 12}"><output>${du.reducao ?? 12} dB</output></div>` : '<p class="nota">Precisa de uma pista do tipo Voz e outra do tipo Música (escolha o tipo na cabeça da pista).</p>'}
      <p class="nota">"Ao vivo" toca com o efeito na hora. "No arquivo" entra só na exportação e na Prévia fiel. Marque "Sem efeitos" na barra para comparar.</p>`;
    desenharMedidas();
  }
  function desenharMedidas() {
    const t = S.tarefas.filter((x) => x.projeto === S.proj?.id && x.tipo === 'medir').slice(-1)[0];
    const el = $('#medidas'); if (!el || !t) return;
    if (t.estado !== 'pronta') { el.innerHTML = `<p class="nota">Medindo… ${Math.round(100 * t.progresso)}%</p>`; return; }
    const r = t.resultado || {};
    el.innerHTML = `<div class="medida"><div><b>${r.lufs ?? '–'}</b><span>LUFS integrado</span></div><div><b>${r.true_peak ?? '–'}</b><span>true peak dB</span></div><div><b>${r.lra ?? '–'}</b><span>LRA (LU)</span></div>
      <div><b class="${r.acx?.rms_ok ? 'ok' : 'nao'}">${r.rms != null ? r.rms.toFixed(1) : '–'}</b><span>RMS dB (ACX −23 a −18)</span></div>
      <div><b class="${r.acx?.pico_ok ? 'ok' : 'nao'}">${r.pico != null ? r.pico.toFixed(1) : '–'}</b><span>pico dB (ACX ≤ −3)</span></div>
      <div><b class="${r.acx?.ruido_ok ? 'ok' : 'nao'}">${r.ruido != null ? r.ruido.toFixed(1) : '–'}</b><span>ruído dB (ACX ≤ −60)</span></div></div>`;
  }
  $('#aba-efeitos').addEventListener('change', async (e) => {
    const t = e.target, card = t.closest('.efx');
    if (t.id === 'addEfeito' && t.value) {
      const def = S.catalogo.efeitos.find((x) => x.id === t.value);
      S.proj.master.push({ id: uid(), ef: def.id, ativo: true, p: Object.fromEntries(def.p.map((p) => [p.id, p.padrao])) });
      confirmar(); Toca.montarCadeia(); desenharEfeitos(); return;
    }
    if (card) {
      const m = S.proj.master[+card.dataset.i];
      if (t.matches('[data-on]')) m.ativo = t.checked;
      else if (t.dataset.p) m.p[t.dataset.p] = t.type === 'range' ? +t.value : t.value;
      confirmar(); Toca.montarCadeia(); if (t.matches('[data-on]')) card.classList.toggle('off', !t.checked);
      return;
    }
    if (t.id === 'loAtivo' || t.id === 'loAlvo' || t.id === 'loPico') { S.proj.loudness = { ativo: $('#loAtivo').checked, alvo: +$('#loAlvo').value, pico: +$('#loPico').value }; confirmar(); }
    if (t.id === 'duAtivo' || t.id === 'duReducao') { S.proj.ducking = { ativo: $('#duAtivo').checked, reducao: +($('#duReducao')?.value || 12) }; confirmar(); }
  });
  $('#aba-efeitos').addEventListener('input', (e) => {
    const t = e.target;
    if (t.type === 'range' && t.nextElementSibling?.tagName === 'OUTPUT') { const un = t.nextElementSibling.textContent.replace(/^[-\d.\s]+/, ''); t.nextElementSibling.textContent = `${t.value}${un ? ` ${un}` : ''}`; }
    const card = t.closest('.efx');
    if (card && t.dataset.p && t.type === 'range') { S.proj.master[+card.dataset.i].p[t.dataset.p] = +t.value; Toca.montarCadeia(); }
  });
  $('#aba-efeitos').addEventListener('click', async (e) => {
    const card = e.target.closest('.efx'); const b = e.target.closest('button'); if (!b) return;
    if (card && b.dataset.mv) { const i = +card.dataset.i, j = i + +b.dataset.mv; if (j < 0 || j >= S.proj.master.length) return; [S.proj.master[i], S.proj.master[j]] = [S.proj.master[j], S.proj.master[i]]; confirmar(); Toca.montarCadeia(); desenharEfeitos(); }
    else if (card && b.matches('[data-rm]')) { S.proj.master.splice(+card.dataset.i, 1); confirmar(); Toca.montarCadeia(); desenharEfeitos(); }
    else if (b.id === 'previaFiel') {
      await salvar(); b.disabled = true; b.textContent = 'Renderizando…';
      try {
        const r = await fetch(`${API}/projeto/${S.proj.id}/previa?t=${S.agulha}`);
        if (!r.ok) throw new Error(await r.text());
        const ini = +r.headers.get('X-Inicio') || 0; const src = await Toca.tocarWav(await r.arrayBuffer());
        toast(`Prévia fiel de ${fmtCurto(ini)} a ${fmtCurto(ini + 10)}.`); void src;
      } catch (err) { toast(err.message, true); }
      finally { b.disabled = false; b.textContent = '▶ Prévia fiel (10 s)'; }
    } else if (b.id === 'medirAgora') {
      await salvar();
      try { await json(`${API}/projeto/${S.proj.id}/medir`); toast('Medindo na fila…'); Fila.atualizar(); } catch (err) { toast(err.message, true); }
    }
  });

  // ---------------- Exportar ----------------
  function desenharExportar() {
    const el = $('#aba-exportar'); const pad = S.proj.exportar_padrao || {}; const t = S.proj.tags || {};
    const feitos = S.tarefas.filter((x) => x.projeto === S.proj.id && x.tipo === 'exportar' && x.estado === 'pronta' && x.resultado).reverse();
    el.innerHTML = `
      <div class="grade2">
        <div class="campo"><label for="exFormato">Formato</label><select id="exFormato">${['wav', 'flac', 'mp3', 'm4a', 'ogg', 'opus', 'mp4'].map((f) => `<option value="${f}"${(pad.formato || 'wav') === f ? ' selected' : ''}>${f === 'mp4' ? 'MP4 (vídeo com o áudio novo)' : f.toUpperCase()}</option>`).join('')}</select></div>
        <div class="campo"><label for="exSr">Taxa</label><select id="exSr">${[22050, 32000, 44100, 48000, 96000].map((v) => `<option value="${v}"${(pad.sr || 48000) === v ? ' selected' : ''}>${v / 1000} kHz</option>`).join('')}</select></div>
        <div class="campo" id="exBitsC"><label for="exBits">Bits</label><select id="exBits"><option value="16">16 bits</option><option value="24" selected>24 bits</option><option value="32">32 bits float</option></select></div>
        <div class="campo" id="exKbpsC"><label for="exKbps">Qualidade</label><select id="exKbps">${[64, 96, 128, 160, 192, 256, 320].map((v) => `<option value="${v}"${(pad.kbps || 192) === v ? ' selected' : ''}>${v} kbps</option>`).join('')}</select></div>
        <div class="campo"><label for="exCanais">Canais</label><select id="exCanais"><option value="2">Estéreo</option><option value="1"${pad.canais === 1 ? ' selected' : ''}>Mono</option></select></div>
      </div>
      <div id="exVideoC" hidden>
        <h3>Vídeo</h3>
        ${S.proj.video ? `<div class="linha" style="justify-content:space-between;font-size:12.5px"><span>${esc(S.proj.video.nome)} <span class="faint">${fmtCurto(S.proj.video.duracao)} · ${(S.proj.video.bytes / 1048576).toFixed(1)} MB</span></span><label class="btn ghost xs" for="exVideo">Trocar</label></div>`
          : `<div class="linha"><label class="btn xs" for="exVideo">Enviar o vídeo (MP4)</label><span class="faint" style="font-size:12px">o vídeo de onde veio este áudio</span></div>`}
        <input type="file" id="exVideo" accept="video/*,.mkv,.mov,.mp4,.webm" hidden>
        <div class="grade2" style="margin-top:8px">
          <div class="campo"><label for="exSync">Sincronizar</label><select id="exSync"><option value="auto">Automático (pelo som do vídeo)</option><option value="manual">Atraso manual</option></select></div>
          <div class="campo" id="exAtrasoC" hidden><label for="exAtraso">Atraso do áudio (s)</label><input type="number" id="exAtraso" step="0.01" value="0"></div>
        </div>
        <p class="nota">O som original do vídeo sai e a mixagem entra no lugar. A imagem é copiada sem perda; o arquivo tem a duração do vídeo. Cortes no meio da linha do tempo adiantam o áudio dali em diante.</p>
      </div>
      <div id="exRegioesC"><label class="chk"><input type="checkbox" id="exRegioes" ${S.proj.regioes.length ? '' : 'disabled'}> Cada região num arquivo (${S.proj.regioes.length})</label>
      <label class="chk" style="margin-left:14px"><input type="checkbox" id="exSoRegioes" ${S.proj.regioes.length ? '' : 'disabled'}> só as regiões</label></div>
      <h3>Informações do arquivo</h3>
      <div class="grade2">
        ${[['titulo', 'Título'], ['artista', 'Artista'], ['album', 'Álbum'], ['ano', 'Ano'], ['genero', 'Gênero'], ['comentario', 'Comentário']].map(([k, n]) => `<input type="text" data-tag="${k}" placeholder="${n}" value="${esc(t[k] || '')}" aria-label="${n}">`).join('')}
      </div>
      <div class="linha" style="margin-top:8px"><label class="btn ghost xs" for="exCapa">${S.proj.capa ? 'Trocar a capa' : 'Pôr capa'}</label><input type="file" id="exCapa" accept="image/*" hidden>
        ${S.proj.capa ? `<img src="${API}/projeto/${S.proj.id}/capa?v=${Date.now()}" alt="Capa" width="40" height="40" style="border-radius:6px;object-fit:cover">` : ''}<span class="faint" style="font-size:12px">entra no MP3, M4A e FLAC</span></div>
      <button class="btn full" id="btnExportar" style="margin-top:12px">Exportar</button>
      <p class="nota">A exportação roda na fila (em blocos de 10 min nos áudios longos) e o arquivo aparece aqui.</p>
      ${feitos.length ? `<h3>Prontos</h3>${feitos.map((x) => `<div class="linha" style="justify-content:space-between;font-size:12.5px;padding:4px 0"><span>${esc(x.resultado.nome)} <span class="faint">${(x.resultado.bytes / 1048576).toFixed(1)} MB${x.resultado.atraso != null ? ` · áudio ${x.resultado.atraso >= 0 ? '+' : ''}${x.resultado.atraso.toFixed(2)} s` : ''}</span></span><a class="btn xs" href="${API}/projeto/${S.proj.id}/baixar/${encodeURIComponent(x.resultado.arquivo)}">Baixar</a></div>`).join('')}` : ''}
      <h3>Outros</h3>
      <div class="linha"><a class="btn ghost xs" href="${API}/projeto/${S.proj.id}/transcricao.srt">Legenda SRT</a><a class="btn ghost xs" href="${API}/projeto/${S.proj.id}/transcricao.vtt">VTT</a><a class="btn ghost xs" href="${API}/projeto/${S.proj.id}/transcricao.txt">Texto</a><button class="btn ghost xs" id="exProjeto">Projeto (.json)</button></div>`;
    ajustarCamposExport();
  }
  function ajustarCamposExport() {
    const f = $('#exFormato')?.value; if (!f) return;
    $('#exBitsC').hidden = !['wav', 'flac'].includes(f); $('#exKbpsC').hidden = ['wav', 'flac'].includes(f);
    $$('#exBits option[value="32"]').forEach((o) => { o.disabled = f === 'flac'; });
    // taxas que o formato aceita (MP3, AAC e Vorbis vão até 48 kHz; o Opus é sempre 48 kHz)
    const sel = $('#exSr'); const max = ['wav', 'flac'].includes(f) ? 96000 : 48000;
    $$('#exSr option').forEach((o) => { o.disabled = +o.value > max || (f === 'opus' && +o.value !== 48000); });
    if (sel.selectedOptions[0]?.disabled) sel.value = '48000';
    $('#exVideoC').hidden = f !== 'mp4'; $('#exRegioesC').hidden = f === 'mp4';
    $('#exAtrasoC').hidden = $('#exSync').value !== 'manual';
  }
  $('#aba-exportar').addEventListener('change', async (e) => {
    if (e.target.id === 'exFormato' || e.target.id === 'exSync') ajustarCamposExport();
    if (e.target.id === 'exVideo' && e.target.files[0]) {
      const fd = new FormData(); fd.append('file', e.target.files[0]); toast('Enviando o vídeo…');
      try { const d = await api(`${API}/projeto/${S.proj.id}/video`, { method: 'POST', body: fd }); S.proj.video = d.video; desenharExportar(); $('#exFormato').value = 'mp4'; ajustarCamposExport(); toast('Vídeo guardado.'); } catch (err) { toast(err.message, true); }
    }
    if (e.target.dataset.tag) { S.proj.tags = S.proj.tags || {}; S.proj.tags[e.target.dataset.tag] = e.target.value.slice(0, 200); confirmar(); }
    if (e.target.id === 'exCapa' && e.target.files[0]) {
      const fd = new FormData(); fd.append('file', e.target.files[0]);
      try { await api(`${API}/projeto/${S.proj.id}/capa`, { method: 'POST', body: fd }); S.proj.capa = true; desenharExportar(); toast('Capa salva.'); } catch (err) { toast(err.message, true); }
    }
  });
  $('#aba-exportar').addEventListener('click', async (e) => {
    if (e.target.id === 'btnExportar') {
      await salvar();
      const op = { formato: $('#exFormato').value, sr: +$('#exSr').value, bits: $('#exBits').value, kbps: +$('#exKbps').value, canais: +$('#exCanais').value,
        regioes: $('#exRegioes').checked, so_regioes: $('#exSoRegioes').checked && $('#exRegioes').checked };
      if (op.formato === 'mp4') {
        if (!S.proj.video) { toast('Envie o vídeo primeiro.', true); return; }
        op.sync = $('#exSync').value === 'manual' ? String(+$('#exAtraso').value || 0) : 'auto';
      }
      try { await json(`${API}/projeto/${S.proj.id}/exportar`, op); toast('Exportando na fila…'); Fila.atualizar(); } catch (err) { toast(err.message, true); }
    } else if (e.target.id === 'exProjeto') {
      const blob = new Blob([JSON.stringify(JSON.parse(instantaneo()), null, 1)], { type: 'application/json' });
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${S.proj.nome}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    }
  });

  // ---------------- Fila ----------------
  const Fila = (() => {
    let timer = null;
    const nomesEstado = { esperando: 'na fila', rodando: 'rodando', pausada: 'pausada', pronta: 'pronta', erro: 'erro', cancelada: 'cancelada' };
    function desenhar(el, pid) {
      if (!el) return;
      const ts = S.tarefas.filter((t) => !pid || t.projeto === pid || el.id === 'aba-fila');
      el.innerHTML = (el.id === 'aba-fila' ? `<div class="linha" style="justify-content:space-between;margin-bottom:8px"><span class="faint" style="font-size:12.5px">Uma tarefa por vez, em blocos de 10 min; continua de onde parou se o Verto fechar.</span><button class="btn ghost xs" data-limpar>Limpar prontas</button></div>` : '') +
        (ts.length ? '' : '<p class="nota" style="margin-top:0">Nada na fila.</p>') +
        `<div class="fila">${ts.slice().reverse().map((t) => `
          <div class="tarefa ${t.estado}" data-t="${t.id}">
            <div class="l1"><b title="${esc(t.titulo)}">${esc(t.titulo)}</b><span class="estado ${t.estado}">${nomesEstado[t.estado] || t.estado}</span></div>
            <div class="l2"><span>${esc(t.projeto_nome || '')}${t.projeto_nome ? ' · ' : ''}${esc(t.erro || t.etapa || '')}</span><span>${t.estado === 'rodando' || t.estado === 'esperando' ? `${t.blocos > 1 ? `${t.feitos}/${t.blocos} · ` : ''}${fmtEta(t.eta)}` : ''}</span></div>
            <div class="barra"><div style="width:${Math.round(100 * (t.progresso || 0))}%"></div></div>
            <div class="bts">
              ${['esperando', 'rodando'].includes(t.estado) ? `<button class="btn ghost xs" data-ac="pausar">Pausar</button>` : ''}
              ${['pausada', 'erro', 'cancelada'].includes(t.estado) ? `<button class="btn ghost xs" data-ac="retomar">Retomar</button>` : ''}
              ${['esperando', 'rodando', 'pausada'].includes(t.estado) ? `<button class="btn ghost xs" data-ac="cancelar">Cancelar</button>` : ''}
              ${t.estado === 'esperando' ? `<button class="btn ghost xs" data-ac="subir" aria-label="Subir">▲</button><button class="btn ghost xs" data-ac="descer" aria-label="Descer">▼</button>` : ''}
              ${t.tipo === 'exportar' && t.estado === 'pronta' && t.resultado ? `<a class="btn xs" href="${API}/projeto/${t.projeto}/baixar/${encodeURIComponent(t.resultado.arquivo)}">Baixar ${esc(t.resultado.nome)}</a>` : ''}
              ${(!S.proj || t.projeto !== S.proj.id) && t.estado === 'pronta' ? `<button class="btn ghost xs" data-abrir="${t.projeto}">Abrir projeto</button>` : ''}
              ${t.estado !== 'rodando' ? `<button class="btn ghost xs" data-ac="remover" aria-label="Tirar da lista">✕</button>` : ''}
            </div>
          </div>`).join('')}</div>`;
    }
    let antes = {};
    async function atualizar() {
      clearTimeout(timer);
      try {
        const d = await api(`${API}/fila`);
        S.tarefas = d.tarefas;
      } catch { /* servidor ocupado: tenta de novo */ }
      const ativas = S.tarefas.filter((t) => ['esperando', 'rodando'].includes(t.estado));
      const cont = $('#contFila'); cont.textContent = ativas.length; cont.hidden = !ativas.length;
      // terminou alguma tarefa deste projeto? recarrega o que ela mudou
      if (S.proj) {
        let recarregar = false;
        for (const t of S.tarefas) {
          if (t.projeto !== S.proj.id) continue;
          const est = antes[t.id];
          if (est && est !== t.estado && t.estado === 'pronta') {
            recarregar = true;
            if (t.tipo === 'receita') toast(`Receita aplicada: ${t.resultado?.cortado ? `${t.resultado.cortado} s cortados` : 'pronto'}. Ctrl+Z desfaz.`);
            if (t.tipo === 'exportar') toast(`Pronto: ${t.resultado?.nome}${t.resultado?.atraso ? ` (áudio sincronizado ${t.resultado.atraso > 0 ? '+' : ''}${t.resultado.atraso.toFixed(2)} s)` : ''}. Baixe na aba Exportar ou Fila.`);
            if (t.tipo === 'analisar') toast(`Análise pronta: ${t.resultado?.sugestoes ?? 0} sugestão(ões).`);
          }
          if (est && est !== t.estado && t.estado === 'erro') toast(`${t.titulo}: ${t.erro}`, true);
        }
        const prep = Object.values(S.fontes || {}).some((f) => f.estado !== 'pronta');
        if (recarregar || prep) { await recarregarProjeto(true); if (recarregar) caber(); }
      }
      antes = Object.fromEntries(S.tarefas.map((t) => [t.id, t.estado]));
      if (!$('#editor').hidden) {
        if (painelAtual() === 'fila') desenhar($('#aba-fila'));
        else if (['sugestoes', 'texto', 'efeitos', 'exportar'].includes(painelAtual()) && ativas.length) renderPainelLeve();
      } else desenharFilaInicio();
      timer = setTimeout(atualizar, ativas.length ? 1500 : 6000);
    }
    return { desenhar, atualizar };
  })();
  function renderPainelLeve() {
    const a = painelAtual();
    if (a === 'efeitos') desenharMedidas();
    else if (a === 'sugestoes') { const b = $('#btnAnalisar'); const pend = tarefasPendentes(['analisar', 'transcrever']); if (b) { b.disabled = !!pend.length; if (pend.length) b.textContent = `Analisando… (${pend.length} na fila)`; } }
  }
  function cliqueFila(e) {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.limpar != null) { api(`${API}/fila/limpar`, { method: 'POST' }).then(Fila.atualizar); return; }
    if (b.dataset.abrir) { abrirProjeto(b.dataset.abrir); return; }
    const t = b.closest('[data-t]'); if (!t || !b.dataset.ac) return;
    api(`${API}/fila/${t.dataset.t}/${b.dataset.ac}`, { method: 'POST' }).then(Fila.atualizar).catch((err) => toast(err.message, true));
  }
  $('#aba-fila').addEventListener('click', cliqueFila);
  $('#filaInicio').addEventListener('click', cliqueFila);
  $('#filaInicioLimpar').addEventListener('click', () => api(`${API}/fila/limpar`, { method: 'POST' }).then(Fila.atualizar));
  function desenharFilaInicio() {
    const card = $('#filaInicioCard');
    card.hidden = !S.tarefas.length;
    if (S.tarefas.length) Fila.desenhar($('#filaInicio'));
  }

  // ======================================================================
  // Início
  // ======================================================================
  async function listarProjetos() {
    try {
      const d = await api(`${API}/projetos`);
      $('#listaProjetos').innerHTML = d.projetos.length ? d.projetos.map((p) => `
        <div class="proj" data-id="${p.id}" role="button" tabindex="0"><div style="min-width:0"><b>${esc(p.nome)}</b><span>${fmtCurto(p.duracao)} · ${p.pistas} pista(s) · ${esc(p.alterado || p.criado || '')}</span></div>
          <button class="btn ghost xs" data-apagar="${p.id}" aria-label="Apagar ${esc(p.nome)}">✕</button></div>`).join('') : '<p class="nota" style="margin:0">Nenhum projeto ainda.</p>';
    } catch (err) { $('#listaProjetos').innerHTML = `<p class="nota">${esc(err.message)}</p>`; }
  }
  $('#listaProjetos').addEventListener('click', async (e) => {
    const ap = e.target.closest('[data-apagar]');
    if (ap) { if (!confirm('Apagar este projeto e os arquivos importados nele?')) return; await api(`${API}/projeto/${ap.dataset.apagar}`, { method: 'DELETE' }); listarProjetos(); return; }
    const p = e.target.closest('.proj'); if (p) abrirProjeto(p.dataset.id).catch((err) => toast(err.message, true));
  });
  $('#listaProjetos').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.classList.contains('proj')) e.target.click(); });
  $('#novoVazio').addEventListener('click', async () => { const d = await json(`${API}/projetos`, { nome: 'Projeto sem nome' }); abrirProjeto(d.projeto.id); });
  async function novoComArquivos(fs) {
    if (!fs.length) return;
    const d = await json(`${API}/projetos`, { nome: fs[0].name.replace(/\.[^.]+$/, '') });
    const fd = new FormData(); fs.forEach((f) => fd.append('file', f));
    const zona = $('#soltarInicio b'); const antes = zona.textContent; zona.textContent = `Enviando ${fs.length} arquivo(s)…`;
    try { await api(`${API}/projeto/${d.projeto.id}/importar`, { method: 'POST', body: fd }); await abrirProjeto(d.projeto.id); Fila.atualizar(); }
    catch (err) { toast(err.message, true); }
    finally { zona.textContent = antes; }
  }
  const zi = $('#soltarInicio');
  zi.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#arqInicio').click(); } });
  $('#arqInicio').addEventListener('change', (e) => { novoComArquivos([...e.target.files]); e.target.value = ''; });
  ['dragenter', 'dragover'].forEach((ev) => zi.addEventListener(ev, (e) => { e.preventDefault(); zi.classList.add('sobre'); }));
  ['dragleave', 'drop'].forEach((ev) => zi.addEventListener(ev, () => zi.classList.remove('sobre')));
  zi.addEventListener('drop', (e) => { e.preventDefault(); novoComArquivos([...e.dataTransfer.files]); });
  $('#loteArquivos').addEventListener('change', async (e) => {
    const fs = [...e.target.files]; e.target.value = ''; if (!fs.length) return;
    const fd = new FormData(); fs.forEach((f) => fd.append('file', f));
    fd.append('receita', $('#loteReceita').value); fd.append('formato', $('#loteFormato').value); fd.append('kbps', $('#loteKbps').value);
    $('#loteNota').textContent = `Enviando ${fs.length} arquivo(s)…`;
    try { const d = await api(`${API}/lote`, { method: 'POST', body: fd }); $('#loteNota').textContent = `${d.projetos.length} projeto(s) na fila. Acompanhe abaixo; cada um sai exportado.`; listarProjetos(); Fila.atualizar(); }
    catch (err) { $('#loteNota').textContent = err.message; }
  });
  $('#voltarProjetos').addEventListener('click', async () => {
    Toca.parar(false); await salvar(); S.proj = null; history.replaceState(null, '', location.pathname);
    $('#editor').hidden = true; $('#inicio').hidden = false; document.title = 'Áudio Studio'; listarProjetos(); desenharFilaInicio();
  });
  $('#nomeProjeto').addEventListener('change', (e) => { S.proj.nome = e.target.value.trim().slice(0, 120) || S.proj.nome; document.title = `${S.proj.nome} · Áudio Studio`; confirmar(); });
  $('#desfazer').addEventListener('click', desfazer);
  $('#refazer').addEventListener('click', refazer);
  $('#ajuda').addEventListener('click', () => $('#dlgAtalhos').showModal());
  window.addEventListener('beforeunload', (e) => { if (S.sujo) { salvar(); e.preventDefault(); } });

  (async () => {
    try {
      const d = await api(`${API}/catalogo`);
      S.catalogo = d;
      $('#loteReceita').innerHTML = d.receitas.map((r) => `<option value="${r.id}">${esc(r.nome)}</option>`).join('');
    } catch (err) { toast(err.message, true); }
    const q = new URLSearchParams(location.search);
    if (q.get('projeto')) { try { await abrirProjeto(q.get('projeto')); } catch (err) { toast(err.message, true); listarProjetos(); } }
    else listarProjetos();
    Fila.atualizar();
  })();
})();
