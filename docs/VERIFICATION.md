# Verification record

The evidence below was collected on September 8, 2026. Deterministic tests, actual hosted-model calls, local process recovery and hosted infrastructure checks are reported separately. Fictional office records and synthesized speech were used throughout. No employer system or private patient record was involved.

## Automated regression suite

The final full suite passed all 118 tests, with no failures, errors or skips. The test suite exercises real PostgreSQL reads, transactions, ownership, approval, versions, receipts, job recovery and event handling. Model/provider HTTP responses are mocked in deterministic adapter tests; the separate live checks exercise actual hosted models. The machine-readable [JUnit report](../artifacts/verification/pytest.xml) is the authoritative count and result for the latest run.

Coverage includes:

- Approval required before effects; repeat execution without duplicate writes; stale calendar, source and preference versions; expiry and exact role ownership.
- Calendar occupation, protected appointments, preparation time, attendee availability and rejection of a changed availability window after approval.
- Workspace and role isolation for tools, plans, run evidence, direct IDs and the public content route; private source IDs and arbitrary specialist briefs are refused.
- Source checking restricted to allowed URLs; private evidence storage and exact signed-path validation, including rejection of absolute or unrelated URLs.
- Queue recovery, lease generation changes, cancellation and exhaustion; old workers cannot commit after ownership changes.
- Target-specific event handling, duplicate payload detection, repeated completion, review/task relationships and event lease fences across reset.
- Dedicated hosted audio request shape, explicit preset voice, raw MP3 handling, provider rejection, bounded transient retries and invalid transcript/audio responses.

Run the suite against disposable local PostgreSQL:

```sh
TEST_DATABASE_URL=postgresql://USER@127.0.0.1:55432/postgres uv run pytest tests --junitxml=artifacts/verification/pytest.xml
uv run ruff check services tests scripts
```

The fixture owns disposable workspaces and creates separate test databases for queue/API tests. The database account needs permission to create and drop these test databases. A Starlette/AnyIO deprecation warning in the test client is recorded; it does not change the test outcome.

## Physical process termination and recovery

The [crash report](../artifacts/verification/worker-crash.json) records a real subprocess killed with `SIGKILL`, exit code `-9`, immediately after the first action and its receipt committed. A test-owned connection wrapper pauses the process only after the real commit is visible. The replacement uses the normal job claim and executor after the actual two-second lease expires.

The verified result was one task, one demonstration message, two total action receipts, a completed plan and lease generation 2. The first effect was reconciled from its receipt. This checks approved-action execution across process death; it is not a claim that a model inference was killed mid-generation or that an external calendar vendor supports exactly-once delivery.

```sh
TEST_DATABASE_URL=postgresql://USER@127.0.0.1:55432/postgres uv run python -m scripts.verify_worker_crash
```

The script creates and removes its own database and makes no model calls.

## Actual hosted voice, retrieval and telemetry

The [live capability report](../artifacts/verification/live-capabilities.json) passed all four cases in 9.507 seconds, using seven hosted requests:

| Check | Observed result |
|---|---|
| Speech recognition | A 2.379-second locally synthesized WAV was transcribed as “Prepare tomorrow and check the missing paperwork.” |
| Spoken response roundtrip | Kokoro produced a playable 24,456-byte MP3; Whisper transcribed it as “Your demonstration calendar is ready for tomorrow.” |
| Real retrieval | Six source vectors were stored in PostgreSQL with pgvector 0.8.6 and 1,536 dimensions. The paperwork policy and consultation-pricing note each appeared first for their corresponding queries. |
| Telemetry | An actual Gemini request emitted a `model.complete` OpenTelemetry span with the requested/returned model, nine tokens and a measured 720ms duration. |

The sum of reported charges was $0.0000323. The speech endpoint did not return a charge, so that request is marked unknown rather than zero. This is a small functional check, not a latency benchmark or a full accounting statement. The script caps request count, output tokens and known spending. The initial attempted chat-audio route was blocked by the account's existing data policy; the replacement dedicated hosted routes succeeded without changing that policy. The released evidence retains the passing report; unsuccessful route probes are recorded in the build history.

```sh
uv run python -m scripts.verify_live_capabilities --env-file /path/to/private/models.env --database-url postgresql://USER@127.0.0.1:55432/postgres
```

The audio fixture is synthesized with macOS `say`; conversion uses FFmpeg or `afconvert`. The script never opens a microphone. It creates and removes a fictional workspace, uses the actual configured model key, and writes sanitized evidence. External OTLP collector delivery was not exercised; the successful span was observed through the in-process exporter.

A separate [HTTP audio check](../artifacts/verification/http-audio.json) exercised the running local FastAPI service and the Next.js proxy with an authenticated disposable workspace. Both returned HTTP 200 and `audio/mpeg`: 24,456 bytes from the API and 24,288 bytes through the proxy. FFprobe decoded both responses as 3.25-second audio. This verifies the binary HTTP path; browser playback is a separate UI check.

## Routing and MCP

The [routing comparison](../artifacts/verification/model-routes.json) contains three paired requests across Gemini and the OpenAI planner model. All six selected the expected content, report or planner route. It includes actual provider/model names, token counts, reported costs and measured latency. Three examples do not establish general routing accuracy or a statistically meaningful model ranking.

The [MCP result](../artifacts/verification/mcp.json) used a real stdio connection and the authenticated local HTTP API: nine tools were listed, the doctor received the computed 45-minute preparation deadline, the editor received a permission denial for that information, and a wrong argument type was rejected. MCP transport works against this application's services; it is not evidence of an employer MCP endpoint.

## Hosted infrastructure and release distinction

The [cloud infrastructure report](../artifacts/verification/cloud-infrastructure.json) records the checked API revision and separate Supabase/Render results: database TLS and persistent session behavior, anonymous identity, private evidence bucket, owner-only REST and Realtime access, blocked browser office-record reads, API health/readiness, workspace creation, reload persistence, missing-identity rejection and another session's workspace denial. Disposable fixtures were removed.

At the time of that report, the Render worker required an account payment method. That infrastructure report explicitly does not establish queued-agent completion. The final release report must name the deployed revision and verify the live worker's main flows before describing the hosted application as complete. Local verification remains valid independently of hosting status.

## Practical limits

The demonstration supports administrative preparation, public drafting/review and engineering coordination with persistent, fictional office services. It does not claim real employer integration, external message delivery, clinical correctness, HIPAA certification, production load capacity, formal model privacy guarantees or comprehensive adversarial evaluation. Source reachability checks do not refresh the reviewed source notes. A production assessment would require approved connectors, real identities and operating conditions, plus a broader evaluation set drawn from the practice's authorized workflows.
