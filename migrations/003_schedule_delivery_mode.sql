-- v0.7.3 follow-up: per-schedule delivery mode.
-- 'push' = watcher pushes the result via Telegram immediately when the schedule
--          fires (matches the user's intuition for "send me X every Sunday").
-- 'deferred' = watcher enqueues into pending_notifications and the result is
--              delivered as a prefix on the user's next message ("save it for
--              when we next chat").
-- The LLM picks the mode from the user's phrasing when calling schedule_push;
-- it can be overridden via list/cancel + recreate.

ALTER TABLE scheduled_pushes
  ADD COLUMN IF NOT EXISTS delivery_mode TEXT NOT NULL DEFAULT 'push'
    CHECK (delivery_mode IN ('push', 'deferred'));
