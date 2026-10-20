"""CLI for draining exactly one durable section-synthesis job on Windows."""
from pathlib import Path
import os

from backend.app.jobs import JobQueue
from backend.app.projects.gates import GateService
from backend.app.projects.storage import ProjectStore
from backend.app.voice.attempts import VoiceService


def main():
    store = ProjectStore(Path(os.getenv("HVS_DB", "data/historical-studio.sqlite")),
                         Path(os.getenv("HVS_MEDIA", "data/media")))
    result = VoiceService(store, GateService(store), JobQueue(store)).process_one()
    if result is None:
        print("voice-worker: NO_JOB")
        return
    print("voice-worker: job_id=%s state=%s error_code=%s" %
          (result["job_id"], result["state"], result["error_code"]))
    if result["state"] != "SUCCEEDED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
