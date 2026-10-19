# SourceAdapter matrix and G3 integrity
| Adapter | Search | Hydrate | Download | Rights | Authentication |
|---|---|---|---|---|---|
| Wikimedia Commons | MediaWiki file search | imageinfo/extmetadata | imageinfo.url | license/original file page | none |
| Library of Congress | /search?fo=json + pagination | /item/{id}?fo=json | item resources media | rights_and_access, item page | none |
| Europeana | Search API rows/start | Record API | edmIsShownBy/provider media | edmRights, provider page | API key |

Normalized candidate: provider, item_id, source_page_url, title, creator?, creation_date?, depicted_event_date?, period?, place?, collection?, rights_statement?, rights_uri?, license_url?, thumbnail_url?, original_download_url?, MIME?, size?, raw_response_SHA, retrieval_at, historical_exactness, source_match_note, rights_status, review_status.

Historical exactness and reuse permissions are separate. Score exact event vs same subject vs era/context independently from source rights, resolution and quality. Unknown fields remain null; never infer public-domain because a museum hosts it. A candidate cannot render until exact user G3 approval and immutable bytes/metadata are pinned.

Typed SourceAdapter ports: capabilities; search(AssetRequirement, cursor) -> candidates+nextCursor; hydrate(provider_item_id) -> normalized evidence; download -> verified immutable bytes; cancel only current discovery. Rate limiting, request budgets, host allowlist, MIME/byte caps, restart state and typed failure codes required. No silent managed fallback: ARCHIVE_ASSET_UNRESOLVED → user chooses manual upload or managed fallback → proposed candidate(s) → explicit subsequent review.
