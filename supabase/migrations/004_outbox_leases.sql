ALTER TABLE pa_outbox ADD COLUMN IF NOT EXISTS lease_generation integer NOT NULL DEFAULT 0;
ALTER TABLE pa_outbox ADD COLUMN IF NOT EXISTS lease_until timestamptz;
ALTER TABLE pa_outbox ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;
ALTER TABLE pa_outbox ADD COLUMN IF NOT EXISTS error text;
