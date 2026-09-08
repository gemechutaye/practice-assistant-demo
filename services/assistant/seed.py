"""A coherent fictional office and short attributed public-source notes."""

from psycopg.types.json import Jsonb

DEMO_CLOCK = "2026-09-08T08:15:00-07:00"

RECORDS = [
    (
        "visit-maya",
        "event",
        {
            "title": "Maya Chen · procedure appointment",
            "start": "2026-09-09T09:00:00-07:00",
            "end": "2026-09-09T10:00:00-07:00",
            "event_type": "patient",
            "appointment_type": "procedure",
            "owner": "Dr. Avery Morgan",
        },
    ),
    (
        "visit-jordan",
        "event",
        {
            "title": "Jordan Rivera · consultation",
            "start": "2026-09-09T10:00:00-07:00",
            "end": "2026-09-09T11:00:00-07:00",
            "event_type": "patient",
            "appointment_type": "consultation",
            "owner": "Dr. Avery Morgan",
        },
    ),
    (
        "clinic-today",
        "event",
        {
            "title": "Clinic appointments",
            "start": "2026-09-08T09:00:00-07:00",
            "end": "2026-09-08T12:00:00-07:00",
            "event_type": "patient",
            "owner": "Dr. Avery Morgan",
        },
    ),
    (
        "engineering-sync",
        "event",
        {
            "title": "CRM engineering decisions",
            "start": "2026-09-09T09:30:00-07:00",
            "end": "2026-09-09T10:00:00-07:00",
            "event_type": "internal",
            "owner": "Dr. Avery Morgan",
            "attendees": ["Priya Shah", "Sam Ortiz"],
        },
    ),
    (
        "lunch-tomorrow",
        "event",
        {
            "title": "Lunch and catch-up",
            "start": "2026-09-09T12:00:00-07:00",
            "end": "2026-09-09T12:30:00-07:00",
            "event_type": "internal",
            "owner": "Dr. Avery Morgan",
        },
    ),
    (
        "admin-maya",
        "patient_admin",
        {
            "patient_name": "Maya Chen",
            "appointment_id": "visit-maya",
            "paperwork_status": "missing",
            "coordinator": "Alex Kim",
        },
    ),
    (
        "admin-jordan",
        "patient_admin",
        {
            "patient_name": "Jordan Rivera",
            "appointment_id": "visit-jordan",
            "paperwork_status": "complete",
            "coordinator": "Riley Brooks",
        },
    ),
    (
        "task-prep-maya",
        "task",
        {
            "title": "Confirm Maya's paperwork is received",
            "owner": "Alex Kim",
            "status": "open",
            "due_at": "2026-09-08T09:00:00-07:00",
            "related_record_id": "admin-maya",
            "workflow": "preparation",
            "auto_close_on_paperwork": True,
            "follow_up_permission": "Close only this linked preparation task when its paperwork record becomes complete.",
            "access_scope": "office",
        },
    ),
    (
        "task-engineering-update",
        "task",
        {
            "title": "Collect CRM import retry results from Priya",
            "owner": "Sam Ortiz",
            "status": "open",
            "due_at": "2026-09-08T16:00:00-07:00",
            "related_record_id": "engineering-import",
            "access_scope": "office",
        },
    ),
    (
        "task-unrelated",
        "task",
        {
            "title": "Confirm next week's supply order",
            "owner": "Alex Kim",
            "status": "open",
            "due_at": "2026-09-09T15:00:00-07:00",
            "related_record_id": None,
            "access_scope": "office",
        },
    ),
    (
        "message-paperwork",
        "message",
        {
            "subject": "Tomorrow's paperwork is still missing",
            "body": "Maya's portal paperwork has not arrived. I will check the administration record before following up. This is a fictional office message.",
            "sender": "Alex Kim",
            "recipient": "Dr. Avery Morgan",
            "status": "unread",
            "related_record_id": "admin-maya",
            "access_scope": "office",
        },
    ),
    (
        "message-team",
        "message",
        {
            "subject": "CRM decision and team availability",
            "body": "Priya and Sam are available tomorrow 11:00–12:00 or 14:00–15:00 Pacific. Priya needs your decision on which intake fields must be mandatory. Import retry results will be ready today at 16:00.",
            "sender": "Sam Ortiz",
            "recipient": "Dr. Avery Morgan",
            "status": "unread",
            "related_record_id": "engineering-import",
            "access_scope": "office",
        },
    ),
    (
        "message-skincare",
        "message",
        {
            "subject": "Where can I place an EMER Skin order?",
            "body": "The saved shipping-page note says to order through the practice, but shopping links also appear. Please prepare a response that clearly distinguishes the dated source from live availability.",
            "sender": "Demo support coordinator",
            "recipient": "Dr. Avery Morgan",
            "status": "unread",
            "access_scope": "office",
        },
    ),
    (
        "engineering-import",
        "engineering",
        {
            "title": "CRM import retry handling",
            "status": "in_progress",
            "owner": "Priya Shah",
            "summary": "Duplicate-event protection is implemented. The retry test report is due today at 16:00. Fictional integration work; no connection to the employer's CRM.",
            "decision_needed": "Decide whether phone number or email must be present before an intake record can be saved.",
        },
    ),
    (
        "engineering-forms",
        "engineering",
        {
            "title": "Administrative handoff form",
            "status": "ready_for_review",
            "owner": "Sam Ortiz",
            "summary": "The draft form separates administrative follow-up from clinical notes. Schema examples are ready for review.",
            "decision_needed": "Confirm Alex Kim as the initial owner for incomplete paperwork follow-up.",
        },
    ),
    (
        "content-consultation",
        "content",
        {
            "title": "Why pricing starts with a consultation",
            "script": "Every concern is different. A consultation is where the practice can discuss an individual plan and its pricing. This draft is general information and awaits review.",
            "caption": "Start with a consultation to discuss your individual questions. Source: the practice's public scar-revision information.",
            "status": "draft",
            "reviewer": "Jamie Park",
            "source_ids": ["source-scar-pricing"],
            "access_scope": "content",
        },
    ),
    (
        "report-preparation",
        "report",
        {
            "title": "Preparation tasks by coordinator",
            "report_type": "preparation_by_owner",
            "description": "Live counts of open preparation tasks grouped by their assigned coordinator.",
        },
    ),
]

SOURCES = [
    {
        "id": "source-paperwork-policy",
        "title": "Practice administrative timing policy",
        "url": "https://www.jasonemermd.com/financial-policy-payment-terms",
        "excerpt": "The public policy asks patients to complete paperwork and portal requirements 24 hours before the appointment, and arrive 30 minutes before a procedure. This source note supports administrative timing only; it does not establish clinical readiness.",
        "provenance": "public",
        "data": {
            "snapshot_date": "2026-09-08",
            "section": "Paperwork and arrival",
            "retrieval_method": "Research source snapshot",
            "rules": {"paperwork_hours_before": 24, "procedure_arrival_minutes_before": 30},
        },
    },
    {
        "id": "source-scar-pricing",
        "title": "Public scar-revision consultation information",
        "url": "https://www.jasonemermd.com/plastic-surgery-procedures/face/scar-revision",
        "excerpt": "The practice describes individualized scar-revision costs that depend on the characteristics of the concern and says pricing is discussed at consultation. This is a brief public-source note, not an individual quote or treatment recommendation.",
        "provenance": "public",
        "data": {
            "snapshot_date": "2026-09-08",
            "section": "Cost",
            "retrieval_method": "Research source snapshot",
        },
    },
    {
        "id": "source-skin-ordering",
        "title": "EMER Skin ordering notice",
        "url": "https://emerskin.com/pages/shipping-policy",
        "excerpt": "The observed shipping-page notice directed orders through the medical practice, while shopping navigation remained visible. This dated observation does not establish current stock or a working checkout; refer to the linked practice information for confirmation.",
        "provenance": "public",
        "data": {
            "snapshot_date": "2026-09-08",
            "retrieval_method": "Cached research snapshot; current checkout not verified",
        },
    },
    {
        "id": "source-practice-platform",
        "title": "Public account of practice software integrations",
        "url": "https://krazimo.com/jason-emer-md-how-our-ai-crm-got-people-their-botox/",
        "excerpt": "The vendor describes a practice platform and AI concierge covering communications, scheduling, reporting, and CRM/EMR integrations. This is the vendor's public account, not independent confirmation of the current installation.",
        "provenance": "public",
        "data": {"snapshot_date": "2026-09-08", "retrieval_method": "Research source snapshot"},
    },
    {
        "id": "source-emergpt",
        "title": "EmerGPT public announcement",
        "url": "https://www.einnews.com/pr_news/912584533/dr-jason-emer-launches-emergpt-ai-designed-to-think-like-a-specialist-not-just-transcribe-one",
        "excerpt": "The May 14, 2026 announcement describes specialized clinical AI agents and knowledge accumulation. It does not provide a verified public API for this demonstration. All office records and services in Practice Assistant are fictional and independent.",
        "provenance": "public",
        "data": {"published_at": "2026-05-14", "retrieval_method": "Research source snapshot"},
    },
    {
        "id": "source-demo-calendar",
        "title": "Demonstration scheduling and follow-up rules",
        "url": "",
        "excerpt": "Patient appointments are protected. Internal meetings and recording holds may be proposed for approval. Office hours are 08:00–18:00 Pacific. Follow-up may close only the linked preparation or review tasks carrying explicit follow-up permission. Fictional rules supplied for this independent demonstration.",
        "provenance": "demo",
        "data": {"access_scope": "office"},
    },
]


def seed_workspace(conn, workspace_id: str, user_id: str) -> None:
    for record_id, kind, data in RECORDS:
        enriched = {**data, "source_system": "practice-demo", "external_id": record_id, "source_version": "1"}
        conn.execute(
            "INSERT INTO pa_office_records(workspace_id,id,kind,data) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (workspace_id, record_id, kind, Jsonb(enriched)),
        )
    for source in SOURCES:
        conn.execute(
            "INSERT INTO pa_sources(workspace_id,id,title,url,excerpt,accessed_at,provenance,data) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (
                workspace_id,
                source["id"],
                source["title"],
                source["url"],
                source["excerpt"],
                DEMO_CLOCK,
                source["provenance"],
                Jsonb(source["data"]),
            ),
        )
    for pref_id, key, value, scope in [
        (
            "pref-protect-morning",
            "morning_preparation",
            "Keep the 30 minutes before the first patient appointment free of internal meetings and recording.",
            "doctor",
        ),
        (
            "pref-team-updates",
            "engineering_updates",
            "Use a concise asynchronous update unless a decision needs a meeting.",
            "doctor",
        ),
        (
            "pref-content-style",
            "content_style",
            "Use calm, clear language. Explain uncertainty. Do not promise outcomes or invent individual prices.",
            "content",
        ),
    ]:
        conn.execute(
            "INSERT INTO pa_preferences(workspace_id,id,key,value,user_id,scope) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (workspace_id, pref_id, key, Jsonb(value), user_id, scope),
        )
