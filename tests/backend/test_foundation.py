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
                "dependency_fingerprint": gates.board(project_id)[0]["dependency_fingerprint"], "expected_revision": 1}
    with pytest.raises(ContractViolation, match="CLAIM_CRITICAL_UNRESOLVED"):
        gates.decide(project_id, "G1", decision)
    rev = 1
    for claim in story["claims"]:
        if claim["critical"]:
            rev = gates.review_claim(project_id, claim["claim_id"], "REVIEWED",
                                     "Human verification pending external evidence", rev)
    decision["expected_revision"] = rev
    decision["dependency_fingerprint"] = gates.board(project_id)[0]["dependency_fingerprint"]
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
                             "dependency_fingerprint": gate["dependency_fingerprint"],
                             "expected_revision": 1}).status_code == 422
    future = client.post(uri + "/voice/generate", json={}, headers={"Idempotency-Key": "voice-request-1"})
    assert future.status_code == 501
    assert future.json()["code"] == "OPERATION_NOT_IMPLEMENTED"

@pytest.mark.parametrize("rejected_state", ["REJECTED", "CHANGES_REQUESTED"])
def test_gate_rejection_recovery_and_story_reapproval(story, store, rejected_state):
    """R01/R02: real transactions recover only with a different reviewed story."""
    from backend.app.projects.gates import GateService
    project_id = story["project"]["project_id"]
    store.create_project(project_id, "Gate lifecycle")
    first = StoryCandidate.parse(story)
    assert store.import_story(first, 0) == 1
    gates = GateService(store)
    revision = 1
    for claim in story["claims"]:
        if claim["critical"]:
            revision = gates.review_claim(project_id, claim["claim_id"], "REVIEWED",
                                          "Reviewed source leads", revision, "https://www.loc.gov/")
    assert gates.reviews(project_id)[0]["source_url"] == "https://www.loc.gov/"
    decision = lambda sha, rev, kind="APPROVED": {
        "decision": kind, "candidate_sha256": sha,
        "dependency_fingerprint": (gates.board(project_id)[0]["dependency_fingerprint"]
                                   if sha == store.get_story(project_id).sha256 else "0" * 64),
        "expected_revision": rev,
    }
    rejected = gates.decide(project_id, "G1", decision(first.sha256, revision, rejected_state))
    assert gates.board(project_id)[0]["state"] == rejected_state
    with pytest.raises(ContractViolation, match="GATE_ILLEGAL_TRANSITION"):
        gates.decide(project_id, "G1", decision(first.sha256, rejected["project_revision"]))
    second_story = copy.deepcopy(story)
    second_story["sections"][0]["narration"] += " Updated for human review."
    second = StoryCandidate.parse(second_story)
    revision = store.import_story(second, rejected["project_revision"])
    assert gates.board(project_id)[0]["state"] == "BLOCKED"
    for claim in second_story["claims"]:
        if claim["critical"]:
            revision = gates.review_claim(project_id, claim["claim_id"], "REVIEWED",
                                          "Reviewed revised story", revision)
    assert gates.board(project_id)[0]["state"] == "READY_FOR_REVIEW"
    with pytest.raises(ContractViolation, match="APPROVAL_REVISION_CONFLICT"):
        gates.decide(project_id, "G1", decision(first.sha256, revision))
    approved = gates.decide(project_id, "G1", decision(second.sha256, revision))
    assert gates.board(project_id)[0]["state"] == "APPROVED"
    assert store.import_story(second, approved["project_revision"]) == approved["project_revision"]
    assert gates.board(project_id)[0]["state"] == "APPROVED"
    third_story = copy.deepcopy(second_story)
    third_story["sections"][1]["narration"] += " Further correction."
    third = StoryCandidate.parse(third_story)
    revision = store.import_story(third, approved["project_revision"])
    assert gates.board(project_id)[0]["state"] == "BLOCKED"
    assert gates.board(project_id)[3]["state"] == "STALE"
    for claim in third_story["claims"]:
        if claim["critical"]:
            revision = gates.review_claim(project_id, claim["claim_id"], "REVIEWED",
                                          "Reviewed third story", revision)
    reap = gates.decide(project_id, "G1", decision(third.sha256, revision))
    assert gates.board(project_id)[0]["state"] == "APPROVED"
    assert store.get_story(project_id).sha256 == third.sha256
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM gate_events WHERE project_id=? AND gate_id='G1'",
                          (project_id,)).fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM story_candidates").fetchone()[0] == 3
    fake = store.put_artifact(b"pretend voice", "voice_candidate")
    gates.publish_candidate(project_id, "G2", fake, third.sha256, reap["project_revision"])
    with pytest.raises(ContractViolation, match="GATE_ILLEGAL_TRANSITION"):
        gates.decide(project_id, "G2", decision(fake, reap["project_revision"]) |
                     {"dependency_fingerprint": third.sha256})


def test_startup_recovers_jobs_without_replay_and_requires_cancel_confirmation(tmp_path):
    """R03: actual FastAPI lifespan reopen, never a direct recovery helper call."""
    from fastapi.testclient import TestClient
    from backend.app.api.server import create_app
    from backend.app.jobs import JobQueue
    database, media = tmp_path / "state.sqlite", tmp_path / "media"
    app = create_app(database, media)
    store = app.state.store
    store.create_project("proj_restart", "Restart")
    queue = JobQueue(store)
    a = queue.submit("proj_restart", "provider", "recovery-known-task", {"a": 1}, 0)
    b = queue.submit("proj_restart", "provider", "recovery-unknown-task", {"b": 1}, 0)
    known = queue.claim()
    queue.attach_provider_task(known["job_id"], known["lease_token"], "external-original-id")
    unknown = queue.claim()
    assert known["job_id"] == a["job_id"] and unknown["job_id"] == b["job_id"]
    with TestClient(create_app(database, media)) as client:
        assert client.app.state.recovery == {
            "resume_existing_provider_task": 1, "blocked_uncertain_operation": 1
        }
        assert client.get("/api/v1/jobs/" + b["job_id"]).json()["state"] == "BLOCKED_REVIEW"
        assert client.get("/api/v1/jobs/" + a["job_id"]).json()["state"] == "QUEUED"
        q2 = client.app.state.queue
        resumed = q2.claim()
        assert resumed["provider_task_id"] == "external-original-id"
        assert resumed["resume_only"] == 1
        q2.cancel(a["job_id"])
        with pytest.raises(ContractViolation, match="PROVIDER_CANCEL_UNCONFIRMED"):
            q2.acknowledge_cancel(a["job_id"], resumed["lease_token"])
        assert q2.acknowledge_cancel(a["job_id"], resumed["lease_token"],
                                    provider_confirmed=True)["state"] == "CANCELLED"
        assert q2.get(b["job_id"])["state"] == "BLOCKED_REVIEW"
    with TestClient(create_app(database, media)) as reopened:
        assert reopened.app.state.recovery == {
            "resume_existing_provider_task": 0, "blocked_uncertain_operation": 0
        }


def test_api_invalid_import_never_poisoned_replay_and_no_fake_gate(story, tmp_path):
    from fastapi.testclient import TestClient
    from backend.app.api.server import create_app
    with TestClient(create_app(tmp_path / "state.sqlite", tmp_path / "media")) as client:
        p = client.post("/api/v1/projects", json={"title": "Validation project"}).json()["project_id"]
        story["project"]["project_id"] = p
        url = f"/api/v1/projects/{p}/story/import?expected_revision=0"
        headers = {"Idempotency-Key": "same-validating-key"}
        for value in (None, [], "nonsense", 42):
            assert client.post(url, json=value, headers=headers).status_code == 422
        raw = json.dumps(story)
        corrupted = raw.replace('"schema_version": "StoryPackage.v1"',
                                '"schema_version": "StoryPackage.v1", "schema_version": "StoryPackage.v1"', 1)
        assert client.post(url, data=corrupted, headers=headers).status_code == 422
        okay = client.post(url, json=story, headers=headers)
        assert okay.status_code == 200
        assert client.post(url, json=story, headers=headers).json() == okay.json()
        assert client.get(f"/api/v1/projects/{p}/story").json()["claim_reviews"] == []
        bad = client.post(f"/api/v1/projects/{p}/gates/G1/decision",
                          json={"decision": "APPROVED", "candidate_sha256": okay.json()["candidate_sha256"],
                                "dependency_fingerprint": client.get(f"/api/v1/projects/{p}/gates").json()[0]["dependency_fingerprint"],
                                "expected_revision": 1},
                          headers={"Idempotency-Key": "same-gate-key-001"})
        assert bad.status_code == 422
        assert client.post(f"/api/v1/projects/{p}/gates/G1/decision",
                           json={"decision": "APPROVED", "candidate_sha256": "0" * 64,
                                 "dependency_fingerprint": "0" * 64, "expected_revision": 1},
                           headers={"Idempotency-Key": "same-gate-key-001"}).status_code in (409, 422)

def test_story_asset_relevance_selectively_stales_g3(story, store):
    """R02: changing narration does not stale G3; asset requirement changes do."""
    from backend.app.projects.gates import GateService
    project_id = story["project"]["project_id"]
    store.create_project(project_id, "Selective invalidation")
    store.import_story(StoryCandidate.parse(story), 0)
    service = GateService(store)
    narration = copy.deepcopy(story)
    narration["sections"][0]["narration"] += " New historical context."
    revision = store.import_story(StoryCandidate.parse(narration), 1)
    assert service.board(project_id)[2]["state"] == "DRAFT"
    changed = copy.deepcopy(narration)
    changed["asset_requirements"][0]["subject"] += " revised asset scope"
    store.import_story(StoryCandidate.parse(changed), revision)
    states = {gate["gate_id"]: gate["state"] for gate in service.board(project_id)}
    assert states["G3"] == "STALE"
    assert states["G1"] == "BLOCKED"
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM story_candidates").fetchone()[0] == 3


def test_gate_never_approved_revised_story_ready_after_claim_review(story, store):
    """A1-04 P1-01: a revised unapproved draft must never be trapped STALE."""
    from backend.app.projects.gates import GateService
    project_id = story["project"]["project_id"]
    store.create_project(project_id, "Unapproved draft")
    gates = GateService(store)
    assert gates.board(project_id)[0]["state"] == "DRAFT"
    store.import_story(StoryCandidate.parse(story), 0)
    updated = copy.deepcopy(story)
    updated["sections"][0]["narration"] += " Evidence checked for this revision."
    revision = store.import_story(StoryCandidate.parse(updated), 1)
    gates = GateService(store)
    assert gates.board(project_id)[0]["state"] == "BLOCKED"
    for claim in updated["claims"]:
        if claim["critical"]:
            revision = gates.review_claim(project_id, claim["claim_id"], "REVIEWED",
                                          "Researched historical lead", revision)
    board = gates.board(project_id)[0]
    assert board["state"] == "READY_FOR_REVIEW"
    decision = {"decision": "APPROVED", "candidate_sha256": board["candidate_sha256"],
                "dependency_fingerprint": board["dependency_fingerprint"], "expected_revision": revision}
    gates.decide(project_id, "G1", decision)
    assert gates.board(project_id)[0]["state"] == "APPROVED"


def test_gate_review_edit_after_approval_invalidates_effective_head(story, store):
    """A1-04 P1-02: persisted evidence modification must deactivate prior approval."""
    from backend.app.projects.gates import GateService
    project_id = story["project"]["project_id"]
    store.create_project(project_id, "Evidence provenance")
    store.import_story(StoryCandidate.parse(story), 0)
    gates = GateService(store)
    revision = 1
    for claim in story["claims"]:
        if claim["critical"]:
            revision = gates.review_claim(project_id, claim["claim_id"], "REVIEWED",
                                          "First human review", revision)
    candidate = gates.board(project_id)[0]
    gates.decide(project_id, "G1", {"decision": "APPROVED", "candidate_sha256": candidate["candidate_sha256"],
       "dependency_fingerprint": candidate["dependency_fingerprint"], "expected_revision": revision})
    assert gates.board(project_id)[0]["state"] == "APPROVED"
    critical_id = next(c["claim_id"] for c in story["claims"] if c["critical"])
    gates.review_claim(project_id, critical_id, "REVIEWED", "Corrected evidence note", store.revision(project_id))
    assert gates.board(project_id)[0]["state"] != "APPROVED"


@pytest.mark.parametrize("change", ["disposition", "note", "source_url"])
def test_gate_review_dependency_generation_snapshots_and_reapproval(story, store, change):
    """A1-04: evidence lineage, no-op, A->B->A and selective preservation on real SQLite."""
    import hashlib
    from backend.app.projects.gates import GateService
    project = story["project"]["project_id"]
    store.create_project(project, "G1 approval evidence")
    store.import_story(StoryCandidate.parse(story), 0)
    gates = GateService(store)
    critical = next(c["claim_id"] for c in story["claims"] if c["critical"])
    base = ("REVIEWED", "Initial source analysis", "https://www.loc.gov/item/001")
    rev = gates.review_claim(project, critical, *base[:2], 1, base[2])
    for claim in story["claims"]:
        if claim["critical"] and claim["claim_id"] != critical:
            rev = gates.review_claim(project, claim["claim_id"], "REVIEWED",
                                     "Reviewed other critical claim", rev, base[2])
    first = gates.board(project)[0]
    assert first["state"] == "READY_FOR_REVIEW" and first["dependency_fingerprint"] != first["candidate_sha256"]
    def decision(board, expected, action="APPROVED"):
        return {"decision": action, "candidate_sha256": board["candidate_sha256"],
                "dependency_fingerprint": board["dependency_fingerprint"], "expected_revision": expected}
    approved = gates.decide(project, "G1", decision(first, rev))
    original_fp = first["dependency_fingerprint"]
    with sqlite3.connect(store.database) as db:
        first_snapshot = db.execute("SELECT snapshot_json FROM gate_approval_reviews WHERE approval_id=?",
                                    (approved["approval_id"],)).fetchone()[0]
    assert hashlib.sha256(first_snapshot.encode()).hexdigest() == original_fp
    assert gates.review_claim(project, critical, *base[:2], approved["project_revision"], base[2]) == approved["project_revision"]
    assert gates.board(project)[0]["state"] == "APPROVED"
    audio = store.put_artifact(b"existing audio bytes", "voice_candidate")
    gates.publish_candidate(project, "G2", audio, first["dependency_fingerprint"], approved["project_revision"])
    archive = store.put_artifact(b"approved archive original", "original")
    revised_values = {
        "disposition": ("VERIFIED", base[1], base[2]),
        "note": ("REVIEWED", "Revised conclusion", base[2]),
        "source_url": ("REVIEWED", base[1], "https://www.loc.gov/item/002"),
    }[change]
    current = store.revision(project)
    rev = gates.review_claim(project, critical, revised_values[0], revised_values[1],
                             current, revised_values[2])
    edited = gates.board(project)[0]
    assert edited["state"] != "APPROVED" and edited["dependency_fingerprint"] != original_fp
    states = {row["gate_id"]: row["state"] for row in gates.board(project)}
    assert states["G4"] == "STALE" and states["G2"] == "READY_FOR_REVIEW"
    with pytest.raises(ContractViolation, match="GATE_ILLEGAL_TRANSITION"):
        gates.decide(project, "G2", {"decision": "CHANGES_REQUESTED",
            "candidate_sha256": audio, "dependency_fingerprint": original_fp,
            "expected_revision": rev})
    with pytest.raises(ContractViolation, match="APPROVAL_REVISION_CONFLICT"):
        gates.decide(project, "G1", decision(first, rev))
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM gate_events WHERE gate_id='G1'").fetchone()[0] == 1
        assert db.execute("SELECT snapshot_json FROM gate_approval_reviews WHERE approval_id=?",
                          (approved["approval_id"],)).fetchone()[0] == first_snapshot
    # Old evidence text restored is a new generation; old approval remains ineffective.
    rev = gates.review_claim(project, critical, *base[:2], rev, base[2])
    reversed_board = gates.board(project)[0]
    assert reversed_board["state"] == "READY_FOR_REVIEW"
    assert reversed_board["dependency_fingerprint"] != original_fp
    with pytest.raises(ContractViolation, match="APPROVAL_REVISION_CONFLICT"):
        gates.decide(project, "G1", decision(first, rev))
    new_approval = gates.decide(project, "G1", decision(reversed_board, rev))
    assert gates.board(project)[0]["state"] == "APPROVED"
    assert store.get_artifact(audio) == b"existing audio bytes"
    assert store.get_artifact(archive) == b"approved archive original"
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM gate_events WHERE gate_id='G1'").fetchone()[0] == 2
        assert db.execute("SELECT generation FROM claim_reviews WHERE project_id=? AND claim_id=?",
                          (project, critical)).fetchone()[0] == 3
        assert db.execute("SELECT snapshot_json FROM gate_approval_reviews WHERE approval_id=?",
                          (approved["approval_id"],)).fetchone()[0] == first_snapshot
        assert db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G1'",
                          (project,)).fetchone()[0] == new_approval["approval_id"]
    assert GateService(ProjectStore(store.database, store.artifacts.root)).board(project)[0]["state"] == "APPROVED"


def test_gate_effective_head_blocks_dependent_decisions_and_import_rollback(story, store):
    """A1-04: stale historical head never authorizes G2, and failed imports cannot alter ledger."""
    from backend.app.projects.gates import GateService
    project = story["project"]["project_id"]
    store.create_project(project, "Transactional lifecycle")
    first_story = StoryCandidate.parse(story)
    store.import_story(first_story, 0)
    gates = GateService(store)
    rev = 1
    for claim in story["claims"]:
        if claim["critical"]:
            rev = gates.review_claim(project, claim["claim_id"], "REVIEWED", "Reviewed", rev)
    current = gates.board(project)[0]
    approved = gates.decide(project, "G1", {"decision": "APPROVED",
        "candidate_sha256": current["candidate_sha256"],
        "dependency_fingerprint": current["dependency_fingerprint"], "expected_revision": rev})
    fake = store.put_artifact(b"some unapproved voice", "voice_candidate")
    gates.publish_candidate(project, "G2", fake, current["dependency_fingerprint"], approved["project_revision"])
    modified = copy.deepcopy(story)
    modified["sections"][0]["narration"] += " Other historical source context."
    with sqlite3.connect(store.database) as db:
        db.execute("CREATE TRIGGER reject_story_change BEFORE UPDATE OF revision ON projects "
                   "BEGIN SELECT RAISE(ABORT, 'forced transaction failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        store.import_story(StoryCandidate.parse(modified), approved["project_revision"])
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM story_candidates").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM gate_events WHERE gate_id='G1'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM gate_staleness WHERE gate_id='G1'").fetchone()[0] == 0
        db.execute("DROP TRIGGER reject_story_change")
    rev = store.import_story(StoryCandidate.parse(modified), approved["project_revision"])
    assert gates.board(project)[0]["state"] == "BLOCKED"
    with pytest.raises(ContractViolation, match="GATE_ILLEGAL_TRANSITION"):
        gates.decide(project, "G2", {"decision": "CHANGES_REQUESTED", "candidate_sha256": fake,
            "dependency_fingerprint": current["dependency_fingerprint"], "expected_revision": rev})
    assert GateService(ProjectStore(store.database, store.artifacts.root)).board(project)[0]["state"] == "BLOCKED"
    assert gates.board(project)[1]["candidate_sha256"] == fake


def test_api_g1_saved_review_fingerprint_idempotency_and_cas(story, tmp_path):
    """A1-04: HTTP uses same persisted fingerprint as GateService and durable ledger."""
    from backend.app.projects.gates import GateService
    from fastapi.testclient import TestClient
    from backend.app.api.server import create_app
    db, media = tmp_path / "state.sqlite", tmp_path / "media"
    project = story["project"]["project_id"]
    store = ProjectStore(db, media)
    store.create_project(project, "G1 HTTP review")
    with TestClient(create_app(db, media)) as client:
        root = f"/api/v1/projects/{project}"
        imported = client.post(root + "/story/import?expected_revision=0", json=story,
                               headers={"Idempotency-Key": "story-current-0001"})
        assert imported.status_code == 200
        claim = next(c["claim_id"] for c in story["claims"] if c["critical"])
        url = root + f"/story/claims/{claim}/review"
        def submit_review(rev, note, key):
            return client.post(url, json={"expected_revision": rev, "status": "REVIEWED",
                        "evidence_note": note, "source_url": "https://www.loc.gov/"},
                        headers={"Idempotency-Key": key})
        response = submit_review(1, "First review", "review-current-0001")
        assert response.status_code == 200
        rev = response.json()["project_revision"]
        for other in story["claims"]:
            if other["critical"] and other["claim_id"] != claim:
                other_result = client.post(root + f"/story/claims/{other['claim_id']}/review",
                    json={"expected_revision": rev, "status": "REVIEWED",
                          "evidence_note": "Reviewed additional critical claim",
                          "source_url": "https://www.loc.gov/"},
                    headers={"Idempotency-Key": f"review-other-{other['claim_id']}-v1"})
                assert other_result.status_code == 200
                rev = other_result.json()["project_revision"]
        current = client.get(root + "/gates").json()[0]
        def decide(board, rev, key):
            return client.post(root + "/gates/G1/decision", json={
                "decision": "APPROVED", "candidate_sha256": board["candidate_sha256"],
                "dependency_fingerprint": board["dependency_fingerprint"], "expected_revision": rev},
                headers={"Idempotency-Key": key})
        approved = decide(current, rev, "decision-current-0001")
        assert approved.status_code == 200
        assert decide(current, rev, "decision-current-0001").json() == approved.json()
        approved_rev = approved.json()["project_revision"]
        assert submit_review(approved_rev, "First review", "review-current-0002").json()["project_revision"] == approved_rev
        assert client.get(root + "/gates").json()[0]["state"] == "APPROVED"
        changed = submit_review(approved_rev, "Re-evaluated historical evidence", "review-current-0003")
        assert changed.status_code == 200
        board = client.get(root + "/gates").json()[0]
        assert board["state"] == "READY_FOR_REVIEW"
        assert board["candidate_sha256"] == current["candidate_sha256"]
        assert board["dependency_fingerprint"] != current["dependency_fingerprint"]
        stale_decision = decide(current, changed.json()["project_revision"], "decision-current-0002")
        assert stale_decision.status_code == 409
        assert stale_decision.json()["code"] == "APPROVAL_REVISION_CONFLICT"
        assert decide(board, changed.json()["project_revision"] - 1, "decision-current-0003").status_code == 409
        assert decide(board, changed.json()["project_revision"], "decision-current-0004").status_code == 200
        assert client.get(root + "/gates").json()[0]["state"] == "APPROVED"
    with sqlite3.connect(db) as sql:
        assert sql.execute("SELECT COUNT(*) FROM gate_events WHERE gate_id='G1'").fetchone()[0] == 2
        assert sql.execute("SELECT COUNT(*) FROM gate_approval_reviews").fetchone()[0] == 2
    assert GateService(ProjectStore(db, media)).board(project)[0]["state"] == "APPROVED"
