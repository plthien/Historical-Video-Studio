"""Static full-flow design integrity tests; no providers or media are run."""
import json
import sys
import unittest
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from check_design_contracts import validate_historical_map,validate_template_layout,validate_story,validate_schema,ContractError

class FullFlowDesignTests(unittest.TestCase):
    def test_longform_story_normalization_and_compiled_frames(self):
        folder=ROOT/"contracts"/"examples"/"longform"
        story=json.loads((folder/"StoryPackage.longform.synthetic.json").read_text(encoding="utf-8"))
        blue=json.loads((folder/"VisualBlueprint.longform.synthetic.json").read_text(encoding="utf-8"))
        timeline=json.loads((folder/"CompiledTimeline.longform.synthetic.json").read_text(encoding="utf-8"))
        validate_story(story)
        validate_schema("VisualBlueprint.v1",blue)
        validate_schema("CompiledTimeline.v1",timeline)
        self.assertEqual((len(story["sections"]),len(blue["setup_plans"]),len(timeline["scenes"])),(24,48,48))
        self.assertEqual(timeline["total_frames"],10800)
        self.assertEqual(max(s["start_frame"]+s["duration_frames"] for s in timeline["scenes"]),10800)
        self.assertTrue(all("direction" in s for s in story["visual_setups"]))
        self.assertTrue(all("rect_px" in s["layers"][0] and "camera" in s for s in timeline["scenes"]))
        self.assertTrue(all(c["status"]=="UNVERIFIED" for c in story["claims"]))

    def test_thirty_registry_variants_and_boundaries(self):
        reg=json.loads((ROOT/"contracts"/"registries"/"layouts.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(len(reg["layouts"]),30)
        keys=set()
        for layout in reg["layouts"]:
            validate_template_layout(layout)
            key=(layout["template_id"],layout["variant_id"])
            self.assertNotIn(key,keys)
            keys.add(key)
        self.assertEqual(keys,{(f"T{i:02}",v) for i in range(1,11) for v in "ABC"})

    def test_nineteen_motion_presets_valid_and_unique(self):
        reg=json.loads((ROOT/"contracts"/"registries"/"motion-presets.v1.json").read_text(encoding="utf-8"))
        presets=reg["presets"]
        self.assertEqual(len(presets),19)
        self.assertEqual(len({p["preset_id"] for p in presets}),19)
        for p in presets:
            self.assertLessEqual(p["min_duration_frames"],p["default_duration_frames"])
            self.assertLessEqual(p["default_duration_frames"],p["max_duration_frames"])
            self.assertTrue(p["compatible_layer_kinds"])
            self.assertEqual(p["reduced_motion"] in {"fade_or_hold","none"},True)

    def test_map_period_and_source_not_auto_approved(self):
        map_data=json.loads((ROOT/"contracts"/"examples"/"HistoricalMap.v1.valid.json").read_text(encoding="utf-8"))
        self.assertFalse(map_data["user_approved"])
        with self.assertRaisesRegex(ContractError,"MAP_UNAPPROVED"):
            validate_historical_map(map_data,1871)
        map_data["user_approved"]=True
        validate_historical_map(map_data,1871,"feature_001")

    def test_two_openapi_documents_are_parseable_and_nonoverlapping(self):
        base=yaml.safe_load((ROOT/"contracts"/"openapi.yaml").read_text(encoding="utf-8"))
        ext=json.loads((ROOT/"contracts"/"openapi-fullflow-extension.json").read_text(encoding="utf-8"))
        self.assertEqual(base["openapi"],"3.1.0")
        self.assertEqual(ext["openapi"],"3.1.0")
        full=set((p,m) for p,verbs in base["paths"].items() for m in verbs)
        extended=set((p,m) for p,verbs in ext["paths"].items() for m in verbs)
        self.assertFalse(full.intersection(extended))
        self.assertGreaterEqual(len(extended),20)
        for p,verbs in ext["paths"].items():
            for method,op in verbs.items():
                self.assertTrue(op["summary"])
                if method not in {"get","head"}:
                    self.assertIn("requestBody",op)
                    request_name=op["requestBody"]["content"]["application/json"]["schema"]["$ref"].rsplit("/",1)[-1]
                    if request_name!="ProviderSettings":
                        self.assertIn("expected_revision",ext["components"]["schemas"][request_name]["required"])
                    self.assertIn("Idempotency-Key",[x["name"] for x in op["parameters"]])
                    ref=op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
                    self.assertTrue(ref.startswith("#/components/schemas/"))
                    self.assertIn(ref.rsplit("/",1)[-1],ext["components"]["schemas"])
        base_keys=set(base.get("components",{}).get("schemas",{}))
        self.assertTrue(base_keys)

    def test_original_glabs_document_kept_verbatim_size_and_endpoints(self):
        path=ROOT/"contracts"/"providers"/"reference"/"WEBHOOK_INTEGRATION.vi(1).md"
        content=path.read_text(encoding="utf-8")
        self.assertGreater(len(content),60000)
        self.assertEqual(len(content.splitlines()),1148)
        for endpoint in ["/api/image/generate","/api/status/{task_id}","/api/result/{task_id}","/api/stop/{task_id}"]:
            self.assertIn(endpoint,content)

    def test_archival_source_contracts_exist(self):
        for name in ["WIKIMEDIA_COMMONS.v1.md","LIBRARY_OF_CONGRESS.v1.md","EUROPEANA.v1.md","ARCHIVE_ADAPTER_MATRIX.v1.md"]:
            p=ROOT/"contracts"/"providers"/name
            self.assertTrue(p.exists())
            self.assertGreater(len(p.read_text(encoding="utf-8")),600)

    def test_full_flow_plan_no_pilot_requirement(self):
        plan=(ROOT/"docs"/"step01-02"/"05_IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
        self.assertIn("FULL-FLOW IMPLEMENTATION PLAN",plan)
        self.assertIn("no separate",plan.lower())
        self.assertIn("Windows",plan)
        self.assertIn("T01",plan)
        self.assertIn("T10",plan)

if __name__=="__main__":
    unittest.main()
