BEGIN;
ALTER TABLE public.machines ADD COLUMN IF NOT EXISTS notes text;
ALTER TABLE public.recording_sessions ALTER COLUMN material_id DROP NOT NULL, ALTER COLUMN tool_id DROP NOT NULL, ALTER COLUMN process_type DROP NOT NULL;
SET LOCAL search_path TO mobile_capture,public;
ALTER TABLE recording_rooms ADD COLUMN required_recorder_count integer NOT NULL DEFAULT 3 CHECK(required_recorder_count BETWEEN 1 AND 5);
ALTER TABLE recording_sessions ADD COLUMN machine_id uuid REFERENCES public.machines(machine_id);
ALTER TABLE room_participants ALTER COLUMN source_label DROP NOT NULL, DROP CONSTRAINT room_participants_source_label_check, ADD CHECK(source_label IN ('A','B','C','D','E'));
ALTER TABLE audio_chunks DROP CONSTRAINT audio_chunks_source_label_check, ADD CHECK(source_label IN ('A','B','C','D','E'));
ALTER TABLE room_participants ADD COLUMN leaving boolean NOT NULL DEFAULT false, ADD COLUMN microphone_permission text NOT NULL DEFAULT 'unknown', ADD COLUMN revoked boolean NOT NULL DEFAULT false, ADD COLUMN recorder_id uuid NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE recording_rooms ADD COLUMN assignment_version bigint NOT NULL DEFAULT 0, ADD COLUMN event_version bigint NOT NULL DEFAULT 0, ADD COLUMN closing boolean NOT NULL DEFAULT false;
ˊ˙ALTER TABLE participant_recordings ADD COLUMN source_position text;
UPDATE participant_recordings t SET source_position=p.source_label FROM room_participants p WHERE p.id=t.participant_id;
ALTER TABLE recording_sessions DROP CONSTRAINT recording_sessions_room_id_key;
CREATE UNIQUE INDEX one_open_session ON recording_sessions(room_id) WHERE status NOT IN ('completed','interrupted');
CREATE OR REPLACE FUNCTION fill_chunk_identity() RETURNS trigger LANGUAGE plpgsql SET search_path=mobile_capture,pg_temp AS $$
BEGIN
 SELECT pr.participant_recording_id,pr.source_position INTO NEW.participant_recording_id,NEW.source_label
 FROM participant_recordings pr WHERE pr.session_id=NEW.session_id AND pr.participant_id=NEW.participant_id;
 RETURN NEW;
END;
$$;
-- Preserve legacy take metadata without fabricating machine associations.
ALTER TABLE recording_sessions ADD COLUMN legacy_take boolean NOT NULL DEFAULT true;
ALTER TABLE recording_sessions ALTER COLUMN legacy_take SET DEFAULT false;
ALTER TABLE recording_sessions ADD CONSTRAINT take_requires_machine CHECK(legacy_take OR status='waiting' OR machine_id IS NOT NULL);
COMMIT;
