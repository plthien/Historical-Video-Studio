"""Controlled B1 production-compiler origin for B2 synthetic A/B/C frame fixtures.

Actual registry/layout/font compilation, but NOT real historic G3 rights or G4 approval.
Windows-native only. Synthetic output stays in renderer/.artifacts.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
from backend.tools.b1_smoke import synthetic_ten_template_inputs
from backend.app.director.compiler import compile_timeline
from backend.app.director.blueprint import normalize_story
from backend.app.director.layout import windows_font_measure
from backend.app.director.fingerprint import canonical

ROOT = Path(__file__).resolve().parents[2]
outdir=ROOT / "renderer" / ".artifacts"
outdir.mkdir(parents=True,exist_ok=True)
font=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
measure, identity=windows_font_measure(str(font),hashlib.sha256(font.read_bytes()).hexdigest())
story, bp, words, final, assets, maps=synthetic_ten_template_inputs()
registry=json.loads((ROOT/"contracts/registries/layouts.v1.json").read_text())["layouts"]
payloads={p["setup_id"]:p["template_payload"] for p in bp["setup_plans"]}
compiled={}
for variant in ("A","B","C"):
    authored=copy.deepcopy(story)
    for setup in authored["visual_setups"]:
        layout=next(l for l in registry if l["template_id"]==setup["preferred_template"]
                    and l["variant_id"]==variant)
        available={x["slot_id"] for x in setup["direction"]["asset_slots"]
                   if x["semantic_role"] in {slot["slot_id"] for slot in layout["slots"]}}
        available.update(text["text_id"] for text in setup["direction"]["on_screen_text"]
                   if text["text_id"].split("_",2)[-1] in {slot["slot_id"] for slot in layout["slots"]})
        if not available:
            raise RuntimeError(f"No frozen authored source refs for {setup['setup_id']} {variant}")
        preferred=next((ref for ref in available if ref.endswith(("map_main","map_backdrop","map_before","portrait_main","entity_a"))),sorted(available)[0])
        for beat in setup["direction"]["visual_beats"]:
            if beat["focus_ref"] not in available:
                prior=beat["focus_ref"]
                beat["focus_ref"]=preferred
                for staged in beat["staging"]:
                    if staged["ref"]==prior:
                        staged["ref"]=preferred
                # Only synthetic editorial layout selection, no G1 claims,
                # media sources, narration word alignment or quotes changed.
        # Variant-safe authored dependency ordering: a remapped focus must
        # not depend on itself or reference a slot absent in selected layout.
        # Remap synthetic staging refs only; never rewrite approved G1 data.
        previous_ref=None
        for beat in setup["direction"]["visual_beats"]:
            for staged in beat["staging"]:
                if staged["ref"] not in available:
                    staged["ref"]=beat["focus_ref"]
                dep=staged.get("after_ref")
                if dep not in available or dep==staged["ref"]:
                    staged["after_ref"]=previous_ref if previous_ref!=staged["ref"] else None
                previous_ref=staged["ref"]
        if setup["preferred_template"]=="T10":
            for beat in setup["direction"]["visual_beats"]:
                if beat["focus_ref"].endswith("entity_a"):
                    for staged in beat["staging"]:
                        staged["motion_hint"]="none"
                elif beat["focus_ref"].endswith("entity_b"):
                    for staged in beat["staging"]:
                        staged["motion_hint"]="line_draw"
        setup["direction"]["layout_variant_hint"]=variant
    current=normalize_story(authored,payloads)
    variant_audio=copy.deepcopy(final)
    variant_audio["story_revision_sha256"]=current["story_revision_sha256"]
    timeline=compile_timeline(authored,current,words,variant_audio,assets,maps=maps,font_measure=measure,
                               font_identity=identity,
                               expected_story_sha256=current["story_revision_sha256"])
    if len(timeline["scenes"])!=10:
        raise RuntimeError("Expected one real compiled scene for each T01..T10")
    compiled[variant]=timeline
(outdir/"compiled-30.json").write_bytes(canonical(compiled))
print(json.dumps({"source":"SYNTHETIC B1 compiler, NOT G4 approval",
                  "templates":len(compiled["A"]["scenes"]),
                  "variants":len(compiled),"font_sha256":identity["font_sha256"],
                  "compiled_sha256":hashlib.sha256((outdir/"compiled-30.json").read_bytes()).hexdigest()}))
