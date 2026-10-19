# Library of Congress Adapter — Detailed Contract
**Official APIs:** https://www.loc.gov/apis/json-and-yaml/requests/endpoints/ ; https://www.loc.gov/apis/json-and-yaml/responses/item-and-resource/

Search GET https://www.loc.gov/search/?q=...&fo=json&c=25&sp=1 (or /photos/, /maps/, /newspapers/ with format filters). Parse results array, facets and pagination.next. Follow only allowed host; persist cursor, cap pages. Note LoC has partial collection coverage, some items are modern web pages, and some results lack usable digitized media.

Hydrate canonical /item/{item_id}/?fo=json for item bibliographic fields and resources list. Normalize item URL (LoC may return http in id) to verified https origin. Extract title/date/creator/collection, rights_and_access/rights_advisory when present, subject, location, exactness and digital resource. Source image_url may be only thumbnail/icon. Select usable actual resources download URL and verify MIME/resolution; preserve source item page, raw metadata/hash.

No API key normally needed, but rate limits enforced. A LoC record does not automatically confer public domain reuse or factual exact-event identity. Unknown rights => RIGHTS_REVIEW_REQUIRED; missing downloadable resource => SOURCE_FILE_UNAVAILABLE. Test paging.next, detail resources, thumbnail-only, missing rights, 404, 429, wrong-era record; never auto G3 approve.
