"""Verify three public HTTP workflows using fresh fictional workspaces.

The queue may be processed by a temporary local worker; the report says so
explicitly. No token, secret, database URL or employer data is exported.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

from dotenv import dotenv_values
import httpx


class VerificationFailure(Exception):
    pass


class Verification:
    def __init__(self, env_file, origin, output, resume_completed_preparation=False, worker_location="temporary local process against hosted queue"):
        self.private = dotenv_values(env_file)
        self.auth_path = env_file.parent / "hosted-verification-auth.json"
        self.client = httpx.Client(timeout=65)
        self.base = origin.rstrip("/") + "/api/backend"
        self.output = output
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.report = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "origin": origin,
            "worker_location": worker_location,
            "scope": "Three functional examples through public Vercel proxy, Render API and Supabase; not a general accuracy benchmark. Worker placement is declared by the operator and checked separately in deployment evidence.",
            "maximum_workflows": 3,
            "known_cost_stop_usd": 0.75,
            "budget_target_usd": 0.5,
            "passed": False,
            "cases": [],
        }
        self.headers = {}
        self.current = None
        self.resume_completed_preparation = resume_completed_preparation
        if resume_completed_preparation:
            self.report = json.loads(self.output.read_text())
            if len(self.report["cases"]) != 1 or self.report["cases"][0].get("status") != "completed":
                raise VerificationFailure("Resume requires exactly one completed preparation case")
            self.report.pop("failure", None)
        aborted_probe = self.output.with_name(self.output.stem + "-harness-probe.json")
        if aborted_probe.exists():
            prior = json.loads(aborted_probe.read_text())
            self.report["excluded_harness_probe"] = {
                "reason": "Verifier originally compared plan status to run status; interrupted before any approval. Runtime was not the failure.",
                "known_cost_usd": prior.get("known_cost_usd", 0),
                "run_id": prior["cases"][0]["run_id"],
                "excluded_from_passing_case_count": True,
            }

    def save(self):
        self.output.write_text(json.dumps(self.report, indent=2))

    def request(self, method, path, **kwargs):
        response = self.client.request(method, self.base + path, headers=self.headers, **kwargs)
        if response.is_error:
            try:
                code = response.json().get("code", "http_error")
            except ValueError:
                code = "http_error"
            raise VerificationFailure(f"HTTP {response.status_code} at {path.split('/')[1]} ({code})")
        return response.json()

    def start(self, name, role, prompt):
        if name == "tomorrow_preparation" and self.resume_completed_preparation:
            state = json.loads(self.auth_path.read_text())[name]
            self.headers = state["headers"]
            self.current = self.report["cases"][0]
            return state["before"]
        auth = self.client.post(
            self.private["SUPABASE_URL"].rstrip("/") + "/auth/v1/signup",
            headers={"apikey": self.private["SUPABASE_ANON_KEY"]},
            json={},
        )
        if auth.status_code != 200 or not auth.json().get("access_token"):
            raise VerificationFailure("Anonymous verification identity was unavailable")
        self.headers = {"Authorization": "Bearer " + auth.json()["access_token"], "X-Demo-Role": role}
        session = self.request("POST", "/session", json={"role": role})
        self.headers["X-Workspace-Id"] = session["workspace_id"]
        run = self.request("POST", "/runs", json={"message": prompt})
        case = {
            "name": name,
            "role": role,
            "workspace_id": session["workspace_id"],
            "run_id": run["id"],
            "prompt": prompt,
            "passed": False,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "plans": [],
        }
        self.current = case
        self.report["cases"].append(case)
        private_state = json.loads(self.auth_path.read_text()) if self.auth_path.exists() else {}
        private_state[name] = {"headers": self.headers, "run_id": run["id"], "before": session["snapshot"]}
        self.auth_path.touch(mode=0o600, exist_ok=True)
        self.auth_path.chmod(0o600)
        self.auth_path.write_text(json.dumps(private_state))
        self.save()
        print(json.dumps({"case": name, "stage": "queued", "run_id": run["id"]}), flush=True)
        return session["snapshot"]

    def wait(self, desired, exclude_plan=None, timeout=240):
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            run = self.request("GET", "/runs/" + self.current["run_id"])
            self.current["usage"] = run["usage"]
            total = sum(float(c.get("usage", {}).get("cost") or 0) for c in self.report["cases"]) + float(
                self.report.get("excluded_harness_probe", {}).get("known_cost_usd", 0)
            )
            self.report["known_cost_usd"] = round(total, 6)
            self.current["status"] = run["status"]
            self.save()
            if total >= self.report["known_cost_stop_usd"]:
                self.request("POST", "/runs/" + run["id"] + "/cancel")
                raise VerificationFailure("Verification reached its known-cost stop")
            if run["status"] in {"failed", "cancelled"}:
                raise VerificationFailure("The workflow ended with status " + run["status"])
            if run["status"] == desired:
                if desired != "awaiting_approval" or (
                    run.get("plan")
                    and run["plan"]["id"] != exclude_plan
                    and run["plan"]["status"] == "pending"
                ):
                    return run
            if desired == "awaiting_approval" and run["status"] == "completed":
                if self.current["name"] == "tomorrow_preparation" and self.resume_completed_preparation:
                    return run
                raise VerificationFailure("The requested writable workflow finished without a proposal")
            time.sleep(2)
        self.request("POST", "/runs/" + self.current["run_id"] + "/cancel")
        raise VerificationFailure("The workflow exceeded the verification wait limit")

    def remember_plan(self, run):
        plan = run["plan"]
        self.current["plans"].append(
            {
                "id": plan["id"],
                "status_when_observed": plan["status"],
                "actions": [
                    {"id": a["id"], "kind": a["kind"], "payload": a["payload"]} for a in plan["actions"]
                ],
            }
        )
        self.save()
        return plan

    def approve(self, plan):
        self.request("POST", "/plans/" + plan["id"] + "/approve")
        print(
            json.dumps(
                {
                    "case": self.current["name"],
                    "stage": "approved",
                    "actions": [a["kind"] for a in plan["actions"]],
                }
            ),
            flush=True,
        )

    def complete(self, run):
        self.current.update(
            status=run["status"],
            answer=run["answer"],
            usage=run["usage"],
            model_calls=[
                {
                    "kind": s["kind"],
                    "model": s["model"],
                    "tokens": s["tokens"],
                    "cost": s["cost"],
                    "duration_ms": s["duration_ms"],
                }
                for s in run["steps"]
                if s.get("model")
            ],
            receipts=[
                {
                    "action_id": a["id"],
                    "kind": a["kind"],
                    "status": a.get("status"),
                    "result": a.get("result"),
                }
                for a in run["plan"]["actions"]
            ],
        )
        return self.request("GET", "/snapshot")

    def finish_case(self, checks):
        self.current["checks"] = checks
        self.current["passed"] = all(checks.values())
        self.save()
        if not self.current["passed"]:
            raise VerificationFailure(
                "A workflow invariant failed: " + ", ".join(k for k, v in checks.items() if not v)
            )
        print(json.dumps({"case": self.current["name"], "stage": "verified", "checks": checks}), flush=True)


def patient_times(snapshot):
    return {e["id"]: [e["start"], e["end"]] for e in snapshot["events"] if e["event_type"] == "patient"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--origin", default="https://practice-assistant-demo.vercel.app")
    parser.add_argument("--output", type=Path, default=Path("artifacts/verification/hosted-workflows.json"))
    parser.add_argument("--worker-location", default="temporary local process against hosted queue", help="Actual execution location; stop local workers before claiming cloud-only execution.")
    parser.add_argument(
        "--resume-completed-preparation",
        action="store_true",
        help="Recheck a completed first case from its private saved identity, then run the remaining two cases; makes no replacement preparation inference.",
    )
    args = parser.parse_args()
    verify = Verification(args.env_file, args.origin, args.output, args.resume_completed_preparation, args.worker_location)
    started = time.monotonic()
    try:
        verify.report["api_health"] = verify.request("GET", "/health")
        before = verify.start(
            "tomorrow_preparation",
            "doctor",
            "Prepare tomorrow: inspect the schedule, missing paperwork deadline and existing tasks. Move the conflicting internal engineering meeting to an available confirmed team window. Prepare a demo inbox message to Alex about the paperwork follow-up, reusing the existing task. Remember that I prefer a concise administrative summary.",
        )
        initial_patient_times = patient_times(before)
        run = verify.wait("awaiting_approval")
        plan = verify.remember_plan(run)
        verify.approve(plan)
        after = verify.complete(verify.wait("completed"))
        prep = next(p for p in after["preparation"] if p["id"] == "admin-maya")
        memory = verify.request("POST", "/tools/read", json={"name": "get_preferences", "arguments": {}})
        verify.current["memory_readback"] = memory
        handoff = verify.request(
            "POST",
            "/integrations/handoff",
            json={
                "event_id": "hosted-verification-" + uuid4().hex,
                "event_type": "paperwork_completed",
                "record_id": "admin-maya",
            },
        )
        verify.current["handoff_event_id"] = handoff["id"]
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            handoff_snapshot = verify.request("GET", "/snapshot")
            if (
                next(t for t in handoff_snapshot["tasks"] if t["id"] == "task-prep-maya")["status"]
                == "completed"
            ):
                break
            time.sleep(2)
        verify.finish_case(
            {
                "deadline_is_45_minutes": prep["minutes_remaining"] == 45,
                "patient_appointments_unchanged": patient_times(after) == initial_patient_times,
                "existing_preparation_task_reused": len(
                    [t for t in after["tasks"] if t.get("related_record_id") == "admin-maya"]
                )
                == 1,
                "approved_message_saved": any(a["kind"] == "deliver_demo_message" for a in plan["actions"])
                and len(after["messages"]) > len(before["messages"]),
                "preference_saved_and_retrieved": "concise" in json.dumps(memory).lower()
                and "administrative" in json.dumps(memory).lower(),
                "real_outbox_closed_linked_task": next(
                    t for t in handoff_snapshot["tasks"] if t["id"] == "task-prep-maya"
                )["status"]
                == "completed",
                "unrelated_task_still_open": next(
                    t for t in handoff_snapshot["tasks"] if t["id"] == "task-unrelated"
                )["status"]
                == "open",
            }
        )

        before = verify.start(
            "public_content_review",
            "editor",
            "Create a new short public video script and caption explaining why scar-revision pricing starts with an individual consultation. Retrieve the public source, cite it, and save the new draft in review assigned to Jamie Park. Keep individual prices and treatment recommendations out.",
        )
        run = verify.wait("awaiting_approval")
        plan = verify.remember_plan(run)
        verify.approve(plan)
        after = verify.complete(verify.wait("completed"))
        old_ids = {c["id"] for c in before["content"]}
        new_content = [c for c in after["content"] if c["id"] not in old_ids]
        verify.finish_case(
            {
                "new_draft_saved": len(new_content) == 1,
                "cites_public_pricing_source": bool(new_content)
                and "source-scar-pricing" in new_content[0]["source_ids"],
                "draft_in_review": bool(new_content) and new_content[0]["status"] == "in_review",
                "review_task_assigned": bool(new_content)
                and any(
                    t.get("related_record_id") == new_content[0]["id"]
                    and t["owner"] == "Jamie Park"
                    and t["status"] == "open"
                    for t in after["tasks"]
                ),
                "actual_claude_route_observed": any(
                    "claude" in c["model"] for c in verify.current["model_calls"]
                ),
                "editor_has_no_patient_data": after["patient_admin"] == [] and after["engineering"] == [],
            }
        )

        before = verify.start(
            "engineering_stale_approval",
            "doctor",
            "Read the current engineering updates, messages and schedule. Move the CRM engineering decisions meeting out of clinic to a confirmed available team window tomorrow, and prepare a concise demo message to Sam about the decisions that need the doctor. Preserve patient appointments.",
        )
        initial_patient_times = patient_times(before)
        first = verify.remember_plan(verify.wait("awaiting_approval"))
        first_move = next(a for a in first["actions"] if a["kind"] == "move_meeting")
        verify.request("POST", "/scenarios", json={"scenario": "occupy_proposed_slot"})
        verify.approve(first)
        replacement = verify.remember_plan(verify.wait("awaiting_approval", exclude_plan=first["id"]))
        replacement_move = next(a for a in replacement["actions"] if a["kind"] == "move_meeting")
        changed = verify.request("GET", "/snapshot")
        old_slot_preserved = (
            next(e for e in changed["events"] if e["id"] == "engineering-sync")["start"]
            == "2026-09-09T09:30:00-07:00"
        )
        verify.approve(replacement)
        after = verify.complete(verify.wait("completed"))
        meeting = next(e for e in after["events"] if e["id"] == "engineering-sync")
        verify.finish_case(
            {
                "fresh_plan_required": first["id"] != replacement["id"],
                "stale_approval_did_not_move_meeting": old_slot_preserved,
                "replacement_uses_different_slot": first_move["payload"]["start"]
                != replacement_move["payload"]["start"],
                "within_confirmed_attendee_window": any(
                    meeting["start"] >= w["start"] and meeting["end"] <= w["end"]
                    for w in meeting["attendee_availability"]
                ),
                "approved_move_read_back": meeting["start"] == replacement_move["payload"]["start"],
                "patient_appointments_unchanged": patient_times(after) == initial_patient_times,
            }
        )
        verify.report["passed"] = all(c["passed"] for c in verify.report["cases"])
    except Exception as error:
        verify.report["failure"] = {
            "type": type(error).__name__,
            "note": str(error)
            if isinstance(error, VerificationFailure)
            else "An invariant or transport check did not complete; raw payloads and credentials omitted.",
        }
    finally:
        verify.report["last_invocation_elapsed_seconds"] = round(time.monotonic() - started, 3)
        verify.report["completed_at"] = datetime.now(timezone.utc).isoformat()
        verify.report["elapsed_seconds"] = round(
            (
                datetime.now(timezone.utc) - datetime.fromisoformat(verify.report["started_at"])
            ).total_seconds(),
            3,
        )
        verify.report["workspaces_preserved_for_evidence"] = True
        verify.save()
        verify.client.close()
    print(
        json.dumps(
            {
                "passed": verify.report["passed"],
                "cases": len(verify.report["cases"]),
                "known_cost_usd": verify.report.get("known_cost_usd"),
                "failure": verify.report.get("failure"),
            }
        ),
        flush=True,
    )
    if not verify.report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
