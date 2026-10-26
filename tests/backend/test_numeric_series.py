"""D01: review transactions use the normal FastAPI/SQLite owner path, not fake gate heads."""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.server import create_app


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def ready(tmp_path):
    story = json.loads((ROOT / "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    client = TestClient(create_app(tmp_path / "gates.sqlite", tmp_path / "media"))
    created = client.post("/api/v1/projects", json={"title": "Synthetic numeric review"}).json()
    pid = created["project_id"]
    story["project"]["project_id"] = pid
    root = f"/api/v1/projects/{pid}"
    def post(route, payload, key):
        return client.post(root + route, json=payload, headers={"Idempotency-Key": key})
    imported = post("/story/import?expected_revision=0", story, "import-numeric-test")
    assert imported.status_code == 200, imported.text
    rev = imported.json()["project_revision"]
    for claim in story["claims"]:
        result = post(f"/story/claims/{claim['claim_id']}/review",
                      {"expected_revision": rev, "status": "VERIFIED",
                       "evidence_note": "Synthetic fixture review, NOT a real historical verification",
                       "source_url": "https://www.loc.gov/"},
                      f"review-{claim['claim_id']}")
        assert result.status_code == 200, result.text
        rev = result.json()["project_revision"]
    board = client.get(root + "/gates").json()[0]
    approved = post("/gates/G1/decision",
                    {"decision": "APPROVED", "candidate_sha256": board["candidate_sha256"],
                     "dependency_fingerprint": board["dependency_fingerprint"],
                     "expected_revision": rev, "comment": "Synthetic source software test only"},
                    "approve-synthetic-story")
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "APPROVED"
    return client, root, approved.json(), tmp_path


def _evidence(client, root, rev, claim="claim_001", key="evidence-test-one"):
    data = {"expected_revision": rev,
            "content_base64": base64.b64encode(b"SYNTHETIC_TEST_PROJECT: 0,50,100 (not historical evidence)").decode(),
            "source_url": "https://www.loc.gov/",
            "review_note": "Synthetic numeric observations for software review test only"}
    response = client.post(root + f"/story/claims/{claim}/numeric-series/evidence",
                           json=data, headers={"Idempotency-Key": key})
    return response, data


def _series(rev, story_sha, approval_id, evidence):
    return {"expected_revision": rev, "series_id": "numeric_001",
            "frozen_story_sha256": story_sha, "g1_approval_id": approval_id,
            "unit": "synthetic_count", "precision": 0,
            "authored_duration_frames": 30, "start_value": "0", "end_value": "100",
            "observations": [{"frame_offset": i, "value": v, "source_evidence_sha256": evidence}
                             for i, v in [(0, "0"), (15, "50"), (30, "100")]],
            "operator_reason": "Synthetic review for local D01 software acceptance only"}


def test_numeric_series_owner_evidence_approval_head_revoke_and_cold_reopen(ready):
    client, root, approved, tmp_path = ready
    rev = approved["project_revision"]
    evidence, payload = _evidence(client, root, rev)
    assert evidence.status_code == 200, evidence.text
    assert client.post(root + "/story/claims/claim_001/numeric-series/evidence",
                       json=payload, headers={"Idempotency-Key": "evidence-test-one"}).json() == evidence.json()
    rev = evidence.json()["project_revision"]
    story_sha = client.get(root + "/story").json()["candidate_sha256"]
    series = _series(rev, story_sha, approved["approval_id"], evidence.json()["source_evidence_sha256"])
    route = root + "/story/claims/claim_001/numeric-series/approve"
    saved = client.post(route, json=series, headers={"Idempotency-Key": "reviewed-numeric-series"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["series_sha256"]
    assert client.post(route, json=series, headers={"Idempotency-Key": "reviewed-numeric-series"}).json() == saved.json()
    mutated = copy.deepcopy(series)
    mutated["observations"][1]["value"] = "51"
    assert client.post(route, json=mutated, headers={"Idempotency-Key": "reviewed-numeric-series"}).status_code == 409
    reread = TestClient(create_app(tmp_path / "gates.sqlite", tmp_path / "media"))
    current = reread.get(root + "/story/claims/claim_001/numeric-series/numeric_001")
    assert current.status_code == 200 and current.json()["current"] is True
    assert current.json()["series"]["observations"][1]["value"] == "50"
    assert reread.get(root + "/gates").json()[0]["state"] == "APPROVED"
    revoke = reread.post(root + "/story/claims/claim_001/numeric-series/numeric_001/revoke",
                         json={"expected_revision": saved.json()["project_revision"],
                               "operator_reason": "Withdraw synthetic evidence approval"},
                         headers={"Idempotency-Key": "revoke-numeric-series"})
    assert revoke.status_code == 200, revoke.text
    assert reread.get(root + "/story/claims/claim_001/numeric-series/numeric_001").status_code == 404


@pytest.mark.parametrize("change,expected", [
    ("unregistered_evidence", 422),
    ("wrong_g1_head", 424),
    ("duplicate_frame", 422),
    ("backward_frame", 422),
    ("wrong_end", 422),
    ("wrong_start", 422),
    ("extra_precision", 422),
    ("noncanonical_decimal", 422),
    ("stale_revision", 409),
])
def test_numeric_series_rejects_bad_transactions_without_writes(ready, change, expected):
    client, root, approved, _ = ready
    evidence, _ = _evidence(client, root, approved["project_revision"])
    assert evidence.status_code == 200, evidence.text
    rev = evidence.json()["project_revision"]
    series = _series(rev, client.get(root + "/story").json()["candidate_sha256"],
                     approved["approval_id"], evidence.json()["source_evidence_sha256"])
    if change == "unregistered_evidence":
        series["observations"][1]["source_evidence_sha256"] = "f" * 64
    elif change == "wrong_g1_head":
        series["g1_approval_id"] = "forged-gate-id"
    elif change == "duplicate_frame":
        series["observations"][1]["frame_offset"] = 0
    elif change == "backward_frame":
        series["observations"][1]["frame_offset"] = -3
    elif change == "wrong_end":
        series["end_value"] = "99"
    elif change == "wrong_start":
        series["start_value"] = "1"
    elif change == "extra_precision":
        series["observations"][1]["value"] = "50.12345"
    elif change == "noncanonical_decimal":
        series["observations"][1]["value"] = "050"
    else:
        series["expected_revision"] -= 1
    before = client.get(root).json()["project_revision"]
    result = client.post(root + "/story/claims/claim_001/numeric-series/approve",
                         json=series, headers={"Idempotency-Key": f"negative-{change}"})
    assert result.status_code == expected, result.text
    assert client.get(root).json()["project_revision"] == before
    assert client.get(root + "/story/claims/claim_001/numeric-series/numeric_001").status_code == 404
