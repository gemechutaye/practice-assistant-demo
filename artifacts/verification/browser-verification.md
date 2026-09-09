# Browser verification — September 8, 2026

These checks used the actual Next.js interface, Python API, persisted PostgreSQL records, and live model calls unless explicitly identified as simulated below. All office records are fictional. No employer-private systems or external recipients were involved.

## Public application and access

- Supabase anonymous sign-in created a private workspace. All nine navigation views loaded real API records without interface alerts.
- Two independent browser identities received different workspaces. Identity A requesting identity B’s snapshot returned HTTP 403. An unauthenticated snapshot returned 401.
- The public development-session endpoint returned 404. A separate production-server check with the local-auth environment flag enabled still returned `localAuth:false` and rejected the development endpoint.
- Content editor received zero private messages and zero patient-administration records. The interface explained the restriction. Doctor view was restored afterward.
- Desktop and mobile layouts were visually inspected. At 390×844, document width was exactly 390 pixels with no horizontal overflow.

## Working office flows

- Preparation produced a real demonstration-inbox message. Approval saved it and Messages read it back. The paperwork-arrival event completed the existing authorized preparation task; unrelated work stayed open.
- Content approval saved a sourced script/caption, a review task, a distinct production task, and a recording hold. Completing review closed the linked review task while preserving unfinished production work.
- An interrupted action persisted before timing out. Resume continued the original approved plan. Readback found exactly one instance of the intended task.
- Corrected scheduling test: the assistant proposed 14:00–14:30 inside confirmed 14:00–15:00 team availability. A new conflict invalidated that plan. Approval triggered fresh reads and a new approval for 14:30–15:00. The saved meeting was read back at that time; protected 09:00 and 10:00 patient appointments and the 11:00 recording hold remained unchanged. Existing engineering tasks were reused.
- A natural-language request saved an open-tasks-by-owner report and a persistent morning-brief preference. Both required approval, and the report and memory were read back in their respective views. Direct preference edits also survived reload.
- The inspector displayed actual model names, tokens, reported cost, activity, and saved execution receipts. Its processing-time label excludes queue and approval waits.

## Public drafting boundary

The mixed request checked administrative work and requested a public scar-pricing video. The dedicated `draft_content` call received only validated public source IDs, `video_script` format, and an explanatory angle. Its completed model step used Claude Sonnet 5 through Amazon Bedrock. No private office brief or preferences were passed to this separate drafting model. Approval created the cited content and Jamie Park’s linked review task. Both were read back from stored records.

## Voice, source checks, and export

- The browser played an actual 77,352-byte MP3 Blob with a decoded duration of 11.665501 seconds. The native audio element reached readyState 4, advanced its playback position, and stopped with the Stop reading control.
- Long responses respect the speech API’s 2,200-character limit and are labeled Read first part aloud. Empty audio receives an explicit retry message.
- A source availability check called the real public URL and persisted an unavailable result with a clear explanation that the dated research note remained unchanged.
- Run export created a private Supabase Storage download with ten-minute expiry. Download returned HTTP 200 and 21,057 bytes. Signed URLs and credentials are omitted from this report.

## Safe cold-start recovery

A fresh isolated browser context simulated three delayed 503 readiness responses. The Starting the demo server screen appeared. There were three read-only readiness GETs and **zero backend writes** before readiness succeeded. Retry connection then opened the workspace and restored the Connected indicator. Session setup ran once after readiness. A separate test returned 503 for the first readiness probe, then allowed the real endpoint: the second GET succeeded, the workspace opened automatically without a manual retry, and no writes occurred before readiness.

A separate simulated failure returned 503 for POST `/runs`. The browser sent that mutation **exactly once**. Its count remained one after 6.5 seconds and after an explicit read refresh. No model request was submitted by this test. Only readiness GETs are automatically retried; mutations are not replayed.

## Build and recording scope

TypeScript validation and the production build passed for the delivered interface. The product recording is a silent review of completed real requests and stored results in the local demonstration environment. The technical recording shows actual public GitHub files and saved verification artifacts, not a fresh test execution. Its regression artifact showed 118 tests at capture time; later release checks are reported separately.

Physical microphone capture from the user’s room was not used for automated browser verification. Browser recording conversion is implemented; backend speech recognition round-trip evidence is separate. Final cloud-only supervised-worker checks are recorded in the deployment verification artifacts.

## Final public browser verification after the Render restart

Verified on September 9, 2026 at 01:14:19 UTC (September 8 in Los Angeles), using a fresh isolated browser against `https://practice-assistant-demo.vercel.app/`. The UI release was `dpl_dV9pdg8KAs22MtWSAAaRPkhAEHDJ`. A real Render restart had been accepted; the backend verifier confirmed new API and worker child processes at 01:11:43 UTC, followed by health/readiness HTTP 200. Local workers remained stopped.

The initial browser snapshot showed the ordinary opening-workspace screen. By the next observation, the workspace was already ready. This visit therefore does **not** claim to have observed a prolonged cold-start screen. The deliberate readiness failure/recovery tests above cover that interface behavior separately.

- Public configuration returned `localAuth:false`, a configured backend, and public Supabase client configuration. The token used by the authenticated browser request identified a Supabase anonymous identity (`is_anonymous:true`, role `authenticated`); no token is retained in this report.
- Snapshot returned HTTP 200. All nine views opened without interface alerts: Today, Calendar, Tasks, Messages, Content, Team, Memory, Sources, and Reports.
- Exactly one request was submitted through the interface: “Read current open tasks and tell me how many each owner has. Do not make changes.”
- Run `b95fb29f-47c1-4385-9a9d-fba90053aab1` moved from queued to completed. It returned Alex Kim: 2, Sam Ortiz: 1, total: 3, matching the displayed task records. It produced no action plan and required no approval.
- Recorded activity showed Gemini 3.5 Flash Lite through Google selecting the report route, GPT 5.6 Terra through Azure selecting the read tool, `get_open_tasks` completing, and the final answer completing. The fresh request was processed after the real service restart with no local worker running.
- This single observed run reported 3,189 tokens, USD 0.005604 model cost, and 7.093 seconds of model/retrieval time. These measurements exclude queue waiting and are not an accuracy or performance benchmark.
- Final screenshots show the public task view and completed answer, plus the actual run inspector. No demonstration state was fabricated for these captures.

### Public materials

The public material URLs returned HTTP 200 with byte-range support:

| Material | Content type | Bytes at this check |
| --- | --- | ---: |
| `/materials/practice-assistant-demo.mp4` | video/mp4 | 3,780,558 |
| `/materials/technical-walkthrough.mp4` | video/mp4 | 15,846,740 |
| `/materials/case-study.pdf` | application/pdf | 484,255 |

The product video played from its public URL in a native browser video element: duration 108.208333 seconds, 1440×900 decoded dimensions, readyState 4, actively playing, with playback position advancing beyond 0.7 seconds. The temporary playback element was removed afterward. A later PDF-only update may replace the PDF at the same URL.
