"""B2-05: local G4 storyboard ingress. Immutable G1/G2/G3 heads are the authority.
The editor never becomes a gate approver or a Node-render capability issuer.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

from fastapi import Header, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.app.contracts import ContractViolation
from backend.app.director import draft
from backend.app.director.compiler import revise_g4, compile_from_store
from backend.app.director.blueprint import normalize_story
from backend.app.director.template_payloads import require_payload
from backend.app.contracts import validate_visual_blueprint
from backend.app.assets.provenance import AssetCandidates
from backend.app.assets.resolution import AssetResolution
from backend.app.director.fingerprint import digest

ROOT = Path(__file__).resolve().parents[3]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LayerEdit(Strict):
    layer_id: str = Field(min_length=3, max_length=64)
    x_px: int | None = None
    y_px: int | None = None
    w_px: int | None = Field(default=None, ge=1)
    h_px: int | None = Field(default=None, ge=1)
    approved_asset_id: str | None = None
    crop_normalized: dict[str, float] | None = None


class MotionEdit(Strict):
    event_id: str = Field(min_length=3, max_length=64)
    preset_id: str
    params: dict[str, str | float | int | bool] = Field(default_factory=dict)


class SceneChanges(Strict):
    template_id: str | None = None
    variant_id: str | None = None
    layer_edits: list[LayerEdit] = Field(default_factory=list)
    motion_edits: list[MotionEdit] = Field(default_factory=list)
    cue_word_ids: list[str] = Field(default_factory=list)


class StoryboardEdit(Strict):
    expected_revision: int = Field(ge=0)
    scene_id: str = Field(min_length=3, max_length=64)
    changes: SceneChanges


class StageAction(Strict):
    ref: str
    operation: str
    after_ref: str | None
    motion_hint: str
    priority: int = Field(ge=1, le=20)


class DirectionBeat(Strict):
    beat_id: str = Field(min_length=3)
    shot_goal: str = Field(min_length=1, max_length=350)
    focus_move: str
    staging: list[StageAction] = Field(min_length=1)


class VisualDirectionEdit(Strict):
    expected_revision: int = Field(ge=0)
    story_revision_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    setup_id: str = Field(min_length=3)
    edit_reason: str = Field(min_length=3, max_length=400)
    edits: list[DirectionBeat] = Field(min_length=1)


class AuthoredSetupPayload(Strict):
    expected_revision: int = Field(ge=0)
    story_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload: dict


class G4BuildInput(Strict):
    expected_revision: int = Field(ge=0)
    story_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReviewedMapRequest(Strict):
    expected_revision: int = Field(ge=0)
    story_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    year: int = Field(ge=-10000, le=3000)
    map_record: dict
    feature_ids: list[str]
    route_feature_id: str | None = None
    reviewed_tie_points: list[dict] | None = None


class G4CandidateInput(Strict):
    expected_revision: int = Field(ge=0)


def blocked(code: str, subject: str, remedy: str):
    raise ContractViolation(code, subject, remedy)


def current(store, project: str):
    head = draft.load(store, project)
    project_revision = store.revision(project)
    if project_revision != head["revision"]:
        from backend.app.projects.gates import GateService
        g4 = next(item for item in GateService(store).board(project) if item["gate_id"] == "G4")
        if not (project_revision > head["revision"] and g4["state"] in
                ("APPROVED", "CHANGES_REQUESTED", "REJECTED")):
            blocked("G4_DRAFT_STALE", project, "Reload the current immutable G4 draft.")
        head = {**head, "draft_revision": head["revision"], "revision": project_revision}
    if draft.current_gate_heads(store, project) != head["manifest"]["gate_heads"]:
        blocked("G4_SOURCE_STALE", project, "Current G1/G2/G3 approval differs from the draft.")
    return head


def sources(store, project: str):
    """Fetch actual approved snapshots, NOT browser-provided hashes."""
    story = store.get_story(project).data()
    with store._connection() as db:
        g2 = db.execute(
            "SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
            (project,)).fetchone()
        row = db.execute(
            "SELECT f.final_json,w.map_json FROM final_audio f JOIN word_maps w "
            "ON f.project_id=w.project_id AND f.approval_id=w.approval_id "
            "WHERE f.project_id=? AND f.approval_id=?",
            (project, g2[0] if g2 else None)).fetchone()
        if not row:
            blocked("WORD_MAP_STALE", project, "Current G2 final WAV and word map required.")
        final_audio, word_map = json.loads(row[0]), json.loads(row[1])
        approved = {}
        for req in story["asset_requirements"]:
            rid = req["requirement_id"]
            source = AssetCandidates._source_tx(db, project, rid)
            asset = AssetResolution._head(db, project, rid, source["requirement_sha256"])
            if not asset:
                if req["required"]:
                    blocked("G3_ASSET_UNAPPROVED", rid, "Approved immutable source required.")
                continue
            approved[rid] = {**asset, "asset_class": req["asset_class"],
                            "source_kind": asset.get("evidence", {}).get("source_kind", "")}
    return word_map, final_audio, approved


def revise(store, project: str, expected: int, original: dict, edited: dict,
           reason: str, crop: dict | None = None, layers: dict | None = None,
           motion: dict | None = None, selections: dict | None = None):
    head = current(store, project)
    if expected != head["revision"]:
        blocked("REVISION_CONFLICT", project, "Reload storyboard; project revision changed.")
    word_map, final_audio, approved = sources(store, project)
    return revise_g4(store, project, head["timeline"], original, edited,
                     word_map, final_audio, approved, expected_revision=expected,
                     operator_reason=reason, crop_overrides=crop,
                     layer_overrides=layers, motion_overrides=motion,
                     asset_selection_overrides=selections)


def mark(plan: dict, story_sha: str, reason: str, source_direction: dict):
    fields = sorted(key for key, value in source_direction.items()
                    if plan["editorial_direction"].get(key) != value)
    if not fields:
        blocked("G4_EDIT_INVALID", plan["setup_id"],
                "Choose an actual presentation-direction change.")
    plan["direction_revision"] = {
        "kind": "operator_visual_edit",
        "source_story_revision_sha256": story_sha,
        "edited_paths": fields,
        "operator_confirmed": True,
        "edit_reason": reason,
    }


def mount(app, store, idempotent):
    def ensure_authored_payload_table():
        with store._connection() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS g4_authored_setup_payloads (
                    project_id TEXT NOT NULL,
                    story_sha256 TEXT NOT NULL,
                    setup_id TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    registry_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (project_id,story_sha256,setup_id),
                    FOREIGN KEY (project_id) REFERENCES projects(project_id)
                )
            """)

    def prevent_reauthoring_current_compiled_story(db, project_id: str, story_sha: str):
        table=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                         "AND name='g4_compiled_drafts'").fetchone()
        if not table:
            return  # Initial G4 authoring has not created a compiled draft table.
        existing=db.execute("SELECT manifest_sha256 FROM g4_compiled_drafts "
                            "WHERE project_id=?", (project_id,)).fetchone()
        if not existing:
            return
        manifest=json.loads(store.get_artifact(existing[0]))
        if manifest["story_sha256"] != story_sha:
            return  # New immutable Story identity: fresh source-authoring lineage.
        # A separately re-approved G2/G3 source may legitimately need a new
        # historical map or setup payload, even when G1 Story text is unchanged.
        # Compare exact persisted approval heads INSIDE the current CAS transaction,
        # avoiding a second writer connection while BEGIN IMMEDIATE is held.
        rows=db.execute("SELECT gate_id,candidate_sha256,dependency_fingerprint,approval_id "
                        "FROM gate_heads WHERE project_id=? AND gate_id IN ('G1','G2','G3')",
                        (project_id,)).fetchall()
        stale=db.execute("SELECT gate_id FROM gate_staleness WHERE project_id=? "
                         "AND gate_id IN ('G1','G2','G3')",(project_id,)).fetchall()
        if len(rows) != 3 or stale:
            blocked("G4_SOURCE_STALE",project_id,
                    "Reapprove current G1/G2/G3 source heads before reauthoring a compiled storyboard.")
        current={gate:{"candidate_sha256":candidate,"dependency_fingerprint":fingerprint,
                       "approval_id":approval} for gate,candidate,fingerprint,approval in rows}
        if current != manifest["gate_heads"]:
            return  # Reapproved upstream source: draft.publish creates new G4 generation.
        blocked("G4_DRAFT_EXISTS", project_id,
                "The same approved G1/G2/G3 head already has a compiled G4 draft. "
                "Use bounded scene edits rather than resetting its authored source.")

    @app.get("/api/v1/projects/{project_id}/storyboard/blueprint-authoring")
    def read_blueprint_authoring(project_id: str):
        ensure_authored_payload_table()
        story_obj = store.get_story(project_id)
        story = story_obj.data()
        schema = json.loads((ROOT / "contracts/schema/VisualBlueprint.v1.schema.json").read_text(encoding="utf-8"))
        variants = schema["properties"]["setup_plans"]["items"]["properties"]["template_payload"]["oneOf"]
        by_template = {item["properties"]["template_id"]["const"]: item for item in variants}
        for setup in story["visual_setups"]:
            if setup.get("preferred_template") not in by_template:
                blocked("TEMPLATE_UNKNOWN", setup["setup_id"],
                        "Choose an explicit pinned T01–T10 template before authoring.")
        with store._connection() as db:
            saved = {row[0]: json.loads(row[1]) for row in db.execute(
                "SELECT setup_id,payload_json FROM g4_authored_setup_payloads "
                "WHERE project_id=? AND story_sha256=?", (project_id, story_obj.sha256))}
        setups = [{"setup_id": setup["setup_id"], "template_id": setup["preferred_template"],
                   "section_refs": setup["section_refs"], "claim_refs": setup["claim_refs"],
                   "requirement_refs": setup["requirement_refs"], "direction": setup["direction"],
                   "schema": by_template[setup["preferred_template"]],
                   "payload": saved.get(setup["setup_id"])}
                  for setup in story["visual_setups"]]
        return {"project_revision": store.revision(project_id),
                "story_sha256": story_obj.sha256, "registry_version": "VisualBlueprint.v1",
                "setups": setups, "ready": all(x["payload"] is not None for x in setups)}

    @app.put("/api/v1/projects/{project_id}/storyboard/blueprint-authoring/{setup_id}")
    def save_blueprint_payload(project_id: str, setup_id: str, body: AuthoredSetupPayload,
                               key: str = Header(alias="Idempotency-Key", min_length=12)):
        def apply():
            ensure_authored_payload_table()
            current_story = store.get_story(project_id)
            if current_story.sha256 != body.story_sha256:
                blocked("STORY_SHA_MISMATCH", project_id, "Reload Story and authoring fields after G1 changes.")
            setup = next((x for x in current_story.data()["visual_setups"]
                          if x["setup_id"] == setup_id), None)
            if setup is None:
                blocked("G4_SETUP_UNKNOWN", setup_id, "Select a setup from current StoryPackage.")
            checked = require_payload(setup, body.payload)
            from jsonschema import Draft202012Validator
            schema = json.loads((ROOT / "contracts/schema/VisualBlueprint.v1.schema.json").read_text(encoding="utf-8"))
            variants = schema["properties"]["setup_plans"]["items"]["properties"]["template_payload"]["oneOf"]
            variant = next(x for x in variants if x["properties"]["template_id"]["const"] == setup["preferred_template"])
            errors = list(Draft202012Validator(variant).iter_errors(checked))
            if errors:
                blocked("TEMPLATE_PAYLOAD_INVALID", setup_id, errors[0].message)
            with store._transaction() as db:
                row = db.execute("SELECT revision FROM projects WHERE project_id=?", (project_id,)).fetchone()
                if row is None or row[0] != body.expected_revision:
                    blocked("REVISION_CONFLICT", project_id, "Reload current project before saving typed G4 payload.")
                prevent_reauthoring_current_compiled_story(db, project_id, body.story_sha256)
                db.execute("INSERT INTO g4_authored_setup_payloads VALUES(?,?,?,?,?,?) "
                           "ON CONFLICT(project_id,story_sha256,setup_id) DO UPDATE SET "
                           "template_id=excluded.template_id,registry_version=excluded.registry_version,"
                           "payload_json=excluded.payload_json",
                           (project_id, body.story_sha256, setup_id, setup["preferred_template"],
                            "VisualBlueprint.v1", json.dumps(checked,sort_keys=True,ensure_ascii=False)))
                db.execute("UPDATE projects SET revision=revision+1 WHERE project_id=? AND revision=?",
                           (project_id,body.expected_revision))
            return {"project_revision": body.expected_revision+1,
                    "story_sha256": body.story_sha256, "setup_id": setup_id,
                    "status": "AUTHORED_NOT_COMPILED"}
        return idempotent(project_id, "g4-authored:"+setup_id, key, body.model_dump(), apply)

    @app.post("/api/v1/projects/{project_id}/storyboard/compile")
    def compile_initial_storyboard(project_id: str, body: G4BuildInput,
                                   key: str = Header(alias="Idempotency-Key", min_length=12)):
        def apply():
            ensure_authored_payload_table()
            current_story = store.get_story(project_id)
            if current_story.sha256 != body.story_sha256:
                blocked("STORY_SHA_MISMATCH", project_id, "Reload the current source StoryPackage.")
            if store.revision(project_id) != body.expected_revision:
                blocked("REVISION_CONFLICT", project_id, "Reload current project revision before compiling.")
            story = current_story.data()
            with store._connection() as db:
                saved = {row[0]: json.loads(row[1]) for row in db.execute(
                    "SELECT setup_id,payload_json FROM g4_authored_setup_payloads "
                    "WHERE project_id=? AND story_sha256=? AND registry_version='VisualBlueprint.v1'",
                    (project_id,body.story_sha256))}
            blueprint = normalize_story(story, saved, expected_story_sha256=body.story_sha256)
            validate_visual_blueprint(story, blueprint)
            # Never trust client-supplied WAV, word timing, rights, or GDI font identity.
            from backend.app.director.layout import windows_font_measure
            from pathlib import Path
            from backend.app.director import draft
            import hashlib
            from backend.app.projects.gates import GateService
            gate = {entry["gate_id"]: entry for entry in GateService(store).board(project_id)}
            if any(gate[g]["state"] != "APPROVED" for g in ("G1","G2","G3")):
                blocked("COMPILER_GATE_UNAPPROVED", project_id,
                        "Approve the current G1 Story, G2 Voice and G3 Asset gates first.")
            word_map, final_audio, _ = sources(store, project_id)
            font_file = Path(os.environ["WINDIR"]) / "Fonts" / os.getenv("HVS_G4_FONT_FILE", "arial.ttf")
            if not font_file.is_file():
                blocked("FONT_IDENTITY_STALE", project_id, "Configure a pinned native Windows font file.")
            font_hash = hashlib.sha256(font_file.read_bytes()).hexdigest()
            _, font_identity = windows_font_measure(str(font_file), font_hash)
            ensure_reviewed_maps()
            with store._connection() as db:
                map_requests={row[0]:json.loads(row[1]) for row in db.execute(
                    "SELECT requirement_id,map_request_json FROM g4_reviewed_map_requests "
                    "WHERE project_id=? AND story_sha256=?",(project_id,body.story_sha256))}
            compile_from_store(store,project_id,blueprint,word_map,final_audio,
                               maps=None,map_requests=map_requests,font_identity=font_identity)
            head = draft.load(store,project_id)
            return {"project_revision": store.revision(project_id),
                    "draft_manifest_sha256": head["manifest_sha256"],
                    "state": "COMPILED_AWAITING_G4_REVIEW"}
        return idempotent(project_id, "g4-initial-compile", key, body.model_dump(), apply)

    def ensure_reviewed_maps():
        with store._connection() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS g4_reviewed_map_requests(
                    project_id TEXT NOT NULL,story_sha256 TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,source_original_sha256 TEXT NOT NULL,
                    map_request_json TEXT NOT NULL,
                    PRIMARY KEY(project_id,story_sha256,requirement_id),
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                )""")

    @app.get("/api/v1/projects/{project_id}/storyboard/map-authoring")
    def map_authoring(project_id: str):
        ensure_reviewed_maps()
        candidate = store.get_story(project_id)
        story = candidate.data()
        requirements=[r for r in story["asset_requirements"]
                      if r["asset_class"]=="HISTORICAL_MAP"]
        from backend.app.projects.gates import GateService
        gate={g["gate_id"]:g["state"] for g in GateService(store).board(project_id)}
        approved={}
        with store._connection() as db:
            records={row[0]:json.loads(row[1]) for row in db.execute(
                "SELECT requirement_id,map_request_json FROM g4_reviewed_map_requests "
                "WHERE project_id=? AND story_sha256=?",
                (project_id,candidate.sha256))}
            if gate["G3"]=="APPROVED":
                for requirement in requirements:
                    rid=requirement["requirement_id"]
                    source=AssetCandidates._source_tx(db,project_id,rid)
                    head=AssetResolution._head(db,project_id,rid,source["requirement_sha256"])
                    if head:
                        approved[rid]={"source_asset_id":head["candidate_id"],
                                       "source_original_sha256":head["original_sha256"],
                                       "rights_review_record_id":head["approval_record_id"]}
        return {"project_revision":store.revision(project_id),
                "story_sha256":candidate.sha256,"g3_state":gate["G3"],
                "requirements":[{"requirement_id":r["requirement_id"],
                                 "start_year":r["start_year"],"end_year":r["end_year"],
                                 "map_reconstruction_policy":r["map_reconstruction_policy"],
                                 "approved_source":approved.get(r["requirement_id"]),
                                 "request":records.get(r["requirement_id"])}
                                for r in requirements]}

    @app.put("/api/v1/projects/{project_id}/storyboard/map-authoring/{requirement_id}")
    def save_map_authoring(project_id: str, requirement_id: str, body: ReviewedMapRequest,
                           key: str = Header(alias="Idempotency-Key", min_length=12)):
        def apply():
            ensure_reviewed_maps()
            current_story=store.get_story(project_id)
            if current_story.sha256!=body.story_sha256:
                blocked("STORY_SHA_MISMATCH",requirement_id,"Refresh source-bound G4 map request.")
            requirement=next((r for r in current_story.data()["asset_requirements"]
                              if r["requirement_id"]==requirement_id),None)
            if not requirement or requirement["asset_class"]!="HISTORICAL_MAP":
                blocked("MAP_REQUIREMENT_UNKNOWN",requirement_id,"Choose current G1 historical map requirement.")
            if not requirement["start_year"]<=body.year<=requirement["end_year"]:
                blocked("MAP_PERIOD_MISMATCH",requirement_id,"Selected period year must match the approved G1 requirement.")
            # Verify exact historical map bytes, current G3 source/rights event, map
            # feature IDs, route type, tie points and period using the unchanged
            # authoritative ingest owner rather than trusting browser geometry.
            from backend.app.maps.ingest import ingest_current_approved
            ingest_current_approved(store,project_id,requirement_id,body.map_record,
                                    year=body.year,feature_ids=body.feature_ids,
                                    route_feature_id=body.route_feature_id,
                                    reviewed_tie_points=body.reviewed_tie_points)
            record=body.model_dump(exclude={"expected_revision","story_sha256"})
            with store._transaction() as db:
                rev=db.execute("SELECT revision FROM projects WHERE project_id=?",
                               (project_id,)).fetchone()
                if not rev or rev[0]!=body.expected_revision:
                    blocked("REVISION_CONFLICT",project_id,"Refresh G4 map authoring before saving.")
                prevent_reauthoring_current_compiled_story(db,project_id,body.story_sha256)
                db.execute("INSERT INTO g4_reviewed_map_requests VALUES(?,?,?,?,?) "
                           "ON CONFLICT(project_id,story_sha256,requirement_id) DO UPDATE SET "
                           "source_original_sha256=excluded.source_original_sha256,"
                           "map_request_json=excluded.map_request_json",
                           (project_id,current_story.sha256,requirement_id,
                            body.map_record["source_original_sha256"],
                            json.dumps(record,ensure_ascii=False,sort_keys=True)))
                db.execute("UPDATE projects SET revision=revision+1 WHERE project_id=? AND revision=?",
                           (project_id,body.expected_revision))
            return {"project_revision":body.expected_revision+1,"requirement_id":requirement_id,
                    "source_original_sha256":body.map_record["source_original_sha256"],
                    "state":"REVIEWED_MAP_REQUEST_NOT_G4_APPROVED"}
        return idempotent(project_id,"g4-map:"+requirement_id,key,body.model_dump(),apply)

    @app.post("/api/v1/projects/{project_id}/storyboard/candidate")
    def prepare_candidate(project_id: str, body: G4CandidateInput,
                          key: str = Header(alias="Idempotency-Key", min_length=12)):
        return idempotent(project_id, "storyboard-g4-candidate", key, body.model_dump(),
                          lambda: draft.prepare_review_candidate(
                              store, project_id, body.expected_revision))

    @app.get("/api/v1/projects/{project_id}/storyboard/scenes")
    def scenes(project_id: str, offset: int = Query(default=0, ge=0),
               limit: int = Query(default=30, ge=1, le=100)):
        head = current(store, project_id)
        from backend.app.projects.gates import GateService
        g4 = next(item for item in GateService(store).board(project_id) if item["gate_id"] == "G4")
        items = head["timeline"]["scenes"]
        authored_plans = {p["setup_id"]: p for p in head["blueprint"]["setup_plans"]}
        return {"project_revision": head["revision"], "draft_manifest_sha256": head["manifest_sha256"],
                "story_revision_sha256": head["blueprint"]["story_revision_sha256"],
                "status": "G4_DRAFT_NOT_OPERATOR_APPROVED", "g4_gate": g4,
                "total": len(items), "offset": offset, "limit": limit,
                "scenes": [{"scene_id": s["scene_id"], "setup_id": s["setup_id"],
                            "template_id": s["template_id"], "variant_id": s["variant_id"],
                            "start_frame": s["start_frame"], "duration_frames": s["duration_frames"],
                            "layers": s["layers"], "events": s["events"],
                            "direction_beats": [{"beat_id": b["beat_id"], "shot_goal": b["shot_goal"],
                                                 "focus_move": b["focus_move"], "staging": b["staging"]}
                                                for b in authored_plans[s["setup_id"]]["editorial_direction"]["visual_beats"]],
                            "diagnostics": []} for s in items[offset:offset+limit]]}

    @app.get("/api/v1/projects/{project_id}/storyboard/timeline")
    def timeline(project_id: str):
        head = current(store, project_id)
        from backend.app.projects.gates import GateService
        g4 = next(item for item in GateService(store).board(project_id) if item["gate_id"] == "G4")
        return {"project_revision": head["revision"], "draft_manifest_sha256": head["manifest_sha256"],
                "status": "G4_DRAFT_NOT_OPERATOR_APPROVED", "g4_gate": g4, "timeline": head["timeline"]}

    @app.get("/api/v1/projects/{project_id}/storyboard/scenes/{scene_id}/asset-options/{layer_id}")
    def asset_options(project_id: str, scene_id: str, layer_id: str):
        head=current(store,project_id)
        scene=next((s for s in head["timeline"]["scenes"] if s["scene_id"]==scene_id),None)
        layer=next((l for l in scene["layers"] if l["layer_id"]==layer_id),None) if scene else None
        if not layer or not layer["source_asset_slot_id"] or not layer["asset_id"]:
            blocked("G4_ASSET_SELECTION_FORBIDDEN",layer_id,"Only frozen source asset layers have G3 options.")
        plan=next(p for p in head["blueprint"]["setup_plans"] if p["setup_id"]==scene["setup_id"])
        authored=next((s for s in plan["editorial_direction"]["asset_slots"]
                       if s["slot_id"]==layer["source_asset_slot_id"]),None)
        if not authored:
            blocked("G4_ASSET_SELECTION_FORBIDDEN",layer_id,"Frozen authored slot is missing.")
        resolver=AssetResolution(store)
        eligible=resolver.approved_slot_options(project_id,authored["requirement_id"],
                                                 layer["source_asset_slot_id"])
        return {"project_revision":head["revision"],"draft_manifest_sha256":head["manifest_sha256"],
                "scene_id":scene_id,"layer_id":layer_id,"selected_candidate_id":layer["asset_id"],
                **eligible}

    @app.patch("/api/v1/projects/{project_id}/storyboard/scenes/{scene_id}")
    def patch_scene(project_id: str, scene_id: str, body: StoryboardEdit,
                    key: str = Header(alias="Idempotency-Key", min_length=12)):
        if body.scene_id != scene_id:
            blocked("G4_SCENE_MISMATCH", scene_id, "Body and URL scene must match.")
        def action():
            head = current(store, project_id)
            if body.expected_revision != head["revision"]:
                blocked("REVISION_CONFLICT", project_id, "Reload and retry against current revision.")
            previous = next((s for s in head["timeline"]["scenes"] if s["scene_id"] == scene_id), None)
            if previous is None:
                blocked("G4_SCENE_UNKNOWN", scene_id, "Select an existing compiled scene.")
            edits = body.changes
            if edits.template_id and edits.template_id != previous["template_id"]:
                blocked("G4_SOURCE_EDIT_FORBIDDEN", scene_id, "Template choice is frozen by G1.")
            if edits.cue_word_ids:
                blocked("G4_EDIT_UNSUPPORTED", scene_id, "G2 cue identities are frozen and cannot be edited at G4.")
            layer_patch = {}
            crop_patch = {}
            selection_patch = {}
            known = {layer["layer_id"]: layer for layer in previous["layers"]}
            for item in edits.layer_edits:
                actual = known.get(item.layer_id)
                if actual is None or item.layer_id in layer_patch:
                    blocked("G4_LAYOUT_INVALID", item.layer_id, "Choose an existing, unique frozen layer.")
                if item.approved_asset_id is not None and item.approved_asset_id != actual["asset_id"]:
                    if not actual["source_asset_slot_id"] or not actual["asset_id"] or actual["layer_kind"] in ("map","territory"):
                        blocked("G4_ASSET_SELECTION_FORBIDDEN",item.layer_id,
                                "Historical maps require separate source geometry re-review; no blind asset replacement.")
                    plan=next(p for p in head["blueprint"]["setup_plans"] if p["setup_id"]==previous["setup_id"])
                    authored=next((s for s in plan["editorial_direction"]["asset_slots"]
                                   if s["slot_id"]==actual["source_asset_slot_id"]),None)
                    if not authored:
                        blocked("G4_ASSET_SELECTION_FORBIDDEN",item.layer_id,"Frozen source slot absent.")
                    eligible=AssetResolution(store).approved_slot_options(
                        project_id,authored["requirement_id"],actual["source_asset_slot_id"])
                    option=next((o for o in eligible["options"]
                                 if o["candidate_id"]==item.approved_asset_id),None)
                    if not option or not eligible["choice_set_sha256"]:
                        blocked("G4_ASSET_SELECTION_FORBIDDEN",item.layer_id,
                                "Choose only a currently G3-approved same-slot source.")
                    selection_patch[item.layer_id]={
                        "requirement_id":authored["requirement_id"],
                        "slot_id":actual["source_asset_slot_id"],
                        "candidate_id":option["candidate_id"],
                        "choice_set_id":eligible["choice_set_id"],
                        "choice_set_sha256":eligible["choice_set_sha256"],
                        "review_approval_id":option["review_approval_id"],
                        "original_sha256":option["original_sha256"]}
                if item.crop_normalized is not None:
                    if item.layer_id in crop_patch:
                        blocked("G4_CROP_INVALID", item.layer_id, "Choose one crop per frozen layer.")
                    crop_patch[item.layer_id] = item.crop_normalized
                patch = {key: value for key, value in (
                    ("x", item.x_px), ("y", item.y_px), ("w", item.w_px), ("h", item.h_px))
                         if value is not None}
                if not patch and item.crop_normalized is None and item.layer_id not in selection_patch:
                    blocked("G4_EDIT_INVALID", item.layer_id, "Choose an actual presentation coordinate change.")
                if patch:
                    layer_patch[item.layer_id] = patch
            motion_patch = {}
            events = {event["event_id"]: event for event in previous["events"]}
            for item in edits.motion_edits:
                event = events.get(item.event_id)
                if not event or item.event_id in motion_patch:
                    blocked("G4_MOTION_INVALID", item.event_id, "Select one existing authored event.")
                if item.preset_id != event["preset_id"]:
                    blocked("G4_MOTION_FORBIDDEN", item.event_id, "G4 cannot replace the authored preset.")
                motion_patch[item.event_id] = item.params
            edited = copy.deepcopy(head["blueprint"])
            plan = next(p for p in edited["setup_plans"] if p["setup_id"] == previous["setup_id"])
            if edits.variant_id:
                if edits.variant_id not in ("A", "B", "C"):
                    blocked("LAYOUT_VARIANT_UNKNOWN", scene_id, "Select a registered variant.")
                plan["variant_id"] = edits.variant_id
                plan["layout_control"]["layout_id"] = f'{plan["template_id"]}.{edits.variant_id}.v1'
                plan["editorial_direction"]["layout_variant_hint"] = edits.variant_id
                story = store.get_story(project_id).data()
                source = next(item["direction"] for item in story["visual_setups"]
                              if item["setup_id"] == previous["setup_id"])
                mark(plan, head["timeline"]["story_sha256"],
                     f"Operator storyboard variant update: {scene_id}", source)
            return revise(store, project_id, body.expected_revision, head["blueprint"],
                          edited, f"Storyboard presentation edit: {scene_id}",
                          layers={previous["setup_id"]: layer_patch} if layer_patch else None,
                          crop={previous["setup_id"]: crop_patch} if crop_patch else None,
                          motion={previous["setup_id"]: motion_patch} if motion_patch else None,
                          selections={previous["setup_id"]:selection_patch} if selection_patch else None)
        return idempotent(project_id, "storyboard-scene:"+scene_id, key, body.model_dump(), action)

    @app.post("/api/v1/projects/{project_id}/storyboard/direction-revisions")
    def direction_revisions(project_id: str, body: VisualDirectionEdit,
                            key: str = Header(alias="Idempotency-Key", min_length=12)):
        def action():
            head = current(store, project_id)
            if body.expected_revision != head["revision"]:
                blocked("REVISION_CONFLICT", project_id, "Reload current G4 draft revision.")
            if body.story_revision_sha256 != head["timeline"]["story_sha256"]:
                blocked("STORY_SHA_MISMATCH", project_id, "G1 story identity changed.")
            edited = copy.deepcopy(head["blueprint"])
            plan = next((p for p in edited["setup_plans"] if p["setup_id"] == body.setup_id), None)
            if not plan:
                blocked("G4_SCENE_UNKNOWN", body.setup_id, "Unknown frozen setup.")
            authored = {b["beat_id"]: b for b in plan["editorial_direction"]["visual_beats"]}
            seen = set()
            for item in body.edits:
                if item.beat_id not in authored or item.beat_id in seen:
                    blocked("G4_CUE_INVALID", item.beat_id, "Existing distinct G1 visual beat required.")
                seen.add(item.beat_id)
                beat = authored[item.beat_id]
                if item.shot_goal != beat["shot_goal"]:
                    blocked("G4_SOURCE_EDIT_FORBIDDEN", item.beat_id,
                            "Changing authored shot goal requires a source-authorized plan revision.")
                if item.focus_move not in ("none", "subject_to_subject", "detail_to_overview",
                                           "overview_to_detail", "follow_path", "static"):
                    blocked("G4_EDIT_UNSUPPORTED", item.beat_id,
                            "Choose a focus movement authorized by VisualDirectionEdit.")
                beat["focus_move"] = item.focus_move
                beat["staging"] = [s.model_dump() for s in item.staging]
            story = store.get_story(project_id).data()
            source = next(item["direction"] for item in story["visual_setups"]
                          if item["setup_id"] == body.setup_id)
            mark(plan, head["timeline"]["story_sha256"], body.edit_reason, source)
            return revise(store, project_id, body.expected_revision, head["blueprint"],
                          edited, body.edit_reason)
        return idempotent(project_id, "storyboard-direction:"+body.setup_id,
                          key, body.model_dump(), action)

    @app.get("/api/v1/projects/{project_id}/storyboard/preview")
    def preview(project_id: str):
        """Host is sole preview-input issuer; browser carries no transferable Node capability."""
        def verified_preview_head():
            try:
                return current(store, project_id)
            except ContractViolation as exc:
                if exc.code in ("ARTIFACT_MISSING", "ARTIFACT_CORRUPT",
                                "ARTIFACT_SIZE_MISMATCH"):
                    blocked("PLAYER_PREVIEW_UNAVAILABLE", project_id,
                            "Current approved original bytes are missing or corrupt; restore immutable media before preview.")
                raise
        baseline = verified_preview_head()
        exe = ROOT / "renderer" / "node_modules" / ".bin" / "tsx.cmd"
        if os.name != "nt" or not exe.is_file():
            blocked("PLAYER_HOST_REQUIRED", project_id, "Install the pinned renderer on native Windows.")
        script = ROOT / "renderer" / "scripts" / "preview-host.ts"
        try:
            proc = subprocess.run([str(exe), str(script), str(store.database),
                                   str(store.artifacts.root), project_id],
                                  cwd=str(ROOT), capture_output=True, text=True,
                                  timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired):
            blocked("PLAYER_PREVIEW_UNAVAILABLE", project_id, "Local Windows preview resolver failed.")
        if proc.returncode != 0:
            blocked("PLAYER_PREVIEW_UNAVAILABLE", project_id,
                    "Current approved local sources or font are unavailable.")
        try:
            data = json.loads(proc.stdout)
        except (ValueError, TypeError):
            blocked("PLAYER_PREVIEW_INVALID", project_id, "Verified host did not return canonical JSON.")
        verified = verified_preview_head()
        if (verified["revision"] != baseline["revision"] or
                verified["manifest_sha256"] != baseline["manifest_sha256"] or
                data.get("media", {}).get("authorizingG4ManifestSha256") != baseline["manifest_sha256"]):
            blocked("G4_DRAFT_STALE", project_id, "A new G4 generation appeared while preview inputs were verified.")
        return {"status": "G4_DRAFT_VIEW_ONLY", "project_revision": baseline["revision"],
                "draft_manifest_sha256": baseline["manifest_sha256"],
                "props": data}
