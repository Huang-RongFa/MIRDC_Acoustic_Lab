-- 地端分析 worker 專用的最小權限帳號。由資料庫管理員在套用 migration 004 之後執行一次。
-- 密碼不寫在這裡：執行後用 psql 的 \password analysis_worker 設定，並只放在地端電腦的環境變數。
-- 連線請強制 TLS（sslmode=require），並在 pg_hba.conf 只允許地端電腦的對外 IP。
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='analysis_worker') THEN
    CREATE ROLE analysis_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END $$;
-- 帳號已存在時也重設成無特權，並先收回這幾張表的舊權限，避免沿用過去給過的權限
ALTER ROLE analysis_worker NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
REVOKE ALL ON ALL TABLES IN SCHEMA mobile_capture FROM analysis_worker;
GRANT USAGE ON SCHEMA mobile_capture TO analysis_worker;
-- 讀：找出已封存的音軌與音段。room_participants 只開 id 與聲源代號（不能讀 token_hash、姓名）
GRANT SELECT (id, source_label) ON mobile_capture.room_participants TO analysis_worker;
GRANT SELECT (session_id, participant_id, status) ON mobile_capture.participant_recordings TO analysis_worker;
GRANT SELECT ON mobile_capture.audio_assets, mobile_capture.audio_chunks TO analysis_worker;
-- 工作佇列：只能讀與改狀態，不能新增或刪除工作
GRANT SELECT ON mobile_capture.analysis_jobs TO analysis_worker;
GRANT UPDATE (status, attempts, worker_id, lease_expires_at, pipeline_version, code_commit, error, started_at, finished_at)
  ON mobile_capture.analysis_jobs TO analysis_worker;
-- 結果：只能新增
GRANT INSERT ON mobile_capture.analysis_results, mobile_capture.audio_alignment_runs TO analysis_worker;
COMMIT;
