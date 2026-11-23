-- Targeted repair for missing participant departure flags, NOT a substitute for 001..005.
-- Explicit operator approval required. No application automatically runs this file.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
DO $$
BEGIN
 IF to_regclass('mobile_capture.room_participants') IS NULL THEN
  RAISE EXCEPTION 'Missing mobile_capture.room_participants; inspect migrations 001..005 first';
 END IF;
 IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='mobile_capture'
   AND table_name='room_participants' AND column_name IN ('leaving','revoked') AND data_type<>'boolean') THEN
  RAISE EXCEPTION 'Departure flag has incompatible type; manual review required';
 END IF;
END $$;
ALTER TABLE mobile_capture.room_participants
 ADD COLUMN IF NOT EXISTS leaving boolean NOT NULL DEFAULT false,
 ADD COLUMN IF NOT EXISTS revoked boolean NOT NULL DEFAULT false;
-- Preserve true/false values. NULL in an incomplete prior migration means no recorded departure.
UPDATE mobile_capture.room_participants SET leaving=false WHERE leaving IS NULL;
UPDATE mobile_capture.room_participants SET revoked=false WHERE revoked IS NULL;
ALTER TABLE mobile_capture.room_participants
 ALTER COLUMN leaving SET DEFAULT false, ALTER COLUMN leaving SET NOT NULL,
 ALTER COLUMN revoked SET DEFAULT false, ALTER COLUMN revoked SET NOT NULL,
 ALTER COLUMN source_label DROP NOT NULL;
COMMIT;
