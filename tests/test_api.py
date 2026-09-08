"""HTTP boundaries use local signed identities and a real isolated database."""

from fastapi.testclient import TestClient
import pytest

from services.assistant import api
from services.assistant.auth import Identity
from services.assistant.config import Settings
from services.assistant.domain import Actor, execute_plan, propose_plan
from services.assistant.jobs import Jobs


class NoModelCalls:
    def __getattr__(self, name):
        raise AssertionError("This deterministic API test must not call a hosted model: " + name)


@pytest.fixture
def client_office(demo_office, monkeypatch):
    store, _ = demo_office
    config = Settings(
        database_url=store.database_url,
        openrouter_key="unused-test-value",
        supabase_url="",
        supabase_anon_key="",
        environment="local",
        local_auth_secret="isolated-api-tests-use-this-local-signing-secret",
    )
    jobs, identity = Jobs(store), Identity(config)
    monkeypatch.setattr(api, "settings", lambda: config)
    monkeypatch.setattr(api, "services", lambda: (store, jobs, NoModelCalls(), identity))
    with TestClient(api.app, raise_server_exceptions=False) as client:
        token = client.post("/api/dev-session").json()["access_token"]
        authorization = {"Authorization": "Bearer " + token}
        session = client.post("/api/session", headers=authorization, json={"role": "doctor"})
        assert session.status_code == 200
        workspace_id = session.json()["workspace_id"]
        headers = {**authorization, "X-Workspace-Id": workspace_id, "X-Demo-Role": "doctor"}
        actor = store.get_actor(workspace_id, identity.user_id(authorization["Authorization"]), "doctor")
        yield client, store, jobs, actor, headers


def test_http_requires_identity_and_scopes_each_workspace(client_office):
    client, _, _, actor, headers = client_office
    assert client.post("/api/session", json={}).status_code == 401
    other = client.post("/api/dev-session").json()["access_token"]
    stolen_headers = {**headers, "Authorization": "Bearer " + other}
    assert client.get("/api/snapshot", headers=stolen_headers).status_code == 403
    snapshot = client.get("/api/snapshot", headers=headers).json()
    assert snapshot["workspace_id"] == actor.workspace_id
    assert snapshot["preparation"][0]["paperwork_status"] in {"complete", "missing"}


def test_editor_http_views_and_tools_do_not_leak_office_records(client_office):
    client, _, _, actor, headers = client_office
    switched = client.post(
        "/api/session", headers=headers, json={"workspace_id": actor.workspace_id, "role": "editor"}
    )
    assert switched.status_code == 200
    editor_headers = {**headers, "X-Demo-Role": "editor"}
    snapshot = client.get("/api/snapshot", headers=editor_headers).json()
    assert snapshot["patient_admin"] == [] and snapshot["engineering"] == []
    assert "Maya Chen" not in str(snapshot)
    denied = client.post(
        "/api/tools/read", headers=editor_headers, json={"name": "get_preparation_status", "arguments": {}}
    )
    assert denied.status_code == 403 and denied.json()["code"] == "forbidden"
    denied_memory = client.post(
        "/api/preferences/pref-team-updates", headers=editor_headers, json={"value": "An unauthorized edit"}
    )
    assert denied_memory.status_code == 403


def test_run_trace_cannot_be_read_after_switching_to_editor(client_office):
    client, _, jobs, actor, headers = client_office
    run = client.post("/api/runs", headers=headers, json={"message": "Inspect the preparation status"}).json()
    worker = jobs.claim()
    jobs.step(worker, "tool", "Private administration", {"patient_name": "Maya Chen"})
    editor_headers = {**headers, "X-Demo-Role": "editor"}
    assert client.get("/api/runs/" + run["id"], headers=editor_headers).status_code == 404
    assert client.get("/api/runs", headers=editor_headers).json() == {"runs": []}
    assert (
        client.get("/api/runs/" + run["id"], headers=headers).json()["steps"][0]["detail"]["patient_name"]
        == "Maya Chen"
    )
    jobs.cancel(actor, run["id"])


def test_expired_http_approval_does_not_requeue_work(client_office):
    client, store, jobs, actor, headers = client_office
    run = jobs.create(actor, "Save a preference")
    proposed = propose_plan(
        store,
        actor,
        run["id"],
        [
            {
                "kind": "save_preference",
                "payload": {"key": "test_preference", "value": "This expired change must not be saved"},
            }
        ],
        "Review the preference",
    )
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_runs SET status='awaiting_approval',plan_id=%s WHERE id=%s",
            (proposed["id"], run["id"]),
        )
        conn.execute("UPDATE pa_jobs SET status='paused' WHERE run_id=%s", (run["id"],))
        conn.execute(
            "UPDATE pa_plans SET expires_at=now()-interval '1 minute' WHERE id=%s", (proposed["id"],)
        )
    rejected = client.post("/api/plans/" + proposed["id"] + "/approve", headers=headers)
    assert rejected.status_code == 409 and rejected.json()["code"] == "approval_expired"
    assert jobs.get(actor, run["id"])["status"] == "awaiting_approval"
    assert jobs.claim() is None
    assert not any(p["key"] == "test_preference" for p in store.get_preferences(actor))


def test_http_approval_queues_then_actual_executor_persists_changes(client_office):
    client, store, jobs, actor, headers = client_office
    run = jobs.create(actor, "Create a task")
    proposed = propose_plan(
        store,
        actor,
        run["id"],
        [
            {
                "kind": "create_task",
                "payload": {
                    "title": "Approved through HTTP",
                    "owner": "Alex Kim",
                    "due_at": "2026-09-09T15:00:00-07:00",
                },
            }
        ],
        "Assign Alex this task",
    )
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_runs SET status='awaiting_approval',plan_id=%s WHERE id=%s",
            (proposed["id"], run["id"]),
        )
        conn.execute("UPDATE pa_jobs SET status='paused' WHERE run_id=%s", (run["id"],))
    response = client.post("/api/plans/" + proposed["id"] + "/approve", headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "queued"
    assert not any(t["title"] == "Approved through HTTP" for t in store.snapshot(actor)["tasks"])
    worker = jobs.claim()
    worker_actor = Actor(actor.workspace_id, actor.user_id, actor.role, run["id"], worker["lease_generation"])
    completed = execute_plan(store, worker_actor, proposed["id"])
    assert completed["status"] == "completed"
    jobs.update(worker, status="completed", answer="Verified task saved")
    jobs.finish_job(worker)
    refreshed = client.get("/api/snapshot", headers=headers).json()
    assert any(t["title"] == "Approved through HTTP" for t in refreshed["tasks"])
    second_approval = client.post("/api/plans/" + proposed["id"] + "/approve", headers=headers)
    assert second_approval.json()["status"] == "completed" and jobs.claim() is None


def test_handoff_http_deduplicates_and_rejects_changed_payload(client_office):
    client, store, _, actor, headers = client_office
    payload = {"event_id": "vendor-event-1", "event_type": "paperwork_completed", "record_id": "admin-jordan"}
    first = client.post("/api/integrations/handoff", headers=headers, json=payload)
    assert first.status_code == 200
    repeated = client.post("/api/integrations/handoff", headers=headers, json=payload)
    assert repeated.json()["id"] == first.json()["id"]
    changed = client.post(
        "/api/integrations/handoff", headers=headers, json={**payload, "record_id": "admin-maya"}
    )
    assert changed.status_code == 409 and changed.json()["code"] == "event_conflict"
    with store.connection() as conn:
        row = conn.execute(
            "SELECT payload FROM pa_outbox WHERE workspace_id=%s", (actor.workspace_id,)
        ).fetchone()
        assert row["payload"]["record_id"] == "admin-jordan"
    wrong_kind = client.post(
        "/api/integrations/handoff",
        headers=headers,
        json={**payload, "event_id": "wrong-kind", "record_id": "content-consultation"},
    )
    assert wrong_kind.status_code == 400


def test_invalid_requests_fail_before_models_or_office_writes(client_office):
    client, _, _, _, headers = client_office
    assert client.post("/api/runs", headers=headers, json={"message": "   "}).status_code == 400
    assert (
        client.post("/api/runs", headers=headers, json={"message": "A request", "role": "doctor"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/voice/transcribe",
            headers=headers,
            files={"audio": ("invalid.wav", b"not-a-wave-file", "audio/wav")},
        ).status_code
        == 415
    )
    assert client.get("/api/runs/not-a-uuid", headers=headers).status_code == 422
    assert (
        client.post(
            "/api/tools/read",
            headers=headers,
            json={"name": "execute_arbitrary_sql", "arguments": {"sql": "DELETE FROM anything"}},
        ).status_code
        == 400
    )


def test_http_reset_clears_history_and_restores_records(client_office):
    client, _, jobs, actor, headers = client_office
    run = client.post("/api/runs", headers=headers, json={"message": "Before reset"}).json()
    client.post("/api/scenarios", headers=headers, json={"scenario": "paperwork_complete"})
    reset = client.post("/api/reset", headers=headers)
    assert reset.status_code == 200 and reset.json()["stats"]["needs_attention"] == 1
    assert jobs.list(actor) == []
    assert client.get("/api/runs/" + run["id"], headers=headers).status_code == 404
