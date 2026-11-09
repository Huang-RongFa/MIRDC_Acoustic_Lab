-- Run after creating tables and column comments (read-only).
-- 1) Expect 28 public base tables. Check the 28-table count manually against output.
SELECT count(*) AS table_count FROM information_schema.tables
 WHERE table_schema='public' AND table_type='BASE TABLE';

-- 2) Actual column counts by table (compare with 04_data_dictionary.md).
SELECT table_name, count(*) AS column_count
  FROM information_schema.columns WHERE table_schema='public'
 GROUP BY table_name ORDER BY table_name;

-- 3) Audio session records (returns empty before first recording).
SELECT session_id, machine_id, capture_device_id, status, channel_count,
       sample_rate_hz, sample_format, started_at, finished_at, total_frames
  FROM recording_sessions ORDER BY created_at DESC LIMIT 50;

-- 4) Flag sessions lacking exactly three A/B/C mappings (prepared sessions may be incomplete).
SELECT s.session_id, s.status, count(c.channel_no) AS configured_channels,
       array_agg(c.source_label ORDER BY c.channel_no) FILTER (WHERE c.channel_no IS NOT NULL) AS channel_labels
  FROM recording_sessions s LEFT JOIN recording_channels c USING(session_id)
 GROUP BY s.session_id,s.status
 HAVING count(c.channel_no) <> 3;

-- 5) Find discontinuities in sequence of incoming audio frames (returns empty if complete).
WITH seq AS (
 SELECT session_id, chunk_index, first_frame, frame_count,
        LAG(first_frame + frame_count) OVER
          (PARTITION BY session_id ORDER BY first_frame) AS expected_first_frame,
        ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY first_frame) AS n
 FROM audio_chunks
)
SELECT * FROM seq WHERE (n=1 AND first_frame <> 0)
  OR (n>1 AND first_frame <> expected_first_frame)
ORDER BY session_id, first_frame;

-- 6) Check interleaved PCM payload sizes, already constrained by CHECK.
SELECT session_id, chunk_index, octet_length(pcm_data) AS actual_bytes,
       frame_count*channel_count*(CASE WHEN sample_format='pcm_s16le' THEN 2 ELSE 3 END) AS expected_bytes
  FROM audio_chunks
 WHERE octet_length(pcm_data) <> frame_count*channel_count*(CASE WHEN sample_format='pcm_s16le' THEN 2 ELSE 3 END);
