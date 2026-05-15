CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
  user_id              BIGINT      PRIMARY KEY,
  telegram_username    TEXT,
  display_name         TEXT,
  preferred_languages  TEXT[]      NOT NULL DEFAULT '{}',
  watched_coins        TEXT[]      NOT NULL DEFAULT '{}',
  onboarded            BOOLEAN     NOT NULL DEFAULT FALSE,
  digest_enabled       BOOLEAN     NOT NULL DEFAULT FALSE,
  digest_hour_utc      SMALLINT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS quota_log (
  id      BIGSERIAL   PRIMARY KEY,
  user_id BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  ts      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_quota_user_ts ON quota_log(user_id, ts DESC);

CREATE TABLE IF NOT EXISTS messages (
  id            BIGSERIAL   PRIMARY KEY,
  user_id       BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  role          TEXT        NOT NULL CHECK (role IN ('user','assistant')),
  content       TEXT        NOT NULL,
  language      TEXT,
  llm_provider  TEXT,
  llm_model     TEXT,
  tool_calls    JSONB,
  embedding     vector(768),
  ts            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messages_user_ts ON messages(user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_messages_embed  ON messages
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
