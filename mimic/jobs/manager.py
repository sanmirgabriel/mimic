"""Bounded local worker queue using the application generation service."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from dataclasses import asdict
from pathlib import Path

from mimic.application import GenerationRequest, GenerationService
from mimic.persistence import DataPaths, Repository

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(self, repository: Repository, paths: DataPaths,
                 service: GenerationService | None = None, workers: int = 1,
                 preview_limit: int = 200, count_batch: int = 100) -> None:
        if workers < 1 or preview_limit < 1 or count_batch < 1:
            raise ValueError("workers, preview_limit and count_batch must be positive")
        self.repository = repository
        self.paths = paths
        self.service = service or GenerationService()
        self.workers = workers
        self.preview_limit = preview_limit
        self.count_batch = count_batch
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._events: dict[str, threading.Event] = {}
        self._done: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._stopping = threading.Event()

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._threads:
                return
            self.repository.database.initialize()
            self.repository.recover_incomplete()
            if self.paths.jobs.is_symlink():
                raise ValueError("jobs directory must not be a symlink")
            for job_dir in self.paths.jobs.iterdir():
                if not job_dir.is_dir() or job_dir.is_symlink():
                    continue
                try:
                    self.paths.job_dir(job_dir.name)
                except ValueError:
                    continue
                (job_dir / "wordlist.txt.part").unlink(missing_ok=True)
                output = job_dir / "wordlist.txt"
                job = self.repository.get_job(job_dir.name)
                if job is None or job["status"] != "completed":
                    output.unlink(missing_ok=True)
            self._stopping.clear()
            for index in range(self.workers):
                thread = threading.Thread(target=self._worker, name=f"mimic-job-{index}")
                thread.start()
                self._threads.append(thread)

    def stop(self) -> None:
        with self._lifecycle_lock:
            if not self._threads:
                return
            self._stopping.set()
            with self._lock:
                active_ids = list(self._events)
                for event in self._events.values():
                    event.set()
            for job_id in active_ids:
                self.repository.request_cancel(job_id)
            threads = list(self._threads)
            for _ in threads:
                self._queue.put(None)
            for thread in threads:
                thread.join()
            self._threads.clear()
            self.repository.recover_incomplete()

    def submit(self, request: GenerationRequest, target_id: str | None = None,
               engagement_id: str | None = None) -> dict:
        with self._lifecycle_lock:
            if not self._threads or self._stopping.is_set():
                raise RuntimeError("job manager is not running")
            # Round-trip immediately: callers may mutate GenerationRequest after submit.
            snapshot = json.loads(json.dumps(request.to_dict(), ensure_ascii=False))
            frozen = GenerationRequest.from_dict(snapshot)
            if target_id is not None:
                target = self.repository.target_domain(target_id)
                if target is None:
                    raise LookupError("target not found")
                if frozen.target is None:
                    frozen.target = target
                    snapshot = frozen.to_dict()
            if engagement_id is not None and self.repository.get_engagement(engagement_id) is None:
                raise LookupError("engagement not found")
            frozen.validate()
            job = self.repository.create_job(snapshot, target_id, engagement_id)
            with self._lock:
                self._events[job["id"]] = threading.Event()
                self._done[job["id"]] = threading.Event()
            self._queue.put(job["id"])
            return job

    def cancel(self, job_id: str) -> dict | None:
        job = self.repository.request_cancel(job_id)
        if job is not None:
            with self._lock:
                event = self._events.get(job_id)
                done = self._done.get(job_id)
            if event:
                event.set()
            if done and job["status"] == "cancelled":
                done.set()
        return job

    def wait(self, job_id: str, timeout: float = 10) -> dict | None:
        with self._lock:
            done = self._done.get(job_id)
        if done:
            done.wait(timeout)
        return self.repository.get_job(job_id)

    def _is_managed_job_dir(self, job_id: str) -> bool:
        job_dir = self.paths.job_dir(job_id)
        return (not self.paths.jobs.is_symlink() and not job_dir.is_symlink()
                and job_dir.resolve() == self.paths.jobs.resolve() / job_id)

    def completed_output(self, job_id: str) -> Path:
        job = self.repository.get_job(job_id)
        if job is None:
            raise LookupError("job not found")
        if job["status"] != "completed":
            raise ValueError("job is not completed")
        output = self.paths.output(job_id)
        if (not self._is_managed_job_dir(job_id) or output.is_symlink()
                or output.resolve().parent != output.parent.resolve()
                or not output.is_file()):
            raise FileNotFoundError("completed wordlist is unavailable")
        return output

    def _worker(self) -> None:
        while True:
            job_id = self._queue.get()
            claimed = False
            try:
                if job_id is None:
                    return
                if self._stopping.is_set():
                    continue
                claimed = self.repository.start_job(job_id)
                if claimed:
                    self._execute(job_id)
            except BaseException:
                logger.exception("worker failed for job %s", job_id)
                if claimed:
                    try:
                        self.repository.finish_job(job_id, "failed", 0, "unexpected worker error")
                    except Exception:
                        logger.exception("could not persist worker failure for job %s", job_id)
            finally:
                if job_id is not None:
                    try:
                        record = self.repository.get_job(job_id)
                        terminal = record is not None and record["status"] in (
                            "completed", "failed", "cancelled"
                        )
                    except Exception:
                        logger.exception("could not inspect final state for job %s", job_id)
                        terminal = False
                    if terminal:
                        with self._lock:
                            done = self._done.pop(job_id, None)
                            self._events.pop(job_id, None)
                        if done:
                            done.set()
                self._queue.task_done()

    def _execute(self, job_id: str) -> None:
        output = self.paths.output(job_id)
        part = output.with_name(output.name + ".part")
        count = 0
        preview: list[dict] = []
        try:
            job = self.repository.get_job(job_id)
            with self._lock:
                cancellation = self._events[job_id]
            output.parent.mkdir(parents=True, exist_ok=True)
            if not self._is_managed_job_dir(job_id):
                raise ValueError("job output directory is not managed")
            request = GenerationRequest.from_dict(job["request"])
            prepared = self.service.prepare(request)
            with part.open("x", encoding="utf-8") as stream:
                for candidate in prepared.iter_candidates():
                    if cancellation.is_set() or self._stopping.is_set():
                        break
                    stream.write(candidate.value + "\n")
                    count += 1
                    if len(preview) < self.preview_limit:
                        preview.append({"sequence": count, "value": candidate.value,
                                        "origins": [asdict(x) for x in candidate.origins],
                                        "transformations": [asdict(x) for x in candidate.transformations]})
                    if count % self.count_batch == 0:
                        self.repository.set_count(job_id, count)
            self.repository.add_preview(job_id, preview)
            if cancellation.is_set() or self._stopping.is_set() or self.repository.get_job(job_id)["cancel_requested"]:
                self.repository.finish_job(job_id, "cancelled", count)
            else:
                os.replace(part, output)
                if not self.repository.complete_job(job_id, count, str(output)):
                    output.unlink(missing_ok=True)
                    self.repository.finish_job(job_id, "cancelled", count)
        except Exception as exc:
            logger.exception("generation failed for job %s", job_id)
            if self._is_managed_job_dir(job_id):
                output.unlink(missing_ok=True)
            if isinstance(exc, FileNotFoundError):
                message = "source file not found"
            elif isinstance(exc, PermissionError):
                message = "source file is not readable"
            elif isinstance(exc, UnicodeError):
                message = "source file is not valid UTF-8"
            elif isinstance(exc, ValueError):
                message = str(exc).split(": ", 1)[0][:300]
            else:
                message = "generation failed; see server log"
            self.repository.finish_job(job_id, "failed", count, message)
        finally:
            if self._is_managed_job_dir(job_id):
                part.unlink(missing_ok=True)
