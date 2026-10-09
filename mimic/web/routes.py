"""SSR forms translate input; API and application retain business behavior."""

from __future__ import annotations

import asyncio
import logging
import secrets
from functools import partial
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Query, Request
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
from mimic.intelligence import catalog
from mimic.ranking import BUDGET_PRESETS
from mimic.packs import PackError, PackRegistry
from mimic.domain.context import KeyValueContextExtractor
from mimic.domain.models import Organization, Target
from mimic.profile.schema import TargetProfile
from mimic.persistence.repository import StorageConflict
from mimic.web.uploads import UploadStore, MAX_UPLOAD_BYTES
from mimic.web.security import BrowserHeaders, secure_headers
from mimic.web.i18n import (LOCALES, LOCALE_COOKIE, TRANSLATIONS, Message, WebInputError,
                            plural, resolve_locale, safe_return_to, translate)

logger = logging.getLogger(__name__)

COLLECTIONS = ("engagements", "organizations", "targets")
PROFILE_FIELDS = {"nome": "field.profile_name", "data_nascimento": "field.birth_date", "time_futebol": "field.football",
                  "empresa": "field.company", "pet": "field.pet"}
LIST_FIELDS = {"aliases": "field.aliases", "locations": "field.locations", "keywords": "field.keywords",
               "relevant_dates": "field.dates", "domains": "field.domains"}
ORIGIN_FIELDS = {"nome": "field.name", "name": "field.name", "pet": "field.pet", "empresa": "field.company",
                 "apelidos": "origin.nickname", "data_nascimento": "field.birth_date", "time_futebol": "field.football",
                 "keyword": "origin.keyword", "alias": "origin.alias", "location": "origin.location",
                 "domain": "origin.domain", "relevant_date": "origin.date", "role": "origin.role",
                 "recent_year": "origin.year", "common_number": "origin.number"}


class WebError(Exception):
    def __init__(self, status: int, message: Message) -> None:
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
        raise WebInputError("error.reference", field=field.removesuffix("_id")) from exc


def _message(status: int, detail) -> Message:
    if status == 409:
        return Message("error.linked")
    if status == 404:
        return Message("error.not_found")
    return Message("error.invalid", detail=str(detail))


async def _call(operation, *args):
    # Both adapters share record operations and the existing repository/manager.
    try:
        return await run_in_threadpool(operation, *args)
    except PackError:
        raise
    except StorageConflict as exc:
        raise WebError(409, _message(409, str(exc))) from exc
    except LookupError as exc:
        raise WebError(404, _message(404, str(exc))) from exc
    except (ValueError, TypeError, ApplicationError) as exc:
        raise WebError(422, exc.message if isinstance(exc, WebInputError)
                       else Message("error.invalid", detail=str(exc))) from exc


def _required(record):
    if record is None:
        raise WebError(404, _message(404, "resource not found"))
    return record


def origin_label(locale: str, origin: dict) -> str:
    source = origin["source"]
    if source == "dataset":
        return translate(locale, "origin.dataset")
    if source == "ready_candidate":
        return translate(locale, "origin.ready")
    if source == "knowledge" and origin["field"] == "common_password":
        return translate(locale, "catalog.common_password_origin")
    field = origin["field"].rsplit(":", 1)[-1]
    if source == "knowledge" and field.startswith("service.") and field.endswith((".role", ".token")):
        return translate(locale, "origin.service", service=field.split(".")[1],
                         field=translate(locale, "origin.service_role" if field.endswith(".role") else "origin.token"))
    label = translate(locale, ORIGIN_FIELDS[field]) if field in ORIGIN_FIELDS else translate(
        locale, "origin.unknown", field=field.replace("_", " ").capitalize())
    return translate(locale, "origin.knowledge" if source == "knowledge" else "origin.context", field=label) \
        if source in ("knowledge", "context_file") else label


def score_label(locale: str, component: dict) -> str:
    # Codes are structured. Historical descriptions stay untouched, never parsed.
    code = component["code"]
    parts = code.split(".")
    if len(parts) >= 2 and parts[0] == "origin" and "score." + parts[1] in TRANSLATIONS["en"]:
        return translate(locale, "score." + parts[1])
    if len(parts) >= 2 and parts[0] == "transformation":
        key = "case." + parts[2] if parts[1] == "case" and len(parts) == 3 else "step." + parts[1]
        if key in TRANSLATIONS["en"]:
            return translate(locale, key)
    return translate(locale, "score.unknown")


def mount_web(app: FastAPI) -> None:
    app.add_middleware(BrowserHeaders)
    assets = Path(__file__).parent
    templates = Jinja2Templates(directory=str(assets / "templates"))
    templates.env.globals.update(version=__version__, collections=COLLECTIONS, profile_fields=PROFILE_FIELDS,
                                 list_fields=LIST_FIELDS,
                                 service_profiles=SERVICE_PROFILES, budget_presets=BUDGET_PRESETS)
    app.mount("/static", StaticFiles(directory=str(assets / "static")), name="static")
    records = app.state.records
    repo = app.state.repository
    manager = app.state.job_manager
    packs = PackRegistry(manager.paths)
    generation_service = GenerationService(packs)
    csrf_token = secrets.token_urlsafe(32)
    uploads = UploadStore(app.state.job_manager.paths.root)
    app.state.web_uploads = uploads

    def render(request: Request, template: str, *, status: int = 200, **context):
        locale = resolve_locale(request.cookies.get(LOCALE_COOKIE))
        t = partial(translate, locale)
        error = context.get("error")
        if isinstance(error, Message):
            params = dict(error.params)
            if error.key == "error.reference":
                params["field"] = t({"target": "field.target", "organization": "field.org",
                                     "engagement": "nav.engagements"}.get(params["field"], "field.name"))
            if error.key in ("error.extension", "error.upload_limit"):
                params["role"] = t("source." + params["role"])
            context.update(error=t(error.key, **params), error_detail=error.detail)
        warnings = []
        for warning in context.get("warnings", ()):
            key = next((key for key, text in TRANSLATIONS["en"].items()
                        if key.startswith("warning.") and text == warning), None)
            warnings.append(t(key) if key else warning)
        context["warnings"] = warnings
        if "title_key" in context:
            context["title"] = t(context.pop("title_key"))
        local = {"locale": locale, "t": t, "plural": partial(plural, locale),
                 "job_error": lambda error: t(error) if error and error.startswith('pack.error.') and error in TRANSLATIONS[locale] else error,
                 "origin_label": partial(origin_label, locale), "score_label": partial(score_label, locale),
                 "step_label": lambda kind: t("step." + kind) if "step." + kind in TRANSLATIONS["en"] else kind,
                 "param_label": lambda key: t("param." + key) if "param." + key in TRANSLATIONS["en"] else key,
                 "return_to": request.url.path + ("?" + request.url.query if request.url.query else "")}
        response = templates.TemplateResponse(request=request, name=template,
                                              context={"csrf_token": csrf_token, **context, **local}, status_code=status)
        response.headers["Content-Language"] = locale
        response.headers["Vary"] = "Cookie"
        secure_headers(response.headers, request.url.path)
        return response

    async def read_form(request: Request):
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError as exc:
            raise WebError(400, Message("error.size")) from exc
        if content_length > 50 * 1024 * 1024:
            raise WebError(413, Message("error.too_large"))
        form = await request.form(max_files=3, max_fields=80)
        if not secrets.compare_digest(str(form.get("csrf_token", "")).encode("utf-8"), csrf_token.encode("ascii")):
            await form.close()
            raise WebError(403, Message("error.csrf"))
        return form

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("Unexpected local request failure", exc_info=exc)
        if request.url.path.startswith("/api/"):
            response = PlainTextResponse("Internal Server Error", status_code=500)
            secure_headers(response.headers, request.url.path)
            return response
        return render(request, "error.html", status=500, title_key="error.title",
                      error=Message("error.unexpected"), error_status=500)

    @app.exception_handler(WebError)
    async def web_error(request: Request, exc: WebError):
        return render(request, "error.html", status=exc.status, title_key="error.title",
                      error=exc.message, error_status=exc.status)

    @app.exception_handler(PackError)
    async def pack_error(request: Request, exc: PackError):
        return render(request, 'error.html', status=422, title_key='pack.title',
                      error=Message('pack.error.' + exc.code), error_status=422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/"):
            return await http_exception_handler(request, exc)
        return render(request, "error.html", status=exc.status_code, title_key="error.page_title",
                      error=_message(exc.status_code, exc.detail), error_status=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/"):
            return await request_validation_exception_handler(request, exc)
        return render(request, "error.html", status=422, title_key="error.invalid_title",
                      error=Message("error.address"), error_status=422)

    @app.post("/preferences/locale", include_in_schema=False)
    async def locale_preference(request: Request):
        form = await read_form(request)
        try:
            locale = form.get("locale")
            if locale not in LOCALES:
                raise WebError(422, Message("error.locale"))
            response = RedirectResponse(safe_return_to(form.get("return_to")), status_code=303)
            response.set_cookie(LOCALE_COOKIE, locale, max_age=365 * 24 * 60 * 60,
                                httponly=True, samesite="lax", secure=request.url.scheme == "https", path="/")
            return response
        finally:
            await form.close()

    async def choices(request: Request):
        engagements, organizations, targets = await asyncio.gather(
            *(_call(records.list, name) for name in COLLECTIONS)
        )
        return {"engagements": engagements, "organizations": organizations, "targets": targets}

    async def packs_page(request, *, selected=None, verified=False, values=None, error=None, status=200):
        return render(request, 'packs.html', status=status, title_key='pack.title', nav='packs',
                      packs=await _call(packs.list), selected=selected, verified=verified,
                      values=values or {}, error=error)

    @app.get('/services', include_in_schema=False)
    async def service_catalog(request: Request, q: str = Query('', max_length=200), category: str = 'services'):
        if category not in ('services', 'common'):
            raise WebError(400, Message('error.invalid'))
        return render(request, 'services.html', title_key='catalog.title', nav='services',
                      services=catalog.list_services(q), query=q, category=category,
                      selected_service=None, credentials=(), common=catalog.common_vocabulary())

    @app.get('/services/{service_id}', include_in_schema=False)
    async def service_detail(request: Request, service_id: str):
        try:
            service = catalog.get_service(service_id)
        except ValueError:
            raise WebError(404, Message('error.not_found'))
        profile = next(p for p in SERVICE_PROFILES if p.id == service.id)
        return render(request, 'services.html', title=service.display_name, nav='services',
                      services=catalog.list_services(), query='', category='services',
                      selected_service=service, selected_profile=profile,
                      credentials=catalog.list_credentials(service.id), common=catalog.common_vocabulary())

    @app.get('/packs', include_in_schema=False)
    async def pack_list(request: Request):
        return await packs_page(request)

    @app.get('/packs/{identity}', include_in_schema=False)
    async def pack_detail(request: Request, identity: str):
        return await packs_page(request, selected=await _call(packs.get, identity))

    async def read_pack_form(request):
        origin = request.headers.get('origin')
        site = request.headers.get('sec-fetch-site')
        # Firefox can suppress Origin under no-referrer, while retaining the
        # same-origin Fetch Metadata signal. CSRF remains mandatory below.
        same_origin_null = origin == 'null' and site == 'same-origin'
        if site == 'cross-site' or (origin is not None and origin != str(request.base_url).rstrip('/') and not same_origin_null):
            raise WebError(403, Message('error.csrf'))
        return await read_form(request)

    @app.post('/packs/import', include_in_schema=False)
    async def pack_import(request: Request):
        form = await read_pack_form(request)
        values = {k: v for k, v in form.items() if isinstance(v, str)}
        try:
            upload = form.get('pack_file')
            if not isinstance(upload, UploadFile) or not upload.filename:
                raise PackError('file', 'Select a local text file')
            metadata = await run_in_threadpool(packs.import_stream, upload.file,
                id=values.get('id'), version=values.get('version'), kind=values.get('kind'),
                filename=upload.filename, name=values.get('name') or None,
                description=values.get('description', ''), language=values.get('language') or 'und',
                license=values.get('license') or 'NOASSERTION', source_url=values.get('source_url') or None,
                attribution=values.get('attribution') or translate(resolve_locale(request.cookies.get(LOCALE_COOKIE)), 'pack.local_attribution'),
                max_bytes=MAX_UPLOAD_BYTES)
            return RedirectResponse('/packs/' + metadata.identity, status_code=303)
        except PackError as exc:
            return await packs_page(request, values=values, error=Message('pack.error.' + exc.code), status=422)
        except OSError:
            return await packs_page(request, values=values, error=Message('error.source_io'), status=422)
        finally:
            await form.close()

    @app.post('/packs/{identity}/verify', include_in_schema=False)
    async def pack_verify(request: Request, identity: str):
        form = await read_pack_form(request)
        try:
            metadata = await _call(packs.verify, identity)
            return await packs_page(request, selected=metadata, verified=True)
        finally:
            await form.close()

    @app.get("/", include_in_schema=False)
    async def dashboard(request: Request):
        data = await choices(request)
        data["jobs"] = await _call(repo.list_jobs)
        return render(request, "dashboard.html", title_key="nav.dashboard", nav="dashboard", **data)

    async def generation_page(request: Request, values=None, *, error=None, summary=None, warnings=(), status=200):
        defaults = {"mode": "quick", "leet_mode": "partial", "separators": "@!#_.", "min_len": "0",
                    "max_len": "0", "output_priority": "exhaustive", "max_candidates_per_word": "5000", "max_dataset_lines": "100000"}
        if values is None or "intelligence_form" not in values:
            defaults.update({key: "on" for key in ("intelligence_enabled", "common_numbers", "recent_years", "corporate_roles")})
        return render(request, "generate.html", status=status, title_key="generation.new", nav="generate",
                      values={**defaults, **(values or {})}, error=error, summary=summary,
                      warnings=warnings, packs=await _call(packs.list), **await choices(request))

    @app.get("/generate", include_in_schema=False)
    async def generation_form(request: Request, target_id: UUID | None = None, organization_id: UUID | None = None,
                              service: str | None = None):
        values = {"mode": "saved", "target_id": str(target_id)} if target_id else {}
        if organization_id:
            values.update(mode="organization", organization_id=str(organization_id))
        if service is not None:
            try:
                catalog.get_service(service)
            except ValueError:
                raise WebError(400, Message('error.service', {'service': service}))
            values['selected_services'] = [service]
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
                raise WebInputError("error.target")
            # Existing domain adapter owns the target/organization relationship.
            target = await _call(repo.target_domain, target_id)
            if target is None:
                raise WebError(404, Message("error.target_gone"))
        elif mode == "quick":
            profile = TargetProfile.from_dict({**{field: values.get(field) or None for field in PROFILE_FIELDS},
                                               "apelidos": _lines(values.get("apelidos", ""))})
            target = Target(values.get("nome", ""), profile) if any(
                getattr(profile, field) for field in (*PROFILE_FIELDS, "apelidos")) else None
        elif mode == "organization":
            if not organization_id:
                raise WebInputError("error.organization")
            target = None
        else:
            raise WebInputError("error.mode")
        organization = None
        if organization_id:
            data = await _call(records.get, "organizations", organization_id)
            organization = Organization(**{key: data[key] for key in ("id", "name", *LIST_FIELDS)})
        if engagement_id:
            await _call(records.get, "engagements", engagement_id)
        context = values.get("context_text", "")
        if len(context.encode("utf-8")) > 64 * 1024:
            raise WebInputError("error.context_size")
        facts = KeyValueContextExtractor().extract(context, "web.pasted") if context else []
        try:
            policy = PolicyOptions(min_len=int(values.get("min_len", "0")), max_len=int(values.get("max_len", "0")),
                                   **{key: values.get(key) == "on" for key in
                                      ("require_upper", "require_lower", "require_digit", "require_special")})
            limits = GenerationLimits(int(values.get("max_candidates_per_word", "5000")),
                                      int(values.get("max_dataset_lines", "100000")))
        except ValueError as exc:
            raise WebInputError("error.integers") from exc
        try:
            year = int(values["reference_year"]) if values.get("reference_year") else None
        except ValueError as exc:
            raise WebInputError("error.year") from exc
        if year is not None and not 4 <= year <= 9999:
            raise WebInputError("error.year_range")
        # HTML checkbox absence means off. Older form consumers retain defaults.
        configured = values.get("intelligence_form") == "1"
        intelligence = IntelligenceOptions(
            **{key: values.get(form_key) == "on" if configured else True for key, form_key in
               (("enabled", "intelligence_enabled"), ("common_numbers", "common_numbers"),
                ("recent_years", "recent_years"), ("corporate_roles", "corporate_roles"))},
            service_profiles=tuple(form.getlist("service_profiles")), reference_year=year,
        )
        values["selected_services"] = list(intelligence.service_profiles)
        for service in intelligence.service_profiles:
            if service not in {profile.id for profile in SERVICE_PROFILES}:
                raise WebInputError("error.service", service=service)
        priority = values.get("output_priority", "exhaustive")
        if priority not in (*BUDGET_PRESETS, "custom"):
            raise WebInputError("error.priority")
        try:
            ranking = (RankingOptions(True, int(values.get("custom_budget", "")))
                       if priority == "custom" else RankingOptions.from_budget(priority))
        except (ValueError, TypeError) as exc:
            raise WebInputError("error.budget") from exc
        result = GenerationRequest(ranking=ranking, target=target, organization=organization, context_facts=tuple(facts),
                                   intelligence=intelligence,
                                   context_path=source_paths.get("context"),
                                   mutations=MutationOptions(values.get("leet_mode", "partial"),
                                                             values.get("combine") == "on", values.get("separators", "@!#_.")),
                                   policy=policy, limits=limits,
                                   sources=SourceOptions(dataset_paths=(source_paths["dataset"],) if "dataset" in source_paths else (),
                                                         ready_candidate_paths=(source_paths["ready"],) if "ready" in source_paths else (),
                                                         include_common_passwords=values.get('include_common_passwords') == 'on',
                                                         include_ptbr=values.get("include_ptbr") == "on"))
        selected_packs = form.getlist('packs')
        if len(selected_packs) > 64:
            raise PackError('snapshot', 'Too many selected packs')
        from dataclasses import replace
        result.sources = replace(result.sources, packs=tuple([await _call(packs.reference, identity) for identity in selected_packs]))
        result.validate()
        values["reference_year"] = str(result.intelligence.reference_year or "")
        return result, target_id

    @app.post("/generate", include_in_schema=False)
    async def generate(request: Request):
        form = await read_form(request)
        values = {key: value for key, value in form.items() if isinstance(value, str)}
        values["selected_services"] = list(form.getlist("service_profiles"))
        values['selected_packs'] = list(form.getlist('packs'))
        try:
            generation, target_id = await generation_input(request, form, values)
            prepared = await run_in_threadpool(generation_service.prepare, generation)
            summary = prepared.summary().to_dict()
            if not (summary["target_seed_count"] or summary["organization_seed_count"] or summary["context_fact_count"]
                    or summary["ptbr_enabled"] or summary["dataset_source_count"] or summary["ready_candidate_source_count"]
                    or summary.get('common_password_count')
                    or (generation.intelligence.service_profiles and summary["knowledge_seed_count"])):
                raise WebInputError("error.inputs")
            if values.get("intent") == "preview":
                return await generation_page(request, values, summary=summary, warnings=prepared.warnings)
            job = await _call(manager.submit, generation, target_id, values.get("engagement_id") or None)
            return RedirectResponse(f"/jobs/{job['id']}", status_code=303)
        except (ValueError, TypeError, ApplicationError, WebError) as exc:
            status = exc.status if isinstance(exc, WebError) else 422
            error = (Message('pack.error.' + exc.code) if isinstance(exc, PackError) else
                     exc.message if isinstance(exc, (WebError, WebInputError)) else Message("error.invalid", detail=str(exc)))
            if isinstance(exc, UnicodeError) or isinstance(exc.__cause__, UnicodeError):
                error = Message("error.utf8")
            return await generation_page(request, values, error=error, status=status)
        except OSError:
            return await generation_page(request, values, error=Message("error.source_io"), status=422)
        finally:
            await form.close()

    @app.get("/jobs", include_in_schema=False)
    async def job_list(request: Request):
        return render(request, "jobs.html", title_key="nav.jobs", nav="jobs", jobs=await _call(repo.list_jobs))

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
            prepared = await run_in_threadpool(generation_service.prepare, generation)
            summary, warnings = prepared.summary().to_dict(), prepared.warnings
            # Historical job scores use their persisted model, even after a future upgrade.
            if summary["ranking"]["enabled"]:
                stored_version = next((item["score_version"] for item in preview if item["score_version"]), None)
                if stored_version is not None:
                    summary["score_version"] = stored_version
        except (ApplicationError, ValueError, TypeError, OSError):
            warnings = ("Configuration summary is unavailable; the original request remains saved.",)
        return render(request, "job.html", title_key="jobs.detail", nav="jobs", job=job,
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
            raise WebError(404, Message("error.page"))
        return collection

    async def collection_page(request: Request, collection: str, values=None, item_id=None, error=None, status=200):
        label = collection_name(collection)
        data = await choices(request)
        return render(request, "collection.html", status=status,
                      title_key=f"collection.{collection}.{'detail' if item_id else 'title'}",
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
            if "name" in payload and not payload["name"].strip():
                raise WebInputError("error.name")
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
            error = exc.message if isinstance(exc, (WebError, WebInputError)) else Message("error.invalid", detail=str(exc))
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
