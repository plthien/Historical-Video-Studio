"""A3-03 task-specific 202/poll/result/stop with durable SQLite and actual PNG."""
import base64
from pathlib import Path
import json
import httpx
import pytest
from backend.app.contracts import ContractViolation
from backend.app.assets.providers.glabs import GLabs, validate_request
from backend.app.jobs.provider_tasks import GTaskService
from backend.app.jobs import JobQueue, recover_interrupted
from backend.app.assets.provenance import AssetCandidates
from backend.app.projects.storage import ProjectStore
from backend.app.projects.models import StoryCandidate

ROOT=Path(__file__).resolve().parents[2]
def _png(red=0):
    import struct,zlib
    def chunk(name,body):
        return struct.pack(">I",len(body))+name+body+struct.pack(">I",zlib.crc32(name+body))
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress(bytes([0,red,10,30])))+chunk(b"IEND",b""))
PNG=_png()

def setup(tmp_path,handler):
    story=json.loads((ROOT/"contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    store=ProjectStore(tmp_path/"db.sqlite",tmp_path/"media")
    project=story["project"]["project_id"]
    store.create_project(project,"G-Labs test")
    store.import_story(StoryCandidate.parse(story),0)
    client=httpx.Client(transport=httpx.MockTransport(handler))
    provider=GLabs(client,api_key="offline-secret")
    provider.offline_fixture=True
    return store,GTaskService(store,JobQueue(store),provider),project,story["asset_requirements"][0]["requirement_id"]

def test_generate_poll_result_restart_no_duplicate_submission(tmp_path):
    calls=[]
    def handler(req):
        calls.append((req.method,req.url.path))
        if req.url.path=="/api/image/generate":
            assert req.headers["X-API-Key"]=="offline-secret"
            assert req.read() and json.loads(req.content)["aspect_ratio"]=="16:9"
            return httpx.Response(202,json={"task_id":"a1b2c3d4","status":"pending"})
        if req.url.path=="/api/status/a1b2c3d4":
            return httpx.Response(200,json={"task_id":"a1b2c3d4",
                          "status":"running" if len([x for x in calls if x[1].startswith("/api/status")])==1 else "completed"})
        if req.url.path=="/api/result/a1b2c3d4":
            return httpx.Response(200,json={"task_id":"a1b2c3d4","status":"completed",
                                            "results":["http://127.0.0.1:8765/api/files/result.png"]})
        if req.url.path=="/api/files/result.png":
            return httpx.Response(200,content=PNG)
        return httpx.Response(404,json={"error":"not found"})
    store,service,project,requirement=setup(tmp_path,handler)
    with pytest.raises(ContractViolation,match="GLABS_FALLBACK_AUTH_REQUIRED"):
        service.enqueue(project,requirement,"nano_banana_2","Vintage scene",
                        expected_revision=1,idempotency_key="unapproved-001")
    job=service.enqueue(project,requirement,"nano_banana_2","Vintage scene",
        expected_revision=1,idempotency_key="glabs-fixture-001",controlled_offline=True)
    assert service.process_one(job["job_id"])["state"]=="RUNNING"
    active=service.queue.get(job["job_id"])
    assert active["provider_task_id"]=="a1b2c3d4"
    with store._connection() as db:
        assert db.execute("SELECT provider_status FROM glabs_task_observations WHERE job_id=?",
                          (job["job_id"],)).fetchone()[0]=="running"
    recover_interrupted(service.queue)
    resumed=GTaskService(ProjectStore(store.database,store.artifacts.root),
                         JobQueue(store),service.provider)
    result=resumed.run_until_terminal(job["job_id"],poll_seconds=0,max_polls=2)
    assert result["state"]=="SUCCEEDED" and store.get_artifact(result["output_sha256"])==PNG
    with store._connection() as db:
        assert db.execute("SELECT provider_status FROM glabs_task_observations WHERE job_id=?",
                          (job["job_id"],)).fetchone()[0]=="completed"
    assert len([x for x in calls if x[1]=="/api/image/generate"])==1
    with store._connection() as db:
        row=db.execute("SELECT metadata_json,user_approved FROM asset_candidates WHERE project_id=?",
                       (project,)).fetchone()
    obj=json.loads(row[0])
    assert obj["asset_class"]=="AI_ILLUSTRATION" and obj["provider"]=="glabs_webhook"
    assert row[1]==0 and obj["user_approved"] is False
    assert resumed.process_one(job["job_id"]) is None

def test_generate_model_rules_http_errors_and_stop_scope(tmp_path):
    with pytest.raises(ContractViolation,match="GLABS_MODEL_UNSUPPORTED"):
        validate_request("x","unknown","16:9",[])
    with pytest.raises(ContractViolation,match="GLABS_REFERENCE_INVALID"):
        validate_request("x","nano_pics","16:9",[],mode="image_to_image")
    with pytest.raises(ContractViolation,match="GLABS_INPUT_INVALID"):
        validate_request("x","nano_pics","16:9",[],mode="text_to_image",upscale=["4K"])
    calls=[]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/api/image/generate":
            return httpx.Response(202,json={"task_id":"abcddcba","status":"pending"})
        if req.url.path=="/api/status/abcddcba":
            return httpx.Response(200,json={"task_id":"abcddcba","status":"running"})
        if req.url.path=="/api/stop/abcddcba":
            return httpx.Response(200,json={"stopped":["abcddcba"],"skipped":[],"count":1})
        return httpx.Response(404)
    store,service,pid,req=setup(tmp_path,handler)
    job=service.enqueue(pid,req,"nano_banana_2","Ancient village",
        expected_revision=1,idempotency_key="glabs-stop-fixture-01",controlled_offline=True)
    assert service.process_one(job["job_id"])["state"]=="RUNNING"
    active_token=service.queue.get(job["job_id"])["lease_token"]
    assert service.cancel(pid,job["job_id"])["state"]=="CANCELLED"
    assert service.poll(job["job_id"],active_token)["state"]=="CANCELLED"
    with store._connection() as db:
        assert db.execute("SELECT last_error_code FROM glabs_task_observations WHERE job_id=?",
                          (job["job_id"],)).fetchone()[0]=="STOPPED_BY_CLIENT"
    assert "/api/stop/abcddcba" in calls and "/api/stop" not in calls
    with pytest.raises(ContractViolation,match="GLABS_TASK_NOT_FOUND"):
        service.cancel("proj_other",job["job_id"])
    with pytest.raises(ContractViolation,match="GLABS_AUTH_REQUIRED") as err:
        GLabs(httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(401))),
              api_key="wrong").submit({"prompt":"x"})
    assert "wrong" not in str(err.value)
    with pytest.raises(ContractViolation,match="GLABS_STATUS_INVALID"):
        GLabs(httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,
               json={"task_id":"abcddcba","status":"teleported"}))),
              api_key="offline-secret").poll("abcddcba")
    with pytest.raises(ContractViolation,match="GLABS_TASK_ID_INVALID"):
        service.provider.stop("../../stop")
    with pytest.raises(ContractViolation,match="GLABS_UPSCALE_ENTITLEMENT_UNVERIFIED"):
        validate_request("x","nano_banana_2","16:9",[],upscale=["4K"])
    # A timeout before receiving a task ID is an uncertain paid side effect.
    # Never replay it silently, even after another worker looks for queued jobs.
    submits=[]
    def uncertain(request):
        submits.append(request.url.path)
        raise httpx.ReadTimeout("unknown whether provider accepted paid work")
    fail_provider=GLabs(httpx.Client(transport=httpx.MockTransport(uncertain)),
                        api_key="fixture-secret")
    fail_provider.offline_fixture=True
    uncertain_svc=GTaskService(store,JobQueue(store),fail_provider)
    uncertain_job=uncertain_svc.enqueue(pid,req,"nano_banana_2","Old town",
        expected_revision=store.revision(pid),idempotency_key="glabs-uncertain-submit-001",
        controlled_offline=True)
    failed=uncertain_svc.process_one(uncertain_job["job_id"])
    assert failed["state"]=="FAILED_TERMINAL"
    assert failed["provider_task_id"] is None
    assert uncertain_svc.process_one(uncertain_job["job_id"]) is None
    assert submits==["/api/image/generate"]
    with pytest.raises(ContractViolation,match="GLABS_REFERENCE_INVALID"):
        validate_request("x","nano_pics","16:9",
            [{"data":"data:image/jpeg;base64,"+base64.b64encode(PNG).decode()}],mode="image_to_image")


def test_poll_error_499_marks_cancelled_and_never_creates_original(tmp_path):
    def handler(req):
        if req.url.path=="/api/image/generate":
            return httpx.Response(202,json={"task_id":"deadcafe","status":"pending"})
        return httpx.Response(200,json={"task_id":"deadcafe","status":"failed","error_code":499,
                                         "error":"Stopped by client"})
    store,service,project,requirement=setup(tmp_path,handler)
    job=service.enqueue(project,requirement,"nano_banana_2_lite","Historical scene",
        expected_revision=1,idempotency_key="glabs-cancelled-499",controlled_offline=True)
    result=service.process_one(job["job_id"])
    assert result["state"]=="CANCELLED" and result["provider_task_id"]=="deadcafe"
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_candidates WHERE project_id=?",
                          (project,)).fetchone()[0]==0


def test_generate_source_snapshot_blocks_presubmit_and_completion_staleness(tmp_path):
    calls = []
    def handler(req):
        calls.append(req.url.path)
        if req.url.path == "/api/image/generate":
            return httpx.Response(202, json={"task_id": "cafeaffe", "status": "pending"})
        if req.url.path == "/api/status/cafeaffe":
            return httpx.Response(200, json={"task_id": "cafeaffe", "status": "completed"})
        if req.url.path == "/api/result/cafeaffe":
            return httpx.Response(200, json={"task_id": "cafeaffe", "status": "completed",
                    "results": ["http://127.0.0.1:8765/api/files/r.png"]})
        if req.url.path == "/api/files/r.png":
            return httpx.Response(200, content=PNG)
        return httpx.Response(404)
    store, service, pid, req = setup(tmp_path, handler)
    before = service.enqueue(pid, req, "nano_banana_2", "Ancient illustration",
                expected_revision=store.revision(pid), idempotency_key="snapshot-before-001",
                controlled_offline=True)
    payload = json.loads(before["payload_json"])
    assert payload["story_sha256"] == store.get_story(pid).sha256
    assert len(payload["requirement_sha256"]) == 64
    changed = store.get_story(pid).data()
    changed["asset_requirements"][0]["subject"] += " changed"
    store.import_story(StoryCandidate.parse(changed), store.revision(pid))
    blocked = service.process_one(before["job_id"])
    assert blocked["state"] == "FAILED_TERMINAL"
    assert blocked["error_code"] == "GLABS_SOURCE_STALE"
    assert "/api/image/generate" not in calls

    # Generation in progress must never remap an old requirement ID.
    paid = service.enqueue(pid, req, "nano_banana_2", "New illustration",
                expected_revision=store.revision(pid), idempotency_key="snapshot-during-001",
                controlled_offline=True)
    def pending(req_http):
        if req_http.url.path == "/api/status/cafeaffe":
            return httpx.Response(200, json={"task_id": "cafeaffe", "status": "running"})
        return handler(req_http)
    service.provider.client = httpx.Client(transport=httpx.MockTransport(pending))
    started = service.process_one(paid["job_id"])
    assert started["provider_task_id"] == "cafeaffe"
    changed_again = store.get_story(pid).data()
    changed_again["asset_requirements"][0]["subject"] += " changed again"
    store.import_story(StoryCandidate.parse(changed_again), store.revision(pid))
    service.provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    recover_interrupted(service.queue)
    reopened = GTaskService(ProjectStore(store.database,store.artifacts.root),
                            JobQueue(store),service.provider)
    finished = reopened.process_one(paid["job_id"])
    assert finished["state"] == "FAILED_TERMINAL"
    assert finished["error_code"] == "GLABS_SOURCE_STALE"
    assert finished["provider_task_id"] == "cafeaffe"
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_candidates WHERE project_id=?",
                          (pid,)).fetchone()[0] == 0
        assert db.execute("SELECT provider_status, last_error_code FROM glabs_task_observations "
                          "WHERE job_id=?", (paid["job_id"],)).fetchone() == (
                          "completed", "GLABS_SOURCE_STALE")


@pytest.mark.parametrize("http_failure,code,expected", [
    (False, 429, "GLABS_QUOTA_EXCEEDED"),
    (False, 403, "GLABS_PLAN_REQUIRED"),
    (False, 500, "GLABS_SERVER_ERROR"),
    (False, 700, "GLABS_PROVIDER_FAILED"),
    (True, 429, "GLABS_RATE_LIMITED"),
])
def test_poll_error_classifies_terminal_quota_vs_transient_http(tmp_path, http_failure, code, expected):
    submits = []
    def handler(req):
        if req.url.path == "/api/image/generate":
            submits.append(req.url.path)
            return httpx.Response(202, json={"task_id": "fedcba98", "status": "pending"})
        if req.url.path == "/api/status/fedcba98":
            if http_failure:
                return httpx.Response(429)
            return httpx.Response(200, json={"task_id": "fedcba98",
                   "status": "failed", "error_code": code,
                   "error": "someone@example.com quota or account detail"})
        return httpx.Response(404)
    store, svc, project_id, requirement = setup(tmp_path, handler)
    job = svc.enqueue(project_id, requirement, "nano_banana_2", "Test image",
          expected_revision=store.revision(project_id),
          idempotency_key=f"glabs-classification-{code}-{http_failure}", controlled_offline=True)
    outcome = svc.process_one(job["job_id"])
    assert outcome["error_code"] == expected
    assert outcome["state"] == ("FAILED_RETRYABLE" if http_failure else "FAILED_TERMINAL")
    with store._connection() as db:
        assert db.execute("SELECT last_error_code FROM glabs_task_observations "
                          "WHERE job_id=?", (job["job_id"],)).fetchone()[0] == expected
        assert db.execute("SELECT COUNT(*) FROM asset_candidates").fetchone()[0] == 0
    if http_failure:
        # Retrying transient HTTP polling reclaims the same known paid task, not POST.
        resumed=svc.queue.retry(job["job_id"])
        assert resumed["resume_only"]==1 and resumed["provider_task_id"]=="fedcba98"
        again=svc.process_one(job["job_id"])
        assert again["state"]=="FAILED_RETRYABLE" and again["error_code"]==expected
    else:
        with pytest.raises(ContractViolation, match="JOB_RETRY_FORBIDDEN"):
            svc.queue.retry(job["job_id"])
    assert submits == ["/api/image/generate"]


def test_managed_authorization_revoked_before_publication(tmp_path):
    """A3-04 paid boundary: a durable explicit choice is required and rechecked."""
    from backend.app.assets.resolution import AssetResolution
    calls=[]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/api/image/generate":
            return httpx.Response(202,json={"task_id":"abcd9999","status":"pending"})
        if req.url.path=="/api/status/abcd9999":
            return httpx.Response(200,json={"task_id":"abcd9999","status":"running"
                if calls.count("/api/status/abcd9999")==1 else "completed"})
        if req.url.path=="/api/result/abcd9999":
            return httpx.Response(200,json={"task_id":"abcd9999","status":"completed",
                "results":["http://127.0.0.1:8765/api/files/final.png"]})
        if req.url.path=="/api/files/final.png":
            return httpx.Response(200,content=PNG)
        return httpx.Response(404)
    store,service,pid,rid=setup(tmp_path,handler)
    service.provider.offline_fixture=False
    resolver=AssetResolution(store)
    from backend.app.projects.gates import GateService
    gates=GateService(store)
    story=store.get_story(pid).data()
    for claim in story["claims"]:
        if claim["critical"]:
            gates.review_claim(pid,claim["claim_id"],"REVIEWED","Fixture review only",
                               store.revision(pid),source_url="https://example.org/mock-evidence")
    g1=gates.board(pid)[0]
    gates.decide(pid,"G1",{"decision":"APPROVED",
        "candidate_sha256":g1["candidate_sha256"],
        "dependency_fingerprint":g1["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    with pytest.raises(ContractViolation,match="GLABS_FALLBACK_AUTH_REQUIRED"):
        service.enqueue(pid,rid,"nano_banana_2","Historical illustration",expected_revision=store.revision(pid),
                        idempotency_key="managed-not-authorized-01")
    revision=resolver.choose(pid,rid,"MANAGED_FALLBACK","Operator authorizes billable candidate",store.revision(pid))["project_revision"]
    service.provider.key=""
    with pytest.raises(ContractViolation,match="GLABS_KEY_MISSING"):
        service.enqueue(pid,rid,"nano_banana_2","Historical illustration",expected_revision=revision,
                        idempotency_key="managed-missing-key-001")
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs WHERE kind='glabs_image'").fetchone()[0]==0
    service.provider.key="offline-secret"
    job=service.enqueue(pid,rid,"nano_banana_2","Historical illustration",expected_revision=revision,
                        idempotency_key="managed-authorized-001")
    assert service.process_one(job["job_id"])["state"]=="RUNNING"
    assert calls.count("/api/image/generate")==1
    revision=resolver.choose(pid,rid,"MANUAL_UPLOAD","Revoked managed choice",revision)["project_revision"]
    recover_interrupted(service.queue)
    result=service.process_one(job["job_id"])
    assert result["state"]=="FAILED_TERMINAL"
    assert result["error_code"]=="GLABS_FALLBACK_AUTH_REQUIRED"
    assert result["provider_task_id"]=="abcd9999"
    assert calls.count("/api/image/generate")==1
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_candidates").fetchone()[0]==0


def test_provider_identity_is_pinned_before_first_paid_post(tmp_path):
    """F05: settings rotation cannot silently redirect persisted billable task."""
    from backend.app.assets.resolution import AssetResolution
    from backend.app.projects.gates import GateService
    calls=[]
    store,service,pid,rid=setup(tmp_path,lambda req:calls.append(req.url.path) or httpx.Response(500))
    service.provider.offline_fixture=False
    gates=GateService(store)
    story=store.get_story(pid).data()
    for claim in story["claims"]:
        if claim["critical"]:
            gates.review_claim(pid,claim["claim_id"],"REVIEWED","Synthetic human review",
                               store.revision(pid),source_url="https://example.org/mock-evidence")
    g1=gates.board(pid)[0]
    gates.decide(pid,"G1",{"decision":"APPROVED","candidate_sha256":g1["candidate_sha256"],
        "dependency_fingerprint":g1["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    resolver=AssetResolution(store)
    revision=resolver.choose(pid,rid,"MANAGED_FALLBACK","Authorized original endpoint",
                             store.revision(pid))["project_revision"]
    job=service.enqueue(pid,rid,"nano_banana_2","Illustration",
        expected_revision=revision,idempotency_key="provider-identity-pin-001")
    assert "offline-secret" not in service.queue.get(job["job_id"])["payload_json"]
    service.provider.key="rotated-credential"
    outcome=service.process_one(job["job_id"])
    assert outcome["state"]=="FAILED_RETRYABLE"
    assert outcome["error_code"]=="GLABS_PROVIDER_IDENTITY_STALE"
    assert calls==[]
    service.provider.key="offline-secret"
    recovered=service.queue.retry(job["job_id"])
    assert recovered["state"]=="QUEUED"
    assert service.process_one(job["job_id"])["error_code"]=="GLABS_SERVER_ERROR"
    assert calls==["/api/image/generate"]  # only after original identity restored
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_candidates").fetchone()[0]==0



@pytest.mark.parametrize("stop_response,final_state", [
    ("stopped","CANCELLED"),("skipped","SUCCEEDED")
])
def test_remote_owned_queued_cancel_after_restart_obeys_stop_outcome(tmp_path,stop_response,final_state):
    """R02/R03: recovered QUEUED+known task ID must stop, skipped is completed."""
    calls=[]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/api/image/generate":
            return httpx.Response(202,json={"task_id":"aabbccdd","status":"pending"})
        if req.url.path=="/api/status/aabbccdd":
            return httpx.Response(200,json={"task_id":"aabbccdd",
                "status":"running" if calls.count("/api/status/aabbccdd")==1 else "completed"})
        if req.url.path=="/api/stop/aabbccdd":
            return httpx.Response(200,json={"stopped":["aabbccdd"] if stop_response=="stopped" else [],
                "skipped":["aabbccdd"] if stop_response=="skipped" else [],"count":1})
        if req.url.path=="/api/result/aabbccdd":
            return httpx.Response(200,json={"task_id":"aabbccdd","status":"completed",
                "results":["http://127.0.0.1:8765/api/files/a.png"]})
        if req.url.path=="/api/files/a.png":
            return httpx.Response(200,content=PNG)
        return httpx.Response(404)
    store,service,pid,rid=setup(tmp_path,handler)
    job=service.enqueue(pid,rid,"nano_banana_2","Ancient village",expected_revision=1,
        idempotency_key="cancel-resume-"+stop_response,controlled_offline=True)
    assert service.process_one(job["job_id"])["state"]=="RUNNING"
    assert recover_interrupted(service.queue)["resume_existing_provider_task"]==1
    before=service.queue.get(job["job_id"])
    assert before["state"]=="QUEUED" and before["provider_task_id"]=="aabbccdd"
    actual=service.cancel(pid,job["job_id"])
    assert actual["state"]==final_state
    assert calls.count("/api/stop/aabbccdd")==1
    assert calls.count("/api/image/generate")==1
    assert (actual["output_sha256"] is not None)==(final_state=="SUCCEEDED")
    assert service.cancel(pid,job["job_id"])["state"]==final_state
    assert calls.count("/api/stop/aabbccdd")==1


def test_uncertain_stop_recoverable_then_verified_same_task(tmp_path):
    """R04: transport failure cannot fabricate cancel or delete durable provider ID."""
    calls=[]
    fail_stop=[True]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/api/image/generate":
            return httpx.Response(202,json={"task_id":"beadface","status":"pending"})
        if req.url.path=="/api/status/beadface":
            return httpx.Response(200,json={"task_id":"beadface","status":"running"})
        if req.url.path=="/api/stop/beadface":
            if fail_stop[0]: raise httpx.ReadTimeout("uncertain stop")
            return httpx.Response(200,json={"stopped":["beadface"],"skipped":[],"count":1})
        return httpx.Response(404)
    store,service,pid,rid=setup(tmp_path,handler)
    job=service.enqueue(pid,rid,"nano_banana_2","Old town",expected_revision=1,
        idempotency_key="uncertain-remote-stop-01",controlled_offline=True)
    assert service.process_one(job["job_id"])["state"]=="RUNNING"
    blocked=service.cancel(pid,job["job_id"])
    assert blocked["state"]=="BLOCKED_REVIEW"
    assert blocked["provider_task_id"]=="beadface"
    assert blocked["cancel_requested"]==1
    recovered=GTaskService(ProjectStore(store.database,store.artifacts.root),
        JobQueue(store),service.provider)
    assert recovered.queue.get(job["job_id"])["state"]=="BLOCKED_REVIEW"
    fail_stop[0]=False
    cancelled=recovered.cancel(pid,job["job_id"])
    assert cancelled["state"]=="CANCELLED"
    assert calls.count("/api/image/generate")==1
    assert calls.count("/api/stop/beadface")==2


def test_queued_unsubmitted_cancel_has_no_provider_side_effect(tmp_path):
    calls=[]
    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(500)
    store,service,pid,rid=setup(tmp_path,handler)
    job=service.enqueue(pid,rid,"nano_banana_2","No provider yet",expected_revision=1,
        idempotency_key="queued-not-submitted-001",controlled_offline=True)
    assert service.cancel(pid,job["job_id"])["state"]=="CANCELLED"
    assert calls==[]


def test_actual_original_download_guard_blocks_europeana_third_party(tmp_path):
    """V01: do not relax trusted host restrictions to pass thumbnail tests."""
    from backend.app.assets.download import verify_url
    from backend.app.archives.europeana import Europeana
    record={"id":"/abc/123","title":["Original third-party media"],
            "edmIsShownBy":["https://images.unknown-archive.example/media/original.jpg"]}
    candidate=Europeana(key="fixture-key")._norm(record,record,hydrated=True)
    with pytest.raises(ContractViolation,match="ORIGINAL_HOST_FORBIDDEN"):
        verify_url(candidate)
    with pytest.raises(ContractViolation,match="ORIGINAL_NOT_VERIFIED"):
        verify_url({"provider":"europeana",
                    "original_download_url":"https://www.europeana.eu/thumb/preview.jpg"})



def test_stop_skipped_failed_quota_never_becomes_cancelled(tmp_path):
    """R03: skipped is already terminal; provider failed quota remains FAILED_TERMINAL."""
    calls=[]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/api/image/generate":
            return httpx.Response(202,json={"task_id":"deadbeef","status":"pending"})
        if req.url.path=="/api/status/deadbeef":
            if calls.count("/api/status/deadbeef")==1:
                return httpx.Response(200,json={"task_id":"deadbeef","status":"running"})
            return httpx.Response(200,json={"task_id":"deadbeef","status":"failed","error_code":429})
        if req.url.path=="/api/stop/deadbeef":
            return httpx.Response(200,json={"stopped":[],"skipped":["deadbeef"],"count":0})
        return httpx.Response(404)
    store,service,pid,rid=setup(tmp_path,handler)
    job=service.enqueue(pid,rid,"nano_banana_2","Period village",expected_revision=1,
        idempotency_key="skipped-quota-outcome-01",controlled_offline=True)
    assert service.process_one(job["job_id"])["state"]=="RUNNING"
    result=service.cancel(pid,job["job_id"])
    assert result["state"]=="FAILED_TERMINAL" and result["error_code"]=="GLABS_QUOTA_EXCEEDED"
    assert result["state"]!="CANCELLED"
    assert calls.count("/api/image/generate")==1


def test_project_scoped_retry_endpoint_rejects_foreign_and_nonretryable(tmp_path):
    """R05: no cross-project job transition or retry of a still queued job."""
    from backend.app.api.server import create_app
    from fastapi.testclient import TestClient
    store,service,pid,rid=setup(tmp_path,lambda req:httpx.Response(500))
    job=service.enqueue(pid,rid,"nano_banana_2","Original job",expected_revision=1,
        idempotency_key="retry-scope-case-01",controlled_offline=True)
    with TestClient(create_app(store.database,store.artifacts.root)) as http:
        foreign=http.post("/api/v1/projects/proj_foreign/jobs/"+job["job_id"]+"/retry",
            headers={"Idempotency-Key":"foreign-job-retry-001"})
        assert foreign.status_code in (404,409,422),foreign.text
        forbidden=http.post("/api/v1/projects/"+pid+"/jobs/"+job["job_id"]+"/retry",
            headers={"Idempotency-Key":"queued-job-retry-001"})
        assert forbidden.status_code==409,forbidden.text
        assert service.queue.get(job["job_id"])["state"]=="QUEUED"


def test_known_remote_provider_rotation_restores_id_without_duplicate_post(tmp_path):
    """R05: a retryable known task resumes after restoring exact endpoint/key."""
    from backend.app.assets.resolution import AssetResolution
    from backend.app.projects.gates import GateService
    calls=[]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/api/image/generate":
            return httpx.Response(202,json={"task_id":"cafe1234","status":"pending"})
        if req.url.path=="/api/status/cafe1234":
            return httpx.Response(200,json={"task_id":"cafe1234",
                "status":"running" if calls.count("/api/status/cafe1234")==1 else "completed"})
        if req.url.path=="/api/result/cafe1234":
            return httpx.Response(200,json={"task_id":"cafe1234","status":"completed",
                "results":["http://127.0.0.1:8765/api/files/verified.png"]})
        if req.url.path=="/api/files/verified.png":
            return httpx.Response(200,content=PNG)
        return httpx.Response(404)
    store,service,pid,rid=setup(tmp_path,handler)
    service.provider.offline_fixture=False
    gates=GateService(store)
    for claim in store.get_story(pid).data()["claims"]:
        if claim["critical"]:
            gates.review_claim(pid,claim["claim_id"],"REVIEWED",
                "Controlled evidence only",store.revision(pid),
                source_url="https://example.org/reviewed")
    g1=gates.board(pid)[0]
    gates.decide(pid,"G1",{"decision":"APPROVED",
        "candidate_sha256":g1["candidate_sha256"],
        "dependency_fingerprint":g1["dependency_fingerprint"],
        "expected_revision":store.revision(pid)})
    AssetResolution(store).choose(pid,rid,"MANAGED_FALLBACK","Operator controls paid boundary",
                                  store.revision(pid))
    job=service.enqueue(pid,rid,"nano_banana_2","Village illustration",
                        expected_revision=store.revision(pid),
                        idempotency_key="rotation-known-task-001")
    assert service.process_one(job["job_id"])["state"]=="RUNNING"
    running=service.queue.get(job["job_id"])
    assert running["provider_task_id"]=="cafe1234"
    service.provider.key="rotated-key"
    failed=service.poll(job["job_id"],running["lease_token"])
    assert failed["state"]=="FAILED_RETRYABLE"
    with pytest.raises(ContractViolation,match="GLABS_PROVIDER_IDENTITY_STALE"):
        service.retry(pid,job["job_id"])
    service.provider.key="offline-secret"
    assert service.retry(pid,job["job_id"])["resume_only"]==1
    done=service.process_one(job["job_id"])
    assert done["state"]=="SUCCEEDED"
    assert done["provider_task_id"]=="cafe1234"
    assert calls.count("/api/image/generate")==1
    assert store.get_artifact(done["output_sha256"])==PNG



def test_cancel_during_uncertain_first_post_preserves_remote_identity(tmp_path):
    """R02/R04: request cancellation inside provider submit; never false CANCELLED."""
    service_ref={}
    calls=[]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/api/image/generate":
            svc=service_ref["svc"]
            running=svc.queue.get(service_ref["job_id"])
            assert running["state"]=="RUNNING" and not running["provider_task_id"]
            flagged=svc.cancel(service_ref["pid"],service_ref["job_id"])
            assert flagged["cancel_requested"]==1 and flagged["state"]=="RUNNING"
            return httpx.Response(202,json={"task_id":"ab12cd34","status":"pending"})
        if req.url.path=="/api/stop/ab12cd34":
            return httpx.Response(200,json={"stopped":["ab12cd34"],"skipped":[],"count":1})
        if req.url.path=="/api/status/ab12cd34":
            return httpx.Response(200,json={"task_id":"ab12cd34","status":"running"})
        return httpx.Response(404)
    store,svc,pid,rid=setup(tmp_path,handler)
    job=svc.enqueue(pid,rid,"nano_banana_2","Stop while sending",
        expected_revision=1,idempotency_key="cancel-unknown-post-001",controlled_offline=True)
    service_ref.update(svc=svc,pid=pid,job_id=job["job_id"])
    pending=svc.process_one(job["job_id"])
    assert pending["state"]=="BLOCKED_REVIEW",pending
    assert pending["provider_task_id"]=="ab12cd34"
    assert calls.count("/api/image/generate")==1
    confirmed=svc.cancel(pid,job["job_id"])
    assert confirmed["state"]=="CANCELLED"
    assert calls.count("/api/stop/ab12cd34")==1


def test_remote_cancel_terminal_cas_preserves_worker_success(tmp_path):
    """R04: when a remote task completed before operator cancellation, do not stop or overwrite."""
    calls=[]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/api/image/generate":
            return httpx.Response(202,json={"task_id":"ab12ab12","status":"pending"})
        if req.url.path=="/api/status/ab12ab12":
            return httpx.Response(200,json={"task_id":"ab12ab12","status":"completed"})
        if req.url.path=="/api/result/ab12ab12":
            return httpx.Response(200,json={"task_id":"ab12ab12","status":"completed",
                "results":["http://127.0.0.1:8765/api/files/finished.png"]})
        if req.url.path=="/api/files/finished.png":
            return httpx.Response(200,content=PNG)
        return httpx.Response(500)
    store,svc,pid,rid=setup(tmp_path,handler)
    job=svc.enqueue(pid,rid,"nano_banana_2","Finish before cancel",
        expected_revision=1,idempotency_key="terminal-worker-win-001",controlled_offline=True)
    finished=svc.process_one(job["job_id"])
    assert finished["state"]=="SUCCEEDED"
    assert svc.cancel(pid,job["job_id"])["state"]=="SUCCEEDED"
    assert "/api/stop/ab12ab12" not in calls
    assert svc.queue.get(job["job_id"])["output_sha256"]==finished["output_sha256"]


def test_cancel_wins_during_poll_http_error_keeps_remote_verified_cancel(tmp_path):
    """R04: a late transient 429 must not overwrite or crash a CAS-won stop."""
    state={"stop_during_poll":False}
    calls=[]
    svc_holder={}
    def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/api/image/generate":
            return httpx.Response(202,json={"task_id":"abcdd123","status":"pending"})
        if req.url.path=="/api/status/abcdd123":
            if state["stop_during_poll"]:
                result=svc_holder["service"].cancel(svc_holder["pid"],svc_holder["job"])
                assert result["state"]=="CANCELLED"
                return httpx.Response(429)
            return httpx.Response(200,json={"task_id":"abcdd123","status":"running"})
        if req.url.path=="/api/stop/abcdd123":
            return httpx.Response(200,json={"stopped":["abcdd123"],"skipped":[],"count":1})
        return httpx.Response(404)
    store,service,pid,rid=setup(tmp_path,handler)
    job=service.enqueue(pid,rid,"nano_banana_2","Historical note",
        expected_revision=1,idempotency_key="stop-wins-poll-error-01",controlled_offline=True)
    assert service.process_one(job["job_id"])["state"]=="RUNNING"
    svc_holder.update(service=service,pid=pid,job=job["job_id"])
    state["stop_during_poll"]=True
    active=service.queue.get(job["job_id"])
    assert service.poll(job["job_id"],active["lease_token"])["state"]=="CANCELLED"
    assert service.queue.get(job["job_id"])["state"]=="CANCELLED"
    assert calls.count("/api/image/generate")==1 and calls.count("/api/stop/abcdd123")==1
