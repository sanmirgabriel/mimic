# ADR 0008: Web language and theme preferences

Status: Accepted (Block 8.5)

## Context

The local SSR workspace needs natural Brazilian Portuguese and English, plus a
readable light theme alongside the existing dark appearance. Preferences must
remain independent of password intelligence, generation and persisted evidence.

## Decision

Keep translations in the Web adapter, using stable keys in a small Python
catalog with matching PT-BR/EN placeholders. Resolve each request from the
strictly allowlisted `mimic_locale` cookie; absent or invalid cookies use PT-BR,
regardless of Accept-Language. Bind translation helpers to the render context,
including Jinja macros imported with context; never change shared locale globals.

Catalog mappings are read-only at both levels. A missing key logs a warning and
falls back to English or the key itself. Invalid interpolation logs an error
without operator values and presents a generic localized message instead of an
HTTP 500. Gate tests reject missing keys or parameters in real template renders,
so these production fallbacks do not silently hide development mistakes.

A compact PT-BR/EN header form posts to `/preferences/locale` with existing CSRF
protection. Its cookie lasts one year, uses HttpOnly, SameSite=Lax and Path=/,
and is Secure over HTTPS. Redirects preserve safe local paths and queries;
absolute, protocol-relative, malformed and encoded unsafe destinations fall
back to `/`. Full pages and HTMX fragments carry Content-Language and Vary:
Cookie. If polling detects a language changed in another tab, reload before
swapping, keeping the page in one language.

Localize known Web validation through structured message keys. Lower-layer
errors and historical score descriptions retain escaped original technical
details; score presentation uses existing structured codes without parsing
descriptions or recalculating scores. Canonical values, origin fields,
transformations, IDs, request JSON and downloaded wordlists stay unchanged.
Selecting PT-BR does not select the PT-BR corpus.

Use semantic CSS colors for a real light palette and preserve dark as default.
The adjacent accessible theme button persists `dark` or `light` in
`localStorage` under `mimic-theme`. A blocking local script before the stylesheet
applies the saved theme and color-scheme before paint. Unavailable storage and
invalid values safely fall back to dark. Theme and language are independent.

## Consequences

No additional runtime dependencies, preference table or schema migration are
needed. Production changes remain within `mimic/web/`; Core, scoring, API JSON,
CLI and JobManager lifecycle retain their contracts. Existing loopback, CSRF,
CSP, upload containment and Jinja escaping remain in effect, without inline
scripts, unsafe translations or external assets.

New coverage checks catalog parity, concurrent request isolation, redirects,
cookies, errors, HTMX, scripts and canonical data. Release validation includes
the complete suite, an installed-wheel HTTP generation comparison, and Firefox
screenshots for both locales and themes on desktop and mobile.
