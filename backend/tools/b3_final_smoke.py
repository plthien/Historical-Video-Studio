"""B3-04/B3-06 evidence entry points; live mode validates only operator-owned data."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

from backend.app.contracts import ContractViolation
from backend.app.projects.gates import GateService
from backend.app.projects.storage import ProjectStore


ROOT = Path(__file__).resolve().parents[2]
G04 = ROOT / "renderer" / ".artifacts" / "b3-delivery" / "g04-real-process-kill-restart.json"


def _head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


def restart_during_render() -> None:
    rerun = True
    if G04.is_file():
        try:
            previous = json.loads(G04.read_text("utf-8"))
            rerun = (previous.get("code_identity") != _head()
                     or previous.get("result") != "REAL_WINDOWS_KILL_RESTART_PASS")
        except (OSError, json.JSONDecodeError):
            pass
    if rerun:
        subprocess.run([sys.executable, "-m", "backend.tools.b3_delivery_fixture"], cwd=ROOT, check=True)
    evidence = json.loads(G04.read_text("utf-8"))
    original, recovered = evidence["original_identity"], evidence["recovered_identity"]
    if (evidence.get("result") != "REAL_WINDOWS_KILL_RESTART_PASS"
            or evidence.get("code_identity") != _head()
            or not evidence["original_process"]["live_before_kill"]
            or not evidence["original_process"]["renderer_dead_after_kill"]
            or original["job_id"] != recovered["job_id"]
            or original["attempt_id"] != recovered["attempt_id"]
            or original["manifest_sha256"] != recovered["manifest_sha256"]
            or not recovered["lease_changed"]
            or evidence["single_owner"]["duplicate_owners"] != 0):
        raise RuntimeError("B3_G04_REAL_PROCESS_EVIDENCE_INVALID")
    print(json.dumps({"status": "LOCAL_PASS", "scope": "REAL_WINDOWS_PROCESS_SYNTHETIC_MEDIA",
                      "evidence": str(G04), "code_identity": evidence["code_identity"],
                      "job_id": original["job_id"], "attempt_id": original["attempt_id"]}))


def _blocked(missing: list[str]) -> None:
    print(json.dumps({"status": "BLOCKED", "scope": "REAL_TWO_TOPIC_LIVE_ACCEPTANCE",
                      "missing": missing, "side_effects": "NONE"}))
    raise SystemExit(2)


class LiveAuthorityBlocked(RuntimeError):
    """Operator data is incomplete/stale; this is not an application crash."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def verify_live_project_authority(store: ProjectStore, project: str) -> dict:
    """Read-only reconstruction of the current G1-G5/export authority."""
    from backend.app.assets.resolution import AssetResolution
    from backend.app.director import draft
    from backend.app.render.worker import verify_g5_approval
    from backend.app.voice.workflow import word_map_ready

    # GateService.__init__ owns schema bootstrap. Live preflight must not write,
    # so bind the already-initialized operator store directly for board reads.
    gates = GateService.__new__(GateService)
    gates.store = store
    board = {item["gate_id"]: item for item in gates.board(project)}
    reasons = []
    for gate_id in ("G1", "G2", "G3", "G4", "G5"):
        item = board.get(gate_id)
        if item is None or item["state"] != "APPROVED":
            state = item["state"] if item else "MISSING"
            blockers = item.get("blockers", []) if item else ["GATE_NOT_FOUND"]
            reasons.append(f"{project}:{gate_id}:{state}:{','.join(blockers) or 'CURRENT_APPROVAL_REQUIRED'}")
    with store._connection() as db:
        heads = {row[0]: {"candidate_sha256": row[1], "dependency_fingerprint": row[2],
                          "approval_id": row[3]}
                 for row in db.execute(
                     "SELECT gate_id,candidate_sha256,dependency_fingerprint,approval_id "
                     "FROM gate_heads WHERE project_id=?", (project,))}
        for gate_id, item in board.items():
            head = heads.get(gate_id)
            if (not head or head["candidate_sha256"] != item["candidate_sha256"]
                    or head["dependency_fingerprint"] != item["dependency_fingerprint"]):
                reasons.append(f"{project}:{gate_id}:HEAD_DOES_NOT_MATCH_CURRENT_CANDIDATE")
        if not word_map_ready(db, project):
            reasons.append(f"{project}:G2:CURRENT_VERIFIED_WORD_MAP_REQUIRED")
        story_row = db.execute(
            "SELECT sha256,story_json FROM story_candidates WHERE project_id=? ORDER BY revision DESC LIMIT 1",
            (project,)).fetchone()
        if not story_row:
            reasons.append(f"{project}:G1:CURRENT_STORY_REQUIRED")
            story = None
        else:
            story = json.loads(story_row[1])
        required_ids = {item["requirement_id"] for item in story["asset_requirements"]} if story else set()
        source_rows = db.execute(
            "SELECT e.requirement_id,e.original_sha256,e.evidence_json "
            "FROM asset_approval_heads h JOIN asset_approval_events e ON e.approval_id=h.approval_id "
            "WHERE h.project_id=?", (project,)).fetchall()
        actual_ids = {row[0] for row in source_rows}
        if actual_ids != required_ids:
            reasons.append(f"{project}:G3:REQUIREMENT_COVERAGE_MISMATCH:"
                           f"expected={sorted(required_ids)}:actual={sorted(actual_ids)}")
        for requirement_id, original_sha, raw_evidence in source_rows:
            evidence = json.loads(raw_evidence)
            if (evidence.get("rights_status") != "ELIGIBLE"
                    or not evidence.get("rights_evidence_note")
                    or not evidence.get("historical_context_note")
                    or evidence.get("original_sha256") != original_sha):
                reasons.append(f"{project}:G3:{requirement_id}:RIGHTS_OR_ORIGINAL_MISBOUND")
        export = db.execute(
            "SELECT job_id,g5_approval_id,mp4_artifact_id,credits_artifact_id,manifest_artifact_id,export_json "
            "FROM delivery_exports WHERE project_id=? ORDER BY rowid DESC LIMIT 1", (project,)).fetchone()
    if reasons:
        raise LiveAuthorityBlocked(reasons)

    with store._connection() as db:
        g3_candidate = AssetResolution.gate_candidate(db, project, store)
    if not g3_candidate or tuple(g3_candidate) != (
            heads["G3"]["candidate_sha256"], heads["G3"]["dependency_fingerprint"]):
        raise LiveAuthorityBlocked([f"{project}:G3:CURRENT_SOURCE_AUTHORITY_MISMATCH"])
    if not export:
        raise LiveAuthorityBlocked([f"{project}:G5:CURRENT_EXPORT_REQUIRED"])
    try:
        draft.verify_review_candidate(store, project, heads["G4"]["candidate_sha256"],
                                      heads["G4"]["dependency_fingerprint"])
        candidate = verify_g5_approval(store, project, heads["G5"]["approval_id"], export[0])
        dependencies = candidate["dependencies"]
        if (export[1] != heads["G5"]["approval_id"]
                or export[2] != dependencies["mp4_sha256"]
                or export[3] != dependencies["attribution_sha256"]
                or export[4] != dependencies["render_input_manifest_sha256"]):
            raise LiveAuthorityBlocked([f"{project}:G5:EXPORT_NOT_BOUND_TO_CURRENT_RENDER"])
        for digest in (export[2], export[3], export[4], dependencies["qc_report_sha256"]):
            store.get_artifact(digest)
    except ContractViolation as exc:
        raise LiveAuthorityBlocked([f"{project}:{exc.code}:{exc.remediation}"]) from exc
    return {"project_id": project, "story_sha256": story_row[0], "export": export,
            "heads": heads, "board": board, "g5_candidate": candidate}


def verify_distinct_story_identities(projects: list[dict]) -> None:
    if len({item["story_sha256"] for item in projects}) != len(projects):
        raise LiveAuthorityBlocked(["two distinct current StoryPackage identities are required"])


def full_flow_two_topics(mode: str) -> None:
    if mode == "local":
        # This command is the B3-06 owner path, not a reader of a possibly
        # inherited B3-03 summary.  The fixture deletes/rebuilds its SQLite
        # source and drives the real G1..G5 owners, Remotion, QC and export.
        flow_run_id = str(uuid.uuid4())
        flow_root = ROOT / "renderer/.artifacts/local-full-flow" / flow_run_id / "project"
        evidence_dir = flow_root.parent / "delivery"
        project_id = "proj_local_full_" + flow_run_id.replace("-", "")[:16]
        subprocess.run([sys.executable, "-m", "backend.tools.b3_delivery_fixture",
                        "--flow-root", str(flow_root), "--evidence-dir", str(evidence_dir),
                        "--project-id", project_id, "--direct-render"], cwd=ROOT, check=True)
        summary = evidence_dir / "summary.json"
        evidence = json.loads(summary.read_text("utf-8"))
        if evidence.get("scope") != "SYNTHETIC_TEST_ONLY" or evidence["render_job"]["qc_status"] != "PASS":
            raise RuntimeError("B3_SYNTHETIC_FULL_FLOW_INVALID")
        config_path = flow_root.with_suffix(".json")
        config = json.loads(config_path.read_text("utf-8"))
        store = ProjectStore(config["db"], config["artifactRoot"])
        authority = verify_live_project_authority(store, evidence["project"])
        with store._connection() as db:
            before = {"jobs": db.execute("SELECT COUNT(*) FROM jobs WHERE project_id=?",
                                          (evidence["project"],)).fetchone()[0],
                      "exports": db.execute("SELECT COUNT(*) FROM delivery_exports WHERE project_id=?",
                                             (evidence["project"],)).fetchone()[0]}
        from fastapi.testclient import TestClient
        from backend.app.api.server import create_app
        reopened = create_app(config["db"], config["artifactRoot"])
        client = TestClient(reopened)
        project_response = client.get(f"/api/v1/projects/{evidence['project']}")
        jobs_response = client.get(f"/api/v1/projects/{evidence['project']}/jobs")
        if project_response.status_code != 200 or jobs_response.status_code != 200:
            raise RuntimeError("B3_REOPEN_API_READ_FAILED")
        with reopened.state.store._connection() as db:
            after = {"jobs": db.execute("SELECT COUNT(*) FROM jobs WHERE project_id=?",
                                         (evidence["project"],)).fetchone()[0],
                     "exports": db.execute("SELECT COUNT(*) FROM delivery_exports WHERE project_id=?",
                                            (evidence["project"],)).fetchone()[0]}
        if after != before:
            raise RuntimeError("B3_REOPEN_CREATED_SIDE_EFFECTS")
        g04 = json.loads((summary.parent / "g04-real-process-kill-restart.json").read_text("utf-8"))
        trace = {
            "schema_version": "B3LocalFullFlowTrace.v1", "status": "LOCAL_CODE_PASS",
            "scope": "SYNTHETIC_TEST_ONLY", "code_identity": _head(),
            "flow_run_id": flow_run_id, "project_id": evidence["project"],
            "story_sha256": authority["story_sha256"],
            "gate_approval_ids": {gate: authority["heads"][gate]["approval_id"]
                                  for gate in ("G1", "G2", "G3", "G4", "G5")},
            "render": {"job_id": evidence["render_job"]["render_job_id"],
                       "attempt_id": evidence["render_job"]["attempt_id"],
                       "manifest_sha256": evidence["render_job"]["render_input_manifest_sha256"],
                       "qc_status": evidence["render_job"]["qc_status"],
                       "ffprobe": g04["media"]["ffprobe"]},
            "export": evidence["export"],
            "reopen": {"project_status": project_response.status_code,
                       "job_rows_visible": len(jobs_response.json()),
                       "counts_before": before, "counts_after": after,
                       "created_jobs_or_exports": False},
            "negative_cases": evidence["negative_cases"],
            "browser": {"config": str(config_path),
                        "evidence": "frontend/.artifacts/delivery/download.json"},
            "live_two_topic_acceptance": "BLOCKED_PENDING_OPERATOR_INPUT",
        }
        trace_path = ROOT / "reports/acceptance/generated/local-full-flow-trace.json"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(json.dumps(trace, indent=2), "utf-8")
        print(json.dumps({"status": "LOCAL_CODE_PASS", "scope": "SYNTHETIC_TEST_ONLY",
                          "project_id": evidence["project"], "flow_run_id": trace["flow_run_id"],
                          "evidence": str(trace_path),
                          "live_two_topic_acceptance": "BLOCKED"}))
        return
    missing = []
    database, media = os.getenv("HVS_DB"), os.getenv("HVS_MEDIA")
    projects = [value.strip() for value in os.getenv("HVS_LIVE_PROJECT_IDS", "").split(",") if value.strip()]
    if not database or not Path(database).is_file(): missing.append("HVS_DB pointing to the operator database")
    if not media or not Path(media).is_dir(): missing.append("HVS_MEDIA pointing to immutable operator media")
    if len(projects) != 2 or len(set(projects)) != 2: missing.append("two distinct HVS_LIVE_PROJECT_IDS")
    if os.getenv("HVS_LIVE_OPERATOR_ATTESTATION") != "EXPLICIT_G1_G2_G3_G4_G5":
        missing.append("HVS_LIVE_OPERATOR_ATTESTATION=EXPLICIT_G1_G2_G3_G4_G5")
    if os.getenv("HVS_LIVE_RIGHTS_ATTESTATION") != "VERIFIED_ORIGINAL_RIGHTS":
        missing.append("HVS_LIVE_RIGHTS_ATTESTATION=VERIFIED_ORIGINAL_RIGHTS")
    if missing: _blocked(missing)
    store = ProjectStore(database, media)
    verified = []
    with sqlite3.connect(database) as db:
        titles = {project: db.execute("SELECT title FROM projects WHERE project_id=?", (project,)).fetchone()
                  for project in projects}
    for project in projects:
        if not titles[project]:
            _blocked([f"{project}:PROJECT_NOT_FOUND"])
        try:
            authority = verify_live_project_authority(store, project)
        except LiveAuthorityBlocked as exc:
            _blocked(exc.reasons)
        export = authority["export"]
        movie = store.artifacts.path(export[2])
        try:
            probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                               "-of", "json", str(movie)], check=True,
                                              capture_output=True, text=True).stdout)
        except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
            _blocked([f"{project}:MP4_FFPROBE_INVALID:{type(exc).__name__}"])
        video = next((row for row in probe["streams"] if row["codec_type"] == "video"), None)
        audio = next((row for row in probe["streams"] if row["codec_type"] == "audio"), None)
        duration = float(probe["format"]["duration"])
        if (not video or not audio or video["codec_name"] != "h264" or audio["codec_name"] != "aac"
                or video.get("width") != 1920 or video.get("height") != 1080
                or video.get("r_frame_rate") != "30/1" or not 300 <= duration <= 600):
            _blocked([f"{project}:5-10_MINUTE_1080P30_H264_AAC_REQUIRED"])
        verified.append({"project_id": project, "title": titles[project][0],
                         "story_sha256": authority["story_sha256"],
                         "mp4_sha256": export[2], "duration_seconds": duration})
    try:
        verify_distinct_story_identities(verified)
    except LiveAuthorityBlocked as exc:
        _blocked(exc.reasons)
    print(json.dumps({"status": "LIVE_PASS", "scope": "REAL_TWO_TOPIC_LIVE_ACCEPTANCE",
                      "projects": verified, "code_identity": _head()}))
