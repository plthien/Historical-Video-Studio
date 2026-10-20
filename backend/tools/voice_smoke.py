"""A2 owner smoke: real SQLite/FFmpeg; live provider only with operator settings."""
from __future__ import annotations

import io
import json
import math
import struct
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

from backend.app.contracts import ContractViolation
from backend.app.jobs.queue import JobQueue
from backend.app.projects.gates import GateService
from backend.app.projects.models import StoryCandidate
from backend.app.projects.storage import ProjectStore
from backend.app.voice.attempts import VoiceService


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "contracts/examples/longform/StoryPackage.longform.synthetic.json"


def _fixture_wav():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(24000)
        writer.writeframes(b"".join(struct.pack("<h", int(2800 * math.sin(2 * math.pi * 210 * i / 24000)))
                                    for i in range(24000 * 3)))
    return buffer.getvalue()


def run(case: str, mode: str) -> None:
    if mode == "live" and case == "section-repair":
        raise SystemExit("section-repair must run --mode local")
    if mode == "local" and case != "section-repair":
        raise SystemExit("Live TTS cases must use --mode live; no provider simulation as LIVE_PASS.")
    story = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if mode == "local":
        story["sections"][0]["narration"] = "These seven words form our short historical narration."
    for index, claim in enumerate(story["claims"]):
        claim["critical"] = index == 0
    with tempfile.TemporaryDirectory() as root:
        base = Path(root)
        store = ProjectStore(base / "voice.sqlite", base / "media")
        project_id = story["project"]["project_id"]
        store.create_project(project_id, "Controlled voice smoke")
        store.import_story(StoryCandidate.parse(story), 0)
        gates = GateService(store)
        rev = gates.review_claim(project_id, story["claims"][0]["claim_id"], "REVIEWED",
                                 "Fixture review only; not historical verification", 1)
        board = gates.board(project_id)[0]
        gates.decide(project_id, "G1", {"decision": "APPROVED",
                     "candidate_sha256": board["candidate_sha256"],
                     "dependency_fingerprint": board["dependency_fingerprint"], "expected_revision": rev})
        queue = JobQueue(store)
        voice = VoiceService(store, gates, queue)
        provider = "kokoro_local" if case in ("tts-kokoro", "section-repair") else "elevenlabs_tts"
        ident = {"model_id": "synthetic-offline-smoke"} if mode == "local" else None
        try:
            if mode == "local":
                with patch("backend.app.voice.attempts._provider_identity", return_value=ident):
                    request = voice.enqueue(project_id, "sec_001", provider, "am_adam",
                                            1.0, "controlled section repair", store.revision(project_id),
                                            "controlled-smoke-section")
                    result = voice.process_one(lambda req, metadata: _fixture_wav())
            else:
                request = voice.enqueue(project_id, "sec_001", provider,
                                        # Operator must explicitly provide exact selected voice.
                                        __import__("os").environ.get("HVS_LIVE_VOICE_ID", ""),
                                        float(__import__("os").environ.get("HVS_LIVE_VOICE_SPEED", "nan")),
                                        "explicit live provider smoke", store.revision(project_id),
                                        "live-voice-section-smoke")
                result = voice.process_one()
            if not result or result["state"] != "SUCCEEDED":
                raise RuntimeError("TTS job did not succeed: %s" % (result and result["error_code"]))
            selected = voice.list_attempts(project_id, "sec_001")["attempts"][0]
            from backend.app.voice.correction import inspect_wav
            assert inspect_wav(store.get_artifact(selected["audio_sha256"]))["sample_count"] > 0
            if mode == "local":
                words = len(story["sections"][0]["narration"].split())
                correction = voice.apply_correction(project_id, "sec_001", selected["attempt_id"],
                                  "ffmpeg_tempo", (words * 60 / 3) * 1.1, store.revision(project_id))
                assert correction["source_attempt_id"] == selected["attempt_id"]
                assert VoiceService(ProjectStore(store.database, store.artifacts.root),
                                    GateService(store), JobQueue(store)).list_attempts(project_id, "sec_001")[
                                    "selected_attempt_id"] == correction["attempt_id"]
                assert store.get_artifact(selected["audio_sha256"])
                print("section-repair: LOCAL_PASS real SQLite/FFmpeg, SYNTHETIC source WAV, NO live TTS")
            else:
                print(f"{case}: LIVE_PASS real provider WAV persisted and inspected; job={request['job_id']}")
        except ContractViolation as exc:
            print(f"{case}: BLOCKED/FAIL ({exc.code}) — {exc.remediation}")
            raise SystemExit(2) from exc
