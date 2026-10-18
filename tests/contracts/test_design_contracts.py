"""Offline data-contract acceptance and negative regressions for Step 01/02."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_design_contracts import (ContractError, check_all, load_example,
    can_approve_story, validate_story, validate_word_map, validate_asset_resolution,
    validate_timeline, validate_gate_approval)


class DesignContractTests(unittest.TestCase):
    def test_all_valid_fixtures_and_schemas(self):
        self.assertEqual(len(check_all()), 10)

    def test_duplicate_section(self):
        s = load_example("StoryPackage.v1")
        s["sections"].append(copy.deepcopy(s["sections"][0]))
        with self.assertRaisesRegex(ContractError, "DUPLICATE_ID"):
            validate_story(s)

    def test_dangling_asset_requirement(self):
        s = load_example("StoryPackage.v1")
        s["visual_setups"][0]["requirement_refs"] = ["req_missing"]
        with self.assertRaisesRegex(ContractError, "CROSS_REFERENCE_MISSING"):
            validate_story(s)

    def test_inverted_years(self):
        s = load_example("StoryPackage.v1")
        s["asset_requirements"][0]["end_year"] = 1800
        with self.assertRaisesRegex(ContractError, "PERIOD_INVALID"):
            validate_story(s)

    def test_unreviewed_critical_fact_cannot_approve_g1(self):
        s = load_example("StoryPackage.v1")
        s["claims"][0]["critical"] = True
        with self.assertRaisesRegex(ContractError, "CLAIM_CRITICAL_UNRESOLVED"):
            can_approve_story(s)

    def test_text_or_audio_revision_stales_word_map(self):
        words, audio = load_example("WordTimingMap.v1"), load_example("FinalAudio.v1")
        audio["audio_sha256"] = "1" * 64
        with self.assertRaisesRegex(ContractError, "WORD_MAP_STALE"):
            validate_word_map(words, audio)

    def test_word_nonmonotonic_and_out_of_bounds(self):
        words, audio = load_example("WordTimingMap.v1"), load_example("FinalAudio.v1")
        words["words"][1]["start_sample"] = 0
        with self.assertRaisesRegex(ContractError, "WORD_RANGE_INVALID"):
            validate_word_map(words, audio)
        words = load_example("WordTimingMap.v1")
        words["words"][1]["end_sample"] = audio["duration_samples"] + 1
        with self.assertRaisesRegex(ContractError, "WORD_RANGE_INVALID"):
            validate_word_map(words, audio)

    def test_managed_fallback_requires_user_authorization(self):
        r = load_example("AssetResolution.v1")
        r.update(resolution_mode="MANAGED_FALLBACK", status="MANAGED_FALLBACK_AUTHORIZED")
        with self.assertRaisesRegex(ContractError, "FALLBACK_NOT_AUTHORIZED"):
            validate_asset_resolution(r)

    def test_managed_fallback_generation_is_not_approval(self):
        r = load_example("AssetResolution.v1")
        r.update(resolution_mode="MANAGED_FALLBACK", operator_authorized=True,
                 status="APPROVED", candidate_asset_ids=["asset_001"])
        with self.assertRaisesRegex(ContractError, "FALLBACK_NOT_APPROVED"):
            validate_asset_resolution(r)

    def test_timeline_stale_asset_and_missing_word(self):
        timeline, words = load_example("CompiledTimeline.v1"), load_example("WordTimingMap.v1")
        with self.assertRaisesRegex(ContractError, "ASSET_BINDING_STALE"):
            validate_timeline(timeline, words, set())
        timeline["scenes"][0]["events"][0]["cue_word_id"] = "word_unknown"
        with self.assertRaisesRegex(ContractError, "INVALID_CUE_WORD"):
            validate_timeline(timeline, words, {"asset_001"})

    def test_scene_bounds_and_event_layer(self):
        timeline, words = load_example("CompiledTimeline.v1"), load_example("WordTimingMap.v1")
        timeline["scenes"][0]["events"][0]["start_frame"] = 145
        with self.assertRaisesRegex(ContractError, "SCENE_RANGE_INVALID"):
            validate_timeline(timeline, words, {"asset_001"})
        timeline = load_example("CompiledTimeline.v1")
        timeline["scenes"][0]["events"][0]["layer_id"] = "layer_missing"
        with self.assertRaisesRegex(ContractError, "LAYER_REF_MISSING"):
            validate_timeline(timeline, words, {"asset_001"})

    def test_revision_conflict(self):
        with self.assertRaisesRegex(ContractError, "APPROVAL_REVISION_CONFLICT"):
            validate_gate_approval("G3", "READY_FOR_REVIEW", "a", "b", 4, 4, True)
        with self.assertRaisesRegex(ContractError, "GATE_ILLEGAL_TRANSITION"):
            validate_gate_approval("G4", "READY_FOR_REVIEW", "a", "a", 4, 4, False)

    def test_happy_gate_candidate(self):
        validate_gate_approval("G1", "READY_FOR_REVIEW", "abc", "abc", 4, 4, True)


if __name__ == "__main__":
    unittest.main()
