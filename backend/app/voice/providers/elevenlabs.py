"""ElevenLabs official POST /v1/text-to-speech/{voice_id} audio boundary."""
from __future__ import annotations

import os

import httpx

from backend.app.contracts import ContractViolation


def identity() -> dict:
    model_id = os.getenv("HVS_ELEVENLABS_MODEL_ID", "").strip()
    if not model_id:
        raise ContractViolation("VOICE_MODEL_IDENTITY_MISSING", "elevenlabs_tts",
                                "Configure HVS_ELEVENLABS_MODEL_ID explicitly.")
    if not os.getenv("HVS_ELEVENLABS_API_KEY"):
        raise ContractViolation("PROVIDER_CREDENTIALS_MISSING", "elevenlabs_tts",
                                "Configure HVS_ELEVENLABS_API_KEY locally.")
    return {"model_id": model_id, "output_format": "mp3_44100_128"}


def synthesize(text: str, voice_id: str, speed: float, settings: dict) -> bytes:
    api_key = os.getenv("HVS_ELEVENLABS_API_KEY", "")
    if not api_key or settings["model_id"] != os.getenv("HVS_ELEVENLABS_MODEL_ID"):
        raise ContractViolation("PROVIDER_IDENTITY_CHANGED", voice_id,
                                "Voice provider credentials or configured model changed; resubmit.")
    if not 0.7 <= speed <= 1.2:
        raise ContractViolation("VOICE_SPEED_UNSUPPORTED", voice_id,
                                "ElevenLabs voice_settings.speed must be between 0.7 and 1.2.")
    try:
        response = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            params={"output_format": settings["output_format"]},
            headers={"xi-api-key": api_key, "Content-Type": "application/json",
                     "Accept": "audio/mpeg"},
            json={"text": text, "model_id": settings["model_id"],
                  "voice_settings": {"speed": speed}},
            timeout=httpx.Timeout(120.0, connect=10.0))
    except httpx.TimeoutException as exc:
        raise ContractViolation("PROVIDER_TIMEOUT", voice_id, "ElevenLabs transport timeout; retry safely.") from exc
    except httpx.RequestError as exc:
        raise ContractViolation("PROVIDER_TRANSPORT_FAILED", voice_id,
                                "Cannot contact ElevenLabs; check network and provider status.") from exc
    if response.status_code != 200:
        code = ("PROVIDER_QUOTA_EXCEEDED" if response.status_code == 429 else
                "PROVIDER_AUTH_FAILED" if response.status_code in (401, 403) else
                "VOICE_IDENTITY_INVALID" if response.status_code == 404 else
                "PROVIDER_UNAVAILABLE" if response.status_code >= 500 else
                "PROVIDER_REJECTED")
        raise ContractViolation(code, voice_id, f"ElevenLabs returned HTTP {response.status_code}; no attempt saved.")
    if not response.content or not response.headers.get("content-type", "").lower().startswith(("audio/", "application/octet-stream")):
        raise ContractViolation("PROVIDER_AUDIO_INVALID", voice_id, "ElevenLabs returned no supported audio bytes.")
    return response.content
