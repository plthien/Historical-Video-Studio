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
from backend.app.director.layout import windows_font_measure
from backend.app.director.fingerprint import canonical

ROOT = Path(__file__).resolve().parents[2]
outdir=ROOT / "renderer" / ".artifacts"
outdir.mkdir(parents=True,exist_ok=True)
font=Path(os.environ["WINDIR"])/"Fonts"/"arial.ttf"
measure, identity=windows_font_measure(str(font),hashlib.sha256(font.read_bytes()).hexdigest())
story, bp, words, final, assets, maps=synthetic_ten_template_inputs()
compiled={}
for variant in ("A","B","C"):
    current=copy.deepcopy(bp)
    for p in current["setup_plans"]:
        p["variant_id"]=variant
        p["layout_control"]["layout_id"]=f'{p["template_id"]}.{variant}.v1.1'
    timeline=compile_timeline(story,current,words,final,assets,maps=maps,font_measure=measure,
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
