BEGIN;
SET LOCAL search_path TO mobile_capture;
-- Cloud backend only writes; an on-premises worker claims jobs and writes results back.
-- The table is the only channel between them. See docs/analysis-worker.md.
CREATE TABLE analysis_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 session_id uuid NOT NULL REFERENCES recording_sessions,
 kind text NOT NULL DEFAULT 'multi_mic' CHECK(kind IN ('multi_mic')),
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
 max_attempts integer NOT NULL DEFAULT 3 CHECK(max_attempts>0),
 worker_id text,
 lease_expires_at timestamptz,
 pipeline_version text,
 code_commit text,
 error text CHECK(error IS NULL OR length(error)<=500),
 created_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz,
 finished_at timestamptz,
 CONSTRAINT running_job_has_lease CHECK(status<>'running' OR (worker_id IS NOT NULL AND lease_expires_at IS NOT NULL)),
 CONSTRAINT finished_job_has_time CHECK(status NOT IN ('completed','failed') OR finished_at IS NOT NULL)
);
-- At most one waiting or running job per session and kind. Re-runs after completion add a new row.
CREATE UNIQUE INDEX analysis_jobs_one_active ON analysis_jobs(session_id,kind) WHERE status IN ('queued','running');
CREATE INDEX analysis_jobs_claim_order ON analysis_jobs(created_at) WHERE status IN ('queued','running');
CREATE INDEX analysis_jobs_session ON analysis_jobs(session_id);

ALTER TABLE analysis_results ADD COLUMN job_id uuid REFERENCES analysis_jobs;
ALTER TABLE analysis_results ADD CONSTRAINT analysis_results_one_per_job UNIQUE(job_id);
ALTER TABLE audio_alignment_runs ADD COLUMN job_id uuid REFERENCES analysis_jobs;

-- SECURITY DEFINER: the backend role completing a session does not need INSERT on analysis_jobs,
-- so a missing grant can never make recording completion fail. search_path is pinned for safety.
CREATE FUNCTION enqueue_session_analysis() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=mobile_capture,pg_temp AS $$
BEGIN
 INSERT INTO analysis_jobs(session_id) VALUES(NEW.id) ON CONFLICT DO NOTHING;
 RETURN NEW;
END;
$$;
-- Enqueue in the same transaction that marks the session completed, so no completed session is missed.
CREATE TRIGGER session_completed_enqueue AFTER UPDATE OF status ON recording_sessions
 FOR EACH ROW WHEN (NEW.status='completed' AND OLD.status IS DISTINCT FROM 'completed')
 EXECUTE FUNCTION enqueue_session_analysis();

-- Backfill: sessions completed before this migration and never analysed.
INSERT INTO analysis_jobs(session_id)
SELECT s.id FROM recording_sessions s
WHERE s.status='completed' AND NOT EXISTS (SELECT 1 FROM analysis_results r WHERE r.session_id=s.id)
ON CONFLICT DO NOTHING;
COMMIT;
