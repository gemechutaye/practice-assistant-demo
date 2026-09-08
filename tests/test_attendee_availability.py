from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from services.assistant.domain import DomainError, approve_plan, execute_plan, propose_plan


def meeting(start, end):
    return {"kind": "move_meeting", "payload": {"event_id": "engineering-sync", "start": start, "end": end}}


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-09-09T12:30:00-07:00", "2026-09-09T13:00:00-07:00"),
        ("2026-09-09T11:30:00-07:00", "2026-09-09T12:30:00-07:00"),
        ("2026-09-10T14:00:00-07:00", "2026-09-10T14:30:00-07:00"),
    ],
)
def test_free_calendar_time_still_requires_attendee_availability(demo_office, start, end):
    store, actor = demo_office
    with pytest.raises(DomainError) as error:
        propose_plan(store, actor, str(uuid4()), [meeting(start, end)], "Move the meeting")
    assert error.value.code == "attendee_unavailable"


def test_changed_attendee_window_invalidates_approval(demo_office):
    store, actor = demo_office
    plan = propose_plan(
        store,
        actor,
        str(uuid4()),
        [meeting("2026-09-09T14:00:00-07:00", "2026-09-09T14:30:00-07:00")],
        "Move the meeting",
    )
    approve_plan(store, actor, plan["id"])
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_office_records SET data=jsonb_set(data,'{attendee_availability}',%s),version=version+1 WHERE workspace_id=%s AND id='engineering-sync'",
            (
                Jsonb([{"start": "2026-09-09T11:00:00-07:00", "end": "2026-09-09T12:00:00-07:00"}]),
                actor.workspace_id,
            ),
        )
    result = execute_plan(store, actor, plan["id"])
    assert result["status"] == "stale"
    assert store.get_record(actor, "engineering-sync")["start"] == "2026-09-09T09:30:00-07:00"


def test_confirmed_window_executes(demo_office):
    store, actor = demo_office
    plan = propose_plan(
        store,
        actor,
        str(uuid4()),
        [meeting("2026-09-09T14:00:00-07:00", "2026-09-09T14:30:00-07:00")],
        "Move the meeting",
    )
    approve_plan(store, actor, plan["id"])
    assert execute_plan(store, actor, plan["id"])["status"] == "completed"
