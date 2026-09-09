# Practice Assistant

A working, independent demonstration built by Gemechu Taye for a physician-facing AI systems role. It coordinates a fictional doctor's calendar, administrative preparation, content review, reporting, and engineering follow-up. It uses attributed public information about Dr. Emer's practice; it has no connection to the practice's private systems or EmerGPT.

The assistant selects tools through live hosted models, proposes exact changes, waits for approval, then verifies stored results. If the office changes, it rereads the records and asks for approval of a new plan. If a response is interrupted after a write, it resumes from durable receipts without duplicating the effect.

[Open the live demo](https://practice-assistant-demo.vercel.app) · [Watch the product walkthrough](https://practice-assistant-demo.vercel.app/materials/practice-assistant-demo.mp4) · [Watch the code walkthrough](https://practice-assistant-demo.vercel.app/materials/technical-walkthrough.mp4)

Read the [six-page engineering case study](docs/case-study.pdf) for the design, measured evidence, and boundaries. The free demo starts on demand; allow about a minute when the server has been idle. It preserves records and jobs in Supabase, and pauses unattended work while the service sleeps. Model calls use funded OpenRouter credit.

The [release guide](docs/RELEASE.md) records what works, what was tested and the connection boundaries. The [walkthrough guide](docs/WALKTHROUGHS.md) gives timestamps and explains what each recording demonstrates.

## Try these workflows

- **Prepare tomorrow:** inspect protected clinic appointments, calculate the paperwork deadline, reuse existing tasks, and prepare useful follow-up.
- **Create public content:** retrieve source notes, draft a script and caption, assign a review, and find a safe recording slot.
- **Coordinate engineering:** read current updates, identify decisions, and prepare a concrete follow-up using team availability.

The Demo controls can complete paperwork, occupy a proposed time, interrupt a write after it commits, and complete a content review. Open the run inspector for model calls, tools, costs, approvals, and saved receipts.

## Architecture

- Next.js 15, React 19, and TypeScript frontend on Vercel.
- Python 3.12, FastAPI, and a durable worker as supervised processes in one free Render web service.
- Supabase anonymous identity, PostgreSQL, pgvector, Realtime, and private evidence storage.
- OpenRouter: Google for routing, OpenAI for planning and embeddings, Anthropic for public content, and hosted audio input/output.
- LangGraph with PostgreSQL checkpoints; database leases and fencing coordinate worker ownership.
- An MCP stdio server uses the same authenticated HTTP boundary.
- OpenTelemetry spans, measured provider usage, per-run limits, and a bounded application spending budget.

Every visitor owns a separate fictional workspace. Role switching is a demonstration feature within that workspace. It is not enterprise staff identity management. This application does not diagnose, provide treatment recommendations, send real email, or claim HIPAA compliance.

## Run locally

Install Python 3.12, uv, Node.js 20+, and Docker. Keep the model key in an ignored local environment file.

```sh
cp .env.example .env
```

For local development, set `DATABASE_URL=postgresql://practice:practice-local-only@127.0.0.1:55432/practice_assistant`, supply your `OPENROUTER_API_KEY`, and set `ENVIRONMENT=local`. Add a random `LOCAL_AUTH_SECRET` (for example, generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`). Supabase values can be blank when using local identity; private exports then report storage unavailable until configured.

```sh
export ENV_FILE="$PWD/.env"
docker compose up -d database
uv sync --frozen
uv run python -m services.assistant.migrate
uv run uvicorn services.assistant.api:app --port 8100
# Separate terminal, with the same ENV_FILE:
uv run python -m services.assistant.worker
# Separate terminal:
cd apps/web
npm ci
cp .env.example .env.local
# Add LOCAL_DEMO_AUTH=true to .env.local, then:
npm run dev
```

The Compose database uses a disposable local password and binds only to localhost. Hosted configuration requires Supabase Auth; local authentication is disabled in production by both the backend and frontend. The reference deployment instructions use separate API and worker processes.

See [deployment](docs/DEPLOYMENT.md), [architecture](docs/ARCHITECTURE.md), [verification](docs/VERIFICATION.md), and the [HTTP contract](docs/CONTRACT.md). Actual test evidence is in `artifacts/verification/`.

## Validation

```sh
TEST_DATABASE_URL=postgresql://USER@127.0.0.1:55432/postgres uv run pytest
uv run ruff check services tests scripts
cd apps/web && npm run build
```

Tests create and remove dedicated test databases. Use a PostgreSQL instance where that is allowed; do not point this command at an employer database. Live verification scripts call actual model services and report measured results separately from deterministic tests.

## Operational boundaries

The public-source notes are concise, attributed research snapshots. Checking a URL establishes reachability and a content fingerprint; it does not silently replace the reviewed note or certify current prices or policies. Exports use private Supabase storage and expire after ten minutes. A real practice deployment would require its own approved connectors, staff identity, contracts, security review, operational ownership, and validation of each workflow.
