"""Browser preference scripts run under Node without a frontend dependency."""
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.web.security import HTML_CSP


@pytest.mark.parametrize("locale", ["pt-BR", "en"])
def test_theme_assets_header_and_csp(tmp_path, locale):
    with TestClient(create_app(data_dir=tmp_path), cookies={"mimic_locale": locale}) as client:
        page = client.get("/")
        assert page.headers["content-security-policy"] == HTML_CSP
        assert 'type="button" data-theme-toggle' in page.text
        assert 'data-light-label=' in page.text and 'data-dark-label=' in page.text
        assert 'data-theme="dark"' in page.text
        assert page.text.index('theme-init.js') < page.text.index('app.css')
        assert '<script>' not in page.text and 'onclick=' not in page.text
        for name in ("theme-init.js", "app.js", "app.css"):
            assert client.get("/static/" + name).status_code == 200


def test_css_has_semantic_palettes_for_every_component():
    css = Path("mimic/web/static/app.css").read_text()
    assert ':root[data-theme="light"]' in css
    assert "color-scheme:dark" in css and "color-scheme:light" in css
    assert "filter:invert" not in css and "filter: invert" not in css
    for name in ("bg", "surface", "raised", "text", "muted", "border", "accent", "input-bg",
                 "sidebar-bg", "topbar-bg", "selection-text", "table-head", "error-bg", "warning-bg", "candidate-text"):
        assert css.count("--" + name + ":") == 2
    components = css.split('\n*{', 1)[1]
    assert "#131924" not in components
    assert "var(--card-gradient),var(--surface)" in css
    assert "max-width:380px" in css
    assert ":focus-visible" in css


def test_theme_preference_scripts_and_polling_without_frontend_stack():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable; browser scripts require a JS runtime")
    script = r'''
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const init = fs.readFileSync("mimic/web/static/theme-init.js", "utf8");
const app = fs.readFileSync("mimic/web/static/app.js", "utf8");
for (const locale of ["pt-BR", "en"]) {
  for (const stored of ["dark", "light", "invalid", null, "blocked"]) {
    const docEvents = {}, winEvents = {}, buttonEvents = {};
    const values = new Map([["mimic-theme", stored]]);
    const root = {lang: locale, dataset: {}};
    const meta = {content: "dark"}, icon = {textContent: ""};
    const labels = locale === "en" ? ["Switch to light theme", "Switch to dark theme"]
                                  : ["Ativar tema claro", "Ativar tema escuro"];
    const button = {hidden: true, dataset: {lightLabel: labels[0], darkLabel: labels[1]}, attrs: {},
      setAttribute(k,v) {this.attrs[k]=v;}, querySelector() {return icon;},
      addEventListener(k,v) {buttonEvents[k]=v;}};
    const live = {dataset: {pollError: locale === "en" ? "Polling failed" : "Falha na atualização"},
      notice: null, querySelector() {return this.notice;}, prepend(n) {this.notice=n;}};
    let reloads = 0;
    const context = {document: {documentElement: root,
      querySelector(s) {return s === "[data-theme-toggle]" ? button : s.startsWith("meta") ? meta : null;},
      querySelectorAll() {return [];}, getElementById() {return live;},
      createElement() {return {setAttribute() {}};},
      addEventListener(k,v) {docEvents[k]=v;}},
      window: {localStorage: {
        getItem(k) {if(stored==="blocked") throw Error("blocked"); return values.get(k);},
        setItem(k,v) {if(stored==="blocked") throw Error("blocked"); values.set(k,v);}},
        location: {reload() {reloads++;}}, addEventListener(k,v) {winEvents[k]=v;}}};
    vm.createContext(context);
    vm.runInContext(init, context);
    const initial = stored === "light" ? "light" : "dark";
    assert.equal(root.dataset.theme, initial);
    assert.equal(meta.content, initial);
    vm.runInContext(app, context);
    assert.equal(button.hidden, false);
    assert.equal(button.attrs["aria-label"], labels[initial === "light" ? 1 : 0]);
    buttonEvents.click();
    const next = initial === "light" ? "dark" : "light";
    assert.equal(root.dataset.theme, next);
    assert.equal(meta.content, next);
    assert.equal(icon.textContent, next === "light" ? "☀" : "☾");
    assert.equal(button.attrs["aria-label"], labels[next === "light" ? 1 : 0]);
    if (stored !== "blocked") assert.equal(values.get("mimic-theme"), next);
    assert.equal(root.lang, locale);
    winEvents.storage({key: "mimic-theme", newValue: "invalid"});
    assert.equal(root.dataset.theme, "dark");
    docEvents["htmx:responseError"]();
    assert.equal(live.notice.textContent, live.dataset.pollError);
    const same = {detail: {shouldSwap: true, xhr: {getResponseHeader() {return locale;}}}};
    docEvents["htmx:beforeSwap"](same);
    assert.equal(same.detail.shouldSwap, true);
    const changed = {detail: {shouldSwap: true, xhr: {getResponseHeader() {return locale === "en" ? "pt-BR" : "en";}}}};
    docEvents["htmx:beforeSwap"](changed);
    assert.equal(changed.detail.shouldSwap, false);
    assert.equal(reloads, 1);
  }
}
console.log("theme/persistence/storage-failure/locale-isolation/polling checks passed");
'''
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
    assert "checks passed" in result.stdout
