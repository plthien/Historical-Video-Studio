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
from backend.app.director.compiler import revise_g4
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


def blocked(code: str, subject: str, remedy: str):
    raise ContractViolation(code, subject, remedy)


def current(store, project: str):
    head = draft.load(store, project)
    if store.revision(project) != head["revision"]:
        blocked("G4_DRAFT_STALE", project, "Reload the current immutable G4 draft.")
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
           reason: str, crop: dict | None = None, layers: dict | None = None):
    head = current(store, project)
    if expected != head["revision"]:
        blocked("REVISION_CONFLICT", project, "Reload storyboard; project revision changed.")
    word_map, final_audio, approved = sources(store, project)
    return revise_g4(store, project, head["timeline"], original, edited,
                     word_map, final_audio, approved, expected_revision=expected,
                     operator_reason=reason, crop_overrides=crop,
                     layer_overrides=layers)


def mark(plan: dict, story_sha: str, reason: str, fields: list[str]):
    plan["direction_revision"] = {
        "kind": "operator_visual_edit",
        "source_story_revision_sha256": story_sha,
        "edited_paths": fields,
        "operator_confirmed": True,
        "edit_reason": reason,
    }


def mount(app, store, idempotent):
    @app.get("/api/v1/projects/{project_id}/storyboard/scenes")
    def scenes(project_id: str, offset: int = Query(default=0, ge=0),
               limit: int = Query(default=30, ge=1, le=100)):
        head = current(store, project_id)
        items = head["timeline"]["scenes"]
        return {"project_revision": head["revision"], "draft_manifest_sha256": head["manifest_sha256"],
                "status": "G4_DRAFT_NOT_OPERATOR_APPROVED",
                "total": len(items), "offset": offset, "limit": limit,
                "scenes": [{"scene_id": s["scene_id"], "setup_id": s["setup_id"],
                            "template_id": s["template_id"], "variant_id": s["variant_id"],
                            "start_frame": s["start_frame"], "duration_frames": s["duration_frames"],
                            "layers": s["layers"], "events": s["events"],
                            "diagnostics": []} for s in items[offset:offset+limit]]}

    @app.get("/api/v1/projects/{project_id}/storyboard/timeline")
    def timeline(project_id: str):
        head = current(store, project_id)
        return {"project_revision": head["revision"], "draft_manifest_sha256": head["manifest_sha256"],
                "status": "G4_DRAFT_NOT_OPERATOR_APPROVED", "timeline": head["timeline"]}

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
            if edits.motion_edits or edits.cue_word_ids:
                blocked("G4_EDIT_UNSUPPORTED", scene_id, "Motion/cue edits require authored staging; use direction-revisions without rewriting G2 words.")
            layer_patch = {}
            known = {layer["layer_id"]: layer for layer in previous["layers"]}
            for item in edits.layer_edits:
                actual = known.get(item.layer_id)
                if actual is None or item.layer_id in layer_patch:
                    blocked("G4_LAYOUT_INVALID", item.layer_id, "Choose an existing, unique frozen layer.")
                if item.approved_asset_id is not None and item.approved_asset_id != actual["asset_id"]:
                    blocked("G4_ASSET_SELECTION_FORBIDDEN", item.layer_id, "G4 cannot rebind to a different G3 original.")
                patch = {key: value for key, value in (
                    ("x", item.x_px), ("y", item.y_px), ("w", item.w_px), ("h", item.h_px))
                         if value is not None}
                if not patch:
                    blocked("G4_EDIT_INVALID", item.layer_id, "Choose an actual presentation coordinate change.")
                layer_patch[item.layer_id] = patch
            edited = copy.deepcopy(head["blueprint"])
            plan = next(p for p in edited["setup_plans"] if p["setup_id"] == previous["setup_id"])
            if edits.variant_id:
                if edits.variant_id not in ("A", "B", "C"):
                    blocked("LAYOUT_VARIANT_UNKNOWN", scene_id, "Select a registered variant.")
                plan["variant_id"] = edits.variant_id
                plan["layout_control"]["layout_id"] = f'{plan["template_id"]}.{edits.variant_id}.v1'
                plan["editorial_direction"]["layout_variant_hint"] = edits.variant_id
            mark(plan, head["timeline"]["story_sha256"],
                 f"Operator storyboard variant update: {scene_id}", ["layout_variant_hint"])
            return revise(store, project_id, body.expected_revision, head["blueprint"],
                          edited, f"Storyboard presentation edit: {scene_id}",
                          layers={previous["setup_id"]: layer_patch} if layer_patch else None)
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
                if item.focus_move not in ("none", "static"):
                    blocked("G4_EDIT_UNSUPPORTED", item.beat_id,
                            "Only frozen focus movement is currently authoritative.")
                beat["staging"] = [s.model_dump() for s in item.staging]
            mark(plan, head["timeline"]["story_sha256"], body.edit_reason, ["visual_beats"])
            return revise(store, project_id, body.expected_revision, head["blueprint"],
                          edited, body.edit_reason)
        return idempotent(project_id, "storyboard-direction:"+body.setup_id,
                          key, body.model_dump(), action)

    @app.get("/api/v1/projects/{project_id}/storyboard/preview")
    def preview(project_id: str):
        """Host is sole preview-input issuer; browser carries no transferable Node capability."""
        current(store, project_id)
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
        return {"status": "G4_DRAFT_VIEW_ONLY", "project_revision": store.revision(project_id),
                "draft_manifest_sha256": current(store, project_id)["manifest_sha256"],
                "props": data}
