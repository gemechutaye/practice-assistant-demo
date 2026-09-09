# Verification record

The evidence below was collected on September 8, 2026. Deterministic tests, actual hosted-model calls, local process recovery and hosted infrastructure checks are reported separately. Fictional office records and synthesized speech were used throughout. No employer system or private patient record was involved.

## Automated regression suite

The final full suite passed all 125 tests, with no failures, errors or skips. The test suite exercises real PostgreSQL reads, transactions, ownership, approval, versions, receipts, job recovery and event handling. Model/provider HTTP responses are mocked in deterministic adapter tests; the separate live checks exercise actual hosted models. The machine-readable [JUnit report](../artifacts/verification/pytest.xml) is the authoritative count and result for the latest run.

Coverage includes:

- Approval required before effects; repeat execution without duplicate writes; stale calendar, source and preference versions; expiry and exact role ownership.
- Calendar occupation, protected appointments, preparation time, attendee availability and rejection of a changed availability window after approval.
- Workspace and role isolation for tools, plans, run evidence, direct IDs and the public content route; private source IDs and arbitrary specialist briefs are refused.
- Source checking restricted to allowed URLs; private evidence storage and exact signed-path validation, including rejection of absolute or unrelated URLs.
- Queue recovery, lease generation changes, cancellation and exhaustion; old workers cannot commit after ownership changes.
- Real supervisor child processes verify sibling failure, signal propagation, forced shutdown and reaping; idle polling backs off without retrying private error payloads.
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

A separate [HTTP audio check](../artifacts/verification/http-audio.json) exercised the running local FastAPI service and the Next.js proxy with an authenticated disposable workspace. Both returned HTTP 200 and `audio/mpeg`: 24,456 bytes from the API and 24,288 bytes through the proxy. FFprobe decoded both responses as 3.25-second audio. This verifies the binary HTTP path. A separate real-browser check loaded a 77,352-byte MP3, reached readyState 4, and observed playback advancing to 1.22 seconds within an 11.6655-second response.

## Routing and MCP

The [routing comparison](../artifacts/verification/model-routes.json) contains three paired requests across Gemini and the OpenAI planner model. All six selected the expected content, report or planner route. It includes actual provider/model names, token counts, reported costs and measured latency. Three examples do not establish general routing accuracy or a statistically meaningful model ranking.

The [MCP result](../artifacts/verification/mcp.json) used a real stdio connection and the authenticated local HTTP API: nine tools were listed, the doctor received the computed 45-minute preparation deadline, the editor received a permission denial for that information, and a wrong argument type was rejected. MCP transport works against this application's services; it is not evidence of an employer MCP endpoint.

## Hosted infrastructure and release distinction

The [cloud infrastructure report](../artifacts/verification/cloud-infrastructure.json) records the checked API revision and separate Supabase/Render results: database TLS and persistent session behavior, anonymous identity, private evidence bucket, owner-only REST and Realtime access, blocked browser office-record reads, API health/readiness, workspace creation, reload persistence, missing-identity rejection and another session's workspace denial. Disposable fixtures were removed.

At the time of that report, the Render worker required an account payment method. That earlier billing requirement was removed by the later free combined-service deployment described below.

## Public-path workflow execution

The [hosted workflow report](../artifacts/verification/hosted-workflows.json) passed three real model-driven examples through `https://practice-assistant-demo.vercel.app/api/backend`, the Render API at revision `e02a8e5e657804d47043ff5e5a89dd068bee4c0b`, and hosted Supabase. **A temporary local worker processed the hosted queue; the paid Render worker was still awaiting billing setup.** These results establish the working public HTTP/database/model path, not an independently running cloud worker deployment.

| Case | Verified behavior |
|---|---|
| Preparation for tomorrow | Calculated the 45-minute paperwork deadline, reused the existing preparation task, preserved patient appointments, saved an approved internal meeting move and demonstration message, and saved/retrieved a concise-summary preference. A real queued handoff completed only the linked preparation task; an unrelated task stayed open. |
| Public content and review | An editor request used the actual Claude route, cited the public consultation-pricing source, saved a new draft in review, and assigned Jamie Park its linked review task. The editor snapshot contained no patient administration or engineering records. |
| Engineering coordination | The verifier occupied a proposed slot before approving its original plan. The original approval caused no meeting move. The worker prepared a distinct replacement, obtained a separate exact approval, and saved a different slot within confirmed attendee availability while preserving patient appointments. |

The total recorded cost was $0.076869, including a $0.01725 unapproved preliminary probe excluded from the three passing cases. That probe was interrupted because the verifier confused plan status (`pending`) with run status (`awaiting_approval`). A remaining verifier task-status assertion was corrected from `done` to the actual `completed` value, then the already-completed preparation case was rechecked through its saved identity without repeating its inference. These were verification harness corrections; the application required no runtime change for these checks.

The report preserves run IDs, exact proposed actions, actual model/usage records, committed action readbacks and per-case invariants. Anonymous identities are kept only in a private local file for recovery; no credentials enter the report. The three fictional workspaces remain available for evidence inspection. Three successful requests demonstrate these concrete flows and do not establish general model accuracy, throughput or continuous hosted availability.

```sh
uv run python -m scripts.verify_hosted_workflows --env-file /path/to/private/cloud.env
```

The verifier uses fresh anonymous sessions and a known-spending stop. Its `--resume-completed-preparation` option rechecks an already-completed first case from privately saved credentials, then continues the remaining two cases without a replacement preparation inference. Keep that credential file outside version control. The earlier worker placement is preserved here as historical provenance. The final free deployment and fresh cloud-only tests are recorded below.

## Practical limits

The demonstration supports administrative preparation, public drafting/review and engineering coordination with persistent, fictional office services. It does not claim real employer integration, external message delivery, clinical correctness, HIPAA certification, production load capacity, formal model privacy guarantees or comprehensive adversarial evaluation. Source reachability checks do not refresh the reviewed source notes. A production assessment would require approved connectors, real identities and operating conditions, plus a broader evaluation set drawn from the practice's authorized workflows.

## Final free cloud deployment

Three fresh workflows passed through the public Vercel proxy, Render API and supervised Render worker, Supabase and OpenRouter, with both temporary laptop workers stopped. The [cloud-only workflow report](../artifacts/verification/cloud-workflows.json) identifies API revision `fc692db36be80d8a361cf40c63d497b907235819`, three completed cases, and 19 passing checks. It records clinic preparation with persisted memory and linked-event handling; a sourced public draft assigned for review; and an engineering conflict that required a distinct plan and fresh approval before the valid calendar move. Known model cost for this check was $0.076842. These are functional examples, not a general accuracy benchmark.

The [cloud worker evidence](../artifacts/verification/cloud-worker.json) correlates the tested run IDs with Render's actual worker logs and records observed service memory: maximum sampled 142.62 MiB of the 512 MiB limit during the check. A real Render restart then started both child processes and preserved identical plans, receipts, and answers for all three completed runs. The database-backed queue, API and model calls operate independently of the laptop. Free Render compute sleeps after 15 minutes without inbound traffic; background processing pauses while asleep and resumes when a visitor or real webhook wakes the service. There is no artificial keepalive.

The [browser verification report](../artifacts/verification/browser-verification.md) distinguishes real UI/provider checks from simulated startup failures. Readiness checks retried safely; no mutations were sent before readiness, and a failed mutation was submitted exactly once. The short video reviews saved local demonstration results; the technical video shows the public source and the 118-test artifact that existed at capture time. The current regression result is 125 passing tests.
