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
    assert service.cancel(pid,job["job_id"])["state"]=="CANCELLED"
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
