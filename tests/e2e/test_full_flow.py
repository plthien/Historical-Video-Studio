"""B3-06 production-wiring evidence, explicitly separated from live acceptance."""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.projects.revisions import mark_stale
from backend.app.projects.storage import ProjectStore
from backend.tools.b3_final_smoke import (
    LiveAuthorityBlocked,
    full_flow_two_topics,
    verify_distinct_story_identities,
    verify_live_project_authority,
)


ROOT = Path(__file__).resolve().parents[2]
@pytest.fixture(scope="module")
def owner_authority_config(tmp_path_factory):
    """Produce current owner evidence once; individual negatives clone it."""
    root = tmp_path_factory.mktemp("authority-owner")
    flow = root / "project"
    subprocess.run([sys.executable, "-m", "backend.tools.b3_delivery_fixture",
                    "--flow-root", str(flow), "--evidence-dir", str(root / "delivery"),
                    "--project-id", "proj_authority_boundary", "--direct-render"],
                   cwd=ROOT, check=True)
    return json.loads(flow.with_suffix(".json").read_text("utf-8"))


@pytest.fixture
def current_authority_store(tmp_path, owner_authority_config):
    """Clone the exact owner-produced G1-G5 fixture; never mutate shared evidence."""
    config = owner_authority_config
    database = tmp_path / "authority.sqlite"
    destination = sqlite3.connect(database)
    try:
        with sqlite3.connect(config["db"]) as source:
            source.backup(destination)
    finally:
        destination.close()
    media = tmp_path / "media"
    shutil.copytree(config["artifactRoot"], media)
    return ProjectStore(database, media), config["project"]


def test_full_flow_short_real_media_fixture_and_restart_negatives():
    full_flow_two_topics("local")
    trace = json.loads((ROOT / "reports/acceptance/generated/local-full-flow-trace.json").read_text("utf-8"))
    assert trace["status"] == "LOCAL_CODE_PASS"
    assert trace["project_id"].startswith("proj_local_full_")
    assert set(trace["gate_approval_ids"]) == {"G1", "G2", "G3", "G4", "G5"}
    assert trace["render"]["qc_status"] == "PASS"
    assert trace["reopen"]["counts_before"] == trace["reopen"]["counts_after"]
    assert trace["reopen"]["created_jobs_or_exports"] is False
    assert {"G4_APPROVAL_REQUIRED", "FORGED_G4_BLOCKED", "LOCAL_RENDER_CANCEL_CONFIRMED",
            "MUTED_REVIEW_LISTENED_ZERO_AND_COMPLETION_BLOCKED", "DIRECT_REAL_RENDER_PASS"}.issubset(
                set(trace["negative_cases"]))


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


def test_live_authority_accepts_current_owner_lineage_before_media_duration(current_authority_store):
    store, project = current_authority_store
    result = verify_live_project_authority(store, project)
    assert result["project_id"] == project
    assert set(result["heads"]) == {"G1", "G2", "G3", "G4", "G5"}
    assert {item["state"] for item in result["board"].values()} == {"APPROVED"}


def test_live_authority_rejects_same_story_identity_under_distinct_project_titles():
    with pytest.raises(LiveAuthorityBlocked, match="distinct current StoryPackage"):
        verify_distinct_story_identities([
            {"project_id": "first", "title": "Title A", "story_sha256": "a" * 64},
            {"project_id": "second", "title": "Title B", "story_sha256": "a" * 64},
        ])


@pytest.mark.parametrize("mutation,expected", [
    ("claim_stale", ":G1:STALE:"),
    ("asset_stale", ":G3:STALE:"),
    ("g4_stale", ":G4:STALE:"),
    ("g5_stale", ":G5:STALE:"),
    ("word_map_job_failed", ":G2:CURRENT_VERIFIED_WORD_MAP_REQUIRED"),
    ("wrong_requirement_id", ":G3:"),
    ("missing_mp4", ":ARTIFACT_MISSING:"),
])
def test_live_authority_blocks_stale_or_misbound_owner_state(
        current_authority_store, mutation, expected):
    store, project = current_authority_store
    with store._connection() as db:
        before = (db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                  db.execute("SELECT COUNT(*) FROM delivery_exports").fetchone()[0])
    if mutation in {"claim_stale", "asset_stale", "g4_stale", "g5_stale"}:
        with store._transaction() as db:
            mark_stale(db, project, {"claim_stale": "claim_review",
                                     "asset_stale": "asset_replace",
                                     "g4_stale": "scene_layout",
                                     "g5_stale": "render_retry"}[mutation])
    elif mutation == "word_map_job_failed":
        with store._transaction() as db:
            approval = db.execute(
                "SELECT approval_id FROM gate_heads WHERE project_id=? AND gate_id='G2'",
                (project,)).fetchone()[0]
            db.execute("UPDATE jobs SET state='FAILED_TERMINAL',error_code='TEST_INVALIDATED' "
                       "WHERE project_id=? AND kind='final_alignment' "
                       "AND json_extract(payload_json,'$.approval_id')=?", (project, approval))
    elif mutation == "wrong_requirement_id":
        with store._transaction() as db:
            approval = db.execute(
                "SELECT approval_id FROM asset_approval_heads WHERE project_id=? LIMIT 1",
                (project,)).fetchone()[0]
            db.execute("UPDATE asset_approval_events SET requirement_id='req_wrong' WHERE approval_id=?",
                       (approval,))
    elif mutation == "missing_mp4":
        with store._connection() as db:
            digest = db.execute(
                "SELECT mp4_artifact_id FROM delivery_exports WHERE project_id=? ORDER BY rowid DESC LIMIT 1",
                (project,)).fetchone()[0]
        store.artifacts.path(digest).unlink()
    with pytest.raises(LiveAuthorityBlocked) as blocked:
        verify_live_project_authority(store, project)
    assert expected in ";".join(blocked.value.reasons)
    with store._connection() as db:
        after = (db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                 db.execute("SELECT COUNT(*) FROM delivery_exports").fetchone()[0])
    assert after == before


@pytest.mark.live
def test_live_two_topic_acceptance_uses_only_existing_operator_projects():
    full_flow_two_topics("live")
