# Practice Assistant — access and verified results

Open [Practice Assistant](https://practice-assistant-demo.vercel.app). The [source repository](https://github.com/gemechutaye/practice-assistant-demo) is public and contains the application, migrations, tests, container configuration, and measured evidence.

## Current operating status

The Vercel frontend, Render API, and dedicated Supabase project are live. Supabase anonymous identity, PostgreSQL, pgvector, private evidence storage, and owner-scoped Realtime have been verified.

The API and worker now run as separate supervised processes in **one free Render web service**. The laptop workers were stopped before three fresh end-to-end cloud workflows passed. No paid worker or payment method is required for this deployment. Model calls use your funded OpenRouter credit.

Render may put the free service to sleep after 15 minutes without inbound traffic. Both processes pause; a visitor or real webhook wakes them. Allow about a minute for a cold start. The interface retries readiness checks and shows its startup state without automatically replaying writes. Supabase retains records, queued jobs, checkpoints, and receipts. This is an independently cloud-hosted demonstration, with unattended processing paused while the service sleeps.

Coolify was checked: its free offer is self-hosted software requiring your own server. Its Cloud service starts at $5/month and also requires your own server. The delivered Render configuration avoids that additional infrastructure. See [Coolify pricing](https://coolify.io/pricing) and [Render's free-service limits](https://render.com/docs/free).

## What works

| Capability | Implemented behavior and evidence |
| --- | --- |
| Physician assistant | Open requests lead to actual model-selected tools, current office reads, and proposed actions. |
| Clinic preparation | Code computes the 45-minute fictional paperwork deadline; existing tasks are reused and patient appointments remain fixed. |
| Engineering coordination | Reads team decisions and messages; meeting changes must fit calendar constraints and confirmed attendee windows. |
| Content workflow | Real public-source retrieval, a restricted drafting specialist, script/caption, assigned review task, and approved recording holds. |
| Approval | Immutable action payloads, expiry, role checks, record/source versions, and fresh approval after replanning. |
| Recovery | Persistent LangGraph checkpoints, worker leases, per-action receipts, partial completion, cancellation, and retry without duplicate committed effects. |
| Memory | Confirmed preferences persist between requests and can be inspected, edited, or deleted. |
| Retrieval | Live OpenRouter embeddings, 1,536 dimensions, pgvector similarity plus PostgreSQL text ranking, and source citations. |
| Voice | Hosted Whisper transcription into an editable composer and hosted Kokoro audio output; real browser playback verified. |
| MCP and handoffs | Real MCP stdio tools use the authenticated API. Typed synthetic events drive target-specific paperwork/review follow-up. |
| Operational views | Nine working views for office state, source provenance, tasks, content, engineering, memory, and database-backed reports. |
| Evidence and monitoring | Run traces, provider/model metadata, reported tokens and costs, measured model/retrieval time, OpenTelemetry spans, and private exports with ten-minute links. |
| Isolation | Independent Supabase identities and workspaces; server-side role restrictions, browser database restrictions, and owner-only live updates. |

## Verification

- 125 automated tests passed using real local PostgreSQL and actual supervisor child processes, with no failures, errors, or skipped tests. External HTTP responses are mocked in deterministic adapter tests; live provider tests are reported separately.
- All three primary workflows ran through the real browser UI and wrote approved results to PostgreSQL. Three fresh workflows then passed through public Vercel → Render → Supabase → OpenRouter with both laptop workers stopped. The cloud tests checked preparation and memory, public content review, and a conflicting meeting slot requiring fresh approval; known model cost was $0.076842 for this three-case check.
- A changed engineering slot triggered a fresh approval at 14:30–15:00, within confirmed 14:00–15:00 availability. Patient appointments and existing tasks remained intact.
- Render logs correlated all three new runs with the hosted worker. The largest memory sample during the test window was 142.62 MiB against a 512 MiB limit; this is an observation, not a load-capacity guarantee.
- A real Render restart started both processes again. All three completed runs retained identical plans, action receipts, and answers when reloaded through the public API.
- A real executor subprocess was killed with SIGKILL immediately after its first committed action. A replacement obtained lease generation 2 and finished with exactly one task, one message, and two receipts.
- The MCP transport listed nine tools; a doctor could read the computed preparation deadline, an editor was denied that information, and invalid argument types were rejected.
- Hosted voice input/output, six real source vectors, and an actual OpenTelemetry span passed live capability checks.
- Real browser audio playback loaded a 77,352-byte MP3, decoded 11.67 seconds of audio, advanced playback time, and stopped through the UI.
- Supabase REST and WebSocket checks rejected another identity's workspace and withheld its updates. Production local-development sign-in is disabled.
- A signed evidence export downloaded successfully from private Supabase storage. Source-availability results persisted honestly, including unavailable pages.
- After the actual Render restart, a fresh public browser identity opened all nine views and completed one new read-only model request. Its answer matched the three displayed tasks; no action plan was created. Both public videos and the PDF returned HTTP 200, and the product video played in the browser.
- The GitHub CI run verified Python checks, the frontend production build, and the Docker build. Final run-specific evidence is in the repository's `artifacts/verification/` directory.

The small routing comparison used three paired requests. Both models chose the expected route in all six calls. It reports actual cost/latency; it is not a general performance or accuracy claim. Missing provider charges are marked unknown, not zero. External OTLP collector delivery was not tested. Automated speech-input checks used synthetic audio; physical recording from your room’s microphone was not part of the automated test.

## Application materials

- [Product walkthrough — 1:48](https://practice-assistant-demo.vercel.app/materials/practice-assistant-demo.mp4)
- [Technical walkthrough — 3:22](https://practice-assistant-demo.vercel.app/materials/technical-walkthrough.mp4)
- [Six-page engineering case study](https://practice-assistant-demo.vercel.app/materials/case-study.pdf)
- [Source, tests, and verification evidence](https://github.com/gemechutaye/practice-assistant-demo)

The output folder also contains a timestamp guide, a demonstration guide, the source archive, and a follow-up email draft. Nothing has been sent to the employer.

The case study is an engineering demonstration, not a clinical research paper. The implementation was AI-assisted. Rehearse the code walkthrough so that you can explain the decisions and limitations in your own words.

## Connection boundaries

The demonstration uses fictional Dr. Avery Morgan and fictional office records. It is independent of Dr. Emer and EmerGPT. Real email, calendars, CRM/EMR systems, and social accounts are represented by persistent demonstration services and explicit API contracts; no private employer integration is claimed. Public-source notes are attributed and dated. URL availability checks do not update the reviewed notes or verify clinical claims.

There is no clinical decision support, treatment recommendation, HIPAA certification, real patient data, or automated external message delivery. Demo role switching is for exploring permission behavior inside one visitor's workspace; real staff provisioning is not part of this release.
