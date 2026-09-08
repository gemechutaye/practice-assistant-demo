"""Approved, scoped operations against the independent demonstration office."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from .seed import DEMO_CLOCK

ROLES = {"doctor", "coordinator", "editor"}
PACIFIC = ZoneInfo("America/Los_Angeles")


class DomainError(Exception):
    def __init__(self, message: str, code="invalid_argument", status_code=400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.status = status_code


@dataclass(frozen=True)
class Actor:
    workspace_id: str
    user_id: str
    role: str
    run_id: str | None = None
    lease_generation: int | None = None


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        raise DomainError("Use an ISO date and time with a time-zone offset", "invalid_argument")
    if parsed.tzinfo is None:
        raise DomainError("Date and time must include a time-zone offset", "invalid_argument")
    return parsed


def text_field(payload, key, maximum=2000, required=True, default=None):
    value = payload.get(key, default)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise DomainError(f"{key} must contain 1–{maximum} characters", "invalid_argument")
    return value.strip()


def can_read_record(actor, rec):
    if actor.role == "doctor":
        return True
    if actor.role == "coordinator":
        return rec["kind"] != "engineering"
    if actor.role == "editor":
        return (
            rec["kind"] == "content"
            or (rec["kind"] == "event" and rec.get("event_type") == "recording")
            or (rec["kind"] in ("task", "message") and rec.get("access_scope") == "content")
        )
    return False


def preparation_status(admin_records, events):
    by_id = {e["id"]: e for e in events}
    clock = parse_time(DEMO_CLOCK)
    result = []
    for admin in admin_records:
        appointment = by_id.get(admin.get("appointment_id"))
        if not appointment:
            continue
        deadline = parse_time(appointment["start"]) - timedelta(hours=24)
        minutes = int((deadline - clock).total_seconds() // 60)
        result.append(
            {
                **admin,
                "appointment_start": appointment["start"],
                "paperwork_deadline": deadline.isoformat(),
                "minutes_remaining": minutes,
                "timing": "complete"
                if admin["paperwork_status"] == "complete"
                else ("overdue" if minutes < 0 else f"due in {minutes} minutes"),
                "source_id": "source-paperwork-policy",
                "arrival_at": (parse_time(appointment["start"]) - timedelta(minutes=30)).isoformat()
                if appointment.get("appointment_type") == "procedure"
                else None,
                "note": "Administrative paperwork status only; this does not assess clinical readiness.",
            }
        )
    return result


def read_tool(store, actor, name, args):
    if not isinstance(args, dict):
        raise DomainError("Tool arguments must be an object")
    restricted = {"get_preparation_status", "get_engineering_updates", "get_report"}
    if actor.role == "editor" and name in restricted:
        raise DomainError("That office information is unavailable to the content role", "forbidden", 403)
    if name == "get_engineering_updates" and actor.role != "doctor":
        raise DomainError("Engineering decisions are available to the doctor role", "forbidden", 403)
    if name == "get_preferences":
        return {"preferences": store.get_preferences(actor)}
    if name == "get_report":
        return store.get_report(actor, args.get("report_type", "preparation_by_owner"))
    if name == "get_preparation_status":
        result = preparation_status(
            store.list_records(actor, "patient_admin"), store.list_records(actor, "event")
        )
        if args.get("patient_id") or args.get("id"):
            target = args.get("patient_id", args.get("id"))
            result = [r for r in result if r["id"] == target or r.get("appointment_id") == target]
        return {
            "clock": DEMO_CLOCK,
            "patients": result,
            "preparation": result,
            "source_id": "source-paperwork-policy",
        }
    mapping = {
        "get_schedule": ("event", "events"),
        "find_messages": ("message", "messages"),
        "get_open_tasks": ("task", "tasks"),
        "get_engineering_updates": ("engineering", "engineering"),
        "get_content": ("content", "content"),
    }
    if name not in mapping:
        raise DomainError("Unknown read tool", "invalid_tool")
    kind, key = mapping[name]
    records = store.list_records(actor, kind)
    target = args.get("id") or args.get("record_id")
    if target:
        records = [r for r in records if r["id"] == target]
        if not records:
            raise DomainError("Record is unavailable for this role", "not_found", 404)
    query = args.get("query", "")
    if query:
        if not isinstance(query, str):
            raise DomainError("query must be text")
        records = [r for r in records if query.casefold() in str(r).casefold()]
    if kind == "task":
        records = [r for r in records if r.get("status") == args.get("status", "open")]
    if kind == "event":
        records.sort(key=lambda r: parse_time(r["start"]))
        date = args.get("date")
        if date:
            records = [
                r for r in records if parse_time(r["start"]).astimezone(PACIFIC).date().isoformat() == date
            ]
        if args.get("start"):
            start = parse_time(args["start"])
            records = [r for r in records if parse_time(r["end"]) > start]
        if args.get("end"):
            end = parse_time(args["end"])
            records = [r for r in records if parse_time(r["start"]) < end]
    result = {key: records, "clock": DEMO_CLOCK}
    if kind == "event" and actor.role == "editor":
        result["available_recording_slots"] = available_recording_slots(store, actor, args.get("date"))
        result["recording_slot_minutes"] = 30
        result["availability_note"] = (
            "Free recording times computed from the office calendar and preparation rules. Private calendar details are omitted."
        )
    return result


def _calendar(conn, workspace_id):
    return conn.execute(
        "SELECT id,version,data FROM pa_office_records WHERE workspace_id=%s AND kind='event' ORDER BY id",
        (workspace_id,),
    ).fetchall()


def available_recording_slots(store, actor, local_date=None):
    """Share free half-hour windows without disclosing any private event record."""
    if local_date is None:
        target_date = parse_time(DEMO_CLOCK).astimezone(PACIFIC).date() + timedelta(days=1)
    else:
        try:
            target_date = date.fromisoformat(local_date)
        except (ValueError, TypeError):
            raise DomainError("Choose a calendar date in YYYY-MM-DD format", "invalid_argument")
    beginning = datetime.combine(target_date, time(8), PACIFIC)
    closing = datetime.combine(target_date, time(18), PACIFIC)
    with store.connection() as conn:
        store.authorize(conn, actor)
        events = _calendar(conn, actor.workspace_id)
    busy = [(parse_time(e["data"]["start"]), parse_time(e["data"]["end"])) for e in events]
    patients = [
        parse_time(e["data"]["start"])
        for e in events
        if e["data"].get("event_type") == "patient"
        and parse_time(e["data"]["start"]).astimezone(PACIFIC).date() == target_date
    ]
    if patients:
        first = min(patients)
        busy.append((first - timedelta(minutes=30), first))
    slots = []
    start = beginning
    while start + timedelta(minutes=30) <= closing:
        end = start + timedelta(minutes=30)
        if not any(start < busy_end and end > busy_start for busy_start, busy_end in busy):
            slots.append({"start": start.isoformat(), "end": end.isoformat()})
        start = end
    return slots


def _validate_slot(conn, actor, payload, ignored_id=None):
    start, end = parse_time(payload["start"]), parse_time(payload["end"])
    local_start, local_end = start.astimezone(PACIFIC), end.astimezone(PACIFIC)
    if end <= start or end - start > timedelta(hours=4):
        raise DomainError("Choose a positive meeting duration of no more than four hours")
    if (
        local_start.date() != local_end.date()
        or local_start.hour < 8
        or local_end > local_end.replace(hour=18, minute=0, second=0, microsecond=0)
    ):
        raise DomainError("Choose a slot within demonstration office hours, 08:00–18:00 Pacific")
    events = _calendar(conn, actor.workspace_id)
    for event in events:
        if event["id"] == ignored_id:
            continue
        event_start, event_end = parse_time(event["data"]["start"]), parse_time(event["data"]["end"])
        if start < event_end and end > event_start:
            raise DomainError(
                "That calendar slot is occupied; read the current schedule and choose another slot",
                "calendar_conflict",
                409,
            )
    patients = [
        e
        for e in events
        if e["data"].get("event_type") == "patient"
        and parse_time(e["data"]["start"]).astimezone(PACIFIC).date() == local_start.date()
    ]
    if patients:
        first = min(parse_time(e["data"]["start"]) for e in patients)
        if start < first and end > first - timedelta(minutes=30):
            raise DomainError(
                "The 30 minutes before the first patient appointment are protected", "calendar_conflict", 409
            )


def _validate_action(store, conn, actor, action):
    if not isinstance(action, dict) or set(action) - {"kind", "payload"}:
        raise DomainError("An action contains only kind and payload")
    kind, raw = action.get("kind"), action.get("payload")
    if not isinstance(raw, dict):
        raise DomainError("Action payload must be an object")
    allowed = {
        "move_meeting": {"event_id", "start", "end"},
        "create_task": {
            "title",
            "owner",
            "due_at",
            "related_record_id",
            "workflow",
            "auto_close_on_paperwork",
        },
        "deliver_demo_message": {"subject", "body", "recipient", "related_record_id"},
        "save_preference": {"key", "value", "scope"},
        "create_content": {"title", "script", "caption", "reviewer", "source_ids", "status"},
        "create_recording": {"title", "start", "end", "related_record_id"},
        "save_report": {"title", "report_type"},
    }
    if kind not in allowed:
        raise DomainError("Unknown action kind")
    extra = set(raw) - allowed[kind]
    if extra:
        raise DomainError("Unsupported action fields: " + ", ".join(sorted(extra)))
    if actor.role == "editor" and kind not in {
        "create_content",
        "create_recording",
        "create_task",
        "deliver_demo_message",
    }:
        raise DomainError("This action is unavailable to the content role", "forbidden", 403)
    if kind == "save_preference" and actor.role != "doctor":
        raise DomainError("Only the doctor can save preferences", "forbidden", 403)
    payload, preconditions = {}, {}
    if kind in ("move_meeting", "create_recording"):
        payload.update(
            start=parse_time(text_field(raw, "start")).isoformat(),
            end=parse_time(text_field(raw, "end")).isoformat(),
        )
        if kind == "move_meeting":
            event_id = text_field(raw, "event_id", 150)
            event = store.get_record(actor, event_id, conn)
            if event["kind"] != "event" or event.get("event_type") != "internal":
                raise DomainError(
                    "Only internal meetings can be moved; patient appointments are protected",
                    "forbidden",
                    403,
                )
            payload["event_id"] = event_id
            preconditions["record"] = {"id": event_id, "version": event["version"]}
        else:
            payload.update(
                title=text_field(raw, "title", 200), owner="Dr. Avery Morgan", event_type="recording"
            )
            if raw.get("related_record_id"):
                related = store.get_record(actor, text_field(raw, "related_record_id", 150), conn)
                if related["kind"] != "content":
                    raise DomainError("Recording holds can link only to content")
                payload["related_record_id"] = related["id"]
                preconditions["related_record"] = {"id": related["id"], "version": related["version"]}
        _validate_slot(conn, actor, payload, payload.get("event_id"))
        preconditions["calendar"] = {r["id"]: r["version"] for r in _calendar(conn, actor.workspace_id)}
    elif kind == "create_task":
        payload.update(
            title=text_field(raw, "title", 240),
            owner=text_field(raw, "owner", 120),
            due_at=parse_time(text_field(raw, "due_at")).isoformat(),
            status="open",
            access_scope="office",
        )
        related_id = text_field(raw, "related_record_id", 150, required=False)
        if related_id:
            related = store.get_record(actor, related_id, conn)
            payload["related_record_id"] = related_id
            preconditions["related_record"] = {"id": related_id, "version": related["version"]}
            if related["kind"] == "content":
                payload["access_scope"] = "content"
                payload["workflow"] = "content_review"
                payload["follow_up_permission"] = (
                    "Close this linked review task when its content is marked reviewed."
                )
            if related["kind"] == "patient_admin":
                payload["workflow"] = "preparation"
                if raw.get("auto_close_on_paperwork") is True:
                    if related.get("paperwork_status") == "complete":
                        raise DomainError(
                            "This paperwork is already complete; refresh the preparation status before assigning follow-up",
                            "stale_plan",
                            409,
                        )
                    payload["auto_close_on_paperwork"] = True
                    payload["follow_up_permission"] = (
                        "Close only this linked preparation task when its paperwork record becomes complete."
                    )
        elif actor.role == "editor":
            raise DomainError("Content tasks must link to an accessible content record", "forbidden", 403)
        if actor.role == "editor" and payload["access_scope"] != "content":
            raise DomainError("Content tasks must link to an accessible content record", "forbidden", 403)
        if "auto_close_on_paperwork" in raw and not isinstance(raw["auto_close_on_paperwork"], bool):
            raise DomainError("auto_close_on_paperwork must be a boolean")
    elif kind == "deliver_demo_message":
        payload.update(
            subject=text_field(raw, "subject", 240),
            body=text_field(raw, "body", 8000),
            recipient=text_field(raw, "recipient", 160),
            sender="Jamie Park" if actor.role == "editor" else "Dr. Avery Morgan",
            status="delivered_to_demo_inbox",
            access_scope="content" if actor.role == "editor" else "office",
        )
        if raw.get("related_record_id"):
            related = store.get_record(actor, text_field(raw, "related_record_id", 150), conn)
            payload["related_record_id"] = related["id"]
            preconditions["related_record"] = {"id": related["id"], "version": related["version"]}
            if related["kind"] == "content":
                payload["access_scope"] = "content"
    elif kind == "save_preference":
        payload.update(
            key=text_field(raw, "key", 100),
            value=text_field(raw, "value", 2000),
            scope=raw.get("scope", "doctor"),
        )
        if payload["scope"] not in {"doctor", "content"}:
            raise DomainError("Preference scope must be doctor or content")
        current = conn.execute(
            "SELECT id,version FROM pa_preferences WHERE workspace_id=%s AND key=%s",
            (actor.workspace_id, payload["key"]),
        ).fetchone()
        preconditions["preference"] = {
            "key": payload["key"],
            "version": current["version"] if current else None,
        }
    elif kind == "create_content":
        payload.update(
            title=text_field(raw, "title", 240),
            script=text_field(raw, "script", 12000),
            caption=text_field(raw, "caption", 3000),
            reviewer=text_field(raw, "reviewer", 120, default="Jamie Park"),
            status=raw.get("status", "in_review"),
            access_scope="content",
        )
        source_ids = raw.get("source_ids")
        if (
            not isinstance(source_ids, list)
            or not 1 <= len(source_ids) <= 10
            or not all(isinstance(s, str) for s in source_ids)
        ):
            raise DomainError("Content must cite one to ten public source IDs")
        sources = {s["id"]: s for s in store.get_sources(actor, conn) if s["provenance"] == "public"}
        if any(s not in sources for s in source_ids):
            raise DomainError("Content cites an unavailable public source")
        payload["source_ids"] = list(dict.fromkeys(source_ids))
        preconditions["sources"] = {s: sources[s]["version"] for s in payload["source_ids"]}
        if payload["status"] not in {"draft", "in_review"}:
            raise DomainError("New content must be draft or in_review")
        if payload["status"] == "in_review":
            payload["review_task"] = {
                "title": "Review: " + payload["title"],
                "owner": payload["reviewer"],
                "due_at": "2026-09-09T16:00:00-07:00",
                "follow_up_permission": "Close this linked review task when its content is marked reviewed.",
            }
    elif kind == "save_report":
        payload.update(
            title=text_field(raw, "title", 240), report_type=raw.get("report_type", "preparation_by_owner")
        )
        store.get_report(actor, payload["report_type"], conn)
    return kind, payload, preconditions


def propose_plan(store, actor, run_id, actions, summary, *, content_only=False):
    if not isinstance(actions, list) or not 1 <= len(actions) <= 12:
        raise DomainError("A plan must contain one to twelve actions")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 4000:
        raise DomainError("A plan needs a concise summary")
    plan_id = str(uuid4())
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    with store.connection() as conn:
        store.authorize(conn, actor, lock=True)
        action_actor = Actor(actor.workspace_id, actor.user_id, "editor") if content_only else actor
        validated = [_validate_action(store, conn, action_actor, a) for a in actions]
        targets = [p["event_id"] for kind, p, _ in validated if kind == "move_meeting"]
        if len(targets) != len(set(targets)):
            raise DomainError("A plan cannot move the same meeting twice")
        preference_keys = [p["key"] for kind, p, _ in validated if kind == "save_preference"]
        if len(preference_keys) != len(set(preference_keys)):
            raise DomainError("A plan cannot change the same preference twice")
        proposed_slots = [p for kind, p, _ in validated if kind in {"move_meeting", "create_recording"}]
        for index, slot in enumerate(proposed_slots):
            for other in proposed_slots[index + 1 :]:
                if parse_time(slot["start"]) < parse_time(other["end"]) and parse_time(
                    slot["end"]
                ) > parse_time(other["start"]):
                    raise DomainError(
                        "The proposed calendar changes overlap each other; choose separate slots",
                        "calendar_conflict",
                        409,
                    )
        conn.execute(
            "INSERT INTO pa_plans(id,workspace_id,run_id,user_id,role,summary,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (plan_id, actor.workspace_id, str(run_id), actor.user_id, actor.role, summary.strip(), expires),
        )
        for index, (kind, payload, preconditions) in enumerate(validated):
            action_id = str(uuid4())
            if kind not in {"move_meeting", "save_preference"}:
                payload["record_id"] = "action-" + action_id
            conn.execute(
                "INSERT INTO pa_actions(id,plan_id,position,kind,payload,preconditions) VALUES (%s,%s,%s,%s,%s,%s)",
                (action_id, plan_id, index, kind, Jsonb(payload), Jsonb(preconditions)),
            )
        store.touch(conn, actor.workspace_id)
    return store.get_plan(actor, plan_id)


def _owned_plan(store, conn, actor, plan_id):
    store.authorize(conn, actor, lock=True)
    try:
        UUID(str(plan_id))
    except (ValueError, TypeError, AttributeError):
        raise DomainError("Plan not found", "not_found", 404)
    plan = conn.execute(
        "SELECT * FROM pa_plans WHERE id=%s AND workspace_id=%s AND user_id=%s AND role=%s FOR UPDATE",
        (plan_id, actor.workspace_id, actor.user_id, actor.role),
    ).fetchone()
    if not plan:
        raise DomainError("Plan is unavailable for this role", "not_found", 404)
    return plan


def _fence(conn, actor, plan):
    if actor.run_id is None:
        return
    if actor.run_id != str(plan["run_id"]) or actor.lease_generation is None:
        raise DomainError("Worker no longer owns this run", "lease_lost", 409)
    job = conn.execute(
        "SELECT id FROM pa_jobs WHERE run_id=%s AND workspace_id=%s AND lease_generation=%s AND lease_until>now() AND status='running' FOR UPDATE",
        (actor.run_id, actor.workspace_id, actor.lease_generation),
    ).fetchone()
    if not job:
        raise DomainError("Worker lease expired; another worker will resume the run", "lease_lost", 409)


def approve_plan(store, actor, plan_id):
    with store.connection() as conn:
        plan = _owned_plan(store, conn, actor, plan_id)
        if plan["status"] in {"completed", "approved", "partial"}:
            return store.get_plan(actor, plan_id, conn)
        if plan["status"] != "pending":
            raise DomainError("This plan requires a new proposal", "stale_plan", 409)
        if plan["expires_at"] <= datetime.now(timezone.utc):
            conn.execute(
                "UPDATE pa_plans SET status='expired',error='Approval expired. Prepare a fresh plan.' WHERE id=%s",
                (plan_id,),
            )
        else:
            conn.execute("UPDATE pa_plans SET status='approved',approved_at=now() WHERE id=%s", (plan_id,))
            conn.execute(
                "UPDATE pa_actions SET status='approved' WHERE plan_id=%s AND status='proposed'", (plan_id,)
            )
        store.touch(conn, actor.workspace_id)
    return store.get_plan(actor, plan_id)


def _check_preconditions(conn, actor, plan_id, action):
    pre = action["preconditions"]
    if "related_record" in pre:
        related = pre["related_record"]
        row = conn.execute(
            "SELECT version FROM pa_office_records WHERE workspace_id=%s AND id=%s",
            (actor.workspace_id, related["id"]),
        ).fetchone()
        expected = related["version"]
        own_receipts = conn.execute(
            "SELECT r.result FROM pa_action_receipts r JOIN pa_actions a ON a.id=r.operation_id WHERE a.plan_id=%s",
            (plan_id,),
        ).fetchall()
        for receipt in own_receipts:
            rec = receipt["result"].get("record", {})
            if rec.get("id") == related["id"]:
                expected = rec["version"]
        if not row or row["version"] != expected:
            raise DomainError(
                "A record linked to this action changed. Read its current state and prepare a fresh proposal.",
                "stale_plan",
                409,
            )
    target = pre.get("record")
    if target:
        row = conn.execute(
            "SELECT version FROM pa_office_records WHERE workspace_id=%s AND id=%s",
            (actor.workspace_id, target["id"]),
        ).fetchone()
        if not row or row["version"] != target["version"]:
            raise DomainError(
                "The proposed record changed. Read the latest state and prepare a new plan.",
                "stale_plan",
                409,
            )
    if "calendar" in pre:
        expected = dict(pre["calendar"])
        receipts = conn.execute(
            "SELECT r.result FROM pa_action_receipts r JOIN pa_actions a ON a.id=r.operation_id WHERE a.plan_id=%s",
            (plan_id,),
        ).fetchall()
        for receipt in receipts:
            rec = receipt["result"].get("record", {})
            if rec.get("kind") == "event":
                expected[rec["id"]] = rec["version"]
        current = {r["id"]: r["version"] for r in _calendar(conn, actor.workspace_id)}
        if current != expected:
            raise DomainError(
                "The calendar changed after this plan was prepared. Read the new schedule and prepare a fresh proposal.",
                "stale_plan",
                409,
            )
    if "preference" in pre:
        row = conn.execute(
            "SELECT version FROM pa_preferences WHERE workspace_id=%s AND key=%s",
            (actor.workspace_id, pre["preference"]["key"]),
        ).fetchone()
        if (row["version"] if row else None) != pre["preference"]["version"]:
            raise DomainError("This preference changed after the plan was prepared", "stale_plan", 409)
    for source_id, version in pre.get("sources", {}).items():
        row = conn.execute(
            "SELECT version FROM pa_sources WHERE workspace_id=%s AND id=%s", (actor.workspace_id, source_id)
        ).fetchone()
        if not row or row["version"] != version:
            raise DomainError(
                "A cited source changed; prepare the draft using its current version", "stale_plan", 409
            )


def _write_action(store, conn, actor, action):
    kind, payload = action["kind"], dict(action["payload"])
    operation_id = str(action["id"])
    if kind == "move_meeting":
        event = store.get_record(actor, payload["event_id"], conn, lock=True)
        if event.get("event_type") != "internal":
            raise DomainError("Patient appointments are protected", "forbidden", 403)
        _validate_slot(conn, actor, payload, payload["event_id"])
        data = {k: v for k, v in event.items() if k not in {"id", "kind", "version"}}
        data.update(start=payload["start"], end=payload["end"])
        conn.execute(
            "UPDATE pa_office_records SET data=%s,version=version+1,updated_at=now() WHERE workspace_id=%s AND id=%s",
            (Jsonb(data), actor.workspace_id, event["id"]),
        )
        result = {
            "operation_id": operation_id,
            "record": store.get_record(actor, event["id"], conn),
            "verification": "Read back the saved calendar record",
        }
    elif kind == "save_preference":
        if actor.role != "doctor":
            raise DomainError("Only the doctor can save preferences", "forbidden", 403)
        pref_id = "preference-" + operation_id
        row = conn.execute(
            "INSERT INTO pa_preferences(workspace_id,id,key,value,user_id,scope,source_request) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,key) DO UPDATE SET value=EXCLUDED.value,scope=EXCLUDED.scope,version=pa_preferences.version+1,updated_at=now(),source_request=EXCLUDED.source_request RETURNING id,key,value,version,scope",
            (
                actor.workspace_id,
                pref_id,
                payload["key"],
                Jsonb(payload["value"]),
                actor.user_id,
                payload["scope"],
                "Confirmed in approved plan " + str(action["plan_id"]),
            ),
        ).fetchone()
        result = {
            "operation_id": operation_id,
            "preference": row,
            "verification": "Read back the confirmed preference",
        }
    else:
        record_id = payload.pop("record_id")
        record_kind = {
            "create_task": "task",
            "deliver_demo_message": "message",
            "create_content": "content",
            "create_recording": "event",
            "save_report": "report",
        }[kind]
        if kind == "create_recording":
            _validate_slot(conn, actor, payload)
        payload.update(source_system="practice-demo", external_id=operation_id, source_version="1")
        review_task = payload.pop("review_task", None)
        conn.execute(
            "INSERT INTO pa_office_records(workspace_id,id,kind,data) VALUES (%s,%s,%s,%s)",
            (actor.workspace_id, record_id, record_kind, Jsonb(payload)),
        )
        result = {
            "operation_id": operation_id,
            "record": store.get_record(actor, record_id, conn),
            "verification": "Read back the saved " + record_kind + " record",
        }
        if review_task:
            task_id = record_id + "-review"
            review_task.update(
                status="open",
                workflow="content_review",
                related_record_id=record_id,
                access_scope="content",
                source_system="practice-demo",
            )
            conn.execute(
                "INSERT INTO pa_office_records(workspace_id,id,kind,data) VALUES (%s,%s,'task',%s)",
                (actor.workspace_id, task_id, Jsonb(review_task)),
            )
            result["review_task"] = store.get_record(actor, task_id, conn)
        if kind == "deliver_demo_message":
            result["delivery"] = "Delivered to demo inbox. No external message was sent."
        if kind == "save_report":
            result["computed"] = store.get_report(actor, payload["report_type"], conn)
    conn.execute(
        "INSERT INTO pa_action_receipts(operation_id,workspace_id,result) VALUES (%s,%s,%s)",
        (operation_id, actor.workspace_id, Jsonb(result)),
    )
    conn.execute(
        "UPDATE pa_actions SET status='completed',result=%s,error=NULL WHERE id=%s",
        (Jsonb(result), operation_id),
    )
    store.touch(conn, actor.workspace_id)
    return result


def execute_plan(store, actor, plan_id):
    with store.connection() as conn:
        plan = _owned_plan(store, conn, actor, plan_id)
        if plan["status"] == "completed":
            return store.get_plan(actor, plan_id, conn)
        if plan["status"] not in {"approved", "partial"}:
            raise DomainError("This plan must be approved before execution", "approval_required", 409)
        _fence(conn, actor, plan)
        if plan["expires_at"] <= datetime.now(timezone.utc):
            conn.execute(
                "UPDATE pa_plans SET status='expired',error='The approval expired before the remaining actions ran.' WHERE id=%s",
                (plan_id,),
            )
            return store.get_plan(actor, plan_id, conn)
        action_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM pa_actions WHERE plan_id=%s ORDER BY position", (plan_id,)
            ).fetchall()
        ]
        # Detect already-known stale state before committing any additional action.
        pending = conn.execute(
            "SELECT a.* FROM pa_actions a LEFT JOIN pa_action_receipts r ON r.operation_id=a.id WHERE a.plan_id=%s AND r.operation_id IS NULL ORDER BY a.position",
            (plan_id,),
        ).fetchall()
        for action in pending:
            try:
                _check_preconditions(conn, actor, plan_id, action)
            except DomainError as error:
                conn.execute("UPDATE pa_plans SET status='stale',error=%s WHERE id=%s", (str(error), plan_id))
                conn.execute(
                    "UPDATE pa_actions SET status='failed',error=%s WHERE id=%s", (str(error), action["id"])
                )
                store.touch(conn, actor.workspace_id)
                return store.get_plan(actor, plan_id, conn)
    for action_id in action_ids:
        timeout = False
        try:
            with store.connection() as conn:
                plan = _owned_plan(store, conn, actor, plan_id)
                _fence(conn, actor, plan)
                if plan["status"] == "completed":
                    return store.get_plan(actor, plan_id, conn)
                if plan["status"] not in {"approved", "partial"}:
                    raise DomainError("This plan is no longer executable", "stale_plan", 409)
                if plan["expires_at"] <= datetime.now(timezone.utc):
                    raise DomainError("The approval expired before this action ran", "approval_expired", 409)
                action = conn.execute(
                    "SELECT * FROM pa_actions WHERE id=%s FOR UPDATE", (action_id,)
                ).fetchone()
                receipt = conn.execute(
                    "SELECT result FROM pa_action_receipts WHERE operation_id=%s AND workspace_id=%s",
                    (action_id, actor.workspace_id),
                ).fetchone()
                if receipt:
                    conn.execute(
                        "UPDATE pa_actions SET status='completed',result=%s,error=NULL WHERE id=%s",
                        (Jsonb({**receipt["result"], "reconciled": True}), action_id),
                    )
                    continue
                _check_preconditions(conn, actor, plan_id, action)
                _write_action(store, conn, actor, action)
                workspace = store.authorize(conn, actor)
                if action["kind"] == "create_task" and workspace["scenario"].get("task_timeout_after_write"):
                    conn.execute(
                        "UPDATE pa_workspaces SET scenario=scenario-'task_timeout_after_write' WHERE id=%s",
                        (actor.workspace_id,),
                    )
                    timeout = True
            if timeout:
                with store.connection() as conn:
                    _owned_plan(store, conn, actor, plan_id)
                    conn.execute(
                        "UPDATE pa_actions SET status='outcome_unknown',error='The task service response was interrupted after its database commit. Resume to verify the receipt.' WHERE id=%s",
                        (action_id,),
                    )
                    conn.execute(
                        "UPDATE pa_plans SET status='partial',error='A task response timed out. The next attempt will check its operation receipt before retrying.' WHERE id=%s",
                        (plan_id,),
                    )
                    store.touch(conn, actor.workspace_id)
                return store.get_plan(actor, plan_id)
        except DomainError as error:
            if error.code == "lease_lost":
                raise
            with store.connection() as conn:
                _owned_plan(store, conn, actor, plan_id)
                conn.execute(
                    "UPDATE pa_actions SET status='failed',error=%s WHERE id=%s", (str(error), action_id)
                )
                failure_status = (
                    "expired"
                    if error.code == "approval_expired"
                    else ("stale" if error.code in {"stale_plan", "calendar_conflict"} else "failed")
                )
                conn.execute(
                    "UPDATE pa_plans SET status=%s,error=%s WHERE id=%s",
                    (failure_status, str(error), plan_id),
                )
                store.touch(conn, actor.workspace_id)
            return store.get_plan(actor, plan_id)
    with store.connection() as conn:
        plan = _owned_plan(store, conn, actor, plan_id)
        _fence(conn, actor, plan)
        conn.execute("UPDATE pa_plans SET status='completed',error=NULL WHERE id=%s", (plan_id,))
        store.touch(conn, actor.workspace_id)
    return store.get_plan(actor, plan_id)


def apply_handoff(
    store,
    actor,
    event_id,
    event_type,
    record_id,
    outbox_id: str | None = None,
    outbox_generation: int | None = None,
):
    """Apply a version-one fictional handoff to its exact referenced record.

    The event receipt and all office effects commit together. An event ID is
    bound to its payload; independently repeated events also respect target state.
    """
    event_id = text_field({"event_id": event_id}, "event_id", 100)
    record_id = text_field({"record_id": record_id}, "record_id", 150)
    if event_type not in {"paperwork_completed", "content_reviewed"}:
        raise DomainError("Unknown version-one handoff event type", "invalid_event")
    if event_type == "paperwork_completed" and actor.role not in {"doctor", "coordinator"}:
        raise DomainError("This role cannot receive paperwork handoffs", "forbidden", 403)
    payload = {"schema_version": 1, "event_type": event_type, "record_id": record_id}
    event_key = "handoff:" + event_id
    with store.connection() as conn:
        store.authorize(conn, actor, lock=True)
        if outbox_id is not None or outbox_generation is not None:
            try:
                UUID(str(outbox_id))
            except (ValueError, TypeError, AttributeError):
                raise DomainError("This worker no longer owns the handoff", "lease_lost", 409)
            if type(outbox_generation) is not int or outbox_generation < 1:
                raise DomainError("This worker no longer owns the handoff", "lease_lost", 409)
            owned_event = conn.execute(
                "SELECT id FROM pa_outbox WHERE id=%s AND workspace_id=%s AND user_id=%s AND role=%s AND status='processing' AND lease_generation=%s AND lease_until>now() AND event_key=%s AND payload->>'event_type'=%s AND payload->>'record_id'=%s FOR UPDATE",
                (
                    outbox_id,
                    actor.workspace_id,
                    actor.user_id,
                    actor.role,
                    outbox_generation,
                    event_id,
                    event_type,
                    record_id,
                ),
            ).fetchone()
            if not owned_event:
                raise DomainError("This handoff lease expired or its workspace was reset", "lease_lost", 409)
        prior = conn.execute(
            "SELECT result FROM pa_scenario_events WHERE workspace_id=%s AND event_key=%s",
            (actor.workspace_id, event_key),
        ).fetchone()
        if prior and prior["result"].get("payload") != payload:
            raise DomainError(
                "This event ID was already used with a different handoff payload", "event_conflict", 409
            )
        target = store.get_record(actor, record_id, conn, lock=True)
        expected_kind = "patient_admin" if event_type == "paperwork_completed" else "content"
        if target["kind"] != expected_kind:
            raise DomainError("This handoff event does not match the referenced record kind", "invalid_event")
        if prior:
            return {**prior["result"], "replayed": True}
        if event_type == "paperwork_completed":
            changed = target.get("paperwork_status") != "complete"
            if changed:
                conn.execute(
                    "UPDATE pa_office_records SET data=jsonb_set(data,'{paperwork_status}','\"complete\"'),version=version+1,updated_at=now() WHERE workspace_id=%s AND id=%s",
                    (actor.workspace_id, record_id),
                )
            closed = conn.execute(
                "UPDATE pa_office_records t SET data=t.data || '{\"status\":\"completed\",\"completion_reason\":\"Linked paperwork is complete\"}'::jsonb,version=t.version+1,updated_at=now() WHERE t.workspace_id=%s AND t.kind='task' AND t.data->>'status'='open' AND t.data->>'related_record_id'=%s AND t.data->>'workflow'='preparation' AND t.data->>'auto_close_on_paperwork'='true' AND t.data ? 'follow_up_permission' AND EXISTS (SELECT 1 FROM pa_office_records a WHERE a.workspace_id=t.workspace_id AND a.id=%s AND a.kind='patient_admin' AND a.data->>'paperwork_status'='complete') RETURNING t.id",
                (actor.workspace_id, record_id, record_id),
            ).fetchall()
        else:
            if target.get("status") not in {"draft", "in_review", "approved"}:
                raise DomainError(
                    "Only saved content drafts can receive a review handoff", "invalid_state", 409
                )
            changed = target["status"] != "approved"
            if changed:
                conn.execute(
                    'UPDATE pa_office_records SET data=data || \'{"status":"approved","review_note":"Reviewed in the demonstration; nothing was published"}\'::jsonb,version=version+1,updated_at=now() WHERE workspace_id=%s AND id=%s',
                    (actor.workspace_id, record_id),
                )
            closed = conn.execute(
                "UPDATE pa_office_records t SET data=t.data || '{\"status\":\"completed\",\"completion_reason\":\"Linked content was reviewed\"}'::jsonb,version=t.version+1,updated_at=now() WHERE t.workspace_id=%s AND t.kind='task' AND t.data->>'related_record_id'=%s AND t.data->>'status'='open' AND t.data->>'workflow'='content_review' AND t.data ? 'follow_up_permission' AND EXISTS (SELECT 1 FROM pa_office_records c WHERE c.workspace_id=t.workspace_id AND c.id=%s AND c.kind='content' AND c.data->>'status'='approved') RETURNING t.id",
                (actor.workspace_id, record_id, record_id),
            ).fetchall()
        result = {
            **payload,
            "payload": payload,
            "event_id": event_id,
            "source_system": "practice-demo",
            "changed": changed,
            "closed_task_ids": sorted(r["id"] for r in closed),
            "record": store.get_record(actor, record_id, conn),
            "replayed": False,
        }
        conn.execute(
            "INSERT INTO pa_scenario_events(workspace_id,event_key,result) VALUES (%s,%s,%s)",
            (actor.workspace_id, event_key, Jsonb(result)),
        )
        if changed or closed:
            store.touch(conn, actor.workspace_id)
        return result


def apply_scenario(store, actor, scenario):
    allowed = {
        "paperwork_complete",
        "occupy_proposed_slot",
        "task_timeout_after_write",
        "reset_failure",
        "content_reviewed",
    }
    if scenario not in allowed:
        raise DomainError("Unknown demonstration scenario")
    if actor.role == "editor" and scenario != "content_reviewed":
        raise DomainError("Only office roles can change office scenarios", "forbidden", 403)
    if scenario == "paperwork_complete":
        apply_handoff(store, actor, "scenario-paperwork-admin-maya", "paperwork_completed", "admin-maya")
        return store.snapshot(actor)
    if scenario == "content_reviewed":
        with store.connection() as conn:
            store.authorize(conn, actor)
            row = conn.execute(
                "SELECT id FROM pa_office_records WHERE workspace_id=%s AND kind='content' ORDER BY updated_at DESC,id LIMIT 1",
                (actor.workspace_id,),
            ).fetchone()
        if row:
            event_id = "scenario-review-" + str(uuid5(NAMESPACE_URL, row["id"]))
            apply_handoff(store, actor, event_id, "content_reviewed", row["id"])
        return store.snapshot(actor)
    with store.connection() as conn:
        store.authorize(conn, actor, lock=True)
        if scenario == "task_timeout_after_write":
            conn.execute(
                "UPDATE pa_workspaces SET scenario=scenario || '{\"task_timeout_after_write\":true}'::jsonb WHERE id=%s",
                (actor.workspace_id,),
            )
        elif scenario == "reset_failure":
            conn.execute(
                "UPDATE pa_workspaces SET scenario=scenario-'task_timeout_after_write' WHERE id=%s",
                (actor.workspace_id,),
            )
        elif scenario == "occupy_proposed_slot":
            row = conn.execute(
                "SELECT a.payload FROM pa_actions a JOIN pa_plans p ON p.id=a.plan_id WHERE p.workspace_id=%s AND p.user_id=%s AND p.role=%s AND p.status='pending' AND a.kind IN ('move_meeting','create_recording') ORDER BY p.created_at DESC,a.position LIMIT 1",
                (actor.workspace_id, actor.user_id, actor.role),
            ).fetchone()
            if not row:
                raise DomainError(
                    "Prepare a calendar proposal before occupying its proposed slot",
                    "no_pending_calendar_plan",
                    409,
                )
            payload = row["payload"]
            blocker_id = "scenario-slot-" + payload["start"]
            data = {
                "title": "New internal commitment · scenario",
                "start": payload["start"],
                "end": payload["end"],
                "event_type": "internal",
                "owner": "Dr. Avery Morgan",
                "source_system": "practice-demo",
            }
            conn.execute(
                "INSERT INTO pa_office_records(workspace_id,id,kind,data) VALUES (%s,%s,'event',%s) ON CONFLICT DO NOTHING",
                (actor.workspace_id, blocker_id, Jsonb(data)),
            )
        store.touch(conn, actor.workspace_id)
    return store.snapshot(actor)
