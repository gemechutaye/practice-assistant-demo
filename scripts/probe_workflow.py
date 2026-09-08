"""Live integration probe against an isolated fictional office."""

import json
from pathlib import Path
import time

from services.assistant.config import settings
from services.assistant.store import Store
from services.assistant.jobs import Jobs
from services.assistant.model_router import Models
from services.assistant.agent import Agent
from services.assistant.domain import approve_plan

cfg = settings()
store = Store(cfg.database_url)
jobs = Jobs(store)
models = Models(cfg)
workspace = store.create_workspace("live-verification")
actor = store.get_actor(workspace, "live-verification", "doctor")
created = jobs.create(
    actor,
    "Prepare me for tomorrow. Check paperwork, protect my clinic time, and propose the useful follow-up work. Do not duplicate tasks already assigned.",
)
job = jobs.claim()
started = time.monotonic()
Agent(store, jobs, models, cfg).run(job)
result = jobs.get(actor, created["id"])
print(
    json.dumps(
        {
            "stage": "planned",
            "status": result["status"],
            "answer": result["answer"],
            "actions": result.get("plan", {}).get("actions") if result.get("plan") else None,
            "usage": result["usage"],
        }
    ),
    flush=True,
)
if result["status"] == "awaiting_approval":
    approve_plan(store, actor, result["plan"]["id"])
    jobs.enqueue_continuation(actor, result["id"])
    Agent(store, jobs, models, cfg).run(jobs.claim())
    result = jobs.get(actor, created["id"])
out = Path("artifacts/development")
out.mkdir(parents=True, exist_ok=True)
(out / "first-live-workflow.json").write_text(
    json.dumps({"run": result, "snapshot": store.snapshot(actor)}, indent=2)
)
print(
    json.dumps(
        {
            "stage": "final",
            "status": result["status"],
            "answer": result["answer"],
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "usage": result["usage"],
        }
    ),
    flush=True,
)
