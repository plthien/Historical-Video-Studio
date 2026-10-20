# A2-01/02 Windows local voice setup

Regenerate requires an effective approved G1 story, explicit provider/voice/speed, and expected revision. The API queues a durable synthesis job; QUEUED is not audio success. GET /api/v1/jobs/{job_id} reports actual results, while python -m backend.tools.voice_worker drains one queued job. Existing A1 recovery prevents blind replay after an uncertain interrupted submit.

## Kokoro local
Install separately into Windows Python 3.12 venv: .venv\Scripts\python.exe -m pip install kokoro-onnx==0.6.1 soundfile==0.14.0
Install the upstream kokoro-v1.0.onnx and voices-v1.0.bin and verify their SHA256. Configure HVS_KOKORO_MODEL_PATH and HVS_KOKORO_VOICES_PATH or place the files in models/. The adapter uses Kokoro.create from documented kokoro-onnx Python, isolated in a Windows subprocess with timeout. Missing model/voices or an unavailable voice fail closed.

## ElevenLabs
Configure HVS_ELEVENLABS_API_KEY and HVS_ELEVENLABS_MODEL_ID locally; choose an actual voice ID and explicit speed. The adapter posts to the official text-to-speech API, retains raw returned MP3 bytes, and decodes a separate immutable PCM16 WAV. HTTP auth/quota/provider errors remain typed. Never commit credentials.

## Live verification (only after configuring a real model/credential and HVS_LIVE_VOICE_ID/HVS_LIVE_VOICE_SPEED)
.venv\Scripts\python.exe -m backend.tools.smoke --case tts-kokoro --mode live
.venv\Scripts\python.exe -m backend.tools.smoke --case tts-elevenlabs --mode live

## Offline/local verification
.venv\Scripts\python.exe -m pytest -q tests/voice/test_voice_pipeline.py
.venv\Scripts\python.exe -m backend.tools.smoke --case section-repair --mode local
The local smoke synthesizes a controlled PCM fixture ONLY at the provider boundary, then runs real FFmpeg and SQLite/filesystem checks. It is not a live TTS test or G1 operator approval.

A2-03 assembly, A2-04 alignment and A2-05 Voice Studio UI remain unimplemented.
