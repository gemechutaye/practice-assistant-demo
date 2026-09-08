"""Real PostgreSQL checks of approvals, isolation, state changes and recovery."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from services.assistant.domain import (
    Actor,
    DomainError,
    apply_handoff,
    apply_scenario,
    approve_plan,
    execute_plan,
    parse_time,
    propose_plan,
    read_tool,
)
from services.assistant.store import Store


@pytest.fixture
def office():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL database")
    store = Store(database_url)
    with store.connection() as conn:
        conn.execute(Path("supabase/migrations/001_domain.sql").read_text())
    user = "test-" + str(uuid4())
    workspace = store.create_workspace(user)
    actor = store.get_actor(workspace, user, "doctor")
    yield store, actor
    with store.connection() as conn:
        conn.execute("DELETE FROM pa_workspaces WHERE id=%s", (workspace,))


def task(title="Call about missing paperwork"):
    return {
        "kind": "create_task",
        "payload": {
            "title": title,
            "owner": "Alex Kim",
            "due_at": "2026-09-08T09:00:00-07:00",
            "related_record_id": "admin-maya",
            "auto_close_on_paperwork": True,
        },
    }


def meeting(start="2026-09-09T11:00:00-07:00", end="2026-09-09T11:30:00-07:00"):
    return {"kind": "move_meeting", "payload": {"event_id": "engineering-sync", "start": start, "end": end}}


def plan(store, actor, actions):
    return propose_plan(store, actor, str(uuid4()), actions, "Review these changes in the fictional office")


def test_preparation_deadline_uses_aware_time_and_actual_records(office):
    store, actor = office
    result = read_tool(store, actor, "get_preparation_status", {})
    maya = next(r for r in result["patients"] if r["id"] == "admin-maya")
    assert maya["minutes_remaining"] == 45
    assert maya["timing"] == "due in 45 minutes"
    assert maya["paperwork_deadline"] == "2026-09-08T09:00:00-07:00"
    assert store.get_report(actor)["total"] == 1


def test_approval_is_required_and_receipts_prevent_duplicates(office):
    store, actor = office
    before = len(store.snapshot(actor)["tasks"])
    proposed = plan(store, actor, [task()])
    assert len(store.snapshot(actor)["tasks"]) == before
    with pytest.raises(DomainError, match="approved"):
        execute_plan(store, actor, proposed["id"])
    approve_plan(store, actor, proposed["id"])
    completed = execute_plan(store, actor, proposed["id"])
    assert completed["status"] == "completed"
    assert completed["actions"][0]["result"]["record"]["title"] == "Call about missing paperwork"
    execute_plan(store, actor, proposed["id"])
    assert len(store.snapshot(actor)["tasks"]) == before + 1


def test_changed_calendar_prevents_every_remaining_write(office):
    store, actor = office
    before = len(store.snapshot(actor)["tasks"])
    proposed = plan(store, actor, [task(), meeting()])
    apply_scenario(store, actor, "occupy_proposed_slot")
    approve_plan(store, actor, proposed["id"])
    stale = execute_plan(store, actor, proposed["id"])
    assert stale["status"] == "stale"
    assert len(store.snapshot(actor)["tasks"]) == before
    assert store.get_record(actor, "engineering-sync")["start"] == "2026-09-09T09:30:00-07:00"


def test_timeout_after_commit_resumes_without_duplicate(office):
    store, actor = office
    before = len(store.snapshot(actor)["tasks"])
    proposed = plan(
        store,
        actor,
        [
            meeting(),
            task(),
            {
                "kind": "deliver_demo_message",
                "payload": {
                    "subject": "Paperwork reminder",
                    "body": "Please check the administration record and follow up.",
                    "recipient": "Alex Kim",
                },
            },
        ],
    )
    apply_scenario(store, actor, "task_timeout_after_write")
    approve_plan(store, actor, proposed["id"])
    interrupted = execute_plan(store, actor, proposed["id"])
    assert interrupted["status"] == "partial"
    assert [a["status"] for a in interrupted["actions"]] == ["completed", "outcome_unknown", "approved"]
    assert len(store.snapshot(actor)["tasks"]) == before + 1
    resumed = execute_plan(store, actor, proposed["id"])
    assert resumed["status"] == "completed"
    assert resumed["actions"][1]["result"]["reconciled"] is True
    assert len(store.snapshot(actor)["tasks"]) == before + 1
    assert "No external message" in resumed["actions"][2]["result"]["delivery"]


def test_follow_up_is_linked_authorized_and_idempotent(office):
    store, actor = office
    proposed = plan(store, actor, [task()])
    approve_plan(store, actor, proposed["id"])
    execute_plan(store, actor, proposed["id"])
    first = apply_scenario(store, actor, "paperwork_complete")
    second = apply_scenario(store, actor, "paperwork_complete")
    assert next(t for t in first["tasks"] if t["id"] == "task-prep-maya")["status"] == "completed"
    assert next(t for t in second["tasks"] if t["id"] == "task-unrelated")["status"] == "open"
    assert (
        next(r for r in first["patient_admin"] if r["id"] == "admin-maya")["version"]
        == next(r for r in second["patient_admin"] if r["id"] == "admin-maya")["version"]
    )
    assert store.get_report(actor)["total"] == 0


def test_content_flow_assigns_review_and_closes_only_review_task(office):
    store, actor = office
    content = {
        "kind": "create_content",
        "payload": {
            "title": "Consultation pricing",
            "script": "Pricing is discussed at consultation because individual concerns vary.",
            "caption": "Bring your questions to your consultation.",
            "reviewer": "Jamie Park",
            "source_ids": ["source-scar-pricing"],
        },
    }
    proposed = plan(
        store,
        actor,
        [
            content,
            {
                "kind": "create_recording",
                "payload": {
                    "title": "Record consultation pricing post",
                    "start": "2026-09-09T14:00:00-07:00",
                    "end": "2026-09-09T14:30:00-07:00",
                },
            },
        ],
    )
    assert proposed["actions"][0]["payload"]["review_task"]["owner"] == "Jamie Park"
    approve_plan(store, actor, proposed["id"])
    completed = execute_plan(store, actor, proposed["id"])
    editor = store.get_actor(actor.workspace_id, actor.user_id, "editor")
    snapshot = store.snapshot(editor)
    assert snapshot["patient_admin"] == [] and snapshot["engineering"] == []
    assert all(e["event_type"] == "recording" for e in snapshot["events"])
    assert snapshot["stats"]["content_in_review"] == 1
    reviewed = apply_scenario(store, editor, "content_reviewed")
    content_id = completed["actions"][0]["result"]["record"]["id"]
    assert next(c for c in reviewed["content"] if c["id"] == content_id)["status"] == "approved"
    assert next(t for t in reviewed["tasks"] if t["related_record_id"] == content_id)["status"] == "completed"
    assert store.get_record(actor, "task-unrelated")["status"] == "open"
    repeated = apply_scenario(store, editor, "content_reviewed")
    assert next(c for c in repeated["content"] if c["id"] == "content-consultation")["status"] == "draft"
    assert next(c for c in repeated["content"] if c["id"] == content_id)["version"] == 2


def test_roles_and_workspace_ownership_are_enforced_in_tools_and_plans(office):
    store, doctor = office
    editor = store.get_actor(doctor.workspace_id, doctor.user_id, "editor")
    coordinator = store.get_actor(doctor.workspace_id, doctor.user_id, "coordinator")
    with pytest.raises(DomainError):
        read_tool(store, editor, "get_preparation_status", {})
    with pytest.raises(DomainError):
        store.get_record(editor, "admin-maya")
    with pytest.raises(DomainError):
        plan(store, editor, [task()])
    with pytest.raises(DomainError):
        plan(
            store,
            coordinator,
            [{"kind": "save_preference", "payload": {"key": "test", "value": "Unauthorized preference"}}],
        )
    proposed = plan(store, doctor, [task()])
    with pytest.raises(DomainError):
        approve_plan(store, editor, proposed["id"])
    with pytest.raises(DomainError):
        store.snapshot(Actor(doctor.workspace_id, "different-user", "doctor"))
    assert all(s["provenance"] == "public" for s in store.snapshot(editor)["sources"])


def test_protected_appointments_and_conflicts_are_rejected(office):
    store, actor = office
    action = meeting()
    action["payload"]["event_id"] = "visit-maya"
    with pytest.raises(DomainError, match="protected"):
        plan(store, actor, [action])
    recording = {
        "kind": "create_recording",
        "payload": {
            "title": "Record a public overview",
            "start": "2026-09-09T10:15:00-07:00",
            "end": "2026-09-09T10:45:00-07:00",
        },
    }
    with pytest.raises(DomainError, match="occupied"):
        plan(store, actor, [recording])
    recording["payload"].update(start="2026-09-09T08:30:00-07:00", end="2026-09-09T09:00:00-07:00")
    with pytest.raises(DomainError, match="protected"):
        plan(store, actor, [recording])


def test_preferences_survive_fresh_actor_and_stale_overwrite_is_rejected(office):
    store, actor = office
    action = {
        "kind": "save_preference",
        "payload": {
            "key": "engineering_updates",
            "value": "Collect written updates by 16:00 before scheduling a meeting.",
        },
    }
    proposed = plan(store, actor, [action])
    approve_plan(store, actor, proposed["id"])
    execute_plan(store, actor, proposed["id"])
    fresh = store.get_actor(actor.workspace_id, actor.user_id, "doctor")
    assert any(p["value"] == action["payload"]["value"] for p in store.get_preferences(fresh))
    stale_plan = plan(store, actor, [action])
    store.update_preference(actor, "pref-team-updates", "Use the written briefing first.")
    approve_plan(store, actor, stale_plan["id"])
    assert execute_plan(store, actor, stale_plan["id"])["status"] == "stale"
    store.delete_preference(actor, "pref-team-updates")
    assert not any(p["id"] == "pref-team-updates" for p in store.get_preferences(actor))


def test_reset_reseeds_same_isolated_workspace(office):
    store, actor = office
    apply_scenario(store, actor, "paperwork_complete")
    reset = store.reset_workspace(actor)
    assert reset["workspace_id"] == actor.workspace_id
    assert reset["stats"]["needs_attention"] == 1
    assert store.get_record(actor, "admin-maya")["version"] == 1


def test_paperwork_update_invalidates_a_prepared_follow_up(office):
    store, actor = office
    proposed = plan(store, actor, [task()])
    before = len(store.snapshot(actor)["tasks"])
    apply_scenario(store, actor, "paperwork_complete")
    approve_plan(store, actor, proposed["id"])
    assert execute_plan(store, actor, proposed["id"])["status"] == "stale"
    assert len(store.snapshot(actor)["tasks"]) == before
    with pytest.raises(DomainError, match="already complete"):
        plan(store, actor, [task()])


def test_expired_approval_cannot_write(office):
    store, actor = office
    proposed = plan(store, actor, [task()])
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_plans SET expires_at=now()-interval '1 minute' WHERE id=%s", (proposed["id"],)
        )
    assert approve_plan(store, actor, proposed["id"])["status"] == "expired"
    with pytest.raises(DomainError):
        execute_plan(store, actor, proposed["id"])


def test_duplicate_or_conflicting_changes_rejected_before_approval(office):
    store, actor = office
    recording = {
        "kind": "create_recording",
        "payload": {
            "title": "Record script",
            "start": "2026-09-09T14:00:00-07:00",
            "end": "2026-09-09T14:30:00-07:00",
        },
    }
    with pytest.raises(DomainError, match="overlap"):
        plan(store, actor, [recording, recording])
    preference = {"kind": "save_preference", "payload": {"key": "content_style", "value": "Be concise."}}
    with pytest.raises(DomainError, match="same preference"):
        plan(store, actor, [preference, preference])
    injection = task()
    injection["payload"]["workspace_id"] = "someone-else"
    with pytest.raises(DomainError, match="Unsupported"):
        plan(store, actor, [injection])


def test_concurrent_executors_preserve_single_receipt(office):
    store, actor = office
    before = len(store.snapshot(actor)["tasks"])
    proposed = plan(
        store,
        actor,
        [
            task(),
            {
                "kind": "deliver_demo_message",
                "payload": {
                    "subject": "Concurrent check",
                    "body": "The demonstration should deliver this once.",
                    "recipient": "Alex Kim",
                },
            },
        ],
    )
    approve_plan(store, actor, proposed["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute_plan(store, actor, proposed["id"]), range(2)))
    assert all(r["status"] == "completed" for r in results)
    assert len(store.snapshot(actor)["tasks"]) == before + 1
    assert sum(m["subject"] == "Concurrent check" for m in store.snapshot(actor)["messages"]) == 1


def test_worker_lease_fences_late_effects(office):
    store, actor = office
    run_id = str(uuid4())
    with store.connection() as conn:
        conn.execute(Path("supabase/migrations/002_runs.sql").read_text())
        conn.execute(
            "INSERT INTO pa_runs(id,workspace_id,user_id,role,message) VALUES (%s,%s,%s,'doctor','Lease test')",
            (run_id, actor.workspace_id, actor.user_id),
        )
        conn.execute(
            "INSERT INTO pa_jobs(id,run_id,workspace_id,status,lease_generation,lease_until) VALUES (%s,%s,%s,'running',2,now()+interval '1 minute')",
            (str(uuid4()), run_id, actor.workspace_id),
        )
    proposed = propose_plan(store, actor, run_id, [task()], "One authorized task")
    approve_plan(store, actor, proposed["id"])
    old_worker = Actor(actor.workspace_id, actor.user_id, actor.role, run_id, 1)
    with pytest.raises(DomainError) as error:
        execute_plan(store, old_worker, proposed["id"])
    assert error.value.code == "lease_lost"
    current_worker = Actor(actor.workspace_id, actor.user_id, actor.role, run_id, 2)
    assert execute_plan(store, current_worker, proposed["id"])["status"] == "completed"


def test_source_change_invalidates_unreviewed_content(office):
    store, actor = office
    proposed = plan(
        store,
        actor,
        [
            {
                "kind": "create_content",
                "payload": {
                    "title": "Pricing",
                    "script": "Discuss individual pricing at consultation.",
                    "caption": "Bring your questions.",
                    "source_ids": ["source-scar-pricing"],
                },
            }
        ],
    )
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_sources SET version=version+1 WHERE workspace_id=%s AND id='source-scar-pricing'",
            (actor.workspace_id,),
        )
    approve_plan(store, actor, proposed["id"])
    assert execute_plan(store, actor, proposed["id"])["status"] == "stale"
    assert len(store.snapshot(actor)["content"]) == 1


def test_handoff_targets_the_referenced_content_not_the_latest(office):
    store, actor = office
    proposed = plan(
        store,
        actor,
        [
            {
                "kind": "create_content",
                "payload": {
                    "title": "A later draft",
                    "script": "Individual pricing is discussed at consultation.",
                    "caption": "Bring questions.",
                    "source_ids": ["source-scar-pricing"],
                },
            }
        ],
    )
    approve_plan(store, actor, proposed["id"])
    completed = execute_plan(store, actor, proposed["id"])
    later_id = completed["actions"][0]["result"]["record"]["id"]
    receipt = apply_handoff(store, actor, "review-older-draft", "content_reviewed", "content-consultation")
    assert receipt["schema_version"] == 1 and receipt["changed"] is True
    assert store.get_record(actor, "content-consultation")["status"] == "approved"
    assert store.get_record(actor, later_id)["status"] == "in_review"
    assert receipt["closed_task_ids"] == []
    later_receipt = apply_handoff(store, actor, "review-later-draft", "content_reviewed", later_id)
    assert later_receipt["closed_task_ids"] == [later_id + "-review"]
    assert store.get_record(actor, later_id + "-review")["status"] == "completed"


def test_handoff_event_and_target_state_idempotence(office):
    store, actor = office
    first = apply_handoff(store, actor, "paperwork-vendor-event-1", "paperwork_completed", "admin-maya")
    assert first["changed"] is True and first["closed_task_ids"] == ["task-prep-maya"]
    replay = apply_handoff(store, actor, "paperwork-vendor-event-1", "paperwork_completed", "admin-maya")
    assert replay["replayed"] is True and replay["record"]["version"] == 2
    independent_repeat = apply_handoff(
        store, actor, "paperwork-vendor-event-2", "paperwork_completed", "admin-maya"
    )
    assert independent_repeat["changed"] is False and independent_repeat["closed_task_ids"] == []
    assert independent_repeat["record"]["version"] == 2
    with pytest.raises(DomainError) as conflict:
        apply_handoff(store, actor, "paperwork-vendor-event-1", "paperwork_completed", "admin-jordan")
    assert conflict.value.code == "event_conflict"
    assert store.get_record(actor, "task-unrelated")["status"] == "open"


def test_handoff_accepts_any_owned_admin_record_and_closes_only_its_work(office):
    store, actor = office
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_office_records SET data=jsonb_set(data,'{paperwork_status}','\"missing\"') WHERE workspace_id=%s AND id='admin-jordan'",
            (actor.workspace_id,),
        )
    jordan_task = task("Confirm Jordan's paperwork")
    jordan_task["payload"]["related_record_id"] = "admin-jordan"
    proposed = plan(store, actor, [jordan_task])
    approve_plan(store, actor, proposed["id"])
    completed = execute_plan(store, actor, proposed["id"])
    task_id = completed["actions"][0]["result"]["record"]["id"]
    receipt = apply_handoff(store, actor, "jordan-paperwork", "paperwork_completed", "admin-jordan")
    assert receipt["closed_task_ids"] == [task_id]
    assert store.get_record(actor, "admin-jordan")["paperwork_status"] == "complete"
    assert store.get_record(actor, "admin-maya")["paperwork_status"] == "missing"
    assert store.get_record(actor, "task-prep-maya")["status"] == "open"


def test_handoff_rejects_wrong_kind_unauthorized_actor_and_editor_office_access(office):
    store, actor = office
    with pytest.raises(DomainError):
        apply_handoff(store, actor, "bad-kind", "content_reviewed", "admin-maya")
    with pytest.raises(DomainError):
        apply_handoff(store, actor, "bad-type", "appointment_cancelled", "visit-maya")
    editor = store.get_actor(actor.workspace_id, actor.user_id, "editor")
    with pytest.raises(DomainError):
        apply_handoff(store, editor, "private-data", "paperwork_completed", "admin-maya")
    wrong_user = Actor(actor.workspace_id, "another-user", "doctor")
    with pytest.raises(DomainError):
        apply_handoff(store, wrong_user, "wrong-user", "content_reviewed", "content-consultation")
    assert (
        apply_handoff(store, editor, "allowed-editor", "content_reviewed", "content-consultation")["changed"]
        is True
    )


def test_editor_recording_availability_has_no_private_records_and_obeys_rules(office):
    store, doctor = office
    editor = store.get_actor(doctor.workspace_id, doctor.user_id, "editor")
    result = read_tool(store, editor, "get_schedule", {})
    assert result["events"] == []
    assert "Maya" not in str(result) and "Jordan" not in str(result)
    assert "engineering-sync" not in str(result) and "visit-maya" not in str(result)
    slots = result["available_recording_slots"]
    assert slots and all(set(s) == {"start", "end"} for s in slots)
    assert all(s["start"].startswith("2026-09-09") for s in slots)
    assert not any(s["start"] == "2026-09-09T08:30:00-07:00" for s in slots)
    events = store.list_records(doctor, "event")
    for slot in slots:
        start, end = parse_time(slot["start"]), parse_time(slot["end"])
        assert start.hour >= 8 and end.hour <= 18
        assert (end - start).total_seconds() == 1800
        assert not any(start < parse_time(e["end"]) and end > parse_time(e["start"]) for e in events)


def test_editor_available_windows_change_when_an_office_slot_is_occupied(office):
    store, doctor = office
    editor = store.get_actor(doctor.workspace_id, doctor.user_id, "editor")
    before = read_tool(store, editor, "get_schedule", {"date": "2026-09-09"})
    candidate = {"start": "2026-09-09T11:00:00-07:00", "end": "2026-09-09T11:30:00-07:00"}
    assert candidate in before["available_recording_slots"]
    plan(store, doctor, [meeting()])
    apply_scenario(store, doctor, "occupy_proposed_slot")
    after = read_tool(store, editor, "get_schedule", {"date": "2026-09-09"})
    assert candidate not in after["available_recording_slots"]
    assert len(after["available_recording_slots"]) == len(before["available_recording_slots"]) - 1
    assert after["events"] == [] and "internal commitment" not in str(after)
    with pytest.raises(DomainError):
        read_tool(store, editor, "get_schedule", {"date": "tomorrow afternoon"})
