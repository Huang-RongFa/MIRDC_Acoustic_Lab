BEGIN;
SET LOCAL search_path TO mobile_capture;
ALTER TABLE participant_recordings ADD COLUMN participant_recording_id uuid NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE participant_recordings ADD CONSTRAINT participant_recording_identity UNIQUE(participant_recording_id,session_id,participant_id);
ALTER TABLE participant_recordings ADD COLUMN sample_rate integer CHECK(sample_rate BETWEEN 8000 AND 384000);
ALTER TABLE participant_recordings ADD COLUMN channel_count integer CHECK(channel_count BETWEEN 1 AND 32);
ALTER TABLE participant_recordings ADD COLUMN duration_ms double precision CHECK(duration_ms>=0);
ALTER TABLE participant_recordings ADD COLUMN server_started_at timestamptz;
ALTER TABLE participant_recordings ADD COLUMN server_stopped_at timestamptz;
ALTER TABLE audio_chunks ADD COLUMN participant_recording_id uuid;
ALTER TABLE audio_chunks ADD COLUMN source_label text CHECK(source_label IN ('A','B','C'));
ALTER TABLE audio_chunks ADD COLUMN byte_size integer GENERATED ALWAYS AS (octet_length(audio_data)) STORED;
UPDATE audio_chunks ch SET participant_recording_id=pr.participant_recording_id,source_label=p.source_label
FROM participant_recordings pr JOIN room_participants p ON p.id=pr.participant_id
WHERE ch.session_id=pr.session_id AND ch.participant_id=pr.participant_id;
ALTER TABLE audio_chunks ALTER COLUMN participant_recording_id SET NOT NULL;
ALTER TABLE audio_chunks ALTER COLUMN source_label SET NOT NULL;
ALTER TABLE audio_chunks ADD FOREIGN KEY(participant_recording_id,session_id,participant_id)
 REFERENCES participant_recordings(participant_recording_id,session_id,participant_id);
-- Keep older API inserts compatible while enforcing the identity at the DB boundary.
CREATE FUNCTION fill_chunk_identity() RETURNS trigger LANGUAGE plpgsql SET search_path=mobile_capture,pg_temp AS $$
BEGIN
 SELECT pr.participant_recording_id,p.source_label INTO NEW.participant_recording_id,NEW.source_label
 FROM participant_recordings pr JOIN room_participants p ON p.id=pr.participant_id
 WHERE pr.session_id=NEW.session_id AND pr.participant_id=NEW.participant_id;
 RETURN NEW;
END;
$$;
CREATE TRIGGER chunk_identity BEFORE INSERT ON audio_chunks FOR EACH ROW EXECUTE FUNCTION fill_chunk_identity();
COMMIT;
