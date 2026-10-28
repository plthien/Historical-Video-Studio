"""Crash recovery cannot replay an unknown external side effect."""
import os
from backend.app.jobs.queue import JobQueue


def _process_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259)
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def recover_interrupted(queue: JobQueue) -> dict[str, int]:
    resumed = blocked = 0
    with queue.store._transaction() as db:
        for job_id, provider_task_id, cancel_requested, kind in db.execute(
            "SELECT job_id,provider_task_id,cancel_requested,kind FROM jobs WHERE state='RUNNING'"
        ).fetchall():
            if kind == "final_assembly" and not cancel_requested:
                # Final WAV assembly is a deterministic local operation. It is
                # safe to re-run from its frozen selection snapshot.
                db.execute("UPDATE jobs SET state='QUEUED',resume_only=0,lease_token=NULL,error_code=NULL "
                           "WHERE job_id=?", (job_id,))
                resumed += 1
            elif kind == "final_render" and not cancel_requested:
                # Local render has no remote side effect. Partial temp files are
                # never authoritative, so deterministic exact-input requeue is safe.
                table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='render_attempts'").fetchone()
                pid_row = (db.execute("SELECT process_id FROM render_attempts WHERE job_id=?", (job_id,)).fetchone()
                           if table else None)
                alive = bool(pid_row and pid_row[0] and _process_alive(pid_row[0]))
                if alive:
                    db.execute("UPDATE jobs SET state='BLOCKED_REVIEW',lease_token=NULL,"
                               "error_code='INTERRUPTED_LOCAL_PROCESS_STILL_RUNNING' WHERE job_id=?", (job_id,))
                    blocked += 1
                else:
                    db.execute("UPDATE jobs SET state='QUEUED',lease_token=NULL,error_code=NULL "
                               "WHERE job_id=?", (job_id,))
                    if table:
                        db.execute("UPDATE render_attempts SET process_id=NULL WHERE job_id=?", (job_id,))
                    resumed += 1
            elif kind == "final_render" and cancel_requested:
                # App restart proves its owned child is gone only when its exact
                # persisted PID no longer exists. Otherwise require review.
                table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='render_attempts'").fetchone()
                pid_row = (db.execute("SELECT process_id FROM render_attempts WHERE job_id=?", (job_id,)).fetchone()
                           if table else None)
                alive = bool(pid_row and pid_row[0] and _process_alive(pid_row[0]))
                if alive:
                    db.execute("UPDATE jobs SET state='BLOCKED_REVIEW',lease_token=NULL,"
                               "error_code='INTERRUPTED_LOCAL_CANCEL_UNCONFIRMED' WHERE job_id=?", (job_id,))
                    blocked += 1
                else:
                    db.execute("UPDATE jobs SET state='CANCELLED',lease_token=NULL,"
                               "error_code='STOPPED_BY_RESTART' WHERE job_id=?", (job_id,))
            elif provider_task_id and not cancel_requested:
                db.execute("UPDATE jobs SET state='QUEUED',resume_only=1,lease_token=NULL "
                           "WHERE job_id=?", (job_id,))
                resumed += 1
            else:
                db.execute("UPDATE jobs SET state='BLOCKED_REVIEW',lease_token=NULL,"
                           "error_code='INTERRUPTED_UNCERTAIN_SIDE_EFFECT' WHERE job_id=?", (job_id,))
                blocked += 1
    return {"resume_existing_provider_task": resumed, "blocked_uncertain_operation": blocked}
