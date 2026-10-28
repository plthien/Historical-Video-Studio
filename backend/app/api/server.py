"""A1 local FastAPI endpoints. Later-owner routes fail explicitly instead of pretending to work."""
from __future__ import annotations

import hashlib
import json
import base64
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.imports import import_story
from backend.app.projects.models import StoryCandidate
from backend.app.contracts import ContractViolation
from backend.app.jobs import JobQueue, recover_interrupted
from backend.app.projects.gates import GateService
from backend.app.projects.numeric_series import NumericSeries
from backend.app.projects.storage import ProjectStore
from backend.app.voice.attempts import VoiceService
from backend.app.voice.workflow import FinalVoiceWorkflow
from backend.app.api.voice import mount as mount_voice
from backend.app.api.assets import mount as mount_assets
from backend.app.api.storyboard import mount as mount_storyboard
from backend.app.api.delivery import mount as mount_delivery
from backend.app.render import DeliveryService


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=4)
    language: str = "en"
    style_id: str = "HistoryEditorialPaper.v1"


class ClaimReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    status: str
    evidence_note: str = Field(min_length=1)
    source_url: str | None = None


class ScriptEdit(BaseModel):
    """One bounded change to an existing narration section; no G1 fact changes."""
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    narration: str = Field(min_length=1, max_length=100000)
    reason: str = Field(min_length=1, max_length=2000)


class NumericObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_offset: int = Field(ge=0)
    value: str
    source_evidence_sha256: str


class NumericEvidenceUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    content_base64: str = Field(min_length=1, max_length=7_000_000)
    source_url: str = Field(pattern=r"^https?://", max_length=2048)
    review_note: str = Field(min_length=8, max_length=2000)


class NumericSeriesBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    series_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,63}$")
    operator_reason: str = Field(min_length=8, max_length=2000)


class NumericSeriesRevocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    operator_reason: str = Field(min_length=8, max_length=2000)


class NumericSeriesApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    series_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{2,63}$")
    frozen_story_sha256: str
    g1_approval_id: str
    unit: str = Field(min_length=1, max_length=32)
    precision: int = Field(ge=0, le=6)
    authored_duration_frames: int = Field(gt=0, le=100000)
    start_value: str
    end_value: str
    observations: list[NumericObservation] = Field(min_length=3, max_length=500)
    operator_reason: str = Field(min_length=8, max_length=2000)


class GateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    candidate_sha256: str
    dependency_fingerprint: str
    expected_revision: int = Field(ge=0)
    comment: str = ""
    affected_ids: list[str] = Field(default_factory=list)


def create_app(database: str | Path | None = None, media_root: str | Path | None = None) -> FastAPI:
    db_file = Path(database or os.getenv("HVS_DB", "data/historical-studio.sqlite"))
    media = Path(media_root or os.getenv("HVS_MEDIA", "data/media"))
    store = ProjectStore(db_file, media)
    gates = GateService(store)
    numeric_series = NumericSeries(store)
    queue = JobQueue(store)
    voice_service = VoiceService(store, gates, queue)
    final_voice = FinalVoiceWorkflow(store, gates, queue)
    delivery = DeliveryService(store, queue)
    with store._connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS api_requests (
                project_id TEXT NOT NULL, route_key TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('PENDING','DONE')),
                result_json TEXT,
                PRIMARY KEY(project_id,route_key,idempotency_key)
            );
        """)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        import asyncio
        application.state.recovery = recover_interrupted(queue)
        # Dispatch persisted work by its existing durable ID. Each handler must
        # still win JobQueue.claim(), which remains the sole execution lease.
        with store._connection() as db:
            queued_glabs = [row[0] for row in db.execute(
                "SELECT job_id FROM jobs WHERE kind='glabs_image' AND state='QUEUED' "
                "AND cancel_requested=0")]
            queued_renders = [row[0] for row in db.execute(
                "SELECT job_id FROM jobs WHERE kind='final_render' AND state='QUEUED' "
                "AND cancel_requested=0")]
            queued_assemblies = [row[0] for row in db.execute(
                "SELECT job_id FROM jobs WHERE kind='final_assembly' AND state='QUEUED' "
                "AND cancel_requested=0")]

        async def run_persisted(kind: str, job_id: str, operation):
            try:
                result = await asyncio.to_thread(operation, job_id)
                application.state.startup_job_outcomes[(kind, job_id)] = result
            except Exception as exc:
                # Keep the exception visible for diagnostics. Owners persist
                # their job outcome before returning/raising.
                application.state.startup_job_outcomes[(kind, job_id)] = {
                    "state": "DISPATCH_FAILED", "error": type(exc).__name__
                }

        application.state.startup_job_outcomes = {}
        tasks = [asyncio.create_task(run_persisted("glabs_image", job_id,
                                                   application.state.run_glabs_job))
                 for job_id in queued_glabs if hasattr(application.state, "run_glabs_job")]
        tasks.extend(asyncio.create_task(run_persisted("final_render", job_id,
                                                       application.state.delivery.process))
                     for job_id in queued_renders)
        tasks.extend(asyncio.create_task(run_persisted("final_assembly", job_id,
                                                       application.state.final_voice.process_pending))
                     for job_id in queued_assemblies)
        application.state.startup_job_tasks = tasks
        try:
            yield
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

    app = FastAPI(title="Historical Video Studio Local API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173",
                                                       "http://127.0.0.1:5174", "http://localhost:5174"],
                       allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH"],
                       allow_headers=["Content-Type", "Idempotency-Key"])
    app.state.store, app.state.gates, app.state.queue = store, gates, queue
    app.state.voice = voice_service
    app.state.final_voice = final_voice
    app.state.delivery = delivery

    @app.exception_handler(ContractViolation)
    async def violation(_request: Request, exc: ContractViolation):
        if "CONFLICT" in exc.code or exc.code in ("GATE_ILLEGAL_TRANSITION", "JOB_RETRY_FORBIDDEN", "IDEMPOTENCY_IN_PROGRESS", "G4_DRAFT_STALE"):
            status = 409
        elif exc.code in ("STORY_NOT_FOUND", "CANDIDATE_NOT_READY", "WORD_MAP_STALE", "G4_SOURCE_STALE", "G4_DRAFT_UNREGISTERED", "G3_ASSET_UNAPPROVED", "PLAYER_PREVIEW_UNAVAILABLE",
                               "G1_APPROVAL_REQUIRED", "VOICE_STORY_STALE", "VOICE_SOURCE_STALE",
                                "FINAL_AUDIO_SOURCE_STALE", "FINAL_AUDIO_SELECTION_INCOMPLETE",
                                "NUMERIC_SERIES_UNVERIFIED", "NUMERIC_SERIES_SOURCE_STALE",
                                "G4_APPROVAL_REQUIRED", "G5_APPROVAL_REQUIRED", "G5_REVIEW_REQUIRED"):
            status = 424
        elif exc.code in ("PROJECT_NOT_FOUND", "JOB_NOT_FOUND", "CLAIM_NOT_FOUND",
                               "VOICE_SECTION_NOT_FOUND", "VOICE_ATTEMPT_NOT_FOUND", "NUMERIC_SERIES_NOT_FOUND",
                               "RENDER_JOB_NOT_FOUND"):
            status = 404
        else:
            status = 422
        return JSONResponse(status_code=status, content=exc.as_problem())

    def idempotent(project_id: str, route: str, key: str, body: dict, operation):
        if len(key) < 12:
            raise ContractViolation("IDEMPOTENCY_KEY_INVALID", project_id, "Provide Idempotency-Key >= 12 chars.")
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with store._transaction() as db:
            row = db.execute(
                "SELECT payload_sha256,state,result_json FROM api_requests "
                "WHERE project_id=? AND route_key=? AND idempotency_key=?",
                (project_id, route, key)
            ).fetchone()
            if row is not None:
                if row[0] != digest:
                    raise ContractViolation("IDEMPOTENCY_CONFLICT", project_id, "A different payload used this key.")
                if row[1] == "DONE":
                    return json.loads(row[2])
                raise ContractViolation("IDEMPOTENCY_IN_PROGRESS", project_id,
                                        "Operation may still be in progress. Never double-submit.")
            db.execute("INSERT INTO api_requests VALUES(?,?,?,?,'PENDING',NULL)",
                       (project_id, route, key, digest))
        # If the process dies after mutation but before DONE, leave PENDING rather than replaying.
        try:
            result = operation()
        except ContractViolation:
            # Known validation/transaction rejection cannot leave a half-mutated owner transaction.
            with store._transaction() as db:
                db.execute("DELETE FROM api_requests WHERE project_id=? AND route_key=? "
                           "AND idempotency_key=? AND state='PENDING'",
                           (project_id, route, key))
            raise
        # Unknown crashes remain PENDING and must be reconciled, never replayed.
        with store._transaction() as db:
            db.execute("UPDATE api_requests SET state='DONE',result_json=? "
                       "WHERE project_id=? AND route_key=? AND idempotency_key=?",
                       (json.dumps(result, sort_keys=True), project_id, route, key))
        return result

    @app.get("/api/v1/health")
    def health():
        return {"status": "ready", "scope": "A1", "provider_checks": "NOT_RUN"}

    @app.post("/api/v1/projects", status_code=201)
    def create_project(body: ProjectInput):
        if body.language != "en" or body.style_id != "HistoryEditorialPaper.v1":
            raise ContractViolation("PROJECT_INVALID", "/", "Only English editorial style is supported.")
        project_id = "proj_" + uuid4().hex
        store.create_project(project_id, body.title)
        return {"project_id": project_id, "project_revision": 0, "next_action": "IMPORT_STORY"}

    @app.get("/api/v1/projects/{project_id}")
    def project(project_id: str):
        return {"project_id": project_id, "project_revision": store.revision(project_id),
                "gates": gates.board(project_id)}

    @app.post("/api/v1/projects/{project_id}/story/import")
    async def story_import(project_id: str, request: Request, expected_revision: int,
                           idempotency_key: str = Header(alias="Idempotency-Key")):
        raw = await request.body()
        candidate = StoryCandidate.parse(raw)  # validates duplicate keys, top-level and all crossrefs BEFORE replay
        if candidate.project_id != project_id:
            raise ContractViolation("STORY_PROJECT_MISMATCH", project_id, "Story project_id must match route.")
        return idempotent(project_id, "story-import", idempotency_key,
                          {"candidate_sha256": candidate.sha256, "expected_revision": expected_revision},
                          lambda: import_story(store, candidate.canonical_bytes, expected_revision))

    @app.get("/api/v1/projects/{project_id}/story")
    def get_story(project_id: str):
        story = store.get_story(project_id)
        return {"project_revision": store.revision(project_id),
                "candidate_sha256": story.sha256, "story": story.data(),
                "claim_reviews": gates.reviews(project_id)}

    @app.patch("/api/v1/projects/{project_id}/story/sections/{section_id}")
    def patch_story_section(project_id: str, section_id: str, body: ScriptEdit,
                            idempotency_key: str = Header(alias="Idempotency-Key")):
        # The current StoryPackage is the source of truth; only narration changes.
        # ProjectStore.import_story performs canonical validation, CAS and
        # selective G1/G2/G4/G5 staleness in its existing single transaction.
        def apply():
            source = store.get_story(project_id)
            current = source.data()
            section = next((item for item in current["sections"]
                            if item["section_id"] == section_id), None)
            if section is None:
                raise ContractViolation("STORY_SECTION_NOT_FOUND", section_id,
                                        "Select an existing section of the current StoryPackage.")
            if not body.narration.strip():
                raise ContractViolation("STORY_NARRATION_INVALID", section_id,
                                        "Provide nonempty narration.")
            previous = section["narration"]
            section["narration"] = body.narration
            updated = StoryCandidate.parse(current)
            revision = store.import_story(updated, body.expected_revision)
            return {"project_id": project_id, "section_id": section_id,
                    "previous_story_sha256": source.sha256,
                    "candidate_sha256": updated.sha256,
                    "project_revision": revision,
                    "changed": previous != body.narration,
                    "next_action": "REVIEW_G1" if previous != body.narration else "NONE"}

        return idempotent(project_id, f"story-section:{section_id}",
                          idempotency_key, body.model_dump(), apply)

    @app.post("/api/v1/projects/{project_id}/story/claims/{claim_id}/review")
    def review_claim(project_id: str, claim_id: str, body: ClaimReview,
                     idempotency_key: str = Header(alias="Idempotency-Key")):
        if body.status not in ("REVIEWED", "VERIFIED"):
            raise ContractViolation("CLAIM_REVIEW_INVALID", claim_id, "Explicit review disposition required.")
        payload = body.model_dump()
        return idempotent(project_id, f"claim:{claim_id}", idempotency_key, payload, lambda: {
            "project_revision": gates.review_claim(project_id, claim_id, body.status,
                                                  body.evidence_note, body.expected_revision, body.source_url),
            "claim_id": claim_id, "status": body.status
        })

    @app.get("/api/v1/projects/{project_id}/story/claims/{claim_id}/numeric-series/{series_id}")
    def get_numeric_series(project_id: str, claim_id: str, series_id: str):
        record = numeric_series.get(project_id, claim_id, series_id)
        if record is None:
            raise ContractViolation("NUMERIC_SERIES_NOT_FOUND", series_id, "No reviewed series exists for this claim.")
        return record

    @app.post("/api/v1/projects/{project_id}/story/claims/{claim_id}/numeric-series/bind")
    def bind_numeric_series(project_id: str, claim_id: str, body: NumericSeriesBinding,
                            idempotency_key: str = Header(alias="Idempotency-Key")):
        payload = body.model_dump()
        return idempotent(project_id, f"numeric-bind:{claim_id}", idempotency_key, payload,
                          lambda: numeric_series.bind(project_id, claim_id, body.series_id,
                                                      body.expected_revision, body.operator_reason))

    @app.post("/api/v1/projects/{project_id}/story/claims/{claim_id}/numeric-series/evidence")
    def upload_numeric_evidence(project_id: str, claim_id: str, body: NumericEvidenceUpload,
                                idempotency_key: str = Header(alias="Idempotency-Key")):
        payload = body.model_dump()
        return idempotent(project_id, f"numeric-evidence:{claim_id}", idempotency_key, payload,
                          lambda: numeric_series.attach_evidence(project_id, claim_id, payload))

    @app.post("/api/v1/projects/{project_id}/story/claims/{claim_id}/numeric-series/{series_id}/revoke")
    def revoke_numeric_series(project_id: str, claim_id: str, series_id: str, body: NumericSeriesRevocation,
                              idempotency_key: str = Header(alias="Idempotency-Key")):
        payload = body.model_dump()
        return idempotent(project_id, f"numeric-revoke:{claim_id}:{series_id}", idempotency_key, payload,
                          lambda: numeric_series.revoke(project_id, claim_id, series_id,
                                                        body.expected_revision, body.operator_reason))

    @app.post("/api/v1/projects/{project_id}/story/claims/{claim_id}/numeric-series/approve")
    def approve_numeric_series(project_id: str, claim_id: str, body: NumericSeriesApproval,
                               idempotency_key: str = Header(alias="Idempotency-Key")):
        payload = body.model_dump()
        return idempotent(project_id, f"numeric-series:{claim_id}:{body.series_id}",
                          idempotency_key, payload,
                          lambda: numeric_series.approve(project_id, claim_id, payload))

    @app.get("/api/v1/projects/{project_id}/gates")
    def gate_board(project_id: str):
        return gates.board(project_id)

    @app.post("/api/v1/projects/{project_id}/gates/{gate_id}/decision")
    def gate_decision(project_id: str, gate_id: str, body: GateDecision,
                      background: BackgroundTasks,
                      idempotency_key: str = Header(alias="Idempotency-Key")):
        data = body.model_dump()
        result = idempotent(project_id, f"gate:{gate_id}", idempotency_key, data,
                            lambda: gates.decide(project_id, gate_id, data))
        if gate_id == "G2" and result.get("job_id"):
            # Durable job commit precedes scheduling; recovery owns interrupted jobs.
            background.add_task(final_voice.process_pending, result["job_id"])
        return result

    @app.get("/api/v1/projects/{project_id}/jobs")
    def project_jobs(project_id: str):
        store.revision(project_id)
        rows = queue.list_for_project(project_id)
        with store._connection() as db:
            has_render = bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='render_attempts'").fetchone())
            for row in rows:
                row.pop("payload_json", None)
                row.pop("payload_sha256", None)
                row.pop("lease_token", None)
                row["progress"] = None
                if has_render and row["kind"] == "final_render":
                    progress = db.execute("SELECT progress_frames,total_frames,output_sha256 FROM render_attempts WHERE job_id=?",
                                          (row["job_id"],)).fetchone()
                    if progress:
                        row["progress"] = {"completed": progress[0], "total": progress[1]}
                        row["output_available"] = bool(progress[2])
                row["retry_action"] = (
                    "managed_resume" if row["kind"] == "glabs_image" and row["state"] == "FAILED_RETRYABLE"
                    and not row["cancel_requested"] else
                    "render_retry" if row["kind"] == "final_render" and row["state"] == "FAILED_RETRYABLE" else
                    "voice_alignment_retry" if row["kind"] == "final_alignment" and row["state"] == "FAILED_RETRYABLE" else None)
                row["remediation"] = (
                    "Restore the original provider credentials and reconcile the exact provider task."
                    if row["kind"] == "glabs_image" and row["state"] == "BLOCKED_REVIEW" else
                    "Open Final Video to retry against the current approved G4 timeline."
                    if row.get("retry_action") == "render_retry" else
                    "Open Voice to retry forced alignment against the exact final WAV."
                    if row.get("retry_action") == "voice_alignment_retry" else
                    "Resume the original provider task; this action never submits a replacement paid task."
                    if row.get("retry_action") == "managed_resume" else
                    "Review the persisted error and source approvals before taking another action."
                    if row["error_code"] else None)
        return rows

    @app.get("/api/v1/jobs/{job_id}")
    def job_read(job_id: str):
        return queue.get(job_id)

    @app.post("/api/v1/jobs/{job_id}/cancel")
    def job_cancel(job_id: str, idempotency_key: str = Header(alias="Idempotency-Key")):
        job = queue.get(job_id)
        return idempotent(job["project_id"], f"cancel:{job_id}", idempotency_key, {"job_id": job_id},
                          lambda: app.state.cancel_glabs(job["project_id"],job_id) if job["kind"]=="glabs_image" else queue.cancel(job_id))

    mount_voice(app, voice_service, idempotent, final_voice)
    mount_assets(app, store, gates, queue, idempotent)
    mount_storyboard(app, store, idempotent)
    mount_delivery(app, delivery, idempotent)

    @app.api_route("/api/v1/{remaining:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unavailable(remaining: str):
        return JSONResponse(status_code=501, content={
            "code": "OPERATION_NOT_IMPLEMENTED", "message": "This operation belongs to a later A2/A3/B1–B3 task.",
            "remediation": "Complete its owner task before enabling this workspace action.",
            "retryable": False, "entity_id": remaining, "blocking_gate": None
        })

    # The packaged/one-click application serves the built six-workspace UI
    # from the same local process as the API. Development remains on Vite when
    # frontend/dist does not exist.
    frontend_dist = Path(os.getenv("HVS_FRONTEND_DIST", Path(__file__).parents[3] / "frontend" / "dist"))
    if frontend_dist.joinpath("index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="studio-ui")

    return app


app = create_app()
