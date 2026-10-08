"""Presentation locales, isolation, SSR security and unchanged canonical data."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import html
from html.parser import HTMLParser
from pathlib import Path
import re
from string import Formatter

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.application import GenerationRequest, MutationOptions, RankingOptions
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.web.i18n import (LOCALES, TRANSLATIONS, plural, safe_return_to, translate)
from mimic.web.security import HTML_CSP


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        yield client


def token(client):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get("/generate").text)[1]


def language(client, locale):
    client.cookies.set("mimic_locale", locale)


def test_catalog_parity_placeholders_and_no_html():
    pt, en = (TRANSLATIONS[locale] for locale in LOCALES)
    assert pt.keys() == en.keys()
    for key in pt:
        assert pt[key].strip() and en[key].strip()
        fields = lambda text: {field for _, field, _, _ in Formatter().parse(text) if field is not None}
        assert fields(pt[key]) == fields(en[key]), key
        assert "<" not in pt[key] and "<" not in en[key], key
        assert "{" not in translate("pt-BR", key, **{f: "sample" for f in fields(pt[key])})


@pytest.mark.parametrize("cookie", [None, "xx", "EN", "pt", "en-US", "<script>"])
def test_portuguese_default_and_invalid_cookie_fallback(client, cookie):
    if cookie is not None:
        language(client, cookie)
    response = client.get("/", headers={"accept-language": "en-US,en;q=0.9"})
    assert response.status_code == 200
    assert 'lang="pt-BR"' in response.text
    assert "Sua área de trabalho local" in response.text
    assert "Pular para o conteúdo" in response.text
    assert response.headers["Content-Language"] == "pt-BR"
    assert response.headers["Vary"] == "Cookie"


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("path,key", [
    ("/", "dashboard.heading"), ("/engagements", "collection.engagements.create"),
    ("/organizations", "collection.organizations.create"), ("/targets", "generation.profile"),
    ("/generate", "generation.heading"), ("/jobs", "jobs.description"),
    ("/missing", "error.title"),
])
def test_web_pages_and_header_use_request_locale(client, locale, path, key):
    language(client, locale)
    response = client.get(path)
    assert response.status_code == (404 if path == "/missing" else 200)
    assert f'lang="{locale}"' in response.text
    assert translate(locale, key) in html.unescape(response.text)
    assert 'name="locale" value="pt-BR"' in response.text
    assert 'name="locale" value="en"' in response.text
    assert f'value="{locale}" aria-pressed="true"' in response.text
    assert translate(locale, "theme.light") in response.text
    assert response.headers["Content-Security-Policy"] == HTML_CSP


def test_locale_cookie_redirect_and_persistence(client):
    response = client.post("/preferences/locale", data={"csrf_token": token(client),
        "locale": "en", "return_to": "/generate?mode=saved&target_id=abc"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/generate?mode=saved&target_id=abc"
    cookie = response.headers["set-cookie"]
    assert "mimic_locale=en" in cookie and "HttpOnly" in cookie
    assert "SameSite=lax" in cookie and "Path=/" in cookie and "Max-Age=31536000" in cookie
    assert "Secure" not in cookie
    assert "Your local workspace" in client.get("/").text
    assert "From context to candidates" in client.get("/generate").text
    response = client.post("/preferences/locale", data={"csrf_token": token(client),
        "locale": "pt-BR", "return_to": "/"})
    assert "Sua área de trabalho local" in response.text


def test_https_cookie_is_secure(tmp_path):
    with TestClient(create_app(data_dir=tmp_path), base_url="https://testserver") as client:
        response = client.post("/preferences/locale", data={"csrf_token": token(client),
            "locale": "en", "return_to": "/"}, follow_redirects=False)
        assert "Secure" in response.headers["set-cookie"]
        assert 'lang="en"' in client.get("/").text


@pytest.mark.parametrize("value", ["", "bad", "é", "<script>"])
def test_locale_post_requires_csrf(client, value):
    response = client.post("/preferences/locale", data={"csrf_token": value, "locale": "en"})
    assert response.status_code == 403
    assert "Este formulário expirou" in response.text
    assert "mimic_locale" not in response.headers.get("set-cookie", "")


def test_invalid_locale_is_rejected_without_persisting(client):
    response = client.post("/preferences/locale", data={"csrf_token": token(client), "locale": "fr"})
    assert response.status_code == 422 and "Escolha PT-BR ou EN" in response.text
    assert not client.cookies.get("mimic_locale")


@pytest.mark.parametrize("destination", [
    "https://evil.test/", "http://evil.test/", "//evil.test/", "///evil.test/",
    "/\\evil.test/", "\\evil.test", "/%2fevil.test", "/%252fevil.test",
    "/%5cevil.test", "/%0aevil.test", "/bad\r\nLocation: evil", "javascript:alert(1)",
    "relative", "/%zz", "/bad path", "", None,
])
def test_unsafe_return_destinations_fall_back_to_root(client, destination):
    assert safe_return_to(destination) == "/"
    data = {"csrf_token": token(client), "locale": "en"}
    if destination is not None:
        data["return_to"] = destination
    response = client.post("/preferences/locale", data=data, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/"


def test_request_local_context_does_not_leak_concurrently(client):
    def fetch(locale):
        response = client.get("/generate", headers={"cookie": "mimic_locale=" + locale})
        assert f'lang="{locale}"' in response.text
        assert translate(locale, "generation.heading") in response.text
        assert translate(locale, "field.birth_date") in response.text
        assert translate(locale, "theme.light") in response.text
        other = "en" if locale == "pt-BR" else "pt-BR"
        assert translate(other, "generation.heading") not in response.text
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(fetch, ["pt-BR", "en"] * 12))


@pytest.mark.parametrize("locale", LOCALES)
def test_dynamic_confirmation_interpolation_is_escaped(client, locale):
    language(client, locale)
    name = '<img src=x onerror="alert(1)">'
    record = client.post("/api/organizations", json={"name": name}).json()
    page = client.get("/organizations/" + record["id"]).text
    assert name not in page and name in html.unescape(page)
    class Forms(HTMLParser):
        confirmations = []
        def handle_starttag(self, tag, attrs):
            if tag == "form" and "data-confirm" in dict(attrs):
                self.confirmations.append(dict(attrs)["data-confirm"])
    forms = Forms()
    forms.feed(page)
    assert translate(locale, "collection.confirm_links", item=name) in forms.confirmations
    assert plural(locale, "provenance.first", 1, order="x") != plural(locale, "provenance.first", 2, order="x")


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("values,key", [
    ({"reference_year": "bad"}, "error.year"),
    ({"reference_year": "3"}, "error.year_range"),
    ({"output_priority": "custom", "custom_budget": "0"}, "error.budget"),
    ({"mode": "saved"}, "error.target"),
    ({"max_len": "bad"}, "error.integers"),
    ({"context_text": "x" * 65537}, "error.context_size"),
])
def test_known_web_validation_is_localized(client, locale, values, key):
    language(client, locale)
    response = client.post("/generate", data={"csrf_token": token(client), "nome": "Pedro", **values})
    assert response.status_code == 422
    assert translate(locale, key) in response.text


@pytest.mark.parametrize("locale", LOCALES)
def test_unknown_service_and_upload_errors_are_localized(client, locale):
    language(client, locale)
    response = client.post("/generate", data={"csrf_token": token(client),
        "nome": "Pedro", "service_profiles": "bogus"})
    assert response.status_code == 422
    assert translate(locale, "error.service", service="bogus") in response.text
    response = client.post("/generate", data={"csrf_token": token(client), "nome": "Pedro"},
        files={"dataset_file": ("bad.exe", b"x")})
    assert response.status_code == 422
    assert translate(locale, "error.extension", role="Dataset", extensions=".txt, .lst, .wordlist, .dic") in response.text


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("status", ["pending", "running", "completed", "failed", "cancelled"])
def test_job_status_and_htmx_fragment_are_localized(client, locale, status):
    repository = client.app.state.repository
    job = repository.create_job(GenerationRequest().to_dict(), None, None)
    if status != "pending":
        repository.start_job(job["id"])
    if status == "completed":
        path = client.app.state.job_manager.paths.output(job["id"])
        path.parent.mkdir(parents=True)
        path.write_text("")
        repository.complete_job(job["id"], 0, str(path))
    elif status in ("failed", "cancelled"):
        repository.finish_job(job["id"], status, 0)
    language(client, locale)
    response = client.get("/jobs/" + job["id"] + "/status", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["Content-Language"] == locale
    assert translate(locale, "status." + status) in response.text
    assert translate(locale, "provenance.preview") in response.text
    assert translate(locale, "poll.error") in response.text
    assert "<!doctype" not in response.text
    assert ('hx-trigger="every 2s"' in response.text) == (status in ("pending", "running"))


def test_locale_never_changes_api_json(client):
    record = client.post("/api/organizations", json={"name": "ACME", "keywords": ["editor"]}).json()
    snapshots = []
    for locale in LOCALES:
        language(client, locale)
        snapshots.append([(client.get(path).status_code, client.get(path).json()) for path in (
            "/api/organizations/" + record["id"], "/api/organizations/not-a-uuid", "/api/health")])
    assert snapshots[0] == snapshots[1]


def test_scores_provenance_and_wordlist_stay_canonical(client, monkeypatch):
    repository = client.app.state.repository
    job = repository.create_job(GenerationRequest(ranking=RankingOptions(True, 1)).to_dict(), None, None)
    repository.start_job(job["id"])
    candidate = Candidate("ACMEeditor2026", (Origin("organization", "name", "ACME"),),
                          (Transformation("case", (("mode", "original"),)),))
    components = [{"code": "origin.organization.name", "delta": 22,
                   "description": "Recorded organization.name=ACME"}]
    repository.add_preview(job["id"], [{"sequence": 1, "rank": 1, "value": candidate.value,
        "origins": [asdict(o) for o in candidate.origins],
        "transformations": [asdict(t) for t in candidate.transformations],
        "score": 22, "score_version": "score-v1", "score_components": components}])
    path = client.app.state.job_manager.paths.output(job["id"])
    path.parent.mkdir(parents=True)
    path.write_text(candidate.value + "\n")
    repository.complete_job(job["id"], 1, str(path))
    original = repository.get_job(job["id"]), repository.list_preview(job["id"])
    monkeypatch.setattr("mimic.application.generation.score_candidate",
                        lambda *args: pytest.fail("presentation rescored a stored job"))
    for locale in LOCALES:
        language(client, locale)
        page = client.get("/jobs/" + job["id"]).text
        assert translate(locale, "provenance.why") in page
        assert translate(locale, "score.organization") in page
        assert translate(locale, "technical.recorded") in page
        assert components[0]["description"] in page
        assert candidate.value in page and "organization.name" in page
        assert client.get("/api/jobs/" + job["id"] + "/download").content == (candidate.value + "\n").encode()
        assert client.get("/api/jobs/" + job["id"] + "/candidates").json() == original[1]
        assert (repository.get_job(job["id"]), repository.list_preview(job["id"])) == original
    with repository.database.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_locale_never_changes_generation_request_or_corpus_selection(client):
    requests, downloads, previews = [], [], []
    for locale in LOCALES:
        language(client, locale)
        data = {"csrf_token": token(client), "mode": "quick", "nome": "Pedro",
                "leet_mode": "partial", "separators": "", "max_candidates_per_word": "40",
                "intelligence_form": "1", "data_nascimento": "17/08/2002", "intent": "preview"}
        preview = client.post("/generate", data=data)
        assert translate(locale, "generation.ready") in preview.text
        data["intent"] = "generate"
        response = client.post("/generate", data=data, follow_redirects=False)
        assert response.status_code == 303
        job_id = response.headers["location"].split("/")[-1]
        job = client.app.state.job_manager.wait(job_id, 10)
        assert job["status"] == "completed"
        requests.append(job["request"])
        downloads.append(client.get("/api/jobs/" + job_id + "/download").content)
        rows = client.get("/api/jobs/" + job_id + "/candidates").json()
        assert all(row["job_id"] == job_id for row in rows)
        previews.append([{k: v for k, v in row.items() if k != "job_id"} for row in rows])
        assert job["request"]["sources"]["include_ptbr"] is False
        assert "locale" not in job["request"] and "theme" not in job["request"]
    assert requests[0] == requests[1]
    assert downloads[0] == downloads[1]
    assert previews[0] == previews[1]


def test_templates_have_no_unsafe_translation_or_shared_locale_globals():
    root = Path("mimic/web")
    routes = (root / "routes.py").read_text()
    assert 'env.globals["locale"]' not in routes
    for path in (root / "templates").glob("*.html"):
        text = path.read_text()
        assert "|safe" not in text
        if "import 'macros.html'" in text:
            assert "as m with context" in text
        for key in re.findall(r"(?<!\w)(?:t|plural)\('([\w.-]+)'\)", text):
            assert key in TRANSLATIONS["en"], (path, key)


@pytest.mark.parametrize("locale", LOCALES)
def test_localized_generation_form_submits_canonical_option_values(client, locale):
    language(client, locale)

    class Options(HTMLParser):
        def __init__(self):
            super().__init__()
            self.select = None
            self.values = {}
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "select":
                self.select = attrs.get("name")
                self.values[self.select] = []
            elif tag == "option" and self.select:
                self.values[self.select].append(attrs.get("value"))
        def handle_endtag(self, tag):
            if tag == "select":
                self.select = None

    options = Options()
    options.feed(client.get("/generate").text)
    assert options.values["leet_mode"] == ["none", "partial", "full"]
    assert options.values["output_priority"] == ["exhaustive", "quick", "focused", "balanced", "large", "custom"]
    for mode in options.values["leet_mode"]:
        preview = client.post("/generate", data={"csrf_token": token(client), "mode": "quick",
            "nome": "Pedro", "leet_mode": mode, "intent": "preview", "reference_year": "2026"})
        assert preview.status_code == 200
        assert translate(locale, "generation.ready") in preview.text
        assert translate(locale, "leet." + mode) in preview.text
        assert "leet.None" not in preview.text and "leet.Nenhum" not in preview.text
