"""B3-01..03 thin HTTP surface over the durable delivery owner."""
from __future__ import annotations

import json

from fastapi import BackgroundTasks, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.app.contracts import ContractViolation


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RenderStart(Strict):
    expected_revision: int = Field(ge=0)
    codec: str = "h264"
    container: str = "mp4"


class RenderRetry(Strict):
    expected_revision: int = Field(ge=0)
    approved_timeline_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    codec: str
    container: str


class ReviewHeartbeat(Strict):
    nonce: str = Field(min_length=16)
    position_seconds: float = Field(ge=0)
    playing_with_audio: bool


class ReviewComplete(Strict):
    nonce: str = Field(min_length=16)


class FinalExport(Strict):
    expected_revision: int = Field(ge=0)
    gate_g5_approval_id: str = Field(min_length=3, max_length=64)
    render_job_id: str = Field(min_length=3, max_length=64)
    include_attribution: bool


def mount(app, service, idempotent):
    @app.post("/api/v1/projects/{project_id}/render-jobs", status_code=202)
    def start_render(project_id: str, body: RenderStart, background: BackgroundTasks,
                     key: str = Header(alias="Idempotency-Key", min_length=12)):
        if body.codec != "h264" or body.container != "mp4":
            raise ContractViolation("RENDER_FORMAT_UNSUPPORTED", project_id,
                                    "V1 delivery is H264 in MP4.", blocking_gate="G4")
        result = service.submit(project_id, body.expected_revision, key)
        if result["state"] == "QUEUED": background.add_task(service.process, result["render_job_id"])
        return result

    @app.get("/api/v1/projects/{project_id}/render-jobs/{render_job_id}")
    def render_job(project_id: str, render_job_id: str):
        return service.read(project_id, render_job_id)

    @app.post("/api/v1/projects/{project_id}/render-jobs/retry", status_code=202)
    def retry_render(project_id: str, body: RenderRetry, background: BackgroundTasks,
                     key: str = Header(alias="Idempotency-Key", min_length=12)):
        with service.store._connection() as db:
            row = db.execute("SELECT r.job_id FROM render_attempts r JOIN jobs j ON j.job_id=r.job_id "
                             "WHERE j.project_id=? AND json_extract(j.payload_json,'$.render_input_manifest_sha256')="
                             "r.manifest_sha256 AND j.state='FAILED_RETRYABLE' ORDER BY j.rowid DESC LIMIT 1",
                             (project_id,)).fetchone()
        if not row:
            raise ContractViolation("JOB_RETRY_FORBIDDEN", project_id,
                                    "No retryable render exists for this project.", blocking_gate="G4")
        result = idempotent(project_id, "render-retry:" + row[0], key, body.model_dump(),
                            lambda: service.retry(project_id, row[0], body.model_dump()))
        background.add_task(service.process, row[0])
        return result

    @app.get("/api/v1/projects/{project_id}/attributions")
    def attributions(project_id: str):
        with service.store._connection() as db:
            row = db.execute("SELECT r.attribution_sha256 FROM render_attempts r JOIN jobs j ON j.job_id=r.job_id "
                             "WHERE j.project_id=? AND j.state='SUCCEEDED' AND r.qc_status='PASS' "
                             "ORDER BY j.rowid DESC LIMIT 1", (project_id,)).fetchone()
        if not row:
            raise ContractViolation("ATTRIBUTION_NOT_READY", project_id,
                                    "Complete a current render and QC first.", blocking_gate="G5")
        return json.loads(service.store.get_artifact(row[0]))

    @app.get("/api/v1/projects/{project_id}/render-jobs/{render_job_id}/media")
    def review_media(project_id: str, render_job_id: str):
        row = service.read(project_id, render_job_id)
        if row["state"] != "SUCCEEDED" or row["qc_status"] != "PASS":
            raise ContractViolation("RENDER_MEDIA_NOT_READY", render_job_id,
                                    "Only the exact QC-passed MP4 can be reviewed.", blocking_gate="G5")
        # Inline range-capable response for the actual review player. Approved
        # export downloads use the separate attachment endpoint below.
        return FileResponse(service.store.artifacts.path(row["output_sha256"]), media_type="video/mp4")

    @app.post("/api/v1/projects/{project_id}/render-jobs/{render_job_id}/review-sessions")
    def start_review(project_id: str, render_job_id: str,
                     key: str = Header(alias="Idempotency-Key", min_length=12)):
        return idempotent(project_id, "g5-review-start:" + render_job_id, key,
                          {"render_job_id": render_job_id},
                          lambda: service.start_review(project_id, render_job_id))

    @app.post("/api/v1/projects/{project_id}/review-sessions/{session_id}/heartbeat")
    def review_heartbeat(project_id: str, session_id: str, body: ReviewHeartbeat):
        return service.review_heartbeat(project_id, session_id, body.nonce,
                                        body.position_seconds, body.playing_with_audio)

    @app.post("/api/v1/projects/{project_id}/review-sessions/{session_id}/complete")
    def complete_review(project_id: str, session_id: str, body: ReviewComplete,
                        key: str = Header(alias="Idempotency-Key", min_length=12)):
        return idempotent(project_id, "g5-review-complete:" + session_id, key, body.model_dump(),
                          lambda: service.complete_review(project_id, session_id, body.nonce))

    @app.post("/api/v1/projects/{project_id}/delivery/export")
    def export(project_id: str, body: FinalExport,
               key: str = Header(alias="Idempotency-Key", min_length=12)):
        # The owner table is itself unique/idempotent. Revalidate on every call
        # so a previously cached HTTP replay can never bypass later G4/G5 staleness.
        return service.export(project_id, body.model_dump())

    @app.get("/api/v1/projects/{project_id}/delivery/artifacts/{artifact_id}")
    def artifact(project_id: str, artifact_id: str):
        with service.store._connection() as db:
            row = db.execute("SELECT mp4_artifact_id,credits_artifact_id,manifest_artifact_id "
                             "FROM delivery_exports WHERE project_id=? AND ? IN "
                             "(mp4_artifact_id,credits_artifact_id,manifest_artifact_id)",
                             (project_id, artifact_id)).fetchone()
        if not row:
            raise ContractViolation("DELIVERY_ARTIFACT_FORBIDDEN", artifact_id,
                                    "Download only an artifact from this project's approved export.", blocking_gate="G5")
        media = "video/mp4" if artifact_id == row[0] else "application/json"
        suffix = ".mp4" if media == "video/mp4" else ".json"
        return FileResponse(service.store.artifacts.path(artifact_id), media_type=media,
                            filename=artifact_id + suffix)
