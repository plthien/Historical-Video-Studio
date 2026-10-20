"""Windows operator/automation: drain one durable A2 final assembly or alignment job."""
import os
import argparse
from uuid import uuid4
from pathlib import Path
from backend.app.projects.storage import ProjectStore
from backend.app.projects.gates import GateService
from backend.app.jobs.queue import JobQueue
from backend.app.voice.workflow import FinalVoiceWorkflow


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--retry-assembly-project")
    args=parser.parse_args()
    store=ProjectStore(Path(os.getenv("HVS_DB","data/historical-studio.sqlite")),
                       Path(os.getenv("HVS_MEDIA","data/media")))
    workflow=FinalVoiceWorkflow(store,GateService(store),JobQueue(store))
    job_id = None
    if args.retry_assembly_project:
        job_id=workflow.retry_assembly(args.retry_assembly_project,
                                      store.revision(args.retry_assembly_project),
                                      "assembly-retry-"+uuid4().hex)
        print("final-voice-worker: explicit technical retry queued",job_id)
        workflow.process_pending(job_id)
    outcome=workflow.queue.get(job_id) if job_id else workflow.process_one()
    if not outcome:
        print("final-voice-worker: NO_JOB")
        return
    print("final-voice-worker: job_id=%s state=%s error_code=%s" %
          (outcome["job_id"],outcome["state"],outcome["error_code"]))
    if outcome["state"]!="SUCCEEDED":raise SystemExit(1)


if __name__=="__main__":
    main()
