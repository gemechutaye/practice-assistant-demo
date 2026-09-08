from uuid import uuid4

import pytest

from services.assistant.domain import DomainError, approve_plan, execute_plan, propose_plan


@pytest.mark.parametrize(
    "action",
    [
        {"kind": "save_preference", "payload": {"key": "private", "value": "An office preference"}},
        {
            "kind": "save_report",
            "payload": {"title": "Private counts", "report_type": "preparation_by_owner"},
        },
        {
            "kind": "move_meeting",
            "payload": {
                "event_id": "engineering-sync",
                "start": "2026-09-09T11:00:00-07:00",
                "end": "2026-09-09T11:30:00-07:00",
            },
        },
        {
            "kind": "create_task",
            "payload": {
                "title": "Private follow-up",
                "owner": "Alex Kim",
                "due_at": "2026-09-09T14:00:00-07:00",
                "related_record_id": "admin-maya",
            },
        },
        {
            "kind": "create_task",
            "payload": {"title": "Unlinked task", "owner": "Alex Kim", "due_at": "2026-09-09T14:00:00-07:00"},
        },
    ],
)
def test_content_route_cannot_use_doctor_authority_for_office_actions(demo_office, action):
    store, doctor = demo_office
    with pytest.raises(DomainError):
        propose_plan(
            store, doctor, str(uuid4()), [action], "A restricted content-route proposal", content_only=True
        )
    with store.connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM pa_plans WHERE workspace_id=%s", (doctor.workspace_id,)
            ).fetchone()["n"]
            == 0
        )


def test_content_route_retains_doctor_approval_owner_with_scoped_actions(demo_office):
    store, doctor = demo_office
    proposed = propose_plan(
        store,
        doctor,
        str(uuid4()),
        [
            {
                "kind": "create_task",
                "payload": {
                    "title": "Review the public draft",
                    "owner": "Jamie Park",
                    "due_at": "2026-09-09T16:00:00-07:00",
                    "related_record_id": "content-consultation",
                },
            }
        ],
        "Assign the editor's review",
        content_only=True,
    )
    assert proposed["role"] == "doctor"
    assert proposed["actions"][0]["payload"]["access_scope"] == "content"
    editor = store.get_actor(doctor.workspace_id, doctor.user_id, "editor")
    with pytest.raises(DomainError):
        approve_plan(store, editor, proposed["id"])
    approve_plan(store, doctor, proposed["id"])
    complete = execute_plan(store, doctor, proposed["id"])
    assert complete["status"] == "completed"
    assert any(t["title"] == "Review the public draft" for t in store.snapshot(editor)["tasks"])
