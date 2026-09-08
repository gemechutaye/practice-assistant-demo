from contextlib import contextmanager
import json
from types import SimpleNamespace

import httpx
import pytest

from services.assistant import evidence
from services.assistant.domain import Actor, DomainError
from services.assistant.jobs import Jobs


def export_fixture(store, actor):
    jobs = Jobs(store)
    run = jobs.create(actor, "Inspect the preparation status")
    worker = jobs.claim()
    jobs.step(worker, "tool", "Private preparation", {"patient_name": "Maya Chen"})
    return jobs, run


def mock_storage(monkeypatch, signed_value=None, fail_status=None):
    requests = []
    client_class = httpx.Client

    def respond(request):
        requests.append(request)
        if fail_status:
            return httpx.Response(fail_status, json={"error": "test failure"})
        if "/object/sign/" in request.url.path:
            signed = (
                signed_value
                if signed_value is not None
                else request.url.path.removeprefix("/storage/v1") + "?token=unit-signature"
            )
            return httpx.Response(200, json={"signedURL": signed})
        return httpx.Response(200, json={"Key": "saved-private-object"})

    monkeypatch.setattr(
        evidence.httpx,
        "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs),
    )
    return requests


def test_export_is_scoped_and_uses_the_exact_uploaded_private_path(demo_office, monkeypatch):
    store, actor = demo_office
    jobs, run = export_fixture(store, actor)
    requests = mock_storage(monkeypatch)
    config = SimpleNamespace(
        supabase_url="https://storage.example.test", supabase_service_role_key="test-service-key"
    )
    result = evidence.export_run(config, store, jobs, actor, run["id"])
    assert len(requests) == 2
    assert f"/{actor.workspace_id}/doctor/{run['id']}/" in requests[0].url.path
    body = json.loads(requests[0].content)
    assert body["role"] == "doctor" and body["run"]["id"] == run["id"]
    assert "Maya Chen" in str(body)
    assert "test-service-key" not in str(body)
    assert json.loads(requests[1].content) == {"expiresIn": 600}
    assert result["expires_in"] == 600 and result["bytes"] == len(requests[0].content)
    assert result["url"].startswith("https://storage.example.test/storage/v1/object/sign/practice-evidence/")
    assert "test-service-key" not in str(result)


def test_export_denies_other_roles_or_workspaces_before_storage_request(demo_office, monkeypatch):
    store, doctor = demo_office
    jobs, run = export_fixture(store, doctor)
    requests = mock_storage(monkeypatch)
    config = SimpleNamespace(
        supabase_url="https://storage.example.test", supabase_service_role_key="test-key"
    )
    editor = store.get_actor(doctor.workspace_id, doctor.user_id, "editor")
    other_workspace = store.create_workspace("another-owner")
    other = store.get_actor(other_workspace, "another-owner", "doctor")
    for actor in (editor, other, Actor(doctor.workspace_id, "wrong-user", "doctor")):
        with pytest.raises(DomainError):
            evidence.export_run(config, store, jobs, actor, run["id"])
    assert requests == []


@pytest.mark.parametrize(
    "signed_value",
    [
        "https://attacker.example/file.json?token=x",
        "//attacker.example/file.json?token=x",
        "/object/sign/practice-evidence/another-workspace/doctor/file.json?token=x",
        "/object/sign/../../private/file.json?token=x",
        "/object/sign/file.json#fragment",
        None,
        42,
    ],
)
def test_export_rejects_unexpected_signed_download_locations(demo_office, monkeypatch, signed_value):
    store, actor = demo_office
    jobs, run = export_fixture(store, actor)
    # None normally requests the valid default from the helper, so test a missing URL explicitly.
    malformed = "" if signed_value is None else signed_value
    mock_storage(monkeypatch, malformed)
    config = SimpleNamespace(
        supabase_url="https://storage.example.test", supabase_service_role_key="test-key"
    )
    with pytest.raises(DomainError) as rejected:
        evidence.export_run(config, store, jobs, actor, run["id"])
    assert rejected.value.code == "storage_unavailable"


def test_export_storage_failure_does_not_expose_service_credentials(demo_office, monkeypatch):
    store, actor = demo_office
    jobs, run = export_fixture(store, actor)
    mock_storage(monkeypatch, fail_status=403)
    config = SimpleNamespace(
        supabase_url="https://storage.example.test", supabase_service_role_key="never-return-this-secret"
    )
    with pytest.raises(DomainError) as rejected:
        evidence.export_run(config, store, jobs, actor, run["id"])
    assert rejected.value.status_code == 503
    assert "never-return" not in str(rejected.value)


def test_source_check_uses_fixed_url_no_redirects_and_preserves_research_note(demo_office, monkeypatch):
    store, actor = demo_office
    source = next(s for s in store.get_sources(actor) if s["id"] == "source-scar-pricing")
    called = []

    @contextmanager
    def stream(method, url, **kwargs):
        called.append((method, url, kwargs))
        yield httpx.Response(
            200, content=b"A public page availability response", request=httpx.Request(method, url)
        )

    monkeypatch.setattr(evidence.httpx, "stream", stream)
    result = evidence.check_source(store, actor, source["id"])
    assert result["status"] == "reachable" and result["changed"] is None
    assert called[0][1] == source["url"] and called[0][2]["follow_redirects"] is False
    refreshed = next(s for s in store.get_sources(actor) if s["id"] == source["id"])
    assert refreshed["excerpt"] == source["excerpt"] and refreshed["version"] == source["version"]
    assert "Availability alone does not verify" in result["note"]
    assert evidence.check_source(store, actor, source["id"]) == result
    assert len(called) == 1


def test_source_url_override_or_private_source_is_rejected_before_fetch(demo_office, monkeypatch):
    store, doctor = demo_office
    monkeypatch.setattr(
        evidence.httpx,
        "stream",
        lambda *_args, **_kwargs: pytest.fail("An unapproved URL must not be requested"),
    )
    with store.connection() as conn:
        conn.execute(
            "UPDATE pa_sources SET url='http://127.0.0.1/private' WHERE workspace_id=%s AND id='source-scar-pricing'",
            (doctor.workspace_id,),
        )
    for source_id in ("source-scar-pricing", "source-demo-calendar", "https://example.test/override"):
        with pytest.raises(DomainError):
            evidence.check_source(store, doctor, source_id)


def test_source_redirect_is_not_followed_or_reported_as_verified(demo_office, monkeypatch):
    store, actor = demo_office

    @contextmanager
    def stream(method, url, **kwargs):
        assert kwargs["follow_redirects"] is False
        yield httpx.Response(
            302, headers={"Location": "http://127.0.0.1/internal"}, request=httpx.Request(method, url)
        )

    monkeypatch.setattr(evidence.httpx, "stream", stream)
    result = evidence.check_source(store, actor, "source-scar-pricing")
    assert result["status"] == "unavailable" and result["http_status"] == 302
    assert "content_sha256" not in result
