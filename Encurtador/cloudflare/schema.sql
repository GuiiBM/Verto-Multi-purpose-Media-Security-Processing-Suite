-- Banco D1 do Encurtador GBM. O Verto aplica este arquivo ao conectar (é idempotente).

CREATE TABLE IF NOT EXISTS links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE COLLATE NOCASE,
  url TEXT NOT NULL,
  titulo TEXT,
  notas TEXT,
  tags TEXT,
  criado_em INTEGER NOT NULL,
  atualizado_em INTEGER NOT NULL,
  expira_em INTEGER,
  max_cliques INTEGER,
  senha_hash TEXT,
  ativo INTEGER NOT NULL DEFAULT 1,
  tipo_redirect INTEGER NOT NULL DEFAULT 302,
  cliques INTEGER NOT NULL DEFAULT 0,
  ultimo_clique INTEGER
);

CREATE TABLE IF NOT EXISTS cliques (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  link_id INTEGER NOT NULL,
  ts INTEGER NOT NULL,
  referencia TEXT,
  dispositivo TEXT,
  navegador TEXT,
  so TEXT,
  pais TEXT,
  visitante TEXT,
  bot INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cliques_link_ts ON cliques (link_id, ts);

CREATE TABLE IF NOT EXISTS tentativas (
  chave TEXT PRIMARY KEY,
  n INTEGER NOT NULL,
  inicio INTEGER NOT NULL
);
