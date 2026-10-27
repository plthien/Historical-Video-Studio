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
                CREATE TABLE IF NOT EXISTS asset_mask_derivative_events(
                    review_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, requirement_id TEXT NOT NULL,
                    slot_id TEXT NOT NULL, requirement_sha256 TEXT NOT NULL,
                    parent_candidate_id TEXT NOT NULL, parent_original_sha256 TEXT NOT NULL,
                    derivative_asset_id TEXT NOT NULL, derivative_sha256 TEXT NOT NULL,
                    width INTEGER NOT NULL, height INTEGER NOT NULL,
                    source_crop_json TEXT NOT NULL, review_reason TEXT NOT NULL,
                    committed_revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS asset_mask_derivative_heads(
                    project_id TEXT NOT NULL, requirement_id TEXT NOT NULL,
                    slot_id TEXT NOT NULL, parent_candidate_id TEXT NOT NULL,
                    review_id TEXT NOT NULL REFERENCES asset_mask_derivative_events(review_id),
                    PRIMARY KEY(project_id,requirement_id,slot_id,parent_candidate_id));
                CREATE TABLE IF NOT EXISTS asset_choice_set_events (
                    set_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL, slot_id TEXT NOT NULL,
                    requirement_sha256 TEXT NOT NULL, set_sha256 TEXT NOT NULL,
                    review_json TEXT NOT NULL, operator_reason TEXT NOT NULL,
                    committed_revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS asset_choice_set_heads (
                    project_id TEXT NOT NULL, requirement_id TEXT NOT NULL,
                    slot_id TEXT NOT NULL, set_id TEXT NOT NULL REFERENCES asset_choice_set_events(set_id),
                    PRIMARY KEY(project_id, requirement_id, slot_id));
                CREATE TABLE IF NOT EXISTS asset_choice_set_items (
                    review_approval_id TEXT PRIMARY KEY,
                    set_id TEXT NOT NULL REFERENCES asset_choice_set_events(set_id),
                    candidate_id TEXT NOT NULL, original_sha256 TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL,
                    UNIQUE(set_id,candidate_id));
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
            changed=False
            for item,requirement_sha,evidence in planned:
                previous=self._head(db,project,item["requirement_id"],requirement_sha)
                if previous and previous["candidate_id"]==item["candidate_id"] and previous["evidence"]==evidence:
                    created.append({"requirement_id":item["requirement_id"],
                                    "approval_record_id":previous["approval_record_id"],
                                    "approved_candidate_sha256":previous["approved_candidate_sha256"]})
                    continue
                changed=True
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
            if changed:
                mark_stale(db,project,"asset_replace")
                db.execute("UPDATE projects SET revision=? WHERE project_id=?",(revision+1,project))
            return {"project_revision": revision+int(changed), "approved":created}

    def validate_batch(self, project, items, expected_revision):
        """Validate every staged row without mutating approval heads.

        This is presentation support only. ``approve_batch`` remains the sole
        atomic commit and repeats all validation inside its transaction.
        """
        if not isinstance(items, list) or not items or len(items) > 100:
            raise ContractViolation("ASSET_BATCH_INVALID", project,
                                    "Select 1–100 explicit candidate reviews.")
        required = {"requirement_id", "candidate_id", "original_sha256", "rights_status",
                    "rights_evidence_note", "historical_context_note"}
        if any(not isinstance(item, dict) or not required.issubset(item) for item in items):
            raise ContractViolation("ASSET_BATCH_INVALID", project, "Incomplete candidate review.")
        if len({item["requirement_id"] for item in items}) != len(items):
            raise ContractViolation("ASSET_BATCH_INVALID", project, "Choose one candidate per requirement.")
        current_revision = self.store.revision(project)
        if current_revision != expected_revision:
            return {"project_revision": current_revision, "revision_matches": False,
                    "items": [{"requirement_id": item["requirement_id"],
                               "candidate_id": item["candidate_id"],
                               "original_sha256": item["original_sha256"],
                               "status": "BLOCKED", "error_code": "REVISION_CONFLICT",
                               "reason": "Project changed; refresh and validate the complete batch again."}
                              for item in items]}
        results = []
        with self.store._connection() as db:
            for item in items:
                try:
                    self.store.get_artifact(item["original_sha256"])
                    self._review_tx(db, project, item)
                    status, code = "VALID", None
                    reason = "Exact current original, source revision and rights review are valid."
                except ContractViolation as exc:
                    if exc.code in {"ASSET_SOURCE_STALE", "ASSET_ORIGINAL_SHA_MISMATCH"}:
                        status = "STALE"
                    elif exc.code in {"ASSET_RESOLUTION_REQUIRED", "ARTIFACT_NOT_FOUND",
                                      "ARTIFACT_SIZE_MISMATCH", "ARTIFACT_SHA_MISMATCH"}:
                        status = "BLOCKED"
                    else:
                        status = "INVALID"
                    code, reason = exc.code, exc.remediation
                results.append({"requirement_id": item["requirement_id"],
                                "candidate_id": item["candidate_id"],
                                "original_sha256": item["original_sha256"],
                                "status": status, "error_code": code, "reason": reason})
        return {"project_revision": current_revision, "revision_matches": True, "items": results}

    @staticmethod
    def _active_choice_sets(db, project, requirement, requirement_sha):
        """Immutable current pool, not historic asset_approval_events or old set history."""
        rows=db.execute("""SELECT e.set_id,e.slot_id,e.set_sha256,e.review_json,e.requirement_sha256
            FROM asset_choice_set_heads h JOIN asset_choice_set_events e ON e.set_id=h.set_id
            WHERE h.project_id=? AND h.requirement_id=? ORDER BY e.slot_id""",
            (project,requirement)).fetchall()
        results={}
        for set_id,slot,sha,raw,requirement_hash in rows:
            if requirement_hash!=requirement_sha:
                continue
            items=json.loads(raw)
            if _digest(items)!=sha:
                raise ContractViolation("G3_CHOICE_SET_CORRUPT",set_id,"Restore the immutable reviewed pool.")
            results[slot]={"set_id":set_id,"set_sha256":sha,"items":items}
        return results

    def review_choice_set(self, project, requirement, slot, reviews, reason, expected_revision):
        """Operator's choice-set review NEVER reapproves the separate G3 gate."""
        if len(reason.strip())<8 or not 2<=len(reviews)<=25 or len({x.get("candidate_id") for x in reviews})!=len(reviews):
            raise ContractViolation("G3_CHOICE_SET_INVALID",requirement,"Review at least two distinct candidates.")
        story=self.store.get_story(project).data()
        slots=[s for setup in story["visual_setups"]
               for s in setup["direction"]["asset_slots"]
               if s["slot_id"]==slot and s["requirement_id"]==requirement]
        if not slots:
            raise ContractViolation("G3_CHOICE_SLOT_INVALID",slot,"Select an authored G1 asset slot and its exact requirement.")
        for item in reviews:
            if item.get("requirement_id")!=requirement:
                raise ContractViolation("G3_CHOICE_SLOT_INVALID",requirement,"Choices must share one source requirement.")
            self.store.get_artifact(item["original_sha256"])
        with self.store._transaction() as db:
            rev=self._revision(db,project,expected_revision)
            source=self.assets._source_tx(db,project,requirement)
            head=self._head(db,project,requirement,source["requirement_sha256"])
            if not head:
                raise ContractViolation("G3_ASSET_UNAPPROVED",requirement,"Approve an eligible primary original first.")
            planned=[]
            for item in reviews:
                sha,evidence=self._review_tx(db,project,item)
                if sha!=source["requirement_sha256"]:
                    raise ContractViolation("G3_CHOICE_SOURCE_STALE",requirement,"Source requirement changed.")
                original=self.store.get_artifact(evidence["original_sha256"])
                if hashlib.sha256(original).hexdigest()!=evidence["original_sha256"]:
                    raise ContractViolation("G3_SOURCE_CORRUPT",item["candidate_id"],"Immutable bytes have changed.")
                planned.append({"candidate_id":item["candidate_id"],
                                "requirement_sha256":sha,
                                "source_story_sha256":source["story_sha256"],
                                "evidence":evidence,"original_sha256":evidence["original_sha256"],
                                "review_approval_id":"choice_review_"+uuid4().hex})
            if len({v["original_sha256"] for v in planned})!=len(planned) or head["candidate_id"] not in {v["candidate_id"] for v in planned}:
                raise ContractViolation("G3_CHOICE_SET_INVALID",requirement,"Include distinct originals and the current primary source.")
            payload=[{k:v for k,v in entry.items() if k!="review_approval_id"} for entry in planned]
            sha=_digest(payload)
            set_id="choice_"+uuid4().hex
            db.execute("INSERT INTO asset_choice_set_events VALUES(?,?,?,?,?,?,?,?,?)",
                       (set_id,project,requirement,slot,source["requirement_sha256"],sha,
                        json.dumps(payload,sort_keys=True),reason.strip(),rev+1))
            for item in planned:
                db.execute("INSERT INTO asset_choice_set_items VALUES(?,?,?,?,?)",
                           (item["review_approval_id"],set_id,item["candidate_id"],
                            item["original_sha256"],_digest(item["evidence"])))
            db.execute("""INSERT INTO asset_choice_set_heads VALUES(?,?,?,?)
                ON CONFLICT(project_id,requirement_id,slot_id) DO UPDATE SET set_id=excluded.set_id""",
                (project,requirement,slot,set_id))
            mark_stale(db,project,"g3_choice_set")
            db.execute("UPDATE projects SET revision=? WHERE project_id=?",(rev+1,project))
            return {"set_id":set_id,"set_sha256":sha,"project_revision":rev+1,
                    "g3_reapproval_required":True,
                    "items":[{"candidate_id":x["candidate_id"],
                              "review_approval_id":x["review_approval_id"],
                              "original_sha256":x["original_sha256"]} for x in planned]}

    def current_choice_set(self, project, requirement, slot):
        with self.store._connection() as db:
            source=self.assets._source_tx(db,project,requirement)
            selected=self._active_choice_sets(db,project,requirement,source["requirement_sha256"]).get(slot)
            if selected is None:
                return {"set_id":None,"items":[],"g3_current":False}
            g3=GateService.__new__(GateService)
            g3.store=self.store
            current=g3._status(db,project,"G3")[0]=="APPROVED"
            return {**selected,"g3_current":current}

    def approved_slot_options(self, project: str, requirement: str, slot: str):
        """Only fresh same-slot G3 pool items are usable by G4; source metadata is display-only."""
        with self.store._connection() as db:
            source=self.assets._source_tx(db,project,requirement)
            pools=self._active_choice_sets(db,project,requirement,source["requirement_sha256"])
            pool=pools.get(slot)
            gate=GateService.__new__(GateService)
            gate.store=self.store
            if not pool or gate._status(db,project,"G3")[0]!="APPROVED":
                return {"choice_set_id":None,"choice_set_sha256":None,"options":[]}
            primary=self._head(db,project,requirement,source["requirement_sha256"])
            if not primary:
                raise ContractViolation("G3_ASSET_UNAPPROVED",requirement,"Current approved primary is missing.")
            story=self.store.get_story(project).data()
            requirement_class=next(r["asset_class"] for r in story["asset_requirements"]
                                   if r["requirement_id"]==requirement)
            options=[]
            for item in pool["items"]:
                cand=self.assets._owned_tx(db,project,requirement,item["candidate_id"])
                evidence=item["evidence"]
                if (item["requirement_sha256"]!=source["requirement_sha256"] or
                    item["source_story_sha256"]!=source["story_sha256"] or
                    item["original_sha256"]!=cand["original_sha256"] or
                    cand["asset_class"]!=primary["evidence"]["asset_class"] or
                    evidence["rights_status"]!="ELIGIBLE" or
                    evidence["candidate_id"]!=cand["candidate_id"] or
                    not evidence["rights_evidence_note"] or not evidence["historical_context_note"]):
                    raise ContractViolation("G3_CHOICE_SOURCE_STALE",slot,"Reviewed original no longer matches current rights/requirement.")
                sha=item["original_sha256"]
                self.store.get_artifact(sha)
                rid=db.execute("""SELECT review_approval_id FROM asset_choice_set_items
                    WHERE set_id=? AND candidate_id=? AND original_sha256=? AND evidence_sha256=?""",
                    (pool["set_id"],cand["candidate_id"],sha,_digest(evidence))).fetchone()
                if not rid:
                    raise ContractViolation("G3_CHOICE_SET_CORRUPT",slot,"Missing immutable operator review record.")
                options.append({"candidate_id":cand["candidate_id"],
                                "original_sha256":sha,
                                "review_approval_id":rid[0],
                                "asset_class":requirement_class,
                                "source_candidate_class":cand["asset_class"],
                                "title":cand.get("title","Reviewed original"),
                                "source_provider":cand["provider"]})
            return {"requirement_id":requirement,"slot_id":slot,
                    "choice_set_id":pool["set_id"],"choice_set_sha256":pool["set_sha256"],
                    "options":options}

    @staticmethod
    def _active_mask_derivatives(db,project,requirement,requirement_sha):
        rows=db.execute("""SELECT e.review_id,e.slot_id,e.parent_candidate_id,e.parent_original_sha256,
                                 e.derivative_asset_id,e.derivative_sha256,e.width,e.height,
                                 e.source_crop_json,e.requirement_sha256
            FROM asset_mask_derivative_heads h JOIN asset_mask_derivative_events e ON e.review_id=h.review_id
            WHERE h.project_id=? AND h.requirement_id=? ORDER BY e.slot_id""",
            (project,requirement)).fetchall()
        return {slot+":"+parent:{"review_id":rid,"slot_id":slot,
                     "parent_candidate_id":parent,"parent_original_sha256":parent_sha,
                     "derivative_asset_id":derivative_id,"derivative_sha256":sha,
                     "width":w,"height":h,"source_crop":json.loads(crop)}
                for rid,slot,parent,parent_sha,derivative_id,sha,w,h,crop,req_sha in rows
                if req_sha==requirement_sha}

    def review_mask_derivative(self,project,requirement,slot,parent_id,parent_sha,
                               png,source_crop,review_reason,expected_revision):
        from backend.app.assets.alpha_mask import rgba_alpha_extent
        from backend.app.assets.download import inspect
        if len(review_reason.strip())<8 or source_crop!={"x":0,"y":0,"w":1,"h":1}:
            raise ContractViolation("MASK_DERIVATIVE_INVALID",slot,
                                    "Review full-source aligned alpha; arbitrary transforms need G3 re-review.")
        width,height=rgba_alpha_extent(png)
        story=self.store.get_story(project).data()
        authored=next((s for setup in story["visual_setups"] if setup["preferred_template"]=="T02"
                       for s in setup["direction"]["asset_slots"]
                       if s["slot_id"]==slot and s["requirement_id"]==requirement),None)
        if not authored:
            raise ContractViolation("MASK_DERIVATIVE_SLOT_INVALID",slot,"A current authored T02 portrait slot is required.")
        original=self.store.get_artifact(parent_sha)
        dimensions=inspect(original)
        if (dimensions["width"],dimensions["height"])!=(width,height):
            raise ContractViolation("MASK_DERIVATIVE_DIMENSION_MISMATCH",slot,
                                    "Mask pixels must correspond to exact parent original dimensions.")
        with self.store._transaction() as db:
            rev=self._revision(db,project,expected_revision)
            source=self.assets._source_tx(db,project,requirement)
            primary=self._head(db,project,requirement,source["requirement_sha256"])
            candidate=self.assets._owned_tx(db,project,requirement,parent_id)
            eligible=(primary is not None and
                      primary["candidate_id"]==parent_id and primary["original_sha256"]==parent_sha)
            pools=self._active_choice_sets(db,project,requirement,source["requirement_sha256"])
            if not eligible:
                eligible=any(x["candidate_id"]==parent_id and x["original_sha256"]==parent_sha
                             for p in pools.values() for x in p["items"])
            requirement_class=next(r["asset_class"] for r in story["asset_requirements"]
                                   if r["requirement_id"]==requirement)
            if (not eligible or candidate["original_sha256"]!=parent_sha or
                candidate["source_requirement_sha256"]!=source["requirement_sha256"] or
                requirement_class not in ("ARCHIVAL_PHOTO","HISTORICAL_ARTWORK") or
                candidate["provider"]=="glabs_webhook"):
                raise ContractViolation("MASK_DERIVATIVE_PARENT_UNAPPROVED",slot,
                                        "Choose current reviewed G3 original from exact portrait requirement.")
            sha,new=self.store.artifacts.put(png)
            try:
                rel=str(self.store.artifacts.path(sha).relative_to(self.store.artifacts.root)).replace("\\","/")
                db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?)",
                           (sha,len(png),"mask_derivative",rel))
                row=db.execute("SELECT byte_count,kind,relative_path FROM artifacts WHERE sha256=?",(sha,)).fetchone()
                if row!=(len(png),"mask_derivative",rel):
                    raise ContractViolation("MASK_DERIVATIVE_INVALID",slot,"Derivative cannot reuse an unrelated artifact.")
                rid="mask_review_"+uuid4().hex
                asset_id="mask_"+rid.split("_")[-1]
                db.execute("INSERT INTO asset_mask_derivative_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (rid,project,requirement,slot,source["requirement_sha256"],
                            parent_id,parent_sha,asset_id,sha,width,height,
                            json.dumps(source_crop,sort_keys=True),review_reason.strip(),rev+1))
                db.execute("""INSERT INTO asset_mask_derivative_heads VALUES(?,?,?,?,?)
                    ON CONFLICT(project_id,requirement_id,slot_id,parent_candidate_id)
                    DO UPDATE SET review_id=excluded.review_id""",
                    (project,requirement,slot,parent_id,rid))
                mark_stale(db,project,"g3_derivative")
                db.execute("UPDATE projects SET revision=? WHERE project_id=?",(rev+1,project))
            except BaseException:
                if new:self.store.artifacts.path(sha).unlink(missing_ok=True)
                raise
            return {"review_id":rid,"derivative_asset_id":asset_id,"derivative_sha256":sha,
                    "width":width,"height":height,"project_revision":rev+1,
                    "g3_reapproval_required":True}

    def reviewed_mask(self,project,requirement,slot,parent_id):
        with self.store._connection() as db:
            source=self.assets._source_tx(db,project,requirement)
            active=self._active_mask_derivatives(db,project,requirement,source["requirement_sha256"])
            item=active.get(slot+":"+parent_id)
            gate=GateService.__new__(GateService)
            gate.store=self.store
            if not item or gate._status(db,project,"G3")[0]!="APPROVED":
                return None
            candidate=self.assets._owned_tx(db,project,requirement,parent_id)
            primary=self._head(db,project,requirement,source["requirement_sha256"])
            pools=self._active_choice_sets(db,project,requirement,source["requirement_sha256"])
            eligible=(primary is not None and primary["candidate_id"]==parent_id and
                      primary["original_sha256"]==item["parent_original_sha256"])
            eligible=eligible or any(
                reviewed["candidate_id"]==parent_id and
                reviewed["original_sha256"]==item["parent_original_sha256"]
                for pool in pools.values() for reviewed in pool["items"] if pool["set_id"])
            if (not eligible or candidate["original_sha256"]!=item["parent_original_sha256"] or
                candidate["source_requirement_sha256"]!=source["requirement_sha256"]):
                raise ContractViolation("MASK_DERIVATIVE_PARENT_UNAPPROVED",slot,
                                        "Parent no longer belongs to the current G3-approved source pool.")
            self.store.get_artifact(item["parent_original_sha256"])
            original=self.store.get_artifact(item["derivative_sha256"])
            from backend.app.assets.alpha_mask import rgba_alpha_extent
            if rgba_alpha_extent(original)!=(item["width"],item["height"]):
                raise ContractViolation("MASK_DERIVATIVE_INVALID",slot,"Reviewed alpha bytes changed.")
            return {**item,"requirement_id":requirement}

    @staticmethod
    def gate_candidate(db, project, store):
        row=db.execute("SELECT sha256,story_json FROM story_candidates WHERE project_id=? ORDER BY revision DESC LIMIT 1",
                       (project,)).fetchone()
        if not row:
            return None
        if hashlib.sha256(row[1]).hexdigest()!=row[0]:
            raise ContractViolation("STORY_SHA_MISMATCH",project,"Immutable StoryPackage bytes changed.")
        requirements=json.loads(row[1])["asset_requirements"]
        if not requirements:
            # Valid empty requirements still require explicit G3 operator approval.
            # Bind to the already-verified immutable StoryPackage SHA.
            manifest={"assets":[],"story_sha256":row[0]}
            return _digest(manifest),_digest({"empty_asset_review":manifest["story_sha256"]})
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='asset_approval_heads'").fetchone():
            return None
        pinned=[]
        choices=[]
        derivatives=[]
        for r in requirements:
            rid=r["requirement_id"]
            current=AssetCandidates._source_tx(db,project,rid)
            head=AssetResolution._head(db,project,rid,current["requirement_sha256"])
            if not head:
                return None
            # A replaced/corrupt immutable original cannot be approved as render input.
            store.get_artifact(head["original_sha256"])
            pools=AssetResolution._active_choice_sets(db,project,rid,current["requirement_sha256"])
            for slot, pool in pools.items():
                for item in pool["items"]:
                    registered=AssetCandidates._owned_tx(db,project,rid,item["candidate_id"])
                    if (registered["original_sha256"]!=item["original_sha256"] or
                        registered["source_requirement_sha256"]!=current["requirement_sha256"]):
                        raise ContractViolation("G3_CHOICE_SOURCE_STALE",rid,"Choice set's reviewed source changed.")
                    store.get_artifact(item["original_sha256"])
                choices.append({"requirement_id":rid,"slot_id":slot,
                                "set_id":pool["set_id"],"set_sha256":pool["set_sha256"]})
            for derivative in AssetResolution._active_mask_derivatives(
                    db,project,rid,current["requirement_sha256"]).values():
                original=AssetCandidates._owned_tx(db,project,rid,derivative["parent_candidate_id"])
                if original["original_sha256"]!=derivative["parent_original_sha256"]:
                    raise ContractViolation("MASK_DERIVATIVE_PARENT_UNAPPROVED",rid,"Reviewed mask parent was replaced.")
                store.get_artifact(derivative["derivative_sha256"])
                derivatives.append({"requirement_id":rid,**derivative})
            pinned.append({"requirement_id":rid,"requirement_sha256":current["requirement_sha256"],
                           "candidate_sha256":head["approved_candidate_sha256"],
                           "original_sha256":head["original_sha256"],
                           "review_approval_id":head["approval_record_id"]})
        manifest={"assets":sorted(pinned,key=lambda x:x["requirement_id"])}
        if choices:
            manifest["choice_sets"]=sorted(choices,key=lambda x:(x["requirement_id"],x["slot_id"]))
        if derivatives:
            manifest["mask_derivatives"]=sorted(derivatives,key=lambda x:(x["requirement_id"],x["slot_id"],x["parent_candidate_id"]))
        # A new human review event is a new G3 candidate even when the exact
        # original image and review text match an earlier approved version.
        # This makes STALE -> new review -> READY_FOR_REVIEW possible without
        # silently resurrecting a historical G3 approval (A -> B -> A).
        lineage={"review_lineage": [(x["requirement_id"],x["requirement_sha256"],
                                                x["review_approval_id"]) for x in manifest["assets"]]}
        if choices:
            lineage["choice_sets"]=manifest["choice_sets"]
        if derivatives:
            lineage["mask_derivatives"]=manifest["mask_derivatives"]
        fingerprint=_digest(lineage)
        return _digest(manifest),fingerprint
