-- 外部分析服務的最小權限帳號（對接規格 2026-11-17 第 10 節）。
-- 由資料庫管理者執行；可以重複執行。不含密碼：建立後用 \password track_analysis_writer 設定，並以安全管道交付。
-- 不要把 PostgreSQL 管理者帳號給外部分析服務使用。
--
-- 能做的事：
--   讀：錄音批次、房間代碼、各裝置錄音狀態、顯示名稱、封存紀錄、音段位元組
--   讀寫：recording_tracks、track_analysis_runs、track_analysis_artifacts（SELECT／INSERT／UPDATE）
-- 不能做的事（限 mobile_capture 這個 schema）：
--   改或刪任何原始錄音資料；讀 room_participants.token_hash；DELETE；在 mobile_capture 建表或改表
--
-- 這支腳本管不到的事，執行後請看最後印出的檢查結果：
--   1. 這個帳號在「其他 schema」原本就有的權限不會被收回（腳本只處理 mobile_capture）。
--   2. PostgreSQL 預設讓所有帳號（PUBLIC）在資料庫裡建立暫存表（TEMP）。這是整個資料庫的設定，
--      要關掉得由管理者決定：REVOKE TEMPORARY ON DATABASE <資料庫> FROM PUBLIC（會影響所有帳號）。
--   3. 這是整表權限，不會套用網站的房間隔離。外部服務若只能處理部分房間，需要另設受控 view 或服務 API。
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'track_analysis_writer') THEN
    CREATE ROLE track_analysis_writer LOGIN;
  END IF;
END
$$;
ALTER ROLE track_analysis_writer NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- 先收回以前給過的全部權限（含欄位權限），再重新授予，重跑時不會留下舊的多餘權限
REVOKE ALL ON ALL TABLES IN SCHEMA mobile_capture FROM track_analysis_writer;
REVOKE ALL ON SCHEMA mobile_capture FROM track_analysis_writer;

GRANT USAGE ON SCHEMA mobile_capture TO track_analysis_writer;

-- 輸入：只開必要欄位
-- 規格第 4 節另外列了 machine_id、started_at、stopped_at；目前程式沒有用到，所以不開。之後要用再加。
GRANT SELECT (id, room_id, status, created_at, conditions)
  ON mobile_capture.recording_sessions TO track_analysis_writer;
GRANT SELECT (id, code) ON mobile_capture.recording_rooms TO track_analysis_writer;
GRANT SELECT (session_id, participant_id, source_position, status, interrupted, sample_rate, channel_count,
              requested_sample_rate, requested_channel_count, duration_ms, expected_chunks)
  ON mobile_capture.participant_recordings TO track_analysis_writer;
GRANT SELECT (id, name) ON mobile_capture.room_participants TO track_analysis_writer;
GRANT SELECT (session_id, participant_id, mime_type, chunk_count, byte_count, checksum)
  ON mobile_capture.audio_assets TO track_analysis_writer;
GRANT SELECT (session_id, participant_id, chunk_index, audio_data, checksum)
  ON mobile_capture.audio_chunks TO track_analysis_writer;

-- 輸出：三張結果表；沒有 DELETE
GRANT SELECT, INSERT, UPDATE ON mobile_capture.recording_tracks TO track_analysis_writer;
GRANT SELECT, INSERT, UPDATE ON mobile_capture.track_analysis_runs TO track_analysis_writer;
GRANT SELECT, INSERT, UPDATE ON mobile_capture.track_analysis_artifacts TO track_analysis_writer;

-- 檢查：列出這個帳號在 mobile_capture 以外還有哪些權限（本腳本不會收回，請管理者判斷）
DO $$
DECLARE
  n_tables integer;
  n_schemas integer;
  can_temp boolean;
BEGIN
  -- 用「實際有效」的權限來數（包含經由 PUBLIC 或其他角色間接得到的），不只是直接授予這個帳號的
  SELECT count(*) INTO n_tables
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
     AND n.nspname NOT LIKE 'pg\_%' AND n.nspname NOT IN ('information_schema', 'mobile_capture')
     AND has_table_privilege('track_analysis_writer', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE');
  SELECT count(*) INTO n_schemas FROM pg_namespace n
   WHERE n.nspname NOT LIKE 'pg\_%' AND n.nspname <> 'information_schema'
     AND has_schema_privilege('track_analysis_writer', n.oid, 'CREATE');
  can_temp := has_database_privilege('track_analysis_writer', current_database(), 'TEMPORARY');
  IF n_tables > 0 THEN
    RAISE WARNING 'track_analysis_writer 在 mobile_capture 以外還能存取 % 張資料表或 view（含經由 PUBLIC 得到的權限），本腳本沒有收回', n_tables;
  END IF;
  IF n_schemas > 0 THEN
    RAISE WARNING 'track_analysis_writer 可以在 % 個 schema 建立物件（CREATE），本腳本沒有收回', n_schemas;
  END IF;
  IF can_temp THEN
    RAISE NOTICE 'track_analysis_writer 可以建立暫存表（資料庫對 PUBLIC 的預設權限）';
  END IF;
END
$$;
