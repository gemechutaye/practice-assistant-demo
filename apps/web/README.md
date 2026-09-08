# Practice Assistant web application

The Next.js application is the human review surface for the Python assistant. It reads office state from the backend; it does not fabricate successful responses or maintain a second set of office records.

## Run

Use Node.js 22 or newer.

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Set `ASSISTANT_API_URL` to the Python service origin, without `/api`. Set the public Supabase URL and anonymous key. The anonymous key is a public client identifier; service keys and model keys belong only on the backend.

```sh
npm run typecheck
npm run build
npm run start
```

The production entry point is `npm run start`; Vercel uses the Next.js framework integration.

## Identity and requests

The browser creates a Supabase anonymous identity and sends its bearer token through the same-origin `/api/backend/` proxy. The backend verifies the identity and binds a fictional workspace to it. Selecting a demonstration role never changes ownership. The backend, not the interface, determines access.

`/api/config` returns only the public Supabase configuration and connection flags. No model credentials or privileged database keys are sent to the browser.

For local development only, `LOCAL_DEMO_AUTH=true` under `next dev` exposes an explicit local identity path. It requires the backend's separately gated `/api/dev-session`. Both the configuration flag and proxy route are disabled in production. The interface visibly identifies this mode.

## Working interface

- Today: actual readiness counts, paperwork deadlines, team decisions, and calendar records.
- Calendar: sorted dates, protected clinical events, and internal or recording events.
- Tasks: open/completed filtering and assistant-assisted assignment.
- Messages: searching, expanding, and preparing follow-up.
- Content: scripts, captions, assigned review, and cited source pages.
- Team: engineering progress and outstanding decisions.
- Memory: persistent preferences, explicit edits, and deletion.
- Sources: attributed public pages and clearly identified demonstration notes.
- Reports: counts computed from current records, task distribution, and saved report data.
- Assistant: resumable request history, live progress, exact proposed changes, approval, cancellation, error recovery, and a run inspector.

Voice requests are recorded only after the user presses Speak. Browser recordings are converted to mono PCM WAV before transcription. The transcript is placed in the composer for review before sending. Reading an answer aloud uses the backend speech endpoint.

Realtime workspace revision notifications trigger an authorized snapshot fetch. Private office tables are never queried directly from the browser. Periodic refresh and run polling keep the application usable if a Realtime connection is interrupted.
