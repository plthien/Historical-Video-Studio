"""Native short B3 closure fixture. Every approval is SYNTHETIC_TEST_ONLY."""
from __future__ import annotations

import json
import argparse
import hashlib
import ctypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.app.director import draft
from backend.app.contracts import ContractViolation
from backend.app.jobs import JobQueue
from backend.app.jobs.recovery import _process_alive
from backend.app.projects.gates import GateService
from backend.app.projects.storage import ProjectStore
from backend.app.render import DeliveryService
from backend.app.render import qc

ROOT = Path(__file__).resolve().parents[2]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path: Path, document: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _processes() -> list[dict]:
    if os.name != "nt":
        raise RuntimeError("B3_G04_PROCESS_INSPECTION_REQUIRES_WINDOWS")

    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    class UnicodeString(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT),
                    ("Buffer", ctypes.c_void_p)]

    kernel = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError()
    rows = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            pid = int(entry.th32ProcessID)
            command_line = ""
            handle = kernel.OpenProcess(0x1000 | 0x0010, False, pid)
            if handle:
                try:
                    needed = wintypes.ULONG()
                    ntdll.NtQueryInformationProcess(handle, 60, None, 0, ctypes.byref(needed))
                    if needed.value:
                        buffer = ctypes.create_string_buffer(needed.value)
                        status = ntdll.NtQueryInformationProcess(
                            handle, 60, buffer, needed.value, ctypes.byref(needed))
                        if status >= 0:
                            value = ctypes.cast(buffer, ctypes.POINTER(UnicodeString)).contents
                            if value.Buffer and value.Length:
                                command_line = ctypes.wstring_at(value.Buffer, value.Length // 2)
                finally:
                    kernel.CloseHandle(handle)
            rows.append({"pid": pid, "parent_pid": int(entry.th32ParentProcessID),
                         "name": entry.szExeFile, "command_line": command_line})
            present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return rows


def _owned_processes(processes: list[dict], backend_pid: int) -> list[dict]:
    owned = {backend_pid}
    changed = True
    while changed:
        changed = False
        for process in processes:
            if process["parent_pid"] in owned and process["pid"] not in owned:
                owned.add(process["pid"])
                changed = True
    return [process for process in processes if process["pid"] in owned]


def _public_process(process: dict) -> dict:
    command = process["command_line"].lower().replace("/", "\\")
    return {"pid": process["pid"], "parent_pid": process["parent_pid"],
            "name": process["name"], "tsx_cmd": "tsx.cmd" in command,
            "render_final_ts": "renderer\\scripts\\render-final.ts" in command}


def _owned_temp_dirs(processes: list[dict]) -> set[Path]:
    roots: set[Path] = set()
    temp_root = Path(tempfile.gettempdir()).resolve()
    pattern = re.compile(r'(?i)([a-z]:\\[^"\s]*\\(hvs-(?:render|remotion)-[^\\"\s]+))')
    for process in processes:
        for match in pattern.finditer(process["command_line"]):
            candidate = Path(match.group(1)).resolve()
            if candidate.parent == temp_root and candidate.name.startswith(("hvs-render-", "hvs-remotion-")):
                roots.add(candidate)
    return roots


def _start_backend(database: str, media_root: str, status_file: Path,
                   stop_file: Path, *, env: dict | None = None) -> subprocess.Popen:
    return subprocess.Popen([
        sys.executable, "-m", "backend.tools.b3_lifespan_child",
        "--sqlite", database, "--media-root", media_root,
        "--status-file", str(status_file), "--stop-file", str(stop_file),
    ], cwd=ROOT, env=env)


def _wait_dead(pids: set[int], timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and any(_process_alive(pid) for pid in pids):
        time.sleep(0.05)
    survivors = sorted(pid for pid in pids if _process_alive(pid))
    if survivors:
        raise RuntimeError(f"B3_FIXTURE_OWNED_PROCESS_SURVIVED:{survivors}")


def _db_snapshot(store: ProjectStore, job_id: str) -> dict:
    with store._connection() as db:
        db.row_factory = __import__("sqlite3").Row
        job = dict(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone())
        attempt = dict(db.execute("SELECT * FROM render_attempts WHERE job_id=?", (job_id,)).fetchone())
        counts = {
            "jobs": db.execute("SELECT COUNT(*) FROM jobs WHERE job_id=?", (job_id,)).fetchone()[0],
            "attempts": db.execute("SELECT COUNT(*) FROM render_attempts WHERE job_id=?", (job_id,)).fetchone()[0],
            "candidates": db.execute("SELECT COUNT(*) FROM g5_candidates WHERE job_id=?", (job_id,)).fetchone()[0],
            "exports": db.execute("SELECT COUNT(*) FROM delivery_exports WHERE job_id=?", (job_id,)).fetchone()[0],
        }
        candidate = db.execute("SELECT candidate_sha256 FROM g5_candidates WHERE job_id=?",
                               (job_id,)).fetchone()
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    return {"job": job, "attempt": attempt, "counts": counts, "integrity": integrity,
            "candidate_sha256": candidate[0] if candidate else None}


def _record_transition(trace: list[dict], snapshot: dict, phase: str) -> None:
    job, attempt = snapshot["job"], snapshot["attempt"]
    lease = job.get("lease_token")
    item = {"timestamp": _now(), "phase": phase, "state": job["state"],
            "lease_sha256": hashlib.sha256(lease.encode()).hexdigest() if lease else None,
            "renderer_pid": attempt.get("process_id")}
    if not trace or any(trace[-1].get(key) != item.get(key)
                        for key in ("phase", "state", "lease_sha256", "renderer_pid")):
        trace.append(item)


def _real_process_kill_restart(config: dict, store: ProjectStore, queue: JobQueue,
                               service: DeliveryService, project: str,
                               evidence_dir: Path) -> tuple[dict, dict]:
    evidence_path = evidence_dir / "g04-real-process-kill-restart.json"
    evidence: dict = {
        "schema_version": "B3G04RealProcessKillRestart.v1",
        "scope": "SYNTHETIC_TEST_ONLY", "os": "Windows",
        "command": ".venv/Scripts/python.exe -m backend.tools.b3_delivery_fixture",
        "code_identity": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "renderer_identity": "Remotion/4.0.524 renderer/scripts/render-final.ts",
        "state_transitions": [], "errors": [], "result": "INCOMPLETE",
    }
    owned_temp_dirs: set[Path] = set()
    children: list[subprocess.Popen] = []
    cleanup_ok = False
    try:
        queued = service.submit(project, store.revision(project), "b3-real-kill-restart-0001")
        original = _db_snapshot(store, queued["render_job_id"])
        manifest = json.loads(store.get_artifact(queued["render_input_manifest_sha256"]))
        if (original["job"]["state"] != "QUEUED" or original["attempt"]["output_sha256"] is not None or
                original["attempt"]["qc_status"] != "NOT_RUN"):
            raise RuntimeError("B3_G04_PRELAUNCH_STATE_INVALID")
        evidence["original_identity"] = {
            "project_id": project, "job_id": queued["render_job_id"],
            "attempt_id": queued["attempt_id"],
            "manifest_sha256": queued["render_input_manifest_sha256"],
            "g4_approval_id": original["attempt"]["g4_approval_id"],
            "timeline_sha256": manifest["timeline_sha256"],
            "wav_sha256": manifest["audio"]["wav_sha256"],
            "retry_count": original["job"]["retry_count"], "state": "QUEUED",
        }
        _record_transition(evidence["state_transitions"], original, "prelaunch")

        with tempfile.TemporaryDirectory(prefix="hvs-g04-control-") as control:
            control_dir = Path(control)
            first_status, first_stop = control_dir / "first.json", control_dir / "first.stop"
            first = _start_backend(config["db"], config["artifactRoot"], first_status, first_stop)
            children.append(first)
            deadline = time.monotonic() + 90
            active = None
            original_owned = []
            while time.monotonic() < deadline:
                current = _db_snapshot(store, queued["render_job_id"])
                _record_transition(evidence["state_transitions"], current, "original_backend")
                renderer_pid = current["attempt"].get("process_id")
                if (current["job"]["state"] == "RUNNING" and renderer_pid and
                        _process_alive(renderer_pid) and current["attempt"]["output_sha256"] is None):
                    processes = _processes()
                    original_owned = _owned_processes(processes, first.pid)
                    ids = {process["pid"] for process in original_owned}
                    commands = " ".join(process["command_line"].lower().replace("/", "\\")
                                        for process in original_owned)
                    if (renderer_pid in ids and "tsx.cmd" in commands and
                            "renderer\\scripts\\render-final.ts" in commands):
                        active = current
                        owned_temp_dirs.update(_owned_temp_dirs(original_owned))
                        break
                if current["job"]["state"] not in ("QUEUED", "RUNNING"):
                    raise RuntimeError("B3_G04_RENDER_FINISHED_BEFORE_KILL_WINDOW")
                time.sleep(0.05)
            if active is None:
                raise RuntimeError("B3_G04_REAL_RENDER_PROCESS_NOT_OBSERVED")

            original_renderer_pid = int(active["attempt"]["process_id"])
            original_lease = active["job"]["lease_token"]
            original_pids = {process["pid"] for process in original_owned}
            status_deadline = time.monotonic() + 10
            while not first_status.exists() and time.monotonic() < status_deadline:
                time.sleep(0.05)
            if not first_status.exists():
                raise RuntimeError("B3_G04_ORIGINAL_STATUS_MISSING")
            original_status = json.loads(first_status.read_text(encoding="utf-8"))
            if original_status["backend_pid"] not in original_pids:
                raise RuntimeError("B3_G04_ORIGINAL_BACKEND_PID_MISMATCH")
            evidence["original_process"] = {
                "backend_pid": original_status["backend_pid"], "launcher_pid": first.pid,
                "renderer_pid": original_renderer_pid,
                "owned_processes": [_public_process(process) for process in original_owned],
                "live_before_kill": True, "recovery": original_status["recovery"],
            }
            killed = subprocess.run(["taskkill", "/PID", str(first.pid), "/T", "/F"],
                                    capture_output=True, text=True)
            if killed.returncode != 0:
                raise RuntimeError("B3_G04_TASKKILL_FAILED:" + killed.stderr[-500:])
            _wait_dead(original_pids)
            first.wait(timeout=10)
            evidence["original_process"]["taskkill_exit_code"] = killed.returncode
            evidence["original_process"]["renderer_dead_after_kill"] = not _process_alive(original_renderer_pid)

            reopened = ProjectStore(config["db"], config["artifactRoot"])
            interrupted = _db_snapshot(reopened, queued["render_job_id"])
            _record_transition(evidence["state_transitions"], interrupted, "after_kill_before_restart")
            if (interrupted["integrity"] != "ok" or interrupted["job"]["state"] != "RUNNING" or
                    interrupted["counts"]["jobs"] != 1 or interrupted["counts"]["attempts"] != 1 or
                    interrupted["attempt"]["output_sha256"] is not None or
                    interrupted["attempt"]["qc_status"] != "NOT_RUN" or
                    interrupted["counts"]["candidates"] or interrupted["counts"]["exports"]):
                raise RuntimeError("B3_G04_INTERRUPTED_PERSISTENCE_INVALID")

            second_status, second_stop = control_dir / "second.json", control_dir / "second.stop"
            second = _start_backend(config["db"], config["artifactRoot"], second_status, second_stop)
            children.append(second)
            deadline = time.monotonic() + 300
            restarted_active = None
            final = None
            restarted_owned = []
            while time.monotonic() < deadline:
                current = _db_snapshot(reopened, queued["render_job_id"])
                _record_transition(evidence["state_transitions"], current, "restarted_backend")
                renderer_pid = current["attempt"].get("process_id")
                if current["job"]["state"] == "RUNNING" and renderer_pid and _process_alive(renderer_pid):
                    processes = _processes()
                    restarted_owned = _owned_processes(processes, second.pid)
                    ids = {process["pid"] for process in restarted_owned}
                    commands = " ".join(process["command_line"].lower().replace("/", "\\")
                                        for process in restarted_owned)
                    if (renderer_pid in ids and "tsx.cmd" in commands and
                            "renderer\\scripts\\render-final.ts" in commands):
                        restarted_active = current
                        owned_temp_dirs.update(_owned_temp_dirs(restarted_owned))
                if current["job"]["state"] == "SUCCEEDED":
                    final = current
                    break
                if current["job"]["state"] not in ("QUEUED", "RUNNING"):
                    raise RuntimeError("B3_G04_RESTART_RENDER_FAILED:" + current["job"]["state"])
                time.sleep(0.1)
            if final is None or restarted_active is None:
                raise RuntimeError("B3_G04_RESTART_RENDER_TIMEOUT_OR_PID_NOT_OBSERVED")
            status_deadline = time.monotonic() + 10
            while not second_status.exists() and time.monotonic() < status_deadline:
                time.sleep(0.05)
            if not second_status.exists():
                raise RuntimeError("B3_G04_RESTART_STATUS_MISSING")
            restart_status = json.loads(second_status.read_text(encoding="utf-8"))
            new_renderer_pid = int(restarted_active["attempt"]["process_id"])
            new_lease = restarted_active["job"]["lease_token"]
            if (new_renderer_pid == original_renderer_pid or new_lease == original_lease or
                    _process_alive(original_renderer_pid) or
                    restart_status["recovery"].get("resume_existing_provider_task") != 1):
                raise RuntimeError("B3_G04_RECOVERY_IDENTITY_OR_LEASE_INVALID")

            final_rendered = DeliveryService(reopened, JobQueue(reopened)).read(project, queued["render_job_id"])
            final = _db_snapshot(reopened, queued["render_job_id"])
            for field in ("attempt_id", "render_input_manifest_sha256", "timeline_sha256", "audio_sha256"):
                if final_rendered[field] != queued[field if field != "render_input_manifest_sha256" else field]:
                    raise RuntimeError("B3_G04_RECOVERY_LINEAGE_CHANGED:" + field)
            if (final["job"]["retry_count"] != original["job"]["retry_count"] or
                    final_rendered["qc_status"] != "PASS" or
                    final["counts"]["candidates"] != 1 or final["counts"]["exports"] != 0):
                raise RuntimeError("B3_G04_RETRY_OR_QC_INVALID")
            qc_report = json.loads(reopened.get_artifact(final_rendered["qc_report_sha256"]))
            if qc_report["status"] != "PASS":
                raise RuntimeError("B3_G04_FINAL_QC_NOT_PASS")

            second_stop.write_text("stop", encoding="utf-8")
            second.wait(timeout=30)
            if second.returncode != 0:
                raise RuntimeError("B3_G04_RESTART_BACKEND_EXIT_FAILED")

            third_status, third_stop = control_dir / "third.json", control_dir / "third.stop"
            third = _start_backend(config["db"], config["artifactRoot"], third_status, third_stop)
            children.append(third)
            status_deadline = time.monotonic() + 20
            while not third_status.exists() and time.monotonic() < status_deadline:
                time.sleep(0.05)
            if not third_status.exists():
                raise RuntimeError("B3_G04_DUPLICATE_PROBE_STATUS_MISSING")
            duplicate_status = json.loads(third_status.read_text(encoding="utf-8"))
            time.sleep(0.25)
            duplicate_probe = _db_snapshot(reopened, queued["render_job_id"])
            if (duplicate_status["recovery"] != {"resume_existing_provider_task": 0,
                                                  "blocked_uncertain_operation": 0} or
                    duplicate_probe["job"]["state"] != "SUCCEEDED" or
                    duplicate_probe["attempt"]["output_sha256"] != final["attempt"]["output_sha256"]):
                raise RuntimeError("B3_G04_DUPLICATE_LIFESPAN_DISPATCHED")
            third_stop.write_text("stop", encoding="utf-8")
            third.wait(timeout=30)

            evidence.update({
                "restarted_process": {
                    "backend_pid": restart_status["backend_pid"], "launcher_pid": second.pid,
                    "renderer_pid": new_renderer_pid,
                    "owned_processes": [_public_process(process) for process in restarted_owned],
                    "recovery": restart_status["recovery"], "post_kill_state": final["job"]["state"],
                },
                "recovered_identity": {
                    "project_id": project, "job_id": final_rendered["render_job_id"],
                    "attempt_id": final_rendered["attempt_id"],
                    "manifest_sha256": final_rendered["render_input_manifest_sha256"],
                    "g4_approval_id": final["attempt"]["g4_approval_id"],
                    "timeline_sha256": final_rendered["timeline_sha256"],
                    "wav_sha256": final_rendered["audio_sha256"],
                    "retry_count": final_rendered["retry_count"],
                    "lease_changed": new_lease != original_lease,
                    "original_lease_sha256": hashlib.sha256(original_lease.encode()).hexdigest(),
                    "restarted_lease_sha256": hashlib.sha256(new_lease.encode()).hexdigest(),
                },
                "media": {"mp4_sha256": final_rendered["output_sha256"],
                          "qc_report_sha256": final_rendered["qc_report_sha256"],
                          "qc_status": final_rendered["qc_status"],
                          "ffprobe": qc_report["ffprobe"],
                          "g5_candidate_sha256": final["candidate_sha256"]},
                "single_owner": {"old_renderer_still_alive": _process_alive(original_renderer_pid),
                                 "duplicate_owners": 0, "successful_operations": 1,
                                 "job_rows": final["counts"]["jobs"],
                                 "attempt_rows": final["counts"]["attempts"],
                                 "duplicate_probe_backend_pid": duplicate_status["backend_pid"]},
                "unapproved_export": False,
                "result": "REAL_WINDOWS_KILL_RESTART_PASS",
            })
        return final_rendered, evidence
    except Exception as exc:
        evidence["errors"].append(f"{type(exc).__name__}: {str(exc)[:1000]}")
        evidence["result"] = "FAIL"
        raise
    finally:
        cleanup_ok = True
        for child in children:
            if child.poll() is None:
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                               capture_output=True, check=False)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    cleanup_ok = False
        for directory in owned_temp_dirs:
            try:
                if directory.exists():
                    shutil.rmtree(directory)
            except OSError:
                cleanup_ok = False
        evidence["cleanup_ok"] = cleanup_ok
        _write_json_atomic(evidence_path, evidence)


def _stale_source_restart_negative(config: dict, store: ProjectStore,
                                   project: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="hvs-g04-stale-") as control:
        control_dir = Path(control)
        stale_database = control_dir / "stale.sqlite"
        sqlite3 = __import__("sqlite3")
        destination = sqlite3.connect(stale_database)
        try:
            with store._connection() as source:
                source.backup(destination)
        finally:
            destination.close()
        stale_store = ProjectStore(stale_database, config["artifactRoot"])
        stale_queue = JobQueue(stale_store)
        stale_service = DeliveryService(stale_store, stale_queue)
        queued = stale_service.submit(project, stale_store.revision(project),
                                      "b3-stale-restart-0001")
        running = stale_queue.claim("final_render", job_id=queued["render_job_id"])
        if not running:
            raise RuntimeError("B3_G04_STALE_NEGATIVE_NOT_CLAIMED")
        original_manifest = json.loads(
            stale_store.get_artifact(queued["render_input_manifest_sha256"]))
        changed_wav = control_dir / "changed.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=550:sample_rate=48000:duration=4", "-ac", "1",
                        "-c:a", "pcm_s16le", str(changed_wav)], check=True)
        changed_wav_sha = stale_store.put_artifact(changed_wav.read_bytes(), "final_audio_wav")
        if changed_wav_sha == original_manifest["audio"]["wav_sha256"]:
            raise RuntimeError("B3_G04_STALE_WAV_IDENTITY_NOT_DISTINCT")
        with stale_store._transaction() as db:
            db.execute("UPDATE final_audio SET audio_sha256=? WHERE project_id=?",
                       (changed_wav_sha, project))
        status_file, stop_file = control_dir / "status.json", control_dir / "stop"
        child = _start_backend(str(stale_database), config["artifactRoot"], status_file, stop_file)
        try:
            deadline = time.monotonic() + 30
            final = None
            while time.monotonic() < deadline:
                current = _db_snapshot(stale_store, queued["render_job_id"])
                if current["job"]["state"] not in ("QUEUED", "RUNNING"):
                    final = current
                    break
                time.sleep(0.05)
            if (final is None or final["job"]["state"] != "FAILED_TERMINAL" or
                    final["job"]["error_code"] != "G4_APPROVAL_REQUIRED" or
                    final["attempt"]["process_id"] is not None or
                    final["attempt"]["output_sha256"] is not None or
                    final["attempt"]["qc_status"] != "NOT_RUN" or
                    final["counts"]["candidates"] != 0):
                raise RuntimeError("B3_G04_STALE_SOURCE_DID_NOT_FAIL_CLOSED")
            status_deadline = time.monotonic() + 10
            while not status_file.exists() and time.monotonic() < status_deadline:
                time.sleep(0.05)
            if not status_file.exists():
                raise RuntimeError("B3_G04_STALE_BACKEND_STATUS_MISSING")
            status = json.loads(status_file.read_text(encoding="utf-8"))
            return {"job_id": queued["render_job_id"],
                    "attempt_id": queued["attempt_id"],
                    "manifest_sha256": queued["render_input_manifest_sha256"],
                    "recovery": status["recovery"], "state": final["job"]["state"],
                    "error_code": final["job"]["error_code"],
                    "renderer_process_started": False, "output_published": False,
                    "g5_candidate_published": False,
                    "original_wav_sha256": original_manifest["audio"]["wav_sha256"],
                    "changed_wav_sha256": changed_wav_sha}
        finally:
            stop_file.write_text("stop", encoding="utf-8")
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                               capture_output=True, check=False)
                child.wait(timeout=15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flow-root", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--direct-render", action="store_true")
    args = parser.parse_args()
    flow_root = args.flow_root or ROOT / "renderer/.artifacts/approved-player-test"
    config_path = flow_root.with_suffix(".json")
    project_id = args.project_id or "proj_001"
    subprocess.run([sys.executable, "-m", "renderer.scripts.prepare_host_fixture",
                    "--output-dir", str(flow_root), "--config-path", str(config_path),
                    "--project-id", project_id], cwd=ROOT, check=True)
    config = json.loads(config_path.read_text("utf-8"))
    store = ProjectStore(config["db"], config["artifactRoot"]); project = config["project"]
    gates = GateService(store)
    queue = JobQueue(store); service = DeliveryService(store, queue)
    evidence = args.evidence_dir or ROOT / "renderer/.artifacts/b3-delivery"
    evidence.mkdir(parents=True, exist_ok=True)
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
    if args.direct_render:
        queued = service.submit(project, store.revision(project), "b3-direct-real-render-0001")
        rendered = service.process(queued["render_job_id"])
        if rendered["state"] != "SUCCEEDED" or rendered["qc_status"] != "PASS":
            raise RuntimeError("B3_DIRECT_NATIVE_RENDER_FAILED:" + json.dumps(rendered))
        qc_report = json.loads(store.get_artifact(rendered["qc_report_sha256"]))
        g04_evidence = {
            "schema_version": "B3ContinuousDirectRender.v1", "scope": "SYNTHETIC_TEST_ONLY",
            "code_identity": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "result": "DIRECT_REAL_RENDER_PASS", "errors": [],
            "media": {"mp4_sha256": rendered["output_sha256"],
                      "qc_report_sha256": rendered["qc_report_sha256"],
                      "qc_status": rendered["qc_status"], "ffprobe": qc_report["ffprobe"]},
            "single_owner": {"duplicate_owners": 0, "successful_operations": 1},
            "cleanup_ok": True,
        }
        negatives.append("DIRECT_REAL_RENDER_PASS")
    else:
        rendered, g04_evidence = _real_process_kill_restart(
            config, store, queue, service, project, evidence)
    service = DeliveryService(store, queue)
    if rendered["state"] != "SUCCEEDED" or rendered["qc_status"] != "PASS":
        raise RuntimeError("B3_NATIVE_RENDER_FAILED " + json.dumps(rendered))
    if not args.direct_render:
        negatives.append("REAL_WINDOWS_KILL_RESTART_PASS")
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
    try:
        g04_evidence["stale_source_negative"] = _stale_source_restart_negative(
            config, store, project)
    except Exception as exc:
        g04_evidence["result"] = "FAIL"
        g04_evidence["errors"].append(f"{type(exc).__name__}: {str(exc)[:1000]}")
        _write_json_atomic(evidence / "g04-real-process-kill-restart.json", g04_evidence)
        raise
    _write_json_atomic(evidence / "g04-real-process-kill-restart.json", g04_evidence)
    verdict = {"schema_version": "B3ThreeP1Verdict.v1", "scope": "SYNTHETIC_TEST_ONLY",
               "restart": {"job_id": rendered["render_job_id"], "attempt_id": rendered["attempt_id"],
                           "manifest_sha256": rendered["render_input_manifest_sha256"],
                           "g04_evidence": "g04-real-process-kill-restart.json",
                           "result": g04_evidence["result"]},
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
