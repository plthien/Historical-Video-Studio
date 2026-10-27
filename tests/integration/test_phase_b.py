"""B3-04/05 behavioral integration on real SQLite/files/processes."""
from __future__ import annotations

import base64
import copy
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.server import create_app
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.contracts import ContractViolation
from backend.app.jobs import JobQueue, recover_interrupted
from backend.app.projects.backup import BackupError, create_backup, restore_backup
from backend.app.projects.gates import GateService
from backend.app.projects.models import StoryCandidate
from backend.app.projects.storage import ProjectStore


ROOT = Path(__file__).resolve().parents[2]
STORY = ROOT / "contracts" / "examples" / "StoryPackage.v1.valid.json"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMwSpkGAAH4AS3k7SvZAAAAAElFTkSuQmCC")


def _store(tmp_path: Path, project: str = "proj_phase_b") -> ProjectStore:
    store = ProjectStore(tmp_path / "state.sqlite", tmp_path / "media")
    store.create_project(project, "Phase B integration")
    return store


def test_restart_reconciles_only_safe_local_or_original_provider_identity(tmp_path):
    store = _store(tmp_path)
    queue = JobQueue(store)
    assembly = queue.submit("proj_phase_b", "final_assembly", "assembly-restart-0001", {}, 0)
    assembly_running = queue.claim("final_assembly")
    provider = queue.submit("proj_phase_b", "glabs_image", "provider-restart-0001", {}, 0)
    provider_running = queue.claim("glabs_image")
    queue.attach_provider_task(provider["job_id"], provider_running["lease_token"], "provider-original-42")
    uncertain = queue.submit("proj_phase_b", "voice_synthesis", "voice-restart-000001", {}, 0)
    queue.claim("voice_synthesis")

    result = recover_interrupted(queue)

    assert result == {"resume_existing_provider_task": 2, "blocked_uncertain_operation": 1}
    assert queue.get(assembly["job_id"])["state"] == "QUEUED"
    recovered = queue.get(provider["job_id"])
    assert (recovered["state"], recovered["provider_task_id"], recovered["resume_only"]) == (
        "QUEUED", "provider-original-42", 1)
    assert queue.get(uncertain["job_id"])["state"] == "BLOCKED_REVIEW"


def test_queue_api_itemizes_kind_specific_actions_progress_and_credentials_block(tmp_path):
    app = create_app(tmp_path / "state.sqlite", tmp_path / "media")
    store, queue = app.state.store, app.state.queue
    store.create_project("proj_queue_view", "Queue view")
    managed = queue.submit("proj_queue_view", "glabs_image", "queue-managed-000001", {}, 0)
    render = queue.submit("proj_queue_view", "final_render", "queue-render-0000001", {}, 0)
    voice = queue.submit("proj_queue_view", "voice_synthesis", "queue-voice-00000001", {}, 0)
    with store._transaction() as db:
        db.execute("UPDATE jobs SET state='FAILED_RETRYABLE',error_code='GLABS_KEY_MISSING' WHERE job_id=?", (managed["job_id"],))
        db.execute("UPDATE jobs SET state='FAILED_RETRYABLE',error_code='RENDER_PROCESS_FAILED' WHERE job_id=?", (render["job_id"],))
        db.execute("UPDATE jobs SET state='BLOCKED_REVIEW',error_code='PROVIDER_CREDENTIALS_UNAVAILABLE' WHERE job_id=?", (voice["job_id"],))
        db.execute("INSERT INTO render_attempts(job_id,attempt_id,manifest_sha256,g4_approval_id,progress_frames,total_frames,created_at) VALUES(?,?,?,?,?,?,?)",
                   (render["job_id"], "attempt_queue", "a" * 64, "approval_g4", 27, 120, "2026-10-27T00:00:00Z"))
    rows = TestClient(app).get("/api/v1/projects/proj_queue_view/jobs").json()
    by_kind = {row["kind"]: row for row in rows}
    assert by_kind["glabs_image"]["retry_action"] == "managed_resume"
    assert by_kind["final_render"]["retry_action"] == "render_retry"
    assert by_kind["final_render"]["progress"] == {"completed": 27, "total": 120}
    assert by_kind["voice_synthesis"]["retry_action"] is None
    assert by_kind["voice_synthesis"]["state"] == "BLOCKED_REVIEW"
    assert all("payload_json" not in row and "lease_token" not in row for row in rows)


def _three_requirement_story(project: str) -> dict:
    story = json.loads(STORY.read_text("utf-8"))
    story["project"]["project_id"] = project
    original = story["asset_requirements"][0]
    for number in (2, 3):
        item = copy.deepcopy(original)
        item["requirement_id"] = f"req_00{number}"
        item["subject"] = f"Synthetic source {number}"
        story["asset_requirements"].append(item)
        story["sections"][0]["asset_requirement_refs"].append(item["requirement_id"])
    return story


def _manual(resolver: AssetResolution, assets: AssetCandidates, store: ProjectStore,
            project: str, requirement: str, suffix: str) -> dict:
    resolver.choose(project, requirement, "MANUAL_UPLOAD", "Explicit synthetic integration source",
                    store.revision(project))
    return assets.manual(project, requirement, PNG, "Synthetic " + suffix,
                         "Synthetic historical context", "Synthetic test rights")


def _review(requirement: str, candidate: dict, rights: str = "ELIGIBLE") -> dict:
    return {"requirement_id": requirement, "candidate_id": candidate["candidate_id"],
            "original_sha256": candidate["original_sha256"], "rights_status": rights,
            "rights_evidence_note": "Explicit synthetic rights review",
            "historical_context_note": "Explicit synthetic period review"}


def test_batch_preflight_itemizes_mixed_rows_and_atomic_commit_stays_zero(tmp_path):
    project = "proj_batch_items"
    store = _store(tmp_path, project)
    story = _three_requirement_story(project)
    store.import_story(StoryCandidate.parse(story), 0)
    resolver, assets = AssetResolution(store), AssetCandidates(store)
    _manual(resolver, assets, store, project, "req_001", "old one")
    old_two = _manual(resolver, assets, store, project, "req_002", "old two")
    _manual(resolver, assets, store, project, "req_003", "old three")
    changed = copy.deepcopy(story)
    changed["asset_requirements"][1]["subject"] = "Changed exact source identity"
    store.import_story(StoryCandidate.parse(changed), store.revision(project))
    current_one = assets.manual(project, "req_001", PNG, "current one",
                                "Current context", "Synthetic test rights")
    resolver.choose(project, "req_002", "MANUAL_UPLOAD", "Changed source needs new review", store.revision(project))
    current_three = assets.manual(project, "req_003", PNG, "current three",
                                  "Current context", "Synthetic test rights")
    rows = [_review("req_001", current_one), _review("req_002", old_two),
            _review("req_003", current_three, "UNKNOWN")]
    revision = store.revision(project)

    checked = resolver.validate_batch(project, rows, revision)

    assert {row["requirement_id"]: row["status"] for row in checked["items"]} == {
        "req_001": "VALID", "req_002": "STALE", "req_003": "INVALID"}
    with pytest.raises(ContractViolation): resolver.approve_batch(project, rows, revision)
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM asset_approval_heads WHERE project_id=?", (project,)).fetchone()[0] == 0
    approved = resolver.approve_batch(project, [rows[0]], revision)
    assert [row["requirement_id"] for row in approved["approved"]] == ["req_001"]
    stale_revision = approved["project_revision"]
    with store._transaction() as db:
        db.execute("UPDATE projects SET revision=revision+1 WHERE project_id=?", (project,))
    with pytest.raises(ContractViolation, match="REVISION_CONFLICT"):
        resolver.approve_batch(project, [_review("req_003", current_three)], stale_revision)


def test_backup_restore_preserves_database_gate_heads_and_exact_artifacts(tmp_path):
    project = "proj_backup_restore"
    store = _store(tmp_path / "source", project)
    story = json.loads(STORY.read_text("utf-8")); story["project"]["project_id"] = project
    store.import_story(StoryCandidate.parse(story), 0)
    GateService(store)
    artifacts = {kind: store.put_artifact((kind + " exact bytes").encode(), kind)
                 for kind in ("voice_audio", "word_map", "original", "final_mp4", "attribution_manifest", "render_input_manifest")}
    with store._transaction() as db:
        for gate in ("G1", "G2", "G3", "G4", "G5"):
            db.execute("INSERT INTO gate_heads VALUES(?,?,?,?,?)", (project, gate, "a" * 64, "b" * 64, "approval_" + gate.lower()))
        db.execute("CREATE TABLE acceptance_export(project_id TEXT,mp4_sha TEXT,credits_sha TEXT,manifest_sha TEXT)")
        db.execute("INSERT INTO acceptance_export VALUES(?,?,?,?)",
                   (project, artifacts["final_mp4"], artifacts["attribution_manifest"], artifacts["render_input_manifest"]))
        db.execute("CREATE TABLE local_provider_settings(provider TEXT PRIMARY KEY,api_key TEXT NOT NULL,base_url TEXT NOT NULL)")
        db.execute("INSERT INTO local_provider_settings VALUES('glabs_webhook','do-not-back-up','https://example.invalid')")
    backup = tmp_path / "backup"
    manifest = create_backup(store.database, store.artifacts.root, backup, application_root=ROOT)
    restored = tmp_path / "restored"
    restore_backup(backup, restored)

    reopened = create_app(restored / "data" / "historical-studio.sqlite", restored / "data" / "media")
    response = TestClient(reopened).get("/api/v1/projects/" + project)
    assert response.status_code == 200
    assert manifest["database"]["integrity_check"] == "ok" and not manifest["credentials_included"]
    with reopened.state.store._connection() as db:
        assert {row[0] for row in db.execute("SELECT gate_id FROM gate_heads WHERE project_id=?", (project,))} == {"G1", "G2", "G3", "G4", "G5"}
        assert db.execute("SELECT api_key FROM local_provider_settings WHERE provider='glabs_webhook'").fetchone()[0] == ""
    for kind, digest in artifacts.items():
        assert reopened.state.store.get_artifact(digest) == (kind + " exact bytes").encode()
    with pytest.raises(BackupError, match="RESTORE_DESTINATION_EXISTS"):
        restore_backup(backup, restored)
    victim = backup / "media" / manifest["artifacts"][0]["relative_path"]
    victim.unlink()
    with pytest.raises(BackupError, match="RESTORE_ARTIFACT_TAMPERED"):
        restore_backup(backup, tmp_path / "tampered-restore")


@pytest.mark.skipif(os.name != "nt", reason="B3-05 is Windows-only")
def test_launch_real_backend_and_built_ui_then_clean_exit(tmp_path):
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        pytest.fail("Build frontend before the B3-05 launcher integration test")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0)); port = reservation.getsockname()[1]
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               str(ROOT / "scripts" / "windows" / "start-studio.ps1"), "-Smoke", "-NoBrowser",
               "-SkipBootstrap", "-Port", str(port), "-DataRoot", str(tmp_path / "persistent")]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "STUDIO_SMOKE_PASS" in completed.stdout and "STUDIO_STOPPED" in completed.stdout
    assert (tmp_path / "persistent" / "historical-studio.sqlite").is_file()


@pytest.mark.skipif(os.name != "nt", reason="B3-05 is Windows-only")
def test_launch_rejects_occupied_port_without_orphan(tmp_path):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0)); occupied.listen(); port = occupied.getsockname()[1]
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "scripts" / "windows" / "start-studio.ps1"), "-Smoke", "-NoBrowser",
            "-SkipBootstrap", "-Port", str(port), "-DataRoot", str(tmp_path / "occupied")],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert completed.returncode != 0
    assert "already in use" in completed.stdout + completed.stderr
