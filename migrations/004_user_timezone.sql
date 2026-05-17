-- v0.7.4 follow-up: per-user timezone for scheduled-push time conversion.
-- Default Asia/Tbilisi (UTC+4, no DST) — the current user base is Georgian-
-- and Russian-speaking. set_user_profile auto-detects from preferred_languages
-- at onboarding; users can override via admin or future profile-edit tool.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'Asia/Tbilisi';
