from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from services.assistant.domain import (
    Actor,
    DomainError,
    apply_handoff,
    approve_plan,
    execute_plan,
    propose_plan,
)
from services.assistant.jobs import Jobs
from services.assistant.worker import process_outbox


def test_run_survives_worker_replacement_and_fences_old_generation(demo_office):
    store, actor = demo_office
    jobs = Jobs(store)
    run = jobs.create(actor, "Prepare tomorrow")
    first = jobs.claim()
    assert first["run_id"] == run["id"] and first["lease_generation"] == 1
    assert jobs.renew(first) is True
    jobs.step(first, "tool", "Read current status", {"record_id": "admin-maya"}, duration_ms=12)
    with store.connection() as conn:
        conn.execute("UPDATE pa_jobs SET lease_until=now()-interval '1 minute' WHERE id=%s", (first["id"],))
    replacement = Jobs(store).claim()
    assert replacement["run_id"] == run["id"]
    assert replacement["lease_generation"] == 2 and replacement["attempts"] == 2
    with pytest.raises(DomainError, match="no longer owns"):
        jobs.update(first, answer="A stale worker must not publish this")
    assert jobs.renew(first) is False
    jobs.update(replacement, status="completed", answer="Recovered the existing run")
    jobs.finish_job(replacement)
    saved = Jobs(store).get(actor, run["id"])
    assert saved["answer"] == "Recovered the existing run"
    assert len(saved["steps"]) == 1 and saved["steps"][0]["detail"]["record_id"] == "admin-maya"


def test_cancellation_prevents_remaining_approved_effects(demo_office):
    store, actor = demo_office
    jobs = Jobs(store)
    run = jobs.create(actor, "Assign a task")
    worker = jobs.claim()
    proposed = propose_plan(
        store,
        actor,
        run["id"],
        [
            {
                "kind": "create_task",
                "payload": {
                    "title": "A cancelled task",
                    "owner": "Alex Kim",
                    "due_at": "2026-09-09T14:00:00-07:00",
                },
            }
        ],
        "Create the task",
    )
    approve_plan(store, actor, proposed["id"])
    jobs.update(worker, plan_id=proposed["id"])
    cancelled = jobs.cancel(actor, run["id"])
    assert cancelled["status"] == "cancelled"
    fenced_actor = Actor(actor.workspace_id, actor.user_id, actor.role, run["id"], worker["lease_generation"])
    with pytest.raises(DomainError) as rejected:
        execute_plan(store, fenced_actor, proposed["id"])
    assert rejected.value.code == "lease_lost"
    assert not any(t["title"] == "A cancelled task" for t in store.snapshot(actor)["tasks"])
    assert jobs.claim() is None


def test_concurrent_claims_never_share_a_job(demo_office):
    store, actor = demo_office
    jobs = Jobs(store)
    run_ids = {jobs.create(actor, "First request")["id"], jobs.create(actor, "Second request")["id"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: Jobs(store).claim(), range(2)))
    assert {j["run_id"] for j in claimed} == run_ids
    assert len({j["id"] for j in claimed}) == 2
    assert jobs.claim() is None


def test_run_history_and_traces_are_scoped_by_role_and_owner(demo_office):
    store, doctor = demo_office
    jobs = Jobs(store)
    run = jobs.create(doctor, "Read private preparation")
    worker = jobs.claim()
    jobs.step(worker, "tool", "Private preparation", {"patient_name": "Maya Chen"})
    editor = store.get_actor(doctor.workspace_id, doctor.user_id, "editor")
    assert jobs.list(editor) == []
    with pytest.raises(DomainError):
        jobs.get(editor, run["id"])
    stranger = Actor(doctor.workspace_id, "another-user", "doctor")
    with pytest.raises(DomainError):
        jobs.get(stranger, run["id"])
    assert jobs.get(doctor, run["id"])["steps"][0]["detail"]["patient_name"] == "Maya Chen"


def test_exhausted_restart_attempts_become_visible_failure(demo_office):
    store, actor = demo_office
    jobs = Jobs(store)
    run = jobs.create(actor, "Interrupted repeatedly")
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_jobs SET status='running',attempts=8,lease_until=now()-interval '1 minute' WHERE run_id=%s",
            (run["id"],),
        )
        conn.execute("UPDATE pa_runs SET status='running' WHERE id=%s", (run["id"],))
    assert jobs.claim() is None
    failed = jobs.get(actor, run["id"])
    assert failed["status"] == "failed" and "restart limit" in failed["error"]


def test_usage_aggregation_preserves_unknown_cost_and_session_limits(demo_office):
    store, actor = demo_office
    jobs = Jobs(store)
    first = jobs.create(actor, "First")
    jobs.create(actor, "Second")
    with pytest.raises(DomainError) as limited:
        jobs.create(actor, "Third")
    assert limited.value.code == "too_many_runs"
    worker = jobs.claim()
    jobs.step(worker, "model", "No price returned", {}, usage={"total_tokens": 10})
    assert jobs.get(actor, worker["run_id"])["usage"]["cost"] is None
    jobs.step(worker, "model", "Measured price", {}, usage={"total_tokens": 20, "cost": 0.02}, duration_ms=30)
    usage = jobs.get(actor, worker["run_id"])["usage"]
    assert usage["tokens"] == 30 and float(usage["cost"]) == 0.02
    jobs.cancel(actor, first["id"])
    with pytest.raises(DomainError) as total_limit:
        jobs.create(actor, "Over total limit", limit=2)
    assert total_limit.value.code == "run_limit"


def test_reset_invalidates_inflight_job_and_removes_private_history(demo_office):
    store, actor = demo_office
    jobs = Jobs(store)
    run = jobs.create(actor, "Before reset")
    worker = jobs.claim()
    jobs.step(worker, "tool", "Read patient administration", {"record_id": "admin-maya"})
    store.reset_workspace(actor)
    with pytest.raises(DomainError) as stopped:
        jobs.check_fence(worker)
    assert stopped.value.code == "lease_lost"
    assert jobs.list(actor) == []
    with pytest.raises(DomainError):
        jobs.get(actor, run["id"])


def test_explicit_resume_reuses_the_same_job(demo_office):
    store, actor = demo_office
    jobs = Jobs(store)
    run = jobs.create(actor, "Await approval")
    first = jobs.claim()
    jobs.update(first, status="awaiting_approval")
    jobs.finish_job(first, "paused")
    jobs.enqueue_continuation(actor, run["id"])
    second = jobs.claim()
    assert second["id"] == first["id"] and second["lease_generation"] == 2
    with store.connection() as conn:
        assert (
            conn.execute("SELECT count(*) AS n FROM pa_jobs WHERE run_id=%s", (run["id"],)).fetchone()["n"]
            == 1
        )


def create_outbox(store, actor, event_id="leased-paperwork", generation=2):
    outbox_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "event_type": "paperwork_completed",
        "record_id": "admin-maya",
        "source_system": "practice-demo",
    }
    with store.connection() as conn:
        conn.execute(
            "INSERT INTO pa_outbox(id,workspace_id,user_id,role,event_key,payload,status,lease_generation,lease_until,attempts) VALUES (%s,%s,%s,%s,%s,%s,'processing',%s,now()+interval '1 minute',1)",
            (outbox_id, actor.workspace_id, actor.user_id, actor.role, event_id, Jsonb(payload), generation),
        )
    return outbox_id, payload


def test_handoff_rejects_obsolete_expired_and_mismatched_leases(demo_office):
    store, actor = demo_office
    outbox_id, payload = create_outbox(store, actor)
    with pytest.raises(DomainError) as old:
        apply_handoff(
            store,
            actor,
            payload["event_id"],
            payload["event_type"],
            payload["record_id"],
            outbox_id=outbox_id,
            outbox_generation=1,
        )
    assert old.value.code == "lease_lost"
    with pytest.raises(DomainError) as wrong_target:
        apply_handoff(
            store,
            actor,
            payload["event_id"],
            payload["event_type"],
            "admin-jordan",
            outbox_id=outbox_id,
            outbox_generation=2,
        )
    assert wrong_target.value.code == "lease_lost"
    with store.connection() as conn:
        conn.execute("UPDATE pa_outbox SET lease_until=now()-interval '1 minute' WHERE id=%s", (outbox_id,))
    with pytest.raises(DomainError) as expired:
        apply_handoff(
            store,
            actor,
            payload["event_id"],
            payload["event_type"],
            payload["record_id"],
            outbox_id=outbox_id,
            outbox_generation=2,
        )
    assert expired.value.code == "lease_lost"
    assert store.get_record(actor, "admin-maya")["paperwork_status"] == "missing"


def test_workspace_reset_fences_old_handoff_before_fresh_records_change(demo_office):
    store, actor = demo_office
    outbox_id, payload = create_outbox(store, actor)
    store.reset_workspace(actor)
    with pytest.raises(DomainError) as rejected:
        apply_handoff(
            store,
            actor,
            payload["event_id"],
            payload["event_type"],
            payload["record_id"],
            outbox_id=outbox_id,
            outbox_generation=2,
        )
    assert rejected.value.code == "lease_lost"
    assert store.get_record(actor, "admin-maya")["paperwork_status"] == "missing"
    assert store.get_record(actor, "task-prep-maya")["status"] == "open"


def test_handoff_worker_reconciles_crash_after_receipt_commit(demo_office):
    store, actor = demo_office
    outbox_id, payload = create_outbox(store, actor, generation=1)
    receipt = apply_handoff(
        store,
        actor,
        payload["event_id"],
        payload["event_type"],
        payload["record_id"],
        outbox_id=outbox_id,
        outbox_generation=1,
    )
    assert receipt["changed"] is True and receipt["record"]["version"] == 2
    # Simulate process loss after the receipt commit but before outbox completion.
    with store.connection() as conn:
        conn.execute("UPDATE pa_outbox SET lease_until=now()-interval '1 minute' WHERE id=%s", (outbox_id,))
    assert process_outbox(store) is True
    with store.connection() as conn:
        saved = conn.execute(
            "SELECT status,attempts,lease_generation FROM pa_outbox WHERE id=%s", (outbox_id,)
        ).fetchone()
    assert saved == {"status": "completed", "attempts": 2, "lease_generation": 2}
    assert store.get_record(actor, "admin-maya")["version"] == 2
    assert store.get_record(actor, "task-prep-maya")["version"] == 2
    assert process_outbox(store) is False


def test_handoff_worker_exhaustion_is_reported(demo_office):
    store, actor = demo_office
    outbox_id, _ = create_outbox(store, actor)
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_outbox SET attempts=8,lease_until=now()-interval '1 minute' WHERE id=%s", (outbox_id,)
        )
    assert process_outbox(store) is False
    with store.connection() as conn:
        saved = conn.execute("SELECT status,error FROM pa_outbox WHERE id=%s", (outbox_id,)).fetchone()
    assert saved["status"] == "failed" and "retry limit" in saved["error"]
