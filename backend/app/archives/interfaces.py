"""A3-01 bounded archive transport, normalization, cursor scope and review-only records."""
from __future__ import annotations
import hashlib
import html
import json
import os
import re
import time
from urllib.parse import urlparse
from datetime import datetime, timezone

import httpx
from backend.app.contracts import ContractViolation

UA = "HistoricalVideoStudio/1.0 (local historical source review)"
LIMIT = 25
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode()).hexdigest()

def first(v):
    if isinstance(v, list):
        return first(v[0]) if v else None
    if isinstance(v, dict):
        return first(v.get("def") or v.get("en") or next(iter(v.values()), None))
    return str(v) if v is not None and v != "" else None

def plain(v):
    s = first(v)
    if s is None: return None
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip() or None

def candidate(provider, item_id, source_url, raw, *, title=None, creator=None, date=None,
              collection=None, place=None, rights=None, rights_uri=None, original=None, preview=None):
    return dict(provider=provider, item_id=str(item_id), source_page_url=source_url,
                title=plain(title) or "(untitled source)", creator=plain(creator),
                creation_date=plain(date), collection=plain(collection), place=plain(place),
                rights_statement=plain(rights), rights_uri=rights_uri,
                original_download_url=original, thumbnail_url=preview,
                raw_response_sha256=digest(raw), retrieved_at=datetime.now(timezone.utc).isoformat(),
                rights_status="REVIEW_REQUIRED" if rights else "UNKNOWN",
                historical_exactness="UNREVIEWED", review_status="CANDIDATE",
                user_approved=False, asset_class=None, depicted_event_date=None, period=None)

class Transport:
    def __init__(self, client=None):
        self.client = client or httpx.Client(timeout=httpx.Timeout(12.0), follow_redirects=False,
                                            headers={"User-Agent": UA})
    def json(self, url, params=None, *, secret=False):
        host = urlparse(url).hostname
        if not host or urlparse(url).scheme != "https":
            raise ContractViolation("ARCHIVE_URL_UNSAFE", "archive", "HTTPS provider API required.")
        for attempt in range(3):
            try:
                r = self.client.get(url, params=params, timeout=12)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < 2: continue
                raise ContractViolation("ARCHIVE_NETWORK_ERROR", "archive", "Network failed; retry discovery.") from exc
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(0.15 * (attempt + 1))
                continue
            if r.status_code == 429: code="ARCHIVE_RATE_LIMITED"
            elif r.status_code in (401, 403): code="ARCHIVE_AUTH_REQUIRED"
            elif r.status_code == 404: code="ARCHIVE_ITEM_MISSING"
            elif r.status_code >= 400: code="ARCHIVE_HTTP_ERROR"
            else: code=None
            if code:
                # Deliberately do not expose URLs (Europeana wskey may be in query).
                raise ContractViolation(code, "archive", f"Provider HTTP {r.status_code}; check account or retry.")
            if r.is_redirect:
                raise ContractViolation("ARCHIVE_REDIRECT_UNVERIFIED", "archive", "Provider API redirected unexpectedly.")
            try:
                value=r.json()
            except (ValueError, TypeError) as exc:
                raise ContractViolation("ARCHIVE_JSON_INVALID", "archive", "Provider response was not JSON.") from exc
            if not isinstance(value, dict):
                raise ContractViolation("ARCHIVE_JSON_INVALID", "archive", "Expected provider JSON object.")
            return value
        raise ContractViolation("ARCHIVE_NETWORK_ERROR","archive","Retries exhausted.")

def make_cursor(provider, query, position):
    return json.dumps({"provider":provider,"q":digest(query),"p":position},
                      separators=(",",":"),sort_keys=True)

def read_cursor(provider, query, cursor):
    if not cursor: return None
    try:
        obj=json.loads(cursor)
        if obj["provider"] != provider or obj["q"] != digest(query):
            raise ValueError()
        return obj["p"]
    except (ValueError, TypeError, KeyError):
        raise ContractViolation("ARCHIVE_CURSOR_MISMATCH",provider,"Cursor belongs to another provider/query.")

def checked_query(query, size):
    if not isinstance(query, str) or not query.strip() or len(query)>300 or not 1<=size<=LIMIT:
        raise ContractViolation("ARCHIVE_QUERY_INVALID","query","Supply a short query and <=25 results.")
