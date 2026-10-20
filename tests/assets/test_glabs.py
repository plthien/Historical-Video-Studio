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
PNG=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/1XcAAAAASUVORK5CYII=")

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
    recover_interrupted(service.queue)
    resumed=GTaskService(ProjectStore(store.database,store.artifacts.root),
                         JobQueue(store),service.provider)
    result=resumed.process_one(job["job_id"])
    assert result["state"]=="SUCCEEDED" and store.get_artifact(result["output_sha256"])==PNG
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
    assert "/api/stop/abcddcba" in calls and "/api/stop" not in calls
    with pytest.raises(ContractViolation,match="GLABS_TASK_NOT_FOUND"):
        service.cancel("proj_other",job["job_id"])
    with pytest.raises(ContractViolation,match="GLABS_AUTH_REQUIRED"):
        GLabs(httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(401))),
              api_key="wrong").submit({"prompt":"x"})
