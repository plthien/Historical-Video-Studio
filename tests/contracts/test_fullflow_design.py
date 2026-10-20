"""Static full-flow design integrity tests; no providers or media are run."""
import json
import sys
import unittest
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from check_design_contracts import validate_historical_map,validate_story,validate_schema,ContractError

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
                    # Two project-scoped job controls are intentionally bodyless.
                    # Keep requestBody and expected_revision assertions for every
                    # existing operation; idempotency binds job identity in the path.
                    if p in ("/projects/{project_id}/jobs/{job_id}/retry",
                             "/projects/{project_id}/jobs/{job_id}/cancel"):
                        self.assertEqual(method,"post")
                        self.assertNotIn("requestBody",op)
                        self.assertIn("Idempotency-Key",[x["name"] for x in op["parameters"]])
                        continue
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


if __name__=="__main__":
    unittest.main()
