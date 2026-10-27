"""B3 owner regressions. Synthetic decisions/media are test-only, never live approval."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.server import create_app
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.contracts import ContractViolation
from backend.app.director.fingerprint import canonical
from backend.app.jobs import JobQueue, recover_interrupted
from backend.app.projects.storage import ProjectStore
from backend.app.render import DeliveryService
from backend.app.render import attribution, frame_qc, qc


def project(tmp_path, name="proj_b3_test"):
    store = ProjectStore(tmp_path / (name + ".sqlite"), tmp_path / (name + "-media"))
    store.create_project(name, "Synthetic B3 test only")
    return store


def test_render_api_rejects_draft_without_real_g4_manifest(tmp_path):
    app = create_app(tmp_path / "api.sqlite", tmp_path / "media")
    store = app.state.store; store.create_project("proj_render", "Synthetic render negative")
    response = TestClient(app).post("/api/v1/projects/proj_render/render-jobs",
        headers={"Idempotency-Key": "render-no-g4-0001"},
        json={"expected_revision": 0, "codec": "h264", "container": "mp4"})
    assert response.status_code in (422, 424)
    assert response.json()["code"] == "G4_APPROVAL_REQUIRED"
    assert JobQueue(store).list_for_project("proj_render") == []


def test_render_local_recovery_requeues_exact_manifest_but_cancel_is_terminal(tmp_path):
    store = project(tmp_path); queue = JobQueue(store)
    manifest_sha = store.put_artifact(b'{"schema_version":"RenderInputManifest.v1"}', "render_input_manifest")
    job = queue.submit("proj_b3_test", "final_render", "render-recovery-001",
                       {"render_input_manifest_sha256": manifest_sha}, 0)
    running = queue.claim(job_id=job["job_id"]); assert running["state"] == "RUNNING"
    assert recover_interrupted(queue) == {"resume_existing_provider_task": 1,
                                          "blocked_uncertain_operation": 0}
    assert queue.get(job["job_id"])["state"] == "QUEUED"
    assert queue.cancel(job["job_id"])["state"] == "CANCELLED"
    assert queue.claim(job_id=job["job_id"]) is None


def test_render_manifest_idempotency_conflict_cannot_duplicate_job(tmp_path):
    store = project(tmp_path); queue = JobQueue(store)
    one = queue.submit("proj_b3_test", "final_render", "render-idempotent-001", {"manifest": "a"}, 0)
    assert queue.submit("proj_b3_test", "final_render", "render-idempotent-001", {"manifest": "a"}, 0)["job_id"] == one["job_id"]
    with pytest.raises(ContractViolation, match="IDEMPOTENCY_CONFLICT"):
        queue.submit("proj_b3_test", "final_render", "render-idempotent-001", {"manifest": "b"}, 0)


def test_render_restart_blocks_while_exact_local_process_is_alive(tmp_path):
    store = project(tmp_path); queue = JobQueue(store); DeliveryService(store, queue)
    manifest_sha = store.put_artifact(b'{"video":{"total_frames":1}}', "render_input_manifest")
    job = queue.submit("proj_b3_test", "final_render", "render-live-process-001",
                       {"render_input_manifest_sha256": manifest_sha}, 0)
    queue.claim(job_id=job["job_id"])
    with store._transaction() as db:
        db.execute("INSERT INTO render_attempts(job_id,attempt_id,manifest_sha256,g4_approval_id,total_frames,"
                   "process_id,created_at) VALUES(?,?,?,?,?,?,?)",
                   (job["job_id"], "attempt_live", manifest_sha, "approval_g4", 1, os.getpid(),
                    "2026-01-01T00:00:00+00:00"))
    stats = recover_interrupted(queue)
    assert stats["blocked_uncertain_operation"] == 1
    assert queue.get(job["job_id"])["state"] == "BLOCKED_REVIEW"


def test_render_queued_job_is_dispatched_by_fresh_lifespan_once(tmp_path, monkeypatch):
    app = create_app(tmp_path / "startup.sqlite", tmp_path / "startup-media")
    store = app.state.store; store.create_project("proj_startup", "Synthetic startup dispatch")
    queue = app.state.queue
    manifest_sha = store.put_artifact(canonical({"video": {"total_frames": 1}}), "render_input_manifest")
    job = queue.submit("proj_startup", "final_render", "startup-render-0001",
                       {"render_input_manifest_sha256": manifest_sha}, 0)
    with store._transaction() as db:
        db.execute("INSERT INTO render_attempts(job_id,attempt_id,manifest_sha256,g4_approval_id,"
                   "total_frames,created_at) VALUES(?,?,?,?,?,?)",
                   (job["job_id"], "attempt_startup", manifest_sha, "approval_g4", 1,
                    "2026-01-01T00:00:00+00:00"))
    calls = []
    def process(job_id):
        claimed = queue.claim("final_render", job_id=job_id)
        calls.append((job_id, claimed["lease_token"] if claimed else None))
        if claimed:
            output = store.put_artifact(b"startup-dispatch-output", "test_output")
            queue.finish(job_id, claimed["lease_token"], output)
        return queue.get(job_id)
    monkeypatch.setattr(app.state.delivery, "process", process)
    with TestClient(app):
        deadline = time.monotonic() + 5
        while queue.get(job["job_id"])["state"] != "SUCCEEDED" and time.monotonic() < deadline:
            time.sleep(.01)
    assert queue.get(job["job_id"])["state"] == "SUCCEEDED"
    assert len(calls) == 1 and calls[0][0] == job["job_id"]
    assert calls[0][1] is not None


def _ffmpeg():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Native FFmpeg/FFprobe required; Windows CI installs both")


def _wav(path: Path, *, duration=1):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency=440:sample_rate=48000:duration={duration}",
                    "-ac", "1", "-c:a", "pcm_s16le", str(path)], check=True)


def _movie(path: Path, *, color="red", fps=30, audio=True, duration=1,
           audio_volume=1.0, black_frame: int | None = None):
    command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
               f"color=c={color}:s=1920x1080:r={fps}:d={duration}"]
    if audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}"]
    if black_frame is not None:
        command += ["-vf", f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='eq(n,{black_frame})'"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        command += ["-af", f"volume={audio_volume}", "-c:a", "aac", "-b:a", "128k"]
    command += [str(path)]
    subprocess.run(command, check=True)


def _qc_manifest(store, wav: Path, frames=30):
    wav_sha = store.put_artifact(wav.read_bytes(), "final_audio_wav")
    return {"video": {"total_frames": frames}, "audio": {"duration_samples": frames * 1600,
            "sample_rate": 48000, "wav_sha256": wav_sha, "word_map_sha256": "b" * 64},
            "g4_manifest_sha256": "c" * 64}


def test_qc_ffprobe_and_decoded_frames_accept_real_h264_aac(tmp_path, monkeypatch):
    _ffmpeg(); movie = tmp_path / "good.mp4"; wav = tmp_path / "good.wav"; _movie(movie); _wav(wav)
    store = project(tmp_path, "proj_qc_good")
    monkeypatch.setattr("backend.app.render.qc.draft.load", lambda *_: {
        "timeline": {"scenes": [{"start_frame": 0}]}})
    report, report_sha = qc.inspect(store, "proj_qc_good", movie, _qc_manifest(store, wav))
    assert report["status"] == "PASS" and store.get_artifact(report_sha) == canonical(report)
    streams = report["ffprobe"]["streams"]
    assert {s["codec_name"] for s in streams} >= {"h264", "aac"}
    assert len(report["decoded_frames"]["sampled_frames"]) == 3
    assert report["decoded_frames"]["full_stream"]["status"] == "PASS"
    assert report["decoded_audio"]["status"] == "PASS"


def test_qc_ffprobe_rejects_real_no_audio_and_wrong_fps(tmp_path, monkeypatch):
    _ffmpeg(); movie = tmp_path / "bad.mp4"; wav = tmp_path / "bad.wav"; _movie(movie, fps=24, audio=False); _wav(wav)
    store = project(tmp_path, "proj_qc_bad")
    monkeypatch.setattr("backend.app.render.qc.draft.load", lambda *_: {
        "timeline": {"scenes": [{"start_frame": 0}]}})
    report, _ = qc.inspect(store, "proj_qc_bad", movie, _qc_manifest(store, wav))
    assert report["status"] == "FAIL"
    assert {"QC_FRAME_RATE", "QC_FRAME_COUNT", "QC_AUDIO_CODEC"} <= set(report["problems"])


def test_black_frame_detection_decodes_actual_pixels(tmp_path):
    _ffmpeg(); movie = tmp_path / "black.mp4"; _movie(movie, color="black")
    evidence = frame_qc.inspect_frames(movie, 30, [])
    assert evidence["status"] == "FAIL" and evidence["unexpected_black_frames"] == [0, 15, 29]


def test_near_black_limited_range_is_rejected_but_dark_navy_is_valid(tmp_path):
    _ffmpeg(); near = tmp_path / "near-black.mp4"; navy = tmp_path / "navy.mp4"
    _movie(near, color="0x050505"); _movie(navy, color="navy")
    assert frame_qc.inspect_frames(near, 30, [])["full_stream"]["status"] == "FAIL"
    assert frame_qc.inspect_frames(navy, 30, [])["status"] == "PASS"


def test_qc_full_stream_rejects_unsampled_black_frame_80(tmp_path, monkeypatch):
    _ffmpeg(); movie = tmp_path / "frame80.mp4"; wav = tmp_path / "frame80.wav"
    _movie(movie, duration=4, black_frame=80); _wav(wav, duration=4)
    store = project(tmp_path, "proj_qc_frame80")
    monkeypatch.setattr("backend.app.render.qc.draft.load", lambda *_: {
        "timeline": {"scenes": [{"start_frame": 0}, {"start_frame": 60}]}})
    report, _ = qc.inspect(store, "proj_qc_frame80", movie, _qc_manifest(store, wav, 120))
    intervals = report["decoded_frames"]["full_stream"]["black_intervals"]
    assert report["status"] == "FAIL" and "QC_VISUAL_ANOMALY" in report["problems"]
    assert any(item["start_frame"] <= 80 <= item["end_frame"] for item in intervals)


def test_qc_rejects_near_silent_aac_against_approved_audible_wav(tmp_path, monkeypatch):
    _ffmpeg(); movie = tmp_path / "silent.mp4"; wav = tmp_path / "approved.wav"
    _movie(movie, audio_volume=.00003); _wav(wav)
    store = project(tmp_path, "proj_qc_silent")
    monkeypatch.setattr("backend.app.render.qc.draft.load", lambda *_: {
        "timeline": {"scenes": [{"start_frame": 0}]}})
    report, _ = qc.inspect(store, "proj_qc_silent", movie, _qc_manifest(store, wav))
    assert report["status"] == "FAIL" and "QC_AUDIO_CONTENT_MISMATCH" in report["problems"]
    assert report["decoded_audio"]["approved_wav_sha256"] == _qc_manifest(store, wav)["audio"]["wav_sha256"]
    assert report["decoded_audio"]["global_deficit_db"] > 12


def test_attribution_covers_every_used_asset_and_blocks_missing_rights(tmp_path, monkeypatch):
    store = project(tmp_path, "proj_attr"); AssetResolution(store)
    original = store.put_artifact(b"synthetic original bytes", "original")
    metadata = {"title": "Synthetic archive item", "creator": "Test", "source_page_url": "https://example.test/item",
                "rights_statement": "Test-only", "provider": "manual_upload", "asset_class": "ARCHIVAL_PHOTO"}
    evidence = {"rights_status": "ELIGIBLE", "rights_evidence_note": "Synthetic test review",
                "historical_context_note": "Synthetic context", "asset_class": "ARCHIVAL_PHOTO"}
    with store._transaction() as db:
        db.execute("INSERT INTO asset_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   ("asset_test", "proj_attr", "req_test", "manual_upload", json.dumps(metadata),
                    hashlib.sha256(canonical(metadata)).hexdigest(), original, "image/png", 24, "CANDIDATE", 0))
        db.execute("INSERT INTO asset_approval_events VALUES(?,?,?,?,?,?,?,?,?)",
                   ("approval_attr", "proj_attr", "req_test", "d" * 64, "asset_test", "e" * 64,
                    original, json.dumps(evidence), "2026-01-01T00:00:00+00:00"))
    monkeypatch.setattr("backend.app.render.attribution.draft.load", lambda *_: {"timeline": {"scenes": [
        {"scene_id": "scene_test", "layers": [{"layer_id": "layer_test", "asset_id": "asset_test",
          "mask": {"asset_id": None}}]}]}})
    manifest = {"g4_manifest_sha256": "f" * 64}
    credits, credits_sha = attribution.build(store, "proj_attr", manifest)
    assert [x["asset_id"] for x in credits["assets"]] == ["asset_test"]
    assert store.get_artifact(credits_sha) == canonical(credits)
    monkeypatch.setattr("backend.app.render.attribution.draft.load", lambda *_: {"timeline": {"scenes": [
        {"scene_id": "scene_test", "layers": [{"layer_id": "layer_test", "asset_id": "forged",
          "mask": {"asset_id": None}}]}]}})
    with pytest.raises(ContractViolation, match="ATTRIBUTION_SOURCE_MISSING"):
        attribution.build(store, "proj_attr", manifest)


def test_gate_5_review_session_rejects_instant_seen_flag_and_export_forgery(tmp_path):
    store = project(tmp_path, "proj_gate5"); queue = JobQueue(store); service = DeliveryService(store, queue)
    manifest_doc = {"video": {"total_frames": 300}}
    manifest_sha = store.put_artifact(canonical(manifest_doc), "render_input_manifest")
    job = queue.submit("proj_gate5", "final_render", "gate5-review-job-001",
                       {"render_input_manifest_sha256": manifest_sha}, 0)
    candidate = canonical({"schema_version": "G5ReviewCandidate.v1"})
    candidate_sha = store.put_artifact(candidate, "g5_review_candidate")
    with store._transaction() as db:
        db.execute("UPDATE jobs SET state='SUCCEEDED',output_sha256=? WHERE job_id=?", ("a" * 64, job["job_id"]))
        db.execute("INSERT INTO render_attempts(job_id,attempt_id,manifest_sha256,g4_approval_id,total_frames,"
                   "output_sha256,qc_report_sha256,qc_status,attribution_sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (job["job_id"], "attempt_gate5", manifest_sha, "approval_g4", 300, "a" * 64,
                    "b" * 64, "PASS", "c" * 64, "2026-01-01T00:00:00+00:00"))
        db.execute("INSERT INTO g5_candidates VALUES(?,?,?,?,?)", (candidate_sha, "proj_gate5", job["job_id"],
                   "d" * 64, candidate.decode()))
    session = service.start_review("proj_gate5", job["job_id"])
    with pytest.raises(ContractViolation, match="G5_REVIEW_INCOMPLETE"):
        service.complete_review("proj_gate5", session["review_session_id"], session["nonce"])
    with pytest.raises(ContractViolation, match="G5_APPROVAL_REQUIRED"):
        service.export("proj_gate5", {"expected_revision": 0, "include_attribution": True,
                       "gate_g5_approval_id": "forged", "render_job_id": job["job_id"]})


def test_gate_5_muted_video_credits_viewing_but_not_listening(tmp_path, monkeypatch):
    store = project(tmp_path, "proj_gate5_muted"); queue = JobQueue(store); service = DeliveryService(store, queue)
    manifest_sha = store.put_artifact(canonical({"video": {"total_frames": 300}}), "render_input_manifest")
    job = queue.submit("proj_gate5_muted", "final_render", "gate5-muted-job-0001",
                       {"render_input_manifest_sha256": manifest_sha}, 0)
    candidate = canonical({"schema_version": "G5ReviewCandidate.v1"})
    candidate_sha = store.put_artifact(candidate, "g5_review_candidate")
    with store._transaction() as db:
        db.execute("UPDATE jobs SET state='SUCCEEDED',output_sha256=? WHERE job_id=?", ("a" * 64, job["job_id"]))
        db.execute("INSERT INTO render_attempts(job_id,attempt_id,manifest_sha256,g4_approval_id,total_frames,"
                   "output_sha256,qc_report_sha256,qc_status,attribution_sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (job["job_id"], "attempt_muted", manifest_sha, "approval_g4", 300, "a" * 64,
                    "b" * 64, "PASS", "c" * 64, "2026-01-01T00:00:00+00:00"))
        db.execute("INSERT INTO g5_candidates VALUES(?,?,?,?,?)", (candidate_sha, "proj_gate5_muted", job["job_id"],
                   "d" * 64, candidate.decode()))
    session = service.start_review("proj_gate5_muted", job["job_id"])
    with store._transaction() as db:
        db.execute("UPDATE g5_review_sessions SET last_monotonic=0 WHERE session_id=?", (session["review_session_id"],))
    monkeypatch.setattr("backend.app.render.worker.time.monotonic", lambda: 10.0)
    progress = service.review_heartbeat("proj_gate5_muted", session["review_session_id"], session["nonce"],
                                        10.0, True, False)
    assert progress["viewed_seconds"] == 10 and progress["listened_seconds"] == 0
    with pytest.raises(ContractViolation, match="G5_REVIEW_INCOMPLETE"):
        service.complete_review("proj_gate5_muted", session["review_session_id"], session["nonce"])
    with pytest.raises(ContractViolation, match="G5_REVIEW_PLAYER_STATE_INVALID"):
        service.review_heartbeat("proj_gate5_muted", session["review_session_id"], session["nonce"],
                                 10.0, False, True)
