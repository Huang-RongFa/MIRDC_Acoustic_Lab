BEGIN;
-- Additive migration. The public V1.2 shared-clock tables remain untouched.
CREATE SCHEMA IF NOT EXISTS mobile_capture;
SET LOCAL search_path TO mobile_capture;
CREATE TABLE IF NOT EXISTS recording_rooms (
 id uuid PRIMARY KEY, code text NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS room_participants (
 id uuid PRIMARY KEY, room_id uuid NOT NULL REFERENCES recording_rooms,
 source_label text NOT NULL CHECK (source_label IN ('A','B','C')),
 name text NOT NULL, token_hash text NOT NULL UNIQUE, is_host boolean NOT NULL DEFAULT false,
 mic boolean NOT NULL DEFAULT false, ready boolean NOT NULL DEFAULT false,
 error text, UNIQUE(room_id,source_label), UNIQUE(id,room_id)
);
CREATE TABLE IF NOT EXISTS recording_sessions (
 id uuid PRIMARY KEY, room_id uuid NOT NULL UNIQUE REFERENCES recording_rooms,
 status text NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting','preparing','countdown','recording','finalizing','completed','interrupted')),
 conditions jsonb NOT NULL DEFAULT '{}', starts_at double precision, started_at double precision,
 stopped_at double precision, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(id,room_id)
);
CREATE TABLE IF NOT EXISTS participant_recordings (
 session_id uuid NOT NULL, participant_id uuid NOT NULL, room_id uuid NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','prepared','recording','uploading','stored','failed','interrupted')),
 mime_type text, actual_started_at double precision, start_perf_ms double precision,
 stopped_at double precision, expected_chunks integer CHECK(expected_chunks>0),
 interrupted boolean NOT NULL DEFAULT false, error text,
 PRIMARY KEY(session_id,participant_id),
 FOREIGN KEY(session_id,room_id) REFERENCES recording_sessions(id,room_id),
 FOREIGN KEY(participant_id,room_id) REFERENCES room_participants(id,room_id)
);
CREATE TABLE IF NOT EXISTS audio_chunks (
 session_id uuid NOT NULL, participant_id uuid NOT NULL, chunk_index integer NOT NULL CHECK(chunk_index>=0),
 mime_type text NOT NULL, created_at double precision NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
 checksum text NOT NULL CHECK(checksum ~ '^[a-f0-9]{64}$'), audio_data bytea NOT NULL CHECK(octet_length(audio_data)>0 AND octet_length(audio_data)<=8388608),
 PRIMARY KEY(session_id,participant_id,chunk_index),
 FOREIGN KEY(session_id,participant_id) REFERENCES participant_recordings
);
CREATE TABLE IF NOT EXISTS audio_assets (
 session_id uuid NOT NULL, participant_id uuid NOT NULL, mime_type text NOT NULL,
 chunk_count integer NOT NULL CHECK(chunk_count>0), byte_count bigint NOT NULL CHECK(byte_count>0),
 checksum text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(session_id,participant_id), FOREIGN KEY(session_id,participant_id) REFERENCES participant_recordings
);
CREATE TABLE IF NOT EXISTS device_clock_observations (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 session_id uuid NOT NULL, participant_id uuid NOT NULL,
 client_sent_ms double precision NOT NULL, server_received_ms double precision NOT NULL,
 client_received_ms double precision NOT NULL, performance_ms double precision NOT NULL,
 FOREIGN KEY(session_id,participant_id) REFERENCES participant_recordings
);
CREATE TABLE IF NOT EXISTS audio_alignment_runs (
 id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES recording_sessions,
 status text NOT NULL, method text NOT NULL, offsets jsonb, evidence jsonb,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS analysis_results (
 id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES recording_sessions,
 result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS catalog_items (
 id uuid PRIMARY KEY, room_id uuid NOT NULL REFERENCES recording_rooms,
 kind text NOT NULL CHECK(kind IN ('machines','materials','tools','setups','presets')),
 name text NOT NULL, values jsonb NOT NULL, UNIQUE(room_id,kind,name)
);
COMMIT;
