# Europeana Adapter — Detailed Contract
**Official materials:** https://pro.europeana.eu/page/get-api ; https://pro.europeana.eu/post/using-jquery-with-the-europeana-api ; https://pro.europeana.eu/page/available-rights-statements

Requires Europeana account API key; store server-side only, redact query/log URLs. Search documentation pattern GET https://www.europeana.eu/api/v2/search.json?wskey=SECRET&query=...&start=1&rows=24&profile=rich. Confirm current supported host/path and Record API details when implementing; do not assert examples are guaranteed stable endpoints.

Extract items, totalResults, item id, title, creator, year/date, country, provider/dataProvider, edmPreview, edmIsShownAt, edmIsShownBy and rights/edmRights when available. Hydrate richer Record API metadata before user review. edmPreview is thumbnail, not a high-res production asset. edmIsShownBy/direct provider media may be usable if rights and MIME verified. Preserve raw response and institution source link.

Europeana rights URIs reflect different reuse conditions, from PD/CC to restricted or unclear. Metadata alone never establishes exact historic depiction. Pagination bounded via declared start/rows (or current official cursor if actually advertised). 401/403 key configuration, 429 backoff, 404 missing record; uncertain rights => G3 review. Test invalid key, preview-only, metadata nulls, conflicting rights, pagination and sanitized logs.
