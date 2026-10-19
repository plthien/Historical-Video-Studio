"""Adversarial visual grammar regression tests. No Remotion/AI provider is called."""
from __future__ import annotations
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_design_contracts import ContractError
from validate_visual_design import (
    load_visual_fixtures, load_registries,
    validate_blueprint, validate_directed_story, validate_visual_registry,
    validate_visual_timeline, validate_visual_case_package
)


class VisualDesignV11Tests(unittest.TestCase):
    def setUp(self):
        self.story, self.blue, self.timeline = load_visual_fixtures()
        self.layouts, self.motions = load_registries()

    def test_all_ten_template_payloads_three_stage_contracts(self):
        validate_visual_case_package(self.story, self.blue, self.timeline)
        self.assertEqual({p["template_id"] for p in self.blue["setup_plans"]},
                         {f"T{i:02d}" for i in range(1, 11)})
        self.assertEqual(len(self.timeline["scenes"]), 10)

    def test_thirty_layouts_different_and_per_template_roles(self):
        validate_visual_registry(self.layouts, self.motions)
        rows = {(x["template_id"], x["variant_id"]): x for x in self.layouts["layouts"]}
        self.assertEqual(len(rows), 30)
        self.assertEqual(len({x["visual_variation_signature"] for x in self.layouts["layouts"]}), 30)
        self.assertGreaterEqual(sum(x["role"]=="archival_photo" for x in rows["T03","A"]["slots"]), 3)
        self.assertEqual(sum(x["role"]=="map" for x in rows["T07","A"]["slots"]), 2)
        self.assertGreaterEqual(sum(x["role"]=="date" for x in rows["T05","A"]["slots"]), 2)
        self.assertEqual(sum(x["role"]=="route" for x in rows["T04","A"]["slots"]), 1)

    def test_each_preset_has_distinct_schema_and_phase(self):
        from jsonschema import Draft202012Validator
        p={x["preset_id"]:x for x in self.motions["presets"]}
        self.assertEqual(len(p),18)
        for x in p.values():
            Draft202012Validator.check_schema(x["parameter_schema"])
            Draft202012Validator(x["parameter_schema"]).validate(x["default_params"])
        self.assertIn("route_geometry_ref",p["route-line-draw"]["parameter_schema"]["required"])
        self.assertIn("near_layer_ids",p["parallax-layers"]["parameter_schema"]["required"])
        self.assertIn("approved_feature_ids",p["map-region-wipe"]["parameter_schema"]["required"])

    def test_bad_visual_focus_reference_is_blocker(self):
        x=copy.deepcopy(self.story)
        x["visual_setups"][0]["direction"]["visual_beats"][0]["focus_ref"]="missing_critical"
        with self.assertRaisesRegex(ContractError,"VISUAL_BEAT_FOCUS_UNKNOWN"):
            validate_directed_story(x)

    def test_bad_relationship_reference_is_blocker(self):
        x=copy.deepcopy(self.story)
        x["visual_setups"][2]["direction"]["visual_beats"][1]["relationships"][0]["to_ref"]="missing_source"
        with self.assertRaisesRegex(ContractError,"VISUAL_RELATION_UNKNOWN"):
            validate_directed_story(x)

    def test_template_discriminator_and_card_order(self):
        x=copy.deepcopy(self.blue)
        x["setup_plans"][2]["template_payload"]["card_reveal_order"].pop()
        with self.assertRaisesRegex(ContractError,"COLLAGE_ORDER_INVALID"):
            validate_blueprint(self.story,x)
        x=copy.deepcopy(self.blue)
        x["setup_plans"][2]["template_payload"]["template_id"]="T07"
        with self.assertRaises(Exception):
            validate_blueprint(self.story,x)

    def test_route_waypoints_must_reference_story_beat(self):
        x=copy.deepcopy(self.blue)
        x["setup_plans"][3]["template_payload"]["waypoints"][1]["cue_beat_id"]="beat_unknown"
        with self.assertRaisesRegex(ContractError,"TEMPLATE_BEAT_MISSING"):
            validate_blueprint(self.story,x)

    def test_timeline_must_have_min_two_events(self):
        x=copy.deepcopy(self.blue)
        x["setup_plans"][4]["template_payload"]["timeline_events"][1]["chronology_order"]=1
        with self.assertRaisesRegex(ContractError,"CHRONOLOGY_ORDER_INVALID"):
            validate_blueprint(self.story,x)

    def test_map_comparison_rejects_same_year(self):
        x=copy.deepcopy(self.blue)
        x["setup_plans"][6]["template_payload"]["before_map"]["year"]=1914
        with self.assertRaisesRegex(ContractError,"MAP_PERIOD_MISMATCH|MAP_PAIR_NOT_DISTINCT"):
            validate_blueprint(self.story,x)

    def test_false_verbatim_quote_is_rejected(self):
        x=copy.deepcopy(self.blue)
        x["setup_plans"][8]["template_payload"]["quote_kind"]="verbatim_verified"
        with self.assertRaisesRegex(ContractError,"QUOTE_SOURCE_NOT_VERIFIED"):
            validate_blueprint(self.story,x)

    def test_unsupported_movement_params_or_space(self):
        x=copy.deepcopy(self.timeline)
        e=x["scenes"][3]["events"][0]
        e["params"]["route_geometry_ref"]="geometry_wrong"
        with self.assertRaisesRegex(ContractError,"MOTION_ROUTE_UNBOUND"):
            validate_visual_timeline(self.blue,x,self.layouts,self.motions)
        x=copy.deepcopy(self.timeline)
        x["scenes"][2]["events"][2]["motion_space"]="screen"
        with self.assertRaisesRegex(ContractError,"MOTION_SPACE_INVALID"):
            validate_visual_timeline(self.blue,x,self.layouts,self.motions)

    def test_missing_parallax_planes(self):
        x=copy.deepcopy(self.timeline)
        x["scenes"][2]["events"][2]["depth_parallax"]=None
        with self.assertRaisesRegex(ContractError,"PARALLAX_DEPTH_MISSING"):
            validate_visual_timeline(self.blue,x,self.layouts,self.motions)

    def test_missing_two_map_layers(self):
        x=copy.deepcopy(self.timeline)
        scene=x["scenes"][6]
        scene["layers"]=[l for l in scene["layers"] if "map_after" not in l["layer_id"]]
        with self.assertRaisesRegex(ContractError,"LAYOUT_REQUIRED_ROLE_MISSING"):
            validate_visual_timeline(self.blue,x,self.layouts,self.motions)

    def test_invalid_causal_edge(self):
        x=copy.deepcopy(self.blue)
        x["setup_plans"][9]["template_payload"]["causal_links"][0]["to_entity_id"]="unknown_entity"
        with self.assertRaisesRegex(ContractError,"CAUSAL_LINK_INVALID"):
            validate_blueprint(self.story,x)

    def test_missing_staging_camera_target(self):
        x=copy.deepcopy(self.timeline)
        x["scenes"][0]["camera"]["focus_path"][0]["focus_layer_id"]="ghost_layer"
        with self.assertRaisesRegex(ContractError,"CAMERA_TARGET_UNKNOWN"):
            validate_visual_timeline(self.blue,x,self.layouts,self.motions)

    def test_synthetic_claims_cannot_gain_g1_approval(self):
        from check_design_contracts import can_approve_story
        with self.assertRaisesRegex(ContractError,"CLAIM_CRITICAL_UNRESOLVED"):
            can_approve_story(self.story)


if __name__ == "__main__":
    unittest.main()
