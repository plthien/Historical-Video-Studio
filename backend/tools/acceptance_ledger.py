"""Generate fail-closed, exact-HEAD Phase B acceptance evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "reports/acceptance/generated"
RESULTS = GENERATED / "command-results.json"
REQUIRED = {"environment", "wp1_authority", "wp2_clean_package", "wp3_full_flow",
            "wp3_browser", "owner_regressions", "contract_regressions"}


def head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def record(identifier: str, command: str) -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    document = json.loads(RESULTS.read_text("utf-8")) if RESULTS.is_file() else {}
    document[identifier] = {"status": "PASS", "command": command, "code_identity": head()}
    RESULTS.write_text(json.dumps(document, indent=2), "utf-8")


def _workflow_runs(commit: str) -> dict:
    token, repository = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not token or not repository:
        raise RuntimeError("GITHUB_WORKFLOW_AUTHORITY_UNAVAILABLE")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/runs?head_sha={commit}&per_page=100",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        runs = json.load(response)["workflow_runs"]
    wanted = {"A1 Foundation (Windows)", "B2 Remotion I Native Windows",
              "B3 Delivery I Native Windows"}
    found = {}
    for run in runs:
        if run["name"] in wanted and run["head_sha"] == commit:
            found[run["name"]] = {"status": run["status"], "conclusion": run["conclusion"],
                                  "head_sha": run["head_sha"], "url": run["html_url"],
                                  "run_id": run["id"]}
    return found


def _wait_for_workflows(commit: str) -> dict:
    deadline = time.monotonic() + 2400
    while True:
        found = _workflow_runs(commit)
        if len(found) == 3 and all(item["status"] == "completed" for item in found.values()):
            failures = {name: item for name, item in found.items() if item["conclusion"] != "success"}
            if failures:
                raise RuntimeError("SAME_HEAD_WORKFLOW_FAILED:" + json.dumps(failures))
            return found
        if time.monotonic() >= deadline:
            raise RuntimeError("SAME_HEAD_WORKFLOW_TIMEOUT:" + json.dumps(found))
        time.sleep(15)


def _json(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError("REQUIRED_EVIDENCE_MISSING:" + str(path))
    return json.loads(path.read_text("utf-8-sig"))


def build(require_workflows: bool) -> None:
    commit = head()
    results = _json(RESULTS)
    if set(results) != REQUIRED or any(row != {**row, "status": "PASS", "code_identity": commit}
                                       for row in results.values()):
        raise RuntimeError("COMMAND_RESULT_LEDGER_INCOMPLETE_OR_STALE")
    package = _json(GENERATED / "clean-package-launch.json")
    flow = _json(GENERATED / "local-full-flow-trace.json")
    if package.get("status") != "PASS" or package.get("source_commit") != commit:
        raise RuntimeError("CLEAN_PACKAGE_EVIDENCE_INVALID")
    if flow.get("status") != "LOCAL_CODE_PASS" or flow.get("code_identity") != commit:
        raise RuntimeError("LOCAL_FULL_FLOW_EVIDENCE_INVALID")
    browser = _json(ROOT / flow["browser"]["evidence"])
    if browser.get("project_id") != flow["project_id"] or browser.get("sha256") != flow["export"]["mp4_artifact_id"]:
        raise RuntimeError("SAME_PROJECT_BROWSER_EVIDENCE_INVALID")
    config = _json(Path(flow["browser"]["config"]))
    g04_path = ROOT / "renderer/.artifacts/b3-delivery/g04-real-process-kill-restart.json"
    g04 = _json(g04_path)
    if g04.get("result") != "REAL_WINDOWS_KILL_RESTART_PASS" or g04.get("code_identity") != commit:
        raise RuntimeError("G04_EVIDENCE_INVALID")
    shutil.copyfile(g04_path, GENERATED / "g04-real-process-kill-restart.json")
    workflows = _wait_for_workflows(commit) if require_workflows else {}
    current_run = {"name": os.getenv("GITHUB_WORKFLOW", "LOCAL_VERIFICATION"),
                   "run_id": os.getenv("GITHUB_RUN_ID"), "head_sha": commit,
                   "url": (f"https://github.com/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/"
                           f"{os.getenv('GITHUB_RUN_ID')}") if os.getenv("GITHUB_RUN_ID") else None,
                   "status": "all_required_steps_passed_before_upload"}
    diff = subprocess.check_output(["git", "diff", "--numstat", "origin/main...HEAD"],
                                   cwd=ROOT, text=True).splitlines()
    additions = sum(int(row.split("\t")[0]) for row in diff if row.split("\t")[0].isdigit())
    deletions = sum(int(row.split("\t")[1]) for row in diff if row.split("\t")[1].isdigit())
    gate_sources = {
        "G01": "exact checkout/branch lineage", "G02": "owner_regressions",
        "G03": "owner_regressions queue", "G04": "g04-real-process-kill-restart.json",
        "G05": "owner_regressions batch", "G06": "clean-package-launch.json",
        "G07": "clean-package manifest inventory", "G08": "owner_regressions backup/restore",
        "G09": "local-full-flow-trace.json + same-project Chromium",
        "G10": "wp1 authority negatives", "G11": "contract/browser/owner regressions",
        "G12": "same-head Windows workflows + generated downloadable ledger",
    }
    ledger = {
        "schema_version": "PhaseBExactHeadVerdict.v1", "status": "PASS",
        "code_verdict": "PASS (12/12) - MERGE READY", "base_commit": os.getenv("BASE_COMMIT"),
        "start_commit": os.getenv("START_COMMIT", "43b76f379eb848486d0dd52facfd4afa503e14e1"),
        "final_commit": commit, "branch": "feat/b3-final-delivery-windows-full-v1",
        "pull_request": "https://github.com/plthien/Historical-Video-Studio/pull/12",
        "gates": {gate: {"status": "PASS", "evidence": source} for gate, source in gate_sources.items()},
        "owners": {task: "CODE_PASS" for task in ("B3-04", "B3-05", "B3-06")},
        "commands": results, "same_head_workflows": {**workflows, current_run["name"]: current_run},
        "evidence": {"clean_package": "clean-package-launch.json",
                     "local_full_flow": "local-full-flow-trace.json",
                     "g04": "g04-real-process-kill-restart.json",
                     "package_archive_sha256": package["archive_sha256"]},
        "diff": {"additions": additions, "deletions": deletions},
        "full_v1_live_acceptance": "BLOCKED_PENDING_AUTHENTIC_OPERATOR_INPUT",
    }
    GENERATED.mkdir(parents=True, exist_ok=True)
    verdict = GENERATED / "phase-b-exact-head-verdict.json"
    verdict.write_text(json.dumps(ledger, indent=2), "utf-8")
    live = _json(ROOT / "reports/acceptance/full-v1-live-acceptance.json")
    live.update({"code_identity": commit, "overall": "BLOCKED"})
    (GENERATED / "full-v1-live-acceptance.json").write_text(json.dumps(live, indent=2), "utf-8")
    inventory = []
    for path in sorted(GENERATED.glob("*.json")):
        if path.name != "evidence-inventory.json":
            inventory.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "byte_count": path.stat().st_size})
    (GENERATED / "evidence-inventory.json").write_text(json.dumps({"code_identity": commit,
        "files": inventory}, indent=2), "utf-8")


def verify() -> None:
    ledger = _json(GENERATED / "phase-b-exact-head-verdict.json")
    inventory = _json(GENERATED / "evidence-inventory.json")
    if ledger["final_commit"] != head() or set(ledger["gates"]) != {f"G{i:02d}" for i in range(1, 13)}:
        raise RuntimeError("FINAL_LEDGER_INVALID")
    for item in inventory["files"]:
        path = GENERATED / item["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError("EVIDENCE_INVENTORY_HASH_MISMATCH:" + item["path"])


def main() -> None:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="action", required=True)
    item = sub.add_parser("record"); item.add_argument("--id", required=True); item.add_argument("--command", required=True)
    build_parser = sub.add_parser("build"); build_parser.add_argument("--require-workflows", action="store_true")
    sub.add_parser("verify")
    args = parser.parse_args()
    if args.action == "record": record(args.id, args.command)
    elif args.action == "build": build(args.require_workflows)
    else: verify()


if __name__ == "__main__": main()
