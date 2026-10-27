"""Native short B3 closure fixture. Every approval is SYNTHETIC_TEST_ONLY."""
from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.server import create_app
from backend.app.director import draft
from backend.app.contracts import ContractViolation
from backend.app.jobs import JobQueue
from backend.app.projects.gates import GateService
from backend.app.projects.storage import ProjectStore
from backend.app.render import DeliveryService
from backend.app.render import qc

ROOT = Path(__file__).resolve().parents[2]


def main():
    subprocess.run([sys.executable, "-m", "renderer.scripts.prepare_host_fixture"],
                   cwd=ROOT, check=True)
    config = json.loads((ROOT / "renderer/.artifacts/approved-player-test.json").read_text("utf-8"))
    store = ProjectStore(config["db"], config["artifactRoot"]); project = config["project"]
    gates = GateService(store)
    queue = JobQueue(store); service = DeliveryService(store, queue)
    negatives = []
    try:
        service.submit(project, store.revision(project), "b3-draft-must-not-render")
        raise RuntimeError("Unapproved G4 draft rendered")
    except ContractViolation as exc:
        if exc.code != "G4_APPROVAL_REQUIRED": raise
        negatives.append(exc.code)
    candidate = draft.prepare_review_candidate(store, project, store.revision(project))
    try:
        gates.decide(project, "G4", {"decision": "APPROVED", "candidate_sha256": "f" * 64,
            "dependency_fingerprint": candidate["dependency_fingerprint"],
            "expected_revision": store.revision(project), "affected_ids": [], "comment": "forged negative"})
        raise RuntimeError("Forged G4 candidate approved")
    except ContractViolation as exc:
        if exc.code != "APPROVAL_REVISION_CONFLICT": raise
        negatives.append("FORGED_G4_BLOCKED")
    g4 = gates.decide(project, "G4", {"decision": "APPROVED", **candidate,
        "expected_revision": store.revision(project), "affected_ids": [],
        "comment": "SYNTHETIC_TEST_ONLY G4 decision for native B3 CI"})
    cancelled = service.submit(project, store.revision(project), "b3-native-cancel-0001")
    cancel_thread = threading.Thread(target=service.process, args=(cancelled["render_job_id"],))
    cancel_thread.start()
    deadline = time.monotonic() + 30
    while queue.get(cancelled["render_job_id"])["state"] == "QUEUED" and time.monotonic() < deadline:
        time.sleep(.05)
    queue.cancel(cancelled["render_job_id"]); cancel_thread.join(timeout=30)
    if cancel_thread.is_alive() or queue.get(cancelled["render_job_id"])["state"] != "CANCELLED":
        raise RuntimeError("B3_EXACT_LOCAL_PROCESS_CANCEL_FAILED")
    negatives.append("LOCAL_RENDER_CANCEL_CONFIRMED")
    queued = service.submit(project, store.revision(project), "b3-native-render-0001")
    queued_attempt = queued["attempt_id"]
    interrupted = queue.claim("final_render", job_id=queued["render_job_id"])
    if not interrupted or interrupted["state"] != "RUNNING":
        raise RuntimeError("B3_COULD_NOT_STAGE_INTERRUPTED_RENDER")
    # A fresh backend lifespan, not a request-side callback, must dispatch the
    # known-dead formerly RUNNING exact render job after recovery requeues it.
    restarted = create_app(config["db"], config["artifactRoot"])
    with TestClient(restarted):
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            rendered = restarted.state.delivery.read(project, queued["render_job_id"])
            if rendered["state"] not in ("QUEUED", "RUNNING"):
                break
            time.sleep(.25)
        else:
            raise RuntimeError("B3_RESTART_DISPATCH_TIMEOUT")
    service = DeliveryService(store, queue)
    if rendered["state"] != "SUCCEEDED" or rendered["qc_status"] != "PASS":
        raise RuntimeError("B3_NATIVE_RENDER_FAILED " + json.dumps(rendered))
    if rendered["attempt_id"] != queued_attempt:
        raise RuntimeError("B3_RESTART_CHANGED_ATTEMPT_LINEAGE")
    negatives.append("RECOVERED_QUEUED_FINAL_RENDER_AUTO_DISPATCHED")
    review = service.start_review(project, rendered["render_job_id"])
    time.sleep(.1)
    muted = service.review_heartbeat(project, review["review_session_id"], review["nonce"],
                                     store.revision(project), .1, True, False)
    if muted["listened_seconds"] != 0:
        raise RuntimeError("B3_MUTED_REVIEW_EARNED_LISTENING_CREDIT")
    try:
        service.complete_review(project, review["review_session_id"], review["nonce"])
        raise RuntimeError("B3_MUTED_REVIEW_COMPLETED")
    except ContractViolation as exc:
        if exc.code != "G5_REVIEW_INCOMPLETE": raise
        negatives.append("MUTED_REVIEW_LISTENED_ZERO_AND_COMPLETION_BLOCKED")
    review = service.start_review(project, rendered["render_job_id"])
    duration = rendered["progress"]["total_frames"] / 30
    position = 0.0
    while position < duration:
        time.sleep(.5); position = min(duration, position + .5)
        service.review_heartbeat(project, review["review_session_id"], review["nonce"],
                                 store.revision(project), position, True, True)
    service.complete_review(project, review["review_session_id"], review["nonce"])
    g5_board = next(x for x in gates.board(project) if x["gate_id"] == "G5")
    g5 = gates.decide(project, "G5", {"decision": "APPROVED",
        "candidate_sha256": g5_board["candidate_sha256"],
        "dependency_fingerprint": g5_board["dependency_fingerprint"],
        "expected_revision": store.revision(project), "affected_ids": [],
        "comment": "SYNTHETIC_TEST_ONLY complete audiovisual review in native B3 CI"})
    exported = service.export(project, {"expected_revision": store.revision(project),
        "gate_g5_approval_id": g5["approval_id"], "render_job_id": rendered["render_job_id"],
        "include_attribution": True})
    evidence = ROOT / "renderer/.artifacts/b3-delivery"; evidence.mkdir(parents=True, exist_ok=True)
    names = {"final.mp4": exported["mp4_artifact_id"], "credits.json": exported["credits_artifact_id"],
             "render-input-manifest.json": exported["manifest_artifact_id"],
             "qc-report.json": exported["qc_report_sha256"]}
    for name, identity in names.items():
        shutil.copyfile(store.artifacts.path(identity), evidence / name)
    render_manifest = json.loads(store.get_artifact(exported["manifest_artifact_id"]))
    source_mp4 = store.artifacts.path(exported["mp4_artifact_id"])
    black_mp4 = evidence / "negative-black-frame-80.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source_mp4), "-vf",
                    "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='eq(n,80)'",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", str(black_mp4)], check=True)
    black_report, _ = qc.inspect(store, project, black_mp4, render_manifest)
    if black_report["status"] != "FAIL" or "QC_VISUAL_ANOMALY" not in black_report["problems"]:
        raise RuntimeError("B3_INJECTED_BLACK_FRAME_NOT_REJECTED")
    (evidence / "negative-black-qc.json").write_text(json.dumps(black_report, indent=2), "utf-8")
    silent_mp4 = evidence / "negative-near-silent-aac.mp4"
    sample_rate = render_manifest["audio"]["sample_rate"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source_mp4), "-f", "lavfi", "-i",
                    f"sine=frequency=440:sample_rate={sample_rate}:duration={duration}",
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", "volume=0.00003",
                    "-c:a", "aac", "-ac", "1", "-ar", str(sample_rate), str(silent_mp4)], check=True)
    silent_report, _ = qc.inspect(store, project, silent_mp4, render_manifest)
    if silent_report["status"] != "FAIL" or "QC_AUDIO_CONTENT_MISMATCH" not in silent_report["problems"]:
        raise RuntimeError("B3_NEAR_SILENT_AAC_NOT_REJECTED")
    (evidence / "negative-audio-qc.json").write_text(json.dumps(silent_report, indent=2), "utf-8")
    verdict = {"schema_version": "B3ThreeP1Verdict.v1", "scope": "SYNTHETIC_TEST_ONLY",
               "restart": {"job_id": rendered["render_job_id"], "attempt_id": rendered["attempt_id"],
                           "manifest_sha256": rendered["render_input_manifest_sha256"],
                           "result": "RECOVERED_QUEUED_FINAL_RENDER_AUTO_DISPATCHED"},
               "black_frame": {"mp4_sha256": hashlib.sha256(black_mp4.read_bytes()).hexdigest(),
                               "problem": "QC_VISUAL_ANOMALY",
                               "intervals": black_report["decoded_frames"]["full_stream"]["black_intervals"]},
               "near_silent_aac": {"mp4_sha256": hashlib.sha256(silent_mp4.read_bytes()).hexdigest(),
                                   "problem": "QC_AUDIO_CONTENT_MISMATCH",
                                   "audio": silent_report["decoded_audio"]},
               "review": {"muted_listened_seconds": muted["listened_seconds"],
                          "muted_complete": "BLOCKED", "audible_complete": "PASS"},
               "positive": {"mp4_sha256": exported["mp4_artifact_id"],
                            "qc_status": rendered["qc_status"], "export_id": exported["export_id"]}}
    (evidence / "three-p1-verdict.json").write_text(json.dumps(verdict, indent=2), "utf-8")
    summary = {"scope": "SYNTHETIC_TEST_ONLY", "project": project,
               "g4_approval_id": g4["approval_id"], "g5_approval_id": g5["approval_id"],
               "negative_cases": negatives, "render_job": rendered, "export": exported}
    (evidence / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(json.dumps({"status": "LOCAL_PASS", "evidence": str(evidence), **exported}))


if __name__ == "__main__": main()
