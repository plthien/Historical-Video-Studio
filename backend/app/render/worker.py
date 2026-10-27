"""B3 durable local Remotion attempts and exact G5 evidence binding."""
from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from backend.app.contracts import ContractViolation, validate_document
from backend.app.director.fingerprint import canonical, digest
from backend.app.jobs.queue import JobQueue
from backend.app.projects.gates import GateService
from . import attribution, manifest, qc

ROOT = Path(__file__).parents[3]


def _fail(code, entity, remedy, gate="G5"):
    raise ContractViolation(code, entity, remedy, blocking_gate=gate)


class DeliveryService:
    def __init__(self, store, queue: JobQueue):
        self.store, self.queue = store, queue
        GateService(store)
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS render_attempts(
                    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id), attempt_id TEXT UNIQUE NOT NULL,
                    manifest_sha256 TEXT NOT NULL, g4_approval_id TEXT NOT NULL,
                    progress_frames INTEGER NOT NULL DEFAULT 0, total_frames INTEGER NOT NULL,
                    output_sha256 TEXT, qc_report_sha256 TEXT, qc_status TEXT NOT NULL DEFAULT 'NOT_RUN',
                    attribution_sha256 TEXT, log_json TEXT NOT NULL DEFAULT '[]',
                    process_id INTEGER, created_at TEXT NOT NULL, finished_at TEXT);
                CREATE TABLE IF NOT EXISTS g5_candidates(
                    candidate_sha256 TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_id TEXT UNIQUE NOT NULL,
                    dependency_fingerprint TEXT NOT NULL, candidate_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS g5_review_sessions(
                    session_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
                    candidate_sha256 TEXT NOT NULL, nonce TEXT NOT NULL, started_monotonic REAL NOT NULL,
                    last_monotonic REAL NOT NULL, last_position REAL NOT NULL DEFAULT 0,
                    viewed_seconds REAL NOT NULL DEFAULT 0, listened_seconds REAL NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS delivery_exports(
                    export_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
                    g5_approval_id TEXT NOT NULL, mp4_artifact_id TEXT NOT NULL,
                    credits_artifact_id TEXT NOT NULL, manifest_artifact_id TEXT NOT NULL,
                    export_json TEXT NOT NULL, UNIQUE(project_id,job_id,g5_approval_id));
            """)
            fields = {row[1] for row in db.execute("PRAGMA table_info(render_attempts)")}
            if "process_id" not in fields:
                db.execute("ALTER TABLE render_attempts ADD COLUMN process_id INTEGER")

    def submit(self, project: str, expected_revision: int, idempotency_key: str) -> dict:
        if self.store.revision(project) != expected_revision:
            _fail("REVISION_CONFLICT", project, "Reload before starting a render.", "G4")
        document, manifest_sha = manifest.build(self.store, project)
        job = self.queue.submit(project, "final_render", idempotency_key,
                                {"render_input_manifest_sha256": manifest_sha}, expected_revision)
        with self.store._transaction() as db:
            row = db.execute("SELECT manifest_sha256 FROM render_attempts WHERE job_id=?",
                             (job["job_id"],)).fetchone()
            if row and row[0] != manifest_sha:
                _fail("IDEMPOTENCY_CONFLICT", job["job_id"], "Operation key belongs to different inputs.", "G4")
            if not row:
                db.execute("INSERT INTO render_attempts(job_id,attempt_id,manifest_sha256,g4_approval_id,"
                           "total_frames,created_at) VALUES(?,?,?,?,?,?)",
                           (job["job_id"], "renderattempt_" + uuid4().hex, manifest_sha,
                            document["g4_approval_id"], document["video"]["total_frames"],
                            datetime.now(timezone.utc).isoformat()))
        return self.read(project, job["job_id"])

    def _attempt(self, db, project, job_id):
        db.row_factory = __import__("sqlite3").Row
        row = db.execute("SELECT r.*,j.project_id,j.state,j.retry_count,j.error_code,j.cancel_requested "
                         "FROM render_attempts r JOIN jobs j ON j.job_id=r.job_id "
                         "WHERE r.job_id=? AND j.project_id=?", (job_id, project)).fetchone()
        if not row: _fail("RENDER_JOB_NOT_FOUND", job_id, "Select this project's render job.", "G4")
        return dict(row)

    def read(self, project: str, job_id: str) -> dict:
        with self.store._connection() as db:
            row = self._attempt(db, project, job_id)
            g5 = db.execute("SELECT h.approval_id FROM gate_heads h JOIN g5_candidates c "
                            "ON c.candidate_sha256=h.candidate_sha256 WHERE h.project_id=? "
                            "AND h.gate_id='G5' AND c.job_id=?", (project, job_id)).fetchone()
            exported = db.execute("SELECT export_json FROM delivery_exports WHERE project_id=? AND job_id=? "
                                  "ORDER BY rowid DESC LIMIT 1", (project, job_id)).fetchone()
        if row["state"] == "SUCCEEDED" and row["qc_status"] == "PASS" and not g5:
            # Reconcile a crash/race between durable job completion and the
            # separate candidate publication. Stale authority still fails closed.
            try: self._publish_g5(project, job_id)
            except ContractViolation: pass
            with self.store._connection() as db:
                g5 = db.execute("SELECT h.approval_id FROM gate_heads h JOIN g5_candidates c "
                                "ON c.candidate_sha256=h.candidate_sha256 WHERE h.project_id=? "
                                "AND h.gate_id='G5' AND c.job_id=?", (project, job_id)).fetchone()
        core = {"schema_version": "RenderJob.v1", "render_job_id": job_id, "project_id": project,
                "timeline_sha256": json.loads(self.store.get_artifact(row["manifest_sha256"]))["timeline_sha256"],
                "audio_sha256": json.loads(self.store.get_artifact(row["manifest_sha256"]))["audio"]["wav_sha256"],
                "renderer_version": "Remotion/4.0.524", "state": row["state"],
                "output_sha256": row["output_sha256"], "qc_status": row["qc_status"],
                "attribution_manifest_sha256": row["attribution_sha256"],
                "retry_count": row["retry_count"], "error_code": row["error_code"]}
        validate_document("RenderJob.v1", core)
        return {**core,
                "attempt_id": row["attempt_id"], "render_input_manifest_sha256": row["manifest_sha256"],
                "qc_report_sha256": row["qc_report_sha256"], "progress": {
                    "frames_processed": row["progress_frames"], "total_frames": row["total_frames"]},
                "logs": json.loads(row["log_json"]), "g5_approval_id": g5[0] if g5 else None,
                "export": json.loads(exported[0]) if exported else None}

    def process(self, job_id: str) -> dict:
        job = self.queue.claim("final_render", job_id=job_id)
        if not job: return self.queue.get(job_id)
        token, project = job["lease_token"], job["project_id"]
        try:
            with self.store._connection() as db: attempt = self._attempt(db, project, job_id)
            doc = manifest.verify(self.store, project, attempt["manifest_sha256"])
            exe = ROOT / "renderer" / "node_modules" / ".bin" / "tsx.cmd"
            if os.name != "nt" or not exe.is_file():
                _fail("RENDER_TOOLCHAIN_UNAVAILABLE", job_id, "Install pinned Node/Remotion on native Windows.", "G4")
            audio_path = self.store.artifacts.path(doc["audio"]["wav_sha256"])
            with tempfile.TemporaryDirectory(prefix="hvs-render-") as temp:
                output = Path(temp) / "final.mp4"
                command = [str(exe), str(ROOT / "renderer" / "scripts" / "render-final.ts"),
                           str(self.store.database), str(self.store.artifacts.root), project,
                           str(audio_path), str(output)]
                proc = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
                with self.store._transaction() as db:
                    db.execute("UPDATE render_attempts SET process_id=? WHERE job_id=?", (proc.pid, job_id))
                logs = []
                def pump():
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        line = line.rstrip()
                        logs.append(line[-1000:])
                        try:
                            event = json.loads(line)
                            frames = max(0, min(doc["video"]["total_frames"],
                                                int(event.get("framesProcessed", 0))))
                        except (ValueError, TypeError):
                            continue
                        with self.store._transaction() as db:
                            db.execute("UPDATE render_attempts SET progress_frames=? WHERE job_id=?",
                                       (frames, job_id))
                reader = threading.Thread(target=pump, daemon=True); reader.start()
                while proc.poll() is None:
                    latest = self.queue.get(job_id)
                    if latest["cancel_requested"]:
                        if os.name == "nt":
                            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                           capture_output=True, check=False)
                        else:
                            proc.terminate()
                        try: proc.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            proc.kill(); proc.wait(timeout=15)
                        reader.join(timeout=2)
                        with self.store._transaction() as db:
                            db.execute("UPDATE render_attempts SET process_id=NULL WHERE job_id=?", (job_id,))
                        self.queue.acknowledge_cancel(job_id, token, provider_confirmed=True)
                        return self.read(project, job_id)
                    time.sleep(.2)
                reader.join(timeout=5); logs = logs[-40:]
                with self.store._transaction() as db:
                    db.execute("UPDATE render_attempts SET process_id=NULL WHERE job_id=?", (job_id,))
                if proc.returncode or not output.is_file():
                    raise ContractViolation("RENDER_PROCESS_FAILED", job_id,
                                            "Pinned Remotion/FFmpeg render failed.", blocking_gate="G4")
                # Reconstruct authority after the process, before publishing bytes.
                manifest.verify(self.store, project, attempt["manifest_sha256"])
                report, qc_sha = qc.inspect(self.store, project, output, doc)
                output_sha = self.store.put_artifact(output.read_bytes(), "final_mp4")
                if output_sha != report["mp4_sha256"]:
                    _fail("QC_OUTPUT_SHA_MISMATCH", job_id, "QC must inspect the exact published MP4.")
                if report["status"] != "PASS":
                    with self.store._transaction() as db:
                        self.queue._owned(db, job_id, token)
                        db.execute("UPDATE render_attempts SET output_sha256=?,qc_report_sha256=?,"
                                   "qc_status='FAIL',log_json=? WHERE job_id=?",
                                   (output_sha, qc_sha, json.dumps(logs), job_id))
                    raise ContractViolation("QC_FAILED", job_id, "Inspect immutable QC problems and rerender.", blocking_gate="G5")
                credits, credits_sha = attribution.build(self.store, project, doc)
                with self.store._transaction() as db:
                    self.queue._owned(db, job_id, token)
                    manifest.verify(self.store, project, attempt["manifest_sha256"])
                    db.execute("UPDATE render_attempts SET progress_frames=total_frames,output_sha256=?,"
                               "qc_report_sha256=?,qc_status='PASS',attribution_sha256=?,log_json=?,finished_at=? "
                               "WHERE job_id=?", (output_sha, qc_sha, credits_sha, json.dumps(logs),
                                                  datetime.now(timezone.utc).isoformat(), job_id))
                self.queue.finish(job_id, token, output_sha)
                self._publish_g5(project, job_id)
                return self.read(project, job_id)
        except ContractViolation as exc:
            latest = self.queue.get(job_id)
            if latest["state"] == "RUNNING":
                self.queue.fail(job_id, token, exc.code,
                                retryable=exc.code in {"RENDER_PROCESS_FAILED", "QC_FAILED",
                                                       "RENDER_TOOLCHAIN_UNAVAILABLE"})
            return self.read(project, job_id)
        except Exception as exc:
            latest = self.queue.get(job_id)
            if latest["state"] == "RUNNING":
                with self.store._transaction() as db:
                    db.execute("UPDATE render_attempts SET log_json=? WHERE job_id=?",
                               (json.dumps([f"{type(exc).__name__}: {str(exc)[:800]}"]), job_id))
                self.queue.fail(job_id, token, "RENDER_EXECUTION_FAILED", retryable=True)
            return self.read(project, job_id)

    def retry(self, project: str, job_id: str, body: dict) -> dict:
        row = self.read(project, job_id)
        doc = manifest.verify(self.store, project, row["render_input_manifest_sha256"])
        if (body.get("expected_revision") != self.store.revision(project) or
                body.get("approved_timeline_sha256") != doc["timeline_sha256"] or
                body.get("codec") != "h264" or body.get("container") != "mp4"):
            _fail("RENDER_RETRY_STALE", job_id, "Retry exact current approved H264/MP4 inputs.", "G4")
        self.queue.retry(job_id)
        with self.store._transaction() as db:
            db.execute("UPDATE jobs SET error_code=NULL WHERE job_id=?", (job_id,))
            db.execute("UPDATE render_attempts SET attempt_id=?,progress_frames=0,output_sha256=NULL,"
                       "qc_report_sha256=NULL,qc_status='NOT_RUN',attribution_sha256=NULL,log_json='[]',finished_at=NULL "
                       "WHERE job_id=?", ("renderattempt_" + uuid4().hex, job_id))
        return self.read(project, job_id)

    def _publish_g5(self, project, job_id):
        with self.store._connection() as db: row = self._attempt(db, project, job_id)
        if row["state"] not in ("RUNNING", "SUCCEEDED") or row["qc_status"] != "PASS": return
        render_manifest = manifest.verify(self.store, project, row["manifest_sha256"])
        dependencies = {"job_id": job_id, "attempt_id": row["attempt_id"],
            "mp4_sha256": row["output_sha256"], "qc_report_sha256": row["qc_report_sha256"],
            "attribution_sha256": row["attribution_sha256"],
            "render_input_manifest_sha256": row["manifest_sha256"],
            "g4_approval_id": render_manifest["g4_approval_id"],
            "g4_manifest_sha256": render_manifest["g4_manifest_sha256"],
            "gate_heads": render_manifest["gate_heads"]}
        candidate = {"schema_version": "G5ReviewCandidate.v1", "project_id": project,
                     "dependencies": dependencies, "dependency_fingerprint": digest(dependencies)}
        candidate_sha = self.store.put_artifact(canonical(candidate), "g5_review_candidate")
        with self.store._transaction() as db:
            db.execute("INSERT OR IGNORE INTO g5_candidates VALUES(?,?,?,?,?)",
                       (candidate_sha, project, job_id, candidate["dependency_fingerprint"],
                        canonical(candidate).decode("utf-8")))
        GateService(self.store).publish_candidate(project, "G5", candidate_sha,
                                                  candidate["dependency_fingerprint"],
                                                  self.store.revision(project))

    def start_review(self, project, job_id):
        with self.store._connection() as db:
            row = self._attempt(db, project, job_id)
            candidate = db.execute("SELECT candidate_sha256 FROM g5_candidates WHERE project_id=? AND job_id=?",
                                   (project, job_id)).fetchone()
        if row["state"] != "SUCCEEDED" or row["qc_status"] != "PASS" or not candidate:
            _fail("G5_CANDIDATE_NOT_READY", job_id, "Complete render, QC and credits first.")
        now = time.monotonic(); session = "review_" + uuid4().hex; nonce = uuid4().hex
        with self.store._transaction() as db:
            db.execute("INSERT INTO g5_review_sessions VALUES(?,?,?,?,?,?,?,?,?,?,0)",
                       (session, project, job_id, candidate[0], nonce, now, now, 0, 0, 0))
        return {"review_session_id": session, "nonce": nonce, "candidate_sha256": candidate[0]}

    def review_heartbeat(self, project, session_id, nonce, expected_revision, position_seconds,
                         playing_video, playing_with_audio):
        if expected_revision != self.store.revision(project):
            _fail("REVISION_CONFLICT", project, "Reload the current review before continuing playback.")
        if playing_with_audio and not playing_video:
            _fail("G5_REVIEW_PLAYER_STATE_INVALID", session_id,
                  "Audio playback cannot be credited while video is not naturally playing.")
        if not isinstance(position_seconds, (int, float)) or not math.isfinite(position_seconds) or position_seconds < 0:
            _fail("G5_REVIEW_PLAYER_STATE_INVALID", session_id,
                  "Report a finite non-negative media position.")
        now = time.monotonic()
        with self.store._transaction() as db:
            row = db.execute("SELECT s.nonce,s.last_monotonic,s.last_position,s.viewed_seconds,"
                             "s.listened_seconds,s.completed,s.job_id,s.candidate_sha256 "
                             "FROM g5_review_sessions s JOIN jobs j ON j.job_id=s.job_id "
                             "JOIN g5_candidates c ON c.job_id=s.job_id "
                             "AND c.candidate_sha256=s.candidate_sha256 "
                             "WHERE s.session_id=? AND s.project_id=? AND j.state='SUCCEEDED'",
                             (session_id, project)).fetchone()
            if not row or row[0] != nonce or row[5]: _fail("G5_REVIEW_SESSION_INVALID", session_id, "Start a current server review session.")
            elapsed = max(0, min(now - row[1], 10)); advanced = max(0, position_seconds - row[2])
            if playing_video and advanced > elapsed * 2 + .5:
                _fail("G5_REVIEW_PLAYER_STATE_INVALID", session_id,
                      "Seeking or implausible position jumps cannot earn review credit.")
            viewed = min(elapsed, advanced + .25) if playing_video else 0
            listened = viewed if playing_with_audio else 0
            db.execute("UPDATE g5_review_sessions SET last_monotonic=?,last_position=?,"
                       "viewed_seconds=viewed_seconds+?,listened_seconds=listened_seconds+? WHERE session_id=?",
                       (now, position_seconds, viewed, listened, session_id))
            return {"viewed_seconds": row[3] + viewed, "listened_seconds": row[4] + listened}

    def complete_review(self, project, session_id, nonce):
        with self.store._transaction() as db:
            row = db.execute("SELECT s.job_id,s.candidate_sha256,s.nonce,s.viewed_seconds,s.listened_seconds,"
                             "r.manifest_sha256 FROM g5_review_sessions s "
                             "JOIN render_attempts r ON r.job_id=s.job_id "
                             "JOIN jobs j ON j.job_id=s.job_id AND j.state='SUCCEEDED' "
                             "JOIN g5_candidates c ON c.job_id=s.job_id "
                             "AND c.candidate_sha256=s.candidate_sha256 "
                             "WHERE s.session_id=? AND s.project_id=?", (session_id, project)).fetchone()
            if not row or row[2] != nonce: _fail("G5_REVIEW_SESSION_INVALID", session_id, "Use the issued review nonce.")
            duration = json.loads(self.store.get_artifact(row[5]))["video"]["total_frames"] / 30
            if min(row[3], row[4]) + 1 / 30 < duration:
                _fail("G5_REVIEW_INCOMPLETE", session_id, "View and listen to the complete current MP4.")
            manifest.verify(self.store, project, row[5])
            db.execute("UPDATE g5_review_sessions SET completed=1 WHERE session_id=?", (session_id,))
        return {"review_session_id": session_id, "candidate_sha256": row[1], "completed": True}

    def export(self, project, body):
        if body["expected_revision"] != self.store.revision(project) or body["include_attribution"] is not True:
            _fail("FINAL_EXPORT_STALE", project, "Reload and include exact attribution evidence.")
        verify_g5_approval(self.store, project, body["gate_g5_approval_id"], body["render_job_id"])
        with self.store._transaction() as db:
            existing = db.execute("SELECT export_json FROM delivery_exports WHERE project_id=? AND job_id=? "
                                  "AND g5_approval_id=?", (project, body["render_job_id"],
                                                           body["gate_g5_approval_id"])).fetchone()
            if existing: return json.loads(existing[0])
            row = self._attempt(db, project, body["render_job_id"])
            export_id = "export_" + uuid4().hex
            result = {"export_id": export_id, "render_job_id": body["render_job_id"],
                      "mp4_artifact_id": row["output_sha256"],
                      "credits_artifact_id": row["attribution_sha256"],
                      "manifest_artifact_id": row["manifest_sha256"],
                      "qc_report_sha256": row["qc_report_sha256"]}
            db.execute("INSERT INTO delivery_exports VALUES(?,?,?,?,?,?,?,?)",
                       (export_id, project, body["render_job_id"], body["gate_g5_approval_id"],
                        row["output_sha256"], row["attribution_sha256"], row["manifest_sha256"],
                        json.dumps(result, sort_keys=True)))
            return result


def verify_g5_candidate(store, db, project, candidate_sha, fingerprint):
    row = db.execute("SELECT job_id,candidate_json FROM g5_candidates WHERE project_id=? AND candidate_sha256=? "
                     "AND dependency_fingerprint=?", (project, candidate_sha, fingerprint)).fetchone()
    if not row or store.get_artifact(candidate_sha) != canonical(json.loads(row[1])):
        _fail("G5_CANDIDATE_STALE", project, "Review the exact current successful render.")
    candidate = json.loads(row[1]); dep = candidate["dependencies"]
    attempt = db.execute("SELECT r.output_sha256,r.qc_report_sha256,r.qc_status,r.attribution_sha256,r.manifest_sha256,r.attempt_id "
                         "FROM render_attempts r JOIN jobs j ON j.job_id=r.job_id "
                         "WHERE r.job_id=? AND j.project_id=? AND j.state='SUCCEEDED'", (row[0], project)).fetchone()
    if not attempt or tuple(attempt) != (dep["mp4_sha256"], dep["qc_report_sha256"], "PASS",
                                        dep["attribution_sha256"], dep["render_input_manifest_sha256"], dep["attempt_id"]):
        _fail("G5_CANDIDATE_STALE", project, "Render/QC/credits binding changed.")
    review = db.execute("SELECT 1 FROM g5_review_sessions WHERE project_id=? AND job_id=? "
                        "AND candidate_sha256=? AND completed=1", (project, row[0], candidate_sha)).fetchone()
    if not review: _fail("G5_REVIEW_REQUIRED", project, "Complete a server-issued view/listen session before approval.")
    # Full reconstruction also verifies current G4 and every immutable source.
    manifest.verify(store, project, dep["render_input_manifest_sha256"])
    for item in (dep["mp4_sha256"], dep["qc_report_sha256"], dep["attribution_sha256"]):
        store.get_artifact(item)
    return candidate


def verify_g5_approval(store, project, approval_id, job_id):
    with store._connection() as db:
        head = db.execute("SELECT candidate_sha256,dependency_fingerprint,approval_id FROM gate_heads "
                          "WHERE project_id=? AND gate_id='G5'", (project,)).fetchone()
        if not head or head[2] != approval_id:
            _fail("G5_APPROVAL_REQUIRED", project, "Approve the current exact G5 candidate.")
        candidate = verify_g5_candidate(store, db, project, head[0], head[1])
        if candidate["dependencies"]["job_id"] != job_id:
            _fail("FINAL_EXPORT_JOB_MISMATCH", job_id, "Export only the G5-approved render job.")
    state = next(item for item in GateService(store).board(project) if item["gate_id"] == "G5")
    if state["state"] != "APPROVED": _fail("G5_APPROVAL_STALE", project, "Reapprove current delivery evidence.")
    return candidate
