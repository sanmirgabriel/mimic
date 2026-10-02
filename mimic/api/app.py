"""Local FastAPI adapter over persistence and the one-shot generation service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from mimic import __version__
from mimic.api.schemas import (
    EngagementInput, EngagementPatch, JobInput, OrganizationInput,
    OrganizationPatch, TargetInput, TargetPatch,
)
from mimic.application import ApplicationError, GenerationRequest
from mimic.jobs import JobManager
from mimic.persistence import DataPaths, Database, Repository
from mimic.persistence.repository import StorageConflict


def _payload(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True, mode="json")
    return json.loads(model.json(exclude_unset=True))


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, StorageConflict):
        return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


def _required(record: dict | None) -> dict:
    if record is None:
        raise HTTPException(404, "resource not found")
    return record


def _deleted(found: bool) -> dict:
    if not found:
        raise HTTPException(404, "resource not found")
    return {"deleted": True}


def _name(name: str | None) -> str:
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(422, "name must be a non-empty string")
    return name.strip()


def create_app(data_dir: str | Path | None = None, database_path: str | Path | None = None,
               repository: Repository | None = None,
               manager: JobManager | None = None) -> FastAPI:
    """Create a testable local app without import-time DB or worker side effects."""
    if manager is not None:
        if repository is not None and repository is not manager.repository:
            raise ValueError("manager and repository must use the same repository")
        repository = manager.repository
    if repository is not None and database_path is not None:
        raise ValueError("database_path cannot override an injected repository")
    paths = (manager.paths if manager is not None else
             repository.database.paths if repository is not None and data_dir is None else
             DataPaths(data_dir))
    if data_dir is not None and paths.root != DataPaths(data_dir).root:
        raise ValueError("data_dir must match the injected manager")
    repo = repository or Repository(Database(paths, database_path))
    jobs = manager or JobManager(repo, paths)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        jobs.start()
        try:
            yield
        finally:
            jobs.stop()

    app = FastAPI(title="MIMIC Local API", version=__version__, lifespan=lifespan)
    app.state.repository = repo
    app.state.job_manager = jobs

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/engagements")
    def list_engagements():
        return repo.list_engagements()

    @app.post("/api/engagements", status_code=201)
    def create_engagement(body: EngagementInput):
        return repo.create_engagement(_name(body.name), body.description)

    @app.get("/api/engagements/{item_id}")
    def get_engagement(item_id: UUID):
        item_id = str(item_id)
        return _required(repo.get_engagement(item_id))

    @app.patch("/api/engagements/{item_id}")
    def patch_engagement(item_id: UUID, body: EngagementPatch):
        item_id = str(item_id)
        changes = _payload(body)
        if "name" in changes:
            changes["name"] = _name(changes["name"])
        return _required(repo.update_engagement(item_id, changes))

    @app.delete("/api/engagements/{item_id}")
    def delete_engagement(item_id: UUID):
        item_id = str(item_id)
        try:
            return _deleted(repo.delete_engagement(item_id))
        except StorageConflict as exc:
            raise _translate(exc) from exc

    @app.get("/api/organizations")
    def list_organizations():
        return repo.list_organizations()

    @app.post("/api/organizations", status_code=201)
    def create_organization(body: OrganizationInput):
        data = _payload(body)
        data["name"] = _name(body.name)
        try:
            return repo.create_organization(data)
        except StorageConflict as exc:
            raise _translate(exc) from exc

    @app.get("/api/organizations/{item_id}")
    def get_organization(item_id: UUID):
        item_id = str(item_id)
        return _required(repo.get_organization(item_id))

    @app.patch("/api/organizations/{item_id}")
    def patch_organization(item_id: UUID, body: OrganizationPatch):
        item_id = str(item_id)
        changes = _payload(body)
        if "name" in changes:
            changes["name"] = _name(changes["name"])
        for key in ("aliases", "locations", "keywords", "relevant_dates", "domains"):
            if key in changes and changes[key] is None:
                raise HTTPException(422, f"{key} must be a list")
        try:
            return _required(repo.update_organization(item_id, changes))
        except StorageConflict as exc:
            raise _translate(exc) from exc

    @app.delete("/api/organizations/{item_id}")
    def delete_organization(item_id: UUID):
        item_id = str(item_id)
        try:
            return _deleted(repo.delete_organization(item_id))
        except StorageConflict as exc:
            raise _translate(exc) from exc

    @app.get("/api/targets")
    def list_targets():
        return repo.list_targets()

    @app.post("/api/targets", status_code=201)
    def create_target(body: TargetInput):
        data = _payload(body)
        data["name"] = _name(body.name)
        try:
            return repo.create_target(data)
        except (StorageConflict, ValueError, TypeError) as exc:
            raise _translate(exc) from exc

    @app.get("/api/targets/{item_id}")
    def get_target(item_id: UUID):
        item_id = str(item_id)
        return _required(repo.get_target(item_id))

    @app.patch("/api/targets/{item_id}")
    def patch_target(item_id: UUID, body: TargetPatch):
        item_id = str(item_id)
        changes = _payload(body)
        if "name" in changes:
            changes["name"] = _name(changes["name"])
        if "profile" in changes and changes["profile"] is None:
            raise HTTPException(422, "profile must be an object")
        try:
            return _required(repo.update_target(item_id, changes))
        except (StorageConflict, ValueError, TypeError) as exc:
            raise _translate(exc) from exc

    @app.delete("/api/targets/{item_id}")
    def delete_target(item_id: UUID):
        item_id = str(item_id)
        try:
            return _deleted(repo.delete_target(item_id))
        except StorageConflict as exc:
            raise _translate(exc) from exc

    @app.get("/api/jobs")
    def list_jobs():
        return repo.list_jobs()

    @app.post("/api/jobs", status_code=201)
    def create_job(body: JobInput):
        try:
            request = GenerationRequest.from_dict(body.request)
            return jobs.submit(request, str(body.target_id) if body.target_id else None,
                               str(body.engagement_id) if body.engagement_id else None)
        except (ApplicationError, ValueError, TypeError, AttributeError,
                StorageConflict, LookupError) as exc:
            raise _translate(exc) from exc

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: UUID):
        job_id = str(job_id)
        return _required(repo.get_job(job_id))

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: UUID):
        job_id = str(job_id)
        return _required(jobs.cancel(job_id))

    @app.get("/api/jobs/{job_id}/candidates")
    def candidates(job_id: UUID, limit: int = Query(200, ge=1, le=200),
                   offset: int = Query(0, ge=0)):
        job_id = str(job_id)
        _required(repo.get_job(job_id))
        return repo.list_preview(job_id, limit, offset)

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: UUID):
        job_id = str(job_id)
        try:
            output = jobs.completed_output(job_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return FileResponse(output, media_type="text/plain; charset=utf-8",
                            filename=f"mimic-{job_id}.txt")

    return app
