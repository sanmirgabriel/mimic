"""Read-only SSR of validated aggregates, never a password upload workflow."""

import io
import json
import logging
import re

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.application import GenerationService
from mimic.application.observations import ObservationError, PatternAnalysisService, save_report
from mimic.web.i18n import TRANSLATIONS, translate
from mimic.web.patterns import artifact_path, list_artifacts
from mimic.web.security import HTML_CSP


def populate(root):
    directory = root / "patterns"; directory.mkdir()
    report = PatternAnalysisService().analyze(io.BytesIO(b"NeverEchoSecret_2026\n" * 5 + b"ACME!\n" * 5), authorized=True,
                                             reference_year=2026, source_label="synthetic")
    save_report(report, directory / "review.json")
    return directory


@pytest.mark.parametrize("locale", ["pt-BR", "en"])
@pytest.mark.parametrize("path", ["/patterns", "/patterns/review"])
def test_readonly_localized_ssr_preserves_headers_and_starts_no_job(tmp_path, monkeypatch, locale, path):
    directory = populate(tmp_path)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        client.cookies.set("mimic_locale", locale)
        def forbidden(*args, **kwargs): raise AssertionError("analysis or generation started")
        monkeypatch.setattr(PatternAnalysisService, "analyze", forbidden)
        monkeypatch.setattr(GenerationService, "prepare", forbidden)
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["Content-Security-Policy"] == HTML_CSP
        assert response.headers["Content-Language"] == locale
        assert response.headers["Cache-Control"] == "no-store"
        assert translate(locale, "patterns.title") in response.text
        assert translate(locale, "patterns.help") in response.text
        assert "NeverEchoSecret" not in response.text
        assert 'type="file"' not in response.text and 'name="password"' not in response.text
        if path.endswith("review"):
            assert "WORD + SEPARATOR + YEAR" in response.text
            assert "ACRONYM + SPECIAL" in response.text
            assert translate(locale, "patterns.analysis_only") in response.text
            assert "5/10" in response.text and "1900–2026" in response.text
            assert '<th scope="col">' in response.text and 'class="table-wrap"' in response.text
        assert client.get("/api/jobs").json() == []
        assert not (tmp_path / "uploads").exists()
        assert list(directory.iterdir()) == [directory / "review.json"]


def test_empty_catalog_does_not_create_artifact_directory(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        page = client.get("/patterns")
        assert page.status_code == 200 and translate("pt-BR", "patterns.empty") in page.text
        assert not (tmp_path / "patterns").exists()


@pytest.mark.parametrize("payload", [b'NeverEchoSecret', b'{"passwords":["NeverEchoSecret"]}',
    b'{"structure":"<script>NeverEchoSecret</script>"}', b'x' * 16385],
    ids=["plaintext", "unknown-fields", "xss", "oversize"])
def test_invalid_artifact_is_never_displayed_logged_uploaded_or_saved_to_jobs(payload, tmp_path, caplog):
    directory = tmp_path / "patterns"; directory.mkdir()
    source = directory / "untrusted.json"; source.write_bytes(payload)
    with caplog.at_level(logging.DEBUG), TestClient(create_app(data_dir=tmp_path)) as client:
        index = client.get("/patterns")
        assert 'href="/patterns/untrusted"' not in index.text
        invalid = client.get("/patterns/untrusted")
        assert invalid.status_code == 422 and "NeverEchoSecret" not in invalid.text + caplog.text
        assert translate("pt-BR", "patterns.invalid") in invalid.text
        assert client.get("/api/jobs").json() == []
        assert not (tmp_path / "uploads").exists()
    assert source.read_bytes() == payload and list(directory.iterdir()) == [source]
    for path in tmp_path.rglob("*"):
        if path.is_file() and path != source:
            assert b"NeverEchoSecret" not in path.read_bytes()


def test_web_has_no_password_analysis_or_upload_route(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        for path in ("/patterns", "/patterns/analyze", "/patterns/review"):
            response = client.post(path, files={"file": ("sample.txt", b"NeverEchoSecret", "text/plain")})
            assert response.status_code in (404, 405, 422)
            assert "NeverEchoSecret" not in response.text
        assert not (tmp_path / "uploads").exists()
        assert not (tmp_path / "patterns").exists()
        assert client.get("/api/jobs").json() == []


def test_artifact_catalog_confines_paths_rejects_symlinks_and_bounds_directory(tmp_path):
    directory = populate(tmp_path)
    outsider = tmp_path / "outside.json"; outsider.write_bytes((directory / "review.json").read_bytes())
    (directory / "alias.json").symlink_to(outsider)
    assert list_artifacts(tmp_path) == ("review",)
    for identifier in ("../outside", "/outside", "review.json", "x" * 65, "<script>"):
        with pytest.raises(ObservationError): artifact_path(tmp_path, identifier)
    for i in range(63): (directory / f"extra-{i}.txt").write_bytes(b"")
    with pytest.raises(ObservationError) as caught:
        list_artifacts(tmp_path)
    assert caught.value.code == "artifact_directory"
    other = tmp_path / "other"; other.mkdir(); (other / "patterns").symlink_to(directory)
    with pytest.raises(ObservationError): list_artifacts(other)


def test_pattern_translation_parity_and_canonical_grammar_labels():
    keys = {key for key in TRANSLATIONS["en"] if key.startswith("patterns.") or key == "nav.patterns"}
    assert len(keys) == 32
    assert all(key in TRANSLATIONS["pt-BR"] for key in keys)
    assert TRANSLATIONS["en"].keys() == TRANSLATIONS["pt-BR"].keys()


def test_small_samples_remain_suppressed_in_web(tmp_path):
    directory = tmp_path / "patterns"; directory.mkdir()
    report = PatternAnalysisService().analyze(io.BytesIO(b"NeverEchoSecret_2026\n"), authorized=True)
    save_report(report, directory / "small.json")
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.get("/patterns/small")
        assert response.status_code == 200
        assert "WORD + SEPARATOR + YEAR" not in response.text and "NeverEchoSecret" not in response.text
        assert translate("pt-BR", "patterns.no_visible") in response.text
