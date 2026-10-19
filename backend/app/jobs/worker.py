"""Small single-operation worker. Providers must implement poll/resume, not implicit duplicate submit."""
from backend.app.contracts import ContractViolation
from backend.app.jobs.queue import JobQueue


def run_one(queue: JobQueue, handlers: dict, *, kind: str | None = None) -> dict | None:
    job = queue.claim(kind)
    if job is None:
        return None
    job_id, token = job["job_id"], job["lease_token"]
    handler = handlers.get(job["kind"])
    if handler is None:
        return queue.fail(job_id, token, "JOB_HANDLER_UNAVAILABLE", retryable=False)
    if job["resume_only"] and not job["provider_task_id"]:
        return queue.fail(job_id, token, "PROVIDER_TASK_ID_MISSING", retryable=False)
    try:
        # Real implementations receive original provider_task_id and are required to poll it.
        output_sha = handler(job, queue)
        if queue.get(job_id)["cancel_requested"]:
            # Handler must actually cancel external operation before acknowledging;
            # otherwise preserve uncertain state for operator review.
            return queue.fail(job_id, token, "CANCELLATION_NOT_CONFIRMED", retryable=False)
        return queue.finish(job_id, token, output_sha)
    except ContractViolation as exc:
        return queue.fail(job_id, token, exc.code, retryable=False)
    except Exception:
        return queue.fail(job_id, token, "JOB_EXECUTION_FAILED", retryable=True)
