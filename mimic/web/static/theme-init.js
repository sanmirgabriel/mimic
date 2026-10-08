"use strict";

// Blocking local script runs before CSS, independently of interface language.
(() => {
  let theme = "dark";
  try {
    if (window.localStorage.getItem("mimic-theme") === "light") theme = "light";
  } catch (_) { /* Storage may be unavailable; dark remains the default. */ }
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="color-scheme"]').content = theme;
})();
