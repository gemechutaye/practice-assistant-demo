# Shared implementation contract

Build authorized September 8, 2026. This is an independent practice assistant using fictional office records and attributed public information. All user-facing language is plain English.

## Ownership

- Root: FastAPI routes, live OpenRouter agent, durable run coordination, MCP, deployment integration, end-to-end acceptance.
- Backend specialist: `services/assistant/store.py`, `domain.py`, `seed.py`, `supabase/migrations/`, domain/storage tests. Do not edit root files.
- Frontend specialist: `apps/web/` only, complete Next.js interface and browser-facing client. No secrets in frontend.
- Infrastructure specialist: read-only account discovery and dedicated cloud provisioning, coordinate credentials privately. No existing production changes. Own `infra/` and deployment docs when requested.

## Python module boundary

Package `services.assistant`. Python 3.12. PostgreSQL is authoritative. `DATABASE_URL` connection string; `OPENROUTER_API_KEY`; `SUPABASE_URL`; `SUPABASE_ANON_KEY`; optional server `SUPABASE_SERVICE_ROLE_KEY`. Root handles environment loading and HTTP auth. Every domain/storage function receives an `Actor(workspace_id: str, user_id: str, role: str)` object from `domain.py`; roles doctor/coordinator/editor. Never trust model arguments for identity.

Implement `Store(database_url: str)`, `migrate()`, `create_workspace(user_id: str) -> str`, `get_actor(workspace_id: str,user_id: str,role: str) -> Actor`, `snapshot(actor) -> dict`, `reset_workspace(actor) -> dict`.

Use a small typed records system: `office_records(id text, workspace_id uuid, kind text, data jsonb, version integer, updated_at timestamptz)`. `kind`: event, task, message, patient_admin, content, engineering, report. Every returned record `{id,kind,version,...data}`. Domain validation restricts allowed fields/kinds; record kinds are not arbitrary user-created tables.

Use namespaced `pa_` table names to avoid collision, dedicated Supabase project preferred. Migrations additive/idempotent. RLS on browser-accessible records; no unrestricted anonymous table access. Root will use DB connections with explicit Actor checks. Supabase Auth identities map to workspace membership. Workspace ownership ties actual user ID to an isolated fictional office; demo role switching only within owned workspace.

## Snapshot shape

`{workspace_id,role,clock:"2026-09-08T08:15:00-07:00",doctor_name:"Dr. Avery Morgan",events:[],tasks:[],messages:[],patient_admin:[],content:[],engineering:[],reports:[],preferences:[],sources:[],stats:{open_tasks:number,needs_attention:number,content_in_review:number}}`

Events: id,title,start,end,event_type(patient/internal/recording),owner,version.
Tasks: id,title,owner,status(open/completed),due_at,related_record_id,version.
Messages: id,subject,body,sender,recipient,status,version.
Patient_admin: id,patient_name,appointment_id,paperwork_status(missing/complete),version.
Content: id,title,script,caption,status(draft/in_review/approved),reviewer,source_ids,version.
Engineering: id,title,status,owner,summary,decision_needed,version.
Preferences: id,key,value,version.
Sources: id,title,url,excerpt,accessed_at,provenance(public/demo),version.

Seed IDs stable within a workspace. Include one tomorrow 09:00 appointment, missing paperwork due in45min today, another completed paperwork case; engineering meeting conflicts with clinic; engineering updates; public policy and pricing source notes; content draft. Dates stored timezone-aware. Editor snapshot omits patient_admin, private messages, patient events, engineering; sources public only, content and recording events visible. Coordinator cannot modify personal preferences or move protected patient appointments. Reports computed from actual records.

## Domain functions to implement

`read_tool(store,actor,name,args)->dict` for get_schedule, get_preparation_status, find_messages, get_open_tasks, get_engineering_updates, get_preferences, get_report, get_content. Read tools return fresh state and versions, handle missing IDs.

`propose_plan(store,actor,run_id,actions:list[dict],summary:str)->dict` stores immutable revision and expected versions; no writes until approval. Action shape `{kind:"move_meeting"|"create_task"|"deliver_demo_message"|"save_preference"|"create_content"|"create_recording"|"save_report",payload:{...}}`. Store enriches IDs, expected versions, calendar revision, approval expiry. Validate roles and payload before saving. Return `{id,run_id,status:"pending",summary,actions:[{id,kind,payload,status:"proposed"}],expires_at}`.

`approve_plan(store,actor,plan_id)->dict` checks owner/role/expiry and marks plan approved; `execute_plan(store,actor,plan_id)->dict` rechecks preconditions and executes per-action with receipts. Unique stable operation IDs prevent duplicates. Calendar conflict must check relevant calendar state, not only event version. No patient appointment mutations. Return current plan; stale status requires new plan. No global transaction guarantee across actions; commit mutation + receipt per action. Error injection modes root can set through scenario.

`apply_scenario(store,actor,scenario:str)->dict`: paperwork_complete, occupy_proposed_slot, task_timeout_after_write, reset_failure, content_reviewed. Idempotent follow-up closes only linked prep task; duplicate incoming events don't duplicate effects. Office writes only this demo workspace.

`save_preference` handled approved action; expose edit/delete endpoint via root after explicit request. Storage methods for root SQL should use `store.connection()` context manager yielding psycopg connection with dict_row.

## Root-owned run tables and orchestration

Root adds migration 002 for runs, jobs, tool traces, vectors, LangGraph checkpoints as needed. Separate worker claims jobs/renews lease and resumes. Root uses `Store` connection to persist run data. Domain owns plans/actions migrations.

## Browser API contract

Next.js proxy `/api/backend/[...path]` -> Python API origin `ASSISTANT_API_URL`; forward Authorization Bearer token. Browser Supabase Auth obtains anonymous user JWT using public `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Backend validates Supabase identity. First-load anonymous sign-in supports easy demo; provide honest unavailable/error state if config/auth unavailable. Never hardcode fake success.

All Python endpoints prefixed `/api`:

- POST `/session` `{workspace_id?:str,role:"doctor"|"coordinator"|"editor"}` -> `{workspace_id,role,snapshot}`. If existing workspace owned, switch permitted demo role. Header `X-Workspace-Id`, `X-Demo-Role` on later requests resolved against ownership.
- GET `/snapshot` -> snapshot above.
- POST `/runs` `{message:str}` -> `{id,status:"queued"}`.
- GET `/runs` -> `{runs:[{id,message,status,answer,created_at,plan_id}]}`.
- GET `/runs/{id}` -> `{id,message,status,answer,plan,steps:[{id,kind,title,detail,status,duration_ms,model,tokens,cost}],usage:{tokens,cost,latency_ms},error}`. statuses queued/running/awaiting_approval/completed/partial/failed/cancelled. Poll every 1s while active; persist/reconnect. Sources from snapshot link to output references.
- POST `/runs/{id}/cancel` -> run.
- POST `/plans/{id}/approve` -> `{id,status}` then poll run.
- POST `/scenarios` `{scenario}` -> updated snapshot.
- POST `/preferences/{id}` `{value}`; DELETE `/preferences/{id}` -> snapshot.
- POST `/reset` -> snapshot, clears prior runs in workspace.
- POST `/voice/transcribe` multipart audio -> `{text}`.
- POST `/voice/speak` `{text}` -> audio/mpeg.
- GET `/health` -> `{status,version}`.

Errors JSON `{detail:string,code?:string}`. UI surfaces errors and retry; buttons disabled when pending. No claims real external emails, employer connection, clinical advice or measured impact. Demonstration label always visible. A source explains public vs fictional information.

## UI target

Polished calm physician work console, responsive, warm off-white/dark-ink/teal accent, deliberate typography, clear whitespace. Working home brief with three suggested requests, central voice/text composer, attention items, approval pane, activity history. Sidebar views Today, Calendar, Tasks, Messages, Content, Team, Memory, Sources, Reports. Role switch and scenario controls in clearly labeled Demo controls; run inspector separate from everyday interface. All views backed by API state. No decorative charts or unconnected widgets.
