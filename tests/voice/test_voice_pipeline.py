"""A2-01/02 behavioral voice tests: actual SQLite and FFmpeg, synthetic provider boundary only."""
import copy
import io
import json
import math
import sqlite3
import struct
import wave
from pathlib import Path

import pytest

from backend.app.contracts import ContractViolation
from backend.app.jobs.queue import JobQueue
from backend.app.projects.gates import GateService
from backend.app.projects.models import StoryCandidate
from backend.app.projects.storage import ProjectStore
from backend.app.voice import attempts
from backend.app.voice.attempts import VoiceService
from backend.app.voice.correction import inspect_wav


ROOT = Path(__file__).resolve().parents[2]


def audio_fixture(seconds=3, frequency=220):
    """Valid PCM samples, never a simulated production provider success."""
    frames = bytearray()
    for index in range(int(seconds * 24000)):
        frames += struct.pack("<h", int(3500 * math.sin(2 * math.pi * frequency * index / 24000)))
    out = io.BytesIO()
    with wave.open(out, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(frames)
    return out.getvalue()


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    story = json.loads((ROOT / "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    story["sections"][0]["narration"] = "These seven words form our short historical narration."
    story["sections"][1]["narration"] = "Another section describes the historical town and people."
    for index, claim in enumerate(story["claims"]):
        claim["critical"] = index == 0
    store = ProjectStore(tmp_path / "store.sqlite", tmp_path / "bytes")
    project = story["project"]["project_id"]
    store.create_project(project, "Voice test")
    store.import_story(StoryCandidate.parse(story), 0)
    gates = GateService(store)
    rev = gates.review_claim(project, story["claims"][0]["claim_id"], "REVIEWED",
                             "Human reviewed fixture, not real historic verification", 1)
    board = gates.board(project)[0]
    assert board["state"] == "READY_FOR_REVIEW"
    gates.decide(project, "G1", {"decision": "APPROVED",
        "candidate_sha256": board["candidate_sha256"],
        "dependency_fingerprint": board["dependency_fingerprint"], "expected_revision": rev})
    service = VoiceService(store, gates, JobQueue(store))
    monkeypatch.setattr(attempts, "_provider_identity", lambda provider: {
        "model_id": "offline-boundary-model", "output_format": "wav",
        "model_sha256": "f" * 64
    })
    return store, gates, service, project, story


def queue_one(ctx, section="sec_001", speed=1.0, key="voice-request-00001"):
    store, _, service, project, _ = ctx
    return service.enqueue(project, section, "kokoro_local", "am_adam",
                           speed, "regenerate requested section", store.revision(project), key)


def test_tts_identity_transport_rejects_invalid_or_empty_audio(ctx, monkeypatch):
    store, _, service, project, _ = ctx
    with pytest.raises(ContractViolation, match="VOICE_SPEED_SETTING_MISSING"):
        queue_one(ctx, speed=None)
    with pytest.raises(ContractViolation, match="VOICE_PROVIDER_INVALID"):
        # Bypass intentionally fake identity in the separate explicit validation case.
        monkeypatch.setattr(attempts, "_provider_identity", lambda x: (_ for _ in ()).throw(
            ContractViolation("VOICE_PROVIDER_INVALID", x, "Unknown provider")))
        queue_one(ctx)
    monkeypatch.setattr(attempts, "_provider_identity", lambda x: {
        "model_id": "offline-boundary-model", "output_format": "wav", "model_sha256": "f" * 64})
    pending = queue_one(ctx)
    assert pending["state"] == "QUEUED"
    assert service.list_attempts(project, "sec_001")["attempts"] == []
    failed = service.process_one(lambda request, identity: b"")
    assert failed["state"] == "FAILED_TERMINAL"
    assert failed["error_code"] == "PROVIDER_AUDIO_INVALID"
    assert service.list_attempts(project, "sec_001")["attempts"] == []
    queue_one(ctx, key="voice-silent-attempt-0002")
    silent = io.BytesIO()
    with wave.open(silent, "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 24000)
    failed = service.process_one(lambda request, identity: silent.getvalue())
    assert failed["state"] == "FAILED_TERMINAL" and failed["error_code"] == "VOICE_AUDIO_SILENT"
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM voice_attempts").fetchone()[0] == 0


def test_tts_transport_error_and_source_changed_cannot_commit(ctx, monkeypatch):
    store, _, service, project, story = ctx
    queue_one(ctx)
    def fail_transport(_request, _identity):
        raise ContractViolation("PROVIDER_TIMEOUT", "elevenlabs_tts", "No response")
    job = service.process_one(fail_transport)
    assert job["error_code"] == "PROVIDER_TIMEOUT" and job["state"] == "FAILED_TERMINAL"
    next_job = queue_one(ctx, key="voice-request-stale-0002")
    updated = copy.deepcopy(story)
    updated["sections"][0]["narration"] += " Correction requires new approval."
    store.import_story(StoryCandidate.parse(updated), store.revision(project))
    called = []
    result = service.process_one(lambda request, identity: called.append(True) or audio_fixture())
    assert result["state"] == "FAILED_TERMINAL"
    assert result["error_code"] in ("G1_APPROVAL_REQUIRED", "VOICE_SOURCE_STALE")
    assert not called and not service.queue.get(next_job["job_id"])["output_sha256"]


def test_regenerate_attempt_selection_restore_exact_identity(ctx):
    store, _, service, project, _ = ctx
    one = queue_one(ctx)
    assert service.process_one(lambda req, ident: audio_fixture(3))["state"] == "SUCCEEDED"
    first = service.list_attempts(project, "sec_001")["attempts"][0]
    original = store.get_artifact(first["audio_sha256"])
    assert inspect_wav(original)["sample_count"] == 72000
    queue_one(ctx, section="sec_002", key="voice-request-second-0002")
    assert service.process_one(lambda req, ident: audio_fixture(2))["state"] == "SUCCEEDED"
    second_selected = service.list_attempts(project, "sec_002")["selected_attempt_id"]
    queue_one(ctx, key="voice-request-third-0003")
    assert service.process_one(lambda req, ident: audio_fixture(4))["state"] == "SUCCEEDED"
    selected = service.list_attempts(project, "sec_001")["selected_attempt_id"]
    assert selected != first["attempt_id"]
    assert service.list_attempts(project, "sec_002")["selected_attempt_id"] == second_selected
    with pytest.raises(ContractViolation, match="VOICE_ATTEMPT_IDENTITY_CONFLICT"):
        service.restore(project, "sec_001", first["attempt_id"], "0" * 64,
                        store.revision(project), "wrong sha")
    with pytest.raises(ContractViolation, match="VOICE_ATTEMPT_NOT_FOUND"):
        service.restore(project, "sec_002", first["attempt_id"], first["audio_sha256"],
                        store.revision(project), "cross section")
    restored = service.restore(project, "sec_001", first["attempt_id"], first["audio_sha256"],
                               store.revision(project), "Restore known voice")
    assert restored["selected_attempt_id"] == first["attempt_id"]
    assert store.get_artifact(first["audio_sha256"]) == original
    assert service.list_attempts(project, "sec_002")["selected_attempt_id"] == second_selected
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM voice_selection_events WHERE project_id=?",
                          (project,)).fetchone()[0] == 4
    reopened = VoiceService(ProjectStore(store.database, store.artifacts.root),
                            GateService(store), JobQueue(store))
    assert reopened.list_attempts(project, "sec_001")["selected_attempt_id"] == first["attempt_id"]
    service.enqueue(project, "sec_001", "kokoro_local", "af_heart", 1.0,
                    "different voice", store.revision(project), "voice-different-0004")
    assert service.process_one(lambda req, ident: audio_fixture(3))["state"] == "SUCCEEDED"
    with pytest.raises(ContractViolation, match="VOICE_ATTEMPT_IDENTITY_CONFLICT"):
        service.restore(project, "sec_001", first["attempt_id"], first["audio_sha256"],
                        store.revision(project), "wrong voice lineage")


def test_correction_ffmpeg_real_samples_failure_keeps_selection(ctx, monkeypatch):
    store, _, service, project, story = ctx
    queue_one(ctx)
    assert service.process_one(lambda req, ident: audio_fixture(3))["state"] == "SUCCEEDED"
    old = service.list_attempts(project, "sec_001")["attempts"][0]
    old_wav = store.get_artifact(old["audio_sha256"])
    words = len(story["sections"][0]["narration"].split())
    measured_wpm = words * 60 / 3
    with pytest.raises(ContractViolation, match="VOICE_CORRECTION_OUT_OF_RANGE"):
        service.apply_correction(project, "sec_001", old["attempt_id"],
                                 "ffmpeg_tempo", 400, store.revision(project))
    assert service.list_attempts(project, "sec_001")["selected_attempt_id"] == old["attempt_id"]
    with pytest.raises(ContractViolation, match="VOICE_CORRECTION_METHOD_UNSUPPORTED"):
        service.apply_correction(project, "sec_001", old["attempt_id"],
                                 "regenerate_provider", measured_wpm, store.revision(project))
    # Fail FFmpeg at its process boundary without changing persisted attempt history.
    monkeypatch.setattr("backend.app.voice.correction.subprocess.run",
                        lambda *a, **kw: (_ for _ in ()).throw(OSError("ffmpeg inaccessible")))
    with pytest.raises(ContractViolation, match="VOICE_FFMPEG_FAILED"):
        service.apply_correction(project, "sec_001", old["attempt_id"],
                                 "ffmpeg_tempo", measured_wpm * 1.1, store.revision(project))
    monkeypatch.undo()
    revised = service.apply_correction(project, "sec_001", old["attempt_id"],
                                       "ffmpeg_tempo", measured_wpm * 1.1, store.revision(project))
    assert revised["audio_sha256"] != old["audio_sha256"]
    assert revised["audio"]["sample_count"] < old["sample_count"]
    assert store.get_artifact(old["audio_sha256"]) == old_wav
    assert service.list_attempts(project, "sec_001")["selected_attempt_id"] == revised["attempt_id"]
    assert {g["gate_id"]: g["state"] for g in service.gates.board(project)}["G2"] == "DRAFT"
    with sqlite3.connect(store.database) as db:
        correction = db.execute("SELECT correction_json,source_attempt_id,raw_audio_sha256 FROM voice_attempts "
                                "WHERE attempt_id=?", (revised["attempt_id"],)).fetchone()
        assert json.loads(correction[0])["method"] == "ffmpeg_tempo"
        assert correction[1] == old["attempt_id"] and correction[2] == old["raw_audio_sha256"]


def test_regenerate_http_is_durable_job_and_not_fake_voice_success(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.api.server import create_app
    story = json.loads((ROOT / "contracts/examples/longform/StoryPackage.longform.synthetic.json").read_text())
    for i, c in enumerate(story["claims"]):
        c["critical"] = i == 0
    with TestClient(create_app(tmp_path / "s.sqlite", tmp_path / "artifacts")) as client:
        created = client.post("/api/v1/projects", json={"title": "Voice integration"}).json()
        project = created["project_id"]
        story["project"]["project_id"] = project
        root = f"/api/v1/projects/{project}"
        response = client.post(root + "/story/import?expected_revision=0", json=story,
                               headers={"Idempotency-Key": "voice-approval-story-000"})
        assert response.status_code == 200
        reviewed = client.post(root + "/story/claims/" + story["claims"][0]["claim_id"] + "/review",
                               json={"expected_revision": 1, "status": "REVIEWED",
                                     "evidence_note": "Operator reviewed controlled fixture"},
                               headers={"Idempotency-Key": "voice-approval-review-000"})
        assert reviewed.status_code == 200
        gate = client.get(root + "/gates").json()[0]
        assert client.post(root + "/gates/G1/decision", json={
            "decision": "APPROVED", "candidate_sha256": gate["candidate_sha256"],
            "dependency_fingerprint": gate["dependency_fingerprint"], "expected_revision": 2
        }, headers={"Idempotency-Key": "voice-approval-decision-000"}).status_code == 200
        # TestClient BackgroundTask performs a real job transition but only a synthetic
        # provider response, clearly not a live TTS call.
        monkeypatch.setattr(attempts, "_provider_identity", lambda provider: {
            "model_id": "offline-model", "output_format": "wav"})
        monkeypatch.setattr(attempts, "_synthesize", lambda *args: audio_fixture(2))
        section = "sec_001"
        url = root + f"/voice/sections/{section}/regenerate"
        payload = {"expected_revision": 3, "provider_id": "kokoro_local",
                   "voice_id": "am_adam", "reason": "offline integration", "speed": 1.0}
        queued = client.post(url, json=payload, headers={"Idempotency-Key": "voice-api-generate-001"})
        assert queued.status_code == 202 and queued.json()["job_id"].startswith("job_")
        job = client.get("/api/v1/jobs/" + queued.json()["job_id"]).json()
        assert job["state"] == "SUCCEEDED" and job["output_sha256"]
        listed = client.get(root + f"/voice/sections/{section}/attempts")
        assert listed.status_code == 200 and len(listed.json()["attempts"]) == 1
        assert client.post(url, json=payload,
                           headers={"Idempotency-Key": "voice-api-generate-001"}).json()["job_id"] == queued.json()["job_id"]
        assert client.post(url, json={**payload, "voice_id": "different"},
                           headers={"Idempotency-Key": "voice-api-generate-001"}).status_code == 409
        wrong = client.post(root + f"/voice/sections/sec_002/select-attempt",
                            json={"expected_revision": 4, "attempt_id": listed.json()["selected_attempt_id"],
                                  "expected_audio_sha256": job["output_sha256"]},
                            headers={"Idempotency-Key": "voice-api-restore-000"})
        assert wrong.status_code == 404
        updated = copy.deepcopy(story)
        updated["sections"][1]["narration"] += " The archive source has changed."
        replaced = client.post(root + "/story/import?expected_revision=4", json=updated,
                               headers={"Idempotency-Key": "voice-story-replaced-0002"})
        assert replaced.status_code == 200
        history = client.get(root + f"/voice/sections/{section}/attempts")
        assert history.status_code == 200
        assert history.json()["selected_attempt_id"] == listed.json()["selected_attempt_id"]
        assert history.json()["attempts"][0]["compatible_source"] is False
        rejected = client.post(root + f"/voice/sections/{section}/select-attempt",
                               json={"expected_revision": 5,
                                     "attempt_id": listed.json()["selected_attempt_id"],
                                     "expected_audio_sha256": job["output_sha256"]},
                               headers={"Idempotency-Key": "voice-stale-restore-0003"})
        assert rejected.status_code == 424


def test_tts_elevenlabs_http_boundary_identity_and_quota(monkeypatch):
    from backend.app.voice.providers import elevenlabs
    import httpx
    monkeypatch.setenv("HVS_ELEVENLABS_MODEL_ID", "operator-selected-model")
    monkeypatch.setenv("HVS_ELEVENLABS_API_KEY", "local-test-placeholder")
    settings = elevenlabs.identity()
    assert settings["model_id"] == "operator-selected-model"
    observed = []
    def responder(url, **kwargs):
        observed.append((url, kwargs))
        return httpx.Response(429, headers={"content-type": "application/json"},
                              request=httpx.Request("POST", url), json={"detail": "quota"})
    monkeypatch.setattr(elevenlabs.httpx, "post", responder)
    with pytest.raises(ContractViolation, match="PROVIDER_QUOTA_EXCEEDED"):
        elevenlabs.synthesize("Not sent to the real network.", "explicit-voice-id", 1.0, settings)
    assert "/v1/text-to-speech/explicit-voice-id" in observed[0][0]
    assert observed[0][1]["json"]["model_id"] == "operator-selected-model"
    assert observed[0][1]["json"]["voice_settings"]["speed"] == 1.0
    with pytest.raises(ContractViolation, match="VOICE_SPEED_UNSUPPORTED"):
        elevenlabs.synthesize("Text", "explicit-voice-id", 1.9, settings)


def test_tts_kokoro_local_worker_timeout_and_missing_assets(tmp_path, monkeypatch):
    from backend.app.voice.providers import kokoro
    import subprocess
    monkeypatch.setenv("HVS_KOKORO_MODEL_PATH", str(tmp_path / "wrong-model.onnx"))
    monkeypatch.setenv("HVS_KOKORO_VOICES_PATH", str(tmp_path / "voices-v1.0.bin"))
    with pytest.raises(ContractViolation, match="KOKORO_ASSETS_MISSING"):
        kokoro.identity()
    model = tmp_path / "kokoro-v1.0.onnx"
    voices = tmp_path / "voices-v1.0.bin"
    model.write_bytes(b"test-model-fixture")
    voices.write_bytes(b"test-voice-fixture")
    monkeypatch.setenv("HVS_KOKORO_MODEL_PATH", str(model))
    monkeypatch.setenv("HVS_KOKORO_VOICES_PATH", str(voices))
    settings = kokoro.identity()
    assert settings["model_id"] == "kokoro-v1.0" and len(settings["model_sha256"]) == 64
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("test", 180)
    monkeypatch.setattr(kokoro.subprocess, "run", timeout)
    with pytest.raises(ContractViolation, match="PROVIDER_TIMEOUT"):
        kokoro.synthesize("Offline test sample.", "am_adam", 1.0, settings)


def test_gate_state_first_voice_and_unapproved_candidate_invalidation(ctx):
    """V01/V02/V04/V05/V06/V08/V11: selecting audio never creates a fake prior G2/G4/G5 approval."""
    store, gates, voice, project, _ = ctx
    assert {g["gate_id"]: g["state"] for g in gates.board(project)} == {
        "G1": "APPROVED", "G2": "DRAFT", "G3": "DRAFT", "G4": "DRAFT", "G5": "DRAFT"}
    queue_one(ctx)
    assert voice.process_one(lambda req, settings: audio_fixture())["state"] == "SUCCEEDED"
    board = {g["gate_id"]: g["state"] for g in gates.board(project)}
    assert board["G1"] == "APPROVED" and board["G3"] == "DRAFT"
    assert all(board[gate] == "DRAFT" for gate in ("G2", "G4", "G5"))
    old = voice.list_attempts(project, "sec_001")["selected_attempt_id"]
    artifact = store.put_artifact(b"unapproved G2 candidate", "voice_candidate")
    gates.publish_candidate(project, "G2", artifact, "0" * 64, store.revision(project))
    queue_one(ctx, section="sec_002", key="voice-gate-second-001")
    assert voice.process_one(lambda req, settings: audio_fixture(2))["state"] == "SUCCEEDED"
    assert gates.board(project)[1]["state"] == "DRAFT"
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM gate_candidates WHERE project_id=? AND gate_id='G2'",
                          (project,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM gate_staleness WHERE project_id=? AND gate_id IN ('G2','G4','G5')",
                          (project,)).fetchone()[0] == 0
    assert store.get_artifact(artifact) == b"unapproved G2 candidate"
    # Repair legacy false markers when a genuinely fresh owner candidate arrives.
    with store._transaction() as db:
        db.execute("INSERT INTO gate_staleness VALUES(?,?,?)", (project, "G2", "voice_audio"))
    new_candidate = store.put_artifact(b"new G2 review draft", "voice_candidate")
    gates.publish_candidate(project, "G2", new_candidate, "1" * 64, store.revision(project))
    assert gates.board(project)[1]["state"] == "READY_FOR_REVIEW"
    assert voice.list_attempts(project, "sec_001")["selected_attempt_id"] == old
    assert {g["gate_id"]: g["state"] for g in gates.board(project)}["G4"] == "DRAFT"


def test_history_read_independent_of_g1_and_story_sha(ctx):
    """V13–V19: read only persists across G1 invalidation; restore and correction still fail closed."""
    store, gates, voice, project, story = ctx
    queue_one(ctx)
    assert voice.process_one(lambda req, ident: audio_fixture())["state"] == "SUCCEEDED"
    old = voice.list_attempts(project, "sec_001")["attempts"][0]
    with sqlite3.connect(store.database) as db:
        count = db.execute("SELECT COUNT(*) FROM voice_selection_events").fetchone()[0]
    replacement = copy.deepcopy(story)
    replacement["sections"][1]["narration"] += " Later evidence changes the overall story hash."
    store.import_story(StoryCandidate.parse(replacement), store.revision(project))
    assert gates.board(project)[0]["state"] != "APPROVED"
    history = voice.list_attempts(project, "sec_001")
    assert history["selected_attempt_id"] == old["attempt_id"]
    assert len(history["attempts"]) == 1
    assert history["attempts"][0]["compatible_source"] is False
    assert history["attempts"][0]["story_sha256"] == old["story_sha256"]
    assert history["attempts"][0]["text_sha256"] == old["text_sha256"]
    with pytest.raises(ContractViolation, match="G1_APPROVAL_REQUIRED"):
        voice.restore(project, "sec_001", old["attempt_id"], old["audio_sha256"],
                      store.revision(project), "try stale restore")
    with pytest.raises(ContractViolation, match="G1_APPROVAL_REQUIRED"):
        voice.apply_correction(project, "sec_001", old["attempt_id"], "ffmpeg_tempo",
                               150, store.revision(project))
    with pytest.raises(ContractViolation, match="G1_APPROVAL_REQUIRED"):
        queue_one(ctx, key="voice-invalid-g1-001")
    assert not voice.list_attempts(project, "sec_002")["attempts"]
    # Review and approve replacement: identical narration text does NOT revive old source SHA.
    review_revision = gates.review_claim(project, replacement["claims"][0]["claim_id"],
                                         "REVIEWED", "Human reviewed replacement", store.revision(project))
    approved_board = gates.board(project)[0]
    assert approved_board["state"] == "READY_FOR_REVIEW"
    gates.decide(project, "G1", {"decision": "APPROVED",
        "candidate_sha256": approved_board["candidate_sha256"],
        "dependency_fingerprint": approved_board["dependency_fingerprint"],
        "expected_revision": review_revision})
    assert gates.board(project)[0]["state"] == "APPROVED"
    assert voice.list_attempts(project, "sec_001")["attempts"][0]["compatible_source"] is False
    with pytest.raises(ContractViolation, match="VOICE_SOURCE_STALE"):
        voice.restore(project, "sec_001", old["attempt_id"], old["audio_sha256"],
                      store.revision(project), "old story restore forbidden")
    with pytest.raises(ContractViolation, match="PROJECT_NOT_FOUND"):
        voice.list_attempts("proj_no_such", "sec_001")
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM voice_selection_events").fetchone()[0] == count
    assert VoiceService(ProjectStore(store.database, store.artifacts.root),
                        GateService(store), JobQueue(store)).list_attempts(project, "sec_001")["attempts"][0][
                            "compatible_source"] is False
    changed_narration = copy.deepcopy(replacement)
    changed_narration["sections"][0]["narration"] += " A new voice source now exists."
    store.import_story(StoryCandidate.parse(changed_narration), store.revision(project))
    assert voice.list_attempts(project, "sec_001")["attempts"][0]["compatible_source"] is False
    without_section = copy.deepcopy(changed_narration)
    without_section["sections"] = [s for s in without_section["sections"] if s["section_id"] != "sec_001"]
    without_section["visual_setups"] = [
        setup for setup in without_section["visual_setups"] if "sec_001" not in setup["section_refs"]]
    store.import_story(StoryCandidate.parse(without_section), store.revision(project))
    history_without_section = voice.list_attempts(project, "sec_001")
    assert len(history_without_section["attempts"]) == 1
    assert history_without_section["attempts"][0]["compatible_source"] is False
    with pytest.raises(ContractViolation, match="VOICE_SECTION_NOT_FOUND"):
        voice.list_attempts(project, "sec_nonexistent")


def test_previously_approved_head_only_is_genuinely_stale(ctx):
    """V10/V12: simulated historical approved heads, not fabricated operator acceptance."""
    store, gates, voice, project, _ = ctx
    artifact = store.put_artifact(b"future stage candidate", "voice_candidate")
    with store._transaction() as db:
        for gate in ("G2", "G4", "G5"):
            db.execute("INSERT INTO gate_heads VALUES(?,?,?,?,?)",
                       (project, gate, artifact, "a" * 64, "synthetic_history_" + gate))
    queue_one(ctx)
    assert voice.process_one(lambda req, ident: audio_fixture())["state"] == "SUCCEEDED"
    state = {gate["gate_id"]: gate["state"] for gate in gates.board(project)}
    assert state == {"G1": "APPROVED", "G2": "STALE", "G3": "DRAFT",
                     "G4": "STALE", "G5": "STALE"}
    with sqlite3.connect(store.database) as db:
        assert {r[0] for r in db.execute("SELECT gate_id FROM gate_staleness WHERE project_id=?",
                                         (project,))} == {"G2", "G4", "G5"}
    queue_one(ctx, key="voice-second-approved-head-0002")
    assert voice.process_one(lambda req, ident: audio_fixture(2))["state"] == "SUCCEEDED"
    assert gates.board(project)[1]["state"] == "STALE"  # never silently clear a real stale head


def test_gate_2_final_wav_assemble_alignment_and_cold_reopen(tmp_path):
    """A2-03/04: selected 2 sections -> G2 intent -> actual sample offsets -> provider word map."""
    from backend.tools.voice_final_smoke import setup,approval,mock_alignment
    from backend.app.voice.correction import inspect_wav
    from backend.app.voice.workflow import FinalVoiceWorkflow
    store,gates,voice,workflow,project,story=setup(tmp_path)
    first=voice.list_attempts(project,"sec_001")["attempts"][0]
    original=store.get_artifact(first["audio_sha256"])
    gate=gates.board(project)[1]
    assert gate["state"]=="READY_FOR_REVIEW"
    decision=approval(store,gates,project)
    assert decision["state"]=="APPROVED"
    with pytest.raises(ContractViolation,match="GATE_ILLEGAL_TRANSITION|APPROVAL_REVISION_CONFLICT"):
        gates.decide(project,"G2",{"decision":"APPROVED",
            "candidate_sha256":gate["candidate_sha256"],
            "dependency_fingerprint":gate["dependency_fingerprint"],
            "expected_revision":store.revision(project)})
    assert workflow.status(project)["final_audio"] is None
    assert workflow.status(project)["g4_ready_dependency"] is False
    completed=workflow.process_one()
    assert completed["state"]=="SUCCEEDED"
    current=workflow.status(project)
    final=current["final_audio"]
    offsets=final["section_offsets"]
    assert len(offsets)==2 and offsets[0]["start_sample"]==0
    assert offsets[0]["end_sample"]==offsets[1]["start_sample"]
    assert offsets[-1]["end_sample"]==final["duration_samples"]
    assert inspect_wav(store.get_artifact(final["audio_sha256"]))["sample_count"]==final["duration_samples"]
    assert store.get_artifact(first["audio_sha256"])==original
    assert current["g4_ready_dependency"] is False
    # An owner draft alone cannot make G4 eligible before verified alignment.
    draft=store.put_artifact(b"unapproved G4 candidate bytes","voice_candidate")
    gates.publish_candidate(project,"G4",draft,"b"*64,store.revision(project))
    assert gates.board(project)[3]["state"]=="BLOCKED"
    assert "WORD_MAP_MISSING_OR_STALE" in gates.board(project)[3]["blockers"]
    failed=workflow.process_one(lambda *_:{"words":[]})
    assert failed["state"]=="FAILED_TERMINAL" and failed["error_code"]=="ALIGNMENT_TRANSCRIPT_MISMATCH"
    assert workflow.status(project)["word_map"] is None
    with pytest.raises(ContractViolation,match="ALIGNMENT_RETRY_FORBIDDEN"):
        # Cannot queue duplicate alignment while an existing retry is already queued.
        workflow.retry_alignment(project,store.revision(project),final["audio_sha256"],
                                 final["transcript_sha256"],"new-retry-duplicate-000")
        workflow.retry_alignment(project,store.revision(project),final["audio_sha256"],
                                 final["transcript_sha256"],"another-retry-duplicate")
    done=workflow.process_one(lambda audio,text:mock_alignment(final,text))
    assert done["state"]=="SUCCEEDED",done
    stable=workflow.status(project)
    assert stable["g4_ready_dependency"]
    assert gates.board(project)[3]["state"]=="READY_FOR_REVIEW"
    words=stable["word_map"]["words"]
    assert len(words)==len("\n".join(s["narration"] for s in story["sections"]).split())
    assert all(words[i]["end_sample"]<=words[i+1]["start_sample"] for i in range(len(words)-1))
    reopened=FinalVoiceWorkflow(ProjectStore(store.database,store.artifacts.root),
                                GateService(store),JobQueue(store))
    assert reopened.status(project)["word_map"]==stable["word_map"]
    queue_one_ctx=(store,gates,voice,project,story)
    from unittest.mock import patch
    with patch.object(attempts,"_provider_identity",return_value={"model_id":"fixture_only"}):
        voice.enqueue(project,"sec_001","kokoro_local","am_adam",1.0,
                      "new selection",store.revision(project),"new-voice-after-g2")
        assert voice.process_one(lambda *_:audio_fixture(2))["state"]=="SUCCEEDED"
    assert gates.board(project)[1]["state"] in ("STALE","READY_FOR_REVIEW")
    with store._connection() as db:
        assert db.execute("SELECT cause FROM gate_staleness WHERE project_id=? AND gate_id='G2'",
                          (project,)).fetchone()[0]=="voice_audio"
    assert workflow.status(project)["g4_ready_dependency"] is False
    assert store.get_artifact(final["audio_sha256"])  # historical bytes still immutable


def test_gate_2_missing_selection_and_corrupt_wav_block_before_approval(tmp_path):
    """A2-03: no authorization/job or partial output on incomplete/corrupt selection."""
    from backend.tools.voice_final_smoke import setup
    store,gates,voice,workflow,project,_=setup(tmp_path)
    selected=voice.list_attempts(project,"sec_002")["selected_attempt_id"]
    with store._transaction() as db:
        db.execute("DELETE FROM voice_selected WHERE project_id=? AND section_id=?",(project,"sec_002"))
    assert gates.board(project)[1]["state"]=="DRAFT"
    with pytest.raises(ContractViolation,match="GATE_ILLEGAL_TRANSITION"):
        gates.decide(project,"G2",{"decision":"APPROVED","candidate_sha256":"0"*64,
          "dependency_fingerprint":"0"*64,"expected_revision":store.revision(project)})
    with store._transaction() as db:
        db.execute("INSERT INTO voice_selected VALUES(?,?,?)",(project,"sec_002",selected))
    a=voice.list_attempts(project,"sec_001")["attempts"][0]
    store.artifacts.path(a["audio_sha256"]).write_bytes(b"corrupted")
    board=gates.board(project)[1]
    with pytest.raises(ContractViolation,match="ARTIFACT_CORRUPT|VOICE_AUDIO_INVALID"):
        gates.decide(project,"G2",{"decision":"APPROVED",
           "candidate_sha256":board["candidate_sha256"],"dependency_fingerprint":board["dependency_fingerprint"],
           "expected_revision":store.revision(project)})
    assert workflow.status(project)["final_audio"] is None
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM gate_events WHERE gate_id='G2'").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM jobs WHERE kind='final_assembly'").fetchone()[0]==0


def test_alignment_word_map_rejects_malformed_overlap_and_wrong_section(tmp_path):
    from backend.tools.voice_final_smoke import setup,approval,mock_alignment
    from backend.app.voice.word_map import word_map
    from backend.app.voice.alignment import align_audio
    import httpx
    store,gates,voice,workflow,project,story=setup(tmp_path)
    approval(store,gates,project);workflow.process_one()
    final=workflow.status(project)["final_audio"]
    transcript="\n".join(s["narration"] for s in story["sections"])
    answer=mock_alignment(final,transcript)
    broken=copy.deepcopy(answer);broken["words"][0]["end"]=broken["words"][1]["end"]+1
    with pytest.raises(ContractViolation,match="ALIGNMENT_TIME_INVALID"):
        word_map(project,final,transcript,broken,story["sections"])
    broken=copy.deepcopy(answer);broken["words"][0]["text"]="unrelated"
    with pytest.raises(ContractViolation,match="ALIGNMENT_TRANSCRIPT_MISMATCH"):
        word_map(project,final,transcript,broken,story["sections"])
    broken=copy.deepcopy(answer);broken["words"][0]["start"]=-1.0
    with pytest.raises(ContractViolation,match="ALIGNMENT_TIME_INVALID"):
        word_map(project,final,transcript,broken,story["sections"])
    from backend.app.voice import alignment
    from unittest.mock import patch
    with patch.dict("os.environ",{"HVS_ELEVENLABS_API_KEY":"offline-test-token"}):
        with patch.object(alignment.httpx,"post",return_value=httpx.Response(
                401,request=httpx.Request("POST","https://api.elevenlabs.io/v1/forced-alignment"))):
            with pytest.raises(ContractViolation,match="PROVIDER_AUTH_FAILED"):
                align_audio(store.get_artifact(final["audio_sha256"]),transcript)
    with patch.dict("os.environ",{"HVS_ELEVENLABS_API_KEY":""}):
        with pytest.raises(ContractViolation,match="PROVIDER_CREDENTIALS_MISSING"):
            align_audio(store.get_artifact(final["audio_sha256"]),transcript)


def test_alignment_api_status_and_media_bytes_on_real_store(tmp_path):
    from backend.tools.voice_final_smoke import setup,approval
    from fastapi.testclient import TestClient
    from backend.app.api.server import create_app
    store,gates,voice,workflow,project,story=setup(tmp_path)
    approved=approval(store,gates,project)
    with TestClient(create_app(store.database,store.artifacts.root)) as client:
        base="/api/v1/projects/"+project+"/voice"
        assert client.get(base+"/alignment").json()["final_audio"] is None
        assert workflow.process_one()["state"]=="SUCCEEDED"
        metadata=client.get(base+"/alignment").json()
        final=metadata["final_audio"]
        assert metadata["g4_ready_dependency"] is False
        # S11: identical WAV with another transcript must never inherit a prior word map.
        with store._transaction() as db:
            db.execute("INSERT INTO word_maps VALUES(?,?,?,?,?,?,?)",
                       (approved["approval_id"],project,final["audio_sha256"],"0"*64,"1"*64,"{}",
                        "wrong-transcript-mock-job"))
        incompatible=client.get(base+"/alignment")
        assert incompatible.status_code==200
        assert incompatible.json()["word_map"] is None
        assert incompatible.json()["g4_ready_dependency"] is False
        # These are two *independent* malformed-fixture scenarios for the same
        # approval. Only one immutable map lineage per approval may exist.
        with store._transaction() as db:
            db.execute("DELETE FROM word_maps WHERE approval_id=?", (approved["approval_id"],))
        # A schema-valid map inserted without a successfully owned alignment job is
        # not provider evidence and must not unlock the G4 dependency.
        from backend.tools.voice_final_smoke import mock_alignment
        from backend.app.voice.word_map import word_map
        from backend.app.voice.assemble import canonical,sha
        transcript="\n".join(s["narration"] for s in story["sections"])
        forged=word_map(project,final,transcript,mock_alignment(final,transcript),story["sections"])
        doc=canonical(forged)
        digest=store.put_artifact(doc,"word_map")
        with store._transaction() as db:
            db.execute("INSERT INTO word_maps VALUES(?,?,?,?,?,?,?)",
                       (approved["approval_id"],project,final["audio_sha256"],final["transcript_sha256"],
                        digest,doc.decode("utf-8"),"no_successful_provider_job"))
        assert client.get(base+"/alignment").json()["g4_ready_dependency"] is False
        assert client.get(base+"/alignment").json()["word_map"] is None
        assert client.get(base+"/audio/"+final["audio_sha256"]).content==store.get_artifact(final["audio_sha256"])
        assert client.get("/api/v1/projects/proj_foreign/voice/audio/"+final["audio_sha256"]).status_code==404
        assert client.get(base+"/audio/"+"0"*64).status_code==404
        assert client.post(base+"/alignment/retry",json={
            "expected_revision":store.revision(project),"audio_sha256":final["audio_sha256"],
            "transcript_sha256":final["transcript_sha256"]},headers={
            "Idempotency-Key":"should-not-retry-active"}).status_code in (409,422)


def test_gate_2_technical_assembly_retry_preserves_original_approval(tmp_path):
    """A2-03 failure/recovery: blocked/failed jobs can be retried without another G2 approval."""
    from backend.tools.voice_final_smoke import setup,approval
    store,gates,voice,workflow,project,story=setup(tmp_path)
    accepted=approval(store,gates,project)
    leased=workflow.queue.claim("final_assembly")
    assert leased and leased["job_id"]==accepted["job_id"]
    workflow.queue.fail(leased["job_id"],leased["lease_token"],"FINAL_AUDIO_ASSEMBLY_FAILED",False)
    revision=store.revision(project)
    retry=workflow.retry_assembly(project,revision,"manual-technical-retry-001")
    assert retry != accepted["job_id"] and store.revision(project)==revision
    assert workflow.process_one()["state"]=="SUCCEEDED"
    assert workflow.status(project)["final_audio"]
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM gate_events WHERE project_id=? AND gate_id='G2'",
                          (project,)).fetchone()[0]==1
    with pytest.raises(ContractViolation,match="FINAL_AUDIO_RETRY_FORBIDDEN"):
        workflow.retry_assembly(project,store.revision(project),"invalid-second-technical-retry")


def test_gate_2_reapproval_after_restore_same_wav_keeps_distinct_alignment_lineage(tmp_path):
    """R01/C02-C06: A→B→A is a new review, never automatic old approval."""
    from unittest.mock import patch
    from backend.tools.voice_final_smoke import setup, approval, mock_alignment, wav_fixture
    from backend.app.voice.workflow import FinalVoiceWorkflow
    store, gates, voice, workflow, project, story = setup(tmp_path)
    first = voice.list_attempts(project, "sec_001")["attempts"][0]
    old_candidate = gates.board(project)[1]
    initial = approval(store, gates, project)
    assert workflow.process_one()["state"] == "SUCCEEDED"
    frozen = workflow.status(project)["final_audio"]
    assert workflow.process_one(lambda wav, txt: mock_alignment(frozen, txt))["state"] == "SUCCEEDED"
    first_map = workflow.status(project)["word_map"]
    with patch.object(attempts, "_provider_identity", return_value={"model_id": "fixture_only"}):
        voice.enqueue(project, "sec_001", "kokoro_local", "am_adam", 1.0,
                      "new B voice", store.revision(project), "reapproval-voice-change-b")
        assert voice.process_one(lambda *_: wav_fixture(2))["state"] == "SUCCEEDED"
    # The old approval must not authorize B; a fresh B candidate may already
    # be READY_FOR_REVIEW rather than displaying a stale historical candidate.
    assert gates.board(project)[1]["state"] in ("STALE", "READY_FOR_REVIEW")
    from backend.app.voice.workflow import word_map_source_current
    with store._connection() as db:
        assert word_map_source_current(db, project) is False
    b = voice.list_attempts(project, "sec_001")["selected_attempt_id"]
    voice.restore(project, "sec_001", first["attempt_id"], first["audio_sha256"],
                  store.revision(project), "restore original A")
    state = gates.board(project)[1]
    assert state["state"] == "READY_FOR_REVIEW"
    current_id = state["candidate_sha256"]
    assert voice.list_attempts(project, "sec_001")["selected_attempt_id"] != b
    with pytest.raises(ContractViolation, match="APPROVAL_REVISION_CONFLICT"):
        gates.decide(project, "G2", {"decision": "APPROVED",
            "candidate_sha256": old_candidate["candidate_sha256"],
            "dependency_fingerprint": old_candidate["dependency_fingerprint"],
            "expected_revision": store.revision(project)})
    renewed = approval(store, gates, project)
    assert renewed["approval_id"] != initial["approval_id"]
    assert workflow.process_one()["state"] == "SUCCEEDED"
    second = workflow.status(project)["final_audio"]
    assert second["audio_sha256"] == frozen["audio_sha256"]
    assert second["transcript_sha256"] == frozen["transcript_sha256"]
    assert workflow.status(project)["g4_ready_dependency"] is False
    assert workflow.process_one(lambda wav, txt: mock_alignment(second, txt))["state"] == "SUCCEEDED"
    assert workflow.status(project)["g4_ready_dependency"]
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM gate_events WHERE project_id=? AND gate_id='G2'", (project,)).fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM final_audio WHERE project_id=?", (project,)).fetchone()[0] == 2
    assert first_map == workflow.status(project)["word_map"]
    assert current_id != "0"*64


@pytest.mark.parametrize("first,second", [
    ("First word.\n\nAgain word, word.", "Later again."),
    ("First word.\r\nAgain word, word.", "Later\r\nagain."),
    ("First\n\nword.", "Word,\nagain.\nFinal word.")
])
def test_alignment_multiline_uses_frozen_section_manifest(tmp_path, first, second):
    """R02/C08-C13: embedded CRLF and blank lines never become artificial section boundaries."""
    from backend.tools.voice_final_smoke import setup, approval
    from backend.app.voice.word_map import word_map
    from backend.app.voice.assemble import transcript_for
    from backend.app.voice.assemble import sha
    import copy
    store, gates, voice, workflow, project, story = setup(tmp_path, (first, second))
    final_audio = {"audio_sha256": "a"*64, "transcript_sha256": sha((first+"\n"+second).encode()),
                   "sample_rate": 24000, "duration_samples": 144000,
                   "section_offsets": [
                      {"section_id":"sec_001","start_sample":0,"end_sample":60000},
                      {"section_id":"sec_002","start_sample":60000,"end_sample":144000}]}
    sections=[{"section_id":"sec_001","narration":first},
              {"section_id":"sec_002","narration":second}]
    transcript=transcript_for(sections)
    provider_words=[]
    for s,off in zip(sections,final_audio["section_offsets"]):
        words=s["narration"].split()
        width=off["end_sample"]-off["start_sample"]
        for i,w in enumerate(words):
            a=off["start_sample"]+round(width*(i+.05)/len(words))
            b=off["start_sample"]+round(width*(i+.75)/len(words))
            provider_words.append({"text":w,"start":a/24000,"end":b/24000,"loss":0.1})
    mapped=word_map(project,final_audio,transcript,{"words":provider_words},sections)
    # Same texts through approved G2 assembly and a provider-shaped response:
    # real WAV sample offsets and frozen section texts must survive SQLite reopen.
    from backend.tools.voice_final_smoke import approval
    approval(store,gates,project)
    assert workflow.process_one()["state"]=="SUCCEEDED"
    actual=workflow.status(project)["final_audio"]
    assert actual["duration_samples"]==144000
    assert actual["transcript_sha256"]==final_audio["transcript_sha256"]
    assert actual["section_offsets"]==final_audio["section_offsets"]
    assert workflow.process_one(lambda wav,txt:{"words":provider_words})["state"]=="SUCCEEDED"
    actual_map=word_map(project,actual,transcript,{"words":provider_words},sections)
    assert workflow.status(project)["word_map"]==actual_map
    reopened=__import__("backend.app.voice.workflow",fromlist=["FinalVoiceWorkflow"]).FinalVoiceWorkflow(
        ProjectStore(store.database,store.artifacts.root),GateService(store),JobQueue(store))
    assert reopened.status(project)["word_map"]==actual_map
    assert len(mapped["words"])==len(first.split())+len(second.split())
    assert [x["section_id"] for x in mapped["words"]] == (
        ["sec_001"]*len(first.split())+["sec_002"]*len(second.split()))
    bad=copy.deepcopy(provider_words)
    bad[0]["text"]="wrong"
    with pytest.raises(ContractViolation, match="ALIGNMENT_TRANSCRIPT_MISMATCH"):
        word_map(project,final_audio,transcript,{"words":bad},sections)
    bad=copy.deepcopy(provider_words)
    bad[len(first.split())-1]["end"]=60001/24000
    with pytest.raises(ContractViolation, match="ALIGNMENT_SECTION_MISMATCH|ALIGNMENT_TIME_INVALID"):
        word_map(project,final_audio,transcript,{"words":bad},sections)


def test_exact_job_background_chain_skips_other_queued_assemblies(tmp_path):
    """R03/C14-C16: two real project G2 approvals, exact independent job lineage."""
    from unittest.mock import patch
    from backend.tools.voice_final_smoke import setup, approval, mock_alignment, wav_fixture
    from backend.app.projects.models import StoryCandidate
    store,gates,voice,workflow,project,story=setup(tmp_path)
    other="proj_queued_other"
    other_story=copy.deepcopy(story)
    other_story["project"]["project_id"]=other
    store.create_project(other,"Earlier approved independent voice project")
    store.import_story(StoryCandidate.parse(other_story),0)
    g1=gates.board(other)[0]
    gates.decide(other,"G1",{"decision":"APPROVED",
        "candidate_sha256":g1["candidate_sha256"],
        "dependency_fingerprint":g1["dependency_fingerprint"],
        "expected_revision":store.revision(other)})
    with patch.object(attempts,"_provider_identity",return_value={"model_id":"fixture_only"}):
        for section,duration in zip(other_story["sections"],(2.5,3.5)):
            voice.enqueue(other,section["section_id"],"kokoro_local","am_adam",1.0,
                          "synthetic other project",store.revision(other),
                          "other-project-"+section["section_id"]+"-tts")
            assert voice.process_one(lambda req,ident,seconds=duration:wav_fixture(seconds))["state"]=="SUCCEEDED"
    other_decision=approval(store,gates,other)
    decision=approval(store,gates,project)
    workflow.process_pending(decision["job_id"],
        provider=lambda wav,transcript:mock_alignment(workflow.status(project)["final_audio"],transcript))
    assert workflow.status(project)["g4_ready_dependency"] is True
    assert workflow.queue.get(other_decision["job_id"])["state"]=="QUEUED"
    assert workflow.queue.get(decision["job_id"])["state"]=="SUCCEEDED"
    assert workflow.status(other)["final_audio"] is None
    workflow.process_pending(other_decision["job_id"],
        provider=lambda wav,transcript:mock_alignment(workflow.status(other)["final_audio"],transcript))
    assert workflow.status(other)["g4_ready_dependency"] is True
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs WHERE kind='final_alignment'").fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM gate_events WHERE gate_id='G2'").fetchone()[0]==2
    workflow.process_pending(decision["job_id"],provider=lambda *_:pytest.fail("duplicate provider call"))
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs WHERE kind='final_alignment'").fetchone()[0]==2
