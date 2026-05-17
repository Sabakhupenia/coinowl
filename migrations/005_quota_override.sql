-- v0.7.4 follow-up: per-user quota override for the admin panel.
-- NULL = use the bot's default limit (10 messages / 3-hour window).
-- A non-null value lets the admin raise or lower a specific user's cap
-- without changing the global default.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS quota_override INTEGER;
