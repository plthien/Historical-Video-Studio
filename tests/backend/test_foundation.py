"""A1 behavioral assertions over real JSON Schema, SQLite and immutable bytes."""
import copy
import json
import sqlite3
from pathlib import Path
import pytest
from backend.app.api.imports import import_story
from backend.app.contracts import ContractViolation, validate_visual_blueprint
from backend.app.projects.models import StoryCandidate
from backend.app.projects.storage import ProjectStore

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def story():
    return json.loads((ROOT / "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "db.sqlite", tmp_path / "originals")


def test_schema_import_24_sections_and_g1_draft(story, store):
    assert len(story["sections"]) == 24
    project = story["project"]
    store.create_project(project["project_id"], project["title"])
    r = import_story(store, json.dumps(story), 0)
    assert r["gate_state"] == "DRAFT"
    assert store.revision(project["project_id"]) == 1
    assert store.get_story(project["project_id"]).data() == story
    reopened = ProjectStore(store.database, store.artifacts.root)
    assert reopened.get_story(project["project_id"]).sha256 == r["candidate_sha256"]


def test_schema_import_rejects_unknown_ids_without_side_effects(story, store):
    store.create_project(story["project"]["project_id"], "Real persisted project")
    story["sections"][0]["claim_refs"] = ["claim_DOES_NOT_EXIST"]
    with pytest.raises(ContractViolation) as err:
        import_story(store, json.dumps(story), 0)
    assert err.value.code == "CROSS_REFERENCE_MISSING"
    assert store.revision(story["project"]["project_id"]) == 0


def test_schema_import_rejects_duplicate_json_keys_and_invalid_enum(story):
    with pytest.raises(ContractViolation, match="JSON_DUPLICATE_KEY"):
        StoryCandidate.parse('{"schema_version":1,"schema_version":2}')
    story["visual_setups"][0]["preferred_template"] = "T11"
    with pytest.raises(ContractViolation) as err:
        StoryCandidate.parse(json.dumps(story))
    assert err.value.code == "SCHEMA_INVALID"
    assert "visual_setups" in err.value.path


def test_schema_template_oneof_and_invalid_variant():
    original = json.loads((ROOT / "contracts/examples/visual_cases/StoryPackage.visual_cases.synthetic.json").read_text())
    blueprint = json.loads((ROOT / "contracts/examples/visual_cases/VisualBlueprint.visual_cases.synthetic.json").read_text())
    validate_visual_blueprint(original, blueprint)
    tags = {p["template_payload"]["template_id"] for p in blueprint["setup_plans"]}
    assert tags == {f"T{i:02}" for i in range(1, 11)}
    bad = copy.deepcopy(blueprint)
    bad["setup_plans"][0]["template_payload"]["template_id"] = "T99"
    with pytest.raises(ContractViolation, match="SCHEMA_INVALID"):
        validate_visual_blueprint(original, bad)


def test_storage_artifact_corruption_and_reopen(store):
    data = b"\x00\x00original binary\xff"
    digest = store.put_artifact(data, "original")
    assert ProjectStore(store.database, store.artifacts.root).get_artifact(digest) == data
    path = store.artifacts.path(digest)
    path.write_bytes(b"tampered")
    with pytest.raises(ContractViolation, match="ARTIFACT_CORRUPT"):
        store.get_artifact(digest)
    with pytest.raises(ContractViolation, match="ARTIFACT_CORRUPT"):
        store.put_artifact(data, "original")


def test_storage_revision_conflict_rollbacks_and_never_approves(story, store):
    project_id = story["project"]["project_id"]
    store.create_project(project_id, "Fixture")
    candidate = StoryCandidate.parse(story)
    store.import_story(candidate, 0)
    with pytest.raises(ContractViolation, match="REVISION_CONFLICT"):
        store.import_story(candidate, 0)
    assert store.revision(project_id) == 1
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM story_candidates").fetchone()[0] == 1
        assert db.execute("SELECT DISTINCT gate_state FROM story_candidates").fetchone()[0] == "DRAFT"


def test_artifact_mismatched_sha_leaves_no_metadata(store):
    with pytest.raises(ContractViolation, match="ARTIFACT_SHA_MISMATCH"):
        store.put_artifact(b"original", "original", "0" * 64)
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0


def test_storage_partial_sqlite_revision_rollback(story, store):
    project_id = story["project"]["project_id"]
    store.create_project(project_id, "Fixture")
    candidate = StoryCandidate.parse(story)
    with sqlite3.connect(store.database) as db:
        db.execute("CREATE TRIGGER reject_revision BEFORE UPDATE OF revision ON projects "
                   "BEGIN SELECT RAISE(ABORT, 'simulated disk transaction failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        store.import_story(candidate, 0)
    assert store.revision(project_id) == 0
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM story_candidates").fetchone()[0] == 0


def test_storage_rejects_conflicting_kind_without_touching_original(store):
    digest = store.put_artifact(b"same-bytes", "original")
    assert store.put_artifact(b"same-bytes", "original") == digest
    with pytest.raises(ContractViolation, match="ARTIFACT_METADATA_CONFLICT"):
        store.put_artifact(b"same-bytes", "generated")
    reopened = ProjectStore(store.database, store.artifacts.root)
    assert reopened.get_artifact(digest) == b"same-bytes"
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT kind FROM artifacts WHERE sha256=?", (digest,)).fetchone() == ("original",)


def test_contract_problem_gate_is_contextual(story):
    from backend.app.contracts import validate_document, validate_story_package
    with pytest.raises(ContractViolation) as generic:
        validate_document("StoryPackage.v1", {})
    assert generic.value.as_problem()["blocking_gate"] is None
    with pytest.raises(ContractViolation) as imported:
        validate_story_package({})
    assert imported.value.as_problem()["blocking_gate"] == "G1"
    with pytest.raises(ContractViolation) as visual:
        validate_visual_blueprint(story, {})
    assert visual.value.as_problem()["blocking_gate"] is None


def test_schema_generator_detects_stale_or_missing_outputs(tmp_path):
    """A1-02: --check is read-only and rejects changed or absent generated models."""
    import subprocess
    import sys
    from scripts.generate_contract_types import generate
    py_path, ts_path = tmp_path / "types.py", tmp_path / "types.ts"
    expected_py, expected_ts = generate()
    py_path.write_text(expected_py, encoding="utf-8")
    ts_path.write_text(expected_ts, encoding="utf-8")
    cmd = [sys.executable, "scripts/generate_contract_types.py",
           "--check", "--out-py", str(py_path), "--out-ts", str(ts_path)]
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode == 0
    py_path.write_text("corrupted", encoding="utf-8")
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode != 0
    assert py_path.read_text(encoding="utf-8") == "corrupted"
    py_path.write_text(expected_py, encoding="utf-8")
    ts_path.unlink()
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode != 0
    assert not ts_path.exists()


def test_schema_generated_python_import_preserves_tuple(tmp_path):
    """A1-02: emitted Python annotation must retain exactly two typed points."""
    import importlib.util
    from typing import get_args, get_type_hints
    from scripts.generate_contract_types import generate
    output = tmp_path / "generated.py"
    output.write_text(generate()[0], encoding="utf-8")
    spec = importlib.util.spec_from_file_location("temporary_contract_models", output)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        model = module.VisualBlueprint_v1Setup_PlansItemLayout_Control
        annotated = get_type_hints(model)["focal_point"]
        assert get_args(annotated) == (float, float)
        assert module.API_REQUEST_MODELS["post__projects_project_id_voice_sections_section_id_regenerate"]
    finally:
        sys.modules.pop(spec.name, None)


def test_artifact_race_cannot_overwrite_sha_path(tmp_path, monkeypatch):
    """A1-03: another writer winning between existence check and publication is never overwritten."""
    import hashlib
    from backend.app.assets import store as asset_module
    from backend.app.assets.store import ArtifactStore
    originals = ArtifactStore(tmp_path / "media")
    data = b"frozen original"
    digest = hashlib.sha256(data).hexdigest()

    def competing_publication(temp_path, target):
        Path(target).write_bytes(b"competing corrupt bytes")
        raise FileExistsError(str(target))

    monkeypatch.setattr(asset_module.os, "link", competing_publication)
    with pytest.raises(ContractViolation, match="ARTIFACT_CORRUPT"):
        originals.put(data)
    assert originals.path(digest).read_bytes() == b"competing corrupt bytes"


def test_gate_review_critical_claim_and_crop_invalidation(story, store):
    from backend.app.projects.gates import GateService
    from backend.app.projects.revisions import invalidate
    project_id = story["project"]["project_id"]
    store.create_project(project_id, "Review")
    store.import_story(StoryCandidate.parse(story), 0)
    gates = GateService(store)
    sha = store.get_story(project_id).sha256
    decision = {"decision": "APPROVED", "candidate_sha256": sha,
                "dependency_fingerprint": sha, "expected_revision": 1}
    with pytest.raises(ContractViolation, match="CLAIM_CRITICAL_UNRESOLVED"):
        gates.decide(project_id, "G1", decision)
    rev = 1
    for claim in story["claims"]:
        if claim["critical"]:
            rev = gates.review_claim(project_id, claim["claim_id"], "REVIEWED",
                                     "Human verification pending external evidence", rev)
    decision["expected_revision"] = rev
    result = gates.decide(project_id, "G1", decision)
    assert result["state"] == "APPROVED"
    # Approval increased project revision but must not hide the last imported StoryPackage.
    assert store.get_story(project_id).sha256 == sha
    states = {g["gate_id"]: g["state"] for g in gates.board(project_id)}
    assert states["G1"] == "APPROVED"
    changed = invalidate(gates, project_id, "scene_crop", result["project_revision"])
    assert changed["stale_gates"] == ["G4", "G5"]
    states = {g["gate_id"]: g["state"] for g in gates.board(project_id)}
    assert states["G1"] == "APPROVED"
    assert states["G4"] == "STALE"
    with pytest.raises(ContractViolation, match="APPROVAL_REVISION_CONFLICT"):
        gates.decide(project_id, "G1", decision)


def test_queue_restart_preserves_provider_task_and_scoped_cancel(store):
    from backend.app.jobs import JobQueue, recover_interrupted
    store.create_project("proj_one", "One")
    q = JobQueue(store)
    first = q.submit("proj_one", "provider", "idem-operation-one", {"request": 1}, 0)
    second = q.submit("proj_one", "provider", "idem-operation-two", {"request": 2}, 0)
    assert q.submit("proj_one", "provider", "idem-operation-one", {"request": 1}, 0)["job_id"] == first["job_id"]
    with pytest.raises(ContractViolation, match="IDEMPOTENCY_CONFLICT"):
        q.submit("proj_one", "provider", "idem-operation-one", {"request": 3}, 0)
    running = q.claim()
    q.attach_provider_task(running["job_id"], running["lease_token"], "external-123")
    canceled = q.cancel(second["job_id"])
    assert canceled["state"] == "CANCELLED"
    assert q.get(first["job_id"])["state"] == "RUNNING"
    assert recover_interrupted(JobQueue(store))["resume_existing_provider_task"] == 1
    resumed = q.claim()
    assert resumed["job_id"] == first["job_id"]
    assert resumed["provider_task_id"] == "external-123"
    assert resumed["resume_only"] == 1
    with pytest.raises(ContractViolation, match="PROVIDER_TASK_CONFLICT"):
        q.attach_provider_task(resumed["job_id"], resumed["lease_token"], "new-task")
    assert q.fail(resumed["job_id"], resumed["lease_token"], "HTTP_503", True)["error_code"] == "HTTP_503"
    retried = q.retry(first["job_id"])
    assert retried["retry_count"] == 1
    assert retried["provider_task_id"] == "external-123"


def test_api_gates_review_and_idempotent_mutation(story, tmp_path):
    from fastapi.testclient import TestClient
    from backend.app.api.server import create_app
    client = TestClient(create_app(tmp_path / "api.sqlite", tmp_path / "artifacts"))
    created = client.post("/api/v1/projects", json={
        "title": "Real project", "language": "en", "style_id": "HistoryEditorialPaper.v1"
    })
    assert created.status_code == 201
    project_id = created.json()["project_id"]
    story["project"]["project_id"] = project_id
    uri = f"/api/v1/projects/{project_id}"
    request = client.post(uri + "/story/import?expected_revision=0",
                          json=story, headers={"Idempotency-Key": "one-story-import"})
    assert request.status_code == 200
    assert client.post(uri + "/story/import?expected_revision=0",
                       json=story, headers={"Idempotency-Key": "one-story-import"}).json() == request.json()
    changed = copy.deepcopy(story)
    changed["sections"][0]["narration"] = "An entirely different historical narrative for this section."
    assert client.post(uri + "/story/import?expected_revision=0", json=changed,
                       headers={"Idempotency-Key": "one-story-import"}).status_code == 409
    gate = client.get(uri + "/gates").json()[0]
    assert gate["state"] == "READY_FOR_REVIEW" if not any(x["critical"] for x in story["claims"]) else gate["state"] == "BLOCKED"
    assert client.post(uri + "/gates/G1/decision", headers={"Idempotency-Key": "approve-story-1"},
                       json={"decision": "APPROVED", "candidate_sha256": request.json()["candidate_sha256"],
                             "dependency_fingerprint": request.json()["candidate_sha256"],
                             "expected_revision": 1}).status_code == 422
    future = client.post(uri + "/voice/generate", json={}, headers={"Idempotency-Key": "voice-request-1"})
    assert future.status_code == 501
    assert future.json()["code"] == "OPERATION_NOT_IMPLEMENTED"
