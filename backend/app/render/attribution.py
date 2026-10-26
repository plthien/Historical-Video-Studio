"""Complete immutable credits for every source selected by approved G4."""
from __future__ import annotations

import json
from hashlib import sha256

from backend.app.contracts import ContractViolation
from backend.app.director import draft
from backend.app.director.fingerprint import canonical


def build(store, project: str, render_manifest: dict) -> tuple[dict, str]:
    timeline = draft.load(store, project)["timeline"]
    uses = {}
    for scene in timeline["scenes"]:
        for layer in scene["layers"]:
            for role, asset_id in (("source", layer.get("asset_id")),
                                   ("mask", layer.get("mask", {}).get("asset_id"))):
                if asset_id:
                    uses.setdefault(asset_id, []).append({"scene_id": scene["scene_id"],
                        "layer_id": layer["layer_id"], "role": role,
                        "crop_normalized": layer.get("crop_normalized"),
                        "source_asset_slot_id": layer.get("source_asset_slot_id")})
    used = sorted({value for scene in timeline["scenes"] for layer in scene["layers"]
                   for value in (layer.get("asset_id"), layer.get("mask", {}).get("asset_id")) if value})
    credits = []
    with store._connection() as db:
        for asset_id in used:
            row = db.execute(
                "SELECT e.requirement_id,e.candidate_id,e.original_sha256,e.evidence_json,c.metadata_json "
                "FROM asset_approval_events e JOIN asset_candidates c ON c.candidate_id=e.candidate_id "
                "WHERE e.project_id=? AND e.candidate_id=? ORDER BY e.rowid DESC LIMIT 1",
                (project, asset_id)).fetchone()
            if row:
                evidence, metadata = json.loads(row[3]), json.loads(row[4])
                if evidence.get("rights_status") != "ELIGIBLE" or not evidence.get("rights_evidence_note"):
                    raise ContractViolation("ATTRIBUTION_RIGHTS_BLOCKED", asset_id,
                                            "Every used original needs an explicit eligible rights decision.", blocking_gate="G5")
                ai = evidence.get("asset_class") == "AI_ILLUSTRATION"
                if ai and metadata.get("provider") != "glabs_webhook":
                    raise ContractViolation("ATTRIBUTION_AI_DISCLOSURE_MISSING", asset_id,
                                            "AI illustrations require explicit managed-source disclosure.", blocking_gate="G5")
                credits.append({"asset_id": asset_id, "kind": "original", "requirement_id": row[0],
                    "original_sha256": row[2], "title": metadata.get("title"),
                    "creator": metadata.get("creator"), "source_url": metadata.get("source_page_url"),
                    "license": metadata.get("license") or metadata.get("rights_statement"),
                    "rights_status": evidence["rights_status"],
                    "rights_evidence_note": evidence["rights_evidence_note"],
                    "historical_context_note": evidence.get("historical_context_note"),
                    "asset_class": evidence.get("asset_class"),
                    "ai_disclosure": "AI-generated illustration; explicitly approved at G3" if ai else None,
                    "uses": uses[asset_id], "approval_id": db.execute(
                        "SELECT approval_id FROM asset_approval_events WHERE project_id=? AND candidate_id=? "
                        "ORDER BY rowid DESC LIMIT 1", (project, asset_id)).fetchone()[0]})
                continue
            choice = db.execute(
                "SELECT e.requirement_id,e.slot_id,e.review_json,i.original_sha256,i.review_approval_id,c.metadata_json "
                "FROM asset_choice_set_items i JOIN asset_choice_set_events e ON e.set_id=i.set_id "
                "JOIN asset_choice_set_heads h ON h.set_id=e.set_id "
                "JOIN asset_candidates c ON c.candidate_id=i.candidate_id "
                "WHERE e.project_id=? AND i.candidate_id=? ORDER BY e.rowid DESC LIMIT 1",
                (project, asset_id)).fetchone()
            if choice:
                reviewed = next((item for item in json.loads(choice[2])
                                 if item["candidate_id"] == asset_id), None)
                evidence = reviewed.get("evidence", {}) if reviewed else {}
                metadata = json.loads(choice[5])
                if evidence.get("rights_status") != "ELIGIBLE" or not evidence.get("rights_evidence_note"):
                    raise ContractViolation("ATTRIBUTION_RIGHTS_BLOCKED", asset_id,
                                            "Reviewed G3 alternatives need eligible rights evidence.", blocking_gate="G5")
                ai = evidence.get("asset_class") == "AI_ILLUSTRATION"
                if ai and metadata.get("provider") != "glabs_webhook":
                    raise ContractViolation("ATTRIBUTION_AI_DISCLOSURE_MISSING", asset_id,
                                            "AI choices require managed-source disclosure.", blocking_gate="G5")
                credits.append({"asset_id": asset_id, "kind": "reviewed_choice", "requirement_id": choice[0],
                    "slot_id": choice[1], "original_sha256": choice[3], "title": metadata.get("title"),
                    "creator": metadata.get("creator"), "source_url": metadata.get("source_page_url"),
                    "license": metadata.get("license") or metadata.get("rights_statement"),
                    "rights_status": evidence["rights_status"],
                    "rights_evidence_note": evidence["rights_evidence_note"],
                    "historical_context_note": evidence.get("historical_context_note"),
                    "asset_class": evidence.get("asset_class"),
                    "ai_disclosure": "AI-generated illustration; explicitly approved at G3" if ai else None,
                    "uses": uses[asset_id], "approval_id": choice[4]})
                continue
            derivative = db.execute(
                "SELECT requirement_id,slot_id,parent_candidate_id,parent_original_sha256,derivative_sha256,"
                "review_id,source_crop_json FROM asset_mask_derivative_events "
                "WHERE project_id=? AND derivative_asset_id=? ORDER BY rowid DESC LIMIT 1",
                (project, asset_id)).fetchone()
            if not derivative:
                raise ContractViolation("ATTRIBUTION_SOURCE_MISSING", asset_id,
                                        "Resolve every used G4 asset to approved G3 evidence.", blocking_gate="G5")
            credits.append({"asset_id": asset_id, "kind": "reviewed_mask_derivative",
                "requirement_id": derivative[0], "slot_id": derivative[1],
                "parent_candidate_id": derivative[2], "parent_original_sha256": derivative[3],
                "original_sha256": derivative[4], "review_id": derivative[5],
                "source_crop": json.loads(derivative[6]), "uses": uses[asset_id]})
    if set(used) != {item["asset_id"] for item in credits}:
        raise ContractViolation("ATTRIBUTION_INCOMPLETE", project,
                                "Credits must cover every selected timeline asset.", blocking_gate="G5")
    document = {"schema_version": "AttributionManifest.v1", "project_id": project,
                "render_input_manifest_sha256": sha256(canonical(render_manifest)).hexdigest(),
                "g4_manifest_sha256": render_manifest["g4_manifest_sha256"], "assets": credits}
    return document, store.put_artifact(canonical(document), "attribution_manifest")
