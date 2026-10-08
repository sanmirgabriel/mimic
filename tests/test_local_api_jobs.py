"""Block 5 local persistence, worker, HTTP and import boundary tests."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mimic.api import create_app
from mimic.application import GenerationRequest
from mimic.core.candidate import Candidate, Origin
from mimic.ranking import GenerationResult
from mimic.jobs import JobManager
from mimic.persistence import DataPaths, Database, Repository
from mimic.persistence.repository import StorageConflict


def request_for(value: str = "Pedro") -> GenerationRequest:
    return GenerationRequest(base_candidates=(Candidate(value, (Origin("test", "name", value),)),))


def store(tmp_path):
    paths = DataPaths(tmp_path)
    db = Database(paths)
    db.initialize()
    return paths, Repository(db)


def test_repository_crud_relationships_and_sqlite_settings(tmp_path):
    paths, repo = store(tmp_path)
    with repo.database.connection() as con:
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    engagement = repo.create_engagement("Project", "scope")
    assert repo.list_engagements() == [engagement]
    assert repo.get_engagement(engagement["id"]) == engagement
    assert repo.update_engagement(engagement["id"], {"name": "New"})["name"] == "New"
    org = repo.create_organization({"name": "Org", "engagement_id": engagement["id"],
                                    "aliases": ["São Paulo"]})
    assert repo.get_organization(org["id"])["aliases"] == ["São Paulo"]
    assert repo.update_organization(org["id"], {"keywords": ["Lab"]})["keywords"] == ["Lab"]
    target = repo.create_target({"name": "Pedro", "profile": {"nome": " João "},
                                 "organization_id": org["id"]})
    assert repo.get_target(target["id"])["profile"]["nome"] == "João"
    assert repo.update_target(target["id"], {"name": "João"})["name"] == "João"
    job = repo.create_job(request_for().to_dict(), target["id"], engagement["id"])
    assert repo.get_job(job["id"])["request"] == json.loads(json.dumps(request_for().to_dict()))
    with pytest.raises(StorageConflict):
        repo.delete_target(target["id"])
    with pytest.raises(StorageConflict):
        repo.delete_organization(org["id"])
    with pytest.raises(StorageConflict):
        repo.delete_engagement(engagement["id"])
    assert repo.list_targets()[0]["id"] == target["id"]
    assert repo.list_jobs()[0]["id"] == job["id"]
    with pytest.raises(StorageConflict):
        repo.create_target({"name": "bad", "organization_id": "missing"})
    # A second independent connection sees committed state.
    assert Repository(Database(paths)).get_engagement(engagement["id"])["name"] == "New"


def test_repository_delete_unreferenced(tmp_path):
    _, repo = store(tmp_path)
    e = repo.create_engagement("E")
    o = repo.create_organization({"name": "O"})
    t = repo.create_target({"name": "T"})
    assert repo.delete_target(t["id"])
    assert repo.delete_organization(o["id"])
    assert repo.delete_engagement(e["id"])
    assert repo.get_target(t["id"]) is None


def test_job_completion_snapshot_isolation_preview_and_restart(tmp_path):
    paths, repo = store(tmp_path)
    manager = JobManager(repo, paths, preview_limit=3, count_batch=2)
    manager.start()
    request = request_for("Pedro")
    first = manager.submit(request)
    request.base_candidates = (Candidate("Changed"),)
    second = manager.submit(request_for("João"))
    a = manager.wait(first["id"], 10)
    b = manager.wait(second["id"], 10)
    assert a["status"] == b["status"] == "completed"
    assert a["id"] != b["id"]
    assert a["candidate_count"] > 0 and b["candidate_count"] > 0
    assert paths.output(a["id"]) != paths.output(b["id"])
    assert "P3dro" in paths.output(a["id"]).read_text(encoding="utf-8")
    assert paths.output(a["id"]).read_text(encoding="utf-8") != paths.output(b["id"]).read_text(encoding="utf-8")
    assert "Changed" not in paths.output(a["id"]).read_text(encoding="utf-8")
    assert not paths.output(a["id"]).with_name("wordlist.txt.part").exists()
    preview = repo.list_preview(a["id"])
    assert len(preview) == 3
    assert preview[0]["sequence"] == 1
    assert preview[0]["origins"] == [asdict(Origin("test", "name", "Pedro"))]
    assert isinstance(preview[1]["transformations"], list)
    assert repo.list_preview(a["id"], 1, 1)[0] == preview[1]
    assert repo.get_job(a["id"])["request"]["base_candidates"][0]["value"] == "Pedro"
    manager.stop()
    pending = repo.create_job(request_for().to_dict(), None, None)
    repo.start_job(pending["id"])
    part = paths.output(pending["id"]).with_name("wordlist.txt.part")
    part.parent.mkdir(parents=True)
    part.write_text("partial", encoding="utf-8")
    restarted = JobManager(repo, paths)
    restarted.start()
    assert repo.get_job(pending["id"])["status"] == "failed"
    assert "restart" in repo.get_job(pending["id"])["error"]
    assert not part.exists()
    restarted.stop()


def test_job_cancel_and_failure_no_final_output(tmp_path):
    paths, repo = store(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class BlockingPrepared:
        evaluated_count = 0

        def iter_results(self, checkpoint=None):
            for candidate in self.iter_candidates():
                if checkpoint:
                    checkpoint()
                self.evaluated_count += 1
                yield GenerationResult(candidate)

        def iter_candidates(self):
            entered.set()
            release.wait(5)
            yield Candidate("one", (Origin("test", "seed", "one"),))

    class BlockingService:
        def prepare(self, request):
            return BlockingPrepared()

    manager = JobManager(repo, paths, service=BlockingService())
    manager.start()
    job = manager.submit(request_for())
    assert entered.wait(5)
    assert repo.get_job(job["id"])["status"] == "running"
    assert manager.cancel(job["id"])["cancel_requested"]
    release.set()
    assert manager.wait(job["id"], 5)["status"] == "cancelled"
    assert not paths.output(job["id"]).exists()
    manager.stop()

    class FailingPrepared:
        evaluated_count = 0

        def iter_results(self, checkpoint=None):
            for candidate in self.iter_candidates():
                if checkpoint:
                    checkpoint()
                self.evaluated_count += 1
                yield GenerationResult(candidate)

        def iter_candidates(self):
            yield Candidate("first")
            raise RuntimeError("secret internal detail")

    class FailingService:
        def prepare(self, request):
            return FailingPrepared()

    failed_manager = JobManager(repo, paths, service=FailingService())
    failed_manager.start()
    failed = failed_manager.submit(request_for())
    result = failed_manager.wait(failed["id"], 5)
    assert result["status"] == "failed" and result["candidate_count"] == 1
    assert "secret" not in result["error"]
    assert not paths.output(failed["id"]).exists()
    assert not paths.output(failed["id"]).with_name("wordlist.txt.part").exists()
    failed_manager.stop()


def test_pending_cancel_and_single_prepare(tmp_path):
    paths, repo = store(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class Prepared:
        evaluated_count = 0

        def iter_results(self, checkpoint=None):
            for candidate in self.iter_candidates():
                if checkpoint:
                    checkpoint()
                self.evaluated_count += 1
                yield GenerationResult(candidate)

        def iter_candidates(self):
            entered.set()
            release.wait(5)
            yield Candidate("one")

    class Service:
        calls = 0

        def prepare(self, request):
            self.calls += 1
            return Prepared()

    service = Service()
    manager = JobManager(repo, paths, service=service)
    manager.start()
    running = manager.submit(request_for())
    assert entered.wait(5)
    pending = manager.submit(request_for("other"))
    assert repo.get_job(pending["id"])["status"] == "pending"
    assert manager.cancel(pending["id"])["status"] == "cancelled"
    release.set()
    assert manager.wait(running["id"], 5)["status"] == "completed"
    assert manager.wait(pending["id"], 5)["status"] == "cancelled"
    assert service.calls == 1
    assert not paths.output(pending["id"]).exists()
    manager.stop()


def test_http_crud_jobs_errors_docs_and_download(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        e = client.post("/api/engagements", json={"name": "Project"}).json()
        assert client.get("/api/engagements").json()[0]["id"] == e["id"]
        assert client.patch(f"/api/engagements/{e['id']}", json={"description": "Scope"}).json()["description"] == "Scope"
        org = client.post("/api/organizations", json={"name": "Org", "engagement_id": e["id"]}).json()
        target = client.post("/api/targets", json={"name": "Person", "profile": {"nome": "Pedro"},
                                                      "organization_id": org["id"]}).json()
        assert client.get(f"/api/targets/{target['id']}").status_code == 200
        assert client.patch(f"/api/targets/{target['id']}", json={"name": "Other"}).json()["name"] == "Other"
        assert client.delete(f"/api/organizations/{org['id']}").status_code == 409
        assert client.get("/api/targets/missing").status_code == 422
        assert client.post("/api/jobs", json={"request": {"limits": {"max_candidates_per_word": 0}}}).status_code == 422
        assert client.post("/api/jobs", json={"request": {"sources": []}}).status_code == 422
        created = client.post("/api/jobs", json={"request": request_for().to_dict(),
                                                  "target_id": target["id"], "engagement_id": e["id"]})
        assert created.status_code == 201
        job_id = created.json()["id"]
        assert app.state.job_manager.wait(job_id, 10)["status"] == "completed"
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
        assert client.get("/api/jobs").json()[0]["id"] == job_id
        assert client.get(f"/api/jobs/{job_id}/candidates?limit=1").json()[0]["origins"]
        assert client.get(f"/api/jobs/{job_id}/download").status_code == 200
        assert client.post("/api/jobs", json={"request": {}, "output_path": "/tmp/unsafe"}).status_code == 422
        assert client.get("/api/jobs/missing/download").status_code == 422
        assert client.post("/api/jobs/missing/cancel").status_code == 422
        assert client.delete(f"/api/targets/{target['id']}").status_code == 409


def test_stored_target_snapshot_survives_edit(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        target = client.post("/api/targets", json={"name": "Person", "profile": {"nome": "Pedro"}}).json()
        job = client.post("/api/jobs", json={"request": {}, "target_id": target["id"]}).json()
        assert client.patch(f"/api/targets/{target['id']}",
                            json={"profile": {"nome": "João"}}).status_code == 200
        saved = client.get(f"/api/jobs/{job['id']}").json()
        assert saved["request"]["target"]["profile"]["nome"] == "Pedro"
        assert app.state.job_manager.wait(job["id"], 10)["status"] == "completed"


def test_http_download_rejects_running_and_cancelled(tmp_path):
    paths, repo = store(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class Service:
        def prepare(self, request):
            class Prepared:
                evaluated_count = 0

                def iter_results(self, checkpoint=None):
                    entered.set()
                    release.wait(5)
                    checkpoint()
                    self.evaluated_count += 1
                    yield GenerationResult(Candidate("one"))
            return Prepared()

    manager = JobManager(repo, paths, service=Service())
    with TestClient(create_app(repository=repo, manager=manager)) as client:
        job = client.post("/api/jobs", json={"request": request_for().to_dict()}).json()
        assert entered.wait(5)
        assert client.get(f"/api/jobs/{job['id']}/download").status_code == 409
        assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 200
        release.set()
        assert manager.wait(job["id"], 5)["status"] == "cancelled"
        assert client.get(f"/api/jobs/{job['id']}/download").status_code == 409


def test_job_id_path_validation_and_import_boundary(tmp_path):
    paths = DataPaths(tmp_path)
    with pytest.raises(ValueError):
        paths.output("../../etc/passwd")
    script = "import sys; import mimic.persistence, mimic.jobs; assert 'fastapi' not in sys.modules; assert 'mimic.cli' not in sys.modules"
    subprocess.run([sys.executable, "-B", "-c", script], check=True,
                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
