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
    def _provider_identity(self):
        # Store only a fingerprint of the endpoint+credential, never the API key.
        key=getattr(self.provider,"key","")
        base=getattr(self.provider,"base","")
        if not key or not base:
            raise ContractViolation("GLABS_KEY_MISSING","glabs",
                                    "Configure the original local webhook and API key before enqueue.")
        return sha256((base+"\\n"+key).encode("utf-8")).hexdigest()

    def _assert_job_provider(self,job,payload):
        if payload.get("authorization")=="MANAGED_FALLBACK_AUTHORIZED":
            actual=self._provider_identity()
            if payload.get("provider_identity")!=actual:
                raise ContractViolation("GLABS_PROVIDER_IDENTITY_STALE",job["job_id"],
                    "Webhook endpoint/key changed; restore original job credentials before continuing.")

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
        if controlled_offline:
            if not getattr(self.provider,"offline_fixture",False):
                raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",requirement,
                                        "Controlled tests require an explicit offline provider boundary.")
            authorization="CONTROLLED_OFFLINE_FIXTURE"
        else:
            if getattr(self.provider,"offline_fixture",False):
                raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",requirement,
                                        "Mock providers cannot impersonate managed authorization.")
            from backend.app.projects.gates import GateService
            if GateService(self.store).board(project)[0]["state"]!="APPROVED":
                raise ContractViolation("G1_APPROVAL_REQUIRED",requirement,
                                        "Approve current G1 critical evidence before any paid provider call.")
            from backend.app.assets.resolution import AssetResolution
            with self.store._connection() as db:
                choice=AssetResolution._choice(db,project,requirement,source["requirement_sha256"])
            if not choice or choice["mode"]!="MANAGED_FALLBACK" or not choice["operator_authorized"]:
                raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",requirement,
                                        "Operator must explicitly select managed fallback.")
            authorization="MANAGED_FALLBACK_AUTHORIZED"
        body=validate_request(prompt,model,ratio,refs or [],upscale,mode,keep)
        provider_identity=self._provider_identity() if not controlled_offline else None
        payload={"project_id":project,"requirement_id":requirement,
                 "story_sha256":source["story_sha256"],
                 "story_revision":source["story_revision"],
                 "requirement_sha256":source["requirement_sha256"],
                 "request":body,
                 "request_sha256":sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
                 "authorization":authorization,
                 "provider_identity":provider_identity}
        return self.queue.submit(project,"glabs_image",idempotency_key,payload,expected_revision)
    def process_one(self,job_id=None):
        job=self.queue.claim("glabs_image",job_id=job_id)
        if not job: return None
        try:
            if job["resume_only"] and not job["provider_task_id"]:
                raise ContractViolation("GLABS_UNCERTAIN_SUBMISSION",job["job_id"],
                                        "Do not resubmit an uncertain paid generation.")
            data=json.loads(job["payload_json"])
            if data.get("authorization")=="CONTROLLED_OFFLINE_FIXTURE":
                if not getattr(self.provider,"offline_fixture",False):
                    raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",job["job_id"],"Offline task requires mock provider.")
            elif data.get("authorization")=="MANAGED_FALLBACK_AUTHORIZED":
                if getattr(self.provider,"offline_fixture",False):
                    raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",job["job_id"],"Cannot bill mock fallback.")
            else:
                raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",job["job_id"],"Explicit authorization missing.")
            self._assert_job_provider(job,data)
            if not job["provider_task_id"]:
                # This check is immediately before a potentially billable network request.
                with self.store._connection() as db:
                    owned=self.queue._owned(db,job["job_id"],job["lease_token"])
                    if owned["cancel_requested"]:
                        raise ContractViolation("JOB_CANCEL_PENDING",job["job_id"],
                                                "Cancelled before provider submission.")
                    self._current_source(db,owned,data)
                    if data["authorization"]=="MANAGED_FALLBACK_AUTHORIZED":
                        from backend.app.assets.resolution import AssetResolution
                        choice=AssetResolution._choice(db,owned["project_id"],data["requirement_id"],data["requirement_sha256"])
                        if not choice or choice["mode"]!="MANAGED_FALLBACK" or not choice["operator_authorized"]:
                            raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",job["job_id"],"Fallback authorization changed.")
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
            retryable=(exc.code=="GLABS_PROVIDER_IDENTITY_STALE" or
                       (bool(current["provider_task_id"]) and
                        exc.code in ("GLABS_RATE_LIMITED","GLABS_NETWORK_ERROR")))
            if current["state"] in ("CANCELLED","SUCCEEDED","FAILED_TERMINAL","BLOCKED_REVIEW"):
                return current
            if exc.code=="JOB_LEASE_CONFLICT":
                return current
            return self.queue.fail(job["job_id"],job["lease_token"],exc.code,
                                   retryable=retryable)
        except Exception:
            latest=self.queue.get(job["job_id"])
            if latest["state"] in ("BLOCKED_REVIEW","CANCELLED","SUCCEEDED","FAILED_TERMINAL"):
                return latest
            return self.queue.fail(job["job_id"],job["lease_token"],"GLABS_OPERATION_UNCERTAIN",False)
    def poll(self,job_id,token):
        try:
            with self.store._connection() as db:
                job=self.queue._owned(db,job_id,token)
        except ContractViolation as exc:
            if exc.code=="JOB_LEASE_CONFLICT":
                # Cancel/another worker already decided the durable state.
                return self.queue.get(job_id)
            raise
        if job["kind"]!="glabs_image" or not job["provider_task_id"]:
            raise ContractViolation("GLABS_TASK_ID_MISSING",job_id,"No submitted provider task.")
        if job["cancel_requested"]:
            raise ContractViolation("JOB_CANCEL_PENDING",job_id,"Task cancelled; confirm stop first.")
        try:
            self._assert_job_provider(job,json.loads(job["payload_json"]))
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
                if payload["authorization"]=="MANAGED_FALLBACK_AUTHORIZED":
                    from backend.app.assets.resolution import AssetResolution
                    choice=AssetResolution._choice(db,owned["project_id"],payload["requirement_id"],payload["requirement_sha256"])
                    if not choice or choice["mode"]!="MANAGED_FALLBACK" or not choice["operator_authorized"]:
                        raise ContractViolation("GLABS_FALLBACK_AUTH_REQUIRED",job_id,"Authorization revoked before publication.")
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
            current=self.queue.get(job_id)
            if current["state"]!="RUNNING" or current["lease_token"]!=token:
                # Remote stop/success won while provider polling; preserve CAS result.
                return current
            if exc.code=="STOPPED_BY_CLIENT":
                self.queue.cancel(job_id)
                result=self.queue.confirm_remote_stop(job_id,job["provider_task_id"])
                if result["state"]=="CANCELLED":
                    self._observe(job_id,"failed","STOPPED_BY_CLIENT")
                return result
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
                                   retryable=exc.code in ("GLABS_RATE_LIMITED","GLABS_NETWORK_ERROR",
                                                          "GLABS_PROVIDER_IDENTITY_STALE"))
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

    def _scoped(self,project,job_id):
        job=self.queue.get(job_id)
        if job["project_id"]!=project or job["kind"]!="glabs_image":
            raise ContractViolation("GLABS_TASK_NOT_FOUND",job_id,"Not this project's generation.")
        return job

    def cancel(self,project,job_id):
        job=self._scoped(project,job_id)
        if job["state"] in ("SUCCEEDED","CANCELLED","FAILED_TERMINAL"):
            return job
        # Only this durable pre-submit identity preflight proves that no
        # billable request occurred. Missing provider_task_id alone is unsafe.
        safe=self.queue.cancel_verified_presubmit(job_id)
        if safe is not None:
            return safe
        # QUEUED with a recovered remote ID is remote-owned, not local-only work.
        flagged=self.queue.cancel(job_id)
        if not job["provider_task_id"]:
            if flagged["state"]=="CANCELLED":
                return flagged
            # Worker may have just submitted while we requested cancellation.
            fresh=self.queue.get(job_id)
            if fresh["provider_task_id"]:
                return self.cancel(project,job_id)
            if flagged["state"]=="QUEUED" and flagged["resume_only"]:
                return self.queue.cancellation_uncertain(job_id,"GLABS_UNCERTAIN_SUBMISSION")
            if flagged["state"]=="FAILED_RETRYABLE":
                # No durable proof that this error happened before the paid POST.
                # Preserve the original diagnostic and require operator reconciliation.
                return self.queue.cancellation_uncertain(job_id,
                    flagged["error_code"] or "GLABS_UNCERTAIN_SUBMISSION")
            return flagged
        try:
            self._assert_job_provider(job,json.loads(job["payload_json"]))
            outcome=self.provider.stop(job["provider_task_id"])
            if outcome=="stopped":
                result=self.queue.confirm_remote_stop(job_id,job["provider_task_id"])
                if result["state"]=="CANCELLED":
                    self._observe(job_id,"failed","STOPPED_BY_CLIENT")
                return result
            # Skipped means already finished, not cancelled. Reconcile original task.
            self.queue.reconcile_cancel(job_id)
            fresh=self.queue.get(job_id)
            if fresh["state"]=="RUNNING":
                result=self.poll(job_id,fresh["lease_token"])
            else:
                result=self.process_one(job_id)
            if result and result["state"]=="RUNNING":
                return self.queue.cancellation_uncertain(job_id,"GLABS_STOP_SKIPPED_NOT_TERMINAL")
            return result or self.queue.get(job_id)
        except ContractViolation as exc:
            current=self.queue.get(job_id)
            if current["state"] in ("SUCCEEDED","CANCELLED","FAILED_TERMINAL"):
                return current
            # An unknown stop response or credential rotation must be explicitly reconciled.
            self._observe(job_id,"cancel_unknown",exc.code)
            return self.queue.cancellation_uncertain(job_id,
                     "CANCELLATION_NOT_CONFIRMED" if exc.code!="GLABS_PROVIDER_IDENTITY_STALE" else exc.code)

    def retry(self,project,job_id):
        job=self._scoped(project,job_id)
        if job["state"]!="FAILED_RETRYABLE":
            raise ContractViolation("JOB_RETRY_FORBIDDEN",job_id,
                                    "Only retryable provider jobs can be resumed.")
        payload=json.loads(job["payload_json"])
        self._assert_job_provider(job,payload)
        if job["cancel_requested"]:
            raise ContractViolation("JOB_CANCEL_PENDING",job_id,"Reconcile cancellation first.")
        return self.queue.retry(job_id)
