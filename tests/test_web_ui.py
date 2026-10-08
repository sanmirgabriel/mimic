"""SSR contract tests, using the same API/service and persisted job preview."""
from __future__ import annotations

import html
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from importlib.resources import files
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from mimic.api import create_app
from mimic.application import GenerationRequest, GenerationResult
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.jobs import JobManager
from mimic.persistence import DataPaths, Database, Repository
from mimic.web.uploads import DRAFT_TTL_SECONDS, UploadStore


@pytest.fixture
def web(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app, cookies={"mimic_locale": "en"}) as client:
        yield client, app


def token(client, path="/generate"):
    response = client.get(path)
    assert response.status_code == 200
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]


def submit(client, path, values, **kwargs):
    return client.post(path, data={"csrf_token": token(client), **values}, **kwargs)


def quick(**values):
    return {"mode": "quick", "nome": "Pedro", "leet_mode": "none", "separators": "",
            "max_candidates_per_word": "20", "max_dataset_lines": "100", **values}


@pytest.mark.parametrize("path,title", [
    ("/", "Your local workspace"), ("/engagements", "Engagements"),
    ("/organizations", "Organizations"), ("/targets", "Targets"),
    ("/generate", "From context to candidates"), ("/jobs", "Jobs"),
    ("/engagements/new", "Create engagement"),
])
def test_pages_and_local_assets(web, path, title):
    client, _ = web
    response = client.get(path)
    assert response.status_code == 200 and title in response.text
    assert "text/html" in response.headers["content-type"]
    assert 'aria-label="Workspace navigation"' in response.text
    assert "/static/htmx.min.js" in response.text
    assert "/static/app.css" in response.text


def test_assets_docs_and_api_remain_available(web):
    client, _ = web
    for name in ("app.css", "app.js", "htmx.min.js"):
        response = client.get("/static/" + name)
        assert response.status_code == 200 and len(response.content) > 500
    assert client.get("/docs").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/targets/not-a-uuid").headers["content-type"] == "application/json"
    assert "/generate" not in client.get("/openapi.json").json()["paths"]


def test_crud_forms_all_fields_conflicts_and_generation_link(web):
    client, _ = web
    e = submit(client, "/engagements/new", {"name": "Audit", "description": "Local scope"}, follow_redirects=False)
    assert e.status_code == 303
    eid = e.headers["location"].split("/")[-1]
    org_values = {"name": "São Paulo Lab", "engagement_id": eid, "aliases": "Lab\nSP",
                  "locations": "São Paulo\nCampinas", "keywords": "Research\nLab",
                  "relevant_dates": "29/02\n17/08/2002", "domains": "example.test\nlab.test"}
    o = submit(client, "/organizations/new", org_values, follow_redirects=False)
    assert o.status_code == 303
    oid = o.headers["location"].split("/")[-1]
    profile = {"name": "Display João", "nome": "João", "apelidos": "Joca\nJ",
               "organization_id": oid, "engagement_id": eid, "pet": "Luna", "empresa": "Lab",
               "data_nascimento": "29/02/2024", "time_futebol": "Flamengo"}
    t = submit(client, "/targets/new", profile, follow_redirects=False)
    assert t.status_code == 303
    tid = t.headers["location"].split("/")[-1]
    stored = client.get(f"/api/targets/{tid}").json()
    assert stored["profile"]["apelidos"] == ["Joca", "J"]
    assert stored["profile"]["nome"] == "João" and stored["name"] == "Display João"
    assert stored["profile"]["pet"] == "Luna" and stored["profile"]["time_futebol"] == "Flamengo"
    assert f"/generate?target_id={tid}" in client.get(f"/targets/{tid}").text
    assert "Joca\nJ" in client.get(f"/targets/{tid}").text
    assert "example.test\nlab.test" in client.get(f"/organizations/{oid}").text
    assert "1 org · 1 target" in client.get("/engagements").text
    for collection, item_id, values in (("engagements", eid, {"name": "Edited", "description": "New scope"}),
                                       ("organizations", oid, {**org_values, "keywords": "Updated"}),
                                       ("targets", tid, {**profile, "pet": "Sol"})):
        response = submit(client, f"/{collection}/{item_id}", values, follow_redirects=False)
        assert response.status_code == 303
    assert client.get(f"/api/targets/{tid}").json()["profile"]["pet"] == "Sol"
    assert client.get(f"/api/organizations/{oid}").json()["keywords"] == ["Updated"]
    for collection, item_id in (("engagements", eid), ("organizations", oid)):
        response = submit(client, f"/{collection}/{item_id}/delete", {})
        assert response.status_code == 409 and "linked resources" in response.text
        assert "Traceback" not in response.text
    for collection, item_id in (("targets", tid), ("organizations", oid), ("engagements", eid)):
        assert submit(client, f"/{collection}/{item_id}/delete", {}, follow_redirects=False).status_code == 303
        assert client.get(f"/api/{collection}/{item_id}").status_code == 404


def test_form_errors_preserve_values_and_escape_html(web):
    client, _ = web
    hostile = '<script>alert("x")</script>'
    response = submit(client, "/engagements/new", {"name": " ", "description": hostile})
    assert response.status_code == 422
    assert hostile in html.unescape(response.text) and hostile not in response.text
    response = submit(client, "/targets/new", {"name": "Keep this", "organization_id": "invalid"})
    assert response.status_code == 422 and 'value="Keep this"' in response.text
    response = submit(client, "/generate", quick(nome=hostile, min_len="12", max_len="8", intent="preview"))
    assert response.status_code == 422 and hostile in html.unescape(response.text)
    assert "min_len" in response.text and "Traceback" not in response.text
    created = submit(client, "/engagements/new", {"name": hostile})
    assert created.status_code == 200 and hostile not in created.text and hostile in html.unescape(created.text)
    response = submit(client, "/generate", quick(context_text="unexpected context", intent="preview"))
    assert response.status_code == 422 and "unexpected context" in response.text


def test_csrf_invalid_uuids_missing_records_and_request_size(web):
    client, _ = web
    assert client.post("/engagements/new", data={"name": "bad"}).status_code == 403
    assert client.get("/api/engagements").json() == []
    for path, status in (("/targets/no", 422), (f"/targets/{uuid4()}", 404), ("/unknown", 404)):
        response = client.get(path)
        assert response.status_code == status and "text/html" in response.headers["content-type"]
        assert "Traceback" not in response.text
    assert client.post("/generate", headers={"content-length": "bad"}).status_code == 400
    assert client.post("/generate", headers={"content-length": str(51 * 1024 * 1024)}).status_code == 413


def test_configuration_preview_uses_service_without_consuming_sources(web, monkeypatch):
    client, app = web
    from mimic.application.generation import GenerationService, PreparedGeneration
    original = GenerationService.prepare
    calls = []

    def prepare(self, request):
        calls.append(request)
        return original(self, request)

    def forbidden(*args, **kwargs):
        raise AssertionError("Preview must not generate candidates")

    monkeypatch.setattr(GenerationService, "prepare", prepare)
    monkeypatch.setattr(PreparedGeneration, "iter_candidates", forbidden)
    # Sources are configured during prepare but their iterators must stay lazy.
    def unread_source(*args, **kwargs):
        raise AssertionError("Preview must not read datasets")
        yield
    monkeypatch.setattr("mimic.application.generation.stream_dataset", unread_source)
    monkeypatch.setattr("mimic.application.generation.stream_ptbr", unread_source)
    response = submit(client, "/generate", quick(intent="preview", context_text="pet: Luna", include_ptbr="on"),
                      files={"dataset_file": ("words.txt", b"sample\n")})
    assert response.status_code == 200 and "Ready to generate" in response.text
    assert "Target engine inputs" in response.text and "Dataset sources" in response.text
    assert "PT-BR built-ins" in response.text and "Enabled" in response.text
    assert "Policy" in response.text and "Limits" in response.text
    assert len(calls) == 1 and calls[0].context_facts[0].candidate.value == "Luna"
    assert app.state.repository.list_jobs() == []


def test_saved_target_inherits_org_and_explicit_override(web):
    client, app = web
    org = client.post("/api/organizations", json={"name": "Inherited", "keywords": ["Lab"]}).json()
    override = client.post("/api/organizations", json={"name": "Override", "keywords": ["Scope"]}).json()
    target = client.post("/api/targets", json={"name": "Display", "profile": {"nome": "Pedro"},
                                             "organization_id": org["id"]}).json()
    page = client.get(f"/generate?target_id={target['id']}")
    assert 'value="saved" checked' in page.text and f'value="{target["id"]}" selected' in page.text
    for oid in ("", override["id"]):
        response = submit(client, "/generate", quick(mode="saved", target_id=target["id"], organization_id=oid),
                          follow_redirects=False)
        assert response.status_code == 303
        job_id = response.headers["location"].split("/")[-1]
        job = app.state.job_manager.wait(job_id, 10)
        assert job["status"] == "completed" and job["target_id"] == target["id"]
        assert job["request"]["target"]["organization"]["id"] == org["id"]
        assert (job["request"]["organization"] or {}).get("id") == (oid or None)
        assert ("Override" if oid else "Inherited") in client.get(f"/jobs/{job_id}").text


def test_quick_submission_completed_provenance_download_and_no_terminal_poll(web):
    client, app = web
    response = submit(client, "/generate", quick(leet_mode="partial", data_nascimento="17/08/2002"),
                      follow_redirects=False)
    assert response.status_code == 303
    path = response.headers["location"]
    job_id = path.split("/")[-1]
    job = app.state.job_manager.wait(job_id, 10)
    assert job["status"] == "completed"
    detail = client.get(path)
    assert "Configuration snapshot" in detail.text and "Candidates written" in detail.text
    assert "profile.nome" in detail.text and "profile.data_nascimento" in detail.text
    # With cap=20, original-first partial fills Affix before leet variants.
    assert "Leet substitution" not in detail.text and "Date token" in detail.text
    assert 'class="candidate-detail"' in detail.text
    assert f'href="/api/jobs/{job_id}/download"' in detail.text
    assert "hx-trigger" not in detail.text and "Cancel generation" not in detail.text
    fragment = client.get(path + "/status")
    assert fragment.status_code == 200 and 'id="job-live"' in fragment.text
    assert "<!doctype" not in fragment.text and "hx-trigger" not in fragment.text
    downloaded = client.get(f"/api/jobs/{job_id}/download")
    assert downloaded.status_code == 200 and "attachment" in downloaded.headers["content-disposition"]
    preview = client.get(f"/api/jobs/{job_id}/candidates").json()
    assert len(preview) <= 200
    assert preview[0]["value"] == "Pedro"
    assert not any(t["kind"] == "leet" for row in preview for t in row["transformations"])
    assert preview[0]["value"] in downloaded.text
    assert "Pedro" in client.get("/").text and "Completed" in client.get("/jobs").text


def test_persisted_preview_escaping_all_origin_and_step_labels(web):
    client, app = web
    repo = app.state.repository
    value = '<img src=x onerror="alert(1)">'
    origins = [Origin(source, field, value) for source, field in
               (("profile", "pet"), ("organization", "keyword"), ("dataset", "external.txt"),
                ("ready_candidate", "ready.txt"), ("context_file", "web.pasted:nome"))]
    steps = [Transformation(kind, (("literal", value),)) for kind in ("case", "leet", "date", "affix", "combine", "reverse")]
    job = repo.create_job(GenerationRequest().to_dict(), None, None)
    repo.start_job(job["id"])
    repo.add_preview(job["id"], [{"sequence": 1, "value": value, "origins": [asdict(o) for o in origins],
                                 "transformations": [asdict(t) for t in steps]}])
    repo.finish_job(job["id"], "failed", 1, "Generation failed.")
    response = client.get(f"/jobs/{job['id']}")
    assert response.status_code == 200 and value not in response.text
    assert value in html.unescape(response.text)
    for label in ("Pet", "Organization keyword", "External dataset", "Ready candidate", "Context · Name",
                  "Case", "Leet substitution", "Date token", "Affix", "Combine", "Reverse", "literal"):
        assert label in response.text
    assert "Generation failed." in response.text and "Download wordlist" not in response.text
    assert "hx-trigger" not in response.text


def test_active_polling_real_cancellation_and_failed_worker(tmp_path):
    paths = DataPaths(tmp_path)
    db = Database(paths)
    db.initialize()
    repo = Repository(db)
    entered, release = threading.Event(), threading.Event()

    class Service:
        def prepare(self, request):
            class Prepared:
                evaluated_count = 0

                def iter_results(self, checkpoint=None):
                    entered.set()
                    release.wait(10)
                    checkpoint()
                    self.evaluated_count += 1
                    yield GenerationResult(Candidate("one"))
            return Prepared()

    manager = JobManager(repo, paths, service=Service())
    with TestClient(create_app(repository=repo, manager=manager), cookies={"mimic_locale": "en"}) as client:
        try:
            response = submit(client, "/generate", quick(), follow_redirects=False)
            path = response.headers["location"]
            assert entered.wait(5)
            active = client.get(path + "/status")
            assert 'hx-trigger="every 2s"' in active.text and "Cancel generation" in active.text
            assert "Download wordlist" not in active.text
            # The single worker keeps the second job pending, which polls too.
            pending = submit(client, "/generate", quick(nome="Other"), follow_redirects=False).headers["location"]
            assert "Pending" in client.get(pending + "/status").text
            assert submit(client, pending + "/cancel", {}, follow_redirects=False).status_code == 303
            assert "hx-trigger" not in client.get(pending + "/status").text
            assert submit(client, path + "/cancel", {}, follow_redirects=False).status_code == 303
            release.set()
            assert manager.wait(path.split("/")[-1], 5)["status"] == "cancelled"
            cancelled = client.get(path + "/status")
            assert "Cancelled" in cancelled.text and "hx-trigger" not in cancelled.text
            assert "Download wordlist" not in cancelled.text
        finally:
            release.set()

    class FailingService:
        def prepare(self, request):
            raise RuntimeError("secret traceback information")

    failed_manager = JobManager(repo, paths, service=FailingService())
    with TestClient(create_app(repository=repo, manager=failed_manager), cookies={"mimic_locale": "en"}) as client:
        response = submit(client, "/generate", quick(), follow_redirects=False)
        path = response.headers["location"]
        assert failed_manager.wait(path.split("/")[-1], 5)["status"] == "failed"
        detail = client.get(path).text
        assert "Failed" in detail and "secret traceback" not in detail
        assert "Download wordlist" not in detail and "hx-trigger" not in detail


@pytest.mark.parametrize("role,filename,content", [
    ("dataset", "../escape.txt", b"External\n"),
    ("ready", "candidatos-ação.txt", b"ready-value\n"),
    ("context", "context.txt", b"pet: Luna\n"),
])
def test_managed_upload_preview_reuse_and_causal_generation(web, tmp_path, role, filename, content):
    client, app = web
    preview = submit(client, "/generate", quick(intent="preview"), files={role + "_file": (filename, content)})
    assert preview.status_code == 200
    upload_id = re.search(r'name="' + role + r'_upload_id" value="([^"]+)"', preview.text)[1]
    assert str(UUID(upload_id)) == upload_id
    path = tmp_path / "uploads" / upload_id / f"{role}.txt"
    assert path.read_bytes() == content and path.resolve().is_relative_to(tmp_path.resolve())
    assert not (tmp_path.parent / "escape.txt").exists()
    response = submit(client, "/generate", quick(**{role + "_upload_id": upload_id}), follow_redirects=False)
    assert response.status_code == 303
    job_id = response.headers["location"].split("/")[-1]
    job = app.state.job_manager.wait(job_id, 10)
    assert job["status"] == "completed"
    output = client.get(f"/api/jobs/{job_id}/download").text
    assert {"dataset": "External", "ready": "ready-value", "context": "Luna"}[role] in output
    preview = app.state.repository.list_preview(job_id)
    source = {"dataset": "dataset", "ready": "ready_candidate", "context": "context_file"}[role]
    matching = [o for c in preview for o in c["origins"] if o["source"] == source]
    assert matching and str(path) in matching[0]["field"]


def test_upload_validation_missing_reference_and_values_retained(web, monkeypatch):
    client, app = web
    response = submit(client, "/generate", quick(intent="preview"), files={"dataset_file": ("bad.exe", b"text")})
    assert response.status_code == 422 and "files must use" in response.text
    response = submit(client, "/generate", quick(dataset_upload_id="../../etc/passwd"))
    assert response.status_code == 422 and "Invalid source file reference" in response.text
    response = submit(client, "/generate", quick(dataset_upload_id=str(uuid4())))
    assert response.status_code == 422 and "no longer available" in response.text
    # Earlier uploads remain reusable when a later source or policy is invalid.
    response = submit(client, "/generate", quick(min_len="bad"), files={"dataset_file": ("ok.txt", b"word")})
    assert response.status_code == 422 and "dataset_upload_id" in response.text
    assert 'value="Pedro"' in response.text
    monkeypatch.setattr("mimic.web.uploads.CONTEXT_MAX_BYTES", 4)
    response = submit(client, "/generate", quick(), files={"context_file": ("c.txt", b"pet: Luna")})
    assert response.status_code == 422 and "upload limit" in response.text
    assert not list(app.state.web_uploads.root.glob("*/context.txt"))
    response = submit(client, "/generate", quick(), files={"context_file": ("bad.txt", b"\xff")})
    assert response.status_code == 422 and "Traceback" not in response.text


def test_upload_io_failure_is_friendly(web, monkeypatch):
    client, _ = web

    async def fail(*args):
        raise OSError("secret local path")

    monkeypatch.setattr(UploadStore, "save", fail)
    response = submit(client, "/generate", quick(), files={"dataset_file": ("a.txt", b"word")})
    assert response.status_code == 422 and "could not be stored" in response.text
    assert "secret local path" not in response.text


def test_upload_cleanup_only_abandoned_drafts_and_symlink_safety(tmp_path):
    store = UploadStore(tmp_path)
    old, referenced, fresh = [str(uuid4()) for _ in range(3)]
    for upload_id in (old, referenced, fresh):
        path = store.path(upload_id, "dataset")
        path.parent.mkdir(parents=True)
        path.write_text("word", encoding="utf-8")
    past = time.time() - DRAFT_TTL_SECONDS - 60
    for upload_id in (old, referenced):
        os.utime(store.root / upload_id, (past, past))
    unrelated = store.root / "keep"
    unrelated.mkdir()
    (unrelated / "dataset.txt").write_text("keep", encoding="utf-8")
    os.utime(unrelated, (past, past))
    external = tmp_path / "external"
    external.mkdir()
    (external / "dataset.txt").write_text("external", encoding="utf-8")
    link_id = str(uuid4())
    (store.root / link_id).symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError):
        store.existing(link_id, "dataset")
    store.cleanup([{"request": {"sources": {"dataset_paths": [str(store.path(referenced, "dataset"))]}}}])
    assert not (store.root / old).exists()
    assert (store.root / referenced).exists() and (store.root / fresh).exists()
    assert unrelated.exists() and (external / "dataset.txt").read_text() == "external"


def test_package_assets_and_core_import_without_web_dependencies():
    assets = files("mimic.web")
    assert (assets / "templates/base.html").is_file()
    assert (assets / "static/app.css").is_file()
    assert (assets / "static/htmx.min.js").is_file()
    assert (assets / "static/LICENSE-HTMX.txt").is_file()
    script = '''
import importlib.abc, sys
class NoWeb(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'fastapi', 'starlette', 'jinja2', 'multipart', 'python_multipart', 'httpx', 'uvicorn'}:
            raise ImportError('Web dependencies unavailable')
sys.meta_path.insert(0, NoWeb())
import mimic.core, mimic.domain, mimic.application, mimic.cli
from mimic.application import GenerationRequest, GenerationResult, GenerationService
from mimic.core.candidate import Candidate
assert list(GenerationService().prepare(GenerationRequest(base_candidates=(Candidate('Pedro'),))).iter_candidates())
assert 'mimic.web.routes' not in sys.modules
'''
    subprocess.run([sys.executable, "-B", "-c", script], check=True,
                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def test_dashboard_lists_and_polling_do_not_prepare_generation(web, monkeypatch):
    client, app = web
    job = app.state.repository.create_job(GenerationRequest().to_dict(), None, None)

    def forbidden(*args):
        raise AssertionError("Overview and polling must only read persisted data")

    monkeypatch.setattr("mimic.application.generation.GenerationService.prepare", forbidden)
    for path in ("/", "/jobs", "/targets", "/organizations", "/engagements", f"/jobs/{job['id']}/status"):
        assert client.get(path).status_code == 200


def test_upload_root_symlink_rejected_and_cleanup_runs_on_start(tmp_path):
    draft_store = UploadStore(tmp_path)
    upload_id = str(uuid4())
    path = draft_store.path(upload_id, "dataset")
    path.parent.mkdir(parents=True)
    path.write_text("draft", encoding="utf-8")
    past = time.time() - DRAFT_TTL_SECONDS - 60
    os.utime(path.parent, (past, past))
    with TestClient(create_app(data_dir=tmp_path)):
        assert not path.exists()
    # An unexpected directory is preserved rather than recursively deleted.
    odd = draft_store.path(str(uuid4()), "ready")
    odd.mkdir(parents=True)
    os.utime(odd.parent, (past, past))
    draft_store.cleanup([])
    assert odd.is_dir()
    linked = UploadStore(tmp_path / "linked")
    linked.root.parent.mkdir()
    linked.root.symlink_to(draft_store.root, target_is_directory=True)
    with pytest.raises(ValueError):
        linked.existing(upload_id, "dataset")


def test_dataset_upload_size_limit_leaves_no_partial_file(web, monkeypatch):
    client, app = web
    monkeypatch.setattr("mimic.web.uploads.MAX_UPLOAD_BYTES", 4)
    response = submit(client, "/generate", quick(), files={"dataset_file": ("a.txt", b"oversized")})
    assert response.status_code == 422 and "upload limit" in response.text
    assert not list(app.state.web_uploads.root.iterdir())


@pytest.mark.parametrize("field", ["target_id", "organization_id", "engagement_id"])
def test_generation_identifiers_cannot_change_internal_api_routes(web, field):
    client, app = web
    response = submit(client, "/generate", quick(mode="saved" if field == "target_id" else "quick",
                                                **{field: "../health"}))
    assert response.status_code == 422 and "reference is invalid" in response.text
    assert app.state.repository.list_jobs() == []


def test_non_ascii_csrf_token_is_rejected_without_server_error(web):
    client, _ = web
    response = client.post("/engagements/new", data={"csrf_token": "á", "name": "Rejected"})
    assert response.status_code == 403 and "Reload the page" in response.text
    assert client.get("/api/engagements").json() == []
