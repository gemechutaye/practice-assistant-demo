CREATE TABLE IF NOT EXISTS pa_workspaces (
  id uuid PRIMARY KEY, user_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  clock timestamptz NOT NULL DEFAULT '2026-09-08 08:15:00-07', scenario jsonb NOT NULL DEFAULT '{}', revision bigint NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS pa_workspaces_user ON pa_workspaces(user_id);
CREATE TABLE IF NOT EXISTS pa_office_records (
  workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
  id text NOT NULL, kind text NOT NULL CHECK(kind IN ('event','task','message','patient_admin','content','engineering','report')),
  data jsonb NOT NULL, version integer NOT NULL DEFAULT 1 CHECK(version > 0),
  updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(workspace_id,id)
);
CREATE INDEX IF NOT EXISTS pa_records_kind ON pa_office_records(workspace_id,kind);
CREATE TABLE IF NOT EXISTS pa_preferences (
  workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
  id text NOT NULL, key text NOT NULL, value jsonb NOT NULL, user_id text NOT NULL,
  scope text NOT NULL DEFAULT 'doctor', version integer NOT NULL DEFAULT 1,
  source_request text NOT NULL DEFAULT 'Confirmed demonstration preference',
  updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,key)
);
CREATE TABLE IF NOT EXISTS pa_sources (
  workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
  id text NOT NULL, title text NOT NULL, url text NOT NULL, excerpt text NOT NULL,
  accessed_at timestamptz NOT NULL, provenance text NOT NULL CHECK(provenance IN ('public','demo')),
  version integer NOT NULL DEFAULT 1, data jsonb NOT NULL DEFAULT '{}', PRIMARY KEY(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS pa_plans (
  id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
  run_id text NOT NULL, user_id text NOT NULL, role text NOT NULL,
  status text NOT NULL DEFAULT 'pending', summary text NOT NULL, expires_at timestamptz NOT NULL,
  approved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), error text
);
CREATE INDEX IF NOT EXISTS pa_plans_workspace ON pa_plans(workspace_id,created_at DESC);
CREATE TABLE IF NOT EXISTS pa_actions (
  id uuid PRIMARY KEY, plan_id uuid NOT NULL REFERENCES pa_plans(id) ON DELETE CASCADE,
  position integer NOT NULL, kind text NOT NULL, payload jsonb NOT NULL, preconditions jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'proposed', result jsonb, error text, UNIQUE(plan_id,position)
);
CREATE TABLE IF NOT EXISTS pa_action_receipts (
  operation_id uuid PRIMARY KEY REFERENCES pa_actions(id) ON DELETE CASCADE,
  workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
  result jsonb NOT NULL, committed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pa_scenario_events (
  workspace_id uuid NOT NULL REFERENCES pa_workspaces(id) ON DELETE CASCADE,
  event_key text NOT NULL, result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(workspace_id,event_key)
);
ALTER TABLE pa_workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_office_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_action_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE pa_scenario_events ENABLE ROW LEVEL SECURITY;
-- Office records are served through the role-aware Python API. No anonymous or
-- authenticated browser grant can bypass the selected demonstration role.
-- Realtime may notify an owner that their workspace changed without exposing records.
DO $$ BEGIN
  IF to_regprocedure('auth.uid()') IS NOT NULL THEN
    EXECUTE 'DROP POLICY IF EXISTS pa_workspace_owner_read ON pa_workspaces';
    EXECUTE 'CREATE POLICY pa_workspace_owner_read ON pa_workspaces FOR SELECT TO authenticated USING (user_id = auth.uid()::text)';
  END IF;
END $$;
