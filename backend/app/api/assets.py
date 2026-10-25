"""A3-04/05 local asset HTTP API. Review and provider credentials are operator-owned."""
from __future__ import annotations
import base64
import binascii
import os
import hashlib
from fastapi import Header, BackgroundTasks
from fastapi.responses import Response
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

class ChoiceSetReview(Input):
    expected_revision: int = Field(ge=0)
    slot_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,63}$")
    reviews: list[Review] = Field(min_length=2, max_length=25)
    operator_reason: str = Field(min_length=8, max_length=2000)

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

class Hydrate(Input):
    expected_revision: int = Field(ge=0)
    candidate_id: str

class Generation(Input):
    expected_revision: int = Field(ge=0)
    requirement_id: str
    model: str
    prompt: str = Field(min_length=1)
    aspect_ratio: str = "16:9"

class Settings(Input):
    provider: str
    api_key: str | None = None
    base_url: str = ""
    clear_key: bool = False

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
        if body.provider not in ("glabs_webhook","europeana"):
            raise ContractViolation("PROVIDER_SETTINGS_INVALID",body.provider,"Supported providers: Europeana and G-Labs.")
        if body.clear_key and body.api_key:
            raise ContractViolation("PROVIDER_SETTINGS_INVALID",body.provider,
                                    "Explicit clear cannot also rotate the key.")
        if body.provider=="glabs_webhook":
            GLabs(base_url=body.base_url or "http://127.0.0.1:8765")
        elif body.base_url:
            raise ContractViolation("PROVIDER_SETTINGS_INVALID","europeana","Europeana endpoint is fixed.")
        # Journal only hashed credential inputs, never a raw secret.
        digest=__import__("hashlib").sha256((body.api_key or "").encode()).hexdigest()
        journal={"provider":body.provider,"key_digest":digest,
                 "base_url":body.base_url,"clear_key":body.clear_key}
        def action():
            with store._transaction() as db:
                row=db.execute("SELECT api_key,base_url FROM local_provider_settings WHERE provider=?",
                               (body.provider,)).fetchone()
                existing_key=row[0] if row else (os.getenv("HVS_GLABS_API_KEY","") if body.provider=="glabs_webhook"
                                                 else os.getenv("HVS_EUROPEANA_API_KEY",""))
                secret=("" if body.clear_key else body.api_key or existing_key)
                old_base=row[1] if row else os.getenv("HVS_GLABS_BASE_URL","")
                base=body.base_url or (old_base if body.provider=="glabs_webhook" else "")
                db.execute("INSERT INTO local_provider_settings VALUES(?,?,?) "
                           "ON CONFLICT(provider) DO UPDATE SET api_key=excluded.api_key,base_url=excluded.base_url",
                           (body.provider,secret,base))
            return {"provider":body.provider,"configured":bool(secret),
                    "live_status":"NOT_RUN"}
        return idempotent("__local_provider_settings__","provider-settings:"+body.provider,
                          key,journal,action)

    def stored_provider_key(name):
        with store._connection() as db:
            row=db.execute("SELECT api_key,base_url FROM local_provider_settings WHERE provider=?",
                           (name,)).fetchone()
        if row:
            return row  # An explicitly cleared key must not silently fall back to env.
        if name=="glabs_webhook":
            return (os.getenv("HVS_GLABS_API_KEY"),os.getenv("HVS_GLABS_BASE_URL"))
        if name=="europeana":
            return (os.getenv("HVS_EUROPEANA_API_KEY"),None)
        return (None,None)

    def cancel_glabs(project_id,job_id):
        secret,base=stored_provider_key("glabs_webhook")
        return GTaskService(store,queue,GLabs(base_url=base or None,api_key=secret)).cancel(project_id,job_id)
    app.state.cancel_glabs=cancel_glabs

    def retry_glabs(project_id,job_id):
        secret,base=stored_provider_key("glabs_webhook")
        return GTaskService(store,queue,GLabs(base_url=base or None,api_key=secret)).retry(project_id,job_id)
    app.state.retry_glabs=retry_glabs

    @app.post("/api/v1/projects/{project_id}/jobs/{job_id}/retry")
    def retry_job(project_id:str,job_id:str,background:BackgroundTasks,
                  key:str=Header(alias="Idempotency-Key")):
        result=idempotent(project_id,"glabs-retry:"+job_id,key,{"job_id":job_id},
                           lambda:retry_glabs(project_id,job_id))
        if result["state"]=="QUEUED":
            background.add_task(run_glabs_job,job_id)
        return result

    @app.post("/api/v1/projects/{project_id}/jobs/{job_id}/cancel")
    def cancel_project_job(project_id:str,job_id:str,key:str=Header(alias="Idempotency-Key")):
        return idempotent(project_id,"glabs-cancel:"+job_id,key,{"job_id":job_id},
                          lambda:cancel_glabs(project_id,job_id))

    def run_glabs_job(job_id):
        secret,base=stored_provider_key("glabs_webhook")
        if not secret:
            return None  # Do not fail a resumable task merely because credentials are unavailable.
        return GTaskService(store,queue,GLabs(base_url=base or None,api_key=secret)).run_until_terminal(job_id)
    app.state.run_glabs_job=run_glabs_job

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

    @app.post("/api/v1/projects/{project_id}/assets/{requirement_id}/hydrate")
    def hydrate_record(project_id:str,requirement_id:str,body:Hydrate,
                       key:str=Header(alias="Idempotency-Key")):
        def action():
            with store._connection() as db:
                resolver._revision(db,project_id,body.expected_revision)
                source=assets._source_tx(db,project_id,requirement_id)
                chosen=assets._owned_tx(db,project_id,requirement_id,body.candidate_id)
                assets._assert_source(source,{"project_id":project_id,
                    "story_sha256":chosen.get("source_story_sha256"),
                    "story_revision":chosen.get("source_story_revision"),
                    "requirement_sha256":chosen.get("source_requirement_sha256")})
                if chosen.get("provider")!="europeana" or chosen.get("hydrated"):
                    raise ContractViolation("SOURCE_HYDRATION_REQUIRED",body.candidate_id,
                                            "Select an unhydrated Europeana search candidate.")
                item_id=chosen.get("item_id")
            api_key,_=stored_provider_key("europeana")
            return assets.hydrate(project_id,requirement_id,Europeana(key=api_key),item_id,
                                  candidate_id=body.candidate_id,frozen_source=source)
        return idempotent(project_id,"asset-hydrate:"+requirement_id,key,body.model_dump(),action)

    @app.get("/api/v1/projects/{project_id}/assets/{requirement_id}/candidates/{candidate_id}/original-preview")
    def original_preview(project_id:str,requirement_id:str,candidate_id:str):
        with store._connection() as db:
            current=assets._source_tx(db,project_id,requirement_id)
            chosen=assets._owned_tx(db,project_id,requirement_id,candidate_id)
            assets._assert_source(current,{"project_id":project_id,
                "story_sha256":chosen.get("source_story_sha256"),
                "story_revision":chosen.get("source_story_revision"),
                "requirement_sha256":chosen.get("source_requirement_sha256")})
        sha=chosen.get("original_sha256")
        if not sha:
            raise ContractViolation("ORIGINAL_NOT_VERIFIED",candidate_id,
                                    "Hydrate and download the exact original before reviewing.")
        raw=store.get_artifact(sha)
        if hashlib.sha256(raw).hexdigest()!=sha:
            raise ContractViolation("ARTIFACT_SHA_MISMATCH",candidate_id,
                                    "Stored original does not match its immutable SHA.")
        from backend.app.assets.download import inspect
        media=inspect(raw)["mime_type"]
        if media not in ("image/png","image/jpeg","image/webp") or media!=chosen["mime_type"]:
            raise ContractViolation("ORIGINAL_MIME_INVALID",candidate_id,
                                    "Only a verified original image can be previewed.")
        return Response(raw,media_type=media,headers={
            "Cache-Control":"no-store","X-Content-Type-Options":"nosniff",
            "Content-Security-Policy":"default-src 'none'"})

    @app.post("/api/v1/projects/{project_id}/assets/{requirement_id}/approve")
    def approve(project_id:str,requirement_id:str,body:Approval,
                key:str=Header(alias="Idempotency-Key")):
        if body.review.requirement_id!=requirement_id:
            raise ContractViolation("ASSET_REQUIREMENT_MISMATCH",requirement_id,"Review requirement differs from route.")
        return idempotent(project_id,"asset-approve:"+requirement_id,key,body.model_dump(),
             lambda:resolver.approve_batch(project_id,[body.review.model_dump()],body.expected_revision))

    @app.get("/api/v1/projects/{project_id}/assets/{requirement_id}/choice-sets/{slot_id}")
    def current_choice_set(project_id:str,requirement_id:str,slot_id:str):
        return resolver.current_choice_set(project_id,requirement_id,slot_id)

    @app.post("/api/v1/projects/{project_id}/assets/{requirement_id}/choice-sets/review")
    def review_choice_set(project_id:str,requirement_id:str,body:ChoiceSetReview,
                          key:str=Header(alias="Idempotency-Key")):
        return idempotent(project_id,"g3-choice-set:"+requirement_id+":"+body.slot_id,
                          key,body.model_dump(),
                          lambda:resolver.review_choice_set(project_id,requirement_id,body.slot_id,
                              [r.model_dump() for r in body.reviews],
                              body.operator_reason,body.expected_revision))

    @app.post("/api/v1/projects/{project_id}/assets/batch-approve")
    def batch_approve(project_id:str,body:Batch,key:str=Header(alias="Idempotency-Key")):
        return idempotent(project_id,"asset-batch",key,body.model_dump(),
            lambda:resolver.approve_batch(project_id,[x.model_dump() for x in body.reviews],body.expected_revision))

    @app.post("/api/v1/projects/{project_id}/assets/generate")
    def generate(project_id:str,body:Generation,background:BackgroundTasks,key:str=Header(alias="Idempotency-Key")):
        k,base=stored_provider_key("glabs_webhook")
        service=GTaskService(store,queue,GLabs(base_url=base or None,api_key=k))
        job=service.enqueue(project_id,body.requirement_id,body.model,body.prompt,
                            body.aspect_ratio,expected_revision=body.expected_revision,
                            idempotency_key=key)
        # Worker runs only after the durable queue transaction; restart preserves provider identity.
        background.add_task(service.run_until_terminal,job["job_id"])
        return {"job_id":job["job_id"],"state":job["state"],"project_revision":store.revision(project_id)}
