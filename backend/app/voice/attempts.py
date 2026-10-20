"""A2-01/02: exact-G1-bound section synthesis, immutable attempts and selection events.

The ONLY provider simulation seam is synthesize(...), replaced at the boundary in
offline tests. Every persisted success requires real decoded WAV samples/bytes.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from uuid import uuid4

from backend.app.contracts import ContractViolation, validate_document
from backend.app.jobs.queue import JobQueue
from backend.app.projects.gates import GateService
from backend.app.projects.revisions import mark_stale
from backend.app.projects.storage import ProjectStore
from backend.app.voice.correction import correct, ffmpeg_wav, inspect_wav
from backend.app.voice.providers import elevenlabs, kokoro


def _canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _provider_identity(provider_id: str) -> dict:
    if provider_id == "kokoro_local":
        return kokoro.identity()
    if provider_id == "elevenlabs_tts":
        return elevenlabs.identity()
    raise ContractViolation("VOICE_PROVIDER_INVALID", provider_id, "Select kokoro_local or elevenlabs_tts.")


def _synthesize(provider_id: str, text: str, voice_id: str, speed: float, settings: dict) -> bytes:
    if provider_id == "kokoro_local":
        return kokoro.synthesize(text, voice_id, speed, settings)
    if provider_id == "elevenlabs_tts":
        return elevenlabs.synthesize(text, voice_id, speed, settings)
    raise ContractViolation("VOICE_PROVIDER_INVALID", provider_id, "Select a supported provider.")


class VoiceService:
    def __init__(self, store: ProjectStore, gates: GateService, queue: JobQueue):
        self.store, self.gates, self.queue = store, gates, queue
        with store._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS voice_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL, section_id TEXT NOT NULL,
                    story_sha256 TEXT NOT NULL, text_sha256 TEXT NOT NULL,
                    provider_id TEXT NOT NULL, voice_id TEXT NOT NULL,
                    settings_json TEXT NOT NULL, model_identity_sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('SYNTHESIS','CORRECTION')),
                    source_attempt_id TEXT,
                    raw_audio_sha256 TEXT NOT NULL, audio_sha256 TEXT NOT NULL,
                    sample_rate INTEGER NOT NULL, channels INTEGER NOT NULL,
                    sample_count INTEGER NOT NULL, duration_seconds REAL NOT NULL,
                    correction_json TEXT, job_id TEXT UNIQUE,
                    FOREIGN KEY(source_attempt_id) REFERENCES voice_attempts(attempt_id)
                );
                CREATE TABLE IF NOT EXISTS voice_selected (
                    project_id TEXT NOT NULL, section_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL, PRIMARY KEY(project_id,section_id),
                    FOREIGN KEY(attempt_id) REFERENCES voice_attempts(attempt_id)
                );
                CREATE TABLE IF NOT EXISTS voice_selection_events (
                    event_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    section_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
                    reason TEXT NOT NULL, committed_revision INTEGER NOT NULL,
                    FOREIGN KEY(attempt_id) REFERENCES voice_attempts(attempt_id)
                );
            """)

    def _source(self, project_id: str, section_id: str) -> tuple[str, str, str]:
        board = self.gates.board(project_id)[0]
        if board["state"] != "APPROVED":
            raise ContractViolation("G1_APPROVAL_REQUIRED", project_id,
                                    "Approve current G1 StoryPackage and saved claim evidence first.",
                                    blocking_gate="G1")
        story = self.store.get_story(project_id)
        if story.sha256 != board["candidate_sha256"]:
            raise ContractViolation("VOICE_STORY_STALE", section_id, "G1 story source was replaced.")
        section = next((s for s in story.data()["sections"] if s["section_id"] == section_id), None)
        if section is None:
            raise ContractViolation("VOICE_SECTION_NOT_FOUND", section_id, "Choose a section from current G1.")
        return story.sha256, section["narration"], _hash(section["narration"])

    def enqueue(self, project_id: str, section_id: str, provider_id: str, voice_id: str,
                speed: float | None, reason: str, expected_revision: int, key: str) -> dict:
        if not isinstance(reason, str) or not reason.strip() or not isinstance(voice_id, str) or not voice_id.strip():
            raise ContractViolation("VOICE_IDENTITY_INVALID", section_id, "Voice and regeneration reason are required.")
        if speed is None:
            raise ContractViolation("VOICE_SPEED_SETTING_MISSING", section_id,
                                    "Choose an explicit playback/synthesis speed for this section.")
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed):
            raise ContractViolation("VOICE_SPEED_INVALID", section_id, "Specify a finite speed.")
        story_sha, text, text_sha = self._source(project_id, section_id)
        identity = _provider_identity(provider_id)
        model_sha = _hash(_canonical({k: v for k, v in identity.items() if k not in ("model_path", "voices_path")}))
        voice_request = {"schema_version": "VoiceRequest.v1", "project_id": project_id,
                         "story_revision_sha256": story_sha, "provider_id": provider_id, "language": "en",
                         "voice_id": voice_id, "sections": [{
                             "section_id": section_id, "text_sha256": text_sha,
                             "text": text, "speed": speed}]}
        validate_document("VoiceRequest.v1", voice_request)
        job = self.queue.submit(project_id, "voice_synthesis", key,
                                {"voice_request": voice_request, "model_identity": identity,
                                 "model_identity_sha256": model_sha, "reason": reason}, expected_revision)
        return {"job_id": job["job_id"], "state": job["state"], "project_revision": self.store.revision(project_id),
                "section_id": section_id, "candidate_sha256": story_sha}

    def _load_attempt(self, db, project_id: str, section_id: str, attempt_id: str) -> dict:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM voice_attempts WHERE project_id=? AND section_id=? AND attempt_id=?",
                         (project_id, section_id, attempt_id)).fetchone()
        if row is None:
            raise ContractViolation("VOICE_ATTEMPT_NOT_FOUND", attempt_id,
                                    "Select an existing attempt belonging to the exact section.")
        return dict(row)

    def _selected(self, db, project_id: str, section_id: str) -> dict:
        row = db.execute("SELECT attempt_id FROM voice_selected WHERE project_id=? AND section_id=?",
                         (project_id, section_id)).fetchone()
        if row is None:
            raise ContractViolation("VOICE_SELECTION_MISSING", section_id, "Synthesize a section attempt first.")
        return self._load_attempt(db, project_id, section_id, row[0])

    @staticmethod
    def _select(db, project_id: str, section_id: str, attempt_id: str, reason: str, revision: int):
        db.execute("INSERT INTO voice_selected(project_id,section_id,attempt_id) VALUES(?,?,?) "
                   "ON CONFLICT(project_id,section_id) DO UPDATE SET attempt_id=excluded.attempt_id",
                   (project_id, section_id, attempt_id))
        db.execute("INSERT INTO voice_selection_events VALUES(?,?,?,?,?,?)",
                   ("selection_" + uuid4().hex, project_id, section_id, attempt_id, reason, revision))

    def list_attempts(self, project_id: str, section_id: str) -> dict:
        _, text, text_sha = self._source(project_id, section_id)
        with self.store._connection() as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute(
                "SELECT * FROM voice_attempts WHERE project_id=? AND section_id=? ORDER BY rowid",
                (project_id, section_id))]
            selected = db.execute("SELECT attempt_id FROM voice_selected WHERE project_id=? AND section_id=?",
                                  (project_id, section_id)).fetchone()
        for row in rows:
            row["settings"] = json.loads(row.pop("settings_json"))
            row["correction"] = json.loads(row["correction_json"]) if row["correction_json"] else None
            row.pop("correction_json")
            row["selected"] = bool(selected and row["attempt_id"] == selected[0])
            row["compatible_source"] = row["text_sha256"] == text_sha
        return {"section_id": section_id, "attempts": rows, "selected_attempt_id": selected[0] if selected else None}

    def _source_matches(self, project_id: str, section_id: str, row: dict) -> str:
        current_story, text, text_sha = self._source(project_id, section_id)
        if (row["story_sha256"] != current_story or row["text_sha256"] != text_sha):
            raise ContractViolation("VOICE_SOURCE_STALE", section_id,
                                    "This attempt predates current G1 story/text; regenerate.")
        return text

    def restore(self, project_id: str, section_id: str, attempt_id: str,
                expected_audio_sha256: str, expected_revision: int, reason: str) -> dict:
        if not reason:
            reason = "Operator restored previously selected attempt"
        with self.store._transaction() as db:
            self.gates._check_revision(db, project_id, expected_revision)
            target = self._load_attempt(db, project_id, section_id, attempt_id)
            current = self._selected(db, project_id, section_id)
            self._source_matches(project_id, section_id, target)
            if (target["audio_sha256"] != expected_audio_sha256 or
                    any(target[k] != current[k] for k in
                        ("provider_id", "voice_id", "model_identity_sha256", "settings_json"))):
                raise ContractViolation("VOICE_ATTEMPT_IDENTITY_CONFLICT", attempt_id,
                                        "Restore requires exact source SHA, provider, voice and settings identity.")
            if target["attempt_id"] == current["attempt_id"]:
                raise ContractViolation("VOICE_ATTEMPT_ALREADY_SELECTED", attempt_id,
                                        "The requested attempt is already selected.")
            self.store.get_artifact(target["audio_sha256"])
            revision = expected_revision + 1
            self._select(db, project_id, section_id, attempt_id, reason, revision)
            mark_stale(db, project_id, "voice_audio")
            db.execute("UPDATE projects SET revision=? WHERE project_id=?", (revision, project_id))
            return {"attempt_id": attempt_id, "selected_attempt_id": attempt_id, "project_revision": revision}

    def apply_correction(self, project_id: str, section_id: str, attempt_id: str,
                         method: str, target_wpm: float, expected_revision: int) -> dict:
        if method != "ffmpeg_tempo":
            raise ContractViolation("VOICE_CORRECTION_METHOD_UNSUPPORTED", method,
                                    "Use ffmpeg_tempo; provider regeneration uses /regenerate.")
        self.store.revision(project_id)
        with self.store._connection() as db:
            self.gates._check_revision(db, project_id, expected_revision)
            selected = self._selected(db, project_id, section_id)
            if attempt_id != selected["attempt_id"]:
                raise ContractViolation("VOICE_ATTEMPT_SELECTION_CONFLICT", attempt_id,
                                        "Correct only the currently selected attempt.")
            text = self._source_matches(project_id, section_id, selected)
        original = self.store.get_artifact(selected["audio_sha256"])
        output, correction = correct(original, text, target_wpm)
        info = inspect_wav(output)
        digest = self.store.put_artifact(output, "voice_audio")
        with self.store._transaction() as db:
            self.gates._check_revision(db, project_id, expected_revision)
            still = self._selected(db, project_id, section_id)
            if still["attempt_id"] != attempt_id:
                raise ContractViolation("VOICE_ATTEMPT_SELECTION_CONFLICT", attempt_id,
                                        "Selection changed while FFmpeg was running.")
            self._source_matches(project_id, section_id, still)
            new_id = "attempt_" + uuid4().hex
            db.execute("INSERT INTO voice_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                new_id, project_id, section_id, selected["story_sha256"], selected["text_sha256"],
                selected["provider_id"], selected["voice_id"], selected["settings_json"],
                selected["model_identity_sha256"], "CORRECTION", attempt_id,
                selected["raw_audio_sha256"], digest, info["sample_rate"], info["channels"],
                info["sample_count"], info["duration_seconds"], _canonical(correction), None))
            revision = expected_revision + 1
            self._select(db, project_id, section_id, new_id, "ffmpeg_tempo", revision)
            mark_stale(db, project_id, "voice_audio")
            db.execute("UPDATE projects SET revision=? WHERE project_id=?", (revision, project_id))
        return {"attempt_id": new_id, "selected_attempt_id": new_id, "audio_sha256": digest,
                "source_attempt_id": attempt_id, "project_revision": revision, "audio": info, "correction": correction}

    def process_one(self, synthesizer=None) -> dict | None:
        """One real leased job; fake only at the provider boundary in explicit offline smoke."""
        job = self.queue.claim("voice_synthesis")
        if job is None:
            return None
        try:
            if job["resume_only"]:
                raise ContractViolation("VOICE_OPERATION_UNCERTAIN", job["job_id"],
                                        "External synthesis may already have run; reconcile before retry.")
            payload = json.loads(job["payload_json"])
            request = payload["voice_request"]
            section = request["sections"][0]
            project, section_id = job["project_id"], section["section_id"]
            sha, text, text_sha = self._source(project, section_id)
            if (sha != request["story_revision_sha256"] or text_sha != section["text_sha256"]
                    or text != section["text"]):
                raise ContractViolation("VOICE_SOURCE_STALE", section_id,
                                        "G1-approved section changed since synth request; no provider call.")
            provider = request["provider_id"]
            fresh_identity = _provider_identity(provider) if synthesizer is None else payload["model_identity"]
            if fresh_identity != payload["model_identity"]:
                raise ContractViolation("PROVIDER_IDENTITY_CHANGED", provider,
                                        "Voice model or provider config changed after the request was queued.")
            raw = (_synthesize(provider, text, request["voice_id"], section["speed"], fresh_identity)
                   if synthesizer is None else synthesizer(request, fresh_identity))
            if not raw or len(raw) > 100_000_000:
                raise ContractViolation("PROVIDER_AUDIO_INVALID", section_id, "No valid bounded provider audio.")
            wav = ffmpeg_wav(raw)
            info = inspect_wav(wav)
            raw_sha = self.store.put_artifact(raw, "voice_audio")
            audio_sha = self.store.put_artifact(wav, "voice_audio")
            with self.store._transaction() as db:
                owned = self.queue._owned(db, job["job_id"], job["lease_token"])
                if owned["cancel_requested"]:
                    raise ContractViolation("JOB_CANCEL_PENDING", job["job_id"], "Resolve cancellation first.")
                # Validated again immediately before publishing: stale sources never become selected.
                self._source_matches(project, section_id, {
                    "story_sha256": sha, "text_sha256": text_sha})
                revision = self.gates._check_revision(
                    db, project, db.execute("SELECT revision FROM projects WHERE project_id=?",
                                           (project,)).fetchone()[0])
                attempt_id = "attempt_" + uuid4().hex
                db.execute("INSERT INTO voice_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    attempt_id, project, section_id, sha, text_sha, provider, request["voice_id"],
                    _canonical({"speed": section["speed"], "provider": fresh_identity}),
                    payload["model_identity_sha256"], "SYNTHESIS", None, raw_sha, audio_sha,
                    info["sample_rate"], info["channels"], info["sample_count"],
                    info["duration_seconds"], None, job["job_id"]))
                self._select(db, project, section_id, attempt_id, payload["reason"], revision + 1)
                mark_stale(db, project, "voice_audio")
                db.execute("UPDATE projects SET revision=? WHERE project_id=?", (revision + 1, project))
                db.execute("UPDATE jobs SET state='SUCCEEDED',output_sha256=?,lease_token=NULL,"
                           "error_code=NULL WHERE job_id=? AND state='RUNNING' AND lease_token=?",
                           (audio_sha, job["job_id"], job["lease_token"]))
            return self.queue.get(job["job_id"])
        except ContractViolation as exc:
            return self.queue.fail(job["job_id"], job["lease_token"], exc.code,
                                   retryable=exc.code == "PROVIDER_QUOTA_EXCEEDED")
        except Exception:
            return self.queue.fail(job["job_id"], job["lease_token"], "VOICE_OPERATION_UNCERTAIN", retryable=False)
