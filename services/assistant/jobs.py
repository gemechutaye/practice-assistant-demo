"""PostgreSQL is the owner of work, leases, progress, and run visibility."""

import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from .domain import Actor, DomainError


def serial(value):
    return json.loads(json.dumps(value, default=str))


class Jobs:
    def __init__(self, store):
        self.store = store

    def create(self, actor: Actor, message: str, limit: int = 60) -> dict:
        run_id = str(uuid4())
        with self.store.connection() as conn:
            conn.execute("SELECT id FROM pa_workspaces WHERE id=%s FOR UPDATE", (actor.workspace_id,))
            count = conn.execute(
                "SELECT count(*) AS n FROM pa_runs WHERE workspace_id=%s", (actor.workspace_id,)
            ).fetchone()["n"]
            if count >= limit:
                raise DomainError("This demo workspace has reached its run limit.", "run_limit", 429)
            active = conn.execute(
                "SELECT count(*) AS n FROM pa_runs WHERE workspace_id=%s AND status IN ('queued','running')",
                (actor.workspace_id,),
            ).fetchone()["n"]
            if active >= 2:
                raise DomainError("Please wait for the current work to finish.", "too_many_runs", 429)
            conn.execute(
                "INSERT INTO pa_runs(id,workspace_id,user_id,role,message) VALUES (%s,%s,%s,%s,%s)",
                (run_id, actor.workspace_id, actor.user_id, actor.role, message),
            )
            conn.execute(
                "INSERT INTO pa_jobs(id,run_id,workspace_id) VALUES (%s,%s,%s)",
                (str(uuid4()), run_id, actor.workspace_id),
            )
        return {"id": run_id, "status": "queued"}

    def get(self, actor: Actor, run_id: str) -> dict:
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM pa_runs WHERE id=%s AND workspace_id=%s AND user_id=%s AND role=%s",
                (run_id, actor.workspace_id, actor.user_id, actor.role),
            ).fetchone()
            if not row:
                raise DomainError("This run is not available in your current role.", "run_not_found", 404)
            steps = conn.execute(
                "SELECT * FROM pa_steps WHERE run_id=%s ORDER BY created_at,id", (run_id,)
            ).fetchall()
        plan = self.store.get_plan(actor, str(row["plan_id"])) if row["plan_id"] else None
        known_costs = [float(s["cost"]) for s in steps if s["cost"] is not None]
        return serial(
            {
                **row,
                "plan": plan,
                "steps": steps,
                "usage": {
                    "tokens": sum(s["tokens"] or 0 for s in steps),
                    "cost": sum(known_costs) if known_costs else None,
                    "latency_ms": sum(
                        s["duration_ms"] for s in steps if s["kind"] in {"model", "routing", "retrieval"}
                    ),
                },
            }
        )

    def list(self, actor: Actor) -> list:
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT id,message,status,answer,created_at,plan_id FROM pa_runs WHERE workspace_id=%s AND user_id=%s AND role=%s ORDER BY created_at DESC LIMIT 30",
                (actor.workspace_id, actor.user_id, actor.role),
            ).fetchall()
        return serial(rows)

    def claim(self, lease_seconds: int = 120) -> dict | None:
        with self.store.connection() as conn:
            exhausted = conn.execute(
                "UPDATE pa_jobs SET status='failed',lease_until=NULL WHERE attempts>=8 AND (status='queued' OR (status='running' AND lease_until<now())) RETURNING run_id"
            ).fetchall()
            for item in exhausted:
                conn.execute(
                    "UPDATE pa_runs SET status='failed',error='This job exceeded its restart limit.',updated_at=now() WHERE id=%s",
                    (item["run_id"],),
                )
            row = conn.execute("""SELECT j.* FROM pa_jobs j JOIN pa_runs r ON r.id=j.run_id
                WHERE r.cancelled=false AND j.attempts<8 AND
                ((j.status='queued' AND j.available_at<=now()) OR (j.status='running' AND j.lease_until<now()))
                ORDER BY j.available_at FOR UPDATE OF j SKIP LOCKED LIMIT 1""").fetchone()
            if not row:
                return None
            claimed = conn.execute(
                "UPDATE pa_jobs SET status='running',lease_generation=lease_generation+1,lease_until=now()+(%s * interval '1 second'),attempts=attempts+1 WHERE id=%s RETURNING *",
                (lease_seconds, row["id"]),
            ).fetchone()
            run = conn.execute(
                "UPDATE pa_runs SET status='running',updated_at=now() WHERE id=%s RETURNING *",
                (row["run_id"],),
            ).fetchone()
        return serial({**claimed, "run": run})

    def renew(self, job: dict, lease_seconds: int = 120) -> bool:
        with self.store.connection() as conn:
            row = conn.execute(
                "UPDATE pa_jobs j SET lease_until=now()+(%s * interval '1 second') FROM pa_runs r WHERE j.id=%s AND j.lease_generation=%s AND j.status='running' AND j.lease_until>now() AND r.id=j.run_id AND r.cancelled=false RETURNING j.id",
                (lease_seconds, job["id"], job["lease_generation"]),
            ).fetchone()
        return bool(row)

    def check_fence(self, job: dict) -> None:
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT j.id FROM pa_jobs j JOIN pa_runs r ON r.id=j.run_id WHERE j.id=%s AND j.lease_generation=%s AND j.status='running' AND j.lease_until>now() AND r.cancelled=false",
                (job["id"], job["lease_generation"]),
            ).fetchone()
        if not row:
            raise DomainError("This worker no longer owns the run.", "lease_lost", 409)

    def update(
        self,
        job: dict,
        *,
        status: str | None = None,
        answer: str | None = None,
        error: str | None = None,
        plan_id: str | None = None,
        route: str | None = None,
        selected_model: str | None = None,
    ) -> None:
        with self.store.connection() as conn:
            conn.execute("SELECT id FROM pa_workspaces WHERE id=%s FOR UPDATE", (job["workspace_id"],))
            valid = conn.execute(
                "SELECT j.id FROM pa_jobs j JOIN pa_runs r ON r.id=j.run_id WHERE j.id=%s AND j.lease_generation=%s AND j.status='running' AND j.lease_until>now() AND r.cancelled=false FOR UPDATE OF j",
                (job["id"], job["lease_generation"]),
            ).fetchone()
            if not valid:
                raise DomainError("This worker no longer owns the run.", "lease_lost", 409)
            conn.execute(
                """UPDATE pa_runs SET status=coalesce(%s,status),answer=coalesce(%s,answer),
                error=%s,plan_id=coalesce(%s,plan_id),route=coalesce(%s,route),
                selected_model=coalesce(%s,selected_model),updated_at=now() WHERE id=%s""",
                (status, answer, error, plan_id, route, selected_model, job["run_id"]),
            )
            conn.execute("UPDATE pa_workspaces SET revision=revision+1 WHERE id=%s", (job["workspace_id"],))

    def finish_job(self, job: dict, status: str = "completed") -> None:
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE pa_jobs SET status=%s,lease_until=NULL WHERE id=%s AND lease_generation=%s AND status='running'",
                (status, job["id"], job["lease_generation"]),
            )

    def enqueue_continuation(self, actor: Actor, run_id: str) -> None:
        self.get(actor, run_id)
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE pa_runs SET cancelled=false,status='queued',error=NULL,updated_at=now() WHERE id=%s",
                (run_id,),
            )
            conn.execute(
                "UPDATE pa_jobs SET status='queued',available_at=now(),lease_until=NULL WHERE run_id=%s AND status <> 'running'",
                (run_id,),
            )

    def cancel(self, actor: Actor, run_id: str) -> dict:
        self.get(actor, run_id)
        with self.store.connection() as conn:
            # Lock the job just as the action executor does: cancellation and a
            # committed mutation have an unambiguous ordering.
            conn.execute("SELECT id FROM pa_jobs WHERE run_id=%s FOR UPDATE", (run_id,))
            conn.execute(
                "UPDATE pa_runs SET cancelled=true,status='cancelled',updated_at=now() WHERE id=%s", (run_id,)
            )
            conn.execute(
                "UPDATE pa_jobs SET status='cancelled',lease_generation=lease_generation+1,lease_until=NULL WHERE run_id=%s",
                (run_id,),
            )
        return self.get(actor, run_id)

    def step(
        self,
        job: dict,
        kind: str,
        title: str,
        detail: dict,
        *,
        duration_ms: int = 0,
        model: str | None = None,
        usage: dict | None = None,
        status: str = "completed",
    ) -> None:
        self.check_fence(job)
        usage = usage or {}
        with self.store.connection() as conn:
            conn.execute(
                "INSERT INTO pa_steps(id,run_id,workspace_id,kind,title,detail,status,duration_ms,model,tokens,cost) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    str(uuid4()),
                    job["run_id"],
                    job["workspace_id"],
                    kind,
                    title,
                    Jsonb(serial(detail)),
                    status,
                    duration_ms,
                    model,
                    usage.get("total_tokens"),
                    usage.get("cost"),
                ),
            )

    def cost(self, run_id: str) -> float:
        with self.store.connection() as conn:
            return float(
                conn.execute(
                    "SELECT coalesce(sum(cost),0) AS cost FROM pa_steps WHERE run_id=%s", (run_id,)
                ).fetchone()["cost"]
            )

    def record_usage(self, actor: Actor, category: str, usage: dict) -> None:
        with self.store.connection() as conn:
            conn.execute(
                "INSERT INTO pa_usage(id,workspace_id,category,usage) VALUES (%s,%s,%s,%s)",
                (str(uuid4()), actor.workspace_id, category, Jsonb(usage)),
            )

    def check_daily_budget(self, limit: float = 10.0) -> None:
        with self.store.connection() as conn:
            total = conn.execute("""SELECT
              coalesce((SELECT sum(cost) FROM pa_steps WHERE created_at>=now()-interval '24 hours'),0)
              +coalesce((SELECT sum((usage->>'cost')::numeric) FROM pa_usage WHERE created_at>=now()-interval '24 hours'),0) AS cost""").fetchone()[
                "cost"
            ]
            count = conn.execute(
                "SELECT count(*) AS n FROM pa_usage WHERE created_at>=now()-interval '1 hour'"
            ).fetchone()["n"]
        if float(total) >= limit or count >= 300:
            raise DomainError(
                "The shared demonstration has reached its usage budget. Please return later.",
                "daily_budget",
                429,
            )
