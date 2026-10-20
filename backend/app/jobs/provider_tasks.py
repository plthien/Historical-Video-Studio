"""A3-03 durable one-task G-Labs lifecycle on existing SQLite JobQueue.

A3-04 must supply managed-fallback authorization before live generation can be connected.
Controlled offline tests can exercise the paid boundary with explicit mock authorization.
"""
import json
from hashlib import sha256
from backend.app.contracts import ContractViolation
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.providers.glabs import validate_request, GLabs

class GTaskService:
    def __init__(self,store,queue,provider=None):
        self.store,self.queue=store,queue
        self.provider=provider or GLabs()
        self.assets=AssetCandidates(store)
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS glabs_task_observations(
                    job_id TEXT PRIMARY KEY, provider_status TEXT NOT NULL,
                    last_error_code TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id));
            """)
    def _observe(self,job_id,status,error=None):
        with self.store._transaction() as db:
            db.execute("INSERT INTO glabs_task_observations VALUES(?,?,?) "
                       "ON CONFLICT(job_id) DO UPDATE SET provider_status=excluded.provider_status, "
                       "last_error_code=excluded.last_error_code",(job_id,status,error))
    def _current_source(self,db,job,payload):
        """Compare frozen StoryPackage + requirement under the caller's SQLite transaction."""
        if job["project_id"]!=payload.get("project_id"):
            raise ContractViolation("GLABS_SOURCE_STALE",job["job_id"],"Project identity changed.")
        try:
            current=self.assets._source_tx(db,job["project_id"],payload["requirement_id"])
        except (ContractViolation,KeyError) as exc:
            raise ContractViolation("GLABS_SOURCE_STALE",job["job_id"],
                                    "Original source requirement no longer exists.") from exc
        if any(current[k]!=payload.get(k) for k in
               ("story_sha256","story_revision","requirement_sha256")):
            raise ContractViolation("GLABS_SOURCE_STALE",job["job_id"],
                                    "Source changed; do not publish or resubmit paid work.")
        return current

    def enqueue(self,project,requirement,model,prompt,ratio="16:9",refs=None,upscale=(),
                mode=None,keep=1,*,expected_revision,idempotency_key,controlled_offline=False):
        source=self.assets._requirement(project,requirement)
        if source["project_revision"]!=expected_revision:
            raise ContractViolation("REVISION_CONFLICT",project,
                                    "Reload the project before queueing source-bound generation.")
        # No A3-04 fallback authorization ledger exists yet. Never bill by default.
        if not controlled_offline:
            raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",requirement,
                                    "A3-04 operator managed-fallback authorization is not implemented.")
        if not getattr(self.provider,"offline_fixture",False):
            raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",requirement,
                                    "Controlled tests require an explicit offline provider boundary.")
        body=validate_request(prompt,model,ratio,refs or [],upscale,mode,keep)
        payload={"project_id":project,"requirement_id":requirement,
                 "story_sha256":source["story_sha256"],
                 "story_revision":source["story_revision"],
                 "requirement_sha256":source["requirement_sha256"],
                 "request":body,
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
                # This check is immediately before a potentially billable network request.
                with self.store._connection() as db:
                    owned=self.queue._owned(db,job["job_id"],job["lease_token"])
                    if owned["cancel_requested"]:
                        raise ContractViolation("JOB_CANCEL_PENDING",job["job_id"],
                                                "Cancelled before provider submission.")
                    self._current_source(db,owned,data)
                tid=self.provider.submit(data["request"])
                self.queue.attach_provider_task(job["job_id"],job["lease_token"],tid)
                job=self.queue.get(job["job_id"])
                self._observe(job["job_id"],"pending")
            return self.poll(job["job_id"],job["lease_token"])
        except ContractViolation as exc:
            if exc.code=="GLABS_SOURCE_STALE":
                self._observe(job["job_id"],"not_submitted",exc.code)
            current=self.queue.get(job["job_id"])
            # A rejected/uncertain first POST must never be automatically reissued.
            retryable=(bool(current["provider_task_id"]) and
                       exc.code in ("GLABS_RATE_LIMITED","GLABS_NETWORK_ERROR"))
            return self.queue.fail(job["job_id"],job["lease_token"],exc.code,
                                   retryable=retryable)
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
            self._observe(job_id,status["status"])
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
                self._current_source(db,owned,payload)
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
                db.execute("INSERT INTO glabs_task_observations VALUES(?,?,NULL) "
                           "ON CONFLICT(job_id) DO UPDATE SET provider_status='completed',last_error_code=NULL",
                           (job_id,"completed"))
                db.execute("UPDATE jobs SET state='SUCCEEDED',output_sha256=?,lease_token=NULL,"
                           "error_code=NULL WHERE job_id=? AND lease_token=? AND state='RUNNING'",
                           (digests[0][0],job_id,token))
            return self.queue.get(job_id)
        except ContractViolation as exc:
            if exc.code=="STOPPED_BY_CLIENT":
                self.queue.cancel(job_id)
                self._observe(job_id,"failed","STOPPED_BY_CLIENT")
                return self.queue.acknowledge_cancel(job_id,token,provider_confirmed=True)
            if exc.code=="GLABS_SOURCE_STALE":
                # Provider completed successfully; only Studio publication is stale.
                self._observe(job_id,"completed",exc.code)
            elif exc.code in ("GLABS_RATE_LIMITED","GLABS_NETWORK_ERROR"):
                # A transient HTTP failure does not make the remote task terminal.
                with self.store._connection() as db:
                    row=db.execute("SELECT provider_status FROM glabs_task_observations "
                                   "WHERE job_id=?",(job_id,)).fetchone()
                self._observe(job_id,row[0] if row else "pending",exc.code)
            else:
                self._observe(job_id,"failed",exc.code)
            return self.queue.fail(job_id,token,exc.code,
                                   retryable=exc.code in ("GLABS_RATE_LIMITED","GLABS_NETWORK_ERROR"))
    def run_until_terminal(self,job_id,*,poll_seconds=3,max_polls=180):
        """Bounded 3–5 second provider polling; resume persisted task, never resubmit."""
        import time
        if max_polls<1 or max_polls>300 or (poll_seconds not in (3,4,5) and
                not (poll_seconds==0 and getattr(self.provider,"offline_fixture",False))):
            raise ContractViolation("GLABS_POLL_SETTINGS_INVALID",job_id,
                                    "Use 3–5s polls and a bounded number of attempts.")
        current=self.process_one(job_id)
        for _ in range(max_polls):
            if current is None or current["state"]!="RUNNING":
                return current
            if poll_seconds: time.sleep(poll_seconds)
            current=self.poll(job_id,current["lease_token"])
        if current is not None and current["state"]=="RUNNING":
            return self.queue.fail(job_id,current["lease_token"],"GLABS_POLL_TIMEOUT",retryable=True)
        return current

    def cancel(self,project,job_id):
        job=self.queue.get(job_id)
        if job["project_id"]!=project or job["kind"]!="glabs_image":
            raise ContractViolation("GLABS_TASK_NOT_FOUND",job_id,"Not this project's generation.")
        if job["state"] in ("SUCCEEDED","CANCELLED","FAILED_TERMINAL"):
            return job
        flagged=self.queue.cancel(job_id)
        if job["provider_task_id"] and job["state"]=="RUNNING":
            self.provider.stop(job["provider_task_id"])
            result=self.queue.acknowledge_cancel(job_id,job["lease_token"],provider_confirmed=True)
            self._observe(job_id,"failed","STOPPED_BY_CLIENT")
            return result
        return flagged
