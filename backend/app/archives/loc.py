"""Library of Congress search and resource-aware item hydration."""
from urllib.parse import urlparse, quote, urljoin
from backend.app.contracts import ContractViolation
from .interfaces import Transport, candidate, first, read_cursor, make_cursor, checked_query

ROOT="https://www.loc.gov"
def identifier(record):
    url=record.get("id") or record.get("url")
    if isinstance(url,str) and urlparse(url).hostname in ("loc.gov","www.loc.gov"):
        path=urlparse(url).path
        if "/item/" in path: return path.split("/item/")[1].strip("/").split("/")[0]
    return str(record.get("item_id") or "") or None

class LOC:
    provider="loc"
    def __init__(self,client=None): self.http=Transport(client)
    def _norm(self, item, raw, resources=None):
        code=identifier(item)
        if not code or "/" in code or len(code)>150: raise ContractViolation("ARCHIVE_ITEM_INVALID","loc","Unknown LoC item identifier.")
        original=None
        for res in (resources or []):
            for group in res.get("files",[]) if isinstance(res,dict) else []:
                for file in group if isinstance(group,list) else [group]:
                    if isinstance(file,dict) and str(file.get("mimetype","")).startswith("image/"):
                        url=file.get("url")
                        if isinstance(url,str) and url.startswith("https://") and not ("thumb" in url.lower() or "icon" in url.lower()):
                            original=url; break
                if original: break
            if original: break
        return candidate(self.provider,code,f"{ROOT}/item/{quote(code)}/",raw,
            title=item.get("title"),creator=item.get("contributor") or item.get("contributors"),
            date=item.get("date"),collection=item.get("partof") or item.get("source_collection"),
            place=item.get("location"),rights=item.get("rights_and_access") or item.get("rights_advisory"),
            original=original,preview=first(item.get("image_url")))
    def search(self,query,cursor=None,page_size=20):
        checked_query(query,page_size)
        page=read_cursor(self.provider,query,cursor) or 1
        if type(page)!=int or not 1<=page<=100: raise ContractViolation("ARCHIVE_CURSOR_INVALID","loc","Page limit exceeded.")
        data=self.http.json(ROOT+"/search/",dict(q=query,fo="json",c=page_size,sp=page))
        rows=data.get("results")
        if not isinstance(rows,list): raise ContractViolation("ARCHIVE_JSON_INVALID","loc","Invalid result array.")
        nxt=(data.get("pagination") or {}).get("next")
        if nxt and urlparse(nxt).hostname not in ("loc.gov","www.loc.gov"):
            raise ContractViolation("ARCHIVE_CURSOR_INVALID","loc","Untrusted next link.")
        return {"candidates":[self._norm(x,x) for x in rows],
                "next_cursor":make_cursor(self.provider,query,page+1) if nxt and page<100 else None}
    def hydrate(self,item_id):
        if not isinstance(item_id,str) or not item_id or len(item_id)>150 or "/" in item_id:
            raise ContractViolation("ARCHIVE_ITEM_INVALID","loc","Invalid LoC ID.")
        raw=self.http.json(ROOT+"/item/"+quote(item_id)+"/",{"fo":"json"})
        return self._norm(raw.get("item") or {},raw,raw.get("resources") or [])
