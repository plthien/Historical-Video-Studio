"""A1-04: immutable gate decisions with revision-CAS and explicit candidate recovery."""
from __future__ import annotations

import json
import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from backend.app.contracts import ContractViolation, validate_document
from backend.app.projects.storage import ProjectStore

GATES = ("G1", "G2", "G3", "G4", "G5")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _fail(code: str, entity: str, remediation: str, gate: str | None = None):
    raise ContractViolation(code, entity, remediation, blocking_gate=gate)


def _story(db: sqlite3.Connection, project_id: str):
    row = db.execute("SELECT sha256,story_json FROM story_candidates WHERE project_id=? "
                     "ORDER BY revision DESC LIMIT 1", (project_id,)).fetchone()
    if not row:
        _fail("STORY_NOT_FOUND", project_id, "Import a StoryPackage first.", "G1")
    return row[0], json.loads(row[1])


def _g1_identity(db: sqlite3.Connection, project_id: str):
    """One authority for candidate SHA, saved human review generation and fingerprint."""
    sha, _ = _story(db, project_id)
    reviews = [dict(claim_id=r[0], disposition=r[1], evidence_note=r[2],
                    source_url=r[3], generation=r[4])
               for r in db.execute(
                   "SELECT claim_id,disposition,note,source_url,generation FROM claim_reviews "
                   "WHERE project_id=? AND story_sha256=? ORDER BY claim_id",
                   (project_id, sha))]
    snapshot = json.dumps({"story_sha256": sha, "reviews": reviews},
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    fingerprint = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
    return sha, fingerprint, snapshot


def _head(db, project_id: str, gate: str):
    return db.execute("SELECT candidate_sha256,dependency_fingerprint FROM gate_heads "
                      "WHERE project_id=? AND gate_id=?", (project_id, gate)).fetchone()


def _decision(db, project_id: str, gate: str):
    row = db.execute("SELECT record_json FROM gate_events WHERE project_id=? AND gate_id=? "
                     "ORDER BY committed_revision DESC LIMIT 1", (project_id, gate)).fetchone()
    return json.loads(row[0]) if row else None


class GateService:
    def __init__(self, store: ProjectStore):
        self.store = store
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS claim_reviews (
                    project_id TEXT NOT NULL, story_sha256 TEXT NOT NULL,
                    claim_id TEXT NOT NULL, disposition TEXT NOT NULL,
                    note TEXT NOT NULL, source_url TEXT,
                    generation INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(project_id,story_sha256,claim_id)
                );
                CREATE TABLE IF NOT EXISTS gate_candidates (
                    project_id TEXT NOT NULL, gate_id TEXT NOT NULL,
                    candidate_sha256 TEXT NOT NULL, dependency_fingerprint TEXT NOT NULL,
                    PRIMARY KEY(project_id,gate_id)
                );
                CREATE TABLE IF NOT EXISTS gate_heads (
                    project_id TEXT NOT NULL, gate_id TEXT NOT NULL,
                    candidate_sha256 TEXT NOT NULL, dependency_fingerprint TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    PRIMARY KEY(project_id,gate_id)
                );
                CREATE TABLE IF NOT EXISTS gate_events (
                    approval_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    gate_id TEXT NOT NULL, record_json TEXT NOT NULL,
                    committed_revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gate_staleness (
                    project_id TEXT NOT NULL, gate_id TEXT NOT NULL,
                    cause TEXT NOT NULL, PRIMARY KEY(project_id,gate_id)
                );
                CREATE TABLE IF NOT EXISTS gate_approval_reviews (
                    approval_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL,
                    FOREIGN KEY(approval_id) REFERENCES gate_events(approval_id)
                );
            """)
            # Fresh V1 compatibility with the first A1-04 implementation, not old-tool migration.
            fields = {row[1] for row in db.execute("PRAGMA table_info(claim_reviews)")}
            if "source_url" not in fields:
                db.execute("ALTER TABLE claim_reviews ADD COLUMN source_url TEXT")
            if "generation" not in fields:
                # Extend existing A1-04 DBs in place without migrating old-tool data.
                db.execute("ALTER TABLE claim_reviews ADD COLUMN generation INTEGER NOT NULL DEFAULT 1")

    @staticmethod
    def _check_revision(db, project_id, expected_revision):
        row = db.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            _fail("PROJECT_NOT_FOUND", project_id, "Create the project first.")
        if row[0] != expected_revision:
            _fail("APPROVAL_REVISION_CONFLICT", project_id, "Refresh the project before changing it.")
        return row[0]

    @staticmethod
    def _critical_missing(db, project_id, sha, story):
        reviewed = {x[0] for x in db.execute(
            "SELECT claim_id FROM claim_reviews WHERE project_id=? AND story_sha256=? "
            "AND disposition IN ('REVIEWED','VERIFIED')", (project_id, sha))}
        return [c["claim_id"] for c in story["claims"] if c["critical"] and c["claim_id"] not in reviewed]

    def reviews(self, project_id: str) -> list[dict]:
        with self.store._connection() as db:
            sha, _ = _story(db, project_id)
            return [dict(claim_id=r[0], status=r[1], evidence_note=r[2], source_url=r[3])
                    for r in db.execute("SELECT claim_id,disposition,note,source_url FROM claim_reviews "
                                        "WHERE project_id=? AND story_sha256=? ORDER BY claim_id", (project_id, sha))]

    def review_claim(self, project_id: str, claim_id: str, disposition: str,
                     note: str, expected_revision: int, source_url: str | None = None) -> int:
        if disposition not in ("REVIEWED", "VERIFIED") or not note.strip():
            _fail("CLAIM_REVIEW_INVALID", claim_id, "Provide a human-reviewed disposition and evidence note.", "G1")
        if source_url is not None and not source_url.startswith(("https://", "http://")):
            _fail("CLAIM_SOURCE_INVALID", claim_id, "Use a sourced HTTP(S) URL.", "G1")
        with self.store._transaction() as db:
            revision = self._check_revision(db, project_id, expected_revision)
            story_sha, story = _story(db, project_id)
            claim = next((item for item in story["claims"] if item["claim_id"] == claim_id), None)
            if claim is None:
                _fail("CLAIM_NOT_FOUND", claim_id, "Choose a claim in the current story.", "G1")
            if claim["critical"] and not claim["source_leads"] and not source_url:
                _fail("CLAIM_CRITICAL_UNRESOLVED", claim_id, "Critical claim requires a source link.", "G1")
            previous = db.execute(
                "SELECT disposition,note,source_url FROM claim_reviews "
                "WHERE project_id=? AND story_sha256=? AND claim_id=?",
                (project_id, story_sha, claim_id)).fetchone()
            if previous == (disposition, note, source_url):
                return revision  # saved evidence identical: no new generation or invalidation
            db.execute(
                "INSERT INTO claim_reviews(project_id,story_sha256,claim_id,disposition,note,source_url,generation) "
                "VALUES (?,?,?,?,?,?,1) ON CONFLICT(project_id,story_sha256,claim_id) "
                "DO UPDATE SET disposition=excluded.disposition,note=excluded.note,"
                "source_url=excluded.source_url,generation=claim_reviews.generation+1",
                (project_id, story_sha, claim_id, disposition, note, source_url))
            from backend.app.projects.revisions import mark_stale
            mark_stale(db, project_id, "claim_review")
            db.execute("UPDATE projects SET revision=? WHERE project_id=?", (revision + 1, project_id))
            return revision + 1

    def publish_candidate(self, project_id: str, gate: str, candidate_sha256: str,
                          dependency_fingerprint: str, expected_revision: int) -> None:
        """Owner producers may publish drafts; artifact existence is NOT approval evidence."""
        if gate not in GATES[1:]:
            _fail("GATE_ILLEGAL_TRANSITION", project_id, "G1 candidates are imported stories.", gate)
        if not _SHA.fullmatch(candidate_sha256) or not _SHA.fullmatch(dependency_fingerprint):
            _fail("CANDIDATE_SHA_INVALID", project_id, "Provide exact SHA-256 fingerprints.", gate)
        self.store.get_artifact(candidate_sha256)
        with self.store._transaction() as db:
            self._check_revision(db, project_id, expected_revision)
            previous = db.execute("SELECT candidate_sha256,dependency_fingerprint "
                                  "FROM gate_candidates WHERE project_id=? AND gate_id=?",
                                  (project_id, gate)).fetchone()
            if previous and tuple(previous) == (candidate_sha256, dependency_fingerprint):
                return  # never clear stale by re-submitting identical invalid evidence
            db.execute("INSERT INTO gate_candidates VALUES(?,?,?,?) "
                       "ON CONFLICT(project_id,gate_id) DO UPDATE SET "
                       "candidate_sha256=excluded.candidate_sha256,"
                       "dependency_fingerprint=excluded.dependency_fingerprint",
                       (project_id, gate, candidate_sha256, dependency_fingerprint))
            if not _head(db, project_id, gate):
                # Legacy false STALE markers from unapproved drafts must not
                # block the first fresh owner candidate; real approved heads
                # retain their staleness until actual reapproval.
                db.execute("DELETE FROM gate_staleness WHERE project_id=? AND gate_id=?",
                           (project_id, gate))

    def _candidate(self, db, project_id, gate):
        if gate == "G1":
            return _g1_identity(db, project_id)[:2]
        if gate == "G3":
            from backend.app.assets.resolution import AssetResolution
            return AssetResolution.gate_candidate(db, project_id, self.store)
        if gate == "G2":
            from backend.app.voice.assemble import selection_identity
            current = selection_identity(db, project_id)
            if current:
                return current
        return db.execute("SELECT candidate_sha256,dependency_fingerprint FROM gate_candidates "
                          "WHERE project_id=? AND gate_id=?", (project_id, gate)).fetchone()

    def _status(self, db, project_id, gate):
        candidate = self._candidate(db, project_id, gate) if gate != "G1" or db.execute(
            "SELECT 1 FROM story_candidates WHERE project_id=?", (project_id,)).fetchone() else None
        head = _head(db, project_id, gate)
        last = _decision(db, project_id, gate)
        stale = db.execute("SELECT cause FROM gate_staleness WHERE project_id=? AND gate_id=?",
                           (project_id, gate)).fetchone()
        missing = []
        if gate == "G1" and candidate:
            story_sha, story = _story(db, project_id)
            missing = self._critical_missing(db, project_id, story_sha, story)
        blockers = [] if candidate else ["CANDIDATE_NOT_READY"]
        blockers.extend("CLAIM_CRITICAL_UNRESOLVED:" + claim for claim in missing)
        if gate == "G1":
            # A draft changing is not evidence of an invalidated approval.
            # Historical decisions only bind their exact candidate + persisted review fingerprint.
            if not candidate:
                state = "DRAFT"
            elif missing:
                state = "BLOCKED"
            elif last and last["decision"] in ("CHANGES_REQUESTED", "REJECTED") and (
                    candidate[0], candidate[1]) == (
                    last["candidate_sha256"], last["dependency_fingerprint"]):
                state = last["decision"]
            elif head and tuple(head) == tuple(candidate) and not stale:
                state = "APPROVED"
            else:
                state = "READY_FOR_REVIEW"
            return state, candidate, blockers, last

        # Only a previously APPROVED head can become STALE. Drafts carrying
        # historical false markers are blocked (if a candidate remains), never
        # represented as a revoked approval.
        if not head and stale:
            if candidate:
                blockers.append("CANDIDATE_DEPENDENCY_CHANGED")
                return "BLOCKED", candidate, blockers, last
            return "DRAFT", None, blockers, last
        if not head and candidate and gate in ("G2", "G3", "G4", "G5") and (
                self._status(db, project_id, "G1")[0] != "APPROVED"):
            blockers.append("G1_APPROVAL_REQUIRED")
            return "BLOCKED", candidate, blockers, last

        if gate == "G4" and (candidate or head):
            from backend.app.voice.workflow import word_map_ready
            if not word_map_ready(db, project_id):
                blockers.append("WORD_MAP_MISSING_OR_STALE")
                return ("STALE" if head else "BLOCKED"), candidate, blockers, last
        # Current G1 authorization, never just a historical gate_heads row, is
        # required before any dependent gate becomes effectively approved.
        if gate in ("G4", "G5") and head and self._status(db, project_id, "G1")[0] != "APPROVED":
            blockers.append("G1_APPROVAL_STALE")
            return "STALE", candidate, blockers, last
        changed_since = bool(last and candidate and (
            candidate[0] != last["candidate_sha256"] or
            candidate[1] != last["dependency_fingerprint"]))
        changed_head = bool(head and candidate and tuple(head) != tuple(candidate))
        if last and last["decision"] in ("CHANGES_REQUESTED", "REJECTED") and not changed_since:
            state = last["decision"]
            if stale:
                blockers.append(stale[0])
        elif stale or changed_head:
            if candidate and changed_since and not missing:
                state = "READY_FOR_REVIEW"
            else:
                state = "STALE"
                blockers.append(stale[0] if stale else "CANDIDATE_SHA_CHANGED")
        elif last and last["decision"] in ("CHANGES_REQUESTED", "REJECTED"):
            state = "READY_FOR_REVIEW" if changed_since and not missing else last["decision"]
        elif head and candidate and tuple(head) == tuple(candidate):
            state = "APPROVED"
        elif blockers:
            state = "BLOCKED" if candidate else "DRAFT"
        else:
            state = "READY_FOR_REVIEW"
        return state, candidate, blockers, last

    def board(self, project_id: str) -> list[dict]:
        revision = self.store.revision(project_id)
        with self.store._connection() as db:
            out = []
            for gate in GATES:
                state, candidate, blockers, _ = self._status(db, project_id, gate)
                out.append({"gate_id": gate, "state": state,
                            "candidate_sha256": candidate[0] if candidate else None,
                            "dependency_fingerprint": candidate[1] if candidate else None,
                            "blockers": blockers, "revision": revision})
            return out

    def decide(self, project_id: str, gate: str, payload: dict, *, approval_id: str | None = None) -> dict:
        if gate not in GATES:
            _fail("GATE_UNKNOWN", gate, "Use one of G1–G5.")
        required = {"decision", "candidate_sha256", "dependency_fingerprint", "expected_revision"}
        if not isinstance(payload, dict) or not required.issubset(payload):
            _fail("GATE_DECISION_INVALID", gate, "Supply all required GateDecision fields.", gate)
        if payload["decision"] not in ("APPROVED", "CHANGES_REQUESTED", "REJECTED"):
            _fail("GATE_DECISION_INVALID", gate, "Use an allowed decision.", gate)
        with self.store._transaction() as db:
            revision = self._check_revision(db, project_id, payload["expected_revision"])
            state, candidate, blockers, last = self._status(db, project_id, gate)
            if not candidate:
                _fail("GATE_ILLEGAL_TRANSITION", gate, "No candidate from its owner.", gate)
            if tuple(candidate) != (payload["candidate_sha256"], payload["dependency_fingerprint"]):
                _fail("APPROVAL_REVISION_CONFLICT", gate, "Candidate SHA or dependency snapshot changed.", gate)
            if state != "READY_FOR_REVIEW":
                if gate == "G1" and any("CLAIM_CRITICAL_UNRESOLVED" in b for b in blockers):
                    _fail("CLAIM_CRITICAL_UNRESOLVED", gate, "Review all critical claims first.", gate)
                _fail("GATE_ILLEGAL_TRANSITION", gate, "This candidate is not ready for a new decision.", gate)
            if gate != "G1":
                # A2/A3/B1–B3 must supply real pipeline evidence before approval.
                # No generic artifact, schema-valid fixture, or invented table can authorize them.
                if payload["decision"] == "APPROVED" and gate not in ("G2","G3"):
                    _fail("GATE_ILLEGAL_TRANSITION", gate, "Owner pipeline approval evidence is not implemented.", gate)
                if gate == "G3" and payload["decision"] == "APPROVED":
                    from backend.app.assets.resolution import AssetResolution
                    actual = AssetResolution.gate_candidate(db,project_id,self.store)
                    if actual is None or tuple(actual)!=tuple(candidate):
                        _fail("G3_SOURCE_STALE",gate,"Every asset needs current exact source/rights approval.",gate)
                if gate == "G2" and payload["decision"] == "APPROVED":
                    from backend.app.voice.assemble import selection_snapshot, canonical, sha, assemble_frozen
                    snapshot = selection_snapshot(db, project_id)
                    if not snapshot or sha(canonical(snapshot)) != candidate[0]:
                        _fail("GATE_ILLEGAL_TRANSITION", gate,
                              "A G2 owner candidate must bind selected current audio in every section.", gate)
                    # Validate real audio samples before creating immutable approval intent.
                    assemble_frozen(self.store, project_id, snapshot)
                if self._status(db, project_id, "G1")[0] != "APPROVED":
                    _fail("GATE_ILLEGAL_TRANSITION", gate, "Approve the CURRENT G1 review dependencies first.", gate)
            record = {
                "schema_version": "ApprovalRecord.v1",
                "approval_id": approval_id or "approval_" + uuid4().hex,
                "project_id": project_id, "gate_id": gate, "decision": payload["decision"],
                "candidate_sha256": candidate[0], "dependency_fingerprint": candidate[1],
                "expected_revision": revision, "approved_by": "local_operator",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "affected_ids": payload.get("affected_ids", []), "comment": payload.get("comment", "")
            }
            validate_document("ApprovalRecord.v1", record)
            db.execute("INSERT INTO gate_events VALUES(?,?,?,?,?)",
                       (record["approval_id"], project_id, gate, json.dumps(record, sort_keys=True), revision + 1))
            if gate == "G1":
                _, fingerprint, evidence = _g1_identity(db, project_id)
                if fingerprint != candidate[1]:
                    _fail("APPROVAL_REVISION_CONFLICT", gate, "Review evidence changed during approval.", gate)
                db.execute("INSERT INTO gate_approval_reviews(approval_id,snapshot_json) VALUES(?,?)",
                           (record["approval_id"], evidence))
            if record["decision"] == "APPROVED":
                db.execute("INSERT INTO gate_heads VALUES(?,?,?,?,?) ON CONFLICT(project_id,gate_id) "
                           "DO UPDATE SET candidate_sha256=excluded.candidate_sha256,"
                           "dependency_fingerprint=excluded.dependency_fingerprint,approval_id=excluded.approval_id",
                           (project_id, gate, candidate[0], candidate[1], record["approval_id"]))
                db.execute("DELETE FROM gate_staleness WHERE project_id=? AND gate_id=?", (project_id, gate))
            job_id = None
            if gate == "G2" and record["decision"] == "APPROVED":
                from backend.app.voice.workflow import enqueue_assembly_tx
                job_id = enqueue_assembly_tx(db, project_id, record["approval_id"])
            db.execute("UPDATE projects SET revision=? WHERE project_id=?", (revision + 1, project_id))
            return {"approval_id": record["approval_id"], "gate_id": gate,
                    "state": record["decision"], "project_revision": revision + 1,
                    **({"job_id": job_id} if job_id else {})}
