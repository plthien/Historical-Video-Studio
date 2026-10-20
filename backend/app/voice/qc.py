"""Frozen native-sample WAV operations. No estimated pauses or WPM."""
from __future__ import annotations
import io
import wave
from backend.app.contracts import ContractViolation
from backend.app.voice.correction import inspect_wav


def join_wavs(parts: list[tuple[str, bytes]]) -> tuple[bytes, list[dict], int]:
    if not parts or len({section for section, _ in parts}) != len(parts):
        raise ContractViolation("FINAL_AUDIO_SECTIONS_INVALID", "G2",
                                "Select each narrated section exactly once.")
    frames = []
    offsets = []
    cursor = 0
    for section, data in parts:
        info = inspect_wav(data)
        if info["sample_rate"] != 24000 or info["channels"] != 1:
            raise ContractViolation("FINAL_AUDIO_FORMAT_INVALID", section,
                                    "Each selected attempt must be 24kHz mono PCM16 WAV.")
        with wave.open(io.BytesIO(data), "rb") as audio:
            chunk = audio.readframes(audio.getnframes())
        if len(chunk) != info["sample_count"] * 2:
            raise ContractViolation("VOICE_AUDIO_TRUNCATED", section, "Selected WAV has incomplete samples.")
        frames.append(chunk)
        offsets.append({"section_id": section, "start_sample": cursor,
                        "end_sample": cursor + info["sample_count"]})
        cursor += info["sample_count"]
    result = io.BytesIO()
    with wave.open(result, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"".join(frames))
    assert inspect_wav(result.getvalue())["sample_count"] == cursor
    return result.getvalue(), offsets, cursor
