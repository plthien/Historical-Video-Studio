"""B3-04/B3-06 evidence entry points; live mode validates only operator-owned data."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

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
            rerun = json.loads(G04.read_text("utf-8")).get("code_identity") != _head()
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


def full_flow_two_topics(mode: str) -> None:
    if mode == "local":
        summary = ROOT / "renderer" / ".artifacts" / "b3-delivery" / "summary.json"
        if not summary.is_file():
            subprocess.run([sys.executable, "-m", "backend.tools.b3_delivery_fixture"], cwd=ROOT, check=True)
        evidence = json.loads(summary.read_text("utf-8"))
        if evidence.get("scope") != "SYNTHETIC_TEST_ONLY" or evidence["render_job"]["qc_status"] != "PASS":
            raise RuntimeError("B3_SYNTHETIC_FULL_FLOW_INVALID")
        print(json.dumps({"status": "LOCAL_CODE_PASS", "scope": "SYNTHETIC_TEST_ONLY",
                          "project_id": evidence["project"],
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
        for project in projects:
            title = db.execute("SELECT title FROM projects WHERE project_id=?", (project,)).fetchone()
            heads = {row[0]: row[1] for row in db.execute(
                "SELECT gate_id,approval_id FROM gate_heads WHERE project_id=?", (project,))}
            export = db.execute("SELECT mp4_artifact_id,credits_artifact_id,manifest_artifact_id,export_json "
                                "FROM delivery_exports WHERE project_id=? ORDER BY rowid DESC LIMIT 1", (project,)).fetchone()
            if not title or set(heads) != {"G1", "G2", "G3", "G4", "G5"} or not export:
                _blocked([f"complete G1-G5 heads and export for {project}"])
            audio = db.execute("SELECT f.audio_sha256,w.map_sha256 FROM final_audio f JOIN word_maps w "
                               "ON w.project_id=f.project_id AND w.approval_id=f.approval_id "
                               "AND w.audio_sha256=f.audio_sha256 AND w.transcript_sha256=f.transcript_sha256 "
                               "WHERE f.project_id=? AND f.approval_id=?", (project, heads["G2"])).fetchone()
            story_row = db.execute("SELECT story_json FROM story_candidates WHERE project_id=? ORDER BY revision DESC LIMIT 1",
                                   (project,)).fetchone()
            source_rows = db.execute("SELECT e.original_sha256 FROM asset_approval_heads h JOIN asset_approval_events e "
                                     "ON e.approval_id=h.approval_id WHERE h.project_id=?", (project,)).fetchall()
            required_sources = len(json.loads(story_row[0])["asset_requirements"]) if story_row else -1
            render = db.execute("SELECT r.qc_status,r.qc_report_sha256,r.attribution_sha256,j.output_sha256 "
                                "FROM delivery_exports e JOIN jobs j ON j.job_id=e.job_id "
                                "JOIN render_attempts r ON r.job_id=j.job_id WHERE e.project_id=? "
                                "AND e.g5_approval_id=? ORDER BY e.rowid DESC LIMIT 1",
                                (project, heads["G5"])).fetchone()
            if not audio or len(source_rows) != required_sources or not render or render[0] != "PASS":
                _blocked([f"current aligned WAV, complete reviewed sources and QC-passed G5 export for {project}"])
            for digest in (*audio, *(row[0] for row in source_rows), *render[1:]):
                store.get_artifact(digest)
            for digest in export[:3]: store.get_artifact(digest)
            movie = store.artifacts.path(export[0])
            probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                               "-of", "json", str(movie)], check=True,
                                              capture_output=True, text=True).stdout)
            video = next((row for row in probe["streams"] if row["codec_type"] == "video"), None)
            audio = next((row for row in probe["streams"] if row["codec_type"] == "audio"), None)
            duration = float(probe["format"]["duration"])
            if (not video or not audio or video["codec_name"] != "h264" or audio["codec_name"] != "aac"
                    or video.get("width") != 1920 or video.get("height") != 1080
                    or video.get("r_frame_rate") != "30/1" or not 300 <= duration <= 600):
                _blocked([f"5-10 minute 1080p30 H264/AAC export for {project}"])
            verified.append({"project_id": project, "title": title[0], "mp4_sha256": export[0],
                             "duration_seconds": duration})
    if verified[0]["title"] == verified[1]["title"]:
        _blocked(["two unrelated project topics/titles"])
    print(json.dumps({"status": "LIVE_PASS", "scope": "REAL_TWO_TOPIC_LIVE_ACCEPTANCE",
                      "projects": verified, "code_identity": _head()}))
