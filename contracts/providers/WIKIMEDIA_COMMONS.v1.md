# Wikimedia Commons Adapter — Detailed Contract
**Official APIs:** https://www.mediawiki.org/wiki/API:Action_API ; https://www.mediawiki.org/wiki/API:Imageinfo

Search files: GET https://commons.wikimedia.org/w/api.php with action=query, generator=search, gsrsearch, gsrnamespace=6, gsrlimit, format=json, formatversion=2; prop=imageinfo, iiprop=url|size|mime|extmetadata|timestamp. Search can alternatively list=search then query specific File titles. Resume using continue token; bounded pages and per-host request rate. Respect descriptive User-Agent.

Hydrate candidate using File page and imageinfo metadata: pageid/title, canonical file page, original download URL, MIME and dimensions, Artist/Credit/LicenseShortName/LicenseUrl/UsageTerms/Copyrighted fields as available, image description, creation date if actually supplied. Sanitize extmetadata HTML for UI. Preserve original metadata response/hash and actual media bytes SHA. Commons upload time is NOT event date; license metadata does NOT prove photo depicts exact event.

Download only approved media candidate from verified source URL, not arbitrary ChatGPT URL; don't confuse thumb with original. Missing file/rights/license or irrelevant date => keep candidate unapproved and G3 review required. 429 and 5xx bounded retry/backoff. Test: imageinfo happy path, missing creator, HTML description, continuation, 429, thumbnail-only, wrong historical exactness. Candidate status must remain CANDIDATE until user approves exact asset.
