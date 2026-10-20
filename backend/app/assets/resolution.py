"""A3-04: explicit missing-source choice, independently reviewed immutable G3 approvals."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from backend.app.assets.provenance import AssetCandidates
from backend.app.contracts import ContractViolation
from backend.app.projects.gates import GateService
from backend.app.projects.revisions import mark_stale


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class AssetResolution:
    def __init__(self, store):
        self.store = store
        self.assets = AssetCandidates(store)
        GateService(store)
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS asset_resolution_choices (
                    project_id TEXT NOT NULL, requirement_id TEXT NOT NULL,
                    requirement_sha256 TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('MANUAL_UPLOAD','MANAGED_FALLBACK')),
                    reason TEXT NOT NULL, operator_authorized INTEGER NOT NULL,
                    PRIMARY KEY(project_id,requirement_id));
                CREATE TABLE IF NOT EXISTS asset_approval_events (
                    approval_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL, requirement_sha256 TEXT NOT NULL,
                    candidate_id TEXT NOT NULL, candidate_sha256 TEXT NOT NULL,
                    original_sha256 TEXT NOT NULL, evidence_json TEXT NOT NULL,
                    approved_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS asset_approval_heads (
                    project_id TEXT NOT NULL, requirement_id TEXT NOT NULL,
                    approval_id TEXT NOT NULL REFERENCES asset_approval_events(approval_id),
                    PRIMARY KEY(project_id,requirement_id));
            """)

    @staticmethod
    def _revision(db, project, expected):
        row = db.execute("SELECT revision FROM projects WHERE project_id=?", (project,)).fetchone()
        if row is None:
            raise ContractViolation("PROJECT_NOT_FOUND", project, "Create this project first.")
        if row[0] != expected:
            raise ContractViolation("REVISION_CONFLICT", project, "Refresh and retry with the current revision.")
        return row[0]

    @staticmethod
    def _choice(db, project, requirement, sha):
        row = db.execute("SELECT mode,reason,operator_authorized FROM asset_resolution_choices "
                         "WHERE project_id=? AND requirement_id=? AND requirement_sha256=?",
                         (project, requirement, sha)).fetchone()
        return {"mode": row[0], "reason": row[1], "operator_authorized": bool(row[2])} if row else None

    @staticmethod
    def _head(db, project, requirement, sha):
        row = db.execute("SELECT e.approval_id,e.candidate_id,e.candidate_sha256,"
                         "e.original_sha256,e.evidence_json FROM asset_approval_heads h "
                         "JOIN asset_approval_events e ON e.approval_id=h.approval_id "
                         "WHERE h.project_id=? AND h.requirement_id=? AND e.requirement_sha256=?",
                         (project, requirement, sha)).fetchone()
        return ({"approval_record_id": row[0], "candidate_id": row[1],
                 "approved_candidate_sha256": row[2], "original_sha256": row[3],
                 "evidence": json.loads(row[4])} if row else None)

    def requirements(self, project):
        story = self.store.get_story(project).data()
        with self.store._connection() as db:
            result = []
            for requirement in story["asset_requirements"]:
                rid = requirement["requirement_id"]
                source = self.assets._source_tx(db, project, rid)
                choice = self._choice(db, project, rid, source["requirement_sha256"])
                head = self._head(db, project, rid, source["requirement_sha256"])
                versions = db.execute("SELECT metadata_json FROM asset_candidates WHERE project_id=? "
                                      "AND requirement_id=?",(project,rid)).fetchall()
                count = sum(1 for (raw,) in versions if
                            (meta:=json.loads(raw)).get("source_story_sha256")==source["story_sha256"]
                            and meta.get("source_requirement_sha256")==source["requirement_sha256"])
                status = ("APPROVED" if head else "MANAGED_FALLBACK_AUTHORIZED"
                          if choice and choice["mode"]=="MANAGED_FALLBACK" else "MANUAL_SELECTED"
                          if choice else "CANDIDATES_READY" if count else "ARCHIVE_ASSET_UNRESOLVED")
                result.append({"requirement": requirement, "requirement_id": rid,
                               "status": status, "resolution_mode": choice["mode"] if choice else "NONE",
                               "operator_authorized": bool(choice and choice["operator_authorized"]),
                               "candidate_count": count, "approved_asset_id": head["candidate_id"] if head else None,
                               "approved_candidate_sha256": head["approved_candidate_sha256"] if head else None,
                               "approval_record_id": head["approval_record_id"] if head else None})
            return {"project_revision": self.store.revision(project), "requirements": result}

    def candidates(self, project, requirement):
        self.assets._requirement(project, requirement)
        with self.store._connection() as db:
            rows = db.execute("SELECT candidate_id FROM asset_candidates WHERE project_id=? "
                              "AND requirement_id=? ORDER BY rowid DESC", (project,requirement)).fetchall()
            current = self.assets._source_tx(db,project,requirement)
            head = self._head(db,project,requirement,current["requirement_sha256"])
        items = []
        for (cid,) in rows:
            item = self.assets.get(project,cid)
            item["current_source"] = (item.get("source_story_sha256")==current["story_sha256"] and
                                      item.get("source_requirement_sha256")==current["requirement_sha256"])
            item["approved"] = bool(head and head["candidate_id"]==cid)
            # Do not expose inline image data or webhook key in source metadata.
            item.pop("raw_source", None)
            items.append(item)
        return {"project_revision": self.store.revision(project), "candidates": items}

    def choose(self, project, requirement, mode, reason, expected_revision):
        if mode not in ("MANUAL_UPLOAD","MANAGED_FALLBACK") or not isinstance(reason,str) or not reason.strip():
            raise ContractViolation("ASSET_RESOLUTION_INVALID", requirement,
                                    "Explicitly choose manual or managed and explain why.")
        with self.store._transaction() as db:
            revision = self._revision(db,project,expected_revision)
            source = self.assets._source_tx(db,project,requirement)
            old = self._choice(db,project,requirement,source["requirement_sha256"])
            if old and old["mode"]==mode and old["reason"]==reason:
                return {"project_revision": revision, "resolution_mode": mode, "operator_authorized": mode=="MANAGED_FALLBACK"}
            db.execute("INSERT INTO asset_resolution_choices VALUES(?,?,?,?,?,?) "
                       "ON CONFLICT(project_id,requirement_id) DO UPDATE SET "
                       "requirement_sha256=excluded.requirement_sha256,mode=excluded.mode,"
                       "reason=excluded.reason,operator_authorized=excluded.operator_authorized",
                       (project,requirement,source["requirement_sha256"],mode,reason,int(mode=="MANAGED_FALLBACK")))
            db.execute("DELETE FROM asset_approval_heads WHERE project_id=? AND requirement_id=?",
                       (project,requirement))
            mark_stale(db,project,"asset_replace")
            db.execute("UPDATE projects SET revision=? WHERE project_id=?",(revision+1,project))
            return {"project_revision": revision+1, "resolution_mode": mode,
                    "operator_authorized": mode=="MANAGED_FALLBACK"}

    def _review_tx(self, db, project, item):
        rid = item["requirement_id"]
        cid = item["candidate_id"]
        original_sha = item["original_sha256"]
        right = item["rights_status"]
        rights_note = item["rights_evidence_note"]
        context_note = item["historical_context_note"]
        if right!="ELIGIBLE" or not all(isinstance(x,str) and x.strip() for x in (rights_note,context_note)):
            raise ContractViolation("ASSET_REVIEW_REQUIRED",cid,
                                    "Record explicit eligible rights evidence and historical suitability.")
        source = self.assets._source_tx(db,project,rid)
        candidate = self.assets._owned_tx(db,project,rid,cid)
        if candidate.get("source_story_sha256")!=source["story_sha256"] or (
                candidate.get("source_requirement_sha256")!=source["requirement_sha256"]):
            raise ContractViolation("ASSET_SOURCE_STALE",cid,"Choose a candidate from the current source revision.")
        if candidate["original_sha256"]!=original_sha or not original_sha:
            raise ContractViolation("ASSET_ORIGINAL_SHA_MISMATCH",cid,
                                    "Review and approve the exact downloaded original bytes.")
        choice = self._choice(db,project,rid,source["requirement_sha256"])
        provider = candidate["provider"]
        if provider=="manual_upload" and (not choice or choice["mode"]!="MANUAL_UPLOAD"):
            raise ContractViolation("ASSET_RESOLUTION_REQUIRED",rid,"Select manual upload before approving.")
        if provider=="glabs_webhook" and (not choice or choice["mode"]!="MANAGED_FALLBACK" or
                                          not choice["operator_authorized"]):
            raise ContractViolation("ASSET_RESOLUTION_REQUIRED",rid,"Explicitly authorize managed fallback.")
        if provider=="glabs_webhook" and candidate.get("asset_class")!="AI_ILLUSTRATION":
            raise ContractViolation("ASSET_CLASS_INVALID",cid,"AI media cannot be presented as archival.")
        stored = db.execute("SELECT metadata_sha256 FROM asset_candidates WHERE candidate_id=?",
                            (cid,)).fetchone()[0]
        evidence = {"candidate_id":cid,"candidate_metadata_sha256":stored,
                    "original_sha256":original_sha,"rights_status":right,
                    "rights_evidence_note":rights_note,"historical_context_note":context_note,
                    "asset_class":candidate.get("asset_class","ARCHIVAL_PHOTO"),
                    "provider":provider}
        return source["requirement_sha256"],evidence

    def approve_batch(self, project, items, expected_revision):
        if not isinstance(items,list) or not items or len(items)>100:
            raise ContractViolation("ASSET_BATCH_INVALID",project,"Select 1–100 explicit candidate reviews.")
        required={"requirement_id","candidate_id","original_sha256","rights_status",
                  "rights_evidence_note","historical_context_note"}
        if any(not isinstance(item,dict) or not required.issubset(item) for item in items):
            raise ContractViolation("ASSET_BATCH_INVALID",project,"Incomplete candidate review.")
        if len({item["requirement_id"] for item in items})!=len(items):
            raise ContractViolation("ASSET_BATCH_INVALID",project,"Choose one candidate per requirement.")
        # Files are content-addressed and verified before the approval transaction.
        for item in items:
            self.store.get_artifact(item["original_sha256"])
        with self.store._transaction() as db:
            revision=self._revision(db,project,expected_revision)
            planned=[(item,*self._review_tx(db,project,item)) for item in items]
            created=[]
            for item,requirement_sha,evidence in planned:
                approved_sha=_digest(evidence)
                approval_id="approval_"+uuid4().hex
                db.execute("INSERT INTO asset_approval_events VALUES(?,?,?,?,?,?,?,?,?)",
                           (approval_id,project,item["requirement_id"],requirement_sha,
                            item["candidate_id"],approved_sha,item["original_sha256"],
                            json.dumps(evidence,sort_keys=True),datetime.now(timezone.utc).isoformat()))
                db.execute("INSERT INTO asset_approval_heads VALUES(?,?,?) "
                           "ON CONFLICT(project_id,requirement_id) DO UPDATE SET approval_id=excluded.approval_id",
                           (project,item["requirement_id"],approval_id))
                created.append({"requirement_id":item["requirement_id"],"approval_record_id":approval_id,
                                "approved_candidate_sha256":approved_sha})
            mark_stale(db,project,"asset_replace")
            db.execute("UPDATE projects SET revision=? WHERE project_id=?",(revision+1,project))
            return {"project_revision": revision+1, "approved":created}

    @staticmethod
    def gate_candidate(db, project, store):
        row=db.execute("SELECT story_json FROM story_candidates WHERE project_id=? ORDER BY revision DESC LIMIT 1",
                       (project,)).fetchone()
        if not row:
            return None
        requirements=json.loads(row[0])["asset_requirements"]
        if not requirements:
            # Valid empty requirements still require an explicit human G3 decision.
            # Bind to the exact StoryPackage, not an implicit approval by absence.
            manifest={"assets":[],"story_sha256":__import__("hashlib").sha256(row[0]).hexdigest()}
            return _digest(manifest),_digest({"empty_asset_review":manifest["story_sha256"]})
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='asset_approval_heads'").fetchone():
            return None
        pinned=[]
        for r in requirements:
            rid=r["requirement_id"]
            current=AssetCandidates._source_tx(db,project,rid)
            head=AssetResolution._head(db,project,rid,current["requirement_sha256"])
            if not head:
                return None
            # A replaced/corrupt immutable original cannot be approved as render input.
            store.get_artifact(head["original_sha256"])
            pinned.append({"requirement_id":rid,"requirement_sha256":current["requirement_sha256"],
                           "candidate_sha256":head["approved_candidate_sha256"],
                           "original_sha256":head["original_sha256"],
                           "review_approval_id":head["approval_record_id"]})
        manifest={"assets":sorted(pinned,key=lambda x:x["requirement_id"])}
        # A new human review event is a new G3 candidate even when the exact
        # original image and review text match an earlier approved version.
        # This makes STALE -> new review -> READY_FOR_REVIEW possible without
        # silently resurrecting a historical G3 approval (A -> B -> A).
        fingerprint=_digest({"review_lineage": [(x["requirement_id"],x["requirement_sha256"],
                                                x["review_approval_id"]) for x in manifest["assets"]]})
        return _digest(manifest),fingerprint
