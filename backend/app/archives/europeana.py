"""Europeana Search API V2 + Record API, explicit key and no preview promotion."""
import os
from urllib.parse import quote
from backend.app.contracts import ContractViolation
from .interfaces import Transport, candidate, first, make_cursor, read_cursor, checked_query

BASE="https://www.europeana.eu/api/v2"
class Europeana:
    provider="europeana"
    def __init__(self,client=None,key=None):
        self.http=Transport(client)
        self.key=key if key is not None else os.getenv("HVS_EUROPEANA_API_KEY","")
    def _key(self):
        if not self.key:
            raise ContractViolation("ARCHIVE_AUTH_REQUIRED","europeana","Configure Europeana API key locally.")
        return self.key
    def _norm(self,record,raw):
        item_id=record.get("id")
        if not isinstance(item_id,str) or not item_id.startswith("/") or len(item_id)>400:
            raise ContractViolation("ARCHIVE_ITEM_INVALID","europeana","Missing dataset/record ID.")
        shown=first(record.get("edmIsShownBy"))
        if shown and not shown.startswith("https://"): shown=None
        return candidate(self.provider,item_id,"https://www.europeana.eu/en/item"+item_id,raw,
             title=record.get("title") or record.get("dcTitle"),creator=record.get("dcCreator"),
             date=record.get("year") or record.get("dcDate"),collection=record.get("dataProvider") or record.get("provider"),
             place=record.get("country"),rights=record.get("rights") or record.get("edmRights"),
             rights_uri=first(record.get("rights") or record.get("edmRights")),
             original=shown,preview=first(record.get("edmPreview")))
    def search(self,query,cursor=None,page_size=20):
        checked_query(query,page_size)
        start=read_cursor(self.provider,query,cursor) or 1
        if type(start)!=int or not 1<=start<=1000:
            raise ContractViolation("ARCHIVE_CURSOR_INVALID","europeana","Search paging exceeded.")
        data=self.http.json(BASE+"/search.json",{"wskey":self._key(),"query":query,
                                  "start":start,"rows":page_size,"profile":"rich"},secret=True)
        rows=data.get("items")
        if not isinstance(rows,list): raise ContractViolation("ARCHIVE_JSON_INVALID","europeana","Invalid Europeana items.")
        nxt=start+len(rows)
        return {"candidates":[self._norm(x,x) for x in rows],
                "next_cursor":make_cursor(self.provider,query,nxt)
                    if rows and nxt <= min(int(data.get("totalResults",0)),1000) else None}
    def hydrate(self,item_id):
        if not isinstance(item_id,str) or not item_id.startswith("/") or ".." in item_id or len(item_id)>400:
            raise ContractViolation("ARCHIVE_ITEM_INVALID","europeana","Expected dataset/record ID.")
        raw=self.http.json(BASE+"/record"+quote(item_id,safe="/")+".json",{"wskey":self._key()},secret=True)
        record=raw.get("object") or raw
        agg=(record.get("aggregations") or [{}])[0]
        merged={**record,**agg,"id":item_id}
        if not merged.get("rights"): merged["rights"]=agg.get("edmRights")
        if not merged.get("title"): merged["title"]=first((record.get("proxies") or [{}])[0].get("dcTitle"))
        return self._norm(merged,raw)
