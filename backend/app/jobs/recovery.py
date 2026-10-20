"""Crash recovery cannot replay an unknown external side effect."""
from backend.app.jobs.queue import JobQueue


def recover_interrupted(queue: JobQueue) -> dict[str, int]:
    resumed = blocked = 0
    with queue.store._transaction() as db:
        for job_id, provider_task_id, cancel_requested in db.execute(
            "SELECT job_id,provider_task_id,cancel_requested FROM jobs WHERE state='RUNNING'"
        ).fetchall():
            if provider_task_id and not cancel_requested:
                db.execute("UPDATE jobs SET state='QUEUED',resume_only=1,lease_token=NULL "
                           "WHERE job_id=?", (job_id,))
                resumed += 1
            else:
                db.execute("UPDATE jobs SET state='BLOCKED_REVIEW',lease_token=NULL,"
                           "error_code='INTERRUPTED_UNCERTAIN_SIDE_EFFECT' WHERE job_id=?", (job_id,))
                blocked += 1
    return {"resume_existing_provider_task": resumed, "blocked_uncertain_operation": blocked}
