"""Authenticated application boundary. No provider secret reaches the browser."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import logging
import os
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, Depends, Header, UploadFile, File
from fastapi.responses import JSONResponse, Response
import jwt
from pydantic import BaseModel, Field, ConfigDict
from psycopg.types.json import Jsonb

from .auth import Identity
from .config import settings
from .domain import Actor, DomainError, approve_plan, read_tool, apply_scenario
from .jobs import Jobs, serial
from .knowledge import Knowledge
from .model_router import Models, ModelError
from .store import Store
from .evidence import export_run, check_source

log = logging.getLogger("practice_assistant.api")
app = FastAPI(
    title="Practice Assistant",
    version="0.1.0",
    description="Independent demonstration using fictional office records and attributed public information.",
)


@lru_cache
def services():
    cfg = settings()
    store = Store(cfg.database_url)
    models = Models(cfg)
    return store, Jobs(store), models, Identity(cfg)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionInput(Input):
    workspace_id: UUID | None = None
    role: Literal["doctor", "coordinator", "editor"] = "doctor"


class RunInput(Input):
    message: str = Field(min_length=1, max_length=4000)


class ScenarioInput(Input):
    scenario: Literal[
        "paperwork_complete",
        "occupy_proposed_slot",
        "task_timeout_after_write",
        "reset_failure",
        "content_reviewed",
    ]


class PreferenceInput(Input):
    value: str = Field(min_length=1, max_length=2000)


class SpeechInput(Input):
    text: str = Field(min_length=1, max_length=2200)


class ToolInput(Input):
    name: str = Field(min_length=1, max_length=60)
    arguments: dict = Field(default_factory=dict)


class HandoffInput(Input):
    event_id: str = Field(min_length=1, max_length=100)
    event_type: Literal["paperwork_completed", "content_reviewed"]
    source_system: Literal["practice-demo"] = "practice-demo"
    record_id: str = Field(min_length=1, max_length=150)


def identity(authorization: str | None = Header(default=None)) -> str:
    return services()[3].user_id(authorization)


def actor(
    user_id: str = Depends(identity),
    x_workspace_id: str = Header(),
    x_demo_role: str = Header(default="doctor"),
) -> Actor:
    return services()[0].get_actor(x_workspace_id, user_id, x_demo_role)


@app.exception_handler(DomainError)
async def domain_error(_request, error):
    return JSONResponse({"detail": str(error), "code": error.code}, status_code=error.status_code)


@app.exception_handler(ModelError)
async def model_error(_request, error):
    return JSONResponse({"detail": str(error), "code": error.code}, status_code=503)


@app.exception_handler(Exception)
async def unexpected(_request, error):
    # Operational errors are correlated by class without returning connection URLs,
    # tokens, provider response bodies, or raw database details to the client.
    log.error("request_failed error_type=%s", type(error).__name__)
    return JSONResponse(
        {
            "detail": "This operation could not finish. Please retry or inspect the run's recorded progress.",
            "code": "internal_error",
        },
        status_code=500,
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "revision": os.getenv("RENDER_GIT_COMMIT", os.getenv("GIT_SHA", "local")),
    }


@app.get("/api/ready")
def ready():
    with services()[0].connection() as conn:
        conn.execute("SELECT 1 FROM pa_workspaces LIMIT 1")
        vector = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
    return {"status": "ready", "vector_extension": vector["extversion"] if vector else None}


@app.post("/api/dev-session")
def dev_session():
    cfg = settings()
    if cfg.environment != "local" or not cfg.local_auth_secret:
        raise DomainError("Not found.", "not_found", 404)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iss": "practice-assistant-local",
            "aud": "practice-assistant",
            "iat": now,
            "exp": now + timedelta(hours=12),
        },
        cfg.local_auth_secret,
        algorithm="HS256",
    )
    return {
        "access_token": token,
        "mode": "Local development identity; Supabase sign-in is required in production",
    }


@app.post("/api/session")
def session(data: SessionInput, user_id: str = Depends(identity)):
    store = services()[0]
    workspace = str(data.workspace_id) if data.workspace_id else store.create_workspace(user_id)
    current = store.get_actor(workspace, user_id, data.role)
    return {"workspace_id": workspace, "role": data.role, "snapshot": store.snapshot(current)}


@app.get("/api/snapshot")
def snapshot(current: Actor = Depends(actor)):
    return services()[0].snapshot(current)


@app.post("/api/runs")
def start_run(data: RunInput, current: Actor = Depends(actor)):
    jobs = services()[1]
    jobs.check_daily_budget()
    if not data.message.strip():
        raise DomainError("Enter a request.")
    return jobs.create(current, data.message.strip(), settings().max_workspace_runs)


@app.get("/api/runs")
def runs(current: Actor = Depends(actor)):
    return {"runs": services()[1].list(current)}


@app.get("/api/runs/{run_id}")
def run(run_id: UUID, current: Actor = Depends(actor)):
    return services()[1].get(current, str(run_id))


@app.post("/api/runs/{run_id}/cancel")
def cancel(run_id: UUID, current: Actor = Depends(actor)):
    return services()[1].cancel(current, str(run_id))


@app.post("/api/runs/{run_id}/export")
def export(run_id: UUID, current: Actor = Depends(actor)):
    store, jobs, *_ = services()
    return export_run(settings(), store, jobs, current, str(run_id))


@app.post("/api/sources/{source_id}/check")
def source_check(source_id: str, current: Actor = Depends(actor)):
    return check_source(services()[0], current, source_id)


@app.post("/api/plans/{plan_id}/approve")
def approve(plan_id: UUID, current: Actor = Depends(actor)):
    store, jobs, *_ = services()
    plan = store.get_plan(current, str(plan_id))
    if plan["status"] == "completed":
        return {"id": str(plan_id), "status": "completed"}
    if plan["status"] == "partial":
        # Approval is still bound to the same immutable action list. This only
        # resumes unfinished actions, checking their receipts first.
        pass
    else:
        plan = approve_plan(store, current, str(plan_id))
    if plan["status"] not in {"approved", "partial"}:
        raise DomainError(
            "This approval is no longer executable. Prepare a fresh proposal.", "approval_expired", 409
        )
    jobs.enqueue_continuation(current, str(plan["run_id"]))
    return {"id": str(plan_id), "status": "queued"}


@app.post("/api/scenarios")
def scenario(data: ScenarioInput, current: Actor = Depends(actor)):
    return apply_scenario(services()[0], current, data.scenario)


@app.post("/api/preferences/{preference_id}")
def preference(preference_id: str, data: PreferenceInput, current: Actor = Depends(actor)):
    store = services()[0]
    store.update_preference(current, preference_id, data.value)
    return store.snapshot(current)


@app.delete("/api/preferences/{preference_id}")
def delete_preference(preference_id: str, current: Actor = Depends(actor)):
    store = services()[0]
    store.delete_preference(current, preference_id)
    return store.snapshot(current)


@app.post("/api/reset")
def reset(current: Actor = Depends(actor)):
    return services()[0].reset_workspace(current)


@app.post("/api/voice/transcribe")
async def transcribe(audio: UploadFile = File(), current: Actor = Depends(actor)):
    _, jobs, models, _ = services()
    jobs.check_daily_budget()
    data = await audio.read(8 * 1024 * 1024 + 1)
    if not data or len(data) > 8 * 1024 * 1024:
        raise DomainError("Record a short voice note smaller than 8 MB.", "audio_size", 413)
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise DomainError("Voice input must be a WAV recording.", "audio_format", 415)
    # The synchronous hosted request runs in a worker thread so other API requests
    # remain responsive during transcription.
    from starlette.concurrency import run_in_threadpool

    text, usage = await run_in_threadpool(models.transcribe, data, "wav")
    jobs.record_usage(current, "transcription", usage)
    return {"text": text, "model": settings().audio_model}


@app.post("/api/voice/speak")
def speak(data: SpeechInput, current: Actor = Depends(actor)):
    _, jobs, models, _ = services()
    jobs.check_daily_budget()
    audio, usage = models.speak(data.text)
    jobs.record_usage(current, "speech", usage)
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/tools/read")
def tool_read(data: ToolInput, current: Actor = Depends(actor)):
    store, jobs, models, _ = services()
    if data.name == "search_sources":
        jobs.check_daily_budget()
        query = data.arguments.get("query")
        if not isinstance(query, str) or not 1 <= len(query) <= 1500:
            raise DomainError("Supply a source query of 1–1500 characters.")
        result = Knowledge(store, models).search(current, query)
        jobs.record_usage(current, "embedding", result.get("usage", {}))
        return result
    return read_tool(store, current, data.name, data.arguments)


@app.post("/api/integrations/handoff")
def handoff(data: HandoffInput, current: Actor = Depends(actor)):
    store = services()[0]
    record = store.get_record(current, data.record_id)
    expected = "patient_admin" if data.event_type == "paperwork_completed" else "content"
    if record["kind"] != expected:
        raise DomainError("This event does not match the referenced record.")
    event_id = str(uuid4())
    with store.connection() as conn:
        row = conn.execute(
            "INSERT INTO pa_outbox(id,workspace_id,user_id,role,event_key,payload) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,event_key) DO UPDATE SET event_key=excluded.event_key RETURNING id,status,payload",
            (
                event_id,
                current.workspace_id,
                current.user_id,
                current.role,
                data.event_id,
                Jsonb(data.model_dump()),
            ),
        ).fetchone()
        if row["payload"] != data.model_dump():
            raise DomainError(
                "This event ID was already used for a different handoff.", "event_conflict", 409
            )
    return serial(
        {
            "id": row["id"],
            "status": row["status"],
            "source": "Fictional approved handoff; no EmerGPT connection",
        }
    )
