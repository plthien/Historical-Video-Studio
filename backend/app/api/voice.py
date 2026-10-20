"""A2-02 owner routes; no G2 approval/assembly/alignment and no extra UI gate."""
from __future__ import annotations

from fastapi import BackgroundTasks, Header, FastAPI
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from backend.app.voice.attempts import VoiceService
from backend.app.contracts import ContractViolation


class Regenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    provider_id: str
    voice_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    speed: float | None = Field(default=None, ge=0.5, le=2.0)


class SelectAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    attempt_id: str = Field(min_length=3, max_length=64)
    expected_audio_sha256: str
    reason: str = ""


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    attempt_id: str = Field(min_length=3, max_length=64)
    method: str
    target_wpm: float = Field(ge=50, le=400)


class AlignmentRetry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def mount(app: FastAPI, service: VoiceService, idempotent, final_voice) -> None:
    @app.get("/api/v1/projects/{project_id}/voice/sections/{section_id}/attempts")
    def list_section_attempts(project_id: str, section_id: str):
        return service.list_attempts(project_id, section_id)

    @app.post("/api/v1/projects/{project_id}/voice/sections/{section_id}/regenerate", status_code=202)
    def regenerate(project_id: str, section_id: str, body: Regenerate, background: BackgroundTasks,
                   idempotency_key: str = Header(alias="Idempotency-Key")):
        job = service.enqueue(project_id, section_id, body.provider_id, body.voice_id,
                              body.speed, body.reason, body.expected_revision, idempotency_key)
        if job["state"] == "QUEUED":
            background.add_task(service.process_one)
        return job  # QUEUED now, never a fabricated audio-success response

    @app.post("/api/v1/projects/{project_id}/voice/sections/{section_id}/select-attempt")
    def select_attempt(project_id: str, section_id: str, body: SelectAttempt,
                       idempotency_key: str = Header(alias="Idempotency-Key")):
        return idempotent(project_id, f"voice-select:{section_id}", idempotency_key, body.model_dump(),
                          lambda: service.restore(project_id, section_id, body.attempt_id,
                                                   body.expected_audio_sha256, body.expected_revision, body.reason))

    @app.post("/api/v1/projects/{project_id}/voice/sections/{section_id}/correction")
    def correction(project_id: str, section_id: str, body: Correction,
                   idempotency_key: str = Header(alias="Idempotency-Key")):
        return idempotent(project_id, f"voice-correction:{section_id}", idempotency_key, body.model_dump(),
                          lambda: service.apply_correction(project_id, section_id, body.attempt_id,
                                                           body.method, body.target_wpm, body.expected_revision))


    @app.get("/api/v1/projects/{project_id}/voice/alignment")
    def alignment_status(project_id: str):
        return final_voice.status(project_id)

    @app.post("/api/v1/projects/{project_id}/voice/alignment/retry", status_code=202)
    def retry_alignment(project_id: str, body: AlignmentRetry, background: BackgroundTasks,
                        idempotency_key: str = Header(alias="Idempotency-Key")):
        payload = body.model_dump()
        result = idempotent(project_id, "alignment-retry", idempotency_key, payload,
            lambda: final_voice.retry_alignment(project_id, body.expected_revision,
                body.audio_sha256, body.transcript_sha256, idempotency_key))
        background.add_task(final_voice.process_pending, result["job_id"])
        return result

    @app.get("/api/v1/projects/{project_id}/voice/audio/{audio_sha256}")
    def audio(project_id: str, audio_sha256: str):
        if len(audio_sha256) != 64 or any(c not in "0123456789abcdef" for c in audio_sha256):
            raise ContractViolation("VOICE_AUDIO_SHA_INVALID", audio_sha256, "Use an exact 64-character SHA.")
        return Response(content=final_voice.audio(project_id, audio_sha256),
                        media_type="audio/wav", headers={"Cache-Control": "private, no-store"})
