"""A3-04/05 local asset HTTP API. Review and provider credentials are operator-owned."""
from __future__ import annotations
import base64
import binascii
import os
from fastapi import Header
from pydantic import BaseModel, ConfigDict, Field
from backend.app.contracts import ContractViolation
from backend.app.assets.resolution import AssetResolution
from backend.app.assets.provenance import AssetCandidates
from backend.app.archives.wikimedia import Wikimedia
from backend.app.archives.loc import LOC
from backend.app.archives.europeana import Europeana
from backend.app.jobs.provider_tasks import GTaskService
from backend.app.assets.providers.glabs import GLabs

class Input(BaseModel):
    model_config=ConfigDict(extra="forbid")

class Choice(Input):
    expected_revision: int = Field(ge=0)
    resolution_mode: str
    reason: str = Field(min_length=1)

class Upload(Input):
    expected_revision: int = Field(ge=0)
    data_base64: str
    title: str = Field(min_length=1)
    source_note: str = Field(min_length=1)
    rights_note: str = Field(min_length=1)

class Review(Input):
    requirement_id: str
    candidate_id: str
    original_sha256: str
    rights_status: str
    rights_evidence_note: str = Field(min_length=1)
    historical_context_note: str = Field(min_length=1)

class Approval(Input):
    expected_revision: int = Field(ge=0)
    review: Review

class Batch(Input):
    expected_revision: int = Field(ge=0)
    reviews: list[Review] = Field(min_length=1, max_length=100)

class Search(Input):
    expected_revision: int = Field(ge=0)
    requirement_id: str
    provider: str
    query: str = Field(min_length=1)
    cursor: str | None = None

class Original(Input):
    expected_revision: int = Field(ge=0)
    requirement_id: str
    candidate_id: str

class Generation(Input):
    expected_revision: int = Field(ge=0)
    requirement_id: str
    model: str
    prompt: str = Field(min_length=1)
    aspect_ratio: str = "16:9"

class Settings(Input):
    provider: str
    api_key: str = ""
    base_url: str = ""

def mount(app, store, gates, queue, idempotent):
    assets=AssetCandidates(store)
    resolver=AssetResolution(store)
    app.state.assets=resolver
    with store._connection() as db:
        db.executescript("""CREATE TABLE IF NOT EXISTS local_provider_settings(
            provider TEXT PRIMARY KEY, api_key TEXT NOT NULL, base_url TEXT NOT NULL);
        """)

    def providers():
        with store._connection() as db:
            rows={x[0]:(bool(x[1]),x[2]) for x in db.execute(
                "SELECT provider,api_key,base_url FROM local_provider_settings")}
        return [{"provider":name,"configured":rows.get(name,(bool(os.getenv(env)),''))[0],
                 "base_url":rows.get(name,('', ''))[1] if name=="glabs_webhook" else "",
                 "live_status":"NOT_RUN"}
                for name,env in (("glabs_webhook","HVS_GLABS_API_KEY"),
                                 ("europeana","HVS_EUROPEANA_API_KEY"),
                                 ("wikimedia_commons",""),("loc",""))]

    @app.get("/api/v1/providers")
    def provider_info():
        return {"providers":providers(), "live_status":"NOT_RUN"}

    @app.put("/api/v1/providers/settings")
    def provider_settings(body: Settings, key: str=Header(alias="Idempotency-Key")):
        if len(key)<12:
            raise ContractViolation("IDEMPOTENCY_KEY_INVALID","provider","Provide a unique request key.")
        if body.provider not in ("glabs_webhook","europeana"):
            raise ContractViolation("PROVIDER_SETTINGS_INVALID",body.provider,"Supported providers: Europeana and G-Labs.")
        if body.provider=="glabs_webhook":
            GLabs(base_url=body.base_url or "http://127.0.0.1:8765",api_key=body.api_key)
        elif body.base_url:
            raise ContractViolation("PROVIDER_SETTINGS_INVALID","europeana","Europeana endpoint is fixed.")
        with store._transaction() as db:
            db.execute("INSERT INTO local_provider_settings VALUES(?,?,?) "
                       "ON CONFLICT(provider) DO UPDATE SET api_key=excluded.api_key,base_url=excluded.base_url",
                       (body.provider,body.api_key,body.base_url))
        return {"provider":body.provider,"configured":bool(body.api_key),"live_status":"NOT_RUN"}

    def stored_provider_key(name):
        with store._connection() as db:
            row=db.execute("SELECT api_key,base_url FROM local_provider_settings WHERE provider=?",
                           (name,)).fetchone()
        return row if row else (None,None)

    @app.get("/api/v1/projects/{project_id}/assets/requirements")
    def requirements(project_id:str):
        return resolver.requirements(project_id)

    @app.get("/api/v1/projects/{project_id}/assets/{requirement_id}/candidates")
    def candidates(project_id:str,requirement_id:str):
        return resolver.candidates(project_id,requirement_id)

    @app.post("/api/v1/projects/{project_id}/assets/{requirement_id}/resolve")
    def resolve(project_id:str,requirement_id:str,body:Choice,
                key:str=Header(alias="Idempotency-Key")):
        return idempotent(project_id,"asset-choice:"+requirement_id,key,body.model_dump(),
            lambda:resolver.choose(project_id,requirement_id,body.resolution_mode,
                                   body.reason,body.expected_revision))

    @app.post("/api/v1/projects/{project_id}/assets/{requirement_id}/upload")
    def upload(project_id:str,requirement_id:str,body:Upload,
               key:str=Header(alias="Idempotency-Key")):
        def action():
            if store.revision(project_id)!=body.expected_revision:
                raise ContractViolation("REVISION_CONFLICT",project_id,"Reload project.")
            with store._connection() as db:
                source=assets._source_tx(db,project_id,requirement_id)
                choice=resolver._choice(db,project_id,requirement_id,source["requirement_sha256"])
            if not choice or choice["mode"]!="MANUAL_UPLOAD":
                raise ContractViolation("ASSET_RESOLUTION_REQUIRED",requirement_id,"Select manual upload first.")
            try:
                binary=base64.b64decode(body.data_base64,validate=True)
            except (ValueError,binascii.Error) as exc:
                raise ContractViolation("ASSET_UPLOAD_INVALID",requirement_id,"Expected base64 image.") from exc
            if len(binary)>20*1024*1024:
                raise ContractViolation("ORIGINAL_SIZE_INVALID",requirement_id,"Upload must be under 20 MB.")
            result=assets.manual(project_id,requirement_id,binary,body.title,body.source_note,body.rights_note)
            return {"candidate":result,"project_revision":store.revision(project_id)}
        return idempotent(project_id,"asset-upload:"+requirement_id,key,
                          {**body.model_dump(exclude={"data_base64"}),"content_sha256":__import__('hashlib').sha256(body.data_base64.encode()).hexdigest()},
                          action)

    @app.post("/api/v1/projects/{project_id}/assets/search")
    def archive_search(project_id:str,body:Search,key:str=Header(alias="Idempotency-Key")):
        def action():
            if store.revision(project_id)!=body.expected_revision:
                raise ContractViolation("REVISION_CONFLICT",project_id,"Reload project.")
            if body.provider=="wikimedia_commons":adapter=Wikimedia()
            elif body.provider=="loc":adapter=LOC()
            elif body.provider=="europeana":
                secret,_=stored_provider_key("europeana")
                adapter=Europeana(key=secret)
            else:raise ContractViolation("ASSET_SOURCE_INVALID",body.provider,"Choose a known archive.")
            return assets.search(project_id,body.requirement_id,body.query,adapter,body.cursor)
        return idempotent(project_id,"asset-search",key,body.model_dump(),action)

    @app.post("/api/v1/projects/{project_id}/assets/original")
    def original(project_id:str,body:Original,key:str=Header(alias="Idempotency-Key")):
        def action():
            if store.revision(project_id)!=body.expected_revision:
                raise ContractViolation("REVISION_CONFLICT",project_id,"Reload project.")
            return assets.original(project_id,body.requirement_id,body.candidate_id)
        return idempotent(project_id,"asset-original",key,body.model_dump(),action)

    @app.post("/api/v1/projects/{project_id}/assets/{requirement_id}/approve")
    def approve(project_id:str,requirement_id:str,body:Approval,
                key:str=Header(alias="Idempotency-Key")):
        if body.review.requirement_id!=requirement_id:
            raise ContractViolation("ASSET_REQUIREMENT_MISMATCH",requirement_id,"Review requirement differs from route.")
        return idempotent(project_id,"asset-approve:"+requirement_id,key,body.model_dump(),
             lambda:resolver.approve_batch(project_id,[body.review.model_dump()],body.expected_revision))

    @app.post("/api/v1/projects/{project_id}/assets/batch-approve")
    def batch_approve(project_id:str,body:Batch,key:str=Header(alias="Idempotency-Key")):
        return idempotent(project_id,"asset-batch",key,body.model_dump(),
            lambda:resolver.approve_batch(project_id,[x.model_dump() for x in body.reviews],body.expected_revision))

    @app.post("/api/v1/projects/{project_id}/assets/generate")
    def generate(project_id:str,body:Generation,key:str=Header(alias="Idempotency-Key")):
        k,base=stored_provider_key("glabs_webhook")
        service=GTaskService(store,queue,GLabs(base_url=base or None,api_key=k))
        job=service.enqueue(project_id,body.requirement_id,body.model,body.prompt,
                            body.aspect_ratio,expected_revision=body.expected_revision,
                            idempotency_key=key)
        # Don't perform paid generation inline with a request; persistent queue worker owns submission.
        return {"job_id":job["job_id"],"state":job["state"],"project_revision":store.revision(project_id)}
