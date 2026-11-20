BEGIN;
SET LOCAL search_path TO mobile_capture, public;
-- Additive V1.4 analysis extension. Public V1.2 shared-clock data stays readable.
ALTER TABLE participant_recordings ADD COLUMN requested_sample_rate integer CHECK(requested_sample_rate IN (44100,48000));
ALTER TABLE participant_recordings ADD COLUMN requested_channel_count integer CHECK(requested_channel_count IN (1,2));
CREATE TABLE recording_tracks (
 track_id uuid PRIMARY KEY, session_id uuid NOT NULL, device_id uuid NOT NULL,
 device_name text NOT NULL, channel_index integer NOT NULL CHECK(channel_index IN (0,1)),
 channel_label text NOT NULL CHECK(channel_label IN ('Mono','Left','Right')),
 source_channel_count integer NOT NULL CHECK(source_channel_count IN (1,2)),
 requested_sample_rate integer, original_sample_rate integer NOT NULL CHECK(original_sample_rate>0),
 actual_sample_rate integer NOT NULL CHECK(actual_sample_rate>0), analysis_sample_rate integer NOT NULL CHECK(analysis_sample_rate=44100),
 duration_seconds double precision NOT NULL CHECK(duration_seconds>0), total_frames bigint NOT NULL CHECK(total_frames>0),
 analysis_status text NOT NULL CHECK(analysis_status IN ('completed','failed','no_data')),
 UNIQUE(session_id,device_id,channel_index),
 FOREIGN KEY(session_id,device_id) REFERENCES audio_assets(session_id,participant_id),
 CHECK(channel_index<source_channel_count),
 CHECK((source_channel_count=1 AND channel_label='Mono') OR (source_channel_count=2 AND ((channel_index=0 AND channel_label='Left') OR (channel_index=1 AND channel_label='Right'))))
);
CREATE TABLE track_analysis_runs (
 id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES recording_sessions,
 fingerprint text NOT NULL, start_seconds double precision NOT NULL CHECK(start_seconds>=0),
 end_seconds double precision CHECK(end_seconds>start_seconds),
 status text NOT NULL CHECK(status IN ('queued','running','completed','partial','failed')),
 result jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(session_id,fingerprint)
);
CREATE INDEX track_analysis_queue ON track_analysis_runs(created_at) WHERE status='queued';
CREATE TABLE track_analysis_artifacts (
 run_id uuid NOT NULL REFERENCES track_analysis_runs, track_id uuid NOT NULL REFERENCES recording_tracks,
 kind text NOT NULL CHECK(kind IN ('spectrogram','mfcc','matrices')),
 content bytea NOT NULL, PRIMARY KEY(run_id,track_id,kind)
);
COMMIT;
