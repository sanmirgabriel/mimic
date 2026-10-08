"""Independent pre-commit checks for presentation, isolation and compatibility."""
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import html
from html.parser import HTMLParser
from pathlib import Path
import re
from string import Formatter
from uuid import uuid4

from fastapi.testclient import TestClient
from jinja2 import Environment, nodes
import pytest

from mimic.api import create_app
from mimic.application import GenerationRequest, MutationOptions, RankingOptions
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.web import routes
from mimic.web.i18n import LOCALES, MESSAGES, TRANSLATIONS, translate
from tests.test_web_i18n import token


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        yield client


def historical_job(client, hostile="ACMEeditor2026"):
    repo = client.app.state.repository
    request = GenerationRequest(ranking=RankingOptions(True, 1))
    job = repo.create_job(request.to_dict(), None, None)
    repo.start_job(job["id"])
    candidate = Candidate(hostile, (Origin("organization", "name", hostile),
        Origin("context_file", "web:<script>alert(\"x\")</script>", hostile)),
        (Transformation("case", (("mode", "original"),)),))
    repo.add_preview(job["id"], [{"sequence": 1, "rank": 1, "value": candidate.value,
        "origins": [asdict(o) for o in candidate.origins],
        "transformations": [asdict(t) for t in candidate.transformations],
        "score": 22, "score_version": "score-v1", "score_components": [
            {"code": "origin.organization.name", "delta": 22, "description": hostile},
            {"code": "historical.unknown", "delta": 0, "description": hostile}]}])
    path = client.app.state.job_manager.paths.output(job["id"])
    path.parent.mkdir(parents=True)
    path.write_text(candidate.value + "\n")
    repo.complete_job(job["id"], 1, str(path))
    return job["id"]


def test_catalogs_are_read_only_and_have_no_duplicate_literals():
    with pytest.raises(TypeError):
        TRANSLATIONS["en"] = {}
    with pytest.raises(TypeError):
        TRANSLATIONS["en"]["nav.jobs"] = "changed"
    with pytest.raises(TypeError):
        MESSAGES["nav.jobs"] = ("changed", "changed")
    for path in (Path("mimic/web/i18n.py"), Path("mimic/web/routes.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                assert not [key for key, count in Counter(keys).items() if count > 1], (path, node.lineno)


@pytest.mark.parametrize("locale", LOCALES)
def test_translation_defects_have_observable_safe_fallbacks(locale, caplog):
    assert translate(locale, "missing.audit.key") == "missing.audit.key"
    assert "Missing Web translation" in caplog.text
    assert translate(locale, "collection.confirm", wrong="secret-operator-data") == translate(locale, "error.invalid")
    assert translate(locale, "collection.confirm") == translate(locale, "error.invalid")
    assert "Invalid Web translation interpolation" in caplog.text
    assert "secret-operator-data" not in caplog.text
    assert translate("invalid", "nav.dashboard") == translate("pt-BR", "nav.dashboard")


def test_template_literal_text_is_only_deliberate_technical_names():
    # Strip Jinja syntax before parsing HTML, so interpolated attributes do not
    # become false positives and unlocalized text nodes remain observable.
    class Visible(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text = []
        def handle_data(self, text):
            if re.search(r"[A-Za-zÀ-ÿ]{2}", text):
                self.text.append(re.sub(r"[^A-Za-zÀ-ÿ]+", " ", text).strip())
    for path in Path("mimic/web/templates").glob("*.html"):
        parser = Visible()
        parser.feed(re.sub(r"\{[{%#].*?[}%#]\}", "", path.read_text(), flags=re.S))
        assert set(parser.text) <= {"MIMIC", "Password Intelligence", "Leet"}, (path, parser.text)
        for call in Environment().parse(path.read_text()).find_all(nodes.Call):
            if isinstance(call.node, nodes.Name) and call.node.name == "t" and call.args and isinstance(call.args[0], nodes.Const):
                assert call.args[0].value in TRANSLATIONS["en"], (path, call.lineno)


@pytest.mark.parametrize("locale", LOCALES)
def test_runtime_keys_and_interpolations_cover_all_templates(client, monkeypatch, locale, caplog):
    used = set()
    original = routes.translate
    def checked(lang, key, **params):
        assert key in TRANSLATIONS[lang], (lang, key)
        required = {f for _, f, _, _ in Formatter().parse(TRANSLATIONS[lang][key]) if f}
        assert required <= params.keys(), (key, required, params.keys())
        used.add(key)
        return original(lang, key, **params)
    monkeypatch.setattr(routes, "translate", checked)
    monkeypatch.setattr("mimic.web.i18n.translate", checked)
    client.cookies.set("mimic_locale", locale)
    engagement = client.post("/api/engagements", json={"name": "Projeto"}).json()
    organization = client.post("/api/organizations", json={"name": "ACME", "engagement_id": engagement["id"]}).json()
    target = client.post("/api/targets", json={"name": "Pedro", "organization_id": organization["id"],
        "profile": {"nome": "Pedro", "apelidos": ["PH"], "data_nascimento": "17/08/2002", "pet": "Luna"}}).json()
    job_id = historical_job(client)
    for path in ["/", "/generate", "/jobs", "/missing", "/jobs/" + job_id, "/jobs/" + job_id + "/status"] + [
            f"/{kind}{suffix}" for kind, record in [("engagements", engagement), ("organizations", organization), ("targets", target)]
            for suffix in ("", "/new", "/" + record["id"])]:
        assert client.get(path).status_code in (200, 404)
    for mode in ("quick", "saved", "organization"):
        for priority in ("exhaustive", "quick", "focused", "balanced", "large", "custom"):
            for leet in ("none", "partial", "full"):
                response = client.post("/generate", data={"csrf_token": token(client), "intent": "preview",
                    "mode": mode, "nome": "Pedro", "target_id": target["id"], "organization_id": organization["id"],
                    "output_priority": priority, "custom_budget": "3", "leet_mode": leet, "reference_year": "2026",
                    "combine": "on", "require_upper": "on", "require_lower": "on", "require_digit": "on",
                    "require_special": "on", "include_ptbr": "on", "service_profiles": "wordpress"})
                assert response.status_code == 200
    assert {"nav.jobs", "collection.organizations.all", "collection.orgs.one", "collection.targets.one",
            "score.unknown", "origin.unknown", "ranking.custom", "leet.none", "pipeline.combine", "warning.ptbr"} <= used
    assert "Missing Web translation" not in caplog.text and "Invalid Web translation" not in caplog.text


def test_independent_clients_isolate_four_pages_concurrently(client):
    job_id = historical_job(client)
    clients = {locale: TestClient(client.app, cookies={"mimic_locale": locale}) for locale in LOCALES}
    paths = [("/", "dashboard.heading"), ("/generate", "generation.heading"),
             ("/jobs/" + job_id, "jobs.snapshot"), ("/jobs/" + job_id + "/status", "jobs.live")]
    def fetch(task):
        locale, path, key = task
        response = clients[locale].get(path)
        assert response.status_code == 200
        assert response.headers["Content-Language"] == locale
        assert translate(locale, key) in response.text
        other = "en" if locale == "pt-BR" else "pt-BR"
        assert translate(other, key) not in response.text
        if not path.endswith("/status"):
            assert f'lang="{locale}"' in response.text
            assert translate(locale, "theme.light") in response.text
    try:
        tasks = [(locale, path, key) for _ in range(8) for locale in LOCALES for path, key in paths]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(fetch, tasks))
    finally:
        for independent in clients.values():
            independent.close()


@pytest.mark.parametrize("locale", LOCALES)
def test_hostile_data_is_escaped_in_records_labels_descriptions_and_scores(client, monkeypatch, locale):
    hostile = '<script>alert("x")</script>'
    client.cookies.set("mimic_locale", locale)
    engagement = client.post("/api/engagements", json={"name": hostile, "description": hostile}).json()
    organization = client.post("/api/organizations", json={"name": hostile}).json()
    target = client.post("/api/targets", json={"name": hostile, "profile": {"nome": hostile}}).json()
    job_id = historical_job(client, hostile)
    before = client.app.state.repository.list_preview(job_id)
    monkeypatch.setattr("mimic.application.generation.score_candidate", lambda *_: pytest.fail("render rescored history"))
    for path in ("/", "/generate", "/engagements/" + engagement["id"], "/organizations/" + organization["id"],
                 "/targets/" + target["id"], "/jobs/" + job_id, "/jobs/" + job_id + "/status"):
        page = client.get(path).text
        assert hostile not in page and html.escape(hostile) in page.replace("&#34;", "&quot;")
        assert '<script>' not in page and '<script>alert' not in page
    page = client.get("/jobs/" + job_id).text
    assert translate(locale, "score.unknown") in page
    assert translate(locale, "technical.recorded") in page
    assert before == client.app.state.repository.list_preview(job_id)


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("case,status,key", [
    ("csrf", 403, "error.csrf"), ("organization", 422, "error.reference"),
    ("missing-target", 404, "error.target_gone"), ("year", 422, "error.year"),
    ("budget", 422, "error.budget"), ("service", 422, "error.service"),
    ("upload", 422, "error.extension"), ("size", 413, "error.too_large"),
    ("job", 404, "error.not_found"), ("missing", 404, "error.page"),
    ("http", 405, "error.invalid"),
])
def test_localized_errors_keep_status_codes(client, locale, case, status, key):
    client.cookies.set("mimic_locale", locale)
    data = {"csrf_token": token(client), "nome": "Pedro", "intent": "preview"}
    params = {}
    if case == "csrf": data["csrf_token"] = "bad"
    elif case == "organization": data["organization_id"] = "invalid"; params = {"field": translate(locale, "field.org")}
    elif case == "missing-target": data.update(mode="saved", target_id=str(uuid4()))
    elif case == "year": data["reference_year"] = "invalid"
    elif case == "budget": data.update(output_priority="custom", custom_budget="-1")
    elif case == "service": data["service_profiles"] = "unknown"; params = {"service": "unknown"}
    if case == "upload":
        response = client.post("/generate", data=data, files={"context_file": ("bad.exe", b"x")})
        params = {"role": translate(locale, "source.context"), "extensions": ".txt"}
    elif case == "size": response = client.post("/generate", data=data, headers={"content-length": str(51 * 1024 * 1024)})
    elif case == "job": response = client.get("/jobs/" + str(uuid4()))
    elif case == "missing": response = client.get("/missing")
    elif case == "http": response = client.patch("/generate")
    else: response = client.post("/generate", data=data)
    assert response.status_code == status
    assert translate(locale, key, **params) in html.unescape(response.text)


def test_api_contracts_and_errors_match_across_locales(client):
    records = {}
    for collection in ("engagements", "organizations", "targets"):
        records[collection] = client.post("/api/" + collection, json={"name": "Audit"}).json()
    job_id = historical_job(client)
    snapshots = []
    for locale in LOCALES:
        client.cookies.set("mimic_locale", locale)
        responses = []
        paths = ["/api/health", "/api/jobs", "/api/jobs/" + job_id, "/api/jobs/" + job_id + "/candidates",
                 "/api/jobs/" + str(uuid4()), "/api/jobs/invalid"]
        # Use one stable missing UUID in both requests rather than comparing it.
        paths[4] = "/api/jobs/00000000-0000-0000-0000-000000000001"
        paths += ["/api/" + collection + suffix for collection, record in records.items()
                  for suffix in ("", "/" + record["id"], "/invalid")]
        for path in paths:
            response = client.get(path)
            responses.append((response.status_code, response.json()))
        for path, payload in [("/api/organizations", {"name": ""}), ("/api/jobs", {"request": {"ranking": {"enabled": True, "budget": 0}}})]:
            response = client.post(path, json=payload)
            assert response.status_code == 422
            responses.append((response.status_code, response.json()))
        blocked = client.post("/api/organizations", json={"name": "Audit"}, headers={"origin": "https://external.test"})
        responses.append((blocked.status_code, blocked.json()))
        snapshots.append(responses)
    assert snapshots[0] == snapshots[1]


@pytest.mark.parametrize("include_ptbr", [False, True])
def test_corpus_selection_is_independent_in_both_directions(client, include_ptbr):
    captured = []
    for locale in ("pt-BR", "en", "pt-BR"):
        client.cookies.set("mimic_locale", locale)
        data = {"csrf_token": token(client), "nome": "Pedro", "mode": "quick", "intent": "generate",
                "intelligence_form": "1", "leet_mode": "none", "separators": "", "max_candidates_per_word": "1"}
        if include_ptbr: data["include_ptbr"] = "on"
        response = client.post("/generate", data=data, follow_redirects=False)
        assert response.status_code == 303
        job = client.app.state.job_manager.wait(response.headers["location"].split("/")[-1], 10)
        assert job["status"] == "completed" and job["request"]["sources"]["include_ptbr"] is include_ptbr
        captured.append(job["request"])
    assert captured[0] == captured[1] == captured[2]


@pytest.mark.parametrize("destination", ["/%0d%0aLocation:%20https://evil.test", "/%25255cevil.test", "/%25252fevil.test", "/" + "a" * 2049])
def test_redirect_header_and_nested_encoding_attacks(client, destination):
    response = client.post("/preferences/locale", data={"csrf_token": token(client), "locale": "en", "return_to": destination}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert len(response.headers.get_list("location")) == 1


def test_locale_get_and_invalid_post_do_not_mutate_preference(client):
    client.cookies.set("mimic_locale", "en")
    response = client.get("/preferences/locale?locale=pt-BR")
    assert response.status_code == 422  # Existing generic UUID route owns GET.
    assert "set-cookie" not in response.headers and client.cookies.get("mimic_locale") == "en"
    for locale in ("en\r\nInjected: yes", "en-US", "EN", "pt"):
        response = client.post("/preferences/locale", data={"csrf_token": token(client), "locale": locale})
        assert response.status_code == 422 and "set-cookie" not in response.headers
    response = client.post("/preferences/locale", data={"csrf_token": token(client), "locale": "pt-BR", "return_to": "/generate?name=Jo%C3%A3o&mode=quick"}, follow_redirects=False)
    assert response.headers["location"] == "/generate?name=Jo%C3%A3o&mode=quick"


def test_solid_palette_text_pairs_have_sufficient_contrast():
    css = Path("mimic/web/static/app.css").read_text()
    palettes = re.findall(r":root[^{}]*\{([^}]+)\}", css)[:2]
    def luminance(color):
        color = color.lstrip("#")
        if len(color) == 3:
            color = "".join(c * 2 for c in color)
        channels = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        return sum(weight * (c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4)
                   for weight, c in zip((.2126, .7152, .0722), channels))
    for theme, palette in zip(("dark", "light"), palettes):
        colors = dict(re.findall(r"--([\w-]+):(#[0-9a-fA-F]{3,8});", palette + ";"))
        for foreground, background in [("text", "surface"), ("muted", "surface"),
                ("placeholder", "input-bg"), ("on-accent", "accent-bg"),
                ("on-accent", "primary-hover"), ("danger", "danger-bg"),
                ("warning-text", "warning-bg"), ("active-text", "active-bg")]:
            a, b = luminance(colors[foreground]), luminance(colors[background])
            assert (max(a, b) + .05) / (min(a, b) + .05) >= 4.5, (theme, foreground, background)
