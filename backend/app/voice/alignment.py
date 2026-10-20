"""Real ElevenLabs forced-alignment transport; no inferred word timings."""
from __future__ import annotations
import os
import httpx
from backend.app.contracts import ContractViolation


def align_audio(wav: bytes, transcript: str) -> dict:
    key = os.environ.get("HVS_ELEVENLABS_API_KEY", "")
    if not key:
        raise ContractViolation("PROVIDER_CREDENTIALS_MISSING", "elevenlabs_forced_alignment",
                                "Configure HVS_ELEVENLABS_API_KEY to align the approved final WAV.")
    try:
        response = httpx.post("https://api.elevenlabs.io/v1/forced-alignment",
                              headers={"xi-api-key": key},
                              data={"text": transcript},
                              files={"file": ("final.wav", wav, "audio/wav")},
                              timeout=httpx.Timeout(180.0, connect=12.0))
    except httpx.TimeoutException as exc:
        raise ContractViolation("ALIGNMENT_TIMEOUT", "G2", "Alignment timed out; verify operation before retry.") from exc
    except httpx.RequestError as exc:
        raise ContractViolation("ALIGNMENT_TRANSPORT_FAILED", "G2",
                                "Cannot contact ElevenLabs forced alignment.") from exc
    if response.status_code != 200:
        code = ("PROVIDER_AUTH_FAILED" if response.status_code in (401, 403) else
                "PROVIDER_QUOTA_EXCEEDED" if response.status_code == 429 else
                "PROVIDER_UNAVAILABLE" if response.status_code >= 500 else
                "ALIGNMENT_REJECTED")
        raise ContractViolation(code, "G2",
                                f"ElevenLabs forced alignment HTTP {response.status_code}; no word map saved.")
    try:
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload["words"], list):
            raise ValueError("Missing word list")
        return payload
    except (ValueError, KeyError, TypeError) as exc:
        raise ContractViolation("ALIGNMENT_RESPONSE_INVALID", "G2",
                                "ElevenLabs returned a malformed forced-alignment response.") from exc
