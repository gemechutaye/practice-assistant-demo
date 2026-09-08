"""PostgreSQL records with workspace ownership and explicit role filtering."""

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .domain import Actor, DomainError, ROLES, can_read_record, preparation_status
from .seed import DEMO_CLOCK, seed_workspace


def serializable(value):
    if isinstance(value, (datetime, UUID)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, dict):
        return {k: serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    return value


def record(row: dict) -> dict:
    return {**row["data"], "id": row["id"], "kind": row["kind"], "version": row["version"]}


class Store:
    def __init__(self, database_url: str):
        self.database_url = database_url

    @contextmanager
    def connection(self):
        with psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=15) as conn:
            yield conn

    def migrate(self):
        directory = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
        with self.connection() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(824501)")
            for path in sorted(directory.glob("*.sql")):
                conn.execute(path.read_text())

    @staticmethod
    def authorize(conn, actor: Actor, lock: bool = False):
        if actor.role not in ROLES:
            raise DomainError("Unknown demonstration role", "forbidden", 403)
        suffix = " FOR UPDATE" if lock else ""
        try:
            UUID(actor.workspace_id)
        except (ValueError, TypeError, AttributeError):
            raise DomainError("Workspace not found", "not_found", 404)
        row = conn.execute(
            "SELECT * FROM pa_workspaces WHERE id=%s AND user_id=%s" + suffix,
            (actor.workspace_id, actor.user_id),
        ).fetchone()
        if not row:
            raise DomainError("This workspace does not belong to this session", "forbidden", 403)
        return row

    @staticmethod
    def touch(conn, workspace_id):
        conn.execute("UPDATE pa_workspaces SET revision=revision+1 WHERE id=%s", (workspace_id,))

    def create_workspace(self, user_id: str) -> str:
        if not user_id or len(user_id) > 200:
            raise DomainError("A valid signed-in user is required", "unauthorized", 401)
        workspace_id = str(uuid4())
        with self.connection() as conn:
            conn.execute("INSERT INTO pa_workspaces(id,user_id) VALUES (%s,%s)", (workspace_id, user_id))
            seed_workspace(conn, workspace_id, user_id)
        return workspace_id

    def get_actor(self, workspace_id: str, user_id: str, role: str) -> Actor:
        actor = Actor(workspace_id, user_id, role)
        with self.connection() as conn:
            self.authorize(conn, actor)
        return actor

    def list_records(self, actor, kind=None, conn=None):
        if conn is None:
            with self.connection() as opened:
                return self.list_records(actor, kind, opened)
        self.authorize(conn, actor)
        rows = conn.execute(
            "SELECT * FROM pa_office_records WHERE workspace_id=%s AND (%s::text IS NULL OR kind=%s) ORDER BY id",
            (actor.workspace_id, kind, kind),
        ).fetchall()
        return [record(row) for row in rows if can_read_record(actor, record(row))]

    def get_record(self, actor, record_id, conn=None, lock=False):
        if conn is None:
            with self.connection() as opened:
                return self.get_record(actor, record_id, opened, lock)
        self.authorize(conn, actor)
        row = conn.execute(
            "SELECT * FROM pa_office_records WHERE workspace_id=%s AND id=%s"
            + (" FOR UPDATE" if lock else ""),
            (actor.workspace_id, record_id),
        ).fetchone()
        if not row or not can_read_record(actor, record(row)):
            raise DomainError("Record is unavailable for this role", "not_found", 404)
        return record(row)

    def get_preferences(self, actor, conn=None):
        if conn is None:
            with self.connection() as opened:
                return self.get_preferences(actor, opened)
        self.authorize(conn, actor)
        rows = conn.execute(
            "SELECT id,key,value,version,scope,source_request,updated_at FROM pa_preferences WHERE workspace_id=%s AND (%s='doctor' OR scope='content') ORDER BY key",
            (actor.workspace_id, actor.role),
        ).fetchall()
        return serializable(rows)

    def get_sources(self, actor, conn=None):
        if conn is None:
            with self.connection() as opened:
                return self.get_sources(actor, opened)
        self.authorize(conn, actor)
        rows = conn.execute(
            "SELECT id,title,url,excerpt,accessed_at,provenance,version,data FROM pa_sources WHERE workspace_id=%s AND (%s<>'editor' OR provenance='public') ORDER BY id",
            (actor.workspace_id, actor.role),
        ).fetchall()
        return serializable([{**r.pop("data"), **r} for r in rows])

    def get_report(self, actor, report_type="preparation_by_owner", conn=None):
        if actor.role == "editor":
            raise DomainError("Office reports are unavailable to the content role", "forbidden", 403)
        if report_type not in (
            "preparation_by_owner",
            "open_tasks_by_owner",
            "content_status",
            "office_overview",
        ):
            raise DomainError(
                "Choose preparation_by_owner, open_tasks_by_owner, content_status, or office_overview",
                "invalid_argument",
            )
        if conn is None:
            with self.connection() as opened:
                return self.get_report(actor, report_type, opened)
        self.authorize(conn, actor)
        if report_type == "content_status":
            rows = conn.execute(
                "SELECT data->>'status' AS owner,count(*)::integer AS count FROM pa_office_records WHERE workspace_id=%s AND kind='content' GROUP BY data->>'status' ORDER BY owner",
                (actor.workspace_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT data->>'owner' AS owner,count(*)::integer AS count FROM pa_office_records WHERE workspace_id=%s AND kind='task' AND data->>'status'='open' AND (%s<>'preparation_by_owner' OR data->>'workflow'='preparation') GROUP BY data->>'owner' ORDER BY owner",
                (actor.workspace_id, report_type),
            ).fetchall()
        return {
            "report_type": report_type,
            "total": sum(r["count"] for r in rows),
            "by_owner": rows,
            "rows": rows,
            "computed_from": "Current PostgreSQL records",
            "clock": DEMO_CLOCK,
        }

    def snapshot(self, actor) -> dict:
        with self.connection() as conn:
            workspace = self.authorize(conn, actor)
            records = self.list_records(actor, conn=conn)
            groups = {
                kind: [r for r in records if r["kind"] == kind]
                for kind in ("event", "task", "message", "patient_admin", "content", "engineering", "report")
            }
            groups["event"].sort(key=lambda x: x["start"])
            for report in groups["report"]:
                report["computed"] = self.get_report(
                    actor, report.get("report_type", "preparation_by_owner"), conn
                )
            prep = preparation_status(groups["patient_admin"], groups["event"])
            return {
                "workspace_id": actor.workspace_id,
                "role": actor.role,
                "clock": DEMO_CLOCK,
                "doctor_name": "Dr. Avery Morgan",
                "revision": workspace["revision"],
                "events": groups["event"],
                "tasks": groups["task"],
                "messages": groups["message"],
                "patient_admin": groups["patient_admin"],
                "content": groups["content"],
                "engineering": groups["engineering"],
                "reports": groups["report"],
                "preferences": self.get_preferences(actor, conn),
                "sources": self.get_sources(actor, conn),
                "stats": {
                    "open_tasks": sum(t["status"] == "open" for t in groups["task"]),
                    "needs_attention": sum(p["paperwork_status"] == "missing" for p in prep),
                    "content_in_review": sum(c["status"] == "in_review" for c in groups["content"]),
                },
                "preparation": prep,
            }

    def get_plan(self, actor, plan_id, conn=None):
        if conn is None:
            with self.connection() as opened:
                return self.get_plan(actor, plan_id, opened)
        self.authorize(conn, actor)
        try:
            UUID(str(plan_id))
        except ValueError:
            raise DomainError("Plan not found", "not_found", 404)
        plan = conn.execute(
            "SELECT * FROM pa_plans WHERE id=%s AND workspace_id=%s AND user_id=%s AND role=%s",
            (plan_id, actor.workspace_id, actor.user_id, actor.role),
        ).fetchone()
        if not plan:
            raise DomainError("Plan is unavailable for this role", "not_found", 404)
        plan["actions"] = conn.execute(
            "SELECT id,kind,payload,status,result,error FROM pa_actions WHERE plan_id=%s ORDER BY position",
            (plan_id,),
        ).fetchall()
        return serializable(plan)

    def update_preference(self, actor, preference_id, value):
        if actor.role != "doctor":
            raise DomainError("Only the doctor can change personal preferences", "forbidden", 403)
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise DomainError("Preference must be 1–2000 characters", "invalid_argument")
        with self.connection() as conn:
            self.authorize(conn, actor, lock=True)
            row = conn.execute(
                "UPDATE pa_preferences SET value=%s,version=version+1,updated_at=now(),source_request='Edited explicitly in Memory' WHERE workspace_id=%s AND id=%s RETURNING id",
                (Jsonb(value.strip()), actor.workspace_id, preference_id),
            ).fetchone()
            if not row:
                raise DomainError("Preference not found", "not_found", 404)
            self.touch(conn, actor.workspace_id)
        return self.snapshot(actor)

    def delete_preference(self, actor, preference_id):
        if actor.role != "doctor":
            raise DomainError("Only the doctor can delete personal preferences", "forbidden", 403)
        with self.connection() as conn:
            self.authorize(conn, actor, lock=True)
            row = conn.execute(
                "DELETE FROM pa_preferences WHERE workspace_id=%s AND id=%s RETURNING id",
                (actor.workspace_id, preference_id),
            ).fetchone()
            if not row:
                raise DomainError("Preference not found", "not_found", 404)
            self.touch(conn, actor.workspace_id)
        return self.snapshot(actor)

    def reset_workspace(self, actor):
        with self.connection() as conn:
            self.authorize(conn, actor, lock=True)
            conn.execute("DELETE FROM pa_workspaces WHERE id=%s", (actor.workspace_id,))
            conn.execute(
                "INSERT INTO pa_workspaces(id,user_id) VALUES (%s,%s)", (actor.workspace_id, actor.user_id)
            )
            seed_workspace(conn, actor.workspace_id, actor.user_id)
        return self.snapshot(actor)
