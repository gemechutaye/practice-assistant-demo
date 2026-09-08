-- Structured fixture availability is enforced alongside calendar conflicts.
-- Existing office state remains intact; old plans become stale through versioning.
UPDATE pa_office_records
SET data = data || '{"attendee_availability":[{"start":"2026-09-09T11:00:00-07:00","end":"2026-09-09T12:00:00-07:00"},{"start":"2026-09-09T14:00:00-07:00","end":"2026-09-09T15:00:00-07:00"}]}'::jsonb,
    version = version + 1
WHERE id = 'engineering-sync' AND kind = 'event' AND NOT data ? 'attendee_availability';
