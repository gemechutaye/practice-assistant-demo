CREATE TABLE IF NOT EXISTS pa_runs (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
 user_id text NOT NULL, role text NOT NULL, message text NOT NULL,
 status text NOT NULL DEFAULT 'queued', answer text NOT NULL DEFAULT '', error text,
 plan_id uuid, route text, selected_model text, cancelled boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pa_runs_workspace ON pa_runs(workspace_id,created_at DESC);
CREATE TABLE IF NOT EXISTS pa_jobs (
 id uuid PRIMARY KEY, run_id uuid NOT NULL UNIQUE REFERENCES pa_runs(id) ON DELETE CASCADE,
 workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'queued', lease_generation integer NOT NULL DEFAULT 0,
 lease_until timestamptz, available_at timestamptz NOT NULL DEFAULT now(), attempts integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pa_jobs_claim ON pa_jobs(status,available_at,lease_until);
CREATE TABLE IF NOT EXISTS pa_steps (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES pa_runs(id) ON DELETE CASCADE,
 workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
 kind text NOT NULL, title text NOT NULL, detail jsonb NOT NULL DEFAULT '{}', status text NOT NULL DEFAULT 'completed',
 duration_ms integer NOT NULL DEFAULT 0, model text, tokens integer, cost numeric, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pa_steps_run ON pa_steps(run_id,created_at);
CREATE TABLE IF NOT EXISTS pa_outbox (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
 user_id text NOT NULL, role text NOT NULL, event_key text NOT NULL, payload jsonb NOT NULL,
 status text NOT NULL DEFAULT 'queued', created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(workspace_id,event_key)
);
CREATE TABLE IF NOT EXISTS pa_usage (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
 category text NOT NULL, usage jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE pa_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_usage ENABLE ROW LEVEL SECURITY;
CREATE SCHEMA IF NOT EXISTS pa_checkpoint;
REVOKE ALL ON SCHEMA pa_checkpoint FROM PUBLIC;
