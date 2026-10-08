"""SSR forms translate input; API and application retain business behavior."""

from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from mimic import __version__
from mimic.application import (
    ApplicationError, GenerationLimits, GenerationRequest, GenerationService,
    MutationOptions, PolicyOptions, SourceOptions,
    IntelligenceOptions,
    RankingOptions,
)
from mimic.intelligence.builtins import SERVICE_PROFILES
from mimic.ranking import BUDGET_PRESETS
from mimic.domain.context import KeyValueContextExtractor
from mimic.domain.models import Organization, Target
from mimic.profile.schema import TargetProfile
from mimic.persistence.repository import StorageConflict
from mimic.web.uploads import UploadStore
from mimic.web.security import BrowserHeaders, secure_headers

logger = logging.getLogger(__name__)

COLLECTIONS = {"engagements": "Engagement", "organizations": "Organization", "targets": "Target"}
PROFILE_FIELDS = {"nome": "Profile name", "data_nascimento": "Birth date", "time_futebol": "Football team",
                  "empresa": "Company", "pet": "Pet"}
LIST_FIELDS = {"aliases": "Aliases", "locations": "Locations", "keywords": "Keywords",
               "relevant_dates": "Relevant dates", "domains": "Domains"}
ORIGIN_FIELDS = {"nome": "Name", "name": "Name", "pet": "Pet", "empresa": "Company",
                 "apelidos": "Nickname", "data_nascimento": "Birth date", "time_futebol": "Football team",
                 "keyword": "Organization keyword", "alias": "Alias", "location": "Location",
                 "domain": "Domain", "relevant_date": "Relevant date"}
STEPS = {"knowledge_template": "Knowledge template", "organization_domain_label": "Organization domain label",
         "case": "Case", "leet": "Leet substitution", "date": "Date token", "affix": "Affix",
         "combine": "Combine", "reverse": "Reverse"}


class WebError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message


def _lines(value: str) -> list[str]:
    return [line for line in value.splitlines() if line.strip()]


def _selected_id(values: dict, field: str) -> str | None:
    value = values.get(field)
    if not value:
        return None
    try:
        return str(UUID(value))
    except ValueError as exc:
        label = field.removesuffix("_id").replace("_", " ").capitalize()
        raise ValueError(f"{label} reference is invalid. Choose a saved record.") from exc


def _message(status: int, detail) -> str:
    if status == 409:
        return "This record has linked resources or job history. Remove its links before deleting it."
    if status == 404:
        return "This record could not be found. It may have been deleted."
    if isinstance(detail, list):
        return "; ".join(f"{item.get('loc', ['Input'])[-1]}: {item.get('msg', 'Invalid value')}" for item in detail)
    return str(detail)


async def _call(operation, *args):
    # Both adapters share record operations and the existing repository/manager.
    try:
        return await run_in_threadpool(operation, *args)
    except StorageConflict as exc:
        raise WebError(409, _message(409, str(exc))) from exc
    except LookupError as exc:
        raise WebError(404, _message(404, str(exc))) from exc
    except (ValueError, TypeError, ApplicationError) as exc:
        raise WebError(422, str(exc)) from exc


def _required(record):
    if record is None:
        raise WebError(404, _message(404, "resource not found"))
    return record


def origin_label(origin: dict) -> str:
    source = origin["source"]
    if source == "dataset":
        return "External dataset"
    if source == "ready_candidate":
        return "Ready candidate"
    field = origin["field"].rsplit(":", 1)[-1]
    label = ORIGIN_FIELDS.get(field, field.replace("_", " ").capitalize())
    return ("Password Intelligence · " if source == "knowledge" else
            "Context · " if source == "context_file" else "") + label


def mount_web(app: FastAPI) -> None:
    app.add_middleware(BrowserHeaders)
    assets = Path(__file__).parent
    templates = Jinja2Templates(directory=str(assets / "templates"))
    templates.env.globals.update(version=__version__, collections=COLLECTIONS, profile_fields=PROFILE_FIELDS,
                                 list_fields=LIST_FIELDS, origin_label=origin_label, step_labels=STEPS,
                                 service_profiles=SERVICE_PROFILES, budget_presets=BUDGET_PRESETS)
    app.mount("/static", StaticFiles(directory=str(assets / "static")), name="static")
    records = app.state.records
    repo = app.state.repository
    manager = app.state.job_manager
    csrf_token = secrets.token_urlsafe(32)
    uploads = UploadStore(app.state.job_manager.paths.root)
    app.state.web_uploads = uploads

    def render(request: Request, template: str, *, status: int = 200, **context):
        response = templates.TemplateResponse(request=request, name=template,
                                              context={"csrf_token": csrf_token, **context}, status_code=status)
        secure_headers(response.headers, request.url.path)
        return response

    async def read_form(request: Request):
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError as exc:
            raise WebError(400, "Invalid request size. Reload the form and try again.") from exc
        if content_length > 50 * 1024 * 1024:
            raise WebError(413, "The upload is too large. Each source file is limited to 16 MiB.")
        form = await request.form(max_files=3, max_fields=80)
        if not secrets.compare_digest(str(form.get("csrf_token", "")).encode("utf-8"), csrf_token.encode("ascii")):
            await form.close()
            raise WebError(403, "This form has expired. Reload the page and try again.")
        return form

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("Unexpected local request failure", exc_info=exc)
        if request.url.path.startswith("/api/"):
            response = PlainTextResponse("Internal Server Error", status_code=500)
            secure_headers(response.headers, request.url.path)
            return response
        return render(request, "error.html", status=500, title="Request could not be completed",
                      error="An unexpected error occurred. Reload the page and try again.", error_status=500)

    @app.exception_handler(WebError)
    async def web_error(request: Request, exc: WebError):
        return render(request, "error.html", status=exc.status, title="Request could not be completed",
                      error=exc.message, error_status=exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/"):
            return await http_exception_handler(request, exc)
        return render(request, "error.html", status=exc.status_code, title="Page unavailable",
                      error=_message(exc.status_code, exc.detail), error_status=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/"):
            return await request_validation_exception_handler(request, exc)
        return render(request, "error.html", status=422, title="Invalid request",
                      error="Check the address and form values, then try again.", error_status=422)

    async def choices(request: Request):
        engagements, organizations, targets = await asyncio.gather(
            *(_call(records.list, name) for name in COLLECTIONS)
        )
        return {"engagements": engagements, "organizations": organizations, "targets": targets}

    @app.get("/", include_in_schema=False)
    async def dashboard(request: Request):
        data = await choices(request)
        data["jobs"] = await _call(repo.list_jobs)
        return render(request, "dashboard.html", title="Dashboard", nav="dashboard", **data)

    async def generation_page(request: Request, values=None, *, error=None, summary=None, warnings=(), status=200):
        defaults = {"mode": "quick", "leet_mode": "partial", "separators": "@!#_.", "min_len": "0",
                    "max_len": "0", "output_priority": "exhaustive", "max_candidates_per_word": "5000", "max_dataset_lines": "100000"}
        if values is None or "intelligence_form" not in values:
            defaults.update({key: "on" for key in ("intelligence_enabled", "common_numbers", "recent_years", "corporate_roles")})
        return render(request, "generate.html", status=status, title="New generation", nav="generate",
                      values={**defaults, **(values or {})}, error=error, summary=summary,
                      warnings=warnings, **await choices(request))

    @app.get("/generate", include_in_schema=False)
    async def generation_form(request: Request, target_id: UUID | None = None, organization_id: UUID | None = None):
        values = {"mode": "saved", "target_id": str(target_id)} if target_id else {}
        if organization_id:
            values.update(mode="organization", organization_id=str(organization_id))
        return await generation_page(request, values)

    async def generation_input(request: Request, form, values: dict) -> tuple[GenerationRequest, str | None]:
        selected_target = _selected_id(values, "target_id") if values.get("mode") == "saved" else None
        organization_id = _selected_id(values, "organization_id")
        engagement_id = _selected_id(values, "engagement_id")
        values["engagement_id"] = engagement_id or ""
        source_paths = {}
        for role in ("dataset", "ready", "context"):
            upload = form.get(role + "_file")
            if isinstance(upload, UploadFile) and upload.filename:
                upload_id = await uploads.save(upload, role)
                values[role + "_upload_id"] = upload_id
                values[role + "_label"] = upload.filename
            upload_id = values.get(role + "_upload_id", "")
            if upload_id:
                source_paths[role] = uploads.existing(upload_id, role)

        mode = values.get("mode", "quick")
        target_id = None
        if mode == "saved":
            target_id = selected_target
            if not target_id:
                raise ValueError("Choose a saved target.")
            # Existing domain adapter owns the target/organization relationship.
            target = await _call(repo.target_domain, target_id)
            if target is None:
                raise WebError(404, "This target is no longer available.")
        elif mode == "quick":
            profile = TargetProfile.from_dict({**{field: values.get(field) or None for field in PROFILE_FIELDS},
                                               "apelidos": _lines(values.get("apelidos", ""))})
            target = Target(values.get("nome", ""), profile) if any(
                getattr(profile, field) for field in (*PROFILE_FIELDS, "apelidos")) else None
        elif mode == "organization":
            if not organization_id:
                raise ValueError("Choose a saved organization.")
            target = None
        else:
            raise ValueError("Choose Quick generation, Saved target or Organization only.")
        organization = None
        if organization_id:
            data = await _call(records.get, "organizations", organization_id)
            organization = Organization(**{key: data[key] for key in ("id", "name", *LIST_FIELDS)})
        if engagement_id:
            await _call(records.get, "engagements", engagement_id)
        context = values.get("context_text", "")
        if len(context.encode("utf-8")) > 64 * 1024:
            raise ValueError("Pasted context is limited to 64 KiB.")
        facts = KeyValueContextExtractor().extract(context, "web.pasted") if context else []
        try:
            policy = PolicyOptions(min_len=int(values.get("min_len", "0")), max_len=int(values.get("max_len", "0")),
                                   **{key: values.get(key) == "on" for key in
                                      ("require_upper", "require_lower", "require_digit", "require_special")})
            limits = GenerationLimits(int(values.get("max_candidates_per_word", "5000")),
                                      int(values.get("max_dataset_lines", "100000")))
        except ValueError as exc:
            raise ValueError("Policy lengths and limits must be whole numbers.") from exc
        try:
            year = int(values["reference_year"]) if values.get("reference_year") else None
        except ValueError as exc:
            raise ValueError("Reference year must be a whole number.") from exc
        # HTML checkbox absence means off. Older form consumers retain defaults.
        configured = values.get("intelligence_form") == "1"
        intelligence = IntelligenceOptions(
            **{key: values.get(form_key) == "on" if configured else True for key, form_key in
               (("enabled", "intelligence_enabled"), ("common_numbers", "common_numbers"),
                ("recent_years", "recent_years"), ("corporate_roles", "corporate_roles"))},
            service_profiles=tuple(form.getlist("service_profiles")), reference_year=year,
        )
        values["selected_services"] = list(intelligence.service_profiles)
        priority = values.get("output_priority", "exhaustive")
        if priority not in (*BUDGET_PRESETS, "custom"):
            raise ValueError("Choose a valid output priority.")
        try:
            ranking = (RankingOptions(True, int(values.get("custom_budget", "")))
                       if priority == "custom" else RankingOptions.from_budget(priority))
        except (ValueError, TypeError) as exc:
            raise ValueError("Custom output budget must be a positive whole number.") from exc
        result = GenerationRequest(ranking=ranking, target=target, organization=organization, context_facts=tuple(facts),
                                   intelligence=intelligence,
                                   context_path=source_paths.get("context"),
                                   mutations=MutationOptions(values.get("leet_mode", "partial"),
                                                             values.get("combine") == "on", values.get("separators", "@!#_.")),
                                   policy=policy, limits=limits,
                                   sources=SourceOptions(dataset_paths=(source_paths["dataset"],) if "dataset" in source_paths else (),
                                                         ready_candidate_paths=(source_paths["ready"],) if "ready" in source_paths else (),
                                                         include_ptbr=values.get("include_ptbr") == "on"))
        result.validate()
        values["reference_year"] = str(result.intelligence.reference_year or "")
        return result, target_id

    @app.post("/generate", include_in_schema=False)
    async def generate(request: Request):
        form = await read_form(request)
        values = {key: value for key, value in form.items() if isinstance(value, str)}
        values["selected_services"] = list(form.getlist("service_profiles"))
        try:
            generation, target_id = await generation_input(request, form, values)
            prepared = await run_in_threadpool(GenerationService().prepare, generation)
            summary = prepared.summary().to_dict()
            if not (summary["target_seed_count"] or summary["organization_seed_count"] or summary["context_fact_count"]
                    or summary["ptbr_enabled"] or summary["dataset_source_count"] or summary["ready_candidate_source_count"]
                    or (generation.intelligence.service_profiles and summary["knowledge_seed_count"])):
                raise ValueError("Add a name, saved target, context or source file to generate candidates.")
            if values.get("intent") == "preview":
                return await generation_page(request, values, summary=summary, warnings=prepared.warnings)
            job = await _call(manager.submit, generation, target_id, values.get("engagement_id") or None)
            return RedirectResponse(f"/jobs/{job['id']}", status_code=303)
        except (ValueError, TypeError, ApplicationError, WebError) as exc:
            status = exc.status if isinstance(exc, WebError) else 422
            error = exc.message if isinstance(exc, WebError) else str(exc)
            if isinstance(exc, UnicodeError) or isinstance(exc.__cause__, UnicodeError):
                error = "The source file must contain valid UTF-8 text."
            return await generation_page(request, values, error=error, status=status)
        except OSError:
            return await generation_page(request, values, error="The source file could not be stored or read. Please upload it again.", status=422)
        finally:
            await form.close()

    @app.get("/jobs", include_in_schema=False)
    async def job_list(request: Request):
        return render(request, "jobs.html", title="Jobs", nav="jobs", jobs=await _call(repo.list_jobs))

    async def job_data(request: Request, job_id: UUID):
        job = _required(await _call(repo.get_job, str(job_id)))
        preview = await _call(repo.list_preview, str(job_id), 200)
        return job, preview

    @app.get("/jobs/{job_id}/status", include_in_schema=False)
    async def job_status(request: Request, job_id: UUID):
        job, preview = await job_data(request, job_id)
        return render(request, "job_status.html", job=job, preview=preview)

    @app.get("/jobs/{job_id}", include_in_schema=False)
    async def job_detail(request: Request, job_id: UUID):
        job, preview = await job_data(request, job_id)
        summary, warnings = None, ()
        try:
            generation = GenerationRequest.from_dict(job["request"])
            prepared = await run_in_threadpool(GenerationService().prepare, generation)
            summary, warnings = prepared.summary().to_dict(), prepared.warnings
            # Historical job scores use their persisted model, even after a future upgrade.
            if summary["ranking"]["enabled"]:
                stored_version = next((item["score_version"] for item in preview if item["score_version"]), None)
                if stored_version is not None:
                    summary["score_version"] = stored_version
        except (ApplicationError, ValueError, TypeError, OSError):
            warnings = ("Configuration summary is unavailable; the original request remains saved.",)
        return render(request, "job.html", title="Generation detail", nav="jobs", job=job,
                      preview=preview, summary=summary, warnings=warnings)

    @app.post("/jobs/{job_id}/cancel", include_in_schema=False)
    async def cancel_job(request: Request, job_id: UUID):
        form = await read_form(request)
        try:
            _required(await _call(manager.cancel, str(job_id)))
        finally:
            await form.close()
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    def collection_name(collection: str) -> str:
        if collection not in COLLECTIONS:
            raise WebError(404, "This page could not be found.")
        return COLLECTIONS[collection]

    async def collection_page(request: Request, collection: str, values=None, item_id=None, error=None, status=200):
        label = collection_name(collection)
        data = await choices(request)
        return render(request, "collection.html", status=status, title=label + (" detail" if item_id else "s"),
                      nav=collection, collection=collection, label=label, values=values or {}, item_id=item_id,
                      records=data[collection], error=error, **data)

    @app.get("/{collection}", include_in_schema=False)
    async def collection_list(request: Request, collection: str):
        return await collection_page(request, collection)

    @app.get("/{collection}/new", include_in_schema=False)
    async def collection_new(request: Request, collection: str):
        return await collection_page(request, collection)

    @app.get("/{collection}/{item_id}", include_in_schema=False)
    async def collection_detail(request: Request, collection: str, item_id: UUID):
        collection_name(collection)
        record = await _call(records.get, collection, str(item_id))
        values = {**record, **record.get("profile", {})}
        for field in (*LIST_FIELDS, "apelidos"):
            if field in values:
                values[field] = "\n".join(values[field])
        return await collection_page(request, collection, values, str(item_id))

    async def save_record(request: Request, collection: str, item_id: str | None = None):
        collection_name(collection)
        form = await read_form(request)
        values = {key: value for key, value in form.items() if isinstance(value, str)}
        try:
            present = lambda field: not item_id or field in values
            payload = {"name": values.get("name", "")} if present("name") else {}
            if collection == "engagements":
                if present("description"):
                    payload["description"] = values.get("description") or None
            elif collection == "organizations":
                payload.update({field: _lines(values.get(field, "")) for field in LIST_FIELDS if present(field)})
            else:
                fields = (*PROFILE_FIELDS, "apelidos")
                if any(present(field) for field in fields):
                    # HTML partial edits retain omitted fields in the API's profile snapshot.
                    profile = (await _call(records.get, collection, item_id))["profile"] if item_id else {}
                    profile.update({field: values.get(field) or None for field in PROFILE_FIELDS if present(field)})
                    if present("apelidos"):
                        profile["apelidos"] = _lines(values.get("apelidos", ""))
                    payload["profile"] = profile
                if present("organization_id"):
                    payload["organization_id"] = _selected_id(values, "organization_id")
            if collection != "engagements" and present("engagement_id"):
                payload["engagement_id"] = _selected_id(values, "engagement_id")
            record = (await _call(records.update, collection, item_id, payload) if item_id
                      else await _call(records.create, collection, payload))
            return RedirectResponse(f"/{collection}/{record['id']}", status_code=303)
        except (WebError, ValueError) as exc:
            error = exc.message if isinstance(exc, WebError) else str(exc)
            status = exc.status if isinstance(exc, WebError) else 422
            return await collection_page(request, collection, values, item_id, error, status)
        finally:
            await form.close()

    @app.post("/{collection}/new", include_in_schema=False)
    async def collection_create(request: Request, collection: str):
        return await save_record(request, collection)

    @app.post("/{collection}/{item_id}", include_in_schema=False)
    async def collection_update(request: Request, collection: str, item_id: UUID):
        return await save_record(request, collection, str(item_id))

    @app.post("/{collection}/{item_id}/delete", include_in_schema=False)
    async def collection_delete(request: Request, collection: str, item_id: UUID):
        collection_name(collection)
        form = await read_form(request)
        try:
            await _call(records.delete, collection, str(item_id))
        except WebError as exc:
            return await collection_page(request, collection, error=exc.message, status=exc.status)
        finally:
            await form.close()
        return RedirectResponse(f"/{collection}", status_code=303)
