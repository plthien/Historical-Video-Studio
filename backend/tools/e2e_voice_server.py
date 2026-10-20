"""Test-only FastAPI server: real production endpoints/SQLite/FFmpeg, fake TTS boundary.

Never import in production; explicit Playwright config uses this entry point.
ElevenLabs forced alignment is not mocked here: missing credentials produce a
real FAILED_TERMINAL job, never a fabricated G4-ready word map.
"""
import os
from backend.app.voice import attempts
from backend.tools.voice_final_smoke import wav_fixture

os.environ.pop("HVS_ELEVENLABS_API_KEY", None)
attempts._provider_identity=lambda provider: {"model_id":"CHROMIUM_OFFLINE_MOCK"}
attempts._synthesize=lambda *args: wav_fixture(1.5)

from backend.app.api.server import create_app
app=create_app()
