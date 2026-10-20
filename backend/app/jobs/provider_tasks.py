"""A3-03 durable one-task G-Labs lifecycle on existing SQLite JobQueue.

A3-04 must supply managed-fallback authorization before live generation can be connected.
Controlled offline tests can exercise the paid boundary with explicit mock authorization.
"""
import json
import uuid
from hashlib import sha256
from backend.app.contracts import ContractViolation
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.providers.glabs import validate_request, GLabs

class GTaskService:
    def __init__(self,store,queue,provider=None):
        self.store,self.queue=store,queue
        self.provider=provider or GLabs()
        self.assets=AssetCandidates(store)
    def enqueue(self,project,requirement,model,prompt,ratio="16:9",refs=None,upscale=(),
                mode=None,keep=1,*,expected_revision,idempotency_key,controlled_offline=False):
        self.assets._requirement(project,requirement)
        # No A3-04 fallback authorization ledger exists yet. Never bill by default.
        if not controlled_offline:
            raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",requirement,
                                    "A3-04 operator managed-fallback authorization is not implemented.")
        if not getattr(self.provider,"offline_fixture",False):
            raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",requirement,
                                    "Controlled tests require an explicit offline provider boundary.")
        body=validate_request(prompt,model,ratio,refs or [],upscale,mode,keep)
        payload={"requirement_id":requirement,"request":body,
                 "request_sha256":sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
                 "authorization":"CONTROLLED_OFFLINE_FIXTURE"}
        return self.queue.submit(project,"glabs_image",idempotency_key,payload,expected_revision)
    def process_one(self,job_id=None):
        job=self.queue.claim("glabs_image",job_id=job_id)
        if not job: return None
        try:
            if job["resume_only"] and not job["provider_task_id"]:
                raise ContractViolation("GLABS_UNCERTAIN_SUBMISSION",job["job_id"],
                                        "Do not resubmit an uncertain paid generation.")
            data=json.loads(job["payload_json"])
            if data.get("authorization")!="CONTROLLED_OFFLINE_FIXTURE" or not getattr(self.provider,"offline_fixture",False):
                raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",job["job_id"],"A3-04 authorization required.")
            if not job["provider_task_id"]:
                tid=self.provider.submit(data["request"])
                self.queue.attach_provider_task(job["job_id"],job["lease_token"],tid)
                job=self.queue.get(job["job_id"])
            return self.poll(job["job_id"],job["lease_token"])
        except ContractViolation as exc:
            return self.queue.fail(job["job_id"],job["lease_token"],exc.code,
                                   retryable=exc.code in ("GLABS_RATE_LIMITED",))
        except Exception:
            return self.queue.fail(job["job_id"],job["lease_token"],"GLABS_OPERATION_UNCERTAIN",False)
    def poll(self,job_id,token):
        with self.store._connection() as db:
            job=self.queue._owned(db,job_id,token)
        if job["kind"]!="glabs_image" or not job["provider_task_id"]:
            raise ContractViolation("GLABS_TASK_ID_MISSING",job_id,"No submitted provider task.")
        if job["cancel_requested"]:
            raise ContractViolation("JOB_CANCEL_PENDING",job_id,"Task cancelled; confirm stop first.")
        try:
            status=self.provider.poll(job["provider_task_id"])
            if status["status"]!="completed":
                return self.queue.get(job_id)
            files=self.provider.result(job["provider_task_id"])
            payload=json.loads(job["payload_json"])
            digests=[]
            for raw,info in files:
                digests.append((self.store.put_artifact(raw,"original"),info))
            with self.store._transaction() as db:
                owned=self.queue._owned(db,job_id,token)
                if owned["cancel_requested"]:
                    raise ContractViolation("JOB_CANCEL_PENDING",job_id,"Cancellation pending; no publish.")
                row=db.execute("SELECT revision FROM projects WHERE project_id=?",
                               (job["project_id"],)).fetchone()
                self.assets._requirement(job["project_id"],payload["requirement_id"])
                for digest,info in digests:
                    metadata=dict(provider="glabs_webhook",item_id=job["provider_task_id"],
                        title="AI generated illustration candidate",asset_class="AI_ILLUSTRATION",
                        source_page_url=None,original_download_url=None,
                        rights_statement=None,rights_status="REVIEW_REQUIRED",
                        historical_exactness="UNREVIEWED",provenance_status="CANDIDATE",
                        request_sha256=payload["request_sha256"],model=payload["request"]["model"],
                        aspect_ratio=payload["request"]["aspect_ratio"],reference_hashes=[
                        sha256(x.encode()).hexdigest() for x in payload["request"]["reference_images"]],
                        provider_task_id=job["provider_task_id"],user_approved=False)
                    self.assets._save(db,job["project_id"],payload["requirement_id"],metadata,
                                      digest,info["mime_type"],info["byte_count"])
                db.execute("UPDATE jobs SET state='SUCCEEDED',output_sha256=?,lease_token=NULL,"
                           "error_code=NULL WHERE job_id=? AND lease_token=? AND state='RUNNING'",
                           (digests[0][0],job_id,token))
            return self.queue.get(job_id)
        except ContractViolation as exc:
            return self.queue.fail(job_id,token,exc.code,retryable=exc.code=="GLABS_RATE_LIMITED")
    def cancel(self,project,job_id):
        job=self.queue.get(job_id)
        if job["project_id"]!=project or job["kind"]!="glabs_image":
            raise ContractViolation("GLABS_TASK_NOT_FOUND",job_id,"Not this project's generation.")
        if job["state"] in ("SUCCEEDED","CANCELLED","FAILED_TERMINAL"):
            return job
        flagged=self.queue.cancel(job_id)
        if job["provider_task_id"] and job["state"]=="RUNNING":
            self.provider.stop(job["provider_task_id"])
            return self.queue.acknowledge_cancel(job_id,job["lease_token"],provider_confirmed=True)
        return flagged
