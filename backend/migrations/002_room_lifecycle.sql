BEGIN;
SET LOCAL search_path TO mobile_capture;
-- Admission expiry is not a recording duration limit. Active capture never auto-stops.
ALTER TABLE recording_rooms ADD COLUMN IF NOT EXISTS expires_at timestamptz NOT NULL DEFAULT (now() + interval '24 hours');
ALTER TABLE recording_rooms ADD COLUMN IF NOT EXISTS closed_at timestamptz;
COMMIT;
