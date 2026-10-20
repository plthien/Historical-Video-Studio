"""A2-03/04: immutable G2 approval->assembly->forced-alignment jobs.

Approval intent and durable job are inserted in the same SQLite transaction by
GateService. Actual final WAV and provider-derived word map only commit on success.
"""
from __future__ import annotations

import json
from uuid import uuid4

from backend.app.contracts import ContractViolation, validate_document
from backend.app.voice.assemble import canonical, sha, assemble_frozen, selection_snapshot, selection_identity
from backend.app.voice.alignment import align_audio
from backend.app.voice.word_map import word_map
from backend.app.projects.gates import _head, _g1_identity


def enqueue_tx(db, project: str, kind: str, key: str, payload: dict) -> str:
    body = canonical(payload).decode("utf-8")
    digest = sha(body.encode("utf-8"))
    old = db.execute("SELECT job_id,payload_sha256 FROM jobs WHERE project_id=? AND kind=? "
                     "AND idempotency_key=?", (project, kind, key)).fetchone()
    if old:
        if old[1] != digest:
            raise ContractViolation("IDEMPOTENCY_CONFLICT", project, "Use a new key for a different operation.")
        return old[0]
    job_id = "job_" + uuid4().hex
    db.execute("INSERT INTO jobs(job_id,project_id,kind,idempotency_key,payload_sha256,"
               "payload_json,state) VALUES(?,?,?,?,?,?,'QUEUED')",
               (job_id, project, kind, key, digest, body))
    return job_id


def enqueue_assembly_tx(db, project: str, approval_id: str) -> str:
    snapshot = selection_snapshot(db, project)
    if snapshot is None:
        raise ContractViolation("FINAL_AUDIO_SELECTION_INCOMPLETE", project,
                                "Approve G1 and select a compatible attempt for every section.")
    return enqueue_tx(db, project, "final_assembly", "assembly-" + approval_id,
                      {"approval_id": approval_id, "snapshot": snapshot})


def word_map_ready(db, project: str) -> bool:
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='word_maps'").fetchone():
        return False
    head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                      (project,)).fetchone()
    if not head or db.execute("SELECT 1 FROM gate_staleness WHERE project_id=? AND gate_id='G2'",
                              (project,)).fetchone():
        return False
    expected = selection_identity(db, project)
    approved = _head(db, project, "G2")
    if not expected or tuple(approved) != tuple(expected):
        return False
    row = db.execute("SELECT f.audio_sha256,f.transcript_sha256,w.audio_sha256 "
                     "FROM final_audio f LEFT JOIN word_maps w ON w.audio_sha256=f.audio_sha256 "
                     "AND w.transcript_sha256=f.transcript_sha256 AND w.project_id=f.project_id "
                     "WHERE f.project_id=? AND f.approval_id=?",
                     (project, head[0])).fetchone()
    return bool(row and row[2] == row[0])


class FinalVoiceWorkflow:
    def __init__(self, store, gates, queue):
        self.store, self.gates, self.queue = store, gates, queue
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS final_audio(
                    approval_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    audio_sha256 TEXT NOT NULL, transcript_sha256 TEXT NOT NULL,
                    final_json TEXT NOT NULL, transcript TEXT NOT NULL,
                    selection_sha256 TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS word_maps(
                    project_id TEXT NOT NULL, audio_sha256 TEXT NOT NULL,
                    transcript_sha256 TEXT NOT NULL,
                    map_sha256 TEXT NOT NULL, map_json TEXT NOT NULL,
                    job_id TEXT UNIQUE NOT NULL,
                    PRIMARY KEY(project_id,audio_sha256,transcript_sha256)
                );
            """)

    def preflight(self, project: str) -> dict:
        with self.store._connection() as db:
            snapshot = selection_snapshot(db, project)
        if not snapshot:
            raise ContractViolation("FINAL_AUDIO_SELECTION_INCOMPLETE", project,
                                    "All current G1 sections need approved-source selected attempts.")
        # Validate original bytes and actual sample metadata prior to accepting the human decision.
        final, data, _ = assemble_frozen(self.store, project, snapshot)
        if not final["duration_samples"] or not data:
            raise ContractViolation("FINAL_AUDIO_INVALID", project, "Selected WAV contains no audio.")
        return snapshot

    def process_one(self, provider=None) -> dict | None:
        job = self.queue.claim("final_assembly")
        if job is not None:
            return self._assemble(job)
        job = self.queue.claim("final_alignment")
        if job is not None:
            return self._align(job, provider)
        return None

    def process_pending(self, provider=None) -> None:
        # One assembly + its downstream alignment, if queued.
        self.process_one(provider)
        self.process_one(provider)

    def _fail(self, job: dict, code: str) -> dict:
        return self.queue.fail(job["job_id"], job["lease_token"], code, retryable=False)

    def _assemble(self, job: dict) -> dict:
        try:
            if job["resume_only"]:
                raise ContractViolation("VOICE_OPERATION_UNCERTAIN", job["job_id"],
                                        "Interrupted assembly needs a new explicit recovery review.")
            payload = json.loads(job["payload_json"])
            project, approval, snapshot = job["project_id"], payload["approval_id"], payload["snapshot"]
            result, wav, transcript = assemble_frozen(self.store, project, snapshot)
            # Artifact bytes are immutable and verified before transaction publishes current status.
            self.store.put_artifact(wav, "voice_audio", result["audio_sha256"])
            result_json = canonical(result).decode("utf-8")
            manifest_sha = sha(canonical(snapshot))
            with self.store._transaction() as db:
                owned = self.queue._owned(db, job["job_id"], job["lease_token"])
                if owned["cancel_requested"]:
                    raise ContractViolation("JOB_CANCEL_PENDING", job["job_id"], "Resolve cancellation first.")
                head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                                  (project,)).fetchone()
                if not head or head[0] != approval or selection_snapshot(db, project) != snapshot:
                    raise ContractViolation("FINAL_AUDIO_SOURCE_STALE", project,
                                            "Voice selections or G1 changed before final WAV commit.")
                db.execute("INSERT INTO final_audio VALUES(?,?,?,?,?,?,?)",
                           (approval, project, result["audio_sha256"], result["transcript_sha256"],
                            result_json, transcript, manifest_sha))
                enqueue_tx(db, project, "final_alignment", "align-" + approval,
                           {"approval_id": approval, "audio_sha256": result["audio_sha256"],
                            "transcript_sha256": result["transcript_sha256"]})
                db.execute("UPDATE jobs SET state='SUCCEEDED',output_sha256=?,lease_token=NULL,"
                           "error_code=NULL WHERE job_id=? AND lease_token=? AND state='RUNNING'",
                           (result["audio_sha256"], job["job_id"], job["lease_token"]))
            return self.queue.get(job["job_id"])
        except ContractViolation as exc:
            return self._fail(job, exc.code)
        except Exception:
            return self._fail(job, "FINAL_AUDIO_ASSEMBLY_FAILED")

    def _align(self, job: dict, provider=None) -> dict:
        try:
            if job["resume_only"]:
                raise ContractViolation("ALIGNMENT_UNCERTAIN_OPERATION", job["job_id"],
                                        "Review interrupted provider request before retrying.")
            payload = json.loads(job["payload_json"])
            project, approval = job["project_id"], payload["approval_id"]
            with self.store._connection() as db:
                row = db.execute("SELECT final_json,transcript FROM final_audio "
                                 "WHERE project_id=? AND approval_id=?", (project, approval)).fetchone()
                head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                                  (project,)).fetchone()
                if not row or not head or head[0] != approval or not word_map_source_current(db, project):
                    raise ContractViolation("WORD_MAP_STALE", project,
                                            "Final WAV no longer matches current approved G2 selection.")
            final, transcript = json.loads(row[0]), row[1]
            if (final["audio_sha256"] != payload["audio_sha256"] or
                    final["transcript_sha256"] != payload["transcript_sha256"]):
                raise ContractViolation("WORD_MAP_STALE", project, "Alignment payload identity differs.")
            wav = self.store.get_artifact(final["audio_sha256"])
            response = (align_audio(wav, transcript) if provider is None else provider(wav, transcript))
            result = word_map(project, final, transcript, response)
            doc = canonical(result)
            digest = self.store.put_artifact(doc, "word_map")
            with self.store._transaction() as db:
                owned = self.queue._owned(db, job["job_id"], job["lease_token"])
                if owned["cancel_requested"] or not word_map_source_current(db, project):
                    raise ContractViolation("WORD_MAP_STALE", project, "Source changed while alignment ran.")
                head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                                  (project,)).fetchone()
                if not head or head[0] != approval:
                    raise ContractViolation("WORD_MAP_STALE", project, "Approval changed while aligning.")
                db.execute("INSERT INTO word_maps VALUES(?,?,?,?,?,?)",
                           (project, final["audio_sha256"], final["transcript_sha256"],
                            digest, doc.decode("utf-8"), job["job_id"]))
                db.execute("UPDATE jobs SET state='SUCCEEDED',output_sha256=?,lease_token=NULL,"
                           "error_code=NULL WHERE job_id=? AND lease_token=? AND state='RUNNING'",
                           (digest, job["job_id"], job["lease_token"]))
            return self.queue.get(job["job_id"])
        except ContractViolation as exc:
            return self._fail(job, exc.code)
        except Exception:
            return self._fail(job, "ALIGNMENT_RESPONSE_INVALID")

    def status(self, project: str) -> dict:
        self.store.revision(project)
        with self.store._connection() as db:
            head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                              (project,)).fetchone()
            approval = head[0] if head else None
            final_row = db.execute("SELECT final_json FROM final_audio WHERE project_id=? AND approval_id=?",
                                   (project, approval)).fetchone()
            current = bool(approval and word_map_source_current(db, project))
            latest = lambda kind: db.execute(
                "SELECT job_id,state,error_code,retry_count FROM jobs WHERE project_id=? AND kind=? "
                "ORDER BY rowid DESC LIMIT 1", (project, kind)).fetchone()
            assembly, alignment_job = latest("final_assembly"), latest("final_alignment")
            final = json.loads(final_row[0]) if final_row and current else None
            row = (db.execute("SELECT map_json,map_sha256 FROM word_maps "
                              "WHERE project_id=? AND audio_sha256=? AND transcript_sha256=?",
                              (project, final["audio_sha256"], final["transcript_sha256"])).fetchone() if final else None)
            word = json.loads(row[0]) if row else None
        if final:
            self.store.get_artifact(final["audio_sha256"])
        if word:
            self.store.get_artifact(row[1])
        return {"approval_id": approval, "current": current, "final_audio": final, "word_map": word,
                "assembly_job": dict(zip(("job_id","state","error_code","retry_count"), assembly)) if assembly else None,
                "alignment_job": dict(zip(("job_id","state","error_code","retry_count"), alignment_job)) if alignment_job else None,
                "g4_ready_dependency": bool(current and word)}

    def retry_assembly(self, project: str, expected_revision: int, key: str) -> str:
        """Explicit technical recovery of a failed/interrupted frozen G2 job; no second approval."""
        with self.store._transaction() as db:
            self.gates._check_revision(db, project, expected_revision)
            head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                              (project,)).fetchone()
            snapshot = selection_snapshot(db, project)
            approved = _head(db, project, "G2")
            if not head or not snapshot or tuple(approved) != selection_identity(db, project):
                raise ContractViolation("FINAL_AUDIO_SOURCE_STALE", project,
                                        "G2 selection changed; a technical retry cannot revive stale audio.")
            current = db.execute("SELECT job_id,state,payload_json FROM jobs WHERE project_id=? "
                                 "AND kind='final_assembly' ORDER BY rowid DESC LIMIT 1",
                                 (project,)).fetchone()
            if (not current or current[1] not in ("FAILED_TERMINAL","FAILED_RETRYABLE","BLOCKED_REVIEW")
                    or json.loads(current[2])["approval_id"] != head[0]):
                raise ContractViolation("FINAL_AUDIO_RETRY_FORBIDDEN", project,
                                        "Retry is allowed only after an actual failed/blocked assembly job.")
            if db.execute("SELECT 1 FROM final_audio WHERE approval_id=?", (head[0],)).fetchone():
                raise ContractViolation("FINAL_AUDIO_RETRY_FORBIDDEN", project, "Final WAV already exists.")
            return enqueue_tx(db, project, "final_assembly", key,
                              {"approval_id": head[0], "snapshot": snapshot})

    def retry_alignment(self, project: str, expected_revision: int, audio_sha: str,
                        transcript_sha: str, key: str) -> dict:
        with self.store._transaction() as db:
            self.gates._check_revision(db, project, expected_revision)
            if not word_map_source_current(db, project):
                raise ContractViolation("WORD_MAP_STALE", project, "Reapprove changed audio selection first.")
            head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                              (project,)).fetchone()
            row = db.execute("SELECT audio_sha256,transcript_sha256 FROM final_audio "
                             "WHERE approval_id=? AND project_id=?", (head[0], project)).fetchone()
            if not row or tuple(row) != (audio_sha, transcript_sha):
                raise ContractViolation("WORD_MAP_STALE", project, "Retry requires exact frozen final WAV and transcript.")
            previous = db.execute("SELECT state FROM jobs WHERE project_id=? AND kind='final_alignment' "
                                  "ORDER BY rowid DESC LIMIT 1", (project,)).fetchone()
            if not previous or previous[0] not in ("FAILED_TERMINAL","FAILED_RETRYABLE","BLOCKED_REVIEW"):
                raise ContractViolation("ALIGNMENT_RETRY_FORBIDDEN", project,
                                        "Retry is available only after a failed or review-blocked attempt.")
            job = enqueue_tx(db, project, "final_alignment", key,
                             {"approval_id": head[0], "audio_sha256": audio_sha,
                              "transcript_sha256": transcript_sha})
        return self.queue.get(job)

    def audio(self, project: str, digest: str) -> bytes:
        self.store.revision(project)
        with self.store._connection() as db:
            found = db.execute(
                "SELECT 1 FROM voice_attempts WHERE project_id=? AND audio_sha256=? "
                "UNION SELECT 1 FROM final_audio WHERE project_id=? AND audio_sha256=?",
                (project, digest, project, digest)).fetchone()
        if not found:
            raise ContractViolation("VOICE_ATTEMPT_NOT_FOUND", digest, "Audio belongs to another project or is absent.")
        return self.store.get_artifact(digest)


def word_map_source_current(db, project: str) -> bool:
    head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                      (project,)).fetchone()
    if not head or db.execute("SELECT 1 FROM gate_staleness WHERE project_id=? AND gate_id='G2'",
                              (project,)).fetchone():
        return False
    identity = selection_identity(db, project)
    approved = _head(db, project, "G2")
    if not identity or not approved or tuple(approved) != tuple(identity):
        return False
    row = db.execute("SELECT 1 FROM final_audio WHERE project_id=? AND approval_id=?",
                     (project, head[0])).fetchone()
    return bool(row)
