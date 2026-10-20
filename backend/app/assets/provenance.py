"""A3-01/02 scoped immutable asset candidates; no G3 approval transition."""
import json
from uuid import uuid4
from hashlib import sha256
from backend.app.contracts import ContractViolation
from .download import inspect, download

class AssetCandidates:
    def __init__(self,store):
        self.store=store
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS archive_discovery(
                    project_id TEXT NOT NULL, requirement_id TEXT NOT NULL,
                    provider TEXT NOT NULL, query_sha TEXT NOT NULL,
                    next_cursor TEXT, candidate_ids_json TEXT NOT NULL,
                    PRIMARY KEY(project_id,requirement_id,provider,query_sha));
                CREATE TABLE IF NOT EXISTS asset_candidates(
                    candidate_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL, origin TEXT NOT NULL,
                    metadata_json TEXT NOT NULL, metadata_sha256 TEXT NOT NULL,
                    original_sha256 TEXT, mime_type TEXT, byte_count INTEGER,
                    review_status TEXT NOT NULL CHECK(review_status='CANDIDATE'),
                    user_approved INTEGER NOT NULL CHECK(user_approved=0));
                CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_versions ON asset_candidates(
                    project_id, requirement_id, origin, metadata_sha256, IFNULL(original_sha256,''));
            """)
    def _requirement(self,project,requirement):
        story=self.store.get_story(project).data()
        if requirement not in {x["requirement_id"] for x in story["asset_requirements"]}:
            raise ContractViolation("ASSET_REQUIREMENT_NOT_FOUND",requirement,"Requirement not in StoryPackage.")
    def _save(self,db,project,requirement,candidate,original_sha=None,mime=None,size=None):
        origin=candidate.get("provider")
        if origin not in ("wikimedia_commons","loc","europeana","manual_upload","glabs_webhook"):
            raise ContractViolation("ASSET_ORIGIN_INVALID","candidate","Unknown source provenance.")
        candidate={**candidate,"review_status":"CANDIDATE","user_approved":False}
        body=json.dumps(candidate,sort_keys=True,separators=(",",":"),ensure_ascii=False)
        identity={k:v for k,v in candidate.items() if k!="retrieved_at"}
        digest=sha256(json.dumps(identity,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        row=db.execute("SELECT candidate_id FROM asset_candidates WHERE project_id=? AND "
                       "requirement_id=? AND origin=? AND metadata_sha256=? AND "
                       "IFNULL(original_sha256,'')=IFNULL(?,'')",
                       (project,requirement,origin,digest,original_sha)).fetchone()
        if row:return row[0]
        cid="assetcand_"+uuid4().hex
        db.execute("INSERT INTO asset_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (cid,project,requirement,origin,body,digest,original_sha,mime,size,"CANDIDATE",0))
        return cid
    def search(self,project,requirement,query,adapter,cursor=None,page_size=20):
        self._requirement(project,requirement)
        from backend.app.archives.interfaces import digest
        from backend.app.archives.interfaces import digest
        inner=None
        if cursor:
            try:
                token=json.loads(cursor)
                if (token["project"]!=project or token["requirement"]!=requirement or
                        token["provider"]!=adapter.provider or token["query_sha256"]!=digest(query)):
                    raise ValueError("scope")
                inner=token["inner"]
            except (ValueError,TypeError,KeyError):
                raise ContractViolation("ARCHIVE_CURSOR_MISMATCH",requirement,
                                        "Cursor belongs to another project, requirement or query.")
        result=adapter.search(query,inner,page_size)
        continuation=(json.dumps({"project":project,"requirement":requirement,
                      "provider":adapter.provider,"query_sha256":digest(query),
                      "inner":result["next_cursor"]},separators=(",",":"),sort_keys=True)
                      if result["next_cursor"] else None)
        with self.store._transaction() as db:
            ids=[self._save(db,project,requirement,x) for x in result["candidates"]]
            db.execute("INSERT INTO archive_discovery VALUES(?,?,?,?,?,?) ON CONFLICT"
                       "(project_id,requirement_id,provider,query_sha) DO UPDATE SET "
                       "next_cursor=excluded.next_cursor,candidate_ids_json=excluded.candidate_ids_json",
                       (project,requirement,adapter.provider,digest(query),continuation,json.dumps(ids)))
        return {"candidate_ids":ids,"next_cursor":continuation}
    def get(self,project,candidate_id):
        self.store.revision(project)
        with self.store._connection() as db:
            row=db.execute("SELECT metadata_json,original_sha256,mime_type,byte_count FROM "
                           "asset_candidates WHERE project_id=? AND candidate_id=?",
                           (project,candidate_id)).fetchone()
        if not row: raise ContractViolation("ASSET_CANDIDATE_NOT_FOUND",candidate_id,"Not this project's candidate.")
        return {**json.loads(row[0]),"candidate_id":candidate_id,"original_sha256":row[1],
                "mime_type":row[2],"byte_count":row[3],"user_approved":False}
    def hydrate(self,project,requirement,adapter,item_id):
        self._requirement(project,requirement)
        metadata=adapter.hydrate(item_id)
        with self.store._transaction() as db:
            cid=self._save(db,project,requirement,metadata)
        return self.get(project,cid)
    def original(self,project,requirement,candidate_id,client=None):
        self._requirement(project,requirement)
        metadata=self.get(project,candidate_id)
        if metadata["provider"] not in ("wikimedia_commons","loc","europeana"):
            raise ContractViolation("ORIGINAL_NOT_VERIFIED","candidate","Must originate from an archive.")
        if metadata["provider"]=="europeana" and not metadata.get("hydrated"):
            raise ContractViolation("SOURCE_HYDRATION_REQUIRED","candidate",
                                    "Europeana Record hydration required before original intake.")
        original,info,url=download(metadata,client)
        stored=self.store.put_artifact(original,"original")
        raw={k:v for k,v in metadata.items() if k not in
             ("candidate_id","original_sha256","mime_type","byte_count")}
        raw["actual_download_url"]=url
        with self.store._transaction() as db:
            cid=self._save(db,project,requirement,raw,stored,info["mime_type"],len(original))
        return self.get(project,cid)
    def manual(self,project,requirement,data,title,source_note,rights_note):
        self._requirement(project,requirement)
        if not all(isinstance(x,str) and x.strip() for x in (title,source_note,rights_note)):
            raise ContractViolation("MANUAL_EVIDENCE_REQUIRED","manual","Title, source and rights notes required.")
        info=inspect(data)
        original=self.store.put_artifact(data,"original")
        metadata=dict(provider="manual_upload",title=title,creator=None,creation_date=None,
                      source_page_url=None,original_download_url=None,thumbnail_url=None,
                      rights_statement=rights_note,rights_status="REVIEW_REQUIRED",
                      historical_exactness="UNREVIEWED",historical_context_note=source_note,
                      review_status="CANDIDATE",user_approved=False,asset_class="USER_SUPPLIED")
        with self.store._transaction() as db:
            cid=self._save(db,project,requirement,metadata,original,info["mime_type"],len(data))
        return self.get(project,cid)
