"""Windows operator/automation: drain one durable A2 final assembly or alignment job."""
import os
from pathlib import Path
from backend.app.projects.storage import ProjectStore
from backend.app.projects.gates import GateService
from backend.app.jobs.queue import JobQueue
from backend.app.voice.workflow import FinalVoiceWorkflow


def main():
    store=ProjectStore(Path(os.getenv("HVS_DB","data/historical-studio.sqlite")),
                       Path(os.getenv("HVS_MEDIA","data/media")))
    outcome=FinalVoiceWorkflow(store,GateService(store),JobQueue(store)).process_one()
    if not outcome:
        print("final-voice-worker: NO_JOB")
        return
    print("final-voice-worker: job_id=%s state=%s error_code=%s" %
          (outcome["job_id"],outcome["state"],outcome["error_code"]))
    if outcome["state"]!="SUCCEEDED":raise SystemExit(1)


if __name__=="__main__":
    main()
