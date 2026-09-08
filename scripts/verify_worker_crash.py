"""Kill an isolated executor process after commit, then resume its leased job."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from services.assistant.domain import Actor, approve_plan, execute_plan, propose_plan
from services.assistant.jobs import Jobs
from services.assistant.store import Store


def child():
    class PauseAfterCommit(Store):
        paused = False

        @contextmanager
        def connection(self):
            with super().connection() as conn:
                yield conn
            if not self.paused:
                with Store.connection(self) as check:
                    committed = check.execute(
                        "SELECT count(*) AS n FROM pa_action_receipts WHERE workspace_id=%s",
                        (os.environ["CRASH_WORKSPACE"],),
                    ).fetchone()["n"]
                if committed:
                    self.paused = True
                    Path(os.environ["CRASH_MARKER"]).write_text("A real mutation and receipt committed.\n")
                    while True:
                        time.sleep(1)

    store = PauseAfterCommit(os.environ["CRASH_DATABASE_URL"])
    jobs = Jobs(store)
    job = jobs.claim(lease_seconds=2)
    if not job:
        raise RuntimeError("No isolated test job was claimable")
    raw = job["run"]
    actor = Actor(
        str(raw["workspace_id"]), raw["user_id"], raw["role"], str(raw["id"]), job["lease_generation"]
    )
    execute_plan(store, actor, os.environ["CRASH_PLAN"])


def main():
    if "--child" in sys.argv:
        child()
        return
    admin_url = os.environ["TEST_DATABASE_URL"]
    database_name = "pa_crash_" + uuid4().hex
    output = Path("artifacts/verification")
    output.mkdir(parents=True, exist_ok=True)
    marker = output / (".crash-marker-" + uuid4().hex)
    process = None
    report = {
        "test": "Physical executor crash after committed action",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "passed": False,
        "model_calls": 0,
    }
    started = time.monotonic()
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        store = Store(make_conninfo(admin_url, dbname=database_name))
        with store.connection() as conn:
            for path in sorted(Path("supabase/migrations").glob("*.sql")):
                if path.name.startswith(("001_", "002_", "004_")):
                    conn.execute(path.read_text())
        workspace_id = store.create_workspace("crash-verification")
        actor = store.get_actor(workspace_id, "crash-verification", "doctor")
        jobs = Jobs(store)
        run = jobs.create(actor, "Verify that committed actions survive a process crash")
        plan = propose_plan(
            store,
            actor,
            run["id"],
            [
                {
                    "kind": "create_task",
                    "payload": {
                        "title": "Crash verification task",
                        "owner": "Alex Kim",
                        "due_at": "2026-09-09T16:00:00-07:00",
                    },
                },
                {
                    "kind": "deliver_demo_message",
                    "payload": {
                        "subject": "Crash verification message",
                        "body": "This fictional message should be delivered exactly once after recovery.",
                        "recipient": "Alex Kim",
                    },
                },
            ],
            "Verify task creation and demo-message delivery",
        )
        approve_plan(store, actor, plan["id"])
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONUNBUFFERED": "1",
            "CRASH_DATABASE_URL": store.database_url,
            "CRASH_WORKSPACE": workspace_id,
            "CRASH_PLAN": plan["id"],
            "CRASH_MARKER": str(marker.resolve()),
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "scripts.verify_worker_crash", "--child"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 12
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if not marker.exists():
            raise RuntimeError("The executor did not reach its committed-action pause")
        with store.connection() as conn:
            receipt_count = conn.execute(
                "SELECT count(*) AS n FROM pa_action_receipts WHERE workspace_id=%s", (workspace_id,)
            ).fetchone()["n"]
        assert receipt_count == 1
        os.kill(process.pid, signal.SIGKILL)
        exit_code = process.wait(timeout=5)
        assert exit_code == -signal.SIGKILL
        replacement = None
        deadline = time.monotonic() + 6
        while replacement is None and time.monotonic() < deadline:
            replacement = jobs.claim()
            if replacement is None:
                time.sleep(0.05)
        assert replacement and replacement["lease_generation"] == 2
        resumed_actor = Actor(
            actor.workspace_id, actor.user_id, actor.role, run["id"], replacement["lease_generation"]
        )
        result = execute_plan(store, resumed_actor, plan["id"])
        jobs.update(replacement, status="completed", answer="Verified recovery after process termination")
        jobs.finish_job(replacement)
        snapshot = store.snapshot(actor)
        task_count = sum(t["title"] == "Crash verification task" for t in snapshot["tasks"])
        message_count = sum(m["subject"] == "Crash verification message" for m in snapshot["messages"])
        with store.connection() as conn:
            final_receipts = conn.execute(
                "SELECT count(*) AS n FROM pa_action_receipts WHERE workspace_id=%s", (workspace_id,)
            ).fetchone()["n"]
        assert result["status"] == "completed" and task_count == message_count == 1 and final_receipts == 2
        report.update(
            passed=True,
            killed_process_exit_code=exit_code,
            committed_receipts_before_kill=receipt_count,
            replacement_lease_generation=2,
            task_count=task_count,
            delivered_demo_message_count=message_count,
            receipts_after_resume=final_receipts,
            completed_plan_status=result["status"],
            first_action_reconciled=result["actions"][0]["result"].get("reconciled", False),
        )
    except Exception as error:
        report.update(
            error_type=type(error).__name__,
            note="Verification did not complete; no credentials or database connection details are included.",
        )
        raise
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        marker.unlink(missing_ok=True)
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()",
                (database_name,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (output / "worker-crash.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
