"""Real local disk/SQLite smoke; not G1 approval or live provider evidence."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from backend.app.api.imports import import_story
from backend.app.projects.storage import ProjectStore
from backend.app.contracts import ContractViolation

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "contracts/examples/longform/StoryPackage.longform.synthetic.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["story-import", "reopen-project", "gate-transitions", "restart-running-job", "api-and-ui"], required=False)
    parser.add_argument("--mode", choices=["local"], default="local")
    parser.add_argument("--inspect", nargs=3, metavar=("DATABASE", "MEDIA_ROOT", "PROJECT_ID"))
    args = parser.parse_args()
    if args.inspect:
        db, media, project_id = args.inspect
        store = ProjectStore(db, media)
        candidate = store.get_story(project_id)
        print(json.dumps({"sha256": candidate.sha256, "revision": store.revision(project_id)}))
        return
    if not args.case:
        parser.error("--case required")
    data = EXAMPLE.read_bytes()
    with TemporaryDirectory() as dirname:
        root = Path(dirname)
        store = ProjectStore(root / "state.sqlite", root / "media")
        candidate = json.loads(data)
        project_id = candidate["project"]["project_id"]
        store.create_project(project_id, candidate["project"]["title"])
        result = import_story(store, data, expected_revision=0)
        if result["gate_state"] != "DRAFT" or len(store.get_story(project_id).data()["sections"]) != 24:
            raise RuntimeError("Story import did not preserve 24 sections in G1 draft")
        if args.case == "gate-transitions":
            from backend.app.projects.gates import GateService
            from backend.app.projects.models import StoryCandidate
            gates = GateService(store)
            if gates.board(project_id)[0]["state"] != "BLOCKED":
                raise RuntimeError("Unreviewed critical claims must block G1")
            revision = store.revision(project_id)
            for claim in candidate["claims"]:
                if claim["critical"]:
                    revision = gates.review_claim(project_id, claim["claim_id"], "REVIEWED",
                                                  "Synthetic test disposition only", revision)
            sha = store.get_story(project_id).sha256
            decision = {"decision": "APPROVED", "candidate_sha256": sha,
                        "dependency_fingerprint": sha, "expected_revision": revision}
            approved = gates.decide(project_id, "G1", decision)
            revised = json.loads(data)
            revised["sections"][0]["narration"] += " Corrected historical context."
            version_b = StoryCandidate.parse(revised)
            next_rev = store.import_story(version_b, approved["project_revision"])
            if gates.board(project_id)[0]["state"] != "STALE":
                raise RuntimeError("Old approved StoryPackage was not invalidated")
            for claim in revised["claims"]:
                if claim["critical"]:
                    next_rev = gates.review_claim(project_id, claim["claim_id"], "REVIEWED",
                                                  "Synthetic revised claim review only", next_rev)
            renewed = gates.decide(project_id, "G1", {"decision": "APPROVED",
                "candidate_sha256": version_b.sha256, "dependency_fingerprint": version_b.sha256,
                "expected_revision": next_rev})
            if gates.board(project_id)[0]["state"] != "APPROVED" or renewed["project_revision"] <= next_rev:
                raise RuntimeError("New candidate was not reapproved")
            print("gate-transitions: LOCAL_PASS, synthetic SQLite gate transitions only; no real operator approval")
            return
        if args.case == "restart-running-job":
            from backend.app.jobs import JobQueue, recover_interrupted
            queue = JobQueue(store)
            job = queue.submit(project_id, "provider", "local-restart-job", {"content": 1}, 1)
            running = queue.claim()
            queue.attach_provider_task(job["job_id"], running["lease_token"], "provider-existing-1")
            from fastapi.testclient import TestClient
            from backend.app.api.server import create_app
            with TestClient(create_app(root / "state.sqlite", root / "media")) as app:
                stats = app.app.state.recovery
                recovered = app.app.state.queue.claim()
                if stats["resume_existing_provider_task"] != 1 or recovered["provider_task_id"] != "provider-existing-1":
                    raise RuntimeError("App startup lost external provider operation identity")
                if not recovered["resume_only"]:
                    raise RuntimeError("Restart must prohibit a duplicate provider submit")
            print("restart-running-job: LOCAL_PASS, actual FastAPI lifespan recovery; no live provider")
            return
        if args.case == "api-and-ui":
            from fastapi.testclient import TestClient
            from backend.app.api.server import create_app
            web = TestClient(create_app(root / "state.sqlite", root / "media"))
            response = web.get(f"/api/v1/projects/{project_id}/gates")
            if response.status_code != 200 or len(response.json()) != 5:
                raise RuntimeError("Gate board API unavailable")
            if web.post(f"/api/v1/projects/{project_id}/voice/generate").status_code != 501:
                raise RuntimeError("Future backend incorrectly advertised as implemented")
            print("api-and-ui: LOCAL_PASS, A1 HTTP endpoints only; browser UI NOT_RUN")
            return
        if args.case == "reopen-project":
            digest = store.put_artifact(b"\x00\x01historical-original\xff", "original")
            observed = subprocess.check_output([
                sys.executable, "-m", "backend.tools.smoke", "--inspect",
                str(root / "state.sqlite"), str(root / "media"), project_id,
            ], text=True)
            if json.loads(observed)["sha256"] != result["candidate_sha256"]:
                raise RuntimeError("Cold process reopen returned different story content")
            if ProjectStore(root / "state.sqlite", root / "media").get_artifact(digest) != b"\x00\x01historical-original\xff":
                raise RuntimeError("Cold artifact read was corrupted")
        print(f"{args.case}: LOCAL_PASS, candidate_sha={result['candidate_sha256']}, revision=1, G1=DRAFT")


if __name__ == "__main__":
    main()
