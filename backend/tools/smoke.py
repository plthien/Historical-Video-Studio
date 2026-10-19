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
            from backend.app.projects.revisions import invalidate
            gates = GateService(store)
            if gates.board(project_id)[0]["state"] != "BLOCKED":
                raise RuntimeError("Unreviewed critical claims must block G1")
            print("gate-transitions: LOCAL_PASS, real SQLite gate blockers")
            return
        if args.case == "restart-running-job":
            from backend.app.jobs import JobQueue, recover_interrupted
            queue = JobQueue(store)
            job = queue.submit(project_id, "provider", "local-restart-job", {"content": 1}, 1)
            running = queue.claim()
            queue.attach_provider_task(job["job_id"], running["lease_token"], "provider-existing-1")
            stats = recover_interrupted(JobQueue(ProjectStore(root / "state.sqlite", root / "media")))
            recovered = queue.claim()
            if stats["resume_existing_provider_task"] != 1 or recovered["provider_task_id"] != "provider-existing-1":
                raise RuntimeError("Restart lost provider operation identity")
            print("restart-running-job: LOCAL_PASS, durable provider identity recovered")
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
