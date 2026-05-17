-- v0.7.3: alerts & subscriptions
-- Two trigger types (price threshold, time-based cron) sharing one background
-- watcher. Price alerts push immediately on cross; scheduled pushes enqueue
-- into pending_notifications and wait for the user's next message.

CREATE TABLE IF NOT EXISTS alerts (
  id                BIGSERIAL     PRIMARY KEY,
  user_id           BIGINT        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  symbol            TEXT          NOT NULL,
  coin_id           TEXT          NOT NULL,
  threshold         NUMERIC(20,8) NOT NULL,
  direction         TEXT          NOT NULL CHECK (direction IN ('above','below')),
  recurring         BOOLEAN       NOT NULL DEFAULT FALSE,
  original_phrasing TEXT          NOT NULL,
  enabled           BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  last_fired_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(enabled, coin_id) WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_alerts_user   ON alerts(user_id);

CREATE TABLE IF NOT EXISTS scheduled_pushes (
  id                BIGSERIAL   PRIMARY KEY,
  user_id           BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  cron_expr         TEXT        NOT NULL,
  tool_name         TEXT        NOT NULL,
  tool_args_json    JSONB       NOT NULL DEFAULT '{}'::jsonb,
  original_phrasing TEXT        NOT NULL,
  enabled           BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_fired_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_schedules_active ON scheduled_pushes(enabled) WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_schedules_user   ON scheduled_pushes(user_id);

CREATE TABLE IF NOT EXISTS pending_notifications (
  id           BIGSERIAL   PRIMARY KEY,
  user_id      BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  schedule_id  BIGINT      NOT NULL REFERENCES scheduled_pushes(id) ON DELETE CASCADE,
  payload_json JSONB       NOT NULL,
  fired_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  delivered_at TIMESTAMPTZ
);
-- At most one undelivered row per (user, schedule). Old fires get overwritten
-- by the next fire if the user is still offline, so they only see "where things
-- stand now" not a stack of stale digests.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_one_per_schedule
  ON pending_notifications(user_id, schedule_id)
  WHERE delivered_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_pending_user_undelivered
  ON pending_notifications(user_id) WHERE delivered_at IS NULL;
