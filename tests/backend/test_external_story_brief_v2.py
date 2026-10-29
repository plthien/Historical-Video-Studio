"""A1-06 targeted V2 external-authoring behavior and G4 cue boundary."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.server import create_app
from backend.app.contracts import ContractViolation
from backend.app.director.blueprint import normalize_story
from backend.app.director.timing import bind_beats, resolve_cue
from backend.app.projects.authoring_brief import BRIEF_VERSION, TEMPLATE_GUIDANCE, build_brief
from backend.app.projects.models import StoryCandidate

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "contracts/schema/StoryPackage.v1.schema.json"
REGISTRY = ROOT / "contracts/registries/layouts.v1.json"
EXAMPLE = ROOT / "contracts/examples/longform/StoryPackage.longform.synthetic.json"
SIMPLE = ROOT / "contracts/examples/StoryPackage.v1.valid.json"


def _save_and_build(client: TestClient, minutes: int, suffix: str = "") -> tuple[str, str]:
    pid = client.post("/api/v1/projects", json={"title": f"V2 authoring {minutes}{suffix}"}).json()["project_id"]
    body = {"topic": "Evidence-led port history", "audience": "Adult learners",
            "runtime_minutes": minutes,
            "editorial_goals": 'Preserve this exactly: maps, "quoted commas", and caution.'}
    saved = client.put(f"/api/v1/projects/{pid}/authoring-settings",
                       json={**body, "expected_revision": 0},
                       headers={"Idempotency-Key": f"v2-settings-{minutes}-{suffix or 'base'}"})
    assert saved.status_code == 200, saved.text
    response = client.post(f"/api/v1/projects/{pid}/authoring-brief", json=body)
    assert response.status_code == 200, response.text
    return pid, response.json()["content"]


def _schema_appendix(brief: str) -> dict:
    appendix = brief.split("## APPENDIX - Exact StoryPackage.v1 canonical JSON Schema\n", 1)[1]
    return json.loads(appendix.split("~~~json\n", 1)[1].rsplit("\n~~~", 1)[0])


def test_v2_version_exact_schema_determinism_and_runtime_guidance(tmp_path):
    app = create_app(tmp_path / "brief.sqlite", tmp_path / "media")
    with TestClient(app) as client:
        generated = {}
        for minutes, expected in ((5, "750-850"), (7, "1,050-1,190"), (10, "1,500-1,700")):
            pid, brief = _save_and_build(client, minutes)
            generated[minutes] = brief
            repeated = client.post(f"/api/v1/projects/{pid}/authoring-brief", json={
                "topic": "Evidence-led port history", "audience": "Adult learners",
                "runtime_minutes": minutes,
                "editorial_goals": 'Preserve this exactly: maps, "quoted commas", and caution.'}).json()
            assert repeated["brief_version"] == BRIEF_VERSION == "HVS-EXTERNAL-STORY-BRIEF.v2"
            assert repeated["content"] == brief
            assert f"Brief version: {BRIEF_VERSION}" in brief
            assert expected in brief
            assert "Final WAV" in brief and "determine achieved duration" in brief
            assert _schema_appendix(brief) == json.loads(SCHEMA.read_text(encoding="utf-8"))
            policy = brief.split("## APPENDIX", 1)[0]
            before_metadata, after_metadata = policy.split("~~~", 2)[::2]
            assert len(before_metadata + after_metadata) <= 8_000
        assert len(set(generated.values())) == 3
        assert "Black Death" not in generated[7]
        assert 'Preserve this exactly: maps, \\"quoted commas\\", and caution.' in generated[7]
        changed = {"topic": "Changed saved port history", "audience": "Adult learners",
                   "runtime_minutes": 10, "editorial_goals": "New persisted priority"}
        saved = client.put(f"/api/v1/projects/{pid}/authoring-settings",
                           json={**changed, "expected_revision": 1},
                           headers={"Idempotency-Key": "v2-settings-saved-change"})
        assert saved.status_code == 200
        rebuilt = client.post(f"/api/v1/projects/{pid}/authoring-brief", json=changed)
        assert rebuilt.status_code == 200 and rebuilt.json()["content"] != generated[10]


def test_v2_policy_matches_registry_and_preserves_gates(tmp_path):
    app = create_app(tmp_path / "policy.sqlite", tmp_path / "media")
    with TestClient(app) as client:
        _, brief = _save_and_build(client, 7, "policy")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    template_ids = {layout["template_id"] for layout in registry["layouts"]}
    assert set(TEMPLATE_GUIDANCE) == template_ids == {f"T{i:02}" for i in range(1, 11)}
    for template_id in template_ids:
        assert brief.count(f"- {template_id}:") == 1
    required = [
        "MUST include preferred_template", "Never use null", "globally unique beat IDs",
        "zero-based index", "chronological and non-overlapping", "pre-alignment only",
        "empty source_leads is truthful", "never pretend to have browsed", "status to UNVERIFIED",
        "never G1 APPROVED", "G3 rights-approved", "modern maps", "verbatim_verified",
        "editorial causal connector is not a geographic route", "start_year <= end_year",
    ]
    assert all(text in brief for text in required)
    assert "source leads are verified" not in brief.lower()
    assert "Return ONLY one complete StoryPackage.v1 JSON object" in brief

    # Existing frozen packages remain parseable; V2 is prompt policy, not a schema migration.
    candidate = StoryCandidate.parse(EXAMPLE.read_bytes())
    assert candidate.data()["schema_version"] == "StoryPackage.v1"

    story = StoryCandidate.parse(SIMPLE.read_bytes()).data()
    payload = json.loads((ROOT / "contracts/examples/VisualBlueprint.v1.valid.json").read_text(encoding="utf-8"))["setup_plans"][0]["template_payload"]
    missing = copy.deepcopy(story)
    missing["visual_setups"][0].pop("preferred_template")
    StoryCandidate.parse(missing)  # frozen schema still permits omission
    with pytest.raises(ContractViolation, match="LAYOUT_VARIANT_UNKNOWN"):
        normalize_story(missing, {"setup_001": payload})
    invalid_null = copy.deepcopy(story)
    invalid_null["visual_setups"][0]["preferred_template"] = None
    with pytest.raises(ContractViolation, match="SCHEMA_INVALID"):
        StoryCandidate.parse(invalid_null)

    sample_project = "proj_prompt_sample_black_death_v2"
    app.state.store.create_project(sample_project, "Black Death V2 prompt sample")
    sample = build_brief(app.state.store, sample_project,
        topic="How the Black Death Spread Across Europe in Just Six Years (1347-1353)",
        audience="Adults", runtime_minutes=7,
        editorial_goals="PROMPT_SAMPLE_ONLY. Prioritize historical maps, timeline, carefully qualified quantities, source traceability, and explicit reconstruction caveats.")
    assert (ROOT / "reports/authoring/PROMPT_SAMPLE_ONLY_BLACK_DEATH_7_MIN_V2.md").read_text(encoding="utf-8") == sample


def _word_map() -> dict:
    # Controlled synthetic timing: representation test only, not external-model evidence.
    tokens = [("rise", "sec_one"), ("again", "sec_one"), ("then", "sec_one"),
              ("rise", "sec_one"), ("again", "sec_one"), ("later", "sec_one"),
              ("rise", "sec_two"), ("again", "sec_two")]
    return {"schema_version": "WordTimingMap.v1", "project_id": "proj_cue_test",
            "provider_id": "elevenlabs_forced_alignment", "audio_sha256": "a" * 64,
            "transcript_sha256": "b" * 64, "sample_rate": 8000, "anomalies": [],
            "words": [{"word_id": f"word_{index:03}", "section_id": section, "text": text,
                       "start_sample": index * 1000, "end_sample": index * 1000 + 900}
                      for index, (text, section) in enumerate(tokens)]}


def _beat(beat_id: str, section: str, phrase: str, occurrence: int) -> dict:
    return {"beat_id": beat_id, "section_ref": section,
            "cue": {"section_id": section, "phrase": phrase, "occurrence": occurrence},
            "focus_ref": "slot_one", "focus_move": "static", "staging": [],
            "continuity": {"group_id": "group_one", "carry_refs": [],
                           "entry": "new_setup", "exit": "hard_cut", "reason": "synthetic test"}}


def _blueprint(*beats: dict) -> dict:
    return {"project_id": "proj_cue_test", "setup_plans": [{"setup_id": "setup_one",
            "section_refs": ["sec_one", "sec_two"],
            "editorial_direction": {"visual_beats": list(beats)}}]}


def test_controlled_synthetic_cues_cover_occurrence_section_and_global_order():
    words = _word_map()
    first = resolve_cue({"section_id": "sec_one", "phrase": "rise again", "occurrence": 0}, words, "beat_first")
    second = resolve_cue({"section_id": "sec_one", "phrase": "rise again", "occurrence": 1}, words, "beat_second")
    assert first["word_ids"] == ["word_000", "word_001"]
    assert second["word_ids"] == ["word_003", "word_004"]
    with pytest.raises(ContractViolation, match="CUE_MISSING"):
        resolve_cue({"section_id": "sec_one", "phrase": "not spoken", "occurrence": 0}, words, "beat_missing")
    with pytest.raises(ContractViolation, match="CUE_AMBIGUOUS"):
        resolve_cue({"section_id": "sec_one", "phrase": "rise again"}, words, "beat_absent_occurrence")
    with pytest.raises(ContractViolation, match="CUE_OCCURRENCE_INVALID"):
        resolve_cue({"section_id": "sec_one", "phrase": "rise again", "occurrence": 2}, words, "beat_bad_occurrence")

    kwargs = {"audio_sha256": words["audio_sha256"],
              "transcript_sha256": words["transcript_sha256"], "audio_total_samples": 9000}
    valid = bind_beats(_blueprint(_beat("beat_first", "sec_one", "rise again", 0),
                                  _beat("beat_second", "sec_one", "rise again", 1)), words, **kwargs)
    assert [item["occurrence"] for item in valid] == [0, 1]
    mismatch = _beat("beat_mismatch", "sec_one", "rise again", 0)
    mismatch["cue"]["section_id"] = "sec_two"
    with pytest.raises(ContractViolation, match="CUE_SECTION_MISMATCH"):
        bind_beats(_blueprint(mismatch), words, **kwargs)
    with pytest.raises(ContractViolation, match="CUE_RANGE_INVALID"):
        bind_beats(_blueprint(_beat("beat_later", "sec_one", "rise again", 1),
                              _beat("beat_earlier", "sec_one", "rise again", 0)), words, **kwargs)
    with pytest.raises(ContractViolation, match="CUE_OVERLAP"):
        bind_beats(_blueprint(_beat("beat_overlap_a", "sec_one", "rise again", 0),
                              _beat("beat_overlap_b", "sec_one", "again then", 0)), words, **kwargs)
