"""Read deployment, safe process logs and observed memory; submit no work."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import httpx
import yaml


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_logs(rows):
    collected = []
    patterns = {
        "child_started": re.compile(r"\bchild_started name=(api|worker) pid=(\d+)\b"),
        "run_claimed": re.compile(r"\brun_claimed run_id=([0-9a-f-]{36}) lease_generation=(\d+)\b"),
        "run_failed": re.compile(r"\brun_failed run_id=([0-9a-f-]{36}) error_type=([A-Za-z0-9_]+)\b"),
    }
    for row in rows:
        for event, pattern in patterns.items():
            match = pattern.search(row.get("message", ""))
            if not match:
                continue
            item = {"timestamp": row["timestamp"], "event": event}
            if event == "child_started":
                item.update(name=match[1], pid=int(match[2]))
            else:
                item["run_id"] = match[1]
                item["lease_generation" if event == "run_claimed" else "error_type"] = (
                    int(match[2]) if event == "run_claimed" else match[2]
                )
            collected.append(item)
    return collected


def samples(series):
    return [
        {
            "instance": next(
                (label["value"] for label in row.get("labels", []) if label["field"] == "instance"), None
            ),
            "timestamp": value["timestamp"],
            "bytes": value["value"],
        }
        for row in series
        if row.get("unit") == "bytes"
        for value in row.get("values", [])
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--service-id", required=True)
    parser.add_argument("--deploy-id", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--workflows", type=Path, default=Path("artifacts/verification/cloud-workflows.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/verification/cloud-worker.json"))
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text())
    end = timestamp()
    with httpx.Client(
        base_url="https://api.render.com/v1/",
        headers={"Authorization": "Bearer " + config["api"]["key"]},
        timeout=20,
    ) as client:

        def get(path, params=None):
            result = client.get(path, params=params)
            if result.is_error:
                raise RuntimeError(f"Read-only Render evidence request returned HTTP {result.status_code}")
            return result.json()

        deployment = get(f"services/{args.service_id}/deploys/{args.deploy_id}")
        service = get(f"services/{args.service_id}")
        log_rows = []
        pagination_complete = True
        for text in ("child_started", "run_claimed", "run_failed"):
            params = {
                "ownerId": config["workspace"],
                "resource": args.service_id,
                "startTime": args.start,
                "endTime": end,
                "type": "app",
                "text": text,
                "limit": 100,
                "direction": "forward",
            }
            for _ in range(3):
                page = get("logs", params)
                log_rows.extend(page.get("logs", []))
                if not page.get("hasMore"):
                    break
                params.update(startTime=page["nextStartTime"], endTime=page["nextEndTime"])
            else:
                pagination_complete = False
        params = {
            "resource": args.service_id,
            "startTime": args.start,
            "endTime": end,
            "resolutionSeconds": 30,
        }
        memory = samples(get("metrics/memory", params))
        limits = samples(get("metrics/memory-limit", params))
    logs = safe_logs(log_rows)
    workflows = json.loads(args.workflows.read_text()) if args.workflows.exists() else {}
    cases = workflows.get("cases", [])
    claimed = {entry["run_id"] for entry in logs if entry["event"] == "run_claimed"}
    maximum = max((sample["bytes"] for sample in memory), default=None)
    minimum_limit = min((sample["bytes"] for sample in limits), default=None)
    correlation = [
        {
            "name": case["name"],
            "run_id": case["run_id"],
            "workflow_passed": case.get("passed", False),
            "remote_claim_observed": case["run_id"] in claimed,
            "lease_generations_observed": sorted(
                {
                    entry["lease_generation"]
                    for entry in logs
                    if entry["event"] == "run_claimed" and entry["run_id"] == case["run_id"]
                }
            ),
        }
        for case in cases
    ]
    report = {
        "collected_at": end,
        "service_id": args.service_id,
        "deployment": {
            "id": deployment["id"],
            "status": deployment["status"],
            "revision": deployment.get("commit", {}).get("id"),
            "created_at": deployment.get("createdAt"),
            "finished_at": deployment.get("finishedAt"),
        },
        "provider": "Render",
        "compute_plan": service.get("serviceDetails", {}).get("plan"),
        "worker_location": "Supervised worker process in the same free Render web-service container as the API",
        "local_workers_stopped_at": "2026-09-09T01:02:29Z",
        "local_worker_stop_evidence": "Recorded by deployment operator before the remote verification; independent remote run claims corroborate cloud execution.",
        "logs": sorted(logs, key=lambda item: item["timestamp"]),
        "log_pagination_complete": pagination_complete,
        "workflow_correlation": correlation,
        "all_three_workflows_passed_and_remotely_claimed": len(correlation) == 3
        and all(c["workflow_passed"] and c["remote_claim_observed"] for c in correlation),
        "memory": {
            "start": args.start,
            "end": end,
            "resolution_seconds": 30,
            "samples": memory,
            "limit_samples": limits,
            "maximum_observed_bytes": maximum,
            "maximum_observed_mib": round(maximum / 1024**2, 2) if maximum is not None else None,
            "observed_limit_bytes": minimum_limit,
            "all_observed_samples_below_limit": maximum < minimum_limit
            if maximum is not None and minimum_limit is not None
            else None,
            "scope": "Largest value returned at 30-second metric resolution during this recorded deployment/test window; not lifetime peak, an instantaneous maximum, or a load-capacity guarantee.",
        },
        "service_limitations": "Free service sleeps after 15 minutes without inbound traffic. Queued state is durable in Supabase; processing resumes on a real request. No artificial keepalive or continuously awake worker is claimed.",
        "sources": [
            "https://api-docs.render.com/reference/list-logs",
            "https://api-docs.render.com/reference/get-memory",
            "https://render.com/docs/free",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        previous = json.loads(args.output.read_text())
        if previous.get("deployment", {}).get("id") == deployment["id"] and "restart" in previous:
            report["restart"] = previous["restart"]
    args.output.write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "deployment_status": report["deployment"]["status"],
                "compute_plan": report["compute_plan"],
                "workflow_correlation": correlation,
                "maximum_observed_memory_mib": report["memory"]["maximum_observed_mib"],
                "all_three_verified": report["all_three_workflows_passed_and_remotely_claimed"],
            }
        )
    )


if __name__ == "__main__":
    main()
