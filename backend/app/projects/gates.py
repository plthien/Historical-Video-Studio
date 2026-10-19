"""G1–G5 transactional decisions on immutable candidate and dependency identities."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from backend.app.contracts import ContractViolation, validate_document
from backend.app.projects.storage import ProjectStore

GATES = ("G1", "G2", "G3", "G4", "G5")


def _fail(code: str, project_id: str, remediation: str, gate: str | None = None):
    raise ContractViolation(code, project_id, remediation, blocking_gate=gate)


def _story(db: sqlite3.Connection, project_id: str):
    row = db.execute(
        "SELECT sha256, story_json FROM story_candidates WHERE project_id=? "
        "ORDER BY revision DESC LIMIT 1", (project_id,)
    ).fetchone()
    if row is None:
        _fail("STORY_NOT_FOUND", project_id, "Import the StoryPackage first.", "G1")
    return row[0], json.loads(row[1])


def _head(db, project_id, gate):
    return db.execute(
        "SELECT candidate_sha256, dependency_fingerprint FROM gate_heads "
        "WHERE project_id=? AND gate_id=?", (project_id, gate)
    ).fetchone()


class GateService:
    def __init__(self, store: ProjectStore):
        self.store = store
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS claim_reviews (
                    project_id TEXT NOT NULL, story_sha256 TEXT NOT NULL,
                    claim_id TEXT NOT NULL, disposition TEXT NOT NULL,
                    note TEXT NOT NULL,
                    PRIMARY KEY(project_id, story_sha256, claim_id)
                );
                CREATE TABLE IF NOT EXISTS gate_candidates (
                    project_id TEXT NOT NULL, gate_id TEXT NOT NULL,
                    candidate_sha256 TEXT NOT NULL, dependency_fingerprint TEXT NOT NULL,
                    PRIMARY KEY(project_id, gate_id)
                );
                CREATE TABLE IF NOT EXISTS gate_heads (
                    project_id TEXT NOT NULL, gate_id TEXT NOT NULL,
                    candidate_sha256 TEXT NOT NULL, dependency_fingerprint TEXT NOT NULL,
                    approval_id TEXT NOT NULL, PRIMARY KEY(project_id, gate_id)
                );
                CREATE TABLE IF NOT EXISTS gate_events (
                    approval_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    gate_id TEXT NOT NULL, record_json TEXT NOT NULL,
                    committed_revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gate_staleness (
                    project_id TEXT NOT NULL, gate_id TEXT NOT NULL,
                    cause TEXT NOT NULL, PRIMARY KEY(project_id, gate_id)
                );
            """)

    def review_claim(self, project_id: str, claim_id: str, disposition: str,
                     note: str, expected_revision: int) -> int:
        if disposition not in ("REVIEWED", "VERIFIED") or not note.strip():
            _fail("CLAIM_REVIEW_INVALID", project_id, "Explicit claim disposition and review note required.", "G1")
        with self.store._transaction() as db:
            revision = self._check_revision(db, project_id, expected_revision)
            story_sha, story = _story(db, project_id)
            claim = next((x for x in story["claims"] if x["claim_id"] == claim_id), None)
            if claim is None:
                _fail("CLAIM_NOT_FOUND", claim_id, "Select a claim from current StoryPackage.", "G1")
            if claim["critical"] and not claim["source_leads"]:
                _fail("CLAIM_CRITICAL_UNRESOLVED", claim_id, "Critical claim needs source leads for human research.", "G1")
            db.execute("INSERT INTO claim_reviews VALUES (?,?,?,?,?) "
                       "ON CONFLICT(project_id,story_sha256,claim_id) DO UPDATE SET "
                       "disposition=excluded.disposition, note=excluded.note",
                       (project_id, story_sha, claim_id, disposition, note))
            db.execute("UPDATE projects SET revision=? WHERE project_id=?", (revision + 1, project_id))
            return revision + 1

    def publish_candidate(self, project_id: str, gate: str, candidate_sha256: str,
                          dependency_fingerprint: str, expected_revision: int) -> None:
        """Internal producer handoff only; not an HTTP endpoint or an approval."""
        if gate not in GATES[1:]:
            _fail("GATE_ILLEGAL_TRANSITION", project_id, "G1 uses the imported StoryPackage.", gate)
        for digest in (candidate_sha256, dependency_fingerprint):
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                _fail("CANDIDATE_SHA_INVALID", project_id, "Use exact SHA-256 identities.", gate)
        # Requires actual immutable artifact bytes, not an invented status string.
        self.store.get_artifact(candidate_sha256)
        with self.store._transaction() as db:
            self._check_revision(db, project_id, expected_revision)
            db.execute("INSERT INTO gate_candidates VALUES(?,?,?,?) "
                       "ON CONFLICT(project_id,gate_id) DO UPDATE SET "
                       "candidate_sha256=excluded.candidate_sha256,"
                       "dependency_fingerprint=excluded.dependency_fingerprint",
                       (project_id, gate, candidate_sha256, dependency_fingerprint))

    @staticmethod
    def _check_revision(db, project_id, expected_revision):
        row = db.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            _fail("PROJECT_NOT_FOUND", project_id, "Create project before gate action.")
        if row[0] != expected_revision:
            _fail("APPROVAL_REVISION_CONFLICT", project_id, "Reload the latest project revision.")
        return row[0]

    @staticmethod
    def _critical_missing(db, project_id, sha, story):
        reviewed = {x[0] for x in db.execute(
            "SELECT claim_id FROM claim_reviews WHERE project_id=? AND story_sha256=?",
            (project_id, sha)
        )}
        return [c["claim_id"] for c in story["claims"] if c["critical"] and c["claim_id"] not in reviewed]

    def board(self, project_id: str) -> list[dict]:
        revision = self.store.revision(project_id)
        with self.store._connection() as db:
            try:
                story_sha, story = _story(db, project_id)
                missing = self._critical_missing(db, project_id, story_sha, story)
            except ContractViolation:
                story_sha, missing = None, []
            results = []
            for gate in GATES:
                row = ((story_sha, story_sha) if story_sha else None) if gate == "G1" else db.execute(
                    "SELECT candidate_sha256,dependency_fingerprint FROM gate_candidates "
                    "WHERE project_id=? AND gate_id=?", (project_id, gate)
                ).fetchone()
                head = _head(db, project_id, gate)
                stale = db.execute("SELECT cause FROM gate_staleness WHERE project_id=? AND gate_id=?",
                                   (project_id, gate)).fetchone()
                blockers = ([] if row else ["CANDIDATE_NOT_READY"])
                if gate == "G1":
                    blockers.extend(f"CLAIM_CRITICAL_UNRESOLVED:{name}" for name in missing)
                if stale or (head and (not row or tuple(head) != tuple(row))):
                    state = "STALE"
                    blockers.append(stale[0] if stale else "CANDIDATE_SHA_CHANGED")
                elif head and row:
                    state = "APPROVED"
                elif blockers:
                    state = "BLOCKED" if row else "DRAFT"
                else:
                    state = "READY_FOR_REVIEW"
                results.append({"gate_id": gate, "state": state, "candidate_sha256": row[0] if row else None,
                                "dependency_fingerprint": row[1] if row else None,
                                "blockers": blockers, "revision": revision})
            return results

    def decide(self, project_id: str, gate: str, payload: dict, *, approval_id: str | None = None) -> dict:
        if gate not in GATES:
            _fail("GATE_UNKNOWN", project_id, "Use G1–G5.")
        required = {"decision", "candidate_sha256", "dependency_fingerprint", "expected_revision"}
        if not isinstance(payload, dict) or not required.issubset(payload):
            _fail("GATE_DECISION_INVALID", project_id, "Provide complete GateDecision.", gate)
        with self.store._transaction() as db:
            revision = self._check_revision(db, project_id, payload["expected_revision"])
            row = (_story(db, project_id)[0],) * 2 if gate == "G1" else db.execute(
                "SELECT candidate_sha256,dependency_fingerprint FROM gate_candidates "
                "WHERE project_id=? AND gate_id=?", (project_id, gate)
            ).fetchone()
            if not row:
                _fail("GATE_ILLEGAL_TRANSITION", project_id, "Candidate not produced by its owner.", gate)
            if tuple(row) != (payload["candidate_sha256"], payload["dependency_fingerprint"]):
                _fail("APPROVAL_REVISION_CONFLICT", project_id, "Candidate or dependency SHA is stale.", gate)
            if db.execute("SELECT 1 FROM gate_staleness WHERE project_id=? AND gate_id=?",
                          (project_id, gate)).fetchone():
                _fail("GATE_ILLEGAL_TRANSITION", project_id, "Regenerate the stale candidate first.", gate)
            if gate == "G1":
                story_sha, story = _story(db, project_id)
                if self._critical_missing(db, project_id, story_sha, story):
                    _fail("CLAIM_CRITICAL_UNRESOLVED", project_id, "Review every critical claim before G1.", gate)
            else:
                if not _head(db, project_id, "G1"):
                    _fail("GATE_ILLEGAL_TRANSITION", project_id, "Approve G1 first.", gate)
                if gate in ("G4", "G5"):
                    if not _head(db, project_id, "G2") or not _head(db, project_id, "G3"):
                        _fail("GATE_ILLEGAL_TRANSITION", project_id, "Approve G2 and G3 first.", gate)
                    # A2's real WordTimingMap validator must attest alignment. Until then fail closed.
                    if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alignment_evidence'").fetchone():
                        _fail("WORD_MAP_STALE", project_id, "Final WAV and genuine aligned word map are required.", gate)
                if gate == "G5" and not _head(db, project_id, "G4"):
                    _fail("GATE_ILLEGAL_TRANSITION", project_id, "Approve G4 before G5.", gate)
            if _head(db, project_id, gate):
                _fail("APPROVAL_REVISION_CONFLICT", project_id, "Already decided; do not duplicate approval.", gate)
            if payload["decision"] == "APPROVED" and gate == "G2":
                # A2 owns actual final WAV assembly and alignment. Never claim it happened here.
                _fail("GATE_ILLEGAL_TRANSITION", project_id, "Voice assembly/alignment owner A2 not implemented.", gate)
            record = {"schema_version": "ApprovalRecord.v1",
                      "approval_id": approval_id or "approval_" + uuid4().hex,
                      "project_id": project_id, "gate_id": gate,
                      "decision": payload["decision"], "candidate_sha256": row[0],
                      "dependency_fingerprint": row[1], "expected_revision": revision,
                      "approved_by": "local_operator",
                      "approved_at": datetime.now(timezone.utc).isoformat(),
                      "affected_ids": payload.get("affected_ids", []),
                      "comment": payload.get("comment", "")}
            validate_document("ApprovalRecord.v1", record)
            db.execute("INSERT INTO gate_events VALUES(?,?,?,?,?)",
                       (record["approval_id"], project_id, gate, json.dumps(record, sort_keys=True), revision + 1))
            if record["decision"] == "APPROVED":
                db.execute("INSERT INTO gate_heads VALUES (?,?,?,?,?)",
                           (project_id, gate, row[0], row[1], record["approval_id"]))
            db.execute("UPDATE projects SET revision=? WHERE project_id=?", (revision + 1, project_id))
            return {"approval_id": record["approval_id"], "gate_id": gate,
                    "state": record["decision"], "project_revision": revision + 1}
