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
    hydrated=e.hydrate("/abc/123")
    assert hydrated["original_download_url"].endswith("full.png")
    assert hydrated["hydrated"] is True
    assert pages[2]["candidates"][0].get("hydrated") is not True
    with pytest.raises(ContractViolation,match="ARCHIVE_CURSOR_MISMATCH"):
        w.search("different",pages[0]["next_cursor"])
    store,pid,req=project(tmp_path)
    service=AssetCandidates(store)
    ids=service.search(pid,req,"history",w)["candidate_ids"]
    assert len(ids)==1 and service.get(pid,ids[0])["user_approved"] is False
    second_req=store.get_story(pid).data()["asset_requirements"][1]["requirement_id"]
    with pytest.raises(ContractViolation,match="ARCHIVE_CURSOR_MISMATCH"):
        service.search(pid,second_req,"history",w,cursor=service.search(pid,req,"history",w)["next_cursor"])
    imported=store.get_story(pid).data()
    imported["project"]["project_id"]="proj_other_a3"
    store.create_project("proj_other_a3","Independent project")
    store.import_story(StoryCandidate.parse(imported),0)
    with pytest.raises(ContractViolation,match="ARCHIVE_CURSOR_MISMATCH"):
        service.search("proj_other_a3",req,"history",w,
            cursor=service.search(pid,req,"history",w)["next_cursor"])
    with pytest.raises(ContractViolation,match="ASSET_CANDIDATE_NOT_FOUND"):
        service.get("proj_other_a3",ids[0])
    assert AssetCandidates(ProjectStore(store.database,store.artifacts.root)).get(pid,ids[0])["creator"]=="Map Maker"
    eu=service.search(pid,req,"history",e)["candidate_ids"][0]
    with pytest.raises(ContractViolation,match="SOURCE_HYDRATION_REQUIRED"):
        service.original(pid,req,eu,transport(lambda req:httpx.Response(200,content=PNG)))
    ready=service.hydrate(pid,req,e,"/abc/123")
    assert ready["hydrated"] is True and not ready["user_approved"]
    original=service.original(pid,req,ready["candidate_id"],
        transport(lambda req:httpx.Response(200,content=PNG,headers={"content-type":"image/png"})))
    assert store.get_artifact(original["original_sha256"])==PNG
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
    count=[0]
    def retry(request):
        count[0]+=1
        if count[0]<3: return httpx.Response(503)
        return httpx.Response(200,json={"query":{"pages":[]}})
    assert Wikimedia(transport(retry)).search("war")["candidates"]==[]
    assert count[0]==3
    def timeout(request): raise httpx.TimeoutException("offline simulated timeout")
    with pytest.raises(ContractViolation,match="ARCHIVE_NETWORK_ERROR"):
        LOC(transport(timeout)).search("war")

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
    changed=service.original(pid,req,cid,
             transport(lambda request:httpx.Response(200,content=_png(50),
                                headers={"content-type":"image/png"})))
    assert changed["original_sha256"]!=one["original_sha256"]
    assert store.get_artifact(one["original_sha256"])==PNG
    assert store.get_artifact(changed["original_sha256"])==_png(50)
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
    path=store.artifacts.path(one["original_sha256"])
    path.write_bytes(b"tampered media")
    with pytest.raises(ContractViolation,match="ARTIFACT_CORRUPT"):
        reread.store.get_artifact(one["original_sha256"])


def test_original_requires_exact_requirement_and_rechecks_after_download(tmp_path):
    store, project_id, req_a = project(tmp_path)
    req_b = store.get_story(project_id).data()["asset_requirements"][1]["requirement_id"]
    candidates = AssetCandidates(store)
    source = dict(provider="wikimedia_commons", item_id="File:Period.png",
                  original_download_url="https://upload.wikimedia.org/period/original.png",
                  thumbnail_url=None, rights_status="UNKNOWN", user_approved=False)
    with store._transaction() as db:
        candidate_id = candidates._save(db, project_id, req_a, source)
    calls = []
    def media(request):
        calls.append(request.url.path)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
    with pytest.raises(ContractViolation, match="ASSET_CANDIDATE_REQUIREMENT_MISMATCH"):
        candidates.original(project_id, req_b, candidate_id, transport(media))
    assert not calls
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_candidates WHERE requirement_id=?",
                          (req_b,)).fetchone()[0] == 0
    approved = candidates.original(project_id, req_a, candidate_id, transport(media))
    assert store.get_artifact(approved["original_sha256"]) == PNG
    assert not approved["user_approved"]
    # Sharing bytes is legitimate only after another independently owned candidate exists.
    with store._transaction() as db:
        independently_scoped = candidates._save(db,project_id,req_b,source)
    shared = candidates.original(project_id,req_b,independently_scoped,transport(media))
    assert shared["original_sha256"] == approved["original_sha256"]
    assert shared["candidate_id"] != approved["candidate_id"]

    # External download finishes after original source requirement was replaced.
    def race(request):
        changed = store.get_story(project_id).data()
        changed["asset_requirements"][0]["subject"] += " — revised identity"
        store.import_story(StoryCandidate.parse(changed), store.revision(project_id))
        return httpx.Response(200, content=_png(83),
                              headers={"content-type": "image/png"})
    before = len(store.get_artifact(approved["original_sha256"]))
    with pytest.raises(ContractViolation, match="ASSET_SOURCE_STALE"):
        candidates.original(project_id, req_a, candidate_id, transport(race))
    assert candidates.get(project_id, candidate_id)["original_sha256"] is None
    assert len(store.get_artifact(approved["original_sha256"])) == before
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_candidates WHERE project_id=?",
                          (project_id,)).fetchone()[0] == 4
    assert AssetCandidates(ProjectStore(store.database, store.artifacts.root)).get(
        project_id, candidate_id)["original_sha256"] is None
