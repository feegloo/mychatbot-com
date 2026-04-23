-- 1. Kill idle / idle-in-transaction connections

-- Inspect first
SELECT pid, usename, application_name, state, state_change, query_start, wait_event, left(query, 120) AS query
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY state_change;

-- Terminate idle (and idle-in-transaction) connections older than 5 minutes
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND state IN ('idle', 'idle in transaction', 'idle in transaction (aborted)')
  AND state_change < NOW() - INTERVAL '5 minutes';


-- 2. Clear stuck processing jobs
  -- See what's stuck
SELECT conversation_id, file_name, status, step, retry_count,
       started_at, created_at, NOW() - COALESCE(started_at, created_at) AS age
FROM processing_jobs
WHERE status IN ('pending', 'running', 'retrying')
ORDER BY created_at DESC;

-- Mark stuck running/pending jobs as failed (older than 10 min)
UPDATE processing_jobs
SET status = 'failed',
    error_message = COALESCE(error_message, 'Manually cancelled - stuck'),
    completed_at = NOW()
WHERE status IN ('pending', 'running', 'retrying')
  AND COALESCE(started_at, created_at) < NOW() - INTERVAL '10 minutes';

-- Or fully delete non-terminal jobs for a specific conversation
DELETE FROM processing_jobs
WHERE conversation_id = '6jFJMR5MY6o8cRfF'
  AND status IN ('pending', 'running', 'retrying');

-- Nuke all non-terminal jobs (use with care)
DELETE FROM processing_jobs
WHERE status IN ('pending', 'running', 'retrying');

-- 3. Quick "reset" bundle for the stuck conversation in screenshot

BEGIN;

DELETE FROM processing_jobs
WHERE conversation_id = '6jFJMR5MY6o8cRfF'
  AND status IN ('pending', 'running', 'retrying');

-- then terminate any idle-in-tx holders
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND state LIKE 'idle%'
  AND state_change < NOW() - INTERVAL '2 minutes';

COMMIT;