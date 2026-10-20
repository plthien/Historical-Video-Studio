"""A3-01/02 real adapter HTTP boundary, immutable PNG bytes and SQLite reopen."""
import base64
import httpx
import pytest
from backend.app.contracts import ContractViolation
from backend.app.archives.wikimedia import Wikimedia
from backend.app.archives.loc import LOC
from backend.app.archives.europeana import Europeana
from backend.app.assets.provenance import AssetCandidates
from backend.app.projects.storage import ProjectStore
from backend.app.projects.models import StoryCandidate
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[2]
def _png(red=0):
    import struct,zlib
    def chunk(name,body):
        return struct.pack(">I",len(body))+name+body+struct.pack(">I",zlib.crc32(name+body))
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress(bytes([0,red,10,30])))+chunk(b"IEND",b""))
PNG=_png()

def project(tmp_path):
    story=json.loads((ROOT/"contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    store=ProjectStore(tmp_path/"db.sqlite",tmp_path/"media")
    pid=story["project"]["project_id"]
    store.create_project(pid,"A3 owner test")
    store.import_story(StoryCandidate.parse(story),0)
    return store,pid,story["asset_requirements"][0]["requirement_id"]

def transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))

def test_search_paging_hydrate_three_archives_and_null_rights(tmp_path):
    seen=[]
    def response(req):
        seen.append((req.url.path, dict(req.url.params)))
        if req.url.host=="commons.wikimedia.org":
            if req.url.params.get("generator")=="search":
                return httpx.Response(200,json={"query":{"pages":[
                    {"title":"File:Old map.png","imageinfo":[{"url":"https://upload.wikimedia.org/test/original.png",
                    "extmetadata":{"Artist":{"value":"<a>Map Maker</a>"}}}]}]},
                    "continue":{"gsroffset":20,"continue":"gsroffset||"}})
            return httpx.Response(200,json={"query":{"pages":[{"title":"File:Old map.png",
                "imageinfo":[{"url":"https://upload.wikimedia.org/test/original.png"}]}]}})
        if req.url.host=="www.loc.gov":
            if req.url.path=="/search/":
                return httpx.Response(200,json={"results":[{"id":"http://www.loc.gov/item/12345/",
                    "title":"Map","image_url":["https://www.loc.gov/thumb/icon.jpg"]}],
                    "pagination":{"next":"https://www.loc.gov/search/?sp=2"}})
            return httpx.Response(200,json={"item":{"id":"http://www.loc.gov/item/12345/",
                "title":"Map"},"resources":[{"files":[[{"url":"https://www.loc.gov/media/full.jpg",
                "mimetype":"image/jpeg"}]]}]})
        if req.url.path=="/api/v2/search.json":
            assert req.url.params["wskey"]=="fixture-secret"
            return httpx.Response(200,json={"totalResults":21,"items":[{"id":"/abc/123",
                 "title":["Antique book"],"edmPreview":["https://www.europeana.eu/thumb.jpg"],
                 "edmRights":["http://rightsstatements.org/unknown"]}]})
        return httpx.Response(200,json={"object":{"id":"/abc/123","title":["Antique book"],
             "aggregations":[{"edmIsShownBy":"https://www.europeana.eu/full.png"}]}})
    cli=transport(response)
    w,l,e=Wikimedia(cli),LOC(cli),Europeana(cli,"fixture-secret")
    pages=[p.search("history") for p in (w,l,e)]
    assert all(p["next_cursor"] for p in pages)
    assert pages[0]["candidates"][0]["creator"]=="Map Maker"
    assert pages[0]["candidates"][0]["rights_status"]=="UNKNOWN"
    assert pages[1]["candidates"][0]["original_download_url"] is None
    assert pages[2]["candidates"][0]["original_download_url"] is None
    assert l.hydrate("12345")["original_download_url"].endswith("full.jpg")
    assert e.hydrate("/abc/123")["original_download_url"].endswith("full.png")
    with pytest.raises(ContractViolation,match="ARCHIVE_CURSOR_MISMATCH"):
        w.search("different",pages[0]["next_cursor"])
    store,pid,req=project(tmp_path)
    service=AssetCandidates(store)
    ids=service.search(pid,req,"history",w)["candidate_ids"]
    assert len(ids)==1 and service.get(pid,ids[0])["user_approved"] is False
    assert AssetCandidates(ProjectStore(store.database,store.artifacts.root)).get(pid,ids[0])["creator"]=="Map Maker"
    assert len(seen)>=6

def test_search_errors_hydrate_404_and_key_redacted():
    def bad(req):
        return httpx.Response(429)
    with pytest.raises(ContractViolation,match="ARCHIVE_RATE_LIMITED"):
        Wikimedia(transport(bad)).search("battle")
    with pytest.raises(ContractViolation,match="ARCHIVE_AUTH_REQUIRED"):
        Europeana(transport(bad),key="").search("battle")
    with pytest.raises(ContractViolation,match="ARCHIVE_CURSOR_MISMATCH"):
        LOC(transport(bad)).search("war","{}")
    with pytest.raises(ContractViolation,match="ARCHIVE_JSON_INVALID"):
        Wikimedia(transport(lambda req:httpx.Response(200,text="<html>"))).search("war")

def test_download_rights_manual_provenance_and_original_bytes(tmp_path):
    from backend.app.assets.download import inspect,download
    store,pid,req=project(tmp_path)
    service=AssetCandidates(store)
    cand={"provider":"wikimedia_commons","item_id":"File:Map.png",
          "title":"Unknown era map","rights_statement":None,"rights_status":"UNKNOWN",
          "original_download_url":"https://upload.wikimedia.org/maps/original.png",
          "thumbnail_url":"https://upload.wikimedia.org/maps/thumb.png",
          "user_approved":False}
    with store._transaction() as db:
        cid=service._save(db,pid,req,cand)
    def handler(request):
        return httpx.Response(200,content=PNG,headers={"Content-Type":"image/png"})
    one=service.original(pid,req,cid,transport(handler))
    assert one["rights_status"]=="UNKNOWN" and not one["user_approved"]
    assert store.get_artifact(one["original_sha256"])==PNG
    two=service.original(pid,req,cid,transport(handler))
    assert two["original_sha256"]==one["original_sha256"]
    reread=AssetCandidates(ProjectStore(store.database,store.artifacts.root))
    assert reread.get(pid,one["candidate_id"])["original_sha256"]==one["original_sha256"]
    manual=service.manual(pid,req,PNG,"Unreviewed manual asset","Owner supplied","Rights unverified")
    assert manual["asset_class"]=="USER_SUPPLIED" and not manual["user_approved"]
    with pytest.raises(ContractViolation,match="SOURCE_FILE_UNAVAILABLE"):
        download({"provider":"loc","original_download_url":None})
    with pytest.raises(ContractViolation,match="ORIGINAL_HOST_FORBIDDEN"):
        download({**cand,"original_download_url":"http://127.0.0.1/private.png"})
    with pytest.raises(ContractViolation,match="ORIGINAL_REDIRECT_FORBIDDEN"):
        download(cand,transport(lambda req:httpx.Response(302,headers={"Location":"https://evil.org/x"})))
    with pytest.raises(ContractViolation,match="ORIGINAL_MEDIA_INVALID"):
        inspect(b"fake image")
    corrupt=bytearray(PNG)
    corrupt[45]^=1
    with pytest.raises(ContractViolation,match="ORIGINAL_MEDIA_INVALID"):
        inspect(bytes(corrupt))
    with pytest.raises(ContractViolation,match="ORIGINAL_SIZE_INVALID"):
        inspect(b"x"*(20*1024*1024+1))
