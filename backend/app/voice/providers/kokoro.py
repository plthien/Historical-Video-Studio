"""Kokoro-ONNX 1.0 local synthesis, using its documented Python Kokoro.create API.

Optional kokoro-onnx + soundfile and canonical model assets must be installed by
the operator. A subprocess provides an actual synthesis timeout on Windows.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

from backend.app.contracts import ContractViolation


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def identity() -> dict:
    model = Path(os.environ.get("HVS_KOKORO_MODEL_PATH", "models/kokoro-v1.0.onnx"))
    voices = Path(os.environ.get("HVS_KOKORO_VOICES_PATH", "models/voices-v1.0.bin"))
    if (model.name != "kokoro-v1.0.onnx" or voices.name != "voices-v1.0.bin"
            or not model.is_file() or not voices.is_file()):
        raise ContractViolation("KOKORO_ASSETS_MISSING", "kokoro_local",
                                "Install exact Kokoro v1.0 ONNX model and voices-v1.0.bin.")
    return {"model_id": "kokoro-v1.0", "model_sha256": _file_hash(model),
            "voices_sha256": _file_hash(voices), "model_path": str(model.resolve()),
            "voices_path": str(voices.resolve())}


def _synthesize_worker(settings: dict) -> bytes:
    try:
        import soundfile as sf
        from kokoro_onnx import Kokoro
    except ImportError as exc:
        raise ContractViolation("KOKORO_RUNTIME_MISSING", "kokoro_local",
                                "Install kokoro-onnx and soundfile into the Windows Python 3.12 venv.") from exc
    model = Kokoro(settings["model_path"], settings["voices_path"])
    try:
        if settings["voice_id"] not in model.get_voices():
            raise ContractViolation("VOICE_IDENTITY_INVALID", settings["voice_id"],
                                    "Select an English Kokoro voice available in voices-v1.0.bin.")
        samples, sample_rate = model.create(settings["text"], voice=settings["voice_id"],
                                            speed=settings["speed"], lang="en-us")
        out = io.BytesIO()
        sf.write(out, samples, sample_rate, format="WAV", subtype="PCM_16")
        return out.getvalue()
    finally:
        if hasattr(model, "voices") and hasattr(model.voices, "close"):
            model.voices.close()


def synthesize(text: str, voice_id: str, speed: float, settings: dict) -> bytes:
    command = [sys.executable, "-m", "backend.app.voice.providers.kokoro", "--worker"]
    payload = json.dumps({**settings, "text": text, "voice_id": voice_id, "speed": speed})
    try:
        result = subprocess.run(command, input=payload.encode("utf-8"),
                                capture_output=True, timeout=180, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ContractViolation("PROVIDER_TIMEOUT", "kokoro_local",
                                "Kokoro inference exceeded the bounded local execution time.") from exc
    except OSError as exc:
        raise ContractViolation("KOKORO_PROCESS_FAILED", "kokoro_local",
                                "Cannot launch the isolated Kokoro inference process.") from exc
    if result.returncode != 0:
        code = result.stderr.decode("utf-8", errors="replace").strip()
        if code not in {"KOKORO_RUNTIME_MISSING", "VOICE_IDENTITY_INVALID", "KOKORO_GENERATION_FAILED"}:
            code = "KOKORO_GENERATION_FAILED"
        raise ContractViolation(code, "kokoro_local", "Verify Kokoro runtime, model and selected voice.")
    return result.stdout


def main() -> None:
    try:
        audio = _synthesize_worker(json.loads(sys.stdin.buffer.read()))
    except ContractViolation as exc:
        print(exc.code, file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        print("KOKORO_GENERATION_FAILED", file=sys.stderr)
        raise SystemExit(2)
    sys.stdout.buffer.write(audio)


if __name__ == "__main__":
    main()
