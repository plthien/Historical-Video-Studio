"""Reviewed G1 auxiliary numeric-series events; never a substitute for G1 gate approval."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from backend.app.contracts import ContractViolation
from backend.app.projects.gates import GateService, _story, _head
from backend.app.projects.revisions import mark_stale

_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$|^-(?:[1-9][0-9]*)(?:\.[0-9]+)?$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _fail(code: str, entity: str, message: str):
    raise ContractViolation(code, entity, message, blocking_gate="G1")


class NumericSeries:
    """Events remain immutable. A separate current head is the only eligible revision."""

    def __init__(self, store):
        self.store = store
        GateService(store)
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS numeric_series_events(
                    approval_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL, series_id TEXT NOT NULL,
                    series_sha256 TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                    committed_revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS numeric_series_heads(
                    project_id TEXT NOT NULL, claim_id TEXT NOT NULL,
                    series_id TEXT NOT NULL, approval_id TEXT NOT NULL,
                    PRIMARY KEY(project_id,claim_id,series_id),
                    FOREIGN KEY(approval_id) REFERENCES numeric_series_events(approval_id)
                );
            """)

    def get(self, project_id: str, claim_id: str, series_id: str):
        with self.store._connection() as db:
            row = db.execute("""
                SELECT e.approval_id,e.series_sha256,e.snapshot_json
                  FROM numeric_series_heads h JOIN numeric_series_events e
                    ON e.approval_id=h.approval_id
                 WHERE h.project_id=? AND h.claim_id=? AND h.series_id=?
            """, (project_id, claim_id, series_id)).fetchone()
            if not row:
                return None
            snapshot = json.loads(row[2])
            story_sha, _ = _story(db, project_id)
            head = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G1'", (project_id,)).fetchone()
            current = story_sha == snapshot["frozen_story_sha256"] and bool(head) and head[0] == snapshot["g1_approval_id"]
            return {"approval_id": row[0], "series_sha256": row[1],
                    "current": current, "series": snapshot}

    def approve(self, project_id: str, claim_id: str, data: dict):
        with self.store._transaction() as db:
            rev = GateService._check_revision(db, project_id, data["expected_revision"])
            gates = GateService(self.store)
            if gates._status(db, project_id, "G1")[0] != "APPROVED":
                _fail("NUMERIC_SERIES_UNVERIFIED", claim_id, "Current G1 gate approval required.")
            story_sha, story = _story(db, project_id)
            if not any(c["claim_id"] == claim_id for c in story["claims"]):
                _fail("CLAIM_NOT_FOUND", claim_id, "Select a claim from this approved story.")
            review = db.execute("""
                SELECT disposition,source_url,note FROM claim_reviews
                 WHERE project_id=? AND story_sha256=? AND claim_id=?
            """, (project_id, story_sha, claim_id)).fetchone()
            if not review or review[0] != "VERIFIED" or not (review[1] or review[2]):
                _fail("NUMERIC_SERIES_UNVERIFIED", claim_id, "Verify the claim and its source context first.")
            g1 = db.execute("SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G1'", (project_id,)).fetchone()[0]
            if data["frozen_story_sha256"] != story_sha or data["g1_approval_id"] != g1:
                _fail("NUMERIC_SERIES_SOURCE_STALE", claim_id, "Refresh the exact approved G1 lineage.")
            obs = data["observations"]
            if len(obs) < 3 or obs[0]["frame_offset"] != 0 or obs[-1]["frame_offset"] != data["authored_duration_frames"]:
                _fail("NUMERIC_SERIES_INVALID", claim_id, "Include start, intermediate and exact end frames.")
            last = -1
            for entry in obs:
                offset, value, evidence = entry["frame_offset"], entry["value"], entry["source_evidence_sha256"]
                if offset <= last or not _DECIMAL.fullmatch(value):
                    _fail("NUMERIC_SERIES_INVALID", claim_id, "Use strictly increasing frames and canonical decimal strings.")
                last = offset
                try:
                    d = Decimal(value)
                except InvalidOperation:
                    _fail("NUMERIC_SERIES_INVALID", claim_id, "Value must be finite decimal.")
                if not d.is_finite() or -d.as_tuple().exponent > data["precision"]:
                    _fail("NUMERIC_SERIES_INVALID", claim_id, "Value exceeds reviewed decimal precision.")
                if not _SHA.fullmatch(evidence):
                    _fail("NUMERIC_SERIES_UNVERIFIED", claim_id, "Evidence SHA invalid.")
                # Store read re-hashes actual bytes; a plausible SHA string is not evidence.
                self.store.artifacts.read(evidence)
            if obs[-1]["value"] != data["end_value"]:
                _fail("NUMERIC_SERIES_INVALID", claim_id, "Reviewed endpoint must equal authored endpoint.")
            snapshot = {"schema_version": "ApprovedNumericSeries.v1", "project_id": project_id,
                        "source_claim_id": claim_id, "series_id": data["series_id"],
                        "frozen_story_sha256": story_sha, "g1_approval_id": g1,
                        "unit": data["unit"], "precision": data["precision"],
                        "display_interpolation": "STEP_VERIFIED_VALUES_ONLY",
                        "authored_duration_frames": data["authored_duration_frames"],
                        "end_value": data["end_value"], "observations": obs,
                        "operator_reason": data["operator_reason"], "source_review_note": review[2]}
            payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            sha = hashlib.sha256(payload.encode()).hexdigest()
            approval_id = "numeric_" + uuid4().hex
            db.execute("INSERT INTO numeric_series_events VALUES(?,?,?,?,?,?,?)",
                       (approval_id, project_id, claim_id, data["series_id"], sha, payload, rev + 1))
            db.execute("""
                INSERT INTO numeric_series_heads VALUES(?,?,?,?)
                ON CONFLICT(project_id,claim_id,series_id) DO UPDATE
                SET approval_id=excluded.approval_id
            """, (project_id, claim_id, data["series_id"], approval_id))
            mark_stale(db, project_id, "numeric_series")
            db.execute("UPDATE projects SET revision=? WHERE project_id=?", (rev + 1, project_id))
            return {"approval_id": approval_id, "series_sha256": sha, "project_revision": rev + 1,
                    "source_provenance": "OPERATOR_REVIEWED_SOURCE_UNSPECIFIED"}
