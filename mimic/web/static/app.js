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
    notice.textContent = "Status could not be refreshed. Reload this page to reconnect.";
    live.prepend(notice);
  }
}
document.addEventListener("htmx:responseError", pollingError);
document.addEventListener("htmx:sendError", pollingError);

const prioritySelect = document.querySelector('[name="output_priority"]');
if (prioritySelect) {
  prioritySelect.addEventListener('change', () => {
    document.querySelector('[data-custom-budget]').hidden = prioritySelect.value !== 'custom';
  });
}
