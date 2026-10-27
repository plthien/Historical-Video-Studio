"""B3-06 production-wiring evidence, explicitly separated from live acceptance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.tools.b3_final_smoke import full_flow_two_topics, restart_during_render


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "renderer" / ".artifacts" / "b3-delivery"


def test_full_flow_short_real_media_fixture_and_restart_negatives():
    restart_during_render()
    full_flow_two_topics("local")
    summary = json.loads((EVIDENCE / "summary.json").read_text("utf-8"))
    verdict = json.loads((EVIDENCE / "three-p1-verdict.json").read_text("utf-8"))
    restart = json.loads((EVIDENCE / "g04-real-process-kill-restart.json").read_text("utf-8"))
    assert summary["scope"] == "SYNTHETIC_TEST_ONLY"
    assert summary["render_job"]["state"] == "SUCCEEDED"
    assert summary["render_job"]["qc_status"] == "PASS"
    assert summary["export"]["export_id"]
    assert {verdict["black_frame"]["problem"], verdict["near_silent_aac"]["problem"]} == {
        "QC_VISUAL_ANOMALY", "QC_AUDIO_CONTENT_MISMATCH"}
    assert restart["stale_source_negative"] == {
        **restart["stale_source_negative"], "state": "FAILED_TERMINAL",
        "error_code": "G4_APPROVAL_REQUIRED", "renderer_process_started": False,
        "output_published": False, "g5_candidate_published": False}
    assert restart["single_owner"]["duplicate_owners"] == 0


def test_full_flow_live_preflight_is_blocked_without_operator_inputs(monkeypatch, capsys):
    for name in ("HVS_DB", "HVS_MEDIA", "HVS_LIVE_PROJECT_IDS",
                 "HVS_LIVE_OPERATOR_ATTESTATION", "HVS_LIVE_RIGHTS_ATTESTATION"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit) as stopped:
        full_flow_two_topics("live")
    assert stopped.value.code == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED" and result["side_effects"] == "NONE"
    assert "two distinct HVS_LIVE_PROJECT_IDS" in result["missing"]


@pytest.mark.live
def test_live_two_topic_acceptance_uses_only_existing_operator_projects():
    full_flow_two_topics("live")
