"""Audio inspection and bounded FFmpeg tempo correction using measured samples."""
from __future__ import annotations

import io
import math
import subprocess
import tempfile
import wave
from pathlib import Path

from backend.app.contracts import ContractViolation


def inspect_wav(data: bytes) -> dict:
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            rate, channels, width = source.getframerate(), source.getnchannels(), source.getsampwidth()
            count, frames = source.getnframes(), source.readframes(source.getnframes())
    except (EOFError, wave.Error, ValueError) as exc:
        raise ContractViolation("VOICE_AUDIO_INVALID", "audio", "Audio is not a valid PCM WAV.") from exc
    if not (rate == 24000 and channels == 1 and width == 2 and 0 < count <= 24000 * 3600):
        raise ContractViolation("VOICE_AUDIO_INVALID", "audio",
                                "Require nonempty 24 kHz mono 16-bit PCM WAV, at most one hour.")
    if len(frames) != count * channels * width:
        raise ContractViolation("VOICE_AUDIO_TRUNCATED", "audio", "WAV samples do not match the declared frame count.")
    if not any(frames):
        raise ContractViolation("VOICE_AUDIO_SILENT", "audio", "All decoded PCM samples are silent.")
    return {"sample_rate": rate, "channels": channels, "sample_count": count,
            "duration_seconds": count / rate, "sample_width": width}


def ffmpeg_wav(data: bytes, *, atempo: float | None = None) -> bytes:
    if atempo is not None and (not math.isfinite(atempo) or not 0.75 <= atempo <= 1.25):
        raise ContractViolation("VOICE_CORRECTION_OUT_OF_RANGE", "atempo",
                                "FFmpeg correction is limited to 0.75–1.25x; regenerate for larger changes.")
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "render.wav"
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-i", "pipe:0", "-vn", "-ac", "1", "-ar", "24000"]
        if atempo is not None:
            command += ["-af", f"atempo={atempo:.8f}"]
        command += ["-c:a", "pcm_s16le", str(output)]
        try:
            result = subprocess.run(command, input=data, capture_output=True,
                                    timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContractViolation("VOICE_FFMPEG_FAILED", "ffmpeg",
                                    "FFmpeg is missing or timed out; original attempt remains unchanged.") from exc
        if result.returncode != 0 or not output.is_file():
            raise ContractViolation("VOICE_FFMPEG_FAILED", "ffmpeg",
                                    "FFmpeg decoding/correction failed; inspect audio input and codec.")
        processed = output.read_bytes()
        inspect_wav(processed)
        return processed


def correct(data: bytes, transcript: str, target_wpm: float) -> tuple[bytes, dict]:
    if not isinstance(target_wpm, (int, float)) or not math.isfinite(target_wpm) or not 50 <= target_wpm <= 400:
        raise ContractViolation("VOICE_CORRECTION_OUT_OF_RANGE", "target_wpm",
                                "Choose a finite target WPM between 50 and 400.")
    metadata = inspect_wav(data)
    words = len(transcript.split())
    if not words:
        raise ContractViolation("VOICE_TEXT_INVALID", "transcript", "Cannot tempo-correct an empty section.")
    measured_wpm = words * 60 / metadata["duration_seconds"]
    ratio = target_wpm / measured_wpm
    result = ffmpeg_wav(data, atempo=ratio)
    return result, {"method": "ffmpeg_tempo", "target_wpm": target_wpm,
                    "measured_source_wpm": measured_wpm, "atempo": ratio}
