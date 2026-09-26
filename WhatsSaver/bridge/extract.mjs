// Extração do que interessa ao WhatsSaver nas mensagens que o Baileys entrega:
// fotos e vídeos (inclusive os enviados como documento), a mensagem mais
// antiga/mais nova de cada conversa, contatos e o mapa LID <-> número.
// Fica separado da ponte para poder ser testado sem conectar ao WhatsApp.
import { normalizeMessageContent, getContentType, jidNormalizedUser, isJidGroup, isLidUser, toNumber } from 'baileys'

const IMAGE_EXT = new Set(['jpg', 'jpeg', 'jfif', 'png', 'gif', 'webp', 'heic', 'heif', 'avif', 'bmp', 'tif', 'tiff', 'dng', 'raw', 'cr2', 'cr3', 'nef', 'arw', 'orf', 'rw2'])
const VIDEO_EXT = new Set(['mp4', 'mov', 'm4v', '3gp', '3g2', 'mkv', 'avi', 'webm', 'wmv', 'flv', 'mpg', 'mpeg', 'ts', 'mts', 'm2ts', 'hevc', 'vob'])

const SKIP_SERVERS = ['broadcast', 'newsletter', 'bot', 'call']
export function skipJid (jid) {
  if (!jid) return true
  const server = jid.split('@')[1] || ''
  return SKIP_SERVERS.includes(server)
}

// Bytes do protobuf viram base64. Algumas rotas do Baileys já entregam os
// bytes como texto base64 (toJSON): aí é só repassar.
const b64 = v => (!v ? null : typeof v === 'string' ? v : Buffer.from(v).toString('base64'))
const extOf = name => ((name || '').match(/\.([a-z0-9]{2,5})$/i)?.[1] || '').toLowerCase()

export function documentKind (doc) {
  const mime = (doc.mimetype || '').toLowerCase()
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('video/')) return 'video'
  const ext = extOf(doc.fileName)
  if (IMAGE_EXT.has(ext)) return 'image'
  if (VIDEO_EXT.has(ext)) return 'video'
  return null
}

// Foto ou vídeo da mensagem, venha como mídia normal ou como documento.
export function mediaOf (content) {
  if (content.imageMessage) return { type: 'imageMessage', media: content.imageMessage, kind: 'image', asFile: false }
  if (content.videoMessage) return { type: 'videoMessage', media: content.videoMessage, kind: 'video', asFile: false }
  if (content.ptvMessage) return { type: 'videoMessage', media: content.ptvMessage, kind: 'video', asFile: false, ptv: true }
  if (content.documentMessage) {
    const kind = documentKind(content.documentMessage)
    if (kind) return { type: 'documentMessage', media: content.documentMessage, kind, asFile: true }
  }
  return null
}

export function mediaRecord (m, content, chat, ts) {
  const found = mediaOf(content)
  if (!found) return null
  const { type, media, kind, asFile } = found
  // Visualização única e mensagens sem chave não têm como ser baixadas. Sem
  // endereço (comum em mídia antiga) ainda dá: o celular reenvia e manda um novo.
  if (media.viewOnce || !media.mediaKey) return null
  const key = m.key
  return {
    chat,
    id: key.id,
    fromMe: !!key.fromMe,
    sender: key.fromMe ? null : jidNormalizedUser(key.participant || key.remoteJid),
    pushName: key.fromMe ? null : (m.pushName || null),
    ts,
    kind,
    asFile,
    gif: !!media.gifPlayback,
    ptv: !!found.ptv,
    mimetype: media.mimetype || null,
    fileName: media.fileName || null,
    size: toNumber(media.fileLength) || null,
    width: media.width || null,
    height: media.height || null,
    seconds: media.seconds || null,
    caption: media.caption || null,
    thumb: b64(media.jpegThumbnail),
    // Só o necessário para baixar depois (e pedir reenvio ao celular).
    payload: {
      key: { remoteJid: key.remoteJid, fromMe: !!key.fromMe, id: key.id, participant: key.participant || null },
      type,
      media: {
        url: media.url || null,
        directPath: media.directPath || null,
        mediaKey: b64(media.mediaKey),
        fileEncSha256: b64(media.fileEncSha256),
        mimetype: media.mimetype || null,
        fileLength: toNumber(media.fileLength) || null,
      },
    },
  }
}

const IGNORED_TYPES = new Set(['protocolMessage', 'senderKeyDistributionMessage', 'reactionMessage', 'pollUpdateMessage', 'keepInChatMessage'])

// Separa as mídias e, por conversa, a mensagem mais antiga e a mais nova
// (de qualquer tipo): a mais antiga é o ponto de partida para pedir ao
// celular as mensagens anteriores.
export function collect (messages) {
  const media = []
  const bounds = new Map()
  const mappings = []
  for (const m of messages || []) {
    const key = m?.key
    if (!key?.remoteJid || !key.id) continue
    const chat = jidNormalizedUser(key.remoteJid)
    if (skipJid(chat)) continue
    const content = normalizeMessageContent(m.message)
    const type = content ? getContentType(content) : null
    if (content && IGNORED_TYPES.has(type)) continue
    if (!content && !m.messageStubType) continue

    for (const [a, b] of [[key.remoteJid, key.remoteJidAlt], [key.participant, key.participantAlt]]) {
      if (!a || !b) continue
      const [x, y] = [jidNormalizedUser(a), jidNormalizedUser(b)]
      if (isLidUser(x) && !isLidUser(y)) mappings.push({ lid: x, pn: y })
      else if (isLidUser(y) && !isLidUser(x)) mappings.push({ lid: y, pn: x })
    }

    const ts = toNumber(m.messageTimestamp) || 0
    let b = bounds.get(chat)
    if (!b) bounds.set(chat, (b = { jid: chat, count: 0, newest: 0, oldest: null }))
    b.count += 1
    if (ts > b.newest) b.newest = ts
    if (ts && (!b.oldest || ts < b.oldest.ts)) {
      b.oldest = { ts, key: { remoteJid: key.remoteJid, fromMe: !!key.fromMe, id: key.id, participant: key.participant || null } }
    }
    if (content) {
      const rec = mediaRecord(m, content, chat, ts)
      if (rec) media.push(rec)
    }
  }
  return { media, bounds: [...bounds.values()], mappings }
}

export function chatInfo (c) {
  const jid = c?.id && jidNormalizedUser(c.id)
  if (!jid || skipJid(jid)) return null
  return {
    jid,
    name: c.name || c.displayName || c.subject || null,
    group: isJidGroup(jid) || false,
    ts: toNumber(c.conversationTimestamp) || toNumber(c.lastMsgTimestamp) || toNumber(c.lastMessageRecvTimestamp) || null,
    pn: c.pnJid ? jidNormalizedUser(c.pnJid) : null,
    lid: c.lidJid ? jidNormalizedUser(c.lidJid) : null,
  }
}

export function contactInfo (c) {
  const jid = c?.id && jidNormalizedUser(c.id)
  if (!jid || skipJid(jid)) return null
  return {
    jid,
    name: c.name || null,
    notify: c.notify || null,
    verified: c.verifiedName || null,
    lid: c.lid ? jidNormalizedUser(c.lid) : null,
    pn: c.phoneNumber ? jidNormalizedUser(c.phoneNumber) : null,
  }
}

export function compact (list, fn) {
  return (list || []).map(fn).filter(Boolean)
}
