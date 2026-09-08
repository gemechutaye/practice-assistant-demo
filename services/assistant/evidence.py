"""Private, role-scoped evidence exports and bounded public-source availability checks."""

from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
from psycopg.types.json import Jsonb

from .domain import DomainError
from .jobs import serial
from .seed import SOURCES


def export_run(config, store, jobs, actor, run_id):
    run = jobs.get(actor, run_id)
    if not config.supabase_url or not config.supabase_service_role_key:
        raise DomainError(
            "Evidence storage is not configured for this environment.", "storage_unavailable", 503
        )
    document = {
        "format_version": 1,
        "description": "Independent demonstration; fictional office records. No employer system connection.",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "role": actor.role,
        "run": run,
        "sources": store.get_sources(actor),
    }
    body = json.dumps(serial(document), indent=2).encode()
    if len(body) > 4 * 1024 * 1024:
        raise DomainError("This evidence bundle exceeds the export size limit.", "export_size", 413)
    # Determined by the authenticated workspace and run, never a client-supplied path.
    path = f"practice-evidence/{actor.workspace_id}/{actor.role}/{run_id}/{uuid4().hex}.json"
    headers = {
        "Authorization": "Bearer " + config.supabase_service_role_key,
        "apikey": config.supabase_service_role_key,
    }
    try:
        with httpx.Client(
            base_url=config.supabase_url + "/storage/v1", headers=headers, timeout=30
        ) as client:
            response = client.post(
                "/object/" + path, content=body, headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            signed = client.post("/object/sign/" + path, json={"expiresIn": 600})
            signed.raise_for_status()
            url = signed.json()["signedURL"]
    except (httpx.HTTPError, KeyError, ValueError):
        raise DomainError(
            "The private evidence export could not finish. Please retry.", "storage_unavailable", 503
        ) from None
    parsed = urlsplit(url) if isinstance(url, str) else None
    if (
        not parsed
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or parsed.path != "/object/sign/" + path
        or not parsed.query
    ):
        raise DomainError("Storage returned an invalid download location.", "storage_unavailable", 503)
    return {
        "url": config.supabase_url + "/storage/v1" + url,
        "expires_in": 600,
        "storage": "Supabase private storage",
        "bytes": len(body),
    }


def check_source(store, actor, source_id):
    source = next((s for s in store.get_sources(actor) if s["id"] == source_id), None)
    allowed = {s["id"]: s["url"] for s in SOURCES if s["provenance"] == "public"}
    if not source or source_id not in allowed or source["url"] != allowed[source_id]:
        raise DomainError("This source has no approved public URL to check.", "source_unavailable", 404)
    previous = source.get("live_check") or {}
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "unavailable",
        "http_status": None,
        "changed": None,
        "note": "The dated research note remains unchanged. Availability alone does not verify its current claims.",
    }
    last_time = previous.get("checked_at")
    if last_time and (datetime.now(timezone.utc) - datetime.fromisoformat(last_time)).total_seconds() < 60:
        return previous
    try:
        # No redirects or user-supplied targets: a page cannot redirect this fetch to a private host.
        with httpx.stream(
            "GET",
            source["url"],
            timeout=20,
            follow_redirects=False,
            headers={"User-Agent": "PracticeAssistantDemo/1.0 public-source-check"},
        ) as response:
            result["http_status"] = response.status_code
            if response.status_code == 200:
                hasher = hashlib.sha256()
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 1024 * 1024:
                        result["note"] = (
                            "The page exceeds the check size limit; the dated note remains unchanged."
                        )
                        break
                    hasher.update(chunk)
                else:
                    fingerprint = hasher.hexdigest()
                    result.update(
                        status="reachable",
                        content_sha256=fingerprint,
                        changed=(fingerprint != previous["content_sha256"])
                        if previous.get("content_sha256")
                        else None,
                    )
    except httpx.HTTPError:
        pass
    with store.connection() as conn:
        store.authorize(conn, actor, lock=True)
        conn.execute(
            "UPDATE pa_sources SET data=jsonb_set(data,'{live_check}',%s) WHERE workspace_id=%s AND id=%s",
            (Jsonb(result), actor.workspace_id, source_id),
        )
        store.touch(conn, actor.workspace_id)
    return result
