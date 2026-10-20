"""A1-05 durable SQLite job identities, leases, cancellation and explicit retry."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from uuid import uuid4

from backend.app.contracts import ContractViolation
from backend.app.projects.storage import ProjectStore

STATES = frozenset(("QUEUED", "RUNNING", "SUCCEEDED", "FAILED_RETRYABLE",
                    "FAILED_TERMINAL", "CANCELLED", "BLOCKED_REVIEW"))


class JobQueue:
    def __init__(self, store: ProjectStore):
        self.store = store
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                        ('QUEUED','RUNNING','SUCCEEDED','FAILED_RETRYABLE',
                         'FAILED_TERMINAL','CANCELLED','BLOCKED_REVIEW')),
                    lease_token TEXT, provider_task_id TEXT,
                    resume_only INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    output_sha256 TEXT, error_code TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id),
                    UNIQUE(project_id,kind,idempotency_key)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_provider_identity
                    ON jobs(kind,provider_task_id) WHERE provider_task_id IS NOT NULL;
            """)

    @staticmethod
    def _row(db, job_id):
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise ContractViolation("JOB_NOT_FOUND", job_id, "Select an existing job.")
        return dict(row)

    def get(self, job_id: str) -> dict:
        with self.store._connection() as db:
            return self._row(db, job_id)

    def submit(self, project_id: str, kind: str, idempotency_key: str,
               payload: dict, expected_revision: int) -> dict:
        if len(idempotency_key) < 12 or not kind or len(kind) > 64:
            raise ContractViolation("JOB_INPUT_INVALID", project_id,
                                    "Provide a kind and an Idempotency-Key of at least 12 characters.")
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        with self.store._transaction() as db:
            db.row_factory = sqlite3.Row
            old = db.execute(
                "SELECT * FROM jobs WHERE project_id=? AND kind=? AND idempotency_key=?",
                (project_id, kind, idempotency_key)
            ).fetchone()
            if old is not None:
                if old["payload_sha256"] != digest:
                    raise ContractViolation("IDEMPOTENCY_CONFLICT", project_id,
                                            "Do not reuse an operation key for different inputs.")
                return dict(old)
            revision = db.execute("SELECT revision FROM projects WHERE project_id=?",
                                  (project_id,)).fetchone()
            if revision is None or revision[0] != expected_revision:
                raise ContractViolation("REVISION_CONFLICT", project_id, "Reload the project before queueing.")
            job_id = "job_" + uuid4().hex
            db.execute("INSERT INTO jobs(job_id,project_id,kind,idempotency_key,payload_sha256,"
                       "payload_json,state) VALUES(?,?,?,?,?,?,'QUEUED')",
                       (job_id, project_id, kind, idempotency_key, digest, body))
            return self._row(db, job_id)

    def claim(self, kind: str | None = None, *, job_id: str | None = None) -> dict | None:
        with self.store._transaction() as db:
            row = db.execute(
                "SELECT job_id FROM jobs WHERE state='QUEUED' AND cancel_requested=0 "
                "AND (? IS NULL OR kind=?) AND (? IS NULL OR job_id=?) ORDER BY rowid LIMIT 1",
                (kind, kind, job_id, job_id)
            ).fetchone()
            if row is None:
                return None
            token = "lease_" + uuid4().hex
            db.execute("UPDATE jobs SET state='RUNNING',lease_token=? WHERE job_id=? AND state='QUEUED'",
                       (token, row[0]))
            return self._row(db, row[0])

    def attach_provider_task(self, job_id: str, lease_token: str, task_id: str) -> None:
        if not task_id:
            raise ContractViolation("PROVIDER_TASK_INVALID", job_id, "Provider task ID is required.")
        with self.store._transaction() as db:
            job = self._owned(db, job_id, lease_token)
            if job["resume_only"] and task_id != job["provider_task_id"]:
                raise ContractViolation("PROVIDER_TASK_CONFLICT", job_id,
                                        "Resume the original provider task, never submit another.")
            if job["provider_task_id"] and job["provider_task_id"] != task_id:
                raise ContractViolation("PROVIDER_TASK_CONFLICT", job_id,
                                        "Provider task identity is immutable.")
            db.execute("UPDATE jobs SET provider_task_id=? WHERE job_id=?", (task_id, job_id))

    def _owned(self, db, job_id: str, token: str) -> dict:
        row = self._row(db, job_id)
        if row["state"] != "RUNNING" or row["lease_token"] != token:
            raise ContractViolation("JOB_LEASE_CONFLICT", job_id, "This worker no longer owns the job.")
        return row

    def cancel(self, job_id: str) -> dict:
        with self.store._transaction() as db:
            row = self._row(db, job_id)
            if row["state"] == "QUEUED":
                db.execute("UPDATE jobs SET state='CANCELLED',cancel_requested=1 WHERE job_id=?", (job_id,))
            elif row["state"] == "RUNNING":
                # Provider cancellation is not complete until the worker acknowledges it.
                db.execute("UPDATE jobs SET cancel_requested=1 WHERE job_id=?", (job_id,))
            return self._row(db, job_id)

    def acknowledge_cancel(self, job_id: str, lease_token: str, *, provider_confirmed: bool = False) -> dict:
        with self.store._transaction() as db:
            job = self._owned(db, job_id, lease_token)
            if not job["cancel_requested"]:
                raise ContractViolation("JOB_CANCEL_NOT_REQUESTED", job_id, "Request cancellation first.")
            if job["provider_task_id"] and not provider_confirmed:
                raise ContractViolation("PROVIDER_CANCEL_UNCONFIRMED", job_id,
                                        "Confirm external task cancellation before marking cancelled.")
            db.execute("UPDATE jobs SET state='CANCELLED',lease_token=NULL WHERE job_id=?", (job_id,))
            return self._row(db, job_id)

    def finish(self, job_id: str, lease_token: str, output_sha256: str) -> dict:
        # Success is an immutable local artifact, not a mocked handler return value.
        self.store.get_artifact(output_sha256)
        with self.store._transaction() as db:
            job = self._owned(db, job_id, lease_token)
            if job["cancel_requested"]:
                raise ContractViolation("JOB_CANCEL_PENDING", job_id, "Resolve cancellation before success.")
            db.execute("UPDATE jobs SET state='SUCCEEDED',output_sha256=?,lease_token=NULL,"
                       "error_code=NULL WHERE job_id=?", (output_sha256, job_id))
            return self._row(db, job_id)

    def fail(self, job_id: str, lease_token: str, error_code: str, retryable: bool) -> dict:
        if not error_code:
            raise ContractViolation("JOB_ERROR_REQUIRED", job_id, "Persist an actionable error code.")
        with self.store._transaction() as db:
            self._owned(db, job_id, lease_token)
            state = ("BLOCKED_REVIEW" if error_code == "CANCELLATION_NOT_CONFIRMED"
                     else "FAILED_RETRYABLE" if retryable else "FAILED_TERMINAL")
            db.execute("UPDATE jobs SET state=?,error_code=?,lease_token=NULL WHERE job_id=?",
                       (state, error_code, job_id))
            return self._row(db, job_id)

    def retry(self, job_id: str, max_retries: int = 3) -> dict:
        with self.store._transaction() as db:
            row = self._row(db, job_id)
            if row["state"] != "FAILED_RETRYABLE" or row["retry_count"] >= max_retries:
                raise ContractViolation("JOB_RETRY_FORBIDDEN", job_id, "Job is terminal or retry budget exhausted.")
            # Retain provider_task_id; resume-only jobs must poll, never resubmit.
            db.execute("UPDATE jobs SET state='QUEUED',retry_count=retry_count+1,"
                       "resume_only=CASE WHEN provider_task_id IS NULL THEN 0 ELSE 1 END,"
                       "cancel_requested=0 WHERE job_id=?", (job_id,))
            return self._row(db, job_id)

    def list_for_project(self, project_id: str) -> list[dict]:
        with self.store._connection() as db:
            db.row_factory = sqlite3.Row
            return [dict(x) for x in db.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY rowid DESC",
                                                (project_id,))]
