# Deployment

The application uses a Next.js frontend on Vercel, a Python API and persistent worker on Render, and a dedicated Supabase project. These instructions describe the release configuration. A configuration file alone does not establish a live deployment; deployed URLs and verification results belong in the release report.

## Supabase

Create a dedicated project for the fictional demonstration. Enable anonymous sign-in under Authentication so an interviewer can start an isolated office without creating a personal account. The resulting identity owns only that office. Database rows must remain protected by RLS; the Python API applies the selected role on every request. Never point the demonstration at an existing production database.

The Python API and worker need `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `OPENROUTER_API_KEY`. Use a direct PostgreSQL connection or Supabase's **session** pooler; transaction pooling is unsuitable for sessions that rely on PostgreSQL checkpoint behavior. Keep the service-role key server-side if storage operations require it. Use TLS for hosted database connections.

Run migrations against the dedicated project before starting both services:

```sh
uv run python -m services.assistant.migrate
```

The migrations are versioned in `supabase/migrations`. Public browser access must not grant unrestricted reads of office records. Changes to an office are served by the authenticated Python API.

## Render

The Blueprint is `infra/render.yaml`. Set this path when creating the Blueprint. Both services build `infra/Dockerfile` from the repository root and use the committed dependency lock. Start commands are `api` and `worker` through `infra/start.sh`.

The configuration uses Render's free web-service plan and the smallest documented persistent worker plan, `0.5c-512mb`. The worker is billable. Confirm the current amount in the target account before provisioning. The web service may have a cold start; an always-on web plan can be selected when that cost is approved. Current plan identifiers are from the [Render Blueprint specification](https://render.com/docs/blueprint-spec).

Provide secrets through the Render environment form or its authenticated API. Never commit them to the Blueprint. The worker references the new API service's shared environment values, so both use the same dedicated database and model configuration. Automatic deployments are disabled until the first complete release is verified; release both services from the same tested revision.

The API binds to `0.0.0.0:$PORT` and exposes `/api/health`. The worker does not expose a public port. Before releasing the browser app, verify the API health response, anonymous identity validation, workspace creation, and one queued run completed by the worker.

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
