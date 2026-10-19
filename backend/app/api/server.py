"""A1 local FastAPI endpoints. Later-owner routes fail explicitly instead of pretending to work."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.imports import import_story
from backend.app.contracts import ContractViolation
from backend.app.jobs import JobQueue
from backend.app.projects.gates import GateService
from backend.app.projects.storage import ProjectStore


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
    queue = JobQueue(store)
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

    app = FastAPI(title="Historical Video Studio Local API", version="1.0.0")
    app.state.store, app.state.gates, app.state.queue = store, gates, queue

    @app.exception_handler(ContractViolation)
    async def violation(_request: Request, exc: ContractViolation):
        if "CONFLICT" in exc.code or exc.code in ("GATE_ILLEGAL_TRANSITION", "JOB_RETRY_FORBIDDEN"):
            status = 409
        elif exc.code in ("STORY_NOT_FOUND", "CANDIDATE_NOT_READY", "WORD_MAP_STALE"):
            status = 424
        elif exc.code in ("PROJECT_NOT_FOUND", "JOB_NOT_FOUND", "CLAIM_NOT_FOUND"):
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
        result = operation()
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
        try:
            obj = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise ContractViolation("STORY_JSON_INVALID", "/", "Submit valid StoryPackage JSON.") from exc
        if obj.get("project", {}).get("project_id") != project_id:
            raise ContractViolation("STORY_PROJECT_MISMATCH", project_id, "Story project_id must match route.")
        return idempotent(project_id, "story-import", idempotency_key,
                          {"payload": obj, "expected_revision": expected_revision},
                          lambda: import_story(store, raw, expected_revision))

    @app.get("/api/v1/projects/{project_id}/story")
    def get_story(project_id: str):
        story = store.get_story(project_id)
        return {"project_revision": store.revision(project_id),
                "candidate_sha256": story.sha256, "story": story.data()}

    @app.post("/api/v1/projects/{project_id}/story/claims/{claim_id}/review")
    def review_claim(project_id: str, claim_id: str, body: ClaimReview,
                     idempotency_key: str = Header(alias="Idempotency-Key")):
        if body.status not in ("REVIEWED", "VERIFIED"):
            raise ContractViolation("CLAIM_REVIEW_INVALID", claim_id, "Explicit review disposition required.")
        payload = body.model_dump()
        return idempotent(project_id, f"claim:{claim_id}", idempotency_key, payload, lambda: {
            "project_revision": gates.review_claim(project_id, claim_id, body.status,
                                                  body.evidence_note, body.expected_revision),
            "claim_id": claim_id, "status": body.status
        })

    @app.get("/api/v1/projects/{project_id}/gates")
    def gate_board(project_id: str):
        return gates.board(project_id)

    @app.post("/api/v1/projects/{project_id}/gates/{gate_id}/decision")
    def gate_decision(project_id: str, gate_id: str, body: GateDecision,
                      idempotency_key: str = Header(alias="Idempotency-Key")):
        data = body.model_dump()
        return idempotent(project_id, f"gate:{gate_id}", idempotency_key, data,
                          lambda: gates.decide(project_id, gate_id, data))

    @app.get("/api/v1/projects/{project_id}/jobs")
    def project_jobs(project_id: str):
        store.revision(project_id)
        return queue.list_for_project(project_id)

    @app.get("/api/v1/jobs/{job_id}")
    def job_read(job_id: str):
        return queue.get(job_id)

    @app.post("/api/v1/jobs/{job_id}/cancel")
    def job_cancel(job_id: str, idempotency_key: str = Header(alias="Idempotency-Key")):
        job = queue.get(job_id)
        return idempotent(job["project_id"], f"cancel:{job_id}", idempotency_key, {"job_id": job_id},
                          lambda: queue.cancel(job_id))

    @app.api_route("/api/v1/{remaining:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unavailable(remaining: str):
        return JSONResponse(status_code=501, content={
            "code": "OPERATION_NOT_IMPLEMENTED", "message": "This operation belongs to a later A2/A3/B1–B3 task.",
            "remediation": "Complete its owner task before enabling this workspace action.",
            "retryable": False, "entity_id": remaining, "blocking_gate": None
        })

    return app


app = create_app()
