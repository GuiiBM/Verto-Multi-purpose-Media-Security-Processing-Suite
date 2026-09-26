// Ponte entre o Verto (Flask) e o WhatsApp Web, usando o Baileys.
//
// O Python abre este processo e conversa com ele por stdin/stdout, uma linha
// JSON por mensagem: os comandos chegam como {id, cmd, ...} e voltam como
// {id, ok, data} ou {id, ok: false, error, code}; o resto que sai por stdout
// são eventos {ev, ...} (estado da conexão, histórico, mídias novas, contatos).
// O stdout é só do protocolo: qualquer console.log de biblioteca vai para o log.
//
// A ponte não guarda mensagens. Ela filtra fotos e vídeos (inclusive os
// enviados como documento) e manda para o Python, que mantém o banco SQLite e
// baixa as mídias. O que só a conexão do WhatsApp faz fica aqui: pedir ao
// celular mensagens antigas e o reenvio de mídias que saíram do servidor.
// Quando o stdin fecha (Flask parou ou recarregou), a ponte fecha junto.
import fs from 'node:fs'
import path from 'node:path'
import readline from 'node:readline'
import pino from 'pino'
import makeWASocket, {
  DisconnectReason, WAMessageStubType, proto, useMultiFileAuthState, fetchLatestWaWebVersion,
  jidNormalizedUser, encryptMediaRetryRequest, decryptMediaRetryData, getUrlFromDirectPath,
} from 'baileys'
import { collect, chatInfo, contactInfo, compact } from './extract.mjs'

const DATA_DIR = process.env.WHATSSAVER_DATA || path.resolve('dados')
const AUTH_DIR = path.join(DATA_DIR, 'auth')
// Nome que aparece em "Aparelhos conectados" no celular. O segundo campo
// precisa ser um navegador: com "Desktop" o WhatsApp recusa o pareamento (428).
const BROWSER = ['LocalTools WhatsSaver', 'Chrome', '1.0.0']
const REUPLOAD_TIMEOUT_MS = 60_000

// ------------------------------------------------------------------ log ---

fs.mkdirSync(DATA_DIR, { recursive: true })
const LOG_PATH = path.join(DATA_DIR, 'bridge.log')
try {
  if (fs.statSync(LOG_PATH).size > 5 * 1024 * 1024) fs.renameSync(LOG_PATH, LOG_PATH + '.old')
} catch {}
const logFile = fs.createWriteStream(LOG_PATH, { flags: 'a' })
const logger = pino({ level: process.env.WHATSSAVER_LOG_LEVEL || 'warn' }, logFile)
// O libsignal escreve direto no console; nada disso pode cair no stdout.
for (const k of ['log', 'info', 'warn', 'error', 'debug', 'trace']) {
  console[k] = (...args) => logFile.write(`[console.${k}] ${args.map(a => (a instanceof Error ? a.stack : String(a))).join(' ')}\n`)
}
process.on('unhandledRejection', err => logger.error({ err }, 'unhandled rejection'))
process.on('uncaughtException', err => logger.error({ err }, 'uncaught exception'))

const send = obj => process.stdout.write(JSON.stringify(obj) + '\n')

class BridgeError extends Error {
  constructor (message, code) { super(message); this.code = code }
}

// ---------------------------------------------------------------- estado ---

let sock = null
let starting = false
let shuttingDown = false
let reconnectTimer = null
let failures = 0
let saveCreds = async () => {}
const state = { status: 'idle', qr: null, pairingCode: null, me: null, error: null }

function setState (patch) {
  Object.assign(state, patch)
  send({ ev: 'state', ...state })
}

function meInfo () {
  const u = sock?.user
  if (!u) return null
  return { id: jidNormalizedUser(u.id), lid: u.lid ? jidNormalizedUser(u.lid) : null, name: u.name || u.notify || null }
}

async function latestVersion () {
  // Versão do WhatsApp Web que o servidor espera. Se a busca falhar, o
  // Baileys usa a que vem com ele.
  const timeout = new Promise(resolve => setTimeout(() => resolve(null), 8000))
  try {
    const res = await Promise.race([fetchLatestWaWebVersion({}), timeout])
    return res?.version
  } catch {
    return undefined
  }
}

async function start () {
  if (sock || starting || shuttingDown) return
  starting = true
  clearTimeout(reconnectTimer)
  try {
    const auth = await useMultiFileAuthState(AUTH_DIR)
    saveCreds = auth.saveCreds
    const paired = auth.state.creds.me
    if (paired?.id && !state.me) {
      state.me = { id: jidNormalizedUser(paired.id), lid: paired.lid ? jidNormalizedUser(paired.lid) : null, name: paired.name || null }
    }
    const version = await latestVersion()
    if (shuttingDown) return
    setState({ status: state.me ? 'reconnecting' : 'connecting', error: null })
    sock = makeWASocket({
      auth: auth.state,
      logger,
      browser: BROWSER,
      ...(version ? { version } : {}),
      // Pede o histórico completo ao parear e aceita todos os tipos de
      // sincronização (o padrão do Baileys descarta o tipo FULL).
      syncFullHistory: true,
      shouldSyncHistoryMessage: () => true,
      // Não marcar "online": assim o celular continua recebendo as notificações.
      markOnlineOnConnect: false,
      generateHighQualityLinkPreview: false,
      getMessage: async () => undefined,
    })
    const current = sock
    sock.ev.process(async events => {
      if (current !== sock) return
      try {
        await handleEvents(events)
      } catch (err) {
        logger.error({ err }, 'erro tratando eventos')
      }
    })
  } catch (err) {
    logger.error({ err }, 'falha ao iniciar')
    sock = null
    setState({ status: 'error', error: 'Não consegui iniciar a conexão: ' + (err.message || err) })
  } finally {
    starting = false
  }
}

function scheduleReconnect () {
  failures += 1
  const delay = Math.min(30_000, 1000 * 2 ** Math.min(failures, 5))
  clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(start, delay)
}

function wipeAuth () {
  fs.rmSync(AUTH_DIR, { recursive: true, force: true })
}

function onConnectionUpdate ({ connection, lastDisconnect, qr }) {
  if (qr) setState({ status: 'qr', qr, error: null })
  if (connection === 'open') {
    failures = 0
    setState({ status: 'open', qr: null, pairingCode: null, error: null, me: meInfo() })
    const me = meInfo()
    if (me?.lid) send({ ev: 'mappings', mappings: [{ lid: me.lid, pn: me.id }] })
    loadGroups().catch(err => logger.warn({ err }, 'falha ao listar grupos'))
  }
  if (connection !== 'close') return

  const code = lastDisconnect?.error?.output?.statusCode
  const registered = !!sock?.authState?.creds?.me?.id || !!state.me
  sock = null
  if (shuttingDown) return
  if (code === DisconnectReason.loggedOut) {
    wipeAuth()
    setState({ status: 'logged_out', qr: null, pairingCode: null, me: null, error: null })
  } else if (code === DisconnectReason.connectionReplaced) {
    setState({ status: 'replaced', qr: null, error: 'Outra janela do WhatsSaver assumiu a conexão.' })
  } else if (code === DisconnectReason.restartRequired) {
    start()  // o WhatsApp pede para reabrir logo depois do pareamento
  } else if (!registered && state.status === 'qr') {
    // O QR foi trocado algumas vezes e ninguém escaneou: para até o usuário pedir outro.
    setState({ status: 'qr_expired', qr: null, pairingCode: null })
  } else if (!registered && failures >= 3) {
    setState({ status: 'error', qr: null, error: 'O WhatsApp recusou a conexão. Tente de novo em alguns minutos.' })
  } else {
    setState({ status: registered ? 'reconnecting' : 'connecting', qr: null, error: lastDisconnect?.error?.message || null })
    scheduleReconnect()
  }
}

async function loadGroups () {
  if (!sock) return
  const groups = await sock.groupFetchAllParticipating()
  const chats = Object.values(groups || {}).map(g => ({ jid: g.id, name: g.subject || null, group: true, ts: null }))
  if (chats.length) send({ ev: 'chats', chats })
}

// Conversas e remetentes que chegam só com o LID (id anônimo) viram duas
// conversas separadas se o número não for conhecido. O Baileys guarda esse
// mapa, mas só avisa (lid-mapping.update) quando aprende um par novo.
const lidAsked = new Set()
async function resolveLids (jids) {
  const lids = [...new Set(jids)].filter(j => j && j.endsWith('@lid') && !lidAsked.has(j))
  if (!lids.length || !sock?.signalRepository?.lidMapping) return
  lids.forEach(j => lidAsked.add(j))
  try {
    const found = await sock.signalRepository.lidMapping.getPNsForLIDs(lids)
    const mappings = (found || []).filter(x => x?.lid && x?.pn).map(x => ({ lid: jidNormalizedUser(x.lid), pn: jidNormalizedUser(x.pn) }))
    if (mappings.length) send({ ev: 'mappings', mappings })
  } catch (err) {
    logger.warn({ err }, 'falha ao consultar LIDs')
  }
}

function lidsOf ({ media, bounds }, chats = []) {
  return [...bounds.map(b => b.jid), ...media.map(m => m.sender), ...chats.map(c => c?.jid)]
}

async function handleEvents (events) {
  if (events['connection.update']) onConnectionUpdate(events['connection.update'])
  if (events['creds.update']) await saveCreds()

  const hist = events['messaging-history.set']
  if (hist) {
    const { media, bounds, mappings } = collect(hist.messages)
    send({
      ev: 'history',
      syncType: hist.syncType ?? null,
      progress: hist.progress ?? null,
      isLatest: !!hist.isLatest,
      sessionId: hist.peerDataRequestSessionId || null,
      chats: compact(hist.chats, chatInfo),
      contacts: compact(hist.contacts, contactInfo),
      mappings: [...(hist.lidPnMappings || []).map(x => ({ lid: jidNormalizedUser(x.lid), pn: jidNormalizedUser(x.pn) })), ...mappings],
      media,
      bounds,
    })
    resolveLids(lidsOf({ media, bounds }, compact(hist.chats, chatInfo)))
  }
  if (events['messaging-history.status']) {
    send({ ev: 'history_status', ...events['messaging-history.status'] })
  }

  const upsert = events['messages.upsert']
  if (upsert) {
    const { media, bounds, mappings } = collect(upsert.messages)
    if (media.length || bounds.length || mappings.length) send({ ev: 'messages', media, bounds, mappings })
    resolveLids(lidsOf({ media, bounds }))
  }

  const deleted = []
  for (const u of events['messages.update'] || []) {
    if (u.update?.messageStubType === WAMessageStubType.REVOKE || u.update?.message === null) {
      if (u.key?.remoteJid && u.key.id) deleted.push({ chat: jidNormalizedUser(u.key.remoteJid), id: u.key.id })
    }
  }
  const del = events['messages.delete']
  if (del && 'keys' in del) {
    for (const k of del.keys) if (k.remoteJid && k.id) deleted.push({ chat: jidNormalizedUser(k.remoteJid), id: k.id })
  }
  if (deleted.length) send({ ev: 'deleted', items: deleted })

  const contacts = [...compact(events['contacts.upsert'], contactInfo), ...compact(events['contacts.update'], contactInfo)]
  if (contacts.length) send({ ev: 'contacts', contacts })

  const chats = [...compact(events['chats.upsert'], chatInfo), ...compact(events['chats.update'], chatInfo)]
  for (const g of [...(events['groups.upsert'] || []), ...(events['groups.update'] || [])]) {
    if (g.id && g.subject) chats.push({ jid: g.id, name: g.subject, group: true, ts: null })
  }
  if (chats.length) send({ ev: 'chats', chats })

  if (events['lid-mapping.update']) {
    const { lid, pn } = events['lid-mapping.update']
    if (lid && pn) send({ ev: 'mappings', mappings: [{ lid: jidNormalizedUser(lid), pn: jidNormalizedUser(pn) }] })
  }
}

// -------------------------------------------------------------- reenvio ---

function requireOpen () {
  if (!sock || state.status !== 'open') throw new BridgeError('O WhatsApp não está conectado agora.', 'offline')
}

// Pede ao celular para reenviar ao servidor uma mídia que já expirou, como o
// WhatsApp Web faz. Só funciona se o celular estiver online e tiver o arquivo.
async function reupload (key, media) {
  const current = sock
  const wait = new Promise((resolve, reject) => {
    const finish = (fn, value) => {
      clearTimeout(timer)
      current.ev.off('messages.media-update', onUpdate)
      fn(value)
    }
    const onUpdate = updates => {
      const hit = updates.find(u => u.key?.id === key.id)
      if (hit) finish(resolve, hit)
    }
    const timer = setTimeout(() => finish(reject, new BridgeError(
      'O arquivo expirou no servidor e o celular não respondeu ao pedido de reenvio. Deixe o celular ligado, com internet e o WhatsApp aberto, e tente de novo.',
      'phone_timeout')), REUPLOAD_TIMEOUT_MS)
    current.ev.on('messages.media-update', onUpdate)
  })
  await current.sendNode(encryptMediaRetryRequest(key, media.mediaKey, current.authState.creds.me.id))
  const hit = await wait
  if (hit.error) {
    throw new BridgeError('O celular não conseguiu reenviar o arquivo (' + (hit.error.message || 'erro') + ').', 'reupload_failed')
  }
  const res = decryptMediaRetryData(hit.media, media.mediaKey, hit.key.id)
  if (res.result === proto.MediaRetryNotification.ResultType.NOT_FOUND) {
    throw new BridgeError('O arquivo expirou no servidor do WhatsApp e o celular não tem mais uma cópia dele (ou nunca chegou a baixar).', 'not_found')
  }
  if (res.result !== proto.MediaRetryNotification.ResultType.SUCCESS || !res.directPath) {
    throw new BridgeError('O celular não conseguiu reenviar o arquivo.', 'reupload_failed')
  }
  media.directPath = res.directPath
  media.url = getUrlFromDirectPath(res.directPath, current.getMediaHost?.())
}

// ------------------------------------------------------------- comandos ---

const commands = {
  async status () { return { ...state } },

  async connect () {
    if (state.status === 'replaced' || state.status === 'error' || state.status === 'qr_expired' || state.status === 'logged_out' || state.status === 'idle') {
      failures = 0
      if (sock) { try { sock.end(undefined) } catch {} sock = null }
      start()
    }
    return { ...state }
  },

  async pair_code ({ phone }) {
    const digits = String(phone || '').replace(/\D/g, '')
    if (digits.length < 10) throw new BridgeError('Digite o número com DDI e DDD, por exemplo 55 11 91234-5678.', 'bad_phone')
    if (!sock || state.status !== 'qr') throw new BridgeError('Espere o QR aparecer e tente de novo.', 'not_ready')
    const code = await sock.requestPairingCode(digits)
    setState({ pairingCode: code })
    return { code }
  },

  async logout () {
    const s = sock
    sock = null
    clearTimeout(reconnectTimer)
    if (s) {
      try { await s.logout() } catch (err) { logger.warn({ err }, 'logout') }
      try { s.end(undefined) } catch {}
    }
    wipeAuth()
    setState({ status: 'logged_out', qr: null, pairingCode: null, me: null, error: null })
    return { ok: true }
  },

  async fetch_history ({ key, ts, count }) {
    requireOpen()
    if (!key?.remoteJid || !key.id || !ts) throw new BridgeError('Conversa sem mensagens conhecidas.', 'bad_request')
    const k = { remoteJid: key.remoteJid, fromMe: !!key.fromMe, id: key.id }
    const requestId = await sock.fetchMessageHistory(Math.min(Math.max(count || 50, 1), 50), k, ts * 1000)
    return { requestId }
  },

  async reupload ({ key, mediaKey }) {
    requireOpen()
    if (!key?.remoteJid || !key.id || !mediaKey) throw new BridgeError('Dados da mídia incompletos.', 'bad_request')
    const k = { remoteJid: key.remoteJid, fromMe: !!key.fromMe, id: key.id, ...(key.participant ? { participant: key.participant } : {}) }
    const media = { mediaKey: Buffer.from(mediaKey, 'base64') }
    await reupload(k, media)
    return { directPath: media.directPath, url: media.url || null }
  },

  async avatar ({ jid }) {
    requireOpen()
    try {
      return { url: (await sock.profilePictureUrl(jid, 'preview', 10_000)) || null }
    } catch {
      return { url: null }
    }
  },

  async groups () {
    requireOpen()
    await loadGroups()
    return { ok: true }
  },
}

async function runCommand (msg) {
  const fn = commands[msg.cmd]
  if (!fn) return send({ id: msg.id, ok: false, error: 'Comando desconhecido: ' + msg.cmd, code: 'bad_request' })
  try {
    send({ id: msg.id, ok: true, data: (await fn(msg)) ?? null })
  } catch (err) {
    logger.warn({ err, cmd: msg.cmd }, 'comando falhou')
    const status = err?.output?.statusCode
    send({ id: msg.id, ok: false, error: err.message || String(err), code: err.code || (status ? 'http_' + status : 'error') })
  }
}

async function shutdown () {
  if (shuttingDown) return
  shuttingDown = true
  clearTimeout(reconnectTimer)
  try { await saveCreds() } catch {}
  try { sock?.end(undefined) } catch {}
  setTimeout(() => process.exit(0), 300)
}

const rl = readline.createInterface({ input: process.stdin })
rl.on('line', line => {
  let msg
  try { msg = JSON.parse(line) } catch { return }
  if (msg?.cmd === 'shutdown') return shutdown()
  if (msg?.cmd) runCommand(msg)
})
rl.on('close', shutdown)
process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)

send({ ev: 'ready', pid: process.pid, node: process.version })
start()
