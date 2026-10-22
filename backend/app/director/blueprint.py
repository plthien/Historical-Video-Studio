"""B1-01: SHA-bound VisualBlueprint from G1 story plus explicitly authored payloads."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from backend.app.contracts import ContractViolation, validate_visual_blueprint
from backend.app.projects.models import StoryCandidate
from backend.app.director.template_payloads import require_payload

ROOT = Path(__file__).resolve().parents[3]
LAYOUTS = ROOT / "contracts/registries/layouts.v1.json"

def normalize_story(story: dict, payloads_by_setup: dict,
                    expected_story_sha256: str | None = None,
                    selected_variants: dict | None = None) -> dict:
    """No hidden template inference: caller supplies factual per-template content.

    The StoryPackage does not encode full card/quote/map-specific payload fields.
    Draft source-slot bindings stay None until a separate G3 decision.
    """
    candidate = StoryCandidate.parse(story)
    if expected_story_sha256 is not None and candidate.sha256 != expected_story_sha256:
        raise ContractViolation("STORY_SHA_MISMATCH", candidate.project_id,
                                "Reload the frozen G1 StoryPackage before normalizing its visual plan.")
    layouts = json.loads(LAYOUTS.read_text(encoding="utf-8"))["layouts"]
    idx = {(x["template_id"], x["variant_id"]): x for x in layouts}
    if len(idx) != 30:
        raise ContractViolation("REGISTRY_INCOMPLETE", "layouts", "Restore the pinned 30-layout registry.")
    ids = {x["setup_id"] for x in story["visual_setups"]}
    if not isinstance(payloads_by_setup, dict) or set(payloads_by_setup) != ids:
        raise ContractViolation("TEMPLATE_PAYLOAD_MISSING", candidate.project_id,
                                "Provide one explicit authored T01–T10 payload for every G1 visual setup.")
    plans = []
    for setup in story["visual_setups"]:
        sid = setup["setup_id"]
        d = copy.deepcopy(setup["direction"])
        tid = setup.get("preferred_template")
        hint = (selected_variants or {}).get(sid, d["layout_variant_hint"])
        variant = "A" if hint == "AUTO" else hint
        layout = idx.get((tid, variant))
        if layout is None:
            raise ContractViolation("LAYOUT_VARIANT_UNKNOWN", sid,
                                    "Choose a pinned A/B/C variant of this exact template.")
        payload = copy.deepcopy(require_payload(setup, payloads_by_setup[sid]))
        slots = d["asset_slots"]
        plan = {
            "setup_id": sid, "template_id": tid, "variant_id": variant,
            "section_refs": list(setup["section_refs"]),
            "claim_refs": list(setup["claim_refs"]),
            "requirement_refs": list(setup["requirement_refs"]),
            "layer_roles": [slot["role"] for slot in layout["slots"] if slot["required"]
                            and slot["role"] not in {"annotation"}],
            "editorial_direction": d,
            "asset_slot_bindings": [{"slot_id": s["slot_id"], "requirement_id": s["requirement_id"],
                                      "approved_asset_id": None, "selection_reason": "G3 approval required"}
                                     for s in slots],
            "layout_control": {
                "layout_id": f"{tid}.{variant}.v1",
                "safe_area_pct": {key: layout["safe_area_px"][key]/(
                    layout["canvas"]["width"] if key in ("left", "right") else layout["canvas"]["height"])
                    for key in ("left","top","right","bottom")},
                "text_density": "balanced", "focal_point": [0.5, 0.5]
            },
            "template_payload": payload,
            "direction_revision": {
                "kind": "inherited", "source_story_revision_sha256": candidate.sha256,
                "edited_paths": [], "operator_confirmed": False, "edit_reason": None
            }
        }
        plans.append(plan)
    result = {"schema_version": "VisualBlueprint.v1",
              "project_id": candidate.project_id,
              "story_revision_sha256": candidate.sha256,
              "setup_plans": plans}
    validate_visual_blueprint(story, result)
    return result
