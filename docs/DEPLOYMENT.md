# Deployment

The default demonstration uses a Next.js frontend on Vercel, separate Python API and worker processes supervised inside one free Render web service, and a dedicated Supabase project. These instructions describe the release configuration. A configuration file alone does not establish a live deployment; deployed URLs and verification results belong in the release report.

## Supabase

Create a dedicated project for the fictional demonstration. Enable anonymous sign-in under Authentication so an interviewer can start an isolated office without creating a personal account. The resulting identity owns only that office. Database rows must remain protected by RLS; the Python API applies the selected role on every request. Never point the demonstration at an existing production database.

The Python API and worker need `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `OPENROUTER_API_KEY`. Use a direct PostgreSQL connection or Supabase's **session** pooler on port 5432. The worker requires a persistent session for PostgreSQL checkpoints. Keep the service-role key server-side for private evidence exports. Use TLS for hosted database connections.

Run migrations against the dedicated project before starting the application processes:

```sh
uv run python -m services.assistant.migrate
```

The migrations are versioned in `supabase/migrations`. Public browser access must not grant unrestricted reads of office records. Changes to an office are served by the authenticated Python API.

After migration, include `public.pa_workspaces` in the `supabase_realtime` publication. Its owner-only SELECT policy permits revision notifications for the current anonymous identity. Keep office records outside direct browser access. Verify isolation with two anonymous sessions, including a direct REST request for the other session's workspace.

Create the private Storage bucket `practice-evidence` with a 10MB file limit. Allow JSON, PDF, Markdown, and plain text. Evidence objects use workspace-scoped paths and server-issued links. Do not create a public bucket or grant browser writes.

## Render: default free demonstration

Use `infra/render.yaml`. It declares one free web service, builds `infra/Dockerfile` from the repository root with the committed dependency lock, and starts `/app/infra/start.sh demo`. This command supervises separate API and worker processes inside the same container. The API binds to `0.0.0.0:$PORT`; the worker has no public port.

Both children share the dedicated database and model configuration. If either process exits, the supervisor stops the other and exits so the platform can restart the service. Shutdown signals are forwarded to both processes. The worker polls with a bounded idle backoff, so a newly queued request can take up to 15 seconds to start while the service is awake.

The free instance is suitable for this interactive demonstration. Render spins it down after 15 minutes without inbound traffic and wakes it on the next request; the documented wake-up is about one minute. **The worker also stops while the instance sleeps.** The interface waits and retries during wake-up. Supabase retains the jobs, checkpoints, records and receipts, so unfinished work can resume after the instance returns. There is no keepalive loop or promise of unattended, always-on processing. See [Render's free service limits](https://render.com/docs/free).

Provide `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` and `OPENROUTER_API_KEY` through Render's environment settings or its authenticated API. Do not commit them. The API and worker use the same configured model routes and limits. Automatic deployments remain disabled; deploy a tested source revision deliberately.

The free container has 512MB of memory. Models run through hosted APIs; the image does not install a local inference engine or download model weights. Verify actual service memory during complete workflows before calling the release healthy. Import-only measurements on a development machine do not establish cloud peak memory.

Before releasing the browser app, verify `/api/health`, `/api/ready`, anonymous identity validation, workspace creation, one queued run completed by the container's worker, and recovery after a process restart. Check the Render logs to establish that both supervised processes are running. A responding API alone does not establish worker health.

### Optional separate persistent worker

`infra/render-separate-worker.yaml` is an explicitly optional layout. It starts the API with `/app/infra/start.sh api` and creates a separately billed worker using `/app/infra/start.sh worker`. Do not apply this file for the default free demonstration.

The smallest persistent worker plan, `0.5c-512mb`, costs $7/month for 512MB RAM according to [Render pricing](https://render.com/pricing), checked September 8, 2026. It requires a payment method. This layout supports worker activity while the free API is idle; an always-on API would require its own appropriate compute plan. Use the same tested revision and private environment configuration for both services. Current plan identifiers are documented in the [Render Blueprint specification](https://render.com/docs/blueprint-spec).

### Updating an existing service

The documented service PATCH accepts the start-command change below. A separate deployment request is required for the change to take effect. See [Render service updates](https://api-docs.render.com/reference/update-service).

```json
{"serviceDetails":{"envSpecificDetails":{"dockerCommand":"/app/infra/start.sh demo"}}}
```

Use `GET /v1/metrics/memory` with the service ID in `resource`, ISO timestamps in `startTime` and `endTime`, and `resolutionSeconds` of at least 30. Read the unit returned with each time series. `GET /v1/metrics/memory-limit` exposes the corresponding limit. Metrics may lag a fresh deployment. See [Render memory metrics](https://api-docs.render.com/reference/get-memory).

## Vercel

Create a dedicated project with `apps/web` as its root. Configure:

| Variable | Visibility | Meaning |
|---|---|---|
| `ASSISTANT_API_URL` | Server only | New Render API origin, without `/api` |
| `NEXT_PUBLIC_SUPABASE_URL` | Public | Dedicated demo Supabase origin |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Public | Supabase public key, protected by RLS |

The browser sends its Supabase bearer token through the Next.js proxy. No OpenRouter key, database password, or Supabase service key belongs in Vercel's public variables or browser responses.

## Local reproduction

Create `.env` from the application's environment example, supplying the model key and the configured authentication service. Then run:

```sh
docker compose up --build
```

This starts a local pgvector database, applies migrations, and launches independent API and worker processes. It binds PostgreSQL to `127.0.0.1:55432` and the API to `127.0.0.1:8100`. Its fixed database password is only for this disposable loopback-bound development database. Hosted services must use generated credentials.

Run the frontend separately from `apps/web` with its API origin set to `http://127.0.0.1:8100`. Stop the local services with `docker compose down`. That command keeps the named database volume and the saved demonstration records.

## Release evidence

Record the deployed source revision and URLs, then verify three working user flows, reload persistence, role denial, stale approval rejection, and timeout-after-write recovery. Include actual model and tool traces. A reachable home page without a connected model, database, and worker is not a completed release.


## Existing server or Coolify

The API and worker are ordinary Docker processes. A server already owned by the operator can run only the worker while retaining the Vercel frontend, Render API, and Supabase data. Build the repository with `infra/Dockerfile`, use the private production environment values, and run `/app/infra/start.sh worker` with the container restart policy enabled. No public port or domain is needed for this outbound worker. Apply database migrations once before starting a new release.

Coolify can manage that container on an operator-supplied Linux server. Its self-hosted software is free, but server capacity is separate. Coolify Cloud starts at $5/month and also requires operator-supplied servers; it does not include free compute. See [Coolify pricing](https://coolify.io/pricing) and [installation requirements](https://coolify.io/docs/get-started/installation). No Coolify deployment is claimed in this release.
