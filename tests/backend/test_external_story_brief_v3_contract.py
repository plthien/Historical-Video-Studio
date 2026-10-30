"""A1-06 exact V3 prompt asset, deterministic substitution and refusal contract."""
from __future__ import annotations

import hashlib
import json
import re
import socket
import urllib.request

import pytest
from fastapi.testclient import TestClient

from backend.app.api.server import create_app
from backend.app.contracts import ContractViolation
from backend.app.projects import authoring_brief
from backend.app.projects.authoring_brief import (
    BRIEF_VERSION, SCHEMA_PATH, SENTINELS, V3_PROMPT_PATH, build_brief,
)
from backend.app.projects.storage import ProjectStore


PROMPT_SHA256 = "e7234d15cc00a1f8b47196e7a7190296218ff9654bff4beb9818826c6848e494"
SCHEMA_SHA256 = "a209646795794042fe4acb10404529288315d47023e2668012af4ff3cbd5d6da"


def _store(tmp_path, project_id: str = "proj_v3_contract") -> ProjectStore:
    store = ProjectStore(tmp_path / "state.sqlite", tmp_path / "media")
    store.create_project(project_id, "V3 prompt contract")
    return store


def _inputs(**changes) -> dict:
    values = {"topic": "Evidence-led port history", "audience": "Adult learners",
              "runtime_minutes": 7, "editorial_goals": "Preserve uncertainty."}
    values.update(changes)
    return values


def _metadata(brief: str) -> dict:
    return json.loads(brief.split("~~~json\n", 1)[1].split("\n~~~", 1)[0])


def _appendix(brief: str) -> dict:
    appendix = brief.split("## APPENDIX — Exact frozen StoryPackage.v1 JSON Schema\n", 1)[1]
    return json.loads(appendix.split("~~~json\n", 1)[1].split("\n~~~", 1)[0])


def test_v3_raw_asset_is_exact_utf8_lf_single_sentinel_authority():
    raw = V3_PROMPT_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PROMPT_SHA256
    assert len(raw) == 24_253 and raw.count(b"\n") == 135 and b"\r" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf") and raw.endswith(b"\n")
    text = raw.decode("utf-8")
    assert all(text.count(token) == 1 for token in SENTINELS)
    assert hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest() == SCHEMA_SHA256


def test_v3_generated_brief_is_one_pass_golden_deterministic_and_api_bound(tmp_path):
    app = create_app(tmp_path / "api.sqlite", tmp_path / "api-media")
    with TestClient(app) as client:
        project_id = client.post("/api/v1/projects", json={"title": "V3 API"}).json()["project_id"]
        body = _inputs()
        saved = client.put(f"/api/v1/projects/{project_id}/authoring-settings",
                           json={**body, "expected_revision": 0},
                           headers={"Idempotency-Key": "v3-exact-settings"})
        assert saved.status_code == 200
        response = client.post(f"/api/v1/projects/{project_id}/authoring-brief", json=body)
        assert response.status_code == 200
        envelope = response.json()
        assert envelope["brief_version"] == BRIEF_VERSION == "HVS-EXTERNAL-STORY-BRIEF.v3"
        brief = envelope["content"]
        assert brief.count("Brief version: HVS-EXTERNAL-STORY-BRIEF.v3") == 1
        assert brief.count('"brief_version": "HVS-EXTERNAL-STORY-BRIEF.v3"') == 1
        assert brief.count(BRIEF_VERSION) == 2
        assert "At the V2 planning envelope" not in brief
        assert all(token not in brief for token in SENTINELS)

        metadata = {"brief_version": BRIEF_VERSION, "project_id": project_id,
                    "topic": body["topic"], "audience": body["audience"],
                    "runtime_minutes": 7, "editorial_goals": body["editorial_goals"],
                    "language": "en", "style_id": "HistoryEditorialPaper.v1",
                    "output": "16:9 1920x1080 30fps"}
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        substitutions = {
            SENTINELS[0]: json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2),
            SENTINELS[1]: (
                "At the provisional 150–170 spoken WPM planning envelope, 7 minutes "
                "corresponds to approximately 1,050–1,190 spoken words before allowances "
                "for pauses, difficult names, titles and audio gaps. Treat this as editorial "
                "guidance, not a schema or timed-audio gate; G2 Final WAV/alignment owns actual duration."
            ),
            SENTINELS[2]: json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2),
        }
        pattern = re.compile("|".join(re.escape(token) for token in SENTINELS))
        expected = pattern.sub(lambda match: substitutions[match.group(0)],
                               V3_PROMPT_PATH.read_text(encoding="utf-8"))
        assert brief == expected
        assert client.post(f"/api/v1/projects/{project_id}/authoring-brief", json=body).json()["content"] == brief
        assert _metadata(brief) == metadata and _appendix(brief) == schema


@pytest.mark.parametrize(("minutes", "budget"), [
    (5, "750–850"), (7, "1,050–1,190"), (10, "1,500–1,700"),
])
def test_v3_runtime_budget_is_exact(minutes, budget, tmp_path):
    store = _store(tmp_path, f"proj_v3_budget_{minutes}")
    brief = build_brief(store, f"proj_v3_budget_{minutes}", **_inputs(runtime_minutes=minutes))
    assert f"{minutes} minutes corresponds to approximately {budget} spoken words" in brief


def test_v3_unicode_and_sentinel_looking_operator_text_is_preserved_not_rescanned(tmp_path):
    project_id = "proj_v3_unicode"
    store = _store(tmp_path, project_id)
    topic = 'Đại Việt {"quoted": true}\n' + SENTINELS[2]
    audience = "Người xem — general adults"
    goals = "Keep literal markers: " + " | ".join(SENTINELS)
    brief = build_brief(store, project_id, **_inputs(
        topic=topic, audience=audience, editorial_goals=goals))
    metadata = _metadata(brief)
    assert metadata["topic"] == topic and metadata["audience"] == audience
    assert metadata["editorial_goals"] == goals
    assert brief.count(SENTINELS[0]) == 1
    assert brief.count(SENTINELS[1]) == 1
    assert brief.count(SENTINELS[2]) == 2


@pytest.mark.parametrize("token", SENTINELS)
@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_v3_missing_or_duplicate_template_marker_fails(token, mutation, tmp_path, monkeypatch):
    template = V3_PROMPT_PATH.read_text(encoding="utf-8")
    changed = template.replace(token, "", 1) if mutation == "missing" else template.replace(token, token + token, 1)
    bad = tmp_path / "bad-template.md"
    bad.write_text(changed, encoding="utf-8", newline="\n")
    monkeypatch.setattr(authoring_brief, "V3_PROMPT_PATH", bad)
    store = _store(tmp_path / "store", f"proj_v3_marker_{mutation}")
    with pytest.raises(ContractViolation, match="BRIEF_TEMPLATE_INVALID"):
        build_brief(store, f"proj_v3_marker_{mutation}", **_inputs())


@pytest.mark.parametrize("changes", [
    {"topic": ""}, {"topic": "   "}, {"audience": ""},
    {"runtime_minutes": 4}, {"runtime_minutes": 11}, {"runtime_minutes": 7.0},
])
def test_v3_invalid_operator_inputs_fail_closed(changes, tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ContractViolation, match="BRIEF_INPUT_INVALID"):
        build_brief(store, "proj_v3_contract", **_inputs(**changes))


def test_v3_missing_project_and_registry_drift_fail_closed(tmp_path, monkeypatch):
    store = ProjectStore(tmp_path / "state.sqlite", tmp_path / "media")
    with pytest.raises(ContractViolation):
        build_brief(store, "proj_missing", **_inputs())
    store.create_project("proj_registry_drift", "registry drift")
    registry = json.loads(authoring_brief.LAYOUTS_PATH.read_text(encoding="utf-8"))
    registry["layouts"][0]["template_id"] = "T99"
    changed = tmp_path / "layouts.json"
    changed.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(authoring_brief, "LAYOUTS_PATH", changed)
    with pytest.raises(ContractViolation, match="BRIEF_TEMPLATE_GUIDE_STALE"):
        build_brief(store, "proj_registry_drift", **_inputs())


def test_v3_builder_makes_no_network_or_llm_call(tmp_path, monkeypatch):
    store = _store(tmp_path, "proj_v3_offline")
    monkeypatch.setattr(socket, "create_connection",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network called")))
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network called")))
    assert build_brief(store, "proj_v3_offline", **_inputs()).startswith("# EXTERNAL CHATGPT")
