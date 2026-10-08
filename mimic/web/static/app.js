"use strict";

function showMode(form) {
  const selected = form.querySelector('input[name="mode"]:checked');
  if (!selected) return;
  form.querySelectorAll("[data-mode]").forEach(section => {
    section.hidden = section.dataset.mode !== selected.value;
  });
}

document.addEventListener("change", event => {
  if (event.target.matches('input[name="mode"]')) showMode(event.target.form);
});

document.addEventListener("submit", event => {
  const form = event.target;
  if (!form.matches("[data-submit]")) return;
  if (form.dataset.submitting === "true") {
    event.preventDefault();
    return;
  }
  if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
    event.preventDefault();
    return;
  }
  // Keep the chosen submit action when its button becomes disabled.
  if (event.submitter && event.submitter.name) {
    const action = document.createElement("input");
    action.type = "hidden";
    action.name = event.submitter.name;
    action.value = event.submitter.value;
    action.dataset.submitAction = "true";
    form.appendChild(action);
  }
  form.dataset.submitting = "true";
  form.setAttribute("aria-busy", "true");
  form.querySelectorAll('button[type="submit"]').forEach(button => {
    if (!button.disabled) {
      button.dataset.submitLock = "true";
      button.disabled = true;
    }
  });
});

// Restore usable forms when the browser returns from its back/forward cache.
window.addEventListener("pageshow", () => {
  document.querySelectorAll("form[data-submitting]").forEach(form => {
    delete form.dataset.submitting;
    form.removeAttribute("aria-busy");
    form.querySelectorAll("[data-submit-action]").forEach(input => input.remove());
    form.querySelectorAll("button[data-submit-lock]").forEach(button => {
      button.disabled = false;
      delete button.dataset.submitLock;
    });
  });
});

function pollingError() {
  const live = document.getElementById("job-live");
  if (live && !live.querySelector(".poll-error")) {
    const notice = document.createElement("p");
    notice.className = "alert poll-error";
    notice.setAttribute("role", "alert");
    notice.textContent = live.dataset.pollError;
    live.prepend(notice);
  }
}
document.addEventListener("htmx:responseError", pollingError);
document.addEventListener("htmx:sendError", pollingError);

// A preference changed in another tab must not mix fragment/page languages.
document.addEventListener("htmx:beforeSwap", event => {
  const locale = event.detail.xhr.getResponseHeader("Content-Language");
  if (locale && locale !== document.documentElement.lang) {
    event.detail.shouldSwap = false;
    window.location.reload();
  }
});

const prioritySelect = document.querySelector('[name="output_priority"]');
if (prioritySelect) {
  prioritySelect.addEventListener('change', () => {
    document.querySelector('[data-custom-budget]').hidden = prioritySelect.value !== 'custom';
  });
}

const themeToggle = document.querySelector("[data-theme-toggle]");
function updateThemeToggle() {
  if (!themeToggle) return;
  const light = document.documentElement.dataset.theme === "light";
  const label = light ? themeToggle.dataset.darkLabel : themeToggle.dataset.lightLabel;
  themeToggle.setAttribute("aria-label", label);
  themeToggle.setAttribute("title", label);
  themeToggle.setAttribute("aria-pressed", String(light));
  themeToggle.querySelector("[data-theme-icon]").textContent = light ? "☀" : "☾";
  themeToggle.hidden = false;
}
if (themeToggle) {
  updateThemeToggle();
  themeToggle.addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="color-scheme"]').content = theme;
    try { window.localStorage.setItem("mimic-theme", theme); } catch (_) { /* Still usable in memory. */ }
    updateThemeToggle();
  });
  window.addEventListener("pageshow", updateThemeToggle);
  window.addEventListener("storage", event => {
    if (event.key !== "mimic-theme" && event.key !== null) return;
    const theme = event.newValue === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="color-scheme"]').content = theme;
    updateThemeToggle();
  });
}
