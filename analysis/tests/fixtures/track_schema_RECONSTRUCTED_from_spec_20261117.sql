-- 重建的測試用 schema，不是網站的正式 migration。
--
-- 來源：《CNC Acoustic Lab｜外部音訊分析系統對接規格》（2026-11-17）第 4 節與第 6.1–6.3 節的文字描述。
-- 規格提到的正式檔案 backend/migrations/004_multi_recorder.sql、005_track_analysis.sql 不在這個儲存庫，
-- 也不在開發這支程式的電腦上，所以這裡照規格的欄位、型別、唯一鍵與外鍵重建，只供 analysis/tests 使用。
-- 拿到正式 migration 之後：用正式檔取代本檔重跑測試；欄位名稱、NOT NULL、CHECK 若有出入，以正式檔為準。
--
-- 套用順序：本儲存庫的 001_mobile_capture.sql → 002_room_lifecycle.sql → 003_recording_metadata.sql → 本檔。
BEGIN;
SET LOCAL search_path TO mobile_capture;

-- ── 規格第 4 節列出、但 001–003 沒有的輸入欄位（規格稱來自 004_multi_recorder）──────────────
ALTER TABLE recording_sessions ADD COLUMN machine_id uuid;
ALTER TABLE participant_recordings ADD COLUMN source_position integer;
ALTER TABLE participant_recordings ADD COLUMN requested_sample_rate integer;
ALTER TABLE participant_recordings ADD COLUMN requested_channel_count integer;
-- 規格 4：source_label「可能因退出而變成 NULL」
ALTER TABLE room_participants ALTER COLUMN source_label DROP NOT NULL;
-- 規格 5.1 的 take_id：同一個房間可以有多次錄音
ALTER TABLE recording_sessions DROP CONSTRAINT IF EXISTS recording_sessions_room_id_key;

-- ── 規格 6.1 ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE recording_tracks (
 track_id uuid PRIMARY KEY,
 session_id uuid NOT NULL,
 device_id uuid NOT NULL,
 device_name text NOT NULL,
 channel_index integer NOT NULL CHECK (channel_index IN (0, 1)),
 channel_label text NOT NULL CHECK (channel_label IN ('Mono', 'Left', 'Right')),
 source_channel_count integer NOT NULL CHECK (source_channel_count IN (1, 2)),
 requested_sample_rate integer,
 original_sample_rate integer NOT NULL CHECK (original_sample_rate > 0),
 actual_sample_rate integer NOT NULL CHECK (actual_sample_rate > 0),
 analysis_sample_rate integer NOT NULL CHECK (analysis_sample_rate = 44100),
 duration_seconds double precision NOT NULL CHECK (duration_seconds > 0),
 total_frames bigint NOT NULL CHECK (total_frames > 0),
 analysis_status text NOT NULL CHECK (analysis_status IN ('completed', 'failed', 'no_data')),
 UNIQUE (session_id, device_id, channel_index),
 FOREIGN KEY (session_id, device_id) REFERENCES audio_assets (session_id, participant_id),
 -- 規格 6.1：「Mono 只能 index=0；Stereo index=0 是 Left、index=1 是 Right」
 CHECK ((source_channel_count = 1 AND channel_index = 0 AND channel_label = 'Mono')
     OR (source_channel_count = 2 AND channel_index = 0 AND channel_label = 'Left')
     OR (source_channel_count = 2 AND channel_index = 1 AND channel_label = 'Right'))
);

-- ── 規格 6.2 ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE track_analysis_runs (
 id uuid PRIMARY KEY,
 session_id uuid NOT NULL REFERENCES recording_sessions,
 fingerprint text NOT NULL,
 start_seconds double precision NOT NULL CHECK (start_seconds >= 0),
 end_seconds double precision CHECK (end_seconds IS NULL OR end_seconds > start_seconds),
 status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'partial', 'failed')),
 result jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (session_id, fingerprint)
);

-- ── 規格 6.3 ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE track_analysis_artifacts (
 run_id uuid NOT NULL REFERENCES track_analysis_runs,
 track_id uuid NOT NULL REFERENCES recording_tracks,
 kind text NOT NULL CHECK (kind IN ('spectrogram', 'mfcc', 'matrices')),
 content bytea NOT NULL,
 PRIMARY KEY (run_id, track_id, kind)
);
COMMIT;
