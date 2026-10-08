"""Deterministic Gate 5 checks for races, lifecycle and HTTP boundaries."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mimic import __version__
from mimic.api import create_app
from mimic.application import GenerationRequest, MutationOptions, SourceOptions
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.ranking import GenerationResult
from mimic.jobs import JobManager
from mimic.persistence import DataPaths, Database, Repository


def storage(tmp_path):
    paths = DataPaths(tmp_path)
    repo = Repository(Database(paths))
    repo.database.initialize()
    return paths, repo


def request(value="Pedro"):
    return GenerationRequest(base_candidates=(Candidate(value, (Origin("audit", "name", value),)),),
                             mutations=MutationOptions(leet_mode="none"))


def test_terminal_states_and_atomic_claim(tmp_path):
    _, repo = storage(tmp_path)
    pending = repo.create_job(request().to_dict(), None, None)
    cancelled = repo.request_cancel(pending["id"])
    assert cancelled["status"] == "cancelled"
    assert not repo.start_job(pending["id"])
    assert not repo.finish_job(pending["id"], "failed", 0)
    assert repo.request_cancel(pending["id"]) == cancelled

    completed = repo.create_job(request().to_dict(), None, None)
    assert repo.start_job(completed["id"])
    assert repo.complete_job(completed["id"], 4, "internal")
    before = repo.get_job(completed["id"])
    assert not repo.start_job(completed["id"])
    assert not repo.finish_job(completed["id"], "failed", 0)
    assert repo.request_cancel(completed["id"]) == before
    with pytest.raises(ValueError):
        repo.finish_job(completed["id"], "completed", 4)

    failed = repo.create_job(request().to_dict(), None, None)
    assert repo.start_job(failed["id"])
    assert repo.finish_job(failed["id"], "failed", 2, "failure")
    before = repo.get_job(failed["id"])
    assert repo.request_cancel(failed["id"]) == before
    assert not repo.complete_job(failed["id"], 3, "internal")

    contested = repo.create_job(request().to_dict(), None, None)
    barrier = threading.Barrier(2)

    def claim():
        barrier.wait(5)
        return repo.start_job(contested["id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(claim)
        b = pool.submit(claim)
        assert sorted((a.result(5), b.result(5))) == [False, True]


def test_duplicate_queue_entry_is_executed_once(tmp_path):
    paths, repo = storage(tmp_path)
    calls = 0
    lock = threading.Lock()

    class Service:
        def prepare(self, req):
            nonlocal calls
            with lock:
                calls += 1

            class Prepared:
                evaluated_count = 0

                def iter_results(self, checkpoint=None):
                    for candidate in self.iter_candidates():
                        if checkpoint:
                            checkpoint()
                        self.evaluated_count += 1
                        yield GenerationResult(candidate)

                def iter_candidates(self):
                    yield Candidate("only-once")

            return Prepared()

    manager = JobManager(repo, paths, service=Service(), workers=2)
    manager.start()
    try:
        job = manager.submit(request())
        manager._queue.put(job["id"])  # Deliberately duplicate a queue delivery.
        assert manager.wait(job["id"], 5)["status"] == "completed"
        manager._queue.join()
        assert calls == 1
        assert paths.output(job["id"]).read_text(encoding="utf-8") == "only-once\n"
    finally:
        manager.stop()


def test_cancel_between_last_check_and_rename(tmp_path, monkeypatch):
    paths, repo = storage(tmp_path)
    manager = JobManager(repo, paths)
    entered = threading.Event()
    release = threading.Event()
    original_replace = os.replace

    def paused_replace(source, destination):
        entered.set()
        assert release.wait(5)
        return original_replace(source, destination)

    monkeypatch.setattr("mimic.jobs.manager.os.replace", paused_replace)
    manager.start()
    try:
        job = manager.submit(request())
        assert entered.wait(5)
        assert not paths.output(job["id"]).exists()
        assert manager.cancel(job["id"])["cancel_requested"]
        release.set()
        assert manager.wait(job["id"], 5)["status"] == "cancelled"
        assert not paths.output(job["id"]).exists()
        assert not paths.output(job["id"]).with_name("wordlist.txt.part").exists()
    finally:
        release.set()
        manager.stop()


def test_rename_error_fails_without_final_file(tmp_path, monkeypatch):
    paths, repo = storage(tmp_path)

    def broken_replace(source, destination):
        raise OSError("rename failed")

    monkeypatch.setattr("mimic.jobs.manager.os.replace", broken_replace)
    manager = JobManager(repo, paths)
    manager.start()
    try:
        job = manager.submit(request())
        result = manager.wait(job["id"], 5)
        assert result["status"] == "failed"
        assert not paths.output(job["id"]).exists()
        assert not paths.output(job["id"]).with_name("wordlist.txt.part").exists()
    finally:
        manager.stop()


def test_concurrent_read_and_double_cancel(tmp_path):
    paths, repo = storage(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class Service:
        def prepare(self, req):
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
                    assert release.wait(5)
                    yield Candidate("one")
            return Prepared()

    manager = JobManager(repo, paths, service=Service())
    manager.start()
    try:
        job = manager.submit(request())
        assert entered.wait(5)
        with ThreadPoolExecutor(max_workers=4) as pool:
            reads = [pool.submit(repo.get_job, job["id"]) for _ in range(10)]
            cancels = [pool.submit(manager.cancel, job["id"]) for _ in range(2)]
            assert all(f.result(5)["id"] == job["id"] for f in reads)
            assert all(f.result(5)["cancel_requested"] for f in cancels)
        release.set()
        assert manager.wait(job["id"], 5)["status"] == "cancelled"
    finally:
        release.set()
        manager.stop()


def test_restart_keeps_terminals_and_cleans_only_incomplete(tmp_path):
    paths, repo = storage(tmp_path)
    jobs = {name: repo.create_job(request(name).to_dict(), None, None)
            for name in ("pending", "running", "completed", "failed", "cancelled")}
    repo.start_job(jobs["running"]["id"])
    repo.start_job(jobs["completed"]["id"])
    completed_path = paths.output(jobs["completed"]["id"])
    completed_path.parent.mkdir(parents=True)
    completed_path.write_text("done\n", encoding="utf-8")
    repo.complete_job(jobs["completed"]["id"], 1, str(completed_path))
    repo.start_job(jobs["failed"]["id"])
    repo.finish_job(jobs["failed"]["id"], "failed", 0, "old failure")
    repo.request_cancel(jobs["cancelled"]["id"])
    for name in ("pending", "running"):
        part = paths.output(jobs[name]["id"]).with_name("wordlist.txt.part")
        part.parent.mkdir(parents=True)
        part.write_text("partial", encoding="utf-8")
    manager = JobManager(repo, paths)
    manager.start()
    try:
        statuses = {name: repo.get_job(job["id"])["status"] for name, job in jobs.items()}
        assert statuses == {"pending": "failed", "running": "failed", "completed": "completed",
                            "failed": "failed", "cancelled": "cancelled"}
        assert completed_path.read_text(encoding="utf-8") == "done\n"
        for name in ("pending", "running"):
            assert not paths.output(jobs[name]["id"]).with_name("wordlist.txt.part").exists()
        completed_path.unlink()
        with pytest.raises(FileNotFoundError):
            manager.completed_output(jobs["completed"]["id"])
        assert repo.get_job(jobs["completed"]["id"])["status"] == "completed"
    finally:
        manager.stop()


def test_shutdown_and_lifecycle_are_cooperative(tmp_path):
    paths, repo = storage(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class Service:
        def prepare(self, req):
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
                    yield Candidate("late")
            return Prepared()

    manager = JobManager(repo, paths, service=Service())
    manager.start()
    manager.start()
    assert len(manager._threads) == 1
    job = manager.submit(request())
    assert entered.wait(5)
    stopper = threading.Thread(target=manager.stop)
    stopper.start()
    try:
        assert manager._stopping.wait(5)
        release.set()
        stopper.join(5)
        assert not stopper.is_alive()
        assert not manager._threads
        assert repo.get_job(job["id"])["status"] == "cancelled"
        assert not paths.output(job["id"]).exists()
        with pytest.raises(RuntimeError, match="not running"):
            manager.submit(request())
        manager.stop()
    finally:
        release.set()
        stopper.join(5)


def test_two_apps_are_isolated(tmp_path):
    app_a = create_app(data_dir=tmp_path / "a")
    app_b = create_app(data_dir=tmp_path / "b")
    assert app_a.state.job_manager is not app_b.state.job_manager
    with ExitStack() as stack:
        a = stack.enter_context(TestClient(app_a))
        b = stack.enter_context(TestClient(app_b))
        job_a = a.post("/api/jobs", json={"request": request("Alpha").to_dict()}).json()
        job_b = b.post("/api/jobs", json={"request": request("Beta").to_dict()}).json()
        assert app_a.state.job_manager.wait(job_a["id"], 5)["status"] == "completed"
        assert app_b.state.job_manager.wait(job_b["id"], 5)["status"] == "completed"
        assert a.get(f"/api/jobs/{job_b['id']}").status_code == 404
        assert b.get(f"/api/jobs/{job_a['id']}").status_code == 404
        assert (tmp_path / "a" / "mimic.db").exists()
        assert (tmp_path / "b" / "mimic.db").exists()
        assert app_a.state.job_manager.paths.output(job_a["id"]).exists()
        assert app_b.state.job_manager.paths.output(job_b["id"]).exists()
    assert not app_a.state.job_manager._threads
    assert not app_b.state.job_manager._threads


def test_preview_bound_count_lines_and_provenance(tmp_path):
    paths, repo = storage(tmp_path)
    source = tmp_path / "ready.txt"
    source.write_text("".join(f"word{i}\n" for i in range(230)), encoding="utf-8")
    req = GenerationRequest(sources=SourceOptions(ready_candidate_paths=(str(source),)),
                            mutations=MutationOptions(leet_mode="none"))
    manager = JobManager(repo, paths)
    manager.start()
    try:
        job = manager.submit(req)
        result = manager.wait(job["id"], 10)
        preview = repo.list_preview(job["id"], 300)
        assert result["status"] == "completed"
        assert result["candidate_count"] == len(paths.output(job["id"]).read_text(encoding="utf-8").splitlines())
        assert result["candidate_count"] > len(preview) == 200
        assert [item["sequence"] for item in preview] == list(range(1, 201))
        assert preview[0]["origins"][0]["source"] == "ready_candidate"
        assert isinstance(preview[0]["transformations"], list)
        source.unlink()
        paths.output(job["id"]).unlink()
    finally:
        manager.stop()


def test_dataset_contents_are_lazy_while_request_is_snapshotted(tmp_path):
    paths, repo = storage(tmp_path)
    source = tmp_path / "ready.txt"
    source.write_text("before\n", encoding="utf-8")
    entered = threading.Event()
    release = threading.Event()

    from mimic.application import GenerationService

    class Service(GenerationService):
        def prepare(self, req):
            if req.base_candidates and req.base_candidates[0].value == "BLOCK":
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
                        yield Candidate("block")
                return Prepared()
            return super().prepare(req)

    manager = JobManager(repo, paths, service=Service())
    manager.start()
    try:
        blocker = manager.submit(request("BLOCK"))
        assert entered.wait(5)
        req = GenerationRequest(sources=SourceOptions(ready_candidate_paths=(str(source),)),
                                mutations=MutationOptions(leet_mode="none"))
        job = manager.submit(req)
        assert repo.get_job(job["id"])["status"] == "pending"
        source.write_text("after\n", encoding="utf-8")
        req.sources = SourceOptions()
        release.set()
        assert manager.wait(blocker["id"], 5)["status"] == "completed"
        assert manager.wait(job["id"], 5)["status"] == "completed"
        assert paths.output(job["id"]).read_text(encoding="utf-8") == "after\n"
        assert repo.get_job(job["id"])["request"]["sources"]["ready_candidate_paths"] == [str(source)]
    finally:
        release.set()
        manager.stop()


def test_failed_source_then_next_job_succeeds(tmp_path):
    paths, repo = storage(tmp_path)
    missing = tmp_path / "missing.txt"
    req = GenerationRequest(sources=SourceOptions(dataset_paths=(str(missing),)))
    manager = JobManager(repo, paths)
    manager.start()
    try:
        failed = manager.submit(req)
        first = manager.wait(failed["id"], 5)
        assert first["status"] == "failed"
        assert first["error"] == "source file not found"
        assert str(missing) not in first["error"]
        assert not paths.output(failed["id"]).exists()
        assert not paths.output(failed["id"]).with_name("wordlist.txt.part").exists()
        good = manager.submit(request("Good"))
        assert manager.wait(good["id"], 5)["status"] == "completed"
    finally:
        manager.stop()


def test_symlink_job_directory_cannot_write_outside_data_dir(tmp_path):
    paths, repo = storage(tmp_path / "data")
    outside = tmp_path / "outside"
    outside.mkdir()
    entered = threading.Event()
    release = threading.Event()

    from mimic.application import GenerationService

    class Service(GenerationService):
        def prepare(self, req):
            if req.base_candidates and req.base_candidates[0].value == "BLOCK":
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
                        yield Candidate("block")
                return Prepared()
            return super().prepare(req)

    manager = JobManager(repo, paths, service=Service())
    manager.start()
    try:
        blocker = manager.submit(request("BLOCK"))
        assert entered.wait(5)
        attack = manager.submit(request("Attack"))
        paths.job_dir(attack["id"]).symlink_to(outside, target_is_directory=True)
        release.set()
        assert manager.wait(blocker["id"], 5)["status"] == "completed"
        assert manager.wait(attack["id"], 5)["status"] == "failed"
        assert not (outside / "wordlist.txt").exists()
        assert not (outside / "wordlist.txt.part").exists()
    finally:
        release.set()
        manager.stop()


def test_stored_organization_snapshot_and_unicode_http_shape(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        org = client.post("/api/organizations", json={"name": "São Paulo",
                                                    "keywords": ["Coração"]}).json()
        target = client.post("/api/targets", json={"name": "João", "organization_id": org["id"],
                                                 "profile": {"nome": "João", "apelidos": ["Joca"]}}).json()
        candidate = Candidate("João", (Origin("manual", "nome", "João"),),
                              (Transformation("case", (("mode", "original"),)),))
        req = GenerationRequest(base_candidates=(candidate,))
        posted = client.post("/api/jobs", json={"request": req.to_dict(), "target_id": target["id"]})
        assert posted.status_code == 201
        job_id = posted.json()["id"]
        assert client.patch(f"/api/organizations/{org['id']}",
                            json={"keywords": ["Mudou"]}).status_code == 200
        saved = client.get(f"/api/jobs/{job_id}").json()["request"]
        assert saved["target"]["organization"]["keywords"] == ["Coração"]
        assert saved["base_candidates"][0]["value"] == "João"
        assert saved["base_candidates"][0]["transformations"][0]["kind"] == "case"
        assert app.state.job_manager.wait(job_id, 5)["status"] == "completed"
        preview = client.get(f"/api/jobs/{job_id}/candidates").json()
        assert any(item["origins"] and item["origins"][0]["value"] == "João" for item in preview)


def test_nested_output_path_cannot_redirect_job(tmp_path):
    app = create_app(data_dir=tmp_path / "data")
    owned = tmp_path / "owned.txt"
    payload = request().to_dict()
    payload["output_path"] = str(owned)
    with TestClient(app) as client:
        response = client.post("/api/jobs", json={"request": payload})
        assert response.status_code == 201
        job_id = response.json()["id"]
        assert app.state.job_manager.wait(job_id, 5)["status"] == "completed"
        assert not owned.exists()
        assert app.state.job_manager.paths.output(job_id).exists()


def test_serve_rejects_remote_hosts_and_bad_ports(monkeypatch, tmp_path):
    from mimic.cli import main

    seen = []

    def fake_run(app, *, host, port):
        seen.append((host, port, app.state.job_manager.paths.root))

    monkeypatch.setattr("uvicorn.run", fake_run)
    assert main(["serve", "--data-dir", str(tmp_path)]) == 0
    assert seen[-1][:2] == ("127.0.0.1", 8787)
    assert main(["serve", "--host", "::1", "--port", "9000",
                 "--data-dir", str(tmp_path)]) == 0
    assert seen[-1][:2] == ("::1", 9000)
    for host in ("localhost", "0.0.0.0", "192.168.1.4", "8.8.8.8"):
        with pytest.raises(SystemExit) as exc:
            main(["serve", "--host", host])
        assert exc.value.code == 2
    for port in ("0", "65536", "-1"):
        with pytest.raises(SystemExit) as exc:
            main(["serve", "--port", port])
        assert exc.value.code == 2
    assert len(seen) == 2


def test_uuid_patch_crud_and_download_containment(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        unknown = str(uuid4())
        for resource in ("engagements", "organizations", "targets", "jobs"):
            assert client.get(f"/api/{resource}/bad-id").status_code == 422
            assert client.get(f"/api/{resource}/{unknown}").status_code == 404
        for path in ("../", "%2e%2e", "bad-id", unknown):
            response = client.get(f"/api/jobs/{path}/download")
            assert response.status_code in (404, 422)
        assert client.get("/api/health").json() == {"status": "ok", "version": __version__}
        schema = client.get("/openapi.json").json()
        assert "/api/jobs/{job_id}/download" in schema["paths"]
        assert "/api/targets/{item_id}" in schema["paths"]
        invalid = client.post("/api/jobs", json={"request": {"limits": {"max_dataset_lines": 0}}})
        assert invalid.status_code == 422 and isinstance(invalid.json()["detail"], str)
        absent = client.get(f"/api/jobs/{unknown}")
        assert absent.status_code == 404 and isinstance(absent.json()["detail"], str)

        e = client.post("/api/engagements", json={"name": "E"}).json()
        o = client.post("/api/organizations", json={"name": "O", "engagement_id": e["id"],
                                                     "aliases": ["A"], "locations": ["São Paulo"],
                                                     "keywords": ["K"], "relevant_dates": ["01/01"],
                                                     "domains": ["example.test"]}).json()
        assert client.get(f"/api/organizations/{o['id']}").json() == o
        assert client.get("/api/organizations").json() == [o]
        assert client.patch(f"/api/organizations/{o['id']}", json={"keywords": None}).status_code == 422
        updated = client.patch(f"/api/organizations/{o['id']}", json={"aliases": []}).json()
        assert updated["aliases"] == [] and updated["locations"] == ["São Paulo"]
        t = client.post("/api/targets", json={"name": "T", "organization_id": o["id"],
                                               "profile": {"nome": "João", "apelidos": ["Joca"]}}).json()
        assert client.get(f"/api/targets/{t['id']}").json() == t
        assert client.get("/api/targets").json() == [t]
        assert client.patch(f"/api/targets/{t['id']}", json={"profile": None}).status_code == 422
        changed = client.patch(f"/api/targets/{t['id']}", json={"name": "T2"}).json()
        assert changed["profile"] == t["profile"]
        assert client.delete(f"/api/engagements/{e['id']}").status_code == 409
        assert client.delete(f"/api/organizations/{o['id']}").status_code == 409
        j = client.post("/api/jobs", json={"request": request().to_dict(), "target_id": t["id"]}).json()
        assert app.state.job_manager.wait(j["id"], 5)["status"] == "completed"
        output = app.state.job_manager.paths.output(j["id"])
        external = tmp_path / "external.txt"
        external.write_text("secret", encoding="utf-8")
        output.unlink()
        output.symlink_to(external)
        assert client.get(f"/api/jobs/{j['id']}/download").status_code == 404
        output.unlink()
        assert client.delete(f"/api/targets/{t['id']}").status_code == 409


def test_schema_version_and_utc_timestamps(tmp_path):
    paths, repo = storage(tmp_path)
    with repo.database.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    job = repo.create_job(request().to_dict(), None, None)
    assert repo.start_job(job["id"])
    assert repo.finish_job(job["id"], "failed", 0)
    saved = repo.get_job(job["id"])
    for field in ("created_at", "started_at", "finished_at"):
        parsed = datetime.fromisoformat(saved[field])
        assert parsed.tzinfo == timezone.utc
    with sqlite3.connect(paths.database) as connection:
        connection.execute("PRAGMA user_version = 3")
    with pytest.raises(RuntimeError, match="unsupported database schema version"):
        repo.database.initialize()


def test_import_api_has_no_storage_or_worker_side_effect(tmp_path):
    script = ("import os, pathlib, threading; import mimic.api.app; "
              "root = pathlib.Path(os.environ['XDG_DATA_HOME']) / 'mimic'; "
              "assert not root.exists(); assert len(threading.enumerate()) == 1")
    subprocess.run([sys.executable, "-B", "-c", script], check=True,
                   env={**os.environ, "XDG_DATA_HOME": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"})
