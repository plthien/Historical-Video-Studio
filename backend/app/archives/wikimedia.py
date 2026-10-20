"""MediaWiki Commons File search, continuation and imageinfo hydration."""
from urllib.parse import quote
from backend.app.contracts import ContractViolation
from .interfaces import Transport, candidate, first, plain, make_cursor, read_cursor, checked_query

URL="https://commons.wikimedia.org/w/api.php"
class Wikimedia:
    provider="wikimedia_commons"
    def __init__(self, client=None): self.http=Transport(client)
    def _normalize(self, page):
        meta=(page.get("imageinfo") or [{}])[0]
        extra=meta.get("extmetadata") or {}
        val=lambda key: (extra.get(key) or {}).get("value")
        title=page.get("title","")
        if not title.startswith("File:"):
            raise ContractViolation("ARCHIVE_ITEM_INVALID","commons","Expected a File page.")
        original=meta.get("url")
        if original and not original.startswith("https://upload.wikimedia.org/"): original=None
        return candidate(self.provider,title,
            "https://commons.wikimedia.org/wiki/"+quote(title.replace(" ","_"),safe=":()_-"),
            page,title=val("ObjectName") or title[5:],creator=val("Artist") or val("Credit"),
            date=val("DateTimeOriginal"),collection=val("Credit"),rights=val("LicenseShortName") or val("UsageTerms"),
            rights_uri=val("LicenseUrl"),original=original,preview=meta.get("thumburl"))
    def search(self, query, cursor=None, page_size=20):
        checked_query(query,page_size)
        c=read_cursor(self.provider,query,cursor)
        params=dict(action="query",generator="search",gsrsearch=query,gsrnamespace=6,
                    gsrlimit=page_size,prop="imageinfo",iiprop="url|size|mime|extmetadata|timestamp",
                    iiurlwidth=320,format="json",formatversion=2)
        if c: params.update(c)
        raw=self.http.json(URL,params)
        pages=raw.get("query",{}).get("pages",[])
        if not isinstance(pages,list): raise ContractViolation("ARCHIVE_JSON_INVALID","commons","Invalid search pages.")
        return {"candidates":[self._normalize(p) for p in pages],
                "next_cursor":make_cursor(self.provider,query,raw["continue"]) if raw.get("continue") else None}
    def hydrate(self, item_id):
        if not isinstance(item_id,str) or not item_id.startswith("File:") or len(item_id)>400:
            raise ContractViolation("ARCHIVE_ITEM_INVALID","commons","Expected File: title.")
        data=self.http.json(URL,dict(action="query",titles=item_id,prop="imageinfo",
                     iiprop="url|size|mime|extmetadata|timestamp",iiurlwidth=320,format="json",formatversion=2))
        pages=data.get("query",{}).get("pages",[])
        if not pages or pages[0].get("missing"): raise ContractViolation("ARCHIVE_ITEM_MISSING","commons","File missing.")
        return self._normalize(pages[0])
