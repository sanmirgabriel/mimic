"""Gaps identified during Gate 6; browser review stays outside CI tooling."""
from __future__ import annotations

import asyncio
import html
import io
import os
import re
import time
from dataclasses import asdict
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from mimic.api import create_app
from mimic.application import GenerationRequest
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.web.uploads import UploadStore, MAX_UPLOAD_BYTES, CONTEXT_MAX_BYTES, DRAFT_TTL_SECONDS
from tests.test_web_ui import web, token, submit, quick


def test_web_calls_shared_operations_without_http(web, monkeypatch):
    client, app = web
    assert 'id="main" tabindex="-1"' in client.get("/").text
    import httpx

    def forbidden(*args, **kwargs):
        raise AssertionError("HTML routes must not call the API via HTTP")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    for path in ("/", "/targets", "/generate", "/jobs"):
        assert client.get(path).status_code == 200
    target = submit(client, "/targets/new", {"name": "Direct", "nome": "Pedro"}, follow_redirects=False)
    assert target.status_code == 303
    tid = target.headers["location"].split("/")[-1]
    response = submit(client, "/generate", quick(mode="saved", target_id=tid), follow_redirects=False)
    path = response.headers["location"]
    assert app.state.job_manager.wait(path.split("/")[-1], 5)["status"] == "completed"
    assert client.get(path).status_code == 200 and client.get(path + "/status").status_code == 200


def test_partial_form_edits_preserve_omitted_fields_and_explicit_empty_clears(web):
    client, _ = web
    e = client.post("/api/engagements", json={"name": "E", "description": "Keep"}).json()
    o = client.post("/api/organizations", json={"name": "O", "engagement_id": e["id"],
                    "aliases": ["São Paulo"], "locations": ["Centro"], "keywords": ["Old"],
                    "domains": ["example.test"], "relevant_dates": ["29/02"]}).json()
    t = client.post("/api/targets", json={"name": "Display", "organization_id": o["id"],
                    "profile": {"nome": "João", "pet": "Luna", "apelidos": ["J"]}}).json()
    assert submit(client, f"/engagements/{e['id']}", {"name": "New"}).status_code == 200
    assert client.get(f"/api/engagements/{e['id']}").json()["description"] == "Keep"
    response = submit(client, f"/organizations/{o['id']}", {"keywords": " Ω \n\n  \nSão Paulo\nCentro"})
    assert response.status_code == 200
    stored = client.get(f"/api/organizations/{o['id']}").json()
    assert stored["keywords"] == [" Ω ", "São Paulo", "Centro"]
    for field in ("aliases", "locations", "domains", "relevant_dates", "name", "engagement_id"):
        assert stored[field] == o[field]
    assert submit(client, f"/targets/{t['id']}", {"pet": "Sol"}).status_code == 200
    stored = client.get(f"/api/targets/{t['id']}").json()
    assert stored["name"] == "Display" and stored["profile"]["nome"] == "João"
    assert stored["organization_id"] == o["id"] and stored["profile"]["apelidos"] == ["J"]
    assert stored["profile"]["pet"] == "Sol"
    assert submit(client, f"/organizations/{o['id']}", {"aliases": "", "engagement_id": ""}).status_code == 200
    stored = client.get(f"/api/organizations/{o['id']}").json()
    assert stored["aliases"] == [] and stored["engagement_id"] is None


def test_user_record_names_keywords_and_source_labels_are_escaped(web):
    client, _ = web
    payload = "<script>alert(1)</script>"
    org = client.post("/api/organizations", json={"name": payload, "keywords": [payload]}).json()
    target = client.post("/api/targets", json={"name": payload, "organization_id": org["id"]}).json()
    for path in ("/organizations", f"/organizations/{org['id']}", "/targets", f"/targets/{target['id']}"):
        response = client.get(path)
        assert response.status_code == 200
        assert payload not in response.text
        assert payload in html.unescape(response.text)
    response = submit(client, "/generate", quick(intent="preview"),
                      files={"dataset_file": (payload + ".txt", b"word")})
    assert response.status_code == 200
    assert payload not in response.text
    assert payload in html.unescape(response.text)


@pytest.mark.parametrize("bad", [None, "wrong", "á☃"])
def test_all_html_mutations_require_csrf(web, bad):
    client, app = web
    records = app.state.records
    ids = {collection: records.create(collection, {"name": "Keep"})["id"]
           for collection in ("engagements", "organizations", "targets")}
    job = app.state.repository.create_job(GenerationRequest().to_dict(), None, None)
    data = {"name": "Changed"} if bad is None else {"name": "Changed", "csrf_token": bad}
    for collection, item_id in ids.items():
        for path in (f"/{collection}/new", f"/{collection}/{item_id}", f"/{collection}/{item_id}/delete"):
            assert client.post(path, data=data).status_code == 403
        assert records.get(collection, item_id)["name"] == "Keep"
        assert len(records.list(collection)) == 1
    assert client.post(f"/jobs/{job['id']}/cancel", data=data).status_code == 403
    assert client.post("/generate", data=data, files={"dataset_file": ("a.txt", b"word")}).status_code == 403
    assert not app.state.web_uploads.root.exists()
    assert app.state.repository.get_job(job["id"])["status"] == "pending"


def test_json_api_form_content_types_and_cross_origin_cancel(web):
    client, app = web
    for mime, body in (("application/x-www-form-urlencoded", "name=Attack"),
                       ("text/plain", '{"name":"Attack"}')):
        assert client.post("/api/targets", content=body, headers={"content-type": mime}).status_code == 422
    assert client.post("/api/targets", files={"name": (None, "Attack")}).status_code == 422
    assert client.get("/api/targets").json() == []
    job = app.state.repository.create_job(GenerationRequest().to_dict(), None, None)
    path = f"/api/jobs/{job['id']}/cancel"
    for headers in ({"origin": "https://attacker.test"}, {"origin": "null"}, {"sec-fetch-site": "cross-site"}):
        assert client.post(path, headers=headers).status_code == 403
        assert app.state.repository.get_job(job["id"])["status"] == "pending"
    assert client.post(path, headers={"origin": "http://testserver"}).status_code == 200
    assert client.post(path).status_code == 200  # terminal cancel is a no-op
    assert client.post("/api/targets", json={"name": "Programmatic"}).status_code == 201


def test_security_headers_static_types_traversal_and_sanitized_500(web, monkeypatch):
    client, app = web
    for path in ("/", "/generate", "/api/health", "/static/app.css", "/static/app.js", "/docs"):
        response = client.get(path)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        csp = response.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in csp
        if path != "/docs":
            assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert client.get("/static/app.css").headers["content-type"].startswith("text/css")
    for name in ("app.js", "htmx.min.js"):
        assert "javascript" in client.get("/static/" + name).headers["content-type"]
    for path in ("/static/%2e%2e/routes.py", "/jobs/not-a-uuid", "/jobs/%2e%2e/%2e%2e/etc/passwd"):
        assert client.get(path).status_code in (404, 422)
    def fail():
        raise RuntimeError("/home/user/private SQLite statement traceback")
    monkeypatch.setattr(app.state.repository, "list_jobs", fail)
    error_client = TestClient(app, raise_server_exceptions=False, cookies={"mimic_locale": "en"})
    try:
        response = error_client.get("/")
        assert response.status_code == 500 and "unexpected error" in response.text
        assert "text/html" in response.headers["content-type"]
        assert "SQLite" not in response.text and "/home/user" not in response.text
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    finally:
        error_client.close()


@pytest.mark.parametrize("role,limit", [("dataset", MAX_UPLOAD_BYTES), ("ready", MAX_UPLOAD_BYTES), ("context", CONTEXT_MAX_BYTES)])
def test_upload_exact_byte_boundaries(tmp_path, role, limit):
    store = UploadStore(tmp_path)
    for size in (limit, limit + 1):
        upload = UploadFile(file=io.BytesIO(b"x" * size), filename="a.txt")
        if size == limit:
            upload_id = asyncio.run(store.save(upload, role))
            assert store.path(upload_id, role).stat().st_size == limit
        else:
            with pytest.raises(ValueError, match="upload limit"):
                asyncio.run(store.save(upload, role))
        asyncio.run(upload.close())
    assert len(list(store.root.iterdir())) == 1


def test_pasted_context_exact_utf8_boundaries(web):
    client, _ = web
    # Multibyte content verifies bytes rather than codepoint count.
    prefix = "pet: "
    valid = prefix + "á" * ((64 * 1024 - len(prefix) - 1) // 2) + "x"
    assert len(valid.encode("utf-8")) == 64 * 1024
    response = submit(client, "/generate", quick(intent="preview", context_text=valid))
    assert response.status_code == 200
    response = submit(client, "/generate", quick(intent="preview", context_text=valid + "x"))
    assert response.status_code == 422 and "64 KiB" in response.text


@pytest.mark.parametrize("filename", ["../../evil.txt", "/absolute.txt", "ação-☃.txt", "x" * 4000 + ".txt", "same.txt"])
def test_filename_never_selects_upload_path(web, filename):
    client, app = web
    paths = []
    for _ in range(2):
        response = submit(client, "/generate", quick(intent="preview"), files={"dataset_file": (filename, b"word\n")})
        assert response.status_code == 200
        upload_id = re.search(r'name="dataset_upload_id" value="([^"]+)"', response.text)[1]
        path = app.state.web_uploads.path(upload_id, "dataset")
        assert path.name == "dataset.txt" and path.read_bytes() == b"word\n"
        assert path.resolve().is_relative_to(app.state.job_manager.paths.root)
        paths.append(path)
    assert paths[0] != paths[1]


def test_partial_upload_read_error_removes_draft(tmp_path):
    class BrokenUpload:
        filename = "valid.txt"
        reads = 0
        async def read(self, size):
            self.reads += 1
            if self.reads == 1:
                return b"partial"
            raise OSError("write/read interrupted")
    store = UploadStore(tmp_path)
    with pytest.raises(OSError):
        asyncio.run(store.save(BrokenUpload(), "dataset"))
    assert not list(store.root.iterdir())


@pytest.mark.parametrize("status", ["pending", "running", "completed", "failed", "cancelled"])
@pytest.mark.parametrize("role", ["dataset", "ready", "context"])
def test_cleanup_preserves_all_job_states_and_source_roles(tmp_path, status, role):
    store = UploadStore(tmp_path)
    path = store.path(str(uuid4()), role)
    path.parent.mkdir(parents=True)
    path.write_text("source", encoding="utf-8")
    past = time.time() - DRAFT_TTL_SECONDS - 1
    os.utime(path.parent, (past, past))
    request = ({"context_path": str(path)} if role == "context" else
               {"sources": {"dataset_paths" if role == "dataset" else "ready_candidate_paths": [str(path)]}})
    store.cleanup([{"status": status, "request": request}])
    assert path.read_text() == "source"


def test_two_hundred_candidates_unknown_provenance_and_long_values(web):
    client, app = web
    repo = app.state.repository
    job = repo.create_job(GenerationRequest().to_dict(), None, None)
    repo.start_job(job["id"])
    origins = [Origin("profile", field, "<script>alert(1)</script>") for field in ("nome", "pet", "time_futebol")]
    origins += [Origin("organization", field, "Value") for field in ("keyword", "location")]
    origins += [Origin("custom source", "unfamiliar_field", "Custom")]
    steps = [Transformation("unknown_step", (("param", "<script>alert(1)</script>"),))]
    value = "João ☃ 😀 com espaços " + "x" * 2000
    repo.add_preview(job["id"], [{"sequence": i, "value": value + str(i),
                     "origins": [asdict(o) for o in origins], "transformations": [asdict(t) for t in steps]}
                     for i in range(1, 202)])
    repo.finish_job(job["id"], "failed", 201, "Generation failed.")
    response = client.get(f"/jobs/{job['id']}")
    assert response.text.count('class="candidate-detail"') == 200
    for label in ("Name", "Pet", "Football team", "Organization keyword", "Location", "Unfamiliar field", "unknown_step"):
        assert label in response.text
    assert "<script>alert(1)</script>" not in response.text
    assert "<script>alert(1)</script>" in html.unescape(response.text)
    assert repo.list_preview(job["id"], 1)[0]["origins"] == [asdict(o) for o in origins]
    assert "No candidate preview" not in response.text


def test_destructive_gets_do_not_mutate_and_dashboard_avoids_n_plus_one(web, monkeypatch):
    client, app = web
    t = app.state.records.create("targets", {"name": "T"})
    job = app.state.repository.create_job(GenerationRequest().to_dict(), None, None)
    assert client.get(f"/targets/{t['id']}/delete").status_code == 405
    assert client.get(f"/jobs/{job['id']}/cancel").status_code == 405
    assert app.state.records.get("targets", t["id"])
    assert app.state.repository.get_job(job["id"])["status"] == "pending"
    for i in range(100):
        app.state.records.create("targets", {"name": f"T{i}"})
    calls = []
    original = app.state.repository.database.connection
    def connection():
        calls.append(1)
        return original()
    monkeypatch.setattr(app.state.repository.database, "connection", connection)
    assert client.get("/").status_code == 200
    assert len(calls) == 4


@pytest.mark.parametrize("role", ["dataset", "ready", "context"])
def test_invalid_utf8_and_extensions_are_human(web, role):
    client, app = web
    bad_extension = submit(client, "/generate", quick(intent="preview"), files={role + "_file": ("bad.png", b"data")})
    assert bad_extension.status_code == 422 and "files must use" in bad_extension.text
    # MIME is a browser hint; fixed extension and the UTF-8 reader own semantics.
    response = submit(client, "/generate", quick(), files={role + "_file": ("invalid.txt", b"\xff", "image/png")}, follow_redirects=False)
    if role == "context":
        assert response.status_code == 422 and "valid UTF-8 text" in response.text
    else:
        assert response.status_code == 303
        path = response.headers["location"]
        assert app.state.job_manager.wait(path.rsplit("/", 1)[-1], 5)["status"] == "failed"
        assert "source file is not valid UTF-8" in client.get(path).text


def test_large_multipart_source_is_spooled_before_managed_copy(web, monkeypatch):
    client, _ = web
    original = UploadStore.save
    observed = []
    async def inspect(self, upload, role):
        observed.append(upload.file._rolled)
        return await original(self, upload, role)
    monkeypatch.setattr(UploadStore, "save", inspect)
    response = submit(client, "/generate", quick(intent="preview"), files={"dataset_file": ("big.txt", b"x" * (2 * 1024 * 1024))})
    assert response.status_code == 200 and observed == [True]
