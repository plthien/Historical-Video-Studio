"""Native short B3 closure fixture. Every approval is SYNTHETIC_TEST_ONLY."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from backend.app.director import draft
from backend.app.contracts import ContractViolation
from backend.app.jobs import JobQueue
from backend.app.projects.gates import GateService
from backend.app.projects.storage import ProjectStore
from backend.app.render import DeliveryService

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
    rendered = service.process(queued["render_job_id"])
    if rendered["state"] != "SUCCEEDED" or rendered["qc_status"] != "PASS":
        raise RuntimeError("B3_NATIVE_RENDER_FAILED " + json.dumps(rendered))
    review = service.start_review(project, rendered["render_job_id"])
    duration = rendered["progress"]["total_frames"] / 30
    position = 0.0
    while position < duration:
        time.sleep(.5); position = min(duration, position + .5)
        service.review_heartbeat(project, review["review_session_id"], review["nonce"], position, True)
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
    summary = {"scope": "SYNTHETIC_TEST_ONLY", "project": project,
               "g4_approval_id": g4["approval_id"], "g5_approval_id": g5["approval_id"],
               "negative_cases": negatives, "render_job": rendered, "export": exported}
    (evidence / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(json.dumps({"status": "LOCAL_PASS", "evidence": str(evidence), **exported}))


if __name__ == "__main__": main()
